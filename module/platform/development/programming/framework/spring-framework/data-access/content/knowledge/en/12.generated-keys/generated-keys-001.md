# INSERT, UPDATE, and DELETE with JdbcTemplate.update()

In Spring Framework Data Access, the `JdbcTemplate.update()` method is the commonly used API for executing **data-modifying** statements: `INSERT` (insert), `UPDATE` (update), and `DELETE` (delete). The most important commonality: this method **returns the number of affected rows** as an `int` — it does **not** return an entity object, a `ResultSet`, or a database-generated ID.

Example of the same repository using `JdbcTemplate`:

```java
// Insert a product with an application-provided ID.
int inserted = jdbc.update(
    "INSERT INTO products(id, name, stock) VALUES (?, ?, ?)",
    10L, "Pen", 5
);

// Update an existing product.
int updated = jdbc.update(
    "UPDATE products SET stock = ? WHERE id = ?",
    7, 10L
);

// Delete a product by primary key.
int deleted = jdbc.update(
    "DELETE FROM products WHERE id = ?",
    10L
);
```

The statements above are a **snippet inside a method that has a `jdbc` variable** and a `products` table with matching columns; not a standalone Java program. When there is exactly one record with `id=10` and no constraint errors, each call typically returns `1`. If `UPDATE` or `DELETE` finds no record matching `WHERE`, the result is usually `0`.

This lesson explains how to properly use all three statement types, parameterization, checking affected row counts, transactions, concurrent update conflicts, error handling, and how to separate **primary key generation** to an overload with `KeyHolder` when needed.

## 1. Mental model: update() executes changes, not data queries

`JdbcTemplate` is a Spring JDBC helper class that takes a configured `DataSource`. When executing `update()`, Spring obtains a `Connection` appropriate for the current transaction (if any), prepares the statement, binds parameters, calls JDBC `executeUpdate()`, translates SQL errors to `DataAccessException`, and cleans up resources within the proper scope.

```text
Service / Repository
        |
        | jdbc.update(sql, args...)
        v
     JdbcTemplate
        |
        +---- DataSourceUtils obtains Connection from transaction context
        |
        +---- Creates PreparedStatement with ?-parameterized SQL
        |
        +---- Binds parameters (setString/setLong/setObject/...)
        |
        +---- PreparedStatement.executeUpdate()
        |
        +---- Returns affected row count (int)
        |
        +---- Cleans up Statement and releases Connection via Spring mechanism
        v
Database: INSERT / UPDATE / DELETE
```

Key things to remember:

- `update()` does **not** mean executing only SQL `UPDATE`. The method name is JDBC terminology for DML operations, including `INSERT` and `DELETE`.
- Use `query()`/`queryForObject()`/`queryForList()` when you want to retrieve data as a `ResultSet`; do not use `update()` in place of `SELECT`.
- The returned `int` is the row count **reported by the JDBC driver** for the statement; it is not a generated ID or the number of committed transactions.
- A successful `update()` call only means the statement ran without throwing an error; the business operation may still **fail** if exactly one row was expected but the result is `0`.

### 1.1. Common overloads

| `JdbcTemplate` API | Purpose | Notes |
| --- | --- | --- |
| `update(String sql, Object... args)` | DML with `?` and value list | Simple, common choice. |
| `update(String sql, Object[] args, int[] argTypes)` | DML with explicit SQL types | Useful for `NULL`/type-sensitive drivers. |
| `update(String sql, PreparedStatementSetter pss)` | Manually bind parameters onto `PreparedStatement` | Flexible for specialized types. |
| `update(PreparedStatementCreator psc)` | Manually create `PreparedStatement` | Used when statement customization is needed. |
| `update(PreparedStatementCreator psc, KeyHolder keyHolder)` | DML while retrieving driver-returned generated keys | Must enable generated-keys request when creating the statement. |
| `update(String sql)` | Run parameterless SQL via `Statement` | Should only be used with **static, trusted** SQL. |

All overloads in the table above (when DML executes successfully) return `int`. When an error occurs, Spring throws an exception from the `DataAccessException` hierarchy; it does not return arbitrary negative error codes to indicate every failure case.

Do not confuse with `batchUpdate()`: the batch method returns `int[]` for multiple statements/batches and has its own JDBC reporting semantics.

## 2. SQL syntax and parameter binding

### INSERT: create a new record

Example `products` table:

```sql
CREATE TABLE products (
    id BIGINT PRIMARY KEY,
    name VARCHAR(100) NOT NULL,
    stock INT NOT NULL CHECK (stock >= 0),
    version INT NOT NULL DEFAULT 0
);
```

Insert operation:

```java
int rows = jdbc.update(
    "INSERT INTO products(id, name, stock) VALUES (?, ?, ?)",
    id, name, initialStock
);
```

