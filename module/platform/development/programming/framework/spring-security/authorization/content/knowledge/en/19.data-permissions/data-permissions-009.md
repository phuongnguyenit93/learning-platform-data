# Data Sharing, Temporary Delegation, and Time Limits in Spring Security

## 1. The Problem: Access Permissions Change by **Recipient, Resource, Action, and Time**

Suppose Alice owns `Document #42` in a project management system. Normally, only Alice and members permitted by policy may read the document. Alice wants to **share read access with Bob from 09:00 to 10:00**, ending automatically afterward; if shared by mistake, Alice must be able to **revoke immediately** before 10:00.

A simple rule like `hasRole('USER')` cannot solve this: Alice and Bob may both be USERs, yet each document has different share recipients and expiration times. Likewise, a functional `document:read` authority does not prove Bob can read **Document #42** during **the current time window**.

The policy needs to answer:

```text
Who?      Bob (authenticated subject / grantee)
What?     READ
Where?    Document #42 in tenant A
Why?      Alice is a valid authorized sharer
From?     2026-11-05T02:00:00Z
Until?    2026-11-05T03:00:00Z (exclusive)
Valid?    Not revoked, no other invalidating condition
```

The example uses UTC timestamps for consistency. Corresponding local times depend on the user's time zone; **never** store a bare `"09:00"` string without date/time zone and rely on the browser clock for authorization.

**Principle:** sharing permission is strictly a **controlled additional path** past default access rules for **the exact object and action**, within **a valid time window**. That permission never bypasses tenant isolation, locked account status, resource state, or a revocation command.

This lesson distinguishes three models:

1. **Named-recipient sharing (named-recipient grant):** recipient Bob logs in; the server stores a grant for Bob on Document #42.
2. **Temporary delegation to another actor/app:** an actor receives scoped, time-limited authority; verify who granted, who received, and for what purpose.
3. **Share link/token (bearer capability):** anyone holding the valid secret can exercise the link's designed capabilities; requires dedicated leak controls, revocation, and expiration.

The three models carry different trust assumptions. Never turn a URL sent by email into a default substitute for recipient authentication, and never confuse login/JWT lifetime with **resource access grant lifetime**.

## 2. Distinguishing Authentication, Authority, ACL, and Time-Limited Grants

| Concept | Question Answered | Example |
| --- | --- | --- |
| Authentication | Who is making the request? | `subject=bob` from verified session/JWT |
| Authority/role | Which features may this person use? | `document:read`, `ROLE_EDITOR` |
| Object authorization | What is allowed on **Document #42**? | Owner, member, ACL, policy |
| Sharing grant | Who receives which extra action on which object? | Bob has READ on #42 |
| Time window | Is the grant active **right now**? | `validFrom <= now < expiresAt` |
| Revocation | Has the grant been revoked/terminated early? | `revokedAt != null` |
| Token/session lifetime | Is the authentication credential still valid? | JWT `exp`, session timeout |

A valid JWT does not guarantee the user can still read Document #42. Conversely, an unexpired grant does not turn an expired token into valid authentication.

In a Spring Security system:

- `SecurityFilterChain` typically handles authentication and rejects unauthenticated requests.
- `authorizeHttpRequests(...)` can enforce coarse-grained endpoint access.
- `@PreAuthorize(...)` or `AuthorizationManager<MethodInvocation>` can invoke a Java policy bean with the document ID.
- `AclPermissionEvaluator`/Spring ACL can evaluate ACEs per recipient; however, **per-grant expiration and revocation are not built into** standard ACEs unless the application adds matching mechanisms.
- Repositories/databases must still protect objects and tenants; caches/search/file storage must obey the decision too.

**Do not** assume using Spring ACL makes every ACE expire automatically. The standard `ACL_ENTRY` table stores mask, granting, SID, and ACE order—not an `expires_at` per entry by default. If lifetimes are needed, add a domain sharing grant/policy or intentionally extend the storage model.

## 3. What Must a Temporary Grant Store?

Foundational model for identity-based sharing:

| Field | Security Meaning |
| --- | --- |
| `grantId` | Stable ID of the grant record, for auditing/revocation |
| `resourceType` and `resourceId` | Exact resource type and **resource ID** |
| `grantorSubjectId` | Person/actor who granted permission, taken from Authentication |
| `recipientSubjectId` | Recipient granted access, stable internal identifier |
| `permission` | READ, COMMENT, EDIT, DOWNLOAD, or specific permission |
| `validFrom` | Start timestamp when access begins |
| `expiresAt` | **Expiration** boundary, exclusive |
| `revokedAt` | Set when an authorized subject revokes |
| `createdAt`, `updatedAt` | Auditing, state reconciliation |
| `tenantId` | Tenant scope when using multi-tenancy |
| `createdByReason`/`source` | Operational reason/ticket, if needed |

Sometimes `maxUses`, use count, `allowedIpRange`, `deviceBinding`, `approvalId`, `watermark`, `externalRecipient`, `delegationDepth`, `grantVersion`, or `policyVersion` are also needed. Add them only if genuinely required and reliably enforceable; unnecessary complexity does not automatically increase security.

### READ Permission Does Not Expand to EDIT

A `permission=READ` grant does not mean:

- Allowed to edit content.
- Allowed to download the raw file if DOWNLOAD is a separate permission.
- Allowed to re-share with Carol.
- Allowed to change owner or tenant.
- Allowed to view all other documents in the same folder.
- Allowed to export the entire dataset.
- Allowed to keep access after expiry/revocation.

If business requires sharing groups of actions, represent an **explicit permission set** and check per action. Never use a single `shared=true` flag meaning all operations are allowed.

## 4. Granting Conditions: Sharers Must Not Self-Escalate

A common risk is letting any user who can read a document call:

```http
POST /api/documents/42/shares
Content-Type: application/json

{
  "recipientId": "carol",
  "permission": "ADMIN",
  "expiresAt": "2099-01-01T00:00:00Z"
}
```

If the server saves the raw body, Carol could gain ADMIN on the document, even exceeding Alice's privileges. **Permission to share** must be a distinct privilege such as `document:share`, never automatically inferred from READ. Creating a new grant must check:

1. Caller is authenticated and still active.
2. Caller has SHARE permission on **Document #42** at grant time.
3. Document belongs to the verified tenant and is not deleted/locked/marked confidential forbidding sharing.
4. Recipient is valid, permitted to receive shares in the tenant/group, or on an approved external recipients list.
5. Proposed permission lies within the **delegable permission set**, potentially constrained to a subset of the grantor's actual rights.
6. Duration does not exceed policy: e.g., max 24 hours for external shares, max 30 days for internal shares.
7. Cannot extend duration beyond an upstream delegated grant: if Alice was granted access until 10:00, she cannot grant Bob until 17:00 unless policy permits.
8. Cannot re-grant previously revoked permissions by replaying requests lacking idempotency/revocation checks.
9. Approval, quota, classification, and audit rules are satisfied.

