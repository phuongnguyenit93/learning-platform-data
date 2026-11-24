# Executing Two Write Operations in One Business Flow

## 1. The First Transaction Problem

**Goal:** understand and run a Spring Framework business operation in which **two data write operations must succeed together or be canceled together**. After this lesson, you can:

1. Identify the data state before and after two write statements.
2. Distinguish **two sequentially executed statements** from **two statements inside the same transaction**.
3. Place the `@Transactional` boundary at the service layer so two repository operations share the same JDBC transaction.
4. Trigger an intentional error after the first operation, observe the rollback, and accurately explain why the first operation was not persisted.
5. Verify results against actual data instead of merely claiming the method has an annotation.

Throughout this example, the `wallets` table holds two accounts:

| Account | `id` | Initial `balance` |
| --- | ---: | ---: |
| A (sender) | 1 | 100 |
| B (receiver) | 2 | 50 |

The business operation of **transferring 20 units from A to B** requires two write statements:

```sql
-- Write 1: debit A, only deduct if balance is sufficient.
UPDATE wallets
SET balance = balance - 20
WHERE id = 1 AND balance >= 20;

-- Write 2: credit B.
UPDATE wallets
SET balance = balance + 20
WHERE id = 2;
```

If both succeed, the balances become **A = 80, B = 70**, with the total still equal to 150. If write 1 succeeds while write 2 fails, the business operation must return data to **A = 100, B = 50**. The desired property is **atomicity**: all changes belonging to the transaction are committed as a single unit or rolled back as a single unit.

In this example, both writes belong to **the same JDBC database**. Do not generalize that Spring automatically rolls back emails, HTTP requests, sent messages, or two independent databases if they do not participate in the corresponding transaction mechanism.

## 2. Why Calling Two Statements Sequentially Is Not Enough

Consider a method without a transaction boundary:

```java
public void transferWithoutTransaction(int from, int to, int amount) {
    repository.debit(from, amount);  // First write.
    repository.credit(to, amount); // Second write.
}
```

This is **simulated service-layer code**, assuming `repository` provides both methods. Java statement ordering does not create a transaction by itself. In common JDBC configurations, connections not managed by Spring within a transaction run with `autoCommit=true`: each statement can be committed individually. If the second write fails, the already-committed first write will not automatically reverse.

| Moment | Without shared transaction | Inside a single transaction |
| --- | --- | --- |
| Initially | A=100, B=50 | A=100, B=50 |
| After write 1 | A is debited; may already be committed | A is debited **inside an uncommitted transaction** |
| Write 2 fails | A may remain debited, B not credited | Exception causes transaction rollback |
| Error outcome | Data may be corrupted: A=80, B=50 | Restored to A=100, B=50 |

Distinguish **temporary state inside a transaction** from **committed state**: write statement 1 is still executed by the database, so the current transaction can see the tentative result; rollback is what cancels it. Whether other transactions can see tentative data depends on database isolation.

A transaction does not replace business validation. Both `UPDATE` statements can run and affect **0 rows** (for instance, the destination account does not exist). Therefore, code must check the **updated row count** and treat an unsatisfactory result as an error so the whole transaction rolls back.

## 3. Where to Place the Transaction Boundary in Spring?

A readable structure is:

```text
Application/Controller
    |
    v
WalletService.transfer(...)        <- @Transactional: business boundary
    |
    +--> WalletRepository.debit(...)   <- first UPDATE
    |
    +--> WalletRepository.credit(...)  <- second UPDATE
    |
    v
Commit when both succeed;
Roll back if a required step throws an error requiring rollback.
```

**Why place it on the service?** The service decides that the two repository operations form **one use case**. The repository only executes queries/updates; invoking two repository methods inside the same transaction is a business-coordination decision.

With `@Transactional` running in common Spring AOP proxy mode:

1. The caller obtains `WalletService` from the Spring context and calls `transfer()` **through the proxy**.
2. The transaction interceptor asks `PlatformTransactionManager` to start a transaction (or join an existing one per propagation).
3. Both `debit()` and `credit()` use `JdbcTemplate` and the same `DataSource`, so Spring obtains the JDBC `Connection` bound to the active transaction.
4. Normal method completion: manager commits. If an unchecked exception escapes: default rollback; caller receives the exception.

