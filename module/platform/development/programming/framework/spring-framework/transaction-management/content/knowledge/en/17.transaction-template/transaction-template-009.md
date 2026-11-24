# Comparing the Coupling of `TransactionTemplate` with Declarative Transaction Management

## Conclusion First: Where Does the Difference Lie?

In Spring Framework, **`TransactionTemplate` (programmatic transaction management)** causes code to **call Spring's transaction API directly** to define transaction boundaries. Conversely, **declarative transaction management**—most commonly `@Transactional`—places *metadata* outside the business processing flow; a transaction interceptor and transaction manager coordinate begin/commit/rollback without the business method having to write a transaction-management callback itself.

According to Spring's documentation, `TransactionTemplate` **directly couples** application code to Spring's transaction infrastructure and APIs. This is a disadvantage in terms of source-code coupling, though it does not mean this approach is wrong or always hard to maintain. In return, it offers the ability to proactively place very explicit transaction boundaries, control rollback with `TransactionStatus`, assign transaction names, and choose dedicated policies for a block of code.

**`@Transactional` is not completely "decoupled" from Spring.** The `org.springframework.transaction.annotation.Transactional` annotation is still a Spring import, and the system still needs a `TransactionManager`, AOP proxy, or suitable AspectJ weaving. The difference lies in **the degree of coupling inside the method body and the code organization model**:

- With `TransactionTemplate`, the service must know the concepts of callbacks, templates, and possibly `TransactionStatus`.
- With `@Transactional`, the service mainly describes transaction semantics via annotations; the method body focuses on logic.
- With declarative configuration via **XML advice/pointcuts** or an application-defined facade, the business class may need to import neither Spring's transaction APIs nor Spring's annotations, though this pays the cost of configuration and boundary conventions elsewhere.
- **Both approaches still need Spring transaction infrastructure at runtime.** Changing syntax does not make JDBC/JPA/DB transactions operate by themselves without a transaction manager.

This lesson belongs to the parent topic **TransactionTemplate**, focusing on **coupling compared to declarative management**: source-code coupling, infrastructure, testability, refactoring, AOP/self-invocation, flexibility, and selection criteria. A complete Java 17/Spring JDBC/H2 example uses **the exact same business processing core**, run in turn with `TransactionTemplate` and `@Transactional`, to prove the difference lies mainly in **how transaction boundaries are organized**, not in the nature of database commit/rollback.

---

## 1. What Is "Coupling" in Transaction Management?

**Coupling** is the degree to which one component must know about or depend on another component in order to compile, execute, be tested, and change behavior. In the context of transactions, we should separate at least four dimensions rather than merely counting annotations.

| Coupling dimension | Question to answer |
| --- | --- |
| **Source/API coupling** | Does the business class import `TransactionTemplate`, `TransactionStatus`, `@Transactional`, or directly call `PlatformTransactionManager`? |
| **Configuration coupling** | Are transaction boundaries and attributes declared on the method, in an adapter, in XML, or in separate configuration? |
| **Runtime/infrastructure coupling** | How does the code rely on a `TransactionManager`, datasource/JPA persistence unit, Spring context, and AOP proxy? |
| **Behavioral coupling** | Does business logic assume the caller already has a transaction, or that an inner call is intercepted by proxy advice, or that a transaction is held inside a callback? |

Example of a service implementing a stock-receiving step:

```java
@Transactional
public void receiveStock(Shipment shipment) {
    warehouse.updateQuantity(shipment);
    auditRepository.recordReceipt(shipment);
}
```

This is an **illustrative fragment**, needing declared dependencies and types. The method imports Spring's annotation, yet does not itself know how to begin or commit a transaction; those tasks are the infrastructure's responsibility.

Compared to:

```java
public void receiveStock(Shipment shipment) {
    transactionTemplate.executeWithoutResult(status -> {
        warehouse.updateQuantity(shipment);
        auditRepository.recordReceipt(shipment);
    });
}
```

This is also an **illustrative fragment**. The method adds a `TransactionTemplate` object and Spring's callback API. That makes the **transaction concern more visible in the flow**, which is both beneficial when a local boundary is needed and creates a direct source-level dependency on Spring inside the class.

You cannot simply read two fragments and conclude "the second approach runs slower" or "the first approach is completely framework-independent"; performance depends on the DB, AOP, SQL, contention, and architecture.

## 2. `TransactionTemplate`: Transactions Programmed Directly

`TransactionTemplate` resides in package:

```java
org.springframework.transaction.support.TransactionTemplate
```

Typical usage:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);

String result = template.execute(status -> {
    repository.insert();
    return "created";
});
```

This is a **fragment** needing `transactionManager`, `repository`, and imports. When `execute(...)` is called, the template obtains a transaction according to its configured properties, runs the callback, and coordinates commit/rollback/cleanup. If the callback throws a `RuntimeException` or `Error`, the template handles rollback per its contract and lets the exception escape.

When no return value is needed:

```java
template.executeWithoutResult(status -> {
    repository.update();
});
```

A callback can use `status.setRollbackOnly()` in a business situation where it decides not to commit:

```java
String outcome = template.execute(status -> {
    boolean canReserve = repository.isAvailable();
    if (!canReserve) {
        status.setRollbackOnly();
        return "NOT_AVAILABLE";
    }
    repository.reserve();
    return "RESERVED";
});
```

These fragments are not standalone programs. In the `NOT_AVAILABLE` branch, the template is asked to roll back and returns a normal result. **The caller must understand this result does not represent a committed transaction.** Moreover, if the template uses `REQUIRED` propagation and is joining a caller's transaction, rollback-only can affect the shared transaction; do not assume it is a "callback-only rollback".

### 2.1. Concrete API Coupling

A service using the template typically holds:

```java
private final TransactionTemplate transactionTemplate;
```

and receives `PlatformTransactionManager` or the template itself via constructor injection. That puts Spring transaction API types into the service source code. If the application later migrates to a non-Spring runtime, those calls must be replaced or wrapped.

However, **the entire domain model does not have to depend on Spring**: you can place the template in an application coordinator/adapter layer while the business core uses repository interfaces or its own abstractions. That is an architectural choice rather than a mandatory limitation of the template.

### 2.2. Template vs. Manually Calling `getTransaction`, `commit`, `rollback`

Manual management is possible using `PlatformTransactionManager`, `TransactionDefinition`, and `TransactionStatus`, but then business code must handle lifecycle and exceptions safely:

```java
TransactionStatus status = manager.getTransaction(definition);
try {
    executeBusinessLogic();
    manager.commit(status);
} catch (RuntimeException ex) {
    if (!status.isCompleted()) {
        manager.rollback(status);
    }
    throw ex;
}
```

This is an **illustrative fragment**; `manager`, `definition`, and `executeBusinessLogic()` must be defined. Complete manual code would also have to handle exceptions in `commit`/`rollback` properly to avoid double rollback or masking original errors. `TransactionTemplate` removes much of that boilerplate; when comparing against `@Transactional`, use **the template**, not manual `PlatformTransactionManager` management as the mandatory representative of programmatic management.

## 3. Declarative Management: `@Transactional` Places Policy Outside the Method Body

In Spring Java configuration, the declarative style is typically:

```java
@Configuration
@EnableTransactionManagement
public class TransactionConfiguration {
    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }
}
```

This is a **fragment**, needing a configured `DataSource` and imports. `@EnableTransactionManagement` infrastructure reads `@Transactional` metadata, creates a transaction advisor/interceptor, and builds appropriate proxies. In an XML application context, it can be enabled with `<tx:annotation-driven/>`.

Declarative service:

```java
@Service
public class BookingService {
    private final BookingRepository bookings;

