# 31.12. Testing Provider Isolation, Tenant Isolation, and Account Linking

## 1. Why Testing Successful Login Is Still Not Enough

A **Spring Security OAuth 2.0 OIDC Client** application may support logging in with corporate accounts, partner accounts, and multiple OpenID Providers (OPs). At the same time, a single person can belong to multiple **tenants** (organizations/customers), and a single internal application account can be **linked to multiple external identities**.

Testing that "user A logs in with provider X and gets HTTP 200" only proves one branch works. It **does not prove** that:

- A user from provider X cannot view data meant only for provider Y.
- Two providers issuing the same `sub` or email are not accidentally merged into one internal account.
- A user in tenant Alpha cannot guess an ID to read or enable features in tenant Beta.
- A successful OAuth2 callback cannot be abused to **attach an attacker's identity to a victim's account**.
- A token from provider A is not accidentally stored in provider B's authorized-client store.
- An `admin` privilege from an external OP does not automatically become `ROLE_ADMIN` in the application.
- A logout, revocation, or refresh for user A does not alter user B's connection.
- Two browser tabs linking an identity concurrently cannot trigger a race condition or misassign ownership.

**Goal of this lesson:** build an integration testing suite that can prove **identity isolation, tenant isolation, token isolation, and account-linking safety** across multiple layers: database, Spring Security, authorization services, the OAuth2/OIDC protocol, HTTP requests, and asynchronous flows.

### 1.1. Example Risk

~~~text
OpenID Provider A
  issuer = https://id.alpha.example.test
  sub    = 12345
  email  = alex@example.test

OpenID Provider B
  issuer = https://id.beta.example.test
  sub    = 12345
  email  = alex@example.test

Application stores:
  external_user_id = "12345"

=> Two unrelated identities may be merged by mistake.
~~~

The root cause is not an OAuth2 code exchange failure, but the application **failing to preserve the issuer boundary when mapping identities**.

### 1.2. Overall Architecture Diagram

~~~mermaid
flowchart TD
    A["Browser / BFF / RP"] --> B["Spring Security OAuth2/OIDC Login"]
    B --> C["ClientRegistration A"]
    B --> D["ClientRegistration B"]
    C --> E["Issuer A, ID Token A"]
    D --> F["Issuer B, ID Token B"]
    E --> G["Trusted identity normalization"]
    F --> G
    G --> H["External identity: issuer + subject"]
    H --> I["Internal account"]
    I --> J["Tenant membership + role policy"]
    J --> K["Tenant-scoped repositories / APIs"]
    B --> L["Authorized Client Store"]
    L --> M["Token scoped by registration + principal"]
    I --> N["Account Linking Workflow"]
    N --> H
~~~

**Note:** Never treat an email address, `preferred_username`, raw `sub`, or `tid` claim as global proof that two identities belong to the same person.

## 2. Distinguishing Four Security Boundaries

| Boundary | Key / Scope | Question to Test |
| --- | --- | --- |
| **Provider/issuer** | OP issuer, client registration, keys | Could an ID Token from issuer A be accepted under registration B? |
| **External identity** | Verified `(issuer, subject)` | Could two users with the same `sub`/email at two OPs be merged? |
| **Tenant** | Tenant ID and internal membership | Does the user have permission for the exact current tenant and resource? |
| **OAuth2 connection** | Registration, principal, client, token audience | Could an Access/Refresh Token be used, deleted, or refreshed cross-context? |

A complete authorization decision may require all four:

~~~text
verified OIDC issuer + subject
             |
             v
internal account
             |
             v
membership in requested tenant
             |
             v
role/permission inside that tenant
             |
             v
resource belongs to that tenant
             |
             v
ALLOW or DENY
~~~

Checking only `ROLE_REPORT_VIEWER` while skipping the report's owning tenant still leaves **IDOR/BOLA** (Insecure Direct Object Reference / Broken Object Level Authorization).

### 2.1. Provider Is Not Tenant

One provider can serve multiple tenants; one tenant can allow logins from multiple providers. Therefore:

~~~text
provider != tenant
registrationId != tenantId
sub != internalAccountId
email != identity key
issuer != API authorization scope
~~~

Do not write a rule like `"registrationId=company => tenant=company"` unless the product has a trusted, explicitly verified mapping.

## 3. Security Invariants to Prove

Before writing tests, express requirements as **security invariants**:

1. **I1 — Trusted issuer:** only accept identities from properly configured OP/registrations with ID Tokens verified against issuer and client.
2. **I2 — Stable identity:** an external identity is keyed by issuer + subject, never by email or raw subject alone.
3. **I3 — Explicit linking:** account linking requires explicit intent, an already authenticated current session, and fresh protocol completion; never auto-merge on matching email.
4. **I4 — Uniqueness:** one external identity cannot be linked to two internal accounts simultaneously if the domain enforces single ownership.
5. **I5 — Tenant membership:** the requested tenant must be verified server-side against the internal account.
6. **I6 — Resource ownership:** the resource belongs to the target tenant; never trust only the tenant in a URL/header.
7. **I7 — Authorization least privilege:** roles/scopes/claims from one OP do not automatically carry equivalent privileges on another OP.
8. **I8 — Token isolation:** an authorized client must stay bound to the exact client registration, principal, and storage context.
9. **I9 — Session binding:** callback/link attempts bind to the right browser/session, `state`/`nonce`/PKCE, and cannot be replayed.
10. **I10 — Fail closed:** issuer mismatch, tenant ambiguity, missing membership, link collision, or provider errors must never degrade into granted access.
11. **I11 — Atomic updates:** concurrent link/unlink/refresh operations never create duplicate mappings or lose newer tokens.
12. **I12 — Audit/privacy:** link/unlink/denied events are logged safely without leaking tokens, codes, or session cookies.

These invariants should be verified with both **positive tests and negative tests**. A test that only checks for HTTP 200 never proves isolation.

## 4. Test Levels: What Does Each Tool Prove?

| Level | Tool | What It Proves | What It Does Not Prove |
| --- | --- | --- | --- |
| Unit | JUnit + fake repositories | Identity normalization, policies, state machines | OIDC protocol, HTTP filters |
| Spring Security controller | MockMvc + `oidcLogin()` | Route/method security and in-app principal mapping | ID Token signature, authorization code, OP callback |
| Reactive controller | WebTestClient + `mockOidcLogin()` | WebFlux chain, Reactor context, route authorization | Real Token Endpoint/JWKS |
| Repository integration | Testcontainers PostgreSQL | Unique constraints, transactions, concurrent inserts | OIDC `state`/`nonce` |
| Mock OP integration | WireMock/MockWebServer/test OIDC server | Discovery, callback, code/PKCE, token validation, UserInfo | Production provider behavior |
| Browser E2E | Playwright/Selenium + test OP | Cookies, redirects, SameSite, state/session binding | All production tenant policies |
| Contract sandbox | Provider test tenant/clients | Real OP semantics, supported claims/scopes | Full incident behavior |
| Load/race tests | Controlled parallel requests | Atomic linking, token refresh consistency | Security if the real OP is compromised |

**`oidcLogin()` and `mockOidcLogin()` do not issue ID Tokens via a real Token Endpoint**. They supply a mock principal for Spring Security tests—very useful, but no substitute for integration tests verifying signatures, `iss`/`aud`, PKCE, and `state`.

## 5. Designing Fixtures That Deliberately Create Collisions

To uncover isolation bugs, **do not give every test user a distinct email and `sub`**. Intentionally use colliding values:

| Fixture | Issuer | Subject | Email | Tenant Memberships |
| --- | --- | --- | --- | --- |
| Alice-A | issuer A | `shared-100` | `alex@example.test` | Alpha |
| Bob-B | issuer B | `shared-100` | `alex@example.test` | Beta |
| Carol-A | issuer A | `carol-200` | `carol@example.test` | Alpha + Beta |
| Dave-A | issuer A | `dave-300` | `dave@example.test` | None |
| Admin-B | issuer B | `admin-400` | `admin@example.test` | Beta admin |
| Duplicate-A | issuer A | `shared-100` | `new-email@example.test` | Same identity as Alice |

### 5.1. Test Tenants

~~~text
Tenant Alpha: tenant_id = t-alpha
  report_id = report-001
  provider registrations allowed = corp-alpha, partner

Tenant Beta: tenant_id = t-beta
  report_id = report-002
  provider registrations allowed = corp-beta, partner

Internal account alice:
  external identity (issuer A, shared-100)
  membership Alpha, role REPORT_VIEWER

Internal account bob:
  external identity (issuer B, shared-100)
  membership Beta, role REPORT_VIEWER
~~~

If a collision exists, the test immediately catches Alice viewing Bob's content or the account mapping being overwritten.

### 5.2. Two Issuers with Distinct Client IDs and Signing Keys

~~~text
OP A issuer    = https://id-a.example.test
OP A client_id = portal-a
OP A JWKS      = key-a

