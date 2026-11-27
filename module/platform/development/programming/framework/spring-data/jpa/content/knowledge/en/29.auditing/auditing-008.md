# Limitations of Auditing with Bulk DML and Updates Outside JPA

## 1. The Problem to Understand

In Spring Data JPA, auditing normally populates **who created/modified** and **when created/modified** an entity via `@CreatedBy`, `@CreatedDate`, `@LastModifiedBy`, and `@LastModifiedDate`. This mechanism is tied to the JPA-managed entity lifecycle, typically via `AuditingEntityListener` and events such as `@PrePersist` and `@PreUpdate`.

**Core limitation:** When executing *bulk DML* (a single `UPDATE`/`DELETE` statement acting directly on a set of rows) or updating the database outside the JPA lifecycle, **there is no guarantee that the auditing listener will run for each entity**. Therefore, merely declaring auditing annotations is not enough for every change to leave an accurate trace.

For example: a record has `updated_at = 10:00`, `updated_by = "alice"`. At 11:00, a background job executes `UPDATE account SET locked = true WHERE ...`. The `locked` value changes, yet if the statement does not update the two audit columns itself, they may still show 10:00 and "alice". Someone reading the data could mistakenly assume Alice performed the most recent change.

Distinguish two concepts:
- **Audit metadata:** columns like `created_at`, `created_by`, `updated_at`, and `updated_by` only reflect the current metadata state; they are not a full history.
- **Audit trail/history:** an immutable log or versioned records capturing each change, before/after state, actor, and timestamp; must be designed separately if tracking multiple historical changes is required.

## 2. When Does Auditing Run Automatically and When Is It Bypassed?

| Data Modification Approach | Entity Lifecycle/Auditing | Notes |
| --- | --- | --- |
| Load entity via `findById`, mutate properties, let dirty checking issue `UPDATE` on flush | Normally **runs** `@PreUpdate` and Spring Data JPA auditing, if configured | If there are effectively no changes to update, callbacks may not run |
| `save` / `saveAll` on entities via `persist`/`merge` operations | Follows normal entity lifecycle | `saveAll` is not synonymous with a bulk JPQL `UPDATE`; JDBC batching only optimizes how SQL statements are sent |
| `@Modifying @Query("update ...")`, `EntityManager.createQuery(...).executeUpdate()` | **Does not run callbacks per entity** | Must set required audit fields explicitly |
| JPQL `DELETE`, `CriteriaUpdate` / `CriteriaDelete` | **Does not run callbacks per entity** | Watch out for `@PreRemove`, relationships, and cache |
| `@Query(nativeQuery = true)` direct updates, `JdbcTemplate`, SQL migrations/scripts, stored procedures, external systems writing to DB | **Does not go through JPA's auditing listener** | Ensure audit columns via SQL/DB and identify the actor |
| `JpaRepository`'s `deleteAllInBatch(...)` | Does not fire per-entity JPA lifecycle events | Javadoc also notes it does not honor JPA cascade semantics |
| Database triggers | Do not trigger JPA listeners; triggers have their own mechanism | Triggers can populate timestamps/audit tables if designed properly |

An easy distinction to confuse: **bulk DML** is a statement updating/deleting directly across a set of rows; **JDBC batching** groups multiple SQL statements generated from regular entity changes to improve performance. You cannot assume that every operation containing the word "batch" bypasses auditing.

## 3. Three Technical Consequences of Bulk DML

### 3.1. Audit Columns Are Not Populated Automatically

The `@LastModifiedDate` and `@LastModifiedBy` annotations only take effect when the auditing infrastructure receives the corresponding entity events. A JPQL statement like the following does not automatically add `updated_at`/`updated_by`:

```java
@Modifying
@Query("update CustomerAccount a set a.locked = true where a.id = :id")
int lockWithoutAudit(@Param("id") Long id);
```

Assuming the listener is fully enabled, the statement above still updates only `locked` as declared. With SQL executed from outside the application, `AuditorAware` is also never invoked: it cannot infer the user of a standalone database command.

