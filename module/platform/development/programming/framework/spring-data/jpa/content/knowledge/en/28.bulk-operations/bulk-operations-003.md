# Transaction Requirements for Modifying Queries in Spring Data JPA

When using Spring Data JPA to execute direct `UPDATE` or `DELETE` queries with JPQL or SQL, the application must run the query within an active transaction. The `@Modifying` annotation tells Spring Data that a `@Query` method is a data-modifying query; this annotation **does not open a transaction on its own**. Defining the transaction boundary is the responsibility of `@Transactional` or an enclosing transaction around the call.

This article focuses on bulk DML queries declared in repositories, placing transactions in the service layer, the effects of flush/clear on the persistence context, and common pitfalls when running modifying queries.

> The Java snippets below are intended for a Java 17+ project using Spring Boot 3+ and `spring-boot-starter-data-jpa`. They illustrate classes and methods to integrate into an application, not standalone programs that can be compiled and run directly with `javac`/`java`.

## 1. Why do modifying queries require a transaction?

A transaction groups one or more database operations into a single unit of work. With a transaction, the application can ensure related changes commit together or roll back when work fails.

An `UPDATE` or `DELETE` query alters data state. JPA requires these write operations to execute within a transaction. Calling a DML query without an appropriate transaction can cause the provider to throw `jakarta.persistence.TransactionRequiredException` or an error translated by Spring into another exception.

Transactions also allow combining bulk queries with other business steps. For example, when disabling accounts and writing an audit log entry, both operations should be in the same transaction if the business logic requires them to succeed or fail together.

A `@Transactional` service method is usually the right place to define that boundary. The transaction starts when the call passes through the Spring proxy, internal operations participate in the transaction, and the transaction commits when the method finishes normally. If an exception matching the rollback rules is thrown, the transaction rolls back.

## 2. Distinguishing @Modifying and @Transactional

The two annotations have different roles:

| Annotation | Role |
|---|---|
| `@Modifying` | Marks a `@Query` method as a data-modifying query so Spring Data JPA executes it in modifying mode. |
| `@Transactional` | Defines the transaction enclosing the operation, including when it starts, propagation, read-only status, and rollback rules. |

A repository method declaring a JPQL `UPDATE` or `DELETE` needs `@Modifying`. However, `@Modifying` does not replace `@Transactional`.

Repository example:

```java
import java.time.Instant;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface AccountRepository
        extends JpaRepository<Account, Long> {

    @Modifying
    @Query("""
        update Account a
           set a.enabled = false
         where a.lastLoginAt < :cutoff
           and a.enabled = true
        """)
    int disableInactiveAccounts(@Param("cutoff") Instant cutoff);
}
```

This is an explicitly declared query method. Custom-declared query methods like this do not automatically carry the same transaction configuration as CRUD methods inherited from `JpaRepository`. Therefore, place `@Transactional` on the calling service or directly on the repository method.

## 3. Placing transactions in the service layer

Placing the transaction in the service allows a use case to encompass multiple repository operations within one unit of work. Example:

```java
import java.time.Instant;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountMaintenanceService {

    private final AccountRepository accountRepository;
    private final AuditRepository auditRepository;

    public AccountMaintenanceService(
            AccountRepository accountRepository,
            AuditRepository auditRepository) {
        this.accountRepository = accountRepository;
        this.auditRepository = auditRepository;
    }

    @Transactional
    public int disableInactiveAccounts(Instant cutoff) {
        int affected = accountRepository.disableInactiveAccounts(cutoff);

        if (affected > 0) {
            auditRepository.save(
                    new AuditEntry("DISABLE_INACTIVE_ACCOUNTS", affected));
        }

        return affected;
    }
}
```

When the service method is called through the Spring bean proxy:

1. Spring starts a transaction according to the `@Transactional` configuration.
2. The repository executes the bulk update statement within the current transaction.
3. If records were affected, the service saves an audit entry in the same transaction.
4. When the method finishes normally, Spring commits the transaction.
5. If an operation throws an error causing a rollback, changes from both the update query and the audit entry roll back together.

