# Identity Brokering Between Applications and Multiple External IdPs

**Module:** Spring Security – federation → OIDC and Brokering.  
**Goal:** design and operate an **Identity Broker** so applications integrate with a single internal identity issuer while the broker connects to multiple external Identity Providers (IdPs) via OpenID Connect (OIDC), SAML2, or supported protocols. This lesson explains trust boundaries, login flows, identity mapping, IdP routing, token protection, and how to implement a Spring Security application as an OIDC Relying Party (RP).

**Core takeaway:** a broker is **not merely a login button chooser**. To perform true OIDC brokering, it must **verify upstream messages**, link external subjects to **broker-managed accounts**, establish its own session, and **issue new OIDC tokens under the broker's issuer** to downstream applications. Applications must never directly trust an ID Token from IdP A as if it were signed by the broker or intended for their audience.

This lesson targets Java 17+, Spring Boot 4.1.x / Spring Security 7.x (Servlet/MVC), and a suitable broker/OIDC Provider. `example.com` domains are learning data; replace them with real system metadata, client registrations, and certificates/keys.

## 1. The Problem: One Application, Multiple Identity Providers

A B2B platform serves three groups:

- Company employees using internal IdP A, supporting OIDC.
- Enterprise partner B using its own OIDC IdP.
- Legacy partner C providing only a SAML2 IdP.
- A web app, mobile BFF, API, and admin portal all need to resolve internal accounts, tenants, roles, and policies.

If every application integrates directly with all three IdPs, the number of connections, login screens, token mechanisms, rotation procedures, and user-mapping policies multiplies. Each app must understand IdP-specific claims, issuers, key rollovers, callback errors, and differing session/logout semantics. Account collision risk rises if apps casually use email as the user ID.

An **Identity Broker** establishes an intermediate federation hub:

```text
             ┌───────────────────────────────┐
             │  App Web / BFF / Mobile / API │
             │  OIDC client or resource      │
             │  server trusting BROKER       │
             └──────────────┬────────────────┘
                            │ OIDC (broker issuer)
                            ▼
             ┌───────────────────────────────┐
             │       IDENTITY BROKER         │
             │ OIDC Provider toward apps     │
             │ OIDC RP / SAML SP toward IdPs │
             │ Login routing                 │
             │ Identity mapping / JIT        │
             │ Session, consent, policy      │
             │ Token issuance + JWKS         │
             └───────────┬──────┬────────────┘
                         │      │
                 OIDC ───┘      └── SAML2
                         │      │
             ┌───────────▼─┐  ┌─▼───────────┐
             │ IdP A / B   │  │ IdP C       │
             │ OIDC OP     │  │ SAML IdP    │
             └─────────────┘  └─────────────┘
```

**Distinguish protocol roles**:

| Leg | Who Is Client/RP? | Who Issues Identity? | Token / Callback |
| --- | --- | --- | --- |
| App → broker | Application is **OIDC RP/OAuth client** | Broker is **OIDC Provider/Authorization Server** | App receives authorization code and exchanges it for a broker ID Token |
| Broker → IdP A | Broker is **OIDC RP** of IdP A | IdP A is **OIDC Provider** | Broker receives and verifies **upstream ID Token** |
| Broker → IdP C | Broker is **SAML2 SP** | IdP C is **SAML2 Identity Provider** | Broker verifies `SAMLResponse/Assertion` |
| API → broker | API is **OAuth2 resource server** | Broker issues access tokens for the API | API validates `iss`/`aud`/signature/scopes per policy |

**OIDC is for authentication**, built on OAuth2; an IdP offering only OAuth2 authorization is not automatically OIDC. If a provider issues no ID Token, the broker needs an explicit user-identification mechanism from a trusted provider API and must not fabricate an ID Token label.

## 2. Three Architectures Frequently Confused

| Architecture | Reality | When Appropriate | Points to Watch |
| --- | --- | --- | --- |
| **App integrates multiple OIDC IdPs directly** | Spring `oauth2Login` has multiple `ClientRegistration`s; app receives tokens from each IdP | Small single app, few upstream providers | **This is not yet a broker** if the app does not mint tokens for downstream clients |
| **Identity Broker / OIDC Provider** | App knows only the broker; broker talks to multiple upstreams, builds internal subjects, and mints new tokens | Multiple apps/tenants/IdPs needing unified policies and federation | Broker becomes a trust-critical service requiring HA, key management, and auditing |
| **Gateway forwarding identity headers** | Gateway handles login then injects internal `X-User`/`X-Email` | Legacy apps lacking OAuth2/OIDC | Safe only with network isolation/mTLS/header stripping; **not an OIDC broker** |

**Do not confuse Spring Security `oauth2Login()` with an OIDC Provider.** `oauth2Login()` provides **OAuth2/OIDC client login**—i.e., acting as an RP toward an IdP; for a Spring app to accept upstream logins and issue authorization codes/ID Tokens downstream, you must add an **Authorization Server/OP implementation** (Spring Security OAuth2 Authorization Server or an IAM product) along with client registrations, keys, discovery, sessions, consent, logout, and mapping policies. Calling a single annotation will not "turn a client into a broker".

### 2.1. Buy an IAM Product or Build a Broker?

| Option | Advantages | Responsibilities to Plan For |
| --- | --- | --- |
| Keycloak / IAM with identity brokering | Built-in OIDC/SAML adapters, login flows, federated identity links, user management | Client config, upstream trust, first-broker-login, preventing email auto-linking, key rotation, and HA |
| Managed identity service with federation | Reduces server/key operations; UI, policy, and audit support per service | Vendor contracts, data residency, limits, logout constraints, and migration |
| Custom Spring Security + Authorization Server | Flexibility in claims, business policy, and deep Java integration | Full ownership of every security boundary: credential lifecycle, discovery, token validation/issuance, linking, SLO, and testing |

For multiple real-world IdPs, **prefer a battle-tested IAM product** if requirements fit. Build a custom broker only when a team owns security, protocol interoperability, HSM/secrets, auditing, and incident response.

## 3. End-to-End Brokered OIDC Login Flow