This entails two important conditions: the bean must be Spring-managed and the call must go **through the proxy**; JDBC operations must use resources participating in the same transaction. `JdbcTemplate` acquires connections via `DataSourceUtils`, supporting this rule with `DataSourceTransactionManager`. Calling `this.transfer()` from another method on the target class itself bypasses the proxy in default mode.

In the standalone example below, `@EnableTransactionManagement` enables annotation processing; `DataSourceTransactionManager` manages an H2 `DataSource`.

## 4. Full Practice: Java 17+, Spring Framework, JDBC, H2

This small project uses **Spring Framework 6.2.8**, **H2 2.3.232**, and Maven. Versions are pinned so the example has deterministic dependencies. This is a standalone Java application needing no Spring Boot, HTTP server, or pre-installed database.

### 4.1. File Structure

```text
two-writes-demo/
├── pom.xml
└── src/main/java/example/
    ├── App.java
    ├── TxConfig.java
    ├── WalletRepository.java
    └── WalletService.java
```

### 4.2. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>two-writes-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.8</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-tx</artifactId>
            <version>6.2.8</version>
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
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.4.1</version>
                <configuration>
                    <mainClass>example.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` contains ApplicationContext and proxy infrastructure; `spring-jdbc` contains `JdbcTemplate` and the JDBC transaction manager; `spring-tx` contains the transaction abstraction and `@Transactional`; H2 is the database running in JVM memory. In production projects, dependencies/versions are usually managed centrally with a BOM and an appropriate connection pool is used.

### 4.3. `TxConfig.java` — Configuring Connection and Transaction Manager

```java
package example;

import javax.sql.DataSource;

import org.h2.jdbcx.JdbcDataSource;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DataSourceTransactionManager;

@Configuration
@EnableTransactionManagement
public class TxConfig {

    @Bean
    public DataSource dataSource() {
        JdbcDataSource ds = new JdbcDataSource();
        ds.setURL("jdbc:h2:mem:two_writes;DB_CLOSE_DELAY=-1");
        ds.setUser("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    public JdbcTemplate jdbcTemplate(DataSource dataSource) {
        return new JdbcTemplate(dataSource);
    }

    @Bean
    public PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new DataSourceTransactionManager(dataSource);
    }

    @Bean
    public WalletRepository walletRepository(JdbcTemplate jdbcTemplate) {
        return new WalletRepository(jdbcTemplate);
    }

    @Bean
    public WalletService walletService(WalletRepository walletRepository) {
        return new WalletService(walletRepository);
    }
}
```

- `@EnableTransactionManagement` allows Spring to apply `@Transactional` via the transaction interceptor/proxy.
- `transactionManager()` manages JDBC connections of that exact `dataSource()`. Do not create two separate datasources for the two operations.
- `DB_CLOSE_DELAY=-1` keeps the H2 in-memory database alive until the JVM exits, even when connections temporarily close.
- `JdbcDataSource` here is for demo purposes; real applications normally use a pooling datasource.

### 4.4. `WalletRepository.java` — Exactly Two Write Operations

```java
package example;

import org.springframework.jdbc.core.JdbcTemplate;

public class WalletRepository {

    private final JdbcTemplate jdbc;

    public WalletRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public int debit(int walletId, int amount) {
        return jdbc.update(
            "UPDATE wallets " +
            "SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, walletId, amount
        );
    }

    public int credit(int walletId, int amount) {
        return jdbc.update(
            "UPDATE wallets " +
            "SET balance = balance + ? " +
            "WHERE id = ?",
            amount, walletId
        );
    }
}
```

`debit` is write 1, `credit` is write 2. Both return `int` — the number of rows actually modified by `UPDATE`. In a problem where each `id` is a unique account, the valid result for each step is **1 row**. A result of 0 indicates the account does not exist or the source lacks sufficient balance.

Putting the `balance >= ?` condition directly in the `UPDATE` statement makes balance checking and debiting happen as a conditional SQL operation; avoid doing "SELECT balance -> check in Java -> unconditional UPDATE" while ignoring race risks. Locking, deadlocks, retries, and isolation under concurrent load still need dedicated handling for production environments.

### 4.5. `WalletService.java` — One Boundary Containing Both Writes

```java
package example;

