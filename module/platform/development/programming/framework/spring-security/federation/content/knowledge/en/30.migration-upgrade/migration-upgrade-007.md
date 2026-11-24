# Migrating Applications from CAS or SAML to OIDC via an Identity Broker

**Module:** Spring Security – federation  
**Parent topic:** Migration and Upgrade  
**Context:** A legacy Java/Spring application using CAS or SAML2 needs to migrate to OpenID Connect (OIDC) through an **identity broker**, while centralized identity infrastructure or legacy identity providers may remain active during a transition period.  
**Illustrative technologies:** Java 17+, Spring Boot 3.x, Spring Security 6.x, OAuth2 Login/OIDC, CAS protocol, SAML 2.0 Web Browser SSO, and an IdP broker such as Keycloak or an equivalent product. URLs, accounts, and certificates in this article are **fictional examples**, not a running system.

## 1. Migration Objectives

A successful migration is not merely replacing CAS filters or SAML2 login with `oauth2Login()`. The objectives are:

1. **The application speaks OIDC with the broker**, rather than maintaining multiple legacy protocols simultaneously.
2. **The broker handles upstream CAS/SAML relationships** with proper adapters/trust configuration; the app trusts only the broker's **OIDC issuer**.
3. **Users retain the exact same local accounts, business permissions, and tenants** whether signing in via the legacy upstream or the new broker; never auto-link erroneously by email.
4. **OIDC Authorization Code flow** protects `state`, `nonce`, PKCE (when deployed per client/profile), redirect URI, token signatures/claims, and browser sessions.
5. **Logout, timeouts, reauthentication, MFA/LoA, and revocation** have explicit semantics: never promise that logging out at one layer automatically terminates sessions across all layers.
6. Support **cohort rollout, observability, and rollback** without corrupting account-linking data or resource permissions.
7. Maintain positive/negative SSO tests on both sides of the trust boundary and preserve security when the broker/IdP/proxy fails.

**Boundary:** This is a migration of **authentication federation between a web app and the IdP system**. An OIDC ID Token authenticates the user to the client; it does **not** automatically replace an OAuth2 access token for API protection, and the broker does not define business permissions in your database.

## 2. How Do CAS, SAML2, and OIDC Differ?

| Property | CAS Protocol | SAML 2.0 | OIDC |
| --- | --- | --- | --- |
| Common web flow | Browser receives a **service ticket** (ST); service verifies via CAS server | Browser delivers XML `SAMLResponse` to ACS | Browser delivers **authorization code** to redirect URI; client exchanges code for tokens |
| Authentication evidence reaching app | Result of single-use ticket verification bound to **service URL** | Signed Response/Assertion with Issuer, Audience, Conditions | ID Token/JWT + code flow result, issuer, and audience |
| Metadata/trust | CAS endpoints, TLS, registered service; ticket validation | IdP entityID, SAML metadata, trusted X.509 signing keys | OIDC Discovery issuer, JWKS, client registration/secret or client auth |
| User data | `cas:user` and attributes from validation response | `NameID`, `AttributeStatements`, `AuthnContext` | `iss`, `sub`, `auth_time`, `acr`/`amr`, profile/email/groups when issued |
| Stable principal | CAS user ID depending on deployment | `NameID` format + IdP entityID, may be transient | **(iss, sub)** within the OP context; pairwise `sub` depends on client/sector |
| Session at app | App session + CAS TGC/SSO session | App session + IdP session | App session + broker OP session + upstream IdP session |
| Logout | CAS logout / Single Logout (deployment-dependent) | SAML SLO (front-channel or back-channel) | RP-Initiated Logout, front/back-channel logout if supported by OP/RP |
| Roles | Does not grant app permissions by default | Attributes/Groups are not app roles by default | Claims/scopes are not resource permissions automatically |

**A CAS service ticket is not an OIDC authorization code.** Never rename the `ticket` parameter to `code` or forward a ticket straight to an API pretending it is an OAuth token. CAS STs are normally single-use and bound to an exact service; they must be verified by the CAS server over a trusted channel.

**A `SAMLResponse` XML is not an ID Token.** The broker must verify SAML Issuer/signature/audience/destination/time/subject/replay upstream **before** issuing an OIDC ID Token downstream to the application.

**OIDC differs from plain OAuth2:** Only when the client requests the `openid` scope and implements OIDC does the app receive an ID Token to authenticate identity. An OAuth2 access token has an audience/scope meant for a resource server; never use an ID Token as an arbitrary Bearer API credential.

## 3. Architecture Before and After

### Before Migration

~~~text
                    +----------------------+
Browser ----------> | Spring Application   |
                    | CAS client filter    | ---> CAS Server /serviceValidate
                    | or SAML2 ACS         | ---> SAML IdP (metadata, signing cert)
                    | business authorization|
                    +----------------------+
~~~

The application typically has:

- CAS client filters, CAS service URL, CAS `/login`, `/serviceValidate`, possibly CAS proxy tickets.
- Or Spring Security SAML2 configuration, `RelyingPartyRegistration`, `/saml2/authenticate/{registrationId}`, `/login/saml2/sso/{registrationId}`.
- Custom logic mapping CAS username/SAML NameID/groups to users, authorities, and sessions.
- Legacy protocol logout hooks or Single Logout endpoints.
- An existing business database (users/permissions/tenant/ownership) that must not be corrupted when changing login protocols.

### After Migration: Broker in the Middle

~~~text
  Browser / Session
         |
         v
  Spring Boot application (OIDC Relying Party / OAuth2 Client)
         |
         | Authorization Code (+ PKCE when configured)
         | OIDC ID Token verified from broker; iss+sub
         v
  Identity Broker (downstream OIDC OpenID Provider)
         |
         +------ Upstream SAML2 SP <------ Legacy SAML IdP
         |
         +------ Supported CAS connector <-- Legacy CAS server
         |        OR upstream OIDC/SAML capability of CAS
         |
         +------ optional enterprise OIDC/Social IdPs
         |
         v
  Broker subject mapping + upstream identity links
         |
         v
  App local user ID + app DB roles/resource authorization
~~~

**The broker plays two distinct roles:**

- **Upstream:** the broker is a **SAML Service Provider** to a SAML IdP, or a CAS client via an appropriate connector, or an OIDC Relying Party if the upstream CAS server provides OIDC.
- **Downstream:** the broker is an **OpenID Provider (OP)** issuing authorization codes, ID Tokens, and other tokens to the Spring application.

Never confuse the two credential/trust pairs:

- SAML IdP signing certificate or CAS server trust → used by the **broker** to verify upstream login.
- Broker OIDC issuer, client registration, JWKS, TLS → used by the **Spring app** to verify tokens issued by the broker.

Even when the broker validly verifies a SAML assertion, the Spring app still must **validate the broker's ID Token**; the app no longer trusts the upstream XML/SAML signing cert directly in the new flow.

## 4. Choosing a Migration Path from CAS

**Do not assume every identity broker includes a built-in CAS identity-provider adapter.** Some products support only SAML/OIDC upstream by default; a CAS bridge may be an extension, custom connector, or an OIDC/SAML-issuing capability on the CAS server itself. Verify the version and security support of **your specific product**.

Three common options:

### A. CAS Server Supports OIDC or SAML2 as Upstream

If the CAS deployment supports acting as an **OIDC Provider** or **SAML2 IdP**, prefer standard protocols natively supported by the broker:

~~~text
CAS Server (OIDC/SAML endpoint) --> Broker (OIDC RP / SAML SP)
                                       |
                                       v
                                Spring App (OIDC RP)
~~~

Advantage: fewer custom protocol adapters. You must verify **actual endpoints, versions, licensing, and config**; the fact that a CAS product *can* offer OIDC does not mean the current deployment has it enabled with the right issuer/clients/metadata.

### B. Broker Supports Upstream CAS via a Maintained Connector

~~~text
Legacy CAS Server -- service ticket --> CAS connector at broker
                                                |
                                                v
                                        Broker OIDC OP
                                                |
                                                v
                                          Spring App
~~~

The CAS connector must:

1. Register an **exact service URL** on CAS.
2. Redirect login to the CAS server over HTTPS and receive a service ticket.
3. Validate the ticket server-to-server via `/serviceValidate` (or the endpoint matching the protocol version).
4. Verify TLS/hostname, ticket validity, service binding, ticket reuse/replay, and fail closed.
5. Take user ID/attributes only from **verified** CAS validation output, never from client-supplied queries/headers.
6. Create an upstream identity link carrying its own issuer/source ID; never auto-promote `cas:user` to a local account without policy.
7. Have version updates, security reviews, and an operational owner; community connectors must never be assumed "secure by default."

### C. An Independently Reviewed Translation Service

When no native connector exists, an organization-maintained gateway/adapter may be needed to verify CAS tickets and pass claims into the broker under a properly designed trust contract. This carries high security/operational cost; never implement it by:

- Putting an unvalidated CAS ST into an OIDC claim.
- Trusting headers like `X-User` from a browser.
- Turning an ST into an authorization code merely by renaming parameters.
- Self-signing JWTs for the Spring app to trust without issuer/audience/key-management/replay protections.

**Architectural decision:** If no supported native CAS connector exists, **prefer CAS's OIDC/SAML capability or a standard broker migration path**. Never claim you migrated to OIDC simply because the frontend receives a home-grown token.

### CAS Proxy Tickets / PGT and Delegation

If the legacy app used **Proxy Granting Tickets (PGT)/Proxy Tickets (PT)** to call downstream CAS services on behalf of a user, OAuth2/OIDC browser login does not automatically provide CAS-style delegation. Inventory downstream APIs and design replacements (OAuth2 access tokens with right audience/scopes, standard token exchange if supported by the AS, or policy-governed service-to-service credentials), or maintain the CAS proxy path in a separate phase.

Migrating only the login UI while ignoring CAS proxy delegation can leave users able to log in while background business workflows break.

## 5. Choosing a Migration Path from SAML2

For SAML IdPs, most brokers support configuring an upstream SAML2 IdP. Acting as a SAML SP, the broker requires configuring:

- **The broker's SAML SP EntityID**, broker ACS endpoint, and SP metadata if needed.
- Expected **IdP entityID**, SSO endpoints, and **IdP signing X.509 verification credentials**.
- Signed Response/Assertion rules per profile and IdP contract.
- **Issuer, AudienceRestriction, Destination, Recipient, InResponseTo, NotBefore, NotOnOrAfter**, SubjectConfirmation, unique IDs, and replay protection.
- XML parser hardening (no XXE, no arbitrary external entities/DTDs).
- Metadata fetch only from trusted sources, plus key rotation/`validUntil`/`cacheDuration`/refresh policy.
- Logout capabilities if SAML Single Logout is used.
- Attribute/NameID mapping with the exact format: persistent NameID vs. transient NameID.

**Do not treat `NameID` as equivalent to OIDC `sub`.** A transient NameID can change on every login; emails can also change or be shared. The broker must assign its own **stable broker subject** and store upstream identity links (IdP entityID + persistent external subject) to the broker account.

### SAML→OIDC Trust Flow

~~~text
SAML IdP
  signed Assertion (NameID, AttributeStatement, AuthnContext)
       |
       v
Broker SAML validator
  - verify trusted IdP signing key
  - Issuer, Audience, Destination, InResponseTo, time, replay
  - select signed/validated assertion only
       |
       v
Broker account-link policy + OIDC OP
  - assign stable broker sub for downstream client
  - issue ID Token with broker iss, sub, aud, exp, nonce
       |
       v
Spring OAuth2/OIDC Login
  - validate broker issuer/JWKS/signature/claims
  - map (broker iss, sub) -> local user ID
  - enforce app authorization
~~~

**Vulnerabilities to prevent:** SAML Signature Wrapping (broker verifies signature on Assertion A yet reads attributes from Assertion B), untrusted KeyInfo/IdP metadata, wrong issuer, mismatched ACS, replay, and duplicate IDs. The broker is not a "security bypass"; it becomes a new trust-critical service.

## 6. Designing the Identity Model to Prevent Duplicate Accounts

This is usually the hardest part—not swapping the `SecurityFilterChain` configuration.

### 6.1. Three Separate Identity Layers

1. **Upstream identity:** `(source, upstreamIssuer, upstreamSubject)` — CAS username/ticket-validation subject or SAML IdP EntityID + NameID/persistent ID.
2. **Broker identity:** `(brokerIssuer, brokerSubject)` — broker OP issues `iss` and `sub` to the app; a broker account may link multiple upstream identities after appropriate proof.
3. **Local business identity:** immutable `user_id` in the app DB holding roles, tenant, orders, audits, ownership, and enabled status.

Example:

~~~text
Upstream CAS:
    source=cas-prod
    issuer=https://cas.example.test/cas
    subject=E08142

Upstream SAML:
    source=saml-hr
    issuer=https://idp.example.test/metadata
    subject=persistent-9fb0

