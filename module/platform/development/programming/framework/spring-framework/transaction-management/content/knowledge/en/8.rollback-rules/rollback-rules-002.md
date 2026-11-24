# Checked Exceptions and the Need for Explicit Rollback Declarations in Spring Transaction Management

## 1. Why Can an Exception Still Cause a Transaction to Commit?

In Java, a **checked exception** is an exception that the compiler forces calling code to handle with `catch` or declare with `throws`, such as `IOException`, `SQLException`, or a business exception that `extends Exception`. An **unchecked exception** is typically `RuntimeException` and its subclasses; `Error` is likewise exempt from the compiler's checked-exception requirement.

In **Spring's traditional default rollback configuration**, a `@Transactional` method that throws an exception escaping the method produces these outcomes:

- `RuntimeException` or `Error`: Spring **chooses rollback**.
- A checked `Exception` that is not a `RuntimeException`: Spring **does not choose rollback by default**. If the transaction is owned by that method and can still commit, Spring will **commit even while propagating the checked exception to the caller**.

This is a **Spring transaction interceptor rule**, not a Java rule stating that checked exceptions are “non-serious” or that the database decides automatically based on exception type. Checked vs. unchecked only describes compile-time checking and `Throwable` classification; **what should happen when a failure occurs is a business decision**.

For example, consider a transaction that creates an order, deducts inventory, and then detects an invalid delivery address:

```java
@Transactional
public void placeOrder(...) throws InvalidDeliveryAddressException {
    orderRepository.save(...);
    stockRepository.reserve(...);

    throw new InvalidDeliveryAddressException("Cannot ship to address");
}
```

If `InvalidDeliveryAddressException extends Exception`, no other rollback rule is present, and a transaction was actually opened, **the preceding DB operations may be committed** when the exception exits the method. This usually contradicts the expectation that “an order either succeeds completely or changes nothing.” The explicit way:

```java
@Transactional(rollbackFor = InvalidDeliveryAddressException.class)
public void placeOrder(...) throws InvalidDeliveryAddressException {
    // Same business logic, but this exception tells Spring to roll back the transaction.
}
```

The snippets above are **illustrative code**: repositories, exceptions, and parameters must be defined in a real application. A runnable Spring Boot JDBC project with deterministic output is provided in section 5.

> **Key rule:** “Having `throws`”, “throwing an exception”, “calling `save`”, and “executing SQL updates” are all **insufficient** to infer that the transaction will roll back. You must determine **exception type, rollback rules, transaction boundaries, proxy call path, and DB state**.

## 2. Separating the Three Decision Layers

A common scenario:

```text
Caller
    |
    v
Spring transaction proxy / interceptor
    |-- starts or joins the transaction
    v
Service method
    |-- JDBC/JPA writes data within the transaction
    |-- throw BusinessCheckedException
    v
Proxy receives the exception
    |-- checks rollback rules
    |-- rolls back or attempts to commit
    v
Caller still receives the exception (if the transaction completes as expected)
```

Three distinct decision layers:

1. **Java:** requires `throws BusinessCheckedException` or `catch` because the exception is checked; does not decide database commit/rollback.
2. **Spring:** inspects the method's transaction attributes and rollback/no-rollback rules; may roll back or allow the transaction to proceed to commit.
3. **Database:** executes `COMMIT`/`ROLLBACK` on the managed connection/transaction. The database can fail at commit even if Spring chose commit.

If the caller catches the exception after the proxy has committed, **catching in the caller cannot automatically roll back an already finished transaction**. If the exception is caught **inside** the transactional method and the method then returns normally, the interceptor does not see that exception; if nothing else marked the transaction rollback-only, it typically proceeds to commit.

### Quick Comparison of Outcomes

Assuming a `@Transactional` method is called through a Spring proxy, uses a transactional DB, starts a new transaction, executes DB work successfully up to the throw, and has no other rules:

| Method exit scenario | Traditional default rollback? | Observable consequence after proxy handling |
| --- | --- | --- |
| Method returns normally | No | Commits if there is no error/rollback-only |
| `throw new IllegalStateException(...)` | **Yes** | DB changes in the transaction are rolled back |
| `throw new IOException(...)` | **No** | Transaction may commit before `IOException` is propagated to caller |
| `throw new CustomException(...)` where `CustomException extends Exception` | **No** | May commit even though caller receives checked exception |
| Checked exception + `rollbackFor = CustomException.class` | **Yes** | Spring requests rollback |
| Unchecked exception + `noRollbackFor = SpecificRuntimeException.class` | **No for the specified type** | May commit while the exception is still thrown to caller |
| Exception caught and swallowed inside method | Proxy sees no exiting exception | Usually commits, unless transaction status was already marked rollback-only or DB fails |

All conclusions about commit are **conditional**: commit can fail due to constraints, database errors, deadlocks, a transaction already marked rollback-only, or a transaction owned by an outer scope. “Spring chooses commit” **does not guarantee the commit succeeded**.

## 3. Checked Exceptions: `throws` Does Not Imply Rollback

Example business exception definition:

```java
package demo.rollback;

public class BusinessCheckedException extends Exception {
    public BusinessCheckedException(String message) {
        super(message);
    }
}
```

This is a checked exception because it extends `Exception` directly and **does not** extend `RuntimeException`. The compiler forces callers to handle or declare `throws BusinessCheckedException`. Both APIs below are valid Java:

```java
@Transactional
public void processWithoutRule() throws BusinessCheckedException {
    updateDatabase();
    throw new BusinessCheckedException("Rejected");
}

@Transactional(rollbackFor = BusinessCheckedException.class)
public void processWithRule() throws BusinessCheckedException {
    updateDatabase();
    throw new BusinessCheckedException("Rejected");
}
```

Both methods have the **same `throws` declaration** yet different rollback policies. `rollbackFor` decides rollback when an exception type occurs; it does not affect the compiler's requirement to handle checked exceptions.

Similarly, while raw JDBC throws `SQLException`, which is a checked exception, **`JdbcTemplate` and Spring JDBC usually translate `SQLException` into `DataAccessException`**, which is a `RuntimeException`, so many SQL errors roll back by default. Do not infer from the underlying JDBC API's exception list that `JdbcTemplate` will surface a raw checked `SQLException` up to the service.

With Spring Data JPA, persistence errors also typically surface as unchecked exceptions. Therefore, a test that only triggers a database error may **fail to verify** checked-exception rules; you need to throw a checked business exception after a successful DB operation.

## 4. Declaring Rollback and No-Rollback Rules with `@Transactional`

### 4.1. Prefer Specific Exception Types

The clearest approach:

```java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void registerCustomer(...) throws BusinessCheckedException {
    // If this exception exits the method through the proxy, roll back.
}
```

Multiple types can be specified:

```java
@Transactional(rollbackFor = {
    BusinessCheckedException.class,
    java.io.IOException.class
})
public void completeOrder(...) throws BusinessCheckedException, java.io.IOException {
    // As soon as any of these exceptions exits, the rule applies.
}
```

`rollbackFor` accepts `Class<? extends Throwable>`. Declaring a supertype like `Exception.class` applies to its subclasses, including checked and unchecked `Exception`s; `Error`s do not extend `Exception`, yet still follow default rollback. A broad policy is sometimes convenient, but if a checked exception represents “no data found” and the workflow intentionally needs to commit, forcing rollback on everything may be undesirable.

A specific rule is generally easier to understand and maintain:

```java
@Transactional(rollbackFor = BusinessCheckedException.class)
```

compared to:

```java
@Transactional(rollbackFor = Exception.class)
```

The decision should be based on the **business contract**: which exceptions indicate the transaction must be cancelled, and which merely represent a state that can still commit.

### 4.2. `noRollbackFor`: Exception Still Thrown, Transaction Can Commit

Some exceptions represent an acceptable state after recording a change—for instance, a runtime exception used to signal to the caller that “follow-up action is needed” while an audit record **must be preserved**. In that case you can configure:

```java
@Transactional(noRollbackFor = ExpectedStatusException.class)
public void recordStatusAndReport() {
    // Write audit/mark confirmed status.
    throw new ExpectedStatusException("Follow-up is required");
}
```

This is **illustrative**: `ExpectedStatusException` needs to be defined (e.g., extending `RuntimeException`). `noRollbackFor` does not catch or swallow the exception; the caller still sees the exception after proxy handling. If the database already reported an error making the transaction uncommittable, this rule **cannot force the database commit to succeed**.

