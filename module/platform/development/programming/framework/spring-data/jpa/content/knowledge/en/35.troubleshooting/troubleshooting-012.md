# Errors That Only Appear at Flush or Commit

In JPA, calling `repository.save(entity)` does not mean all SQL statements have been sent to the database right on that line. Entities are normally managed inside a persistence context; Hibernate can defer INSERT or UPDATE statements until flush. Transactions also only commit after the business method finishes and the transaction manager executes the commit step.

Therefore, a data or concurrency error may not surface at `save()`. It only appears when the persistence context flushes, or later when the database confirms commit. Accurate diagnosis requires identifying which step threw the error, reading the root cause in the stack trace, and testing with the right transaction boundaries.

## 1. Distinguishing Save, Flush, and Commit

Three operations serve distinct roles:

- **save:** asks Spring Data JPA to persist/merge the entity. The repository usually calls `EntityManager.persist()` for new entities or `EntityManager.merge()` for entities needing merge. This updates persistence context state; SQL may be sent immediately or deferred depending on provider, ID generation strategy, and flush mode.
- **flush:** synchronizes pending changes in the persistence context down to the database by issuing the necessary SQL statements. Flush does not end the transaction and does not make data committed.
- **commit:** finalizes the transaction. Before committing, the JPA provider normally flushes remaining changes. Afterward, the database completes the transaction or rejects the commit.

Simple flow example:

```text
repository.save(entity)
        |
        v
Entity is managed in the persistence context
        |
        v
flush: send INSERT / UPDATE / DELETE to the database
        |
        v
commit: database confirms transaction
```

Some actions can trigger flush earlier than commit. Under flush mode `AUTO`, the JPA provider may flush before a query if pending changes could affect query results. Consequently, an error sometimes surfaces on an apparently read-only query, even though its cause was an entity modified earlier.

Do not treat `save()` returning normally as proof that data has been successfully written. Persistence is only confirmed after the transaction commits successfully.

## 2. Why Are Errors Deferred?

JPA uses dirty checking to track managed entities. When the application changes attributes, the provider may record changes only in memory. SQL UPDATE statements are generated at flush time.

Example:

```java
@Transactional
public void rename(Long id, String newName) {
    Customer customer = repository.findById(id)
            .orElseThrow();

    customer.setName(newName);

    // SQL UPDATE may not have executed here yet.
}
```

If the `name` column has a length limit, a unique constraint, or a validating database trigger, the error may surface at flush. When `rename` finishes, the transaction interceptor executes commit; that commit step can trigger the final flush and throw the exception to the caller.

Common causes include:

- **Database constraints:** violating NOT NULL, UNIQUE, FOREIGN KEY, CHECK, or data type limits.
- **Optimistic locking:** the record's version was updated by another transaction; the provider detects it when executing the version-checked UPDATE.
- **Pessimistic locking and deadlocks:** the database fails to grant a lock or detects a deadlock when SQL runs.
- **Bean Validation:** constraints like `@NotNull` and `@Size` are validated during appropriate lifecycle events, typically on persist/update or flush.
- **Entity lifecycle callbacks:** logic in `@PrePersist`, `@PreUpdate`, or listeners can throw exceptions.
- **Deferred database constraints:** some databases allow constraints to be checked at transaction end rather than immediately per statement, causing errors to appear only at commit.

Exact timing depends on the JPA provider, database, JDBC driver, ID generation strategy, and constraint configuration. Some INSERTs execute immediately, such as when using an ID generation strategy requiring the database to return the key right away.

## 3. Using Flush to Surface Errors Earlier

Spring Data JPA provides `saveAndFlush(entity)` and `flush()` via `JpaRepository`. You can invoke them when you need immediate SQL feedback within the current flow:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer create(Customer customer) {
        return repository.saveAndFlush(customer);
    }
}
```

Or:

```java
@Transactional
public void update(Customer customer) {
    repository.save(customer);
    repository.flush();
}
```

`saveAndFlush` saves and then requests a flush. `flush()` synchronizes all pending changes in the associated EntityManager's persistence context, not just the entity passed to the repository. Hence, another entity modified earlier in the same persistence context can also trigger an error during this flush.

Flush surfaces errors that the database checks during SQL execution earlier, yet it does not guarantee all commit errors are caught. Constraints deferred by the database until transaction end, commit failures, or transaction synchronization errors can still occur after a successful flush.

Also avoid calling `saveAndFlush` after every `save` out of habit. Frequent flushes forfeit batching benefits, increase database round-trips, and slow down transactions. Flush early only for clear reasons, such as needing constraint validation results before continuing to the next step.

## 4. Example: Unique Error Surfacing Only at Flush or Commit

Suppose the customer table has a unique constraint on email. Entity:

```java
@Entity
@Table(
    name = "customer",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customer_email",
        columnNames = "email"
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false)
    private String email;

    protected Customer() {
    }

    public Customer(String email) {
        this.email = email;
    }
}
```

Repository:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {
}
```

