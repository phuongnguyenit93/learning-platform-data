# timeout, timeoutString, and Placeholder Configuration in @Transactional

> **Context:** Spring Framework — Transaction Management — `@Transactional`. This lesson explains the two attributes `timeout` and `timeoutString`, how to supply seconds from external configuration via placeholders, the actual enforcement mechanism, the impact of propagation, cases where timeout has no effect, and how to verify configuration. The runnable example uses **Java 17**, **Spring Boot 3.5.7 / Spring Framework 6.2**, and **JDBC/H2**, though the core principles apply across Spring Framework when using an appropriate transaction manager.

## 1. What Is Transaction Timeout and Which Problem Does It Solve?

A transaction kept open too long can hold database connections, locks, and other resources, increasing contention, deadlock risk, query latency, and connection pool exhaustion. **Transaction timeout** is a time limit that the transaction manager/transactional resource can use to constrain a transaction.

For example, a business operation needs to transition an order status and insert an audit record in the same transaction. To prevent database operations from holding resources indefinitely, you can declare:

```java
@Transactional(timeout = 5)
public void confirmOrder(long orderId) {
    // Database operations via repository/JdbcTemplate.
}
```

`timeout = 5` configures a transaction timeout of **5 seconds** for a **new transaction** started by this call. This is Spring metadata: how strictly the deadline is enforced depends on the transaction manager, JDBC driver, database, and kind of work. Do not think of it as a timer that automatically kills the Java method at the exact fifth second.

Distinguish these upfront:

| Limit | Scope | Example |
| --- | --- | --- |
| Transaction timeout | Transaction managed by Spring's transaction manager | `@Transactional(timeout = 5)` |
| Query/statement timeout | A single SQL/JDBC statement | `Statement.setQueryTimeout(3)` |
| Connection acquisition timeout | Time waiting to borrow a connection from the pool | HikariCP `connectionTimeout` setting |
| Network connect/read timeout | HTTP or socket connect/read | HTTP client timeout |
| Request deadline | Entire API request, spanning multiple steps | Server/gateway/application deadline |
| Lock timeout | Time waiting for a lock in the database | Specific settings in PostgreSQL, MySQL, etc. |

**No single timeout automatically replaces the others.** A transaction can block waiting on a lock; an HTTP client can time out; and Java code can compute for a long time even when Spring has declared a transaction limit.

## 2. Two Attributes: `timeout` and `timeoutString`

The `@Transactional` discussed here is Spring's `org.springframework.transaction.annotation.Transactional`, not the JTA annotation `jakarta.transaction.Transactional` (JTA does not provide these two attributes under the same API).

### 2.1. `timeout`: Fixed Integer in Source Code

```java
import org.springframework.transaction.annotation.Transactional;

@Transactional(timeout = 10)
public void importSmallBatch() {
    // Transaction timeout is declared as 10 seconds.
}
```

- Java type: `int`.
- Unit: **seconds**, not milliseconds, `Duration`, or minutes.
- Use when you want a clear, fixed number directly in code.
- Annotation default value: `TransactionDefinition.TIMEOUT_DEFAULT`, i.e. **-1**, indicating use of the transaction infrastructure's default timeout (which may be unlimited if the system does not support timeouts).
- Because this is an `int` annotation element, the value must be a **compile-time constant**. You can use literal `10` or a valid `static final int` constant; you cannot pass a placeholder string or `@Value` field here.

### 2.2. `timeoutString`: String Representing Seconds

```java
@Transactional(timeoutString = "10")
public void importSmallBatch() {
    // 10-second timeout, represented as a String.
}
```

`timeoutString` has the same meaning in **seconds** as `timeout`, but its Java type is `String`. This attribute was introduced in **Spring Framework 5.3**; its main advantage is supporting placeholders:

```java
@Transactional(timeoutString = "${app.tx.import-seconds}")
public void importSmallBatch() {
    // Gets timeout from Spring-resolved configuration.
}
```

After Spring resolves it, the result must parse to a **valid integer number of seconds**. For instance, `"10"` is valid; `"10s"`, `"PT10S"`, and `"500ms"` are not the integer-seconds format expected by this attribute. If you want `Duration`-style configuration elsewhere, convert it cleanly to integer seconds before applying via an appropriate programmatic API.

