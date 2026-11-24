# Testing Ownership Changes During Request Processing

## Objective and Risks to Detect

In a Spring Security system, a user can **hold permission** at check time yet **lose permission** before the data write takes place. For example: Alice requests to edit her document, and the request passes the authorization check; an administrator transfers the document to Bob; Alice's stale request still proceeds to save and overwrite the data. This is a **time-of-check/time-of-use (TOCTOU)** authorization flaw.

This lesson focuses on testing scenarios where *ownership or policy changes while a request is in flight*, rather than merely checking that a new request gets 403 when lacking permission. After this lesson, you should know how to: identify the invariant to protect; coordinate two transactions to reproduce an ordered race; enforce permissions at the point of effect; verify the database, version, and side effects; and recognize the limits of `@PreAuthorize`, `@Transactional`, and optimistic locking.

Suppose `Document` has `id`, `ownerId`, `body`, `status`, and `version`; Alice may edit only when the document is `ACTIVE`, currently owned by Alice, and permitted by the active policy. The client sends `documentId`, the new body, and `expectedVersion`; **Alice's identity must come from the server-authenticated principal**, never trusting a client-declared `actorId` or `ownerId`.

**Invariant:** every accepted update must satisfy the authorization condition at the point the update is applied according to the system's consistency contract; an earlier grant does not carry permanent authority. If the policy requires permission to remain valid until commit, the transaction/locking mechanism must genuinely preserve that invariant until commit. All relevant write paths (HTTP, ownership transfer, batch, consumers) must follow the same mechanism.

## 1. The TOCTOU Scenario to Reproduce

1. **T0 — Check:** document D belongs to Alice, `version=1`. Alice's edit request passes `@PreAuthorize` or a policy service, then pauses before the write operation.
2. **T1 — Ownership transfer:** another transaction changes D's `ownerId` to Bob, increments `version` to 2, and **commits**.
3. **T2 — Resume:** Alice's stale request runs its data update using the state read at T0.
4. **Expected:** `body` is unmodified, no "edit succeeded" event is emitted, ownership remains with Bob; the request is denied or returns a conflict per the API contract.

If at T2 the system executes `UPDATE document SET body = ? WHERE id = ?`, the check at T0 fails to prevent unauthorized modification. The test must control the T0–T1–T2 ordering and observe the **actual write point**.

## 2. Why Early Permission Checks Are Not Enough

Spring Security 6 provides `@EnableMethodSecurity`, `@PreAuthorize`, `PermissionEvaluator`, and authorization services to block requests by principal, role, ACL, or business policy. They are valuable, but passing a check at method entry neither locks the row automatically nor re-checks all conditions on database flush.

Race-prone code example (sketch only, **not a safe implementation**):

```java
@PreAuthorize("@documentPolicy.isOwner(authentication, #documentId)")
@Transactional
public void editUnsafe(UUID documentId, String newBody) {
    Document document = repository.findById(documentId).orElseThrow();
    document.setBody(newBody); // Owner can change during processing.
}
```

Even when a method carries both `@PreAuthorize` and `@Transactional`, you cannot assume permission is protected until commit: advice ordering, transaction isolation, locks, persistence context, and the actual SQL executed determine behavior. Under `READ_COMMITTED`, reading permission once at T0 does not turn that condition into an invariant at T2. With loaded entities, in-memory state can be staler than the database.

Two strategies are commonly applied depending on business requirements:

- **Atomic conditional update:** put predicates for actor, owner, status, and version directly into the `UPDATE`'s `WHERE` clause and inspect the affected row count. Fits changes expressible as a single update statement.
- **Intentional in-transaction locking:** use `SELECT ... FOR UPDATE` or JPA `PESSIMISTIC_WRITE` when multi-step read–compute–write is needed; both ownership-transfer and edit paths must follow the same locking strategy. Test lock ordering, deadlocks, timeouts, and retries as well.

No single annotation protects every dynamic policy. When permission depends on other tables, group memberships, ABAC, or workflow state, concurrency must be controlled consistently for the data deciding that permission, not just `ownerId`.

