# Bulk Updates, Bulk Deletes, and Atomicity When One Item Lacks Permission

> **Scope:** Spring Security – authorization → **Data Permissions**. The focus is a multi-resource UPDATE/DELETE request where **just one item lacks permission or does not exist**. This lesson explains the all-or-nothing contract, how it differs from best-effort, how to combine Spring Method Security with `@Transactional`, data locking/versioning, and testing atomicity. Examples use Java 17+, Spring Boot 3.x, Spring Security 6.x, and Spring Data JPA with H2 tests.

## 1. The Problem: One Unauthorized ID Causes the Whole Batch to Fail

The client requests:

~~~json
{
  "ids": [101, 102, 202],
  "newTitle": "Reviewed"
}
~~~

In the database:

| ID | Tenant | Owner | Does Alice have UPDATE permission? |
| --- | --- | --- | --- |
| 101 | acme | alice | Yes |
| 102 | acme | alice | Yes |
| 202 | acme | bob | **No** |

If the operation updates 101 and 102 and skips 202, the outcome no longer matches the request "update the **entire** list". Worse, if each record committed separately, failing on 202 **cannot roll back** the previous two records.

Core takeaway of this lesson:

> **All-or-nothing:** If a single item does not exist, belongs to a different tenant, fails permission checks, or errors during processing ⇒ **the entire request is rejected or rolled back; no partial update/delete is committed**.

To guarantee that, you must simultaneously:
1. **Check permissions for all items**, not just one item or one general role.
2. **Ensure all requested IDs are present**, including when the database silently skips missing IDs in `WHERE id IN (...)`.
3. **Mutate data only after all checks pass** (or use conditional SQL + verify row count and roll back).
4. **Wrap the whole batch in one transaction** with appropriate rollback rules.
5. **Ensure permissions do not change between check and write** using appropriate locks/versions/SQL predicates.
6. **Return a success response after commit**; never publish success events before the transaction commits.

A transaction does not know whether the caller's owner/tenant is valid; a permission annotation alone does not automatically roll back already-committed transactions. Both authorization and atomicity must be designed together.

## 2. Two Different Contracts: All-or-Nothing vs Best-Effort

| Property | All-or-nothing | Best-effort / partial success |
| --- | --- | --- |
| One item lacks permission | Reject entire batch | May process the remaining items |
| One item does not exist | Reject entire batch (per sample contract) | May return NOT_FOUND for that item alone |
| Committed data when batch fails | None | Possible |
| Permission check | All must pass | Select permitted items |
| Transaction | Usually one shared transaction | Per-item/chunk transaction or stateful workflow |
| Response | Full success or full failure | List of per-item results |
| Use cases | Bulk approvals, consistency-critical change groups, deleting linked sets | Imports, background sync, cleanup tolerating local failures |

An all-or-nothing result for a batch containing Bob's ID:

~~~text
PATCH /api/documents/bulk-title
Alice requests [101, 102, 202]
→ HTTP 403 per sample contract (caller is authenticated)
→ Document#101: unchanged
→ Document#102: unchanged
→ Document#202: unchanged
~~~

A **deliberately designed** best-effort API might return:

~~~json
{
  "status": "PARTIAL",
  "results": [
    {"id": 101, "status": "UPDATED"},
    {"id": 102, "status": "UPDATED"},
    {"id": 202, "status": "DENIED"}
  ]
}
~~~

Never use `continue`, `@PreFilter`, or `filter(...)` to accidentally turn all-or-nothing into partial success without changing the API contract. This lesson implements **all-or-nothing** only.

## 3. Standard Flow: validate → load/lock → authorize all → mutate → commit

~~~text
Request IDs
   |
   v
Validate: non-null/non-empty, positive IDs,
no duplicates, within max batch size
   |
   v
BEGIN TRANSACTION
   |
   v
Load all records by IDs
(with appropriate locking or version control)
   |
   v
Exact count of requested IDs found?
   +-- NO  → DENY → ROLLBACK
   |
   v
EVERY record belongs to valid tenant + owner?
   +-- NO  → DENY → ROLLBACK
   |
   v
EVERY record matches valid state + authority/ACL?
   +-- NO  → DENY → ROLLBACK
   |
   v
Update/Delete ALL in the same transaction
   |
   v
Flush / constraints / optimistic checks
   +-- FAIL → ROLLBACK
   |
   v
COMMIT → SUCCESS
~~~

Each step serves a distinct purpose:

- **Normalize IDs:** check duplicates first because SQL `IN (101, 101, 202)` can return only two rows.
- **Load the full set:** `findAllById` or `WHERE id IN (...)` returns a subset when IDs are missing, so never fail silently.
- **Authorization against trusted data:** never trust `owner`/`tenantId` submitted by the client in JSON.
- **Per-object permissions:** holding `DOC_EDITOR` does not necessarily mean having rights on every document.
- **Fail closed:** if any single item cannot be verified, do not authorize the batch.
- **Commit at the end:** `flush()` is not `commit()`; the transaction can still roll back.

