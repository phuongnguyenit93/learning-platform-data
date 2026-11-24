# Placing the Transaction Boundary on the Orchestrating Service Instead of Individual Small Operations — Spring REQUIRED

## 1. Problem to Solve

A business request often consists of **multiple data operations**, yet users expect them to produce **one consistent outcome**. For example, transferring 10 units from account A to B requires two statements: debiting A and crediting B. If debiting A succeeds and then crediting B fails, the system must not save half of a money transfer.

In Spring Framework, the standard solution is to place **@Transactional(propagation = Propagation.REQUIRED)** on the method of the **orchestrating service (orchestration/application service)** that executes an entire use case. Repositories/DAOs called by the service will join the active transaction if they use the right resource and transaction manager.

What matters is not "every method has @Transactional", but that **the transaction boundary encloses all operations that must commit or roll back together**.

This lesson belongs to the **REQUIRED** section in the Spring transaction management module. After studying it, you should be able to:

- Identify an **atomic business operation**.
- Distinguish a transaction on an **orchestrating service** from multiple transactions on **granular repository operations**.
- Understand why multiple `REQUIRED` methods can share **one physical transaction**, or create **multiple physical transactions** if an outer boundary is missing.
- Choose where to place `@Transactional`, specify rollback rules, and avoid self-invocation mistakes.
- Run a Java 17+ example illustrating the exact same two SQL statements producing **different outcomes when the boundary is placed wrongly**.
- Know when to narrow a transaction, separate side effects, or use consistency solutions outside the DB.

## 2. Business Boundaries Differ from Technical Method Boundaries

Suppose the system has these technical operations:

1. **debit(A, 10):** subtract 10 from A.
2. **credit(B, 10):** add 10 to B.
3. **transfer(A, B, 10):** orchestrate 1 and 2 while checking business preconditions.

Each debit/credit can be a valid method at the repository layer. Yet the **unit of consistency** the user requires is **transfer**, not each individual UPDATE statement.

| Criterion | Transaction around each small operation | Transaction around the orchestrating service |
| --- | --- | --- |
| Boundary | debit() opens/commits separately; credit() opens/commits separately if there is no outer transaction | transfer() opens the transaction; debit() and credit() both join |
| Number of physical transactions when calling debit then credit | Typically 2 local transactions when each `REQUIRED` method is called separately via proxy | Typically 1 physical transaction with the same DataSource and manager |
| If credit fails after debit already committed | Cannot automatically roll back the already-committed debit | Can roll back both uncommitted debit and credit |
| Where the "all succeed/fail together" rule is expressed | Fragmented; depends on external call order | Located in the service executing the use case |
| Repository reusability | Each method guarantees only its own transaction | Repositories remain reusable yet join the outer transaction when one exists |
| Clarity | Easy to mistakenly assume having many `@Transactional`s is safe | Clearly expresses the business boundary |

**Principle:** a transaction normally corresponds to **a use case protecting a set of business invariants**, within the scope of managed ACID resources. Do not choose boundaries merely because a method is short or a class contains multiple SQL statements.

### Invariant example

With accounts A=100 and B=100, the total funds across both accounts before and after an internal transfer of 10 must always remain 200.

~~~text
Initial state:
  A=100, B=100, total=200

Correct — one transaction wraps both UPDATEs:
  begin
  A := A - 10       (90)
  B := B + 10       (110)
  commit
  => A=90, B=110, total=200

Error after step A:
  begin
  A := A - 10       (90 in transaction)
  ERROR
  rollback
  => A=100, B=100, total=200

Wrong — each step commits separately:
  begin debit
  A := A - 10
  commit debit      (A=90)
  ERROR before credit
  => A=90, B=100, total=190 — invariant broken
~~~

Rollback only applies to **uncommitted changes of the relevant transaction**. It cannot "turn back time" to undo an independent debit transaction that already committed.

## 3. How Does REQUIRED Work?

**PROPAGATION_REQUIRED** is the default propagation of `@Transactional`. When a method is managed by the Spring transaction interceptor:

- **No matching transaction exists:** Spring starts a new physical transaction.
- **A matching transaction already exists:** the method joins the existing transaction.
- Scopes can have **separate logical transaction boundaries**, yet when they participate via REQUIRED together, they share **one physical transaction**.
- The transaction truly commits only when the owner of the physical transaction completes successfully; participating inner methods cannot commit independently on their own.

Good call shape:

~~~text
Caller
  |
  v
TransferService.transfer()   @Transactional(REQUIRED)
  |                           |
  |                           +-- Spring creates JDBC transaction T1
  |
  +-- AccountRepository.debit()  REQUIRED -> joins T1
  |
  +-- AccountRepository.credit() REQUIRED -> joins T1
  |
  +-- transfer() returns successfully -> COMMIT T1
      or matching exception -> ROLLBACK T1
~~~