    public BookingService(BookingRepository bookings) {
        this.bookings = bookings;
    }

    @Transactional
    public void book(long seatId) {
        bookings.reserve(seatId);
        bookings.recordReservation(seatId);
    }
}
```

This is a fragment without the repository implementation. There is no `TransactionTemplate` or `TransactionStatus` inside `book()`. Transaction semantics belong to the annotation, while the interceptor and manager execute them.

High-level flow:

```text
Caller
  |
  +--> Spring-managed proxy of BookingService
          |
          +--> TransactionInterceptor
          |       +-- reads @Transactional metadata
          |       +-- manager.getTransaction(definition)
          |
          +--> target.book(seatId)
          |
          +--> manager.commit(...) or rollback(...)
```

Business code barely needs to know transaction APIs, yet it carries an **implicit precondition**: the method must be called in a way that the advice infrastructure actually intercepts.

### 3.1. Annotations Are Still a Form of Coupling

Spring's `@Transactional` brings in imports and specific attributes such as `Propagation.REQUIRES_NEW`, `Isolation.SERIALIZABLE`, `rollbackFor`, `readOnly`, `timeout`, and `transactionManager`. These are source-code dependencies if declared directly in business services.

You can use `jakarta.transaction.Transactional` in suitable Spring models, though its semantics and attribute set do not match every option of Spring's annotation. Do not treat swapping annotations as a zero-cost framework migration.

If maximum **source-level framework neutrality** is desired for domain logic, keep annotations outside the domain core or configure transaction advice via method pointcuts (section 10). Even then, coupling is **moved to configuration/adapters**, not eliminated.

### 3.2. Runtime Coupling Still Exists

Without a valid transaction manager, a coordinated datasource/persistence resource, or calls passing through the Spring proxy, `@Transactional` does not provide commit/rollback by itself. Both templates and declarative management rely on Spring's transaction infrastructure and the DB backend.

Switching to declarative does not guarantee two independent datasources will run in a single distributed transaction. Selecting the manager and coordinating resources remain design responsibilities.

## 4. Comparison Matrix Across Coupling Dimensions

| Criterion | `TransactionTemplate` | Declarative `@Transactional` |
| --- | --- | --- |
| Source-code dependencies | Uses `TransactionTemplate` and possibly `TransactionStatus`, `PlatformTransactionManager` | Usually only imports the annotation; does not directly call lifecycle APIs in the body |
| Transaction boundary seen from method | **Explicit** around the `execute(...)` block | **Declared** on method/class, executed by AOP advice |
| Degree of mixing transactions with business logic | Higher if template is written directly inside the business flow | Usually lower since transaction code sits outside the method body |
| Readability if most methods are transactional | Repetitive callbacks/template usage | Read annotation and follow business flow naturally |
| Ease of placing a boundary around a small block | Convenient; can sit before/after non-transactional steps | Requires choosing a suitable annotated method or splitting beans/boundaries |
| Relies on AOP proxy for transactions | No, `template.execute()` itself is the boundary | Yes in default `proxy` mode; can use AspectJ when woven |
| Self-invocation | Callback still executes if internal call actually runs `execute()` | `this.otherMethod()` does not trigger inner advice in proxy mode |
| `rollback-only` on internal condition | `status.setRollbackOnly()` right inside callback | Direct API is possible yet couples body to Spring; exception/rollback rules are more common |
| Checked exception rollback rules | Must be expressed clearly by throwing suitable error, wrapping, or marking rollback-only | Declare `rollbackFor`/`noRollbackFor`; exception still must escape advice |
| Configuration reuse | Template holds propagation/isolation/timeout config; use suitable stable instances | Annotation/class/composed-annotation metadata, or XML advice/pointcuts |
| Custom transaction name | Can be set programmatically | Declarative name is usually auto-generated `fully.qualified.Class.method` |
| Impact on service unit testing | Needs template/manager or placing transaction orchestration outside core | Body logic can be unit-tested like a POJO, yet unit tests do not verify real transactions |
| Integration testing | Must verify transaction resources/rollback, just like declarative | Must verify proxy/context/rollback, in addition to resources |
| Setup cost | No need to enable annotation proxies for the template itself | Must enable annotation-driven advice / AOP configuration |
| Suitable cases | Few operations, dynamic/local boundaries, explicit per-callback control | Many transactional use cases, stable policies on service methods |

**How to read the table properly:** This is a comparison of **organization styles**, not a claim that one direction is always "better" or faster. If `TransactionTemplate` is placed in a separate transaction adapter, the domain core can have very little coupling. If `@Transactional` is sprinkled across domain entities or misused with self-invocation, declarative code can also become messy.

## 5. Why Does Spring Recommend Each Approach in Different Situations?

Spring documentation on choosing between programmatic and declarative management offers this guidance:

- **Few transactional operations:** programmatic `TransactionTemplate` can be a sensible choice, especially when you do not want to set up transaction proxies just to handle a few update sections.
- **Many transactional operations:** declarative is usually worth the investment because it separates transaction management from business logic and its configuration cost in Spring is relatively low.

This is a **heuristic**, not a rigid threshold like "under 10 methods must use template". Frequency of policy changes, team familiarity, domain architecture, testability, and special rollback needs also matter.

### 5.1. Applications with Many Services Having Stable Contracts

For example, dozens of service methods simply needing `REQUIRED`, `readOnly=true` for queries, and uniform rollback rules: using `@Transactional` on application services makes boundaries quick to spot and avoids repetitive callbacks. Business logic does not have to know `TransactionStatus`.

### 5.2. An Operation with a Boundary in the Middle of a Method

Suppose an application has a long flow:

```text
Validate request (not holding DB transaction)
   |
   v