### 3.2. `@Version` and Optimistic Locking Are Not Applied Automatically

According to Jakarta Persistence, bulk `UPDATE`/`DELETE` statements go straight to the database, **bypassing optimistic-lock checks** of entity operations. The provider does not automatically add `where version = ...` or increment `version` for bulk DML. For entities with `@Version`, a bulk update that omits the version column can leave data and conflict detection inconsistent.

If you need concurrency checking on a single record, explicitly include the version condition in `WHERE`, increment version in `SET`, and check the affected row count. If `UPDATE` returns `0` rows, do not assume success: the id may not exist or the row may have been modified by another transaction. This mechanism is **implemented by the application itself**; returning `0` does not automatically throw an `OptimisticLockException`.

When updating many rows with a broad condition, merely incrementing each row's version is still **not equivalent** to checking an expected version per row. Choose a concurrency strategy suited to business rules and transaction isolation.

### 3.3. The Persistence Context May Retain Stale Data

Consider within the same transaction:
1. `EntityManager` has already loaded `CustomerAccount#42` into the first-level cache with `locked=false`.
2. A bulk `UPDATE` changes row #42 to `locked=true` in the database.
3. The loaded entity reference may still report `locked=false`; bulk DML **does not synchronize** the persistence context.

Spring Data JPA provides `@Modifying(flushAutomatically = true, clearAutomatically = true)`:
- `flushAutomatically=true`: flushes pending changes **before** executing the modifying query.
- `clearAutomatically=true`: clears the persistence context **after** executing the query, detaching existing entities; you must **re-query** to get the updated data. It does not cause the auditing listener to run.

`clear()` can discard unflushed changes and also detach unrelated entities; use it within transactions designed for bulk operations. For SQL written outside JPA, proactively `refresh`/`clear`/reload at appropriate times. If using a second-level cache, evaluate cache invalidation strategies per provider; external writers typically do not notify the ORM.

## 4. Spring Data JPA Example: Explicit Audit and Version Updates

The following snippets are illustrative files intended for a **Spring Boot application with Spring Data JPA, a database driver, and datasource configuration**; they are not standalone Java programs runnable with `javac` alone. Examples use Java 17+, `jakarta.persistence`, and standard audit annotations.

**`CustomerAccount.java`** — an entity with audit metadata and version:

```java
package example.audit;

import jakarta.persistence.*;
import java.time.Instant;
import org.springframework.data.annotation.CreatedDate;
import org.springframework.data.annotation.LastModifiedBy;
import org.springframework.data.annotation.LastModifiedDate;
import org.springframework.data.jpa.domain.support.AuditingEntityListener;

@Entity
@EntityListeners(AuditingEntityListener.class)
public class CustomerAccount {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Version
    private Long version;

    private boolean locked;

    @CreatedDate
    @Column(name = "created_at", updatable = false)
    private Instant createdAt;

    @LastModifiedDate
    @Column(name = "updated_at")
    private Instant updatedAt;

    @LastModifiedBy
    @Column(name = "updated_by")
    private String updatedBy;

    protected CustomerAccount() {}

    public void lock() {
        this.locked = true;
    }
}
```

**`AuditConfig.java`** — enabling auditing. The bean in the example returns a system identity; real applications should obtain the authenticated user/service identity and also define an identity for background jobs:

```java
package example.audit;

import java.util.Optional;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.domain.AuditorAware;
import org.springframework.data.jpa.repository.config.EnableJpaAuditing;

@Configuration
@EnableJpaAuditing
class AuditConfig {
    @Bean
    AuditorAware<String> auditorAware() {
        return () -> Optional.of("system-job");
    }
}
```

In the **standard entity path**, fetch the entity and call `account.lock()` inside a transaction. If `locked` changes from `false` to `true`, dirty checking generates an update statement and the auditing listener has the opportunity to populate `updatedAt`/`updatedBy` on flush. `@CreatedDate` is handled at entity creation, not on every update.

**`CustomerAccountRepository.java`** — writing bulk DML that intentionally updates audit data and version:

```java
package example.audit;

import java.time.Instant;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface CustomerAccountRepository
        extends JpaRepository<CustomerAccount, Long> {

    @Modifying(flushAutomatically = true, clearAutomatically = true)
    @Query("""
        update CustomerAccount a
           set a.locked = true,
               a.updatedAt = :changedAt,
               a.updatedBy = :actor,
               a.version = a.version + 1
         where a.id = :id
           and a.version = :expectedVersion
        """)
    int lockWithAudit(
            @Param("id") Long id,
            @Param("expectedVersion") Long expectedVersion,
            @Param("changedAt") Instant changedAt,
            @Param("actor") String actor);
}
```

**`CustomerAccountService.java`** — checking the result within a transaction:

```java
package example.audit;

import java.time.Instant;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerAccountService {
    private final CustomerAccountRepository repository;

    public CustomerAccountService(CustomerAccountRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void lock(Long id, Long expectedVersion, String trustedActor) {
        int affected = repository.lockWithAudit(
                id, expectedVersion, Instant.now(), trustedActor);

        if (affected != 1) {
            throw new IllegalStateException(
                    "Record does not exist or version has changed");
        }
    }
}
```

Explanation:
- `@Modifying` instructs Spring Data to run `@Query` as a data-modifying statement; this annotation **does not perform auditing automatically**.
- `:changedAt` and `:actor` are passed explicitly; use a consistent timestamp/identity across the system. `trustedActor` must come from an authentication layer or trusted job context, never directly from raw client request input.
- `a.version = a.version + 1` works when version is a numeric type such as `Long`. Other version strategies require corresponding handling.
- `where a.version = :expectedVersion` combined with `affected == 1` detects conflicts for a **single** record. The example throws `IllegalStateException` for illustration; an application can translate it to a business conflict error or HTTP 409.
- After `clearAutomatically` runs, avoid reading state from old entity variables; re-query through the repository if fresh values are needed.

Do not copy this pattern blindly to update millions of rows without deciding on transaction size, isolation, lock contention, filtering indexes, and actor resolution. Bulk updates are faster in many scenarios, in exchange for explicitly managing bypassed lifecycle rules.

## 5. When a Process Outside JPA Writes Data

A SQL job, `JdbcTemplate`, migration script, or another service writing to the same table can set metadata explicitly. The SQL example below uses **named parameters bound by the DB access layer** (adjust syntax per database):

```sql
UPDATE customer_account
   SET locked = TRUE,
       updated_at = CURRENT_TIMESTAMP,
       updated_by = :actor,
       version = version + 1
 WHERE id = :id
   AND version = :expectedVersion;
```

Check the updated row count and roll back if business conditions are not met. When both JPA writers and non-JPA writers exist, agree on:
1. **Timestamp owner:** use the application clock with `Instant` and UTC, or database time (`CURRENT_TIMESTAMP`). If combining two sources, check clock skew, time zones, and precision.
2. **Actor source:** authenticated user, service account, or job name; follow a consistent identifier convention. The database does not know the application user unless that actor is passed in.
3. **Version/concurrency rules:** all writers must agree on whether to check/increment version. A non-JPA writer that forgets to increment version removes conflict signals for ORM sessions managing entities.
4. **Transactions and reload state:** business and audit columns should be updated atomically in the same transaction; flush/clear/reload when returning to the ORM, and handle caching as needed.
5. **Deletion rules:** hard deletes remove the row's metadata along with it. If you must know who deleted a row and its prior values, use soft delete, an audit table, or an appropriate change-capture mechanism.

### Should You Use Database Triggers?

**Possibly**, when multiple applications or ETL pipelines write the same data and the database must guarantee `updated_at` or write to an audit table. Triggers run even when changes originate outside JPA, but require evaluating trigger ordering, transactions, performance, and how identity is passed. A trigger that knows the database's `CURRENT_USER` may not know the application's logged-in user. If both application code and triggers write `updated_at`, designate one authoritative source to avoid unexpected results.