Do not overuse `noRollbackFor` to “patch” a flawed control flow. If the business logic does not treat the condition as a failure, returning a result type such as `Result`/status instead of throwing an exception usually makes the API contract clearer.

### 4.3. Type-Based Rules vs. Class-Name Rules

Spring provides four related attributes:

| Attribute | Declaration form | Meaning |
| --- | --- | --- |
| `rollbackFor` | `BusinessCheckedException.class` | Roll back for the type and its subclasses |
| `rollbackForClassName` | `"demo.rollback.BusinessCheckedException"` | Roll back by exception name string pattern |
| `noRollbackFor` | `SpecificRuntimeException.class` | Do not request rollback for the type and subclasses |
| `noRollbackForClassName` | `"demo.rollback.SpecificRuntimeException"` | Do not request rollback by exception name string pattern |

**Prefer type-safe `.class` references** when the exception class is on the classpath. A string rule such as `rollbackForClassName = "Exception"` does **not** mean “only the exact class named Exception”; the pattern matches a **substring** of the fully qualified name and can accidentally match many other types. `*` is **not** a glob in exception-name patterns. Even `"demo.rollback.BusinessCheckedException"` could match a class named `BusinessCheckedExceptionV2` or a nested class whose name contains the same substring.

Separate illustrative example for patterns when the type cannot be referenced directly:

```java
@Transactional(
    rollbackForClassName = "vendor.partner.CheckedIntegrationException"
)
public void integrate() throws Exception {
    // Rule matches by exception name, not by Java type at compile time.
}
```

Use patterns only when truly necessary; class-based rules carry less risk.

### 4.4. What If Both Rollback and No-Rollback Rules Match?

Spring selects the **strongest matching rule**, based on proximity in the type inheritance hierarchy or pattern match strength. For example:

```java
@Transactional(
    rollbackFor = Exception.class,
    noRollbackFor = SpecificBusinessException.class
)
public void updateAndMaybeReport() throws SpecificBusinessException {
    // SpecificBusinessException extends Exception
}
```

When `SpecificBusinessException` is thrown, the specific `noRollbackFor` rule wins over the broad `rollbackFor = Exception.class` rule. When another checked exception extending `Exception` is thrown, `rollbackFor = Exception.class` can apply. Avoid building an unnecessarily overlapping set of rules or two rules of equal strength; choose clear business intent and test it.

**Distinction:** the “strongest matching rule wins” rule here refers to **exception-rule precedence within a single transaction attribute**. It is not the precedence of `get*`/`save*` method name patterns in XML, nor the ordering of AOP advisors.

## 5. Runnable Example: Same Checked Exception, One Method Commits and One Rolls Back

We use **Java 17 + Spring Boot 3.3.13 + Spring JDBC + H2** to verify default behavior. The project is standalone and needs no REST controller or JPA. The Spring Framework version managed by Spring Boot 3.3.x uses the traditional rollback rules; do not enable a different global rollback policy when running this example.

File structure:

```text
checked-rollback-lab/
├── build.gradle
├── settings.gradle
├── gradlew / gradlew.bat
└── src/main/
    ├── java/demo/rollback/
    │   ├── RollbackDemoApplication.java
    │   ├── AuditService.java
    │   └── BusinessCheckedException.java
    └── resources/
        ├── application.yml
        └── schema.sql
```

### 5.1. Gradle and Database

**`settings.gradle`**

```groovy
rootProject.name = 'checked-rollback-lab'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '0.0.1-SNAPSHOT'

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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

The Spring Boot JDBC starter provides `JdbcTemplate` and the transaction infrastructure; the H2 driver is loaded at runtime. You do not need to declare `spring-tx` separately or use Spring Data JPA for this direct SQL verification. If your project uses another BOM/version catalog, keep Spring modules and drivers compatible with it.

**`src/main/resources/application.yml`**

```yaml
spring:
  datasource:
    url: "jdbc:h2:mem:rollbacklab;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

**`src/main/resources/schema.sql`**

```sql
CREATE TABLE audit_events (
    id BIGINT PRIMARY KEY,
    message VARCHAR(80) NOT NULL
);
```

H2 is an in-memory database living inside the JVM; each fresh app run starts with an empty database. Spring Boot runs `schema.sql` at startup. No manual table creation is needed.

