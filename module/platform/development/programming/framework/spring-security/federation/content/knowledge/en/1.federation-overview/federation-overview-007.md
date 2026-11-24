# Responsibilities of Spring Security, Identity Server, and Business System in Federation

## 1. Understanding the Problem Correctly

**Federation (identity federation)** allows an application to trust the authentication result provided by another identity system, following a pre-configured trust relationship and protocol. For example, an employee signs in at the enterprise identity system (**Identity Provider**, abbreviated **IdP**) and then accesses multiple internal applications without creating separate passwords for each application. This experience is commonly called **Single Sign-On (SSO)**.

Three distinct questions must be answered in three appropriate places:

1. **Who is signing in, and how were they verified?** Focus of the IdP and the authentication process.
2. **Does the application accept the authentication result/token and allow reaching which features?** Focus of Spring Security configured inside each application/API.
3. **Is that person allowed to view invoice A, edit order B, approve transaction C, or access tenant X's data?** Focus of the **business system**, based on its data and policies.

Distinguish two terms:

- **Authentication (AuthN):** establishing the identity of the user or calling application.
- **Authorization (AuthZ):** deciding which actions an authenticated identity is allowed to perform on which resources. A successful login does not mean access to all data.

Spring Security is a **security framework running inside a Spring application**, not by default a centralized IdP. Nor does the IdP automatically know all business rules of every system.

## 2. Components in a Federated Architecture

| Component | Role | Example Responsibilities |
| --- | --- | --- |
| User / browser | Initiates login and uses the application | Redirects to the IdP, returns authorization code or SAML response per flow |
| **Identity Provider (IdP)** | Verifies identity, manages central login session | Passwords, passkeys, MFA, login policy, identity attributes, login events |
| **Authorization Server** | Issues and manages OAuth 2.0 tokens | Client registration, authorization codes, access tokens, refresh tokens, scopes, signing keys, metadata/introspection endpoints |
| **Spring Security in web app** | Acts as OAuth 2.0/OIDC client or SAML relying party | Initiates login flow, validates response, builds `Authentication`, protects sessions and routes |
| **Spring Security in API** | Acts as OAuth 2.0 Resource Server | Verifies JWT access tokens or introspects opaque tokens, builds principal/authorities, protects endpoints |
| **Application and business services** | Owns business permissions and data | Links external identity to internal account, tenant, business roles, record-level permissions, business auditing |
| API Gateway (if present) | Edge control layer | TLS, rate limiting, routing, optional edge token check; does not replace checks at the API |

In real products, the **IdP and Authorization Server may live on the same platform** (such as an OIDC system). Still, these remain two *logical roles*: the IdP handles identity verification; the Authorization Server issues tokens for clients to access resources. One system can play multiple roles simultaneously, yet responsibility boundaries must stay clear.

A **Relying Party (RP)** is an application trusting OIDC authentication results; **Service Provider (SP)** is the common term on the SAML application side. A **Resource Server** is an API receiving access tokens. A single Spring Boot application can serve both web pages and APIs, though the two request types have different security requirements.

## 3. Concrete Responsibility Allocation Table

| Task / Question | IdP / Authorization Server | Spring Security in the Application | Business System |
| --- | --- | --- | --- |
| Store and verify passwords, passkeys | **Leads** | Redirects/receives results; never needs the IdP password | Never stores IdP passwords |
| MFA, identity account lock, login risk | **Leads**, per central policy | Can request/check strong authentication signals when needed | Defines which actions require stronger verification |
| Issue authorization code, ID/access/refresh tokens | **Leads**, depending on protocol | Receives, exchanges, verifies, and uses per client/API role | Never signs tokens on behalf of IdP unless designed as AS |
| Verify signature, issuer, expiration, audience | Provides metadata, keys, and token contents | **Enforces validation of received token/assertion**, per config | Processes only trusted identities/claims |
| Map scopes/groups to app authorities | May issue scopes/groups/claims | Maps and enforces endpoint/method rules | Defines business meaning and boundaries of permissions |
| Who can view invoice 123? | Usually unaware of that record | May invoke security check points | **Decides using ownership data, tenant, relationships, and policy** |
| Internal account, membership status, department in app | Provides identity attributes if available | Passes authenticated identity | **Maps, syncs, and manages lifecycle inside the app** |
| Per-application login session | Manages SSO session at IdP | Manages/checks session in web app if session-based | Defines when to require re-authentication/revoke access |
| Logs and investigation | Auth/token issuance logs | Auth trace and security-layer decisions | Data access and business transaction logs |
| Rejecting a request | Can reject login/token issuance | Returns 401/403 or redirects per config and context | Rejects when business conditions are not met |

