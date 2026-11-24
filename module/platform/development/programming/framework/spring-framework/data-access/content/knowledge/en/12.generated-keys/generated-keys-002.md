# Reading Affected Row Count and Checking Business Expectations

> **Context:** Spring Framework – Data Access, *Updates and Generated Keys* group. The goal is to know how many rows a write statement affected, compare that number against business rules, and then decide whether to continue, return a result, or roll back.

## 1. Why is the affected row count a business signal?

When executing `UPDATE`, `DELETE`, or `INSERT`, the JDBC layer can return an **update count** (*number of affected rows*). With Spring JDBC, `JdbcTemplate.update(...)` returns an `int`, usually the number of rows the database/JDBC driver reports were affected by the statement. It does not merely mean “the SQL ran without error”.

Suppose the application is only allowed to transition **one** order from `PENDING` to `PAID`:

```sql
UPDATE orders
SET status = 'PAID'
WHERE id = ? AND status = 'PENDING';
```

- **`1` row:** a valid state transition of one order was performed; a successful transaction commit is still required to conclude that the change is durable.
- **`0` rows:** no row satisfied the entire `WHERE` condition. The order might not exist, might already be paid, might be cancelled, or might have just been modified by another request; **you cannot conclude from the count alone that “the ID was not found”**.
- **`>1` rows:** violates the “one order” expectation. If the SQL statement can affect multiple rows, this is a sign that the condition is not tight enough or that business rules/schema have an issue. It must be handled before committing.

**Distinctions to keep in mind:**
- **Row count ≠ record count read** from `SELECT COUNT(*)`. A count read before the operation can become stale under concurrent requests.
- **Row count ≠ number of rows whose values actually changed in every DB.** Some DBMSs/drivers report *matched* rows, while others report *actually changed* rows, especially for an `UPDATE` assigning the exact same old value. Verify against the actual DB and driver configuration in use.
- **Row count ≠ proof that the entire business operation succeeded.** Constraints, triggers, transaction rollback, related steps, and state in external systems still must be considered separately.
- **Row count ≠ generated key.** The `int` from `update` indicates the row count; to retrieve an ID generated on `INSERT`, use the corresponding generated-keys / `KeyHolder` mechanism.

## 2. Define expectations before calling SQL

Do not write `if (rows > 0)` out of habit. Clearly define the **allowed** row count and the corresponding response from the use case.

| Operation | Reasonable expectation | Response |
| --- | --- | --- |
| Update one entity by primary key and state condition | `rows == 1` | `0`: condition not met; `>1`: invariant error, do not commit |
| Deduct stock/transfer money with `WHERE available >= amount` | `rows == 1` | `0`: execution condition unmet or data already changed |
| Update with `version` check (optimistic concurrency) | `rows == 1` | `0`: does not exist or stale version |
| Delete a record that *must exist* | `rows == 1` | `0`: report not found or conflict |
| *Idempotent* delete (“after this statement no record remains”) | `rows == 0` **or** `1` | `0` can be a valid outcome, depending on the API contract |
| Update multiple rows by criteria | `0..N` or a specific expected quantity | Check limits, dataset validity, and approved impact |
| Typical single-row `INSERT` | Usually `1` | Handle constraint/duplicate errors; for `UPSERT`/`ON CONFLICT` follow DB-specific conventions |

An easily verifiable design states the **invariant** right in the service: “Each order confirmation must update exactly one row in `PENDING` state”. `rows == 0` is a **business outcome to interpret**, not an infrastructure failure by default. Conversely, `rows > 1` when using a unique key is a dangerous signal requiring investigation.

Do not move `tenant_id`, `status`, `version`, ownership, or business conditions out of `WHERE` and rely solely on an earlier `SELECT`. Conditional updates let the DB verify conditions at write time, reducing race bugs.

## 3. Reading the count with Spring JDBC

`JdbcTemplate.update(String sql, Object... args)` executes a parameterized write statement and returns the number of affected rows. The `?` placeholders are bound safely via JDBC; never concatenate user input directly into SQL.