Service:

```java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void register(String email) {
        repository.save(new Customer(email));
        // INSERT may be deferred until flush or commit.
    }
}
```

If email already exists, calling `register` may only throw when the transaction interceptor flushes and commits after the method body finishes. If you want SQL errors to surface inside the service, change it to:

```java
@Transactional
public void register(String email) {
    repository.saveAndFlush(new Customer(email));
}
```

Both approaches must handle transaction failure. Flushing early does not commit the operation; the transaction can still roll back or fail at commit.

In practice, define clear business behavior for duplicate emails. You can pre-check to improve user messaging, yet `existsByEmail` followed by `save` does not eliminate race conditions: two requests can still both see no existing email. A database unique constraint is the final safeguard. Applications must handle constraint errors to return appropriate responses.

## 5. Common Exceptions and Reading Root Causes

Spring, the JPA provider, and the JDBC driver can wrap the same failure through multiple exception layers. Do not look only at the outermost exception.

| Symptom | What to inspect |
|---|---|
| `DataIntegrityViolationException` | Spring reports a data integrity violation, usually related to constraints or invalid data |
| Hibernate `org.hibernate.exception.ConstraintViolationException` | SQL violated a database constraint |
| `jakarta.validation.ConstraintViolationException` | Bean Validation constraint failed; this is a different exception from Hibernate's same-named class |
| `ObjectOptimisticLockingFailureException` | Spring reports an optimistic locking conflict |
| JPA `OptimisticLockException` | Version or optimistic lock state is no longer valid |
| `TransactionSystemException` | Transaction manager encountered an error finalizing the transaction; inspect cause and root cause |
| `UnexpectedRollbackException` | Transaction was marked rollback-only while outer flow still proceeded to commit |
| `CannotAcquireLockException` or database deadlock error | Failed to acquire a lock or database aborted transaction due to deadlock |

For SQL errors, check the `Caused by` chain for:

- Database SQLState and vendor error code.
- Violated constraint name if supplied by the driver.
- Table, column, or value involved if mentioned in the message.
- Executing SQL statement and the repository/service call that initiated it.
- Original exception type thrown by the JDBC driver or JPA provider.

Do not confuse `org.hibernate.exception.ConstraintViolationException` with `jakarta.validation.ConstraintViolationException`. One originates from database constraints, while the other originates from Bean Validation. Fixes and inspection points differ.

SQL messages can contain sensitive data. Only enable SQL and bind parameter logs in suitable environments, restrict log access, and avoid logging passwords, tokens, or unnecessary personal data.

## 6. Catching Exceptions at the Right Transaction Boundary

With `@Transactional` methods, Spring normally uses a proxy to begin the transaction before entering the method and commit after the method returns. Thus, commit errors can be thrown after the method body has finished, at the proxy invocation site in the caller.

Example:

```java
try {
    customerService.register(email);
} catch (DataIntegrityViolationException ex) {
    // Map constraint error to an appropriate business response.
}
```

Wrapping the service call externally catches errors thrown both inside the method body and during transaction interceptor commit. Still, exact exception types depend on the provider and transaction manager; inspect the cause chain when classifying instead of relying solely on the outermost exception class.

Avoid catching exceptions inside a transaction and continuing as if the transaction were still healthy:

```java
@Transactional
public void register(String email) {
    try {
        repository.saveAndFlush(new Customer(email));
    } catch (DataIntegrityViolationException ex) {
        // Do not ignore and keep using this transaction.
    }

    // Transaction may already be rollback-only or the persistence context
    // is no longer in a valid state to continue.
}
```