Suppose:
- App: `https://portal.example.com`, OIDC client ID `portal-web`.
- Broker: `https://login.example.com/realms/partners`, stable issuer.
- Upstream A: `https://idp-a.partner.example/oidc`.
- Upstream B: `https://idp-b.partner.example/oidc`.
- The app configures **only the broker issuer**, not individual upstream issuers.

```mermaid
sequenceDiagram
    actor User as User
    participant App as Portal (OIDC RP)
    participant Broker as Identity Broker (OIDC OP)
    participant Link as Identity Link DB
    participant IdP as External OIDC IdP A
    User->>App: GET /private
    App-->>User: Redirect to broker /authorize with state, nonce, PKCE
    User->>Broker: OIDC authorization request
    Broker->>Broker: Select IdP A per trusted policy
    Broker-->>User: Redirect to IdP A /authorize (separate upstream state/nonce/PKCE)
    User->>IdP: Authenticate user
    IdP-->>User: Redirect upstream code to broker callback
    User->>Broker: code + state for upstream transaction
    Broker->>IdP: Exchange code with verifier and matching client credentials
    IdP-->>Broker: Upstream ID Token + token response
    Broker->>Broker: Verify iss, aud, signature, nonce, exp, policy
    Broker->>Link: Lookup (upstream issuer, upstream sub, scope)
    Link-->>Broker: broker subject B-100 or trigger linking/JIT
    Broker->>Broker: Create session and authorize downstream client
    Broker-->>User: Redirect authorization code to App
    User->>App: code + state for downstream transaction
    App->>Broker: Exchange code with verifier/client authentication
    Broker-->>App: Broker ID Token, access token if issued
    App->>App: Verify broker iss, aud, signature, nonce, expiry
    App-->>User: Portal session, tenant-based authorization
```

**Two independent authorization codes and two independent state/nonce/PKCE sets:** the code issued by upstream A is exchanged only by the broker at A's token endpoint; the code issued by the broker is exchanged only by the app at the broker's token endpoint. Never send an upstream code straight to the app callback or swap tokens between two authorization servers.

### 3.1. Trust Relationships

1. App → broker: the app trusts the **broker's public signing keys/JWKS, issuer, and metadata**, with `client_id`/`redirect_uri` registered at the broker.
2. Broker → upstream A: the broker trusts A's issuer/discovery/JWKS and holds a **separate client registration at A**.
3. Broker → upstream B: another separate client registration and trust anchor.
4. Broker → SAML C: the broker holds SP metadata and certificates, trusts C's SAML Issuer/signing cert, and verifies SAML assertions.
5. Application authorization: tenant/role/resource permissions are checked **after** brokered authentication; never assume an external group grants internal admin privileges.

**Never use upstream A's certificate/JWKS to verify the broker's ID Token**, nor the broker's JWKS to verify upstream tokens. Each issuer has its own keys, audience, and trust boundary.

## 4. Broker-Issued ID Tokens and Token Boundaries

An illustrative verified upstream ID Token:

```json
{
  "iss": "https://idp-a.partner.example/oidc",
  "sub": "user-938",
  "aud": "broker-client-at-idp-a",
  "iat": 1794020400,
  "exp": 1794024000,
  "auth_time": 1794020350,
  "acr": "urn:example:idp-a:loa2"
}
```

A **different** downstream ID Token signed by the broker specifically for the app:

```json
{
  "iss": "https://login.example.com/realms/partners",
  "sub": "B-100",
  "aud": "portal-web",
  "iat": 1794020420,
  "exp": 1794020720,
  "auth_time": 1794020350,
  "tenant_id": "partner-a"
}
```

These are **illustrative payloads, not complete JWTs or cryptographic proofs**. `iat`/`exp`/`auth_time` are example numbers; the broker must emit real timestamps matching current time and each party's profile. `tenant_id` is a **custom claim** that must be protected, defined, and checked per policy; it is not a standard OIDC claim.

**Key points:**
- Downstream `iss` is **always the broker issuer**, never upstream A's issuer.
- Downstream `sub` is a broker-managed subject, possibly **opaque/pairwise**, and does not automatically equal email or upstream `sub`.
- Downstream `aud` **must be the app's client ID**; an upstream ID Token targeted at the broker **cannot be used to log into the app**.
- The broker must mint a fresh token with its own signing key and support JWKS/rotation; **never** copy an upstream JWT and edit `iss`/`aud` in the payload.
- Upstream `acr`/`amr`/`auth_time` must not be copied verbatim as proof of higher assurance unless the broker verified their meaning, freshness, and IdP contract. If propagated, the broker needs an auditable policy transformation.
- The app handles only the **downstream ID Token**; the broker may retain controlled upstream provenance server-side for auditing or account linking.

### 4.1. ID Token vs. Access Token

| Token | Intended For | Interchangeable with Other Tokens? |
| --- | --- | --- |
| **ID Token** | OIDC RP authenticating user with `aud=client_id` | Never send as an API bearer token by default |
| **Access Token** | OAuth2 resource server with matching scopes and audience | Never treat automatically as proof of RP login identity |
| **Refresh Token** | Client requesting new access tokens per policy | Protect secret, rotate/revoke; avoid inappropriate browser exposure |
| **Upstream token** | Broker/direct client toward upstream issuer | Never forward straight to downstream APIs without explicit token exchange and trust contract |
| **Broker token** | Downstream RP/API per issued audience | Cannot be used directly at upstream APIs due to differing issuer/audience |

If the broker needs to call third-party APIs on a user's behalf, design dedicated authorized-client/token storage, scopes, consent, refresh, and provider-supported token exchange/delegation. **Never forward an upstream access token to every microservice** just because login succeeded. Token exchange, if used, requires authorization-server support, audience control, and auditing.

## 5. ID Token Validation at **Both** Legs Is Mandatory

### 5.1. Broker Validates Tokens from External IdPs

When the broker receives an upstream response:
- `iss` matches the configured/discovered issuer URI for **that exact upstream transaction**; never pick an issuer from an unverified value.
- `aud` includes the **broker's client ID at that IdP**, enforcing `azp` per OIDC profile when present.
- Signature uses public keys/JWKS of that **exact issuer**, with an allowlisted algorithm.
- `exp` is unexpired, `iat` is valid, `nonce` matches the sent request where applicable, and `state`/PKCE match the transaction.
- `sub` is present and stable within the issuer namespace; `email` is only profile data with its own lifecycle.
- If the UserInfo endpoint is called, the returned `sub` must match `sub` in the ID Token as required by OIDC Core.
- If upstream uses SAML, validate Response/Assertion signatures, `InResponseTo`, audience, recipient, issuer, time bounds, and `NameID` per profile instead of trying to use an OIDC JWT validator.