**Key point:** The IdP answers "whom did we verify and which claims may the token carry"; Spring Security answers "does this request carry a valid security identity/credential and pass endpoint/method rules"; business logic answers "can they act on this specific object". A single final answer may require **all three layers**.

## 4. Responsibilities of the Identity Server

An IdP typically:

- Manages identities or integrates with the organization's directory; verifies accounts via password, passkey, second factor, device posture, or upstream IdP login.
- Maintains central SSO sessions and authentication policies (MFA, attempt limits, account recovery).
- When implementing OIDC/OAuth 2.0, publishes **issuer**, discovery metadata, and JWKS/public keys; issues tokens per client, scope, and policy; rotates keys and may support revocation/introspection.
- Emits agreed claims such as a stable subject, email, display name, groups, organization, or authentication level; emits only necessary and authorized attributes.
- Manages identity lifecycle: creating, locking, deleting accounts, or syncing with HR sources. Effects on **already-issued** sessions/tokens depend on revocation mechanisms and token lifetimes.

Limits of the IdP: it may know a user belongs to the `finance` group, yet usually **does not know** which invoice belongs to which branch, who holds approval authority for a payment batch, or whether an order is locked. If an organization puts business policies into a centralized authorization system, that is an **explicitly designed** integration, not a default IdP capability.

## 5. Responsibilities of Spring Security in Each Application

Spring Security provides mechanisms for the application to implement and enforce security:

1. **Intercept requests:** `SecurityFilterChain` processes requests before controllers; selects filter chains based on URL and application type.
2. **Protocol integration:** `oauth2Login()` for OAuth 2.0/OIDC login; `saml2Login()` for SAML 2.0; `oauth2ResourceServer()` for APIs accepting bearer access tokens; OAuth 2.0 Client for the application acquiring tokens to call other services.
3. **Validate incoming data:** handles OIDC/SAML callbacks, validates tokens/assertions per protocol; APIs can verify JWTs using public keys or call an introspection endpoint for opaque tokens.
4. **Represent the principal:** turns valid identity/claims into `Authentication`, `GrantedAuthority`, and the security context (`SecurityContext`).
5. **Enforce technical rules:** e.g., `authenticated()`, `hasAuthority("SCOPE_reports.read")`, `@PreAuthorize`, CSRF control for cookie/session flows, session management, and denial handling.
6. **Support extension:** mapping claims/groups to internal authorities, additional validators, login success/failure handlers, and integration with authorization services.

Spring Security **does not automatically create business accounts**, cannot guess which `tenantId` is authorized, does not turn a scope into ownership of all records, and does not provide multi-app SSO without an IdP and trust configuration.

If an enterprise wants to **build its own Authorization Server/IdP**, it can use **Spring Authorization Server** as a dedicated foundation. That is a separate architectural choice, not an automatic side effect of adding `spring-boot-starter-security` to an app.

## 6. Responsibilities of the Business System

Right after Spring Security authenticates a request, the business system must still:

- **Link external identity to internal user:** use the OIDC/JWT `(iss, sub)` pair as an issuer-scoped trusted identity key; for SAML, use the agreed identifier. Do not default to email as an immutable key because emails can change or be reassigned.
- **Determine tenant/organization context:** which tenants the user belongs to, which memberships are active, which organization is currently selected, and whether a feature supports cross-tenant access.
- **Manage actual roles and permissions:** `FINANCE_REVIEWER`, `INVOICE_APPROVE`, monetary limits, management regions, delegate approvers, and permissions based on transaction state.
- **Check the specific resource:** prevent IDOR/BOLA vulnerabilities. Verify that the object loaded from the database belongs to an authorized tenant and relationship; do not check only that the user has a valid token.
- **Handle internal lifecycle:** create accounts on first login if allowed (JIT provisioning), disable rights upon departure, handle membership changes, and enforce revocation.
- **Define business logic and audit evidence:** who was allowed to do what, why, on which record, and when. Never write full access tokens or refresh tokens to logs.

