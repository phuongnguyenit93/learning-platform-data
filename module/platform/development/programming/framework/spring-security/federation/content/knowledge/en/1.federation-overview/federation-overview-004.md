# Distinguishing Centralized Authentication, Authorization, and Provisioning

In a *federation* system, multiple applications can trust the same Identity Provider (IdP). Nevertheless, **signing in successfully**, **being permitted to perform an operation**, and **having an active account in the application** are three distinct concerns. A secure design must address all three while clearly specifying which system is responsible for each decision.

## 1. Three Core Questions

| Concept | Question to Answer | Primary Responsibility | Typical Outcome |
| --- | --- | --- | --- |
| **Centralized authentication** | **Who is the user?** To whom did they prove their identity? | IdP verifies login credentials, MFA, and login policies; application verifies the IdP response. | Authenticated identity, login session info, or valid tokens. |
| **Authorization** | **What can that identity do, on which resource, in what context?** | The resource-protecting application/API decides per business policy; may reference roles/groups issued by the IdP. | Permit or deny a specific operation. |
| **Account provisioning** | **How are the account, profile, groups, and active status in the application created, updated, and revoked?** | Identity lifecycle management system, target application, or both per integration contract. | Account/group/permission records are synchronized, activated, or disabled. |

The three mechanisms may participate in a single access attempt, but **they do not replace one another**:

- Someone who signs in via SSO successfully can still receive **403 Forbidden** because they are not allowed to view financial reports.
- Someone whose application account was pre-created via SCIM must still authenticate when accessing the system.
- Someone disabled at the IdP may still have an unexpired application session or access token if the system has not handled corresponding revocation.

## 2. Centralized Authentication: Trusting Identity via Federation