The broker **must never** allow browser requests to specify arbitrary `issuer-uri`/`jwk-set-uri`/`token-uri` URLs and trust them. That leads to SSRF, malicious metadata injection, or attacker-controlled token endpoints.

### 5.2. App Validates Tokens from the Broker

The OIDC RP app checks:
- `iss` equals the registered **broker issuer**, matched verbatim per OIDC.
- `aud` contains the app's `client_id`; with multiple audiences, check `azp` and trusted audiences per OIDC.
- Signature/JWS against the broker's JWKS from trusted discovery; reject `alg=none` or disallowed algorithms.
- `exp`/`iat` validity and `nonce` matching the OIDC request when used; `state` bound to browser/request.
- Authorization Code + **PKCE** per OAuth2 Security BCP, with **exact-match** registered redirect URIs.
- `sub` is the broker-side identity key; application account/tenant authorization still runs afterward.

A resource server must never verify only `iss` and signature while skipping `aud`. A JWT can be valid yet intended for a different client or API. When an API requires a specific `aud`, configure an appropriate audience validator and resource policy.

### 5.3. Why Can't IdP A's Token Be Used for App B?

The upstream token carries `aud=broker-client-at-idp-a`. If App B accepts it despite `aud≠app-b`, it becomes vulnerable to **token substitution / confused deputy**: a token issued for one target is accepted as App B's credential. The broker must mint a downstream token with the right audience and app policy, which the app validates independently. A valid issuer/signer on one leg **never automatically creates trust on another leg**.

## 6. Safe IdP Selection (Home Realm Discovery)

When a user reaches the login screen, the broker may offer:
1. **An IdP picker page** organized by organization, branding, and policy.
2. **Domain discovery**: the user enters an organization email and the broker suggests an IdP, yet email domain **is strictly for routing/UX** and never proves tenant or identity.
3. **Server-supplied invitation or tenant slug**: selects the IdP bound to that tenant in config.
4. **Federation hints**: some vendors support parameters like Keycloak's `kc_idp_hint` or `login_hint`; these are not identity verification.
5. **SAML IdP discovery/metadata** per external contract.

**Boundary:** routing decides "where to send the browser", whereas **issuer validation and account mapping** decide "who authenticated and what permissions they hold". Browsers can tamper with query parameters, emails, or tenant hints, so never treat them as authority.

### 6.1. Per-Tenant IdP Allowlist Table

| Tenant | Allowed Upstream Issuer | Protocol | Policy |
| --- | --- | --- | --- |
| `company` | `https://sso.company.example` | OIDC | Employees, org-wide MFA |
| `partner-a` | `https://idp-a.partner.example/oidc` | OIDC | Invitation + identity linking |
| `partner-b` | `https://idp-b.partner.example/oidc` | OIDC | Pre-provisioned users only |
| `legacy-c` | SAML entityID from signed metadata | SAML2 | Stable NameID, stricter mapping |

If an attacker appends `?tenant=company` to Partner B's URL, the broker must never elevate Partner B's identity into a `company` employee. Map issuer/subject to a tenant only when an authorized identity-link/membership exists.

### 6.2. Redirects and Mix-Up with Multiple Upstreams

A broker acts as an OAuth client talking to **multiple authorization servers**, making it susceptible to **authorization server mix-up** if callbacks or stored authorization requests fail to pin the issuer. Per RFC 9700:
- Use single-use random `state` binding session/browser to the **exact upstream issuer + client registration**.
- Prefer authorization response issuer identification (`iss`) per RFC 9207 when supported; compare against the stored issuer.
- Alternatively use **distinct redirect URIs per issuer** as described in RFC 9700 where appropriate.
- Exchange the authorization code **only at the token endpoint belonging to the initially selected issuer**, never choosing endpoints from callback query parameters.
- Enforce PKCE, HTTPS, exact redirect matching, secret protection, and open-redirect prevention.
- Checking ID Token issuer/audience/nonce at the token endpoint does not alone prevent all authorization-response mix-up leaks.

Saving only `authorization_endpoint` is insufficient against mix-up if an attacker can point metadata at another token endpoint. Upstream client registrations must be admin-managed and reviewed.

## 7. Cross-IdP Identity Mapping: Never Use Email as the Key

In OIDC, the two foundational claims identifying a subject are:
- `iss`: verified Provider issuer.
- `sub`: subject identifier stable **within the issuer namespace** per OIDC Core.

The **recommended external identity key** is the tuple `(trusted upstream issuer, upstream sub)`, adding scope/tenant if the subject contract is not issuer-global. For upstream SAML, use `(trusted SAML issuer, stable NameID, qualifiers/SP scope as needed)`.

| Upstream Issuer | Upstream `sub` | Email | Conclusion |
| --- | --- | --- | --- |
| IdP A | `abc-7` | `alice@a.example` | External subject A |
| IdP B | `abc-7` | `alice@a.example` | **Different from subject A** because issuer differs |
| IdP A | `abc-9` | `alice@a.example` | Never auto-link to A just because email matches |
| IdP A | `abc-7` | `alice@new.example` | Same external subject if issuer/`sub` are unchanged |

Emails can change or be reassigned to another person. `email_verified=true` only states that the issuer verified the email under its own policy; **it never proves two identities across two issuers are the same person**, especially where onboarding or account linking risks account takeover.

### 7.1. Three ID Layers

```text
upstream:  (issuer_A, sub_abc7)
                        │
                        ▼
broker:   broker_user_id = U-100
                        │
                        ▼
downstream client: broker sub = opaque_B100
                        │
                        ▼
app:      internal_user_id / memberships / permissions
```

The broker can:
- Issue the same broker `sub` to multiple clients (`public sub`).
- Issue distinct `pairwise sub` values per RP/sector (per broker policy), still mapping back to the internal broker user.
- Attach multiple external links from different IdPs to **one broker user** once linking is proven.