OP B issuer    = https://id-b.example.test
OP B client_id = portal-b
OP B JWKS      = key-b
~~~

When testing with mock OPs, generate **two distinct test keypairs**; never share one signing key and mask issuer/JWKS mix-up bugs.

## 6. Configuring Multiple Spring Boot Registrations

~~~yaml
spring:
  security:
    oauth2:
      client:
        registration:
          corp-alpha:
            provider: op-alpha
            client-id: ${ALPHA_OIDC_CLIENT_ID}
            client-secret: ${ALPHA_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile, email]
          corp-beta:
            provider: op-beta
            client-id: ${BETA_OIDC_CLIENT_ID}
            client-secret: ${BETA_OIDC_CLIENT_SECRET}
            client-authentication-method: client_secret_basic
            authorization-grant-type: authorization_code
            redirect-uri: "{baseUrl}/login/oauth2/code/{registrationId}"
            scope: [openid, profile]
        provider:
          op-alpha:
            issuer-uri: https://id-a.example.test
          op-beta:
            issuer-uri: https://id-b.example.test
~~~

These URIs and environment variables are **examples only**, not real OPs. Each client needs its registered redirect URI, client authentication method, and scopes.

### 6.1. Configuration Checks to Test

- `/oauth2/authorization/corp-alpha` uses only issuer A's config.
- `/oauth2/authorization/corp-beta` uses only issuer B's config.
- Callback `/login/oauth2/code/corp-alpha` is never processed with registration B.
- OP issuer A is never unintentionally pointed at OP B's JWKS URL.
- A bad client ID or secret on registration A does not break flow B when infrastructure is independent.
- Registration IDs come from a server allowlist, not an arbitrary `issuer` query parameter.

## 7. Designing an Accurate External Identity Key

A simple Java model:

~~~java
package com.example.identity;

import java.util.Objects;

public record ExternalIdentityKey(
        String issuer,
        String subject) {

    public ExternalIdentityKey {
        Objects.requireNonNull(issuer, "issuer");
        Objects.requireNonNull(subject, "subject");
        if (issuer.isBlank() || subject.isBlank()) {
            throw new IllegalArgumentException("Empty OIDC identity key");
        }
    }
}
~~~

`issuer` must come from the **verified ID Token**, e.g. `oidcUser.getIdToken().getIssuer()`, and `subject` is the `sub` issued by the OP for the RP. Never take them from a browser-supplied `X-User-Id` header or query parameter.

### 7.1. Positive/Negative Unit Tests

~~~java
import static org.junit.jupiter.api.Assertions.*;
import org.junit.jupiter.api.Test;

class ExternalIdentityKeyTest {

    @Test
    void sameSubjectDifferentIssuerMustRemainDifferent() {
        ExternalIdentityKey a =
            new ExternalIdentityKey("https://id-a.example.test", "shared-100");
        ExternalIdentityKey b =
            new ExternalIdentityKey("https://id-b.example.test", "shared-100");

        assertNotEquals(a, b);
    }

    @Test
    void sameIssuerAndSubjectStaySameWhenEmailChanges() {
        ExternalIdentityKey first =
            new ExternalIdentityKey("https://id-a.example.test", "shared-100");
        ExternalIdentityKey second =
            new ExternalIdentityKey("https://id-a.example.test", "shared-100");

        assertEquals(first, second);
    }
}
~~~

These are unit tests for **key semantics**; they do not prove the issuer was verified. Testing trust requires integration tests with the Token Endpoint and JWKS.

### 7.2. Pairwise Subjects

An OP may issue different `sub` values for the same person across different clients/sectors:

~~~text
Portal client: issuer A, sub pairwise-123
Mobile client: issuer A, sub pairwise-789
~~~

Do not auto-merge by email. When the product needs cross-client identity linking, use an explicit workflow and provider-approved identifiers/correlation. Test both directions: **no auto-merge**, yet a legitimate user can **explicitly link** after proving ownership of both identities.

## 8. Database Schema: Unique Identities, Separate Accounts and Tenants

An illustrative data model:

~~~sql
CREATE TABLE internal_account (
    id UUID PRIMARY KEY,
    status VARCHAR(20) NOT NULL
);

CREATE TABLE external_identity (
    id UUID PRIMARY KEY,
    account_id UUID NOT NULL REFERENCES internal_account(id),
    issuer VARCHAR(512) NOT NULL,
    subject VARCHAR(512) NOT NULL,
    registration_id VARCHAR(100) NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE NOT NULL,
    CONSTRAINT uq_external_identity UNIQUE (issuer, subject)
);

CREATE TABLE tenant_membership (
    account_id UUID NOT NULL REFERENCES internal_account(id),
    tenant_id UUID NOT NULL,
    role VARCHAR(100) NOT NULL,
    status VARCHAR(20) NOT NULL,
    PRIMARY KEY (account_id, tenant_id)
);

CREATE TABLE report (
    id UUID PRIMARY KEY,
    tenant_id UUID NOT NULL,
    title VARCHAR(200) NOT NULL
);
~~~

This is an illustrative PostgreSQL-oriented schema omitting migrations, versioning, indexes, auditing, and soft-delete. If a product intentionally allows one external identity across multiple internal accounts or per-tenant accounts, **explicitly design a different invariant/unique constraint**; never drop the constraint without an equivalent enforced rule.

### 8.1. Why Not Unique by Email?

~~~sql
-- ANTI-PATTERN for multi-issuer identity:
CREATE UNIQUE INDEX uq_external_email
ON external_identity(email);
~~~

Emails can change, be recycled, go unverified, or collide across issuers. Never use email as the global OIDC identifier key.

### 8.2. Testing Constraints Against a Real Database

~~~java
@Test
void identicalIssuerAndSubjectCannotLinkToTwoAccounts() {
    identityRepository.insert(
        accountAlice, "https://id-a.example.test", "shared-100");

    assertThrows(DataIntegrityViolationException.class,
        () -> identityRepository.insert(
            accountBob, "https://id-a.example.test", "shared-100"));
}
~~~

This is a **test fragment**: it assumes the repository runs against a real database where unique constraint violations translate to `DataIntegrityViolationException`. Test against real Testcontainers PostgreSQL/JDBC/R2DBC rather than only in-memory fakes.

### 8.3. Multiple Tenants Mean Memberships, Not Swapping User IDs

One internal account can belong to both Alpha and Beta with different roles. The identity key does not change when switching tenants:

~~~text
identity (issuer A, sub carol-200)
    -> internal account Carol
         -> membership Alpha (REPORT_VIEWER)
         -> membership Beta  (BILLING_READER)
~~~

Switching the active tenant must **re-run authorization checks**, never reusing Alpha's cached role to authorize actions in Beta.

## 9. Deriving `TenantContext` from Trusted Sources

An application might receive the tenant in the path:

~~~http
GET /tenants/t-beta/reports/report-002
~~~

`t-beta` in the URL is only the **requested tenant**; it does not prove the caller is allowed to access that tenant.

### 9.1. Authorization Rule

~~~text
Verified Authentication
        |
        v
Resolve internal account by issuer + subject
        |
        v
Verify tenant membership / account status
        |
        v
Verify required role inside requested tenant
        |
        v
Verify report.tenant_id == requested tenant
        |
        v
Return report
~~~

### 9.2. Illustrative Policy Interface

~~~java
package com.example.security;

import java.util.UUID;
import reactor.core.publisher.Mono;

public interface TenantAuthorization {

    Mono<Void> requireMembership(
        UUID internalAccountId, UUID tenantId);

    Mono<Void> requireRole(
        UUID internalAccountId, UUID tenantId, String role);
}
~~~

`Mono<Void>` **completes** when authorized and emits `AccessDeniedException` when denied. If a service returns `Mono<Boolean>`, callers must explicitly verify `true`/`false` before proceeding.

### 9.3. Do Not Blindly Trust `X-Tenant-Id` Headers

If a gateway or trusted reverse proxy injects a tenant header, the backend must still enforce its trust boundary and verify identity/membership. Headers set directly by Internet callers are never proof of access.

## 10. Testing Object-Level Authorization, Not Just Tenant-Level

An illustrative service:

~~~java
package com.example.report;

import java.util.UUID;
import reactor.core.publisher.Mono;

public class ReportService {
    private final TenantAuthorization authorization;
    private final ReactiveReportRepository reports;

    public Mono<Report> getReport(
            UUID accountId, UUID requestedTenant, UUID reportId) {

        return authorization
            .requireRole(accountId, requestedTenant, "REPORT_VIEWER")
            .then(reports.findByIdAndTenantId(reportId, requestedTenant))
            .switchIfEmpty(Mono.error(
                new org.springframework.security.access.AccessDeniedException(
                    "Report unavailable")));
    }
}
~~~

This fragment assumes `Report`, `ReactiveReportRepository`, and constructor dependencies are provided. The crucial piece is querying the repository by **both report ID and tenant ID**, not calling `findById(reportId)` and relying on the frontend hiding buttons.