Call external pricing API (not holding DB transaction)
   |
   v
Only one INSERT/UPDATE block must be atomic
   |
   v
Only after commit, send notification
```

With a template, wrapping `execute(...)` solely around the DB block is very direct. With declarative, you can still extract a separate `@Transactional` Spring bean method and achieve the same effect. Which option is clearer depends on the architecture; do not conclude annotations cannot create a small transaction boundary.

### 5.3. Pure Domain and Adapter Architecture

A domain core should focus on rules like pricing, limits, and inventory allocation; it can use plain Java interfaces. `TransactionTemplate` can live in an application coordinator calling the domain, or `@Transactional` can sit on an application service rather than on entities/value objects. Both can achieve domain purity when structured properly.

## 6. Do Transaction Semantics Differ Fundamentally?

**No.** When configured equivalently and invoked across the proper boundary, both approaches interact with `PlatformTransactionManager` and the backend resource, so fundamental semantics such as `REQUIRED`, `REQUIRES_NEW`, isolation, timeout, read-only, and commit/rollback can be identical.

Programmatic example:

```java
TransactionTemplate template = new TransactionTemplate(manager);
template.setPropagationBehavior(
    TransactionDefinition.PROPAGATION_REQUIRES_NEW);
template.setIsolationLevel(
    TransactionDefinition.ISOLATION_READ_COMMITTED);
template.setTimeout(20);
template.setReadOnly(false);
```

And declarative:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    isolation = Isolation.READ_COMMITTED,
    timeout = 20,
    readOnly = false
)
public void updateStock() {
    // ...
}
```

These are **two illustrative fragments**. They can request equivalent behavior when the manager/resource match, yet they do not guarantee every runtime situation is identical: `@Transactional` must be intercepted by advice; the template must actually have its callback invoked; default settings and call sites must align.

### 6.1. `REQUIRED` Does Not Always Open a New Transaction

Whether invoked via template or annotation, `REQUIRED` joins an existing transaction if one is present. `TransactionTemplate` **does not automatically create an independent transaction** merely because it is called programmatically. If a separate physical transaction is truly needed when T1 already exists, choose `REQUIRES_NEW` and understand suspension/resource requirements.

### 6.2. Exception and Commit Timing

- With a template, exceptions can escape `execute(...)` while the callback runs or during commit.
- With declarative, exceptions can escape **the proxy call** while the target method runs or when the interceptor commits after the target has returned.
- Both can raise `UnexpectedRollbackException` if a shared transaction was marked rollback-only while an outer scope still tries to commit.
- Inside a callback joining an outer transaction, `status.setRollbackOnly()` can prevent outer from committing; the template does not create a separate commit point while joining.

Therefore, never retry inside the same physical transaction that has already been marked rollback-only in **either** approach. A retry coordinator usually needs to sit **outside** the transaction boundary so each attempt creates a fresh transaction properly.

## 7. Standalone Java 17 Example: Same Logic, Two Ways to Place the Boundary

### 7.1. Illustration Goal

To compare coupling fairly, we keep **the exact same class executing SQL**, named `TransferCore`, and create two coordinators:

- `TemplateTransferService` holds a `TransactionTemplate` and calls `executeWithoutResult(...)`.
- `DeclarativeTransferService` declares `@Transactional` on its method, while its body simply calls `TransferCore`.

Each approach runs once **failing after the first UPDATE** and once **succeeding**. With the same `JdbcTransactionManager` and `DataSource`, DB outcomes after rollback/commit must be equivalent.

The example uses **Java 17+**, **Maven 3.9+**, **Spring Framework 6.2.19**, **Spring JDBC**, and **H2 in-memory 2.3.232**. Spring Boot is omitted so annotation-driven infrastructure is clearly visible. The program is a transaction illustration; it does not handle overdraft protection, concurrent locking, or transfer idempotency, so it is not production financial code.

### 7.2. Project Structure

```text
tx-coupling-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── TxCouplingDemo.java
```

File `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>tx-coupling-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring.version>6.2.19</spring.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>${spring.version}</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.3.232</version>
            <scope>runtime</scope>
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
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` provides IoC/Java configuration; `spring-jdbc` provides `JdbcTemplate`, datasource, and `JdbcTransactionManager`; H2 is only needed at runtime. `@EnableTransactionManagement` and Spring's transaction interceptor are registered via Java configuration.

### 7.3. Complete `TxCouplingDemo.java` Source

File `src/main/java/demo/TxCouplingDemo.java`:

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

@Configuration
@EnableTransactionManagement
public class TxCouplingDemo {

    @Bean
    DataSource dataSource() {
        DriverManagerDataSource ds = new DriverManagerDataSource();
        ds.setDriverClassName("org.h2.Driver");
        ds.setUrl("jdbc:h2:mem:tx_coupling;DB_CLOSE_DELAY=-1");
        ds.setUsername("sa");
        ds.setPassword("");
        return ds;
    }

    @Bean
    JdbcTemplate jdbcTemplate(DataSource ds) {
        return new JdbcTemplate(ds);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource ds) {
        return new JdbcTransactionManager(ds);
    }

    @Bean
    TransferCore transferCore(JdbcTemplate jdbc) {
        return new TransferCore(jdbc);
    }

    @Bean
    TemplateTransferService templateTransferService(
            PlatformTransactionManager manager, TransferCore core) {
        return new TemplateTransferService(manager, core);
    }

    @Bean
    DeclarativeTransferService declarativeTransferService(TransferCore core) {
        return new DeclarativeTransferService(core);
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(
                             TxCouplingDemo.class)) {

            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);

            jdbc.execute("""
                    CREATE TABLE accounts (
                        id INT PRIMARY KEY,
                        balance INT NOT NULL
                    )
                    """);
            jdbc.update(
                    "INSERT INTO accounts(id, balance) VALUES(1, 100)");
            jdbc.update(
                    "INSERT INTO accounts(id, balance) VALUES(2, 50)");

            TemplateTransferService template =
                    context.getBean(TemplateTransferService.class);
            DeclarativeTransferService declarative =
                    context.getBean(DeclarativeTransferService.class);