By default, `@Transactional` uses `REQUIRED` propagation. If a transaction already exists, the call joins it; otherwise, Spring creates a new one. This is usually the right choice for a business use case.

If you want the transaction to start right at the repository, you can declare:

```java
@Modifying
@Transactional
@Query("""
    update Account a
       set a.enabled = false
     where a.id = :id
    """)
int disableAccount(@Param("id") Long id);
```

This approach is valid for a simple single operation. However, if the use case spans multiple repositories or needs coordination with business validations, a service-level transaction clearly expresses the atomic scope of the entire operation. Avoid inadvertently creating separate transactions where part of a use case commits while the remainder fails.

## 4. Calling modifying queries in a read-only transaction

Do not invoke a modifying query inside a transaction marked `@Transactional(readOnly = true)`.

```java
@Transactional(readOnly = true)
public void maintenance() {
    // Do not call bulk UPDATE/DELETE inside this transaction.
}
```

The `readOnly` attribute is an optimization hint for read-only transactions. Depending on the transaction manager, JPA provider, and database engine, it may affect flush mode or set the connection to read-only mode. It is not an identical safeguard across every environment, but it must not be used as a write transaction.

Declare a write transaction at the service boundary:

```java
@Transactional
public int updateAccountStatus(Long id) {
    return accountRepository.disableAccount(id);
}
```

Note: default `REQUIRED` propagation joins an outer transaction if one already exists. If an outer service is running inside a `readOnly = true` transaction, an inner call does not automatically turn the current transaction into a write transaction merely by setting `readOnly = false` on the called method. Design the outer use case's transaction boundary appropriately for writing data.

## 5. Bulk DML and the persistence context

A bulk JPQL query executes directly against the database. It does not load each entity and call setters, so it does not go through the normal dirty-checking pipeline for managed entities.

This has an important consequence: if the persistence context holds an `Account` entity with `enabled = true`, after a bulk query updates the column to `false`, the in-memory object may still hold `true`. The persistence context has become stale relative to the database.

Example:

1. The service loads `Account` ID 10 into the persistence context.
2. A modifying query sets `enabled = false` for that account.
3. The previously loaded entity may still show `enabled = true` in memory.
4. If the old entity continues to be used, business logic may read outdated state.

`@Modifying` provides two options:

- `flushAutomatically = true`: requests flushing the persistence context before running the modifying query.
- `clearAutomatically = true`: requests clearing the persistence context after the query executes.

Example:

```java
@Modifying(
    flushAutomatically = true,
    clearAutomatically = true
)
@Query("""
    update Account a
       set a.enabled = false
     where a.lastLoginAt < :cutoff
    """)
int disableInactiveAccounts(@Param("cutoff") Instant cutoff);
```

Both attributes default to `false`. Enable them only when appropriate for how the service uses the persistence context:

- Flushing before the query synchronizes pending entity changes to the database before bulk DML runs.
- Clearing after the query removes managed entities from the persistence context to avoid continuing to use stale state.
- `clear()` affects the entire current persistence context, not just the entities updated by the query. Previously loaded entities become detached.
- If you clear while unflushed changes still exist, pending changes may be lost from the persistence context. Therefore, consider `flushAutomatically = true` when enabling clear with pending changes.
- After clearing, if fresh data is needed, re-query the entity or use `EntityManager.refresh()` on an appropriate entity.

You do not need to enable both attributes for every modifying query. If the service does not hold related entities in the persistence context or does not reuse them after the query, the default configuration may suffice.

## 6. Transactions, rollback, and exceptions

By default, Spring rolls back a transaction when a transactional method throws a `RuntimeException` or `Error`. Checked exceptions do not automatically trigger a rollback under default rules.

If business logic requires rolling back when a checked exception is thrown, declare it explicitly:

```java
@Transactional(rollbackFor = Exception.class)
public void updateAndRecord() throws Exception {
    accountRepository.disableInactiveAccounts(Instant.now());
    auditRepository.save(new AuditEntry("MAINTENANCE", 1));
    // A checked exception here will trigger a rollback per configuration.
}
```