Integration example inside a Spring application that already has `JdbcTemplate`, an `orders` table, and a transaction manager (this snippet is **not a standalone Java program**):

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderPaymentService {
    private final JdbcTemplate jdbc;

    public OrderPaymentService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void markPaid(long tenantId, long orderId) {
        int rows = jdbc.update(
            "UPDATE orders SET status = ? " +
            "WHERE id = ? AND tenant_id = ? AND status = ?",
            "PAID", orderId, tenantId, "PENDING"
        );

        if (rows != 1) {
            throw new IllegalStateException(
                "Expected one PENDING order, affected rows = " + rows
            );
        }
    }
}
```

Key points to understand:
1. `WHERE id = ? AND tenant_id = ? AND status = ?` narrows down to the exact entity, exact tenant scope, and exact initial state. The count confirms whether **all** of those conditions matched at update time.
2. `@Transactional` wraps the operation. `IllegalStateException` is an unchecked exception; under Spring's default rollback configuration, an exception escaping the transactional method causes the transaction to roll back. If there was an earlier DB write step in the same transaction, that step is rolled back too.
3. If `0` rows are returned, the application may choose to run an additional query (within an appropriate consistency boundary) to distinguish “does not exist” from “already in another state”, and return an appropriate business error code. Do not infer the cause from the count alone.
4. If code calls the `@Transactional` method directly from another method **on the same instance** under standard Spring proxy configuration, the transaction interceptor may not run. Ensure the call goes through the Spring proxy or use `TransactionTemplate` where appropriate.
5. If an exception is caught and swallowed **inside** the `@Transactional` method, the transaction may commit. Let the exception escape or explicitly mark rollback when the business operation truly fails.

`NamedParameterJdbcTemplate.update(...)` also returns `int`, differing only in how parameters are named (e.g., `:orderId` instead of `?`). Regardless of the variant, the count comparison rule stays in the business layer.

## 4. Runnable example: one update succeeds, two updates are rejected

This example uses **Java 17+, Spring JDBC 6.2.x, and H2 2.x**, without Spring Boot. Each operation runs inside `TransactionTemplate`; if the count is not exactly `1`, `IllegalStateException` rolls back the transaction. Use the dependency versions below to reproduce the example.

Structure:

```text
affected-rows-demo/
├── pom.xml
└── src/main/java/demo/AffectedRowsDemo.java
```

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>affected-rows-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.19</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.6.3</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`src/main/java/demo/AffectedRowsDemo.java`:

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class AffectedRowsDemo {
    private static final String DEBIT_SQL =
        "UPDATE account " +
        "SET balance = balance - ?, lock_version = lock_version + 1 " +
        "WHERE id = ? AND balance >= ? AND lock_version = ?";

    public static void main(String[] args) {
        var dataSource = new DriverManagerDataSource(
            "jdbc:h2:mem:counts;DB_CLOSE_DELAY=-1", "sa", ""
        );
        var jdbc = new JdbcTemplate(dataSource);
        var tx = new TransactionTemplate(
            new DataSourceTransactionManager(dataSource)
        );

        jdbc.execute(
            "CREATE TABLE account (" +
            "id BIGINT PRIMARY KEY, " +
            "balance INT NOT NULL, " +
            "lock_version INT NOT NULL)"
        );
        jdbc.update(
            "INSERT INTO account (id, balance, lock_version) VALUES (?, ?, ?)",
            7L, 100, 0
        );

        Integer accepted = tx.execute(status -> {
            int rows = jdbc.update(DEBIT_SQL, 30, 7L, 30, 0);
            requireOne(rows);
            return rows;
        });
        System.out.println("acceptedRows=" + accepted);

        try {
            tx.execute(status -> {
                int rows = jdbc.update(DEBIT_SQL, 80, 7L, 80, 1);
                requireOne(rows);
                return rows;
            });
        } catch (IllegalStateException ex) {
            System.out.println("insufficientFunds=REJECTED");
        }

        try {
            tx.execute(status -> {
                int rows = jdbc.update(DEBIT_SQL, 10, 7L, 10, 0);
                requireOne(rows);
                return rows;
            });
        } catch (IllegalStateException ex) {
            System.out.println("staleVersion=REJECTED");
        }

        Integer balance = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?",
            Integer.class, 7L
        );
        Integer version = jdbc.queryForObject(
            "SELECT lock_version FROM account WHERE id = ?",
            Integer.class, 7L
        );
        System.out.println(
            "balance=" + balance + ", lockVersion=" + version
        );
    }

    private static void requireOne(int affectedRows) {
        if (affectedRows != 1) {
            throw new IllegalStateException(
                "Expected exactly one row; actual=" + affectedRows
            );
        }
    }
}
```

