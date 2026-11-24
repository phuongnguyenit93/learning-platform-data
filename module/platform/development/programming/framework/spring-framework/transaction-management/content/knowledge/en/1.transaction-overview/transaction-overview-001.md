# Transactions Solve the Partial Data Update Problem

## 1. The problem: one business operation with multiple updates

Suppose a system transfers **200 currency units** from account A to account B. Initially, A has 1,000 and B has 500, for a total of 1,500. A single transfer request consists of two data changes **belonging to the same business operation**:

1. Subtract 200 from A: A's balance becomes 800.
2. Add 200 to B: B's balance becomes 700.

If the application or database fails **after step 1 but before completing step 2**, and each SQL statement has already been committed separately, the resulting state is A = 800 and B = 500. The total balance drops to 1,300; the system has recorded **half of a business operation**. Logging an error or letting the user click "retry" does not automatically restore the missing funds.

| Scenario | A | B | Total | Assessment |
| --- | ---: | ---: | ---: | --- |
| Before transfer | 1,000 | 500 | 1,500 | Valid |
| After debiting only A | 800 | 500 | 1,300 | **Partial, violates business rule** |
| After both steps succeed | 800 | 700 | 1,500 | Valid |
| Error occurs and all changes are rolled back | 1,000 | 500 | 1,500 | Valid |

This is the **partial update** problem: individual operations may be valid in SQL, yet the overall state is wrong because they were not completed as a single unit.

## 2. What does a transaction solve?

A **database transaction** groups related changes into a single unit of execution with two outcomes:

- **Commit:** all valid changes within the transaction are confirmed.
- **Rollback:** uncommitted changes within the transaction are undone back to the pre-transaction state.

With the transfer example:

~~~text
Start transaction
    |
    +-- UPDATE A: subtract 200
    |
    +-- UPDATE B: add 200
    |
    +-- Both succeed? -- Yes --> COMMIT --> A=800, B=700
                          |
                          No / error
                          |
                          v
                       ROLLBACK --> A=1000, B=500
~~~

The core point is **Atomicity** in ACID: within the scope of *the same database-supported transaction*, the system does not confirm a "partially completed" state. A transaction protects changes between **begin** and **commit**; it does not mean every operation inside is guaranteed to succeed, nor does it automatically fix invalid data that was already committed earlier.

ACID places atomicity in a broader picture:

| Property | Practical meaning |
| --- | --- |
| **Atomicity** | All changes in a transaction commit together or roll back together. This is the primary solution for partial updates. |
| **Consistency** | A successful transaction must preserve the designed constraints/invariants (primary keys, CHECK constraints, total-balance rules, etc.). A transaction does not invent business rules on its own. |
| **Isolation** | Defines to what extent concurrent transactions see and affect each other; dirty reads, lost updates, and contention must be considered separately. |
| **Durability** | After a successful commit, the database is responsible for persisting the data according to the DBMS's durability guarantees and storage configuration. |

**Important distinction:** rollback resolves failures *before commit*. If a transaction has already committed and the application loses the connection before receiving the response, the client may not know the outcome. Blindly resending the request risks transferring the money twice; this case requires an **idempotency key** or a mechanism to recognize already-processed requests.

## 3. Why can two ordinary UPDATE statements cause partial failures?

Many JDBC connections operate in `autoCommit = true` mode: a successful SQL statement can be committed immediately when the statement finishes. The following conceptual example is *not a transaction spanning the whole business operation*:

~~~sql
UPDATE account SET balance = balance - 200 WHERE id = 1;
-- If the UPDATE above has already committed and the system fails here...
UPDATE account SET balance = balance + 200 WHERE id = 2;
~~~

The second SQL statement failing cannot automatically "undo" the first statement that was already committed. In plain JDBC, a developer can disable auto-commit, explicitly call `commit()`/`rollback()`, and properly restore the connection state. However, when using Spring, we typically delegate transaction lifecycle management to Spring to avoid boilerplate code and ensure a clear business boundary.

## 4. How does Spring Framework manage transactions?

In imperative Spring programming (Spring JDBC/JPA), the common approach is to place `@Transactional` on a **public method of a Spring service** representing a business operation:

~~~java
@Service
public class TransferService {
    @Transactional
    public void transfer(/* source, target, amount */) {
        // 1. Debit source account
        // 2. Credit target account
        // If an error matching rollback rules occurs, the transaction is rolled back.
    }
}
~~~

*The snippet above illustrates a business boundary and is not a standalone Java program.*

Under the default mechanism based on **Spring AOP proxies**, when another object calls `transfer()` **through the Spring bean**:

1. The proxy routes through the transaction interceptor. The appropriate `PlatformTransactionManager` opens a new transaction or joins an existing one, depending on configuration.
2. With JDBC, the transaction manager manages the connection and transaction state bound to the execution context; `JdbcTemplate` uses the connection belonging to that transaction when sharing the same `DataSource`.
3. The business method executes the SQL statements.
4. When the method finishes normally and the existing transaction is not marked rollback-only, Spring commits at the boundary it manages. If an exception matching the rollback rules escapes the method, Spring rolls back (or marks rollback-only if participating in a caller's transaction).

`@Transactional` does not automatically create a transaction on every Java call: if you instantiate with `new TransferService(...)`, if you make an internal call via `this.someTransactionalMethod()` inside the same bean, or if the transaction manager/data source is misconfigured, the call may bypass the proxy or fail to protect the operations as expected. Clear service boundaries and real rollback tests are essential.

**Important default:** Spring rolls back on `RuntimeException` and `Error`; checked exceptions such as `IOException` do **not** trigger rollback by default. When a business operation needs to roll back on a checked exception, explicitly configure `@Transactional(rollbackFor = IOException.class)` (and declare/handle the exception properly in Java). Catching and swallowing an exception inside a transaction can also allow the method to finish normally, leading to an unintended commit.

## 5. Hands-on example: Spring Boot + JDBC + H2

The goal is to directly verify two cases: **a successful transfer commits** and **debiting the source when the target account does not exist rolls back**.

Create a **Spring Boot, Java 17+, and Maven** project using Spring Initializr, adding the **JDBC API / Spring JDBC**, **H2 Database**, and **Spring Boot Starter Test** dependencies. Keep the package structure below; the project includes the Maven Wrapper (`mvnw`, `mvnw.cmd`) provided by Initializr. H2 here is an **in-memory database for learning and running tests**, not a storage design for a real banking system.

**File 1 — `src/main/resources/schema.sql`**

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);
~~~

The `balance` column uses an integer type (smallest currency unit) to avoid binary floating-point rounding errors from `double` in monetary calculations. `CHECK (balance >= 0)` acts as a safeguard at the database layer. With embedded H2 and Spring Boot's standard SQL initialization mechanism, `schema.sql` runs when initializing the database.

**File 2 — `src/main/java/com/example/transactiondemo/TransactionDemoApplication.java`**

~~~java
package com.example.transactiondemo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class TransactionDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(TransactionDemoApplication.class, args);
    }
}
~~~

**File 3 — `src/main/java/com/example/transactiondemo/TransferService.java`**

~~~java
package com.example.transactiondemo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final JdbcTemplate jdbc;

    public TransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromId, long toId, long amount) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, fromId, amount
        );
        if (debited != 1) {
            throw new IllegalStateException(
                "Source account missing or insufficient balance"
            );
        }

        int credited = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, toId
        );
        if (credited != 1) {
            throw new IllegalArgumentException("Target account missing");
        }
    }
}
~~~

Key points analyzed:

- `@Transactional` wraps **both** `jdbc.update` calls. Both operations participate in the same database transaction managed by Spring.
- The debit statement includes the `balance >= ?` condition, rejecting overdrafts directly at the database level; this condition is also helpful when concurrent requests affect the same account.
- `JdbcTemplate.update(...)` returns the **number of affected rows**. If the source account is invalid/has insufficient funds or the target account does not exist, the service throws an unchecked exception to trigger rollback.
- In the missing-target error case, the source debit statement **has already executed**; it is rollback that must restore the source balance to its original value. Therefore, this is an appropriate test for the partial update case.
- The example stays within the scope of **a single database and a single transaction manager**. A real application also needs transfer authorization, duplicate-transfer protection, auditing, retry handling, and currency rules.

**File 4 — `src/test/java/com/example/transactiondemo/TransferServiceTest.java`**

~~~java
package com.example.transactiondemo;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

@SpringBootTest
class TransferServiceTest {
    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private TransferService service;

    @BeforeEach
    void setUp() {
        jdbc.update("DELETE FROM account");
        jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 1L, 1000L);
        jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 2L, 500L);
    }

    @Test
    void commitsWhenBothUpdatesSucceed() {
        service.transfer(1L, 2L, 200L);

        assertEquals(800L, balanceOf(1L));
        assertEquals(700L, balanceOf(2L));
    }

    @Test
    void rollsBackDebitWhenTargetIsMissing() {
        assertThrows(
            IllegalArgumentException.class,
            () -> service.transfer(1L, 99L, 200L)
        );

        assertEquals(1000L, balanceOf(1L));
        assertEquals(500L, balanceOf(2L));
    }

    private long balanceOf(long id) {
        return jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?",
            Long.class,
            id
        );
    }
}
~~~

Run from the project root directory:

~~~bash
# Linux/macOS
./mvnw test
~~~

~~~powershell
# Windows PowerShell
.\mvnw.cmd test
~~~

