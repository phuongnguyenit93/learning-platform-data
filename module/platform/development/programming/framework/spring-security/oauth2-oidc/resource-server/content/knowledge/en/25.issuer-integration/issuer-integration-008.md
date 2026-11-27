# User Identification by Issuer, Subject, and Internal Account Mapping

In a **Spring Security OAuth 2.0 / OpenID Connect (OIDC) Resource Server**, a JWT access token or opaque-token introspection result lets the API confirm **which subject the Authorization Server accepted**. Yet a sales, payments, or admin API typically also maintains an **internal account identifier**: a database user ID, employee record, order owner, tenant membership, and account lock status. Those identifiers **do not necessarily match `sub`, email, or username** supplied by the token issuer.

For example, the Identity Server returns a token with `sub = "00u84x2"`, while the Orders API stores users as `internal_user_id = "usr-0042"`. If the application directly calls `orderRepository.findByOwnerId(jwt.getSubject())`, it may fail to find orders; worse, when integrating multiple issuers, **two issuers can assign the exact same `sub` to two different people**. Conversely, **one internal user can be linked to multiple external identities** (switching Identity Providers, corporate vs. customer accounts, or migrations).

This lesson explains how to establish a **trusted identity via `(issuer, subject)`**, store mappings to internal accounts, decide where to perform lookups in Spring Security, prevent account takeover during linking, and test identity-confusion scenarios across issuers and tenants.

> **Core principle:** External identifiers are not internal database keys. Trust `iss` and `sub` **only after the access token passes issuer, signature/active, audience, lifetime, and profile validation**. Use the **`(iss, sub)`** pair as the external identity key when the issuer contract guarantees subjects within the issuer namespace; map it to an **immutable internal user ID**, while evaluating role/tenant/resource permissions independently.

## 1. Three Roles in an OAuth2/OIDC Flow

Suppose Shop Web calls the Orders API:

- **Identity Server (Authorization Server / OIDC Provider)**: authenticates users and issues access tokens; may issue ID tokens for OIDC Clients.
- **Shop Web (OAuth2/OIDC Client)**: orchestrates login or consent, obtains access tokens, and calls APIs per valid grants/flows.
- **Orders API (Resource Server)**: verifies access tokens and resource access permissions.
- **User Management/Account DB**: manages internal user IDs, account status, external identity links, and memberships.

~~~mermaid
sequenceDiagram
    actor U as User
    participant C as Shop Web / OAuth2 Client
    participant AS as Identity Server
    participant API as Orders API / Resource Server
    participant DB as Identity Link + Account DB

    U->>C: Opens orders page
    C->>AS: OAuth2/OIDC authorization flow
    AS-->>C: Access token for Orders API
    C->>API: Authorization: Bearer <access-token>
    API->>API: Verify JWT / introspect opaque
    API->>API: Confirm issuer, subject, audience
    API->>DB: Lookup by (issuer, subject) if needed
    DB-->>API: internalUserId, enabled, memberships
    API->>API: Check scope + tenant/owner policy
    API-->>C: Permitted data or denial
~~~

Note: The **OIDC Client** handles login and ID tokens; the **Resource Server** verifies **OAuth2 access tokens** intended for the API. An ID token normally carries the Client ID as its audience and **must never substitute for an access token** at the Orders API just because it has `sub` or email.

### 1.1. Two Questions That Must Stay Separate

1. **"Who is this external identity?"** — The Authorization Server attests the subject within the issuer namespace via a token accepted by the API.
2. **"Which application account does that identity map to, and what permissions does it have?"** — Internal mapping/authorization answers this, including account status, tenant membership, and owner/assignments.

A valid token answers the first question, yet **does not** automatically answer the second. A user can log in properly yet lack a provisioned internal account or have Orders API access disabled by an administrator.

## 2. Understanding `iss` and `sub`

### 2.1. `iss` — Issuer

`iss` identifies the token issuer per JWT/OIDC profile semantics. Examples:

~~~text
https://identity.example.test/realms/shop
https://login.partner.example.test/tenant/acme
~~~

These are two **distinct identity namespaces**, even if both emit the exact same `sub`.

**Never infer the issuer from an email domain or the Client request's hostname.** The issuer must belong to the sources the API **is configured to trust**, and JWTs must verify against the right issuer/keys/audience; for opaque tokens, introspection results must bind to a trusted Authorization Server per contract.

### 2.2. `sub` — Subject

`sub` is the subject identifier assigned by the issuer in a token. Example:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "00u84x2",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

In standard user architectures, `sub` represents a user; in other tokens—especially service/client-credentials tokens—it can represent a Client or non-human principal. **Never assume every access token with `sub` is a human user account owning data.**

### 2.3. The External Identity Key Is the `(iss, sub)` Pair

| Issuer | Subject | Who Could It Be? |
| --- | --- | --- |
| `https://identity.example.test/realms/shop` | `00u84x2` | Alice in the internal Identity Server |
| `https://login.partner.example.test/tenant/acme` | `00u84x2` | Carol in the partner IdP |
| `https://identity.example.test/realms/shop` | `00u84x3` | Bob in the same Identity Server |

If the database only queries:

~~~sql
SELECT internal_user_id
FROM external_identities
WHERE subject = '00u84x2';
~~~

Alice's and Carol's rows can **collide or map to the wrong person**. Queries must include the issuer:

~~~sql
SELECT internal_user_id
FROM external_identities
WHERE issuer = :verifiedIssuer
  AND subject = :verifiedSubject;
~~~

**Use the verified issuer value**, never a Client-supplied `X-Issuer` header. Even with a single fixed issuer in config, still store `issuer` in the database to prevent pain during multi-issuer expansion or migration.

### 2.4. Pairwise Subjects in OIDC

An OIDC Provider may issue **pairwise subject identifiers**: the same user receives different `sub` values across different clients/sectors to limit cross-site tracking. Thus:

~~~text
Real user: Alice
OIDC Client A receives sub = pA-123
OIDC Client B receives sub = pB-456
~~~

Never conclude two subjects are the same or different people **solely from string differences**; base decisions on subject identifier policies and IdP-supported identity linking mechanisms. The API should use the identifier **guaranteed by the Authorization Server in API-targeted access tokens**, never swapping in `sub` from another Client's ID token arbitrarily.

## 3. Distinguishing `sub`, Email, Username, Client ID, and Tenant

| Data | Function | Suitable as External Link Key? |
| --- | --- | --- |
| **`iss + sub`** | Identifier within issuer namespace | **Usually yes**, if issuer/profile guarantees stability and semantics |
| `email` | Contact info | **Never automatically**: mutable, reusable, or unverified |
| `email_verified` | Flag indicating email verified per issuer policy | Does not prove two accounts with the same email are the same person or linkable |
| `preferred_username` | Login/display name | Mutable, non-unique, issuer-dependent |
| `name` | Display name | Not an identity key |
| `client_id` | OAuth2 Client issued the token | Not synonymous with internal user |
| `azp` | Authorized party in profiles with this claim | Not a user/tenant ID |
| `aud` | Intended Resource Server/Client recipient | Not an account or owner namespace |
| `tenant_id` / `org_id` (custom) | Tenant context/membership per AS | Does not replace internal user ID and membership policies |
| **`internal_user_id`** | Application-managed account key | **Yes** for internal business tables |

Example of two users from different issuers sharing an email:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "alice-001",
  "email": "shared@example.test",
  "email_verified": true
}
~~~

~~~json
{
  "iss": "https://login.partner.example.test/tenant/acme",
  "sub": "carol-998",
  "email": "shared@example.test",
  "email_verified": true
}
~~~

**Never automatically merge these two identities into one internal account.** That can cause **account takeover** if emails are recycled, issuers apply different verification standards, or one source is managed by a less trusted party than the other.

### 3.1. `Authentication.getName()` Is Not Necessarily an Email

Spring Security sets `sub` as the default JWT authentication principal name. Never assume:

~~~java
String email = authentication.getName(); // May actually be sub!
~~~

If the application needs an email, read it from a verified claim **per contract** and treat it as contact data—never implicitly as an owner lookup key.

### 3.2. Having a Subject Does Not Mean "Human User Currently Logged In via Browser"

In a **Client Credentials** flow, an access token can represent a service:

~~~json
{
  "iss": "https://identity.example.test/realms/shop",
  "sub": "nightly-sync-service",
  "client_id": "nightly-sync-service",
  "aud": ["orders-api"],
  "scope": "orders.sync"
}
~~~

If the API supports service principals, establish a **dedicated service-account mapping and authority policy**, never auto-creating internal human-user accounts or attributing every service call to an employee.

## 4. Where Does Token Trust Come From?

A JSON string containing `iss` and `sub` **is not proof by itself**; a caller can craft any JWT payload.

~~~text
Unverified Bearer token
  -> verify signature/issuer/audience/time/type or introspection
  -> verified token / OAuth2AuthenticatedPrincipal
  -> read iss + sub
  -> look up identity link
  -> check account/membership/permissions
~~~

### 4.1. With JWT Access Tokens

Spring Security Resource Server typically uses `JwtDecoder`/`NimbusJwtDecoder` to:

- Verify JWS using configured trusted keys/JWKS.
- Check `iss` against the configured issuer.
- Check `exp` and `nbf` via validators.
- Check `aud` for **Orders API**; never assume every issuer config automatically enforces your application's desired audience.
- Check token purpose/type/profile per AS contract where required.

**Never Base64-decode a JWT payload and query the database before Spring verifies the token.**

### 4.2. With Opaque Access Tokens

Opaque tokens typically contain no claims the Resource Server may decode locally. Spring Security calls `OpaqueTokenIntrospector`; the AS confirms `active` status and returns profile metadata.

Illustrative response:

~~~json
{
  "active": true,
  "iss": "https://identity.example.test/realms/shop",
  "sub": "00u84x2",
  "aud": ["orders-api"],
  "scope": "orders.read",
  "client_id": "shop-web"
}
~~~

**RFC 7662 does not guarantee every response includes `iss` or `sub`.** If the API needs user identity linking, the AS must commit to emitting those fields **or** the endpoint/registration must provide a trusted issuer binding and well-defined subject identifier. Never inject default `iss` or `sub` values to "patch" a metadata-deficient response.

### 4.3. Separating `iss` in JWTs from Introspection Endpoint Trust

JWTs carry an `iss` claim verified against trusted issuer/JWKS. In opaque flows, the Resource Server first trusts the **introspection endpoint, TLS, and credential/resource restrictions**; an `iss` claim returned by the AS can add an extra issuer constraint. Never accept another issuer merely because an endpoint returns `active: true` if that endpoint's contract allows introspecting multiple realms without API-side source restrictions.

## 5. A Two-Level Mapping Example

Define three entities:

1. **External identity**: `(issuer, subject)` from the Identity Server.
2. **Internal account**: application-created `internal_user_id`, serving as the durable key in business tables.
3. **Tenant membership**: which permissions an account holds in which tenant; changeable independently of identity.