In the `affected-rows-demo` directory, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.AffectedRowsDemo
```

The `System.out.println` output lines of the program (excluding build-tool messages if any):

```text
acceptedRows=1
insufficientFunds=REJECTED
staleVersion=REJECTED
balance=70, lockVersion=1
```

Step-by-step explanation:
- The first call deducts `30` from balance `100`; `balance >= 30` and `lock_version = 0` hold, so count = `1`; after commit, balance is `70`, version is `1`.
- The second call tries to deduct `80`, while balance is only `70`, so count = `0`; the exception triggers rollback.
- The third call deducts `10` but sends stale version `0` instead of `1`, so count = `0`; it makes no change to balance/version.
- At the end, `balance = 70`, `lockVersion = 1` remain.

In this example, the balance and version conditions are in the **same** `UPDATE` statement. If you do `SELECT balance` and then an unconditional update, two concurrent requests could read the same old balance and make wrong decisions. The `UPDATE ... WHERE balance >= ? AND lock_version = ?` pattern provides an atomic check at write time.

## 5. Distinguishing `0` rows: not found, unmet condition, or idempotent?

Do not mechanically turn every `0` into HTTP `404`. For instance, `UPDATE ... WHERE id = 42 AND status = 'PENDING'` returns `0` in at least three situations: ID `42` does not exist, the ID exists but its status is not `PENDING`, or a concurrent change happened before the statement ran.

A sensible workflow:
1. Define the business contract first: if a “mark as paid” request is repeated, should it return **idempotent success** or a **state conflict**?
2. Execute the write statement with a sufficiently specific `WHERE`. When count = `1`, complete within the transaction.
3. If count = `0`, perform an additional read only when you actually need to explain the cause to the caller. A follow-up query can still encounter concurrent data changes; it aids diagnosis rather than replacing the atomic check in the `UPDATE`.
4. If idempotency is a strict requirement, use a request ID/unique key or states designed for retries; **seeing `rows = 0` alone does not prove the earlier request already succeeded**.

Examples:
- `DELETE FROM saved_filters WHERE user_id = ? AND filter_id = ?`: if the contract is “ensure the filter is absent”, count `0` is usually acceptable.
- `UPDATE orders SET status='SHIPPED' WHERE id=? AND status='PAID'`: count `0` may indicate an invalid state transition request, which should be distinguished from not found and recorded clearly.
- `UPDATE inventory SET available=available-? WHERE sku=? AND available>=?`: count `0` means the stock deduction condition was not met; do not assume out-of-stock is the only cause if `sku` could also be missing.

## 6. Controlling concurrent updates and optimistic locking

A common pattern:

```sql
UPDATE documents
SET title = ?, lock_version = lock_version + 1
WHERE id = ? AND lock_version = ?;
```

- The client reads the document at version `5` and sends version `5` when editing.
- If the DB still has version `5`, count is `1` and version increments to `6`.
- If another request already updated it to `6`, count is `0`; the service must report a conflict and let the caller reload the data.
- If the ID does not exist, count is also `0`; handle the distinction when needed.

This is **optimistic concurrency**: the record does not need a long-lived lock from read time until the user saves, but the version condition must be checked right inside the write SQL. With JPA/Hibernate, `@Version` usually manages optimistic locking for entity updates via the ORM mechanism; **bulk JPQL updates** must be evaluated separately because they do not automatically apply all entity-level mechanisms.

The count also helps detect missing unique constraints: if an action is designed for a single entity yet count is `2`, do not treat “at least one record updated” as success. Roll back, fix `WHERE`, and consider a schema unique constraint/index.

## 7. Batch update: do not blindly sum counts

Spring JDBC supports `JdbcTemplate.batchUpdate(...)`. With overloads accepting `List<Object[]>`, it returns an `int[]` containing the count per statement in the batch. Overloads that split batches by `batchSize` can return `int[][]`. The results are determined by the JDBC driver:

- A number `>= 0`: known count, where `0` means no rows were affected.
- `Statement.SUCCESS_NO_INFO` (`-2`): the statement succeeded, but the row count is **unknown**.
- `Statement.EXECUTE_FAILED` (`-3`): failure marker in the update counts array when the driver continues after an error; batch errors can also cause JDBC to throw `BatchUpdateException`, which Spring translates into a data access exception.

The following snippet illustrates this inside a service that already has `jdbc` (not a standalone program):

```java
import java.sql.Statement;
import java.util.ArrayList;
import java.util.List;