Broker:
    iss=https://broker.example.test/realms/enterprise
    sub=broker-user-73a1

Application DB:
    user_id=42
    tenant_id=acme
    role=REPORT_VIEWER
    enabled=true
~~~

Never infer `E08142 = persistent-9fb0 = broker-user-73a1` from a matching email address. Links must come from **verified identifiers and an approved migration table**, strong user reauthentication, or an account-linking step with proof and approval.

### 6.2. Illustrative Migration Data Schema

~~~sql
CREATE TABLE local_user (
    id BIGINT PRIMARY KEY,
    tenant_id VARCHAR(100) NOT NULL,
    enabled BOOLEAN NOT NULL,
    role_code VARCHAR(100) NOT NULL
);

CREATE TABLE identity_link (
    id BIGINT PRIMARY KEY,
    local_user_id BIGINT NOT NULL REFERENCES local_user(id),
    identity_source VARCHAR(40) NOT NULL,
    issuer VARCHAR(500) NOT NULL,
    subject VARCHAR(500) NOT NULL,
    tenant_id VARCHAR(100) NOT NULL,
    link_status VARCHAR(24) NOT NULL,
    approved_at TIMESTAMP NULL,
    UNIQUE(identity_source, issuer, subject, tenant_id)
);
~~~

**This is an illustrative schema**; adjust VARCHAR lengths and constraints for your DB engine. Enforce tenant consistency with `local_user` and policies on multiple links per user or shared accounts per business rules; migration operations must be transactional and audited. With OIDC broker pairwise subjects, `sub` can vary by client or sector identifier, so check before changing redirect URIs or client registrations.

**Never use `email`, `displayName`, or `preferred_username` as a unique linking key**, as they can change, may be unverified, or may not be unique across issuers/tenants.

### 6.3. First-Login / Account Linking Policy

Some brokers provide **first broker login / account linking**. Decide explicitly:

- For enterprise-managed users, prefer **pre-provisioned mappings** (authoritative IAM/HR ID) or explicit verified linking.
- Create new users only through an onboarding policy (invitation/approved tenant, MFA/LoA if required).
- Never auto-link to an existing local user solely on matching email; require proof of account ownership and tenant match.
- Never merge accounts across two upstream issuers/tenants by username local-part.
- Deny login if a mapping is ambiguous/missing when policy requires pre-migration.
- Emit audit events: `LINK_APPROVED`, `LINK_REJECTED`, `LINK_CONFLICT`, `USER_DISABLED`.
- Do not delete legacy mappings before the rollback window ends; never store raw `SAMLResponse`s or CAS STs in the link table.

### 6.4. Public vs. Pairwise OIDC Subjects

Per OIDC, `sub` is stable within an issuer and may be **public** (same `sub` across clients) or **pairwise** (different `sub` per sector identifier). Changing brokers, clients, or sector identifiers can change `sub`. Therefore:

- Record the **broker's** `iss` + `sub` as the lookup key in the downstream app.
- Keep immutable `local_user_id` decoupled from `sub`.
- Verify how client registration/redirect URI changes affect pairwise subjects prior to cutover.
- When changing broker issuers, never "rewrite all `sub`s automatically"; migrate links via verified mappings.
- Design a controlled dual-read phase: look up both legacy and broker identities **only after protocol-specific validation**.
- Never let clients specify issuer/JWKS URLs in login requests, avoiding issuer mix-up/SSRF.

## 7. Claims, MFA, and Authority Mapping: Differences You Cannot Ignore

| Legacy Source | Possible OIDC Broker Claim | Migration Rule |
| --- | --- | --- |
| CAS validated username | Broker `sub`, `preferred_username` | Broker `sub` is canonical; username is display-only |
| CAS attributes | `email`, `name`, custom claims | Minimal release; verify provenance & purpose |
| Persistent SAML NameID | Upstream link -> broker account | Do not copy straight to `sub` without checking stability |
| Transient SAML NameID | Unsuitable as a long-term key | Require a guaranteed persistent upstream ID |
| SAML AttributeStatement (`groups`) | `groups` or custom claim | Allowlist mapping; never auto-grant `ROLE_ADMIN` |
| SAML `AuthnContext` | `acr`/`amr` if broker maps semantics accurately | Enforce assurance policy; never assume equivalence |
| CAS `renew` / forced login semantics | `prompt=login`, `max_age`, `auth_time` per OP support | Test actual support and reauthentication behavior |
| SAML `ForceAuthn`/`RequestedAuthnContext` | OIDC `prompt`/`max_age`/`acr_values` | Do not assume equivalence if broker does not enforce |
| Legacy SLO | OIDC logout/session events | No 1:1 equivalent; design separately |
| CAS PT/PGT proxy delegation | OAuth2 access token / token exchange | Requires dedicated use-case/API architecture |
| Local DB roles | App-issued `GrantedAuthority` | App remains primary authority for business permissions |

**Especially for MFA:** A broker may hold an old session without knowing whether a recent upstream login satisfied required factors. For step-up auth, require `acr`/`amr`/`auth_time` semantics trusted by the broker, enforcing `max_age`/`prompt` or upstream reauthentication per policy; **never arbitrarily assign `acr=mfa`** simply because the IdP generally supports MFA.

**Crucially:** A broker may emit `groups`, yet the app must not map all of them to `GrantedAuthority`. Use an allowlist and/or local DB policy, tenant isolation, account-enabled checks, and role-revocation SLAs. OIDC scopes `openid profile email` do not equal `REPORT_VIEWER`/`ADMIN` permissions.

## 8. Configuring Spring Boot 3 / Spring Security 6 as an OIDC Client

### 8.1. Maven Dependencies

In a Spring Boot project with an appropriate BOM/parent:

~~~xml
<dependencies>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-security</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-oauth2-client</artifactId>
  </dependency>
  <dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
  </dependency>
  <dependency>
    <groupId>org.springframework.security</groupId>
    <artifactId>spring-security-test</artifactId>
    <scope>test</scope>
  </dependency>
</dependencies>
~~~

**Do not** leave Spring SAML2 Service Provider or legacy CAS client dependencies behind once legacy paths are fully disconnected; during dual-stack phases they may remain isolated in separate filter chains by design. Never include the old Spring Security SAML Extension as a dependency of the new OIDC login.

### 8.2. `application.yml`

**src/main/resources/application.yml**

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          enterprise-broker:
            provider: enterprise-broker
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            client-authentication-method: client_secret_basic
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: openid,profile,email
        provider:
          enterprise-broker:
            issuer-uri: https://broker.example.test/realms/enterprise

