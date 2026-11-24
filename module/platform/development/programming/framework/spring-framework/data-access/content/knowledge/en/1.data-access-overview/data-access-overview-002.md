# Relationship Between Business Logic, Data Layer, Connections, and the Database

> **Scope:** This lesson explains the path of a business operation in a Spring Framework application using a relational database: from the Service, through the Repository/DAO, data access API, and JDBC connection, to the database management system (DBMS). Spring JDBC serves as the hands-on example; comparisons with JPA highlight commonalities and differences. These are logical roles and do not necessarily correspond to four separate servers or four separate processes.

## 1. Seeing the Big Picture

Suppose a user requests **to transfer 30 currency units from account A to account B**. Business rules require a positive amount, sufficient balance in the source account, and both balance updates to succeed or fail together. The application should not let the UI/API layer assemble SQL statements; it delegates the task to a Service. The Service uses a Repository to read/write data, the Repository uses Spring's data access tools, and those tools borrow a connection to the DBMS from a DataSource.

~~~mermaid
flowchart TD
    Client["HTTP controller / CLI / scheduled job"] --> Service["Service: business rules and orchestration"]
    Service --> Repo["Repository / DAO: data operations"]
    Repo --> API["JdbcTemplate / JPA EntityManager"]
    API --> DS["DataSource: connection source, typically pooled"]
    DS --> JDBC["JDBC Driver + Connection"]
    JDBC <--> DB[("Relational database")]
~~~

Arrows indicate **call or dependency relationships**. On the return path, the DBMS returns SQL results; JDBC and the data access layer convert results into Java values or objects; the Repository returns data to the Service; the Service determines the business outcome. With JPA, a JPA provider (such as Hibernate) sits between `EntityManager` and JDBC and may defer SQL until flush time.

**Core distinction:** The Service decides *what is allowed to happen*; the Repository decides *which data to query or update*; the DataSource/Connection decides *which session connection the application uses to talk to the DBMS*; the DBMS executes queries, manages transactions, and persists data.

## 2. Responsibilities and Boundaries of Each Layer

| Component | Answers the Question | Typically Contains | Should Not Carry |
| --- | --- | --- | --- |
| Controller / trigger | Who is calling, and what shape do inputs/outputs take? | HTTP mapping, boundary input validation, status codes | SQL, Connection management, or complex business rules |
| Business Service | Is the operation valid and what steps are required? | Rules, condition checks, coordinating multiple repositories, transaction boundaries | Details of opening/closing JDBC Connections or per-table SQL statements |
| Repository / DAO | How is data retrieved or persisted? | SQL or JPA queries, parameters, row mapping, CRUD operations | Cross-object business policies or workflow orchestration |
| Spring Data Access | How is storage interaction simplified? | JdbcTemplate, JdbcClient, EntityManager, exception translation, transaction coordination | Defining business meaning |
| DataSource and pool | How are connections obtained, reused, and returned? | URL configuration, credentials, pool limits, timeouts | Judging whether a money transfer is valid |
| JDBC Driver / Connection | Over which connection are commands sent to the DBMS? | Protocol, PreparedStatement, ResultSet, transaction state | Holding full business rules |
| DBMS | How are reads, writes, locks, and durability handled? | Tables, indexes, constraints, SQL, transaction logs, isolation, commit/rollback | Deciding the application's overall business policies |

A **domain object** represents a business concept; a **row/entity** represents stored data. They may look identical in a small application, but their structures do not have to match. For example, a Service can return a `TransferReceipt` without exposing how many columns the `account` table has. This separation allows changing schemas, swapping storage technologies, or testing business rules with minimal ripple effects across layers.

A Repository is a design boundary: with Spring JDBC, you typically write SQL yourself in a `@Repository` class; with Spring Data JPA, you can declare an interface extending `JpaRepository` and let the framework generate the implementation. Not every Repository opens a Connection directly.

## 3. How a Request Travels Down to the DB and Back

Using the money transfer example with Spring JDBC:

1. **Receive command:** A Controller or background job creates a `transfer(A, B, 30)` request, identifies the caller, and validates input formatting.
2. **Enter Service:** The Service verifies a positive amount, ensures the two accounts differ, and orchestrates the debit/credit steps. The Service is typically where `@Transactional` is placed because the operation requires an atomic business outcome.
3. **Call Repository:** The Service asks the Repository to debit A and credit B. The Repository expresses the operations with parameterized SQL.
4. **Spring data access:** `JdbcTemplate` acquires a Connection matching the active transaction context; it creates a PreparedStatement, binds parameters, executes, and manages JDBC resources.
5. **DataSource and driver:** The DataSource typically draws a connection from the pool; the JDBC driver transmits the command to the DBMS. The connection may already have been acquired before the first SQL statement runs, depending on the transaction manager and configuration.
6. **DBMS processing:** The DBMS validates constraints, executes the UPDATE, manages locks and transaction state, and returns the affected row count or query results.
7. **Result propagates upward:** The Repository reports the updated row count; the Service decides whether it succeeded or throws an exception. The transaction manager commits if everything completes properly, or rolls back if an error matching the rollback rules occurs. Resources are released and the logical connection is returned to the pool.

A single Service call can issue **multiple SQL statements** while still belonging to **one database transaction**. Conversely, acquiring a Connection once does not automatically mean an entire workflow is wrapped in a business transaction.

### Path of a Read Operation

For a `getBalance(accountId)` request, the Service can call the Repository to run `SELECT balance ... WHERE id = ?`. The DBMS returns one row; JdbcTemplate maps the column to `BigDecimal`; the Service returns the value or an appropriate response type. Read queries often do not need a long write transaction, though they may require the same snapshot/transaction when consistency across multiple reads matters.

### Path of a Write Operation

For an UPDATE, the Repository should check the affected row count. `0 rows updated` can mean the record does not exist or a precondition failed—not automatically success. The Service translates that technical signal into a business-meaningful outcome. Database constraints (primary key, unique, foreign key, check) serve as the final guardrail for consistency, even when multiple requests execute concurrently.

## 4. DataSource, Connection, Pool, and Transaction Are Not the Same Concept

- **DataSource:** A Java object configuring the connection source; `getConnection()` returns a JDBC Connection. Spring Boot applications commonly auto-configure a DataSource from `spring.datasource.*` when JDBC libraries and an appropriate driver are present.
- **Connection:** Represents a working session with the DBMS. It carries state such as auto-commit, isolation, transaction start/end timing, and session settings. Never share a Connection arbitrarily across requests or threads.
- **Connection pool:** A collection of reusable connections (such as HikariCP). Borrow → use → `close()` on a pooled connection typically **returns it to the pool**, rather than immediately closing the underlying physical socket. A pool reduces connection creation overhead, but it does not turn slow SQL into fast SQL.
- **Transaction:** A unit of work that must commit or roll back together, managed via a Connection or by the corresponding transaction manager. In a JDBC setup with a single DataSource, Spring typically binds one Connection to the executing thread's transaction context so `JdbcTemplate` calls participate together.

**Relationship to remember:** The DataSource supplies the Connection; the Spring transaction manager manages transaction boundaries and coordinates the Connection; JdbcTemplate uses that Connection to issue SQL; the DBMS determines commit/rollback outcomes according to its transactional guarantees.

A common mistake: manually calling `dataSource.getConnection()` inside a `@Transactional` Service method, then calling `commit()` directly. A manually acquired connection is not automatically the one Spring bound to the transaction; doing so can create two independent transactions. With JDBC, prefer `JdbcTemplate` or Spring transaction utilities like `DataSourceUtils` if low-level JDBC access is needed, and let Spring manage commit/rollback.

A pool might have 10 connections serving many requests; one request holding a transaction too long can occupy a connection and force other requests to wait on the pool. Pool size is a finite resource, not an unlimited allowance for concurrent transactions.

## 5. Where Do Transaction Boundaries Belong?

In a transfer operation, **business logic** requires both UPDATEs to belong to the same atomic unit. Therefore, placing `@Transactional` on a **public Service method called through a Spring proxy** is usually better than putting each Repository method in its own separate transaction:

~~~text
Enter Service.transfer(...) via Spring proxy
    BEGIN / join transaction
        Repository.debit(A, 30)  --> UPDATE account ...
        Repository.credit(B, 30) --> UPDATE account ...
    If all conditions are met: COMMIT
    If a rollback-triggering error occurs: ROLLBACK
