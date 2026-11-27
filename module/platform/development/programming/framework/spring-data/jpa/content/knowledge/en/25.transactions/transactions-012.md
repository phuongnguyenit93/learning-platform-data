# TransactionTemplate: Programmatic Transaction Control

In Spring Data JPA, a transaction groups multiple read/write operations into a single unit of work. If one step fails, changes within the transaction must roll back so data is not left in a half-finished state.

Normally, transaction boundaries are declared with `@Transactional`. When transaction boundaries must be decided directly within processing flow—such as running each data batch in a separate transaction, choosing propagation dynamically, or explicitly marking rollback—Spring provides `TransactionTemplate`.

`TransactionTemplate` is a programmatic transaction management API. It accepts a callback, starts or joins a transaction via `PlatformTransactionManager`, executes the callback, and commits or rolls back based on the execution result.

## 1. When should you use TransactionTemplate?

Use `@Transactional` when the transaction boundary aligns stably with a business method. For example: creating an order, deducting inventory, and recording order history must always succeed or fail together.

Use `TransactionTemplate` when boundaries need to be expressed directly in code:

- Each batch of data needs an independent transaction.
- Only a specific conditional branch needs to open a transaction.
- A component needs to run a transactional block of work without annotating the entire calling method.
- `setRollbackOnly()` must be called explicitly after catching and handling an exception inside the callback.
- Propagation or timeout needs to be chosen for a specific unit of work.

Do not use the template for every repository operation. When `@Transactional` expresses the business boundary clearly, the annotation is usually more concise and readable.

## 2. Participating components

`TransactionTemplate` does not manage database connections directly. It delegates starting, joining, committing, and rolling back to a `PlatformTransactionManager`.

In a Spring Data JPA application using one `EntityManagerFactory`, the transaction manager is typically `JpaTransactionManager`. Spring Boot usually auto-configures this transaction manager when the application has the JPA starter and an appropriate datasource.

Basic execution flow:

1. The application calls `transactionTemplate.execute(...)` or `executeWithoutResult(...)`.
2. The template asks the transaction manager for a transaction according to the configured propagation.
3. The callback executes inside the transaction. JPA repositories join that same transaction when using the matching transaction manager.
4. If the callback finishes normally and the transaction is not marked rollback-only, the template requests a commit.
5. If the callback throws an exception outward or the transaction has been marked rollback-only, the template performs a rollback.

Default propagation is `PROPAGATION_REQUIRED`: join an existing transaction if present; otherwise create a new one. Therefore, calling the template does not always mean creating a new physical transaction.

## 3. Declaring TransactionTemplate as a bean

You can create a template from a Spring-managed transaction manager and inject it into services:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
public class TransactionConfig {

    @Bean
    TransactionTemplate transactionTemplate(
            PlatformTransactionManager transactionManager) {

        TransactionTemplate template =
                new TransactionTemplate(transactionManager);

        // This line can be omitted since REQUIRED is also the default.
        template.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRED);

        // Timeout in seconds; only meaningful when starting a new transaction.
        template.setTimeout(30);

        return template;
    }
}
```

In an application with a single transaction manager, Spring can inject the `PlatformTransactionManager` bean directly. If the application has multiple datasources or multiple transaction managers, use `@Qualifier` to specify the manager corresponding to the repositories being operated on. Choosing the wrong manager can prevent JPA operations from joining the transaction controlled by the template.

Templates should be configured once and reused. `TransactionTemplate` instances are thread-safe once configured; avoid mutating propagation, isolation, or timeout on a shared bean per request. If different policies are needed, declare separate template beans.

## 4. Example: transferring funds between two accounts

Suppose two accounts are persisted via an `Account` entity. When transferring money, debiting and crediting must occur in the same transaction. If the source account has insufficient funds or the destination account does not exist, all changes must roll back.

Illustrative entity:

```java
import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "accounts")
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, precision = 19, scale = 2)
    private BigDecimal balance;

    protected Account() {
    }

    public void debit(BigDecimal amount) {
        if (balance.compareTo(amount) < 0) {
            throw new InsufficientFundsException();
        }
        balance = balance.subtract(amount);
    }

    public void credit(BigDecimal amount) {
        balance = balance.add(amount);
    }
}
```

Business exception as an unchecked exception:

```java
public class InsufficientFundsException extends RuntimeException {
    public InsufficientFundsException() {
        super("Insufficient balance to complete the transaction");
    }
}
```

Repository:

```java
import org.springframework.data.jpa.repository.JpaRepository;

