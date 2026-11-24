# Auditing ACL Changes and Tracing Granted Permissions

> **Topic:** Spring Security – authorization · **Group:** ACL Implementation. This lesson guides you through building a mechanism to **record every permission change per object** and **explain whether a GRANT/DENY decision came from a specific ACE, SID, direct ACL, or parent ACL**. The focus is separating ACL configuration auditing from runtime decision auditing; designing immutable events, transactions/outboxes, historical provenance tracing, and tests. Integration snippets reference Spring Security ACL 6.x/7.x, Spring Boot Servlet, and Java 17+. Never equate the default audit logger with a complete security change-history system.

## 1. Learning Objectives

After this lesson you will be able to:

1. Distinguish **ACL mutation audit**, **authorization decision audit**, and **permission provenance**.
2. Explain `acl_entry.audit_success`, `audit_failure`, `AuditableAcl.updateAuditing(...)`, and `AuditLogger.logIfNeeded(...)` — specifically that **they do not automatically log who changed an ACE**.
3. Design an event schema capturing `actor`, `resource type/id`, `tenant`, `before → after` changes, reason, timestamp, revision, correlation ID, and outcome.
4. Place ACL mutations and audit/outbox writes inside the proper transaction so you never get "permissions changed with no log," or vice versa.
5. Interpret granted permissions across `ObjectIdentity`, ordered `Sid` lists, `Permission`, ACEs, `parentAcl`/`entriesInheriting`, and additional policies.
6. Distinguish **current permissions** from **permissions at a historical point in time**, especially after role memberships, parent ACLs, tenant state, or domain data have changed.
7. Write code and tests for a grant/revoke flow, read back via `AclService`, verify exact audit events, and test rollback failures.
8. Operate logging without leaking tokens/PII, with RBAC on log access, retention, permission-drift monitoring, and tamper resistance.

## 2. The Problem: "Why Could Bob Read Document 42?"

One day, the security team receives a question:

> "At 10:15 AM Thursday, Bob opened Document 42 in tenant alpha. Who granted Bob access, when, was it direct or inherited from a Folder, and was that access valid under policy?"

Querying only the **current** ACL might show:

~~~text
Document(42):
  ACL id=901
  parentAcl = Folder(9)
  entriesInheriting = true
  local entries: [no READ ACE for Bob]

Folder(9):
  ACE: GrantedAuthoritySid("ROLE_REVIEWER") + READ = GRANT

Bob at request time:
  principal = bob
  authorities = [ROLE_REVIEWER, ...]
~~~

From that data you can explain Bob's **current effective permission** as coming from the Folder ACL via `ROLE_REVIEWER`, assuming no higher-priority matching ACE or remaining authorization checks veto it. Yet answering **who added that ACE to Folder and when** requires an independent change history. Answering **whether Bob held ROLE_REVIEWER at 10:15** also requires identity/role evidence at that exact moment. An ACL snapshot at 16:00 does not prove a decision at 10:15.

Therefore, you must design **two event ledgers** alongside a provenance model:

~~~text
1) ACL CHANGE AUDIT:
   admin carol -> INSERT ACE (ROLE_REVIEWER, READ, GRANT)
   resource Folder(9), revision 17 -> 18, reason=CASE-208

2) ACCESS/DECISION AUDIT:
   Bob -> READ Document(42) at 10:15
   decision GRANT, evaluated on ACL Document->Folder,
   matched SID ROLE_REVIEWER, ACE id=375, policyVersion=...

3) IDENTITY / POLICY CONTEXT:
   at 10:15 Bob was ROLE_REVIEWER in tenant alpha;
   Document(42) belonged to alpha; request filters and state rules passed.
~~~

Without recording all three layers, conclusions can go only as far as **the actual evidence allows**, never guessing "Carol probably granted it" or "Bob probably already had that role."

## 3. Distinguishing the Two Audit Types Supported Differently by Spring ACL

| Concept | Events to record | Mechanism / limitations |
| --- | --- | --- |
| **Mutation audit** | INSERT/UPDATE/DELETE ACE; owner/parent/inherit changes; ACL creation/deletion | **Must be built by the application** around `MutableAclService`/DB; no full change history appears merely from using the ACL module |
| **Decision audit** | Runtime GRANT or DENY checks for READ/WRITE | Provides `AuditLogger` and ACE audit flags; needs observability integration to persist in an audit store |
| **Provenance/explain** | Which SID, ACE, and ACL caused GRANT, and whether inherited from a parent | Must interpret using the exact same policy/strategy and snapshot; `Acl.getEntries()` alone does not return inherited entries |
| **Authentication audit** | Who logged in, token/credential type, role/tenant snapshot | Belongs to the authentication/identity layer, not recorded by `MutableAclService` |
| **Business audit** | Who moved a Document across Folders/tenants or changed classification | Belongs to domain workflows; correlate with ACL mutations |

**Principle:** `audit_success` and `audit_failure` **do not mean** "enable auditing for every ACL edit." They are flags for logging **ACE-based permission evaluation outcomes**. Calling `aclService.updateAcl(acl)` does not automatically append an audit event with actor, before/after, reason, and request ID to an application history table.

## 4. APIs and Columns That Actually Exist in Spring Security ACL

### 4.1. The Four Relevant Tables

Spring Security JDBC ACL typically uses:

- `acl_class`: protected object type.
- `acl_sid`: principal SID or granted-authority SID.
- `acl_object_identity`: object ID, owner SID, parent ACL, `entries_inheriting`.
- `acl_entry`: each ACE; `sid`, `mask`, `granting`, `ace_order`, `audit_success`, `audit_failure`.

The following block is only a **conceptual outline**, not a complete migration for a specific DB:

~~~sql
acl_object_identity (
  id,
  object_id_class,
  object_id_identity,
  parent_object,
  owner_sid,
  entries_inheriting
);

acl_entry (
  id,
  acl_object_identity,
  ace_order,
  sid,
  mask,
  granting,
  audit_success,
  audit_failure
);
~~~

These tables represent **current permission state**, not event sourcing/history. When `updateAcl` modifies `acl_entry`, prior data may be replaced/deleted. To answer "what were the old permissions?", you need snapshots/diffs or a separate audit trail.

### 4.2. Mutation API and Audit Flags

~~~java
// Snippet inside an @Service authorized to manage ACLs.
ObjectIdentity oid =
        new ObjectIdentityImpl("com.acme.domain.Document", documentId);
MutableAcl acl = (MutableAcl) mutableAclService.readAclById(oid);

int index = acl.getEntries() == null ? 0 : acl.getEntries().size();
acl.insertAce(index, BasePermission.READ,
              new PrincipalSid("bob"), true);

if (acl instanceof AuditableAcl auditableAcl) {
    auditableAcl.updateAuditing(index, true, true);
}

mutableAclService.updateAcl(acl);
~~~