Exit: clean up transaction context and return Connection
~~~

If debit commits independently and credit fails, data can end up deducting from A without crediting B. When both statements share one transaction, an applicable exception rolls back both. Operations inside the DBMS are still subject to isolation rules and concurrency: **atomicity** does not automatically eliminate deadlocks, lost updates, or all concurrency anomalies.

Easy-to-confuse points:

- Under Spring's default transaction configuration, `RuntimeException` and `Error` trigger rollback; checked exceptions usually require explicit configuration, such as `@Transactional(rollbackFor = IOException.class)` when appropriate.
- In standard proxy mode, calling `this.transfer(...)` from another method on the **same object** bypasses the proxy, so the annotation on the internally called method may not take effect as expected.
- `@Transactional(readOnly = true)` is primarily an optimization/routing hint for underlying resources, not a guarantee that every DBMS will reject writes.
- A JDBC transaction on one DataSource does not automatically form an atomic transaction across two databases or an external HTTP API. Multi-system workflows require dedicated designs (such as outbox, idempotent retries, or compensating actions).
- Do not let user-wait operations, slow network API calls, or long CPU processing hold Connections/locks inside a transaction when they can be separated.

## 6. Runnable Example: Service → Repository → JDBC → H2

This example uses **Java 21, Gradle, Spring Boot 3.3.5, Spring JDBC, and H2**. Running H2 in memory reproduces the full data path without installing a database server. There are three Java files, three configuration/SQL files, and one `build.gradle`. In production, replace H2 with PostgreSQL/MySQL by configuring the driver, URL, and reviewing SQL dialect differences.

Minimal structure:

~~~text
build.gradle
src/main/java/com/example/dataaccess/DataAccessDemoApplication.java
src/main/java/com/example/dataaccess/AccountRepository.java
src/main/java/com/example/dataaccess/TransferService.java
src/main/resources/application.properties
src/main/resources/schema.sql
src/main/resources/data.sql
~~~

**`build.gradle`** — Spring JDBC brings in JDBC transaction management and a default connection pool when dependencies are present.

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(21)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    runtimeOnly 'com.h2database:h2'
}
~~~

**`src/main/resources/application.properties`** — console application, H2 DataSource, loads `schema.sql`/`data.sql` on startup.

~~~properties
spring.main.web-application-type=none
spring.datasource.url=jdbc:h2:mem:lesson;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

**`src/main/resources/schema.sql`** — the DBMS enforces a CHECK constraint to protect the balance.

~~~sql
CREATE TABLE account (
    id BIGINT PRIMARY KEY,
    balance DECIMAL(12, 2) NOT NULL,
    CONSTRAINT chk_balance_nonnegative CHECK (balance >= 0)
);
~~~

**`src/main/resources/data.sql`** — initial seed data.

~~~sql
INSERT INTO account (id, balance) VALUES (1, 100.00);
INSERT INTO account (id, balance) VALUES (2, 50.00);
~~~

**`AccountRepository.java`** — knows only table structure, queries, and affected row counts. SQL parameters use `?` so the driver binds values, avoiding direct string concatenation of inputs into SQL.

~~~java
package com.example.dataaccess;

import java.math.BigDecimal;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class AccountRepository {
    private final JdbcTemplate jdbc;

    public AccountRepository(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean debit(long id, BigDecimal amount) {
        int rows = jdbc.update(
            "UPDATE account SET balance = balance - ? " +
            "WHERE id = ? AND balance >= ?",
            amount, id, amount
        );
        return rows == 1;
    }

    public boolean credit(long id, BigDecimal amount) {
        int rows = jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = ?",
            amount, id
        );
        return rows == 1;
    }

    public BigDecimal balance(long id) {
        return jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?",
            BigDecimal.class,
            id
        );
    }
}
~~~

**`TransferService.java`** — business constraints and a transaction wrapping both Repository calls.

~~~java
package com.example.dataaccess;