public interface AccountRepository
        extends JpaRepository<Account, Long> {
}
```

Service using the template:

```java
import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class TransferService {

    private final AccountRepository accounts;
    private final TransactionTemplate transactionTemplate;

    public TransferService(
            AccountRepository accounts,
            TransactionTemplate transactionTemplate) {
        this.accounts = accounts;
        this.transactionTemplate = transactionTemplate;
    }

    public TransferResult transfer(
            long fromId, long toId, BigDecimal amount) {

        if (amount == null || amount.signum() <= 0) {
            throw new IllegalArgumentException(
                    "Transfer amount must be greater than 0");
        }
        if (fromId == toId) {
            throw new IllegalArgumentException(
                    "Source and destination accounts must differ");
        }

        return transactionTemplate.execute(status -> {
            Account from = accounts.findById(fromId)
                    .orElseThrow(() ->
                            new IllegalArgumentException(
                                    "Source account not found"));

            Account to = accounts.findById(toId)
                    .orElseThrow(() ->
                            new IllegalArgumentException(
                                    "Destination account not found"));

            from.debit(amount);
            to.credit(amount);

            // Both entities are managed by the persistence context.
            // JPA dirty checking will write changes on flush/commit.
            return new TransferResult(fromId, toId, amount);
        });
    }

    public record TransferResult(
            long fromId, long toId, BigDecimal amount) {
    }
}
```

While the callback runs, the two entities fetched via `findById` are managed in the current transaction's persistence context. Hence, changes to `balance` are detected by JPA dirty checking and written to the database at flush or commit; calling `save()` again on the two managed entities is not required.

If `debit()` throws `InsufficientFundsException`, the exception exits the callback and the template rolls back. Crediting the destination account is not committed separately. Likewise, if the destination account is not found after reading the source account, the transaction also rolls back.

The example assumes entities have constructors, getters, or accessors needed by the rest of the application. Entity, repository, exception, and record classes should be placed in separate Java files following project structure.

## 5. execute and executeWithoutResult

Use `execute(TransactionCallback<T>)` when you need to return a value from the callback:

```java
String status = transactionTemplate.execute(txStatus -> {
    // Perform repository operations inside the transaction.
    return "COMPLETED";
});
```

The return type of `execute` is the generic type `T` of the callback. In the fund transfer example, the callback returns `TransferResult`.

Use `executeWithoutResult(Consumer<TransactionStatus>)` when no return value is needed:

```java
transactionTemplate.executeWithoutResult(txStatus -> {
    accounts.save(newAccount);
});
```

Both methods let the template manage the transaction lifecycle. Do not manually call commit, rollback, or close `EntityManager` inside the callback.

## 6. Explicit rollback with TransactionStatus

When an exception escapes the callback, the template rolls back the transaction. However, if the callback catches the exception and returns normally, the template may assume the work succeeded and commit earlier changes.

If you catch an exception but still want a rollback, mark the transaction:

```java
transactionTemplate.executeWithoutResult(status -> {
    try {
        performBusinessOperations();
    } catch (BusinessRuleException ex) {
        status.setRollbackOnly();
        // You can log or prepare a business result here.
    }
});
```

`setRollbackOnly()` requests a rollback when the transaction scope ends. Catching an exception does not automatically imply rollback; decide explicitly whether the callback should fail or mark rollback-only.

If the error must be reported to the caller, usually let an unchecked exception exit the callback instead of swallowing it. `TransactionCallback`'s callback signature does not declare checked exceptions; if a checked error must exit the callback, wrap it in an appropriate unchecked exception.

When the template joins an outer transaction via `PROPAGATION_REQUIRED`, marking rollback-only can affect the entire outer transaction. If the caller still attempts to commit, Spring may throw `UnexpectedRollbackException` to signal the transaction was marked rollback-only.

## 7. Configuring propagation, isolation, timeout, and read-only

Settings are configured on the template before running the callback:

```java
TransactionTemplate template =
        new TransactionTemplate(transactionManager);

template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);

template.setIsolationLevel(
        TransactionDefinition.ISOLATION_READ_COMMITTED);

template.setTimeout(10);
template.setReadOnly(false);
```

Common propagation choices:

| Propagation | Behavior |
|---|---|
| `REQUIRED` | Joins the current transaction; creates a new one if none exists. This is the default. |
| `REQUIRES_NEW` | Suspends the current transaction and creates a new independent transaction. |
| `SUPPORTS` | Joins a transaction if one exists; otherwise executes without a transaction. |
| `MANDATORY` | Requires an existing transaction; throws an error if none exists. |
| `NOT_SUPPORTED` | Suspends the current transaction and runs outside a transaction. |
| `NEVER` | Requires no existing transaction; throws an error if one exists. |
| `NESTED` | Requests a nested transaction, usually based on savepoints and dependent on the transaction manager. |

Key configuration points to understand:

- `REQUIRED` is appropriate when operations must participate in one business transaction. If the template is called inside a `@Transactional` method, it typically joins that transaction.
- `REQUIRES_NEW` is appropriate when a piece of work must commit or roll back independently of the outer transaction, such as writing a separate audit record. The outer transaction is suspended while the new transaction runs.
- Isolation and timeout apply when the transaction manager starts a new transaction. When joining an existing transaction, the existing transaction's settings usually take effect.
- `readOnly=true` is a hint to the transaction manager and persistence provider to optimize read operations. It is not an authorization mechanism and does not guarantee all write operations are blocked.
- `NESTED` depends on savepoint support in the transaction manager. With JPA, a JDBC savepoint does not mean there is a nested persistence context; `JpaTransactionManager` does not enable nested transactions by default.

Example configuring a read-only template:

```java
TransactionTemplate readTemplate =
        new TransactionTemplate(transactionManager);