Key imports: `ObjectIdentityImpl`, `BasePermission`, `PrincipalSid`, `MutableAcl`, `AuditableAcl`, `MutableAclService`, and `ObjectIdentity` from `org.springframework.security.acls.domain` and `org.springframework.security.acls.model`.

Meaning:
1. `insertAce` creates an ACE in the mutable ACL; `true` means GRANT, not enabling auditing.
2. `updateAuditing(index, auditSuccess, auditFailure)` sets the audit flags of the **ACE at index** (`AuditableAcl` API).
3. `updateAcl` persists the mutation to ACL storage.
4. `AuditLogger` may be called when evaluating a matching permission, depending on the ACE's audit flags, strategy, `administrativeMode`, and call path.
5. All four steps **still do not record** "Carol changed the ACL at 10:15 for CASE-208." A dedicated mutation audit must be designed.

**Never store an ACE's list index as an immutable identifier.** `ace_order` can shift on insert/delete/reorder. When auditing, record the persisted `ACE database ID` if available and/or a stable tuple (SID, mask, granting, object, sequence/revision), along with before/after snapshots; never store only the index hoping to look up the same ACE later.

### 4.3. AuditLogger and ConsoleAuditLogger

~~~java
// Illustrative configuration code for Spring Security ACL.
@Bean
PermissionGrantingStrategy permissionGrantingStrategy() {
    return new DefaultPermissionGrantingStrategy(
            new ConsoleAuditLogger());
}
~~~

`DefaultPermissionGrantingStrategy` invokes `AuditLogger.logIfNeeded(boolean granted, AccessControlEntry ace)` during evaluation when the relevant audit flag demands logging. `ConsoleAuditLogger` is a simple implementation printing to stdout. It **is not** an immutable event store, lacks standard correlation IDs, and does not guarantee multi-year historical queries.

For production-grade access events, you can supply a custom `AuditLogger`:

~~~java
// Snippet: sink is an application-implemented interface.
final class StructuredAclAuditLogger implements AuditLogger {
    private final DecisionAuditSink sink;

    StructuredAclAuditLogger(DecisionAuditSink sink) {
        this.sink = sink;
    }

    @Override
    public void logIfNeeded(boolean granted, AccessControlEntry ace) {
        if (!(ace instanceof AuditableAccessControlEntry auditable)) {
            return;
        }
        if ((granted && !auditable.isAuditSuccess())
                || (!granted && !auditable.isAuditFailure())) {
            return;
        }
        sink.offer(ace.getAcl().getObjectIdentity(),
                ace.getSid(), ace.getPermission(), granted);
    }
}
~~~

This is a **non-standalone** snippet, missing the `DecisionAuditSink` interface and bean wiring. The log hook receives the **deciding ACE and granted flag**, yet **does not automatically provide** the calling actor, request ID, tenant, full evaluated SID list, role snapshot, or outcomes of other policy checks. When those are needed, emit an `AuthorizationDecisionEvent` at the service/security boundary where full context and trace IDs are available. Avoid slow/external blocking I/O directly inside the logger on the authorization hot path; use a non-blocking sink with backpressure, policy-driven sampling, and loss-prevention guarantees if required for compliance.

**Note:** `administrativeMode=true` in `Acl.isGranted(..., administrativeMode)` has special meaning: per Javadoc, administrative-mode checks skip auditing. Never use `administrativeMode` to "silence logs for speed" on normal access paths.

## 5. Which Fields Should a Mutation Audit Record?

An event should capture **who requested it**, **what permission changed**, **which object was affected**, **whether it succeeded or failed**, and **transaction correlation evidence**.

| Recommended field | Purpose |
| --- | --- |
| `eventId` | Unique ID for deduplication and reconciliation |
| `occurredAt` | UTC timestamp from a trusted clock |
| `actorId` | Stable principal ID/service identity, not merely a display username |
| `actorType` | USER / SERVICE / SYSTEM; if "on behalf of," also record the requester |
| `tenantId` | Data boundary, never directly self-declared by the client |
| `objectType` + `objectId` | Full `ObjectIdentity`; bare IDs easily collide across resource types |
| `action` | ACL_CREATED, ACE_GRANTED, ACE_DENIED, ACE_REMOVED, ACE_PERMISSION_CHANGED, ACL_OWNER_CHANGED, PARENT_CHANGED, INHERITANCE_CHANGED, ACL_DELETED |
| `sidType` + `sidValue` | PRINCIPAL vs. AUTHORITY; e.g., Bob vs. ROLE_REVIEWER |
| `permissionMask` + `permissionName` | Permission per `BasePermission` or custom Permission |
| `before` / `after` | Canonical snapshot/diff, never inferred from the current ACL |
| `aclRevisionBefore/After` | Monotonic per-object revision to detect lost events or races |
| `reasonCode` / `ticketId` | Approved justification or validated case ID |
| `correlationId` / `requestId` | Links HTTP requests, traces, domain events, and policy decisions |
| `outcome` | SUCCESS / REJECTED / FAILED; distinguish committed facts clearly |
| `policyVersion` | Policy/ACL evaluator version for historical replay |
| `source` | API, batch job, migration, or admin console |
| `integrityMetadata` | Sequence/hash/signature/retention metadata if tamper evidence is required |

**Distinguish request attempts from committed changes.** "Admin clicked Save" does not mean the DB committed. If failed mutation attempts must be audited, write them to a separate security-event stream rather than mixing them into the committed-mutation ledger. An official `"ACE_GRANTED"` fact is confirmed only after the ACL change commits per contract.

### 5.1. Why Store Both Before and After?

Suppose ACE `ROLE_REVIEWER WRITE = DENY` is flipped to `GRANT` with the same SID and mask. An "UPDATE ACE" event alone does not tell whether access expanded or narrowed. Record:

~~~json
{
  "action": "ACE_UPDATED",
  "objectType": "Document",
  "objectId": "42",
  "sidType": "AUTHORITY",
  "sidValue": "ROLE_REVIEWER",
  "before": {"mask": 2, "granting": false},
  "after":  {"mask": 2, "granting": true},
  "reason": "APPROVAL-314"
}
~~~

The `2` here is the standard `BasePermission.WRITE` mask in Spring ACL; with custom permissions, record your application's actual mapping. For parent or inheritance changes, snapshot both old/new parent ObjectIdentities and before/after `entriesInheriting`, not just ACEs.

### 5.2. Snapshot or Diff?

- **Diffs** are compact and easy to search: "granted READ to Bob."
- **Periodic full snapshots** every N revisions make historical reconstruction and gap recovery faster.
- You can store both canonical diff events and periodic snapshots.
- When events serve as compliance evidence, schemas must be versioned with retention and immutability policies. Avoid logging raw Authentications/tokens/secrets or full document contents.
- With parent inheritance, explaining historical permissions requires preserving or reconstructing **both the ACL ancestor chain and corresponding identity/role memberships**.