## 4. Spring Security and Spring Transaction Have Different Responsibilities

| Mechanism | What Does It Protect? | What Does It Not Protect Alone? |
| --- | --- | --- |
| `@PreAuthorize("isAuthenticated()")` | Caller is logged in before entering the method | Per-record owner/tenant |
| `@PreAuthorize("@policy.canEditAll(authentication,#ids)")` | Can check the ID set before the method | Transactions/TOCTOU if the policy checks outside the transaction |
| `@Transactional` | Atomic commit/rollback within a database transaction | Whether the user has permission on the records |
| `@Lock(PESSIMISTIC_WRITE)` | Reduces chance another writer alters rows between check and write | External permission tables or external systems not locked |
| `@Version` | Detects concurrent updates in the entity lifecycle | Bulk JPQL DML can bypass version checks |
| Conditional update/delete SQL | Embeds owner/tenant/state into the write predicate | Policies unexpressible in WHERE without additional logic |

Spring Method Security is enabled via `@EnableMethodSecurity`. `@PreAuthorize` is applied on bean proxies; with self-invocation, manually `new`-instantiated objects, or private/final methods not properly proxied, the security gate may not run.

**Key point:** `@PostAuthorize` evaluates after the method body finishes; never use it as the sole guard for updates, deletes, sending emails, or transferring money. `@PostFilter` only filters returned collections; `@PreFilter` can filter inputs, which is equivalent to processing a subset rather than proving all items are valid.

## 5. Java 17+ / Spring Boot 3.x / JPA / H2 Example

We use an easily verifiable policy: a user may only update or delete documents belonging to the **same tenant** with `ownerId` matching their authenticated identity. The demo defines principals:

| User | Tenant |
| --- | --- |
| alice | acme |
| bob | acme |
| eve | globex |

Production can replace this with policies involving authorities/ACLs, lock state, soft deletes, or retention. The goal of the example is designing a **whole-batch transaction** and testing denial when a single ID is unauthorized.

### 5.1. Dependencies

In the `build.gradle` of a Spring Boot 3.x project configured with compatible Java/Boot/dependency-management plugins:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-security'
    runtimeOnly 'com.h2database:h2'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

`spring-boot-starter-security` does not automatically enable Method Security. Because this demo invokes the service from JUnit, `spring-boot-starter-web` is not required.

### 5.2. Test Database Configuration

**`src/test/resources/application.properties`**

~~~properties
spring.datasource.url=jdbc:h2:mem:batch_security;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
spring.jpa.show-sql=false
~~~

H2 works well for basic functional integration tests; `create-drop` and in-memory settings **must not be used in production**. For PostgreSQL/MySQL/Oracle/SQL Server, verify transaction isolation and locking on your actual target database.

### 5.3. Application

**`src/main/java/demo/batch/BatchAuthorizationApplication.java`**

~~~java
package demo.batch;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@SpringBootApplication
@EnableMethodSecurity
public class BatchAuthorizationApplication {
    public static void main(String[] args) {
        SpringApplication.run(BatchAuthorizationApplication.class, args);
    }
}
~~~

### 5.4. Versioned Entity

**`src/main/java/demo/batch/DocumentEntity.java`**

~~~java
package demo.batch;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.Version;

@Entity
@Table(name = "documents")
public class DocumentEntity {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 64)
    private String tenantId;

    @Column(nullable = false, length = 64)
    private String ownerId;

    @Column(nullable = false, length = 160)
    private String title;

    @Version
    private Long version;

    protected DocumentEntity() {
    }

    public DocumentEntity(String tenantId, String ownerId, String title) {
        this.tenantId = tenantId;
        this.ownerId = ownerId;
        this.title = title;
    }

    public Long getId() {
        return id;
    }

    public String getTenantId() {
        return tenantId;
    }

    public String getOwnerId() {
        return ownerId;
    }

    public String getTitle() {
        return title;
    }

    public Long getVersion() {
        return version;
    }

    public void rename(String newTitle) {
        this.title = newTitle;
    }
}
~~~

`@Version` provides optimistic locking when Hibernate manages entity updates/deletes. It does not automatically protect JPQL bulk updates/deletes; if you choose bulk DML, you must design explicit version predicates and update clauses.

### 5.5. Repository Locking Rows Within the Transaction

**`src/main/java/demo/batch/DocumentRepository.java`**

~~~java
package demo.batch;

import java.util.Collection;
import java.util.List;
import jakarta.persistence.LockModeType;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Lock;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface DocumentRepository extends JpaRepository<DocumentEntity, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select d from DocumentEntity d where d.id in :ids")
    List<DocumentEntity> lockAllByIds(
            @Param("ids") Collection<Long> ids);
}
~~~

`@Lock(PESSIMISTIC_WRITE)` instructs JPA/database to hold an appropriate write lock on the read rows during the transaction. Once ownership is checked, another writer can hardly modify those rows before the current method commits. However, locking behavior differs across databases; row locks do not automatically lock separate ACL/membership tables unless those tables are also controlled.