### 10.1. Required Test Cases

| Case | Membership | Report Owner | Outcome |
| --- | --- | --- | --- |
| Alice views Alpha report | Alpha | Alpha | 200 when role is held |
| Alice views Beta report | Alpha | Beta | 403 or 404 per policy |
| Carol selects Beta with right role | Alpha + Beta | Beta | 200 |
| Carol selects Beta using Alpha role | Only Alpha role | Beta | Deny |
| Dave has valid token but no membership | None | Alpha | Deny |
| User swaps path tenant with old tenant's report ID | Alpha | Beta | Deny |

### 10.2. Repository Spy/Probe

In Reactive code, `PublisherProbe` can confirm that when membership fails, the report query publisher **is never subscribed to**:

~~~java
PublisherProbe<Report> probe =
    PublisherProbe.of(Mono.just(testReport));

Mono<Report> result =
    Mono.<Void>error(new AccessDeniedException("No tenant access"))
        .then(probe.mono());

StepVerifier.create(result)
    .expectError(AccessDeniedException.class)
    .verify();

probe.assertWasNotSubscribed();
~~~

This test proves **sequencing** of the sample pipeline. In real controllers, apply the same technique to repository/gateway mocks or observe query counts.

## 11. Account Linking Is a Separate Security Transaction

Suppose Alice is logged in via Corporate and wants to link her Partner account:

~~~mermaid
sequenceDiagram
    autonumber
    actor User
    participant RP as Spring Security RP
    participant DB as Identity Store
    participant OP as Partner OP
    User->>RP: POST /account/links/partner (CSRF protected)
    RP->>RP: Verify current account/session + step-up policy
    RP->>DB: Create expiring link intent bound to account/session/provider
    RP-->>User: Redirect Authorization Code + state + PKCE
    User->>OP: Authenticate as Partner identity
    OP-->>User: Authorization code + state
    User->>RP: OAuth callback
    RP->>RP: Validate state/PKCE/ID Token issuer + aud + nonce
    RP->>DB: Atomically claim unused link intent
    RP->>DB: Check external identity uniqueness
    RP->>DB: Link verified issuer + sub to intended account
    DB-->>RP: Committed or conflict
    RP-->>User: Linking result
~~~

Never turn every login into "automatic account linking." Linking must only occur after a valid **link intent**.

### 11.1. What Should a Link Intent Contain?

A server-side record:

~~~text
attempt_id = random opaque identifier
target_internal_account_id = Alice
initiator_session_binding = one browser/session
expected_registration_id = partner
expected_issuer = https://id-b.example.test
created_at / expires_at
consumed_at = null
step_up_satisfied = true/false
status = PENDING
~~~

`attempt_id` must not be guessable. Distinguish the **link intent ID** from OAuth2 `state`/`nonce`; the framework must still validate `state`/PKCE/`nonce` properly. In multi-instance deployments, pending link intents must use a shared store or appropriate session architecture.

### 11.2. Never Take the Target Account from Callback Query Parameters

Anti-pattern:

~~~http
GET /login/oauth2/code/partner?code=...&state=...&targetUserId=victim-id
~~~

If the backend trusts a browser-supplied `targetUserId` to link a new identity, an attacker can link their own identity to a victim's account. The **target account** must come strictly from the server-side link intent created while the initiator was authenticated and checked for CSRF/session/step-up policy.

### 11.3. Never Link by Email

~~~text
Provider A: iss=A, sub=alice-a, email=shared@example.test
Provider B: iss=B, sub=bob-b, email=shared@example.test

=> Does not prove same person.
~~~

Even if both return `email_verified=true`, auto-linking by email remains dangerous when addresses are recycled, aliased, or belong to users holding distinct unlinked identities.

## 12. Linking States and Expected Outcomes

~~~mermaid
stateDiagram-v2
    [*] --> PENDING
    PENDING --> AUTHENTICATED_EXTERNAL: Valid OP callback
    PENDING --> EXPIRED: TTL expired
    PENDING --> CANCELLED: User cancelled
    AUTHENTICATED_EXTERNAL --> LINKED: Transaction + uniqueness pass
    AUTHENTICATED_EXTERNAL --> CONFLICT: Identity already belongs to another account
    AUTHENTICATED_EXTERNAL --> DENIED: Wrong session/account/provider/tenant
    LINKED --> [*]
    CONFLICT --> [*]
    DENIED --> [*]
    EXPIRED --> [*]
    CANCELLED --> [*]
~~~

Invariants:

- An attempt **can be consumed only once**.
- `expires_at` in the past -> reject even if the callback tokens are valid.
- Session/account logged out or switched user -> reject.
- Registration/issuer mismatches the intent -> reject.
- Identity already linked to the same account -> can return idempotent success per policy.
- Identity already linked to **another account** -> conflict; never silently transfer ownership.
- Cancelled attempt -> a late callback must never link.
- Database update and marking the attempt consumed must be atomic.

### 12.1. Workflows Should Enforce a Reauthentication Policy

For sensitive mutations like attaching a new login method, **step-up / recent authentication** may be needed. Simply checking that a session exists is insufficient if a cookie was stolen or sessions live for days.

### 12.2. Logging In with a New Identity Can Overwrite `SecurityContext`

In some designs, an OAuth2 Login callback creates a new principal and replaces the browser's current `Authentication`. If linking reads only the **post-callback `Authentication`**, the target account could switch from Alice to Bob. Bind the target to the initiating account/session before redirect, verify the account identity, and execute the link transaction explicitly rather than blindly reading `currentAuthentication.getName()` after callback.

## 13. Key Account-Linking Test Cases

| Test ID | Scenario | Expectation |
| --- | --- | --- |
| LINK-01 | Alice links nonexistent identity B | Succeeds; external key attaches to Alice |
| LINK-02 | B shares Alice's email without explicit link | No auto-link |
| LINK-03 | Identity B already linked to Bob | Conflict; never reassigned to Alice |
| LINK-04 | Alice's attempt, callback in Bob's session | Reject |
| LINK-05 | Attempt expects issuer B, callback from issuer A | Reject |
| LINK-06 | Wrong callback `state` | Reject before linking |
| LINK-07 | Wrong PKCE verifier or code reuse | Reject |
| LINK-08 | Expired intent | Reject, no DB mutation |
| LINK-09 | Attempt replayed a second time | Idempotent read-only or reject |
| LINK-10 | Two requests link same identity to two accounts | Only one transaction succeeds |
| LINK-11 | Alice logs out before callback | Reject per session policy |
| LINK-12 | Session fixation / CSRF attempt | No unauthorized link intent created |
| LINK-13 | Unlink last identity when account lacks recovery | Block or require recovery per policy |
| LINK-14 | Alice attempts to unlink Bob's identity | Deny |
| LINK-15 | External identity email changes | Identity key and link stay intact |
| LINK-16 | Different pairwise `sub` across clients | No auto-link by email alone |
| LINK-17 | OP rejects consent | No link created |
| LINK-18 | OP timeout / invalid ID Token | No link created; recovery UX shown |

Do not assert only HTTP status codes. Inspect **database state after each test** to prove no new identity appeared, no ownership changed, no memberships/roles were lost, and the link attempt was consumed/marked properly.

## 14. Transactions and Unique Constraints Guarding Concurrent Links

Two browser sessions can finish callbacks at the same time:

~~~text
Request A: Alice tries to link (issuer B, sub shared-100)
Request B: Bob   tries to link (issuer B, sub shared-100)

T1: SELECT finds no identity
T2: SELECT finds no identity
T1: INSERT identity -> Alice
T2: INSERT identity -> Bob
~~~

Without database uniqueness, both inserts can succeed in a race. An application-level `existsByIssuerAndSubject` check alone **is not enough**.

### 14.1. Strategy

- Enforce `UNIQUE (issuer, subject)` in the database.
- Atomically consume the link intent and insert the mapping inside a transaction.
- Handle unique violations as **conflicts**, never auto-retrying and reassigning ownership.
- Lock or compare-and-swap on the link attempt or identity key if needed.
- Log conflicts with safe metadata; never log raw ID Tokens.

### 14.2. Transaction Pseudocode

~~~java
@Transactional
public LinkResult completeLink(
        UUID attemptId, VerifiedOidcIdentity identity) {

    LinkAttempt attempt = linkAttempts.lockPending(attemptId);
    requireNotExpired(attempt);
    requireCorrectSessionAndInitiator(attempt);
    requireExpectedRegistrationAndIssuer(attempt, identity);

    ExternalIdentityKey key = new ExternalIdentityKey(
        identity.issuer(), identity.subject());

    // Database UNIQUE(issuer, subject) is the final safeguard.
    identities.insert(key, attempt.internalAccountId());
    linkAttempts.markConsumed(attemptId);
    return LinkResult.LINKED;
}
~~~