### 5.2. Business Exception

**`src/main/java/demo/rollback/BusinessCheckedException.java`**

```java
package demo.rollback;

public class BusinessCheckedException extends Exception {
    public BusinessCheckedException(String message) {
        super(message);
    }
}
```

Because it extends `Exception` and does not extend `RuntimeException`, it is a checked exception.

### 5.3. Service with Three Policies

**`src/main/java/demo/rollback/AuditService.java`**

```java
package demo.rollback;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AuditService {
    private final JdbcTemplate jdbc;

    public AuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void defaultChecked(long id) throws BusinessCheckedException {
        jdbc.update(
            "INSERT INTO audit_events (id, message) VALUES (?, ?)",
            id, "default"
        );
        throw new BusinessCheckedException("business rejected");
    }

    @Transactional(rollbackFor = BusinessCheckedException.class)
    public void explicitChecked(long id) throws BusinessCheckedException {
        jdbc.update(
            "INSERT INTO audit_events (id, message) VALUES (?, ?)",
            id, "explicit"
        );
        throw new BusinessCheckedException("business rejected");
    }

    @Transactional
    public void defaultUnchecked(long id) {
        jdbc.update(
            "INSERT INTO audit_events (id, message) VALUES (?, ?)",
            id, "runtime"
        );
        throw new IllegalStateException("runtime rejected");
    }
}
```

Each method attempts to insert a row into the database and then throws an exception. The difference lies in the policy:

- `defaultChecked`: does not declare `rollbackFor`. Checked exceptions do not trigger rollback under the traditional default.
- `explicitChecked`: explicitly declares `rollbackFor = BusinessCheckedException.class`.
- `defaultUnchecked`: uses unchecked `IllegalStateException` to contrast with default rollback.

### 5.4. Runner Calling Through Spring Proxy and Observing After Transaction Completion

**`src/main/java/demo/rollback/RollbackDemoApplication.java`**

```java
package demo.rollback;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class RollbackDemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(RollbackDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner verify(AuditService service, JdbcTemplate jdbc) {
        return args -> {
            System.out.println("Before: " + count(jdbc));

            try {
                service.defaultChecked(1L);
            } catch (BusinessCheckedException ex) {
                System.out.println("Default checked: " + ex.getMessage());
            }
            System.out.println("After default checked: " + count(jdbc));

            try {
                service.explicitChecked(2L);
            } catch (BusinessCheckedException ex) {
                System.out.println("Explicit checked: " + ex.getMessage());
            }
            System.out.println("After explicit rollback: " + count(jdbc));

            try {
                service.defaultUnchecked(3L);
            } catch (IllegalStateException ex) {
                System.out.println("Runtime: " + ex.getMessage());
            }
            System.out.println("After runtime rollback: " + count(jdbc));

            System.out.println(
                "Remaining ids: " +
                jdbc.queryForList("SELECT id FROM audit_events ORDER BY id",
                                  Long.class)
            );
        };
    }

    private static Integer count(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT COUNT(*) FROM audit_events", Integer.class);
    }
}
```

**Run in the project directory with the Gradle Wrapper**:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

Amidst the usual Gradle/Spring Boot logs, the lines printed by the program must appear in this order:

```text
Before: 0
Default checked: business rejected
After default checked: 1
Explicit checked: business rejected
After explicit rollback: 1
Runtime: runtime rejected
After runtime rollback: 1
Remaining ids: [1]
```

Why are the numbers exact?

1. The table starts empty, so `COUNT(*) = 0`.
2. `defaultChecked(1)` inserts ID 1 and throws a checked exception; the proxy chooses commit by default. The caller catches the exception, yet `COUNT(*)` is now **1**.
3. `explicitChecked(2)` inserts ID 2 and throws the **same checked exception type**; the rollback rule requests rollback. ID 2 does not exist after the method ends, so the count remains **1**.
4. `defaultUnchecked(3)` inserts ID 3 and throws `IllegalStateException`; default rollback applies, and the count remains **1**.
5. Only ID 1 committed, so `Remaining ids: [1]`.

The Java snippets form a **complete Spring Boot project when assembled with the right files and dependencies**; run via `bootRun`, not as standalone files compiled with `javac` alone. Each run starts a fresh JVM and reinitializes in-memory H2; if reusing a persistent DB, manage resetting data before retrying.