            System.out.println("BEFORE=" + balances(jdbc));

            try {
                template.transfer(20, true);
            } catch (IllegalStateException ex) {
                System.out.println("TEMPLATE_FAILURE=" + ex.getMessage());
            }
            System.out.println(
                    "AFTER_TEMPLATE_ROLLBACK=" + balances(jdbc));

            template.transfer(20, false);
            System.out.println(
                    "AFTER_TEMPLATE_COMMIT=" + balances(jdbc));

            jdbc.update(
                    "UPDATE accounts SET balance = 100 WHERE id = 1");
            jdbc.update(
                    "UPDATE accounts SET balance = 50 WHERE id = 2");
            System.out.println("RESET=" + balances(jdbc));

            try {
                declarative.transfer(20, true);
            } catch (IllegalStateException ex) {
                System.out.println("DECLARATIVE_FAILURE=" + ex.getMessage());
            }
            System.out.println(
                    "AFTER_DECLARATIVE_ROLLBACK=" + balances(jdbc));

            declarative.transfer(20, false);
            System.out.println(
                    "AFTER_DECLARATIVE_COMMIT=" + balances(jdbc));
        }
    }

    private static String balances(JdbcTemplate jdbc) {
        Integer a = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = 1", Integer.class);
        Integer b = jdbc.queryForObject(
                "SELECT balance FROM accounts WHERE id = 2", Integer.class);

        return "A=" + a + ", B=" + b;
    }

    public static final class TransferCore {
        private final JdbcTemplate jdbc;

        public TransferCore(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        public void move(int amount, boolean fail) {
            if (amount <= 0) {
                throw new IllegalArgumentException(
                        "amount must be positive");
            }

            int debit = jdbc.update(
                    "UPDATE accounts SET balance = balance - ? "
                    + "WHERE id = 1", amount);

            if (debit != 1) {
                throw new IllegalStateException("source missing");
            }

            if (fail) {
                throw new IllegalStateException("simulated");
            }

            int credit = jdbc.update(
                    "UPDATE accounts SET balance = balance + ? "
                    + "WHERE id = 2", amount);

            if (credit != 1) {
                throw new IllegalStateException("destination missing");
            }
        }
    }

    // Programmatic: direct dependency on Spring transaction API.
    public static class TemplateTransferService {
        private final TransactionTemplate tx;
        private final TransferCore core;

        public TemplateTransferService(
                PlatformTransactionManager manager, TransferCore core) {
            this.tx = new TransactionTemplate(manager);
            this.core = core;
        }

        public void transfer(int amount, boolean fail) {
            tx.executeWithoutResult(status -> core.move(amount, fail));
        }
    }

    // Declarative: metadata on method, body only handles business logic.
    public static class DeclarativeTransferService {
        private final TransferCore core;

        public DeclarativeTransferService(TransferCore core) {
            this.core = core;
        }

        @Transactional
        public void transfer(int amount, boolean fail) {
            core.move(amount, fail);
        }
    }
}
```

**Why are the two branches comparable?**

- Both use **the same `TransferCore`**, same `JdbcTemplate`, same `JdbcTransactionManager`, and one H2 datasource.
- Both default transaction boundaries use `PROPAGATION_REQUIRED`, read-write, and roll back on `IllegalStateException` uncaught within the transactional invocation scope.
- `TemplateTransferService` is a Spring bean yet **does not need a transaction proxy** for `transfer()`: the `tx.executeWithoutResult` callback directly creates the transaction scope.
- `DeclarativeTransferService` is a Spring bean returned by the container **as a transactional proxy** thanks to `@EnableTransactionManagement`; calls from `main` must go through that bean, never instantiated directly via `new DeclarativeTransferService(...)` outside Spring.
- `TransferCore` does not open/commit transactions itself. It runs SQL on the connection synchronized by Spring JDBC with the current transaction.

### 7.4. Running and Reading Stdout

In the `tx-coupling-demo` directory:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.TxCouplingDemo
```

Lines printed **by the program itself**, ignoring Maven/Spring logs:

```text
BEFORE=A=100, B=50
TEMPLATE_FAILURE=simulated
AFTER_TEMPLATE_ROLLBACK=A=100, B=50
AFTER_TEMPLATE_COMMIT=A=80, B=70
RESET=A=100, B=50
DECLARATIVE_FAILURE=simulated
AFTER_DECLARATIVE_ROLLBACK=A=100, B=50
AFTER_DECLARATIVE_COMMIT=A=80, B=70
```

Exact explanation:

1. H2 receives two initial rows: account 1 has 100, account 2 has 50.
2. `template.transfer(20,true)` opens a transaction; debit succeeds, then `IllegalStateException("simulated")` escapes the callback. Template rolls back. Balances stay 100/50.
3. `template.transfer(20,false)` debits 20, credits 20, and commits. Balances become 80/70.
4. The program resets both balances to 100/50 with SQL outside the two test transactions.
5. `declarative.transfer(20,true)` is called through the transactional proxy. Target method throws exception after debit; interceptor rolls back. Balances stay 100/50.
6. `declarative.transfer(20,false)` returns normally; interceptor commits. Balances again become 80/70.

**Lesson takeaway:** DB transaction outcomes are **identical** when boundaries and managers are equivalent. The difference is clearly seen in code: template requires a `TransactionTemplate` field and callback; declarative only has an annotation on the method while the body calls `core.move(...)`.

**Limitations:** The example does not simulate concurrent transfers, insufficient funds, lock isolation, complex transaction propagation, or multiple datasources. Do not use it as a production payment system.

## 8. Testability: Unit Tests and Integration Tests Must Be Distinguished

The claim "`@Transactional` is easier to test than template" is only true if you define clearly **which part is being tested**.

### 8.1. Unit Testing the Business Core

In the example, `TransferCore` still depends on `JdbcTemplate`. To test domain rules completely without Spring, you can extract SQL behind an `AccountPort` interface and inject a fake implementation. That works **in both choices**.

```java
public interface AccountPort {
    int balance(long accountId);
    void debit(long accountId, int amount);
    void credit(long accountId, int amount);
}
```

This is an **interface fragment**. The domain service only knows `AccountPort`, needing neither `JdbcTemplate` nor transactions. In the application adapter:

- You can wrap `domain.transfer(...)` with a template.
- Or use a `@Transactional` annotated application service calling `domain.transfer(...)`.

Spring-independence of the **domain core** is a result of dependency inversion and where transaction boundaries are placed, not an automatic consequence of picking `@Transactional`.