### 2.3. Quick Comparison Table

| Criterion | `timeout` | `timeoutString` |
| --- | --- | --- |
| Attribute type | `int` | `String` |
| Unit | Seconds | Seconds |
| Fixed form | `timeout = 10` | `timeoutString = "10"` |
| Placeholder `${...}` | Cannot be assigned to `int` | Yes |
| Annotation default value | `-1` | Empty string `""` |
| Different values for dev/staging/prod | Requires editing source or another mechanism | Change config/property |
| Deadline semantics after resolution | Same transaction timeout semantics | Same transaction timeout semantics |

**Pick exactly one of the two** to set an explicit timeout on a `@Transactional`. Do not declare both `timeout = 5` and `timeoutString = "7"` simultaneously: Spring treats this as a conflicting declaration and rejects the configuration instead of silently picking one.

## 3. What Problem Do `${...}` Placeholders Solve?

Many systems need different timeouts across local, staging, and production, or need tuning after observing performance. If you hard-code `@Transactional(timeout = 5)`, changing the value usually requires editing Java code and rebuilding. With `timeoutString`, the policy lives in properties:

```java
@Service
public class ExportService {

    @Transactional(timeoutString = "${app.transaction.export-timeout-seconds}")
    public void exportToDatabase() {
        // Operations inside the transaction.
    }
}
```

```properties
# src/main/resources/application.properties
app.transaction.export-timeout-seconds=15
```

When Spring parses and resolves the transaction attribute, `${app.transaction.export-timeout-seconds}` becomes `"15"`, and is then interpreted as **15 seconds**.

You can also declare a **fallback value directly inside the placeholder**:

```java
@Transactional(timeoutString = "${app.transaction.export-timeout-seconds:15}")
public void exportToDatabase() {
    // Uses 15 seconds if the property is not provided.
}
```

The `${key:default}` syntax is Spring's placeholder syntax; `:15` is the value used when the key is missing. Avoid unverified fallback values in highly sensitive workflows: you should know which actual value the application uses.

### 3.1. Externalizing by Environment

Example with Spring Boot:

```properties
# application.properties
app.tx.checkout-seconds=8
app.tx.report-seconds=30
```

```java
@Transactional(timeoutString = "${app.tx.checkout-seconds:8}")
public void checkout() {
    // Transaction maximum per checkout configuration.
}

@Transactional(timeoutString = "${app.tx.report-seconds:30}",
               readOnly = true)
public void buildReport() {
    // Reporting transaction.
}
```

In production you can override `app.tx.checkout-seconds` via an environment variable compatible with Spring Boot's property binding, or pass a command-line argument:

```bash
java -jar target/transaction-timeout-demo-1.0.0.jar \
  --app.tx.checkout-seconds=12
```

This example command is for shells supporting `\` line continuation (like Bash); on PowerShell/Windows you can write it on **one line**. Boot's CLI prioritizes configuration sources according to property precedence. One environment overriding another **does not require changing the source annotation**.

### 3.2. Defining an Explicit Environment Variable

You can route through a dedicated environment variable name:

```properties
# application.properties
app.tx.checkout-seconds=${CHECKOUT_TX_SECONDS:8}
```

```java
@Transactional(timeoutString = "${app.tx.checkout-seconds}")
public void checkout() {
    // 8 seconds by default when CHECKOUT_TX_SECONDS is not declared.
}
```

For example, setting `CHECKOUT_TX_SECONDS=12` before starting the application makes the placeholder ultimately resolve to `12`. Separating configuration this way lets the annotation reference a stable business key while deployment manages how the value is supplied.

### 3.3. Distinguishing Resolution Time from Transaction Start Time

Normally, `timeoutString` is resolved by Spring from configuration/environment when the infrastructure parses transaction attributes and caches method metadata. It is **not an expression re-evaluated per HTTP request or per record**.

Editing `application.properties` on disk while the JVM is running **does not automatically update the timeout of an active annotation**. You need a refresh/bean-recreation mechanism for transaction metadata, or more simply, update configuration and restart/redeploy. If you need to compute timeouts per **individual invocation** based on call data, see `TransactionTemplate` in Section 9.

## 4. Interaction Rules with Propagation and Existing Transactions

The timeout setting applies when **a new transaction is actually started**. This is the most important condition to avoid misreading annotations.

`@Transactional` defaults to `Propagation.REQUIRED`:

- **No current transaction:** `REQUIRED` opens a new transaction. The timeout declared on that call can be applied.
- **Current transaction already exists:** `REQUIRED` joins the existing transaction. It does not open a new physical transaction, so a timeout declared on the participating method **does not reset the clock** or create a new deadline.
- **`REQUIRES_NEW`:** suspends the current transaction (if any) and opens an independent transaction; the new transaction's timeout applies to that new boundary. Understand the impact on connection pools, locks, and independent commit/rollback.
- **`SUPPORTS`/`NOT_SUPPORTED`/`NEVER`:** do not expect annotation timeouts to create a new transaction deadline, since these modes do not create a new transaction in the required sense.
- **`NESTED`:** typically a savepoint within the same JDBC transaction; not a new physical transaction with an independent clock.

### 4.1. Example: Outer 30 Seconds, Inner 5 Seconds

```java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional(timeout = 30)
    public void runJob() {
        inner.runPart();
    }
}

