# Mapping External Identity to a Local Account When Required by Business Logic

In a system using **Spring Security OAuth 2.0 / OIDC Resource Server**, an Access Token tells the API that the request was authenticated by a trusted **Authorization Server** and which permissions were granted. However, an external user or application identity **does not necessarily match a business account** in the internal database.

For example, an identity provider issues an Access Token for a user with `sub: "00u7x9..."`, whereas the order-management system stores users under `app_user.id = 2f8a...`, and tables like `orders`, `approval`, and `membership` reference this **internal ID**. The Resource Server needs a mechanism for **external identity → local account mapping** when business logic must check order ownership, tenant, account status, or activity history.

Key point: **JWT authentication**, **linking identity to an account**, and **business authorization** are three distinct tasks. Never automatically merge accounts using email, username, or client-sent header values. Conversely, not every API needs local accounts: if it only checks scopes to serve non-user-specific data, mapping may be unnecessary.

This lesson uses **Spring Boot 3.x, Spring Security 6.x, Java 17+, Spring MVC, and JWT Bearer Access Tokens** as its primary examples. All issuer, subject, tenant, and ID values are illustrative data.

## 1. Three Identity Layers in a Resource Server

### 1.1. Identity Asserted in the Access Token

Example JWT Claims Set:

~~~json
{
  "iss": "https://identity.example.test/realms/company",
  "sub": "external-user-7812",
  "aud": ["orders-api"],
  "exp": 1893456000,
  "iat": 1893452400,
  "scope": "orders.read orders.write",
  "tenant_id": "tenant-42",
  "email": "employee@example.test"
}
~~~

If the JWT is validly signed by a trusted issuer, targets the API's audience, and satisfies lifetime/profile constraints, these claims provide **authenticated context**. However:

- `sub` identifies the token's subject **within the issuer's context**, not the primary key of the internal user table.
- `email` is normally a contact attribute that can change, be revoked, or be recycled; it is not automatically an account-linking key.
- `tenant_id` may be a contract-specific claim; the API must explicitly define its data type, issuing source, and tenant permission checks.
- `scope` expresses OAuth 2.0 permission scopes; it does not imply ownership of an order or active status of a local account.
- A token signed by the right issuer still needs a matching **audience**. Never accept a client-facing OIDC ID Token in place of an API Access Token.

### 1.2. Principal Created by Spring Security

In a JWT Resource Server, Spring Security typically creates a **`JwtAuthenticationToken`** after `JwtDecoder` verifies the JWT. The principal is normally the `Jwt` object, while scopes may be mapped to `GrantedAuthority` instances such as `SCOPE_orders.read`.

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class PrincipalExampleController {

    @GetMapping("/api/debug/principal-example")
    String principalExample(@AuthenticationPrincipal Jwt jwt) {
        // Illustrates reading subject from a verified JWT only.
        return jwt.getSubject();
    }
}
~~~

This snippet illustrates obtaining the principal, **not an endpoint to enable in production to expose identifiers arbitrarily**. Being able to read `jwt.getSubject()` does not mean the API has found an `AppUser` in the database.

In common setups, `Authentication.getName()` comes from `sub` or another configured principal claim. **Changing the principal name claim** does not turn that value into an internal ID or prove that linking has been approved.

### 1.3. Internal System Account

A business account may store:

~~~text
app_user
--------
id                UUID (internal primary key)
display_name      display name
status            ACTIVE / SUSPENDED / CLOSED
created_at        account creation timestamp
...
~~~

Tables such as `orders.owner_user_id`, `approvals.approver_user_id`, and `user_tenant_membership.user_id` should reference a **stable internal ID** when that matches the domain design. If the organization switches IdPs or a user links a new identity, business data relationships do not need their foreign keys rewritten.

### 1.4. Summary of Relationships

| Layer | Example | Source of Truth | Responsibility |
| --- | --- | --- | --- |
| **JWT claims** | `iss`, `sub`, `aud`, `scope` | Trusted Authorization Server | Information about the token and external principal. |
| **Spring Security Authentication** | `JwtAuthenticationToken` | Token validation + converter | Who the request authenticated as, and which authorities it holds. |
| **Identity link** | `(issuer, subject) → local_user_id` | Database / internal linking workflow | Which local account corresponds to the external principal. |
| **Internal account** | `AppUser.id`, account status | Domain user service | Stable business identity and account lifecycle. |
| **Resource authorization** | Order owner, tenant membership | Domain services/policy | Whether viewing/modifying specific data is allowed. |

## 2. When Should You Map, and When Is Mapping Unnecessary?

**Map to a local account** when the API has a concept of an internal user independent of the IdP:

- Orders, profiles, approval histories, or data must attach to a stable `user_id` key.
- Accounts have an **ACTIVE / SUSPENDED / CLOSED** lifecycle independent of token expiration.
- Domain permissions such as company roles, tenant memberships, or record ownership are managed internally.
- Multiple identity providers can link to the same business account.
- IdP migrations, tenant merges, or historical record retention must occur without changing all foreign keys.
- The system manages onboarding, invitations, eligibility verification, or account approval workflows.

**Mapping may be unnecessary** when the API is purely a technical Resource Server—for instance, endpoints returning non-user-specific data that only require checking `SCOPE_metrics.read` or `SCOPE_catalog.read`. Without a business need for local accounts, creating user records for every Access Token adds needless complexity.