## 3. Spring Data JPA Example: Authorization Conditions at the Write Point

The following snippets are **illustrative components inside an existing Spring Boot application** with entity `Document`, enum `DocumentStatus`, and a security principal. They are not standalone programs.

```java
public interface DocumentRepository extends JpaRepository<Document, UUID> {
    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update Document d
           set d.body = :body,
               d.version = d.version + 1
         where d.id = :documentId
           and d.ownerId = :actorId
           and d.status = :activeStatus
           and d.version = :expectedVersion
        """)
    int updateIfStillOwned(
            @Param("documentId") UUID documentId,
            @Param("actorId") UUID actorId,
            @Param("expectedVersion") long expectedVersion,
            @Param("activeStatus") DocumentStatus activeStatus,
            @Param("body") String body);
}
```

```java
@Service
public class DocumentEditService {
    private final DocumentRepository repository;

    public DocumentEditService(DocumentRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void edit(
            UUID authenticatedActorId,
            UUID documentId,
            long expectedVersion,
            String newBody) {

        int affected = repository.updateIfStillOwned(
                documentId, authenticatedActorId, expectedVersion,
                DocumentStatus.ACTIVE, newBody);

        if (affected != 1) {
            throw new AccessDeniedException("Resource unavailable or changed");
        }
    }
}
```

`authenticatedActorId` **must only be produced server-side from the authenticated identity**. If the client sends an `ownerId` field, it must never be used as the acting identity. In JPA, JPQL syntax must match entity property names; `Document.version` is a numeric field. If the entity uses `@Version`, remember that **bulk JPQL updates do not automatically check or increment the version via normal entity update mechanics**: the example above includes both the version predicate and an explicit version increment. The ownership-transfer path must also increment the version and obey the same concurrency constraints.

`@Modifying` returns the updated row count: `0` can mean the document does not exist, has a different owner, is locked, or has a stale version. The API must consistently return 403, 404, or 409 without disclosing existence/current owner to unauthorized callers. The example picks one generic error for illustration; a product may map errors differently per its defined policy. `flushAutomatically` and `clearAutomatically` affect the persistence context, so transactions should stay narrow and never continue using stale cached entities after a bulk update.

A conditional `UPDATE` on the **same row** controls edit/transfer races on that row via database locking mechanics. It does not automatically solve policies stored in other tables or external side effects. Never send emails, write files, or publish success events **before** confirming the update succeeded.

## 4. Java 17+: Simulating an Ordered Race with Deterministic Results

This standalone example uses `CountDownLatch` to pause the older request after its check; `ConcurrentHashMap.computeIfPresent` makes updates and ownership transfers atomic on the same key. This model illustrates the test mechanics and **does not replace integration tests with real transactions**.

Save as `OwnershipRaceDemo.java`:

```java
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.atomic.AtomicBoolean;

public class OwnershipRaceDemo {
    record Document(long id, String owner, String body, long version) {}

    private static final ConcurrentHashMap<Long, Document> STORE =
            new ConcurrentHashMap<>();

    static boolean canEdit(long id, String actor) {
        Document d = STORE.get(id);
        return d != null && d.owner().equals(actor);
    }

    static void transferOwner(long id, String newOwner) {
        STORE.computeIfPresent(id, (key, d) ->
                new Document(d.id(), newOwner, d.body(), d.version() + 1));
    }

    static boolean guardedUpdate(
            long id, String actor, long expectedVersion, String newBody) {
        AtomicBoolean changed = new AtomicBoolean(false);
        STORE.computeIfPresent(id, (key, d) -> {
            if (!d.owner().equals(actor) || d.version() != expectedVersion) {
                return d;
            }
            changed.set(true);
            return new Document(d.id(), d.owner(), newBody, d.version() + 1);
        });
        return changed.get();
    }

    static void await(CountDownLatch latch) {
        try {
            latch.await();
        } catch (InterruptedException e) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException(e);
        }
    }

    public static void main(String[] args) throws InterruptedException {
        STORE.put(7L, new Document(7L, "alice", "old", 1L));

        CountDownLatch checked = new CountDownLatch(1);
        CountDownLatch transferred = new CountDownLatch(1);

        Thread editingRequest = new Thread(() -> {
            boolean allowedAtT0 = canEdit(7L, "alice");
            checked.countDown();
            await(transferred);
            boolean updatedAtT2 = guardedUpdate(7L, "alice", 1L, "new");
            System.out.println("Precheck alice: " + allowedAtT0);
            System.out.println("Guarded update: " + updatedAtT2);
        });

        editingRequest.start();
        checked.await();             // T0: authorization check has occurred.
        transferOwner(7L, "bob");    // T1: ownership transferred to Bob.
        transferred.countDown();     // T2: stale request resumes.
        editingRequest.join();

        Document finalState = STORE.get(7L);
        System.out.println("Final: " + finalState.owner()
                + ", " + finalState.body()
                + ", v" + finalState.version());
    }
}
```