@Service
class InnerService {
    @Transactional(timeoutString = "${app.tx.part-seconds:5}")
    public void runPart() {
        // Default REQUIRED: joins runJob()'s transaction.
    }
}
```

This is an **illustrative excerpt**, requiring a Spring application with proper transaction manager and proxies. If the caller passes through the Spring proxies of `OuterService` and `InnerService`:

1. `OuterService.runJob()` creates a new transaction with a 30-second timeout.
2. `InnerService.runPart()` is called through the proxy, yet `REQUIRED` **joins the existing transaction**.
3. The value `5` on `runPart()` **does not automatically shorten the existing transaction to 5 seconds**. The original deadline of the transaction created by `runJob()` still governs.

If the inner work truly needs an independent transaction, you can declare:

```java
@Transactional(
    propagation = Propagation.REQUIRES_NEW,
    timeoutString = "${app.tx.part-seconds:5}"
)
public void runPart() {
    // New transaction, with its own timeout.
}
```

Requires importing `org.springframework.transaction.annotation.Propagation`. `REQUIRES_NEW` **is not a default trick to "force a shorter timeout"**: it creates a separate physical transaction and commit/rollback boundary. An outer transaction may roll back while the inner transaction has already committed, so only use it when that independence fits the business logic.

### 4.2. Class Level and Method Level

```java
@Transactional(timeoutString = "${app.tx.default-seconds:15}")
@Service
class BillingService {

    public void regularOperation() {
        // Inherits transaction settings declared at class level,
        // when called through Spring's transaction mechanism.
    }

    @Transactional(timeout = 3)
    public void urgentOperation() {
        // Method annotation overrides class-level settings.
    }
}
```

A more specific annotation on a method has **higher precedence** than a class-level annotation. Spring does not "merge the method's `timeout` with the class's `timeoutString`" into two conflicting values: the transaction attribute is determined from the configuration selected for the method.

## 5. How Is Timeout Enforced in JDBC?

With `DataSourceTransactionManager` or `JdbcTransactionManager`, Spring manages a JDBC connection per transaction. When a timeout is declared for a new transaction, Spring stores the deadline in the connection/transaction context. JDBC operations through `JdbcTemplate` can query the **remaining time** and set the timeout on the corresponding `Statement`.

General sequence:

```text
T=0s  Caller enters proxy of @Transactional(timeout=5)
      -> transaction manager starts transaction, sets deadline.

T=2s  JdbcTemplate creates PreparedStatement
      -> Spring sets query timeout based on remaining time.

T=5s  Transaction deadline reached.
      -> Database access / deadline check may fail.