This is **business-API pseudocode**, not a standalone compilable snippet. `VerifiedOidcIdentity` must come from a verified OIDC principal or equivalent proof; never accept it straight from arbitrary JSON request bodies.

### 14.3. Concurrent Tests Need Real Barriers

Running two futures sequentially does not test a race. Use synchronization barriers/latches so two real transactions hit the database nearly simultaneously, and assert:

~~~text
Success count = 1
Conflict count = 1
Number of external_identity rows for (iss,sub) = 1
Owner account = exactly one legitimate winner
Both link attempts have valid terminal status
~~~

Never rely on SQLite/in-memory behavior and assume PostgreSQL/JDBC isolation behaves identically. Test against a production-like database using Testcontainers.

## 15. Testcontainers PostgreSQL for Repository Integration

Example Gradle dependencies (versions managed by project BOM):

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-security'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
    testImplementation 'org.testcontainers:junit-jupiter'
    testImplementation 'org.testcontainers:postgresql'
}
~~~

A skeleton:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@Testcontainers
@SpringBootTest
class ExternalIdentityDatabaseTest {

    @Container
    static final PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @Test
    void duplicateExternalIdentityIsRejectedByDatabase() {
        // Set up datasource with container, run migrations,
        // insert same (issuer, sub) into 2 internal accounts.
        // Assert UNIQUE violation and that only one owner exists.
    }
}
~~~

**This is a skeleton lacking datasource wiring / `@DynamicPropertySource` or Boot `@ServiceConnection`**, as exact declaration depends on the Spring Boot version. Use real SQL migrations and real DB transaction semantics in implementation.

### 15.1. Do Not Let Test Rollbacks Mask Commit Behavior

Some Spring tests run inside a transaction that rolls back after each method, making concurrency behave differently from production. For concurrent linking tests, worker transactions/threads must actually commit and observe real isolation rather than reading uncommitted state inside one shared test transaction.

## 16. MockMvc with `oidcLogin()` for Testing Tenant Authorization

Spring Security Test provides `SecurityMockMvcRequestPostProcessors.oidcLogin()` to supply a mock `OidcUser` in HTTP tests.

~~~java
package com.example.integration;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.security.test.web.servlet.request
    .SecurityMockMvcRequestPostProcessors.oidcLogin;
import static org.springframework.test.web.servlet.request
    .MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result
    .MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class TenantIsolationMvcTest {

    @Autowired MockMvc mvc;

    @Test
    void memberOfAlphaCannotReadBetaReport() throws Exception {
        mvc.perform(get("/tenants/t-beta/reports/report-002")
            .with(oidcLogin().idToken(token -> token
                .claim("iss", "https://id-a.example.test")
                .claim("sub", "shared-100")
                .claim("email", "alex@example.test"))))
            .andExpect(status().isForbidden());
    }
}
~~~

**Assumptions:** the app defines this endpoint/path and fixtures (`Alice -> Alpha`, `report-002 -> Beta`), and policy returns 403 on denial. If policy intentionally returns 404 to prevent information disclosure, assert 404. This test **only verifies application authorization when the endpoint uses real identity/membership checks**; it does not verify ID Token signatures because `oidcLogin()` is mocked.

### 16.1. Do Not Hard-Code Status Assertions Without Checking Data Flow

An `.andExpect(status().isForbidden())` test can pass falsely if the endpoint returned 403 due to **missing CSRF**, a **missing route**, or an unauthenticated user rather than tenant authorization. While GETs typically skip CSRF, you should still:

- Confirm the expected handler/route ran.
- Check the response/error category.
- Assert the authorized Alpha request returns 200.
- Assert Beta data was never loaded.
- Use repository spies/metrics where appropriate.

### 16.2. Registration ID Also Needs Testing

`oidcLogin()` can configure a custom `ClientRegistration` or per-registration principal. Test that the same issuer/`sub` under a disallowed registration never receives another registration's privileges. Do not test only claims when registry lookup also depends on registration ID.

## 17. MockMvc Provider Collision Tests

Use two test principals:

~~~text
Principal A:
  iss=https://id-a.example.test
  sub=shared-100
  email=alex@example.test

Principal B:
  iss=https://id-b.example.test
  sub=shared-100
  email=alex@example.test
~~~

Required assertions:

1. A resolves to **internal account Alice**.
2. B resolves to **internal account Bob**.
3. `Alice.id != Bob.id`.
4. A has no Beta membership; B has no Alpha membership.
5. Logs/audits record the correct provider alias.
6. When B's email changes, the external identity stays bound to Bob.
7. If registration B uses different claims, it never falls back to A's key.

An illustrative service test:

~~~java
@Test
void sameRawSubAndEmailAcrossIssuersStaySeparate() {
    ExternalIdentityKey a =
        new ExternalIdentityKey("https://id-a.example.test", "shared-100");
    ExternalIdentityKey b =
        new ExternalIdentityKey("https://id-b.example.test", "shared-100");

    UUID aliceId = identityService.resolveAccountId(a);
    UUID bobId = identityService.resolveAccountId(b);

    assertNotEquals(aliceId, bobId);
}
~~~

Assume services/repositories and fixtures exist. The point is preventing cross-issuer account collisions, **not** the exact string literals.

## 18. Testing the Real OIDC Protocol: Two Mock OpenID Providers

`MockMvc`/`oidcLogin()` does not call Authorization Endpoints, Token Endpoints, or JWKS. To test **provider isolation at the protocol layer**, stand up **two independent mock OPs**.

~~~text
Mock OP A:
  issuer = https://id-a.test.example
  client_id = portal-a
  signing key = key-A
  authorization endpoint A
  token endpoint A
  JWKS endpoint A
  UserInfo endpoint A

Mock OP B:
  issuer = https://id-b.test.example
  client_id = portal-b
  signing key = key-B
  authorization endpoint B
  token endpoint B
  JWKS endpoint B
  UserInfo endpoint B
~~~

Test/example hosts are **illustrative only**. In CI, use HTTPS test servers or explicit loopback test configurations within approved boundaries.

### 18.1. Responses to Simulate

| Endpoint | Positive Case | Negative Case |
| --- | --- | --- |
| Discovery A | Issuer/endpoints A | Returns issuer B or wrong JWKS URL |
| Authorization A | Code + correct state | Error, state mismatch |
| Token A | Signed ID Token A, Access Token A | `invalid_client`, `invalid_grant` |
| JWKS A | Public key A | Only key B, unknown `kid` |
| UserInfo A | `sub` matches ID Token A | Different `sub` |
| Authorization B | Correct client and redirect | Wrongly receives callback A |
| Token B | Signed ID Token B | Token carries `aud=portal-a` |
| JWKS B | Key B | Signing key A |

### 18.2. Issuer Mismatch Test

Scenario:

~~~text
1. Browser initiates /oauth2/authorization/corp-alpha.
2. OP A issues a normal authorization code.
3. Test OP returns an ID Token with iss = issuer B.
4. RP must reject authentication.
5. No internal account created, no link made, no authorized client saved.
~~~

### 18.3. Audience Mismatch Test

~~~text
Expected clientId=portal-a
Returned ID Token aud=portal-b

=> Reject.
~~~

An ID Token's audience binds to the **OAuth client ID**, not the Spring `registrationId` name.

### 18.4. Signing-Key Mix-Up Test

An ID Token claims `iss=A` yet is signed with key B (or its JOSE header specifies a `kid` found only in JWKS B). Client A must never fetch keys from an arbitrary URL supplied by the JWT header and accept the token. Tests must enforce trusted `issuer -> JWKS` mapping.

### 18.5. UserInfo Subject Mismatch Test

~~~text
ID Token A sub = user-101
UserInfo A sub = user-999

=> Do not use UserInfo claims.
~~~

The rule `UserInfo sub == ID Token sub` is mandated by OpenID Connect Core. Never work around a mismatch by matching emails.

## 19. State, Nonce, PKCE, and Issuer Mix-Up in Callbacks

In Authorization Code + OIDC:

- `state` binds the callback to the original authorization request.
- PKCE `code_verifier` must match the authorization request's `code_challenge`.
- `nonce` binds the ID Token to the OIDC request when used by the flow.
- `issuer`/`aud` validation proves the token belongs to the intended OP and client.
- `registrationId`/client registration routes the token exchange accurately.

### 19.1. Cross-Callback Test

~~~text
Session 1 starts login with OP A
  -> state A, PKCE verifier A, nonce A

Session 2 starts login with OP B
  -> state B, PKCE verifier B, nonce B

Attack: send OP B callback/code into OP A callback path
  -> Must reject; no account link or session swap.
~~~

### 19.2. Replay Test

A valid authorization code is generally **single-use**. A replayed callback must never create a second link, alter the user session, or pivot the link onto another account.

### 19.3. Multi-Tab Test

- Tab 1 starts linking Partner.
- Tab 2 starts logging in with Corporate.
- Tab 1's callback arrives after Tab 2's callback.