readTemplate.setReadOnly(true);

List<Account> result = readTemplate.execute(status ->
        accounts.findAll());
```

If an application needs multiple transaction policies, create separate templates per policy instead of mutating a shared bean's configuration during request handling.

## 8. Splitting data batches into independent transactions

A useful case is importing data in batches. If each batch must commit independently, you can configure a template with `REQUIRES_NEW`:

```java
TransactionTemplate batchTemplate =
        new TransactionTemplate(transactionManager);
batchTemplate.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);

for (List<ImportRow> batch : batches) {
    batchTemplate.executeWithoutResult(status ->
            importRepository.saveAll(batch));
}
```

Each call creates an independent transaction, provided the transaction manager can start a new transaction. If one batch fails, that batch rolls back; previously committed batches are preserved. This limits transaction duration and the amount of data held in the persistence context.

If the loop runs inside an outer transaction, `REQUIRES_NEW` suspends the outer transaction on every iteration. Consider connection hold times and connection pool configuration when using nested transactions in this manner.

## 9. Specific notes when using with JPA

**Dirty checking and flush:** Entities loaded in a transaction are usually managed. JPA detects changes and synchronizes on flush. Calling `save()` does not replace a transaction boundary, nor does it mean data has committed.

**Errors at flush/commit time:** Some data constraint errors only surface when Hibernate/JPA flushes or when the transaction manager commits. To detect SQL errors early inside the callback, call `EntityManager.flush()`. If catching persistence errors inside the callback, mark rollback-only before returning from the callback.

**Correct transaction manager:** Repositories and the template must work with the transaction manager managing the right `EntityManagerFactory`. Multi-datasource applications must specify managers explicitly via qualifiers.

**Execution threads:** Standard Spring transactions are bound to the current thread. Do not assume transactions automatically propagate to new threads, `@Async`, or background tasks. If async work needs a transaction, open a separate transaction on that execution thread.

**Keep transactions short:** Avoid making HTTP calls, sending emails, or waiting on external operations inside callbacks unless necessary. Such operations prolong database connection and lock hold times. If events must fire after commit, consider `@TransactionalEventListener(phase = AFTER_COMMIT)` or an appropriate transaction synchronization mechanism.

## 10. Common mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Catching an exception without marking rollback-only | Changes prior to the error may commit. | Let the exception exit the callback or call `status.setRollbackOnly()`. |
| Assuming `REQUIRED` always creates a new transaction | Callback may be joining an outer transaction. | Use `REQUIRES_NEW` when an independent transaction is truly needed. |
| Using the wrong transaction manager | JPA repositories may not join the template's transaction. | Inject the right `PlatformTransactionManager` with a qualifier when multiple managers exist. |
| Mutating a shared template's config per request | Concurrent calls may use unintended settings. | Configure beans once or create separate templates per policy. |
| Performing long network I/O inside a callback | DB connections and locks are held longer than needed. | Keep callbacks focused on data operations; handle external work after commit. |
| Assuming transactions propagate to other threads | Async work runs outside the original transaction. | Open a separate transaction on the execution thread. |
| Assuming `readOnly=true` forbids writes | It is only an optimization hint, manager/provider dependent. | Use privilege controls and explicit business rules when writes must be prevented. |

## 11. Choosing @Transactional or TransactionTemplate?

| Criterion | `@Transactional` | `TransactionTemplate` |
|---|---|---|
| Declaration style | Annotation on class or method | Callback in Java code |
| Transaction boundary | Usually fixed per method | Can wrap a specific block of statements |
| Return value | Method returns normally | Callback returns via `execute` |
| Manual rollback | Can use appropriate rollback-marking mechanisms | Directly exposes `TransactionStatus.setRollbackOnly()` |
| Best suited for | Operations with clear method-level boundaries | Dynamic boundaries, batch processing, or direct control |

Both approaches share the `PlatformTransactionManager` infrastructure and can participate in the same transaction according to propagation. Choose the approach that expresses the business boundary most clearly; avoid nesting multiple transaction layers without a concrete reason.

## 12. Pre-production checklist

- Select the right `PlatformTransactionManager` managing the repository's datasource and persistence context.
- Place all operations requiring atomicity inside the same callback.
- Decide clearly whether the callback lets exceptions escape or catches and marks rollback-only.
- Verify propagation when the template is called from an already-`@Transactional` method.
- Only set isolation, timeout, and read-only when specifically needed.
- Keep transactions short and do not rely on another thread's transaction.
- Test both the success path and mid-way failure cases to verify data commits or rolls back as required.

`TransactionTemplate` is useful when an application needs to control transaction boundaries directly within Java flow. With Spring Data JPA, ensure the template and repositories use the matching transaction manager; entity changes, repository operations, and commit/rollback decisions will then coordinate within the same transaction.