List<Object[]> params = new ArrayList<>();
params.add(new Object[] {"DONE", 11L, "PENDING"});
params.add(new Object[] {"DONE", 12L, "PENDING"});

int[] counts = jdbc.batchUpdate(
    "UPDATE jobs SET state = ? WHERE id = ? AND state = ?",
    params
);

for (int i = 0; i < counts.length; i++) {
    int count = counts[i];
    if (count == Statement.SUCCESS_NO_INFO) {
        throw new IllegalStateException(
            "Cannot prove expected count for batch item " + i
        );
    }
    if (count == Statement.EXECUTE_FAILED || count != 1) {
        throw new IllegalStateException(
            "Unexpected affected rows at batch item " + i + ": " + count
        );
    }
}
```

If the business logic requires **exactly one row per item**, `-2` is **insufficient evidence**, even though the driver reported execution success. You can choose individual `update` calls, a verification query by key, or a DB mechanism that returns exact counts. Do not sum `-2` as a negative number to compute a “total updated rows”, and do not treat `counts.length` as the number of succeeded rows. Wrap both the batch and count checks in a transaction if all-or-nothing is required; driver behavior for elements after a failure varies, so roll back the whole transaction when the invariant fails.

## 8. Spring Data JPA: retrieving counts from bulk updates

In a Spring Data JPA repository, you can return `int` from a `@Modifying @Query` method. Example **for integration** into an application that already has entity `Booking`, enum `BookingState`, and `JpaRepository`:

```java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Modifying;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