Three `?` placeholders are needed for the three parameters. `JdbcTemplate` uses `PreparedStatement` for binding, avoiding concatenating raw input into SQL. When `id` duplicates the primary key, `name` is `NULL` despite the `NOT NULL` column, or `stock < 0` violates `CHECK`, the DB rejects the statement; Spring typically throws a specific `DataAccessException` instead of returning `0`.

**Do not assume INSERT always returns 1 for every SQL statement:** `INSERT ... SELECT` or a multi-row DML statement can return a different count. With the single-row `VALUES (...)` example, expecting `1` is reasonable.

### UPDATE: modify records matching WHERE

```java
int rows = jdbc.update(
    "UPDATE products SET name = ?, stock = ? WHERE id = ?",
    newName, newStock, id
);
```

The binding order is `newName`, `newStock`, `id`, matching the order in which each `?` placeholder appears in the SQL. You should make the `WHERE` condition sufficiently specific (usually by primary key and tenant, or version condition) to avoid accidentally updating multiple records.

`UPDATE` finding no matching record usually returns `0` — it does not necessarily throw an exception. If more than one record matches `WHERE`, it can return greater than `1`. Placing `WHERE id = ?` on a primary key with a uniqueness constraint lets you expect at most one record.

### DELETE: remove records matching WHERE

```java
int rows = jdbc.update(
    "DELETE FROM products WHERE id = ?",
    id
);
```

`DELETE` removes data physically (hard delete) unless the database applies triggers/other rules. If no matching record remains, it typically returns `0`. Clarify whether the business logic treats deleting a non-existent record as **idempotent success**, `404 Not Found`, or a concurrency error; do not treat `0` and `1` as equivalent in every use case.

### 2.1. Quick reference table

| Statement | Example | Typical row count | Decision needed |
| --- | --- | --- | --- |
| Single-row `INSERT ... VALUES` | `INSERT ... VALUES (?, ?)` | `1` | Is duplicate ID allowed on insert? |
| `UPDATE ... WHERE id = ?` | `UPDATE ... SET name=? WHERE id=?` | `0` or `1` | How to handle non-existent / stale version? |
| `DELETE ... WHERE id = ?` | `DELETE FROM ... WHERE id=?` | `0` or `1` | Is repeated deletion valid? |
| `UPDATE ... WHERE status = ?` | `UPDATE ... SET status=? WHERE status=?` | `0..N` | Is bulk update truly intended? |
| `DELETE ... WHERE created_at < ?` | `DELETE FROM ... WHERE ...` | `0..N` | Are audit, batching, or time limits needed? |

**Warning:** `UPDATE products SET stock = 0` or `DELETE FROM products` **without `WHERE`** affects all rows in the table according to that statement. They may be valid in controlled migrations, but must undergo special review and are generally inappropriate for single-entity APIs.

## 3. Interpreting the affected row count accurately

Example:

```java
int affected = jdbc.update(
    "UPDATE products SET name = ? WHERE id = ?",
    "Notebook", 10L
);

if (affected == 0) {
    // No matching row, or a guard condition did not match.
}
if (affected == 1) {
    // With a primary key constraint, one row was processed by the statement.
}
if (affected > 1) {
    // Abnormal if the task only expects to update a single entity.
}
```

For each specific statement, define the **postcondition**:

- Inserting a single new row: typically expect `affected == 1`.
- Updating/deleting by unique key: `affected == 1` means one row satisfied the condition and the driver reported an update; `0` may mean not found or a guard condition did not match.
- Bulk updates: `affected >= 0` is normal, but you must know the expected impact scale.
- Never use `affected` as a generated ID value. For example, `affected=1` does **not** mean the new record was generated with `id=1`.

### 3.1. A nuance: “matched rows” vs. “changed rows”

For an `UPDATE` that sets the exact same old value again, the reported row count may depend on the **DBMS/driver/driver configuration**: some environments report matched rows, while others report rows actually changed. Therefore, do not assume absolutely that:

> `affected == 0` always proves the record does not exist.

With `WHERE id = ? AND version = ?` and a statement that actually increments `version`, `0` is more useful for detecting conflicts because every matched row will be modified. If the business logic needs to distinguish “not found” from “stale version”, you can re-check with an appropriate query or use domain optimistic locking; avoid relying solely on the “changed rows” semantics of an unverified driver.

### 3.2. Do not treat affected row count as cascade row count

When deleting a parent with `ON DELETE CASCADE` or when triggers modify child tables, `update()` typically reflects the update count reported by JDBC for the **invoked statement**, not a comprehensive measurement of all side effects across all tables. If you need to audit child row deletions, design an audit mechanism or appropriate queries rather than inferring from a single `int`.

### 3.3. Check the count and promote to a business error

If a use case expects exactly one record, turn the outcome into an explicit condition:

```java
import org.springframework.dao.DataAccessException;

public void renameRequired(long id, String title) {
    int changed = jdbc.update(
        "UPDATE products SET name = ? WHERE id = ?",
        title, id
    );
    if (changed != 1) {
        throw new IllegalStateException(
            "Expected exactly one product to be updated");
    }
}
```

This is a **method snippet** inside a repository/service that already has `JdbcTemplate jdbc`; `DataAccessException` does not need to be imported if the method does not use that type name in its signature. For HTTP APIs, classify the situation as 404/409 or an appropriate domain exception rather than automatically returning 500 for every `0` case.

## 4. Repository code using all three operations

The class below is a Spring component (Java 17+). It only holds `JdbcTemplate`, not a `Connection` in a field:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public final class ProductRepository {
    private final JdbcTemplate jdbc;

    public ProductRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int insert(long id, String name, int stock) {
        return jdbc.update(
            "INSERT INTO products(id, name, stock) VALUES (?, ?, ?)",
            id, name, stock
        );
    }

    public int rename(long id, String name) {
        return jdbc.update(
            "UPDATE products SET name = ? WHERE id = ?",
            name, id
        );
    }

    public int changeStockIfVersion(
            long id, int newStock, int expectedVersion) {
        return jdbc.update(
            """
            UPDATE products
               SET stock = ?, version = version + 1
             WHERE id = ? AND version = ?
            """,
            newStock, id, expectedVersion
        );
    }

    public int delete(long id) {
        return jdbc.update(
            "DELETE FROM products WHERE id = ?",
            id
        );
    }
}
```

**Explanation:**

- `@Repository` can be a singleton because the `JdbcTemplate` dependency is thread-safe after configuration; each call executes a statement with its own parameters.
- `JdbcTemplate.update` manages acquiring/releasing resources via Spring's built-in transaction mechanism.
- The `name`, `id`, and `stock` values are bound, not interpolated into SQL text.
- `changeStockIfVersion` atomically updates `version` together with `stock` when the expected version still matches. A result of `0` may mean a non-existent id or a stale version.
- The methods return `int` so the service layer **decides** the postcondition; it does not hide `0` as if the operation definitely succeeded.

Validate `stock >= 0`, non-blank name/valid length, and access permissions before calling. Database `CHECK`/`NOT NULL`/`PRIMARY KEY` constraints remain the final safeguard; application validation does not replace constraints.

## 5. Runnable Spring Boot + H2 project with deterministic output

This is an end-to-end example running on Java 17+ using Spring Boot 3.3.x, `spring-boot-starter-jdbc`, and H2. It demonstrates:

1. Successful `INSERT` returns 1.
2. `UPDATE` for an existing ID returns 1.
3. `UPDATE` for a non-existent ID returns 0.
4. `UPDATE` with a still-valid `version` condition returns 1 and increments version.
5. `UPDATE` with a stale expected version returns 0.
6. First `DELETE` returns 1; the second returns 0.
7. The table has no remaining records after deletion.

### 5.1. Gradle configuration

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
```

File `src/main/resources/application.properties`:

```properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:jdbc_update_demo;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
```

`DB_CLOSE_DELAY=-1` keeps the H2 in-memory database alive for the lifetime of the JVM even if there are periods when all connections close. This is a demo configuration, not a mandatory production setting.

### 5.2. Complete Java application

File `src/main/java/example/UpdateDemoApplication.java`:

```java
package example;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@SpringBootApplication
public class UpdateDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(UpdateDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, BookRepository repo) {
        return args -> {
            jdbc.execute("""
                CREATE TABLE books (
                    id BIGINT PRIMARY KEY,
                    title VARCHAR(120) NOT NULL,
                    stock INT NOT NULL CHECK (stock >= 0),
                    version INT NOT NULL DEFAULT 0
                )
                """);

            int inserted = repo.insert(10L, "Java", 5);
            int renamed = repo.rename(10L, "Spring JDBC");
            int missing = repo.rename(99L, "Not there");
            int changed = repo.updateStockIfVersion(10L, 4, 0);
            int stale = repo.updateStockIfVersion(10L, 8, 0);

            Integer version = jdbc.queryForObject(
                "SELECT version FROM books WHERE id = ?",
                Integer.class, 10L
            );

            int removed = repo.deleteById(10L);
            int removedAgain = repo.deleteById(10L);

            Integer remaining = jdbc.queryForObject(
                "SELECT COUNT(*) FROM books", Integer.class
            );

            System.out.println("inserted=" + inserted);
            System.out.println("renamed=" + renamed);
            System.out.println("missing=" + missing);
            System.out.println("stockChanged=" + changed);
            System.out.println("staleVersion=" + stale);
            System.out.println("version=" + version);
            System.out.println("removed=" + removed);
            System.out.println("removedAgain=" + removedAgain);
            System.out.println("remaining=" + remaining);
        };
    }
}

@Repository
class BookRepository {
    private final JdbcTemplate jdbc;

    BookRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    int insert(long id, String title, int stock) {
        return jdbc.update(
            "INSERT INTO books(id, title, stock) VALUES (?, ?, ?)",
            id, title, stock
        );
    }

    int rename(long id, String title) {
        return jdbc.update(
            "UPDATE books SET title = ? WHERE id = ?",
            title, id
        );
    }

    int updateStockIfVersion(
            long id, int stock, int expectedVersion) {
        return jdbc.update(
            """
            UPDATE books
               SET stock = ?, version = version + 1
             WHERE id = ? AND version = ?
            """,
            stock, id, expectedVersion
        );
    }

    int deleteById(long id) {
        return jdbc.update(
            "DELETE FROM books WHERE id = ?",
            id
        );
    }
}
```

