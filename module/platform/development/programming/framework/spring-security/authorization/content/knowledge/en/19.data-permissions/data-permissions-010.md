# Avoiding Gaps Between Permission Check Time and Data Use Time

## 1. The Core Problem: Permission Valid at T1 May No Longer Be Valid at T2

In a Spring Security system, a method may check that a user is allowed to edit a document, then read data, compute, call another service, and finally save. Between **time of check (T1)** and **time of use or write (T2)**, the information determining permission can change.

This is a **TOCTOU — Time of Check to Time of Use** flaw, a form of race condition. It is especially dangerous for **data authorization**, because object ID, owner, tenant, ACL, membership, and resource state are attributes that can be modified concurrently by multiple requests, workers, or administrators.

~~~text
T1: Alice has WRITE permission on Document #42
          |
          +--> Admin revokes permission / transfers owner / locks document
          |
T2: Alice still updates Document #42 using the stale decision
~~~

A `@PreAuthorize` check passing at T1 is not an "immutable ticket" for every action at T2. Conversely, wrapping a use case in `@Transactional` **does not automatically guarantee** permissions cannot change: transaction effectiveness also depends on isolation level, what is locked, where permissions live, and how updates execute.

**Design goal:** explicitly define when the permission decision must hold; shrink or eliminate the gap between check and operation using **atomic conditional operations**, **optimistic locking**, **pessimistic locking**, or **appropriate consistency protocols**. When atomicity cannot be achieved, declare the guarantee boundary, apply expiry/re-checks, and fail closed according to risk.

This Knowledge unit covers causes, guarantee levels, SQL/JPA/Spring Security patterns, DB-stored vs external-service permissions, impacts on read/write/delete/download/messaging, a Java 17 example, and how to test race conditions reproducibly.

## 2. Three "Clocks" to Distinguish

Not all timestamps mean the same thing:

| Milestone | What Happens | Question |
|---|---|---|
| **T_authn** | Identity verification, creating Authentication/token/session | Is the identity still valid, or does the token carry stale roles? |
| **T_check** | Policy evaluation: authority, tenant, owner, ACL, resource state | Is there sufficient proof for this operation? |
| **T_use** | Read/write/delete, file download, event emission, external API call | Is the checked permission still valid for the actual action? |

There are also **T_commit**, when the database transaction commits, and **T_delivery**, when an event/file/link is received by an external system. An operation with side effects can span multiple stages.

For example, an API returning `200 OK` after issuing a presigned file download URL: checking permission when **issuing the URL** does not guarantee permission is re-checked when the recipient uses that URL an hour later. Similarly, an event enqueued while an actor had permission but processed the next day may no longer satisfy policy.

Write down the contract:
- Are permissions evaluated **at request start**, **at each mutation**, or **at commit**?
- Does revocation take effect immediately or within a published consistency window?
- For long-running operations, must permissions be re-checked before irreversible side effects?
- What is the denial policy when permissions are missing, unknown, or revoked?

There is no single definition for every product. The mistake is omitting the definition and assuming "we checked earlier" is always enough.

## 3. Common Attributes That Cause TOCTOU

| Changing Attribute | Example Change Between Check and Use | Potential Consequence |
|---|---|---|
| Owner | Document transfers from An to Binh | An edits after losing ownership |
| Tenant | Document moves to another tenant | Cross-tenant read or write |
| Direct ACL/share | WRITE grant is revoked | Recipient still edits under old result |
| Group membership | User leaves `project-review` group | Old group access still allows reading |
| Role/authority | Admin is demoted | Token/cache still holds old role |
| Resource status | Document moves to LOCKED/ARCHIVED | Writing to a locked document |
| Data version | Someone else edits the document | Lost update, overwriting newer data |
| Business threshold | Quota, price, balance, inventory changes | A previously valid decision becomes wrong |
| Session/token | Token revoked, session ended | Async task still carries old identity |
| Policy version | Rule tightened to restrict access | Stale ALLOW decision in cache |
| File/link expiry | Download link stays alive after revocation | Content continues to be downloaded |

**Two distinct race classes:**
1. **Data race:** someone else modifies the document after we read it; solved with versioning/locking or transaction isolation.
2. **Permission race:** the actor's permission on the document changes; a version on the document alone is **insufficient** if grants/ACLs live in another table or system and are not versioned/locked together.

Do not test only one race class and conclude all authorization is safe.

## 4. Anti-Pattern: Check First, Write by Bare ID Later

Easy-to-make mistake:

~~~java
@PreAuthorize("hasAuthority('document:write')")
public void rename(long documentId, String title) {
    if (!documentPolicy.canWrite(currentActor(), documentId)) {
        throw new AccessDeniedException("Denied");
    }

    expensiveCalculation();
    documentRepository.updateTitleById(documentId, title);
}
~~~

This is a **buggy pattern**, not a recommended implementation. The policy may pass at T1, yet during `expensiveCalculation()` the user's permission is revoked or document ownership transfers. `updateTitleById` takes only an ID and ignores old/new permission state.

Even if `@Transactional` is added to the method, check:
- Does `documentPolicy.canWrite` read from **the same database and transaction**?
- Can another transaction update the permission row before `UPDATE` runs?
- Does the isolation level let this transaction see new ACLs or lock against unwanted changes?
- If the policy service lives outside the DB, does `@Transactional` govern that service?
- Does the call pass through a Spring proxy so both transaction and method security actually run?