## 6. Record Mutation Audits Only Where ACL Modifications Are Authorized

A typical flow looks like:

~~~text
PATCH /api/documents/42/acl/grants
    |
    +-- authenticate admin, principal/tenant
    +-- @PreAuthorize("hasAuthority('acl:manage')")
    +-- domain policy: is admin allowed to edit Document 42's ACL?
    +-- check whether recipient SID/permission are valid?
    +-- transaction:
            read ACL with lock / optimistic version
            calculate before
            insertAce/updateAce/deleteAce/...
            updateAcl
            persist audit_outbox / audit_change
            commit atomically
    +-- response success after commit
~~~

Never generate audit events in the UI or trust a client-sent "after" payload. Audit records must be created server-side from verified before/after ACL snapshots. Permission-editing APIs must never infer ACL modification rights from a user holding `READ` on the Document.

### 6.1. ACL Modification Authorization and Mutation Auditing Are Separate Concerns

Spring ACL provides `AclAuthorizationStrategy` to guard certain mutations on `MutableAcl`. For instance, `AclAuthorizationStrategyImpl` may require admin/owner privileges per change type; that is an internal check, not a substitute for business policies:

- Alice may own a Document yet **must not** transfer permissions to another tenant.
- An admin of tenant A must not edit an ACL ObjectIdentity belonging to tenant B.
- Someone allowed to share READ should not necessarily be able to grant WRITE/DELETE/ADMINISTRATION to others.
- Changing `entriesInheriting` or `parentAcl` can cascade permissions to thousands of descendants; require dedicated privileges, reason codes, and impact audits.

Note: never assign `ROLE_ACL_ADMIN` to every request by default "so `updateAcl` won't fail." That creates a direct privilege-escalation hole.

### 6.2. Writing Audits in the Same Transaction

If domain, ACL, and audit outbox share the same database or a single true transaction resource, place `@Transactional` on the application service invoked through a Spring proxy. When the transaction rolls back, neither the ACL change nor any "committed" outbox row remains. After commit, a worker moves events from the outbox to an append-only audit store idempotently by `eventId`.

**`@Transactional` alone does not guarantee atomicity** if:
- JDBC ACL uses a different DataSource/transaction manager than the audit DB.
- You send to Kafka/HTTP audit services mid-transaction and later roll back.
- A Spring method is self-invoked, bypassing the transaction proxy.
- The ACL mutation runs `@Async` on another thread (caller transaction context does not automatically propagate).
- The audit event is emitted after commit and the process crashes before sending.

When event loss is unacceptable, a transactional outbox is far more reliable than making network calls mid-request and hoping "both succeed."

## 7. SQL Audit Outbox: A Practical Design

Manage with application migrations (e.g., PostgreSQL; adapt column types per DB):

~~~sql
-- Design TEMPLATE; add constraints/partitions/RLS per real system.
CREATE TABLE acl_audit_outbox (
    event_id        UUID PRIMARY KEY,
    tenant_id       VARCHAR(120) NOT NULL,
    object_type     VARCHAR(240) NOT NULL,
    object_id       VARCHAR(120) NOT NULL,
    acl_revision    BIGINT NOT NULL,
    actor_id        VARCHAR(160) NOT NULL,
    action          VARCHAR(80) NOT NULL,
    event_payload   JSONB NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    published_at    TIMESTAMPTZ NULL,
    publish_attempt INT NOT NULL DEFAULT 0,
    UNIQUE (tenant_id, object_type, object_id, acl_revision)
);
~~~

**Explanation:**

- `event_id` supports publisher retries and consumer deduplication.
- `tenant_id + object_type + object_id + acl_revision` helps enforce per-object ordering; revisions must be allocated **atomically**.
- `event_payload` contains before/after and `correlationId`, never secrets.
- `published_at` only marks handoff to downstream per contract; it **does not** guarantee downstream processed it if acks/commits fail.
- `publish_attempt` supports failure monitoring.
- `UNIQUE(...)` applies when **each revision emits one consolidated event**. If one mutation emits multiple events, add `event_sequence` or pack diffs into one event rather than leaving a unique constraint that fails the second insert.

This SQL is illustrative DDL; for MySQL/H2 adjust `UUID`/`JSONB`/`TIMESTAMPTZ` accordingly. Beyond the outbox, maintain a separate append-only **audit ledger/history** for long-term queries instead of deleting events as soon as the publisher finishes.

### 7.1. Sample Payload

~~~json
{
  "eventId": "d9bc3cb0-68ae-4a96-a344-d3067d1cda31",
  "schemaVersion": 1,
  "actor": {"kind": "USER", "id": "carol-17"},
  "resource": {
    "tenantId": "tenant-alpha",
    "type": "com.acme.domain.Document",
    "id": "42"
  },
  "action": "ACE_GRANTED",
  "revision": {"before": 7, "after": 8},
  "changes": [{
    "sidType": "PRINCIPAL",
    "sid": "bob-23",
    "permission": "READ",
    "mask": 1,
    "before": null,
    "after": {"granting": true, "auditSuccess": true, "auditFailure": true}
  }],
  "reasonCode": "TICKET-814",
  "correlationId": "req-54bb",
  "occurredAt": "2026-11-05T06:00:00Z"
}
~~~

IDs, timestamps, and actors in the payload are **example data**, not real production events. `mask:1` corresponds to standard READ; if your app uses custom `Permission`s, document the mapping explicitly.

## 8. Spring Service: Granting Permissions and Recording Events in One Boundary

This is an **integration snippet** for a project that already has ACL persistence, audit/outbox repositories, a transaction manager, and tenant policies. It is not standalone because `AclChangeOutbox`, `AclChangeOutboxRepository`, `AclRevisionRepository`, `ScopePolicy`, and `StableIdentity` are application-defined contracts.

~~~java
@Service
public class DocumentAclCommandService {
    private final MutableAclService aclService;
    private final ScopePolicy scopePolicy;
    private final AclRevisionRepository revisions;
    private final AclChangeOutboxRepository outbox;
    private final StableIdentity identity;

    public DocumentAclCommandService(
            MutableAclService aclService, ScopePolicy scopePolicy,
            AclRevisionRepository revisions,
            AclChangeOutboxRepository outbox, StableIdentity identity) {
        this.aclService = aclService;
        this.scopePolicy = scopePolicy;
        this.revisions = revisions;
        this.outbox = outbox;
        this.identity = identity;
    }