**Boundary note:** `AuditService` is a bean injected from the Spring container; the runner calls the service **through the proxy**. The runner is not annotated with `@Transactional`, so counting happens **after the service proxy has decided commit/rollback**. If you place the runner/test inside an outer transaction, isolation and row counts can differ.

## 6. Why Should Rollback Rules Match Business Semantics?

A checked exception often describes a **predictable business outcome** rather than an infrastructure failure. For example:

| Exception | Possible meaning | Choose rollback? |
| --- | --- | --- |
| `InvalidOrderException` | Order cannot be accepted; inventory was temporarily reserved | **Usually yes**, to avoid leaving partial writes behind |
| `InsufficientFundsException` | Cannot debit funds; do not want an incomplete transfer | **Yes** if prior transaction writes must be cancelled |
| `EmailDeliveryException` | DB already confirmed the order, but sending email failed | **Depends**: usually avoid holding the DB transaction open across email calls; handle via outbox/after-commit |
| `ValidationWarningException` | Intentionally save a warning/audit record and then reply to caller | **Possibly no**, if policy requires persisting the processed state |
| `IOException` while reading an import file | File is corrupt midway through updating multiple tables | **Yes** if atomic data import is desired |
| Raw `SQLException` from JDBC | DB error | **Depends** on transaction/DB, though rollback is usually needed; Spring JDBC typically translates it into unchecked `DataAccessException` |

You cannot deduce “all checked exceptions must commit” or “all checked exceptions must roll back” without understanding which resources were modified and what counts as a valid state. Define the **failure contract** right at the service boundary: which exceptions indicate the business operation failed and all writes in the transaction must be cancelled.

An exception that is “typically checked” can also appear **after external side effects** such as HTTP or email have already completed. A DB rollback cannot recall a sent email or API call. When DB changes and notifications must stay consistent, consider a transactional outbox and post-commit handling; `rollbackFor` only controls resources managed by the transaction manager.

## 7. Situations Where Declaring `rollbackFor` Still Falls Short

### 7.1. Exception Caught Directly Inside the Transactional Method

```java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void process() {
    try {
        callBusinessOperation();
    } catch (BusinessCheckedException ex) {
        logWarning(ex);
        // Method returns normally: proxy receives no exception.
    }
}
```

This is **illustrative code** with `callBusinessOperation` and `logWarning` undefined. If the exception is swallowed, the rollback rule is not triggered automatically because no exception exits the method. Prior DB changes **may commit** if the transaction was not marked rollback-only.

A generally better approach is to let the appropriate exception escape to the service boundary:

```java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void process() throws BusinessCheckedException {
    callBusinessOperation();
}
```

When logging is needed, you can catch to log **and then rethrow** the exception. Do not catch-and-ignore merely to avoid declaring `throws`.

### 7.2. Wrapping a Checked Exception into an Unchecked Exception

```java
@Transactional
public void process() {
    try {
        callExternalOperation();
    } catch (java.io.IOException ex) {
        throw new IllegalStateException("Cannot process request", ex);
    }
}
```

If `callExternalOperation` is a method throwing `IOException`, this is a valid illustration of exception mechanics; `IllegalStateException` is unchecked so Spring rolls back by default. However, **do not wrap exceptions into runtime exceptions solely to control rollback** when the business API intends to keep checked exceptions; `rollbackFor = IOException.class` expresses intent more clearly and preserves the type contract.

### 7.3. Internal Bean Call: Proxy Does Not Intercept Self-Invocation

```java
@Service
public class WorkflowService {
    public void run() throws BusinessCheckedException {
        this.saveAndFail(); // Called on the instance itself, bypassing the proxy.
    }

    @Transactional(rollbackFor = BusinessCheckedException.class)
    public void saveAndFail() throws BusinessCheckedException {
        // Perform DB operations and throw a checked exception.
    }
}
```

If `run()` is called directly and no other transaction is active, `this.saveAndFail()` in standard Spring AOP proxy mode **does not trigger advice** on `saveAndFail`. When testing, call the method from another bean via an injected proxy or place the transaction at the appropriate public service boundary. Do not assume an annotation automatically applies to every Java call.

### 7.4. Exception Occurs After the Proxy Has Returned