If the logic stores only a single "last provider selected" flag in session without per-request correlation, it can mislink accounts. Tests must verify that callback A matches only request A and that link intent/session bindings are enforced.

### 19.4. Never Expose Codes/States in Test Artifacts

Browser HAR captures can contain `code`, `state`, cookies, client secrets, and token responses. Never attach raw HAR files to CI artifacts or tickets; redact before sharing.

## 20. Correctness of the Authorized-Client Store in Multi-Provider Setups

Spring Security stores authorized clients keyed by components such as:

~~~text
ClientRegistration + principalName
  -> Access Token
  -> Refresh Token (if present)
~~~

In Servlet:

~~~text
OAuth2AuthorizedClientService
OAuth2AuthorizedClientRepository
~~~

In WebFlux:

~~~text
ReactiveOAuth2AuthorizedClientService
ServerOAuth2AuthorizedClientRepository
~~~

### 20.1. Common Isolation Bugs

- Store keys only by `principalName=email`, ignoring issuer.
- Two registrations share an email and a custom service keys solely by email **without registration**.
- A background job's token manager loads another user's token.
- Provider A returns `invalid_grant`, and the handler deletes all connections for that user, including B.
- A cached `WebClient` injects default authorized client B into API A calls.
- Registration A's Refresh Token is sent to Token Endpoint B.
- Tenant Alpha's data uses tenant Beta's token or vice versa.

### 20.2. Authorized-Client Test Matrix

| Case | Expectation |
| --- | --- |
| Save token A, load A | Returns exact token A |
| Save token B under same principal alias, load B | Returns token B without overwriting A |
| Load ungranted registration C | Does not return token A or B |
| Refresh A succeeds | Updates A, leaves B unchanged |
| A returns `invalid_grant` | Cleans up A per policy, leaves B unchanged |
| A times out / returns 503 | Does not mass-delete A or B |
| Logout from A | Does not revoke B outside policy |
| User B shares email with A | Never uses A's token |
| Tenant switched | Never reuses tokens outside exact account/resource scope |

### 20.3. Do Not Assume `principalName` Namespaces Issuers Automatically

Some default implementations populate `principalName` from OIDC `sub` or customizations. In custom stores, explicitly namespace keys by identity/account/registration. If the app supports pairwise subjects and multiple client IDs, reflect that policy in the key.

### 20.4. Never Log Raw Tokens in Tests

Assert registration ID, client identity, expiration or test-only opaque token hashes, scopes, record counts, and owners; keep raw ID/Access/Refresh Tokens out of reports and logs.

## 21. API Scopes, Authorities, and Tenant Permissions Are Three Different Things

~~~text
OIDC Login:
  User authenticated at OP

App role:
  ROLE_REPORT_VIEWER within tenant Alpha

OAuth2 Access Token:
  scopes: reports.read
  audience: reports-api

Resource Server:
  validates issuer, audience, expiration,
  scope and object-level access
~~~

A `roles=["admin"]` claim from OP B does not prove the user is an admin of tenant Alpha.

### 21.1. Role Mapping Allowlist Tests

| Claim Input | Trusted Source? | Expectation |
| --- | --- | --- |
| Issuer A: `app_roles=["report-reader"]` | Verified A | Mapped per policy A |
| Issuer B: `app_roles=["report-reader"]` | Verified B, different contract | Do not apply A's mapping automatically |
| Issuer B: `app_roles=["admin"]` | B, unknown role | Does not grant `ROLE_ADMIN` |
| Issuer A: wrong claim type (string/object) | A, bad schema | Fail closed |
| Issuer A: claim missing | Unknown privileges | No implicit grants |
| Entra: `tid` outside allowlist | Unapproved tenant | Reject |
| Google: email domain matches without Workspace `hd` proof | Insufficient claim | Do not grant membership |

### 21.2. `GrantedAuthoritiesMapper` Does Not Automatically Inspect Access Tokens

OIDC principal authorities generally derive from ID Token/UserInfo and Spring Security configuration. If a provider places `roles` only inside an API Access Token, never silently treat an unvalidated Access Token JWT as OIDC principal authority data. Explicitly test **claim source**, issuer, token audience, and mapper behavior.

### 21.3. Testing Revoked Memberships

If a tenant admin removes Alice's membership while her OIDC session remains active:

~~~text
Authentication at the OP may still be valid.
Tenant membership at Portal has been revoked.
=> Subsequent requests must obey the new membership policy.
~~~

Test cache invalidation, session/authority freshness, token lifetimes, and business rules. Never treat cached local roles as permanently authoritative after membership changes.

## 22. Testing Cross-Tenant Access with Guessable Resource IDs

A critical test group is **object-level authorization**:

~~~http
GET /tenants/t-alpha/reports/report-alpha-1
GET /tenants/t-alpha/reports/report-beta-1
GET /tenants/t-beta/reports/report-beta-1
~~~

For Alice with access only to Alpha:

- Request 1 succeeds if she holds the required role.
- Request 2 is denied because the report belongs to Beta even though the URL says Alpha.
- Request 3 is denied because she lacks Beta membership.

### 22.1. BOLA Is Not Just GET

Also test:

~~~text
GET     /reports/{id}
PATCH   /reports/{id}
DELETE  /reports/{id}
POST    /tenants/{tenantId}/reports
POST    /tenants/{tenantId}/members
POST    /tenants/{tenantId}/invitations
POST    /accounts/{id}/links
DELETE  /accounts/{id}/links/{linkId}
~~~

State-changing requests need CSRF protection in cookie-authenticated browser apps. With JSON API bearer tokens, authorization policies must still enforce owning tenant and role.

### 22.2. Errors Must Not Leak Other Tenants' Data

On denial, response bodies must not reveal Beta's report name, owner email, or organization metadata. Assert on **bodies**, headers, redirects, and exception messages, not just status 403.

## 23. Selecting a Tenant in the UI Is Not Authorization

A UI with a tenant selector dropdown:

~~~text
Active tenant: Alpha
User changes to Beta
~~~

The outcome must depend on the **user's actual current membership in Beta**, not client-side state. If Beta is unauthorized, the backend must deny even when the frontend sends syntactically valid headers/paths/query parameters.

### 23.1. Session Active Tenant

If the app stores `activeTenantId` in session, verify:

1. Changing tenants verifies membership on the backend.
2. Session writes the tenant only after verification.
3. Switching accounts clears any prior tenant context.
4. Revoked memberships cannot be bypassed by a cached active tenant.
5. Multi-tab tenant switching never causes requests to run with the wrong tenant's permissions.

### 23.2. Hostname/Subdomain Routing

An app may serve `alpha.portal.example.test` and `beta.portal.example.test`. Browser-supplied `Host`/`X-Forwarded-Host` requires trusted-proxy validation. Never treat caller-supplied hostnames as proof of tenant membership.

### 23.3. Service-to-Service Calls

Machine client credentials do not grant unrestricted cross-tenant access. Test that downstream APIs enforce tenant authorization independently and never let machine admin tokens bypass delegated user permissions.

## 24. Account Linking via a New Provider: Anti-Login-CSRF

A **login CSRF / account-linking confusion** attack occurs when an attacker starts an OAuth flow for their own identity and tricks a victim's browser into finishing the callback, linking the attacker's identity to the victim's account.

### 24.1. Controls to Test

- Link initiation is a state-changing action with proper CSRF protection.
- The server persists a link intent bound to the victim's authenticated account/session.
- The authorization request securely stores `state` and PKCE verifier.
- The callback belongs to the same flow, matches issuer/registration, and cannot be replayed.
- The user confirms linking within a valid session per risk policy.
- Recent authentication / step-up may be required.
- Link targets are never read from caller-editable URLs/headers.
- Callbacks never auto-link on matching email alone.

### 24.2. Negative Test: Callback from Another Session

~~~text
Session S1 (Alice):
  create link intent to Partner

Session S2 (Attacker):
  authenticate with Partner user attacker-p

Attack:
  try completing S1 link intent from S2 callback

Expected:
  link rejected
  Alice external identities unchanged
  Attacker identity remains under its own account/unlinked
~~~

### 24.3. Negative Test: Stale Link Intent

If an intent is expired, cancelled, or already consumed, even a protocol-valid callback **must not create a link**. Test explicit idempotency/status handling.

### 24.4. Do Not Auto-"Recover" Links by Email

A UX saying "We noticed the same email and merged your accounts automatically" invites account takeover. If the app suggests linking, the user must still prove control of both identities through a secure linking workflow.

## 25. Unlink, Disconnect, and Logout Need Dedicated Tests

| Operation | Target | Do Not Confuse With |
| --- | --- | --- |
| Local logout | RP browser session | Does not automatically delete external identities |
| OIDC RP-Initiated Logout | OP SSO session | Does not automatically revoke all Access Tokens |
| Disconnect connection | Authorized client/tokens | Does not automatically delete internal account |
| Unlink external identity | Identity->account mapping | Does not automatically remove tenant memberships without policy |
| Delete account | Internal account and data per policy | Does not automatically mean every provider grant was revoked |