Downstream apps **do not necessarily see** upstream issuer/`sub`. If authentication-source auditing is required, the broker can emit a signed, governed custom claim or store it server-side; never turn that custom claim into the sole identity key while dropping `iss=broker` and `sub`.

### 7.2. Suggested Mapping Database

```sql
CREATE TABLE broker_users (
    user_id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL
        CHECK (status IN ('ACTIVE', 'DISABLED')),
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE external_identities (
    identity_id UUID PRIMARY KEY,
    broker_user_id UUID NOT NULL REFERENCES broker_users(user_id),
    upstream_issuer TEXT NOT NULL,
    upstream_subject TEXT NOT NULL,
    provider_scope TEXT NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (upstream_issuer, upstream_subject, provider_scope)
);

CREATE INDEX idx_external_by_user
    ON external_identities(broker_user_id);

CREATE TABLE tenant_memberships (
    tenant_id TEXT NOT NULL,
    broker_user_id UUID NOT NULL REFERENCES broker_users(user_id),
    role_name TEXT NOT NULL,
    PRIMARY KEY (tenant_id, broker_user_id, role_name)
);
```

This is a simplified schema illustrating **structure**, not covering all concurrency, migration, or auditing concerns. `provider_scope` needs a clear canonical value: for standard OIDC it is typically fixed per issuer (never inject an arbitrary tenant that lets two users collide), whereas for SAML it may capture NameID qualifier/SP scope per contract. Multiple memberships/roles should be normalized in a dedicated role model.

During JIT provisioning:
1. Broker **verifies the upstream response** first.
2. Checks whether the IdP is permitted under tenant/onboarding policy.
3. Looks up the link by canonical external key with a unique index.
4. If absent: creates the broker user/link only when policy allows, inside a race-protected transaction.
5. If email matches an existing user: **never auto-link**; require proof of the existing account, invitation, SCIM, or admin approval.
6. Before minting tokens for the app, verify `ACTIVE` status and tenant membership; never grant high roles by default.
7. Emit audit events containing no raw tokens or secrets.

**Never build "fail-open" logins:** if a user is unprovisioned and JIT is disallowed, return a controlled onboarding error rather than granting default tenant membership.

## 8. Account Linking, Migration, and Deprovisioning

### 8.1. Linking the Same Person Across IdP A and B

A user already holds broker account U-100 via IdP A and wants to add IdP B login. Proper workflow:
- User holds an authenticated broker session and passes appropriate re-authentication/CSRF checks.
- Broker **explicitly** initiates upstream login B under an account-linking workflow, never relying on client-sent email or `sub`.
- B authenticates; broker validates B's token issuer/subject and security state.
- User (or admin per policy) confirms linking B → U-100.
- Broker persists the new link in a transaction with uniqueness, blocking takeover if B already links to U-999.
- Audit who/when/where; provide unlinking/revocation with a guard against locking the user out of all login methods.

Keycloak provides a **First Broker Login flow**, identity provider settings, and account-linking workflows. Evaluate `Trust Email` cautiously: trusting an unverified or colliding email during first-login linking risks account takeover. Never turn on automatic email-based linking solely to cut an onboarding step.

### 8.2. User Changes Email or Department

If upstream `iss+sub` remains unchanged, the broker user ID stays constant. Email is a profile/contact attribute that can update per policy without changing the key. Roles and tenant memberships must come from authoritative sources and proper provisioning flows.

### 8.3. Changing IdP or Organization Mergers

Switching from IdP A to B offers **no automatic mapping** between their `sub` values. To preserve history/broker user:
- Verified mapping from SCIM/HR/directory and IdP owners; or
- User proves ownership of both A and B inside an authenticated session; or
- Admin migration with approval, auditing, and rollback.

If the issuer URI or pairwise `sub` changes when creating a new application registration, treat it as an **identity namespace change** and test before rollout. Never run bulk SQL updates matching only by email domain.

### 8.4. Disabling Users and Session Lifecycle

A user disabled upstream is not automatically logged out immediately at the broker or downstream apps: the broker has its own sessions and tokens. Use reliable SCIM/events/webhooks, short TTLs and refresh policies, revocation, and broker user status checks. Apps may need live authorization checks rather than trusting long-lived tokens blindly.

**Multi-hop logout is not synchronous by default.** App local logout, broker RP-initiated logout, broker upstream logout, OIDC front-/back-channel logout, and SAML SLO all behave differently. OIDC Back-Channel Logout defines messages carrying `iss/sub/sid`; propagating signals from upstream through the broker to downstream requires vendor-specific setup and testing. If the upstream IdP still holds an SSO session, the next login may silently re-authenticate.

## 9. Spring Security: Downstream App Connecting Only to the Broker

This is a simple **runnable framework example**: a Spring Boot 4.1.x app using `oauth2Login` connected to **one broker issuer** via OIDC Authorization Code Flow. Even when the broker integrates IdPs A/B/C, this app **needs no knowledge** of A/B/C in its OAuth2 client registrations.

### 9.1. Complete `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
  <modelVersion>4.0.0</modelVersion>
  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
  </parent>
  <groupId>com.example</groupId>
  <artifactId>portal-oidc-client</artifactId>
  <version>1.0.0</version>
  <properties>
    <java.version>17</java.version>
  </properties>
  <dependencies>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-webmvc</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-security-oauth2-client</artifactId>
    </dependency>
    <dependency>
      <groupId>org.springframework.boot</groupId>
      <artifactId>spring-boot-starter-test</artifactId>
      <scope>test</scope>
    </dependency>
  </dependencies>
  <build>
    <plugins>
      <plugin>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-maven-plugin</artifactId>
      </plugin>
    </plugins>
  </build>
</project>
```

**Version note:** In Boot 4, `spring-boot-starter-security-oauth2-client` is the new starter naming; the older `spring-boot-starter-oauth2-client` may still exist as deprecated per metadata. Boot 3.x uses different coordinates; never mix major versions without testing.

### 9.2. `application.yml`

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          broker:
            provider: broker
            client-id: portal-web
            client-secret: ${BROKER_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          broker:
            issuer-uri: https://login.example.com/realms/partners

server:
  servlet:
    session:
      cookie:
        secure: true
        http-only: true
```