```java
service.saveOrder(); // saveOrder's transaction already committed successfully.
throw new BusinessCheckedException("Later validation failed");
```

If `saveOrder` opens and ends its own transaction before returning, an exception thrown by the caller afterward **cannot roll back the already committed transaction**. To keep two steps in one transaction, place the transaction boundary on a service encompassing all DB operations, ensure calls go through the proxy, and configure rollback rules accordingly.

### 7.5. Transaction Owned by the Caller

With `Propagation.REQUIRED` (the default), a method can **join an existing transaction** instead of opening a new one. If an inner method has `rollbackFor` and throws a checked exception, the inner method's transaction interceptor can **mark the shared transaction rollback-only**. A caller that catches the exception and tries to commit may still receive `UnexpectedRollbackException`, because the physical transaction has already been marked for rollback.

Conceptual flow:

```text
outer @Transactional REQUIRED
    -> inner @Transactional(rollbackFor = BusinessCheckedException.class)
       (same transaction, call goes through inner proxy)
    -> inner throws BusinessCheckedException
    -> inner interceptor marks rollback-only
    -> outer catches exception and returns normally
    -> outer tries to commit => cannot commit the whole transaction
       (may receive UnexpectedRollbackException)
```

This description assumes both methods go through proxies and share the same transaction manager. You cannot “just catch to commit” once the transaction is already rollback-only. If `REQUIRES_NEW` is used, the inner method has an independent transaction requiring separate boundary analysis; do not use a new propagation just to hide errors.

### 7.6. The DB Itself Rejects Commit

Some SQL errors render a database transaction unable to continue or trigger constraints checked only at commit time. Even if Spring chooses **no rollback** for the Java exception, commit can still fail or the transaction may already be marked rollback-only. Do not write tests that only check exception counts; **read the data back on a separate connection after the transaction truly finishes**.

### 7.7. Annotation Misplaced, Missing Transaction Manager

`@Transactional` is metadata. You need Spring's transaction infrastructure and a transaction manager matching the resources used. On a service instantiated with `new` outside the Spring container, a private method, or a bean that does not receive a proxy, rollback rules may not be applied. A JDBC transaction does not automatically include a connection opened separately via `DriverManager.getConnection(...)` inside the method, nor does it automatically become a distributed transaction across two independent databases.

## 8. XML Configuration for Checked Exceptions

If an application uses XML-based declarative transactions, the equivalent of `rollbackFor` is the **`rollback-for` attribute of `<tx:method>`**:

```xml
<tx:advice id="txAdvice" transaction-manager="transactionManager">
    <tx:attributes>
        <tx:method name="processOrder"
                   propagation="REQUIRED"
                   rollback-for="demo.rollback.BusinessCheckedException"/>
        <tx:method name="get*" read-only="true"/>
        <tx:method name="*" propagation="REQUIRED"/>
    </tx:attributes>
</tx:advice>

<aop:config>
    <aop:pointcut id="serviceMethods"
                  expression="execution(* demo.rollback.service.*.*(..))"/>
    <aop:advisor pointcut-ref="serviceMethods"
                 advice-ref="txAdvice"/>
</aop:config>
```

This is an **illustrative XML snippet** that must be placed inside `<beans>` with full namespaces/schemas plus `transactionManager` and service bean declarations. The `processOrder` rule specifies that checked `BusinessCheckedException` triggers rollback. If the service is outside the pointcut or the call bypasses the proxy, this advice has no effect.

Key differences:

- Java annotation: `rollbackFor = BusinessCheckedException.class` is type-checked safely at compile time.
- XML: `rollback-for="demo.rollback.BusinessCheckedException"` is an **exception-name string**; use fully qualified names and avoid overly broad patterns like `"Exception"`.
- `no-rollback-for` serves the same purpose as `noRollbackFor`.
- One `<tx:method name="...">` is selected by method name, and Spring then applies that transaction attribute's rollback rules. It does **not merge** attributes from `processOrder` with the `*` fallback when multiple patterns match.

If XML does not use annotations, `<tx:annotation-driven/>` is not required, but the transaction advice and AOP advisor must be properly configured for the services requiring transactions. Avoid configuring overlapping advisors unless you actively verify their ordering and transaction managers.

## 9. Global Rollback Policy Since Spring Framework 6.2