| Scenario | Is a Local Account Needed? | Sensible Design |
| --- | --- | --- |
| API exposing data after verifying an application scope | Usually no | Use `JwtAuthenticationToken` and scope policies. |
| User viewing their own orders | Yes, if orders store internal `owner_user_id` | Resolve external identity → local user; check owner. |
| Multiple subsystems sharing permissions via the same IdP | Depends | Create local users only where local data/status is needed. |
| Service-to-service without an interactive human user | Usually do not create a personal user | Manage `ServicePrincipal`/client identity separately. |
| One person logging in with two IdPs | Yes, if business logic requires a unified account | Link multiple external identities to one local user via a secure flow. |
| Locally suspending/locking an account while tokens remain unexpired | Yes | Check local account status on sensitive requests/actions. |

The design principle is to **keep mapping where real business needs exist**; do not turn logging in at an IdP into automatic creation or modification of local accounts unless the product requires it.

## 3. Base Linking Key: `(iss, sub)`, Not `sub` Alone

Under JWT/OIDC, `sub` must be interpreted within the **scope of issuer `iss`**. Two different issuers may assign the exact same string `sub: "1234"` to two completely different people.

~~~text
Issuer A: https://idp-a.example.test
  sub = "1234" -> User A

Issuer B: https://idp-b.example.test
  sub = "1234" -> User B
~~~

If the database runs only:

~~~sql
SELECT user_id FROM external_identity WHERE subject = '1234';
~~~

it can resolve the wrong user or even merge permissions across accounts. The right way uses the **(issuer, subject) pair**:

~~~sql
SELECT user_id
FROM external_identity
WHERE issuer = 'https://idp-a.example.test'
  AND subject = '1234';
~~~

Never read issuer or subject from HTTP headers like `X-User-Id` or client-sent query parameters. Always read them from an **Access Token whose signature, issuer, audience, and lifetime have been verified by the Resource Server**.

### 3.1. Why Is Email Not the Default Linking Key?

An email can:

1. Change when an employee changes their name, department, or corporate domain.
2. Be recycled after an old account is deleted or deactivated.
3. Be unverified by the issuer, or lack `email_verified`.
4. Collide or fail uniqueness in some identity systems.
5. Follow different normalization rules across parties (case sensitivity, aliases, domains).
6. Appear in an Access Token for display convenience while **not serving as a contractually stable principal identifier**.

Dangerous example:

~~~java
// DO NOT DO THIS: never log in to a local account
// solely by the email claim.
String email = jwt.getClaimAsString("email");
AppUser user = users.findByEmail(email).orElseThrow();
~~~

Even if the issuer sets `email_verified: true`, **that does not prove the user is authorized to claim an existing local account with the same email**. A verified email can be one signal in an invitation or dedicated linking workflow, never a substitute for proving ownership of the local account and external identity source.

### 3.2. `sub` Is Not Always an Employee ID, Username, or Client ID

- `sub` can be an opaque string with no human-readable meaning; never parse it to extract business info.
- OIDC can use **pairwise subject identifiers**; the same person logging in via different clients can receive different `sub` values per **sector identifier**. Never auto-merge two subjects just because their emails match.
- When changing issuers/realms or subject issuance strategies, linking keys can change; migrations must run through a controlled migration/linking workflow.
- In client credentials or machine-to-machine models, `sub` may represent a **client/application** rather than a person, depending on the token profile. Never auto-create a personal `AppUser` for every token containing `sub`.

If you need to identify services, model a separate `ServiceAccount` or `ClientPrincipal` per token contract. Never assume `client_id`, `azp`, and `sub` are always interchangeable.

## 4. Diagram: Mapping External Identity to Domain Account

Suppose the order-management application uses `app_user` and `external_identity`:

~~~text
Browser / OAuth2 Client
        |
        | Authorization: Bearer <JWT Access Token>
        v
Spring Security Resource Server
        |
        +-- Verify signature + iss + aud + exp
        |
        v
JwtAuthenticationToken
        |
        | issuer = https://identity.example.test/realms/company
        | subject = external-user-7812
        v
ExternalIdentityResolver
        |
        | SELECT user_id WHERE issuer=? AND subject=?
        v
external_identity
  (iss, sub) ------------------------> app_user.id
                                       |
                                       +-- status ACTIVE?
                                       +-- membership/tenant?
                                       +-- data policy?
                                       v
                                  Domain service
                                       |
                                       v
                                  Authorized order
~~~

Keep three layers distinct:

- **Authentication:** Spring Security verifies the Bearer Access Token and creates the principal.
- **Account resolution:** the application looks up the established link between the external principal and the local account.
- **Authorization:** business logic checks local account status, tenant permissions, and resource permissions.

Never let **account resolution** replace authentication: decoding a JWT only to extract `sub` and query the database allows a forged token to impersonate someone else's `sub`.

## 5. Database Design for Identity Links

### 5.1. Two Separate Tables

A simple relational schema (e.g., PostgreSQL):

~~~sql
CREATE TABLE app_user (
    id UUID PRIMARY KEY,
    display_name VARCHAR(200) NOT NULL,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CHECK (status IN ('ACTIVE', 'SUSPENDED', 'CLOSED'))
);

CREATE TABLE external_identity (
    id UUID PRIMARY KEY,
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    user_id UUID NOT NULL REFERENCES app_user(id),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_external_issuer_subject
        UNIQUE (issuer, subject)
);

CREATE INDEX idx_external_identity_user
    ON external_identity(user_id);
~~~

**One external identity maps to at most one local account** via `UNIQUE (issuer, subject)`. One local account can hold **multiple external identities** if the product allows logging in with multiple IdPs or linking secondary identities.

In multi-tenant environments with isolated tenant boundaries, clarify whether tenant belongs to the **issuer**, subject, or domain account. Never add `tenant_id` to the unique constraint merely to “silence duplicate key errors” if that accidentally lets one external identity hijack unauthorized accounts. Any expanded linking key must follow the **identity contract** and true authorization boundaries.