### 5.6. Actor and Tenant from Trusted Authentication

**`src/main/java/demo/batch/ActorDirectory.java`**

~~~java
package demo.batch;

import java.util.Map;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.authentication.AnonymousAuthenticationToken;
import org.springframework.security.core.Authentication;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.stereotype.Component;

@Component
public class ActorDirectory {
    public record Actor(String userId, String tenantId) {
    }

    // For test/demo only; not a real IAM system.
    private static final Map<String, Actor> USERS = Map.of(
            "alice", new Actor("alice", "acme"),
            "bob", new Actor("bob", "acme"),
            "eve", new Actor("eve", "globex"));

    public Actor current() {
        Authentication authentication =
                SecurityContextHolder.getContext().getAuthentication();

        if (authentication == null
                || !authentication.isAuthenticated()
                || authentication instanceof AnonymousAuthenticationToken) {
            throw new AccessDeniedException("Batch not permitted");
        }

        Actor actor = USERS.get(authentication.getName());
        if (actor == null) {
            throw new AccessDeniedException("Batch not permitted");
        }
        return actor;
    }
}
~~~

The map above illustrates a **server-side trusted directory** supporting `@WithMockUser`; production must retrieve ID/tenant from a verified principal, signature-verified JWT claims, or an identity service. Never use client-supplied tenant/owner; avoid using usernames that may collide across tenants as permanent identifiers.

### 5.7. All-or-Nothing Service

**`src/main/java/demo/batch/BulkDocumentService.java`**

~~~java
package demo.batch;

import java.util.HashSet;
import java.util.List;
import java.util.Objects;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class BulkDocumentService {
    private static final int MAX_BATCH = 100;

    private final DocumentRepository repository;
    private final ActorDirectory actors;

    public BulkDocumentService(
            DocumentRepository repository,
            ActorDirectory actors) {
        this.repository = repository;
        this.actors = actors;
    }

    @Transactional
    @PreAuthorize("isAuthenticated()")
    public void renameAll(List<Long> requestedIds, String title) {
        List<Long> ids = validateIds(requestedIds);

        if (title == null || title.isBlank() || title.length() > 160) {
            throw new IllegalArgumentException("Invalid title");
        }

        ActorDirectory.Actor actor = actors.current();
        List<DocumentEntity> selected = authorizeAll(ids, actor);

        // Mutate ONLY after EVERY item is authorized.
        for (DocumentEntity document : selected) {
            document.rename(title);
        }
        repository.flush();
    }

    @Transactional
    @PreAuthorize("isAuthenticated()")
    public void deleteAll(List<Long> requestedIds) {
        List<Long> ids = validateIds(requestedIds);
        ActorDirectory.Actor actor = actors.current();
        List<DocumentEntity> selected = authorizeAll(ids, actor);

        // Delete verified entities; never blind-delete by IDs.
        repository.deleteAll(selected);
        repository.flush();
    }

    private List<Long> validateIds(List<Long> input) {
        if (input == null || input.isEmpty() || input.size() > MAX_BATCH) {
            throw new IllegalArgumentException("Invalid batch");
        }
        if (input.stream().anyMatch(Objects::isNull)
                || input.stream().anyMatch(id -> id <= 0)) {
            throw new IllegalArgumentException("Invalid ids");
        }
        if (new HashSet<>(input).size() != input.size()) {
            throw new IllegalArgumentException("Duplicate ids");
        }
        return List.copyOf(input);
    }

    private List<DocumentEntity> authorizeAll(
            List<Long> ids,
            ActorDirectory.Actor actor) {

        List<DocumentEntity> selected = repository.lockAllByIds(ids);

        // IN (...) returns a subset when any ID does not exist.
        if (selected.size() != ids.size()) {
            throw new AccessDeniedException("Batch not permitted");
        }

        for (DocumentEntity doc : selected) {
            if (!doc.getTenantId().equals(actor.tenantId())
                    || !doc.getOwnerId().equals(actor.userId())) {
                throw new AccessDeniedException("Batch not permitted");
            }
        }
        return selected;
    }
}
~~~

**Gate-by-gate explanation:**

1. `@PreAuthorize("isAuthenticated()")` protects the service boundary, then `ActorDirectory` ensures the actor is recognized server-side.
2. `@Transactional` on the **public method called via Spring proxy** opens one transaction spanning all reads, permission checks, and writes.
3. `validateIds` rejects null, empty, zero/negative numbers, duplicates, and lists over 100. If duplicates exist, the row count from `WHERE IN` cannot be directly compared to list size to prove completeness.
4. `lockAllByIds` loads the rows and acquires locks where supported by the DB. Never rely on result list order for permissions; every row must be checked.
5. If any row is missing, throw a generic `AccessDeniedException`, limiting disclosure of which ID belongs to someone else or does not exist.
6. If any row has a different owner/tenant, throw **before** the mutation loop. Never use `continue` or filter silently.
7. `renameAll` mutates managed entities; JPA dirty checking applies within the transaction on flush/commit.
8. `deleteAll` deletes the verified entities, preserving JPA entity lifecycle (compared to bulk deletes which differ in many ways).
9. `flush()` surfaces constraints/SQL errors before exiting the method, yet **has not committed**. The transaction interceptor completes the commit after the method returns.
10. `AccessDeniedException` extends `RuntimeException`, triggering rollback by default.