Spring Framework **6.2+** provides a default rollback policy option for annotation-driven transactions:

```java
import static org.springframework.transaction.annotation.RollbackOn.ALL_EXCEPTIONS;

import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)
public class TransactionDefaultsConfig {
}
```

With `ALL_EXCEPTIONS`, **checked exceptions** also trigger rollback by default for transaction annotations handled by this infrastructure. Specific method-level rules, such as `noRollbackFor`, can still alter the outcome for specified exceptions. This option is useful if the entire application follows the rule “every exception is a transaction failure”, but flows that **intentionally commit when throwing a checked exception** must be reviewed before enabling it.

**Version limitation:** the `rollbackOn` attribute on `@EnableTransactionManagement` and the `RollbackOn` enum were added in **Spring Framework 6.2**; **do not copy this snippet into the Spring Boot 3.3.x example in section 5** (which uses Spring Framework 6.1) and expect it to compile. If your application uses another Spring version, check the actual API and policy before choosing a global configuration approach.

A project enabling the global `ALL_EXCEPTIONS` policy **will no longer produce** `After default checked: 1` as in the section 5 example; this is an intentional change from the traditional default behavior. Do not mix configurations and conclusions from two different environments.

## 10. Testing Rollback Properly

A valuable test must verify both **the exception** and **the DB state after the transaction ends**:

1. Set up known initial data using a transactional database.
2. Call the service via a Spring-container-managed bean, not directly via `new Service`.
3. Ensure the test does not accidentally open an enclosing transaction; `@Transactional` on a test usually makes Spring TestContext auto-roll back at the end of the test, which can mask how the service actually committed/rolled back.
4. Trigger a checked exception **after a successful DB operation** to distinguish default commit from explicit rollback.
5. Catch the exception at the caller **outside the service transaction**, then read the DB back.
6. Test default checked, configured checked, unchecked, and—if special policies exist—`noRollbackFor` cases.
7. If you need to verify behavior on PostgreSQL/MySQL, use the real DB engine (e.g., Testcontainers), because H2 does not fully emulate dialects/constraints/isolation/locking.

Expected table for the section 5 example:

| Method | Exception | Applied rule | Remaining ID after call |
| --- | --- | --- | --- |
| `defaultChecked(1L)` | `BusinessCheckedException` | Default does not roll back checked | `1` |
| `explicitChecked(2L)` | `BusinessCheckedException` | `rollbackFor = BusinessCheckedException.class` | Still only `1` |
| `defaultUnchecked(3L)` | `IllegalStateException` | Default rolls back runtime | Still only `1` |

If results differ, check the **transaction proxy**, **transaction manager**, **global rollback policy**, **call path**, **rollback-only**, **test transaction**, and **commit errors** before concluding the annotation does not work.

### Observing Transaction Status to Assist Debugging

In code running inside a thread-bound Spring transaction, you can check:

```java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
```

This snippet only illustrates checking `active`; it does not prove a commit occurred. `TransactionSynchronizationManager` observes thread-bound state for imperative transactions. With reactive transactions, transaction context propagation uses a different mechanism rather than a simple thread-local.

### When You Must Mark Rollback-Only Because Rethrowing Is Impossible

In very specific cases, code catches a checked exception and decides not to throw it yet still requires rollback:

```java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

// Inside a method managed by a Spring transaction interceptor:
TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
```

This is **programmatic** and depends on transaction advice being active on the call path. It is not a general recommendation to replace `rollbackFor`; for business logic that can propagate exceptions outward, declarative configuration and rethrowing are usually easier to understand and test.

## 11. Common Mistakes to Avoid