Afterward, transaction manager handles commit/rollback
based on exception, rollback-only, and resource capabilities.
```

This **does not mean** Spring forcibly interrupts a CPU loop, `Thread.sleep`, HTTP call, or child process at the exact 5-second mark. In JDBC, timeout usually relies on the driver/database query timeout and transaction deadline checks when the framework interacts with the resource. Actual timing and exception types vary across drivers, databases, and execution methods.

`JdbcTemplate` applies timeout via Spring's JDBC mechanism. If using low-level JDBC, code must obtain the transaction-aware connection (such as `DataSourceUtils.getConnection`) and apply the transaction deadline to each `Statement` using `DataSourceUtils.applyTransactionTimeout` or an appropriate datasource proxy.

**API excerpt** example:

```java
Connection con = DataSourceUtils.getConnection(dataSource);
try {
    PreparedStatement stmt =
        con.prepareStatement("UPDATE jobs SET state = ? WHERE id = ?");
    try (stmt) {
        DataSourceUtils.applyTransactionTimeout(stmt, dataSource);
        stmt.setString(1, "DONE");
        stmt.setLong(2, jobId);
        stmt.executeUpdate();
    }
} finally {
    DataSourceUtils.releaseConnection(con, dataSource);
}
```

The snippet assumes `dataSource` and `jobId` exist; it requires importing `java.sql.Connection`, `java.sql.PreparedStatement`, and `org.springframework.jdbc.datasource.DataSourceUtils`, and should only sit **inside an already-open transaction**. Using `JdbcTemplate` remains the less error-prone approach. Never manually call `commit()`, `rollback()`, or `close()` on a Spring-managed connection.

### 5.1. Exceptions That May Appear

When a timeout is actually detected, depending on the mechanism you may see:

- `org.springframework.transaction.TransactionTimedOutException` when Spring detects the transaction deadline has expired.
- `org.springframework.dao.QueryTimeoutException` or a `DataAccessException` subtype when a query times out and Spring translates the database error.
- A `SQLException` or driver/framework-specific exception if that layer does not translate it as above.
- An additional exception at commit/rollback if the resource is in an error state or already marked rollback-only.

Therefore, **do not hard-code expectations that every timeout throws exactly `TransactionTimedOutException`**. If an unchecked exception escapes through the transaction interceptor, the default policy normally rolls back the transaction. If you catch and swallow the error inside, or if the database is still processing/in an uncertain state, verify the real outcome and rollback policy.

### 5.2. Timeout Does Not Guarantee Canceling External Side Effects

Suppose a `@Transactional(timeout = 5)` method both updates database A and makes an external payment HTTP call. If the HTTP request completes after A expires, rolling back database A **does not automatically reverse** the charge in the payment system. Protecting cross-system workflows requires separate HTTP timeouts, idempotency, handling of uncertain states, and business reconciliation/compensation.

## 6. Complete Java 17 Example: Observing Timeout Resolved from Properties

**Goal of the demo:** create two JDBC transactions with different annotations, verify that `timeout = 3` and `timeoutString` resolve to `7` from configuration, prove that methods called through a Spring bean actually run inside transactions, and write two rows successfully. The demo **does not try to simulate slow SQL with `Thread.sleep`**, because that is not a reliable test of JDBC timeout enforcement.

The project requires JDK 17 and Maven 3.9+; no separate H2 installation is needed.

Structure:

```text
transaction-timeout-demo/
├── pom.xml
└── src/main/
    ├── java/vn/example/tx/
    │   ├── TimeoutDemoApplication.java
    │   └── AuditService.java
    └── resources/
        └── application.properties
```

### 6.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.7</version>
        <relativePath/>
    </parent>

    <groupId>vn.example</groupId>
    <artifactId>transaction-timeout-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-jdbc</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Spring Boot configures an H2 `DataSource` and appropriate JDBC transaction manager when dependencies and auto-configuration conditions are met. `@EnableTransactionManagement` in the example makes the intent to activate transaction annotation processing explicit.

### 6.2. `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:timeout_demo;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=