Production typically also needs `DOC_EDIT`/`DOC_DELETE` authorities, locked documents, legal holds, ACL policies, tenant admins, and versioning. All those conditions must be evaluated for **every item**, not just the first object.

### An Important Rule on Transactions and Self-Invocation

Do not place `@Transactional` on a private helper and expect it to open a transaction. In proxy-based Spring AOP, `this.innerTransactional()` calls are not intercepted. Put the boundary on a public service injected from the Spring Context; if extracting policy into a separate bean, have the public transactional method call the policy within the same transaction.

## 6. Integration Tests: Proving Data Is Not Partially Modified

These tests use real H2 and a real Spring Context. They do not just assert exceptions; they **re-read the DB** after the service fails. `@WithMockUser` creates an Authentication for tests; it is not real password/JWT authentication.

**`src/test/java/demo/batch/BulkDocumentServiceTest.java`**

~~~java
package demo.batch;

import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.security.access.AccessDeniedException;
import org.springframework.security.test.context.support.WithAnonymousUser;
import org.springframework.security.test.context.support.WithMockUser;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;

@SpringBootTest(classes = BatchAuthorizationApplication.class)
class BulkDocumentServiceTest {

    @Autowired BulkDocumentService bulk;
    @Autowired DocumentRepository repository;
    @Autowired PlatformTransactionManager transactionManager;

    private Long a1;
    private Long a2;
    private Long b1;
    private Long e1;

    @BeforeEach
    void seed() {
        repository.deleteAll();
        repository.flush();

        a1 = repository.saveAndFlush(
                new DocumentEntity("acme", "alice", "A1")).getId();
        a2 = repository.saveAndFlush(
                new DocumentEntity("acme", "alice", "A2")).getId();
        b1 = repository.saveAndFlush(
                new DocumentEntity("acme", "bob", "B1")).getId();
        e1 = repository.saveAndFlush(
                new DocumentEntity("globex", "eve", "E1")).getId();
    }

    private String title(Long id) {
        return repository.findById(id).orElseThrow().getTitle();
    }

    @Test
    @WithMockUser(username = "alice")
    void fullAuthorizationUpdatesAll() {
        bulk.renameAll(List.of(a1, a2), "Reviewed");

        assertEquals("Reviewed", title(a1));
        assertEquals("Reviewed", title(a2));
        assertEquals("B1", title(b1));
    }

    @Test
    @WithMockUser(username = "alice")
    void oneForeignOwnerBlocksTheEntireUpdate() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.renameAll(List.of(a1, b1), "Reviewed"));

        assertEquals("A1", title(a1));
        assertEquals("B1", title(b1));
    }

    @Test
    @WithMockUser(username = "alice")
    void crossTenantDocumentBlocksTheEntireUpdate() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.renameAll(List.of(a2, e1), "Reviewed"));

        assertEquals("A2", title(a2));
        assertEquals("E1", title(e1));
    }

    @Test
    @WithMockUser(username = "alice")
    void missingDocumentBlocksTheEntireUpdate() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.renameAll(
                        List.of(a1, Long.MAX_VALUE), "Reviewed"));

        assertEquals("A1", title(a1));
    }

    @Test
    @WithMockUser(username = "alice")
    void duplicateIdIsAnInvalidBatch() {
        assertThrows(IllegalArgumentException.class,
                () -> bulk.renameAll(List.of(a1, a1), "Reviewed"));

        assertEquals("A1", title(a1));
    }

    @Test
    @WithMockUser(username = "alice")
    void mixedAuthorizationDeletesNothing() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.deleteAll(List.of(a1, b1)));

        assertTrue(repository.existsById(a1));
        assertTrue(repository.existsById(b1));
    }

    @Test
    @WithMockUser(username = "alice")
    void missingDocumentBlocksTheEntireDelete() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.deleteAll(List.of(a2, Long.MAX_VALUE)));

        assertTrue(repository.existsById(a2));
    }

    @Test
    @WithMockUser(username = "alice")
    void fullAuthorizationDeletesAllRequestedRows() {
        bulk.deleteAll(List.of(a1, a2));

        assertFalse(repository.existsById(a1));
        assertFalse(repository.existsById(a2));
        assertTrue(repository.existsById(b1));
    }

    @Test
    @WithAnonymousUser
    void anonymousIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.renameAll(List.of(a1), "Reviewed"));

        assertEquals("A1", title(a1));
    }

    @Test
    @WithMockUser(username = "unknown")
    void unknownPrincipalIsDenied() {
        assertThrows(AccessDeniedException.class,
                () -> bulk.deleteAll(List.of(a1)));

        assertTrue(repository.existsById(a1));
    }

    @Test
    void aRuntimeFailureAfterFlushStillRollsBack() {
        TransactionTemplate transaction =
                new TransactionTemplate(transactionManager);

        assertThrows(IllegalStateException.class,
                () -> transaction.executeWithoutResult(status -> {
                    DocumentEntity doc =
                            repository.findById(a1).orElseThrow();
                    doc.rename("Temporary");
                    repository.flush();

                    // SQL was flushed, yet the transaction has NOT committed.
                    throw new IllegalStateException("Injected failure");
                }));

        // Transaction rolled back; subsequent query still sees old value.
        assertEquals("A1", title(a1));
    }
}
~~~