import java.math.BigDecimal;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    private final AccountRepository accounts;

    public TransferService(AccountRepository accounts) {
        this.accounts = accounts;
    }

    @Transactional
    public void transfer(long fromId, long toId, BigDecimal amount) {
        if (amount == null || amount.signum() <= 0 || fromId == toId) {
            throw new IllegalArgumentException("Invalid transaction");
        }
        if (!accounts.debit(fromId, amount)) {
            throw new IllegalArgumentException(
                "Source does not exist or has insufficient balance"
            );
        }
        if (!accounts.credit(toId, amount)) {
            throw new IllegalArgumentException("Target does not exist");
        }
    }
}
~~~

**`DataAccessDemoApplication.java`** — initializes the Spring context, calls the Service through a Spring bean, and prints state for observation.

~~~java
package com.example.dataaccess;

import java.math.BigDecimal;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DataAccessDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DataAccessDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(TransferService transfers, AccountRepository accounts) {
        return args -> {
            show("Before", accounts);
            transfers.transfer(1L, 2L, new BigDecimal("30.00"));
            show("After success", accounts);

            try {
                transfers.transfer(1L, 999L, new BigDecimal("10.00"));
            } catch (IllegalArgumentException ex) {
                System.out.println("Transaction cancelled: " + ex.getMessage());
            }
            show("After rollback", accounts);
        };
    }

    private static void show(String label, AccountRepository accounts) {
        System.out.println(label + ": A=" + accounts.balance(1L)
            + ", B=" + accounts.balance(2L));
    }
}
~~~

In a project directory with a Gradle wrapper, run `./gradlew bootRun` (Windows PowerShell: `.\gradlew.bat bootRun`); if a suitable Gradle is installed and there is no wrapper, run `gradle bootRun`. The lines **explicitly printed by the program** (excluding Spring startup logs) are:

~~~text
Before: A=100.00, B=50.00
After success: A=70.00, B=80.00
Transaction cancelled: Target does not exist
After rollback: A=70.00, B=80.00
~~~

**Layer-by-layer explanation:**

1. The console application acts as the trigger; an HTTP controller scenario could invoke the same Service.
2. `TransferService.transfer` validates preconditions and opens a transaction via a Spring proxy. Target account 999 does not exist, so the second operation in the second attempt returns `false`.
3. `AccountRepository` runs two UPDATEs using JdbcTemplate; it does not decide rollback itself, only reports data operation outcomes.
4. JdbcTemplate coordinates with the Spring transaction manager so the UPDATEs within a single `transfer` use the active transaction; HikariCP supplies the connection and H2 executes the SQL.
5. The first transfer commits: A 100 → 70, B 50 → 80. The transfer to id 999 temporarily deducts from A but throws `IllegalArgumentException`, which is a RuntimeException, so rollback restores A to 70 while B remains 80.

This example is intentionally simplified: it omits user authentication, limits, currencies, auditing, idempotency requirements, HTTP error policies, and lock contention between two accounts or multiple distinct systems. When building real financial transactions, those aspects are mandatory design requirements to address separately; do not treat this demo code as a complete banking system.

## 7. Same Path, Two Spring Data Access Approaches

| Aspect | Spring JDBC (JdbcTemplate) | Spring Data JPA / JPA provider |
| --- | --- | --- |
| Business layer | Service orchestrates, typically with `@Transactional` | Service orchestrates, typically with `@Transactional` |
| Data layer | Repository writes SQL and maps data explicitly | Repository/EntityManager works with entities, JPQL, or query methods |
| SQL timing | Most `update/query` calls send SQL immediately when invoked | Has a persistence context; entity changes may wait until flush before commit or query |
| Connections | JdbcTemplate borrows a Connection coordinated by Spring | JPA provider obtains a Connection from DataSource according to its strategy |
| Transactions | Transaction manager matching the JDBC DataSource | Transaction manager for JPA (typically JpaTransactionManager) |
| Key concerns | SQL, mapping, resource cleanup, affected row counts | N+1 queries, lazy loading, flush, dirty checking, entity states |

**What stays constant:** business logic still belongs in the Service; data still passes through an adapter/repository; the DBMS still decides execution and data durability. Do not think JPA eliminates Connections: it abstracts away underlying JDBC usage when working with relational databases.

Not every storage system goes through JDBC. Redis, MongoDB, or an external API has its own client/protocol; in those cases the connection layer changes, but the principle of separating business logic from storage details remains useful.

## 8. Where Do Consistency, Performance, and Errors Live at the Boundaries?