Call shape missing a service boundary:

~~~text
Caller
  |
  v
TransferService.transferWithoutBoundary()   (no @Transactional)
  |
  +-- AccountRepository.debit()  REQUIRED -> creates T1 -> COMMIT T1
  |
  +-- orchestration logic hits exception
  |
  X-- AccountRepository.credit() not called
      No T1 transaction left to roll back
~~~

Therefore, **REQUIRED does not mean every method in the same HTTP request automatically belongs to the same transaction**. It only means each intercepted invocation **joins an existing transaction or opens a new one**. To have an "existing transaction" for the entire use case, you must create it at the orchestrating layer.

### Logical scope and physical transaction

Suppose outer `transfer()` and inner `debit()` both carry `REQUIRED`. When called properly through proxies:

- The **transfer** scope is a logical transaction boundary.
- The **debit** scope has its own metadata and logical state; it participates in transfer's physical transaction.
- Two scopes do not perform two physical commits.
- If the inner scope marks rollback-only, the shared transaction cannot commit even if outer catches the exception and continues. Depending on how it unfolds, outer may receive **UnexpectedRollbackException** when attempting to commit.

Distinguish **method return** from **physical commit**. `debit()` returning does not mean money has been persisted durably while `transfer()` is still holding the transaction.

## 4. Where Should @Transactional Be Placed?

### 4.1. Recommended boundary: public application service method

Architectural example:

~~~java
// Snippet: repositories are Spring beans, same DataSource/manager.
@Service
public class TransferService {
    private final AccountRepository accounts;
    private final TransferPolicy policy;

    public TransferService(AccountRepository accounts, TransferPolicy policy) {
        this.accounts = accounts;
        this.policy = policy;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void transfer(long from, long to, long amount) {
        policy.validate(from, to, amount);
        accounts.debit(from, amount);
        accounts.credit(to, amount);
    }
}
~~~

This is **illustrative code, not a standalone program**: it requires definitions for `AccountRepository`, `TransferPolicy`, imports, and transaction infrastructure. Meaning: `transfer()` represents **one use case**, while the two repository calls execute steps within that use case.

**Repositories are not required to have @Transactional** if the service method itself already opens the transaction and the repositories access the right resource via Spring JDBC/JPA. `JdbcTemplate`/JPA in standard configuration will use the corresponding transaction-bound resource.

### 4.2. What if the repository also has REQUIRED?

~~~java
@Repository
public class AccountRepository {
    @Transactional(propagation = Propagation.REQUIRED)
    public void debit(long id, long amount) {
        // SQL UPDATE ...
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void credit(long id, long amount) {
        // SQL UPDATE ...
    }
}
~~~

This is also an illustrative snippet. If `transfer()` has already opened transaction T1, both repository methods called through proxies will **join T1**. Yet if `transfer()` has **no** transaction and each repository method is a top-level call, `debit()` and `credit()` normally **each open a new physical transaction**. Annotating individual DAOs does not create atomicity for a service's call sequence.

You can place `REQUIRED` on repositories to support callers invoking a repository directly; that does not replace designing the service boundary. In many projects, centralizing transaction policy at the service layer is easiest to understand and control. Choose a consistent convention to avoid hard-to-trace scopes.

### 4.3. Why not place @Transactional on the Controller?

Controllers receive HTTP requests, map inputs, and construct responses. Putting a transaction over the entire controller can stretch the transaction across deserialization, validation, calling other APIs, building responses, or steps unrelated to the DB. A service transaction is usually a cleaner boundary: wide enough to protect one use case, yet not enclosing web work that does not need ACID.

This is not an absolute ban on transactions in every controller; it is a **boundary design recommendation**. Place policy where it best expresses invariants and where Spring proxies are genuinely invoked.

### 4.4. Why not just wrap a single SQL statement?

A single SQL UPDATE is already atomic in the database. Yet a multi-step use case may need to:
- Write an order, multiple order lines, and update inventory.
- Write a payment record and update invoice status.
- Mark a job completed and write the corresponding result.
- Transfer balance between two accounts in the same database.

Per-statement transactions are insufficient to guarantee **multi-step atomicity**. Conversely, you should also not lump everything in a request into one transaction if they do not share an invariant or use multiple systems outside the database.

## 5. Sequence Diagram: One Transaction with REQUIRED

~~~mermaid
sequenceDiagram
    actor Caller
    participant Proxy as TransferService proxy
    participant TM as JdbcTransactionManager
    participant Repo as Repository proxy
    participant DB as Database
    Caller->>Proxy: transfer()
    Proxy->>TM: getTransaction(REQUIRED)
    TM->>DB: Open transaction T1
    Proxy->>Repo: debit()
    Repo->>TM: REQUIRED, join T1
    Repo->>DB: UPDATE account A
    Repo-->>Proxy: return (no separate commit)
    Proxy->>Repo: credit()
    Repo->>TM: REQUIRED, join T1
    Repo->>DB: UPDATE account B
    alt transfer() succeeds
        Proxy->>TM: commit outer T1
        TM->>DB: COMMIT T1
    else Error matching rollback
        Proxy->>TM: rollback outer T1
        TM->>DB: ROLLBACK T1
    end
    TM-->>Caller: Cleanup, release connection
~~~

The actual path is Spring AOP's `TransactionInterceptor` invoking `TransactionManager`; the manager uses the appropriate `DataSource` and JDBC `Connection`. The DBMS is what executes commit/rollback. An implementation might not send an explicit `"BEGIN"` SQL string; with JDBC, the connection is usually switched to manual-commit mode when needed.

**Conditions for one physical transaction:** calls must run in the appropriate transaction context (typically the same thread for `PlatformTransactionManager`), using the right manager and managed resource. If a repository uses a different `DataSource`, opens a connection manually, or an `@Async` method runs on another thread, the claim "all in T1" may not hold.

## 6. Java 17+ Demo: Same SQL, Different @Transactional Placement

The following exercise uses **Spring Framework 6.2.12 + Spring JDBC + H2 2.3.232**, running a Java `main`. We intentionally place **@Transactional(REQUIRED)** on both repository methods to prove a crucial point:

- When the orchestrating service also has `REQUIRED`, the repository **joins the outer transaction**.
- When the orchestrating service has no transaction, the repository opens and commits separate transactions on its own.

The code covers three scenarios: **atomic failure** (safe rollback), **fragmented failure** (step-by-step commits exposing broken state), and **atomic success** (committing both steps together).

### 6.1. Create the project structure

~~~text
required-boundary-demo/
├── pom.xml
└── src/main/java/demo/RequiredBoundaryDemo.java
~~~

**pom.xml**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>required-boundary-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
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
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.RequiredBoundaryDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Maven Compiler Plugin targets Java 17; Spring 6.x requires Java 17+. In-memory H2 is suitable for learning yet does not replace integration tests on a real DBMS when concurrency/locking matter.

### 6.2. Complete Java main

**src/main/java/demo/RequiredBoundaryDemo.java**

~~~java
package demo;

import javax.sql.DataSource;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

public final class RequiredBoundaryDemo {
    private RequiredBoundaryDemo() {}