Run on JDK 17 or newer:

```bash
javac OwnershipRaceDemo.java
java OwnershipRaceDemo
```

Stdout output:

```text
Precheck alice: true
Guarded update: false
Final: bob, old, v2
```

Alice **held permission at T0**, yet was blocked at write time T2 after ownership changed. Avoid `Thread.sleep`: two latches guarantee ordering regardless of machine speed. Replacing `guardedUpdate` with a write filtering only by `id` can produce `body=new` even though Alice lost permission—precisely the bug to detect.

## 5. Integration Test with Two Real Transactions

A unit test mocking `updateIfStillOwned(...)` to return `0` proves error handling, but **does not prove** the database handles the race properly. Use `@SpringBootTest` with a production-like database (e.g., PostgreSQL Testcontainers if the system uses PostgreSQL), real repositories, and two independent transactions with observable commits.

Test construction steps:

1. Create Alice, Bob, and document D owned by Alice with `body="old"`, `version=1`, `status=ACTIVE`. Commit the seed data.
2. Thread A invokes Alice's edit path; place a test hook/barrier after the pre-check and right before the update statement. Signal `checked`, then wait for `continueWrite`.
3. Thread B transfers ownership of D to Bob and increments the version in another transaction; wait for a **successful commit** before releasing `continueWrite` for A.
4. Wait for both threads with finite timeouts; if A uses a conditional update, affected rows must equal `0` or the service must throw the matching exception. Failures must never silently turn into successes.
5. From a **fresh transaction**, re-read the database: `ownerId=Bob`, `body="old"`, version reflects the transfer; no "edit succeeded" outbox/event/audit exists for A. Check HTTP status and error message per contract, without leaking Bob's info if Alice lacks permission.

Place the pause point at the **exact boundary**: after pre-check, before write. When using pessimistic locking, transaction B may have to block waiting for A; do not add a barrier forcing B to commit before A if A already holds a lock blocking B, as that creates an artificial test deadlock. In that case, verify serialization and outcomes under actual lock ordering.

An important Spring Test note: `@Transactional` on a test method rolls back by default after the test, which can make uncommitted seed data **invisible to other threads**. Manage commits explicitly via `TransactionTemplate` or a separate transactional service, keeping tests independent of hidden rollbacks. Never share an EntityManager across threads; shut down executors; enforce timeouts. Avoid using `sleep` to guess execution order.

## 6. Test Case Matrix