server:
  forward-headers-strategy: none
~~~

**This is an illustrative configuration for a confidential server-side web client**; `client-id`/`client-secret` must come from a secrets manager, never committed to Git. Domain `example.test` is a placeholder; replace with an issuer offering valid OIDC Discovery and client configuration on the broker.

Key points:

- **`issuer-uri`** must match `iss` in the ID Token; the Spring OIDC client can use `.well-known/openid-configuration` discovery to locate authorization, token, and JWKS endpoints.
- `scope` must include **`openid`** for OIDC-specific login; omitting `openid` routes through OAuth2 `UserService` instead of OIDC.
- `/oauth2/authorization/enterprise-broker` is the default URL to start Authorization Code login.
- Default callback `/login/oauth2/code/enterprise-broker` is the redirect URI where the broker returns the authorization code.
- **The redirect URI must be registered identically on the broker**; never derive it dynamically from untrusted `Host`/`X-Forwarded-Host` headers. Behind a proxy with a public HTTPS URL, configure trusted base URL / forwarded headers per threat model.
- `forward-headers-strategy: none` is a cautious default in the illustration to avoid untrusted headers; it is **insufficient** if public callback URLs are otherwise built from an internal host. When `NATIVE`/`FRAMEWORK` is needed, the edge must strip/rebuild forwarded headers and restrict trusted proxies.
- Spring Security's OIDC client normally handles `state`, `nonce`, and signature/claim validation in the configured flow; **test your specific version/provider** and add PKCE per policy.
- Even confidential backend clients should consider **PKCE S256** if supported by the broker, especially where redirect/callback code injection is a risk. Never claim `client_secret` alone replaces all code-interception defenses.

### 8.3. Minimal `SecurityFilterChain`

**src/main/java/com/example/migration/OidcSecurityConfig.java**

~~~java
package com.example.migration;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class OidcSecurityConfig {

    @Bean
    SecurityFilterChain security(HttpSecurity http)
            throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/error", "/login").permitAll()
                .requestMatchers("/admin/**").hasRole("ADMIN")
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());

        return http.build();
    }
}
~~~

This is a **Spring Boot configuration fragment**: it requires a main class, client registration, a real broker, and local authority mapping. No real enterprise broker exists at `example.test`. `oauth2Login()` authenticates downstream OIDC, yet **does not look up a local account, tenant, or database roles automatically**.

**Never disable CSRF** application-wide just to make OIDC callbacks work. Browser session cookies need session fixation protection, `Secure`/`HttpOnly`/`SameSite`, HTTPS, and CSRF protection on unsafe actions. Logout POST/redirect endpoints must follow security policy.

### 8.4. Using `OidcUser` After Validation, Never Trusting Arbitrary Data

Example controller returning only **masked or pseudonymous identity** after Spring Security authentication:

~~~java
package com.example.migration;

import java.util.Map;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.core.oidc.user.OidcUser;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class AccountController {

    @GetMapping("/api/session")
    public Map<String, String> session(
            @AuthenticationPrincipal OidcUser oidcUser) {
        // Illustrates concept; never log raw tokens.
        return Map.of(
            "provider", "enterprise-broker",
            "authenticated", Boolean.toString(
                oidcUser != null));
    }
}
~~~

**Do not write:** looking up a local account solely by `oidcUser.getEmail()` or logging `getIdToken().getTokenValue()`. Account linking must use verified `iss + sub` with tenant policy, never an unchecked email string.

### 8.5. Integrating OIDC Claims with Local Account Mapping

In Spring Security, extension points include **`OidcUserService`**, `OAuth2UserService<OidcUserRequest, OidcUser>`, `GrantedAuthoritiesMapper`, and success handlers. To preserve business permissions:

1. Spring Security validates the authorization code response, ID Token, and broker issuer, producing `OidcUser`.
2. Read `oidcUser.getIdToken().getIssuer()` and `oidcUser.getSubject()` **only from the validated authentication result**.
3. Look up the approved `(broker issuer, broker sub, tenant)` mapping in the DB.
4. Check account enabled/locked status, tenant policy, approved link status, and role revocation.
5. Build authorities from app DB / policy engine or allowlisted trusted claims; **never copy raw groups**.
6. Deny on missing/ambiguous links per the migration contract; never auto-create admins.
7. Establish `SecurityContext`/session through the framework; never craft authenticated tokens from request parameters.
8. On subsequent requests, enforce policies for role updates, disabled accounts, and session revalidation.

**Fragment handling identity lookup in the post-validation callback:**

~~~java
// Fragment inside an OidcUserService wrapper / login success handler.
// oidcUser is the result returned from a valid OIDC login pipeline.
String brokerIssuer =
    oidcUser.getIdToken().getIssuer().toString();
String brokerSub = oidcUser.getSubject();

LocalAccount local = links.findApprovedByBrokerIdentity(
    brokerIssuer, brokerSub, tenantFromTrustedPolicy);

if (local == null || !local.enabled()) {
    throw new OAuth2AuthenticationException(
        new OAuth2Error("account_link_not_approved"));
}

// Map local roles/authorities from DB.
// Never use user-provided email or X-Role header.
~~~

This is a **non-compilable illustrative fragment** because `LocalAccount`, `links`, `tenantFromTrustedPolicy`, and imports belong to your project. Its purpose is to show the right trust boundary; throw the appropriate exception type in the right authentication extension hook and handle failures so clients never see PII details. `tenantFromTrustedPolicy` must come from broker-validated context or registration/local-mapping config, never an arbitrary query parameter.

### 8.6. When APIs Need Protection

A Spring app using `oauth2Login` is a **web login client**. If APIs are called with bearer tokens, add **OAuth2 Resource Server** and validate **access tokens** for issuer, audience, signature/algorithm, `exp`, `nbf`, and scopes/permissions. **An ID Token is not an access token** for APIs.

Never use an access token obtained for the broker's UserInfo endpoint to invoke arbitrary downstream APIs; audience, authorization server, and scopes must match the target resource.

## 9. Standalone Java 17: Simulating Accurate Linking and Blocking Account Confusion

This exercise does not call real CAS/SAML/OIDC. It simulates **already-verified authentication results** and maps two external identities of the same user to one local user ID, while blocking email collisions, wrong issuers, unknown subjects, and unverified inputs.

**File: `BrokerIdentityMigrationDemo.java`**

~~~java
import java.util.Map;

public final class BrokerIdentityMigrationDemo {