A structurally sound version does not treat the initial boolean check as the sole gate. Critical predicates are placed **inside the write operation itself or protected by an appropriate locking/versioning protocol**.

## 5. Guarantee Levels: "Shrinking the Window" Differs from "Eliminating the Race"

| Approach | What It Achieves | What It Does Not Guarantee Alone |
|---|---|---|
| Check in controller, write later | Input gate decision | No protection against revocation/owner change after check |
| Re-check right before save | Narrows the gap | Two separate statements still have a race |
| `@Transactional` in one database | Groups operations under commit/rollback boundary | Does not auto-lock ACLs/owners or guarantee proper snapshots |
| `WHERE id AND tenant AND owner AND status` in UPDATE | Record predicates verified as part of the statement | Permissions in external tables can change; DB isolation still matters |
| Version guard via `@Version` or `WHERE version=:v` | Detects changes to the versioned record | Unaware if ACLs in another table changed without bumping version |
| Lock document row + permission rows | Can serialize critical changes per locking protocol | Fails if revocation path skips the same lock/protocol |
| SERIALIZABLE transaction | Certain anomalies detected/retried by DB | Does not cover external systems; needs retries and non-TX handling |
| Short-lived capability / worker re-check | Bounds lifetime of stale decisions | No instant revocation while token remains valid |
| Policy service with version/revocation protocol | Can provide consistency under its own contract | Holds only if every consumer obeys the protocol |

There is no universal "turn on SERIALIZABLE isolation and TOCTOU disappears" rule for all systems. Guarantees depend on **which data and side effects** sit in which transaction, which DB, and whether permission-writing paths share the same synchronization protocol.

## 6. Simplest Pattern: UPDATE with Permission Constraints on the Record Itself

Suppose only the owner in the tenant may rename the title, the document is editable, and the record carries a version.

~~~sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :document_id
  AND tenant_id = :verified_tenant
  AND owner_user_id = :verified_actor
  AND editable = TRUE
  AND version = :expected_version;
~~~

Here **all conditions are evaluated inside the update statement itself**, with no `findById` followed by an unconstrained save. Under normal DB UPDATE semantics, the statement updates only rows satisfying the predicates during statement execution under the DB's isolation/concurrency control.

Interpret the result carefully:
- **1 row updated:** one document met every predicate and was updated.
- **0 rows updated:** wrong ID, wrong tenant, wrong owner, locked, or version changed. Never treat as success.
- **More than 1:** abnormal if ID is unique; inspect schema/query and never blindly report success.

**Never use `owner_user_id=:ownerFromRequest`**, since clients can spoof ownership. `verified_tenant` and `verified_actor` must come from server-verified identity.

**Record-level permission conditions must sit in the same statement** to prevent check owner at T1, owner changes at T2, write at T3. If policy also depends on ACLs/shares in another table, additional mechanisms are needed beyond an owner guard alone.

## 7. Implementing Spring Data JPA `@Modifying`

Illustrative entity has properties:
- `id: Long`, `tenantId: String`, `ownerUserId: String`.
- `editable: boolean`, `title: String`.
- `version: long`, optionally annotated with `@Version` for optimistic locking in entity flows.

Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentRepository
        extends JpaRepository<Document, Long> {

    @Modifying
    @Query("""
        update Document d
           set d.title = :title,
               d.version = d.version + 1
         where d.id = :id
           and d.tenantId = :tenant
           and d.ownerUserId = :actor
           and d.editable = true
           and d.version = :expectedVersion
        """)
    int renameIfOwnerAndVersion(
            @Param("id") Long id,
            @Param("tenant") String tenant,
            @Param("actor") String actor,
            @Param("title") String title,
            @Param("expectedVersion") long expectedVersion);
}
~~~

This is **Spring Data JPA integration code**, not a standalone runnable program. JPQL properties must match the real model. `@Modifying` explicitly marks an update query; a write transaction must wrap the call. `@Modifying` with `@Query` does not automatically create the use case's desired transaction.

Service:

~~~java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class DocumentCommandService {
    private final DocumentRepository documents;
    private final VerifiedActorResolver actors;

    public DocumentCommandService(
            DocumentRepository documents, VerifiedActorResolver actors) {
        this.documents = documents;
        this.actors = actors;
    }

    @PreAuthorize("isAuthenticated() and hasAuthority('document:write')")
    @Transactional
    public void rename(Long id, String title, long expectedVersion) {
        VerifiedActor actor = actors.requireCurrent();

        if (id == null || id <= 0
                || title == null || title.isBlank()) {
            throw new IllegalArgumentException("Invalid rename request");
        }

        int rows = documents.renameIfOwnerAndVersion(
                id, actor.tenantId(), actor.userId(),
                title, expectedVersion);

        if (rows != 1) {
            throw new ScopedUpdateRejectedException();
        }
    }
}
~~~

`VerifiedActorResolver`, `VerifiedActor`, and `ScopedUpdateRejectedException` are application types to define. The resolver must derive identity and tenant from verified sources. `@PreAuthorize` enforces functional authority, while the **UPDATE** verifies actual ownership at statement execution time.