# If no environment variable is passed, use 7 seconds.
demo.tx.configured-seconds=${TX_TIMEOUT_SECONDS:7}
```

The key `demo.tx.configured-seconds` is custom to this application, **not** a built-in Spring Boot timeout property. `${TX_TIMEOUT_SECONDS:7}` lets you override the value via environment without editing Java code. If no environment variable is supplied, the configured timeout is 7 seconds.

### 6.3. `src/main/java/vn/example/tx/AuditService.java`

```java
package vn.example.tx;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class AuditService {
    private final JdbcTemplate jdbc;

    public AuditService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(timeout = 3)
    public void saveFixed(long id, String details) {
        jdbc.update(
            "INSERT INTO audit_events(id, details) VALUES (?, ?)",
            id, details
        );
    }

    @Transactional(timeoutString = "${demo.tx.configured-seconds:7}")
    public boolean saveConfigured(long id, String details) {
        jdbc.update(
            "INSERT INTO audit_events(id, details) VALUES (?, ?)",
            id, details
        );
        return TransactionSynchronizationManager
            .isActualTransactionActive();
    }
}
```

Two distinct methods for clear observation:

- `saveFixed()` uses a **fixed 3-second timeout**.
- `saveConfigured()` uses **`timeoutString`** from a property, defaulting to 7 seconds if not configured otherwise.
- `TransactionSynchronizationManager.isActualTransactionActive()` checks the transaction status on the current thread **while the method is running**. It returns `true` in this demo; this checks that a transaction is active, **not that a timeout was enforced by the database**.

### 6.4. `src/main/java/vn/example/tx/TimeoutDemoApplication.java`

```java
package vn.example.tx;

import java.lang.reflect.Method;
import java.util.Objects;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.EnableTransactionManagement;
import org.springframework.transaction.interceptor.TransactionAttribute;
import org.springframework.transaction.interceptor.TransactionAttributeSource;

@SpringBootApplication
@EnableTransactionManagement
public class TimeoutDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(TimeoutDemoApplication.class, args);
    }

    @Bean
    CommandLineRunner run(JdbcTemplate jdbc,
                          AuditService service,
                          TransactionAttributeSource attributes) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE audit_events (" +
                "id BIGINT PRIMARY KEY, " +
                "details VARCHAR(80) NOT NULL)"
            );

            service.saveFixed(1L, "fixed");
            boolean active = service.saveConfigured(2L, "configured");

            System.out.println("fixed-timeout-seconds=" +
                timeoutOf(attributes, "saveFixed"));
            System.out.println("configured-timeout-seconds=" +
                timeoutOf(attributes, "saveConfigured"));
            System.out.println("active-inside-transaction=" + active);
            System.out.println("rows=" + jdbc.queryForObject(
                "SELECT COUNT(*) FROM audit_events", Integer.class));
        };
    }

    private static int timeoutOf(TransactionAttributeSource source,
                                 String methodName)
            throws NoSuchMethodException {
        Method method = AuditService.class.getMethod(
            methodName, long.class, String.class
        );
        TransactionAttribute attribute =
            source.getTransactionAttribute(method, AuditService.class);

        return Objects.requireNonNull(attribute,
            "Missing transaction attribute for " + methodName
        ).getTimeout();
    }
}
```

The `timeoutOf` method queries **Spring's resolved transaction metadata**, rather than reading the raw annotation string via plain reflection. `getTimeout()` on `TransactionAttribute` returns the seconds after resolving `timeoutString`. This verifies that the property key resolved properly, though a separate integration test is still needed to prove the database/driver enforces the deadline on a slow query.

The runner calls `AuditService` from another Spring bean, avoiding self-invocation. Both INSERTs run in separate transactions and commit normally. `TransactionAttributeSource` is configured automatically by Spring when `@EnableTransactionManagement` is active.

### 6.5. Running and Comparing

From the project directory:

```bash
java -version
mvn -version
mvn -q package
java -jar target/transaction-timeout-demo-1.0.0.jar
```

**When the `TX_TIMEOUT_SECONDS` environment variable is not set**, the lines explicitly printed by the application are:

```text
fixed-timeout-seconds=3
configured-timeout-seconds=7
active-inside-transaction=true
rows=2
```

Spring Boot may print additional startup logs; only the lines above are the intended business output.

Try changing the value **at startup** without modifying code:

```bash
java -jar target/transaction-timeout-demo-1.0.0.jar \
  --demo.tx.configured-seconds=12