**Product-dependent:** owners may hold SHARE without a global authority, or a tenant admin may share within their scope. Crucially, every allow path must rest on server-side verification, never on client-supplied `grantorId` or `role`.

## 5. Active Time Window: Defining Boundaries Precisely

Recommend using a **half-open interval**:

```text
[validFrom, expiresAt)
```

Meaning:

- Valid when `now >= validFrom`.
- Valid when `now < expiresAt`.
- **Exactly at `expiresAt`**: expired.
- Before `validFrom`: not yet valid.
- `validFrom >= expiresAt`: invalid grant; refuse to store/issue.

Java using `java.time.Instant` and `Clock`:

```java
static boolean withinWindow(
        Instant now, Instant validFrom, Instant expiresAt) {
    return now != null
        && validFrom != null
        && expiresAt != null
        && !now.isBefore(validFrom)
        && now.isBefore(expiresAt);
}
```

This is a **method fragment** requiring `import java.time.Instant`. Compare `Instant` on absolute timestamps; half-open intervals avoid boundary microsecond/nanosecond ambiguity. Never write `now <= expiresAt`, which keeps the grant valid **at the exact moment of expiration**.

### UTC, Clocks, and Database Precision

- Store `validFrom`/`expiresAt` as `Instant` or a DB type representing UTC with clear conventions.
- UI can display local time via `ZoneId`, while the **server** converts to `Instant` for storage and comparison.
- Never trust `Date.now()` from the frontend to allow or deny.
- Injecting `Clock` enables deterministic tests and precise boundary verification.
- Multiple instances must synchronize clocks; for ultra-strict decisions, consider using a single DB/transaction time source.
- Account for SQL column precision (seconds/milliseconds/microseconds) and consistent `Instant` representation.
- JWT clock-skew tolerances must not automatically stretch a **share grant** lifetime that is supposed to end at an exact cutoff.

Example:

```text
validFrom = 2026-11-05T02:00:00Z
expiresAt = 2026-11-05T03:00:00Z

01:59:59.999Z  -> DENY (not yet started)
02:00:00.000Z  -> ALLOW if other conditions hold
02:59:59.999Z  -> ALLOW
03:00:00.000Z  -> DENY (expired)
```

## 6. Revoking Access: Revocation Differs from Waiting for Expiry

Time limits are **expiry**; revocation is an action **asynchronous to the expiration timestamp**. When Alice clicks "Stop sharing" at 09:20, Bob must be denied on subsequent access within the published security SLA, even though `expiresAt` is still 10:00.

Simple state model:

```text
ACTIVE:
  validFrom <= now < expiresAt
  AND revokedAt IS NULL
  AND document is still accessible
  AND recipient / tenant / permission remain valid

REVOKED:
  revokedAt != null

EXPIRED:
  now >= expiresAt

NOT_YET_VALID:
  now < validFrom
```

You can record `revokedAt` instead of deleting rows to preserve audit history. When revoking, update inside a transaction and verify the caller is authorized to revoke (owner, grantor, or properly scoped admin). Admin endpoints must never accept `grantId` and revoke another tenant's grant without object-level authorization.

**Note:** `revokedAt != null` indicates revoked; if the design supports scheduling future revocations, use a separate field or compare `now >= revokedAt` consistently. This lesson's examples use **immediate revocation**, so any non-null `revokedAt` is invalid.

### Ownership Changes Can Also Invalidate Shares

If a Document transfers ownership, is deleted, moves tenants, is reclassified higher, or its project is archived, old grants may no longer be appropriate. Policy can:

- Automatically revoke all grants on ownership/tenant changes.
- Restrict to a subset of actions.
- Require the new owner to reconfirm shares.
- Block all grants on deleted/locked documents.
- Retain history for auditing without granting access.

Remaining lifetime is no proof of access if domain state has changed.

## 7. Spring Security: Protecting Both Endpoints and Services

A document read endpoint:

```http
GET /api/documents/42
Authorization: Bearer <bob-access-token>
```

The HTTP layer can require authentication. Yet checking whether Bob holds an active grant on Document #42 belongs in **service/domain authorization**, because services can also be called by message consumers, batches, or other controllers.

Simple Servlet Security configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.web.builders.HttpSecurity;
import org.springframework.security.web.SecurityFilterChain;

@Configuration
public class HttpSecurityConfig {
    @Bean
    SecurityFilterChain apiSecurity(HttpSecurity http) throws Exception {
        http.authorizeHttpRequests(auth -> auth
            .requestMatchers("/api/documents/**").authenticated()
            .anyRequest().denyAll()
        );
        return http.build();
    }
}
```

This is a **partial configuration**: real applications need authentication mechanisms, CSRF/CORS, exception handling, and other endpoints per requirements. `authenticated()` only blocks unauthenticated requests; **it does not verify permission on ID 42**.

Enable method security:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfiguration {
}
```

And invoke a Java policy bean from `@PreAuthorize`:

```java
@PreAuthorize(
    "hasAuthority('document:read') and " +
    "@sharingPolicy.canRead(authentication, #documentId)"
)
public DocumentView read(@P("documentId") Long documentId) {
    // Executes only after the policy grants access.
}
```

This is a **method fragment**, requiring `@PreAuthorize`, `@P`, and domain class imports. `@P("documentId")` helps Spring Security resolve the parameter in SpEL; alternatively, compile with `-parameters` per the official guide.

**Clear rule:** grant recipients may still require the functional authority `document:read` first; receiving a share does not automatically grant a global authority. If the product has external guests without that authority, design a dedicated guest/capability policy; never drop authentication/authorization without evaluating the threat model.

## 8. Designing the Model and Repository for Sharing Grants

The component classes below target Spring Boot + Spring Security + Spring Data JPA, Java 17+. They are **not** a standalone `javac` program. Your project must define the entities, database schema, JWT/principal mapping, transactions, and repositories.

A concise conceptual entity:

```java
@Entity
@Table(name = "document_share_grants")
public class DocumentShareGrant {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private Long documentId;
    private String tenantId;
    private String grantorSubjectId;
    private String recipientSubjectId;

    @Enumerated(EnumType.STRING)
    private SharePermission permission;

    private Instant validFrom;
    private Instant expiresAt;
    private Instant revokedAt;

    // Constructors, getters, setters, validation, and indexes
    // defined by the application to match the schema.
}
```