~~~mermaid
erDiagram
    INTERNAL_USERS ||--o{ EXTERNAL_IDENTITIES : "linked from"
    INTERNAL_USERS ||--o{ TENANT_MEMBERSHIPS : "belongs to"
    TENANTS ||--o{ TENANT_MEMBERSHIPS : "has members"
    TENANTS ||--o{ ORDERS : "owns"
    INTERNAL_USERS ||--o{ ORDERS : "customer or owner"

    INTERNAL_USERS {
        uuid id PK
        string status
        datetime created_at
    }
    EXTERNAL_IDENTITIES {
        long id PK
        string issuer
        string subject
        uuid internal_user_id FK
        datetime linked_at
    }
    TENANTS {
        uuid id PK
        string name
    }
    TENANT_MEMBERSHIPS {
        uuid user_id FK
        uuid tenant_id FK
        string role
        string status
    }
    ORDERS {
        uuid id PK
        uuid tenant_id FK
        uuid owner_user_id FK
        string status
    }
~~~

Example:

| External Issuer | External Subject | Internal User | Tenant |
| --- | --- | --- | --- |
| Internal IdP | `00u84x2` | `usr-0042` | tenant A |
| Partner IdP | `partner-alice-73` | `usr-0042` | tenant A, after verified linking |
| Partner IdP | `00u84x2` | `usr-1290` | tenant B |

**One internal account can have multiple external identities**; however, each `(issuer, subject)` maps to **at most one internal user** unless the design supports ownership transfers in a dedicated administrative transaction.

### 5.1. Illustrative SQL Schema

PostgreSQL example:

~~~sql
CREATE TABLE internal_users (
    id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE external_identities (
    id BIGSERIAL PRIMARY KEY,
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    internal_user_id UUID NOT NULL
        REFERENCES internal_users(id),
    linked_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_external_identity
        UNIQUE (issuer, subject)
);

CREATE INDEX idx_external_identity_user
    ON external_identities(internal_user_id);

CREATE TABLE tenant_memberships (
    user_id UUID NOT NULL REFERENCES internal_users(id),
    tenant_id UUID NOT NULL,
    role_code VARCHAR(80) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (user_id, tenant_id, role_code)
);
~~~

**The `(issuer, subject)` unique constraint is a data invariant**, not just a query optimization. It prevents two accounts from claiming the same external identity due to race conditions during linking.

### 5.2. Business Data Should Store Internal User IDs

Orders:

~~~sql
CREATE TABLE orders (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    owner_user_id UUID NOT NULL REFERENCES internal_users(id),
    status VARCHAR(32) NOT NULL
);
~~~

Do not store `sub` or email directly in every order table. When an IdP changes issuers or a user links a new identity, **`owner_user_id` remains a stable internal account key**, avoiding migrating business data for every external claim change.

### 5.3. Separate Email Changes from Identity Changes

Email, phone, and display name are **profile attributes** updatable via separate workflows. An email change from the IdP must not automatically change `internal_user_id` or transfer order ownership. Similarly, a new external identity sharing a former user's email **must never automatically inherit that account**.

## 6. Normalization Rules for Issuer and Subject

Issuer and subject identifiers should be treated as **opaque identifiers per contract**, never "cleaned up" with transformations that erase distinctions.

Two issuers:

~~~text
https://identity.example.test/realms/shop
https://identity.example.test/realms/shop/
~~~

can count as **two distinct values** in an issuer contract. Never arbitrarily strip trailing slashes, drop realm paths, downgrade `https` to `http`, merge hostnames, or check `contains("identity")`.

### 6.1. Never Lowercase `sub` Arbitrarily

~~~text
sub = UserABC
sub = userabc
~~~

If the AS treats them as distinct values, lowercasing causes an **identity collision**. Likewise, do not trim, Unicode-normalize, or decode characters inside `sub` unless mandated by contract. Store verified values **verbatim**, with database collations/unique indexes preserving the required case/character sensitivity.

### 6.2. Canonical Issuer per Trusted Configuration

Generally use the **canonical issuer published by the AS**, verified by the JWT validator, as the stored value in identity links. If an AS has official aliases, handle alias mapping through a controlled migration policy—never a rule like "all URLs on the same host are the same issuer."

### 6.3. Never Use Raw Tokens as Identity Keys

Access tokens rotate, expire, or get issued repeatedly for the same subject. Never use the full JWT string as a user key:

~~~text
Token X and token Y differ
-> can still share the same (iss, sub)
-> same internal user ID
~~~

Tokens are secret credentials and should never be stored in external identity tables or placed in URLs/logs.

## 7. Two Lookup Strategies in Spring Security

There are two primary options:

| Strategy | Lookup Location | Behavior | When Appropriate |
| --- | --- | --- | --- |
| **A. Lookup in service** | After JWT authentication, at endpoints needing an account | Token authenticates first; service permits business logic only after resolving the account | APIs with endpoints not needing local accounts, supporting onboarding or service tokens |
| **B. Lookup in authentication converter** | After `JwtDecoder`, before creating `Authentication` | Every authenticated request on the chain requires an active local account link | Every protected request strictly requires a local user |
| **C. Lookup via reactive converter** | Inside `Mono`/`Flux` in WebFlux | Same as B, yet non-blocking | WebFlux APIs requiring account linking during authentication |

**No single strategy fits every system.** What decides is your **security invariant**: must an internal account exist immediately at token authentication, or only when invoking specific operations?

### 7.1. Avoid Ad-Hoc Lookups in Controllers with Inconsistent Conventions

Wrong:

~~~java
// Do not ad-hoc look up accounts by email in controllers.
User user = userRepo.findByEmail(jwt.getClaimAsString("email"));
~~~

If each controller picks a different claim, the system develops **inconsistent identity mapping**. Centralize resolution in an `ExternalIdentityResolver` or dedicated service so every endpoint enforces the same `(iss, sub)` contract.

## 8. Configuring Spring Boot Resource Server to Verify JWTs

Examples use **Spring Boot 3 / Spring Security 6, Java 17+, Servlet/MVC**. The first step must verify tokens accurately.

### 8.1. Dependencies

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-resource-server'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
~~~

Choose DB drivers, migrations, and dependency versions per project. Example code uses synchronous `JpaRepository` in the Servlet stack; **never copy blocking JPA lookups directly onto the Netty WebFlux event loop**.

### 8.2. application.yml

~~~yaml
spring:
  security:
    oauth2:
      resourceserver:
        jwt:
          issuer-uri: ${OAUTH_ISSUER_URI}
          jwk-set-uri: ${OAUTH_JWKS_URI}

app:
  security:
    expected-audience: orders-api
~~~

Example:

~~~text
OAUTH_ISSUER_URI=https://identity.example.test/realms/shop
OAUTH_JWKS_URI=https://identity.example.test/realms/shop/protocol/openid-connect/certs
~~~

These are illustrative URIs. Production must use AS-published endpoints and valid TLS/JWKS/algorithm configurations.

### 8.3. `JwtDecoder` with Issuer, Time, and Audience

When defining a custom decoder, preserve complete validation:

~~~java
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.oauth2.core.DelegatingOAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2Error;
import org.springframework.security.oauth2.core.OAuth2TokenValidator;
import org.springframework.security.oauth2.core.OAuth2TokenValidatorResult;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.jwt.JwtDecoder;
import org.springframework.security.oauth2.jwt.JwtValidators;
import org.springframework.security.oauth2.jwt.NimbusJwtDecoder;

@Configuration
class VerifiedJwtConfiguration {

    @Bean
    JwtDecoder jwtDecoder(
            @Value("${spring.security.oauth2.resourceserver.jwt.issuer-uri}")
            String issuer,
            @Value("${spring.security.oauth2.resourceserver.jwt.jwk-set-uri}")
            String jwksUri,
            @Value("${app.security.expected-audience}")
            String expectedAudience) {

        NimbusJwtDecoder decoder =
                NimbusJwtDecoder.withJwkSetUri(jwksUri).build();

        OAuth2TokenValidator<Jwt> defaultValidators =
                JwtValidators.createDefaultWithIssuer(issuer);

        OAuth2TokenValidator<Jwt> audienceValidator = jwt ->
                jwt.getAudience().contains(expectedAudience)
                    ? OAuth2TokenValidatorResult.success()
                    : OAuth2TokenValidatorResult.failure(
                        new OAuth2Error(
                            "invalid_token",
                            "Invalid audience for Orders API",
                            null));

        decoder.setJwtValidator(
                new DelegatingOAuth2TokenValidator<>(
                    defaultValidators, audienceValidator));
        return decoder;
    }
}
~~~

`JwtValidators.createDefaultWithIssuer` applies the appropriate default validators plus issuer validation for your Spring Security line; **audience** is enforced additionally per the Orders API contract. When customizing the decoder, never accidentally drop issuer/time checks. Multi-issuer apps need an `AuthenticationManager`/decoder selection mechanism backed by a **trusted issuer allowlist**, never letting a token choose its own JWKS URI.

**This is still not the entire token contract.** A system may also require access-token profile/type validation, allowed signing algorithms, and mandatory claims. The key rule is that `(iss, sub)` is used only after this validation layer passes.

### 8.4. `SecurityFilterChain`

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
class OrdersApiSecurity {

    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        return http
            .securityMatcher("/api/**")
            .csrf(AbstractHttpConfigurer::disable)
            .sessionManagement(session -> session
                .sessionCreationPolicy(SessionCreationPolicy.STATELESS))
            .authorizeHttpRequests(auth -> auth
                .requestMatchers(HttpMethod.GET, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.read")
                .requestMatchers(HttpMethod.POST, "/api/orders/**")
                    .hasAuthority("SCOPE_orders.write")
                .anyRequest().denyAll())
            .oauth2ResourceServer(oauth2 -> oauth2
                .jwt(Customizer.withDefaults()))
            .build();
    }
}
~~~

This is a Bearer-header-only API; only under the assumption that **no ambient cookie/session authenticates protected requests** is disabling CSRF on this chain appropriate. Web applications using sessions/cookies still require CSRF protection. `securityMatcher("/api/**")` does not protect URLs outside that scope unless another chain handles them.

`hasAuthority("SCOPE_orders.read")` **does not** replace identity lookup, account status, tenant membership, or object-level policies.

## 9. Spring Data JPA: Mapping `(iss, sub)` to Internal Users

### 9.1. External Identity Entity

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Index;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;

import java.util.UUID;

@Entity
@Table(
    name = "external_identities",
    uniqueConstraints = @UniqueConstraint(
        name = "uq_external_identity",
        columnNames = {"issuer", "subject"}),
    indexes = @Index(
        name = "idx_external_identity_user",
        columnList = "internal_user_id")
)
public class ExternalIdentity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 512)
    private String issuer;

    @Column(nullable = false, length = 512)
    private String subject;

    @Column(name = "internal_user_id", nullable = false)
    private UUID internalUserId;

    protected ExternalIdentity() {}

    public ExternalIdentity(
            String issuer, String subject, UUID internalUserId) {
        this.issuer = issuer;
        this.subject = subject;
        this.internalUserId = internalUserId;
    }

    public String getIssuer() { return issuer; }
    public String getSubject() { return subject; }
    public UUID getInternalUserId() { return internalUserId; }
}
~~~

This example intentionally stores only identity-link fields. In practice, consider account status, auditing, created/updated timestamps, provider registration, and migration procedures; avoid storing raw JWTs or token secrets in this table.

### 9.2. Composite-Key Repository

~~~java
import java.util.Optional;
import org.springframework.data.jpa.repository.JpaRepository;

public interface ExternalIdentityRepository
        extends JpaRepository<ExternalIdentity, Long> {

    Optional<ExternalIdentity> findByIssuerAndSubject(
            String issuer, String subject);
}
~~~

Usage:

~~~java
String verifiedIssuer = jwt.getIssuer().toString();
String verifiedSubject = jwt.getSubject();

ExternalIdentity identity = identities
    .findByIssuerAndSubject(verifiedIssuer, verifiedSubject)
    .orElseThrow(() -> new UnlinkedIdentityException());
~~~

`UnlinkedIdentityException` is an illustrative application-defined business exception. **The JWT has already been verified by the decoder before reaching the service**, and issuer/subject should be checked for null/blank before lookup if required by profile.

### 9.3. User Account and Status

An existing identity link does not guarantee the local user is still active:

~~~text
externalIdentity -> internalUserId
internalUsers[id].status = DISABLED
~~~

If policy requires an enabled account, check it explicitly. A user holding a valid AS token yet disabled in Orders API **must not automatically continue accessing the API**. Conversely, if certain endpoints support onboarding, explicitly define the narrow scope of requests allowed before an account is linked.

## 10. Strategy A: Resolving in the Service When Business Logic Needs It

This option is generally **more loosely coupled** to the database: the Resource Server verifies JWTs and scopes; only services needing the internal user ID resolve the identity.

### 10.1. Dedicated Identity Resolution Service

~~~java
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class InternalIdentityService {

    private final ExternalIdentityRepository links;
    private final InternalUserRepository users;

    public InternalIdentityService(
            ExternalIdentityRepository links,
            InternalUserRepository users) {
        this.links = links;
        this.users = users;
    }

    @Transactional(readOnly = true)
    public UUID requireEnabledUser(Jwt jwt) {
        if (jwt.getIssuer() == null
                || jwt.getSubject() == null
                || jwt.getSubject().isBlank()) {
            throw new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Account not available");
        }

        var link = links.findByIssuerAndSubject(
                jwt.getIssuer().toString(),
                jwt.getSubject())
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Account not available"));

        var user = users.findById(link.getInternalUserId())
            .orElseThrow(() -> new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Account not available"));

        if (!user.isEnabled()) {
            throw new ResponseStatusException(
                HttpStatus.FORBIDDEN, "Account not available");
        }

        return user.getId();
    }
}
~~~

`InternalUserRepository` and `InternalUser` are application types implementing the `internal_users` schema; the example assumes `isEnabled()` and `getId()` exist. Returning a generic public error message avoids leaking why the account is unavailable; internal logs can distinguish unlinked vs. disabled per policy.

### 10.2. Controller Receiving the Verified JWT

~~~java
import java.util.Map;
import java.util.UUID;
import org.springframework.security.core.annotation.AuthenticationPrincipal;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/me")
class MeController {

    private final InternalIdentityService identities;

    MeController(InternalIdentityService identities) {
        this.identities = identities;
    }

    @GetMapping("/account")
    Map<String, String> account(@AuthenticationPrincipal Jwt jwt) {
        UUID id = identities.requireEnabledUser(jwt);
        return Map.of("internalUserId", id.toString());
    }
}
~~~

`@AuthenticationPrincipal Jwt` works while the JWT Resource Server principal remains `Jwt`. If using opaque authentication or a custom principal type, adjust principal extraction per contract rather than casting blindly.

### 10.3. When Does Strategy A Work Best?

- APIs with public/health endpoints or resources needing tokens without local profiles.
- Onboarding flows for identities freshly authenticated by an IdP that lack local accounts yet.
- Systems with both user tokens and service tokens, each following distinct policies.
- Cases where only a subset of operations need account linking, avoiding database lookups on every request.

In return, the service must be invoked across **every business branch using internal user IDs**. Centralize it in a policy/service layer and add negative tests so new endpoints never forget it.

## 11. Strategy B: Resolving in the JWT Authentication Converter

If **every protected request requires an enabled local user**, unlinked/disabled callers can be rejected directly in the authentication converter after `JwtDecoder` verifies the token.

### 11.1. `JwtAuthenticationToken` Keeps the JWT Yet Changes `getName()`

This is an easy detail to misunderstand:

~~~java
new JwtAuthenticationToken(jwt, authorities, internalUserId);
~~~

It preserves:

~~~text
Authentication.getPrincipal()   -> Verified Jwt
Authentication.getName()        -> internalUserId
Authentication.getAuthorities() -> GrantedAuthorities granted
~~~

**Changing `getName()` does not turn `getPrincipal()` into a domain User.** A controller using `@AuthenticationPrincipal Jwt` still receives the `Jwt`; if a domain profile is needed, look it up or design an intentional authentication subtype.

### 11.2. Custom Converter in a Servlet Resource Server

~~~java
import java.util.ArrayList;
import java.util.Collection;
import java.util.List;
import java.util.UUID;

import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.authentication.DisabledException;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;

public final class LocalAccountJwtConverter
        implements Converter<Jwt, AbstractAuthenticationToken> {

    private final ExternalIdentityRepository links;
    private final InternalUserRepository users;
    private final JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

    public LocalAccountJwtConverter(
            ExternalIdentityRepository links,
            InternalUserRepository users) {
        this.links = links;
        this.users = users;
    }

    @Override
    public AbstractAuthenticationToken convert(Jwt jwt) {
        if (jwt.getIssuer() == null
                || jwt.getSubject() == null
                || jwt.getSubject().isBlank()) {
            throw new BadCredentialsException(
                "Missing verified identity");
        }

        String issuer = jwt.getIssuer().toString();
        String subject = jwt.getSubject();

        var link = links.findByIssuerAndSubject(issuer, subject)
            .orElseThrow(() -> new BadCredentialsException(
                "No local account linked"));

        UUID userId = link.getInternalUserId();
        var user = users.findById(userId)
            .orElseThrow(() -> new BadCredentialsException(
                "Local account unavailable"));

        if (!user.isEnabled()) {
            throw new DisabledException(
                "Local account unavailable");
        }

        Collection<GrantedAuthority> scopeAuthorities =
                scopes.convert(jwt);
        List<GrantedAuthority> authorities =
                new ArrayList<>();
        if (scopeAuthorities != null) {
            authorities.addAll(scopeAuthorities);
        }

        // Never grant ROLE_ADMIN by default merely because a link exists.
        return new JwtAuthenticationToken(
                jwt, authorities, userId.toString());
    }
}
~~~

In this example, `InternalUserRepository` is synchronous and the converter runs in **Servlet/MVC**. Querying repositories here makes authentication **database-dependent on every request** without caching or alternative policies. That can be reasonable when "account enabled" is a strict prerequisite, yet latency, availability, transaction boundaries, and database errors must be accounted for.

This code **does not map roles/tenants from the database**. If roles are needed, use an explicit allowlist mapping and tenant scoping—never elevate privileges just because a link exists.

### 11.3. Attaching the Converter to SecurityFilterChain

~~~java
@Bean
SecurityFilterChain api(
        HttpSecurity http,
        ExternalIdentityRepository links,
        InternalUserRepository users) throws Exception {

    return http
        .securityMatcher("/api/**")
        .csrf(AbstractHttpConfigurer::disable)
        .authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyRequest().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2.jwt(jwt -> jwt
            .jwtAuthenticationConverter(
                new LocalAccountJwtConverter(links, users))))
        .build();
}
~~~

This is an **alternative variant** to the chain configuration in Section 8—never register two chains with overlapping matchers expecting the framework to pick converters per request. In production, separate HTTP methods/scopes properly; this snippet merely illustrates where to plug in the converter.

### 11.4. Missing Link: 401 or 403?

If an enabled local account is a **mandatory prerequisite for authentication**, the converter can throw `AuthenticationException`, leaving the request without a valid Authentication and typically returning **401** via the Bearer entry point.

If the token is authenticated yet an endpoint forbids unlinked accounts from performing an action, the API may return **403** in the authorization/business layer. When dedicated onboarding flows exist, **never place a link-requiring converter across all routes** and lock unlinked callers out of onboarding endpoints. This is a **contract decision**; no single status code fits every policy.

### 11.5. Internal User Data Must Never Substitute for Token Validation

Never create a principal merely because the database finds `(iss, sub)` from an unverified token. The converter above receives a `Jwt` **after `JwtDecoder`** in the Spring Security pipeline; never Base64-decode the Authorization header yourself.

## 12. Strategy C: WebFlux and Reactive Lookups

In **Spring WebFlux**, never call blocking JPA/JDBC `findByIssuerAndSubject` directly on the Netty event loop or call `.block()` inside a JWT converter. Use R2DBC/reactive repositories and return `Mono<AbstractAuthenticationToken>`.

### 12.1. Reactive Repository

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

interface ReactiveExternalIdentityRepository
        extends ReactiveCrudRepository<ExternalIdentityRecord, Long> {

    Mono<ExternalIdentityRecord> findByIssuerAndSubject(
            String issuer, String subject);
}
~~~

`ExternalIdentityRecord` is a project-specific R2DBC entity, **not the JPA entity from Section 9**. The database driver and reactive repository must genuinely be non-blocking.

### 12.2. Reactive Converter

~~~java
import java.util.ArrayList;
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.authentication.BadCredentialsException;
import org.springframework.security.core.GrantedAuthority;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtAuthenticationToken;
import org.springframework.security.oauth2.server.resource.authentication
        .JwtGrantedAuthoritiesConverter;

import reactor.core.publisher.Mono;

final class ReactiveLocalIdentityConverter
        implements Converter<Jwt, Mono<AbstractAuthenticationToken>> {

    private final ReactiveExternalIdentityRepository links;
    private final JwtGrantedAuthoritiesConverter scopes =
            new JwtGrantedAuthoritiesConverter();

    ReactiveLocalIdentityConverter(
            ReactiveExternalIdentityRepository links) {
        this.links = links;
    }

    @Override
    public Mono<AbstractAuthenticationToken> convert(Jwt jwt) {
        if (jwt.getIssuer() == null || jwt.getSubject() == null) {
            return Mono.error(new BadCredentialsException(
                    "Missing verified issuer or subject"));
        }

        return links.findByIssuerAndSubject(
                jwt.getIssuer().toString(),
                jwt.getSubject())
            .switchIfEmpty(Mono.error(new BadCredentialsException(
                "Identity is not linked")))
            .map(link -> {
                // link.internalUserId() comes from the trusted DB.
                var authorities = new ArrayList<GrantedAuthority>();
                var tokenScopes = scopes.convert(jwt);
                if (tokenScopes != null) {
                    authorities.addAll(tokenScopes);
                }
                return (AbstractAuthenticationToken)
                    new JwtAuthenticationToken(
                        jwt,
                        authorities,
                        link.internalUserId().toString());
            });
    }
}
~~~

This example **omits checking user enabled status** to stay focused on mapping; if enabled status is mandatory, add a **reactive lookup + validation** before returning `Authentication` and fail closed when disabled or on DB errors.

### 12.3. WebFlux Configuration

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.security.authentication.AbstractAuthenticationToken;
import org.springframework.security.config.web.server.ServerHttpSecurity;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.security.web.server.SecurityWebFilterChain;
import reactor.core.publisher.Mono;

@Bean
SecurityWebFilterChain webfluxApi(
        ServerHttpSecurity http,
        Converter<Jwt, Mono<AbstractAuthenticationToken>> converter) {

    return http
        .authorizeExchange(exchanges -> exchanges
            .pathMatchers("/api/orders/**")
                .hasAuthority("SCOPE_orders.read")
            .anyExchange().denyAll())
        .oauth2ResourceServer(oauth2 -> oauth2
            .jwt(jwt -> jwt.jwtAuthenticationConverter(converter)))
        .build();
}
~~~

This is **WebFlux** code requiring a `ReactiveJwtDecoder` with issuer/audience and security policy; never mix it into a Servlet `HttpSecurity` chain. In reactive contexts, read authentication from `ReactiveSecurityContextHolder` or argument resolvers instead of relying on a mutable global `ThreadLocal`.

**Never call `.block()` or manually `.subscribe()` inside a converter.** The `Mono` pipeline must be subscribed to and handled by Spring Security before the request proceeds. If lookup fails, never fabricate a default "guest/admin" principal.

## 13. Distinguishing Identity Linking from Tenant Authorization

After resolving:

~~~text
(iss, sub) -> internalUserId = usr-0042
~~~

you still cannot assume the user can read every order. Verify:

~~~text
Valid JWT access token
AND aud = orders-api
AND SCOPE_orders.read
AND internalUserId is linked
AND internalUser.enabled = true
AND internalUser is an active member of the requested tenant
AND resource.tenantId belongs to an allowed tenant
AND owner/assignment/role permits record access
~~~

Example:

| Internal User | Tenant | Role | Permissions |
| --- | --- | --- | --- |
| `usr-0042` | tenant A | Order admin | Can manage orders in A per policy |
| `usr-0042` | tenant B | Reader | Read-only per tenant B policy |
| `usr-1290` | tenant B | Member | No permissions in tenant A |

Never mint a **global** `ROLE_ORDER_ADMIN` from a role in tenant A and allow updates in tenant B. Scopes and roles must be **bound to their proper context**, while resource permissions are enforced in domain services/repositories.

### 13.1. A Request Tenant Selector Is Not Proof of Permission

~~~http
GET /api/tenants/tenant-B/orders/42
Authorization: Bearer <token-of-usr-0042>
X-Tenant-Id: tenant-B
~~~

`tenant-B` in the path/header is caller-chosen input. Verify `usr-0042`'s active membership in tenant B or use a trusted AS-verified active-tenant claim. Never rely merely on the header being sent.

### 13.2. Querying Data with internalUserId and Tenant

~~~sql
SELECT *
FROM orders
WHERE id = :orderId
  AND tenant_id = :authorizedTenantId
  AND owner_user_id = :internalUserId;
~~~

If the Orders API supports support staff, policy may add an assigned-support branch **while preserving the tenant boundary**. Never call `findById(id)` and inspect another tenant's data before checking authorization.

### 13.3. One User with Multiple External Identities

~~~text
Internal issuer + sub S1 -> internalUserId usr-0042
Partner issuer  + sub S2 -> internalUserId usr-0042
~~~

Both identities can link to the **same account** through an **authorized account linking workflow**. Business permissions are managed by internal user ID, avoiding duplicating ownership across every order when a user signs in via a second IdP.

This is completely different from finding two accounts with the same email and merging them automatically without verification.

## 14. Secure Account Linking: A Common Source of Account Takeover

Suppose Alice already has local account `usr-0042` via the internal IdP. Alice wants to sign in with a partner IdP. If the app simply does:

~~~text
newIdentity.email == existingUser.email
  -> auto-link new (iss, sub) to existingUser
~~~

an attacker may obtain an external identity returning the same email, or exploit a source with weaker email verification. **An email match must never be treated as proof of internal account ownership.**

### 14.1. Explicit Linking Workflow

A safer flow:

1. User **has authenticated to the current account** via a trusted mechanism, or completes re-authentication for sensitive operations.
2. User explicitly initiates **"Link another sign-in provider"**; the server creates a flow with `state`, PKCE/nonce per the OAuth/OIDC Client profile.
3. User completes authentication at the second IdP.
4. Server/Client verifies the response per OIDC/OAuth rules; extracts the **verified new issuer and subject**.
5. Server verifies the new `(iss, sub)` does not already belong to another user. If already linked, **never transfer ownership automatically**.
6. Server records the new link against the **protected session's exact internal user ID** using a transaction/unique constraint; logs audit events.
7. Notify the user, optionally requiring confirmation or MFA/re-authentication depending on risk level.

**This is an OAuth2/OIDC Client login/linking flow**, not a Resource Server blindly accepting an arbitrary JWT and creating links. An API acting as a Resource Server may expose account management endpoints, yet must restrict permissions and trust only verified authentications.

### 14.2. If the External Identity Is Already Linked to Another Account

Safe handling typically **rejects or routes to a controlled support workflow**, never auto-merging or overwriting accounts:

~~~text
issuer=partner, sub=S2 -> usr-1290 already exists
Logged-in user usr-0042 tries to link S2
=> CONFLICT / manual review, do not overwrite link
~~~

The unique constraint on `(issuer, subject)` also guards against race conditions from concurrent linking requests.

### 14.3. New Registration / Just-in-Time Provisioning

Some products need to auto-create an account when a user from a trusted AS signs in for the first time. This is **JIT provisioning**:

~~~text
Verified (iss, sub) not found
  -> check issuer/client/tenant and onboarding policy
  -> require invitation / eligibility / consent if needed
  -> create new internal_user with minimal default privileges
  -> record external_identity link inside a transaction
~~~

**Never automatically grant admin or tenant membership solely because a token contains an email, email domain, or unknown role string.** If the AS provides organization/membership claims, define an explicit provisioning contract; otherwise, leave new accounts pending/inactive until provisioning completes.

### 14.4. Deleted IdP Users and Reassigned `sub` Values?

The IdP contract must specify subject stability/non-reassignment. If an IdP **reuses `sub`**, stale identity link rows can point to the previous person's account. When onboarding an issuer, confirm **non-reassignment of subjects** per profile. If not guaranteed, require additional identifiers/proof and re-linking/verification workflows—never assume every `sub` is unconditionally immutable.

## 15. Issuer Migration: Never Rewrite Issuer/Subject Blindly

A system migrating from:

~~~text
https://old-id.example.test/realms/shop
~~~

to:

~~~text
https://new-id.example.test/realms/shop
~~~

cannot simply search-and-replace every `issuer` string in the database assuming old subjects still identify the same people. Some IdPs preserve subjects; others generate completely new subjects.

### 15.1. Controlled Migration Process

1. Verify old/new issuers and whether **subject mappings** are guaranteed consistent.
2. Obtain mappings from an authoritative administrative source, or require valid re-authentication/account linking.
3. Insert **new external identity rows** pointing to existing internalUserIds, preserving history/audits per policy.
4. Check unique constraints, account conflicts, and tenant memberships.
5. Update trust configuration for the new issuer; do not keep the old issuer active in production past the approved transition window.
6. Test both old/new tokens during the migration window; confirm untrusted issuers are rejected.
7. After migration, retire legacy links/issuers per policy without breaking owner IDs in business tables.

**Never rely solely on email to migrate mappings.** If email serves as a reconciliation hint, final decisions require proof and ownership verification.

### 15.2. Concurrent Multi-Issuer Support

An API can trust two issuers during a transition period. Each issuer must bind **issuer -> validator/JWKS/audience/profile**.

In Spring Security, use `JwtIssuerAuthenticationManagerResolver` or an allowlist-backed `AuthenticationManagerResolver<HttpServletRequest>`. Idea:

~~~java
// Pseudocode/version-dependent: trust only pre-registered issuers.
Set<String> trustedIssuers = Set.of(
    "https://old-id.example.test/realms/shop",
    "https://new-id.example.test/realms/shop");

// Resolver selects AuthenticationManager for an allowlisted issuer,
// never accepting an arbitrary issuer from the token.
~~~

**Never do:**

~~~java
// WRONG: read unverified iss and fetch JWKS from an attacker-chosen URL.
String jwksUri = unverifiedTokenIssuer + "/.well-known/jwks.json";
~~~

A rogue issuer can cause SSRF, acceptance of attacker keys, or identity confusion if the system blindly trusts whatever endpoint a token declares. **Issuers must be allowlisted and tokens verified using that exact issuer's keys/trust.**

### 15.3. Multi-Issuer + Same Subject Must Never Mix Accounts

Negative test:

~~~text
Issuer old + sub=123 -> internal usr-0042
Issuer new + sub=123 -> internal usr-1290
~~~

If the migration genuinely confirms both belong to the same person, link both to one internal ID under controlled rules. Otherwise, **never** merge them just because the subject strings match.

## 16. Deciding Whether Permissions Come from Tokens or Local Databases

Once the internal user ID is resolved, an application may draw permissions from two sources:

| Permission | Trustworthy Source | Characteristics |
| --- | --- | --- |
| `SCOPE_orders.read` | Verified access token | Operation types granted to the token; time-bounded |
| `ROLE_ORDER_SUPPORT` | Contracted token claim or local role DB | Requires allowlist/prefix mapping |
| Tenant membership | Local membership DB or AS-guaranteed custom claim | Can change after token issuance |
| Owner/assignment | Resource database | Bound per order |
| Account disabled | User management DB/IdP policy | May require rapid revocation |
| Platform-wide support override | Dedicated audited admin workflow | Never implicitly granted from a role string |

**Identity is not permission.** Merely having a valid `(iss, sub)` link does not grant `ROLE_ADMIN` or access across all tenants.

### 16.1. Scope Mapping Does Not Automatically Create Roles

Spring Security's `JwtGrantedAuthoritiesConverter` typically maps `scope`/`scp` into `SCOPE_...` authorities. Custom roles may need a separate converter.

~~~text
scope: orders.read orders.write
  -> SCOPE_orders.read
  -> SCOPE_orders.write
~~~

Role:

~~~text
ROLE_ORDER_SUPPORT
~~~

does not appear automatically unless the token carries the contracted claim/mapper. Never write `hasRole("ORDER_SUPPORT")` assuming an `orders.read` scope will satisfy it.

### 16.2. Tenant-Specific Roles Are Not Global Authorities

Alice may be a manager in tenant A yet only a viewer in tenant B. A global `ROLE_MANAGER` lacking tenant context can leak cross-tenant privileges. Grant global authorities only when truly global, and evaluate membership/tenant entitlements against the **tenant and resource being accessed**.

## 17. Error Classification: Invalid Token, Unlinked Identity, and Missing Permissions

| Scenario | Nature | Typical Response |
| --- | --- | --- |
| Missing Bearer token | Unauthenticated | 401, Bearer challenge |
| JWT bad signature/issuer/audience/expired | Token authentication failure | 401, possibly `invalid_token` |
| Inactive opaque token | Token authentication failure | 401 |
| Valid token yet unlinked local account | Linking/onboarding policy | 401 if link is an auth prerequisite; 403/onboarding flow if checked at app layer |
| Valid token, disabled local account | Account policy | 401/403 per enforcement point, grant no permissions |
| Valid token, linked account, missing `orders.read` | Authorization | 403, possibly `insufficient_scope` |
| Valid scope, valid account, not in tenant | Tenant policy | 403/404 per disclosure policy |
| Valid scope, in tenant, does not own order | Resource policy | 403/404 per contract |
| Identity DB unavailable when lookup is mandatory | Dependency failure | Fail closed; status per error handler, execute no business logic |

**Never use 401/403/404 as an oracle letting unverified users enumerate whether an email is registered.** On account-sensitive endpoints, consider generic messages and rate limiting.

### 17.1. Never Turn an Unlinked Identity into an Admin Account

Wrong:

~~~java
ExternalIdentity link = links
    .findByIssuerAndSubject(issuer, subject)
    .orElse(createDefaultAdminLink());
~~~

This is **fail open / privilege escalation**. If no link is found, handle per onboarding contract or deny—never auto-grant permissions.

### 17.2. Database Down Differs from Missing Link

~~~text
Lookup returns Optional.empty:
  -> no external identity link exists in current DB

Lookup throws timeout/connection exception:
  -> insufficient info due to dependency failure
~~~

Neither may allow unauthorized access when linking is mandatory. However, audits and metrics must distinguish them for incident response rather than reporting every timeout as "user does not exist."

## 18. Caching Identity Links and Revoking Access

Looking up `(iss, sub)` on every request has a cost; caching reduces load yet introduces risks of **stale identity mappings or statuses**.

| Concern | Policy to Define |
| --- | --- |
| Cache key | `(issuer, subject)` pair, plus environment/tenant context when needed |
| TTL | Bounded by acceptable stale identity/status window |
| Disabled accounts | Invalidate cache when locking users; never keep granting beyond SLA |
| Changed identity links | Invalidate old/new links and avoid races |
| Roles/memberships | Cache separately from identity or include appropriate policy version |
| AS key/token revocation | Caching identity **never replaces** token verification |
| Cache failure | Never fabricate accounts/roles when both cache and DB are unavailable |
| Storage | Protect PII/identifiers and avoid storing raw access tokens needlessly |

### 18.1. Caching by `sub` Alone Is a Bug

~~~java
@Cacheable(cacheNames = "identity", key = "#subject")
InternalUser resolve(String issuer, String subject) { ... }
~~~

If two issuers share a subject, cache keys collide and return the **wrong user**. A proper key must include **both canonical issuer and subject**:

~~~java
@Cacheable(
    cacheNames = "identity",
    key = "{#issuer, #subject}")
InternalUser resolve(String issuer, String subject) { ... }
~~~

This illustrates service-level caching; configure TTL and invalidation on the cache provider. If an account is disabled, caching an `InternalUser` indefinitely keeps returning the stale enabled user.

### 18.2. Never Cache Authentication Indefinitely

JWT signatures, expiry, issuer, and audience must still be checked along the security pipeline. Caching an identity link **does not** make an expired token valid and must never conflate tokens X and Y via an issuer-less cache entry.

### 18.3. Time-of-Check / Time-of-Use

If a converter confirms an account is enabled at T1, and tenant membership is revoked at T2 before an order update, sensitive operations may need a **permission check close to write time** or a transactional guard. A valid identity link at request start does not guarantee every entitlement remains valid through workflow completion.

## 19. Testing Identity Mapping Across Layers

Separate:

1. **Resolver/repository mapping unit tests** — from `(iss, sub)` to internal user.
2. **Spring Security HTTP authorization tests** — authentication and route policies given a principal.
3. **JWT/opaque protocol integration tests** — genuinely verified tokens from AS/JWKS/introspection.
4. **Account linking workflow tests** — preventing bad merges or concurrent link races.
5. **Tenant/resource policy tests** — valid links still cannot access unauthorized records.

### 19.1. Baseline Test Matrix

| Case | Issuer | Subject | Link State | Expected |
| --- | --- | --- | --- | --- |
| I01 | Internal | `alice-01` | Linked to enabled `usr-0042` | Resolves `usr-0042` |
| I02 | Partner | `alice-01` | Linked to enabled `usr-1290` | Resolves **`usr-1290`**, no mixing |
| I03 | Internal | `unknown` | No link | Unlinked/onboarding/deny per policy |
| I04 | Internal | `alice-01` | User disabled | Protected action blocked |
| I05 | Internal | `alice-01` | Link exists yet user record deleted/broken FK | Fail closed and flag integrity issue |
| I06 | Partner | `partner-alice` | Verified link to same `usr-0042` | Same internal ID |
| I07 | Untrusted issuer | `alice-01` | DB happens to have link | **Token from that issuer still rejected** |
| I08 | Internal | Bad-signature JWT with `sub=alice-01` | DB has link | Decoder rejects before lookup/authorization |
| I09 | Internal | JWT `aud=billing-api` | DB has link | Decoder/audience validator rejects |
| I10 | Internal | Expired token | DB has link | Not authenticated |
| I11 | Internal | User shares email with partner user | Two different subjects | **No auto-merge** |
| I12 | Internal | Same issuer+subject two concurrent link requests | Race | Unique constraint preserves single owner |
| I13 | Internal | Alice has role in tenant A | Requesting tenant B | Role A not honored in B |
| I14 | Internal | Client Credentials service token | No human-user link | Dedicated service policy |

**I02, I07, I08, and I11 are negative tests guarding the trust boundary.** Testing only a single happy-path issuer and user easily misses cross-issuer/cross-account bugs.

## 20. Unit Testing with JUnit and Mockito

Example standalone resolver:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;

@Service
public class ExternalAccountResolver {

    private final ExternalIdentityRepository identities;

    public ExternalAccountResolver(
            ExternalIdentityRepository identities) {
        this.identities = identities;
    }

    public UUID resolve(String verifiedIssuer,
                        String verifiedSubject) {
        if (verifiedIssuer == null || verifiedIssuer.isBlank()
                || verifiedSubject == null
                || verifiedSubject.isBlank()) {
            throw new IllegalArgumentException(
                "Verified identity is missing");
        }
        return identities
            .findByIssuerAndSubject(
                verifiedIssuer, verifiedSubject)
            .map(ExternalIdentity::getInternalUserId)
            .orElseThrow(UnlinkedIdentityException::new);
    }
}
~~~

`UnlinkedIdentityException` is a project custom exception. The parameter name `verifiedIssuer` emphasizes that **callers of the resolver must pass only already-verified identities**. A public resolver method taking two strings **does not verify JWTs itself**, so keep it behind protected service boundaries rather than exposing an endpoint accepting arbitrary user-supplied issuer/subject strings.

### 20.1. Testing Two Issuers Sharing a Subject

~~~java
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

import java.util.Optional;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class ExternalAccountResolverTest {

    private static final String ISSUER_SHOP =
        "https://identity.example.test/realms/shop";
    private static final String ISSUER_PARTNER =
        "https://login.partner.example.test/tenant/acme";

    @Test
    void sameSubjectFromDifferentIssuersMapsToDifferentUsers() {
        var repo = mock(ExternalIdentityRepository.class);

        UUID shopUser =
            UUID.fromString("11111111-1111-1111-1111-111111111111");
        UUID partnerUser =
            UUID.fromString("22222222-2222-2222-2222-222222222222");

        when(repo.findByIssuerAndSubject(
                ISSUER_SHOP, "shared-sub"))
            .thenReturn(Optional.of(new ExternalIdentity(
                ISSUER_SHOP, "shared-sub", shopUser)));

        when(repo.findByIssuerAndSubject(
                ISSUER_PARTNER, "shared-sub"))
            .thenReturn(Optional.of(new ExternalIdentity(
                ISSUER_PARTNER, "shared-sub", partnerUser)));

        var resolver = new ExternalAccountResolver(repo);

        assertEquals(shopUser,
            resolver.resolve(ISSUER_SHOP, "shared-sub"));
        assertEquals(partnerUser,
            resolver.resolve(ISSUER_PARTNER, "shared-sub"));
    }
}
~~~

This test shows **the same `sub` does not produce the same internal user** when issuers differ. It does not prove signed JWT validation; that belongs to integration tests.

### 20.2. Missing Identity Must Not Create a Default User

~~~java
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.mockito.Mockito.*;
import java.util.Optional;

@Test
void missingLinkMustNotBecomeAnotherUser() {
    var repo = mock(ExternalIdentityRepository.class);
    when(repo.findByIssuerAndSubject(
            ISSUER_SHOP, "unknown"))
        .thenReturn(Optional.empty());

    var resolver = new ExternalAccountResolver(repo);

    assertThrows(UnlinkedIdentityException.class,
        () -> resolver.resolve(ISSUER_SHOP, "unknown"));
}
~~~

This is a **test body** reusing the same class constants/imports as the prior example. When testing JIT provisioning logic, adjust expectations per provisioning policy while **never auto-linking to an existing user by email**.

### 20.3. Testing Against Blind Subject Normalization

~~~text
issuer=shop, sub=UserABC -> usr-0042
issuer=shop, sub=userabc -> usr-1290
~~~

If the issuer contract treats these two subjects as distinct, the resolver and database index must **preserve that distinction**. Use test fixtures with mixed casing, Unicode, or trailing characters matching your real AS schema to catch bad normalization.

## 21. Testing Spring Security with MockMvc and Simulated JWTs

`SecurityMockMvcRequestPostProcessors.jwt()` places a `JwtAuthenticationToken` onto the request without calling JWKS. It is very handy for testing code **after authentication**.

Example:

~~~java
import static org.springframework.security.test.web.servlet.request
        .SecurityMockMvcRequestPostProcessors.jwt;
import static org.springframework.test.web.servlet.request
        .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
        .MockMvcResultMatchers.status;

mockMvc.perform(get("/api/orders/42")
        .with(jwt().jwt(token -> token
            .issuer("https://identity.example.test/realms/shop")
            .subject("alice-01")
            .claim("scope", "orders.read"))
            .authorities(new SimpleGrantedAuthority(
                "SCOPE_orders.read"))))
    .andExpect(status().isOk());
~~~

This is a **test body** assuming a matching controller/service/data fixture, and represents a **simulated happy path**. It does not prove:

- `JwtDecoder` verifies JWS signatures.
- Issuer or audience is actually checked.
- A custom `JwtAuthenticationConverter` runs in the pipeline.
- JWKS rotation works.

`jwt()` can bypass converters/decoders by constructing `Authentication` directly. Thus, when testing **local identity lookup in a converter**, unit test the converter separately and write integration tests sending real JWTs in the Authorization header.

### 21.1. Unit Testing the Converter with Mock Repositories

A focused test:

~~~text
Input: Verified Jwt object
iss=shop, sub=alice-01, scope=orders.read
ExternalIdentityRepository: (shop,alice-01) -> usr-0042
InternalUserRepository: usr-0042 enabled
Expected JwtAuthenticationToken.getName() = UUID usr-0042
Expected getPrincipal() instanceof Jwt
Expected authorities contains SCOPE_orders.read
~~~

Negative cases:

~~~text
unlinked subject -> AuthenticationException
disabled account -> AuthenticationException
DB timeout -> no authenticated principal / fail closed
different issuer + same sub -> different lookup key, never resolves wrong user
~~~

**Never mock an unverified Jwt object and assume mapping is safe with real tokens.** In unit tests, `Jwt` is a fixture for testing post-decoder code; in production, only the authenticated pipeline may invoke the converter.

## 22. Integration Testing with Genuinely Signed JWTs and Mock JWKS

An end-to-end test should:

1. Generate an RSA/EC key pair **strictly for the test environment**; never reuse production private keys.
2. Configure a mock JWKS endpoint serving the test public key and `kid`.
3. Use a real `JwtDecoder`/Resource Server with issuer/audience validators.
4. Issue genuinely signed JWTs with contract-compliant claims.
5. Send `Authorization: Bearer <signed-jwt>` to the HTTP endpoint via MockMvc or a real HTTP client.
6. Verify the converter/service uses the **verified `(iss, sub)`**, returning the right `internalUserId` and resource data.
7. Create another token with the **same `sub` yet another allowlisted issuer** (signed with its corresponding key) and confirm it maps to a different account.
8. Create tokens with untrusted issuers, wrong audiences, bad signatures, or expired lifetimes—all must be **rejected at authentication before business policies**.

### 22.1. Testing Against `iss` Claim Spoofing

Do not merely swap `iss` inside a `Jwt` fixture. A more valuable negative test:

~~~text
JWT declares iss = trusted-shop-issuer
Yet is signed by an attacker/other issuer key
-> JwtDecoder must reject
-> ExternalAccountResolver must never treat the JWT as account proof
~~~

If the API is multi-issuer, test route selection and the allowlist: an issuer outside the trusted set **must never cause the API to fetch arbitrary JWKS** based on a caller-controlled payload.

### 22.2. Opaque Introspection Integration Test

Mock Authorization Server returns:

~~~json
{
  "active": true,
  "iss": "https://identity.example.test/realms/shop",
  "sub": "alice-01",
  "aud": ["orders-api"],
  "scope": "orders.read"
}
~~~

The Resource Server must use trusted endpoints/credentials, parse metadata accurately, and map to the internal ID. Negative cases:

- `active:false` -> not authenticated.
- `active:true` yet different audience -> rejected.
- Missing `iss` when required by contract -> rejected.
- `iss` from an untrusted issuer -> rejected.
- Unlinked `sub` -> handled per account policy.
- Endpoint timeout -> never fail open.

**Never treat `username` from introspection as `sub`** unless the AS explicitly defines them as equivalent. Account mapping requires stable subjects and issuer binding.

## 23. Safe Unit/Integration Testing for Account Linking

A linking flow must test both success and conflict cases:

| Case | Currently Logged-In Account | New External Identity | Expected |
| --- | --- | --- | --- |
| L1 | usr-0042 | Unlinked `(partner,S2)` | New link created after complete verification flow |
| L2 | usr-0042 | `(partner,S2)` already owned by usr-1290 | Rejected, link not transferred |
| L3 | usr-0042 | New token fails issuer/audience/profile | No link created |
| L4 | usr-0042 | Same email yet different `(iss,sub)` | No auto-link by email |
| L5 | No authenticated current account | Request to link into usr-0042 | Disallowed |
| L6 | Two requests create same `(iss,sub)` | Race | Unique constraint preserves single owner |
| L7 | Disabled user account | Attempts to add IdP | Rejected per account policy |
| L8 | External identity link revoked | Old token still unexpired | Invalidation/revocation rules apply |
| L9 | User moves issuers via migration | New verified `(iss,sub)` | Preserves internal ID after controlled mapping |

### 23.1. Race Conditions Must Be Tested on a Real Database

Unit tests can mock repositories, yet **only transaction/unique-index integration tests** prove two concurrent linking requests cannot create two owners for one external identity. On catching a unique constraint violation, return a safe conflict without overwriting existing IDs.

### 23.2. Preventing Linking Callback Replay

OAuth2/OIDC linking callbacks must verify `state`, flow-specific PKCE/nonce, redirect URI, initiating user session, and single-use binding. Never allow an attacker to replay a callback or swap account context between initiating and completing a link to bind an identity to another user.

## 24. Multi-Tenancy and Identity Resolution

One internal user can belong to multiple tenants:

~~~text
(iss, sub) -> usr-0042
usr-0042 -> tenant A: MANAGER
usr-0042 -> tenant B: VIEWER
~~~

Internal identity mapping answers "**who**," while tenant authorization answers "**what they may do in which organization**."

Never write:

~~~java
// WRONG: belonging to tenant A grants no permission in tenant B.
if (userId != null) {
    return orderRepository.findById(orderId);
}
~~~

Instead, the service must determine the verified tenant context, verify membership/role in that tenant, and query:

~~~sql
SELECT *
FROM orders
WHERE id = :orderId
  AND tenant_id = :allowedTenant
  AND owner_user_id = :internalUserId;
~~~

For support/managers, the owner condition may swap for an assignment policy while **preserving the tenant boundary**. Test a token for `usr-0042` used in tenant A trying to read order B; a valid internal ID **must never conjure up tenant B permissions**.

### 24.1. Tenant Claims in JWTs Are Contract-Specific Custom Claims

`tenant_id` is not a mandatory OAuth2/OIDC access token claim. If the AS issues tokens with an active tenant, the API can use that claim after verification while still checking tenant ownership on resources. If a user holds multiple memberships, dynamic lookup may be required. Never trust raw `X-Tenant-Id` headers as proof of membership.

### 24.2. Access Revocation Can Be Faster Than Token Expiry

An access token may have 20 minutes remaining while the user is locked out or removed from a tenant after 1 minute. If business requirements demand near-instant revocation, relying solely on JWTs and long membership caches may fall short. Use TTLs, revocation, dynamic lookups, or shorter token lifetimes aligned with SLAs—never assume unexpired tokens always hold valid permissions.

## 25. OIDC-Specific Concerns: ID Token, UserInfo, and External Profiles

### 25.1. Do Not Use ID Tokens as Resource Server Credentials

OIDC ID tokens are meant for the **OIDC Client** and typically carry the Client ID as `aud`. The Orders API must never accept an ID token in place of an OAuth access token when `aud` does not target the Orders API, even if the ID token has a valid signature and matching `sub`.

### 25.2. UserInfo Is Not a Replacement for Access-Token Authentication

An OIDC Client can call the UserInfo endpoint to retrieve profile claims per protocol. A Resource Server **does not call UserInfo on every request by default** to verify Bearer access tokens, because:

- Access tokens must be verified against the Resource Server contract.
- UserInfo returns user claims per OIDC scopes/profiles, not authorization bindings for the Orders API.
- UserInfo results and ID token subjects follow separate matching rules for OIDC Clients.
- Emails/profiles can change and never replace `(iss, sub)` as an identity key.

If profile synchronization is needed, design a trusted profile-sync workflow with consent/privacy controls rather than using profile attributes as automatic evidence to merge accounts.

### 25.3. ID Token Subject vs. Access Token Subject

In an OIDC deployment, `sub` may represent the same user, yet token structures and subject policies can differ by Client, grant, or privacy profile. The Resource Server may only use **`sub` from the access token it verified**, backed by an AS contract defining claim semantics. Never read `sub` from a separate ID token in the browser to decide resource ownership.

## 26. Privacy and Auditing

External identity links are sensitive data because they connect external identities to internal accounts. Operational systems should:

- Restrict read/write access on links strictly to responsible services and authorized admins.
- Never store raw access tokens/refresh tokens solely for identity lookup.
- Avoid exposing raw `(issuer, subject, internalUserId)` tables publicly to Clients.
- Audit link/unlink/migration actions, initiators, and outcomes with minimal data.
- Support account deletion, unlinking, transaction history, and legal requirements per organizational policy.
- Never use `email` or `sub` as unbounded-cardinality metric labels.
- Distinguish **unverified** token data from claims returned by trusted decoders before logging security events.

### 26.1. Logout Does Not Automatically Delete External Identities

Logging out of a session/OAuth Client or revoking an access token **does not delete an account link**; account links are durable relationships per policy. Conversely, unlinking an external identity does not automatically revoke already-issued access tokens; if immediate blocking is required, the API must check live links or invalidate relevant caches.

### 26.2. Deleting a Link Must Never Let Someone "Reclaim" Another Account

After unlinking, if the same external identity signs in again, never pick a user automatically by email or recent usage. Require a fresh verified onboarding/linking flow; if special unique-key/reassignment policies apply, require auditing and clear governance.

## 27. Common Misconceptions

**"`sub` is globally unique across the entire Internet."** False. It has meaning within the issuer namespace per contract, which is why `(iss, sub)` is required.

**"Two issuers emitting the same `sub` mean the same person."** False. They can be two completely different users.

**"Two external identities with the same email always belong to the same person."** False. Emails are mutable/reusable and depend on verification policies.

**"`email_verified: true` allows auto-merging any accounts."** No. It is neither user consent nor proof of account ownership at another issuer.

**"`preferred_username` is more stable than `sub`."** Not by default. Usernames often change or collide.

**"`Authentication.getName()` is always the internal user ID."** No. JWT defaults usually use `sub`; it becomes an internal ID only with an explicit converter mapping.

**"Changing `getName()` turns `getPrincipal()` into a domain User."** Not with `JwtAuthenticationToken(jwt, authorities, name)`; the principal remains `Jwt`.

**"Finding a link grants admin permissions."** False. Identity mapping and authorization are two separate layers.

**"A validly signed token from Issuer A works on every API."** False. Audience, purpose, timestamps, and contracted validators must still be checked.

**"JWT payloads can be decoded first and signatures verified later."** Unverified claims must never be used to establish identity or permissions.

**"Opaque tokens always include `iss`/`sub`."** No. Introspection responses depend on the AS contract.

**"Multi-issuer just means adding issuers to a list; all roles and keys can be shared."** No. Each issuer needs appropriate trust, claim semantics, and authority mappings.

**"Changing an issuer URL just means find-and-replacing text in `external_identities`."** No. Subject mappings and ownership must be verified during migration.

**"An unexpired JWT guarantees the local account is enabled."** No. Accounts can be locked or memberships revoked after token issuance.

**"Caching by `subject` alone is enough."** No. Omitting the issuer causes identity collisions; caches also need TTL/invalidation.

**"A user with a valid internal ID can read every tenant."** No. Tenant/owner/resource policies must still be enforced.

**"Client Credentials tokens are human users because they have `sub`."** Not by default. A separate service principal policy is required.

**"Passing a MockMvc `jwt()` test proves signed JWTs and the decoder work."** No. `jwt()` usually builds a mock Authentication; signed JWT integration tests are required.

**"Wrapping a JPA repository in `Mono.just` inside a reactive converter makes it non-blocking."** No. Blocking I/O still blocks; use a reactive driver or isolate legacy blocking code per policy.

## 28. Design and Issuer Integration Checklist

1. Which Authorization Servers are trusted? Where do canonical issuers and JWKS/introspection endpoints come from?
2. Which `iss`, `sub`, `aud`, lifetime, and token type/profile contracts apply to access tokens?
3. Does `JwtDecoder`/introspection verify the token before any lookup runs?
4. Does the identity key use **`(iss, sub)`** with a unique constraint?
5. Have you avoided using email/username as account keys or for auto-merging?
6. Are subjects guaranteed stable/non-reassignable by the issuer's profile?
7. Does the IdP use pairwise subjects, multi-client subjects, or special account migrations?
8. Does the external identity table have an FK to the internal user ID and linking audits?
9. If one internal account can link multiple identities, do link/unlink flows enforce proper re-auth/consent?
10. When no link is found, should it onboard, return 401, or return 403? Is there an explicit contract?
11. Within what SLA must disabled accounts and revoked memberships take effect?
12. Is lookup needed at authentication time or only when business operations require it?
13. Does Servlet JPA lookup have latency/availability/cache policies? Is WebFlux non-blocking?
14. Do service/Client Credentials tokens have a dedicated principal/permission policy?
15. Are multi-issuer configs allowlisted without fetching arbitrary JWKS from unverified claims?
16. Are tenant-scoped roles and object-level authorization enforced independently of identity links?
17. Are caches keyed by issuer+subject with invalidation on link/status changes?
18. Does the API avoid overly logging raw Bearer tokens, emails/subjects, or linked identities?
19. Do tests cover same-subject/different-issuer, same-email/different-subjects, missing links, disabled users, and migration conflicts?
20. Do signed-JWT/introspection integration tests prove the decoder genuinely verifies tokens?

## 29. Scenario Exercises

**Scenario A.** Shop IdP issues `iss=shop`, `sub=123`; Partner IdP issues `iss=partner`, `sub=123`. Should both automatically map to one internal user?

**No.** `sub` only has meaning within an issuer namespace. Two distinct external identity keys are needed, and they may share an internal user only after a verified linking flow.

**Scenario B.** Alice changes her email from `alice@old.example` to `alice@new.example` while `(iss, sub)` stays unchanged. Must a new internal account be created?

**Normally no.** The internal identity link still points to the existing account; email is a profile attribute updated per policy.

**Scenario C.** Carol has the same verified email as Alice at another IdP. The system auto-merges Carol into Alice's account. What went wrong?

**Account linking lacked proof of account ownership**, risking account takeover. Never auto-link solely by email, even with `email_verified`.

**Scenario D.** A JWT has `iss=trusted-shop` and `sub=alice` yet an invalid signature. The database has an identity link for Alice. Should `Authentication` be created?

**No.** Tokens must pass the decoder/JWS/validators. An existing identity link never makes a forged JWT valid.

**Scenario E.** Orders API sets `JwtAuthenticationToken`'s name to the internal ID. Does a controller with `@AuthenticationPrincipal Jwt jwt` automatically receive `InternalUser`?

**No.** The principal remains `Jwt`; only `getName()` changes. To obtain a domain user, use a service lookup or a dedicated authentication subtype.

**Scenario F.** A JWT is valid and the account link exists, yet the local user is disabled. Should it be accepted because the token is unexpired?

**No** if API policy requires an active local user. Check account status and handle cache/revocation appropriately.

**Scenario G.** A JWT is valid and internal user `usr-0042` holds ADMIN in tenant A, yet requests an order in tenant B. Is it authorized?

**Not by default.** Account identity does not carry tenant A's roles into tenant B; context-specific tenant membership/resource policies are required.

**Scenario H.** A Resource Server uses opaque introspection and receives only `active:true`, `scope`, and `client_id`, with no `sub` or issuer binding. Can `client_id` serve as the user ID?

**No.** `client_id` is an OAuth Client identifier. A subject and issuer contract is required before mapping human users; service tokens must follow a separate policy.

**Scenario I.** A developer wraps a JPA repository inside `Mono.just(repository.findByIssuerAndSubject(...))` and calls it from a WebFlux JWT converter. Is this non-blocking?

**No.** The blocking repository executes before the `Mono` is even constructed. Use a reactive repository or controlled blocking-I/O isolation.

**Scenario J.** During migration, the new issuer issues the same `sub` as the old issuer. Can we simply update `issuer` in the DB without verifying users?

**No.** Subjects across two issuers are not guaranteed to be the same identity. You need an attested mapping or account linking/re-auth, then add new links in a controlled manner.

**Scenario K.** A resolver unit test passes for `(iss,sub)`, yet production returns 401 due to a disallowed issuer claim. Is the unit test wrong?

**Not necessarily.** Unit tests only test mapping; decoder/integration tests must verify valid issuer/JWKS/audience before the resolver runs. Never weaken validators "just to let the resolver run."

**Scenario L.** A user holds two access tokens with different `scope`s yet the same `(iss,sub)`. Can the identity cache automatically grant scopes from the older token?

**No.** Both tokens may map to the same internal user ID, yet **authorities on each request must come from the current token/policy**, never pulled incorrectly from an identity cache.

---

## Conclusion

When integrating an issuer into a **Spring Security OAuth 2.0/OIDC Resource Server**, the durable approach is verifying the access token **first**, then using the **trusted issuer and subject** as the **`(iss, sub)`** link key to an **internal user ID**. Never use email, username, Client ID, or raw tokens as internal user keys; two issuers can issue identical subjects, while one internal user can link multiple external identities through a **controlled account linking** workflow.

In Spring Security Servlet, perform lookups in a **service** when business operations need them, or in **`JwtAuthenticationConverter`** when every protected request strictly requires a local account. In WebFlux, lookups must run inside **non-blocking `Mono`/`Flux`** pipelines without calling `.block()` or synchronous JPA on the event loop. After mapping, `Authentication.getName()` may hold the internal ID while the principal remains `Jwt`; **identity resolution never replaces scopes, roles, tenant membership, and resource-level authorization**.

To prevent account takeover and cross-issuer confusion, enforce a **unique `(issuer, subject)` constraint, avoid auto-merging by email, allowlist issuers/JWKS, govern migrations/links/unlinks, fail closed when proof is missing**, and test across layers: mapping unit tests, account-linking concurrency, HTTP authorization, plus **signed-JWT or introspection integration tests**. **A valid token proves an external identity; only internal policy decides which account that external identity maps to and what it is permitted to do.**