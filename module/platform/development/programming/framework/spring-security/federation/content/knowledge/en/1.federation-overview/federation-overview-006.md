# Enterprise and Cross-Organization Identity Linking

Identity linking enables a system to recognize that identities coming from different authentication sources may belong to the same person or the same business account. In enterprise environments, this need arises when employees access multiple internal applications, when a company has multiple subsidiaries, or when partner employees need to access resources shared across organizations.

**Learning objectives:** distinguish single sign-on, account linking, and cross-organization identity federation; understand trust boundaries; design stable identifier mapping and per-organization access control; learn how to implement this with Spring Security, manage lifecycles, and avoid account takeover vulnerabilities.

## 1. Distinguishing Easily Confused Concepts

| Concept | Meaning | Automatically Proves Two Accounts Are One Person? |
| --- | --- | --- |
| SSO (Single Sign-On) | One login session at an Identity Provider allows access to multiple integrated applications. | No. |
| Identity federation | An application of organization A accepts authentication results from A's IdP or a trusted organization B's IdP. | No. |
| Account/identity linking | Establishes a verified relationship between an external identity and an internal account, or between multiple external identities. | Yes, if the verification process and policy allow it. |
| Provisioning | Creates/updates/locks accounts and memberships based on an authoritative HR/identity source. | No; this is lifecycle management. |
| Authorization | Decides which resources and which tenant an authenticated user can view/edit. | No; must be checked separately after authentication. |

Example: Lan uses a company account to enter the Portal, CRM, and support system. All three applications rely on the same IdP, so Lan gets SSO. If Lan also has an identity at a partner company, the fact that both sessions share the email `lan@example.com` is not sufficient grounds to merge the two identities. The system must verify both and check data-sharing policies.

**Two main scopes:**

- **Intra-enterprise:** one shared IdP for multiple applications; or multiple IdPs operated by subsidiaries, coordinated through a broker. The goal is a unified login experience and centralized management.
- **Cross-organization (B2B/cross-organization):** the host organization's application accepts sign-ins from a partner IdP, while guest accounts, data, and permissions remain governed by the host organization's policies. Trust is typically scoped per tenant, contract, and application.

## 2. Components and Trust Boundaries

- **User / principal:** the human or accessing subject; display name, email, and department are merely attributes, not global identifier keys.
- **Identity Provider (IdP):** authenticates users, maintains an identity directory, and issues ID tokens/assertions per protocol.
- **Relying Party (RP, in OpenID Connect) / Service Provider (SP, in SAML):** the application trusting authentication results per agreed configuration.
- **Identity broker:** an intermediary connecting multiple IdPs, normalizing login flows and issuing identities to applications; the broker introduces an additional trust boundary.
- **Tenant/organization:** an isolated data and policy space. One person may belong to multiple tenants with different roles.
- **Mapping store:** stores the relationship from external identity to internal user and proof of linking; requires uniqueness constraints, auditing, and unlinking mechanisms.

The IdP confirms **who signed in at that IdP**. The application must still decide which internal account that identity corresponds to, whether it belongs to the requested tenant, and what permissions are granted. Partner B's `admin` role does not automatically become an `admin` role in system A.

Trust example: company A allows supplier B to sign in to the order portal. A may trust signatures and identities issued by B's IdP, but B must not be able to add people to A's tenant or assign A's admin roles on its own. Onboarding and permission-granting policies belong to A.

## 3. Common Deployment Models

| Model | Trust Flow | Suitable When | What Needs Control |
| --- | --- | --- | --- |
| Shared internal IdP | Apps 1, 2, 3 → Enterprise IdP | Multiple apps within one company | MFA policy, login sessions, permission and account revocation |
| Direct Multi-IdP | App → each unit/partner's IdP | Few partners, each with a stable IdP | Separate issuer/client/tenant configs; connections grow with partners |
| Hub-and-spoke via broker | App → broker → source IdPs | Many units, partners, post-merger companies | Upstream config, claim normalization, distinguishing original issuer vs. broker |
| B2B guest accounts | User B → IdP B → App A → guest membership in A | Cross-org collaboration, partner portals | Invitations, access expiration, data ownership, offboarding |
| Two identities linked to one person | IdP X and IdP Y → same internal user after verification | Company transfers, identity consolidation, multiple login methods | Never auto-merge by email; auditing and ability to unlink |