    private static void show(JdbcTemplate jdbc, String label) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM account WHERE id = 2", Integer.class);
        System.out.printf("%s: A=%d, B=%d%n", label, a, b);
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            TransferService service = context.getBean(TransferService.class);
            BalanceRepository repo = context.getBean(BalanceRepository.class);

            jdbc.execute("CREATE TABLE account (" +
                    "id INT PRIMARY KEY, " +
                    "balance INT NOT NULL CHECK (balance >= 0))");
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 1, 100);
            jdbc.update("INSERT INTO account(id, balance) VALUES (?, ?)", 2, 100);

            show(jdbc, "start");
            System.out.println("service proxied=" + AopUtils.isAopProxy(service)
                    + ", repository proxied=" + AopUtils.isAopProxy(repo));

            try {
                service.atomicTransfer(true);
            } catch (IllegalStateException ex) {
                System.out.println("atomic failure caught: " + ex.getMessage());
            }
            show(jdbc, "after atomic failure");

            try {
                service.fragmentedTransfer(true);
            } catch (IllegalStateException ex) {
                System.out.println("fragmented failure caught: " + ex.getMessage());
            }
            show(jdbc, "after fragmented failure");

            // Reset data to run the success branch from the same starting values.
            jdbc.update("UPDATE account SET balance = 100");
            show(jdbc, "after reset");

            service.atomicTransfer(false);
            show(jdbc, "after atomic success");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:required_boundary;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(
                DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }

        @Bean
        public BalanceRepository balanceRepository(JdbcTemplate jdbc) {
            return new BalanceRepository(jdbc);
        }

        @Bean
        public TransferService transferService(BalanceRepository repo) {
            return new TransferService(repo);
        }
    }

    public static class BalanceRepository {
        private final JdbcTemplate jdbc;

        public BalanceRepository(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void debit(int amount) {
            int updated = jdbc.update(
                    "UPDATE account SET balance = balance - ? WHERE id = 1",
                    amount);
            if (updated != 1) {
                throw new IllegalStateException("debit row missing");
            }
        }

        @Transactional(propagation = Propagation.REQUIRED)
        public void credit(int amount) {
            int updated = jdbc.update(
                    "UPDATE account SET balance = balance + ? WHERE id = 2",
                    amount);
            if (updated != 1) {
                throw new IllegalStateException("credit row missing");
            }
        }
    }

    public static class TransferService {
        private final BalanceRepository repo;

        public TransferService(BalanceRepository repo) {
            this.repo = repo;
        }