### 25.1. Testing Unlink Ownership

- Alice can unlink her own identity if reauthentication/recovery rules are satisfied.
- Alice cannot unlink Bob's external identity by guessing a link ID.
- Unlinking one provider leaves unrelated provider connections untouched.
- Prevent removing the **last remaining login identity** if no recovery path exists, unless inside an explicit account-closure flow.
- Pending link attempt active: does unlinking invalidate it per policy?
- Concurrent unlink/login never leaves stale account ownership.

### 25.2. Testing Logout Isolation

Logging out of Corporate A does not implicitly log out of Partner B or every tenant. If the product supports global logout, require explicit session registries / OP contracts and test the exact scope. Logging out one browser session must never terminate another user's session merely because emails match.

## 26. Spring Security WebFlux: WebTestClient + `mockOidcLogin()`

In Reactive apps, use `SecurityMockServerConfigurers.mockOidcLogin()`:

~~~java
package com.example.integration;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;
import org.springframework.test.web.reactive.server.WebTestClient;

import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.springSecurity;
import static org.springframework.security.test.web.reactive.server
    .SecurityMockServerConfigurers.mockOidcLogin;

@SpringBootTest
class ReactiveTenantIsolationTest {

    @Autowired ApplicationContext context;

    private WebTestClient client;

    @BeforeEach
    void setup() {
        client = WebTestClient.bindToApplicationContext(context)
            .apply(springSecurity())
            .configureClient()
            .build();
    }

    @Test
    void authenticatedOidcUserWithoutMembershipIsDenied() {
        client.mutateWith(mockOidcLogin())
            .get().uri("/tenants/t-beta/reports/report-002")
            .exchange()
            .expectStatus().isForbidden();
    }
}
~~~

**Assumptions:** the app already defines routes/fixtures and the default `mockOidcLogin()` principal has no Beta membership; policy returns 403. When tests need a specific issuer/`sub`, use custom configurers/OIDC principals matching your test fixture.

### 26.1. Verifying Reactor SecurityContext

`ReactiveSecurityContextHolder` relies on Reactor Context rather than Servlet's `ThreadLocal` `SecurityContextHolder`. Test that:

- User A's `Authentication` never bleeds into user B across `publishOn`.
- Reactive operations composed within a request retain the right user and tenant.
- Fire-and-forget `subscribe()` calls do not drop context on API/audit/authorized-client work.
- Missing `Authentication` fails closed.
- Wrong tenant context is denied.

### 26.2. Unauthorized Requests Do Not Subscribe Downstream

Use `PublisherProbe` and `StepVerifier`:

~~~java
PublisherProbe<Report> downstream =
    PublisherProbe.of(Mono.just(testReport));

Mono<Report> result =
    Mono.<Void>error(new AccessDeniedException("No Beta membership"))
        .then(downstream.mono());

StepVerifier.create(result)
    .expectError(AccessDeniedException.class)
    .verify();

downstream.assertWasNotSubscribed();
~~~

This is a sequencing fragment; import `reactor.test.*`, Reactor `Mono`, Spring `AccessDeniedException`, and define `testReport`. If production code uses `Mono.when(authCheck, apiCall)`, the API may subscribe before the denial fires; probe tests catch that immediately.

## 27. Testing Concurrent Requests and Responses Without Cross-User Mixing

In Reactive or async Servlet apps, requests from Alice and Bob can interleave:

~~~text
Request Alice -> issuer A/sub shared-100 -> tenant Alpha
Request Bob   -> issuer B/sub shared-100 -> tenant Beta

Concurrent:
  user context
  authorized client
  tenant ID
  report selection
  API token forwarding
~~~

**Assert:**

1. Alice's response never contains Beta data.
2. Bob's response never contains Alpha data.
3. Log correlation prints no raw tokens.
4. `ReactiveSecurityContextHolder` aligns with each subscriber.
5. Custom cache keys never rely on `sub` alone.
6. Database writes never read `tenantId` from a shared mutable singleton field.

### 27.1. Shared Mutable State Anti-Pattern

~~~java
// ANTI-PATTERN: singleton bean stores request tenant in a field.
@Service
class UnsafeTenantService {
    private String currentTenant;

    void setTenant(String tenant) {
        this.currentTenant = tenant;
    }
}
~~~

Under concurrent requests, one request overwrites another's tenant. Use immutable request-scoped context/explicit tenant parameters, proper Reactor Context propagation, or server-validated session context—never mutable singleton fields.

## 28. Testing Token Refresh and Revocation Across Multiple Providers

Client A holds Refresh Token R-A and Client B holds R-B. When A returns `invalid_grant`:

~~~text
AuthorizedClient(A, Alice) -> invalid_grant
AuthorizedClient(B, Alice) -> still valid
AuthorizedClient(A, Bob)   -> still valid
~~~

### 28.1. Testing `invalid_grant` Scope

- The failure handler deletes/marks stale **only authorized client A/Alice**, leaving B and Bob intact.
- Provider B is never marked revoked.
- Reauthorization of A occurs only with valid consent/session.
- Custom `OAuth2AuthorizedClientManager` implementations never send token B to API A.

### 28.2. Refresh Token Rotation Race

~~~text
Request 1 loads Refresh R1 -> OP issues R2 -> save version 2
Request 2 loads Refresh R1 -> invalid_grant
Request 2 handler removes stale version 1

Expected:
  do not mistakenly delete version 2
~~~

Use optimistic locking, single-flight refresh, or compare-and-swap depending on your store. Test with a mock OP controlling response order, not just single sequential requests.

### 28.3. Provider 503 Differs from Revoked Grants

A Token Endpoint 503 does not prove the user revoked consent. Keep valid tokens/connections intact and apply per-provider retry/backoff/circuit breakers. Never mark all users on A as `REAUTH_REQUIRED` during a transient outage.

### 28.4. Token Revocation vs. Local Deletion

`removeAuthorizedClient(...)` only clears the local store; it does not call an RFC 7009 revocation endpoint. Test HTTP revocation, pending queues, and provider responses separately. Ensure revoking A never sends R-B to A's endpoint or vice versa.

## 29. Multi-Tenant Delegated API Calls: Downstream Must Enforce Too

Portal may call a Resource Server:

~~~text
Spring OIDC Client RP
  -> Access Token for Reports API
  -> GET /reports/report-002
  -> Resource Server validates issuer/aud/scope/tenant/resource
~~~

Also test:

- Tokens from issuer A are rejected by Resource Server B unless explicitly trusted.
- Tokens minted for UserInfo are rejected as Reports API tokens.
- Even with valid `aud=reports-api`, a user lacking Beta membership is denied.
- An Access Token with `reports.read` is not enough to grant `ROLE_TENANT_ADMIN`.
- Resource Servers ignore caller-supplied `X-Role: ADMIN` headers.
- Machine-to-machine client credentials never substitute for delegated user permissions.

### 29.1. `issuer + subject` Alone Still Does Not Authorize Object Access

Even after resolving Alice accurately, authorization must check tenant and resource ownership. Test the API tier independently of RP login, because callers can hit APIs directly outside the UI.

### 29.2. Spring Security Resource Server Tests

When testing Resource Servers, the `jwt()` request post-processor mocks a JWT-authenticated principal and authorities without verifying real signatures. Full JWT acceptance tests require a JWT decoder with trusted issuer and audience validation against signed test tokens.

## 30. Diagnosing Provider-Specific Claims

Different OPs emit different claims:

| Provider Type | Common Claims | Must-Test Checks |
| --- | --- | --- |
| Generic OIDC | `iss`, `sub`, profile/email | Never assume email is always present |
| Google Identity | `sub`, `email`, `hd` when applicable | Never substitute email domain for Workspace validation |
| Microsoft Entra ID | `tid`, `oid`, `sub`, optional groups/roles | Tenant allowlists, pairwise `sub`, group overage |
| Keycloak | Protocol-mapped realm/client roles | Configured claim placement and authority mapping |
| Partner OIDC | `org_id`, `employee_id`, custom entitlements | Type/schema/trust checks and tenant mapping |

These are **common patterns**, not guarantees for every deployment. Test against the **actual provider contract**, mock missing/malformed values, and assert fail-closed behavior.

### 30.1. Entra `tid` Is Not a User ID

Two users in the same tenant share the same `tid`. Within a tenant a user has `oid`, while `sub` may be pairwise. Never key account lookups by `tid` alone.

### 30.2. Google Email `hd` / Workspace

An email ending in `@company.example` does not prove Workspace membership in that organization. When policy requires Workspace membership, check `hd` per provider docs and enforcement rules, and add negative tests for spoofed or reassigned email domains.

### 30.3. Keycloak Role Claims

If realm roles appear inside the Access Token while the OIDC principal only reads the ID Token/UserInfo, the app cannot assume `OidcUser` always has roles. Test exact **token placement** and mapper setup; never disable token audience validation just to pull claims.