No model replaces authorization checks in the application. Before letting a user choose an IdP, the system must determine the target tenant from server-side configuration, a valid invitation, or an authenticated context; never blindly trust a tenant header sent by the browser.

## 4. Which Protocol Serves Which Purpose?

**OpenID Connect (OIDC)** layers authentication onto OAuth 2.0. Web applications typically use the Authorization Code Flow; Public Clients need PKCE, and many confidential client setups should also enable PKCE. The RP receives an ID token to verify sign-in. Important fields include `iss` (issuer), `sub` (stable subject within the issuer's scope), `aud` (client receiving the token), expiration time, and `nonce` when required. UserInfo can supplement attributes but does not replace ID token validation.

**SAML 2.0** is common in long-standing enterprise SSO. The IdP sends an assertion to the SP. The SP must validate signature, issuer/entityID, `AudienceRestriction`, recipient/destination, time conditions, and correlation with the authentication request when using SP-initiated login. Mapping keys should rely on a durable identifier agreed by both parties, such as `IdP entityID + persistent NameID`; email-based or transient `NameID` values may be unsuitable for long-term linking.

**OAuth 2.0** handles authorization, not user identity assurance by itself. Access tokens issued for APIs must be verified by the API for issuer/audience/scope and application policy; never substitute an access token for an ID token to log users in. OAuth scopes are not equivalent to internal tenant roles.

**SCIM 2.0** supports synchronizing users/groups and active status across the lifecycle. SCIM is not a login protocol. It complements OIDC/SAML to create, update, and revoke access promptly.

**LDAP/Kerberos/AD** typically belong to internal directory and authentication layers. They may sit behind an IdP; modern applications usually integrate via OIDC/SAML rather than directly connecting to every directory.

## 5. Federated Login Flow with OIDC

Example of a person from partner B using A's ordering application:

1. The user selects organization B from the login portal or an invitation recognized by A. The application selects the `partner-b` client configuration on the server.
2. The application redirects the browser to IdP B's Authorization Endpoint with `state`, redirect URI, and `nonce`/PKCE as configured.
3. IdP B authenticates the user (possibly using MFA per policy), then returns an authorization code via the registered redirect URI.
4. The application exchanges the code for tokens over a secure channel; Spring Security/the OIDC client validates protocol info and the ID token per configuration.
5. The application extracts the verified identity: target tenant determined by the server, `iss` from the valid token, and `sub` from the IdP.
6. The mapping store looks up the local user by this key tuple. If not yet linked, JIT-provision only when policy and onboarding evidence allow it; otherwise direct the user to an invitation/verification flow.
7. The application loads membership, roles, and access limits **from data controlled by organization A**, creating an application session or internal principal. APIs continue enforcing per-resource authorization.

~~~mermaid
sequenceDiagram
    participant U as User B
    participant RP as Application A (RP)
    participant IDP as B's IdP
    participant DB as A's Mapping & Permissions Store
    U->>RP: Select B / follow invitation
    RP->>IDP: OIDC request (state, nonce/PKCE)
    IDP-->>RP: Authorization code
    RP->>IDP: Exchange code for tokens
    IDP-->>RP: ID token
    RP->>RP: Verify token and target tenant
    RP->>DB: Look up (tenant, issuer, subject)
    DB-->>RP: Internal user + membership
    RP-->>U: Session authorized per A
~~~

If the system goes through a broker, `iss` in the token received by the application may be the **broker's issuer**, not the original issuer. To distinguish the upstream IdP, you must use a claim normalized, signed, and semantically guaranteed by the broker; never trust an arbitrary `upstream_issuer` string sent by the browser.

## 6. Designing Identifier Keys and the Data Model

**Do not use email, phone number, display name, domain, or `preferred_username` as an immutable linking key.** They can change, be reused, collide across tenants, or go unverified. Even an `email_verified` claim only proves email verification status per the IdP's rules, not ownership of another internal account.

A reference data model:

| Table / Object | Essential Fields | Required Invariants |
| --- | --- | --- |
| `local_users` | `user_id`, status, display name | Internal `user_id` independent of any IdP |
| `external_identities` | `tenant_id`, `issuer`, `subject`, `user_id`, status, linked timestamp, verification method | Unique key `(tenant_id, issuer, subject)`; one external identity never binds to two local users simultaneously |
| `organization_memberships` | `user_id`, `organization_id`, roles, status, expiration date | Every access must verify membership in the target tenant |
| `trusted_identity_providers` | `organization_id`, `registration_id`, issuer/entityID, trust status, admission policy | Reject issuers outside the organization's allowlist |
| `audit_events` | action, target, actor, verification source, timestamp | Traceable link/unlink, role change, SCIM deactivate, login failure |

The key from OIDC is typically the tuple `(tenant_id, iss, sub)`, where `iss` comes from an ID token verified against a valid registration. Even if all tenants share one IdP and `sub`, including `tenant_id` remains important to scope mappings and permissions per tenant. If the system needs to recognize the same individual across multiple tenants, a global `person_id` can exist, while memberships and permissions remain separate.

In an actual database, enforce a unique constraint on the external key; use transactions when linking; prevent two concurrent requests from attaching the same identity to two people. When an IdP changes its issuer/subject format, run a verified, audited migration procedure rather than bulk-merging by email.

## 7. Secure Workflow for Linking Two Accounts

Suppose someone has an internal account A and an external identity B. Linking should only occur through an explicit action:

1. The user signs in to active account A; for sensitive actions, require recent re-authentication near the time of linking.
2. The user clicks "Link organization B"; the server initiates an OIDC/SAML flow to an approved IdP B.
3. The server validates the returned response and matches `state`/`nonce`, issuer, subject, client, tenant, and the initiating session.
4. The server checks that the user is allowed to link identity B to account A and that identity B is not already linked to another account. When needed, require an admin invitation or secondary confirmation.
5. Persist the mapping in a concurrency-safe transaction, recording timestamp, proof method, and actor; emit an audit event.
6. Display currently linked identities and how to unlink them; retain at least one valid login/recovery method to avoid self-lockout.

Never implement "sign in with B, see an email matching A's email, automatically merge A and B". An attacker could register or compromise an identity holding a recycled email at another source, leading to **account takeover**. Likewise, never auto-link merely because IdP B shares the same username as A.

**Unlinking:** re-verify the user, inspect related sessions and tokens, remove the mapping safely, and log an audit event. If a user is disabled at one IdP, handle account/membership policies separately; an existing mapping does not imply permissions remain active.

## 8. Cross-Organization Provisioning and Lifecycle

Three options to evaluate:

- **Pre-provisioning (before login):** A's administrator approves an invitation or SCIM syncs the user; suits tightly controlled B2B scenarios. The account can exist before the first sign-in.
- **Just-in-Time provisioning (JIT):** creates the account upon the first successful sign-in when the issuer and admission conditions are approved by A. A valid OIDC login alone is not enough to auto-grant roles or tenants.
- **Hybrid:** SCIM/invitations grant membership and permission limits; OIDC/SAML handles login and first-time identity linking.

Design the full lifecycle: add employee/partner → verify and grant membership → department/role change → suspend/offboard → revoke sessions and permissions → retain audit logs per policy. Agree on which source is authoritative for `active`, title, groups, and permissions; handle SCIM delays, failed webhooks, accidental deletions, and cross-unit transfers. Disabling at the source IdP usually blocks new sign-ins, whereas already-issued application sessions or old access tokens may persist until expiration/revocation per design.

For B2B, designate an internal partner sponsor in A, set invitation expiration dates, perform periodic access reviews, and define SLAs to lock access when contracts end. A partner's IdP has authority to authenticate **that partner's own users**, not to grant global permissions inside A's application.

## 9. Implementing with Spring Security: Integration Points

With Spring Boot 3.x, Java 17+, and an OIDC-enabled web app, declare `spring-boot-starter-security` and `spring-boot-starter-oauth2-client`. Each trusted IdP has its own client registration; Spring Security executes the protocol flow, while the application handles internal mapping and authorization.

**Illustrative** configuration example for two hypothetical IdPs (never use placeholder secret values in real environments):

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: portal-corp
            client-secret: REPLACE_FROM_SECRET_MANAGER
            scope: [openid, profile, email]
            authorization-grant-type: authorization_code
          partner-b:
            provider: partner-b
            client-id: portal-partner
            client-secret: REPLACE_FROM_SECRET_MANAGER
            scope: [openid, profile]
            authorization-grant-type: authorization_code
        provider:
          corp:
            issuer-uri: https://idp.corp.example
          partner-b:
            issuer-uri: https://login.partner.example
~~~

The two login entry endpoints are typically `/oauth2/authorization/corp` and `/oauth2/authorization/partner-b`, while default callbacks follow `/login/oauth2/code/{registrationId}`. Redirect URIs must be registered accurately at each IdP; enforce HTTPS and inject secrets via environment variables/a secret manager in real deployments. The `.example` domains are illustrative only.

A web application security configuration:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class FederationSecurityConfig {
    @Bean
    SecurityFilterChain securityFilterChain(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

This is `FederationSecurityConfig.java` in a Spring Boot project with the starters above. The configuration enables OIDC login for the declared registrations; **it does not automatically link internal accounts**. In a real application, integrate `OAuth2UserService<OidcUserRequest, OidcUser>` (or controlled post-login handling) to map verified login claims to `local_user_id` and memberships. Preserve library validation, enforce server-side `issuer↔registration↔tenant` mapping, and never use email to auto-merge accounts.

Example converting an OIDC user **already authenticated by Spring Security** into a domain-layer linking key:

~~~java
import org.springframework.security.oauth2.core.oidc.user.OidcUser;

public record FederatedKey(String tenantId, String issuer, String subject) {
    public static FederatedKey from(String targetTenantId, OidcUser user) {
        return new FederatedKey(
            targetTenantId,
            user.getIdToken().getClaimAsString("iss"),
            user.getSubject()
        );
    }
}
~~~

Save as `FederatedKey.java`. The `targetTenantId` parameter must come from server configuration or a server-verified tenant context; never take it directly from an untrusted query parameter or header. `iss` and `sub` are trustworthy **only after Spring Security has verified the OIDC flow and token**. Mapping this key to internal accounts and memberships requires dedicated repository, transaction, and audit logic.

If using **SAML**, Spring Security provides `spring-security-saml2-service-provider` and `saml2Login` with a `RelyingPartyRegistration` per IdP; metadata, certificates, entityID, and Assertion Consumer Service must be managed. If a separate API receives bearer tokens, use **OAuth2 Resource Server** (`spring-boot-starter-oauth2-resource-server`) with appropriate issuer/audience validators; web login and API token verification are separate responsibilities. With multiple issuers for an API, use a strategy to select trusted validators and apply per-tenant policies rather than merely decoding JWTs.

## 10. Standalone Java 17 Example: One Person, Two Identities from Different Issuers

The following snippet illustrates the **mapping rule**; it does not perform OIDC, connect to a database, or replace real identity verification. The `verified` flag only simulates a verified security-layer outcome.

Create file `IdentityLinkingDemo.java`:

~~~java
import java.util.HashMap;
import java.util.Map;

public class IdentityLinkingDemo {
    record ExternalIdentity(String tenantId, String issuer, String subject) {}
    record LocalUser(String id) {}

    private static final Map<ExternalIdentity, LocalUser> LINKS = new HashMap<>();

    static void linkAfterVerification(
            ExternalIdentity external, LocalUser user, boolean verified) {
        if (!verified) {
            throw new SecurityException("Identity verification required");
        }
        LocalUser previous = LINKS.putIfAbsent(external, user);
        if (previous != null && !previous.equals(user)) {
            throw new IllegalStateException("External identity already linked");
        }
    }

    static String resolve(ExternalIdentity external) {
        LocalUser user = LINKS.get(external);
        return user == null ? "UNLINKED" : user.id();
    }

    public static void main(String[] args) {
        LocalUser alice = new LocalUser("U-100");
        ExternalIdentity corp = new ExternalIdentity(
            "corp", "https://idp.corp.example", "42");
        ExternalIdentity partner = new ExternalIdentity(
            "partner-b", "https://login.partner.example", "42");

        linkAfterVerification(corp, alice, true);
        System.out.println(resolve(corp));
        System.out.println(resolve(partner));

        linkAfterVerification(partner, alice, true);
        System.out.println(resolve(partner));
        System.out.println(LINKS.size());
    }
}
~~~

Run with JDK 17 or higher:

~~~bash
javac IdentityLinkingDemo.java
java IdentityLinkingDemo
~~~

Exact output:

~~~text
U-100
UNLINKED
U-100
2
~~~

Even though both IdPs use `subject = "42"`, including tenant and issuer in the key prevents them from colliding. Only after the second verification/link step do both resolve to `U-100`. In production, remove the caller-supplied boolean parameter and derive verification from a valid session and IdP flow; replace `HashMap` with a transactional repository enforcing unique constraints; never keep sensitive mappings solely in single-instance memory.

## 11. Common Vulnerabilities and Mitigations

| Mistake | Consequence | Mitigation |
| --- | --- | --- |
| Merging users by email/username | Account takeover, wrong user after email change/reuse | Use stable issuer + subject + tenant key; link only with proof |
| Trusting client-supplied `tenant_id` or `role` | Cross-tenant access, privilege escalation | Use server-side trusted mappings and permissions |
| Accepting tokens without verifying issuer/audience/signature/expiration | Tokens from other apps/IdPs accepted | Standard validators, issuer and audience allowlists, JWKS management |
| Skipping `state`/`nonce`, unbound callbacks | Login CSRF, replay, session mix-ups | Use OIDC library properly, verify state/nonce and PKCE |
| Mixing source roles with app roles | Partners bring elevated roles into the app | Per-tenant role mapping, least privilege by default |
| JIT provisioning any valid identity | Any user at a trusted IdP enters the app | Whitelists, invitations, enrollment and approval policies |
| Not syncing offboarding | Guest accounts/sessions persist after partnership ends | SCIM/deprovisioning, session revocation, expiry, and auditing |
| Ignoring concurrent duplicate link races | One external identity binds to multiple local users | Unique constraints, transactions, idempotent link operations |
| Over-trusting a broker or compromised IdP | Forged identities accepted by the system | Limit trust scope, MFA, monitoring, audits, link-severing plan |

For SAML, also verify assertion/response signatures as required, issuer/entityID, recipient, audience, `InResponseTo`, timestamps, and replay protection; never just parse XML and trust attributes. For OIDC, use a vetted library for tokens and callbacks; never roll your own JWT verifier or bypass certificate checks when connecting to an IdP.

## 12. Real-World Application Scenarios

**Internal scenario:** a conglomerate has staff across two units A1/A2, one Portal, and multiple services. It can use a corporate IdP or a broker connecting unit IdPs. The app maps `(tenant, issuer, sub)` to `local_user_id` and grants Portal permissions by unit. When staff transfer from A1 to A2, manage membership in a controlled way; never assume SSO to app A2 implies permission to view A2's data.

**Cross-organization scenario:** A provides a B2B portal for suppliers B and C. Each partner signs in at its own IdP. A configures issuer/registration per partner, requires invitations and guest expiration dates, records mappings, and grants `ORDER_VIEWER` or `ORDER_EDITOR` **per contract/tenant**. A user from B with `admin` at B cannot automatically view C's orders. When B's contract ends, A disables memberships and related sessions, even if the identity at B's IdP still exists.

**Merger scenario:** after an acquisition, the same employee has accounts at both old and new IdPs. Durable key tuples keep the two identities separate; administrators run a verified, audited migration and link them to one internal user if policy permits. Never bulk-merge automatically by email.

## 13. Design, Operations, and Testing Checklist

1. **Trust:** document each `organization↔issuer` pair, endpoints, client registrations, certificates/JWKS, algorithms, contracts, and owners; maintain key-rotation and trust-revocation procedures.
2. **Identity:** unique `(tenant, issuer, subject)` key; retain linking history; link/unlink flows based on two authentication proofs and approved policies.
3. **Tenant authorization:** a user may belong to multiple organizations, but each access is scoped strictly to valid membership, role, resource, and target tenant.
4. **Lifecycle:** identify authoritative HR source, invitations/SCIM/JIT, activation, suspension, transfers, permission removal, guest expiration, and session revocation.
5. **Security:** MFA/step-up when linking or accessing sensitive data; HTTPS, secret manager, redirect URI allowlist, state/nonce/PKCE, audit logs free of leaked tokens/secrets.
6. **Operations:** monitor login/claim mismatches, issuer/JWKS changes, SCIM sync failures, duplicate links, anomalous sign-ins; keep support fallback if a partner IdP goes down.
7. **Mandatory tests:** same `sub` with different `iss` must not auto-merge; same email with different issuer must not auto-link; user B cannot view C's data; unknown IdP or wrong audience token is rejected; departed account loses access; two concurrent link requests cannot create invalid mappings; revoked permissions do not remain usable via old sessions beyond defined limits.
8. **Experience tests:** users know which organization they are acting under, see linked identity details, understand denial reasons, and have a safe recovery path if one IdP is lost.

**Core principle:** federation lets you trust **origin-verified authentication results**, identity linking establishes **verified relationships between identities**, and authorization decides **permissions within a specific tenant and resource**. Keeping these three layers separate is the prerequisite for scaling internal SSO to multi-organization collaboration while maintaining control over accounts and data.