        // Correct: service creates the outer transaction enclosing both operations.
        @Transactional(propagation = Propagation.REQUIRED)
        public void atomicTransfer(boolean failBetweenSteps) {
            repo.debit(10);
            if (failBetweenSteps) {
                throw new IllegalStateException("simulated failure");
            }
            repo.credit(10);
        }

        // Wrong for a transfer use case: no outer transaction.
        // Each REQUIRED repository method opens/commits on its own when called.
        public void fragmentedTransfer(boolean failBetweenSteps) {
            repo.debit(10);
            if (failBetweenSteps) {
                throw new IllegalStateException("simulated failure");
            }
            repo.credit(10);
        }
    }
}
~~~

**Why can the demo distinguish boundaries accurately?**

- `ApplicationContext` registers **TransferService** and **BalanceRepository** as Spring beans; `main` retrieves them from the context.
- **@EnableTransactionManagement(proxyTargetClass=true)** enables declarative transactions via class-based Spring AOP proxies. Both classes are public, and methods are public and non-final.
- Both **JdbcTemplate** and **JdbcTransactionManager** use the same **DataSource**. No connections are opened manually outside Spring management.
- **atomicTransfer(true)** is invoked through the service proxy, so Spring opens an outer transaction. Both repository methods are REQUIRED; `debit()` joins outer. The exception after `debit()` makes outer roll back, with no physical commit.
- **fragmentedTransfer(true)** has no transaction advice on outer. `debit()` is called through the repository proxy, so it creates a local `REQUIRED` transaction on its own and commits when `debit()` returns. The exception in the coordinator occurs **after that commit**, unable to undo the already-committed `debit()`.
- The success branch **atomicTransfer(false)** executes both UPDATEs and commits them together.
- Each `show(...)` runs **after the service call has finished**; it reads the DB state visible at that moment.

### 6.3. Run and read stdout

On a machine with **JDK 17+** and Maven, inside the `required-boundary-demo` directory:

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout from the program's System.out calls** (excluding Spring/Maven logging):

~~~text
start: A=100, B=100
service proxied=true, repository proxied=true
atomic failure caught: simulated failure
after atomic failure: A=100, B=100
fragmented failure caught: simulated failure
after fragmented failure: A=90, B=100
after reset: A=100, B=100
after atomic success: A=90, B=110
~~~

**Line-by-line analysis:**

1. **start:** A=100 and B=100.
2. **service proxied=true, repository proxied=true:** both beans are wrapped by Spring AOP. This is a necessary signal for annotations to be intercepted in the example; a proxy can wrap other advice too, so behavior must still be verified.
3. **atomic failure:** `debit()` executes the UPDATE without committing separately; the service throws `IllegalStateException` and the transaction manager rolls back T1. Balances stay 100/100.
4. **fragmented failure:** `debit()` opens T2 and commits successfully upon exiting the repository proxy. The service has no transaction, so the subsequent error cannot undo T2. A=90, B=100 — total is only 190, violating the transfer requirement.
5. **reset:** an UPDATE outside the business scenario resets A and B to 100 so the final test is independent of the previous broken scenario.
6. **atomic success:** both `debit()` and `credit()` join the same outer transaction T3 and commit when the service completes. A=90, B=110; total stays 200.

**Key takeaway:** same repository, same two SQL statements, same REQUIRED on the repository, yet **the placement of the outer boundary determines the atomicity of the use case**.

### 6.4. Observing transaction logs (optional)

In a Spring Boot application with logging configuration, temporarily enable:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.support=DEBUG
~~~

Indicators you may observe:

~~~text
Creating new transaction ...
Participating in existing transaction
Initiating transaction rollback
Rolling back JDBC transaction on Connection [...]
Initiating transaction commit
Committing JDBC transaction on Connection [...]
Releasing JDBC Connection [...] after transaction
~~~

For **atomicTransfer(true)**, expect one physical transaction rolled back; for **fragmentedTransfer(true)**, `repo.debit` creates a physical transaction that commits on its own before the service throws an exception. Exact log wording and ordering across loggers vary by Spring version, transaction manager, `DataSource`, and log configuration. Do not treat `"Initiating transaction commit"` in logs as a guarantee that the DBMS committed successfully if an exception follows.

This is a logging pattern for Spring Boot applications; the Java `main` in the example does not automatically read `application.properties` like Boot. To verify the demo, **stdout and post-call DB state** are the primary evidence.

## 7. What Happens If the Repository Has NO @Transactional?

With Spring JDBC, repositories can simply use `JdbcTemplate` and leave all policy to the service:

~~~java
// Snippet: repository is a Spring bean; @Transactional is not required here.
public void debit(int amount) {
    jdbcTemplate.update(
            "UPDATE account SET balance = balance - ? WHERE id = 1", amount);
}

public void credit(int amount) {
    jdbcTemplate.update(
            "UPDATE account SET balance = balance + ? WHERE id = 2", amount);
}
~~~

If the service calls the two methods above from an **outer `@Transactional`**, `JdbcTemplate` obtains the transaction-bound connection through Spring infrastructure, so both statements still run inside one local transaction. **Transaction boundaries do not need to be placed on every layer.**

If a repository is called directly **outside** a service transaction, each SQL statement may run in autocommit mode or per the `DataSource` defaults; thus when business logic needs an atomic sequence, callers must invoke the transactional service.

With JPA, the architectural principle is the same: place `@Transactional` on the application service using the proper **`JpaTransactionManager`** so multiple repositories share the appropriate persistence context/transaction. JPA may flush SQL before commit; **flush is not commit**. Do not blindly choose `JdbcTransactionManager` for JPA.

## 8. When a Service Calls Multiple Child Services

Many applications have an orchestration service calling several domain/application services:

~~~text
CheckoutService.placeOrder()    REQUIRED, creates T1
   |
   +-- InventoryService.reserve()   REQUIRED -> joins T1
   +-- OrderService.create()        REQUIRED -> joins T1
   +-- PaymentRecordService.save()  REQUIRED -> joins T1
   |
   +-- completes -> commit/rollback T1
~~~

This structure works well if all three steps use the same database and the same transaction manager. Each child service keeps its own responsibility, while **the orchestrator owns the consistency boundary** for the use case.

A public method on a child service, when called from another use case with no outer transaction, can still open its own transaction due to REQUIRED. That is the reusability benefit of propagation. However, if another use case requires multiple atomic steps, its caller also needs a proper outer boundary.

### 8.1. What if a child service sets REQUIRES_NEW?

`REQUIRES_NEW` opens an independent physical transaction (when supported by the manager), usually suspending the outer transaction. If a child service commits under `REQUIRES_NEW` and outer later rolls back, the child's changes **may still remain persisted**.

Example:
- `CheckoutService` uses `REQUIRED`.
- `InventoryService.reserve()` uses `REQUIRES_NEW` and commits.
- `OrderService.create()` fails, outer rolls back.
- Stock may have been deducted even though no order exists.

Therefore, do not switch to `REQUIRES_NEW` just to "be sure inner has a transaction". When business rules require rolling back together, **`REQUIRED` is the natural choice**. `REQUIRES_NEW` should only be used when independent commit is an intentional requirement, after evaluating its impact on resource pools and consistency.

### 8.2. What if a child service throws an error and outer catches it?

An inner `REQUIRED` scope can **mark rollback-only** when an exception escapes through its proxy. If outer catches the exception and returns normally, when outer tries to commit, the physical transaction may have to roll back; Spring typically throws **UnexpectedRollbackException** so the caller does not think commit succeeded.

~~~text
Outer REQUIRED T1
  -> Inner REQUIRED T1 throws RuntimeException
  -> Inner interceptor marks T1 rollback-only
  -> Outer catches and continues
  -> Outer finishes normally yet attempts commit
  -> rollback T1 + UnexpectedRollbackException
~~~

Simply catching does not make the transaction "healthy again". If an inner operation marked rollback-only or the DBMS transaction is no longer usable after an error, handle it at the appropriate boundary. Do not swallow errors and return success when the entire use case can no longer commit.

If outer catches an exception raised **inside the same body** before it escapes through any transactional inner scope, the outer interceptor may not see the exception and may still commit if there is no other rollback-only flag. You must trace **which proxies the exception passed through** rather than merely eyeing `try/catch`.

## 9. Factors That Make a Seemingly Right Boundary Fail to Work

### 9.1. Self-invocation bypasses the proxy

~~~java
// Illustrative snippet — not a standalone runnable program.
public void handleRequest() {
    this.transfer(1L, 2L, 10L);
}

@Transactional
public void transfer(long a, long b, long amount) {
    // Two data operations ...
}
~~~

In default Spring AOP proxy mode, a **`this.transfer(...)`** call inside the same object does not go through the proxy, so `@Transactional` on `transfer()` may not be applied. If `handleRequest()` does not open a transaction, each repository call may run separately. Common solutions are invoking the transactional method through **another Spring-managed bean**, placing `@Transactional` on the public entry method, or using `TransactionTemplate` when controlling boundaries in code.

### 9.2. @Transactional on private/final methods or manually instantiated objects

Merely adding the annotation is not enough; the method must actually be intercepted by the transaction infrastructure. Proxy mode, visibility, `final` classes/methods, and Spring version all matter. Spring 6.x supports some non-public methods with class-based proxies, yet **a public service method invoked through a Spring proxy** remains the clearest, easiest-to-test choice for business boundaries. An object created with `new` outside the Spring context is not proxied automatically.

### 9.3. Wrong TransactionManager or DataSource

If `TransferService` uses DataSource A's transaction manager yet the repository accesses DataSource B or opens a raw `DriverManager` Connection itself, the outer transaction **does not cover** B's operations. Two UPDATE statements on two independent databases require an appropriate resource-coordination mechanism or a different consistency architecture.

When multiple transaction managers exist, specify explicitly:
~~~java
// Snippet: manager "billingTxManager" and a matching repository must exist.
@Transactional(transactionManager = "billingTxManager")
public void settleInvoice() {
    // Writes to the billing database.
}
~~~

An annotation only takes effect within the scope of resources managed by that manager, not as an "application-wide global transaction".

### 9.4. @Async, Executors, and other threads

Imperative transactions of `PlatformTransactionManager` are typically bound to the current thread. If a service opens transaction T1 and then hands a JDBC task off to `@Async`/Executor running on a worker thread, that work **does not automatically join T1**. The worker needs its own boundary or an asynchronous architecture with designed consistency. Do not assume an HTTP request's lifecycle encompasses every child task.

With the reactive stack (R2DBC), transaction context is propagated via Reactor Context and `ReactiveTransactionManager`; follow the corresponding reactive pipeline principles instead of blindly copying the ThreadLocal JDBC model.

### 9.5. Checked exceptions and rollback rules

By default `@Transactional` normally requests rollback on `RuntimeException` or `Error`, not on checked `Exception`s by default. If business logic throws a checked exception after a debit step, declare the appropriate policy:

~~~java
// Snippet: BusinessCheckedException is an application checked exception.
@Transactional(rollbackFor = BusinessCheckedException.class)
public void transferWithCheckedRule() throws BusinessCheckedException {
    accounts.debit(...);
    throw new BusinessCheckedException("rejected");
}
~~~

In Spring Framework 6.2, projects can also change the default rollback behavior via `rollbackOn=ALL_EXCEPTIONS` when enabling annotation transaction management. When diagnosing, verify the actual policy rather than assuming all `Exception`s roll back. The code above is **not standalone**; `...` merely indicates arguments to be replaced with valid application data, not runnable code.

## 10. Make Transactions Wide Enough, Yet Not Too Wide

**Right boundary** does not mean "the longer, the safer". If a transactional method includes HTTP calls, sending emails, large file downloads, or heavy computation, connections and DB locks can be held too long, hurting throughput or causing deadlocks.

Comparison:

| Scope | Problem | Design direction |
| --- | --- | --- |
| Single SQL only, when the use case has multiple SQLs needing atomicity | Transaction too narrow, partial commit | Open outer `REQUIRED` at the orchestrating service |
| Entire request, including remote APIs and slow processing | Transaction too wide, holds connections/locks | Prepare data beforehand, open transaction close to DB writes, finish early |
| One use case writing multiple tables in the same database | Usually fits outer `REQUIRED` | Service boundary encloses repository calls |
| One use case writing two DBs/messaging systems | One local transaction cannot cover all | Decide between JTA/XA vs. outbox/saga/idempotency |
| A batch of thousands of independent items | Transaction too huge, expensive rollback | Chunk by business atomicity; document consistency between chunks |
| An order and its mandatory line items | Must not be split into multiple commits | One transaction wrapping order header + lines + required inventory updates |

You can move **input collection/low-risk reads or network calls** outside the transaction, yet watch out for race conditions: data validated before the transaction can change before writes happen. For conditions that must be guaranteed, re-check inside the transaction using constraints, locking, or appropriate optimistic versioning.

A workflow can be split into multiple independent use cases: each use case gets its own transaction. What to avoid is **splitting a single invariant into uncoordinated commits**.

### 10.1. Designing an order placement use case

~~~text
HTTP request
  |
  +-- Parse and validate payload structure (outside transaction)
  |
  +-- CheckoutApplicationService.placeOrder()   @Transactional(REQUIRED)
        |
        +-- Check stock with appropriate data/locking
        +-- Reserve inventory
        +-- Insert order header
        +-- Insert order lines
        +-- Insert outbox event in the same DB (if needed)
        +-- COMMIT or ROLLBACK all DB changes
  |
  +-- After commit: publish/retry outbox event via separate worker
  |
  +-- HTTP response
~~~

Strength: changes in the same DB and the outbox event reside in one local transaction. **Publishing messages to a broker** afterward is normally outside the JDBC transaction; outbox + worker handling retries/idempotency bridges that gap. Similarly, do not send emails inside a transaction expecting a rollback to unsend an email.

### 10.2. Do not lengthen transactions with remote calls

If a payment gateway must be called before recording an order, design consistency around business semantics. No `@Transactional` annotation makes an HTTP call to an external provider participate in JDBC commit/rollback. Depending on requirements, choose reservations, idempotent retries, state machines, outbox/sagas, or distributed transactions with verified support; avoid assuming DB rollback rolls back external systems too.

## 11. Isolation, Timeout, and readOnly: Who Defines Them When Inner REQUIRED Joins?

An inner `REQUIRED` scope can declare its own isolation, timeout, or `readOnly`. Yet if outer has already opened a **physical transaction**, those connection/transaction-level attributes normally follow the **outer boundary**; Spring defaults may **ignore** differing inner attributes when joining.

Example:

~~~java
// Policy illustration snippet; must be called properly through Spring proxy.
@Transactional(isolation = Isolation.READ_COMMITTED, timeout = 15)
public void placeOrder() {
    reserveInventory(); // Inner method has REQUIRED with different isolation.
}

@Transactional(
    propagation = Propagation.REQUIRED,
    isolation = Isolation.SERIALIZABLE,
    timeout = 3
)
public void reserveInventory() {
    // ...
}
~~~

If `reserveInventory()` merely joins the outer transaction, do not assume isolation automatically switches to `SERIALIZABLE` or timeout becomes 3 seconds. If the design requires strict matching, `AbstractPlatformTransactionManager` offers **`validateExistingTransaction=true`** to detect certain mismatches when joining. The right approach remains placing **physical-transaction-level policy** on the appropriate owner boundary.

`readOnly=true` is merely a hint that JDBC/JPA/DBMS may support differently; do not use it in place of DB access permissions. Higher isolation can reduce concurrency; verify with integration tests against a real DB.

## 12. Failure Patterns and Signals to Watch

| Symptom | Possible explanation | Check to perform |
| --- | --- | --- |
| Debit A succeeds, credit B fails, yet A stays reduced | Debit committed separately due to missing outer service transaction | Enable transaction logs; verify proxy/manager, place `REQUIRED` on service |
| Service has `@Transactional` yet does not roll back | Self-invocation, bean created with `new`, caught exception, or unmatched checked exception | Check entry via proxy, rollback rules, escaping exceptions |
| Repository has `REQUIRED` yet every SQL commits | Each method called top-level with no outer transaction | Identify transaction owner and caller location |
| Outer throws `UnexpectedRollbackException` | Inner `REQUIRED` set rollback-only then outer attempted commit | Trace inner exception and logical scopes |
| Two transaction managers and data diverges | Wrong manager/`DataSource`/entity manager | Verify manager names and actual resources |
| `REQUIRES_NEW` leaves side changes despite outer rollback | That is an independent physical transaction, no longer synchronized `REQUIRED` | Determine whether independent commit was intentional or a design bug |
| No transaction observed on method | AOP proxy not enabled, non-interceptable method, or internal call | Check `@EnableTransactionManagement`, bean/proxy, method signature |
| Database deadlock/pool timeout | Transaction holds locks too long or nested `REQUIRES_NEW` | Inspect transaction duration, locks, pool metrics |
| JPA flushed yet outer rolled back | Flush is not commit; final transaction rolled back | Re-read data with a fresh transaction/`EntityManager` |
| Local commit finished yet message publish failed | Broker is outside the JDBC transaction | Use outbox/retry/idempotency or an appropriate design |

You can enable loggers:
~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.support=DEBUG
~~~

Observe **Creating new transaction** or **Participating in existing transaction**, followed by **Initiating transaction commit/rollback** and **Releasing JDBC Connection**. Logs are traces, not a substitute for inspecting DB state after the transaction. Under concurrent requests, correlation IDs are needed to match lines accurately.

## 13. Testing the Real Boundary

A good integration test must prove the transaction is not fragmented, rather than merely mocking repositories:

1. Initialize DB with A=100, B=100.
2. Call the service through its Spring bean proxy with `failBetweenSteps=true`.
3. Read balances after the exception is caught **outside the transaction boundary**.
4. Assert A=100 and B=100 — no partial commit.
5. Call the success branch; assert A=90, B=110.
6. Test a separate repository call path to observe the difference without a service boundary.
7. If using JPA, verify with a fresh `EntityManager`/transaction rather than reading stale entities in the persistence context.
8. If concurrency matters, run integration tests on a real DBMS with independent transactions and appropriate contention/locking.

Example expectation table:

| Test case | Initial | Scenario | State after completion |
| --- | --- | --- | --- |
| Atomic success | A=100 B=100 | Service `REQUIRED`, both steps succeed | A=90 B=110 |
| Atomic rollback | A=100 B=100 | Service `REQUIRED`, failure after debit | A=100 B=100 |
| Unrecoverable fragmented rollback | A=100 B=100 | Service has no transaction; debit repository commits on its own, then error | A=90 B=100 |
| Checked exception | A=100 B=100 | Service throws checked exception | Depends on `rollbackFor`/default policy |
| Inner `REQUIRED` marks rollback-only | A=100 B=100 | Outer tries to commit yet inner requested rollback | DB rolls back; caller may receive `UnexpectedRollbackException` |

**Warning about `@Transactional` on tests:** Spring TestContext may roll back the test's transaction at the end by default; reading data inside the same test transaction does not prove a physical commit occurred. To test a service's transaction, design the test boundary or use `TestTransaction`/an independent transaction appropriately. Running the `main` demo in section 6 helps avoid this confusion.

### Testing before/after architectural refactoring

When moving `@Transactional` from DAOs up to the service, do not just edit annotations. You should:

- Document all **use cases** calling multiple repository methods.
- Identify current commit points and where partial updates could have occurred.
- Choose the new service boundary, ensuring repositories and manager share the same resource.
- Preserve rollback rules for checked/business exceptions if any.
- Write regression tests for failures after the first step, between steps, and at commit.
- Test service calls through Spring beans/proxies, not by instantiating `new` objects in unit tests and assuming transactions ran.
- Where multiple managers and databases exist, clearly separate use cases that cannot reside in one local transaction.

## 14. Self-Check Questions

**Question 1.** Both repository methods have `@Transactional(REQUIRED)`. Does that guarantee `transfer()` calling them will be atomic?  
**Answer:** Not if `transfer()` has no outer transaction. Each repository method can create and commit its own physical transaction.

**Question 2.** If `TransferService.transfer()` has `REQUIRED`, while repository methods have NO annotation, does `JdbcTemplate` still join the transaction?  
**Answer:** Yes, when they use the right Spring-managed `DataSource`/`JdbcTemplate`, executing within the service's transaction context and matching transaction manager. Repositories do not need to create new boundaries.

**Question 3.** If outer `transfer()` and inner `debit()` both use `REQUIRED`, does `debit()` returning mean debit committed?  
**Answer:** No. Inner joins the same physical transaction; the outer owner decides the final commit/rollback.

**Question 4.** If inner `debit()` uses `REQUIRES_NEW` and commits, does an outer rollback undo the debit?  
**Answer:** Normally no. Inner `REQUIRES_NEW` is an independent physical transaction; this is why propagation must be chosen according to business requirements.

**Question 5.** Why is `@Transactional` at the controller usually not the first choice?  
**Answer:** A controller can enclose web/IO steps that do not need to hold a DB transaction. An application service boundary is cleaner and makes it easier to minimize connection/lock hold times.

**Question 6.** Why can outer still receive `UnexpectedRollbackException` after catching an exception from inner `REQUIRED`?  
**Answer:** The inner transactional scope may have marked the physical transaction rollback-only. Outer attempts to commit yet the DB must roll back, so Spring signals the caller that it cannot treat it as a successful commit.

**Question 7.** What is the issue with placing the annotation on the service and then calling `this.transfer()` within the same object?  
**Answer:** In proxy mode, self-invocation usually bypasses the proxy, so metadata on `transfer()` does not create a new transaction. Design the entry point through a Spring bean proxy.

**Question 8.** A use case writes an order to DB A and sends an email. Can `@Transactional` on the service roll back the email when the DB fails?  
**Answer:** No. Email is a side effect outside the local JDBC transaction; you need post-commit sending, outbox, retries, or compensation depending on requirements.

**Question 9.** Is it always better for a transaction to enclose as many methods as possible?  
**Answer:** No. The boundary should enclose DB operations that need ACID together, yet must not hold transactions across network calls or unnecessary long processing.

**Question 10.** Inner `REQUIRED` declares `SERIALIZABLE` while outer already opened `READ_COMMITTED`; which isolation usually applies?  
**Answer:** The outer physical transaction's attribute normally remains in effect. Spring defaults may ignore inner's isolation declaration when joining; check `validateExistingTransaction` if you want to catch mismatches.

## 15. Conclusion: Choose Boundaries Based on Consistency

- **The use-case orchestrating method is the natural place for REQUIRED** when multiple operations on the same transaction resource must commit or roll back together.
- **A repository is a data-access unit**, not the arbiter of where an entire business operation ends; `REQUIRED` on a repository only *joins an existing transaction or creates one when none exists*.
- **One physical transaction per business invariant** prevents states like "debited yet not credited".
- **Do not look only at annotations:** ensure calls go through proxies, use the right manager/resource, and verify rollback rules and transaction context.
- **Do not make transactions too wide:** avoid holding locks/connections across HTTP calls or long work; multi-resource systems need dedicated consistency designs.
- **Verify with integration tests:** intentionally fail after the first step and read the DB after the transaction to prove no partial commit occurred.

In the Java example, the exact same two repository methods yielded two different outcomes: outer `REQUIRED` rolled back safely, whereas outer without a transaction left a partial commit. That directly illustrates why **the boundary belongs on the orchestrating service, not just on each small operation**.

## References

- [Spring Framework — Transaction Propagation, especially PROPAGATION_REQUIRED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Framework — Transaction Strategies](https://docs.spring.io/spring-framework/reference/data-access/transaction/strategies.html)
- [Spring Framework — Programmatic Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/programmatic.html)