### 5.2. The Internal Key Must Remain Stable

Suppose a user migrates from IdP A to IdP B:

~~~text
Before migration:
  (iss=A, sub=old-123) -> user_id=550e8400-...

After migration:
  (iss=A, sub=old-123) -> user_id=550e8400-...  [temporarily kept]
  (iss=B, sub=new-789) -> user_id=550e8400-...  [new link]
~~~

Order tables continue referencing the same **internal `user_id`**, with no need to rewrite foreign keys. When removing link A, check active sessions, unexpired tokens, audit trails, and related security requirements. Never automatically delete or merge accounts just because an external identity disappeared from an IdP.

### 5.3. Useful Additional Fields

In production systems, you may need `provider_type`, `link_method`, `linked_by`, `last_seen_at`, `revoked_at`, `created_at`, `identity_status`, or audit records. Distinguish:

- **Identity link active:** active mapping rule for the external principal.
- **Local user active:** business account currently permitted to operate.
- **Membership/permission active:** user still holds access to a specific tenant or resource.

Do not rely on a single `active` flag to represent all three states when their lifecycles differ.

### 5.4. Do Not Log or Expose Linking Pairs Uncontrolled

`iss` and `sub` can act as personal identifiers or enable cross-system correlation. Restrict access to the mapping table, audit link mutations, avoid dumping raw subjects/emails into unnecessary logs/metrics/tickets, and protect this data under personal data policies.

## 6. Spring Security: Obtaining the Verified External Principal

### 6.1. JWT Resource Server Configuration

Example `application.yml`:

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: https://identity.example.test/realms/company
          audiences:
            - orders-api
~~~

If your Spring Boot version supports `audiences`, the API accepts only JWTs targeting `orders-api`. On other versions, configure an explicit audience validator on `JwtDecoder`. Ensure JWT signature, lifetime, and issuer are all verified per applicable profile.

Never read `iss` from an unverified JWT and dynamically fetch metadata/keys from arbitrary URLs. With multiple issuers, use an allowlist and per-approved-source decoders/validators.

API `SecurityFilterChain`:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.http.HttpMethod;
import org.springframework.security.config.Customizer;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.config.annotation.web.configurers.AbstractHttpConfigurer;
import org.springframework.security.config.http.SessionCreationPolicy;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
class ApiSecurityConfig {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session ->
                session.sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/me")
                    .hasAuthority("SCOPE_profile.read")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 ->
                oauth2.jwt(Customizer.withDefaults()));

        return http.build();
    }
}
~~~

In this example, `GET /api/me` is accessible only with a verified JWT carrying `SCOPE_profile.read`; all other unspecified URLs are denied. This illustrates a pure Bearer-header API without session cookies. **Never blindly disable CSRF for web applications using OIDC Login and cookies/sessions.**

### 6.2. What Not to Do with the Principal Name

Spring Security can use `sub` as `Authentication.getName()`, or configure another principal claim via `JwtAuthenticationConverter`. However:

~~~text
Authentication.getName() = "external-user-7812"
~~~

does not mean:

~~~text
app_user.id = "external-user-7812"
~~~

**Changing the principal name claim only changes the label visible to the framework; it does not create a safe link to a local account.** If your domain uses internal UUIDs, implement an explicit resolution step.

Similarly, `JwtGrantedAuthoritiesConverter` maps `scope` to authorities, yet **does not check whether a local account is `SUSPENDED`**, tenant membership, or per-record ownership.

## 7. Implementing External Identity Lookup with Spring Data JPA

Here is a reference model: **do not auto-create local users solely from a Bearer JWT**. The system assumes the link table has already been populated via registration/invite/provisioning or an approved linking workflow.

### 7.1. Entities and Repositories

These classes can live in separate Java files under the application's package.

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.UUID;

@Entity
@Table(
    name = "external_identity",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_external_issuer_subject",
        columnNames = {"issuer", "subject"}))
public class ExternalIdentity {

    @Id
    private UUID id;

    @Column(nullable = false, length = 512)
    private String issuer;

    @Column(nullable = false, length = 512)
    private String subject;

    @Column(name = "user_id", nullable = false)
    private UUID userId;

    protected ExternalIdentity() {}

    public UUID getUserId() {
        return userId;
    }
}
~~~

~~~java
import java.util.Optional;
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ExternalIdentityRepository
        extends JpaRepository<ExternalIdentity, UUID> {

    Optional<ExternalIdentity> findByIssuerAndSubject(
        String issuer, String subject);
}
~~~

Internal user entity:

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.util.UUID;

enum UserStatus {
    ACTIVE, SUSPENDED, CLOSED
}

@Entity
@Table(name = "app_user")
public class AppUser {

    @Id
    private UUID id;

    @Column(name = "display_name", nullable = false)
    private String displayName;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private UserStatus status;

    protected AppUser() {}

    public UUID getId() { return id; }
    public String getDisplayName() { return displayName; }
    public UserStatus getStatus() { return status; }
}
~~~

~~~java
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AppUserRepository
        extends JpaRepository<AppUser, UUID> {
}
~~~

These entities show only fields needed for the mapping example. In production, define actual migrations/schemas, lifecycles, ID generation, and audit columns. The example uses `jakarta.persistence` per Spring Boot 3.x and requires Spring Data JPA and a database driver dependency to run.

### 7.2. Read-Only Service to Resolve the Account

~~~java
import java.util.UUID;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

record CurrentAccount(UUID userId, String displayName) {}

@Service
public class CurrentAccountService {

    private final ExternalIdentityRepository identities;
    private final AppUserRepository users;