```

Now `configured-timeout-seconds` becomes **12**, while `fixed-timeout-seconds` remains **3**, `active-inside-transaction` remains `true`, and `rows` remains **2**. For PowerShell, write `java -jar ... --demo.tx.configured-seconds=12` on **one line**.

> **Important distinction:** This demo verifies **annotation and property resolution**, not canceling a query at the exact 3rd/7th second. A timeout integration test should use a real database/driver with a controlled lock wait or long query, then verify rollback, connection/lock release, and the actual exception type.

## 7. When Is Timeout Used, and When Is It Ignored?

| Scenario | Does timeout take effect? | Explanation |
| --- | --- | --- |
| Caller enters `@Transactional(timeout=5)` with no prior transaction | **Can apply** | `REQUIRED` opens a new transaction with value 5. |
| Caller enters `@Transactional(timeoutString="${...}")`, resolved to 8, no prior transaction | **Can apply** | Same as `timeout=8`, depending on manager/resource. |
| 30-second transaction already exists; inner `REQUIRED` method declares timeout 5 seconds | **Does not reset to 5** | Inner joins the existing transaction. |
| Inner `REQUIRES_NEW` declares timeout 5 seconds | **Yes, for the new transaction** | Outer transaction is suspended; inner has its own boundary. |
| Calling `this.innerMethod()` in the same bean under default proxy mode | **May not open a new transaction as expected** | The call bypasses the Spring proxy. |
| Using `Thread.sleep(20000)` inside a method with timeout 5 seconds | **Not guaranteed to interrupt thread at 5 seconds** | Transaction timeout is not a thread interruption timer. |
| Using `JdbcTemplate` with `JdbcTransactionManager`/`DataSourceTransactionManager` | **Integrated into JDBC statements** | Can pass remaining time to query timeout. |
| Using raw non-transaction-aware JDBC connection/statement | **May not apply fully** | Must use Spring-managed connections/statements. |
| Making HTTP/email calls inside a JDBC transaction | **Does not set network timeouts or roll back remote side effects** | Requires separate deadlines/client timeouts, deduplication, and compensation. |
| Omitting timeout on annotation | Follows **manager/system default** | Not guaranteed to be the same fixed value across all systems. |

The phrase "can apply" in the table emphasizes that the annotation supplies **transaction timeout intent**; enforcement depends on the transaction manager, database, driver, and how resources are accessed.

## 8. Configuring a Default Timeout on the Transaction Manager

When many methods do not declare `timeout`/`timeoutString`, you may want a default policy. For a manager extending `AbstractPlatformTransactionManager`, an example configuration is:

```java
@Configuration
@EnableTransactionManagement
class TransactionConfig {