**JPA note:** bulk JPQL updates bypass dirty checking, optimistic locking, and entity callbacks compared to `save` on managed entities; hence the code **explicitly** checks and increments `version`. Bulk updates can also leave entities in the persistence context stale. Never enable `clearAutomatically` carelessly if unflushed changes exist; design transactions and persistence contexts for your workload.

## 8. Avoiding Leaks Through 0-Row Results

A guarded UPDATE returning 0 rows does not say why. It could be:
- Document ID does not exist.
- Document is in another tenant.
- Actor is no longer owner.
- Document is locked.
- Client sent a stale version.

Do not immediately call an **unscoped** `repository.findById(id)` just to distinguish reasons and return a message naming the real owner or tenant to an unauthorized caller.

A clean response contract could be:
- 404 if the document does not exist **within the actor's visible set**.
- 409 if the actor is confirmed allowed to see the resource and the version is stale.
- 403 if policy intentionally signals lack of permission without leaking unauthorized details.
- 5xx if the database/policy backend fails.

Choose per your API and anti-enumeration requirements. Crucially, **never return 200/204 when affected rows = 0** and never log out-of-scope document contents.

## 9. Optimistic Locking with `@Version`: Preventing Lost Data Updates

A JPA entity has:

~~~java
@Entity
public class Document {
    @Id
    private Long id;

    @Version
    private long version;

    private String tenantId;
    private String ownerUserId;
    private String title;
}
~~~

This is an **entity fragment**, requiring JPA imports, constructors/mappings, and domain logic. When two transactions read the old version and try to write a managed entity, the JPA provider detects an optimistic locking conflict if the version was incremented by an earlier write, instead of silently overwriting.

On concurrency errors, APIs typically return 409 or ask the client to reload the latest version and retry under proper conditions. Never retry infinitely using an old snapshot and stale permission decision.

**However, `@Version` does not automatically block permission revocation in another table.**

Example:
~~~text
Document #42.version = 5
document_grants: Alice WRITE=true

T1: Alice reads Document version=5
T2: admin revokes Alice WRITE in document_grants
T3: Alice writes Document version=5
~~~

If `documents.version` **is not bumped when grants change**, optimistic locking on Document may miss T2. You must design:
- Versioning on permissions/ACLs checked alongside the write;
- Locking the related rows;
- A revocation protocol that also updates a shared guard/version on Document;
- Or defined consistency semantics via DB isolation/transactions.

Never advertise `@Version` as "stopping all permission races" just because it prevents lost data updates.

## 10. When Permissions Live in a Grant Table: Using `EXISTS` While Understanding Concurrency

For direct WRITE shares, an illustrative PostgreSQL query:

~~~sql
UPDATE documents
SET title = :new_title,
    version = version + 1
WHERE id = :id
  AND tenant_id = :verified_tenant
  AND editable = TRUE
  AND version = :expected_version
  AND (
      owner_user_id = :verified_actor
      OR EXISTS (
          SELECT 1
          FROM document_grants g
          WHERE g.document_id = documents.id
            AND g.grantee_user_id = :verified_actor
            AND g.permission = 'WRITE'
            AND g.revoked_at IS NULL
            AND (g.expires_at IS NULL OR g.expires_at > :now)
      )
  );
~~~

This is a **PostgreSQL pattern**; adapt for your actual dialect. Use `:now` strictly from the server clock—never let clients dictate expiry. All ID/tenant/action scopes sit in the same statement. `EXISTS` avoids duplicating target rows when multiple grants exist.

Critically: when a grant-revocation transaction runs **concurrently**, an UPDATE statement and a grant DELETE/UPDATE can observe different snapshots and locks depending on DB/isolation. Putting `EXISTS` in the same statement eliminates application-layer gaps, yet **does not automatically prove revocation instantly beats every in-flight transaction**.

Pick a concrete "effective point": for instance, may an update that already started and took a valid snapshot **before** revocation committed still complete? If policy requires "once revocation commits, no mutation by the old actor may commit", design a stricter synchronization/serialization protocol.

Never promise strong guarantees when reading predicates under `READ_COMMITTED` without verifying exact DB interleavings.

## 11. Pessimistic Locking: Locking the Right Rows and Workflows

When owner/status permissions live on the document row itself, you can use `PESSIMISTIC_WRITE` to read/check/edit in a transaction:

~~~java
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;
import java.util.Optional;

public interface DocumentLockingRepository
        extends JpaRepository<Document, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("""
        select d from Document d
        where d.id = :id
          and d.tenantId = :tenant
        """)
    Optional<Document> lockByIdAndTenant(
            @Param("id") Long id,
            @Param("tenant") String tenant);
}
~~~

A use case can:
1. Start a transaction on a Spring-managed service.
2. Load the document with a scoped locking query.
3. Check owner, editable, status, and business rules while holding the lock.
4. Mutate the managed entity.
5. Commit, releasing the lock per DB semantics.

**Ensure owner-transfer and document-locking flows synchronize on the exact same document row.** If another service modifies ACLs in `document_grants` without locking the same resource, `PESSIMISTIC_WRITE` on the document **does not protect permissions in the grant table**.