### 8.2. Unit Testing an Annotated Method

If you instantiate `new DeclarativeTransferService(fakeCore)` directly in a unit test, the annotation is just metadata: it **does not open a transaction** without Spring AOP infrastructure. That unit test can check flow/exceptions, yet cannot prove rollback.

To verify real transactions, the test needs a Spring context, an appropriate transaction manager, a datasource, and **calls going through the proxy**. Read DB state after the transactional boundary, especially after a failure between two SQL statements.

### 8.3. Unit Testing a Template-Based Method

A `TemplateTransferService` directly requires `TransactionTemplate`/`PlatformTransactionManager`. You can mock it or use a fake coordinator to verify the callback is invoked, yet mocking the transaction lifecycle does not replace integration tests.

If the architecture puts the template in an adapter and leaves the core as a POJO, unit tests of the core remain independent. Choose test styles per layer rather than conflating business logic tests with transaction integration tests.

### 8.4. Tests Using `@Transactional` on the Test Method

Spring Test can open a transaction itself and roll it back at the end of the test. This can hide bugs:

- A method under test missing its proxy still runs inside the test-created transaction.
- `TransactionTemplate(REQUIRED)` can join the test transaction instead of starting a new one as you assumed.
- Read-only/isolation on an inner annotation may not take effect because it joined the outer transaction.

When verifying a **service's** commit/rollback boundary, invoke it from a test context without a matching transaction or observe outcomes after the test transaction ends. Use rollback/commit integration tests with clear fail/success cases.

## 9. AOP Proxies, Self-Invocation, and Hidden Coupling Factors

In default proxy mode, `@Transactional` only intercepts calls **passing through the Spring proxy**. If a class has:

```java
@Service
public class OrderService {
    public void submit() {
        persist(); // this.persist() -> bypasses Spring proxy
    }

    @Transactional
    public void persist() {
        // DB write
    }
}
```

This is an **illustrative fragment**, without a repository. A caller invoking `submit()` through the proxy does not cause the inner `persist()` call to be intercepted by advice again. Hence the transaction boundary the developer thought existed on `persist()` may not exist.

In the programmatic version:

```java
public void submit() {
    persist();
}

public void persist() {
    tx.executeWithoutResult(status -> {
        // DB write
    });
}
```

This is a fragment. Even though `submit()` and `persist()` are in the same class, when execution actually reaches `tx.execute...`, the template still coordinates the transaction. No AOP proxy is needed for the callback. That is an advantage of an explicit boundary, though it **does not** mean the template always starts a new transaction: with `REQUIRED` propagation, it still joins an existing transaction if present.

### 9.1. Do Not Conclude "`@Transactional` Only Works on Public Methods" for All Setups

With Spring 6.0+, class-based proxies can support package-visible/protected methods in some situations. However, interface-based JDK proxies only expose public methods on the interface, and self-invocation still bypasses advice. To minimize surprises across proxy types and keep testing easy, public transaction boundaries on application services are usually the simplest choice.

AspectJ weaving can intercept self-invocation if `spring-aspects`/weaving is configured properly. Merely writing `mode="aspectj"` or `@EnableAspectJAutoProxy` does not turn unwoven code into transaction-aspect-woven code.

### 9.2. The Cost of Explicitness

`TransactionTemplate` lets developers see the boundary right inside the method and easily avoid self-invocation bugs. In return, business/application code must decide when to open transactions, which configuration to use, and when to set rollback-only. The same concern can get duplicated across services if not extracted into an abstraction.

Declarative reduces boilerplate yet carries **coupling to bean/proxy invocation mechanics** and transaction placement conventions. Therefore, you must design boundaries properly, test proxies, and have debugging mechanisms.

## 10. Declarative Does Not Necessarily Mean Using Spring Annotations in Source Code

There is an XML-configured declarative option: applying transaction advice via method patterns and AOP pointcuts. The business class **does not need `@Transactional`**:

```java
package demo;

public class AccountApplicationService {
    public void transfer() {
        // Business SQL/repository
    }
}
```

In Spring XML (fragment needing datasource, transactionManager, and corresponding namespaces):

```xml
<tx:advice id="txAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="transfer" rollback-for="java.lang.Exception"/>
        <tx:method name="get*" read-only="true"/>
        <tx:method name="*"/>
    </tx:attributes>
</tx:advice>

<aop:config>
    <aop:pointcut id="serviceCalls"
        expression="execution(* demo.AccountApplicationService.*(..))"/>
    <aop:advisor advice-ref="txAdvice" pointcut-ref="serviceCalls"/>
</aop:config>
```

These two snippets are **illustrative fragments**, not a standalone application without bean declarations, datasource, transaction manager, `xmlns:tx`/`xmlns:aop`, and schemas. Advantage: the service imports neither transaction APIs nor Spring annotations; policy lives elsewhere.

Trade-offs:

- Transaction boundaries are no longer visible right next to the method in source; developers must know which XML/pointcuts apply.
- Renaming classes, packages, or methods can silently break pointcuts if untested.
- Still relies on Spring AOP proxies/managers at runtime, and still has proxy-mode self-invocation limits.

Therefore, "declarative is less coupled" is most accurate when referring to **application code not directly driving the transaction API**. You should not say it **eliminates all system dependencies** on Spring.

## 11. A Transaction Facade to Reduce `TransactionTemplate` Coupling

In a codebase needing programmatic boundaries frequently, you can define your own abstraction at the application layer:

```java
package app.port;

import java.util.function.Supplier;

public interface UnitOfWork {
    <T> T execute(Supplier<T> work);
}
```

And a Spring adapter:

```java
package app.adapter;

import app.port.UnitOfWork;
import java.util.function.Supplier;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

public final class SpringUnitOfWork implements UnitOfWork {
    private final TransactionTemplate template;

    public SpringUnitOfWork(PlatformTransactionManager manager) {
        this.template = new TransactionTemplate(manager);
    }

    @Override
    public <T> T execute(Supplier<T> work) {
        return template.execute(status -> work.get());
    }
}
```

These are **two fragments that compile when corresponding dependencies/imports and Java package layout exist**, though not a runnable program on their own. An application service can inject `UnitOfWork`:

```java
public final class RegistrationUseCase {
    private final UnitOfWork tx;

    public RegistrationUseCase(UnitOfWork tx) {
        this.tx = tx;
    }

    public String register() {
        return tx.execute(() -> {
            // Call persistence ports/domain logic.
            return "registered";
        });
    }
}
```

