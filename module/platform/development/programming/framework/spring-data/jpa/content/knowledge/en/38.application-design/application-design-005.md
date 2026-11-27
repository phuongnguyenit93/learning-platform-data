# Existence Checks Before Writing and Concurrent Data Races

In a Spring Data JPA application, a common flow is checking whether a record already exists before inserting it. For example, when registering an account by email: the service calls `existsByEmail(email)`; if not present, it creates the entity and calls `save()`.

This approach is useful for early feedback, but it does not guarantee data uniqueness when multiple requests execute concurrently. Between the check and the write lies a window during which another transaction can insert the same data. This is a *time-of-check to time-of-use* (TOCTOU) bug, commonly called a race condition.

The key rule is: pre-write checks improve user experience and avoid unnecessary work; database constraints are the barrier that actually guarantees uniqueness. The service must handle the case where two requests both pass the check and one is rejected by the database.

## 1. The Typical Existence-Check Flow

Spring Data JPA supports derived queries to check whether a record satisfies a condition. For example:

~~~java
public interface AccountRepository extends JpaRepository<Account, Long> {
    boolean existsByEmail(String email);
}
~~~

The service can invoke that method before saving:

~~~java
@Service
@RequiredArgsConstructor
public class AccountService {
    private final AccountRepository accountRepository;

    @Transactional
    public Account register(String email) {
        if (accountRepository.existsByEmail(email)) {
            throw new EmailAlreadyRegisteredException(email);
        }

        return accountRepository.save(new Account(email));
    }
}
~~~

Advantages of this approach:

- Can return a business error early when the data already exists at check time.
- Avoids instantiating an entity or sending an insert when a duplicate is already known.
- Business intent is easy to read.
- Can be combined with a unique constraint to handle concurrent cases.

However, `existsByEmail()` only answers the question at the moment the query runs. It does not reserve the email or lock a non-existent record. Consequently, the code above still has a race condition.

## 2. How Does a Race Condition Occur?

Suppose the database currently does not contain `a@example.com`. Two requests A and B arrive almost simultaneously:

~~~text
Request A                         Request B
---------                         ---------
existsByEmail() -> false
                                  existsByEmail() -> false
save(account A)
                                  save(account B)
commit succeeds
                                  insert rejected by unique constraint
~~~

Both requests read "does not exist". If the database lacks a unique constraint, both can commit and create two accounts with the same email.

If a unique constraint exists, the database permits only one transaction to create that value. The other transaction fails on insert or during flush/commit. This behavior is essential to protect data invariants even when multiple applications or multiple instances write concurrently.

The gap between checking and using the result is TOCTOU:

1. At check time, the email does not exist.
2. Another transaction inserts that email.
3. The original request proceeds based on the stale check result.
4. The database decides whether the write is valid.

Calling `existsByEmail()` multiple times cannot fix the race condition. Another request can still write right after the final check.

## 3. Enforcing a Unique Constraint in the Database

If email must be unique, declare that invariant in the schema. You can use JPA annotations:

~~~java
@Entity
@Table(
    name = "account",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_account_email",
            columnNames = "email"
        )
    }
)
public class Account {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 320)
    private String email;

    protected Account() {
    }

    public Account(String email) {
        this.email = email;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

The `@UniqueConstraint` annotation describes the constraint in schema generated from mappings. In production systems using Flyway or Liquibase, create and manage unique constraints via migrations so the actual schema is guaranteed.

Example SQL migration:

~~~sql
ALTER TABLE account
    ADD CONSTRAINT uk_account_email UNIQUE (email);
~~~

Migration syntax and how existing duplicate rows are handled depend on the database. Before adding the constraint, find and resolve duplicate rows; otherwise, the migration may fail.

A unique constraint can span multiple columns. For example, email only needs to be unique within each tenant:

~~~sql
ALTER TABLE account
    ADD CONSTRAINT uk_account_tenant_email
    UNIQUE (tenant_id, email);
~~~

Here, the same email can appear in two different tenants but cannot be duplicated within the same tenant. The constraint rules must accurately reflect the business scope of uniqueness.

### Unique Constraint and Unique Index

Many databases implement a unique constraint using a unique index. By design, declare invariants as constraints in schemas/migrations so data intent is explicit. Unique indexes can also be used in specialized scenarios, provided you understand the engine's semantics.

Do not rely solely on Java checks or a non-unique index to protect unique data. Application-level checks cannot coordinate all processes, workers, batch jobs, and other services writing to the database.

## 4. Normalizing Data Before Checking and Writing

Another reason existence checks mismatch constraints is when the application uses different representations for the same value.

For example, business rules treat `Alice@Example.com` and `alice@example.com` as the same email. If the application checks one form while the database stores another, results can become inconsistent.

Define canonicalization rules before querying and saving:

~~~java
public final class EmailNormalizer {

    private EmailNormalizer() {
    }

    public static String normalize(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }
}
~~~

The service uses the same normalized value:

~~~java
@Transactional
public Account register(String rawEmail) {
    String email = EmailNormalizer.normalize(rawEmail);

    if (accountRepository.existsByEmail(email)) {
        throw new EmailAlreadyRegisteredException(email);
    }

    return accountRepository.save(new Account(email));
}
~~~

The example above assumes business policy treats all emails as case-insensitive. Actual email rules should align with the authentication system and existing data; do not arbitrarily alter casing if the domain defines different rules.

Cases to watch for:

- Trimming leading/trailing whitespace.
- Case normalization according to business rules.
- Normalizing phone numbers into a single consistent format.
- Unicode normalization if data can be entered in multiple equivalent character forms.
- Tenant ID, soft-delete status, and other columns participating in the uniqueness scope.
- Database collation and string comparison rules.

If normalization must be guaranteed across all writers, consider storing a separate canonical value or using an appropriate database mechanism. Normalizing only inside one service does not protect data when another batch job writes unnormalized values directly.

## 5. Handling Unique Constraint Violations in Spring Data JPA

When two requests both pass the check, the database rejects one insert. With Spring Data JPA, errors from the JPA provider can be translated by Spring into exceptions in the Spring DAO hierarchy, typically `DataIntegrityViolationException` or an appropriate subclass.

Example service using `saveAndFlush()` to force the insert statement to be sent to the database immediately inside the call:

~~~java
@Service
@RequiredArgsConstructor
public class AccountService {
    private final AccountRepository accountRepository;

    @Transactional
    public Account register(String rawEmail) {
        String email = EmailNormalizer.normalize(rawEmail);

        if (accountRepository.existsByEmail(email)) {
            throw new EmailAlreadyRegisteredException(email);
        }

        Account account = new Account(email);

        try {
            return accountRepository.saveAndFlush(account);
        } catch (DataIntegrityViolationException ex) {
            throw new EmailAlreadyRegisteredException(email, ex);
        }
    }
}
~~~

This snippet illustrates translating a persistence error into a business exception. In a real application, ensure the failing constraint is specifically the email constraint. `DataIntegrityViolationException` can also represent foreign key, not-null, or check constraint violations; do not translate every such error into "email already exists".

You can inspect the constraint name or cause chain according to your database/provider. To keep the service less vendor-coupled, encapsulate constraint identification in a separate persistence component and test against a production-compatible database.

### Note on Rollback-Only Transactions

Do not catch a constraint error and then continue performing further writes in the same transaction as if the transaction were still healthy. After an SQL error, the JPA provider or database may have marked the transaction rollback-only or rendered it unusable.

A clean design is to let the persistence exception escape the transactional method, then translate it at a boundary outside the transaction. For example, a non-transactional facade calls a transactional service bean and catches the exception after the proxy has completed rollback:

~~~java
@Service
@RequiredArgsConstructor
public class AccountRegistrationFacade {
    private final AccountWriter accountWriter;

    public Account register(String email) {
        try {
            return accountWriter.registerInTransaction(email);
        } catch (DataIntegrityViolationException ex) {
            if (ConstraintErrors.isEmailUniqueViolation(ex)) {
                throw new EmailAlreadyRegisteredException(email, ex);
            }
            throw ex;
        }
    }
}

@Service
@RequiredArgsConstructor
class AccountWriter {
    private final AccountRepository accountRepository;

    @Transactional
    public Account registerInTransaction(String email) {
        return accountRepository.saveAndFlush(new Account(email));
    }
}
~~~

This example assumes `ConstraintErrors.isEmailUniqueViolation()` is implemented for the project's database/provider and that the two classes are separate Spring beans so the call goes through the proxy. When the exception leaves `AccountWriter`, the transaction interceptor rolls back before the facade catches the exception.

Another option is letting `@RestControllerAdvice` handle the exception after the service transaction has finished. Which approach fits depends on API boundaries and application architecture.

## 6. Existence Checks Do Not Replace Unique Constraints

The two mechanisms serve different goals:

| Mechanism | Role | Prevents two concurrent requests from creating duplicates? |
|---|---|---|
| `existsByEmail()` | Early check, friendly feedback | No |
| Checking via `findByEmail()` | Fetch existing record and validate business logic | No |
| Unique constraint | Protects the invariant in the database | Yes |
| Catching constraint errors | Translates a failed write into a business response | Does not protect data itself; handles the aftermath |
| Distributed lock | Coordinates writers by a logical key | Can reduce contention if implemented properly, but does not replace constraints |

You can omit the pre-check if business requirements accept attempting the insert and translating constraint errors into a duplicate result. This saves one read query per new registration, though duplicate feedback appears only after the write attempt.

If a pre-check is used, treat it as a UX optimization. The constraint must still exist and the exception must still be handled.

## 7. Can Pessimistic Locking Solve This?

JPA supports pessimistic locking via `@Lock`, for example:

~~~java
public interface AccountRepository extends JpaRepository<Account, Long> {

    @Lock(LockModeType.PESSIMISTIC_WRITE)
    @Query("select a from Account a where a.id = :id")
    Optional<Account> findByIdForUpdate(@Param("id") Long id);
}
~~~

This locks an existing row to prevent another transaction from modifying or deleting it in conflicting ways during the lock duration. However, when an email does not exist yet, the query returns no rows to lock. Therefore, `SELECT ... FOR UPDATE` on a lookup for an absent email is not a portable solution for locking that "gap".

Some databases have gap locks, predicate locks, or specialized locking mechanisms depending on isolation level and query plan. Do not rely on them without verifying behavior on your target engine.

Advanced alternatives include:

- Locking a parent or coordinator row that always exists, such as a tenant row, before checking and inserting.
- Using an advisory lock keyed by a logical key if the database supports it and the architecture accepts engine coupling.
- Using `SERIALIZABLE` transaction isolation and retrying the entire transaction when the database reports a serialization failure.
- Using a database-specific atomic insert/upsert statement.

These approaches carry costs in throughput, contention, deadlocks, and portability. A unique constraint should still be kept as the final safeguard.

### SERIALIZABLE Does Not Eliminate All Errors

`SERIALIZABLE` isolation requires the database to guarantee outcomes equivalent to a valid serial order. The database may reject a transaction with a serialization failure rather than allowing both transactions to commit.

The application must retry the entire transaction inside a fresh transaction when encountering a retryable serialization error. Never reuse a failed transaction. Specific implementations and exceptions depend on the database, driver, and transaction manager.

## 8. Upsert and Insert-If-Absent

If business logic requires "create if absent, otherwise update", an atomic upsert statement may fit better than check-then-act. Syntax depends on the database.

PostgreSQL example:

~~~sql
INSERT INTO account(email, display_name)
VALUES (:email, :displayName)
ON CONFLICT (email)
DO UPDATE SET display_name = EXCLUDED.display_name;
~~~

MySQL example:

~~~sql
INSERT INTO account(email, display_name)
VALUES (?, ?)
ON DUPLICATE KEY UPDATE
    display_name = VALUES(display_name);
~~~

This is database-specific SQL, not portable JPQL syntax. Check conflict semantics carefully: which columns are updated, whether version/audit fields change, which triggers fire, what value is returned, and whether updating is permitted by business rules.

If business logic only wants "insert if absent, otherwise keep unchanged", an atomic statement can use a do-nothing branch or engine equivalent. Clarify whether the API should report "created", "already exists", or "updated".

Do not use upsert merely to dodge exceptions if doing so alters business meaning. For example, registering a duplicate email should usually report a conflict rather than silently overwriting the display name or password.

## 9. Uniqueness in Multi-Instance Systems

An application may run across multiple pods, VMs, or processes. Each instance can execute `existsByEmail()` simultaneously with no awareness of another instance's checks.

In-memory per-process solutions like `synchronized`, `ReentrantLock`, or a local map cannot coordinate across other instances. Nor do they protect data when batch jobs, admin scripts, or other services write directly to the same database.

For shared unique data, the database constraint is the authoritative mechanism. Distributed locks can reduce simultaneous contention, but they require handling lease expiration, connection loss, fencing tokens, retries, and deadlocks. Never treat a distributed lock as a replacement for a constraint.

If API idempotency or duplicate message handling is required, store an idempotency key with a unique constraint. When the same key is resubmitted, the application returns the stored outcome instead of re-executing the business operation. Keys need clear scope, retention TTL, and rules for handling differing payloads.

## 10. Testing Race Conditions Properly

A sequential test only proves that two consecutive calls detect an existing record. It does not prove two concurrent transactions are handled properly.

Integration tests need two independent transactions/connections synchronized so both perform the check before inserting, and then verify only one record is committed.

A test scenario:

1. Start with an empty database and ensure the unique constraint is applied.
2. Launch two independent tasks, each with its own transaction.
3. Use a barrier or latch so both tasks complete the existence check at nearly the same time.
4. Have both attempt to insert the same email.
5. Wait for both transactions to finish.
6. Assert only one row exists for that email.
7. Assert one request succeeded and the other received the conflict error defined by the application contract.

Do not wrap both tasks in a single test transaction, or they will no longer behave as two independent transactions like in production. Use a real database via Testcontainers when verifying locking, unique constraints, and isolation of your target engine.

Example invariant assertion after both tasks finish:

~~~java
assertThat(accountRepository.countByEmail(email)).isEqualTo(1);
~~~

The `countByEmail` method can be declared as:

~~~java
long countByEmail(String email);
~~~

Beyond row counts, tests must verify responses of both requests and transaction states. If using PostgreSQL, MySQL, or another engine, run tests on the same engine/version so results accurately reflect production.

## 11. Business Cases That Must Be Defined Clearly

"Already exists" is not always just a single-column comparison.

Clarify:

- Global uniqueness or per tenant/organization?
- Are soft-deleted records considered existing?
- Is email reuse allowed after an account is deleted?
- Are compared values normalized?
- Should two requests creating the same resource return the same resource ID?
- If the record already exists, return HTTP 409, return the existing resource, or update it?
- When a conflict comes from a different constraint, is returning an "already exists" message acceptable?

For instance, if only non-soft-deleted records participate in uniqueness, the constraint must match the database's capabilities. Partial unique indexes are engine-specific; a plain unique constraint on email can still block email reuse even when the old record is soft-deleted.

Ensure database rules, check queries, and exception handling all reflect one consistent definition.

## 12. Safe Implementation Checklist

Before finalizing an existence-check-then-write flow, verify:

1. Is the business key that must be unique accurately identified?
2. Does the database have a unique constraint or equivalent mechanism?
3. Do migrations resolve existing duplicates before adding the constraint?
4. Are values consistently normalized before querying and saving?
5. Is `existsBy...` used solely as an early check, not a concurrency guarantee?
6. Does the service handle unique violations properly and distinguish them from other constraints?
7. Are errors raised at flush/commit handled at the right transaction boundary?
8. Do you avoid continuing to write inside a transaction marked rollback-only?
9. If using retries or SERIALIZABLE, does each attempt use a fresh transaction with appropriate limits?
10. Do integration tests simulate two concurrent transactions on a production-compatible database?
11. If using upsert, do insert/update/conflict semantics match business rules?
12. Do tests cover tenants, soft deletes, normalization, and idempotency if applicable?

## Conclusion

`existsBy...` enables early checks and friendly feedback, but it does not prevent race conditions between two concurrent requests. To guarantee uniqueness, place a unique constraint in the database, normalize values under a single consistent rule, and handle unique violations at the right boundary after transaction rollback. Pessimistic locks, SERIALIZABLE isolation, upserts, or distributed locks can address specific needs, but they require understanding database semantics and operational costs. Finally, test with two independent transactions on a production-like engine to prove only one operation can create the unique record.