    @Transactional
    @PreAuthorize("hasAuthority('acl:manage')")
    public void grantRead(long documentId, String recipientId,
                          String reason, String correlationId) {
        String actorId = identity.requireAuthenticatedActorId();
        String tenantId = identity.requireTrustedTenantId();

        // Must check object, actor, recipient, tenant, and grant permission.
        scopePolicy.requireCanGrantRead(
                actorId, tenantId, documentId, recipientId);

        ObjectIdentity oid =
                new ObjectIdentityImpl(
                        "com.acme.domain.Document", documentId);
        MutableAcl acl = (MutableAcl) aclService.readAclById(oid);

        // Lock/version must be allocated for the same resource and transaction.
        long nextRevision = revisions.lockAndNext(
                tenantId, oid.getType(), String.valueOf(documentId));

        // Prevent duplicate ACEs: repository/policy must detect already-granted cases.
        if (hasExplicitGrant(acl, new PrincipalSid(recipientId),
                             BasePermission.READ)) {
            throw new IllegalStateException("Grant already exists");
        }

        int index = acl.getEntries() == null
                ? 0 : acl.getEntries().size();
        Sid recipient = new PrincipalSid(recipientId);
        acl.insertAce(index, BasePermission.READ, recipient, true);

        if (acl instanceof AuditableAcl auditable) {
            auditable.updateAuditing(index, true, true);
        }
        aclService.updateAcl(acl);

        // Audit event is server-generated data, in the same transaction as the ACL.
        outbox.save(AclChangeOutbox.grantRead(
                tenantId, oid, actorId, recipientId,
                nextRevision, reason, correlationId));
    }

    private boolean hasExplicitGrant(
            Acl acl, Sid sid, Permission permission) {
        List<AccessControlEntry> entries = acl.getEntries();
        if (entries == null) return false;
        return entries.stream().anyMatch(e ->
                e.getSid().equals(sid)
                && e.getPermission().getMask() == permission.getMask()
                && e.isGranting());
    }
}
~~~

**Required imports** when integrating: `org.springframework.stereotype.Service`, `org.springframework.transaction.annotation.Transactional`, `org.springframework.security.access.prepost.PreAuthorize`, `org.springframework.security.acls.model.*`, `org.springframework.security.acls.domain.*`, and `java.util.List`. The helper/repository types are application contracts you implement, not Spring Security classes.

### 8.1. Why Store Before and After Snapshots/Diffs?

`AclChangeOutbox.grantRead(...)` is deliberately an application factory. Real implementations should capture pre-mutation state (or full change tuples), recording **mask, granting, audit flags, sid type/value, and parent/inheritance/owner if changed**. Specifically:
- Never construct events solely from the request payload, since the service may normalize or reorder ACEs.
- If `updateAcl` changes ACE database IDs, record post-persist IDs if needed for lookups.
- On `deleteAce`, snapshot the removed ACE **before deleting it**.
- On `updateAce`, store both old and new permissions/masks.
- On `setParent`, store old/new parent ObjectIdentities and check tenant/cycles.

**Note on `hasExplicitGrant`:** this helper only checks for a **direct ACE** granting that exact mask to the SID; it does not detect inherited permissions. It does not replace `Acl.isGranted(...)` for evaluating effective access. For idempotency checks ("grant already exists locally"), this logic can help, though policies must also inspect opposing grants and duplicate SID/mask entries to avoid surprises.

### 8.2. Revisions and Concurrency

Default `MutableAclService`/schema does not provide an automatic **per-object historical revision** meeting all audit needs. Create your own revision table/column or use optimistic locking on domain/ACL metadata per architecture. `lockAndNext(...)` is a **hypothetical application API**, implemented via row locks, compare-and-swap, or in-transaction serialization.

Never generate revisions with `SELECT MAX(revision)+1` without locks or unique constraints: two concurrent requests could both claim revision 8. If an outbox insert fails on a duplicate revision and rolls back, retries must honor idempotency without creating duplicate grants.

### 8.3. Successful Audit Events vs. Failed Attempt Events

When `@PreAuthorize` blocks a grant call before the method body runs, no mutation occurs and no committed event is written to the service's outbox. To track unauthorized admin attempts, log an **attempt audit** at the security layer:

~~~text
ACL_CHANGE_REJECTED:
  actorId, resource, requestedAction, reasonCode, timestamp, requestId
  outcome=REJECTED
  detail=NOT_AUTHORIZED
~~~

This event must never imply permissions changed. Because a transaction rollback also wipes out that transaction's outbox writes, "failed attempt" events often need an independent, safe write path that limits sensitive data and tolerates service errors. Never let audit-logging failures open access or mask real authorization errors.

## 9. Tracing GRANT Provenance: More Data Than a Boolean

`Acl.isGranted(List<Permission>, List<Sid>, boolean)` is the **ACL permission decision oracle** (within the configured implementation and security context). A GRANT/DENY boolean alone does not say:
- Did it come from `PrincipalSid("bob")` or `GrantedAuthoritySid("ROLE_REVIEWER")`?
- Did it match a direct ACE on Document or a parent ACE on Folder?
- Did the ACE have a READ mask or a composite/custom mask?
- Was the decision constrained by tenant, feature flags, or business state?
- Was `NotFoundException` thrown for missing ACEs, or did an explicit DENY ACE match?
- Did the decision read a stale ACL cache?

### 9.1. Do Not Use getEntries to Decide Permissions Yourself

Per `Acl.getEntries()` Javadoc, that list contains ACEs **belonging to the current ACL**, without automatically merging parent ACEs. An ACL may also be loaded for only a subset of `Sid`s; `isSidLoaded(...)` must be checked when explain/debug tools expect complete data. The API recommends `isGranted(...)` for decisions, rather than guessing "whichever ACE appears first wins."

To capture **permission provenance**:
1. Generate a `decisionId` and record context: actor, tenant, resource, permission, timestamp, policy version, and the ordered SID list.
2. Use the real policy/`Acl.isGranted` to compute the outcome.
3. Capture a trace showing **evaluated candidate ACEs** and their ACL/parent source, avoiding parallel reimplementations that drift from the strategy.
4. If walking the ACL tree to explain access, ensure the same snapshot/transaction or label the output explicitly as a **best-effort current explanation**.
5. Attach the ACL revision and identity membership version when available for future replay.

`AuditLogger.logIfNeeded(granted, ace)` gives you the logged ACE, yet **does not guarantee** a complete narrative of every rule/role evaluated. When exact traces are required for sensitive systems, instrument `PermissionGrantingStrategy`/the authorization layer or build a tracing decision engine and verify equivalence in tests.

### 9.2. Permission Provenance Diagram

~~~text
Auth Bob:
  PrincipalSid("bob")
  GrantedAuthoritySid("ROLE_REVIEWER")
  ...
           |
           v
Target Document 42, permission READ
  ACL(Document 42)
  - local READ for Bob?          none
  - entriesInheriting?           true
  - parentAcl?                   Folder 9
           |
           v
  ACL(Folder 9)
  - ROLE_REVIEWER READ           GRANT
           |
           v
  ACL outcome                    GRANT
           |
           v
  Additional policy:
  - same tenant?                 true
  - account active?              true
           |
           v
  FINAL outcome                  GRANT