To serialize grant/revoke with grant-based writes, a protocol can require both flows to lock **the document row first as a shared mutex** before reading/modifying grants, then update/commit. When doing so:
- Keep lock acquisition ordering consistent to prevent deadlocks.
- Require every writer/revoker to obey the protocol; one unlocked API breaks the guarantee.
- Configure safe timeouts, deadlock handling, and retries.
- Test on the production database dialect.
- Watch throughput and lock hold times; avoid slow network calls while holding DB locks whenever possible.

**Reading under a lock and returning the object for post-commit use leaves that later use unprotected** by the lock. Transaction boundaries and side effects must be evaluated together.

## 12. Isolation Levels and Real-World Semantics

Spring provides `Isolation.READ_COMMITTED`, `REPEATABLE_READ`, `SERIALIZABLE`, etc., yet exact meanings and locking/snapshot mechanisms depend on the DBMS.

| Level | General Behavior | Notes for Authorization TOCTOU |
|---|---|---|
| READ_COMMITTED | Each statement typically sees committed data per DB rules | Separate check and update statements can observe different states |
| REPEATABLE_READ | Stronger snapshot/repeatable reads depending on DB | Seeing the same old data does not mean permissions weren't revoked |
| SERIALIZABLE | Concurrent transactions must match some serial order per DB guarantees | Can abort/retry; does not coordinate systems outside the DB |

A Spring example:

~~~java
@Transactional(isolation = Isolation.SERIALIZABLE)
public void sensitiveUpdate(...) {
    // Scoped authorization + mutation on appropriate DB and transaction.
}
~~~

This is a snippet, not advice to turn on SERIALIZABLE everywhere. Higher isolation can cause contention and serialization errors requiring retries. If policies live in an external OPA service, SQL transactions cannot make external responses transactional.

A subtle issue: a transaction with an older snapshot can be **valid under serializable ordering** yet still violate "a revocation committed before the update commits must win". To guarantee stricter real-time ordering, define a linearization point between revoke and update, and build locking or version/synchronization protocols on both sides.

**State the required guarantee explicitly before picking an isolation level**, instead of calling any level "absolutely safe".

## 13. `@Transactional` and `@PreAuthorize` Do Not Mean Checking in the Same Transaction

A service often has:

~~~java
@PreAuthorize("@documentPolicy.canWrite(authentication, #id)")
@Transactional
public void rename(Long id, String title) {
    // Mutation.
}
~~~

Spring can apply both **authorization advice** and **transaction advice** on the proxy. Advice ordering depends on framework/configuration; never assume the check runs inside the mutation's transaction. If the policy reads ACLs before the transaction starts, a gap remains between check and use.

Even when the check runs inside the same transaction, **that does not ensure it locks every permission row**. Therefore:
- Use `@PreAuthorize` for **coarse-grained entry authorization** where appropriate.
- For writes, evaluate **resource-specific permissions** close to the mutation, inside the transaction or via a guarded update statement.
- When using a custom `AuthorizationManager` or DB-backed policy bean, know the exact transaction propagation and advice order.
- Test actual interceptor order for your Spring version/configuration; never infer it from annotation order in source code.
- Test self-invocation: `this.rename(...)` within the same bean can bypass AOP proxies for both method security and transactions.

A clear way to structure this is **separating Spring beans**: a transactional application service and a policy bean called inside the method body, while still using method security for entry checks. Direct repository write paths must be governed by module architecture and tests.

## 14. Newly Revoked Permissions and Cached Authentication/ACLs

Races do not only happen in SQL. A valid JWT can carry roles/groups from issuance time. When a user leaves a group, the old token still carries old claims until expiration unless the system revokes tokens or re-queries memberships.

Common causes:
- Spring `SecurityContext` populated before role changes.
- Valid JWT whose authorities are read from the token without re-lookup.
- Permission caches/Redis storing ALLOW results with long TTLs.
- ACL cache not invalidated after grant/revoke.
- Another service instance has not yet observed the revocation event.
- Sessions not invalidated on demotion.

Corresponding mitigations:
1. Define **permission freshness**: what maximum delay is acceptable after revocation?
2. For sensitive actions, prefer live permission queries/re-checks or short-lived capability tokens with revocation/versioning.
3. Cache keys must include actor, tenant, resource, action, and policy version; avoid keying solely by ID.
4. On revocation, invalidate critical caches via a tested mechanism; ensure cache hits/misses match the contract.
5. Cache/backend errors must never turn into permits.
6. For legal/financial data, consider querying the authoritative permission source at action time instead of relying on stale claims.

You do not necessarily have to introspect every JWT on every request: the choice depends on latency goals, availability, and your committed **revocation SLA**. What must be avoided is promising "instant revocation" while every layer trusts long-lived tokens/caches.

## 15. When Permissions Live in an External Service Outside the DB

Example:
~~~text
Service A (Document DB)        Service B (Policy/ACL DB)
          |                                |
          +-- canWrite(actor, doc) ------->|   returns ALLOW
          |
          +-- expensive work / network delay
          |
          +-- UPDATE document ------------> Document DB
~~~

`@Transactional` in Service A cannot lock Service B's ACL store by default. The two systems have independent transactions. Unless designed with a true distributed protocol, **you cannot claim atomicity** between a remote authorization decision and a local DB mutation.