**Significance of the final test:** it intentionally mutates an entity and calls `flush` before throwing an unchecked exception from the `TransactionTemplate` callback. Data must roll back when the transaction ends due to the exception. This independently verifies the principle **flush != commit**.

### 6.1. Outcome Matrix

| Case | Expected Outcome |
| --- | --- |
| Alice updates two of her own documents | Both documents change |
| Alice updates one of hers + one of Bob's | Throws, **both remain unchanged** |
| One document from another tenant | Throws, **both remain unchanged** |
| One non-existent ID | Throws, no subset updated |
| Duplicate ID present | Invalid input, no mutation |
| Alice deletes A1 + B1 | Throws, **both still exist** |
| Alice deletes A1 + A2 | Both deleted |
| Anonymous calls batch | Rejected by Method Security |
| Username absent from trusted directory | Rejected by service |
| SQL flush then throw exception | Database rolls back, initial title preserved |

### 6.2. Running Tests

On macOS/Linux:

~~~text
./gradlew test --tests demo.batch.BulkDocumentServiceTest
~~~

On Windows:

~~~text
gradlew.bat test --tests demo.batch.BulkDocumentServiceTest
~~~

The source has no `System.out.println`, so there is no fixed business stdout. What matters is green JUnit tests and Gradle completing the test task. The code is structured to run in a compatible project version; execute it on your real project stack before production.

**Do not put `@Transactional` on the test class itself just to "clean up data":** if the test rolls back after the service runs, it can mask whether the service committed separately or lacked a transaction. This test keeps test methods outside a transaction so every service outcome is observed fresh via the repository.

## 7. Optimizing via Conditional Bulk UPDATE

The primary example loads entities, checks each row, and updates them. Another approach embeds the policy directly into SQL:

~~~sql
UPDATE documents
SET title = :title
WHERE id IN (:ids)
  AND tenant_id = :trusted_tenant
  AND owner_id = :authenticated_user;
~~~

Illustrative Spring Data JPA code:

~~~java
// ILLUSTRATIVE ONLY: place inside DocumentRepository with required imports.
@Modifying
@Query("""
    update DocumentEntity d
       set d.title = :title
     where d.id in :ids
       and d.tenantId = :tenant
       and d.ownerId = :owner
    """)
int conditionalRename(
        @Param("ids") List<Long> ids,
        @Param("tenant") String tenant,
        @Param("owner") String owner,
        @Param("title") String title);
~~~

Calling service:

~~~java
// ILLUSTRATIVE ONLY: actor must come from verified source and IDs normalized.
@Transactional
public void renameConditionally(List<Long> ids, String title, Actor actor) {
    int affected = repository.conditionalRename(
            ids, actor.tenantId(), actor.userId(), title);

    if (affected != ids.size()) {
        // Same transaction -> rolls back the rows just updated.
        throw new AccessDeniedException("Batch not permitted");
    }
}
~~~

**Why check the row count?** An SQL UPDATE with WHERE owner/tenant only updates matching rows. If 3 IDs are requested and 1 belongs to Bob, SQL still returns 2 affected rows without throwing an error. If the service returns success, all-or-nothing is violated. Throwing inside the transaction before commit rolls back the two updated rows.

### Limitations of This Approach

- JPA bulk DML **bypasses** entity callbacks like `@PreUpdate` and may not automatically enforce `@Version`. With optimistic locking, incorporate version conditions/increments into custom SQL design.
- An `EntityManager` holding entities can become stale relative to the DB after `@Modifying`. `clearAutomatically`/`flushAutomatically` affect pending changes and must be used knowledgeably.
- Returned row counts must be verified on your real database/provider, especially regarding no-op updates, triggers, soft deletes, views, and vendor-specific row count semantics.
- If policy also involves LOCKED state, legal holds, complex ACLs, or tenant group memberships, either express **every** condition in WHERE or check beforehand within the transaction.
- For large ID lists, SQL `IN` parameter limits and lock contention may force chunking. If whole-batch atomicity is required, every chunk must still participate in **the same transaction** or use an equivalent staging/set-based update mechanism.