    record ExternalIdentity(
        String source, String issuer, String subject) { }

    private static final Map<ExternalIdentity, String>
        APPROVED_LINKS = Map.of(
            new ExternalIdentity(
                "CAS", "https://cas.example.test/cas", "E08142"),
            "LOCAL-42",
            new ExternalIdentity(
                "OIDC",
                "https://broker.example.test/realms/enterprise",
                "broker-user-73a1"),
            "LOCAL-42");

    static String resolve(ExternalIdentity identity,
            boolean cryptographicallyOrProtocolVerified) {
        if (!cryptographicallyOrProtocolVerified) {
            return "DENY_UNVERIFIED";
        }
        String local = APPROVED_LINKS.get(identity);
        if (local == null) {
            return "REVIEW_OR_DENY_UNLINKED";
        }
        return local;
    }

    public static void main(String[] args) {
        ExternalIdentity oldCas = new ExternalIdentity(
            "CAS", "https://cas.example.test/cas", "E08142");
        ExternalIdentity broker = new ExternalIdentity(
            "OIDC",
            "https://broker.example.test/realms/enterprise",
            "broker-user-73a1");
        ExternalIdentity wrongIssuer = new ExternalIdentity(
            "OIDC", "https://evil.example.test",
            "broker-user-73a1");
        ExternalIdentity unknown = new ExternalIdentity(
            "OIDC",
            "https://broker.example.test/realms/enterprise",
            "another-user");

        String oldAccount = resolve(oldCas, true);
        String newAccount = resolve(broker, true);
        System.out.println("legacy=" + oldAccount);
        System.out.println("broker=" + newAccount);
        System.out.println("sameAccount=" +
            oldAccount.equals(newAccount));
        System.out.println("wrongIssuer=" +
            resolve(wrongIssuer, true));
        System.out.println("unknownSubject=" +
            resolve(unknown, true));
        System.out.println("unverifiedToken=" +
            resolve(broker, false));
        System.out.println("emailAutoLink=false");
    }
}
~~~

Compile and run with **JDK 17**:

~~~bash
javac BrokerIdentityMigrationDemo.java
java BrokerIdentityMigrationDemo
~~~

**Deterministic stdout:**

~~~text
legacy=LOCAL-42
broker=LOCAL-42
sameAccount=true
wrongIssuer=REVIEW_OR_DENY_UNLINKED
unknownSubject=REVIEW_OR_DENY_UNLINKED
unverifiedToken=DENY_UNVERIFIED
emailAutoLink=false
~~~

**What this proves:** two **link-approved** identities resolve to the same local ID. Wrong issuers and unknown subjects never accidentally map to that user. The `verified` flag in the demo is only test-harness input, **not** a SAML/OIDC/CAS verification mechanism; never accept `verified=true` from an HTTP request.

**What it does not prove:** SAML XML Signature verification, CAS ST validation, OIDC JWT/JWKS verification, TLS, nonce/state/PKCE, broker sessions, or authorization. Let official libraries handle the protocol, then apply this approved-link lookup to **validated results** alongside real tenant and account-status checks in the DB.

## 10. Phased Migration, Not Big-Bang

### Phase 0 – Current-State Inventory

Compile an accurate list:

- Is each app using a **CAS client**, Spring Security SAML2, legacy Spring Security SAML Extension, or custom SAML code?
- CAS server version/protocol, ticket validation endpoint, and `service` URL.
- Are CAS **Proxy Granting Tickets/Proxy Tickets** used to call downstream services?
- SAML IdP entityID, signing certificate, metadata, NameID format, signature policy, ACS/SLO endpoints.
- Client lists, redirects, proxy/ingress Host/Proto, cookie domain, CSP/CORS/SameSite.
- Legacy user mapping: username/email/NameID → `user_id`, roles, disabled/locked status, tenant.
- Session/logout/revocation SLAs and MFA/step-up requirements.
- Do service accounts, batch jobs, or API calls rely on CAS/SAML user sessions?
- Recovery/rollback owners, support desk, and production observability.

**Output:** per-app migration matrix, broker upstream adapter readiness, user link quality, risks, and cutover plan. Do not roll out "working OIDC" before mapping all existing auth and delegation paths.

### Phase 1 – Prepare Broker and Trust

1. Select a broker/version offering stable OIDC OP support, HA/backup/recovery, auditing, and key rotation.
2. For SAML upstream: register the broker SAML SP at the IdP, import metadata/trusted signing keys, and verify issuer, audience, ACS, and SLO policies.
3. For CAS upstream: choose **CAS OIDC/SAML upstream** or a supported/reviewed CAS connector; validate service tickets server-side.
4. Configure broker realm/tenant, stable OIDC issuer URL, JWKS, signing algorithm policy, and signing key lifecycle.
5. Create an OIDC confidential client for the Spring app; register exact redirect URIs and post-logout redirect URIs if supported.
6. Configure HTTPS/TLS, proxy trust, egress, time sync, rate limits, and secrets storage.
7. Define broker identity linking, claims release, MFA/`acr`/`amr` semantics, and session lifetimes.
8. Create separate test identities/tenants; never use real secrets/keys in examples or CI.

**Acceptance:** the broker can authenticate a test user via upstream and emit a valid ID Token with **broker `iss`**, **stable `sub`**, **`aud`=app client**, `exp`/`iat`, and `nonce` when required.

### Phase 2 – Identity and Permission Mapping

- Export legacy identities following **security procedures**; never export credentials or tickets.
- Build the `identity_link` table/approved mappings by issuer+subject+tenant and local ID.
- Quantify matched, unmatched, conflicting, transient NameIDs, and email collisions.
- For users sharing emails across multiple issuers, **never auto-merge**; require verified linking/approval.
- Reconcile local roles/permissions per user; never let broker groups emit `ROLE_ADMIN` outside allowlists.
- Test disabled accounts and tenant isolation.
- Ensure existing users retain DB ownership/history; never change `user_id`.
- Record link evidence/approved revisions and rollout flags for rollback.

**Acceptance:** legacy login and broker login for the same user produce **the exact same local `user_id`**, creating no duplicate records or unauthorized permissions.

### Phase 3 – Controlled Dual-Stack

CAS/SAML and OIDC can run side by side during a short window or via blue-green deployment, only with an explicit design:

~~~text
Cohort old: browser -> CAS/SAML legacy chain
Cohort new: browser -> OIDC broker chain
Both: validated identity -> approved link -> same local user ID
~~~