    @Bean
    JdbcTransactionManager transactionManager(DataSource dataSource) {
        JdbcTransactionManager manager =
            new JdbcTransactionManager(dataSource);
        manager.setDefaultTimeout(20);
        return manager;
    }
}
```

This is a **separate configuration excerpt**, requiring imports for `javax.sql.DataSource`, `org.springframework.context.annotation.Bean`, `org.springframework.context.annotation.Configuration`, `org.springframework.transaction.annotation.EnableTransactionManagement`, and `org.springframework.jdbc.support.JdbcTransactionManager`. It illustrates a **20-second** manager default timeout; **do not copy this into Section 6's demo** because Spring Boot auto-configures the transaction manager there.

Resolution rules:

1. If a method declares `@Transactional(timeout=3)`, the value 3 applies when the method opens a new transaction.
2. If a method declares `@Transactional(timeoutString="${...}")` and the property resolves to 7, the value 7 applies when the method opens a new transaction.
3. If a method only has `@Transactional`, the manager can use `defaultTimeout=20`.
4. If the manager has no configured timeout either, the system uses the underlying transaction infrastructure's default timeout, or no timeout if the resource does not support one.

A **custom** property like `app.tx.default-seconds` does not automatically make the transaction manager read it; you must reference it in the annotation or pass it to the manager configuration in code.

## 9. Runtime-Computed Timeout: `TransactionTemplate`

`@Transactional(timeoutString = "${...}")` fits an **application-wide configuration value**. If each batch has a different SLA based on call parameters, a programmatic API may be more appropriate.

**Illustrative excerpt**, assuming `PlatformTransactionManager manager` and `JdbcTemplate jdbc` exist:

```java
public void processBatch(int timeoutSeconds) {
    if (timeoutSeconds < 1 || timeoutSeconds > 300) {
        throw new IllegalArgumentException(
            "timeoutSeconds must be 1..300"
        );
    }

    TransactionTemplate tx = new TransactionTemplate(manager);
    tx.setTimeout(timeoutSeconds);
    tx.executeWithoutResult(status -> {
        jdbc.update(
            "UPDATE batch_jobs SET state = 'RUNNING' WHERE id = 42"
        );
    });
}
```

Requires importing `org.springframework.transaction.support.TransactionTemplate`. Unlike static annotations, `setTimeout(timeoutSeconds)` accepts a runtime value. However, if the callback **joins** an existing transaction (default `REQUIRED` propagation), the new timeout still does not shorten the original physical deadline. If an independent new transaction is required, design propagation, commit/rollback, resources, and concurrency effects properly.

Creating a dedicated `TransactionTemplate` per invocation as shown avoids sharing/mutating timeout state on a single template instance across multiple threads. Validate input bounds to prevent invalid values or uncontrolled SLA configurations.

## 10. Common Errors and Misconceptions

### 10.1. Using a Placeholder on the `int` `timeout` Attribute

**Invalid Java syntax:**

```java
@Transactional(timeout = "${app.tx.seconds}")
public void work() {
}
```

`timeout` requires an `int`, so the source fails to compile because the literal is a `String`. **Correct** is:

```java
@Transactional(timeoutString = "${app.tx.seconds:5}")
public void work() {
}
```

### 10.2. Declaring Both Values Simultaneously

**Invalid transaction metadata:**

```java
@Transactional(timeout = 5, timeoutString = "${app.tx.seconds:8}")
public void work() {
}
```

Do not use both on the same annotation with two actual values; Spring's parser can throw `Specify 'timeout' or 'timeoutString', not both` when reading transaction metadata. Choose one attribute.

### 10.3. Confusing Units

**Incorrect** if you want 5 seconds: `@Transactional(timeout=5000)`, because that is **5,000 seconds**, not 5,000 milliseconds. Write `timeout=5` or `timeoutString="5"`.

### 10.4. Missing or Non-Integer Property

```java
@Transactional(timeoutString = "${app.tx.seconds}")
public void work() {
}
```

If `app.tx.seconds` does not exist, has no default, and is not resolved—or receives a non-numeric string like `"fast"`—Spring may fail during transaction attribute parsing/startup or when the method is first used. Do not rely on the exact failure timing; check properties in startup/integration tests, and favor explicit defaults and deployment input validation.

### 10.5. Using `@Value` as If It Were an Annotation Value

```java
@Value("${app.tx.seconds}")
private int seconds;
```

The `seconds` field can be injected, yet Java does not allow `@Transactional(timeout = seconds)`: annotation elements require compile-time constants. `@Value` and `timeoutString` are different mechanisms; for annotations, use placeholders via `timeoutString`.

### 10.6. Inner Method Joining an Existing Transaction

An inner method annotated with `timeout=1` is not guaranteed to fail after 1 second when it joins an outer 60-second transaction. Check the call graph, proxy boundaries, and propagation before concluding Spring "ignored timeout".

### 10.7. Using `Thread.sleep` to "Prove Timeout"

```java
@Transactional(timeout = 1)
public void slowCpuWork() throws InterruptedException {
    Thread.sleep(5000);
}
```

This is an **illustrative counterexample snippet**, not suitable for testing transaction timeout. A sleeping task is not necessarily aborted by Spring after 1 second. Only an actual JDBC operation that checks or enforces the deadline will observe related errors; committing after expiration also depends on the manager/resource. Do not equate 5 seconds of sleep with 5 seconds of SQL waiting.

### 10.8. Catching the Exception and Returning Success

For example, catching `DataAccessException` and ignoring it prevents the interceptor from seeing an escaping exception; depending on the manager/transaction state, it may fail to roll back as expected or hit rollback-only issues. Explicitly define timeout errors as business failures, throw an appropriate error, or intentionally mark rollback-only; never assume all states are safe after swallowing exceptions.

### 10.9. Confusing Request Timeout with Transaction Timeout

A gateway timeout at 10 seconds does not prove the database transaction rolled back at 10 seconds. Client disconnection may not stop server work. Synchronous timeout design across HTTP client/server, queue waits, pool waits, database queries/locks, and transaction deadlines must be consistent, yet they **are distinct mechanisms**.

### 10.10. Calling Another Service or Running `@Async`

Spring imperative transactions are normally bound to the current thread; spawning another thread or calling `@Async` does not automatically carry over the caller's transaction boundary or deadline. Calls to another microservice do not become participants via annotations either. Design new transactions at the handler, propagate deadlines via API contracts where applicable, and ensure idempotency for side effects.

## 11. How to Test Timeout Meaningfully

### Configuration-Level Tests

- With property `app.tx.seconds=8`, verify that transaction metadata for the method using `timeoutString` resolves to **8**; change it to **12** and verify it resolves to 12 in the corresponding application context.
- Verify a `timeout=3` method always has metadata 3 regardless of properties.
- Verify missing/invalid properties are caught according to your startup/test policy.
- Verify declaring both attributes is caught as a configuration error to fix, rather than accepting implicit outcomes.

### Transaction-Level Tests

Use PostgreSQL/MySQL or the actual production database/driver in integration tests, with a controlled **lock-wait/long-query scenario**, then:

1. Call the service bean through the Spring proxy, ensuring the method creates a new transaction rather than joining an existing one.
2. Configure a short enough timeout for bounded test runtime, while avoiding tiny thresholds that cause flakiness.
3. Check the exception type produced in your **specific stack** rather than hard-coding one type across all databases.
4. Verify the transaction rolled back by reading from a separate connection/transaction.
5. Confirm connections/locks are released and subsequent requests are not stuck.
6. Also test an inner `REQUIRED` vs. inner `REQUIRES_NEW` to observe differing deadlines per transaction boundary.
7. If a Spring Test method itself has `@Transactional`, check whether the service is **joining the test transaction**; this can prevent the service's annotation timeout from applying as expected.

If using `Thread.sleep` to simulate CPU work, treat it as a test of another behavior, **not as proof that transaction timeout enforces SQL limits**.

### Operational Observability

When timeout errors occur, log the transaction name, request/correlation ID, elapsed time, database/pool name, exception class, and retry context. Track long-running transactions, lock waits, query timeouts, waiting connection counts, and rollback rates. Never log secrets, SQL containing sensitive data, or unnecessary user payloads.

## 12. Checklist for Choosing and Applying Timeout

- [ ] Use Spring's `org.springframework.transaction.annotation.Transactional`.
- [ ] Choose `timeout = n` for a fixed integer seconds value or `timeoutString = "${key:default}"` for external configuration.
- [ ] Never declare both `timeout` and `timeoutString` together.
- [ ] Final resolved value is a valid integer number of seconds, with explicit defaults and validation.
- [ ] Transaction infrastructure is enabled; the service is a Spring bean and calls go through the proxy.
- [ ] Know whether the method **starts a new transaction** or only joins an existing one.
- [ ] If using `REQUIRES_NEW`, evaluate connection pools, locks, and independent commit/rollback semantics.
- [ ] Verified that the transaction manager and JDBC/JPA resource actually support the needed timeout.
- [ ] Do not confuse transaction timeout with HTTP, statement, pool, or request timeouts.
- [ ] Have integration tests on a matching database/driver verifying rollback, rather than inferring from `Thread.sleep`.
- [ ] Configuration is externalized, observable, and updated through a clear deployment/configuration lifecycle.
- [ ] If timeouts can occur alongside external non-DB side effects, handle uncertain outcomes and reconciliation.

**Takeaway:** `timeout` and `timeoutString` both specify **the timeout in seconds for a new transaction**. `timeout` takes a fixed `int`; `timeoutString` takes a `String`, which is especially useful with `${...}` placeholders. Annotations declare **policy**, while the transaction manager/driver/database determine **how it is enforced**. A timeout on a `REQUIRED` method does not refresh the deadline of an existing transaction it joins.

## Official Sources for Reference

- Spring Framework 6.2 — [`@Transactional`: configuring timeout, timeoutString, propagation](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html).
- Spring Framework 6.2 — [`@Transactional` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html).
- Spring Framework — [`DefaultTransactionAttribute` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/interceptor/DefaultTransactionAttribute.html): `setTimeoutString` and `resolveAttributeStrings`.
- Spring Framework — [`DataSourceTransactionManager` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceTransactionManager.html): JDBC transaction timeout and `JdbcTemplate`.
- Spring Framework — [`DataSourceUtils` Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/jdbc/datasource/DataSourceUtils.html): `applyTransactionTimeout`.
- Spring Boot — [Externalized Configuration](https://docs.spring.io/spring-boot/3.5/reference/features/external-config.html): property sources, environment, and command-line arguments.