`UpdateDemoApplication.java` contains one public class and one package-private class in the same package `example`; Java allows this structure. With the proper dependencies, the program can boot the Spring context, create the table, and invoke the repository.

### 5.3. Running and stdout

From the project directory with Gradle wrapper:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

The lines produced by **`System.out` of the program** in the H2 environment above:

```text
inserted=1
renamed=1
missing=0
stockChanged=1
staleVersion=0
version=1
removed=1
removedAgain=0
remaining=0
```

Spring Boot/Hikari may print additional logs. The output is deterministic because each operation runs sequentially inside a `CommandLineRunner` on a freshly created table. `version` starts at `0` due to the database default; the successful update increments it to `1`. The second call with `expectedVersion=0` no longer matches and returns `0`. The two delete statements illustrate the difference between an existing record and an already deleted one.

**Important:** The example uses a **code-assigned ID** (`10L`), not a database-generated ID. Returning `inserted=1` is the **row count**, not `id=1`.

## 6. What to do when update() returns 0 or more than 1?

Avoid code like this:

```java
jdbc.update("UPDATE orders SET status = ? WHERE id = ?", status, id);
// Does not check the result, yet still returns HTTP 200 as if the update succeeded.
```

If a client updates a non-existent order or updates a stale version, the result can be `0` with no exception thrown. A better approach is to define the business contract.

| Use case | `affected=0` | `affected=1` | `affected>1` |
| --- | --- | --- | --- |
| Rename entity by primary key | Not found or conflict (must distinguish). | Success according to driver. | Abnormal; review WHERE/constraint. |
| Delete entity by primary key | Can be treated as idempotent success, or 404, depending on API. | Deleted one row. | Abnormal if ID is unique. |
| Conditional state transition | State did not match; need to report conflict. | State transition was processed. | Only valid if multi-row by design. |
| Time-based batch cleanup | No rows needed cleanup; usually normal. | One row affected. | May be valid; needs metrics/audit. |

Example of an atomic state transition:

```java
int claimed = jdbc.update(
    """
    UPDATE jobs
       SET status = 'RUNNING'
     WHERE id = ? AND status = 'READY'
    """,
    jobId
);
if (claimed != 1) {
    // Job is no longer READY or does not exist; do not process a second time.
}
```

This is a **snippet inside a method that has `jdbc` and `jobId`**; the `jobs` table/statuses are prerequisites. Including the old status in `WHERE` is a form of compare-and-set at the database level, avoiding reading state and then blindly updating. Distinguish job claiming ownership and retry semantics when multiple workers compete.

## 7. Safe UPDATE under concurrent requests

### 7.1. Lost update in unprotected read–modify–write

Imagine two requests both read `stock=5`, each wants to sell one item, and both compute `newStock=4` on the client. If both execute in turn:

```sql
UPDATE products SET stock = 4 WHERE id = 10;
```

Both requests can return `1`, yet the final stock remains `4` instead of `3`. **A row count of 1 does not prove the absence of a logic race**.

### 7.2. Arithmetic updates in SQL with conditions

Instead of computing the new stock count in Java from an old snapshot:

```java
int affected = jdbc.update(
    """
    UPDATE products
       SET stock = stock - ?
     WHERE id = ? AND stock >= ?
    """,
    quantity, productId, quantity
);
```

With `quantity > 0` and a DBMS supporting standard atomic update/locking, each statement subtracts directly from the current value under the condition `stock >= quantity`. If stock is insufficient, `affected=0`. This is generally better than the uncontrolled `SELECT stock` → compute in Java → `UPDATE stock = ?` pattern.

You still need to handle isolation, lock contention, transaction retries, and other business invariants. When concurrency is high or multiple tables are involved, a single statement does not solve the entire transaction workflow.

### 7.3. Optimistic locking with a version column

The following statement updates only when the version in the DB still matches the version read by the application:

```sql
UPDATE products
SET name = ?, version = version + 1
WHERE id = ? AND version = ?;
```