Mitigation paths:
- **Re-check right before side effects** to narrow the window, accepting the remaining race if risk allows.
- **Policy revision/version**: bind decisions to an ACL version; the write path verifies the revision is still current in a system capable of enforcing it. If revision is checked via another separate API call, a race still exists between that call and the write.
- **Signed short-lived capability**: bind actor, tenant, object, action, expiry, nonce, and scope; verify on use. Revoking before expiry requires revocation checks.
- **Permission mirror/index in the same DB**: sync policies from the external system and run conditional SQL; define consistency, lag, and fail-closed rules.
- **Distributed workflow/saga**: state machines, idempotency, and compensation for cross-system actions. Compensation cannot always undo externally exposed side effects.

Never create a fallback like "policy service timeout → grant so operations keep running". If a fresh decision cannot be obtained when business demands strict protection, halt the operation and report an appropriate error.

## 16. Reads Have TOCTOU Too: Check Before Reading Sensitive Data

Pattern:
~~~java
if (policy.canRead(actor, documentId)) {
    Document d = repository.findById(documentId).orElseThrow();
    return mapper.toDto(d);
}
~~~

If the document changes tenant/owner or permission is revoked between the two calls, the earlier READ check may no longer hold. For straightforward conditions stored in the same database, prefer **query-time scoping**:

~~~sql
SELECT d.*
FROM documents d
WHERE d.id = :id
  AND d.tenant_id = :verified_tenant
  AND (
      d.owner_user_id = :verified_actor
      OR EXISTS (
          SELECT 1 FROM document_grants g
          WHERE g.document_id = d.id
            AND g.grantee_user_id = :verified_actor
            AND g.permission = 'READ'
            AND g.revoked_at IS NULL
      )
  );
~~~

ID, tenant, and permission predicates are evaluated in the same SELECT statement per DB semantics. This is a much stronger boundary than loading by bare ID and checking afterward once data has already touched mappers/logs/caches.

Even so, a SELECT cannot erase "secrets revoked after the response began" from bytes already sent. Define a clear contract: are permissions evaluated at query time or per streamed chunk? For long-lived streams, design explicit mid-stream revocation handling if needed.

**Do not serialize managed JPA entities after the transaction ends** if lazy loading could pull out-of-scope relations. Map DTOs using exact projections and policies inside the transaction, or write scoped DTO queries.

## 17. File Downloads and Presigned URLs: Access Outliving the Check

Typical steps:
1. User calls `GET /files/42/download-link`.
2. Service checks READ permission on the file.
3. Service generates a presigned object-storage URL, e.g., valid for 30 minutes.
4. User's permission is revoked 1 minute later.
5. Anyone holding the URL can still use it until expiry per provider policy.

This is **not** directly a Spring Security filter bug; a presigned URL is a **capability** existing independently of the original session. If policy requires immediate revocation, shrinking TTL alone may not suffice.

Options:
- Ultra-short URLs, tightly scoped to object/action/method, never leaked in logs or referrers.
- Download through a service proxy checking policy on every request instead of issuing long-lived links.
- Gateway/token revocation checks or versioned access tokens where infrastructure supports them.
- Never cache sensitive files in CDNs/browsers longer than policy permits.
- When rotating object storage keys or revoking, verify how invalidation actually behaves.

Bytes downloaded before revocation cannot be clawed back. A realistic contract states clearly when permissions are evaluated and how post-issuance link usage is bounded.

## 18. Message Queues, Jobs, and Asynchronous Tasks

A command is enqueued at T1 while the actor has WRITE, then consumed at T2 after the actor is revoked. If the consumer trusts an `authorized=true` flag in the message, that is TOCTOU across time and trust boundaries.

~~~text
HTTP at T1 --> "user can export" --> Queue (hours later)
                                       |
                                     Worker at T2
                                       |
                              EXPORT without recheck  // dangerous
~~~

For sensitive tasks, workers must have:
- Verified origin and actor/workload identity; never trust a self-declared `userId` field.
- Explicit resource/action/scope; never conflate user permissions with system job permissions.
- A policy of **re-evaluating at execution time** or signed capabilities with published expiry/revocation semantics.
- Idempotency so retries do not create duplicate side effects.
- Deadlines, policy revisions, or bounds on exported data.
- Auditing of who requested, who executed, and permission state at execution time.

If a task is legitimately authorized to run **even after the user leaves the system** (e.g., statutory accounting retention), define a **system operation** with its own service identity and policy. Do not pretend it is still the old user's permission.

`@Async` can drop `SecurityContext` across threads; controlled context propagation does not mean permissions haven't changed. Never copy `SecurityContext` and assume TOCTOU is solved.

## 19. Outbox and Side Effects Outside Transactions

After checking permissions and writing to the DB, a service may send emails, publish events, or call a payment API. Publishing **before commit** risks emitting false events if the transaction later rolls back.

A common design:
~~~text
transaction:
  - verify permissions at mutation boundary
  - update record with predicate/version
  - insert outbox event in the same transaction
commit
outbox publisher:
  - send event idempotently
~~~

**Transactional outbox** prevents emitting events for rolled-back DB transactions when outbox and mutation share the same database/transaction. It does **not** synchronize permissions with external services, nor stop a downstream consumer from acting after policy changed. Consumers need their own permission contracts when events trigger further actions on other resources.

Irreversible side effects (sent emails, published files, transferred money) require pre-execution guards, idempotency, retries, and sometimes controlled compensation. Avoid external API calls while holding long DB locks unless strictly justified with tight timeouts.