**Example:** The IdP confirms Alice is an employee and has claim `groups=["finance"]`. Spring Security validates the token and maps it to appropriate access for `/api/invoices/**`. The invoice service further determines Alice belongs to tenant A and can only read invoice A-001; when attempting to access invoice B-002 belonging to tenant B, the service **must deny access**. Valid login and scope still do not grant cross-tenant access.

## 7. Federation via OIDC, OAuth 2.0, and SAML 2.0

| Mechanism | Primary Goal | Primary Message | Spring Security Role |
| --- | --- | --- | --- |
| **OpenID Connect (OIDC)** | User authentication on top of OAuth 2.0 | ID token, optionally UserInfo and access token | Web app acts as OIDC Relying Party via OAuth 2.0 Login |
| **OAuth 2.0** | Authorizing a client to access protected resources | Access token with granted permissions/scopes | OAuth 2.0 Client or Resource Server; OAuth 2.0 itself is not a "user login" specification |
| **SAML 2.0 Web SSO** | Federated login via SAML assertions | AuthnRequest / SAMLResponse (usually via browser) | App acts as SAML Service Provider/Relying Party via `saml2Login()` |

Use OIDC when the application needs user identity and modern login via an OIDC-capable IdP. Use OAuth 2.0 Resource Server when an API needs to verify access tokens. Use SAML 2.0 when integrating SSO with partners/infrastructure requiring SAML. Never send a SAML assertion or an OIDC **ID token** as an access token to an API.

Multi-tier federation can occur: the application trusts IdP A, and IdP A federates with partner IdP B. The application must rely on the **issuer/claims and trust policy agreed** with A; never blindly trust an arbitrary token issued by B without configuring valid issuers.

## 8. OIDC Login Flow Among Three Parties

Suppose web app `portal.example.test` uses IdP `login.example.test` and a business API.

1. The user opens a page requiring login. Spring Security sees the app has no authenticated session, so it initiates the login flow to the IdP.
2. The browser is redirected to the authorization endpoint with client details, redirect URI, scope including `openid`, `state`, and flow attack-prevention parameters. With Authorization Code, **PKCE** is used per client config/capability; OIDC has a `nonce` mechanism to bind the ID token to the request.
3. The **IdP** verifies the user via appropriate methods (possibly requiring MFA) and evaluates client policy. The application never receives the IdP password.
4. The IdP redirects the browser to the registered redirect URI with an **authorization code**. Spring Security's OAuth 2.0/OIDC client handles the callback, validates transaction state, and exchanges the code for tokens via the token endpoint.
5. Spring Security and related OIDC components validate the ID token per protocol (issuer, audience/client, expiration, nonce when applicable, signature...) and create the principal/`Authentication`. The web app typically creates its **own session** for this sign-in.
6. The **business system** maps `iss + sub` to an internal account, verifies active membership, and enables only appropriate features. If mapping or business conditions fail, the app can reject access even though the IdP sign-in just succeeded.
7. When the frontend calls an **API** with a bearer access token, the API acts as a Resource Server: validating the token for that API, checking scopes/authorities, and then letting business services check tenant and record-level permissions.

An SSO session at the IdP, a web app session, and an API access token are **three distinct states**. Logging out in one place does not automatically guarantee ending everything everywhere; local logout, OIDC/SAML logout, token lifetimes, and permission revocation must be designed properly.

## 9. Access Tokens, ID Tokens, Refresh Tokens, and Claims

| Type | Purpose | Proper Recipient |
| --- | --- | --- |
| **ID token (OIDC)** | Proves the authentication event and identity info to the OIDC client | OIDC Relying Party with matching `client_id` |
| **Access token** | Authorizes calling resources/APIs within granted scopes | Resource Server with matching audience/contract |
| **Refresh token** | Requests new access tokens from the Authorization Server per policy | Permitted OAuth client; store and protect strictly, never send to business APIs |

Common claims:

- `iss`: issuer; must be on the trusted list and match configuration.
- `sub`: subject identifier provided by the issuer; usually used together with `iss`.
- `aud`: token audience. **An access token issued for API A must not automatically be accepted at API B.**
- `exp`, `nbf`, `iat`: timestamps; check expiration, not-before, and reasonable clock skew.
- `scope` or `scp`: permission scopes granted to the client/token; do not replace per-object data permissions.
- `groups`, `roles`, `tenant`: provider-specific extension claims; **their meaning, trusted source, and mapping rules must be explicitly specified**.