**Never** let an unverified request pick a chain or switch auth mechanisms via query/header. With multiple `SecurityFilterChain`s, use `@Order`, specific `securityMatcher`s, non-overlapping callback routes, a default-deny fallback chain, and test every filter invocation. A simpler alternative is **separating deployments/hostnames** per cohort, reducing the risk of miswiring filters.

During dual-stack:

- Keep session keys/namespaces of the two flows isolated, or plan explicit session transitions.
- Never promote a CAS session into an OIDC session without performing broker login.
- Validate each protocol independently; never accept raw `NameID`/`CAS username` headers.
- Enforce server-side feature flags and rollback routes with clear cohort tracking.
- Never write emails or ID Tokens/JWTs into logs by default.
- Never route an OIDC callback to a SAML ACS or vice versa.

### Phase 4 – Canary, Measurement, and Cutover

Migrate a small cohort first, expanding as rollback confidence holds:

1. Test users and low-criticality apps.
2. One approved tenant/department.
3. Expand client/user cohorts once KPIs hold.
4. Establish freeze/maintenance windows if needed.
5. Switch the default login route to the OIDC broker, keeping legacy endpoints during a policy-bounded deprecation window only.
6. Disable legacy auth in the app once traffic drops to zero and downstream proxy use cases are resolved.

**KPIs go beyond login success:**

- Authorization Code callback success/failure; invalid `state`/`nonce`/`issuer`/`audience`.
- Broker upstream SAML signature / CAS ticket failures and latency.
- Unlinked/ambiguous user counts, newly created local accounts, duplicate-account incidents.
- Denied admin/tenant requests, role mismatches, disabled-account propagation.
- Browser SSO repeat-login rates and logout/session anomalies.
- End-to-end p95/p99 latency, broker HA/availability, login-loop rate.
- Refresh token lifetime / access-token usage if API calls exist.
- Audit privacy: zero raw tokens/NameIDs/`SAMLResponse`s in logs.

### Phase 5 – Retire Legacy and Clean Up

- Remove legacy CAS/SAML endpoints/clients from the app once zero dependencies remain.
- Revoke unused SP signing/decryption keys, CAS service registrations, SAML metadata/certs, and secrets via change control.
- Close old inbound callbacks or route them to a migration notice that performs no authentication.
- Retain mappings/audit records per retention policy without deleting user business records.
- Update runbooks, on-call guides, alert rules, support desk docs, and incident response.
- Verify no old dependencies or unsupported libraries remain on the classpath.
- Communicate re-login and logout UX so users do not hit confusing loops.

## 11. Logout, Sessions, and Reauthentication: Establish a New Contract

After migration there are at least **three sessions**:

~~~text
[1] Local HttpSession at Spring app
[2] OIDC broker OP browser session
[3] Upstream CAS TGC session or SAML IdP session
~~~

A Spring `session.invalidate()` only guarantees terminating **[1]**, not [2] or [3]. Broker logout may end [2], while upstream SSO [3] remains alive so the next login silently re-authenticates. CAS SLO, SAML SLO, and OIDC RP-Initiated Logout **do not share uniform semantics**.

### Recommended Logout Policy

1. Define **local logout**, **broker logout**, and **upstream IdP logout** separately.
2. If the OIDC broker supports RP-Initiated Logout and exposes `end_session_endpoint`, Spring can use `OidcClientInitiatedLogoutSuccessHandler` with `ClientRegistrationRepository`; configure `post_logout_redirect_uri` and ID Token hints per broker.
3. Verify broker support for front-channel/back-channel logout, session IDs, and upstream propagation; never assume every IdP implements SLO.
4. Enforce CSRF protection on logout, `SameSite`/`Secure`/`HttpOnly` cookies, and a return URL allowlist.
5. Define idle/absolute session timeouts, re-login policies, step-up MFA, and revoked/disabled account handling.
6. Test scenarios where the upstream IdP session remains active after broker logout; UX should explain when "sign out everywhere" is required.
7. When migrating from stateful SAML/CAS sessions to OIDC, never copy `SecurityContext` into a new session while bypassing OIDC validation.

**There is no automatic conversion** from a CAS logout token / SAML `LogoutRequest` into an OIDC logout event without an appropriate broker adapter and session/link state.

## 12. Preventing Protocol-Transition Vulnerabilities

| Threat | Migration Mistake | Control |
| --- | --- | --- |
| Issuer confusion | App trusts request-supplied `iss` and fetches dynamic JWKS | Fixed issuer allowlist; verify discovery/JWKS and `iss` claim |
| Invalid ID Token signature | Base64-decodes JWT payload and trusts it | Spring OIDC validation/JWK trust, algorithm allowlist |
| Wrong audience | ID Token for client A accepted at client B | Validate `aud` (and `azp` when required per OIDC semantics) |
| Login replay/CSRF | Missing `state`/`nonce`/session binding | `state`/`nonce`, exact callback, session integrity |
| Authorization code interception | Missing PKCE when client/profile requires it | PKCE S256 supported by broker/client, HTTPS, exact redirect |
| Open redirect | Redirect URI built from arbitrary `Host`/`Forwarded` | Exact registered URLs, trusted proxy config |
| Account takeover | Auto-linking on matching email | Approved issuer+subject identity linking |
| Privilege escalation | Raw broker groups turned into `ROLE_ADMIN` | Local authority policy/allowlist, tenant checks |
| SAML wrapping | Broker verifies Assertion A yet reads B | OpenSAML validator reading only the signed/validated node |
| CAS ST replay | Validating same service ticket multiple times or omitting service binding | One-time CAS server validation + service matching |
| Metadata SSRF | Broker fetches user-supplied SAML metadata URL | Admin allowlist, egress rules, TLS, trusted metadata |
| Key rotation abuse | Trusting any `KeyInfo`/JWKS URL named in payload | Trusted metadata/JWKS, controlled rotation |
| MFA downgrade | Assigning `acr=mfa` even when upstream didn't satisfy it | Verified LoA mapping and reauth policy |
| Token leakage | Logging code/token/cookie/`SAMLResponse` | Redacted logging, secrets protection |
| Session confusion | Reusing legacy session under OIDC | Separate verified flows, explicit session migration |
| Logout gap | Clearing app session only and claiming global SSO ended | Per-layer contract, test upstream persistence |
| Gateway failure | Falling back to anonymous/legacy headers when broker unavailable | Fail closed; controlled rollback deployment |
| API misuse | Using ID Token as access token | Resource Server with right audience/scopes |