`SharePermission` can be:

```java
public enum SharePermission {
    READ, COMMENT, EDIT, DOWNLOAD
}
```

This is an **entity outline** to show fields; do not copy standalone without Jakarta Persistence/`Instant` imports, constructors, getters/setters, and migrations. Even with `tenantId` on the grant, checks must still verify the **real document's** tenant and membership/external-share settings: never trust a cross-tenant grant row.

### Repository Querying Only Currently Active Grants

A Spring Data JPA derived query:

```java
import java.time.Instant;
import org.springframework.data.jpa.repository.JpaRepository;

public interface DocumentShareGrantRepository
        extends JpaRepository<DocumentShareGrant, Long> {

    boolean existsByDocumentIdAndTenantIdAndRecipientSubjectIdAndPermissionAndRevokedAtIsNullAndValidFromLessThanEqualAndExpiresAtGreaterThan(
        Long documentId,
        String tenantId,
        String recipientSubjectId,
        SharePermission permission,
        Instant atOrAfterValidFrom,
        Instant beforeExpiresAt
    );
}
```

The method name is long, yet accurately expresses the predicates:

```sql
SELECT EXISTS (
    SELECT 1
    FROM document_share_grants g
    WHERE g.document_id = :document_id
      AND g.tenant_id = :verified_tenant
      AND g.recipient_subject_id = :subject
      AND g.permission = :permission
      AND g.revoked_at IS NULL
      AND g.valid_from <= :now
      AND g.expires_at > :now
);
```

The SQL above is a **logical model**; exact `SELECT EXISTS (...)` syntax and column types depend on your DB. The derived query passes **the exact same `Instant` `now` to both time parameters**, never sampling the clock twice across different contexts. For multi-permission rules (whether EDIT implies READ or not), define them explicitly and update the query/policy rather than assuming `EDIT` equals `READ`.

For query performance, consider indexing `(document_id, recipient_subject_id, permission)` along with tenant and revoked/time columns per your DB and workload. Never treat indexes as security barriers; DB constraints, FKs, and transactions govern data integrity.

### Why Keep Grants in the Database When Immediate Revocation Is Needed?

If the application embeds all share permissions inside a self-contained JWT and validates only signature/`exp`, the server may **not know** the grant was revoked early. With a database grant store, each policy evaluation can observe the new `revokedAt`. That adds queries, yet satisfies revocation requirements.

Any caching requires invalidation/TTLs and consistency matching your SLA: you cannot cache grants unchecked for 30 minutes while promising sub-second revocation across all nodes.

## 9. SharingPolicy: Reading the Right Resource, Actor, and Time

Application-defined identity contract:

```java
public record ActorScope(
    String subjectId,
    String tenantId,
    boolean active
) {}

public interface CurrentActorService {
    ActorScope requireVerifiedActor();
}
```

`CurrentActorService` is an **application service**, not a standard Spring Security class. It must pull identity from a trusted `Authentication`/SecurityContext, verify subject and tenant membership, check account status, and reject if valid data is missing. Never return an `ActorScope` built from a client-supplied JSON `userId` or `X-Tenant-Id` header.

An illustrative policy bean:

```java
import java.time.Clock;
import java.time.Instant;
import org.springframework.security.core.Authentication;
import org.springframework.stereotype.Component;

@Component("sharingPolicy")
public class SharingPolicy {
    private final DocumentRepository documents;
    private final DocumentShareGrantRepository grants;
    private final CurrentActorService actors;
    private final Clock clock;

    public SharingPolicy(
            DocumentRepository documents,
            DocumentShareGrantRepository grants,
            CurrentActorService actors,
            Clock clock) {
        this.documents = documents;
        this.grants = grants;
        this.actors = actors;
        this.clock = clock;
    }

    public boolean canRead(Authentication auth, Long documentId) {
        if (auth == null || !auth.isAuthenticated()
                || documentId == null || documentId <= 0) {
            return false;
        }

        // Actor is verified from the real server SecurityContext;
        // not merely from auth.getName() or a request parameter.
        ActorScope actor = actors.requireVerifiedActor();
        if (!actor.active()) {
            return false;
        }

        var document = documents
            .findByIdAndTenantIdAndDeletedFalse(
                documentId, actor.tenantId())
            .orElse(null);

        if (document == null) {
            return false;
        }

        // Owner can read if business policy permits.
        if (actor.subjectId().equals(document.getOwnerSubjectId())) {
            return true;
        }

        Instant now = clock.instant();

        return grants
            .existsByDocumentIdAndTenantIdAndRecipientSubjectIdAndPermissionAndRevokedAtIsNullAndValidFromLessThanEqualAndExpiresAtGreaterThan(
                documentId,
                actor.tenantId(),
                actor.subjectId(),
                SharePermission.READ,
                now,
                now
            );
    }
}
```

**This is illustrative integration code**, requiring `DocumentRepository`, a `Document` entity with `getOwnerSubjectId()` and `findByIdAndTenantIdAndDeletedFalse`, a `Clock` bean, and a real security context. Ensure `CurrentActorService` and `auth` represent the same principal; if an untrusted internal API passes an `Authentication` while the actor service reads a different context, an actor mismatch can create a vulnerability. An alternative design lets the actor service accept the verified `Authentication` directly and construct `ActorScope` from it under a clear contract.

With this policy:

- Deleted documents or documents in another tenant are denied.
- Owners get READ per the sample rule.
- Other recipients need an active, unrevoked READ grant.
- An EDIT grant does not implicitly grant READ unless the enum/policy defines inheritance.
- Inactive accounts cannot access.
- Cross-tenant external sharing is **not yet supported** in the sample; it requires dedicated recipient identity and domain policies.

**Note on anonymous users:** `Authentication.isAuthenticated()` alone does not guarantee a real logged-in user (anonymous tokens can report authenticated); `CurrentActorService.requireVerifiedActor()` must reject anonymous/unsupported auth, or the policy must check explicitly with a trust resolver. Never remove that check just to make a demo pass with incomplete `MockUser` fixtures.

### Configuring Clock

```java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ClockConfiguration {
    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
```

In tests, substitute `Clock.fixed(...)` or a mock/injected `Clock`. This yields **deterministic boundary tests without real sleeps**. Production servers must keep cluster clocks synchronized.

## 10. Wiring SharingPolicy to a Scoped Service and Repository

Service receiving an ID from the caller:

```java
import org.springframework.security.access.method.P;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;

@Service
public class DocumentReadService {
    private final DocumentRepository documents;
    private final CurrentActorService actors;

    public DocumentReadService(
            DocumentRepository documents, CurrentActorService actors) {
        this.documents = documents;
        this.actors = actors;
    }

    @PreAuthorize(
        "hasAuthority('document:read') and " +
        "@sharingPolicy.canRead(authentication, #id)"
    )
    public DocumentView read(@P("id") Long id) {
        ActorScope actor = actors.requireVerifiedActor();

        // Defense-in-depth: never call an unscoped findById.
        var doc = documents
            .findByIdAndTenantIdAndDeletedFalse(id, actor.tenantId())
            .orElseThrow(() -> new ResourceNotVisibleException());

        return new DocumentView(doc.getId(), doc.getTitle());
    }

    public record DocumentView(Long id, String title) {}
}
```

`ResourceNotVisibleException` is an **application-defined business exception**, mapped to a neutral 404 when hiding existence; it is not a built-in Spring Security class. This snippet will not run standalone without the application classes.

**Important boundary:** `@PreAuthorize` executes **before** the service method body; it may evaluate the grant in a different transaction/moment than the actual fetch. For data with strict revocation requirements, a permission could be revoked between check and read. Therefore:

- Consider performing **resource lookup and authorization decision within the same service transaction**.
- Use transactions/isolation/locking or queries binding grants and documents together per consistency needs.
- Return data in the response only after all conditions are verified.
- Never treat an out-of-transaction `@PreAuthorize` as an atomic guarantee against revocation.
- If the goal is standard read security, pre-method policy + tenant-scoped query is a solid defense layer, provided the real revocation SLA is defined.

If documents also carry full ACL records or project/folder sharing permissions, the policy must evaluate all active constraints. Never use an unscoped `findById` and return the entity simply because some grant ID "had the same number".

## 11. Creating Grants and Verifying the Grantor Holds SHARE Permission

Grants must never be written via an endpoint letting the caller pick `grantorId`, `tenantId`, or `createdAt`. A share-creation service must handle:

```text
Authenticated grantor
  -> resource exists in verified tenant
  -> grantor has SHARE / delegable permission
  -> recipient valid and authorized to receive
  -> permission subset allowed
  -> duration <= policy maximum
  -> validFrom < expiresAt
  -> idempotency/duplication rules
  -> database insert in transaction
  -> audit & notify after commit
```

Illustrative method pattern:

```java
@Transactional
@PreAuthorize("hasAuthority('document:share')")
public ShareView grantRead(
        Long documentId,
        String recipientSubjectId,
        Instant requestedExpiry) {

    ActorScope actor = actors.requireVerifiedActor();
    Document document = documents
        .findByIdAndTenantIdAndDeletedFalse(
            documentId, actor.tenantId())
        .orElseThrow(ResourceNotVisibleException::new);

    if (!document.getOwnerSubjectId().equals(actor.subjectId())) {
        throw new AccessDeniedException("Sharing not permitted");
    }

    recipients.requireActiveMember(
        recipientSubjectId, actor.tenantId());

    Instant now = clock.instant();
    Instant upper = now.plus(Duration.ofHours(24));

    if (requestedExpiry == null
            || !requestedExpiry.isAfter(now)
            || requestedExpiry.isAfter(upper)) {
        throw new InvalidSharingPeriodException();
    }

    DocumentShareGrant grant = new DocumentShareGrant();
    grant.setDocumentId(documentId);
    grant.setTenantId(actor.tenantId());
    grant.setGrantorSubjectId(actor.subjectId());
    grant.setRecipientSubjectId(recipientSubjectId);
    grant.setPermission(SharePermission.READ);
    grant.setValidFrom(now);
    grant.setExpiresAt(requestedExpiry);
    grant.setRevokedAt(null);

    DocumentShareGrant saved = grants.save(grant);
    return new ShareView(saved.getId(), saved.getExpiresAt());
}
```

This is a **method fragment**: `recipients`, `grants`, `documents`, `actors`, `clock`, DTOs/exceptions/`Duration`/imports, and entity setters must be declared by the application. It demonstrates an **owner-only SHARE** policy, not automatically granting editors share rights or external guest access. The 24-hour cap is an **example**, not a limit set by Spring Security.

In systems supporting re-sharing (subdelegation), checking only the owner is too strict; replace with a tiered delegation policy while constraining scope, duration, recipients, and permissions **never to exceed the parent grant**. If an issuer is revoked, you may need to cascade-revoke all downstream grants along the delegation chain; a `parentGrantId` or authorization graph helps track this.

### Do Not Allow Editing a Grant to Extend Forever

A `PATCH /shares/{grantId}` also needs authorization on **both the grant and the real resource**. Reject `expiresAt=2099` when the max duration is 24 hours. Each renewal may require grantor reauthorization and checking current document/recipient status. Decide whether revoked grants may be reactivated; a safe design typically issues a new grant with a new ID instead of quietly toggling a revoked grant back on.

## 12. Revoking Grants and Protecting the Revocation Endpoint

Scenario:

```http
DELETE /api/documents/42/shares/9001
Authorization: Bearer <alice-token>
```

Do not just look up `grantId=9001` and delete it: an attacker could swap IDs to revoke someone else's or another tenant's grant. The server must verify:

- Grant 9001 belongs to Document 42 from the URL.
- Document 42 belongs to the verified tenant.
- Caller is the owner/grantor or an authorized admin in that scope.
- Revocation idempotency rules are defined; repeated requests never accidentally re-grant.
- State change commits and caches/authorization views invalidate within SLA.

Equivalent SQL example:

```sql
UPDATE document_share_grants
SET revoked_at = :now
WHERE id = :grant_id
  AND document_id = :document_id
  AND tenant_id = :verified_tenant
  AND revoked_at IS NULL
  AND EXISTS (
      SELECT 1
      FROM documents d
      WHERE d.id = document_share_grants.document_id
        AND d.tenant_id = :verified_tenant
        AND d.owner_subject_id = :actor_subject
  );
```

The SQL above is **illustrative**, without assuming identical `UPDATE ... EXISTS` syntax across all DBs. Real systems may include grantor/admin permissions and other rules. What matters is enforcing resource/tenant/actor conditions **right in the update**, rather than merely checking a self-declared grant ID.

If the update affects 0 rows, the grant may not exist, may already be revoked, or the actor lacks permission. The API can return idempotent `204` or neutral `404` per contract; never let responses distinguish another tenant's grant if that existence is confidential.

## 13. Spring ACL: Expiration Is Not Built Into ACEs

Spring Security ACL models:

- `ObjectIdentity`: domain object.
- `Sid`: principal or authority receiving permission.
- `Permission`: action bitmask.
- `AccessControlEntry`: granting/denying entry for SID+permission on an ACL.
- `Acl.isGranted(...)`/`PermissionGrantingStrategy`: evaluates ACEs.

Example inserting a READ ACE for Bob:

```java
acl.insertAce(
    acl.getEntries().size(),
    BasePermission.READ,
    new PrincipalSid("bob"),
    true
);
aclService.updateAcl(acl);
```

This is a **fragment**, requiring `MutableAcl`, `MutableAclService`, and an existing ACL. By default, Bob's READ ACE **knows nothing about `expiresAt`**. If the application also stores a time-limited `ShareGrant`, ensure **both layers stay coordinated**:

- If the READ ACE still exists after the `ShareGrant` expires, will plain `hasPermission(...)` still let Bob read? **Yes, possibly**, if the ACE still grants and no extra time condition runs.
- If the application uses only the grant store and a custom policy, ACEs might not need to be created for each share.
- If syncing grants into ACLs, on expiry/revocation either remove the ACE or enforce time-window checks before allowing; a delayed cleanup job must never leave an unauthorized access window open.

**Recommendation:** pick a single **source of truth** for sharing grants; if integrating with ACLs, avoid two permission stores drifting out of sync. Relying solely on scheduled cleanup to remove ACEs does not guarantee exact-time expiration—jobs can lag, fail, or another node may still hold a stale ACL cache.

## 14. Share Links and Bearer Capabilities

Not every share goes to a logged-in account. Some products issue URLs:

```text
https://example.invalid/share/<opaque-secret>
```

This token/link is typically a **bearer capability**: anyone holding the secret can exercise the link's capabilities within its designed scope. It differs from `recipientSubjectId=bob`, where the server always knows Bob is authenticated.

### Designing a Safe Link

1. Generate tokens with a **CSPRNG** and high entropy; use opaque strings, never incrementing `documentId`s or Base64-encoded IDs.
2. Store only a **hash of the token** in the database where possible; compare safely and never log raw tokens.
3. Bind the token to **one resource ID** and a specific permission like `DOWNLOAD`.
4. Store `validFrom`, `expiresAt`, `revokedAt`, and optional limits.
5. Enforce HTTPS; never leak tokens into analytics, logs, cross-domain referrers, or public messages.
6. Set appropriate response headers/`Referrer-Policy` to prevent URL token leakage.
7. Apply rate limiting and token-guessing detection on public endpoints.
8. Define immediate revocation via datastore/token denylist when needed.
9. Never embed client-trusted owner/tenant/permissions in tokens; even signed claims must verify scope, issuer, audience, and revocation per model.
10. Consider requiring recipient login, a second password/OTP, or IP restrictions for sensitive documents.

For example, hashing an opaque token with SHA-256 can be reasonable when the token has sufficient entropy; never substitute fast hashes for password hashing on **user-chosen passwords**. For short/predictable link tokens, hashing cannot fix weak source entropy.

### Presigned URLs to Object Storage

S3/GCS presigned URLs typically allow direct downloads from storage until the URL expires or credentials/policies invalidate it. If Alice revokes a grant in the database while Bob already holds an unexpired presigned URL, Bob **may still be able to download** if storage is unaware of the revocation.

If the requirement is "revocation takes effect immediately":

- Use a backend download endpoint checking the grant on every request, or
- Use ultra-short-lived presigned URLs with the residual window explicitly documented, or
- Apply appropriate storage-level revocation mechanisms.

Never promise every issued link becomes invalid immediately just because `revokedAt` was set in the application DB.

## 15. Delegated Authorization and OAuth2/JWT: Different Lifetimes

The word "delegation" sometimes refers to **resource sharing** between two users, and other times to **OAuth 2.0 delegated access** for a third-party app. They are related yet **not identical**.

Example:

- Alice grants a reporting app the `reports:read` scope.
- The Authorization Server issues an access token with scope, audience, and expiry.
- Spring Security's Resource Server verifies the token and scopes.
- When the API receives `GET /documents/42`, the server must still check **whether Alice or the app is allowed to read Document 42** if data is authorized per object.

An active access token does not automatically make every document accessible. JWT claims can carry scopes and token lifetime, whereas per-object sharing permissions change more dynamically.

### `exp`, `nbf`, `iat`

In JWTs:

- `exp`: token **must not be accepted at or after** expiration; `now < exp`.
- `nbf`: token must not be accepted before start time; `now >= nbf`.
- `iat`: issued-at time; **does not automatically determine** grant duration.
- `aud` and `iss`: restrict audience and issuer; must be validated per configuration.

Spring Security OAuth2 Resource Server validates signatures, issuers, and `exp`/`nbf` when configured properly. Clock skew for token validation can be configured on the validator. However, **object-level permissions must still be checked at the resource server**.

### Revoking Before JWT Expiration

Self-contained signed JWTs remain verifiable until `exp` even after a database share grant is revoked. Options:

1. Query the ACL/grant DB on every request to determine current permissions.
2. Short-lived access tokens plus revocable refresh tokens, accepting the bounded propagation window.
3. Introspection/opaque tokens or a mutable authorization decision service.
4. Denylists or authorization versions/epochs checked at runtime.
5. Revoke permissions at the API, not only at token issuance.

**Do not** assume changing a password or logging out instantly invalidates all issued JWTs and presigned URLs. That depends on token validation, denylists, sessions, and provider mechanisms.

## 16. Time-Based Authorization and SQL Queries

For named-recipient grants, a sound query can check:

```sql
SELECT d.id, d.title
FROM documents d
WHERE d.id = :document_id
  AND d.tenant_id = :verified_tenant
  AND d.deleted = FALSE
  AND (
       d.owner_subject_id = :authenticated_subject
       OR EXISTS (
           SELECT 1
           FROM document_share_grants g
           WHERE g.document_id = d.id
             AND g.tenant_id = d.tenant_id
             AND g.recipient_subject_id = :authenticated_subject
             AND g.permission = 'READ'
             AND g.revoked_at IS NULL
             AND g.valid_from <= :now_utc
             AND g.expires_at > :now_utc
       )
  );
```

This is a **logical SQL pattern** to map to your exact schema/DB; also constrain account status, tenant membership, and other business fields as required. Placing the owner/share check inside **the same data query** reduces check-then-broad-query mistakes.

**Advantage:** once a permission/share expires, the query returns no object; for sensitive data, this condition provides defense in depth alongside `@PreAuthorize`.