import org.springframework.transaction.annotation.Transactional;

public class WalletService {

    private final WalletRepository repository;

    public WalletService(WalletRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void transfer(
        int fromId,
        int toId,
        int amount,
        boolean failAfterDebit
    ) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("invalid transfer");
        }

        int debited = repository.debit(fromId, amount);  // WRITE 1
        if (debited != 1) {
            throw new IllegalStateException("source missing or insufficient");
        }

        if (failAfterDebit) {
            // Used only in this lab to intentionally break the business operation.
            throw new IllegalStateException("simulated failure after debit");
        }

        int credited = repository.credit(toId, amount); // WRITE 2
        if (credited != 1) {
            throw new IllegalStateException("receiver missing");
        }
    }
}
```

**The decisive point lies in `@Transactional` on `transfer`.** Within one call:

- Spring starts a transaction before executing the method body (if none exists yet).
- The repository executes both `UPDATE` statements using the same JDBC transaction.
- If `debit` or `credit` does not affect 1 row, the service throws an exception rather than returning a fake success.
- If an error occurs between the two writes, `IllegalStateException` is an unchecked exception so Spring rolls back by default.
- Only when the method completes validly does the transaction boundary commit.

The `failAfterDebit` flag is an **experiment-only** switch, used to deliberately verify the "write 1 succeeded but write 2 has not" scenario. A production use case would not have this parameter.

### 4.6. `App.java` — Initializing Data, Calling the Bean, and Observing Output

```java
package example;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.jdbc.core.JdbcTemplate;

public final class App {

    private App() {
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(TxConfig.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            WalletService service = context.getBean(WalletService.class);

            jdbc.execute(
                "CREATE TABLE wallets (" +
                "id INT PRIMARY KEY, " +
                "balance INT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO wallets(id, balance) VALUES (?, ?)", 1, 100
            );
            jdbc.update(
                "INSERT INTO wallets(id, balance) VALUES (?, ?)", 2, 50
            );

            showBalances("Before", jdbc);

            service.transfer(1, 2, 20, false);
            showBalances("After commit", jdbc);

            try {
                service.transfer(1, 2, 10, true);
            } catch (IllegalStateException ex) {
                System.out.println("Expected error: " + ex.getMessage());
            }
            showBalances("After rollback", jdbc);

            try {
                service.transfer(1, 999, 5, false);
            } catch (IllegalStateException ex) {
                System.out.println("Expected error: " + ex.getMessage());
            }
            showBalances("After receiver error", jdbc);
        }
    }