**CDC (Change Data Capture)** can observe committed changes for synchronization or history building, but does not automatically recover application identity, change reasons, or values not stored/emitted. If you need a traceable audit trail, clearly define event schemas and pipeline reliability.

## 6. Choosing a Strategy Based on Requirements

| Need | Approach | Trade-off |
| --- | --- | --- |
| Need `@PreUpdate`, entity validation, cascades, auditing, and per-record logic | Load entities, mutate state inside a transaction; consider JDBC batching and bounded batch processing | More entities/SQL, must manage memory and flushing |
| Need low-cost state changes across many records without per-entity callbacks | Bulk JPQL/Criteria/SQL **with explicit audit field updates, version updates, and clear cache policy** | Application takes responsibility for audit/concurrency/business rules |
| Multiple writers, including outside Java | Database-managed timestamps/triggers/stored procedures or mandatory SQL contracts | Requires actor conventions, migrations, DB operations, and DB testing |
| Need to know **every** change, before/after state, and actor | Properly designed audit table, event/outbox, or CDC | More complex storage, consistency, and history querying |

`@LastModifiedDate` does not replace a history storage system; a single last-modified timestamp cannot answer "which fields were changed over time?".

## 7. Integration Testing and Common Mistakes

Test against a **real database compatible with the deployment environment**, real transactions, and reload using a new or `clear`-ed persistence context. Do not assert solely on entities still sitting in the first-level cache.

Scenarios to cover:
1. **Entity path:** updating a JPA-managed entity updates `updated_at`/`updated_by` and increments `version`; if the entity is not dirty, do not assume callbacks always run.
2. **Bulk path without audit (verifying the limitation):** execute `@Modifying` changing only a business field; reloading from DB shows audit fields did not change automatically.
3. **Full bulk path:** run `lockWithAudit` with the matching version; result is `1` row, and state/audit/version are all updated properly.
4. **Stale version:** call with an outdated `expectedVersion`; result is `0` and the service reports a conflict rather than silently overwriting.
5. **Persistence context:** load the entity before a bulk update, demonstrate stale data can remain on the object; confirm reloading after `clear` fetches the new data.
6. **Non-JPA writers:** test scripts/jobs and triggers (if any) to verify timestamp, actor, version, and transaction correctness; also test rollback.
7. **Bulk delete:** verify cascade behavior, foreign key constraints, and deletion history requirements; do not expect `@PreRemove` when deleting via bulk queries.

Common mistakes:
- Thinking `@EnableJpaAuditing` makes **every** `UPDATE` in the DB update metadata automatically.
- Thinking `@Modifying` automatically invokes `@PreUpdate` or `AuditorAware`.
- Adding only `clearAutomatically=true` to "fix auditing"; in reality, it addresses cache state and does not write audit values.
- Incrementing `version` without checking affected row count or defining a concurrency policy; conversely, forgetting to increment version in bulk updates.
- Using `saveAll` and bulk DML interchangeably, leading to wrong decisions about lifecycle/performance.
- Trusting a client-supplied `updated_by` or failing to identify background jobs.
- Checking only managed entities instead of reading database state after bulk operations.

## 8. Key Takeaways

**Spring Data JPA automatic auditing depends on the entity lifecycle.** Bulk JPQL/Criteria DML and updates outside JPA do not automatically perform entity callbacks, audit-field population, optimistic-lock checks, or first-level cache synchronization. When choosing direct write paths, explicitly design **audit fields + actor/time + version/concurrency + transactions + cache/readback**. When full change history is required, add a genuine audit trail mechanism.

### Official Documentation

- [Spring Data JPA — Auditing](https://docs.spring.io/spring-data/jpa/reference/auditing.html)
- [Spring Data JPA — `@Modifying` API](https://docs.spring.io/spring-data/data-jpa/reference/api/java/org/springframework/data/jpa/repository/Modifying.html)
- [Jakarta Persistence 3.2 — Bulk Update and Delete Operations](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Spring Data JPA — `JpaRepository.deleteAllInBatch` API](https://docs.spring.io/spring-data/jpa/reference/api/java/org/springframework/data/jpa/repository/JpaRepository.html)