## 31. Comprehensive Negative Security Test Matrix

| ID | Adversarial Input | Expectation |
| --- | --- | --- |
| PROVIDER-01 | ID Token B injected into flow A | Reject, no login/link |
| PROVIDER-02 | Token with issuer A signed by key B | Reject signature/trust |
| PROVIDER-03 | ID Token A carrying `aud=client-B` | Reject |
| PROVIDER-04 | Unknown `registrationId` | No arbitrary OP instantiated |
| PROVIDER-05 | UserInfo `sub` differs from ID Token | Ignore/reject UserInfo data |
| PROVIDER-06 | Same raw `sub` across issuers A/B | No identity collision |
| PROVIDER-07 | Same email across issuers A/B | No auto-link |
| PROVIDER-08 | Same OP, different pairwise `sub` across clients | No auto-merge |
| PROVIDER-09 | Malformed/unknown JWT `iss` | Reject |
| TENANT-01 | Alpha member requests Beta tenant | Deny |
| TENANT-02 | Alpha path + Beta resource ID | Deny |
| TENANT-03 | User carries `tid=Beta` claim without membership | Deny |
| TENANT-04 | Forged `X-Tenant-Id` header | Deny |
| TENANT-05 | Member is Alpha admin, Beta viewer | Never apply Alpha admin rights in Beta |
| TENANT-06 | Membership revoked during live session | Deny per freshness policy |
| TENANT-07 | Tenant switch across two tabs | No cross-tab context leakage |
| LINK-01 | Alice attempts to link Bob-owned identity | Conflict |
| LINK-02 | Link attempt completed from another session | Reject |
| LINK-03 | Expired/cancelled/consumed attempt | Reject |
| LINK-04 | Bad `state`/PKCE/nonce | Reject |
| LINK-05 | Mismatched issuer/registration vs. intent | Reject |
| LINK-06 | Concurrent inserts of same external key | Single unique owner |
| LINK-07 | Email changes | `issuer+sub` mapping stays unchanged |
| LINK-08 | Unlink identity owned by another account | Deny |
| LINK-09 | Unlink last identity violating recovery policy | Block |
| TOKEN-01 | Refresh Token A sent to B's token endpoint | Reject; never misroute |
| TOKEN-02 | `invalid_grant` on A | Leave B untouched |
| TOKEN-03 | Token B sent to API A | Never sent |
| TOKEN-04 | Concurrent refresh R1->R2 race | Never delete R2 |
| TOKEN-05 | Outage 503 on A | Never auto-revoke B or other users |
| LOGOUT-01 | Local logout from A | Never delete B outside policy |
| LOGOUT-02 | Logout Token B targeting session A | Never invalidate A |
| LOGGING-01 | Login/link failure | Never log token/code/session |

Every negative test must assert **zero unauthorized side effects**: identity rows, tenant memberships, authorized clients, audit events, and downstream Resource Server calls.

## 32. Practical Test Flows

### A — Two Providers Issuing the Same `sub=42`

Alice-A and Bob-B both have `sub=42`. The RP must create two separate external keys, never logging Bob in as Alice or serving Alpha reports to Bob.

**Assert:** 2 distinct identity rows, 2 internal users, separate memberships, 403/404 cross-tenant.

### B — Matching Email for Two Different People

A Corporate user and a Partner user both use `alex@example.test`.

**Assert:** no auto-link, no shared session/token; linking requires an explicit flow.

### C — Pairwise Subjects for the Same Person

Same OP: Portal gets `sub=pair-1`, Mobile gets `sub=pair-2`.

**Assert:** never auto-merge on email; if the user links them, require a workflow using provider-accepted proof/correlation.

### D — Account Linking Conflict

Alice tries to link a Partner identity already owned by Bob.

**Assert:** conflict; Bob remains owner; Alice receives none of Bob's permissions/tokens; no duplicate identity row is created.

### E — Attacker Alters `targetAccountId` in Callback

The link intent belongs to Alice, and an attacker submits the callback with `targetAccountId=Bob`.

**Assert:** backend ignores caller-supplied input, resolves target server-side, checks session/protocol bindings, and does not link to Bob.

### F — Replayed Link Attempt in Same Session

The first link succeeds, then the browser replays the callback.

**Assert:** no second mapping is created, ownership stays unchanged, and duplicate/expired handling follows policy.

### G — Single User Belonging to Two Tenants

Carol belongs to Alpha and Beta with different roles.

**Assert:** switching to Beta triggers a fresh Beta role check without leaking Alpha's admin privileges into Beta.

### H — Guessing Another Tenant's Report ID

Alice probes `report-beta-1` under both Alpha and Beta URLs.

**Assert:** both requests are denied and responses leak no resource metadata.

### I — OP B Signing Key Injected into JWKS A

Test OP A emits a token signed by key B.

**Assert:** ID Token validation rejects it and never trusts arbitrary keys from JWT headers.

### J — UserInfo Returns a Different Subject

Token A has `sub=alice`, UserInfo A has `sub=bob`.

**Assert:** UserInfo claims are discarded/rejected per OIDC Core; Alice's email/roles are never updated from Bob.

### K — Tenant Membership Revoked After Login

Alice logs in validly, then an admin revokes her Alpha membership.

**Assert:** subsequent API requests obey freshness/cache-invalidation rules rather than trusting only the active OIDC session.

### L — Provider A Refresh Fails While B Stays Healthy

OP A returns `invalid_grant`, while OP B's token stays valid.

**Assert:** connection A requires reauthorization, B is untouched, and the user's other authorized clients are never wiped.

### M — Concurrent Linking

Alice and Bob submit transactions to link the same external identity concurrently.

**Assert:** the database unique constraint preserves one owner, conflicts are handled gracefully, and no lost update occurs.

### N — Logout A While Browser Still Holds B Session

The app logs out of one provider.

**Assert:** scope obeys the product/OP contract; B and unrelated account links are not silently destroyed.

### O — Multi-Node Callback

The authorization request is initiated on node A and the callback lands on node B.

**Assert:** shared session/state storage preserves `state`/PKCE; no linking proceeds if correlation fails.

### P — Reactive Context Bleeds Between Concurrent Users

Alice and Bob send parallel API requests while a service uses a global mutable tenant field.

**Assert:** data never crosses between users; replace mutable state with immutable/request-scoped data or Reactor Context.

## 33. Designing the CI Test Topology

~~~text
CI job: unit + controller tests
  JUnit, MockMvc, WebTestClient, mockOidcLogin

CI job: repository isolation
  Testcontainers PostgreSQL, real migrations

CI job: OIDC protocol
  Test OP A + Test OP B
  Signing keys A/B, JWKS, Authorization/Token/UserInfo

CI job: browser flow
  Test browser A/B, SameSite cookies, PKCE/state/nonce

CI job: concurrency/chaos
  Link race, refresh rotation, multi-node session, OP 503

Optional sandbox contract:
  Provider-specific claims/scopes/logout behavior
~~~

### 33.1. Synthetic Providers Do Not Replace Real Providers

Mock OP tests prove Spring Security/OIDC handling under controlled inputs. Real providers differ in claims, issuer tenancy, pairwise subjects, scopes/consent, JWKS rotation, UserInfo, and logout. Maintain provider sandbox contract tests using dedicated test client registrations.

### 33.2. Test Data Should Be Randomized Yet Have Deliberate Collisions

Keep deterministic fixtures for `shared-100`, colliding emails, wrong tenants, and two-session attacker scenarios; randomize link attempt IDs, `state`, nonces, and token values per run, and keep them out of CI logs.

### 33.3. Parallel Tests Need Data Isolation

Give each test suite schema/database isolation or reliable cleanup. Parallel tests sharing one identity row create flaky false failures or mask races. Isolate independent tests while keeping explicit barriers inside concurrency scenarios.

### 33.4. Never Use Production Credentials

Never commit production client secrets into test YAML, screenshots, HTTP traces, HARs, WireMock mappings, or repositories. Test OPs should generate ephemeral test-only signing keys.

## 34. Observability for Isolation Testing

Useful structured events:

~~~text
event=external_identity_link_attempt
provider_alias=partner
initiator_account_alias=internal-100
requested_tenant_alias=alpha
outcome=DENIED_SESSION_MISMATCH
correlation_id=link-test-62
~~~

~~~text
event=tenant_access_denied
provider_alias=corporate
tenant_alias=beta
reason_category=NO_MEMBERSHIP
resource_type=report
correlation_id=api-test-31
~~~

These are **illustrative formats**, not default Spring logs. Never log raw `sub`, ID/Access/Refresh Tokens, authorization codes, client secrets, browser session cookies, or full ID Token claims.

### 34.1. Metrics