If two requests both read `version=0`, the winning request increments it to `1`, and the other receives `affected=0` and must handle the conflict. Do not blindly retry infinitely with the same stale data; some use cases require re-reading, merging, or asking the user to confirm.

Spring Data/JPA has its own `@Version` mechanism; in `JdbcTemplate`, **you write** the version condition and check the count yourself. Do not assume JPA annotations automatically apply to hand-written `jdbc.update` calls.

## 8. Multiple statements: use transactions instead of expecting update() to wrap them

Each `update()` executes one statement. When no Spring transaction is active and the connection is in auto-commit mode, each successful statement is typically committed individually. If the business logic needs **both changes to succeed together or roll back together**, use a transaction.

Example transferring inventory between two warehouses:

```java
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public final class StockTransferService {
    private final JdbcTemplate jdbc;

    public StockTransferService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(long fromWarehouseId,
                         long toWarehouseId,
                         long productId,
                         int quantity) {
        if (quantity <= 0 || fromWarehouseId == toWarehouseId) {
            throw new IllegalArgumentException("Invalid transfer");
        }

        int debited = jdbc.update(
            """
            UPDATE inventory
               SET quantity = quantity - ?
             WHERE warehouse_id = ?
               AND product_id = ?
               AND quantity >= ?
            """,
            quantity, fromWarehouseId, productId, quantity
        );
        if (debited != 1) {
            throw new IllegalStateException(
                "Source inventory unavailable");
        }

        int credited = jdbc.update(
            """
            UPDATE inventory
               SET quantity = quantity + ?
             WHERE warehouse_id = ? AND product_id = ?
            """,
            quantity, toWarehouseId, productId
        );
        if (credited != 1) {
            throw new IllegalStateException(
                "Destination inventory missing");
        }
    }
}
```

This is a valid Spring class, but it requires an `inventory` table with a unique key on `(warehouse_id, product_id)`, a transaction manager, and `JdbcTemplate` sharing the same `DataSource`. Call the service **through a Spring proxy** so `@Transactional` is applied in proxy mode (self-invocation on the same bean normally does not trigger interception). When the second statement fails to update a row, `IllegalStateException` exits the method, causing Spring by default to roll back the transaction for unchecked exceptions.

Key points:

- `JdbcTemplate` works with `DataSourceUtils` to use the connection bound to the transaction.
- `update()` itself **does not create** a transaction spanning multiple calls in Java.
- A transaction needs clear boundaries; do not make HTTP API calls or slow non-DB processing while holding locks/connections.
- For checked exceptions, Spring's default rollback rules differ from unchecked ones; use `rollbackFor`/appropriate rules if the business logic requires it.
- If code catches an exception and **swallows the error and returns normally**, the transaction manager may commit the already succeeded changes; you must decide explicitly to rethrow/roll back.
- Never store a `Connection` in a singleton field or pass it to another thread to “keep the transaction”.

### 8.1. Do not confuse transaction timeout with the returned row count

`update()` returns the row count reported by the driver, not the global commit status. Timeout/connection errors can occur during statement execution or at commit time. For operations that may be retried (especially when the connection drops after sending SQL), evaluate **idempotency** and transaction outcomes; do not claim that any exception guarantees the database did not apply the change.

## 9. Generated keys: update() returns row count, KeyHolder retrieves the ID

Since this chapter covers “generated keys”, two needs must be distinguished:

1. **Verifying successful insertion:** use `int affected = jdbc.update(...)`.
2. **Retrieving a database-generated primary key** (`IDENTITY`, auto-increment, etc.): use an overload supporting `KeyHolder`, or an equivalent approach suited to the DB/driver.

Suppose a table has a column `id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY`. In a Spring repository with `JdbcTemplate jdbc`:

```java
import java.sql.PreparedStatement;
import java.sql.Statement;

import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.jdbc.support.KeyHolder;

public long insertAndGetId(String name) {
    KeyHolder holder = new GeneratedKeyHolder();

    int rows = jdbc.update(
        connection -> {
            PreparedStatement ps = connection.prepareStatement(
                "INSERT INTO customers(name) VALUES (?)",
                new String[] {"id"}
            );
            ps.setString(1, name);
            return ps;
        },
        holder
    );

    if (rows != 1) {
        throw new IllegalStateException(
            "Expected one inserted customer");
    }

    Number generated = holder.getKey();
    if (generated == null) {
        throw new IllegalStateException(
            "Driver did not return a generated ID");
    }
    return generated.longValue();
}
```

**Snippet scope:** Method body inside a repository that already has `JdbcTemplate jdbc` and table `customers(id identity, name)`; importing `Statement` here is unnecessary for the method because a column-name array is used. If you want to use `Statement.RETURN_GENERATED_KEYS`, you can replace the second parameter of `prepareStatement` with this constant. The driver must support generated keys. `KeyHolder.getKey()` is appropriate when the driver returns a **single numeric key**; if multiple columns/keys are returned, inspect `getKeys()` or `getKeyList()` depending on the problem.