    private static void showBalances(String label, JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = ?", Integer.class, 1
        );
        Integer b = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = ?", Integer.class, 2
        );
        System.out.println(label + ": A=" + a + ", B=" + b);
    }
}
```

Calling `context.getBean(WalletService.class)` is critical: `service` is a bean obtained from Spring and invoked **from outside**, so `@Transactional` is applied by the interceptor. Replacing it with `new WalletService(...)` or having a method inside `WalletService` call `this.transfer(...)` alters proxy behavior.

Initial data is created before running the test transactions. After each service call, `showBalances` re-queries the table and shows committed (or rolled-back) data from the viewpoint of an independent query after the transaction ends.

### 4.7. Compiling and Running

Open a terminal in the directory containing `pom.xml`. Requires JDK 17+ and Maven 3.9+ (with Maven Central access for the first dependency download):

```bash
java -version
mvn -version
mvn -q compile exec:java
```

The lines printed by the program must be (aside from Maven/Spring logs if your environment displays them):

```text
Before: A=100, B=50
After commit: A=80, B=70
Expected error: simulated failure after debit
After rollback: A=80, B=70
Expected error: receiver missing
After receiver error: A=80, B=70
```

**Reading the output per transaction:**

1. **Successful call:** Write 1 debits A by 20, write 2 credits B by 20, then commits. `(100, 50)` becomes `(80, 70)`.
2. **Mid-way error:** The next call attempts to debit A by 10 but throws `simulated failure after debit` before crediting B. Because the exception escapes `transfer`, Spring rolls back the entire transaction. Output remains `(80, 70)`.
3. **Receiver account missing:** Write 1 tentatively debits A by 5; write 2 has `id = 999` so it updates 0 rows, and the service throws `receiver missing`. The transaction rolls back, leaving A/B at `(80, 70)`. This is why checking `update count` is necessary rather than waiting solely for a JDBC driver exception.

The transferred total in the successful run remains 150. The fact that the two error runs do not alter the new balances is direct evidence of rollback for **the entire business flow**.

## 5. What Happens If the Transaction Boundary Is Removed?

You can run an experiment **on a copy of the H2 lab**, never on real data:

- Remove the `@Transactional` annotation on `WalletService.transfer` and re-run the program from scratch in a new JVM.
- The successful call may still produce `(80, 70)` because each `UPDATE` completes.
- On the call that fails between the two writes, `debit` may have already auto-committed on an independent connection; the state after failure becomes **A=70, B=70**, totaling only 140.
- The missing receiver error may likewise leave A reduced, because write 1 committed while write 2 modified 0 rows.

The bug is not in SQL syntax: the same two SQL statements, the same Java order, yet **lacking a shared transaction boundary**, the application no longer guarantees atomicity.

If you put `@Transactional` separately on `WalletRepository.debit()` and `WalletRepository.credit()` and call them from a non-transactional service, each repository method may create **its own transaction**, still failing the "both or neither" requirement. The boundary must enclose **both writes of one use case**.

## 6. Understanding Commit, Rollback, and Propagation via the Lab

By default, `@Transactional` uses `Propagation.REQUIRED`. In `App.main` there is no transaction enclosing `service.transfer()`, so when invoked via proxy, Spring creates a new transaction. If another service has already opened a transaction and calls `transfer()` via proxy with `REQUIRED`, both can **participate in an existing physical transaction**. In that case, the final outcome depends on the outermost caller's transaction; `transfer()` returning does not necessarily mean a physical commit occurred.

For this JDBC transaction:

- **Begin:** The transaction manager acquires a connection, sets the appropriate transaction mode, and binds the resource to the current thread.
- **Write 1 and Write 2:** `JdbcTemplate` goes through `DataSourceUtils` and therefore reuses the connection Spring bound to the transaction.
- **Commit:** When the proxy receives a normal return, the boundary owning the transaction requests commit; the database persists both updates.
- **Rollback:** When an exception matching rollback rules escapes the method, the boundary requests rollback; the database undoes uncommitted changes, including write 1 that already executed.

By default in imperative declarative transactions, `RuntimeException` or `Error` triggers rollback; checked exceptions like `IOException` **do not trigger rollback automatically** without a matching rollback rule. If a use case has a checked exception that must cancel both writes, declare `@Transactional(rollbackFor = IOException.class)`. Global/manager policies can be customized; inspect system configuration when predicting exception behavior.

**Do not catch errors and silently return success** inside a transactional method. The following example **illustrates a design flaw**, not a standalone runnable snippet:

```java
@Transactional
public void transferWrongly() {
    repository.debit(1, 20);
    try {
        repository.credit(999, 20);
    } catch (RuntimeException ex) {
        // Swallowed exception: the interceptor may think the operation succeeded.
    }
}
```

Aside from not checking the update count, the snippet above risks swallowing errors. If an exception is caught and rollback-only is not set, Spring may commit the debit operation. The right way in the lab is to check each result and let the exception escape `transfer`; for special handling scenarios, you can explicitly mark rollback-only.

**Transaction scope and threads:** This JDBC model binds transactions to the caller's thread. Do not offload `debit` and `credit` onto arbitrary threads with `@Async`/`CompletableFuture` and assume the transaction propagates automatically across threads. Reactive R2DBC has a different transaction infrastructure using Reactor Context and `ReactiveTransactionManager`.

## 7. Variant: The Same Two Writes via `TransactionTemplate`

A transaction boundary can also be written programmatically. The following snippet assumes `repository` is `WalletRepository` from the demo and `manager` is `PlatformTransactionManager` managing the right datasource:

```java
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public class TemplateTransferService {
    private final WalletRepository repository;
    private final TransactionTemplate template;

    public TemplateTransferService(
        WalletRepository repository,
        PlatformTransactionManager manager
    ) {
        this.repository = repository;
        this.template = new TransactionTemplate(manager);
    }

    public void transfer(int fromId, int toId, int amount) {
        if (amount <= 0 || fromId == toId) {
            throw new IllegalArgumentException("invalid transfer");
        }

        template.executeWithoutResult(status -> {
            if (repository.debit(fromId, amount) != 1) {
                throw new IllegalStateException("cannot debit");
            }
            if (repository.credit(toId, amount) != 1) {
                throw new IllegalStateException("cannot credit");
            }
        });
    }
}
```

This is an **illustrative class that compiles when added to the project**, not yet registered as a bean in `TxConfig`. `TransactionTemplate` starts and coordinates ending the callback scope itself, so both write statements are still wrapped in one transaction. Using `@Transactional` is convenient when the boundary aligns with the entire service method; the template is useful when only part of a longer flow needs a transaction or when boundaries depend on processing branches.

## 8. Testing Thoroughly Enough for Two Write Operations

A good test must observe **the database state after the transaction finishes**. You can build a test-case matrix for the same `transfer` method:

| Case | Write 1 | Write 2 | Expectation |
| --- | --- | --- | --- |
| Source has enough funds, target exists | 1 row | 1 row | Commit both; total balance unchanged |
| Intentionally throw error between steps | 1 row tentatively | Not run | Rollback; both balances unchanged |
| Destination account missing | 1 row tentatively | 0 rows | Throw error and roll back write 1 |
| Insufficient funds in source | 0 rows | Not run | Throw error; balances unchanged |
| `amount <= 0` or same account | Not run | Not run | Reject input data |

**How to verify:** initialize data; call the service **via Spring bean**; catch the exception on the caller side when continuing checks; re-read via query after the service call has finished; compare individual account balances, not just the total. An unchanged total does not guarantee every transfer was valid; conversely, each step affecting 1 row is not enough without a transaction boundary.

When using Spring Test, a test method annotated with `@Transactional` may run inside the test's own transaction and be rolled back by the framework after the test. If you want to verify actual commit/rollback at the service boundary, structure integration tests to distinguish the **test harness** transaction from the application transaction (e.g., calling the service outside a test-managed transaction).

In real products, you must also handle request idempotency, transfer authorization, validation, concurrency/lock ordering, isolation, connection-pool sizing, connection hold-time monitoring, and controlled retries. Specifically, **do not make HTTP/email calls and assume JDBC rollback will undo external side effects**; you may need outbox, saga, or compensation depending on the problem.

## 9. Summary of Key Knowledge

Two write operations in a business flow are only atomic when they **participate together in a managed transaction**. In a Spring JDBC application, the first approach to practice is placing `@Transactional` on the service method enclosing both repository operations; ensuring calls go through the Spring proxy, repositories use the same datasource/manager, and a failure in one step causes the transaction to roll back.

The most important part of this lab is not running two `UPDATE` statements successfully. It is **deliberately breaking the second operation or failing right after the first operation, and confirming that no partial update was committed**.

Answer these yourself before moving to the next lesson:

1. Why do two consecutive `UPDATE` statements not form a transaction by default?
2. If `credit()` updates 0 rows without throwing an error, does `@Transactional` automatically know the operation failed?
3. Why does `App` retrieve `WalletService` from the Spring context instead of calling `new`?
4. Why is it necessary to re-read state **after** the transactional method ends?
5. What is the consequence of moving `debit` and `credit` to two datasources that do not participate in the same transaction?

## 10. References

- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Controlling Database Connections (`DataSourceUtils`)](https://docs.spring.io/spring-framework/reference/data-access/jdbc/connections.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