After a persistence error, the transaction may have been marked rollback-only. Continuing to write data can lead to `UnexpectedRollbackException` at transaction end or confusing follow-up errors. Let the exception escape the transaction and handle it outside, or isolate secondary work into an independent transaction with explicitly designed propagation.

Also remember that calling a `@Transactional` method internally from another method on the same object usually bypasses the proxy; the annotation may not start a new transaction as expected. Place transaction boundaries on beans/services called via Spring proxies and verify existing transaction propagation.

## 7. Distinguishing Flush Errors from True Commit Errors

Classify by observed timing:

**Errors at flush**

- SQL INSERT/UPDATE/DELETE is sent and the database returns an error.
- Bean Validation or lifecycle callbacks fail as the provider synchronizes the persistence context.
- Optimistic lock is detected when the version-checked UPDATE runs.
- Errors usually appear at `flush()`, `saveAndFlush()`, or before a query triggering provider flush.

**Errors at commit**

- The database checks deferred constraints at transaction end.
- The transaction manager or database reports an error finalizing the transaction.
- The transaction was marked rollback-only by an earlier operation.
- Errors occur during transaction synchronization or commit confirmation.

A successful flush only proves changes synchronized cleanly up to that point. It does not prove the transaction committed. Only after the transaction boundary finishes normally can changes be considered committed.

## 8. Testing Deferred Errors

Ordinary repository tests may miss errors if the test ends before flushing. In `@DataJpaTest`, Spring typically opens a transaction for the test and rolls back afterward. Therefore, explicitly flush to verify SQL errors detectable at that step.

Example:

```java
@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void duplicateEmailFailsOnFlush() {
        repository.saveAndFlush(new Customer("a@example.com"));

        assertThatThrownBy(() ->
                repository.saveAndFlush(
                        new Customer("a@example.com")))
                .isInstanceOf(DataIntegrityViolationException.class);
    }
}
```

This example assumes the unique constraint exists in the test database and Spring translates the exception to `DataIntegrityViolationException`. On different Hibernate/providers or databases, the exact exception type may vary; check the actual cause chain.

To test errors that only surface on commit, tests must go through a transaction that actually commits. If the test has an enclosing transaction like `@DataJpaTest`, a transaction template joining that transaction will not commit independently. Write an integration test without an enclosing transaction, call a `@Transactional` service via the Spring proxy, and catch the exception in the caller after the service returns. Or use `TransactionTemplate` with an isolated transaction and let `execute` complete its commit before asserting failure.

When testing optimistic locking, create two transactions reading the same version, let the first update and commit, then have the second update the stale entity. Verify whether the error surfaces at flush or commit depending on your provider and transaction boundary.

## 9. Diagnostic Workflow in Real Applications

When errors only appear at the end of a request or when a transaction closes, proceed in order:

1. **Identify the transaction boundary.** Find the nearest `@Transactional` method, propagation, and where it is called via Spring proxy.
2. **Locate flush points.** Check for `saveAndFlush`, `EntityManager.flush()`, queries triggering AUTO flush, or end-of-transaction flush only.
3. **Read the full cause chain.** Record the root exception, SQLState, vendor code, and constraint name.
4. **Cross-check data and schema.** Verify nullability, unique, foreign keys, column lengths, check constraints, and version.
5. **Check lifecycle hooks.** Inspect Bean Validation, `@PrePersist`, `@PreUpdate`, entity listeners, and custom callbacks.
6. **Check concurrency.** For optimistic/pessimistic locks, check whether another transaction modified the same record or held locks too long.
7. **Build a reproducing test.** Use a database engine and constraints similar to production; flush explicitly and trigger real commits when testing commit-time errors.
8. **Handle at the right layer.** Roll back the failed transaction, map technical errors to business responses, and only retry transient errors when the operation can be retried safely.

Do not blindly increase timeouts or wrap `save()` in `try/catch` before knowing the root cause. If the cause is a unique constraint, increasing timeouts will not help. If it is an optimistic lock, decide between retrying, reloading data, or reporting a business conflict.

## 10. Key Takeaways

`save()` may only update the persistence context; SQL is usually sent at flush, and transactions are only confirmed at commit. Constraint, validation, callback, optimistic lock, or database errors can therefore surface late. Use `flush()` or `saveAndFlush()` to catch SQL execution errors early when needed, remembering that flush is not commit. Place exception handling outside the transaction boundary, inspect the root cause, and test both flush and actual commit scenarios.