This is a fragment requiring `UnitOfWork` in the imported package, bean injection, and collaborators. `RegistrationUseCase` does not need to import `TransactionTemplate`. Still, it knows the *concept of UnitOfWork*, meaning **business orchestration remains coupled to transaction semantics at the application-abstraction level**. This abstraction can ease swapping adapters/testing, yet if every service just needs one simple `@Transactional`, adding a facade can introduce unnecessary complexity.

### 11.1. Cost of a Facade

`Supplier<T>` does not allow throwing checked exceptions directly; if domain flows need checked errors, design a suitable functional interface and exception policy instead of wrapping all errors arbitrarily. You must also consider where propagation/timeout/read-only are configured on the facade. A narrow general abstraction can be too limiting for complex use cases; an overly option-rich abstraction merely duplicates Spring's API.

### 11.2. Do Not Build an Internal Framework Just to Avoid One Import

The goal is reducing coupling **where it adds value** for module boundaries and testing, not hiding every Spring-named type regardless of added complexity. If the codebase is entirely Spring and `TransactionTemplate` appears in only a few spots, keeping Spring's API directly can be simpler, more readable, and more accurate than a homegrown facade.

## 12. Checked Exceptions and Rollback: Comparing Where Decisions Live

Declarative `@Transactional` (with standard default rollback configuration) rolls back on `RuntimeException`/`Error`, yet does not roll back by default on all checked exceptions. You can declare:

```java
@Transactional(rollbackFor = java.io.IOException.class)
public void importFile() throws java.io.IOException {
    // If IOException escapes the transactional advice, the rollback rule applies.
}
```

This is an illustrative fragment needing real file/repository logic. Spring 6.2 supports changing global rollback defaults (e.g., `@EnableTransactionManagement(rollbackOn=ALL_EXCEPTIONS)`), so know your actual version's configuration.

`TransactionTemplate.execute` takes a callback that does not declare `throws` checked exceptions. Therefore, if code inside encounters a checked exception and needs rollback, it must **express the policy explicitly**:

```java
String outcome = template.execute(status -> {
    try {
        legacyOperationThatMayThrow();
        return "SUCCESS";
    } catch (java.io.IOException ex) {
        status.setRollbackOnly();
        return "IO_FAILURE";
    }
});
```

This is a fragment; `legacyOperationThatMayThrow()` and `template` must exist. This approach only fits if the business contract allows returning a failure outcome. If the caller must see an exception, intentionally wrap it in a runtime exception preserving the cause or design a dedicated abstraction; never swallow the error and report success.

**Coupling perspective:**

- Declarative: rollback policy is described via annotation; the method body can throw checked exceptions normally.
- Programmatic template: policy can appear inside the callback as exception handling/status calls, making the transaction concern explicit right inside the logic.
- Both must account for transaction participation: a rollback-only inside an inner `REQUIRED` can cause an outer commit to fail with `UnexpectedRollbackException`.

## 13. Conditional Transaction Boundaries and Transaction Names

### 13.1. A Method with Sections Not Needing a Transaction

In a use case that prepares data and calls an external API before writing to the DB, the template can hold connections/locks only for the short block:

```java
public Result process(Request req) {
    Quote quote = externalPricingClient.fetch(req);  // outside transaction

    Result saved = txTemplate.execute(status -> {
        // INSERT/UPDATE that must be atomic
        return saveInDatabase(quote);
    });

    notifyAfterCommitOrUseOutbox(saved);              // outside callback
    return saved;
}
```

This is a fragment; types/collaborators must be provided. A method named `notifyAfterCommitOrUseOutbox` **does not guarantee email/message rollback or exactly-once delivery**; outbox/idempotency must be designed separately, especially when the caller has an outer transaction or the template joined an uncommitted T1.

With declarative, you can extract the DB write method into a **separate `@Transactional` bean** and call it from the coordinator; the transaction boundary stays short without needing a template. The difference is **how the boundary is expressed in code**.

### 13.2. Assigning a Transaction Name

Programmatic definitions/templates can set a name for monitoring:

```java
TransactionTemplate template = new TransactionTemplate(manager);
template.setName("reporting.dailyAggregation");
```

This is a fragment. In declarative `@Transactional`, transaction names are usually generated by Spring from `fully.qualified.ClassName.methodName`, with no standard `@Transactional(name="...")` to set arbitrarily. This is a concrete advantage of programmatic management when custom transaction naming is a diagnostic requirement.

### 13.3. Template Is Thread-Safe When Configuration Is Stable

Spring documentation confirms `TransactionTemplate` holds no **conversational state** across executions and can be shared across multiple threads if **configuration is not modified concurrently**.

Sensible usage:

```java
private final TransactionTemplate readOnlyTemplate;
private final TransactionTemplate writeTemplate;
```

Both templates are initialized once with distinct policies; each call uses the right instance. Do not call `setTimeout(...)`/`setPropagationBehavior(...)` on **one shared template** per request to change policy dynamically and expect concurrent requests not to interfere with one another. For multiple policies, create instances whose configuration stays immutable after setup, or construct an appropriate local definition/template before `execute`.

## 14. Can Programmatic and Declarative Be Combined?

Yes. Both rely on Spring's transaction infrastructure and can interact via propagation, though you must understand **who owns the physical transaction**.

Outer declarative example:

```java
@Transactional
public void submit() {
    txTemplate.executeWithoutResult(status -> {
        // Work performed under the template's propagation.
    });
}
```

This is a fragment. With default `REQUIRED` on the template, the callback **joins** the outer transaction rather than creating a separate T2. `status.setRollbackOnly()` or an appropriate error in the callback can prevent outer T1 from committing.

Conversely, outer programmatic:

```java
template.executeWithoutResult(status -> {
    otherSpringBean.transactionalMethod();
});
```

This is a fragment. If `otherSpringBean.transactionalMethod()` is called through the Spring proxy and uses `REQUIRED`, it joins the transaction started by the template. If calling a method in the same class via `this.method()`, the annotation may not be intercepted by advice.

### 14.1. `REQUIRES_NEW` Is Not a Savepoint

If a template uses `PROPAGATION_REQUIRES_NEW` inside an outer `@Transactional`, the manager suspends T1 and opens an independent T2 (when supported by the resource). This may require an extra JDBC connection and allows T2 to commit on its own even if T1 later rolls back. This is a **semantic change**, not merely a syntax switch.

`NESTED`, when supported by the manager/database, typically uses a savepoint **within the same physical transaction**. Do not treat using a template as a mechanism to "dodge" a manager's resource/propagation constraints.