~~~

**Caution:** the diagram illustrates a clean path with few ACEs; never treat it as a full specification when multiple `Sid`s, permissions, or conflicting ACEs exist. `DefaultPermissionGrantingStrategy` evaluates permissions and SIDs in strict list order, and custom matchers can alter mask comparisons. Therefore, **real traces must record the algorithm/version** and never claim "any DENY always wins" or "child ACEs always override parents" across all SID combinations.

### 9.3. Inheritance and Why Access Can Propagate Widely

`Acl.getParentAcl()` represents the parent link, while `Acl.isEntriesInheriting()` decides whether parent ACEs are consulted when needed. If Documents inherit from Folder, a single ACE change on Folder can alter access to many Documents without touching any child ACE rows.

A mutation audit stating only:

~~~text
ACL_CHANGED Folder 9: ROLE_REVIEWER READ = GRANT
~~~

cannot immediately list **every** affected Document. If compliance demands a "blast radius," query descendants (across both ACL hierarchy and domain scope), compute effective rights on relevant items, and store an **impact summary** or run an evaluation job. Never emit "granted READ to all Documents" without verifying the actual policy and hierarchy.

### 9.4. Missing ACE Is Not a DENY ACE

Under `DefaultPermissionGrantingStrategy`, `Acl.isGranted(...)` may throw `NotFoundException` when no matching ACE is found along the lookup path; that is **no decision found**, distinct from an ACE with `granting=false`. In a fail-closed system, both deny the user access, yet logs should distinguish:

~~~text
DENY_EXPLICIT: matched ACE granting=false
DENY_NO_MATCH: no applicable ACE; strategy raised NotFoundException
DENY_TENANT:  ACL might grant, but required tenant policy denies
DENY_AUTHENTICATION: identity not authenticated
~~~

Distinguishing reasons helps investigate missing ACL provisioning, role changes, caching bugs, and probing attacks. Never expose these details verbatim to unauthorized clients, as they can leak object existence, ownership, or tenancy.

## 10. Historical Tracing: Permissions at 10:15 Differ from 16:00

If you store only the current ACL snapshot, the system may be **unable to reconstruct** past decisions because:

- ACEs were deleted or updated (requires mutation history).
- Parent ACL or `entriesInheriting` changed (requires hierarchy history).
- The user lost `ROLE_REVIEWER` (requires authority membership snapshots/events).
- The Document's or user's tenant changed (requires domain identity history).
- Custom permission matchers or policy deployments were upgraded (requires code/policy versions).
- A stale cache on one instance caused the decision to use a snapshot differing from the current DB (requires cache revision/decision facts).
- The token at that time carried stale authority claims despite newer directory state (requires trusted claims snapshots and revocation rules).

### 10.1. What Should a Decision Event Contain?

A structured decision event can record:

~~~json
{
  "decisionId": "dec-9acd",
  "occurredAt": "2026-11-05T03:15:00Z",
  "actorId": "bob-23",
  "tenantId": "tenant-alpha",
  "resource": {"type": "Document", "id": "42"},
  "action": "READ",
  "result": "GRANT",
  "policyVersion": "authz-2026-11-01",
  "aclRevision": 18,
  "matchedAce": {
    "sourceType": "Folder",
    "sourceId": "9",
    "sidType": "AUTHORITY",
    "sid": "ROLE_REVIEWER",
    "permissionMask": 1,
    "granting": true
  },
  "inheritancePath": ["Document:42", "Folder:9"],
  "correlationId": "req-54bb"
}
~~~

This is a **custom schema example**; Spring does not emit this exact JSON object automatically. To assert exact `matchedAce` and `inheritancePath`, instrument the decision engine on the same snapshot rather than guessing later from `AclService.readAclById(...)` at a different point in time.

### 10.2. What Must Be Retained for Reliable Investigations?

- Ordered mutation event ledger with revisions, before/after, and reasons.
- Risk-selected decision events: all sensitive DENYs, GRANTs on top-secret resources, admin actions, and sampling at very high volume (subject to legal obligations).
- Identifiers for policy version and role membership at decision time, or minimal redacted signed claims.
- Transaction/trace/request ID links, delivery status, deadlines, and alerts.
- Integrity/retention proofs and RBAC for investigators; audit-log access itself must be audited.

When evidence is missing, reports should state **"unable to verify exact historical permission cause because snapshot X is missing"**, rather than blaming users or assuming which policy ran.

## 11. Standalone Java 17 Program: Mutation Log and Provenance Explanation

The following program **does not use Spring**. It simulates one SID and one permission, checking local ACEs first and falling back to the parent when `inherits=true`. It shows how Folder permissions affect Document, how local DENY alters the outcome, how a mutation log captures who/what/before/after, and how disabling inheritance alters effective access.

Save as `AclAuditDemo.java`:

~~~java
import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;

public class AclAuditDemo {
    record Key(String sid, String permission) {}

    record Event(long revision, String actor, String resource,
                 String sid, String permission,
                 String before, String after) {}

    static final List<Event> HISTORY = new ArrayList<>();

    static final class Node {
        final String name;
        final Node parent;
        final Map<Key, Boolean> local = new LinkedHashMap<>();
        boolean inherits;
        long revision = 0;

        Node(String name, Node parent, boolean inherits) {
            this.name = name;
            this.parent = parent;
            this.inherits = inherits;
        }

        void change(String actor, String sid, String permission,
                    Boolean granting) {
            Key key = new Key(sid, permission);
            Boolean before = local.get(key);

            if (granting == null) {
                local.remove(key);
            } else {
                local.put(key, granting);
            }
            revision++;

            HISTORY.add(new Event(revision, actor, name, sid, permission,
                    describe(before), describe(granting)));
        }
    }

    static String describe(Boolean value) {
        if (value == null) return "UNSET";
        return value ? "GRANT" : "DENY";
    }

    static String explain(Node node, String sid, String permission) {
        List<String> path = new ArrayList<>();
        Node current = node;
        while (current != null) {
            path.add(current.name);
            Boolean vote = current.local.get(new Key(sid, permission));
            if (vote != null) {
                return describe(vote) + " via " + current.name
                        + " path=" + String.join(">", path);
            }
            if (!current.inherits) break;
            current = current.parent;
        }
        // Missing decision: this model returns NO_ACE rather than assigning GRANT.
        return "NO_ACE path=" + String.join(">", path);
    }

    public static void main(String[] args) {
        Node folder = new Node("Folder", null, false);
        Node document = new Node("Document", folder, true);

        folder.change("carol", "bob", "READ", true);
        System.out.println("initial=" +
                explain(document, "bob", "READ"));

        document.change("alice", "bob", "READ", false);
        System.out.println("local-deny=" +
                explain(document, "bob", "READ"));

        document.change("alice", "bob", "READ", null);
        System.out.println("after-revoke-local=" +
                explain(document, "bob", "READ"));

        document.inherits = false;
        System.out.println("inheritance-off=" +
                explain(document, "bob", "READ"));

        System.out.println("events=" + HISTORY.size());
        for (Event event : HISTORY) {
            System.out.println(event.resource() + "#" + event.revision()
                    + ":" + event.actor() + ":"
                    + event.before() + "->" + event.after());
        }
    }
}
~~~