**A centralized identity broker is also a high-value target.** Require HA, backup/restore, DR, admin MFA, secret/key rotation, least privilege, audit logs, rate limits, and incident playbooks. A compromised broker can issue trusted tokens to many apps; operational controls are part of security architecture.

## 13. E2E Testing for CAS→OIDC and SAML→OIDC

Every SSO test requires a **positive baseline** plus assertions on both broker and app—not just observing HTTP 302 or 200.

| # | Scenario | Expected |
| --- | --- | --- |
| 1 | Valid legacy CAS login via service ticket | Legacy path still works before cutover |
| 2 | Validly signed legacy SAML Response | Legacy path works before cutover |
| 3 | Broker authenticates upstream CAS (supported connector) | Ticket validated, broker session created |
| 4 | Broker authenticates upstream SAML | Signed Assertion trusted; right issuer/audience/time |
| 5 | OIDC Authorization Code broker → Spring | Valid ID Token, authenticated session |
| 6 | Legacy and broker identities for same user | **Same local `user_id`**, data preserved |
| 7 | Unmatched broker `sub` | Review/deny; never auto-link by email |
| 8 | Same email from two IdPs | Never merge against policy |
| 9 | Wrong broker issuer | App rejects |
| 10 | Wrong ID Token audience | App rejects |
| 11 | Expired ID Token | App rejects |
| 12 | Invalid JWS/signature | App rejects |
| 13 | Unknown/untrusted JWKS key | App rejects |
| 14 | Invalid `state` or `nonce` | Reject callback/login |
| 15 | Callback `redirect_uri` differs from registered URL | Broker rejects |
| 16 | Code replay / duplicate callback | Does not create another session |
| 17 | Wrong PKCE verifier when flow requires it | Token exchange rejects |
| 18 | Wrong/expired client secret | Token endpoint denies |
| 19 | Reused CAS ticket | CAS validation denies |
| 20 | CAS ticket for different service URL | CAS validation denies |
| 21 | Untrusted SAML Issuer/signing cert | Broker denies |
| 22 | Expired SAML Assertion | Broker denies |
| 23 | Wrong SAML `InResponseTo`/Audience | Broker denies |
| 24 | SAML XML Signature Wrapping | Broker ignores unsigned assertion |
| 25 | Transient NameID changes across logins | No duplicate account created |
| 26 | Pairwise `sub` changes from client/sector updates | Migration link review, no email auto-link |
| 27 | Disabled local account | Denies business access despite valid OIDC |
| 28 | Broker group claims admin against policy | Never becomes `ROLE_ADMIN` |
| 29 | Tenant A accesses Tenant B object | 403/deny |
| 30 | MFA/LoA fails required `acr` | Step-up/deny |
| 31 | Upstream CAS/SAML session expires | Broker reauthenticates per policy |
| 32 | Spring app logout | Local session ended |
| 33 | Broker OIDC logout | Broker session policy honored |
| 34 | Upstream CAS/SAML session still active | UX/re-login behaves per contract |
| 35 | Logout CSRF / open redirect attempt | Blocked |
| 36 | Broker unavailable | Fail closed, no auth bypass |
| 37 | Broker key rotation | Old/new keys work within trust window |
| 38 | Spoofed `X-Forwarded-Host` header | Does not alter `redirect_uri`/issuer |
| 39 | Error responses/logging | Zero leaked tokens/assertions/PII |
| 40 | Blue-green rollback | Legacy login restored; DB/`user_id` unchanged |
| 41 | Simultaneous legacy and OIDC sessions | Zero identity/session mix-up |
| 42 | CAS PGT/proxy downstream use cases | Replaced or intentionally maintained |
| 43 | App/API ID Token misuse | Resource server rejects ID Token not meant for API |
| 44 | Duplicate broker subject/account link | Unique constraint/approval policy denies |
| 45 | Unapproved new broker signing key | Controlled trust policy, no fail-open |

**Never count a test as PASS if it merely throws 500 or enters a redirect loop.** For instance, a wrong-issuer test must keep all other parameters valid (including a valid signature) when testing issuer logic. An untrusted-key test must prove a token validly signed with an out-of-trust-list key is still rejected by the app. Use fresh `state`, `nonce`, assertion/request IDs, and isolated sessions.

### Testing Identity Linking During Migration

1. Seed a local user with fixed orders/roles.
2. Perform legacy CAS/SAML login with a test account having a verified upstream identity.
3. Perform broker OIDC login from a fresh browser session as the same user.
4. Assert `local_user_id` stays immutable; records and tenant remain unchanged.
5. Test another upstream issuer/email collision; ensure no auto-merge.
6. Disable the local account and log in again; policy must deny even with a valid broker ID Token.
7. Change roles in the local DB and test authorization updates per revocation/session SLA.
8. On rollback, re-use the legacy path and assert the exact same local ID.

### Testing Protocol Isolation

~~~text
Legacy SAMLResponse POST -> only SAML ACS on legacy path
CAS ticket -> validated only by CAS client/broker adapter
OIDC code -> only /login/oauth2/code/{registrationId}
OIDC ID Token -> validated by RP, never taken from client-asserted request
API access token -> Resource Server with audience/scopes
~~~

Never configure a blanket `/login/**` `permitAll` in another security chain that lets callbacks pass straight into business endpoints. When deploying multiple chains, set clear matching/ordering and add negative tests for every alternate route.

## 14. Migration Observability and Incident Troubleshooting

**Safe event logging:**

- `BROKER_UPSTREAM_AUTH_FAILED` with source alias and reason enum.
- `OIDC_TOKEN_VALIDATION_FAILED` with broker alias and category (`ISSUER`, `AUDIENCE`, `SIGNATURE`, `EXPIRY`).
- `ACCOUNT_LINK_NOT_FOUND`, `ACCOUNT_LINK_CONFLICT`, `ACCOUNT_LINK_APPROVED`.
- `LOCAL_USER_DISABLED`, `TENANT_AUTHORIZATION_DENIED`.
- `SSO_LOGIN_SUCCESS`, `LOGIN_LOOP_DETECTED`, `BROKER_UNAVAILABLE`.
- `LOGOUT_LOCAL_SUCCESS`, `BROKER_LOGOUT_STARTED`, `UPSTREAM_LOGOUT_UNSUPPORTED`.

Never log CAS STs, `SAMLResponse`s, Authorization Codes, ID/access/refresh tokens, cookies, raw NameIDs/attributes, or secrets/client credentials. Use generated trace IDs and optional pseudonymous `userTag` **only after validation**.

**Troubleshooting table:**