    public CurrentAccountService(
            ExternalIdentityRepository identities,
            AppUserRepository users) {
        this.identities = identities;
        this.users = users;
    }

    @Transactional(readOnly = true)
    public CurrentAccount resolve(Jwt jwt) {

        // Jwt must come only from a principal already verified by
        // Spring Security, never decoded manually.
        String issuer = jwt.getIssuer() == null
            ? null : jwt.getIssuer().toString();
        String subject = jwt.getSubject();

        if (issuer == null || subject == null || subject.isBlank()) {
            throw new AccessDeniedException("Account unavailable");
        }

        ExternalIdentity linked = identities
            .findByIssuerAndSubject(issuer, subject)
            .orElseThrow(() ->
                new AccessDeniedException("Account unavailable"));

        AppUser user = users.findById(linked.getUserId())
            .orElseThrow(() ->
                new AccessDeniedException("Account unavailable"));

        if (user.getStatus() != UserStatus.ACTIVE) {
            throw new AccessDeniedException("Account unavailable");
        }

        return new CurrentAccount(
            user.getId(), user.getDisplayName());
    }
}
~~~

The sample code intentionally **does not auto-create an account** when no link is found. Nor does it reveal details when a user is suspended. `AccessDeniedException` typically produces **403 Forbidden** once the request is authenticated, depending on security exception handling and where the exception occurs.

In systems with established account mapping, **missing links** or **disabled accounts** should be treated as “authenticated principal, yet **not permitted to use this local account**”, rather than silently inserting a new record.

### 7.3. Controller Retrieving the Local Account

~~~java
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class CurrentAccountController {

    private final CurrentAccountService currentAccountService;

    CurrentAccountController(
            CurrentAccountService currentAccountService) {
        this.currentAccountService = currentAccountService;
    }

    @GetMapping("/api/me")
    CurrentAccount me(@AuthenticationPrincipal Jwt jwt) {
        return currentAccountService.resolve(jwt);
    }
}
~~~

Runtime flow:

~~~text
GET /api/me
Authorization: Bearer <valid-access-token>
       |
       v
JWT verified, scope profile.read valid
       |
       v
Jwt: verified iss + sub
       |
       v
external_identity: look up user_id
       |
       v
app_user: check ACTIVE
       |
       v
200 {"userId": "...", "displayName": "..."}
~~~

**Responses must return only data cleared for disclosure.** Do not return full JWT claims, private emails, identity links, internal roles, or other IdP metadata unless the endpoint actually requires them.

### 7.4. When Should Resolution Happen?

In APIs requiring local accounts, resolution can occur in:

- **Application services** accepting `Jwt` or a normalized external principal structure, as above.
- **A `CurrentUser`/`CurrentAccount` resolver** for endpoints that truly need `AppUser`.
- **A custom `Authentication` converter/provider** if every endpoint in the API requires a local account—taking care with DB I/O, dependency failures, caching, and preserving verified authorities/claims.

Usually, starting with an **explicit service after authentication** keeps JWT verification separate from domain lookups. Never put account creation/modification inside `JwtDecoder`; the decoder should focus purely on token validity. Never write to the database on every Bearer request just to “sync profile” unless it is an explicitly designed, controlled process.

## 8. Mapping Is Not Account Linking: Who Is Authorized to Create Links?

Reading an approved link table is one thing; **creating or modifying links** is a far more sensitive security action. If the system automatically binds `(iss, sub)` to an account based on matching emails, attackers may exploit it to take over accounts.

### 8.1. Common Provisioning / Linking Models

| Model | How It Works | Risks to Manage |
| --- | --- | --- |
| **Pre-provisioning** | Admins/source systems create local users and links from trusted records before first login. | Wrong initial mappings, employee changes, admin privileges, and auditing. |
| **SCIM provisioning** | Identity lifecycle synced via SCIM or equivalent integration. | Identity contracts, deactivation states, idempotency, reconciliation, and connector permissions. |
| **Invite/claim account** | User holds a valid invitation/claim token and proves ownership before binding external identity. | Guessable/replayed invite tokens, wrong tenant, expiration, double linking. |
| **User-initiated account linking** | User logs into existing local account, then actively authenticates with the new IdP and confirms linking. | CSRF, login CSRF, session fixation, token/code replay, failing to verify both sides. |
| **Just-in-time (JIT) provisioning** | Creates local account on first valid principal if policy permits. | Unauthorized account creation, unclear roles/tenants, racing requests, orphan accounts. |

**No single model fits every system.** If business rules require approving employees before data access, pre-provisioning or controlled invites fit better than open JIT. If an API only needs scopes, do not auto-create an `AppUser` simply because every JWT has a `sub`.

### 8.2. Account Linking Must Prove Ownership on Both Sides

A conceptually safe user-initiated linking flow:

1. The user has an authenticated **local account session** permitted to modify login methods.
2. The system requires **reauthentication** if this is a sensitive operation.
3. The user explicitly initiates an OIDC / Authorization Code flow with the IdP to link.
4. The OAuth/OIDC Client verifies `state`, PKCE (where applicable), `nonce` per OIDC requirements, issuer, audience, and login outcome.
5. The system obtains the **verified `(iss, sub)`** of the new identity.
6. Inside a transaction, verify that this identity is not already linked to another account, that the current user may perform linking, plus tenant and policy rules.
7. Persist the link, emit an audit event, notify as needed, and maintain safe unlink/recovery mechanisms.

**A Resource Server is not an OIDC Login Client.** If an identity-linking endpoint needs to guide a user through OIDC, the OAuth 2.0 Client / Relying Party component must execute the protocol properly; never accept an ID Token arbitrarily POSTed by a browser and treat account linking as complete.

