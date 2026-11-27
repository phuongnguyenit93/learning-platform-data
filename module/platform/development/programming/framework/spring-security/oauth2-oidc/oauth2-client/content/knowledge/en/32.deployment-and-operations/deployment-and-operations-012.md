# 32.12. Safe Procedures for Changing Providers or Client Configuration

## 1. Context: A Small Configuration Change Can Shift Trust Boundaries

In **Spring Security OAuth 2.0 OIDC Client**, the `ClientRegistration` and OpenID Provider (OP) configuration determine **whom the application trusts to authenticate users**, **which tokens it accepts**, **which callback endpoints are valid**, **which API permissions are requested**, and **which identity is bound to an internal account**.

A request to “switch the SSO provider,” “rotate the client secret,” “update the issuer URI,” “add a scope,” or “change the callback domain” may sound simple. Yet if deployed without a plan, the application can:

- Hit widespread `invalid_client` errors because the new secret is not yet active on the OP or some pods still hold the old secret.
- Fail to complete callbacks due to `redirect_uri_mismatch`, lost session `state`, or missing PKCE verifiers.
- Reject ID Tokens when the OP rotates JWKS signing keys, changes the issuer, or alters client audiences.
- Create duplicate accounts when `issuer`/`sub` changes, or mistakenly merge two users sharing the same email.
- Call APIs with wrong-audience/wrong-scope tokens, causing `401 invalid_token` or `403 insufficient_scope`.
- Render existing Refresh Tokens unusable after changing the client ID.
- Accidentally delete authorized clients belonging to another provider during migration cleanup.
- Trigger login loops, incomplete logouts, or partial session loss during a rolling deployment.

Example old configuration:

~~~text
registrationId = corporate
issuer         = https://id-old.example.net/realms/workforce
clientId       = portal-web
redirectUri    = https://portal.example.net/login/oauth2/code/corporate
~~~

New requirement:

~~~text
issuer         = https://id-new.example.net/realms/workforce
clientId       = portal-web-v2
redirectUri    = https://portal.example.net/login/oauth2/code/corporate-v2
~~~

**Do not simply replace three strings and deploy to all instances.** Changing an issuer and client ID can be an **identity/authorization migration**, not merely a domain swap.

### Lesson Objectives

After this lesson, you will be able to:

1. Classify changes to `issuer`, client registrations, secrets/keys, endpoints, redirects, scopes, claims, UserInfo, token stores, and logout.
2. Identify blast radius and the **security invariants** that must hold.
3. Plan preparation, testing, canarying, cutover, rollback, and post-change verification.
4. Use **dual ClientRegistration** when migrating providers or client IDs without breaking existing flows.
5. Rotate Client Secrets, private keys, mTLS certificates, and JWKS signing keys in the right sequence.
6. Preserve `state`/PKCE/nonce, session, token lifecycle, tenant, and account-linking boundaries.
7. Operate safely in both Spring Security Servlet and WebFlux/Reactive.

> **Scope:** examples use Spring Boot/Spring Security OAuth2 Client/OIDC Login with Authorization Code + PKCE, Refresh Token, and Client Credentials where appropriate. APIs and starter names may differ between Spring Boot 3.x/4.x and Spring Security 6.x/7.x; cross-check your BOM, OP contract, and deployment environment. URLs, IDs, and secret names are placeholders.

## 2. Map of Affected Boundaries

~~~mermaid
flowchart TD
    A["Browser / RP application"] --> B["Spring Security OAuth2 Login"]
    B --> C["Trusted ClientRegistration"]
    C --> D["Issuer + OIDC Discovery"]
    D --> E["Authorization redirect + state + PKCE"]
    E --> F["Token Endpoint"]
    F --> G["ID Token: signature + iss + aud + nonce + exp"]
    G --> H["External identity: issuer + subject"]
    H --> I["Internal account + tenant membership"]
    F --> J["Access + Refresh Tokens"]
    J --> K["Authorized Client Store"]
    K --> L["Resource Server audience + scopes"]
    B --> M["RP session / OP logout / revocation"]
~~~

### 2.1. Security Invariants

| Code | Invariant | What Must Not Be Done |
| --- | --- | --- |
| S1 | Trusted issuer | Dynamically fetch issuer/JWKS from browser-supplied URLs |
| S2 | ID Token validation | Skip signature, `iss`, `aud`, `exp`, or `nonce` checks when required |
| S3 | Request correlation | Disable `state`/PKCE to make callbacks “pass easily” |
| S4 | Identity separation | Use email or raw `sub` as a global user ID |
| S5 | Token isolation | Send registration A's tokens to provider/API B |
| S6 | Least privilege | Escalate scopes or substitute a machine admin token for a user token |
| S7 | Tenant integrity | Treat an OP claim as tenant membership without policy checks |
| S8 | Secret handling | Log client secrets, Access/Refresh Tokens, codes, or private keys |
| S9 | Recoverability | Revoke old secrets before verifying rollback/forward-fix readiness |
| S10 | Change evidence | Close a change after a single HTTP 200 without negative-path tests |

If a boundary must change intentionally—such as migrating an issuer—create an **approved migration plan**, rather than “temporarily relaxing” validators.

## 3. Classifying Changes by Risk Level

| Change Type | Primary Impact | Typically Suitable Strategy |
| --- | --- | --- |
| Rotate `client-secret`, same client ID | Token Endpoint client authentication | Overlapping secrets if the OP supports it |
| Rotate `private_key_jwt` key | Client assertion signature, JWK registration | Overlapping keys and staged rollout |
| Rotate mTLS certificate/key | Client authentication, token binding | Certificate overlap and trust validation |
| Rotate OP signing keys/JWKS | ID Token verification | Provider-controlled JWKS rollover |
| Change `client-id` | ID Token audience, consent, Refresh Token binding | New registration + reauthorization |
| Change `issuer-uri` | Trust boundary and external identity namespace | Migration + explicit identity mapping |
| Change Authorization/Token Endpoint | Browser/token routing, TLS, network | Verify trusted metadata + canary |
| Change `redirect-uri`/public domain | Callback, cookie, state/PKCE | Dual callback transition |
| Add/remove scopes | Consent, token scopes, API permissions | User/admin consent workflow |
| Change claims/role mapper | Internal authorization, tenant rights | Claim schema + negative tests |
| Change UserInfo Endpoint | Profile claims, `sub` equality | Metadata + UserInfo validation |
| Change logout endpoints | RP/OP sessions, back-channel registry | OP capability + session tests |
| Change token/session store | Persistence, refresh, multi-node behavior | Data compatibility/migration |
| Upgrade Spring Security | Defaults, filter chain, managers/handlers | Compatibility + integration tests |

**Note:** a change involving only a secret for the same client may have less impact on user sessions than changing the issuer, but if a secret has leaked, it is a **security incident** rather than routine maintenance.

## 4. End-to-End Workflow from Proposal to Closure

