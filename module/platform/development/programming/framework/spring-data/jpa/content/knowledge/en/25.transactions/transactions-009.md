# Timeout, Flush, and When Constraint Errors Occur

In Spring Data JPA, these three concepts are closely related yet solve different problems:

- **Timeout** limits how long a transaction, query, or lock wait operation is allowed to run.
- **Flush** synchronizes managed changes in the persistence context to the database.
- **Constraint errors** appear when the database or a validation mechanism detects a record violating rules such as NOT NULL, UNIQUE, FOREIGN KEY, or CHECK.

A common point of confusion is that a **save()** call can complete before the SQL INSERT/UPDATE statement is sent to the database. Consequently, constraint errors sometimes appear only at **flush()** or during transaction commit.

## 1. Transaction timeout in Spring

### 1.1. Setting timeout on a transaction boundary

You can set a maximum duration for a transaction using the **timeout** attribute of **@Transactional**:

~~~java
@Service
public class PaymentService {

    private final PaymentRepository payments;

    public PaymentService(PaymentRepository payments) {
        this.payments = payments;
    }

    @Transactional(timeout = 10)
    public void createPayment(Payment payment) {
        payments.save(payment);
        // Operations belonging to the same transaction
    }
}
~~~

In the example, the timeout is **10 seconds**. This is a time budget for the transaction, not a per-SQL-statement limit. If unconfigured, Spring uses the transaction manager's default timeout; typically, the default imposes no specific limit.

Timeout is only meaningful when the transaction manager and underlying resources support enforcing it. Spring can pass the limit down to JDBC/JPA resources, but how the database, JDBC driver, and JPA provider detect or interrupt overdue operations depends on specific configuration and implementation. Do not treat **timeout** as a guarantee that any Java code will be interrupted at second N. For example, CPU-bound computation or **Thread.sleep()** will not necessarily stop immediately when the transaction time expires.

### 1.2. Transaction timeout attaches to the transaction actually created

By default, **@Transactional** uses **REQUIRED** propagation:

- If no transaction exists, Spring creates a new transaction and applies the declared timeout.
- If an outer transaction already exists, the call usually joins that transaction. The outer transaction's timeout and attributes continue to govern; a timeout declared on the joining method does not reset the clock for the running transaction.

Therefore, place the timeout at the service boundary that actually opens the transaction—typically the service method coordinating multiple repository operations.

**@Transactional** is usually applied through a Spring proxy. Calling a transactional method from another method in the same object (self-invocation) can bypass the proxy, preventing the annotation from applying as expected. Call methods through appropriate Spring beans and verify actual transaction boundaries when debugging.

CRUD methods inherited from **SimpleJpaRepository** already have default transaction configurations: read operations are typically read-only, while write operations have a transaction. Custom query methods declared in a repository do not automatically receive transaction configuration merely because they reside in a repository interface. When a business operation spans multiple operations, declare the transaction at the service so the entire operation shares one commit/rollback boundary.

### 1.3. Distinguishing timeout types

| Timeout type | Typical unit | Scope |
|---|---:|---|
| **@Transactional(timeout = 10)** | Seconds | Transaction time budget |
| JPA query hint **jakarta.persistence.query.timeout** | Milliseconds | A single query |
| JPA lock hint **jakarta.persistence.lock.timeout** | Milliseconds | Lock wait time when a query requires locking |
| Connection pool timeout | Pool-dependent, usually milliseconds | Wait time to acquire a connection from the pool |
| JDBC driver socket/read timeout | Driver-dependent | Wait time for network/database response |

These timeouts do not replace one another. For instance, a transaction timeout is not equivalent to a query timeout; a connection pool timeout can happen before any SQL is sent. JPA query hints are hints to the provider and database, so actual support must be confirmed for your system.

You can set a query timeout for a query method in Spring Data JPA:

~~~java
public interface AppUserRepository extends JpaRepository<AppUser, UUID> {

    @QueryHints(
        value = @QueryHint(
            name = "jakarta.persistence.query.timeout",
            value = "2000"
        )
    )
    @Query("select u from AppUser u where u.email = :email")
    Optional<AppUser> findByEmail(@Param("email") String email);
}
~~~