| Suggested Metric | Meaning |
| --- | --- |
| `oidc_login_success_total` by provider | Login success rate |
| `oidc_login_issuer_mismatch_total` | Detects issuer/registration mix-ups |
| `oidc_userinfo_subject_mismatch_total` | UserInfo/ID Token mismatch |
| `account_link_conflict_total` | Identity already owned by another account |
| `account_link_expired_total` | Link attempt expired by TTL |
| `tenant_access_denied_total` | Denials by membership/resource |
| `authorized_client_wrong_registration_total` | Token routing bug |
| `oauth2_refresh_invalid_grant_total` | Revoked grant / rotation race |
| `logout_session_scope_error_total` | Unexpected session mapping |

Never use email, raw subject, or token values in metric labels to avoid PII leaks and high cardinality. Anomalous spikes in account-link conflicts may warrant security investigation, not just UX triage.

## 35. Pre-Production Checklist

| Concern | Proven by Test? |
| --- | --- |
| ID Token issuer/audience/signature match registration | Mock OP protocol integration |
| ID Token A never accepted under registration B | Negative issuer/JWKS tests |
| Same raw `sub` across two issuers never collides | Identity unit + repository tests |
| Matching email never auto-links | App policy + HTTP tests |
| Pairwise `sub` never auto-merges | Provider contract/linking tests |
| Account linking requires explicit intent | Session/CSRF/step-up tests |
| Link intent session/issuer/client binding | Two-session attack tests |
| Link attempt TTL/replay/cancel | State machine integration |
| Unique `(issuer, sub)` enforced in DB | Testcontainers duplicate/race tests |
| Unlink ownership and last-login recovery | HTTP + repository tests |
| Server-side tenant membership checks | Policy/service tests |
| Resource tenant ownership enforced | IDOR/BOLA tests |
| Roles never leak across providers/tenants | Authority mapping tests |
| Missing/wrongly typed claims fail closed | Provider-specific contract tests |
| Token store scoped by registration/principal | Authorized-client tests |
| Refresh/revocation on A leaves B untouched | Failure handler tests |
| Concurrent refresh never deletes newer tokens | Controlled race tests |
| Logout/session on A leaves B intact per policy | Logout tests |
| Multi-node session/callback consistency | Browser + cluster integration |
| Reactive context isolates users/tenants | WebTestClient + StepVerifier |
| Denied calls never subscribe downstream | `PublisherProbe`/repository spy |
| Zero credentials/PII leaked to logs | Security logging tests |
| CI runs mocks and provider sandbox suites | Test topology/operational plan |

## 36. Review Questions

**1. Why can `sub` not serve as a global user key when multiple providers exist?**

Because `sub` is only unique within a single issuer's scope. Two OPs can assign the same raw subject to two different people. External identity keys must include the verified issuer.

**2. If two OPs both return the same verified email, can we auto-merge accounts?**

No. Emails can change or be reassigned; linking requires an explicit user-initiated secure workflow proving control over both identities.

**3. Do `@WithMockUser`/`oidcLogin()` prove that the ID Token was properly signed by the OP?**

No. Those supply mock `Authentication` principals; proving protocol security requires mock/test OP tests covering signed ID Tokens, JWKS, and issuer/audience/nonce validation.

**4. Can a user holding `ROLE_REPORT_VIEWER` view reports across all tenants?**

No. Authorization must verify the role **inside the target tenant**, tenant membership, and resource ownership.

**5. Why is a database `UNIQUE (issuer, subject)` constraint essential for account linking?**

Because two concurrent requests can both observe "identity does not exist yet." Application pre-checks cannot replace database uniqueness and transactions.

**6. What should happen when a callback carries a valid code but the link intent has expired?**

Never link. Successful protocol authentication does not override an expired intent/session binding.

**7. When an account-linking callback replaces `SecurityContext`, where should the target account come from?**

From the server-side link intent bound to the initiating account/session—never from the post-callback principal or a caller-supplied query parameter.

**8. Does `invalid_grant` from provider A justify deleting provider B's tokens?**

Not by default. Cleanup must be scoped strictly to registration/principal/connection and distinguish revoked grants from provider outages.

**9. Why should two test providers use different signing keys?**

So tests catch code that mixes up JWKS or issuers. Reusing a single signing key masks trust-boundary failures in negative tests.

**10. Is a 403 cross-tenant test enough to prove security?**

No. Also assert the denial reason, zero data leakage in the body, zero downstream execution, zero DB mutations, and that positive same-tenant tests still succeed.

## 37. References

- OpenID Connect Core 1.0, issuer/subject/ID Token/UserInfo: https://openid.net/specs/openid-connect-core-1_0.html
- OpenID Connect Discovery 1.0: https://openid.net/specs/openid-connect-discovery-1_0.html
- OAuth 2.0 Authorization Framework — RFC 6749: https://www.rfc-editor.org/rfc/rfc6749
- Proof Key for Code Exchange — RFC 7636: https://www.rfc-editor.org/rfc/rfc7636
- OAuth 2.0 Security Best Current Practice — RFC 9700: https://www.rfc-editor.org/rfc/rfc9700
- OAuth 2.0 Bearer Token Usage — RFC 6750: https://www.rfc-editor.org/rfc/rfc6750
- OAuth 2.0 Token Revocation — RFC 7009: https://www.rfc-editor.org/rfc/rfc7009
- JWT Best Current Practices — RFC 8725: https://www.rfc-editor.org/rfc/rfc8725
- Spring Security — OAuth2 Login (Servlet): https://docs.spring.io/spring-security/reference/servlet/oauth2/login/index.html
- Spring Security — Advanced OAuth2 Login: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/advanced.html
- Spring Security — MockMvc OAuth2 Login Tests: https://docs.spring.io/spring-security/reference/servlet/test/mockmvc/oauth2.html
- Spring Security — OAuth2 Client Authorized Clients: https://docs.spring.io/spring-security/reference/servlet/oauth2/client/authorized-clients.html
- Spring Security — Reactive OAuth2 Login: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/index.html
- Spring Security — Reactive OAuth2 Client: https://docs.spring.io/spring-security/reference/reactive/oauth2/client/index.html
- Spring Security — WebTestClient Security Testing: https://docs.spring.io/spring-security/reference/reactive/test/web/index.html
- Spring Security — Reactive Method Security: https://docs.spring.io/spring-security/reference/reactive/authorization/method.html
- Spring Security — OIDC Logout Servlet: https://docs.spring.io/spring-security/reference/servlet/oauth2/login/logout.html
- Spring Security — OIDC Logout Reactive: https://docs.spring.io/spring-security/reference/reactive/oauth2/login/logout.html
- Spring Framework — WebTestClient: https://docs.spring.io/spring-framework/reference/testing/webtestclient.html
- Testcontainers — PostgreSQL module: https://java.testcontainers.org/modules/databases/postgres/
- WireMock — Documentation: https://wiremock.org/docs/
- OWASP — Broken Access Control: https://owasp.org/Top10/A01_2021-Broken_Access_Control/
- OWASP — Authorization Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html
- OWASP — Cross-Site Request Forgery Prevention: https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html

## 38. Summary: Identity, Tenants, Account Linking, and Tokens All Need Isolation Testing

~~~text
Provider A --ID Token A--> Verify issuer A/signing key A/client A
      |                                     |
      |                                     v
      +-------------------------> (issuer A, subject A)
                                            |
Provider B --ID Token B--> Verify issuer B/signing key B/client B
      |                                     |
      +-------------------------> (issuer B, subject B)
                                            |
                                      Account lookup
                                            |
                        Explicit linking + uniqueness constraints
                                            |
                                      Internal account
                                            |
                                 Tenant membership + role
                                            |
                                  Resource tenant ownership
                                            |
                                 Scoped Access Token/API

Negative tests always needed:
  Same email / same raw sub / wrong issuer
  Wrong tenant / wrong resource / wrong role
  Wrong session / wrong state / replay link
  Concurrent link conflict / stale authorized client
  Cross-provider logout / refresh / revocation
~~~

**Six principles to remember:**

1. **Provider identities must include the issuer.** Raw `sub` or email cannot identify users across multiple OPs; include tests with intentional collisions.
2. **Tenant isolation must be enforced server-side.** A valid login does not prove membership; check tenant roles and resource ownership per request.
3. **Account linking is a transaction with takeover risk.** Enforce explicit intent, session/CSRF/step-up checks, state/PKCE, issuer binding, and replay protection; never auto-merge by email.
4. **Database constraints protect against races.** `UNIQUE (issuer, sub)`, transactions, and conditional updates matter just as much as service-layer checks.
5. **Authorized clients and tokens must be isolated by registration/principal.** Refresh/logout/revocation failures on one OP must not cascade to unrelated OPs or users.
6. **Multi-layer testing is essential.** `oidcLogin()`/`mockOidcLogin()` verify application policy, while mock OP/JWKS/browsers, Testcontainers, and provider sandbox tests verify protocol and persistence boundaries.

A multi-provider, multi-tenant system is only truly secure when **matching emails, identical raw subjects, shared browsers, concurrent callbacks, or a single provider outage** cannot leak permissions, tokens, or data into another account or tenant.