~~~mermaid
flowchart TD
    A["Create change request"] --> B["Inventory + risk assessment"]
    B --> C{"Issuer/client ID/identity change?"}
    C -->|Yes| D["Dual registration + account migration design"]
    C -->|No| E["Credential/config rotation design"]
    D --> F["Staging + mock OP + provider sandbox tests"]
    E --> F
    F --> G{"Security and integration tests pass?"}
    G -->|No| H["Fix design; do not deploy"]
    H --> F
    G -->|Yes| I["Approval + canary + rollback plan"]
    I --> J["Progressive release"]
    J --> K["Observe authentication, token, API, logout"]
    K --> L{"SLOs and invariants hold?"}
    L -->|No| M["Stop; rollback or forward-fix/contain"]
    L -->|Yes| N["Expand cohort and cutover"]
    N --> O["Retire old registrations/credentials safely"]
    O --> P["Post-change verification and audit"]
~~~

Operational phases:

1. **Prepare:** identify actors, change type, environments, and blast radius.
2. **Design:** choose in-place rotation, dual registration, or issuer/account migration.
3. **Validate:** run protocol, browser, API, session, and authorization tests.
4. **Stage:** prepare OP configuration / secret manager while preserving support for existing flows.
5. **Canary:** enable for approved users/tenants and monitor against baseline.
6. **Cutover:** ramp up traffic under control.
7. **Finalize:** revoke old secrets and remove old routes/issuer trust only once exit criteria are met.
8. **Post-change:** retain evidence, restore baseline logging, and update runbooks.

## 5. What Should a Change Request Contain?

Example operational request **without secrets**:

~~~yaml
change_id: OIDC-CHANGE-EXAMPLE
application: portal
environment: production
owner_team: identity-platform
change_type: client-secret-rotation
affected_registration_ids:
  - corporate
old_provider_alias: corporate-op
new_provider_alias: corporate-op
issuer_change: false
client_id_change: false
overlap_supported: pending_confirmation
expected_user_action: none_if_provider_contract_allows
rollback_condition: invalid_client_above_baseline
secret_material_in_ticket: false
~~~

This is an illustrative template only, not a file to create during Markdown authoring.

### 5.1. Roles

| Role | Responsibilities |
| --- | --- |
| Application owner | Login/authorization/tenant flows |
| IAM/Identity team | OP client registration, scopes, secrets/keys, consent |
| Security | Trust boundaries, compromised credentials, approvals |
| Platform/SRE | Deployment, proxy/TLS, session/cache, monitoring |
| Data/Account team | External identity linking, schemas, and migrations |
| Product/Support | Re-login, consent, and user-impact communications |
| Provider support | Confirming rotation, issuer, endpoints, outage semantics |

Not every change requires the exact same approval path, but **changing an issuer, client ID, or identity mapping** is high-risk and must have clear ownership.

## 6. Inventory Every Dependency Before Making Changes

Do not search only `application.yml`. Configuration can come from Java beans, secret managers, dynamic registration databases, API gateways, or custom provider adapters.

### 6.1. Inventory

| Component | What to Document |
| --- | --- |
| `ClientRegistrationRepository` | List of registration IDs, issuers/client IDs |
| OP metadata | Authorization/Token/JWKS/UserInfo/logout/revocation endpoints |
| Secret manager | Secret/key versions and consumers |
| Callback routes | Registered URIs, public hosts, proxy prefixes |
| Security chains | Servlet/Reactive matchers, login callbacks |
| `OidcUserService` | Custom UserInfo/claim enrichment |
| `GrantedAuthoritiesMapper` | Trusted issuer/role/group mapping |
| Identity DB | Unique `issuer+sub` key, pairwise `sub` semantics |
| Token store | JDBC/Redis/session, encryption, and retention |
| Refresh jobs | Non-request manager, system principal, concurrency |
| Resource Servers | Trusted issuers, audiences, and API scopes |
| RP/OP Logout | End-session endpoint, Back-Channel session registry |
| Session store | Redis/JDBC, cookies, TTL, cross-node compatibility |
| Monitoring | Login, token, API, logout, and incident dashboards |
| Rollback plan | Whether the old secret/endpoint remains valid |

### 6.2. Pre-Deploy Baseline

Collect baseline metrics prior to the change per provider/registration:

- Login success/failure counts and authorization callback latency.
- `redirect_uri_mismatch`, `state` mismatch / login loops.
- Token Endpoint `invalid_client`, `invalid_grant`, 429/503.
- ID Token `iss`/`aud`/signature/`kid` failures.
- UserInfo 401/403 and `sub` mismatches.
- Authorized client refresh failures/races.
- Resource Server `401 invalid_token` and `403 insufficient_scope`.
- OIDC logout failures and session invalidation behavior.
- Provider latency/rate limits and authentication SLOs.

Go/no-go thresholds should rest on **actual baselines and SLOs**, not an arbitrary universal number.

## 7. Verifying Discovery Metadata and Provider Trust Contracts

An OIDC OP may publish:

~~~json
{
  "issuer": "https://id.example.net",
  "authorization_endpoint": "https://id.example.net/authorize",
  "token_endpoint": "https://id.example.net/token",
  "jwks_uri": "https://id.example.net/jwks",
  "userinfo_endpoint": "https://id.example.net/userinfo",
  "end_session_endpoint": "https://id.example.net/connect/endsession",
  "scopes_supported": ["openid", "profile", "email"]
}
~~~

URLs are illustrative; in practice, several metadata fields are optional. Do not invent `/logout`, `/userinfo`, or `/revoke` by appending paths when the OP does not publish them or no contract exists.

| Field | Meaning When Changed |
| --- | --- |
| `issuer` | Trust boundary for ID Tokens and external identities |
| `authorization_endpoint` | Browser login redirect target |
| `token_endpoint` | Code/refresh exchange and client authentication |
| `jwks_uri` | OP signing keys used to verify ID Tokens |
| `userinfo_endpoint` | UserInfo claims and subject binding |
| `token_endpoint_auth_methods_supported` | Basic/Post/`private_key_jwt`/mTLS |
| `scopes_supported` | Scopes advertised by OP, not guaranteed granted |
| `code_challenge_methods_supported` | PKCE `S256` and compatibility |
| `end_session_endpoint` | RP-Initiated Logout when supported |
| `revocation_endpoint` | RFC 7009 token revocation when supported |
| `backchannel_logout_supported` | Back-Channel Logout capability |

### 7.1. Endpoint Changes While Issuer Stays Unchanged

A provider may change its Token Endpoint hostname while keeping the same issuer. This is not necessarily an identity migration, yet you must verify metadata was fetched from the **trusted issuer** and that the new endpoint belongs to an approved domain/certificate. Never let operators or client inputs arbitrarily override the Token Endpoint, or Access/Refresh Tokens could be sent to an attacker's host.

### 7.2. Never Trust an Issuer from a User-Supplied URL

~~~text
POST /connect?issuer=https://attacker.example
  -> App fetches Discovery/JWKS operated by attacker
  -> App accepts ID Token self-signed by attacker
~~~