The value **2000** here represents 2,000 milliseconds per JPA query timeout conventions. Import the corresponding annotations from **jakarta.persistence** and **org.springframework.data.jpa.repository**. Query hints do not automatically create a transaction; if the method needs a transaction, configure it separately. For projects using older JPA versions, the hint name may belong to the **javax.persistence** namespace; use the namespace matching your application version.

## 2. Flush and persistence context

### 2.1. JPA defers data writes

Entities are managed in the persistence context. When calling **save()**, Spring Data JPA asks **EntityManager** to save the entity:

- For a new entity, the repository typically calls **persist()**.
- For an existing entity, the repository typically calls **merge()**.
- When using **merge()**, the returned object is the managed instance; continue using the return value of **save()**.

JPA typically uses a **write-behind** mechanism: changes are recorded in the persistence context first, while SQL may be sent to the database at flush time. Therefore, **save()** does not mean the transaction has committed, nor does it guarantee SQL is executed right at that line of code. Certain ID generation strategies, such as **IDENTITY**, may force the provider to INSERT early to obtain the primary key.

### 2.2. What does flush do?

**flush()** synchronizes managed entity state with the database by generating the necessary INSERT, UPDATE, or DELETE statements within the current transaction.

You can request a flush via **EntityManager** or a repository:

~~~java
@Transactional
public void updateUser(AppUser user) {
    users.save(user);
    users.flush();
}
~~~

**JpaRepository** provides **flush()** and **saveAndFlush()**. Two common patterns:

~~~
users.save(user);
users.flush();
~~~

or:

~~~
users.saveAndFlush(user);
~~~

Flush has important characteristics:

1. SQL is executed within the current transaction.
2. The database has an opportunity to check constraints applying to the executed SQL statements.
3. The transaction has still not committed. Data has not become a committed transaction and can still be rolled back.
4. Database locks may continue to be held until the transaction ends.

**Flush does not mean commit.** Flush only pushes pending changes to the database; commit finalizes the transaction.

### 2.3. When does JPA auto-flush?

With **FlushModeType.AUTO** (the default mode per JPA), the provider must ensure query results reflect relevant pending changes in the persistence context. The provider usually flushes before a query that could be affected by those changes. The provider also flushes before transaction commit.

With **FlushModeType.COMMIT**, synchronization is deferred until commit time per the flush mode setting; do not rely on an intermediate query to force pending changes to the database.

Typical flow:

~~~text
Call repository.save(...)
        |
        v
Entity is managed in persistence context
        |
        v
Manual flush, auto-flush before a relevant query,
or flush on commit
        |
        v
INSERT / UPDATE / DELETE sent to database
        |
        v
Database checks constraints
        |
        v
Commit succeeds or transaction rolls back
~~~

## 3. Why can constraint errors appear late?

### 3.1. Validation timing depends on when SQL runs

Suppose table **app_user** has a UNIQUE constraint on column **email**. A transaction inserting an existing email can proceed as follows:

1. **save()** places the entity into the persistence context.
2. The service method continues executing and may return a result from the method body.
3. On flush, JPA sends the INSERT to the database.
4. The database detects the duplicate email and rejects the INSERT.
5. The transaction cannot commit successfully and must roll back.

Without calling flush manually, step 3 may occur during commit after the service method body finishes running. Even then, the error is still thrown to the caller of the transactional method, because Spring must finish committing before returning control to the caller.

| Timing | What can happen |
|---|---|
| **save() / persist()** | Entity enters the persistence context; some checks or SQL may run early depending on provider and ID generation strategy |
| **flush() / saveAndFlush()** | SQL is sent to the database; constraint errors commonly appear here |
| **commit()** | JPA flushes remaining changes; errors can appear here if not flushed earlier |
| Commit with deferred database constraints | Constraints configured as deferred are only verified at the end of the transaction |