Before running, you need a **real OIDC Provider** at the issuer URL and a `portal-web` OAuth client registered at the broker with an exact matching redirect URI. `BROKER_CLIENT_SECRET` must come from a secret manager/environment, never committed to Git. For local development without HTTPS, use a dev-specific cookie override; never disable `Secure` in production.

Spring Security uses discovery at the broker issuer to locate the authorization endpoint, token endpoint, and JWKS. **Never point `issuer-uri` at upstream A/B** when the intended architecture uses a broker. Changing the broker issuer alters the trust contract for all downstream apps.

### 9.3. `SecurityConfig.java`

```java
package com.example.portal;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                    .requestMatchers("/", "/error").permitAll()
                    .anyRequest().authenticated()
                )
                .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

### 9.4. `PortalApplication.java`

```java
package com.example.portal;

import java.util.Map;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class PortalApplication {
    public static void main(String[] args) {
        SpringApplication.run(PortalApplication.class, args);
    }

    @GetMapping("/")
    String home() {
        return "Portal using OIDC broker";
    }

    @GetMapping("/me")
    Map<String, String> me(@AuthenticationPrincipal OidcUser user) {
        var idToken = user.getIdToken();
        return Map.of(
                "issuer", idToken.getIssuer().toExternalForm(),
                "subject", idToken.getSubject()
        );
    }
}
```

Once configured with a real broker, run:

```bash
mvn test
mvn spring-boot:run
```

Opening `/me` redirects an unauthenticated browser to the broker login, which continues to the chosen upstream IdP. On success, the JSON returns the **broker issuer** and **broker `sub`**, not necessarily IdP A's issuer/`sub`. There is no fixed stdout/HTTP JSON because subject, client, and session come from the live broker. The code intentionally avoids returning raw ID Tokens, access tokens, or email to the client.

**This sample demonstrates only downstream login, not the full broker implementation.** The broker must already have its issuer, keys, registered clients, and federation links configured.

### 9.5. What Happens with Multiple Upstream IdPs?

Do not edit the portal's `application.yml` to add `partner-a` and `partner-b` as direct OIDC providers. Instead configure **inside the broker** the two external IdPs along with routing and linking policies. The app sees only:
- `iss=https://login.example.com/realms/partners`.
- Broker-managed `sub`.
- Claims the broker is authorized to issue to the app.
- Broker signing keys/JWKS and broker session/authorization APIs.

If the app needs tenant-scoped permissions, implement mapping/authorization against the broker user ID and internal business database—never just read `preferred_username`/`email`.

## 10. Spring Security on the **Upstream Broker Side**: Multiple Registrations

If an organization builds its own broker with Spring, the upstream login tier can use `oauth2Login` with multiple `ClientRegistration` entries as below. However, **this tier is only an OIDC RP**; it does not yet mint OIDC ID Tokens for the portal. The downstream OP tier must be built with **Spring Security OAuth2 Authorization Server** or another IAM/OIDC provider.