**Business ↔ Repository:** A Service might check balance first and then UPDATE, but two concurrent requests can read the same stale balance. The example above uses a conditional UPDATE `balance >= ?` directly in the DBMS to reduce overdraft errors under contention. For more complex workflows, consider isolation levels, optimistic locking/versioning, or pessimistic locking; conditional UPDATE is one technique and does not solve every race condition.

**Repository ↔ DBMS:** Syntactically valid SQL is not guaranteed to run fast. Proper indexes, query plans, returned payload size, and batch operations heavily determine latency. N+1 queries in ORM are a symptom of the data layer calling the DB too many times to serve one business request.

**Connection pool ↔ DBMS:** Pool exhaustion can cause timeouts **before SQL is even sent to the DB**, even if the query itself is fast. Conversely, the pool may have idle capacity while SQL is slow due to missing indexes, locks, or DB load. When diagnosing, distinguish Connection wait time, SQL execution time, and business processing time.

**Transactions ↔ data:** The DBMS enforces ACID guarantees according to the engine and isolation level in use. Long transactions hold connections and locks for too long. Poorly split transactions can allow multi-step business operations to succeed only partially.

**Technical errors ↔ business errors:** `0 rows updated`, unique violations, timeouts, and lost connections are distinct signals. Spring JDBC typically translates SQLException into the `DataAccessException` (unchecked) hierarchy so upper layers can handle them consistently. Do not turn every database exception into "not found" or automatically retry every UPDATE; retries must depend on the specific error and idempotency.

## 9. Common Mistakes and How to Fix Them

| Mistake | Consequence | Remedy |
| --- | --- | --- |
| Controller writes SQL and checks all rules | Hard to reuse/test business logic; mixes UI with storage | Controller calls Service; Service calls Repository |
| Putting two UPDATEs in two independent transactions | Can debit without crediting | Wrap the entire operation in one Service transaction |
| Manually opening Connection and committing inside `@Transactional` | Can escape Spring-managed transaction | Use JdbcTemplate/JPA or Spring's transaction-aware APIs |
| Concatenating input into SQL strings | SQL injection or escaping bugs | PreparedStatement/parameter binding |
| Ignoring UPDATE row counts | Fails to detect missing records or failed conditions | Check rows affected and convert to business errors |
| Assuming `@Transactional` always runs on same-class calls | Self-invocation bypasses the proxy | Call via a Spring-managed bean; design clear boundaries |
| Believing a larger pool fixes all latency | Increases DB load; still slow due to SQL/locks | Measure latency, wait time, SQL plans; optimize the actual bottleneck |
| Reading then deciding to write without concurrency consideration | May operate on stale state | Atomic UPDATE, locking, or versioning when needed |
| Validating data only in Java, skipping DB constraints | Multiple write paths can produce invalid data | Keep critical constraints in the schema |
| Holding a transaction across slow API calls | Connections and locks stay occupied | Shrink transactions; design asynchronous integration when needed |

## 10. Self-Check Your Understanding

1. A Service needs to update three tables to complete a command. Where should the transaction boundary be placed? **On a single Service operation encompassing the steps that must be atomic**, then verify all Repositories use compatible resources/transactions.
2. Why are DataSource and Connection not synonymous? **DataSource supplies and manages the provisioning of Connections; Connection is the actual working session to the DBMS.**
3. If the second SQL statement fails after the Repository has already returned data to the Service, will rollback still occur? **Yes, if the error marks the transaction for rollback before commit and all statements participate in that same transaction.**
4. With Spring Data JPA, does the application "not need a database connection"? **No.** The JPA provider still uses connections to the relational DBMS; it merely hides JDBC operations from application code.
5. When an API is slow and many threads are waiting on the pool while queries are fast, what should you investigate first? **Connections held too long, long-running transactions, pool size/timeouts, and resource release**, rather than defaulting to optimizing SELECT statements.

**Key takeaway:** A business operation may traverse several code layers, yet it should have **a single place defining business meaning** and **a transaction boundary aligned with the consistency unit**. Repository, DataSource, Connection, and DBMS each have distinct responsibilities; understanding these boundaries leads to sound design, accurate error handling, and effective bottleneck diagnosis in production.