**Caution:** If a query runs at `now=09:59:59` and returns data at `10:00:01`, "expiring at 10:00" does not retroactively pull back already-read content. Define the policy at **decision time** and rules for streaming/long-running operations. Interrupting an in-flight download at the exact boundary requires explicit stream-cancellation machinery; most APIs mean "permissions are checked when the operation starts" rather than continuous byte-by-byte policing.

### Updates Must Have Dedicated Conditions

A READ grant is insufficient for WRITE. With temporary EDIT grants:

```sql
UPDATE documents d
SET title = :new_title
WHERE d.id = :document_id
  AND d.tenant_id = :verified_tenant
  AND d.deleted = FALSE
  AND EXISTS (
      SELECT 1
      FROM document_share_grants g
      WHERE g.document_id = d.id
        AND g.tenant_id = d.tenant_id
        AND g.recipient_subject_id = :authenticated_subject
        AND g.permission = 'EDIT'
        AND g.revoked_at IS NULL
        AND g.valid_from <= :now_utc
        AND g.expires_at > :now_utc
  );
```

This is an **SQL model**, not guaranteeing every DB supports identical `UPDATE ... alias ... EXISTS` syntax; use a correlated subquery/CTE or matching repository update. Add functional authority checks, optimistic versioning, status checks, field-level authorization, auditing, and proper transactions.

If the update affects 0 rows, never assume access; map 404/403/409 per the API contract without leaking resource existence. For critical operations, keep permission predicates tight inside the write statement to minimize TOCTOU.

## 17. Time and Caching: Where Expired Permissions Accidentally Linger

Suppose Bob reads Document #42 at 09:59 and the system caches `canRead(bob,42)=true` for 15 minutes. At 10:00 the grant expires, yet the cache keeps returning true until 10:14. This is an authorization caching bug.

**Never cache GRANT decisions without bounding by valid lifetime.** If caching:

```text
positiveTTL <= min(
    configuredMaxTTL,
    expiresAt - now,
    allowed revocation propagation delay
)
```

Even this formula handles only **expiry**, not mid-window revocation unless paired with event invalidation or checking the source of truth on every request. For sensitive data, consider not caching grant decisions, or caching at the grant-object layer while re-checking time bounds, `revokedAt`, and versions.

Other traps:

- Cache key contains only `documentId`, omitting `subjectId`/`tenantId`/`permission`.
- Admin cache served to regular users.
- Cached grants surviving after document ownership transfer or deletion.
- Search indexes/listings/count caches returning previously shared objects that have since expired.
- Browser/CDN caching a shared document as public content.
- Frontend retaining pre-revocation downloaded data: the server cannot recall data that already left the system.

If temporary sharing involves high confidentiality, also evaluate downloaded/copied data, offline access, watermarking, and terms of use; authorization only blocks **future access**, not copies already received.

## 18. Short Lifetimes, Long Operations, and Races

Concurrency cases to design proactively:

### 18.1. Grant Revoked Between Check and Response

```text
T1: check grant -> true
T2: owner revokes grant
T1: database read / stream response
```

If the system requires "no new reads after revocation commits", consider transaction snapshots, locks/versions, or unified permission + data queries. To **abort in-flight requests**, add dedicated tracking/cancellation and define ordering guarantees.

### 18.2. Grant Expires Mid-Transaction

An update request starts at `09:59:59` and commits at `10:00:01`. Is permission evaluated at start, at the UPDATE statement, or at commit? Frameworks do not choose one answer for you. Document the decision timestamp explicitly and share one `Instant`/isolation across bundled operations. For financial or sensitive data, re-check near commit or use reliable atomic DB predicates.

### 18.3. Concurrent Renewal and Revocation

If Alice revokes a grant while Bob or another authorized actor renews it, establish policy:

- Revocation is terminal (no reactivation).
- Renewing after revocation must create a new grant.
- Optimistic locking/versioning prevents last-write-wins from accidentally re-enabling access.
- Audit logs record who modified, when, and which request triggered the change.

### 18.4. Delegation Chains

Alice delegates to Bob until 10:00; Bob re-shares with Carol until 11:00. If subdelegation is allowed, Carol **must not hold access longer than Bob** unless backed by an independent valid authority/approval. Lifetime constraints can be:

```text
child.expiresAt <= parent.expiresAt
child.permissions subsetOf parent.delegablePermissions
child.resourceId == parent.resourceId
parent.revoked => child ineffective (per policy)
```

If supporting cascading revocation, store `parentGrantId` and walk the chain on authorization or run safe cascade updates. Avoid delegation cycles and mechanisms where "a recipient re-grants to themselves" indefinitely.

## 19. External Sharing, Invitations, and Enumeration Protection

Internal named-recipient grants usually rely on an existing `recipientSubjectId`. Email sharing, however, can occur before the recipient creates an account. Distinguish:

- **Invitation**: an unaccepted invite; does not automatically grant document access to any identity yet.
- **Accepted grant**: the recipient has proved ownership of the identity/email via an approved flow and the grant binds to a stable subject.
- **Public/bearer link**: a secret conveying bounded capabilities without assuming knowledge of an account identity.

If Alice enters `bob@example.test`:

1. Server only lets Alice invite under a valid SHARE policy.
2. An email alone does not prove the clicker is Bob if the link can be forwarded.
3. Invites carry high-entropy tokens, short TTLs, and action restricted to ACCEPT.
4. If login is required, verify matching email/identity after login per security rules.
5. On accept, create a grant bound to the real subject; log audit without exposing whether accounts exist.
6. Never grant access merely because a `recipientEmail` appears in the request.

In responses, use neutral messages when an email has no account to prevent user enumeration. Do not accidentally leak document lists or tenants via email metadata, URL previews, or redirects.

## 20. Standalone Java 17 Example: Expiration and Revocation

This program **uses no Spring Security/DB**. It illustrates grant rules by identity, object ID, action, tenant, half-open validity window, and revocation. The clock is fixed with `Clock.fixed` for deterministic stdout and instant execution without `Thread.sleep`.

Create `TimedShareGrantDemo.java`:

```java
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.Set;

public class TimedShareGrantDemo {

    record Actor(String id, String tenant, Set<String> authorities) {}
    record Document(long id, String tenant, String owner, boolean deleted) {}
    record Grant(long documentId, String recipient, String permission,
                 Instant validFrom, Instant expiresAt, Instant revokedAt) {}

    static boolean allowed(Actor actor, Document document,
                           String permission, Instant now, Grant grant) {
        if (actor == null || document == null || document.deleted()
                || !actor.tenant().equals(document.tenant())
                || !actor.authorities().contains("document:"
                    + permission.toLowerCase())) {
            return false;
        }

        if (actor.id().equals(document.owner())) {
            return true;
        }

        return grant != null
            && grant.documentId() == document.id()
            && grant.recipient().equals(actor.id())
            && grant.permission().equals(permission)
            && grant.revokedAt() == null
            && !now.isBefore(grant.validFrom())
            && now.isBefore(grant.expiresAt());
    }

    public static void main(String[] args) {
        Instant start = Instant.parse("2026-11-05T09:00:00Z");
        Clock clock = Clock.fixed(start, ZoneOffset.UTC);

        Actor alice = new Actor("alice", "tenant-a",
            Set.of("document:read", "document:edit"));
        Actor bob = new Actor("bob", "tenant-a",
            Set.of("document:read", "document:edit"));
        Actor carol = new Actor("carol", "tenant-b",
            Set.of("document:read"));
        Document document = new Document(42, "tenant-a", "alice", false);

        Grant readGrant = new Grant(
            42, "bob", "READ", clock.instant(),
            clock.instant().plusSeconds(300), null);

        System.out.println("Bob at start: " + allowed(
            bob, document, "READ", start, readGrant));
        System.out.println("Bob before expiry: " + allowed(
            bob, document, "READ",
            start.plusSeconds(299), readGrant));
        System.out.println("Bob at expiry: " + allowed(
            bob, document, "READ",
            start.plusSeconds(300), readGrant));
        System.out.println("Bob cannot edit: " + allowed(
            bob, document, "EDIT",
            start.plusSeconds(60), readGrant));

        Grant revoked = new Grant(
            42, "bob", "READ", start,
            start.plusSeconds(300), start.plusSeconds(120));
        System.out.println("Bob after revocation: " + allowed(
            bob, document, "READ",
            start.plusSeconds(121), revoked));

        System.out.println("Carol other tenant: " + allowed(
            carol, document, "READ",
            start.plusSeconds(60), readGrant));
        System.out.println("Alice owner: " + allowed(
            alice, document, "READ",
            start.plusSeconds(300), null));
    }
}
```

Run on JDK 17 or later:

```bash
javac TimedShareGrantDemo.java
java TimedShareGrantDemo
```

Exact stdout:

```text
Bob at start: true
Bob before expiry: true
Bob at expiry: false
Bob cannot edit: false
Bob after revocation: false
Carol other tenant: false
Alice owner: true
```

Explanation:

- Bob gets READ at `validFrom`, and immediately before `expiresAt`.
- Exactly at `expiresAt`, Bob is denied because `now < expiresAt` no longer holds.
- A READ grant does not grant EDIT even though Bob holds functional authority `document:edit`.
- A grant with `revokedAt` set is no longer active (example code models immediate revocation).
- Carol in another tenant is denied despite knowing the right document ID and holding READ authority.
- Alice is the owner and keeps READ per the sample policy; ownership is not treated as an auto-expiring share grant.

**Simulation limits:** there is no AOP, JWT, database, concurrency, cache, or logic governing who can issue grants. `allowed` describes **access policy**, not **grant issuance/revocation policy**. Production must combine Spring Security/DB, account-state checks, tenant memberships, transactions, and the revocation mechanisms described above.

## 21. Comprehensive Testing: Time, Identity, Permissions, and Revocation

### 21.1. Time-Based Decision Table

Use `Clock.fixed(...)` in tests and inject it into the policy.

| Timestamp | Grant State | Expectation |
| --- | --- | --- |
| `now < validFrom` | Not started | DENY |
| `now == validFrom` | Starts | GRANT if other conditions hold |
| `validFrom < now < expiresAt` | Within window | GRANT if not revoked |
| `now == expiresAt` | Exact expiry boundary | DENY |
| `now > expiresAt` | Expired | DENY |
| `revokedAt != null` | Revoked | DENY |
| `expiresAt <= validFrom` | Invalid grant | Refuse to create grant |
| `expiresAt == null` | No end boundary | DENY or reject per mandatory-expiry policy |
| Clock drift across nodes | Inconsistent | Check time source and SLA |
| Cache retains grant past expiry | Stale allow | DENY, never rely on stale positive cache |

### 21.2. Actor, Resource, and Action Decision Table

| Scenario | Expectation |
| --- | --- |
| Bob has READ grant for #42 and is authenticated | Allow READ within window |
| Bob has READ grant for #42 but requests EDIT | Deny EDIT |
| Bob has READ grant for #42 but calls #43 | Deny on #43 |
| Carol in another tenant, no external grant policy | Deny |
| Alice is owner yet account is locked | Deny per account state |
| Document deleted/archived/classified | Deny or apply new rule; don't look only at grant |
| Another user guesses grantId | Cannot use or revoke a grant they don't control |
| Grantor lacks SHARE | Refuse to create grant |
| Invalid recipient | Do not create grant |
| Grantor tries to grant permission beyond scope | Do not create grant |
| Grantor sets expiry beyond max limit | Reject |
| Owner revokes grant while recipient has screen open | New access denied within SLA; handle already-loaded data separately |
| One HTTP route has method security, another calls same service | All entry paths enforce policy |
| Batch with multiple document IDs | Check grant for **every ID**; never authorize whole batch from one grant |

### 21.3. Testing Real Spring Security

Do not just invoke `SharingPolicy.canRead(...)` in a unit test. Write integration tests with:

- `@EnableMethodSecurity` actually enabled.
- Spring-managed service proxies; avoid testing only via `new DocumentReadService(...)`.
- `MockMvc` or HTTP client running the security filter chain.
- `@WithMockUser`/JWT fixtures matching the application's **real** identity model.
- Separate test DB holding distinct Documents and ShareGrants.
- Swappable `Clock.fixed(...)`.
- Assertions on returned data, body, status, updated rows, and side effects.
- Guest/anonymous/JWT `exp`, `nbf`, and wrong issuer/audience cases.
- Revoking in one request, then reading in another, including across **different nodes** in clusters.

Testing revocation "right after save" is not enough if caches still serve reads. Test updates/revocations with a warm cache and verify access drops on every instance.

### 21.4. Concurrency Testing

Write a two-thread/two-transaction test:

1. Bob's request begins reading.
2. Alice revokes the grant.
3. Database commits the revocation.
4. Bob sends a new request after commit.
5. Verify the new request is denied within the promised SLA.

For writes, test an EDIT grant expiring right during UPDATE/commit. Verify the DB is not mutated without permission and no event/file is published when the write fails. If business requires serializable authorization, use appropriate transactions/isolation/locking or SQL predicates; never expect default `@Transactional` to solve every race.