| Symptom | Likely Cause | What to Check |
| --- | --- | --- |
| Upstream CAS login fails | Wrong service URL / ticket validator / TLS | Registered CAS service, one-time ticket, HTTPS |
| SAML broker login fails | Cert/issuer/audience/destination mismatch | IdP metadata/trust anchors, sanitized SAML logs |
| OIDC broker login loop | Redirect URI, issuer, proxy host, SameSite/session state | Public URLs, exact callback, cookies/CSRF |
| "Invalid state" | Lost browser session / callback mismatch | `OAuth2AuthorizationRequestRepository`, cookie domain |
| "Invalid nonce" | Mismatched state/nonce or swapped token | Request correlation, broker token response |
| Duplicate user created | Linking by email / transient NameID | Stable upstream key → broker key → local user |
| User lost roles | Groups changed or app roles unmapped | Local DB/policy mapping, claim contract |
| Repeated MFA prompts | Wrong `acr`/`amr`/reauth translation | Broker upstream LoA map, `auth_time`/`max_age` |
| Logs out then silently logs back in | Upstream IdP session still active | Layered logout policy, UX |
| API 401 after login | Using ID Token instead of access token | Resource server audience/scope validation |
| Broker outage breaks all logins | New dependency lacks HA | Multi-node/DR/health checks, fail closed |
| Issuer change makes users disappear | `iss`+`sub` changed | Approved mapping/rollback, never email auto-link |

## 15. Production Checklist Before Concluding Migration

- [ ] Complete inventory of CAS, SAML2, proxy tickets, SLO, keytabs/metadata, app sessions, and API dependencies.
- [ ] Upstream broker connector selected **with genuine support**: CAS via CAS adapter, or CAS providing OIDC/SAML; SAML via explicit SP trust.
- [ ] Broker upstream SAML verifies signature, Issuer, Audience, Destination, InResponseTo, time, replay, signed node, and XML parser safety.
- [ ] Broker upstream CAS validates one-time service tickets with registered service URL over HTTPS; never trusts raw browser usernames.
- [ ] Broker downstream OIDC issuer/JWKS/clients/redirect URIs/PKCE/state/nonce/keys/secret storage meet policy.
- [ ] Spring Boot trusts only the broker's OIDC ID Token via configured issuer, never raw JWTs/KeyInfo/JWKS URLs supplied by the browser.
- [ ] Business `user_id` remains immutable; approved `identity_link` keyed by broker `iss`+`sub` and tenant.
- [ ] CAS username, SAML NameID, email, and `preferred_username` are **never** used as global/auto-link keys.
- [ ] Pairwise/public `sub` behavior and broker/client/sector migrations evaluated.
- [ ] Mapped `groups`/`acr`/`amr` come strictly from verified/allowlisted claims; app roles remain DB/policy-driven.
- [ ] Disabled/locked local users and tenant/resource authorization deny accurately.
- [ ] API access tokens carry matching audience/scopes; ID Tokens are never sent as API Bearers.
- [ ] OIDC callback / exact redirect URI, proxy Host/Proto, session SameSite, CSRF, and logout tested.
- [ ] CAS/SAML/OIDC session/logout/SLO semantics have explicit contracts; no false promises of unsupported global logout.
- [ ] CAS PGT/proxy delegated calls replaced with authorized mechanisms or intentionally preserved.
- [ ] Positive baseline and isolated negative tests cover signature/issuer/audience/state/nonce/code replay.
- [ ] E2E mapping tests prove legacy and broker logins resolve to the same local user ID with zero duplicates.
- [ ] Canary/blue-green/dual-stack cohort controls and rollback preserve user mappings intact.
- [ ] Broker has HA, backup, recovery, audit, admin MFA, key rotation, alerts, and DR tests.
- [ ] Logs, APM, proxies, and SIEM contain zero `SAMLResponse`s, CAS STs, JWTs, cookies, NameIDs, or secrets.
- [ ] Legacy CAS/SAML libraries removed from classpath and old callback URLs closed after deprecation window.
- [ ] Security review/QA/operations owners sign off before disabling legacy flows.

**Conclusion:** An identity broker lets you **keep CAS or SAML upstream** while the Spring app gradually adopts **standard OIDC downstream**. Its greatest value is decoupling the application from legacy protocols; its greatest risk is **losing trust boundaries and mis-linking accounts**. Always verify each protocol at the right hop, keep `local_user_id` immutable, key on validated `(broker iss, sub)`, enforce local roles/tenants, design layered logout explicitly, and roll out with a clean rollback path. Never blindly trust emails, raw headers, tickets, SAML NameIDs, or ID Tokens unverified by the framework.

## 16. References

- [Spring Security – OAuth2 Client / OIDC Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html): Authorization Code, OAuth2 Login, and OIDC integration.
- [Spring Security – Core OAuth2 Login Configuration](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html): `ClientRegistration`, `issuer-uri`, `redirect-uri`, scopes.
- [Spring Security – Advanced OAuth2 Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html): `OidcUserService`, authorities, token endpoint configuration.
- [Spring Security – OIDC Logout](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html): `OidcClientInitiatedLogoutSuccessHandler` and post-logout redirect.
- [Keycloak Server Administration – Identity Brokering](https://www.keycloak.org/docs/latest/server_admin/): upstream IdPs, brokered identities, and first-login account linking.
- [Apereo CAS – Protocol Overview](https://apereo.github.io/cas/development/protocol/Protocol-Overview.html): service tickets, CAS, SAML2, and OIDC support per deployment.
- [Apereo CAS – CAS Protocol Specification](https://apereo.github.io/cas/development/protocol/CAS-Protocol-Specification.html): one-time ST validation and service binding.
- [OASIS SAML 2.0 Technical Overview / Core](https://docs.oasis-open.org/security/saml/v2.0/): SAML Assertions, Bindings, Profiles, Metadata.
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html): ID Token, `iss`/`sub`/`aud`/`nonce`, public/pairwise subjects, and authentication.
- [OpenID Connect Discovery 1.0](https://openid.net/specs/openid-connect-discovery-1_0.html): OP issuer and metadata.
- [RFC 7636 – Proof Key for Code Exchange](https://www.rfc-editor.org/rfc/rfc7636): PKCE S256.
- [OAuth 2.0 Security Best Current Practice (RFC 9700)](https://www.rfc-editor.org/rfc/rfc9700): redirect, token flow, and OAuth security recommendations.
- [OWASP OAuth2 Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/OAuth2_Cheat_Sheet.html): OAuth/OIDC client security.
- [OWASP Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): deny by default and resource authorization.