Therefore, conditional SQL can be more efficient, yet requires evaluating policy, version enforcement, and real database behavior; never treat "one SQL statement" as sufficient for authorization alone.

## 8. Never Blindly Bulk-DELETE by Client-Supplied IDs

~~~java
// DANGEROUS if ids come from the client without authorization:
repository.deleteAllByIdInBatch(ids);
~~~

`deleteAllByIdInBatch` can emit a bulk delete statement; it does not check owner/tenant/permissions. `deleteAllInBatch` and bulk JPQL APIs also do not preserve all entity lifecycle semantics:

- They do not necessarily fire `@PreRemove` callbacks or cascades like per-entity deletion.
- The first-level persistence context can fall out of sync with the DB after a bulk query.
- `@Version` may not be enforced automatically.
- Foreign-key constraints, soft-delete policies, and auditing can be affected.

To perform an all-or-nothing bulk DELETE, you can use:

~~~sql
DELETE FROM documents
WHERE id IN (:ids)
  AND tenant_id = :trusted_tenant
  AND owner_id = :authenticated_user;
~~~

Combine **the same transaction**, full-set row counts, and additional policies. If affected count differs from requested count and DB row-count semantics are verified, throw a runtime exception to roll back. If callbacks/cascades or complex policies are needed, loading/locking/checking all and calling `repository.deleteAll(entities)` is usually easier to keep correct.

## 9. Bugs That Break Atomicity

### 9.1. A Separate Transaction Per Item

~~~java
// ANTI-PATTERN:
for (Long id : ids) {
    itemService.updateInIndependentTransaction(id, title);
}
~~~

If items 1 and 2 commit and item 3 fails, an outer transaction cannot roll back the two prior commits. `Propagation.REQUIRES_NEW` always opens an independent physical transaction; never use it per item under an all-or-nothing contract. `Propagation.REQUIRED` normally joins an existing transaction, provided the public service boundary actually opened one.

### 9.2. Catching and Swallowing `AccessDeniedException`

~~~java
// ANTI-PATTERN: valid mutations may commit even when one item is denied.
@Transactional
public void unsafeUpdate(List<Long> ids) {
    for (Long id : ids) {
        try {
            updateOne(id);
        } catch (AccessDeniedException ignored) {
            // continue to next item
        }
    }
}
~~~

If the exception is swallowed without marking rollback-only, the transaction can commit earlier changes. For all-or-nothing, never swallow errors. Let the exception propagate; or if caught for handling, mark rollback-only properly and never return success.

### 9.3. Checked Exceptions Do Not Roll Back by Default

Spring Framework rolls back by default for `RuntimeException` and `Error`. A checked exception like `IOException` does not roll back by default unless configured. For a custom checked batch exception, add:

~~~java
// ILLUSTRATION: BatchPermissionException is a user-defined checked exception.
@Transactional(rollbackFor = BatchPermissionException.class)
public void batch(...) throws BatchPermissionException {
    // ...
}
~~~

In this lesson's code, `AccessDeniedException` is unchecked and thus triggers default rollback.

### 9.4. Self-Invocation and Unproxied Method Security

~~~java
@Service
class UnsafeService {
    public void outer() {
        this.innerTransactional();
    }

    @Transactional
    public void innerTransactional() {
        // ...
    }
}
~~~

`this.innerTransactional()` can bypass the transaction proxy. Likewise, calling a `@PreAuthorize` method on the same target via `this` can bypass the authorization gate. Use a public Spring-managed application service invoked through its proxy; test realistically with `@SpringBootTest`.

### 9.5. Checking Only the First Element

~~~java
// ANTI-PATTERN:
if (policy.canUpdate(authentication, records.get(0))) {
    repository.saveAll(records);
}
~~~

The first record passing does not make the rest pass. If using `PermissionEvaluator` or ACLs, invoke the policy on **every** domain object, or use repository/ACL batch lookups and verify all results.

### 9.6. Request ID Count Does Not Match Row Count

~~~text
Request: [101, 101, 999]
SQL IN returns row 101, ignoring ID 999 and duplicate 101.
~~~

Reject duplicates or explicitly normalize to a Set and document the semantics. Never check merely `!found.isEmpty()` or `affected > 0`; under all-or-nothing, the required condition is **every ID valid and every row authorized**.

### 9.7. Splitting a Batch into Chunks That Commit Individually

~~~text
Chunk 1: 10,000 items → COMMIT
Chunk 2: 10,000 items → COMMIT
Chunk 3: contains unauthorized item → FAIL
~~~

The first two chunks cannot automatically roll back when chunk 3 fails. If batch-wide atomicity is required, share one database transaction or switch to a set-based/staging algorithm with a unified commit. If lock duration prevents that, change the contract to a **stateful partial/async workflow with compensation**; do not call it all-or-nothing.

### 9.8. DB Commits/Rollbacks Cannot Undo External Side Effects

~~~text
DB transaction: update rows → rollback
External email: already sent
Broker: message already published
Object storage: file already deleted
~~~