| Misconception/bad design | Why it is wrong | How to clarify |
| --- | --- | --- |
| “`throws Exception` makes Spring roll back automatically” | `throws` is a Java contract, not a rollback rule | Use `rollbackFor` when a checked exception must cancel the transaction |
| “All exceptions roll back by default” | Traditional default is only `RuntimeException`/`Error`; custom/global policies may exist | Check the actual configuration |
| “Catching the exception in the caller will roll back” | The caller may receive the exception **after the service commits** | Check transaction ownership and catch timing |
| “Catch and return is always safe” | The interceptor does not see a swallowed exception | Rethrow, or mark rollback-only when truly needed |
| “`rollbackForClassName="Exception"` matches exact class `Exception`” | Pattern is a substring, easily matching unintended types | Use `rollbackFor = BusinessException.class` |
| “A DB UPDATE failed, yet `noRollbackFor` will force commit” | The DB may have already marked the transaction failed/aborted | Handle resource errors; do not use rules to bypass the DB |
| “A `@Transactional` test behaves like production” | The test transaction may already be open and auto-roll back afterward | Verify the test's own transaction boundaries |
| “Calling an annotated method in the same object runs advice” | Self-invocation bypasses proxy mode | Call through a Spring-managed proxy/service boundary |
| “Spring DB rollback will undo external emails/APIs” | Non-DB side effects are outside the local transaction | Use outbox, after-commit events, idempotency |
| “Every checked exception is a business failure needing rollback” | Some states require intentional commit | Define a clear exception contract and rollback policy |

## 12. Self-Assessment Questions

**1. `BusinessException extends Exception` is thrown out of a default `@Transactional` method after JDBC executes an INSERT. Is rollback guaranteed?**  
No. Under the traditional rollback configuration, Spring does not choose rollback for that checked exception, so it may commit if the transaction is new, the DB is healthy, and there is no rollback-only flag. `rollbackFor = BusinessException.class` is needed if you want rollback for that type.

**2. Does `@Transactional(rollbackFor = IOException.class)` require changing `IOException` into a `RuntimeException`?**  
No. Spring is configured to roll back when checked `IOException` exits the method, while the Java API keeps the checked exception.

**3. Why does `JdbcTemplate` causing a SQL error usually roll back even though `SQLException` is checked?**  
Because Spring JDBC typically translates `SQLException` into unchecked `DataAccessException`; the actual type reaching the transaction interceptor is what determines default rollback.

**4. If a method catches `BusinessCheckedException` and returns normally, does `rollbackFor` activate automatically?**  
No, because the interceptor sees no escaping exception; unless the transaction was already marked rollback-only for another reason.

**5. Does `noRollbackFor` prevent the caller from receiving the exception?**  
No. It only changes the rollback/commit decision when the transaction manager can commit; the exception is still propagated to the caller.

**6. Why should tests run outside the service's transaction?**  
To observe the commit/rollback decision **after the call through the proxy**, without an enclosing test/caller transaction skewing the result.

**7. Does Spring Framework 6.2+ require all checked exceptions to roll back by default?**  
No. `ALL_EXCEPTIONS` is a **global configuration option**, not the traditional default; when enabled, behavior toward checked exceptions changes.

## 13. Takeaways and Design Rules

**Checked exceptions do not automatically trigger rollback in Spring's traditional default transactions.** When a checked exception must cancel a business operation, write an explicit rule—typically **`@Transactional(rollbackFor = YourCheckedException.class)`**. When an exception should still allow commit, document that intent through the API contract and tests.

Confirming the right rollback policy comes down to four sequential questions:

1. **Which call starts or joins the transaction?** Does it go through a Spring proxy and the right transaction manager?
2. **What exception type actually exits the transactional boundary?** Checked, unchecked, wrapped, or caught?
3. **Which rule decides the outcome?** Default, `rollbackFor`, `noRollbackFor`, or a global rollback option?
4. **What data remains in the database after the transaction ends?** Read the DB back rather than inferring from whether SQL or `save()` executed.

When those four answers are clear, you can design transaction atomicity to match business semantics rather than relying on assumptions about exceptions.

## References

- Spring Framework, *Rolling Back a Declarative Transaction*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html
- Spring Framework 6.2, *Using @Transactional* — defaults, `rollbackFor` and global `rollbackOn`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework, *Declarative Transaction Implementation and Proxy*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework, *<tx:advice/> Settings*: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/txadvice-settings.html
- Spring Framework API, *RollbackRuleAttribute*: https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/transaction/interceptor/RollbackRuleAttribute.html
- Spring Framework API, *RollbackOn enum (since 6.2)*: https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/RollbackOn.html
- Spring Boot 3.3, *SQL Databases*: https://docs.spring.io/spring-boot/3.3/reference/data/sql.html
- Spring Boot 3.3, *SQL Database Initialization*: https://docs.spring.io/spring-boot/3.3/how-to/data-initialization.html