**Do not confuse:** With a single-row `INSERT` that generates ID 745, `update()` can still return `1`; ID 745 comes from generated keys, **not from the row count**. DBMSs also offer `RETURNING`/`OUTPUT` options with different semantics; if a statement returns a result set, use the appropriate API rather than assuming `update()` will return those rows.

## 10. SQL types, NULL, and binding

Varargs `update(sql, Object... args)` is usually sufficient for common types (`String`, `long`, `int`, `BigDecimal`, `Timestamp`). However, `NULL` or specialized DB types sometimes require specifying the JDBC type explicitly so the driver does not misinfer it.

Example when updating a nullable `VARCHAR` column `notes`:

```java
import java.sql.Types;

int rows = jdbc.update(
    "UPDATE products SET notes = ? WHERE id = ?",
    new Object[] { null, productId },
    new int[] { Types.VARCHAR, Types.BIGINT }
);
```

This is a snippet placed inside a method that already has `JdbcTemplate jdbc` and variable `productId`. The `args` and `argTypes` arrays must have the same order and length. Another option is using `SqlParameterValue` to attach `Types.VARCHAR` to a specific parameter.

**Note on SQL NULL:** `WHERE field = NULL` is never a valid comparison under three-valued SQL logic; use `IS NULL` or an explicit nullable condition. If conditions vary with null inputs, design the SQL intentionally rather than concatenating text from untrusted input.

Also be careful with date/time types, `BigDecimal` for money, DBMS-specific JSON/array/enum types, and how the JDBC driver maps them. **Safe binding** and **choosing the right data type** are two separate responsibilities.

## 11. Do not use dynamic raw SQL to substitute table/column names

`?` placeholders only represent **data values**, not table names, column names, or keywords. Do not do this:

```java
// WRONG: data from HTTP can control the SQL structure.
String sql = "DELETE FROM " + requestTable + " WHERE id = ?";
jdbc.update(sql, id);
```

Similarly, `ORDER BY ?` with a bound column-name string does not substitute an identifier as intended. If the business logic allows choosing among a few tables or columns, map the choice through an enum/allow-list **fixed in source code**, and then construct the SQL; all values in `WHERE` continue to use `?`.

### 11.1. Multi-tenancy and update authorization

In multi-tenant systems, **the table's primary key alone is insufficient for access control**. SQL typically needs a tenant/owner condition obtained from a trusted authentication context:

```java
int affected = jdbc.update(
    """
    UPDATE documents
       SET title = ?
     WHERE id = ? AND tenant_id = ?
    """,
    newTitle, documentId, authenticatedTenantId
);
```

`authenticatedTenantId` should not simply be a URL value self-reported by the client. `affected=0` here can mean the record does not exist, does not belong to the tenant, or does not satisfy another condition; avoid leaking the existence of another tenant's record through detailed errors.

## 12. Hard DELETE or soft delete?

**Hard delete:**

```java
int affected = jdbc.update(
    "DELETE FROM products WHERE id = ?",
    id
);
```

The row is removed from the table (barring special DB mechanisms), and foreign keys may block it or trigger cascades. If business requirements demand auditing, order history, or recovery, hard delete may be unsuitable.

**Soft delete:**

```java
int affected = jdbc.update(
    """
    UPDATE products
       SET deleted = TRUE
     WHERE id = ? AND deleted = FALSE
    """,
    id
);
```

This is an `UPDATE`, not a `DELETE`, and requires a `deleted` column in the schema. A result of `0` may mean it does not exist **or was already soft-deleted**. All read queries must consistently filter or handle `deleted=FALSE`; add appropriate unique rules/indexes if needed to avoid name conflicts with hidden records.

Do not treat soft delete as unconditionally safer: it introduces responsibilities around query enforcement, retention lifecycles, privacy, and eventual hard-deletion rules.

## 13. batchUpdate() and bulk operations: choose the right API

If you need to update 10,000 records with the same structure, calling `jdbc.update(...)` 10,000 times in a loop can incur many round trips. `batchUpdate()` is the optimal choice when the driver supports batching; it **does not share the same return type** as `update()`.

Example:

```java
import java.util.List;

import org.springframework.jdbc.core.JdbcTemplate;

public int[] markProcessed(List<Long> ids, JdbcTemplate jdbc) {
    return jdbc.batchUpdate(
        "UPDATE jobs SET processed = TRUE WHERE id = ?",
        ids,
        200,
        (ps, id) -> ps.setLong(1, id)
    ).stream()
     .flatMapToInt(java.util.Arrays::stream)
     .toArray();
}
```