Relational database transactions cannot recall sent emails, published events, or deleted cloud files. Use a transactional outbox to record events in the same DB transaction and let a publisher process **after commit**, paired with idempotent consumers and retry/compensation strategies. `@TransactionalEventListener(AFTER_COMMIT)` controls in-JVM callback timing, yet alone does not guarantee delivery if the process crashes right after commit.

## 10. Data Contention and TOCTOU

### 10.1. Race Between Check and Write

~~~text
T1: Alice reads Document#101 owner=alice → allow
T2: Another transaction transfers owner=Bob
T3: Alice updates Document#101 under stale permission
~~~

This is **time-of-check/time-of-use** (TOCTOU). To reduce risk, check permissions and mutate in the same transaction, use `PESSIMISTIC_WRITE`/optimistic versions/conditional SQL, and account for all policy sources: tenant memberships, ACLs, lock states, and sharing.

Locking a Document row **does not automatically lock** role membership or ACL tables elsewhere. If a policy change invalidates permissions, the system needs synchronized versioning/authorization guards commensurate with business risk.

### 10.2. Deadlocks and Timeouts

Two batches locking overlapping sets in different orders can deadlock. Sorting IDs helps logical consistency, though DB query optimizers do not always lock strictly in input order. Cap batch sizes, keep transactions short, set timeouts, monitor deadlocks, and retry the **entire transaction including authorization** after re-reading data.

### 10.3. Optimistic Versioning

`@Version` typically detects concurrent updates in the entity lifecycle. On `OptimisticLockException` or the corresponding Spring Data exception, the transaction must roll back; retries must re-run queries and authorization against fresh state. With JPQL bulk DML, manage versions manually since bulk operations do not behave like `save(entity)`.

## 11. Extending from Owner-Only to Authorities and ACLs

A realistic UPDATE permission might be:

~~~text
UPDATE document:
  same trusted tenant
  AND (owner OR ACL.WRITE grant)
  AND DOC_EDIT authority
  AND status != LOCKED
~~~

DELETE permission might additionally require no legal hold and DELETE permission in the ACL. If using `PermissionEvaluator`:

~~~java
// ILLUSTRATIVE ONLY: models, helpers, and PermissionEvaluator must be configured.
public boolean canDelete(
        Authentication authentication,
        Document document) {
    return sameTrustedTenant(authentication, document)
            && hasAuthority(authentication, "DOC_DELETE")
            && permissionEvaluator.hasPermission(
                    authentication, document, "DELETE")
            && !document.isLocked();
}
~~~

For batches, check `canDelete` on **every** document before deleting. `AclService.readAclsById` can avoid N+1 when loading multiple ACLs, yet you must call `Acl.isGranted` for **each ObjectIdentity and SID/permission**. One granted row never speaks for all rows.

In multi-tenant systems, users sharing the same username across two tenants need distinct immutable IDs; never use `ownerId` from a JSON request as proof. If policy grants admin override over owners, restrict admins strictly to their tenant and business scope.

## 12. 401/403/404 Errors and Avoiding Data Leaks

An all-or-nothing service can throw `AccessDeniedException("Batch not permitted")` when any item is missing or unauthorized so callers cannot tell exactly which ID belongs to someone else. At the HTTP layer:

- 401 when unauthenticated, per `AuthenticationEntryPoint`.
- 403 when authenticated but unauthorized.
- Some APIs choose 404 or non-disclosing responses to prevent enumeration.

There is no single mandatory HTTP status rule for every application; the API contract must be consistent. Specifically, never return a list of IDs "denied because owned by Bob" to a caller lacking permission to view that metadata.

### Auditing Must Distinguish Failures from Committed Business State

Logs might record:

~~~text
operation=BULK_UPDATE_DENIED
actor=alice
tenant=acme
requested_count=3
result=DENIED
business_committed=false
~~~

Never log tokens, sensitive payloads, or owner metadata of unauthorized items. If an audit row is written inside the same transaction and that transaction rolls back, the audit row may be lost too; an independent audit store or separate outbox/event requires its own security and consistency design.

## 13. Mandatory Pre-Production Test Matrix

| Scenario | Atomic Expectation |
| --- | --- |
| 2 IDs both owned by actor | Both updated/deleted |
| 1 ID owned by actor, 1 owned by another | Zero rows changed |
| 1 ID in another tenant | Zero rows changed |
| 1 non-existent ID | Zero rows changed |
| Duplicate/null/empty list | Reject input, zero rows changed |
| ID count exceeds limit | Reject input |
| Anonymous or unverified principal | Zero mutations |
| SQL error mid-batch or at commit | Rollback |
| Concurrent owner/tenant update | Lock or version conflict; retry whole batch |
| Row has legal hold or LOCKED | Reject whole batch |
| Batch delete with cascade/soft-delete | Verify lifecycle, DB constraints, and full batch |
| Batch SQL affected count less than requested | Throw then roll back |
| Role/ACL changes between check and write | Corresponding policy/version guard triggers |
| Message broker down after commit | Business commits with outbox/retry; no false failure/success |