This is a trust-confusion / SSRF risk. Production providers must belong to an allowlist / approved onboarding flow, never automatically trusting arbitrary OIDC endpoints.

## 8. Choosing a Strategy: In-Place Update or Dual Registration?

### 8.1. In-Place

Usually appropriate when:

- Issuer, client ID, identity semantics, and callback routes **do not change**.
- Only credential versions change, and the OP supports overlap/rotation per contract.
- A rollback path exists using a still-valid credential.
- In-flight login sessions are not broken.

### 8.2. Dual Registration

Consider when:

- Changing the issuer, client ID, or redirect URI.
- Canarying by tenant/user is needed.
- Consents or Refresh Tokens from the old client cannot carry over to the new client.
- Legacy callbacks are still in flight.
- Secure identity migration / account linking is required.

~~~text
Old registration:
  corporate-old -> issuer A, client portal-v1

New registration:
  corporate-new -> issuer B, client portal-v2

Transition:
  old flows are still allowed to complete per policy
  canary cohort uses new registration
  identity account mapping is verified explicitly
~~~

**Do not interpret dual registration as permission to merge `(issuerA, subX)` and `(issuerB, subX)`.** Issuer boundaries remain distinct.

## 9. Example Spring Boot Configuration for Two Registrations

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate-old:
            provider: old-oidc
            client-id: ${OLD_OIDC_CLIENT_ID}
            client-secret: ${OLD_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          corporate-new:
            provider: new-oidc
            client-id: ${NEW_OIDC_CLIENT_ID}
            client-secret: ${NEW_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
        provider:
          old-oidc:
            issuer-uri: https://id-old.example.net/realms/workforce
          new-oidc:
            issuer-uri: https://id-new.example.net/realms/workforce
~~~

This is an illustrative configuration for an **issuer/client migration**, not a prescription to duplicate registrations for every secret rotation. Client secrets come from a protected secret manager/environment—**never commit production secrets in source control**.

### 9.1. Login / Callback Paths

~~~text
/oauth2/authorization/corporate-old
/oauth2/authorization/corporate-new

/login/oauth2/code/corporate-old
/login/oauth2/code/corporate-new
~~~

The OP must register the exact callback matching each client ID. Flows currently logging in via the old registration must be processed with the old flow's configuration and `state`/PKCE.

### 9.2. Servlet SecurityFilterChain

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcWebSecurityConfig {

    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        return http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/login", "/error")
                    .permitAll()
                .anyRequest().authenticated())
            .oauth2Login(oauth2 -> oauth2
                .loginPage("/login"))
            .build();
    }
}
~~~

This is a **standalone** Servlet configuration. Custom `/login` must be implemented. If multiple `SecurityFilterChain` beans exist, verify matchers and ordering so a new chain does not accidentally miss callbacks or bypass protected routes.

### 9.3. Server-Side Registration Selection Rules

~~~java
package com.example.identity;

import java.util.Set;

public final class ApprovedLoginRegistrationPolicy {
    private static final Set<String> APPROVED =
        Set.of("corporate-old", "corporate-new");

    public String chooseForApprovedCohort(boolean canary) {
        return canary ? "corporate-new" : "corporate-old";
    }

    public boolean isApproved(String registrationId) {
        return APPROVED.contains(registrationId);
    }
}
~~~

Here `canary` represents a **trusted server-side rollout flag**, not `?canary=true` sent by the user. Never expose machine Client Credentials registrations on interactive login UIs for callers to pick arbitrarily.

## 10. Changing an Issuer Is an Identity Migration

Fundamental OIDC external identity:

~~~text
(issuer, subject)
~~~

Two records:

~~~text
(https://id-a.example.net, sub=42)
(https://id-b.example.net, sub=42)
~~~

**do not automatically refer to the same person.** Even when emails match and both OPs assert `email_verified=true`, that does not prove the user intends to merge the two accounts.

### 10.1. External Identity Schema

~~~sql
CREATE TABLE external_identity (
    id UUID PRIMARY KEY,
    internal_account_id UUID NOT NULL,
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    registration_id VARCHAR(100) NOT NULL,
    verified_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_external_identity UNIQUE (issuer, subject)
);
~~~

Illustrative schema. For pairwise subjects, multiple client IDs, or multi-tenant semantics, additional client/sector context may be required per contract. Never use email as the unique global identity key.

### 10.2. Pairwise Subjects When Changing Client ID

Even if **the issuer stays the same**, the same person can receive:

~~~text
clientId = portal-web-old -> sub = pairwise-123
clientId = portal-web-new -> sub = pairwise-789
~~~

Never auto-merge `pairwise-123` and `pairwise-789` solely because of a matching email. If linking is needed, use provider-approved correlation or a secure account-linking workflow.

### 10.3. Account-Linking Flow During Migration

1. A user already authenticated with the old identity creates a server-side **migration intent**.
2. Bind the intent to the internal account, initiating session, expected new registration/issuer, and a TTL.
3. The user signs in again through the new OP using a full Authorization Code + `state`/PKCE/nonce flow.
4. The RP verifies the ID Token signature/issuer/audience/nonce and extracts the new subject.
5. Verify the intent is still valid and matches the session/account/provider; perform step-up auth if policy requires.
6. In a database transaction, verify the new identity does not belong to another account, preserving `UNIQUE(issuer, subject)`.
7. Link the new identity to the internal account and emit an audit record.
8. Evaluate tenant roles, authorized clients, and recovery methods before retiring the old identity.

Never run bulk SQL updates replacing `issuer` or `sub` without verifying ownership of each identity.

### 10.4. Two Parallel Callbacks Must Not Mislink Accounts

If a user opens tab A to start the old login and tab B to start new provider linking, callbacks A and B arriving out of order must still match their respective `state`, session, and intent. Never use a global “last selected provider” variable as an authentication source.

## 11. Client Secret Rotation: Correct Order and Fallback Plan

### 11.1. When the OP Supports Secret Overlap

~~~mermaid
sequenceDiagram
    autonumber
    participant IAM as Identity Admin
    participant SM as Secret Manager
    participant RP as Spring Boot Pods
    participant OP as Token Endpoint
    IAM->>OP: Register new secret; old remains valid
    IAM->>SM: Store new secret version
    SM-->>RP: Rollout canary new secret
    RP->>OP: Token exchange with new secret
    OP-->>RP: Success
    IAM->>RP: Progressive rollout all consumers
    RP->>OP: Login/refresh with new secret
    OP-->>RP: Success
    IAM->>OP: Revoke old secret after verification
~~~

Sequence:

1. Inventory every workload using the client secret: web apps, scheduled jobs, workers, emergency tools.
2. Verify the OP **genuinely supports multiple concurrent secrets**.
3. Create the new secret on the OP and store it in the secret manager with proper access controls.
4. Test Token Endpoint authentication in staging and canary.
5. Progressively roll out to all instances while monitoring `invalid_client` and refresh failures.
6. Revoke the old secret only after confirming zero consumers still rely on it, or once rollback risk is accepted.
7. Retire old secret references per retention policy; alert on any attempts still using the old credential.

### 11.2. When the OP Does Not Support Overlap

Zero downtime cannot be promised. Choose among: a brief maintenance window, registering a parallel new client ID, provider-specific atomic rotation, or a communicated degraded mode. Especially with Refresh Token rotation, avoid having two app versions concurrently write tokens in violation of the contract.

### 11.3. Public Clients Cannot Keep Secrets

Never embed confidential client secrets into SPA or mobile source code. For public clients, use Authorization Code + PKCE and appropriate redirect/platform protections. Rotating a “secret” in a public app does not turn it into a confidential client.

## 12. Rotating private_key_jwt, mTLS, and DPoP

| Method | Credential | Checks Required |
| --- | --- | --- |
| `client_secret_basic` / `post` | Client Secret | OP auth method, secret version |
| `private_key_jwt` | Private signing key | Registered JWKs, `kid`, assertion claims/expiry |
| mTLS | Certificate/private key | TLS trust, client binding, expiry |
| DPoP sender-constraining | DPoP key/proof | Key continuity, `htu`/`htm`, nonce/replay |

### 12.1. `private_key_jwt` Key Rotation

Before the client signs assertions with a new key, the OP must know the new public key/JWK via the registration mechanism. Verify `kid`, `aud` (Token Endpoint per provider contract), assertion expiration/clock skew, private-key storage, and key retirement. Never log private keys or raw signed assertions.

### 12.2. mTLS

Rotating an mTLS certificate can impact both **client authentication** and **certificate-bound Access Tokens** when using RFC 8705. Do not swap only an ingress TLS certificate and assume outbound Token Endpoint mTLS rotated too.

### 12.3. DPoP

DPoP (RFC 9449) requires client, OP, and Resource Server to enforce proof/token binding properly. Rotating keys can invalidate existing tokens bound to the old key. Do not merely attach a hand-crafted DPoP header and assume tokens are sender-constrained.

### 12.4. Credential Compromise

If a key/secret leaks, prioritize containment, rotate/revoke at the OP, assess issued tokens/grants, and coordinate incident response. Removing the secret in a newer git commit does not invalidate already exposed copies.

## 13. OP Signing Key / JWKS Rotation Differs from Client Credential Rotation

~~~text
Client secret / private_key_jwt:
  RP authenticates itself to Authorization Server

OP signing key / JWKS:
  RP validates ID Token produced by OpenID Provider
~~~

### 13.1. Normal JWKS Rollover

A provider can publish a new public signing key, start signing tokens with the new `kid`, retain the old key during an overlap window, and then retire it. The RP needs JWKS cache refreshing aligned with trust policy rather than permanently hard-coding a single key.

### 13.2. When a New `kid` Is Missing

Check trusted issuer, JWKS URL, HTTPS/TLS, proxies, cache TTL, key rotation status, and node consistency. Never accept `alg=none`, never skip signature/issuer/audience validation, and never fetch keys from arbitrary attacker-specified JWT `jku`/`x5u` URLs.

### 13.3. Signing Key Compromise

This is an incident, not a normal rollover. Cached compromised keys may be unsafe; follow provider advisories, assess previously issued sessions/tokens, and coordinate a revocation/denylist strategy.

## 14. Changing Scopes: Consent and Resource Servers Must Be Reviewed Together

~~~text
Before: openid profile email
After:  openid profile email reports.read
~~~

Adding `reports.read` does not guarantee all users immediately receive that scope. New user/admin consent, client permission updates, or a fresh authorization request may be required.

### 14.1. Three Things to Distinguish

| Element | Not Equivalent To |
| --- | --- |
| OIDC scopes (`openid`, `profile`, `email`) | Local application roles |
| OAuth2 API scope (`reports.read`) | Portal admin permissions |
| Tenant Alpha's `ROLE_REPORT_VIEWER` | Access to Tenant Beta or other APIs |

### 14.2. Client ID Changes and Offline Access

Refresh Tokens may be bound to the old client. Requesting the `offline_access` scope likewise does not guarantee the OP issues a Refresh Token. After a client ID migration, test reauthorization/refresh against actual provider behavior rather than copying Refresh Token bytes into a new authorized-client record.

### 14.3. Reducing Scopes Also Requires Lifecycle Management

Removing a requested scope in YAML does not automatically revoke already-issued Access Tokens carrying broader permissions. Grant revocation, token TTL/introspection strategies, and authorized client cleanup per policy may be necessary.

## 15. Redirect URI, Domain, Reverse Proxy, and Cookies

Spring Security commonly uses the redirect URI template:

~~~text
{baseUrl}/login/oauth2/code/{registrationId}
~~~

Example:

~~~text
Browser public URL:
  https://portal.example.net

Proxy:
  HTTPS public -> http://app:8080 internal

Correct redirect:
  https://portal.example.net/login/oauth2/code/corporate-new
~~~

If the RP sends `http://app:8080/login/oauth2/code/...`, the OP may reject it.

### 15.1. Forwarded Headers

One Spring Boot option in a trusted proxy topology:

~~~yaml
server:
  forward-headers-strategy: framework
~~~

**Only trust** `Forwarded`/`X-Forwarded-*` headers from trusted proxies, stripping spoofed headers supplied by clients. Trusting an unvalidated `X-Forwarded-Host` can create redirect confusion or open redirects.

### 15.2. Register Callbacks Before Switching Traffic

Register the exact HTTPS callback URI at the OP, verifying path, domain, port, and trailing slash. Never use broad wildcard redirects merely for deployment speed.

### 15.3. In-Flight Logins

A browser may initiate OAuth2 Login under the old registration and only return after MFA. During a rolling deployment, keep compatible callback and authorization request repository support for the old flow when policy/OP allow; never force an old `state`/PKCE across to the new client.

### 15.4. Cookies and SameSite

Changing domain or callback response mode can stop the session cookie from being sent, causing `state` mismatches. Inspect `Secure`, `SameSite`, `Domain`, `Path`, HTTPS, browser cookie exclusion reasons, and session TTL. Callback behavior can differ between `query` and `form_post`.

## 16. Keeping In-Flight Sessions Safe During Rolling Deployments

~~~mermaid
sequenceDiagram
    actor Browser
    participant RP1 as Old Pod
    participant OP as OP
    participant RP2 as New Pod
    Browser->>RP1: Start old login
    RP1-->>Browser: Redirect with state/PKCE
    Browser->>OP: MFA/consent
    Note over RP1,RP2: Rollout begins
    OP-->>Browser: Old callback code/state
    Browser->>RP2: Callback after rollout
    RP2->>RP2: Load compatible old authorization request
    RP2-->>Browser: Safe success or controlled failure
~~~

Items to verify:

- Authorization request storage and `state`/nonce/PKCE verifier.
- Old registration ID remains present for in-flight flows.
- Callback `SecurityFilterChain` matches.
- `HttpSession`/`WebSession` serialization compatibility.
- Cookies/CSRF/session fixation behavior does not change unintentionally.
- Authorized client persistence compatibility across old/new versions.
- Multi-node Redis/JDBC session store and cache consistency.

An RP session from the old issuer does not automatically become an `Authentication` from the new issuer after a config switch; reauthentication or migration is required per policy.

## 17. OAuth2AuthorizedClient and Token Lifecycle

An authorized client typically contains:

~~~text
(ClientRegistration, principalName)
  -> Access Token
  -> Refresh Token (optional)
~~~

Servlet has `OAuth2AuthorizedClientService` and `OAuth2AuthorizedClientRepository`; Reactive has `ReactiveOAuth2AuthorizedClientService` and `ServerOAuth2AuthorizedClientRepository`.

### 17.1. In-Place Secret Rotation for the Same Client

Existing refresh grants **may** continue working if the OP permits the client to authenticate with the new secret. However, there is no universal guarantee across providers; test real login/refresh in a sandbox.

### 17.2. New Client ID / Issuer

Do not assume Access/Refresh Tokens from the old client work with the new client. Reauthorize against the proper provider/registration rather than simply rewriting `registrationId` in a database row.

### 17.3. Local Deletion Differs from Remote Revocation

~~~java
authorizedClientService.removeAuthorizedClient(
    registrationId, principalName);
~~~

This deletes only the entry in the corresponding local store. Token revocation at the Authorization Server requires a separate request/protocol (RFC 7009, if the OP supports it). An HTTP 200 from the revocation endpoint is also returned if a token was already invalid; HTTP 503 means revocation is unconfirmed.

### 17.4. Scope Cleanup Properly

~~~text
AuthorizedClient(A, Alice) -> invalid_grant
AuthorizedClient(B, Alice) -> may still be valid
AuthorizedClient(A, Bob)   -> may still be valid
~~~

Do not wipe all authorized clients because `A`/`Alice` failed. In particular, audit custom success/failure handlers on `OAuth2AuthorizedClientManager` and WebClient OAuth2 filters.

### 17.5. Concurrent Refresh Rotation

~~~text
Pod A: load R1 -> refresh success -> save R2
Pod B: load R1 -> invalid_grant -> deletes R2
~~~

When changing the token store/manager, test optimistic locking/CAS or single-flight refresh. An `invalid_grant` may stem from revocation or a refresh race rather than conclusively proving token theft. Never retry the same invalid token infinitely.

## 18. Claims, UserInfo, and GrantedAuthorities After Changing OPs

| Claim | Migration Risk |
| --- | --- |
| `iss` | Different exact trust namespace |
| `sub` | May change or be pairwise per client |
| `email` | Missing/changed/reassigned; not a global ID |
| `email_verified` | Do not default to true when absent |
| `preferred_username` | Unstable display name |
| `groups`/`roles` | Claim placement/schema/provider policy |
| `tid`/`oid` (Entra) | Provider-specific identifiers |
| `hd` (Google) | Hosted-domain context when required by policy |

OIDC Core requires `sub` in the UserInfo response to **match exactly** the ID Token's `sub`. If they differ, discard the UserInfo claims. Never map a raw `admin` claim from a new OP directly to `ROLE_ADMIN` solely by name similarity; role mapping must follow trusted issuer/schema/tenant policies.

A provider may return groups via a Directory/Graph API instead of UserInfo; that requires dedicated API audience/scope/consent and fail-closed policies if authorization depends on groups.

## 19. Resource Servers Must Be Verified Independently of RP Login

RP login success does not prove the Reports API accepts the new Access Token:

~~~text
RP (OIDC Client)
  -> new issuer Access Token
      -> Reports API (Resource Server)
          verify trusted issuer, audience, expiration,
          scopes, tenant membership and object ownership
~~~

### 19.1. If the Resource Server Only Trusts the Old Issuer

Tokens from the new OP may receive 401. Adding the new issuer to the API allowlist is a separate security change: verify signing keys, audience, scopes, and subject/tenant mapping. **Never disable issuer/audience validation** to suppress errors.

### 19.2. Prepare Resource Servers Before the RP Canary

When necessary, deploy API support/trust for the new token format before migrating users, run negative tests with wrong-issuer/wrong-audience tokens, and only then enable the RP's new registration. Keep the dual-trust window on APIs bounded, with clear criteria to retire the old issuer.

### 19.3. Never Escalate Privileges with a Fallback Token

If a new delegated user token receives `403 insufficient_scope`, never fall back to an admin Client Credentials token to “fix” it. Resolve API consent, roles, and tenant policies properly.

## 20. Logout When Changing OPs

| Mechanism | Scope | What Must Be Tested |
| --- | --- | --- |
| Local RP logout | `HttpSession`/`WebSession` | Browser session invalidated, no state leak |
| RP-Initiated Logout | OP SSO session if supported | `end_session_endpoint`, registered post-logout URI |
| Front-Channel Logout | Browser notification | `SameSite`/iframe/browser restrictions |
| Back-Channel Logout | Signed server-to-server Logout Token | Issuer/audience/`sid`/`sub`/session registry |
| Token revocation | Authorization Server tokens | Correct client/auth endpoint, response handling |

Spring Security Servlet provides `OidcClientInitiatedLogoutSuccessHandler`; Reactive provides `OidcClientInitiatedServerLogoutSuccessHandler`. Never send OP A's `id_token_hint` to OP B's logout endpoint.

An OP `sid` is not the local `JSESSIONID`. Back-Channel Logout requires mapping the OP session/subject to the RP session registry, especially in multi-node environments.

Local logout does not automatically revoke issued JWT Access Tokens. If the product promises “sign out everywhere,” a tested revocation/introspection/session-propagation design is required.

## 21. Operational Differences Between Servlet and Reactive/WebFlux

| Component | Servlet | Reactive |
| --- | --- | --- |
| Security DSL | `HttpSecurity` | `ServerHttpSecurity` |
| Security chain | `SecurityFilterChain` | `SecurityWebFilterChain` |
| Session | `HttpSession` | `WebSession` |
| Client repository | `OAuth2AuthorizedClientRepository` | `ServerOAuth2AuthorizedClientRepository` |
| Client service | `OAuth2AuthorizedClientService` | `ReactiveOAuth2AuthorizedClientService` |
| Request manager | `DefaultOAuth2AuthorizedClientManager` | `DefaultReactiveOAuth2AuthorizedClientManager` |
| Background manager | `AuthorizedClientServiceOAuth2AuthorizedClientManager` | `AuthorizedClientServiceReactiveOAuth2AuthorizedClientManager` |

### 21.1. Reactive SecurityWebFilterChain

~~~java
package com.example.security;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.web.server.SecurityWebFilterChain;

@Configuration
public class ReactiveOidcConfig {

    @Bean
    SecurityWebFilterChain webFilterChain(ServerHttpSecurity http) {
        return http
            .authorizeExchange(auth -> auth
                .pathMatchers("/", "/login", "/error").permitAll()
                .anyExchange().authenticated())
            .oauth2Login(Customizer.withDefaults())
            .build();
    }
}
~~~

This example **replaces** the Servlet chain; do not mix DSLs. In custom reactive token/user services, never invoke blocking JDBC or `RestTemplate` on the event loop. Prefer reactive I/O, or isolate unavoidable blocking calls on `Schedulers.boundedElastic()` with concurrency and timeout bounds.

### 21.2. Do Not Self-Subscribe Inside Reactive Cleanup

~~~java
// ANTI-PATTERN:
reactiveAuthorizedClientService
    .removeAuthorizedClient(id, principal)
    .subscribe();
return Mono.empty();

// BETTER: return the publisher into the request/handler pipeline.
return reactiveAuthorizedClientService
    .removeAuthorizedClient(id, principal);
~~~

Illustrative code fragment without an enclosing class. Calling `.subscribe()` detaches errors, cancellation, and `SecurityContext` from the request and can return the HTTP response before persistence completes.

## 22. Immutable Config, Secret References, and Rolling Deployments

Every release should identify:

~~~text
application-build-id
configuration-version
client-registration-version
secret-manager-reference/version (contains no secret)
trusted-issuer-alias
schema-migration-version
feature-flag-cohort
rollback-artifact
~~~

Never manually edit a single production pod and leave other pods on old configuration without controls. Secrets must be managed in a permissioned, audited secret manager/environment.

### 22.1. Hot Reload Can Create Inconsistent Snapshots

If a dynamic `ClientRegistrationRepository` changes `client-id` or Token Endpoint while an authorization request is in flight, the callback may read the new config alongside `code`/PKCE/redirect from the old config. Use immutable registration snapshots / versioned compatibility or rolling deploys with dual IDs.

### 22.2. Never Fall Back to Hard-Coded Secrets

If KMS or the secret manager is unavailable, affected components should fail closed/degraded per policy and alert—never embed an emergency admin secret in source code.

### 22.3. Secrets Must Never Appear in Logs

Never log `client-secret`, private keys, `Authorization` headers, Access/Refresh/ID Tokens, authorization codes, PKCE verifiers, `state`, or session cookies. DEBUG/TLS/wiretap/CI settings must enforce strict redaction and retention.

## 23. Staging Test Matrix Before Canary

| Area | Positive Case | Negative Case |
| --- | --- | --- |
| Registration | Old/new resolve accurately | Unknown registration ID |
| Authorization | Redirects with valid OP/URI/scope/state/PKCE | Wrong redirect, invalid scope |
| Callback | Code/state/session match | Wrong state, lost session, cross-provider callback |
| Client auth | Token Endpoint accepts new secret | Old/revoked secret, wrong method |
| ID Token | Signature/`iss`/`aud`/nonce/time valid | Wrong issuer, audience, JWKS key |
| UserInfo | `sub` matches ID Token | `sub` mismatch, missing optional claims |
| Account identity | Verified identity maps cleanly | Same email/`sub` cross-issuer collision |
| Tenant/roles | Membership enforced | Role leakage / provider admin confusion |
| API | Token carries valid issuer/`aud`/scope | `401 invalid_token`, `403 insufficient_scope` |
| Token store | Save/load/refresh succeed | Wrong registration/principal, rotation race |
| Browser/session | Cookies/callbacks work across nodes | SameSite/session timeout failure |
| Logout | Local/OP/back-channel succeed | Missing endpoint, wrong-issuer logout token |
| Rollback | Old config/secret still valid | Old secret already revoked |
| Outage | Bounded retry, state preserved | Provider 503 causes mass token wipe |

### 23.1. Mock OIDC Principals Do Not Replace Protocol Integration

`oidcLogin()` in MockMvc and `mockOidcLogin()` in WebTestClient help test app authorization, yet **do not execute real Authorization Code exchange, PKCE, Token Endpoint calls, or JWKS/ID Token signature verification**.

### 23.2. Protocol Tests Need at Least Two OPs

To catch cross-provider confusion, configure mock/test OP A and B with distinct issuers, client IDs, and signing keys:

~~~text
OP A:
  issuer A, client A, key A, JWKS A

OP B:
  issuer B, client B, key B, JWKS B

Test negative:
  ID Token signed by B in OP A flow
  ID Token aud=client B in A flow
  UserInfo sub different from ID Token
  Callback state/code/PKCE of one OP on other route
~~~

Never store production client secrets or real user tokens in test fixtures or CI artifacts.

## 24. Canary Rollout: Cohort Selection and Stopping on Time

### 24.1. Rollout Phases

1. Internal/test accounts against OP test/live sandbox per policy.
2. An approved cohort of users/tenants.
3. Controlled expansion once authentication, API, token, session, and logout metrics match baseline.
4. Keep the old registration for unmigrated flows/users while still valid.
5. Stop and roll back or forward-fix immediately if a boundary violation appears.

### 24.2. Useful Metrics

| Suggested Metric | Why |
| --- | --- |
| `oauth2_login_success_total` per registration | Real sign-ins succeeding |
| `oauth2_token_invalid_client_total` | Misconfigured secret/method rollout |
| `oauth2_invalid_grant_total` | Code, PKCE, Refresh Token errors |
| `oauth2_issuer_audience_fail_total` | Trust mismatch |
| `oauth2_jwks_failure_total` | Signing key/cache issues |
| `oauth2_state_mismatch_total` | Cookie/session/multi-node issues |
| `oauth2_userinfo_subject_mismatch_total` | Token substitution / mix-up |
| `oauth2_api_invalid_token_total` | Resource Server trust mismatch |
| `oauth2_api_insufficient_scope_total` | Granted scope/consent issue |
| `oauth2_refresh_failure_total` | Authorized client lifecycle issues |
| `oauth2_account_link_conflict_total` | Identity migration risk |
| `oauth2_logout_failure_total` | OP/RP logout contract failure |

Never use raw email, `sub`, tokens, `state`, session IDs, or full claim payloads as metric labels.

### 24.3. Stop-the-Line Criteria

Halt rollout immediately if any of the following occur:

- An ID Token with the wrong issuer/audience is accepted.
- Two accounts are merged automatically solely due to matching email or raw `sub`.
- Cross-tenant data leakage or unintended privilege escalation occurs.
- Tokens are sent to the wrong provider or Resource Server host.
- Credentials appear in logs, traces, or CI artifacts.

Availability failures such as rising 503/`invalid_client` may also warrant pausing per SLO, while distinguishing provider outages from security incidents.

## 25. Rollback Must Be Planned Before Cutover

| Action Already Taken | Can Old YAML Roll Back? | Reason |
| --- | --- | --- |
| New secret created, old still valid | Usually yes | Old pods can still authenticate |
| Old secret revoked | **Not straightforward** | Old build lacks valid credentials |
| New client ID granted consent | Does not revert automatically | Tokens/grants are client-bound |
| Issuer migration linked identities | Do not auto-revert mapping | Identity ownership was already verified |
| OP retired a signing key | Should not restore compromised key | Security trust |
| Old callback URI deleted | In-flight flows fail | Requires OP re-registration if permitted |
| Destructive DB schema migration | Possibly no | Code rollback does not restore data |
| Refresh Token rotated | Cannot reuse `R1` | Token family state moved forward |
| User logged into new OP | Does not auto-close new SSO session | OP logout/session differs from RP |

### 25.1. Expand-Contract Schema Migrations

1. **Expand** schema/columns while keeping old app compatibility.
2. **Backfill/verify** identity mappings and record versions.
3. **Switch** readers/writers to the new schema via canary.
4. **Observe** duplicates, nulls, stale records, and account-link conflicts.
5. **Contract** old fields only after the rollback window and data migration finish.

### 25.2. Forward-Fix Can Be Safer Than Rollback

If the old secret was revoked or the old endpoint closed, rolling back the artifact will not resolve the outage. A **forward-fix** is required: issue a new credential, fix endpoint/config on the new version, or adjust token/API trust under approval. The plan must specify when to choose rollback versus forward-fix.

### 25.3. Verify Security Even After Rollback

Do not merely ping `/login`. Verify issuer/audience/signature validation, callback `state`/PKCE, account mapping, tenant permissions, the authorized-client store, API calls, logout, and background jobs.

## 26. Cutover Exit Criteria and Retiring the Old Registration

Retire `corporate-old` only when:

- Required users/tenants have migrated or have a recovery path.
- In-flight old callbacks no longer need processing within the policy window.
- Old tokens/grants have expired/revoked or have a disconnect plan.
- No scheduled jobs still reference the old client secret/registration.
- Old OP sessions and Logout Token / session registries are handled.
- Resource Servers no longer need the old issuer for unexpired tokens, or have an explicit revocation/denylist strategy.
- SLOs, security invariants, and the observation window are approved to close.

**Removing the old registration is the final step**, not the first action right after the new canary scores a single HTTP 200.

## 27. Runbook A — Secret Rotation Causes `invalid_client`

**Symptoms:** Token Endpoint rejects login/refresh; `invalid_client` spikes immediately after rollout.

**Diagnosis:**

1. Are client ID, tenant, and realm correct?
2. Has the new secret been activated on the OP?
3. Did the client auth method change?
4. Are canary pods actually reading the new secret version?
5. Which jobs/regions are still using the old version?

**Recovery:** if the old secret is still valid, roll back the secret reference for the affected cohort and test. If the old secret was revoked, issue a new credential / forward-fix; never log secrets to debug.

## 28. Runbook B — Issuer Change Causes Users to Create New Accounts

**Symptoms:** login on the new OP succeeds, yet the RP cannot find the existing account or creates a duplicate.

**Diagnosis:** compare verified `(oldIssuer, oldSub)` against `(newIssuer, newSub)`, inspecting pairwise subjects and link intents. Never treat a matching email as proof.

**Recovery:** pause the migration cohort, keep the old route if policy permits, and implement verified identity linking/transactions with unique constraints. Never run bulk direct `UPDATE` statements on `issuer`/`sub`.

## 29. Runbook C — Callback Failures After Domain Change

**Symptoms:** the OP reports `redirect_uri_mismatch` or callbacks hit `state` mismatch.

**Diagnosis:** inspect public scheme/host/path, registered redirect URI, trusted forwarded headers, cookies/`SameSite`/`Secure`, session TTL, and multi-node session store.

**Recovery:** restore the exact redirect route / OP allowlist and compatible old callback for in-flight flows; never disable `state`/PKCE checks.

## 30. Runbook D — New JWKS Key Causes ID Token Validation Failures

**Symptoms:** ID Tokens with a new `kid` are rejected, or pods behave inconsistently.

**Diagnosis:** inspect trusted JWKS URL, cache refresh, OP signing key rotation, TLS/proxy, issuer/audience, and clocks.

**Recovery:** update cache/trust per OP metadata and policy; never drop signature validation. If signing-key compromise is suspected, escalate to incident response.

## 31. Runbook E — New Scope Added, Reports API Returns 403

**Symptoms:** login succeeds, yet the API returns `insufficient_scope`.

**Diagnosis:** compare requested vs. actually granted scopes, user/admin consent, token audience, Resource Server policy, and whether an old token was refreshed.

**Recovery:** trigger proper reauthorization/consent and update permissions under least privilege. Never bypass using an admin machine token in place of a user token.

## 32. Runbook F — Refresh Token Rotation Race During Rollout

**Symptoms:** refresh A succeeds `R1->R2`; request B fails with `invalid_grant` and deletes `R2`.

**Diagnosis:** check multiple pods sharing the store, versioned updates/deletes, custom success/failure handlers, and OP token-family policies.

**Recovery:** apply single-flight refresh or CAS/optimistic locking while preserving the newer record; never retry invalid `R1` infinitely.

## 33. Runbook G — Provider 503 During Canary

**Symptoms:** Token Endpoint or UserInfo/JWKS temporarily unavailable; logins/refreshes stall.

**Diagnosis:** identify affected endpoints, regions/tenants, OP incident status, and whether errors are transient.

**Recovery:** pause rollout, keep valid credentials, apply bounded retries with backoff/jitter/`Retry-After` and circuit breakers. If the old OP remains usable within trust policy, retain old traffic; never auto-link identities. Never disable authentication validation to maintain uptime.

## 34. Runbook H — Secret/Key Leaked via Git or Logs

This is an incident:

1. Stop the leak source and restrict access to artifacts/logs.
2. Scope affected clients, tenants, environments, and credential types.
3. Rotate/revoke the compromised credential at both the OP and secret manager.
4. Assess issued tokens/grants for abuse and revoke where appropriate.
5. Quarantine affected connections/sessions if risk warrants.
6. Monitor attempts using the old credential and handle privacy/notifications per policy.
7. Conduct a root-cause postmortem and add redaction regression tests.

Never assume removing a secret from the HEAD git branch is enough; it may persist in history and caches.

## 35. Tests for Rollback and Failure Scenarios

| Case | Expectation |
| --- | --- |
| Coexisting old/new registrations | No issuer/client ID mix-ups |
| In-flight old callback post-deploy | Valid state/callback or safe failure |
| New issuer with same raw `sub`/email | No automatic linking |
| New client ID issuing different pairwise `sub` | Explicit proof workflow |
| Old secret still valid | Rollback verified testable |
| Old secret revoked | Forward-fix plan executable |
| OP 503 | No mass wipe of token store |
| New JWKS `kid` | Verified against trusted key |
| ID Token wrong issuer/audience | Rejected |
| UserInfo `sub` mismatch | UserInfo claims discarded |
| Unconsented scope | No unauthorized API access |
| Wrong API audience | Resource Server 401 |
| OP unsupported logout | Local logout falls back within scope |
| Refresh race | One pod does not delete another pod's `R2` |
| Multi-node session | Callback preserves `state` |
| Database schema migration | Old/new builds interoperate during rollout window |

## 36. One-Hour Pre-Cutover Checklist

| Area | Questions That Must Be Answered |
| --- | --- |
| Ownership | Are owner, approver, and incident contacts confirmed? |
| Scope | Which registrations, tenants, regions, and users are impacted? |
| Issuer | Are metadata/JWKS/trust boundaries verified? |
| Credentials | Are secret/key versions right and absent from logs? |
| Callback | Are exact URI/proxy/cookie/PKCE/`state` accurate? |
| ID Token | Are issuer, audience, signature, nonce, and clocks verified? |
| UserInfo | Are subject equality and missing-claim policies defined? |
| Identity | Are pairwise `sub`, email collisions, and account linking handled? |
| Authorization | Are tenant/role scopes prevented from unintended escalation? |
| Token store | Are authorized-client persistence and refresh races covered? |
| Resource Server | Are trusted issuers, audiences, scopes, and API trust aligned? |
| Logout | Are RP/OP/Back-Channel and session registries checked? |
| Monitoring | Are dashboards, alerts, and canary thresholds ready? |
| Rollback | Are old credentials/endpoints still usable? |
| Forward-fix | Is there a plan if rollback is impossible? |
| Testing | Are mock OP, provider sandbox, and browser/DB tests passing? |
| UX | Are re-consent/re-login/migration communications ready? |
| Cleanup | When will old registrations/secrets be retired? |

## 37. Review Questions

**1. Why is changing `issuer-uri` not just changing a hostname?**

Because the issuer is the OIDC trust boundary and the namespace for external identities. When the issuer changes, the new `(iss, sub)` requires verification/migration rather than auto-linking to an old account by email.

**2. Why can a new client ID change a user's `sub` even when the issuer stays the same?**

An OP can issue pairwise subjects scoped per client or sector. Never auto-merge by email; verified account linking or provider-approved correlation is required.

**3. Can the old secret be revoked immediately during secret rotation?**

Only once every consumer has switched and rollback risk is accepted. If the OP does not support secret overlap, a maintenance window, dual client, or forward-fix plan is needed.

**4. Can an old client's Refresh Token be reused with a new client ID?**

Not by default. Refresh Tokens are typically bound to client/grant; reauthorization or provider-supported migration is required rather than copying token bytes.

**5. During OP JWKS rotation, may signature validation be skipped to keep logins flowing?**

No. Inspect trusted issuer, JWKS cache, and key rollout; if a key is compromised, escalate to incident response.

**6. Why does adding `reports.read` not guarantee an API returns 200?**

User/admin consent may not have granted that scope yet, or the Access Token may be stale or have the wrong audience; the Resource Server still enforces permissions independently.

**7. Does local logout automatically revoke issued JWT Access Tokens?**

No. RP sessions, OP SSO, and Access/Refresh Tokens have separate lifecycles; a separate revocation/introspection/denylist policy is required if promised.

**8. Why can rolling back to an old YAML fail?**

The old secret may have been revoked, the old endpoint closed, Refresh Tokens rotated, or schema changes contracted; sometimes a forward-fix is necessary.

**9. Should a provider be created dynamically from a user-supplied `issuer`?**

No. Without trust onboarding and allowlists, that opens SSRF or allows accepting attacker-signed ID Tokens.

**10. Is testing only `oidcLogin()` in MockMvc enough for an issuer migration?**

No. It mocks `Authentication` and does not exercise real Token Endpoint exchanges, PKCE, or JWKS/ID Token verification. Mock OP, provider sandbox, and browser callback integration tests are required.

## 38. References

- Spring Security — Servlet OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — Advanced OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — Servlet OAuth2 Client: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/index.html
- Spring Security — Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — Servlet OIDC Logout: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security — Reactive OIDC Logout: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Spring Security — OAuth2 Login MockMvc Testing: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
- Spring Security — Reactive WebTestClient Security Testing: https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- Spring Boot — Externalized Configuration: https://docs.spring.io/spring-boot/reference/features/external-config.html
- OpenID Connect Core 1.0: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- OpenID Connect RP-Initiated Logout 1.0: https://openid.net/specs/openid-connect-rpinitiated-1_0.html
- OpenID Connect Back-Channel Logout 1.0: https://openid.net/specs/openid-connect-backchannel-1_0.html
- OAuth 2.0 Authorization Framework — RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- Proof Key for Code Exchange — RFC 7636: https://www.rfc-editor.org/rfc/rfc7636
- OAuth 2.0 Security Best Current Practice — RFC 9700: https://www.rfc-editor.org/rfc/rfc9700
- OAuth 2.0 Token Revocation — RFC 7009: https://www.rfc-editor.org/rfc/rfc7009
- OAuth 2.0 Bearer Token Usage — RFC 6750: https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Mutual TLS and Certificate-Bound Tokens — RFC 8705: https://www.rfc-editor.org/rfc/rfc8705
- OAuth 2.0 DPoP — RFC 9449: https://www.rfc-editor.org/rfc/rfc9449
- JWT Best Current Practices — RFC 8725: https://www.rfc-editor.org/rfc/rfc8725
- OWASP Secrets Management Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Secrets_Management_Cheat_Sheet.html
- OWASP OAuth2 Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html
- OWASP Logging Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Logging_Cheat_Sheet.html

## 39. Summary: OAuth2/OIDC Changes Are Security Changes

~~~text
Change request
    |
    v
Inventory + blast radius + security invariants
    |
    +-- Secret/key rotation?
    |     -> overlap if available -> canary -> retire old
    |
    +-- Client ID/issuer migration?
    |     -> dual registration -> user consent
    |     -> identity linking and token lifecycle
    |
    +-- Endpoint/redirect/scope changes?
    |     -> trusted metadata -> session/PKCE/callback tests
    |     -> Resource Server audience/permissions
    |
    v
Mock OP / provider sandbox / staging tests
    |
    v
Canary + progressive rollout + observability
    |
    +-- Security violation -> STOP + containment
    +-- Availability regression -> pause + rollback/forward-fix
    |
    v
Verified cutover -> retire old safely -> post-change audit
~~~

**Six core principles:**

1. **Do not treat an issuer change like a hostname swap.** Trust and external identities must be re-verified; a new client ID can change pairwise subjects or consent.
2. **Rotation must be ordered.** Register new secrets/keys and verify canary plus all consumers before revoking old credentials; without overlap, prepare maintenance or forward-fix plans.
3. **Preserve protocol invariants.** `state`, PKCE, nonce, issuer, audience, and JWT signatures must never be disabled to work around rollout errors.
4. **Scopes, claims, tenants, tokens, and logout have separate lifecycles.** Each requires scoped tests and cleanup, never falling back to another provider's privileges.
5. **Rollback must be tested like a feature.** Revoked secrets or migrated identities/schemas may not revert via old YAML; prepare a forward-fix path.
6. **Canarying and evidence drive cutover.** Watch errors per registration, API permissions, session continuity, account-link conflicts, and secret protection before closing the change.

A safe change process not only keeps users signing in, it **proves tokens never go to the wrong place, privileges never silently escalate, identities never mistakenly merge, and the team can recover when client or provider configurations change**.