The snippet above is a **method in a class**, using the `batchUpdate(String, Collection<T>, int, ParameterizedPreparedStatementSetter<T>)` overload returning `int[][]`, flattened to easily observe the row counts from each batch. Depending on the JDBC driver, values may include `Statement.SUCCESS_NO_INFO` (`-2`), not always exact non-negative numbers. Do not enforce an invariant that “every result must equal 1” in batches when drivers are permitted to return special codes; read the JDBC contract carefully.

**Lesson focus:** When executing a single `INSERT`/`UPDATE`/`DELETE`, use `update()` and check the `int`. When running many statements of the same kind, consider `batchUpdate()`, transactions, batch size limits, and driver support.

## 14. Error handling: exceptions differ from 0 rows

`JdbcTemplate` translates JDBC `SQLException` into exceptions in the `org.springframework.dao.DataAccessException` hierarchy (unchecked). Some scenarios:

| Scenario | Possible outcome |
| --- | --- |
| `UPDATE ... WHERE id=?` matches no rows | `affected=0`, not always an exception. |
| `DELETE` by an already deleted id | `affected=0` if no match remains. |
| `INSERT` duplicate primary key | `DataIntegrityViolationException`/`DuplicateKeyException` depending on translator/DB. |
| `INSERT` violates `NOT NULL` or `CHECK` | A `DataAccessException` related to data integrity constraints. |
| SQL syntax error/non-existent table | A `DataAccessException` (possibly `BadSqlGrammarException`). |
| DB/network/timeout error | An appropriate `DataAccessException`, depending on driver and translator. |
| Transaction commit failure | Can raise an exception outside the `update()` call site. |

Do not do:

```java
try {
    jdbc.update(sql, args);
} catch (Exception ex) {
    return 0; // WRONG: equates a broken DB/constraint violation with no matching record
}
```

If you genuinely need to convert exceptions into business errors, classify by root cause, log just enough information (without exposing credentials/sensitive data), and preserve rollback/retry semantics. With `@Transactional`, avoid catching and swallowing unchecked exceptions because the transaction might commit statements that already succeeded.

### 14.1. About retries

Retrying after a deadlock or transient connection failure can be reasonable **when controlled**. However, blindly retrying `INSERT` after a network timeout is dangerous: the DB may have succeeded in inserting even though the client never received the response. Build idempotency keys/unique constraints, transaction boundaries, and outcome checks before deciding to retry.

## 15. Performance and observability

`JdbcTemplate.update()` only reduces JDBC boilerplate; it does not make every SQL statement fast. For data-modifying operations, key operational concerns include:

- **Indexes on WHERE conditions:** `UPDATE/DELETE WHERE id=?` typically benefits from the primary-key index. Unindexed conditions can scan many rows.
- **Lock duration:** Long transactions hold row locks longer, increasing wait times and deadlocks.
- **Affected row count:** Logs/metrics help detect anomalous operations, while avoiding exposing sensitive IDs/context.
- **Transaction boundaries:** Group interdependent statements into one transaction; do not keep a transaction open across slow network I/O.
- **Batching:** Use `batchUpdate` for large volumes of changes when beneficial; avoid an unbounded SQL update over millions of rows without a plan.
- **Connection pool:** Each request needs a properly scoped connection; never store a singleton `Connection`. Pool exhaustion can cause operations to wait before the JDBC statement even runs.
- **Query/statement timeout:** Consider transaction duration and DB lock timeouts; a timeout does not by itself guarantee safe rollback in every non-transactional situation.

A high-impact migration or cleanup requires backups, a maintenance window, a plan, auditing, and an appropriate dry run; do not rely solely on `affected` to verify data correctness afterward.

## 16. Common mistakes to avoid

| Mistake | Consequence | Fix |
| --- | --- | --- |
| Thinking `update()` only runs SQL UPDATE | Using the wrong API for INSERT/DELETE. | Remember it executes DML and returns row count. |
| Thinking returning `1` is the generated ID | Confusing row count with generated key. | Use `KeyHolder` when you actually need the ID. |
| Not checking `affected` | Failing to detect 0-row operations. | Define postconditions per business operation. |
| Omitting `WHERE` in UPDATE/DELETE | Can modify/delete the entire table. | Review SQL and key/tenant conditions. |
| Concatenating input into SQL strings | SQL injection and quoting bugs. | Bind data values via `?`; use allow-lists for structure. |
| Computing new value in Java then blindly updating | Lost updates under concurrency. | Atomic SQL/optimistic locking/transactions. |
| Catching DB exceptions and returning 0 | Hides infrastructure errors and can partially commit. | Distinguish exceptions from no-match; roll back explicitly. |
| Assuming multiple update() calls share a transaction automatically | May commit each statement individually. | Properly scoped `@Transactional`/`TransactionTemplate`. |
| Using `update()` to fetch a list of records | Method returns int, not RowMapper results. | Use query APIs for SELECT. |
| Using `DELETE` when history must be kept | Data loss or FK violations. | Consider soft delete, retention, and audit. |
| Confusing row count with cascade row count | Inaccurate auditing. | Track side effects separately. |
| Assuming the SQL type of `NULL` is always inferred | Driver may bind the wrong type. | Supply `Types`/`SqlParameterValue` when needed. |
| Using `batchUpdate()` and expecting a single `int` | Batch returns an array of counts and special codes. | Read the batch/JDBC contract properly. |