Therefore, the line containing **save()** is not necessarily where the error surfaces. To proactively detect SQL errors earlier inside a method, you can call **flush()** or **saveAndFlush()**. Still, even flushing does not guarantee detecting constraints configured by the database to defer checking until commit.

### 3.2. Distinguishing Bean Validation from database constraints

There are two common validation layers:

- **Bean Validation**: e.g., **@NotNull**, **@NotBlank**, **@Email**. When validation is integrated with JPA, the provider can validate entities before writing SQL, typically at lifecycle events like persist or update.
- **Database constraints**: e.g., NOT NULL, UNIQUE, FOREIGN KEY, CHECK. The database checks them when the corresponding SQL statement executes, or at commit if configured as deferred.

**@Column(nullable = false)** describes mapping/schema and can be used during DDL generation; it does not replace data validation in Java. If input validation is needed before touching the database, use appropriate Bean Validation. If data integrity must be protected against concurrent requests, the database still needs real constraints created via migrations or DDL.

### 3.3. Exceptions can be wrapped across multiple layers

When the database rejects an INSERT/UPDATE, the exception passes through the JPA provider and Spring. Depending on provider, dialect, and failure timing, the outermost exception class may vary. Spring Data JPA typically translates data integrity failures into **DataIntegrityViolationException**; the cause chain may hold Hibernate-, JDBC-, or JPA-specific exceptions.

Do not rely solely on the outermost exception name to draw conclusions. Inspect the cause chain, SQLSTATE/vendor code, SQL statement, and the constraint reported by the database. Also distinguish database constraint errors from Bean Validation's **jakarta.validation.ConstraintViolationException**; they share a similar phrase yet belong to two different mechanisms and packages.

### 3.4. Transaction state after a flush failure

When a flush fails, the transaction is usually no longer safe to continue. The JPA provider or transaction manager may mark the transaction rollback-only. If you catch the exception and keep writing data in the same transaction, the final commit attempt may fail—for example, with **UnexpectedRollbackException**.

The safe pattern is usually letting the exception exit the transaction boundary so the transaction rolls back, then translating the error into a business response at the appropriate layer. If retrying or continuing is required, do so in a new transaction after the failed transaction has ended. Do not swallow exceptions and treat the transaction as still valid.

## 4. Example: detecting duplicate email at flush

The following example illustrates an entity with an application-generated UUID and a UNIQUE constraint on email. The code uses Java 17, Jakarta Persistence, and Spring Data JPA; these are classes within a Spring Boot application configured with a datasource, JPA, and schema, not a standalone Java program.

~~~java
import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import java.util.UUID;

@Entity
@Table(
    name = "app_user",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_app_user_email",
        columnNames = "email"
    )
)
public class AppUser {

    @Id
    private UUID id;

    @Column(nullable = false)
    private String email;

    protected AppUser() {
    }

    public AppUser(String email) {
        this.id = UUID.randomUUID();
        this.email = email;
    }

    public UUID getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }
}
~~~

Repository:

~~~java
import java.util.UUID;
import org.springframework.data.jpa.repository.JpaRepository;

public interface AppUserRepository
        extends JpaRepository<AppUser, UUID> {
}
~~~

Service:

~~~java
import java.util.UUID;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RegistrationService {

    private final AppUserRepository users;

    public RegistrationService(AppUserRepository users) {
        this.users = users;
    }

    @Transactional(timeout = 5)
    public UUID register(String email) {
        AppUser saved = users.save(new AppUser(email));

        // Force immediate SQL synchronization here so constraint errors
        // typically surface during the flush call.
        users.flush();

        return saved.getId();
    }
}
~~~

If **register()** is called a second time with an existing email and the database has the corresponding UNIQUE constraint, **users.flush()** makes the database check the INSERT and typically throws a data integrity exception right at that call. The current transaction rolls back. If the **users.flush()** line is omitted, SQL may only be sent when the transaction commits; in that case, the caller still receives the exception while the service call finishes the transaction.

Note: declaring **uniqueConstraints** in an entity only affects schema creation when DDL generation is enabled. For databases managed with migrations, ensure the migration actually creates constraint **uk_app_user_email**; annotations do not automatically alter an existing schema.