**A test asserting only exception/status is insufficient**. After a denied call, re-query the database from outside the transaction to confirm every record remained untouched. Avoid annotating test methods with `@Transactional` in a way that auto-rolls back at test end and accidentally hides the service's real transaction boundary.

## 14. Common Bugs and Fixes

| Symptom | Cause | Fix |
| --- | --- | --- |
| 2/3 rows changed despite API returning error | Per-item commits or swallowed exceptions | One shared transaction, roll back on unhandled error |
| Non-existent IDs silently skipped | `IN` only returns subset | Compare full set against normalized IDs |
| User edits someone else's row | Checking only role or first element | Check owner/tenant/permission on every row |
| `@PreFilter` alters input set | Filters unauthorized items | Never use silent filtering for all-or-nothing |
| `@PostAuthorize` denies yet data changed | Post-check runs after side effects | Authorize before mutation |
| `@Transactional` has no effect | Self-invocation or unproxied target | Public service bean, integration tests |
| Checked exception causes transaction commit | Default rollback only covers runtime/error | `rollbackFor` or unchecked exception |
| `REQUIRES_NEW` commits per item | Independent physical transactions | `REQUIRED` inside one outer transaction |
| `deleteAllByIdInBatch` bypasses policy | Blind bulk DML by client IDs | Check all / conditional SQL before deleting |
| DML bypasses `@Version`/callbacks | Bulk JPQL differs from entity updates | Version-aware WHERE and lifecycle-aware design |
| One row transfers owner after check | TOCTOU | Locks/versions/conditional updates |
| Retry processes only remaining rows | Partial retry breaks atomicity | Retry entire batch after re-authorization |
| Wrong tenant with colliding username | Untrusted ID or tenant source | Verified principal + tenant binding |
| DB rolls back yet email still sent | Side effect outside transaction | Outbox/after-commit/compensation |
| Response 200 yet commit fails | Response sent before completion | Return response outside transaction boundary |
| Test only asserts 403 | Does not verify DB state | Read back all rows after failure |

## 15. Hands-On Exercises

**Exercise 1 – Silent filter mistake.** Try an `unsafeUpdate` version using `continue` on rows not owned by the actor. With IDs [A1,B1], observe A1 changing while B1 does not. Restore all-or-nothing and test both remain unchanged.

**Exercise 2 – Adding LOCKED.** Add a `locked` flag to Document. A single locked ID owned by Alice must cause the entire batch to deny, even when all other IDs are valid.

**Exercise 3 – Adding authorities.** Require `DOC_EDIT` for UPDATE and `DOC_DELETE` for DELETE in addition to owner/tenant. Test an actor with the authority who is not owner, an owner lacking the authority, and an actor with both.

**Exercise 4 – Conditional bulk update.** Create a `@Modifying @Query` repository method binding tenant/owner/status. With 3 IDs where 1 lacks permission, throw when affected count is short. Read back the DB after rollback and verify entity version.

**Exercise 5 – Concurrent writer.** Use two transactions to change owner and update title on the same ID. Compare `PESSIMISTIC_WRITE`, optimistic versioning, and conditional updates on a production-like test database.

**Exercise 6 – Large batches.** Design processing for 10,000 IDs within SQL parameter and lock-time limits. Explain why per-chunk commits are no longer batch-atomic, and when to switch to an async/partial workflow with per-item outcomes.

**Exercise 7 – Per-object ACLs.** Use `PermissionEvaluator` or `AclService` to check `WRITE/DELETE` per ObjectIdentity. One ID missing an ACE must fail the whole batch; test parent inheritance too.

**Exercise 8 – Audit/outbox.** Emit an event only when the batch commits. Intentionally throw an exception after `flush()` to ensure no false success event is published and the DB rolls back.

**Completion criteria:** distinguish all-or-nothing from best-effort; validate IDs thoroughly; check permissions on all rows; place `@Transactional` at the right boundary; verify rollback after flush; avoid blind bulk deletes; recognize TOCTOU, JPQL DML, tenant, multi-transaction, and external side-effect risks.

## Official References

- Spring Security – **Method Security** (`@EnableMethodSecurity`, `@PreAuthorize`, `@PreFilter`, `@PostAuthorize`): https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html
- Spring Framework – **Rolling Back a Declarative Transaction**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework – **@Transactional Settings**: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework – **Transaction Propagation** (`REQUIRED`, `REQUIRES_NEW`): https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html
- Spring Data JPA – **Locking** (`@Lock`): https://docs.spring.io/spring-data/jpa/reference/jpa/locking.html
- Spring Data JPA – **JPA Query Methods** (`@Modifying`, bulk DML, and entity callbacks): https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data JPA – **JpaRepository API**, `deleteAllInBatch`, and `deleteAllByIdInBatch`: https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html