## 22. Common Mistakes

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Setting `share=true` on Document and letting everyone read | No tracking of who, action, or duration | Store grants by recipient, resource, permission, and time |
| Checking only Bob's `USER` role | Bob can view others' documents | Check exact document ID and grant |
| Accepting `grantorId` from JSON | Caller impersonates owner | Derive grantor from verified Authentication |
| Letting a READ-only user issue an ADMIN grant | Privilege escalation | Require SHARE and bound delegable permissions |
| Accepting arbitrary `expiresAt` from client | Infinite sharing | Bound by server policy, reject invalid values |
| Comparing `now <= expiresAt` | Still grants access right at expiration | Use `now < expiresAt` |
| Trusting client device clock | Users tweak system clock | Server `Instant`/`Clock`, synchronized time |
| Using timezone-less `LocalDateTime` | Wrong expiry across DST/timezones | Store `Instant`/UTC, convert in UI |
| Waiting for a cron job to delete expired grants | Delayed jobs leave access open | Evaluate expiry live on every authorization check |
| Setting JWT TTL and assuming the share has that TTL | Tokens and grants have distinct lifetimes | Check grants independently with revocation |
| Revoking in DB while caching GRANT for 30 minutes | Post-revocation access persists | Invalidate and design consistency/SLA |
| Issuing long-lived presigned URLs while claiming instant revocation | Links keep working until expiry | Brokered downloads or ultra-short URLs + storage policy |
| Creating READ ACE without checking expiration | ACE stays valid past expiry | Use grant/policy as source of truth; revoke ACE/cache on time |
| Relying on share ID for authentication | IDs are guessable and not secrets | Require verified identity or opaque CSPRNG tokens |
| Logging bearer links in logs/analytics | Secrets leaked | Redact logs, restrict referrers, enforce TTL/revocation |
| Checking SHARE on Document #42 yet creating grant for #43 | IDOR in permission management | Enforce same resource ID throughout the transaction |
| Allowing subdelegation past parent grant expiry | Unintended lifetime extension | Child expiry <= parent, cascade revoke |
| Issuing READ grant and returning all entity properties | Sensitive data leaked | Allowlist DTOs and field-level authorization |
| Protecting only GET, skipping DOWNLOAD/EXPORT/EDIT | Grants bleed into other actions | Enforce action-specific policies |
| Ignoring account/document status | Grants stay active after lock/delete | Check account, resource, tenant, and classification |
| Using `@PostAuthorize` to protect writes | Side effects may commit beforehand | Pre-check + conditional mutation + transaction |
| Omitting tenant/recipient from cache keys | Cross-user/tenant leaks | Fully scoped keys or auth on every cache hit |
| Swallowing DB timeouts and returning ALLOW | Fail open | Fail closed by default, handle infrastructure errors separately |

## 23. Checklist When Designing Temporary Sharing

1. **Which resource?** Type, ID, tenant, owner, parent, and status.
2. **Who is the sharer?** Verified identity, SHARE permission, and delegable scope.
3. **Who is the recipient?** Authenticated subject, group, external guest, or bearer link; matching verification model.
4. **Which action is granted?** READ, COMMENT, EDIT, DOWNLOAD; constrain and declare explicitly.
5. **When does it start and end?** `[validFrom, expiresAt)`, UTC `Instant`, max duration.
6. **Can it be revoked immediately?** Revocation update mechanism and propagation SLA.
7. **Which events alter permissions?** Document deletion, owner transfer, account suspension, tenant removal.
8. **Is subdelegation allowed?** Depth, `parentGrantId`, permission/expiry ceiling, cascade revocation.
9. **What is the source of truth?** ShareGrant DB, ACL, or capability token; avoid unsynced overlap.
10. **Is caching safe?** Expiry-aware, revoke-aware, keyed by principal/tenant/action/resource.
11. **Are tokens/links secret?** CSPRNG, hashed storage, TTL, rate limits, redaction, security headers.
12. **Are file presigned URLs used?** Understand revocation limits and TTL after URL issuance.
13. **Which entry paths need checks?** HTTP, GraphQL, messages, batches, search, exports, streaming.
14. **Are queries scoped?** Never `findById` alone or trusting client-supplied grant IDs.
15. **Are writes atomic?** Transactions, conditional SQL, races/revocation.
16. **Is auditing present?** Grantor, recipient, permission, expiry, revocation, reason; never log secrets.
17. **Are exact time boundaries tested?** Before start, at start, just before expiry, and at expiry.
18. **Is revocation tested with warm caches and multiple nodes?** Not just database rows.
19. **Are missing-permission and cross-tenant paths tested?** Zero leaks of data or resource metadata.
20. **Are token expiry vs grant expiry handled properly?** Expired JWT does not mean deleted grant; expired grant is not extended by a valid JWT.

**Conclusion:** Data sharing and temporary delegation require policies scoped by **actor + action + resource + time + revocation status**. Spring Security provides authentication, HTTP/method authorization, and ACL infrastructure; the application must still implement **scoped, time-bounded grants**, verify the grantor's authority, evaluate time on every access, keep revocation/caches consistent, and block unauthorized reads/writes at the data layer. A grant is valid only when it matches **the right person, the right resource, the right action, and the right time**.

## Official References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): `@EnableMethodSecurity`, `@PreAuthorize`, policy beans, and parameter-based checks.
- [Spring Security — Authorization Architecture](https://docs.spring.io/spring-security/reference/servlet/authorization/architecture.html): `AuthorizationManager` and contextual access control.
- [Spring Security — ACLs](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): SID/ACE/ObjectIdentity, `PermissionEvaluator`, and standard ACE data limits.
- [Spring Security — OAuth2 Resource Server JWT](https://docs.spring.io/spring-security/reference/servlet/oauth2/resource-server/jwt.html): validating signatures, `exp`, `nbf`, issuers, and clock skew.
- [RFC 7519 — JSON Web Token](https://www.rfc-editor.org/rfc/rfc7519.html): semantics of `exp`/`nbf`/`iat` and time boundaries.
- [OWASP — Authorization Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Authorization_Cheat_Sheet.html): least privilege, deny by default, per-request authorization, and resource-level authorization.
- [OWASP — Insecure Direct Object Reference Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Insecure_Direct_Object_Reference_Prevention_Cheat_Sheet.html): object-level authorization and scoped lookups.
- [OWASP API1:2023 — Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): checking permissions per object ID.
- [OWASP — Forgot Password Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Forgot_Password_Cheat_Sheet.html): principles for high-entropy, expiring, single-use secret tokens applicable to security invitations/tokens.