## 5. How does timeout interact with flush?

A transaction timeout covers both business processing time and resource operations within the transaction. For example, a transaction with a 5-second timeout may spend time on business validation, lock waiting, and SQL execution. If the transaction exceeds the limit, resource access or commit may be rejected depending on the transaction manager, provider, and driver.

Some scenarios:

- The method executes extensive processing before flushing: the timeout may already be spent by the time SQL is sent.
- Flush executes a slow INSERT/UPDATE: the transaction limit or statement timeout may cause the operation to fail.
- The transaction waits on a lock: lock timeout and transaction timeout may both be involved; which takes effect depends on configuration.
- The method joins an outer transaction: the outer transaction's timeout remains the governing limit.
- Transaction timeout is not a substitute for query timeout, connection timeout, or socket timeout.

Do not extend transactions while making HTTP calls, waiting for user input, processing large files, or doing work that does not need an open transaction. Keep transaction boundaries short, set timeouts based on realistic SLAs, optimize queries and indexes, and configure database/driver timeouts when SQL execution time needs strict bounds.

## 6. Diagnostic workflow for timeout or constraint errors

When errors only surface at **flush()** or commit, inspect in order:

1. **Confirm the transaction is active**: verify the method is invoked via a Spring bean/proxy, not self-invocation; identify the transaction manager in use.
2. **Identify where the transaction started**: inspect propagation and outer transactions. A timeout on a joining method does not necessarily alter an existing transaction's timeout.
3. **Check timeout units and scopes**: **@Transactional** uses seconds; JPA query/lock hints typically use milliseconds. Also inspect pool and JDBC driver timeouts.
4. **Determine when SQL actually runs**: enable SQL logging in development or test environments; try intentional **flush()** calls to isolate when data synchronization fails.
5. **Cross-check the database schema**: verify actual constraints, constraint names, data types, duplicate data, and foreign key relationships. Do not rely solely on entity annotations.
6. **Read the cause chain**: extract SQLSTATE/vendor codes and constraint details from the root exception; distinguish Bean Validation from database constraints.
7. **Check transaction state after an error**: if already rollback-only, end the transaction and perform follow-up work in a new transaction when appropriate.
8. **Write integration tests with the target database**: test duplicate emails, null values, invalid foreign keys, lock contention, and slow queries. Behavior can differ between H2 and production databases.

## 7. Common misconceptions

| Misconception | Reality |
|---|---|
| **save()** succeeding means the database committed | **save()** may only update the persistence context; commit occurs at the transaction boundary |
| **saveAndFlush()** is equivalent to commit | It flushes SQL within the current transaction, yet the transaction can still roll back |
| Calling **flush()** means data is durable | Flush does not commit; the transaction is not yet finalized |
| **@Transactional(timeout = 5)** is a 5-millisecond timeout | The unit of this attribute is seconds |
| Query timeout and transaction timeout are the same | One bounds a query, the other bounds a transaction |
| Catching errors at **save()** is enough | Errors may only appear at flush or commit |
| Catching an exception and continuing in the same transaction is always safe | The transaction may already be rollback-only; subsequent commit will still fail |
| **@Column(nullable = false)** ensures input data is valid in Java | Bean Validation is needed for input validation and real database constraints for data integrity |
| Adding **@Transactional** anywhere always works | Proxies, self-invocation, and existing transactions can alter behavior |

## 8. Key takeaways

- Use **@Transactional(timeout = ...)** to set a transaction time budget at the right service boundary.
- Use JPA query/lock timeouts when separate limits on queries or lock waits are required; verify provider and database support.
- Treat **save()** as a request for JPA to save an entity, not a guarantee that SQL has run or the transaction has committed.
- Use **flush()** or **saveAndFlush()** when you need to force SQL execution early and catch database constraint errors before remaining business steps.
- When flush fails, let the transaction roll back and handle the exception at an appropriate boundary; do not keep using a transaction that may already be rollback-only.
- Always verify constraints in the actual schema and test on a database type close to the deployment environment.