Do not catch a query exception, ignore it, and continue treating the transaction as successful. Certain persistence errors cause the transaction to be marked rollback-only. In that case, even if the method does not propagate the error, Spring may still roll back at commit time and throw `UnexpectedRollbackException`.

If you need to translate an exception into a business response, let the transaction finish in its proper state first and handle it at an outer caller layer, or explicitly mark rollback if catching the exception internally is unavoidable.

`@Transactional` works through proxies in Spring's default configuration. Calling another transactional method via `this.someMethod()` within the same object (self-invocation) usually bypasses the proxy, so annotations on the called method may not be applied as expected. Call through an appropriate Spring bean or reorganize service boundaries. Transactions are bound to the current execution thread; do not assume they automatically propagate to a new thread created by `@Async` or an executor.

## 7. DELETE queries, native queries, and affected row counts

The same transaction principles apply to bulk deletes:

```java
@Modifying
@Query("""
    delete from Account a
     where a.enabled = false
       and a.lastLoginAt < :cutoff
    """)
int deleteDisabledAccounts(@Param("cutoff") Instant cutoff);
```

JPQL bulk delete removes matching rows directly. It is not equivalent to loading each entity and calling `repository.delete(entity)`. Entity lifecycle callbacks, ORM-level cascades, and `orphanRemoval` are not executed in the same way as per-entity deletion. If business logic depends on those behaviors, consider deleting entities through an appropriate pipeline or designing cascades/constraints in the database.

For native queries, also use `@Modifying` on `@Query(nativeQuery = true)` methods performing DML, while ensuring an active write transaction exists. Verify syntax, table/column names, and behavior for the target database engine.

An `int` return value indicates the number of rows updated or deleted by the query. This result can be used to verify business conditions, such as when no matching record is found to update:

```java
@Transactional
public void disableAccount(Long id) {
    int affected = accountRepository.disableAccount(id);

    if (affected == 0) {
        throw new IllegalArgumentException(
                "Account not found or status is invalid");
    }
}
```

Interpret the affected row count according to the query conditions. A result of 0 may mean the record does not exist or did not satisfy the `WHERE` condition; there is not always a single cause.

## 8. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| `TransactionRequiredException` when running update/delete | No active write transaction | Enclose the call with `@Transactional` |
| `@Query` update query is treated as a read query | Missing `@Modifying` | Add `@Modifying` to the repository method |
| `@Modifying` is present but transaction error still occurs | Mistakenly assuming `@Modifying` opens a transaction | Add a transaction at the service or repository |
| In-memory entity still holds old values | Bulk DML does not sync the persistence context | Refresh the entity or consider `clearAutomatically` |
| Pending changes disappear after clear | Persistence context cleared before pending changes were flushed | Consider `flushAutomatically = true` before clear |
| Part of use case committed even though later step failed | Operations ran in different transactions | Place a service-level transaction encompassing the use case |
| Transaction does not roll back as expected | Checked exception not in default rollback rules, or exception swallowed | Use appropriate `rollbackFor` and do not swallow persistence errors |
| `@Transactional` appears to have no effect | Self-invocation bypassing proxy or calling an object outside the Spring container | Check bean creation and proxy call path |

## 9. Implementation checklist

- Repository methods using `@Query` for update/delete are annotated with `@Modifying`.
- Modifying query calls run within an active write transaction.
- Transactions are placed in the service when a use case coordinates multiple repository operations.
- Modifying queries are never invoked inside read-only transactions.
- `flushAutomatically` and `clearAutomatically` are clearly understood before enabling them.
- Potentially stale entities are not reused after bulk DML; refresh or reload when needed.
- Rollback rules for business exceptions are defined.
- Tests cover successful updates, zero matching rows, and mid-transaction failures.
- For bulk delete/native queries, callbacks, cascades, persistence context, and database differences are evaluated.

When using modifying queries in Spring Data JPA, treat `@Modifying` as an instruction about the query type and `@Transactional` as the boundary guaranteeing atomicity. Combining both mechanisms properly, along with managing the persistence context after bulk DML, keeps database data and application entity state consistent.