### 10.1. Configuring Two Upstream OIDC Providers (YAML Fragment)

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          idp-a:
            provider: idp-a
            client-id: broker-at-idp-a
            client-secret: ${IDP_A_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile,email
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
          idp-b:
            provider: idp-b
            client-id: broker-at-idp-b
            client-secret: ${IDP_B_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: openid,profile
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
        provider:
          idp-a:
            issuer-uri: https://idp-a.partner.example/oidc
          idp-b:
            issuer-uri: https://idp-b.partner.example/oidc
```

Default initiation endpoints are typically:
- `GET /oauth2/authorization/idp-a`.
- `GET /oauth2/authorization/idp-b`.

Callback endpoints:
- `GET /login/oauth2/code/idp-a`.
- `GET /login/oauth2/code/idp-b`.

Each upstream requires its own client registration, exact redirect URI, keys, secret/PKCE, and trust configuration. **Never equate `registrationId=idp-a` with the upstream issuer URI**; issuer comes from trusted configuration and token validation.

### 10.2. The Broker Must Include a Separate Authorization Server / OP Layer

To issue ID Tokens to the portal, the broker needs:
- A **stable issuer URI** and OIDC discovery `/.well-known/openid-configuration`.
- Authorization/token/JWKS endpoints, signing keys, and key rotation.
- Registered clients, redirect URI allowlist, client authentication, grants/scopes/consent.
- Authorization Code Flow + PKCE and browser/user session management.
- Mapping upstream identities to an immutable **broker user ID**.
- Token customization: broker `iss`, broker `sub`, right downstream client `aud`, and policy-approved claims; never pass upstream tokens verbatim.
- Logout, revocation, refresh token policies, monitoring, and incident response.
- Issuer mix-up protection when the broker itself talks to multiple upstreams.

Spring Security 7 includes the **OAuth2 Authorization Server** feature; Spring Authorization Server folded into Spring Security 7 per official announcements. See [How-to: Authenticate using Social Login](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-social-login.html) as one reference. However, a "social login" guide **does not automatically solve every multi-tenant broker requirement**: safe account linking, SAML protocol translation, cascading logout, provenance, step-up, high availability, and key management still require explicit design.

### 10.3. How Does a Broker Support Upstream SAML?

On the broker → SAML IdP leg, the broker acts as a **SAML Service Provider**, using Spring Security `saml2Login` and `RelyingPartyRegistration` or an IAM adapter. The broker must verify:
- IdP `Issuer` and trusted certificate.
- XML signature, audience, recipient/ACS, `InResponseTo`, and request/session correlation.
- Stable `NameID` per IdP contract; qualifiers/SP scope as needed.
- Validity window, replay, tenant binding, and encrypted assertions if required by the IdP.

The broker then maps the external SAML identity to a broker user and mints a **new OIDC token** for the app. **A `SAMLResponse` is not an OIDC ID Token**; you cannot merely Base64-decode XML and set `sub=email` while skipping account linking. Protocol translation is an authentication boundary that demands auditing and testing.

## 11. Standalone Java 17: Why Issuer + Subject Are Both Required

The following exercise runs on JDK 17+ **without Spring or network access**. It simulates broker identity linking: two upstreams can emit the same `sub` without representing the same person, and the broker maintains its own internal user ID. The example **handles no signatures, nonces, or tokens**, so use it strictly for mapping concepts.

File `IdentityBrokerDemo.java`:

```java
import java.util.HashMap;
import java.util.Map;

public class IdentityBrokerDemo {
    record ExternalSubject(String issuer, String subject) {
        ExternalSubject {
            if (issuer == null || subject == null
                    || issuer.isBlank() || subject.isBlank()) {
                throw new IllegalArgumentException(
                        "Issuer and subject are required");
            }
        }
    }

    public static void main(String[] args) {
        String brokerIssuer = "https://login.example.com/realms/partners";

        ExternalSubject idpA = new ExternalSubject("idp-A", "user-42");
        ExternalSubject idpARepeat =
                new ExternalSubject("idp-A", "user-42");
        ExternalSubject idpB = new ExternalSubject("idp-B", "user-42");

        Map<ExternalSubject, String> links = new HashMap<>();
        links.put(idpA, "broker-user-100");

        System.out.println("Same subject + same issuer: "
                + idpA.equals(idpARepeat));
        System.out.println("Same subject + different issuer: "
                + idpA.equals(idpB));
        System.out.println("Known broker user: "
                + links.get(idpARepeat));
        System.out.println("Other provider: "
                + links.getOrDefault(idpB, "unlinked"));
        System.out.println("Downstream issuer: " + brokerIssuer);
    }
}
```

Compile and run:

```bash
javac IdentityBrokerDemo.java
java IdentityBrokerDemo
```

**Exact stdout:**

```text
Same subject + same issuer: true
Same subject + different issuer: false
Known broker user: broker-user-100
Other provider: unlinked
Downstream issuer: https://login.example.com/realms/partners
```

**Meaning:** the `record` compares both fields together, preventing collisions from `sub` alone. External subjects link to broker users via a dedicated database and policy. An application-facing broker `sub` may be another opaque string rather than the upstream subject. **Never copy the demo map into a production security provider**: inputs here are assumed verified, whereas real systems must verify JWT/SAML, manage keys, govern account linking, handle transactions/races, and enforce policies.

## 12. Multi-Tenancy and Propagating Permissions

A broker can serve multiple B2B organizations, yet **authentication authority is not synonymous with business authorization authority**.

**Separate these layers:**
1. `External identity`: verified IdP issuer + `sub`/NameID.
2. `Broker user`: internal broker account ID and enabled/disabled state.
3. `Tenant membership`: user–tenant relationship with lifecycle/invitation/provisioning.
4. `Application roles`: app/API-specific permissions, often managed in the app's DB.
5. `Assurance state`: `auth_time`, `acr`, `amr`, and session policy for handling step-up.

Upstream groups/roles lack global meaning: `admin` from IdP A may only administer Partner A's systems and **must never** automatically become `ROLE_ADMIN` in the internal portal.

If the broker emits downstream `roles`/`tenant_ids` claims:
- Constrain by IdP issuer, claim namespace, and allowlisted mappings.
- Emit only privileges governed by the broker/application IAM authority.
- Avoid stuffing huge permission lists into JWTs, especially when permissions change frequently.
- APIs must check the right `aud`, scopes/roles, and **resource tenant**, not just the signature.
- Consider short token TTLs, permission lookups, or introspection for sensitive revocable privileges.

**JIT provisioning** may create a broker account without automatically granting tenant membership. SCIM can manage user/membership lifecycles; keeping SCIM/IdP events, broker sessions, and app authorization consistent is an essential operational responsibility.

## 13. MFA, Step-Up, and Authentication Time Across a Broker

OIDC provides these claims:
- `auth_time`: time of last authentication asserted by the OP.
- `acr`: authentication context class reference per policy/provider.
- `amr`: authentication methods declared by the OP.
- `max_age` in auth requests: maximum acceptable authentication age per OIDC.
- `prompt=login`: interactive re-authentication request per OIDC semantics.

In a brokered architecture:
1. App sends a step-up request to the broker under an agreed protocol/policy.
2. Broker identifies the user/upstream IdP and may propagate `max_age`, `prompt`, `acr_values`, or SAML `ForceAuthn`/`RequestedAuthnContext` per provider capability.
3. Broker validates **upstream `auth_time`/`acr`/`amr`** or `AuthnStatement`/`AuthnContext` from the IdP.
4. Broker emits downstream `auth_time`/`acr`/`amr` **only under verified, contracted semantics**, never copying upstream text blindly.
5. App enforces assurance/freshness and user continuity without treating broker login success as blanket MFA proof for every action.

Some IdPs lack step-up or equivalent context mapping. When policy mandates it, the broker must report inability to comply or deny the action—**never downgrade by rewriting claim strings to fake MFA**.

## 14. Logout and Sessions Across Three Legs

A brokered login involves at least:
- Downstream application session (e.g., the portal's `JSESSIONID`).
- Broker session, used for SSO across multiple apps.
- Sessions at IdPs A/B/C.
- Authorization codes and access/refresh tokens on legs configured to issue tokens.

Behavior matrix:

| Event | What Can Happen | What Must Never Be Assumed |
| --- | --- | --- |
| User logs out of portal | App clears SecurityContext/local session | Broker and upstream IdP also logged out |
| User logs out of broker | Broker clears session and may notify downstream | All downstream apps received back-channel logout cleanly |
| Upstream IdP logout | Broker may be notified via supported protocol | Every browser/app session disappears immediately |
| User disabled at IdP | IdP blocks new logins | Already-issued broker tokens immediately lose validity |
| Broker key rotation | JWKS publishes new key; clients refresh | Apps automatically accept new keys if pinning is misconfigured |
| Token expires | Resource server rejects the expired token | Browser IdP/broker session has certainly ended |

**OIDC RP-Initiated Logout** and **Back-Channel Logout** are distinct specifications. The broker must actively support and test fanning out logout to downstream RPs on upstream logout; depending on products, upstream and downstream logout may have only partial support. If compliance requires global logout, make it an acceptance test rather than assuming a Logout button suffices.

Especially with front-channel redirects, networks or browsers may fail to complete every hop. For higher reliability, consider back-channel logout, session revocation, retries, and auditing.

## 15. Security Checklist for Multi-IdP Brokers

| Threat | Risk Source | Mandatory Control |
| --- | --- | --- |
| Authorization-server mix-up | Broker redeems code at wrong issuer's token endpoint | Store expected issuer in state; use RFC 9207 `iss` if supported or distinct redirect policy |
| Login CSRF | Callback lacks browser binding or state reused | Random state, browser/session binding, single-use processing, nonce |
| Token substitution | Upstream ID Token accepted at downstream client | Verify `iss`/`aud`/`azp` on each leg; broker mints fresh tokens |
| JWKS/key confusion | Trusting keys from attacker-supplied `jku`/`kid`/URLs | Trust allowlisted discovery/JWKS, algorithm allowlist, proper caching/rotation |
| SSRF via discovery | User supplies arbitrary `issuer-uri` | Admin-configured allowlist, DNS/IP/egress controls, no dynamic untrusted fetches |
| Open redirect | `redirect_uri` or `returnTo` taken unvalidated from query | Exact redirect matching, allowlist, never echo user-supplied URLs |
| Account takeover via email | First-login auto-links users sharing an email | Identity linking with proof/admin approval, unique issuer+sub |
| Cross-tenant identity mix-up | Confusing IdP B with tenant A | Tenant/issuer mapping and membership/resource-level authorization |
| Weak upstream provider | One IdP enforces weaker assurance than policy | Per-provider/action policy; disallow silent fallback |
| Code/token replay | Replayed auth request/callback | PKCE, state/nonce, token `exp`, single-use redemption |
| Credential leakage | Tokens/secrets in logs, URLs, browser storage | Secure cookies, TLS, vault/HSM, log redaction, short TTLs |
| Key rotation outage | Broker signing key rotates while clients cache stale JWKS | Overlap publishing, cache-aware rollover, negative tests |
| Logout inconsistency | Upstream logout fails to reach downstream | Session revocation/Back-Channel Logout and per-adapter testing |
| Unsafe identity transformation | Broker accepts upstream `roles=admin` and emits admin | Allowlist/policy-based mapping; do not infer |
| Multi-tab race | Two upstream logins occur concurrently | Isolate state/nonce/request per transaction; prevent callback mix-up |
| Insecure reverse proxy | Client spoofs `X-Forwarded-Host`, wrong scheme | Trust forwarded headers only from authenticated proxies |

**A broker can become a concentrated point of risk.** Compromising its signing private key or session store affects many downstream apps. Protect it with HSM/secret storage, rotation, auditing, realm/tenant blast-radius isolation, HA, and incident response.

## 16. Operations: Discovery, Keys, Issuer, and Redirects

### 16.1. Discovery and Issuer

Every OIDC Provider has a stable issuer. Example broker issuer:

```text
https://login.example.com/realms/partners
```

For this issuer, the typical OIDC discovery endpoint is:

```text
https://login.example.com/realms/partners/.well-known/openid-configuration
```

Obtain live endpoints from the broker's OIDC Discovery/metadata. Verify:
- `issuer` in discovery **matches exactly** the issuer configured in apps.
- `authorization_endpoint`, `token_endpoint`, and `jwks_uri` use HTTPS within the same trust boundary.
- `response_types_supported`/`grant_types_supported` support the Authorization Code Flow.
- Public keys/JWKS match the keys the broker **actually signs with**.
- `end_session_endpoint`/back-channel logout are used only when published and supported by the broker.
- Reverse proxies never downgrade `https` to `http` or expose internal hosts in metadata.

When changing FQDN/realm, changing the issuer causes every downstream RP to reject ID Tokens on `iss` checks—that is a **trust migration**, not a casual DNS edit.

### 16.2. Key Rotation

The broker can phase signing keys `K_old` and `K_new`:
1. Publish the new JWK while still signing tokens with `K_old`.
2. Wait for RPs and resource servers to refresh key caches.
3. Switch signing to `K_new`, keeping the old public key until existing tokens expire.
4. Verify signed tokens across every RP/API and check token/cache lifetimes.
5. Retire `K_old` per policy; if a private key is compromised, run incident response rather than keeping a long overlap.

Upstream IdP key rotation is **separate**: the broker must refresh each issuer's JWKS independently and reject keys from other sources. SAML IdP certificates and broker OIDC signing keys are also distinct.

### 16.3. Availability and Failure Isolation

An outage at one upstream IdP should not halt broker logins for all other upstreams unless policy/infrastructure forces it. Implement:
- Timeouts/circuit breakers for metadata/JWKS/UserInfo fetches.
- Metadata caching with proper TTLs and key rotation; never skip signature validation on fetch errors.
- Per-provider/tenant quotas and rate limits, isolating slow IdPs from exhausting thread pools.
- Health checks for the broker, caches/sessions/databases, and audit pipelines.
- Graceful fallback UX ("IdP A is currently unavailable") without routing users to IdP B unless a verified identity link exists.
- Never log codes, tokens, client secrets, cookies, or assertions.

## 17. Pre-Production Test Matrix

| Test Case | Expected Outcome |
| --- | --- |
| App login via broker → IdP A | App receives **broker issuer/`sub`**, not upstream token |
| App login via broker → IdP B | Same downstream issuer, accurate account mapping for upstream B |
| Upstreams A and B share `sub=user-42` | Two distinct external identities; never auto-linked |
| A and B share email yet have different `iss+sub` | Never merged without proof/admin approval |
| User changes email at A while `sub` stays unchanged | Resolves to same broker user |
| User switches IdP via approved migration | New link points to the right broker user with full audit |
| New non-allowlisted IdP | Broker never trusts query-supplied issuer URLs |
| Upstream callback with wrong `state` | Reject; do not exchange authorization code |
| Upstream callback issuer mix-up | Reject; do not send code/secret to another token endpoint |
| Upstream ID Token with wrong `aud` | Reject even if signature is valid |
| Upstream ID Token with wrong `iss` | Reject; do not map identity |
| Expired or wrong-nonce upstream ID Token | Reject; do not create broker session |
| Broker ID Token used as API access token | Reject when API enforces token type/audience |
| Broker token with wrong `aud` | Downstream app/API rejects |
| JWT with `alg=none` or untrusted key | Reject |
| Upstream claim `role=admin` | Never auto-grants admin in app |
| Broker user `DISABLED` | No new session/token issued per policy |
| Revoked tenant membership | API/app denies even if old token is unexpired per revocation policy |
| First broker login with colliding email | Requires linking proof; no automatic takeover |
| Multi-tab upstream A/B callbacks arriving out of order | Client registrations and expected issuers stay isolated |
| Invalid SAML signed assertion from IdP C | Broker rejects; issues no OIDC token |
| Transient SAML `NameID` | Never used automatically as a long-term identity key |
| Broker signing key rotation | Overlapping JWKS rollover; apps validate cleanly |
| Upstream key rotation | Broker refreshes JWKS for right issuer and rejects untrusted keys |
| App local logout | Never promises upstream IdP logout |
| Back-channel logout when supported by IdP | Verify downstream sessions are revoked as designed |
| Upstream outage | Displays dedicated error without falling back to wrong identity |
| OIDC login behind proxy | Redirect URI, issuer, and cookies match public HTTPS origin |
| Log hygiene | Zero raw tokens/secrets/cookies; redacted correlation present |

**Test layers:** unit tests for `issuer+sub` mapping; Spring Security `oauth2Login` integration against a controlled OIDC test provider; broker integration against upstream OIDC/SAML sandboxes; browser E2E for redirects/cookies/multi-tab; negative security tests for token substitution, mix-up, and account-link takeover. Use test keys and synthetic data; never paste production tokens into web decoders.

## 18. Rollout Playbook for Putting an Identity Broker into Production

1. **Inventory:** catalog apps, tenants, upstream issuers, protocols, clients, algorithms, PKCE/redirects, tenant permissions, and lifecycle processes.
2. **Select broker:** prefer an IAM with OIDC Provider + upstream federation, HA, MFA/step-up, auditing, and account linking; if custom-built, establish clear Authorization Server ownership.
3. **Define trust contracts:** apps trust the broker issuer; the broker trusts each upstream issuer/SP metadata; exact keys/redirect URIs without mixing audiences.
4. **Define identity mapping:** upstream `issuer+sub` or stable SAML NameID; immutable broker user ID; tenant mapping; never email as key.
5. **Onboarding/linking:** first-login flows, invitations/SCIM, conditional JIT, uniqueness/transactions; email match is only a suggestion signal, not proof.
6. **Routing:** per-tenant approved IdP policies; `login_hint`/`kc_idp_hint` assist UX only and grant no authority.
7. **Token policy:** lifetimes, signing JWKS, audiences/scopes, refresh/revocation, client secret protection, provenance, and assurance mapping.
8. **Logout/deprovisioning:** design local/broker/upstream sessions, back-channel support, and user-disable handling; never assume global SLO.
9. **Testing:** test multi-IdP, subject collisions, token validation, mix-up, keys/redirects/SSRF, CSRF, step-up, and outages.
10. **Phased rollout:** start with one sandbox app/IdP, canary tenants, monitor login success/error rates, auditing, rollback, and mapping migrations.
11. **Long-term operations:** metadata/key rotation, broker patching, backing DB/session/Redis maintenance, backups, alerting, and incident response.

### Knowledge Check

**Why not configure two `ClientRegistration` entries on the portal and call it a broker?** Because then the portal is a direct RP of two IdPs. A true broker must act as an OP issuing fresh authorization codes/ID Tokens to downstream apps.

**Why not pass upstream `sub` straight through as downstream `sub`?** Because `sub` is scoped to its issuer; it can collide across IdPs or be pairwise per RP. The broker needs a managed broker subject and reliable mapping.

**Is `email_verified=true` enough to auto-link two accounts across two IdPs?** No. Emails can be recycled or verified under different policies. Linking requires proof/admin approval/contract and checks on who already owns the link.

**If IdP A returns a valid token whose `aud` is the broker, can App B use it?** No. App B must accept a broker-issued token scoped to B's audience or use an explicit delegation/token-exchange protocol.

**Does broker logout guarantee every upstream and downstream session is logged out?** No; it requires explicit support and testing of RP-initiated/front/back-channel logout or SAML SLO, session alignment, and revocation.

## 19. Standards and Implementation Guides

1. [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): `iss`, `sub`, `aud`, `nonce`, ID Token validation, public/pairwise subject identifiers.
2. [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): discovery, issuer metadata, and JWKS.
3. [OAuth 2.0 Security Best Current Practice – RFC 9700](https://www.rfc-editor.org/rfc/rfc9700.html): PKCE, exact redirect matching, state, mix-up/issuer, and token defenses.
4. [OAuth 2.0 Authorization Server Issuer Identification – RFC 9207](https://www.rfc-editor.org/rfc/rfc9207.html): `iss` in authorization responses to prevent multi-AS mix-up.
5. [Spring Security – Servlet OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html) and [OAuth2 Client](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html): `oauth2Login`, ClientRegistration, OIDC RP.
6. [Spring Boot – OAuth2 Client configuration](https://docs.spring.io/spring-boot/reference/security/oauth2.html): multiple client registrations, `issuer-uri`, default redirect URI.
7. [Spring Authorization Server – Social Login Guide](https://docs.spring.io/spring-authorization-server/reference/guides/how-to-social-login.html): combining Authorization Server and upstream OAuth2Login.
8. [Spring Security 7 – Authorization Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/authorization-server/index.html): Authorization Server/OP role, clients, issuer, and token signing.
9. [Keycloak – Identity Brokering](https://www.keycloak.org/docs/latest/server_admin/#_identity_broker): upstream OIDC/SAML, first broker login, identity provider configuration, and linking.
10. [OpenID Connect RP-Initiated Logout](https://openid.net/specs/openid-connect-rpinitiated-1_0.html) and [Back-Channel Logout](https://openid.net/specs/openid-connect-backchannel-1_0.html): sessions, logout, and downstream propagation.
11. [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): CSRF, redirects, token validation, and multi-AS threats.

**Conclusion:** implementing an identity broker means establishing **two independent authentication boundaries**: the broker verifies external IdPs and maps external identities to broker users, while applications verify **broker-issued tokens** for the right issuer and audience. Success hinges on isolating issuer/`sub`, protecting OAuth2 code+state+PKCE, never linking accounts by email alone, enforcing independent tenant authorization, governing tokens/keys, and managing sessions/logout across all legs.