**Expected result:** both test methods pass. The first test confirms `(A, B) = (800, 700)` after commit. The second test triggers a failure *after the first UPDATE statement*, then confirms `(A, B) = (1000, 500)`; this proves rollback was triggered and left no partial update in the database. Do not rely on a fixed stdout string because logs and build statistics vary across versions and tools.

If you remove `@Transactional` in this example, try re-running the rollback test in the H2 environment with auto-commit: the source update may already commit before the missing-target error occurs, causing the `balanceOf(1L) == 1000` assertion to fail. Only modify the annotation in a **learning/sandbox environment**; never do this on real data.

## 6. Transaction boundary: where to place it to avoid "partial" states?

A transaction should encompass **all operations that must succeed together**. For example:

- Creating an order and deducting inventory in the **same database**: if creating the order fails, the inventory deduction must be rolled back.
- Writing an invoice and its line items: if any line item is invalid, do not leave an unintended "empty invoice" saved.
- Transferring money between two accounts in the same database: if crediting the target account fails, roll back the debit.

The **service** layer usually represents a complete use case, making it a natural place for `@Transactional`. Do not place separate annotations only on individual repository updates if you want the entire business operation to be a single transaction: two small transactions committing separately can still produce a half-finished state.

### Common pitfalls

| Situation | Consequence to know |
| --- | --- |
| A method calls `this.otherMethod()` annotated with `@Transactional` in the same bean | With default proxies, the internal call is not intercepted to open a separate transaction. Call through a Spring-managed bean or redesign the service boundary. |
| Catching and ignoring an exception after the first update | If the method finishes normally and has not been marked rollback-only, the transaction may commit the changes. Rethrow the exception or explicitly decide on rollback. |
| A checked exception escapes | By default, it does not trigger rollback simply for being a checked exception; use `rollbackFor` when needed. |
| Calling a `@Transactional` method on an object created with `new` | No Spring AOP proxy manages this call. |
| Annotating only the second operation as transactional | The first operation already committed independently and may not be undone when the second fails. |
| Making HTTP calls, sending emails, writing files, or calling external services inside a transactional method | Database rollback does **not** undo external side effects that have already occurred. Design explicit coordination (such as transactional outbox, idempotency, or saga where appropriate). |
| Long-running methods, waiting on the network, or holding a transaction across asynchronous threads | Holds locks/connections longer, increasing contention; thread-bound imperative transactions do not automatically span work running on another thread. |

**About propagation:** `@Transactional` defaults to `REQUIRED`: if a compatible existing transaction exists, the method joins it; otherwise, Spring creates a new one. Therefore, "the method finishes" is **not necessarily** the commit point if it is participating in an outer transaction. `REQUIRES_NEW` can create an independent transaction that commits separately, but misusing it breaks the requirement that *the entire business operation roll back together*. Only change propagation after clearly defining the required commit/rollback rules.

## 7. Transaction limitations and safer design

Transactions solve **atomicity**, but they are not enough on their own to build a data-accurate system under all conditions:

1. **Concurrent contention:** two requests modifying the same account simultaneously also require appropriate SQL/locking/isolation, consistent lock ordering, and deadlock/timeout handling. The `UPDATE ... WHERE balance >= ?` statement prevents a negative balance in the example, but does not replace analyzing all system invariants.
2. **Business constraints:** verify affected row counts, `CHECK` constraints, foreign keys, unique constraints, and input validation; a transaction will not detect "transferred to the wrong person" if all SQL statements are valid.
3. **Multiple resource managers:** a single local DB transaction does not automatically span two independent databases, a message broker, or an HTTP API. Outbox/saga or an appropriate distributed mechanism will need to be considered.
4. **Post-commit failures and retries:** request IDs/idempotency keys and processing states help avoid re-executing the same business command when a client fails to receive a response.
5. **Real verification:** always test at least one failure *after the first step has written data*, then read the database back to verify no partial changes remain.

## 8. Self-check questions

1. If debiting A succeeds and crediting B fails, what is the valid state? **Answer:** roll back both to A = 1,000, B = 500.
2. Why is it not enough that two SQL statements both "succeed when run individually"? **Answer:** correctness belongs to the **entire business operation**, not individual statements in isolation.
3. If `@Transactional` is placed on two different repository methods without an enclosing transaction, is atomicity guaranteed? **No.** Each method can commit independently.
4. Why must we test an exception at the second step? **Because** that is when a prior change exists that needs to be undone; testing an error before any UPDATE does not prove data rollback.
5. Does a database transaction automatically cancel an email that was already sent? **No.** An email is a side effect outside the database transaction.

**Key takeaway:** define the business boundary first, place a single transaction around the changes that must *succeed together or fail together*, validate conditions and errors explicitly, and **prove it with a rollback test**. This is how Spring transactions prevent persisting partially updated data.

### Reference documentation

- Spring Framework — [Declarative transaction management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- Spring Framework — [Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- Spring Boot — [SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)