Compile and run:

~~~bash
javac --release 17 AclAuditDemo.java
java AclAuditDemo
~~~

**Exact stdout:**

~~~text
initial=GRANT via Folder path=Document>Folder
local-deny=DENY via Document path=Document
after-revoke-local=GRANT via Folder path=Document>Folder
inheritance-off=NO_ACE path=Document
events=3
Folder#1:carol:UNSET->GRANT
Document#1:alice:UNSET->DENY
Document#2:alice:DENY->UNSET
~~~

Explanation:
- Carol grants READ on Folder, which Document initially inherits.
- Alice adds a direct DENY on Document, changing Bob's local READ outcome.
- Deleting the local DENY restores READ from Folder. **Removing a deny is not the same as adding a direct grant**, yet it can reopen effective access via inheritance.
- Disabling `inherits` blocks fallback, producing `NO_ACE` (Spring ACL may throw `NotFoundException`). The demo intentionally omits an event for toggling inheritance to illustrate an **audit gap** if only ACE changes are logged while ACL metadata changes are ignored. Real systems must emit `INHERITANCE_CHANGED`.
- Each resource tracks its own revision (Folder#1, Document#1,#2); for a global ordering, add a separate sequence or global event ID.
- This is simulation code; it does not reproduce full multi-SID/multi-mask `DefaultPermissionGrantingStrategy` and is not a transaction manager.

## 12. Proper Testing Across All Three Layers

### 12.1. Unit Testing Mutation Diffs

For a service building `AclChangeEvent`, unit tests should verify:
- Creating a new READ GRANT ACE: before UNSET, after GRANT, right actor/resource/SID/mask.
- Flipping an ACE from DENY to GRANT: before DENY, after GRANT; does not falsely emit `"ACE_CREATED"`.
- Removing a local DENY: event records DENY → UNSET, does not fabricate an explicit grant.
- Editing `audit_success`/`audit_failure`: event records audit flag changes.
- Changing ACL owner: records oldOwner/newOwner.
- Changing `parentAcl`: records oldParent/newParent and checks tenant boundaries.
- Changing `entriesInheriting`: records old/new and estimates blast radius.
- Validation/authorization failures: zero committed mutation events.
- Repository failures: outbox never marked published before commit.

A unit test mocking `MutableAclService` can verify the call sequence `read → insertAce → updateAcl → save(outbox)`, yet **cannot prove** JDBC and outbox roll back together. Write integration tests for that.

### 12.2. Integration Testing: Transactions and Reloads

In a Spring Boot test with a test DB and ACL schema:
1. Grant verified admin authority and invoke the service through a **Spring proxy**.
2. Read the current ACL back via `AclService.readAclById(...)` and read the outbox/ledger in a fresh transaction.
3. Assert the READ ACE for the exact SID, right audit flags, and one before/after event with the right revision.
4. Inject a failure in `outbox.save` after `aclService.updateAcl`; assert after rollback that neither the new ACE nor any committed event exists. Valid only if JDBC ACL and outbox truly share the transaction.
5. Inject a failure in `aclService.updateAcl`; assert no event is recorded as succeeded.
6. Replay the same `eventId`/idempotency key; consumer does not create duplicate ledger rows.
7. Run two concurrent grant/revoke operations; assert monotonic revisions/unique constraints and final state.
8. Verify across restart/reload/cache eviction, not just on the same mutable Java object.
9. Test wrong owner/tenant, forbidden actors, disallowed recipients, and out-of-scope permissions; verify none mutate the ACL.
10. Run tests against a DB dialect/transaction manager close to production; `@SpringBootTest @Transactional` rolling back at test end can hide real commit bugs.

### 12.3. Authorization Decision Tests

Test `Acl.isGranted(...)` directly with ordered `List<Permission>` and `List<Sid>` inputs. Cover these cases:

| ACL setup | Expected result and provenance to explain |
| --- | --- |
| Document local Bob READ GRANT | GRANT from Document |
| Document has no ACE, inherits=true; Folder Bob READ GRANT | GRANT from Folder |
| Document Bob READ DENY, Folder Bob READ GRANT | For single SID+READ: local DENY |
| Document inherits=false; Folder grant | Parent ignored; missing local ACE may raise NotFound |
| Parent ACE revoked | Child relying on parent grant loses access |
| Bob has both PrincipalSid and ROLE_REVIEWER SID | Outcome depends on SID, ACE/mask order; test real implementation |
| ACE `audit_success=true` | `AuditLogger` may be invoked on matching grant |
| ACE `audit_failure=true` | `AuditLogger` may be invoked on matching deny |
| `administrativeMode=true` | Per contract, administrative checks are not audited |
| Child/parent loaded SID subset | Verify `isSidLoaded`/reload before concluding |
| ACL no-match vs. explicit deny | Distinguish `NotFoundException` from false |

Add `hasPermission` tests via `@PreAuthorize`/`AclPermissionEvaluator` and HTTP `MockMvc` if endpoints are public. Avoid unit tests calling the evaluator directly and assuming the method-security proxy works.

### 12.4. Dedicated AuditLogger Tests

To test the logger:
- Supply a fake `AuditLogger` recording `logIfNeeded(granted, ace)` calls.
- Construct `AclImpl` with `DefaultPermissionGrantingStrategy(fakeLogger)` and ACEs with matching audit flags.
- Assert the callback fires when `Acl.isGranted` evaluates that ACE with `administrativeMode=false`.
- Assert no callback fires when audit flags do not match or `administrativeMode=true`.
- **Never equate** decision-audit callbacks with mutation events; test `MutableAclService.updateAcl` and the outbox separately.

## 13. Tracing from Historical Data: A Verifiable Investigation

Suppose a security engineer investigates Bob's access at time T.

### Step 1 — Identify the Request/Decision

Search by `decisionId` or `correlationId` rather than just username and timestamp. Confirm the request actually passed through auth filters/method-security proxies, the target `ObjectIdentity`, and the permission type.

### Step 2 — Determine Actor, Authorities, and Tenant at T

From trusted authentication logs/claims snapshots: who Bob was (stable ID), which authorities were active, and account status/tenant. Never substitute current roles for roles at T.

### Step 3 — Reconstruct the ACL at T

From the mutation ledger/snapshots:
- Document's `ObjectIdentity`.
- Local ACE list with `ace_order`, SIDs, masks, granting, and audit flags.
- Parent chain and `entriesInheriting` at each level.
- Mutations before/after time T, per-object and parent revisions.
- Cached ACL state served on that request, if metadata exists.

### Step 4 — Replay Against the Decision Engine/Policy at T

Use the same-version strategy/mask matcher and the logged ordered SID/permission lists; compare against the recorded final decision. Never write "an approximate rule" and present it as exact proof. If environment/policy version is missing, mark the conclusion as best-effort.

### Step 5 — Locate the Grant Origin

Example:

~~~text
Result: GRANT READ for Document 42
Observed origin:
  ACE #375 at Folder(9), ROLE_REVIEWER, READ, granting=true
  Inheritance path: Document(42) -> Folder(9)
  Change event that introduced ACE: EVT-8821
  Actor: carol-17; reason TICKET-814
  ACL revision: Folder(9)#18
  Bob membership evidence: ROLE_REVIEWER at T
  Additional required policies: tenant/active checks PASS
Confidence: high only if event, decision, identity snapshots align
~~~

If `decisionId` or role history is missing, never assert "Bob was definitely granted at T"; separate observed evidence from assumptions.

### Step 6 — Verify Impact and Close the Investigation

Check other sensitive documents inheriting from Folder, subsequent revocations, active sessions, download/exfiltration signals, audit integrity, and remediation. Never treat every GRANT audit log as proof data was actually downloaded: authorization GRANT can succeed before a controller/DB error aborts the response. To know whether data was accessed, correlate with separate access/business/HTTP outcome logs.

## 14. Operations: Integrity, Retention, Log Access Control, and Alerts

### 14.1. Preventing History Tampering/Deletion

An audit table writable by the same business admin role is untrustworthy if that admin can run `DELETE FROM audit_events`. Effective safeguards:
- Append-only IAM/DB permissions (no UPDATE/DELETE for the application role).
- Stream post-commit events to an administratively isolated store; immutable/WORM retention where compliance mandates.
- Sequence IDs, revisions, and hash chains/signatures to detect tampering **when keys and independent anchors are properly deployed**.
- Monitoring for publication gaps, duplicate event IDs, out-of-order sequences, offset lag, clock skew, and sync failures.
- Auditing access to **the audit logs themselves**, restricting investigators by tenant/need-to-know.

Never claim an in-DB hash chain inside the same database is "tamper-proof": someone able to modify both records and hashes can rewrite the chain. Independent anchors, secret keys, or external ledgers are required for strong tamper evidence.

### 14.2. Never Expose Sensitive Data

Log: stable actor ID, resource type/ID, verified tenant ID, policy-compliant SID type/value, permission mask/action, revision, reason code, correlation ID.

Do not log:
- Raw Authorization/Bearer headers, passwords, refresh/access tokens.
- `Authentication#getCredentials()` or full principal details.
- Document contents, ACL secrets, or internal policy internals beyond audit requirements.
- Excessive PII just for debugging convenience; apply redaction or field-level encryption where needed.

`ConsoleAuditLogger` can print ACE info to stdout; if production logs are broadly readable or forwarded externally, use a controlled structured sink instead of default console debugging.

### 14.3. Choosing Audit Granularity by Risk

| Case | Recommended audit level |
| --- | --- |
| Add/remove admin/WRITE/DELETE ACE | **Mandatory** mutation event, reason/approval, anomaly alerts |
| Reparent, enable inheritance on subtree | Metadata audit, impact analysis, and permission-expansion alerts |
| Change ACL owner | Audit old/new owner and acting authority |
| READ on sensitive resources | Decision GRANT and business access outcome per policy |
| Repeated DENYs from tenant/ACL | Security monitoring for enumeration/probing |
| Millions of public non-sensitive READs | Consider sampling/aggregation without dropping mandatory events |
| ACL/outbox publisher failure | Error alerts, retries/dead-letter queue, gap checks |
| Querying audit history | Dedicated audit of who queried, purpose, and exports |

Retention must follow legal/contractual/data-sensitivity rules for the organization; never pick arbitrary periods. If personal data must be erased while retaining minimal security events, use pseudonymization/key separation aligned with legal policy.

## 15. Common Pitfalls and Fixes

### Mistake 1 — Thinking Enabling audit_success/audit_failure Logs Who Changed the ACL

Wrong. Both flags live on ACEs and govern **decision auditing**. Mutation history requires transactionally written events or DB CDC enriched with actor/before/after context; raw CDC alone rarely knows the reason or requester.

### Mistake 2 — Using ConsoleAuditLogger as an Audit Ledger

`ConsoleAuditLogger` writes basic logs with no immutability, retention, correlation, redelivery, access control, or schema versioning. Use a structured durable audit store/outbox for investigations.

### Mistake 3 — Logging "grant READ" Without SID Type

`PrincipalSid("REVIEWER")` differs from `GrantedAuthoritySid("REVIEWER")`. Omitting SID type confuses an individual grant with a group grant. Log full type/value/permission mask.

### Mistake 4 — Storing Only Object ID

Document 42 and Invoice 42 can share the same ID. Always record `ObjectIdentity` as **type + ID** plus trusted tenant scope.

### Mistake 5 — Logging Only Post-Update State

Without `before`, you cannot tell whether DENY→GRANT, grant→deny, owner change, or parent change happened. Record diffs/snapshots and revisions.

### Mistake 6 — Ignoring Parent/Inheritance Changes

Permissions can cascade down an entire subtree without creating child ACEs. Audits must cover `setParent`/`setEntriesInheriting`/ACL deletion and blast radius.

### Mistake 7 — Ignoring Role Membership Changes

Bob gained `ROLE_REVIEWER` at t1 even though the ACE was created at t0. Effective access can appear **without touching the ACL**. Audit identity/role policies and correlate with ACL decisions.

### Mistake 8 — Using getEntries() as a Permission Oracle

`getEntries()` omits inherited ACEs, and the ACL may have only partial SIDs loaded. Use `Acl.isGranted(...)`/real policies for decisions; provenance/explain must share the same snapshot and algorithm.

### Mistake 9 — Treating a DENY ACE and a Missing ACE as Identical

`NotFoundException` differs from `false` caused by an explicit DENY. Both fail closed, yet logs must distinguish reasons to debug provisioning or caching bugs.

### Mistake 10 — Sending Audit Events Over the Network Inside a Rolling-Back Transaction

The audit stream could record "grant committed" even though the DB rolled back. Use an outbox in the same DB transaction, publish after commit idempotently, and distinguish attempts from committed mutations.

### Mistake 11 — Using @Transactional Alone Across Unshared DataSources

It does not guarantee ACL DB, outbox DB, and domain DB roll back together. Atomicity must be proven with failure-injection integration tests, not assumed from annotations.

### Mistake 12 — Missing Revisions/Locks When Two Admins Edit the Same ACL

Events can arrive out of order, and one ACL update can suffer last-write-wins. Use locks/optimistic versioning and unique event revisions, and test concurrent updates.

### Mistake 13 — Reading Today's ACL to Explain Last Month's Access

Roles, parents, SIDs, and ACEs change over time; inspecting current state does not prove historical state. Keep decision snapshots, event history, and policy versions.

### Mistake 14 — Logging All Principal Details or Tokens

Audit logs can become an easily accessible secret store. Store only necessary fields, redact, scope by tenant, encrypt, and apply purpose-bound retention.

### Mistake 15 — Not Auditing Access to the Audit System Itself

Someone able to read or export audit logs can learn sensitive resource histories. Apply RBAC/ABAC, MFA for sensitive investigations, and audit search/export actions.

### Mistake 16 — Treating GRANT as Proof Data Was Downloaded

An authorization GRANT is only a **permission decision**; it does not prove HTTP returned 200 or bytes were downloaded. Correlate with business events, response statuses, and object-storage access logs when investigating real access.

## 16. Pre-Release QA Matrix

| Case | What must be proven |
| --- | --- |
| Direct READ ACE grant | Both ACL and committed event exist after commit |
| Delete or flip ACE | Accurate before/after, no loss of older history |
| Change parent/inherit | Event covers metadata; cascading access verified |
| Change ACL owner | Old/new owner, actor, and reason recorded |
| ACL write fails before commit | No committed event or partial permission change |
| Outbox insert fails | ACL mutation rolls back if sharing transaction |
| Publisher retry | Consumer deduplicates by eventId, no duplicate ledger rows |
| Two concurrent mutations | Per-object revisions neither collide nor reorder |
| Unauthorized actor | ACL unchanged; attempt audited if required |
| Cross-tenant recipient | Denied; ACL untouched and other users unexposed |
| Inherited READ | Trace pinpoints parent source and inheritance path |
| Local DENY on child | Trace shows exact decision for tested SID/permission |
| Multiple SIDs/permissions | Trace matches `DefaultPermissionGrantingStrategy`, no guessed rules |
| All ACEs absent | Distinguishes NotFound vs. explicit DENY |
| Audit flags off / administrativeMode | Never claim decision callback fires unless configured |
| Role changed while ACL unchanged | Historical decision differing from current decision is explained accurately |
| Multi-instance cache | Post-revoke ACL revisions/caches converge within SLA |
| Audit export/search | RBAC, tenant scoping, and auditing of audit-store access |
| Retention / integrity | Tampering/gaps detected per chosen design |

### Exercise 1 — "Who Granted READ to Bob?"

Document 42's ACL has no local ACEs, while Folder 9 has `ROLE_REVIEWER READ = GRANT`. Bob currently holds `ROLE_REVIEWER`. Looking only at the current tables, can you tell who granted access?

**Answer:** No. You can explain that current effective permission likely inherits from Folder's ACE, yet cannot tell **who or when** the ACE was created without a mutation audit. Proving history requires membership, policy/ACL revisions, and decision logs at the target timestamp.

### Exercise 2 — Does Disabling Inheritance Require Auditing?

Document 42 still references parent Folder 9, while `entriesInheriting` flips true→false. No ACEs were deleted. Should an event be emitted?

**Answer:** Yes. Effective permissions can change drastically; the event should record actor, old/new inheritance, parent, object, revision, and reason. It is a policy mutation even when `acl_entry` rows do not change.

### Exercise 3 — Is Deleting a Local DENY a Grant?

Document has a local READ DENY for Bob, Folder has READ GRANT for `ROLE_REVIEWER`, and Bob holds that role. An admin deletes the local DENY. What happens?

**Answer:** Effective READ may open up via fallback to Folder under the specific SID/strategy combination. The mutation event is **ACE_REMOVED** with before DENY→after UNSET, never mislabeled as "granted local READ ACE."

### Exercise 4 — Why Is a Transactional Outbox Needed?

ACL `updateAcl` succeeds in the DB, yet calling a remote audit service fails. Returning success without logging loses the trail; logging remotely first before a local DB rollback creates a fake event. What is the fix?

**Answer:** Write the outbox row and ACL mutation in the same proper DB transaction; an after-commit publisher delivers to a durable audit store with event ID/idempotency, retries, and monitoring. If two DBs cannot share a transaction, design dedicated compensation/consistency.

### Exercise 5 — Why Doesn't a Decision Log Prove a Successful Download?

`AuditLogger` logs GRANT READ, then the controller throws 500. Can an investigator conclude Bob downloaded the full content?

**Answer:** No. GRANT is only the authorization check result; correlate with HTTP responses, business access/outbox logs, or object-storage logs to verify whether data was actually served.

## 17. Summary

Complete ACL auditing requires **three linked data layers**:

1. **Mutation history**: who changed ACE/owner/parent/inheritance, before and after, on which `ObjectIdentity`, why, revision, and commit status.
2. **Authorization decision audit**: who requested what permission, which policy/ACL version was evaluated, GRANT/DENY/NO_MATCH outcome, correlated with HTTP/business outcomes.
3. **Permission provenance**: if granted, which exact SID/ACE/ACL granted it; whether via parent or role membership; historical investigations require snapshots of identity, ACL, and policy **from that time**.

`audit_success`/`audit_failure` flags and `ConsoleAuditLogger` assist with decision logging, **never replacing** transactional mutation auditing with retention, integrity, and explainability. Use `Acl.isGranted` as the decision basis; any explain tooling must align with the strategy and snapshot rather than guessing from a local ACE list.

**Final principle:** *A permission change is only "real" once committed; a permission is only "granted" when the decision engine allowed it in the right context and moment; an investigation conclusion is only trustworthy when backed by evidence from both.*

## Official Documentation

- [Spring Security – Domain Object Security (ACLs)](https://docs.spring.io/spring-security/reference/servlet/authorization/acls.html): ACL table model, `AclService`, `MutableAclService`, `DefaultPermissionGrantingStrategy`, and `AuditLogger` wiring.
- [DefaultPermissionGrantingStrategy Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/DefaultPermissionGrantingStrategy.html): Permission/SID order, auditing, and `NotFoundException`.
- [AuditLogger Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/AuditLogger.html): `logIfNeeded(granted, ace)`.
- [ConsoleAuditLogger Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/domain/ConsoleAuditLogger.html): basic console audit logger for ACEs.
- [AuditableAcl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/AuditableAcl.html): `updateAuditing(aceIndex,auditSuccess,auditFailure)`.
- [Acl Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/Acl.html): `getEntries`, `isSidLoaded`, `isGranted`, parent/inheritance.
- [AccessControlEntry Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/AccessControlEntry.html): SID, Permission, grant/deny, ACE ID.
- [MutableAclService Javadoc](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/acls/model/MutableAclService.html): create/update/delete ACL; the API itself is not a mutation event store.
- [Spring Framework – Declarative Transactions](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): proxy/transaction boundaries and why shared transaction resources must be verified.