Never take `email` from a new OIDC/JWT token, search for a local user with that email, and auto-link them. If a system supports email-assisted linking, it needs additional verification steps, takeover defenses, and dedicated risk analysis; **email matching alone is insufficient evidence**.

### 8.3. Link Updates Must Be Atomic

Two initial requests can arrive concurrently:

~~~text
Request A: external identity not found -> create link
Request B: external identity not found -> create link
~~~

If code only checks “does not exist” and then inserts, both requests could create duplicate links or bind one subject to two accounts.

Combine:

- **Database `UNIQUE (issuer, subject)`** as the final guardrail.
- **Transactions** around link/account creation.
- **Unique constraint conflict handling** per idempotency policy: if bound to the same user, treat as already linked; if bound to a different user, **reject and investigate**—never auto-merge.
- Auditing of who/which process created the link and what proved ownership.
- Checking tenant boundaries and link status at commit time for sensitive changes.

Never implement “on conflict, update `user_id` to the current caller”: that turns a request into an **account-link hijack**.

## 9. JIT Provisioning: Only Apply When Allowed by Contract

Some products allow organization members to receive a local account on their first API call or login. In that case **JIT provisioning** can be appropriate, provided it is an explicit **account creation policy**, not an unconditional `orElseGet(userRepository::save)` one-liner.

### 9.1. Typical Preconditions Before Creating a User

- The JWT has passed **signature, issuer, audience, expiration**, and token-profile validation.
- The subject is genuinely an **end user** per contract (not a service principal).
- The issuer is in the organization's allowlist and authorized for account registration.
- Tenant/organization membership is verified from a **trusted source**; never accept self-asserted `tenant_id` HTTP headers.
- If an invitation is required, validate an **unexpired, unused invitation matching the right email/tenant/recipient** per ownership proof rules.
- Initial roles follow **least privilege**; never infer `ADMIN` solely from an email domain or arbitrary claim.
- Link creation uses transactions, unique constraints, and auditing.
- The lifecycle supports revoking/suspending accounts and reconciling with the IdP.

If any mandatory condition fails, **do not create an account**. Return a response instructing the user to complete onboarding or deny access per policy.

### 9.2. Risk Example When Auto-Creating by Email

~~~java
// DO NOT DO THIS:
String email = jwt.getClaimAsString("email");
AppUser user = users.findByEmail(email)
    .orElseGet(() -> users.save(
        new AppUser(/* email and roles from JWT */)));
~~~

This snippet uses email as a linking key, bypasses controlled provisioning, and risks equating token claims with internal privileges. Even when a JWT is signed by a trusted issuer, **provisioning a local account** still requires an explicit business decision.

## 10. Authorization: Valid Tokens Can Still Be Rejected by the Local Account

Suppose a user presents an unexpired Access Token with:

~~~json
{
  "iss": "https://identity.example.test/realms/company",
  "sub": "external-user-7812",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "exp": 1893456000
}
~~~

At the time of the API call, the `app_user` table contains:

~~~text
id:      2f8a8fbd-....
status:  SUSPENDED
~~~

The JWT may still be valid in signature, issuer, audience, and expiration, **yet the system must reject operations requiring an `ACTIVE` account**. Local status is an independent constraint and must not be skipped simply because the token is unexpired.

### 10.1. JWT Scopes and Roles Do Not Replace Data Permissions

A token with `SCOPE_orders.read` does not prove a user can view all orders across all tenants. The right flow:

~~~text
Valid JWT, scope orders.read
             |
             v
Resolve local user_id
             |
             v
Check ACTIVE status
             |
             v
Check tenant membership
             |
             v
Check order owner_user_id / specific policy
             |
          Allow or Deny
~~~

In multi-tenant applications, the token's `tenant_id` and internal membership may need to match. If a subject can belong to multiple tenants, design tenant selection and authorization explicitly; never trust a client-chosen `/tenants/{tenantId}` path or `X-Tenant-Id` header on its own.

### 10.2. Example Checking Permissions on an Order

Suppose the domain service resolved `CurrentAccount` and has an `Order` entity with `ownerUserId`:

~~~java
import org.springframework.security.access.AccessDeniedException;

public final class OrderAccessPolicy {

    public void requireOwner(
            CurrentAccount account,
            Order order) {

        if (!order.getOwnerUserId().equals(account.userId())) {
            throw new AccessDeniedException(
                "Order access is not permitted");
        }
    }
}
~~~

Here `Order` is an illustrative domain entity defined in your project; policies may be richer when support staff, tenant admins, or delegated access apply. The key point is **comparing against the resolved local user**, rather than using `sub` as `owner_user_id` unless the database is intentionally designed around external subjects.