public interface BookingRepository extends JpaRepository<Booking, Long> {
    @Modifying
    @Query("""
           update Booking b
              set b.state = :next
            where b.id = :id
              and b.state = :expected
           """)
    int moveState(
        @Param("id") Long id,
        @Param("expected") BookingState expected,
        @Param("next") BookingState next
    );
}
```

The service calls `moveState` inside a transaction and checks `rows == 1` just as with JDBC. Important differences to know:

- **Declared query methods** in Spring Data JPA do not automatically carry the same default transaction configuration as inherited CRUD methods; place `@Transactional` on the service wrapping the operation (or on the query method as appropriate).
- Bulk JPQL update/delete goes directly to the DB and is not equivalent to calling `save(entity)` through each entity's lifecycle. It can bypass lifecycle callbacks, entity-level dirty checking, and automatic `@Version` handling. If optimistic locking conditions are needed, explicitly write `WHERE version = :expectedVersion` and update version according to application policy.
- The persistence context may still hold stale entities after a bulk update. `@Modifying(flushAutomatically = true, clearAutomatically = true)` can be used when flushing beforehand and clearing afterward are needed, but **clearing detaches managed entities**; account for unflushed changes and objects that code continues to use.
- `save(...)` returns the entity, not a row count; ORM-generated SQL may be flushed later. Do not infer written row counts from the return value of `save`.

## 9. Transactions and business error handling

The safe rule is **write → read count → check invariant → decide commit/rollback within the same transaction**.

- `rows == expected`: proceed with remaining steps and commit; commit can still fail due to constraints, deadlocks, connection loss, or DB failure.
- `rows == 0` unacceptable under the contract: throw an appropriate business exception (usually unchecked) to roll back; then map it to an API/domain error at the appropriate boundary.
- `rows > expected`: roll back and emit a structured log including the operation code, safe ID/tenant criteria, `expected`, and `actual`. Avoid logging full SQL alongside sensitive data.
- For checked exceptions, configure `rollbackFor` if default rollback rules do not apply; verify the Spring configuration in use.
- External systems outside the DB (sending emails, messages, HTTP) do not automatically roll back with a DB transaction. To ensure invalid events are not emitted when the count fails, consider transactional outbox or after-commit hooks as appropriate.

**Do not do:**

```java
// Wrong when business logic requires exactly one row:
jdbc.update("UPDATE orders SET status = ? WHERE id = ?", "PAID", orderId);
return true; // Ignores the count.

// Wrong because both 0 and greater than 1 can be abnormal:
return jdbc.update(sql, args) > 0;

// Wrong if check-then-act is performed non-atomically:
if (jdbc.queryForObject(checkSql, Integer.class, id) == 1) {
    jdbc.update(updateWithoutConditionSql, id);
}
```

The right approach is to put the guarding conditions into `UPDATE ... WHERE ...`, read the count, and check the exact row count required by the use case.

## 10. Testing edge cases

Write integration tests against **the same DBMS/driver used in production**, especially for count semantics and concurrent updates:

| Case | Outcome to verify |
| --- | --- |
| Exactly one matching row | Count `1`, data updated properly, transaction commits |
| Non-existent ID | Count `0`, correct business branch |
| ID exists but invalid state | Count `0`, no invalid state written |
| Two requests send the same old version | One request can get count `1`, the other must detect count `0` after version changes (depending on scheduling) |
| Overly broad `WHERE`, two matching rows | Count `2` detected; entire transaction rolls back |
| Business logic allows idempotent retries | `0` interpreted per contract, not falsely returning success without verifying final state |
| Batch has `0` or `-2` element | Does not report all items succeeded; handled per defined policy |
| `UPDATE` assigns the same old value | Measure actual count with the current DB/driver; do not assume uniformity |
| Exception occurs after an update with valid count | Ensure all writes in the transaction roll back when policy requires |

Code review checklist: Does `WHERE` include sufficient keys and status/version/tenant conditions? Is the expected count `== 1`, `0..1`, or `0..N`? How many causes can “0” have? Does the count check occur before commit? Is the transaction actually active? Can a batch return indeterminate counts? Are concurrency and idempotency tests covered?

## 11. Takeaways and references

**Practical recipe:** derive invariants from business requirements → write `UPDATE`/`DELETE` with `WHERE` protecting the invariants → read the row count reported by JDBC/JPA → check against the contract → commit or roll back and interpret the result appropriately. The count is an essential signal for detecting conflicts and overly broad updates, but it must be combined with schema constraints, transactions, and concurrent access tests.

Official documentation:
- Spring Framework, JDBC Batch Operations: https://docs.spring.io/spring-framework/reference/data-access/jdbc/advanced.html
- Spring Framework, `@Transactional` settings and rollback: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Data JPA, modifying queries: https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html
- Spring Data JPA, transactionality: https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html
- JDBC `Statement` update counts: https://docs.oracle.com/en/java/javase/17/docs/api/java.sql/java/sql/Statement.html