A JWT's **payload can be decoded** without a key; decoding **is not signature verification**. An API configured as a JWT Resource Server must validate signature, timestamps, issuer, and **the API's own audience** per configuration. With `issuer-uri`, Spring Security supports issuer and timestamp verification; the application must configure an appropriate audience/validator rather than assuming audience is always protected by default.

For opaque tokens (or tokens needing live status checks), a Resource Server can call an **introspection endpoint**. Locally verified JWTs reduce runtime dependency, but unexpired tokens are not automatically rejected immediately when an account is locked at the IdP; a strategy for TTL, revocation, introspection, and business permission updates is required.

## 10. Spring Boot Configuration Example: Web OIDC Login, API Accepting JWT

The example below illustrates **two responsibilities in one Spring Boot application using Spring Security Servlet**. Java 17+; requires dependencies: `spring-boot-starter-web`, `spring-boot-starter-security`, `spring-boot-starter-oauth2-client`, and `spring-boot-starter-oauth2-resource-server`. The project must register the client/redirect URI with an IdP and replace all `example.test` addresses with real endpoints; this is an integration configuration, not a system that can sign in without connecting to an IdP.

File `src/main/resources/application.yml`:

```yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp:
            provider: corp
            client-id: ${OIDC_CLIENT_ID}
            client-secret: ${OIDC_CLIENT_SECRET}
            scope: [openid, profile, email]
        provider:
          corp:
            issuer-uri: https://login.example.test/realms/work
      resourceserver:
        jwt:
          issuer-uri: https://login.example.test/realms/work
          audiences: https://api.example.test
```

The IdP must have a matching registered redirect URI, normally `{baseUrl}/login/oauth2/code/corp`. In real environments, use a secret manager/environment variables for the client secret, HTTPS, and the exact issuer URL. `audiences` specifies the API intended to receive the token; if your Boot version does not support this property, define an `OAuth2TokenValidator<Jwt>` checking `aud` equivalently.