Enforce authorization near the service/data-access layer to mitigate **BOLA/IDOR** (a user guessing someone else's order ID on the same endpoint).

## 11. Where Should Internal Principal Normalization Happen?

Two implementation styles are common.

### 11.1. Keep the `Jwt` Principal and Resolve When Needed

Following section 7, the controller receives `@AuthenticationPrincipal Jwt`, and a service extracts `iss/sub` to look up `AppUser`.

Advantages:

- Separates **Bearer token authentication** from business data access.
- Avoids querying the database on endpoints that do not use accounts.
- Makes it clear where account status, tenant, and data permissions are enforced.
- Makes services easy to mock when testing authorization.

Disadvantages:

- Multiple user-facing endpoints might repeat resolver calls without a shared application layer.
- Error handling and per-request caching must be consistent to avoid redundant lookups within a single request.

You can use a request-scoped `CurrentAccountContext` or facade to reuse the lookup **within a single request**. Never store mutable account objects in a global cache without considering status consistency.

### 11.2. Create a Custom Domain Principal / Authentication

Some applications want `Authentication` to carry both `Jwt` and `localUserId`, or construct a `CurrentUserPrincipal`. This can make sense when every endpoint genuinely requires a local account.

However, you must handle:

- Never replacing JWT validation with database lookups.
- Never dropping verified authorities or deriving roles from improperly typed data.
- Ensuring suspended/unlinked account errors fail **closed**.
- Putting timeouts, error observability, and cache policies around DB I/O on the authentication path.
- Ensuring caches do not keep granting access until token expiration after a local account is locked.
- Never changing `Authentication.getName()` to an internal ID while assuming components expecting the external subject still work unchanged.

Changing `JwtAuthenticationConverter.setPrincipalClaimName(...)` only alters **which claim supplies the principal name**; it does not perform account/link lookups. If you need a domain principal, build a dedicated converter/provider and test it thoroughly.

**Practical approach:** start with an **explicit post-authentication resolver service**. Move it into the authentication pipeline only for consistent architectural reasons after accounting for query cost, failure modes, and security context behavior.

## 12. Tokens and Account Lifecycles Are Not Synchronized in Real Time

Bearer JWTs typically have a lifetime independent of the local database. Therefore:

~~~text
10:00 — IdP issues JWT valid until 10:15.
10:03 — Local admin marks app_user as SUSPENDED.
10:04 — Client sends the old JWT; signature and exp are still valid.
10:04 — API checks local account status and denies access.
~~~

If the API only validates the JWT **without checking the local user**, local suspension will not be reflected in authorization. That is why account resolution is valuable when the domain manages its own lifecycle state.

### 12.1. How Should Mappings Be Cached?

You can cache `(iss, sub) → userId` to reduce queries, provided you plan for:

- **Unlink/relink**: an identity is revoked or linked to another account via a controlled workflow.
- **SUSPENDED/CLOSED**: account status changes before the JWT expires.
- **Tenant membership**: tenant or record permissions are revoked.
- **TTL and invalidation**: caching must not keep allowing revoked access beyond your defined risk tolerance.
- **Multi-node consistency**: nodes must not hold conflicting mappings for extended windows.

One option is caching stable identity links with a short TTL while querying sensitive status from a current source or using active invalidation. No single TTL fits every system; choose based on revocation requirements and risk level.

### 12.2. JWT Access Tokens and Refresh Tokens Are Not Account-Sync Feeds

A Resource Server normally receives an **Access Token**; it does not exchange refresh tokens to update user profiles. Session/login management and refresh tokens belong to the OAuth 2.0 Client and Authorization Server in their respective flows.

If an organization needs employee joiner/mover/leaver updates, use **SCIM provisioning**, lifecycle events, admin workflows, or HR directory sync rather than expecting every Access Token request to carry up-to-the-second profile state.

## 13. Special Cases: Machine-to-Machine and Delegated Access

### 13.1. Tokens Issued to Clients Rather Than Humans

In OAuth 2.0 **client credentials**, the token represents an authorized application/service, with no human user behind it. Even if the token includes `sub`, its meaning follows the Authorization Server's profile, not a personal `AppUser`.

Example:

~~~json
{
  "iss": "https://identity.example.test/realms/company",
  "sub": "nightly-batch-client",
  "client_id": "nightly-batch-client",
  "aud": ["reports-api"],
  "scope": "reports.generate"
}
~~~

For tokens like this, the system can:

- Construct a separate `ServiceAccount` or `ClientPrincipal` from **verified claims and the agreed profile**.
- Apply policies by client and resource, recording job/service audits accordingly.
- Reject endpoints requiring an **end-user local account** if the token only represents a service principal.

Never create an `AppUser` for a batch client and grant employee-style permissions simply because `sub` is present.

### 13.2. On-Behalf-Of, Delegation, and Actor Claims

In some systems, a token carries **actor** or delegation info, such as under RFC 8693 token exchange. Distinguish:

- The **subject** on whose behalf permissions are exercised;
- The **client/actor** making the request;
- Which **internal account** applies to the business operation;
- The **permissions** of the delegated action.

Never arbitrarily grab claims like `act`, `client_id`, or `azp` and substitute them for `sub` without an explicit token contract. Audits should record both the represented subject and the actor when required by business rules, avoiding mistaking a delegated token for direct login by the account owner.

## 14. Account Linking, Unlinking, and Migration Are Sensitive Operations

### 14.1. Unlinking an Identity

When a user wants to remove an external identity:

- Require the user to be authorized to manage the local account.
- Check whether this is the **last login method** to avoid locking the user out if no recovery option exists.
- Never allow external parties to unlink someone else's identity.
- Revoke/deactivate the link in the database, accounting for unexpired tokens and caches.
- Audit who removed it, when, and from which session.
- If the identity is disputed or under investigation, preserve security audit trails.

### 14.2. Switching IdPs or Changing Issuers

When a realm or issuer changes, the old `iss` and new `iss` are two distinct identifiers; you cannot simply update the verifier configuration and expect the mapping table to keep working automatically.

A migration process typically includes:

1. Inventorying **old external identities** and their local account owners.
2. Establishing mappings via a trusted identity source, with verification workflows where needed.
3. Creating new links inside a transaction, checking uniqueness and conflicts.
4. Validating in a controlled environment that users access only their own data.
5. Coordinating the cutover timing for issuers, keys, and tokens.
6. Revoking old links when appropriate while retaining audit trails.

Never “migrate” by merging every account sharing an email. Whenever two external identities lack valid proof of belonging to the same linkable subject, stop and verify through a dedicated workflow.

### 14.3. When an External Identity Already Points to Another User

If `(iss, sub)` is currently linked to `user-A` and a new request tries to bind it to `user-B`, that is a **security conflict**, not a normal update operation.

Reject automatic reassignment, require verification/investigation, and emit an audit record. In the database, the unique constraint prevents inserting duplicate rows for the pair; additionally, **application rules** must forbid overwriting `user_id` on an existing row arbitrarily.

## 15. Testing Mapping and Internal Authorization

Tests should be split across clear boundaries:

| Layer | Tooling | What It Proves |
| --- | --- | --- |
| **JWT authentication** | `JwtDecoder` with genuinely signed test JWTs or Bearer HTTP integration tests | Signature, issuer, audience, and `exp` are valid; forged tokens are rejected. |
| **ExternalIdentityResolver** | Unit tests with mocked repositories | `(iss, sub)` resolves the right local user; missing/conflicting/disabled cases fail. |
| **Database constraints** | Repository/DB integration tests | Unique `(issuer, subject)`, transactional linking, and FKs work. |
| **Endpoint authorization** | `MockMvc` + `jwt()` + service mocks | Scopes, routes, and how controllers consume the verified principal. |
| **Resource authorization** | Service/integration tests with order/tenant fixtures | Cannot access another user's or tenant's resources. |
| **Account linking flow** | OIDC Client/integration tests | Ownership proof on both sides, `state`/`nonce`/PKCE/CSRF, and conflict handling. |

### 15.1. Core Test Case Matrix

| Scenario | Expected Outcome |
| --- | --- |
| Valid JWT, `(iss, sub)` linked, local account `ACTIVE` | Resolves `userId`; request proceeds to authorization checks. |
| Valid JWT, `sub` has no link | Does not auto-create/assign a user; denies per policy. |
| Valid JWT from issuer B with same `sub` as issuer A | Does not mistakenly use issuer A's mapping. |
| JWT missing `sub` when API profile requires it | Rejected during token validation or unresolvable; no access granted. |
| Forged JWT carrying someone else's `sub`, invalid signature | Rejected before local account lookup. |
| Valid issuer JWT with audience for another API | Rejected before local account lookup. |
| Local account `SUSPENDED` while JWT is unexpired | Denies access requiring `ACTIVE` status. |
| Local account `ACTIVE`, token has scope, but order belongs to another user | Denies resource access. |
| Concurrent linking of `(iss, sub)` to two users | Protected by unique constraint; conflict does not reassign owner automatically. |
| Linking new identity via matching email without proving ownership | Does not auto-merge accounts. |
| Client credentials token calling an end-user endpoint | Not mapped to a personal user; rejected without valid user context. |
| Cache holding an unlinked mapping or suspended status | Invalidation/TTL/policy ensures revoked access is no longer granted unexpectedly. |

### 15.2. Testing the Service Without Real JWTs

For `CurrentAccountService`, unit tests can build a **mock authenticated `Jwt`** to focus on lookup logic:

~~~java
import java.time.Instant;
import java.util.Map;
import org.springframework.security.oauth2.jwt.Jwt;

final class JwtFixtures {

    static Jwt userJwt(String issuer, String subject) {
        Instant now = Instant.now();

        return new Jwt(
            "synthetic-test-token",
            now,
            now.plusSeconds(600),
            Map.of("alg", "RS256"),
            Map.of(
                "iss", issuer,
                "sub", subject,
                "aud", "orders-api"));
    }
}
~~~

Then provide mocked `ExternalIdentityRepository` and `AppUserRepository`, verifying that the service:

- Calls `findByIssuerAndSubject` with **both issuer and subject**.
- Never queries accounts by email.
- Throws `AccessDeniedException` when no mapping is found.
- Rejects `SUSPENDED` users even when a mapping exists.
- Returns the right `CurrentAccount.userId` for `ACTIVE` users.

The fixture uses synthetic tokens and claims and **does not check real signatures**; it is strictly service input data. For actually decoded JWTs, `Jwt` objects and claim getters may be normalized by Spring Security; match unit tests to the API of your version.

### 15.3. MockMvc `jwt()` Tests Do Not Verify Signatures

Example:

~~~java
mockMvc.perform(get("/api/me")
        .with(jwt()
            .jwt(j -> j.claim("iss",
                    "https://identity.example.test/realms/company")
                .claim("sub", "external-user-7812"))
            .authorities(
                new SimpleGrantedAuthority("SCOPE_profile.read"))))
    .andExpect(status().isOk());
~~~

This illustrates **authorization with a mock principal** and assumes the resolver service finds a matching local account. `spring-security-test` creates the `Authentication` directly; **`JwtDecoder` does not verify a real JWS** during this request. To prove tokens with wrong issuer/audience/signature are rejected, write integration tests sending **JWTs signed with test keys** through the real Bearer filter and decoder.

### 15.4. Testing Transactions and Linking

At the database layer, test:

~~~text
T1: link (issuer-A, sub-123) -> user-A  [SUCCESS]
T2: link (issuer-A, sub-123) -> user-B  [CONFLICT]
T3: link (issuer-B, sub-123) -> user-B  [POLICY-DEPENDENT, MAY BE VALID]
~~~

If T2 fails due to the unique constraint, the service must report a safe conflict without modifying T1's row. Also test concurrent requests (races) and idempotent behavior when the same user submits duplicate link requests.

## 16. Design Mistakes That Easily Lead to Account Takeover

| Mistake | Why It Is Dangerous | Right Approach |
| --- | --- | --- |
| Looking up users solely by `sub`. | Two issuers can collide on subjects. | Key by `(iss, sub)` and validate JWT issuer. |
| Looking up users by `email` claim. | Emails can change, be recycled, or be unverified. | Use verified linking/provisioning; never auto-merge by email. |
| Treating `X-User-Id`/tenant headers as verified identity. | Clients self-assert identity/permissions. | Read claims from verified `Authentication`; check domain policies. |
| Only Base64url-decoding JWTs to find local users. | Signature/issuer/audience could be forged. | Let Resource Server verify the token first. |
| Creating `AppUser` by default when mapping is missing. | Grants accounts outside controlled workflows. | Use JIT only when defined by policy, with preconditions and auditing. |
| Reassigning links to a new user on unique-key conflict. | Hijacks a link belonging to another user. | Reject conflicts, verify, and handle via controlled workflow. |
| Equating `Authentication.getName()` with internal UUID. | External principal is not a domain user ID. | Use an explicit resolver mapping. |
| Checking only JWT expiration while ignoring local status. | Suspended users keep access until token expiry. | Check local status and current permissions per policy. |
| Caching mappings/permissions indefinitely. | Unlinks and suspensions are not reflected. | Enforce TTL/invalidation and authorization consistency. |
| Using `client_id` as a human user across all tokens. | Service tokens get treated as human user tokens. | Separate human principals, client principals, and delegation. |
| Linking solely because `email_verified=true`. | Does not prove right to claim a local account. | Prove ownership on both sides through a secure workflow. |
| Logging JWTs/emails/subjects on every request. | Leaks credentials and personal identifiers. | Log error categories, request IDs, and access-controlled audit entries. |

## 17. Interpreting 401, 403, and Onboarding States Properly

### 17.1. Invalid Token: 401

When the JWT is missing or fails signature, issuer, audience, or expiration checks:

~~~http
HTTP/1.1 401 Unauthorized
WWW-Authenticate: Bearer
~~~

This is an **authentication** failure, normally handled by Spring Security in the filter chain. Never allow requests into account resolution before credentials are authenticated.

### 17.2. Valid Token Yet Local Account Not Permitted: Typically 403

If the JWT is valid yet the user is unlinked, `SUSPENDED`, or lacks domain permissions, the API may return:

~~~http
HTTP/1.1 403 Forbidden
Content-Type: application/json

{"code":"account_unavailable","message":"This account cannot be used for this operation."}
~~~

This is a policy example; in products with legitimate onboarding, a dedicated endpoint may return a status directing the user to complete registration per the API's HTTP contract. **Never** turn a valid token into 401 merely because a local row is missing, and never return overly detailed messages that allow enumerating existing or suspended accounts.

When handling `AccessDeniedException` thrown from a controller or service, HTTP behavior depends on method security, filter/exception handling, and application configuration; write integration tests to verify the expected status. Do not assume controller exceptions pass through the exact same handler as errors raised inside the Bearer filter.

### 17.3. Avoid Leaking Identity Mappings in Error Responses

Never return:

~~~json
{
  "error": "External sub external-user-7812 belongs to user 2f8a..."
}
~~~

Replace it with neutral client-facing messages and access-restricted internal audits. Protect `Authorization` headers, JWTs, and identifying data under least-exposure principles.

## 18. Step-by-Step Implementation Checklist

1. **Determine the business need.** If the API needs no local account, rely on appropriate claims/authorities; if data is user-bound, define a domain user ID.
2. **Finalize the identity contract.** Verify JWT Access Tokens, trusted issuers, API audience, `sub` semantics, and human vs. service principal kinds.
3. **Design a dedicated mapping.** Use `external_identity(issuer, subject, user_id)` with uniqueness and FKs; keep local `app_user.id` independent of IdPs.
4. **Define who may create/edit links.** Pre-provisioning, SCIM, invites, linking, or policy-gated JIT; never auto-link by email alone.
5. **Implement a post-authentication account resolver.** Extract `iss/sub` from verified `Jwt`, look up the mapping, verify user status, and return minimal business context.
6. **Enforce resource-level authorization.** Combine token scopes with local status, tenant membership, ownership, and specific policies.
7. **Build lifecycle workflows.** Support suspension, unlinking, IdP changes, mapping migrations, auditing, and cache invalidation on permission changes.
8. **Test failure modes.** Wrong issuer with matching `sub`, missing mapping, suspended account, missing scope, wrong owner/tenant, linking race conditions, and service tokens hitting user endpoints.
9. **Protect data and observability.** Never log Bearer tokens; restrict access to identity links; standardize 401/403 responses and audit controls.

**Remember:** **Spring Security Resource Server** proves an Access Token is valid and supplies the external principal. The **business application** decides whether that principal maps to a local account, whether it is active, and whether it has access to a given resource. When mapping is needed, use the verified **`(iss, sub)`** identity, create links through **controlled workflows**, and keep **local user IDs** independent of identity providers.

## References

- [Spring Security — OAuth 2.0 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html).
- [Spring Security — JwtAuthenticationToken API](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/oauth2/server/resource/authentication/JwtAuthenticationToken.html).
- [Spring Security — OAuth 2.0 Login / OpenID Connect Login](https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html).
- [RFC 7519 — JSON Web Token (JWT)](https://www.rfc-editor.org/rfc/rfc7519).
- [RFC 9068 — JWT Profile for OAuth 2.0 Access Tokens](https://www.rfc-editor.org/rfc/rfc9068).
- [OpenID Connect Core 1.0 — Subject Identifier](https://openid.net/specs/openid-connect-core-1_0.html#SubjectIDTypes).
- [RFC 7644 — SCIM Protocol](https://www.rfc-editor.org/rfc/rfc7644).
- [RFC 8693 — OAuth 2.0 Token Exchange](https://www.rfc-editor.org/rfc/rfc8693).
- [OWASP — Authentication Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authentication_Cheat_Sheet.html).