### 14.2. Do Not Use Two Transaction Managers and Assume Shared Atomicity

A callback with manager A and a `@Transactional` method selecting manager B do not automatically form a global transaction. Even though both use Spring, local JDBC managers only coordinate their respective resources. If multi-resource atomicity must be guaranteed, use an appropriate transaction coordinator or outbox/saga architecture depending on the use case.

## 15. Observation, Testing, and Migration

### 15.1. When Migrating `TransactionTemplate` to `@Transactional`

Minimum checklist:

1. Identify the exact block of code **inside** the template callback; do not accidentally pull network calls or long CPU work into the new transaction.
2. Record existing propagation, isolation, timeout, read-only, transaction manager, name, and rollback-only behavior.
3. Choose a public Spring-managed service method **called by external callers through a proxy**.
4. Translate template settings to annotation or XML advice, understanding checked-exception rollback differences.
5. Check `status.setRollbackOnly()` blocks and business failure results; annotations do not replicate that behavior automatically on a normal return.
6. Check whether callers have an outer transaction; `REQUIRED` may join with the same semantics, though begin/commit timing must be verified.
7. Compare exceptions thrown inside the callback vs. at proxy commit and error/retry paths.
8. Check custom transaction name usage: standard annotations auto-generate names.
9. Write integration tests for both success and failure between two SQL statements, inspecting data after the boundary.
10. If test-level `@Transactional` is present, remove its influence so tests do not always run inside an outer transaction.

### 15.2. When Migrating `@Transactional` to `TransactionTemplate`

Check similarly in the reverse direction:

1. Do not wrap the **entire** method in a template if the previous annotation applied a specific propagation you have not replicated.
2. Use a `TransactionTemplate` configured with the same manager/resource as the old annotated service.
3. Put only the business work needing atomicity inside the callback, keeping non-DB side effects in appropriate positions.
4. Translate checked-exception rollback rules into explicit handling/status/exception policies.
5. Ensure code previously triggered via AOP advice (e.g., security/retry aspects) does not shift order significantly when removing the transaction advisor.
6. Confirm no inner `@Transactional(REQUIRES_NEW)` accidentally turned into `REQUIRED` when switching to a default template.
7. Review shared templates and configuration state; never mutate policy on a singleton between requests.

### 15.3. Logging

In dev/test environments with a supporting logging backend, you can observe:

```properties
logging.level.org.springframework.transaction=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
```

This is a common Spring Boot config snippet, **not** required by the `AnnotationConfigApplicationContext` program in section 7. Logs help reveal begin/join, suspend/resume, and commit/rollback. With both approaches, **DB state after the transaction boundary** remains the ultimate proof of whether an operation committed or rolled back properly.

## 16. Design Scenarios and Suitable Choices

### A. CRUD Service with 40 Similar Write Operations

**Prefer considering declarative.** Annotations on service methods or composed annotations reduce repetitive callbacks. Using many `TransactionTemplate` calls can scatter transaction APIs throughout code, increasing coupling and reading overhead.

### B. A Batch Import with Many Non-Transactional Steps and Only One Write Block Needing Commit

**`TransactionTemplate` helps** by showing the boundary right next to the code. Declarative can still fit if the transactional writer is extracted into a separate bean; pick whichever is easier to review in the existing architecture.

### C. A Domain Model That Wants No Spring Dependency

**Both can achieve this** if transaction concerns stay outside the domain model. With templates, wrap with an application adapter/facade. With declarative, put annotations on Spring application services or use XML advice, avoiding annotations in domain entities.

### D. Retrying Serialization Failures at Commit

Needs a retry coordinator **outside the transaction boundary** so each attempt uses a new transaction. `TransactionTemplate.execute(...)` inside a retry loop outside the transaction is easy to place accurately. Declarative also works if the retry coordinator calls a Spring-managed transactional worker through a proxy, with proper advisor ordering. Never place retries inside an already rollback-only transaction.

### E. Needing `setRollbackOnly()` While Still Returning a Business Outcome

The template lets you handle this directly in the callback. Declarative can access `TransactionAspectSupport.currentTransactionStatus()`, yet that introduces source-level coupling into the body and undermines concern separation; alternatively, redesign exceptions/return policies appropriately. Do not turn every failure into a checked exception and default to rollback.

### F. A Method in the Same Class Calling a `@Transactional` Helper

Proxy-based declarative risks self-invocation bypassing advice. An explicit template still coordinates whenever the callback runs. If wanting to stay declarative, move the helper to another bean, lift the boundary to the outer method, or evaluate AspectJ weaving when truly needed.

## 17. Misconceptions to Avoid

**Misconception 1: "`@Transactional` has no coupling to Spring."**  
False if using Spring's annotation directly; coupling inside the method body is simply lower. If using XML advice, the business class source may import no transaction framework, yet runtime still requires Spring/AOP/manager.

**Misconception 2: "`TransactionTemplate` forces writing manual `try/commit/rollback`."**  
False. The template handles lifecycle while the callback only expresses the work to perform. Manual `PlatformTransactionManager` is a different programmatic style.

**Misconception 3: "Annotations are always better because they take less code."**  
False. A small, conditional boundary inside a long flow can be clearer with a template. Quality depends on readability and testability in the actual codebase.

**Misconception 4: "Templates have no propagation issues."**  
False. A default template uses `REQUIRED` and can join an outer transaction. It does not guarantee every `execute` gets a new physical transaction.

**Misconception 5: "Adding `@Transactional` guarantees the method rolls back."**  
False if the bean was created with `new`, annotation infrastructure is not enabled, the caller bypasses the proxy, or datasource/manager mismatch. You must verify the actual boundary.

**Misconception 6: "If calling a method in the same class, using a template also loses the transaction."**  
False if code actually executes `template.execute(...)`. This differs from `@Transactional` proxy interception.

**Misconception 7: "`readOnly=true` is an absolute DB permission."**  
False. Managers/drivers/providers may apply hints or specific enforcement; annotations do not replace DB permissions.

**Misconception 8: "Adding the annotation and catching an exception inside the method still rolls back automatically."**  
Not necessarily. Swallowing an exception before it escapes advice can lead to commit if there is no rollback-only flag; design explicit policies.

**Misconception 9: "Migrating syntax cannot change behavior."**  
It can change behavior if boundaries, propagation, transaction names, rollback rules, timing, or AOP ordering differ. Test commit/rollback after migration.