File `SecurityConfig.java` placed in the application package:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class SecurityConfig {

    @Bean
    @Order(1)
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .securityMatcher("/api/**")
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/api/health").permitAll()
                .requestMatchers("/api/reports/**")
                    .hasAuthority("SCOPE_reports.read")
                .anyRequest().authenticated())
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .csrf(csrf -> csrf.disable())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()));
        return http.build();
    }

    @Bean
    @Order(2)
    SecurityFilterChain webSecurity(HttpSecurity http) throws Exception {
        http
            .authorizeHttpRequests(auth -> auth
                .requestMatchers("/", "/public/**").permitAll()
                .anyRequest().authenticated())
            .oauth2Login(Customizer.withDefaults());
        return http.build();
    }
}
```

How to read the code:

- The first chain handles only `/api/**` without sessions; API access tokens are verified as JWTs. Scope `reports.read` is mapped by default to authority `SCOPE_reports.read` in OAuth 2.0 Resource Server. The API **must still verify data permissions** before returning records.
- The second chain serves web browsers, enabling OIDC login when `openid` scope and a valid client are configured. Web cookies/sessions are managed via Spring Security. **Do not disable CSRF for the entire web app**; the example disables it only on the stateless API chain accepting bearer tokens via headers rather than cookie authentication.
- `permitAll()` for health/public is an application policy choice, not a permission dictated by the IdP. API routes and web routes must have strictly ordered filter chains; avoid default configs that accidentally open `anyRequest`.

For SAML, use `saml2Login()` and the IdP's metadata/certificates instead of the OIDC flow. For opaque access tokens, use `oauth2ResourceServer(o -> o.opaqueToken(...))` and appropriate introspection. Do not swap these mechanisms if the tokens/partners do not support them.

## 11. Pure Java 17 Example: Business Permissions Still Belong to the Application

The following example is **standalone and runnable with JDK 17** to demonstrate the difference between "knowing an identity" and "being permitted to read an invoice". It does not verify JWTs; it assumes the identity was already authenticated by Spring Security and mapped by the backend to a trusted internal account.

File `PolicyDemo.java`:

```java
import java.util.Set;

public class PolicyDemo {
    record ExternalIdentity(String issuer, String subject) {}
    record Actor(
        ExternalIdentity identity,
        String internalUserId,
        String tenantId,
        Set<String> permissions
    ) {}
    record Invoice(String id, String ownerId, String tenantId) {}

    static boolean canRead(Actor actor, Invoice invoice) {
        return actor.permissions().contains("invoice:read")
            && actor.tenantId().equals(invoice.tenantId())
            && actor.internalUserId().equals(invoice.ownerId());
    }

    public static void main(String[] args) {
        Actor alice = new Actor(
            new ExternalIdentity("https://login.example.test", "alice-123"),
            "user-17",
            "tenant-A",
            Set.of("invoice:read")
        );

        Invoice ownInvoice = new Invoice("A-001", "user-17", "tenant-A");
        Invoice otherTenant = new Invoice("B-002", "user-17", "tenant-B");
        Invoice otherOwner = new Invoice("A-003", "user-99", "tenant-A");

        System.out.println("own=" + canRead(alice, ownInvoice));
        System.out.println("otherTenant=" + canRead(alice, otherTenant));
        System.out.println("otherOwner=" + canRead(alice, otherOwner));
    }
}
```

Commands:

```bash
javac PolicyDemo.java
java PolicyDemo
```

Exact output:

```text
own=true
otherTenant=false
otherOwner=false
```

In a real application, rules may be more complex (collaborators, departments, approval thresholds, invoice status). The decision point must be a service/repository holding real data and invoked on every access path to the resource. **Never accept caller-supplied `tenantId` or `internalUserId` as proof of permission**. Trusted inputs must be constructed from the verified principal and server-side membership data.

## 12. Distinguishing Scope, Role, and Object-Level Permission

- **OAuth 2.0 Scope** describes the extent of access granted to an access token, e.g., `reports.read`. Scopes typically tie to client, consent, and token; they are not necessarily employee roles.
- **Spring Security Authority** is a permission string used by rules like `hasAuthority`. JWT Resource Server maps `scope`/`scp` to `SCOPE_...` by default. Provider-specific claims like `groups`/`roles` must be mapped intentionally (for example via `JwtAuthenticationConverter` or `GrantedAuthoritiesMapper` in the appropriate flow).
- **Business Role** is an application-specific concept, e.g., `ACCOUNTANT`, `PAYMENT_APPROVER`, which can be loaded from the DB or synced under control.
- **Object-level Permission** evaluates rights on `invoiceId`, `projectId`, `tenantId`, state, and ownership; this condition must be checked even if the endpoint already required a scope/role.

Example: a request with `SCOPE_invoice.read` is only enough to **enter the invoice-reading endpoint**; to receive invoice 42, the service must still prove that the invoice belongs to the user's tenant and that policy grants read access to that user.

## 13. Common Mistakes and How to Handle Them

1. **"Being able to sign in means seeing all data."** False: enforce object-level business controls and server-side tenant checks; never trust client-supplied IDs.
2. **Sending an ID token to an API instead of an access token.** Wrong token purpose: APIs accept only access tokens intended for the API with matching audience/issuer.
3. **Only decoding a JWT without verifying it.** Claims can be forged: use a JWT decoder/verifier and configure issuer, audience, timestamps, and trusted algorithms.
4. **Trusting any issuer or JWKS fetched from an untrusted token.** Use only a configured list of IdPs; never let the token sender choose the trusted key source.
5. **Assuming `scope=admin` means superuser across all tenants.** Scope semantics must be agreed upon; data permissions remain enforced by the application.
6. **Using email as a fixed identifier key.** Emails change/get reassigned; use an issuer-scoped stable ID and a verified account-linking mechanism.
7. **Letting only the gateway verify tokens and trusting all internal requests.** APIs need clear trust boundaries; verify trusted access tokens/identity and business permissions where enforced.
8. **Disabling CSRF for the entire app because APIs use JWT.** Separate browser cookie/session flows from stateless bearer APIs; keep CSRF for browser flows that need it.
9. **Assuming logging out in the app immediately revokes all tokens/IdP sessions.** Design local sessions, SSO logout, and TTL/revocation policies; behavior varies by IdP and protocol.
10. **Assuming locking an account at the IdP makes every unexpired JWT vanish.** Control lifecycle via token TTLs, introspection/revocation when needed, and internal permission status checks at access time.
11. **Forgetting reverse proxy/redirect URI and key rotation.** Verify HTTPS, trusted forwarded headers, exact redirect URIs, discovery/JWKS, and monitor token validation errors.
12. **Logging tokens.** Keep traces of `issuer`, protected/hashed subject when appropriate, request ID, decision, and reason; never log bearer tokens, refresh tokens, or secrets.

## 14. Design Verification Scenarios

| Scenario | Expected Outcome | Primary Responsible Layer |
| --- | --- | --- |
| Unauthenticated visit to a protected web page | Redirect to IdP or configured login entry | Spring Security web + IdP |
| User enters wrong password/MFA | IdP denies authentication | IdP |
| API receives expired JWT or invalid signature | Authentication denied, typically HTTP 401 | Spring Security Resource Server |
| API receives token from unknown issuer or audience for another API | Authentication denied if validator is configured properly | Spring Security Resource Server |
| Valid token but missing scope for endpoint | Authorization denied, typically HTTP 403 | Spring Security |
| Correct scope, invoice belongs to another tenant | Deny or hide resource existence per policy | Business service |
| User left department while token is still unexpired | Internal permissions must be updated/checked; token revocation timing depends on design | IdP + membership sync + business logic |
| IdP temporarily unreachable | Logins/token introspection may fail; already-valid JWTs may work per cache and TTL policy | IdP operations + client/API config |
| User clicks logout in the portal | Destroys portal session; ending SSO/cross-app sessions requires corresponding logout integration | Spring Security web + IdP + app |

HTTP 401 and 403 depend on request type and entry point: **bearer APIs** usually use 401 for unauthenticated/invalid tokens and 403 for authenticated but unauthorized calls. **Browser apps** may redirect to a login page instead of returning 401 directly.

## 15. Practical Implementation Principles

1. **Agree on the trust contract:** issuer, OIDC/SAML protocol, client ID, redirect/ACS URL, audience, scopes, algorithms/certificates, key rotation, metadata, and owner of each configuration.
2. **Separate three policy layers:** (a) authentication and MFA at the IdP; (b) endpoints/methods in Spring Security; (c) object/tenant permissions in business logic.
3. **Use stable, namespaced identities:** map `issuer + subject`, avoiding merging two accounts from two providers solely due to matching emails.
4. **Minimize tokens and identity data:** least-privilege scopes, appropriate TTLs, no tokens exposed in URLs/logs, secure secret management, audience checks at APIs.
5. **Define behavior upon permission revocation:** IdP deprovisioning, JIT provisioning, group sync, session revocation, access token TTLs, membership checks at APIs.
6. **Test security in both dimensions:** invalid/insufficient-scope tokens and valid tokens lacking business permission. These are two different test categories.
7. **Observe at the right layer:** password/MFA failures at the IdP; issuer/signature/audience failures at the Resource Server; invoice permission failures at the application service.
8. **Place checks close to the data:** controller/method security helps, yet does not replace policy checks when services are invoked from batch jobs, event consumers, or other APIs.

## 16. Self-Check Questions

- If the IdP authenticates successfully but the user tries to read another tenant's data, which layer must deny it? **The business system**, after Spring Security has validated the token and applied endpoint rules.
- Does Spring Security create an Authorization Server/IdP by default when `oauth2Login()` is enabled? **No**; the application becomes a client/relying party of a configured IdP.
- Can an `ID token` and an `access token` be used interchangeably? **No**; their audiences and purposes differ.
- Why should `sub` be paired with `iss`? **Because subject is meaningful only within the issuer's namespace**; two IdPs can assign the same subject value to two different people.
- Can an unexpired JWT whose user's business permissions were removed always still access data? **No**; the API must check internal status/permissions per policy; immediate JWT revocation requires dedicated design.

## Reference Documentation

- Spring Security, OAuth 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/core.html
- Spring Security, Resource Server JWT: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html
- Spring Security, Resource Server Opaque Token: https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/opaque-token.html
- Spring Security, SAML 2.0 Login: https://docs.spring.io/spring-security/reference/servlet/saml2/login/overview.html
- Spring Authorization Server, Overview: https://docs.spring.io/spring-authorization-server/reference/overview.html

**Key takeaway:** Identity federation enables applications to **trust verifiable authentication results**. Spring Security implements request security in the application/API; the IdP is responsible for establishing and issuing identity information/tokens; the business system owns the final decision on its data and actions.