## 20. Owner Transfers, Tenant Moves, Document Locks: Which Version Increments?

If permissions depend solely on owner/status columns on the document row, every change to them should participate in the same versioning/locking mechanism as content edits.

Example:
~~~text
document#42: owner=an, editable=true, version=5

T1: An receives version=5
T2: ownership transfers to Binh, version=6
T3: An requests UPDATE version=5
--> affectedRows=0
~~~

If an owner-transfer flow runs bulk SQL `UPDATE owner_user_id=...` **without incrementing version**, a version-only guard would miss the change; however, if T3's UPDATE also checks `owner_user_id=:verified_actor`, the ownership change is still caught by the predicate. Ideally **both live predicates and versioning** are used where needed, not just one mechanism.

For tenant moves, queries and mutations must bind the resource's tenant. When a tenant changes, old ACLs/share grants, caches, and search indexes must be re-scoped/revoked. Never update one column and leave old permissions able to access the resource by ID from the old tenant.

For LOCKED status, policy should include `editable = TRUE` or an in-transaction guard tied to the same version/lock. Calling `isEditable()` before a long operation is insufficient.

## 21. Optimistic vs Pessimistic vs Atomic Predicate: How to Choose?

| Context | Option Worth Considering | Notes |
|---|---|---|
| Owner-only, status on row, high throughput | Atomic scoped UPDATE + version | Fewer round trips; check affected rows |
| Document editing from UI | `@Version` + owner/tenant field guards | Users may receive 409 and reload |
| Permissions in same-DB share table | UPDATE with `EXISTS` + tested isolation or locking protocol | Concurrent revokes need clear semantics |
| Business requires serializing grant/revoke with writes | Shared lock protocol on document/ACL rows | Watch deadlocks/timeouts/ordering; all paths must obey |
| External policy service | Re-check/capability/version + workflow consistency | No default atomic DB transaction across services |
| Long-running batch | Small chunks, per-item/group re-check, idempotency | One check at batch start doesn't protect every item |
| Read-only detail | Query with scoped permission predicates | SELECT time differs from streaming completion time |
| Bulk export/download | Scoped query/stream, short-lived capability, re-check if needed | Prevent leaks via caches/unexpired URLs |

You do not need to pessimistically lock every object; that causes needless contention and deadlocks. Equally, never rely on optimistic versioning alone for a permission rule stored in another table. Choose based on **where permissions live**, **revocation guarantees**, and **concurrency cost** of the use case.

## 22. Standalone Java 17: Simulating Stale Checks and Atomic Guards

The following example is plain Java 17 without Spring/JPA. It constructs a **deterministic interleaving** proving: a decision at T1 can become stale at T2; an operation that checks and writes under the same object lock rejects once owner/version changed.

Create `AuthorizationRaceDemo.java`:

~~~java
public class AuthorizationRaceDemo {
    record Actor(String userId, String tenantId) { }

    static final class Document {
        final long id;
        final String tenantId;
        String ownerId;
        String title;
        long version;

        Document(long id, String tenantId, String ownerId,
                 String title, long version) {
            this.id = id;
            this.tenantId = tenantId;
            this.ownerId = ownerId;
            this.title = title;
            this.version = version;
        }

        synchronized boolean canWrite(Actor actor) {
            return actor != null
                    && actor.userId() != null
                    && actor.tenantId() != null
                    && actor.tenantId().equals(tenantId)
                    && actor.userId().equals(ownerId);
        }

        synchronized void transferOwner(String newOwner) {
            ownerId = newOwner;
            version++;
        }

        synchronized void unsafeWriteWithoutRecheck(String newTitle) {
            title = newTitle;
            version++;
        }

        synchronized boolean renameGuarded(
                Actor actor, long expectedVersion, String newTitle) {

            if (!canWrite(actor)
                    || version != expectedVersion
                    || newTitle == null || newTitle.isBlank()) {
                return false;
            }
            title = newTitle;
            version++;
            return true;
        }
    }

    public static void main(String[] args) {
        Actor an = new Actor("an", "north");
        Actor southAn = new Actor("an", "south");

        Document unsafe = new Document(
                42, "north", "an", "Draft", 5);
        boolean checkAtT1 = unsafe.canWrite(an);
        unsafe.transferOwner("binh");          // Revoke ownership at T2
        if (checkAtT1) {
            unsafe.unsafeWriteWithoutRecheck("Changed");
        }
        System.out.println("naive-changed="
                + unsafe.title.equals("Changed"));

        Document guarded = new Document(
                42, "north", "an", "Draft", 5);
        long expected = guarded.version;
        guarded.transferOwner("binh");         // Revoke before mutation
        boolean accepted = guarded.renameGuarded(
                an, expected, "Changed");
        System.out.println("guarded-accepted=" + accepted);
        System.out.println("guarded-title=" + guarded.title);

        Document valid = new Document(
                43, "north", "an", "Draft", 9);
        boolean validWrite = valid.renameGuarded(
                an, 9, "Approved");
        System.out.println("valid-accepted=" + validWrite);
        System.out.println("valid-title=" + valid.title);

        boolean wrongTenant = valid.renameGuarded(
                southAn, 10, "CrossTenant");
        System.out.println("cross-tenant-accepted=" + wrongTenant);

        boolean staleVersion = valid.renameGuarded(
                an, 9, "Stale");
        System.out.println("stale-version-accepted=" + staleVersion);
    }
}
~~~