**Misconception 10: "Unit tests without Spring prove transactions are applied."**  
False. Unit tests only verify business methods; transaction semantics require integration tests with matching managers/resources/proxies.

**Misconception 11: "`TransactionTemplate` is not thread-safe."**  
False per documentation: it can be shared when configuration is stable, though shared policy must not be mutated across requests.

**Misconception 12: "Reactive transactions also use `TransactionTemplate` identically."**  
False. For reactive flows, Spring recommends `TransactionalOperator` and `ReactiveTransactionManager`/Reactor Context; do not use thread-local JDBC semantics to reason about reactive transactions.

## 18. Self-Check and Exercises

**Question 1.** In terms of source-level coupling, what is the fundamental difference between `TransactionTemplate` and `@Transactional`?

**Answer:** The template makes code call transaction APIs directly; declarative puts policy into metadata/annotations while transaction lifecycle lives in an interceptor. Spring's annotation is still a dependency, yet the method body needs no template/status.

**Question 2.** Does `@Transactional` allow omitting Spring's transaction manager altogether?

**Answer:** No. Transaction infrastructure and a matching manager/resource are still required; the annotation is only metadata if unprocessed.

**Question 3.** Can `TransactionTemplate` be used in self-invocation?

**Answer:** Yes. If the internal method executes the `template.execute` callback, the template still coordinates the transaction; self-invocation is only an issue when relying on proxy advice.

**Question 4.** A `@Transactional` service is instantiated with `new` outside Spring and its method is called. Is a transaction guaranteed?

**Answer:** Unlikely; in standard proxy mode, there is no proxy/infrastructure wrapping that object, so the annotation does not open a transaction.

**Question 5.** Does putting `@Transactional(readOnly=true)` on a method guarantee the DB always forbids writes?

**Answer:** No. Read-only is usually a hint; enforcement depends on the manager/provider/database.

**Question 6.** Does a `REQUIRED` `TransactionTemplate` inside an outer transaction open a new T2?

**Answer:** Usually no. It joins T1; an independent transaction requires `REQUIRES_NEW` and resource evaluation.

**Question 7.** Why is the template advantageous when only a short SQL block needs a transaction?

**Answer:** The boundary is expressed directly in code without forcing extraction into an annotated method/bean; parts not needing a transaction can stay outside the callback.

**Question 8.** If many service methods are similarly transactional, which should you choose?

**Answer:** Declarative usually reduces boilerplate and direct coupling to transaction APIs in methods; however, you must understand proxies and configuration.

**Question 9.** If a custom transaction name is needed to trace batches, which approach is convenient?

**Answer:** Programmatic definitions/templates can call `setName`, whereas declarative method names are typically auto-generated by Spring.

**Question 10.** Can `TransactionTemplate` be used as a shared singleton object with policy changing per request?

**Answer:** You should not mutate policy on a single concurrently shared template. The template is thread-safe when configuration is stable; use multiple explicit instances/policies.

**Question 11.** In a template callback, does `status.setRollbackOnly()` followed by returning `"FAIL"` mean the transaction committed?

**Answer:** No. That is a rollback request; `"FAIL"` is only a business result and the caller must understand that meaning. When joining T1, rollback-only can affect the outer transaction.

**Question 12.** A unit test calls `new DeclarativeTransferService(core)` and sees an exception. Does that prove DB rollback?

**Answer:** No. Without a transaction proxy/manager, that test does not verify Spring transactions. An integration test calling the bean through the context and reading the DB after the boundary is required.

**Question 13.** Can XML declarative config be used so business classes do not import `@Transactional`?

**Answer:** Yes, by configuring `<tx:advice>` + an AOP pointcut on matching methods. In exchange, coupling moves to XML and pointcuts/renames must be tested.

**Question 14.** In a pure Spring system, should you build a `UnitOfWork` abstraction solely to avoid importing `TransactionTemplate` in a single service?

**Answer:** Not necessarily. An abstraction is only worthwhile when it creates clearer module/testing/portability boundaries than the added cost.

## 19. Code Review Application Checklist

When deciding between template and declarative, check:

- Where is the current transaction boundary? Does it enclose network calls, file processing, or long computations?
- Does an operation have **few or many** transactional methods needing similar policies?
- Does the business method import `TransactionTemplate`, `TransactionStatus`, or `PlatformTransactionManager`? Are those imports appropriate for the current layer?
- If using `@Transactional`, is the method called through a Spring-managed bean/proxy? Is there self-invocation?
- Do the transaction manager/data source/persistence unit match the DAO/repository?
- Does `REQUIRED` join an outer transaction? If joining is unintended, is propagation designed properly?
- Are rollback rules for checked exceptions/return outcomes clear? Is `status.setRollbackOnly()` used?
- Are there multiple transaction managers, retry mechanisms, or AOP advice changing execution order unexpectedly?
- Is there a need to assign a custom **transaction name** or vary transaction settings for a small block?
- Is any singleton template having its config mutated while multiple threads call it concurrently?
- Does the domain core need to be Spring-independent? Can transaction concerns be pushed up to an application service/adapter without creating superfluous abstractions?
- Do tests distinguish **logic unit tests** from **transaction integration tests**? Have rollbacks between two SQL statements and post-transaction reads been tested?
- If migrating from one approach to the other, have actual begin/commit scopes and propagation been compared?
- Do operations/logging docs clearly report transaction failures and timeouts?

**In short:** `TransactionTemplate` **directly couples code to Spring's transaction API** in exchange for flexible, explicit boundaries; declarative management **reduces transaction boilerplate in business bodies** and generally fits many service operations, yet relies on metadata/proxies and still needs Spring infrastructure. Choose based on boundary placement, orchestration complexity, and testability — not on a dogma that one approach is always superior to the other.

## Official References

- [Spring Framework 6.2 — Programmatic Transaction Management (`TransactionTemplate`)](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html)
- [Spring Framework 6.2 — Choosing Between Programmatic and Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/tx-decl-vs-prog.html)
- [Spring Framework 6.2 — Using `@Transactional`](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html)
- [Spring Framework — Transaction Propagation (`REQUIRED`, `REQUIRES_NEW`, `NESTED`)](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework 6.2 API — `TransactionTemplate`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/support/TransactionTemplate.html)
- [Spring Framework 6.2 API — `TransactionStatus`](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/TransactionStatus.html)
- [Spring Framework — Transaction Resource Synchronization](https://docs.spring.io/spring-framework/reference/data-access/transaction/tx-resource-synchronization.html)