## 17. Self-check questions

**1.** Which SQL statements is `JdbcTemplate.update()` used for and what type does it return?

**Answer:** Primarily `INSERT`, `UPDATE`, `DELETE`, and equivalent DML; it returns an `int` representing the number of affected rows reported by JDBC.

**2.** Does a successful single-row `INSERT` returning `1` mean the generated primary key is 1?

**Answer:** No. `1` is the row count. Generated IDs must be retrieved via `KeyHolder` or an equivalent mechanism.

**3.** Does `UPDATE products SET name=? WHERE id=?` returning `0` always mean an exception?

**Answer:** No. It usually means no rows satisfied the condition (or matched/changed rows differences depending on the driver), and the caller must decide the business case.

**4.** If two requests read stock=5 and both write stock=4 with `UPDATE`, and each returns `1`, is the data definitely correct?

**Answer:** Not necessarily. A lost update may have occurred. Use an atomic SQL subtraction or a version condition and check the row count.

**5.** Why is `WHERE id=? AND version=?` together with `version=version+1` useful?

**Answer:** It turns the update into a version-based compare-and-set. A request with a stale version will not match and will typically receive `0` instead of overwriting someone else's change.

**6.** If two `update()` calls in a service must commit or roll back together, what should you do?

**Answer:** Configure an appropriate Spring transaction (`@Transactional` or `TransactionTemplate`), ensure the same DataSource and active proxy/transaction manager; throw an exception if postconditions are not met.

**7.** Is `DELETE FROM products WHERE id=?` returning `0` on a second deletion always an error?

**Answer:** No. Depending on the API contract, repeated deletion may be an idempotent success or must return not-found. The row count provides the signal to decide.

**8.** What problem does `update(sql, args, argTypes)` solve?

**Answer:** It allows specifying explicit SQL types when binding parameters, especially useful for `NULL` or types the driver struggles to infer.

**9.** When you need to retrieve a database-generated key, which overload is relevant?

**Answer:** `update(PreparedStatementCreator, KeyHolder)`, with a statement requesting generated keys; requires driver support.

## 18. Pre-production checklist

- [ ] Choose `update()` for a single DML operation; choose `query()` for row results, `batchUpdate()` for batches.
- [ ] All SQL parameters are bound with `?`; never concatenate raw input into SQL structure.
- [ ] `WHERE` guarantees proper keys, status/version conditions, and tenant authorization.
- [ ] For single-entity operations, clearly define how to handle `affected=0`, `1`, or abnormal values.
- [ ] Do not confuse `affected` with a DB-generated ID key; use `KeyHolder` when needed.
- [ ] Proper DB constraints exist (`PK`, `FK`, `NOT NULL`, `CHECK`, unique).
- [ ] Transactions wrap statements that must commit/roll back together.
- [ ] `@Transactional` methods are invoked through a proxy according to the configuration mode; never swallow errors causing partial commits.
- [ ] Under concurrency, verify atomic updates/optimistic locking and avoid lost updates.
- [ ] Clear decisions exist on hard delete, soft delete, cascades, and auditing.
- [ ] JDBC types for `NULL`, dates/times, and decimals are tested on the real driver.
- [ ] Tests cover successful/duplicate inserts, 0/1-row updates, repeated deletes, stale versions, and rollbacks.
- [ ] Logs/metrics, query plans, indexes, and timeouts are reviewed for large operations.

## 19. References

- [Spring Framework — JdbcTemplate Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html): `update`, `batchUpdate`, `KeyHolder` overloads, and return values.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate` usage patterns, binding, and error translation.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): transaction boundaries, `@Transactional`, and rollback rules.
- [Java SE — PreparedStatement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/PreparedStatement.html): `executeUpdate()` and parameter binding.
- [Java SE — Statement](https://docs.oracle.com/en/java/javase/21/docs/api/java.sql/java/sql/Statement.html): update counts, `SUCCESS_NO_INFO`, and generated keys.

**Remember:** `JdbcTemplate.update()` executes `INSERT`, `UPDATE`, and `DELETE`, and returns the **number of affected rows**. Bind parameters, check postconditions using the row count, write controlled `WHERE` clauses, use transactions when multiple changes must be atomic, and use `KeyHolder` when you actually need the **generated ID** rather than inferring an ID from the `int` value.