| Case | Test Action | Expected |
| --- | --- | --- |
| Valid owner | Alice still owns, version matches | Writes once; body and version update; success event emitted once |
| Not owner initially | Bob edits Alice's document | Rejected; body, version, and side effects unchanged |
| Revoked between T0–T2 | Alice passes pre-check; D transfers to Bob and commits | Alice cannot write, Bob stays owner, no success event |
| Stale version | Alice is still owner but version incremented by another edit | Stale request does not overwrite new content; contract error returned |
| Two concurrent edits | Same `expectedVersion` | At most one request writes successfully; no lost update |
| Transfer A → B → A | Ownership returns to Alice after two transfers | Version increments on each transfer; request carrying old version is blocked |
| Record locked/soft-deleted | `status` leaves ACTIVE before write | Write rejected even though `ownerId` still matches |
| Failure mid-transaction | 0 rows written or rollback | No partial updates, successful outbox rows, or sent notifications |
| Other processing paths | Batch, consumer, scheduler, or admin modifies D | No path bypasses permission/version constraints |
| Client spoofs owner | Principal Bob sends `actorId=Alice` | Actor derived from principal Bob; request blocked |
| Stale permission cache | ACL/group permission revoked before cache updates | Behavior matches published permission-effect contract; never claim instant revocation if cache still permits |

Tests must go beyond `assertThrows` or `verify(policy).check(...)`. Read **post-commit state** from a fresh transaction, verify update row counts, side effects, and responses. Include tests for valid paths so an implementation that rejects everything does not falsely pass.

If using permission-bearing JWTs, permission caches, or ACL caches, define revocation latency (immediate or after TTL). Tests pass only when aligned with that contract. When immediate revocation is required, read the current version/policy at the decision point rather than trusting stale claims indefinitely.

## 7. Side Effects and Long-Running Processing

Note that a database rollback **does not undo** sent emails, written files, published messages, or external API calls. A request might pass checks at T0, emit a success event, and then have its database update blocked at T2; the system is still broken. For success events, consider a **transactional outbox**: persist the business result and outbox row in the same transaction and publish after commit. For external I/O, design idempotency/compensation or intermediate workflow states; test those paths separately.

Async tasks/queues have two authorization points: **permission to enqueue the job** and **permission to execute the effect when the worker runs**. Decide explicitly whether revoking permission while a job waits cancels execution; pass a trusted actor ID and version data; re-check at the point of effect per contract; retries must neither bypass checks nor duplicate side effects. Whether a worker carries a SecurityContext does not by itself resolve changed permissions.

When processing multiple resources, checking permissions once before a loop is insufficient if individual resources can change ownership independently. Check at each step or use transactions/locks, conditional updates, or guarded batch writes depending on the invariant. If permission depends on related tables, control concurrency on **that policy data itself**.

## 8. Easy-to-Miss Testing Mistakes

**Testing only fresh requests:** testing Alice after Bob already took ownership only verifies normal denial; it never exercises the T0-to-T2 gap.

**Trusting annotations over evidence:** `@PreAuthorize` and `@Transactional` alone do not reveal locking/flush ordering. Inspect the SQL, version checks, and integration tests.

**Misunderstanding `@Version`:** standard entity updates and JPQL bulk updates work differently. Bulk updates must explicitly include version predicates/increments if that is the chosen strategy; ownership transfers must follow suit.

**Using mocks/sleeps:** mocks skip database isolation and locks, and `sleep` makes tests flaky. Use two real transactions, latches/barriers, and explicit commits.

**Reading stale data:** persistence contexts or caches retain stale entities and cause false assertions. Use a fresh transaction/refresh after commit.

**Asserting only error codes:** files can still be written, messages sent, or resources partially mutated before throwing an exception. Verify state and side effects.

**Ignoring batch, consumer, or admin paths:** a single write path updating by `id` without permission/version guards breaks the invariants upheld by REST endpoints.

**Leaking resource info via errors:** distinct messages for "not found" vs "owned by Bob" can leak existence; choose consistent responses aligned with product policy.

## 9. Acceptance Criteria

Testing passes when there is repeatable, deterministic evidence that: authorized owners edit successfully; unauthorized users are blocked; ownership transfers committed between check and write render stale requests ineffective; database state, versions, error codes, and side effects stay consistent; all write paths enforce the same constraints; and tests reproduce a **real race order** using deterministic synchronization.

Self-check question: if `@PreAuthorize` already allowed at T0 while `ownerId` changed at T1, **which SQL statement, version check, or lock** ensures the T2 operation cannot use expired authority? If you cannot answer with evidence at the write/commit point and an integration test, ownership testing is still incomplete.