Run with JDK 17 or later:

~~~bash
javac AuthorizationRaceDemo.java
java AuthorizationRaceDemo
~~~

Exact stdout:

~~~text
naive-changed=true
guarded-accepted=false
guarded-title=Draft
valid-accepted=true
valid-title=Approved
cross-tenant-accepted=false
stale-version-accepted=false
~~~

**Why is this demo meaningful?**

- `naive-changed=true`: checked while An was still owner, then ownership transferred to Binh, yet the write code skipped re-checking and changed the title anyway.
- `guarded-accepted=false`: checking current owner **and** expected version inside the same critical section catches the prior change.
- `valid-accepted=true`: actor matching tenant/owner with valid version succeeds.
- `cross-tenant-accepted=false`: actor with the same name in a different tenant cannot write.
- `stale-version-accepted=false`: version 9 is stale once version incremented to 10.

**Limitation:** `synchronized` protects a Java object **within one JVM** when all threads use that exact object. It **does not** lock database records, protect multiple pods/services, or synchronize ACLs in another store. In real Spring/JPA deployments, replace the in-memory critical section with appropriate **guarded database statements, transactions/locks, or consistency protocols** and test under real concurrency.

## 23. How to Test Race Conditions Reproducibly

A unit test that "calls `canWrite` and immediately calls `save`" always passes because nothing happens in between. Race conditions need tests with **synchronization points** to force interleavings.

Test model:

~~~text
Thread A (writer)                 Thread B (revoker)
---------------------             ----------------------
start request
permission check: ALLOW
signal "checked"
wait "revoked"                    wait "checked"
                                  revoke grant / move owner
                                  commit
                                  signal "revoked"
perform mutation
commit
assert expected outcome
~~~

Use `CountDownLatch`/`CyclicBarrier` in tests with independent transactions per thread. Never use `Thread.sleep(...)` as proof of concurrency safety since timing is unstable. In Spring tests, each thread has its own security context; fixtures must initialize a trusted context per worker instead of relying on accidental thread-locals.

Essential tests:

1. **Naive path** illustrating the bug in an intentionally flawed test fixture—never shipped to production.
2. **Owner change** commits before the guarded update: old writer gets `affectedRows=0`.
3. **Stale version**: two writers use the old version; only one change succeeds or one transaction receives conflict per contract.
4. **Grant revocation** between check and write: outcome matches defined revocation semantics.
5. **Group membership revocation**: old tokens/caches do not grant access beyond the published SLA.
6. **Tenant move**: old-tenant writer cannot update the record after tenant transfer.
7. **Lock tests**: all owner/grant-changing paths obey the locking protocol; timeouts/deadlocks handled.
8. **External policy outage**: when the backend fails to decide, zero mutations occur.
9. **Retry after serialization conflict**: retries re-evaluate actor/policy and re-read state, never reusing an old ALLOW.
10. **Message workers** enqueued before revocation and processed after: do not run if contract requires live permission.
11. **File links**: TTL/revocation verified against the real storage provider, not inferred from Spring APIs.
12. **Database state**: inspect rows, versions, grants, and audit/outbox after denials/rollbacks—not just HTTP status.

Run tests against the production database dialect (e.g., via Testcontainers) with matching isolation/configuration. H2 and mock repositories may not accurately replicate PostgreSQL, MySQL, or other locking/snapshot semantics.

## 24. Testing Real Transactions in Spring/JPA

When structuring tests:
- Inject services from the Spring application context; never instantiate with `new` and assume `@Transactional`/`@PreAuthorize` work.
- Use matching principal/tenant test fixtures (for custom JWT claims, default `@WithMockUser` may be insufficient).
- Ensure the test transaction and competing transaction **do not accidentally share one test transaction**. If a test method itself is `@Transactional` and rolls back at the end, it can hide real commit behavior.
- Verify proxy self-invocation does not bypass transaction or authorization advice.
- Catch and assert the exact exceptions: optimistic conflicts, lock timeouts, denials, and not-founds all need distinct handling.
- Ensure concurrency errors are never caught and turned into fake HTTP 200s.
- For `@Modifying` bulk queries, test both persistence-context staleness and `expectedVersion` guards.

Example expected assertions (snippet, not a standalone test class):

~~~java
int affected = repository.renameIfOwnerAndVersion(
        42L, "north", "an", "New title", 5L);

assertThat(affected).isZero();
assertThat(repository.findById(42L).orElseThrow().getTitle())
        .isEqualTo("Draft");
~~~

This assumes another transaction transferred ownership or bumped version beforehand; use unscoped `findById` strictly inside **test fixtures privileged to inspect the DB**, never in endpoints exposed to unauthorized users.

## 25. Observability: Measuring TOCTOU Risk in Operations

Events to log safely:

| Event | Data to Log | What Not to Log |
|---|---|---|
| Authorization evaluation | Actor ID, verified tenant, action, resource, decision, policy revision | Raw JWT/tokens and full ACLs |
| Guarded update rejected | Row count 0, general reason code, expectedVersion | Real owner of out-of-scope resources |
| Revoke/grant | Who changed permission, resource/tenant, time, revision | Secrets or confidential details |
| Version conflict | Expected version and retry status, correlation ID | Sensitive data in exception bodies |
| Transaction serialization/deadlock | DB error class, attempt, latency, transaction boundary | Connection credentials |
| External policy timeout | Dependency status and SLA breach | Secret tokens/headers |
| Async use | RequestedAt, executedAt, identity/policy version, result | Another actor's confidential payload |