**Goal:** users authenticate at an IdP (such as an organization's identity system), and multiple applications can then use that authentication result under a configured trust relationship. Applications typically do not need to store or verify employee passwords.

**Components:**

- **User / browser:** initiates access.
- **IdP / OpenID Provider:** performs sign-in, MFA, and risk policies; issues appropriate authentication information.
- **Relying application (Relying Party/OIDC Client or Service Provider/SAML):** verifies the result issued by the IdP, identifies the user, and creates its own session if needed.
- **Resource application/API (Resource Server):** verifies the appropriate access token for its API.

With **OpenID Connect (OIDC)**, web applications typically use the *Authorization Code* flow through the IdP. The IdP returns an authorization code; the application exchanges the code per protocol and verifies the **ID token** intended for that client. The ID token describes the authentication event/identity; it is **not** a universal pass to call every API. With **SAML 2.0**, the Service Provider verifies the assertion according to the configured trust relationship.

Before trusting an OIDC response, the client must use the library's verification mechanisms: signature and trusted keys, issuer (`iss`), audience/client ID (`aud`), expiration (`exp`), request state (`state`), `nonce` when applicable, and protocol constraints. Do not decode a JWT manually and treat unverified claims as real identity.

**SSO (Single Sign-On)** is the experience in which multiple applications can reuse a login session at the IdP. Federation is the trust relationship/identity exchange between parties; SSO is a common usage outcome, not synonymous with authorization or account synchronization. Logging out of one application also does not automatically log out all sessions at the IdP and other applications.

**Stable identifier:** link accounts based on the **(`iss`, `sub`)** pair in OIDC, accounting for tenant and the application's account-linking policy. Email, display name, or username can change or be reused, so they should not serve as the sole identity key to automatically merge users across different IdPs.

## 3. Authorization: Resource Permissions Must Be Checked Separately

**Authentication** tells you who is calling; **authorization** decides whether that call is allowed. For example, account `lan` signed in through the IdP but only has permission to read invoices belonging to company A. A request to edit company B's invoice must be rejected even while the token is still valid.

Common data sources used to make decisions:

- **Role (RBAC):** `REPORT_VIEWER`, `ORDER_ADMIN`; roles must have clear meaning and scope.
- **Attributes/context (ABAC):** department, data classification level, access hours, tenant, account status.
- **Relationships/resources:** order creator, project member, record ownership, ACL.
- **OAuth 2.0 scope:** the scope of access granted to an access token, e.g., `reports.read`. Scope does not automatically prove the user has access to **every** record or tenant.

**Who makes the decision?** The IdP may manage groups or issue claims, but the API/application owning the resource must still define and enforce the policy. If using groups from the IdP to grant internal roles, transparent mapping rules, tenant boundaries, claim-source controls, and update timing are required. Spring Security does not automatically interpret arbitrary claims like `groups` as business permissions.

**Distinguishing response codes:** APIs typically return **401 Unauthorized** when a request lacks valid authentication and **403 Forbidden** when the identity is authenticated but lacks permission. Web applications may redirect to the IdP instead of returning 401 directly.

Example of two-level checking for `GET /api/invoices/42`:

1. **Endpoint level:** there is a valid access token intended for this API, with scope `invoices.read`.
2. **Record level:** invoice 42 belongs to a tenant the caller is allowed to access, and the caller has an appropriate relationship/view permission.

Doing only step 1 leaks cross-tenant access or IDOR/BOLA vulnerabilities.

## 4. Account Provisioning: Lifecycle Management, Not Login

**Provisioning** covers creating accounts, profiles, groups, active status, and changes throughout a user's lifecycle. Depending on the application, it also includes creating workspaces, licenses, or tenant memberships. This is a data-administration flow that can run **before** the user ever signs in.

Three common approaches:

| Approach | Timing | Advantages | Limitations to Address |
| --- | --- | --- | --- |
| **Manual administration / user invitation** | Administrator proactively creates/assigns permissions. | Easy approval control for small organizations. | Easy to miss changes and revocations as user count grows. |
| **Just-in-Time (JIT) provisioning** | Creates or links an account when the first valid sign-in occurs. | Reduces pre-creation work; suits simple onboarding. | Does not fully solve group changes and offboarding without additional sync. |
| **Automated sync, typically via SCIM 2.0** | Identity system pushes create/update/disable events on lifecycle changes. | Can prepare accounts before sign-in, with more centralized updates and revocation. | Must design SCIM API authentication, mapping, idempotency, error sync, and latency handling. |

**SCIM 2.0** (RFC 7643/7644) standardizes `User` and `Group` schemas and HTTP endpoints such as `/Users` and `/Groups`, with `POST`, `GET`, `PUT`, `PATCH`, and `DELETE` operations. For instance, the source system can send an `active: false` update for the target application to disable an account; semantics of deactivation, deletion, or data retention must be agreed upon by both sides and follow actual provider support.

Do not conflate these three things:

- **Provisioned account:** a user record exists in the application.
- **Authenticated session:** the user has authenticated for a current session.
- **Authorized access:** that session or request passes the policy for the specific resource.

A created account does not sign itself in; a successful login does not grant admin permissions; a permission existing in the database does not allow skipping session and account-status checks.

## 5. Coordination Flow from Onboarding to Access

~~~text
HR / Directory System
        |
        | new hire / group change / departure
        v
Identity Management System + IdP -----------+
        |                                   |
        | SCIM (create/update/disable)      | OIDC/SAML (sign-in)
        v                                   v
Application Account Database <------> Web App / API
         (status, tenant, role)             |
                                            | permission check
                                            v
                                     Business Resources
~~~

The arrows represent **channels with different purposes**. SCIM updates identity/lifecycle data; OIDC/SAML transfers authentication evidence; the authorization layer checks operations on resources. SCIM is not mandatory for every system, but without SCIM an equivalent lifecycle mechanism is still required.

**Concrete scenario:** Lan newly joins the company and needs to view reports for project Alpha.

1. **Onboarding:** HR activates the employee; the identity system creates the user in the IdP. If integrated with SCIM, the application receives the account create/link event and assigns the tenant and initial least-privilege rights. If using JIT, the application creates the user on first sign-in **after** verifying identity and checking the policy allowing self-provisioning.
2. **Sign-in:** Lan opens the application; `oauth2Login` redirects to the IdP. The IdP authenticates (possibly requiring MFA); the application verifies the ID token and maps `iss + sub` to the internal account. As a result, Lan has a login session, which does not mean Lan can view every report.
3. **Access:** Lan calls the reporting API. The API checks that the access token has the right issuer/audience/expiration and checks both the `reports.read` policy **and** tenant/project membership. If Lan does not belong to Alpha, access is denied despite SSO.
4. **Department transfer:** the source system updates groups/roles via SCIM, sync, or an approval flow. Authorization policies in the application must reflect the change; claims in old tokens may retain old values until tokens are refreshed.
5. **Departure:** the IdP blocks new sign-ins; the provisioning flow disables the application account; the system must handle active sessions, refresh/access tokens, background permissions, and other integrations per revocation requirements. Disabling in only one place does not necessarily cut off all previously issued access immediately.

**Key invariant:** when processing a request, the system must verify **trusted identity + valid account status + permission for the actual resource**; the exact execution path depends on which session, bearer token, and policy model the application uses.

## 6. Placing Responsibilities Properly in Spring Security

Spring Security provides built-in OIDC/OAuth 2.0 authentication, token verification, and authorization enforcement. Internal user management, SCIM, approval workflows, and lifecycle synchronization are parts the application/identity system must implement by design; they do not appear automatically just by enabling `oauth2Login`.

### 6.1. Servlet Web Application Signing In with OIDC

Minimal configuration example for a Spring Boot application with `spring-boot-starter-security` and `spring-boot-starter-oauth2-client` dependencies. This is application configuration, **not a standalone Java program** run with `javac` outside a Spring Boot project.

File `src/main/java/example/federation/FederationSecurityConfig.java`:

~~~java
package example.federation;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
@EnableMethodSecurity
public class FederationSecurityConfig {
    @Bean
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
                .requestMatchers("/public/**", "/error").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
~~~

File `src/main/resources/application.yml` (endpoints and client are **configuration examples**; replace with actual IdP parameters):

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corporate:
            provider: corporate
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            authorization-grant-type: authorization_code
            scope: [openid, profile, email]
        provider:
          corporate:
            issuer-uri: https://idp.example.org/realms/corporate
~~~

With this configuration, an unauthenticated request to a protected path initiates sign-in via the IdP. After the user is authenticated, the web layer must still check per-operation permissions, for example via `authorizeHttpRequests`, `@PreAuthorize`, and a service checking record-level permissions. `@EnableMethodSecurity` enables method-level authorization; permissions from enterprise groups/roles must be **intentionally mapped** to Spring `GrantedAuthority`, rather than existing by default just because the ID token contains groups.

### 6.2. Separate API Receiving JWT Bearer Access Tokens

For a separate **Resource Server** application, use `spring-boot-starter-oauth2-resource-server` and example configuration:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://idp.example.org/realms/corporate
          audiences: https://reports-api.example.org
~~~

Spring Security Resource Server verifies the JWT signature and time/issuer claims as configured; the audience must match the API receiving the token. In this API application, when default scope mapping is used, scope `reports.read` becomes authority `SCOPE_reports.read`. An illustrative condition:

~~~java
@PreAuthorize("hasAuthority('SCOPE_reports.read')")
public ReportDto getReport(String reportId) {
    return reportService.loadIfAllowedForCurrentUser(reportId);
}
~~~

The method snippet above is **illustrative service code**, not independently compilable because it depends on `ReportDto`, `reportService`, and application policy. `loadIfAllowedForCurrentUser` must check permissions on **reportId, tenant, and caller**, avoiding the misconception that having a scope grants access to all reports. When using both session-based login and bearer tokens in the same application, configure appropriate filter chains, matchers, and policies for each request type; the two examples above represent two different application styles.

### 6.3. Where Do Provisioning and Business Authorization Live?

- **OIDC login:** configure `oauth2Login`; map external identity (`issuer + subject`) to the internal user; reject if the user is locked or does not satisfy provisioning policy.
- **JWT API:** configure `oauth2ResourceServer`; verify issuer, audience, signature, expiration; map trusted scopes/claims to authorities.
- **Business authorization:** implement at the API/service/repository layer, checking tenant, ownership, action permissions, and business state, applying *deny by default* and *least privilege*.
- **Provisioning:** integrate SCIM client/server, webhooks, directory sync, or JIT as needed; handle create/update/disable with idempotency, auditing, API permission limits, and reconciliation on sync drift.

If the system uses group claims to grant internal roles, it must clearly specify who the authoritative data source is, the group → role → resource mapping, sync latency, and revocation handling. Never accept roles solely from a request body, query parameter, or JWT from an untrusted issuer.

## 7. Misconceptions That Easily Cause Vulnerabilities

| Misconception | Why It Is Wrong / Correct Practice |
| --- | --- |
| "Having SSO means having admin privileges." | SSO only authenticates identity. Admin is a privilege that must be granted and checked separately. |
| "OAuth 2.0 is always a user authentication standard." | OAuth 2.0 is primarily an access authorization framework; use OIDC for user authentication with ID tokens and standard validation. |
| "ID tokens are used to call any API." | ID tokens are for the client; APIs require access tokens targeting the right resource/audience. |
| "Having the `read` scope allows viewing every record." | You must check permissions by owner, tenant, project, and specific object. |
| "Every login automatically creates an account and grants broad default roles." | JIT must check eligibility conditions, create least-privilege accounts, and write audit logs; approval may be required. |
| "Once SCIM creates an account, login is unnecessary." | SCIM handles lifecycle; access requests still require authentication/authorization. |
| "Deleting a user in the IdP immediately blocks all old sessions." | You must handle app state, sessions, refresh/access tokens, TTLs, and corresponding revocation mechanisms. |
| "Email can be used as a unique ID for federation." | Emails can change or collide across tenants/IdPs; prefer `iss + sub` and explicit mapping. |
| "Group claims automatically become Spring roles." | You must configure claim → authority conversion and define the trusted scope/source. |
| "403 and 401 are the same." | 401 usually means missing valid authentication; 403 means authenticated but unauthorized. |

## 8. Validating Design Through Scenarios

**Scenario A — User logs in properly but has no application account yet:** If JIT is allowed, create/link the account after IdP verification and policy checks with least privilege; if pre-provisioning/pre-approval is required, deny access until a valid account exists. **Do not infer permissions from login alone.**

**Scenario B — Employee transfers from group A to B:** The IdP/directory or SCIM updates attributes/groups; the application recalculates permissions and handles token/session staleness. Role A must not persist indefinitely once revoked at the administrative source.

**Scenario C — Valid JWT calling another tenant's report:** The Resource Server verifies the token successfully, but the business authorization layer must deny access due to tenant mismatch. Signature verification is only a necessary condition, not sufficient.

**Scenario D — Employee leaves with 20 minutes remaining on an access token:** The design must define the desired revocation level: checking account status on sensitive requests, short TTLs, session/refresh token revocation, introspection/revocation mechanisms, or update events when appropriate. Never promise "instant system-wide logout" without a real mechanism in place.

### End-of-Lesson Self-Check

1. **Who confirms "who Lan is"?** The IdP and the relying application verifying the protocol result.
2. **Who decides "can Lan edit invoice 42"?** The application/API owning the invoice, per policy and real context.
3. **Who creates or disables Lan's profile in the application?** The chosen provisioning flow (SCIM/JIT/admin/sync), independent of whether Lan is currently signed in.
4. **Why must the three mechanisms coordinate?** Because a valid identity does not imply resource permissions and does not guarantee lifecycle state has been synchronized.

## References

- [Spring Security: OAuth 2.0 Client, Login, Resource Server](https://docs.spring.io/spring-security/reference/servlet/oauth2/index.html)
- [Spring Security: JWT Resource Server and token verification](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html)
- [OpenID Connect Core 1.0](https://openid.net/specs/openid-connect-core-1_0.html)
- [RFC 7643 — SCIM Core Schema](https://www.rfc-editor.org/rfc/rfc7643)
- [RFC 7644 — SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644)