Measure rates of `affectedRows=0` updates, optimistic conflicts, 403/404/409/5xx responses, authorization cache staleness, revocation-to-enforcement latency, and retries. These metrics reveal when permission changes occur while clients keep getting allowed too long.

Audit logs never replace guards; they support investigation and proof after the system enforces policy.

## 26. Anti-Patterns to Avoid

**1. Checking permissions once in the controller, then service calls `updateById`.** Permissions can change before save; other adapters bypass controllers. **Fix:** service boundary + guarded DB operations.

**2. Adding `@Transactional` alone and assuming races are gone.** Transactions do not auto-lock external ACL tables or external services. **Fix:** define predicates/locks/isolation and test realistically.

**3. Adding `@Version` to Document only when permissions live in another table.** Permission revocations may not bump document version. **Fix:** live permission guards or ACL versioning/locking.

**4. Re-checking right before save across two separate transactions/queries.** Shrinks but does not eliminate races. **Fix:** atomic statements or consistent protocols.

**5. Using `@PreAuthorize` to prove permission still holds at commit.** Advice order and transaction boundaries can differ. **Fix:** enforce resource policy inside safe operations.

**6. Locking the document on writes while grant revocation skips locking the document.** Two paths share no protocol and fail to prevent races. **Fix:** enforce the same lock ordering across all writers and revokers.

**7. Caching ALLOW long-term without invalidating on revoke.** Tokens/caches carry stale permissions. **Fix:** TTL/revision/revocation SLAs and re-checks for sensitive actions.

**8. Workers trusting `authorized=true` in messages.** Flags set at T1 are stale and forgeable. **Fix:** verify origin, actor, and policy at T2 or use controlled capabilities.

**9. Issuing long-lived presigned URLs while promising instant revocation.** URLs remain capabilities until expiry. **Fix:** short TTLs or re-checking gateways.

**10. Retrying an UPDATE using the stale decision.** An optimistic/serialization failure can occur after permissions changed. **Fix:** retries must restart the use case with freshly evaluated actor/policy/state.

**11. Returning 204 when `affectedRows=0`.** Clients think edits succeeded while masking stale/denied states. **Fix:** inspect row counts and map errors safely.

**12. Testing only sequentially.** Races appear only under interleaving. **Fix:** latch-based tests, real transactions, and production-like DBs.

## 27. Checklist for Designing Side-Effect Use Cases

- [ ] Clearly define when permissions must hold: request, mutation, commit, or external execution.
- [ ] Verify actor, tenant, and authorities from trusted sources.
- [ ] Separate coarse role checks from object permissions.
- [ ] ID queries always include matching tenant/owner or allowed scope.
- [ ] If permissions live on the target row, consider guarded UPDATE/DELETE in one statement.
- [ ] When using optimistic locking, ensure all auth-relevant changes participate in required guards/versions.
- [ ] When using pessimistic locking, all grant/revoke/owner-change paths obey the same protocol.
- [ ] Verify actual isolation, advice ordering, and transaction managers.
- [ ] Never treat external policy services as part of a DB transaction without a backing protocol.
- [ ] Never trust ALLOW caches/tokens beyond the revocation SLA.
- [ ] File downloads, queues, batches, and background jobs enforce policies at time of use.
- [ ] External side effects use outboxes/idempotency/guards commensurate with risk.
- [ ] On `affectedRows=0`, never return success; never leak real owner/tenant.
- [ ] On concurrency conflict retries, obtain a fresh permission decision.
- [ ] Test interleavings with revocation/owner transfers, version conflicts, wrong tenants, and outages.
- [ ] Include auditing/correlation/metrics without logging credentials or out-of-scope documents.

**Conclusion:** TOCTOU in authorization occurs when **a past valid decision** is used to authorize **a present side effect** without staying bound to current data and permissions. When permissions sit on the record itself, atomic conditional UPDATEs with tenant/owner/status/version are highly effective. For ACLs, groups, or external policies, add synchronization protocols, revisions, or re-checks matching desired guarantees. Spring Security method security, transactions, and locking support the solution, yet none **automatically** eliminates every race alone.

## References

- [Spring Security – Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): method authorization, interceptors, and defining boundaries.
- [Spring Framework – Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy mode, self-invocation, isolation/propagation/rollback, and advice ordering.
- [Spring Data JPA – Locking](https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html): using `@Lock` with JPA query methods.
- [Spring Data JPA – JPA Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html): `@Modifying`, JPQL updates, and the persistence context.
- [Spring Data JPA – Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html): transaction boundaries and transactional repository operations.
- [Jakarta Persistence – @Version](https://jakarta.ee/specifications/persistence/3.2/apidocs/jakarta.persistence/jakarta/persistence/version): optimistic locking versions in JPA.
- [OWASP API Security Top 10 – Broken Object Level Authorization](https://api-security.owasp.org/editions/2023/en/0xa1-broken-object-level-authorization/): why a direct ID does not prove permission on an object.
