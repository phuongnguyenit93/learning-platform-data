# rollbackFor and noRollbackFor by Exception Type

## 1. Two Attributes That Decide Rollback by Error Type

In Spring Framework, `@Transactional` can manage a transaction spanning multiple database operations. When the method finishes normally, the transaction manager usually tries to **commit**; when an exception escapes a Spring-managed call, the transaction interceptor must decide whether to **roll back or commit**. Two key attributes are:

- **`rollbackFor`:** lists **exception types** (`Class<? extends Throwable>`) that cause Spring to request a rollback.
- **`noRollbackFor`:** lists **exception types** for which Spring **does not request a rollback**, even if it is an unchecked exception that would normally trigger rollback by default.

Example:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importFile() throws IOException {
    // If IOException exits the method, request rollback.
}

@Transactional(noRollbackFor = BusinessNoticeException.class)
public void processNotice() {
    // If BusinessNoticeException exits the method,
    // Spring does not mark rollback solely because of this exception.
}
~~~

This is merely an **annotation illustration snippet**; the method bodies and `BusinessNoticeException` are not defined, so it is not a standalone runnable program. A complete, compilable, and testable example appears in a later section.

**Core distinction:** “the method throws an exception” does not mean “the database definitely rolls back”. Spring reads the **rollback rules** before deciding. Conversely, configuring `noRollbackFor` **does not guarantee** the transaction will commit in every situation: the transaction may already be marked rollback-only, the database may reject the commit, or a separate infrastructure failure may occur.

### Business Context

Suppose you write an order status change to the database and then detect a condition:

- **Severe technical/business failure:** the change must not be saved → roll back.
- **Business notice that does not invalidate what was recorded:** sometimes you still want to commit, even though the method must signal a special situation to the caller.

This must be decided by **business invariants**, not by whether an exception's name sounds “heavy” or “light”. `noRollbackFor` is especially prone to leaving partial data behind if misused.

## 2. Default: Unchecked Rolls Back, Checked Usually Does Not

Before setting custom rules, distinguish two Java exception families:

~~~text
java.lang.Throwable
├── java.lang.Error
└── java.lang.Exception
    ├── java.lang.RuntimeException       (unchecked)
    │   ├── IllegalArgumentException
    │   └── IllegalStateException
    └── IOException / SQLException / ...  (checked)
~~~

- **Unchecked exceptions:** classes extending `RuntimeException`; e.g., `IllegalStateException`, `NullPointerException`. `Error` is also unchecked by Java's rules but does not extend `RuntimeException`.
- **Checked exceptions:** classes extending `Exception` without extending `RuntimeException`; e.g., `IOException`. The compiler requires declaring or catching this kind of exception.
- **Standard Spring default rule:** rolls back on `RuntimeException` and `Error`, and **does not automatically roll back solely because of a checked exception**.

For example, a method successfully writes to the DB and then throws `IOException`. If a new transaction was opened by Spring and no other rule applies, Spring may **commit the write** and then propagate `IOException` to the caller. This often causes surprise.

| Situation | `@Transactional` default | After adding a rule |
| --- | --- | --- |
| `IllegalStateException` escapes | Rollback | `noRollbackFor = IllegalStateException.class` requests not to roll back due to that error type. |
| `IOException` escapes | No rollback by default | `rollbackFor = IOException.class` requests rollback. |
| `Error` escapes | Rollback | Change only with an appropriately configured rule, used with extreme caution. |
| Method returns normally | Commit if Spring owns the transaction and there is no other rollback reason | Exception-based rules have nothing to match. |

These outcomes assume **the transaction is actually active**, the call passes through a Spring proxy, and there is no prior rollback-only state or database failure.

**Version note:** since Spring Framework 6.2, annotation-driven transaction management configuration can actively change the global default, e.g., `@EnableTransactionManagement(rollbackOn = ALL_EXCEPTIONS)`. The lab below **does not enable that option**, so the tests observe the familiar default where `RuntimeException`/`Error` roll back and checked exceptions do not. If your application has customized global default rules, do not apply the default table mechanically; specific rules must still be evaluated against the chosen global policy.

## 3. rollbackFor and noRollbackFor Match by *Type*, Including Subclasses

Two class-typed attributes:

~~~java
@Transactional(
    rollbackFor = {IOException.class, BusinessCheckedException.class},
    noRollbackFor = {NonCriticalBusinessException.class}
)
public void performOperation() {
    // ...
}
~~~

The principles are:

1. A rule `rollbackFor = IOException.class` applies to `IOException` **and its subclasses**. The same applies to `noRollbackFor`.
2. When multiple rules match the same exception, Spring uses the **strongest matching rule**. For class-based rules, you can think of this practically as **the more specific type in the inheritance chain** usually beating a broader parent type.
3. If no custom rule matches, Spring falls back to the default policy (unless the application changed the global policy).
4. Do not write two opposing rules for the **exact same class** and rely on declaration order to guess the result. Make the policy unambiguous.

Simple example of precedence:

~~~java
class BusinessRuntimeException extends RuntimeException { }

class CriticalBusinessException extends BusinessRuntimeException { }

@Transactional(
    noRollbackFor = BusinessRuntimeException.class,
    rollbackFor = CriticalBusinessException.class
)
public void operation() {
    // ...
}
~~~

- Throwing `BusinessRuntimeException`: matches `noRollbackFor` → does not roll back under that rule.
- Throwing `CriticalBusinessException`: matches both the superclass rule and the subclass rule. `rollbackFor` on the **more specific subclass** wins → rolls back.
- If an unrelated `IllegalArgumentException` is thrown: it matches neither custom rule; it is still a `RuntimeException`, so it rolls back by default.

This example **omits method bodies** and is not a standalone runnable class. In the lab section, these exact exception classes and behavior branches are fully declared and tested.

### Class Matching vs. String Name Matching

There are four annotation attributes:

| Type-safe form | String pattern form |
| --- | --- |
| `rollbackFor = IOException.class` | `rollbackForClassName = "java.io.IOException"` |
| `noRollbackFor = BusinessRuntimeException.class` | `noRollbackForClassName = "com.example.BusinessRuntimeException"` |

The **Class** form is checked by the compiler and matches by Java type relationship. The **ClassName** form is a **substring pattern within the fully qualified class name**, not a regular expression or glob; overly broad patterns like `"Exception"` can match unintended classes. For instance, `"CustomException"` risks also matching `CustomExceptionV2` when using patterns. When the class is known at compile time, prefer `rollbackFor`/`noRollbackFor` over strings.

## 4. Decision Diagram When an Exception Exits @Transactional

~~~text
Caller invokes public method THROUGH Spring proxy
                   |
          transaction starts/joins
                   |
          target method executes
                   |
       +-----------+-------------+
       |                         |
       v                         v
  Returns normally         Exception/Error escapes
       |                         |
       |                  Check custom rules
       |                         |
       |              +----------+----------+
       |              |                     |
       |         Rule matches          No rule matches
       |              |                     |
       |      Pick strongest rule     Default by type:
       |              |              RuntimeException/Error -> rollback
       |       rollback / no         checked -> no rollback
       |              |                     |
       +--------------+---------------------+
                      |
            Spring completes transaction
           (commit or rollback conditionally)
                      |
                Caller receives result/error
~~~

“No rollback” in the diagram means **do not request rollback solely due to that exception**; the interceptor may proceed to commit if it opened a new transaction and all other conditions are valid. It does **not** mean swallowing the exception: the caller still receives the exception after advice finishes.

**Important:** If the method only **joins** a `REQUIRED` transaction created by the caller, the service method does not hold final commit authority. Another method may have already set rollback-only, or the outer transaction may roll back later.

## 5. Complete Lab: Measuring DB State After Each Exception

We will build a project using **Java 17+**, **Spring Boot 3.5.0**, **Spring JDBC**, **in-memory H2**, and **JUnit 5** with Maven. No separate PostgreSQL instance is needed. The example uses a row `tx_counter(id=1, value=100)`; each method increments `value` by 10 **before throwing an exception**. After the call:

- **Rollback** → the value must return to **100**.
- **Commit despite exception** → the value is **110**.

The strength of this design: every test performs an actual database mutation to distinguish the two policies. The tests are also not annotated with `@Transactional`, because Spring Test's own transaction would mask whether the service truly committed or rolled back.

File structure:

~~~text
rollback-rules-lab/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/rollbackrules/
    │   │   ├── RollbackRulesApplication.java
    │   │   └── RollbackRuleService.java
    │   └── resources/
    │       ├── application.properties
    │       └── schema.sql
    └── test/
        └── java/com/example/rollbackrules/
            └── RollbackRuleServiceTest.java
~~~

### 5.1. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>rollback-rules-lab</artifactId>
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
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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
~~~

`spring-boot-starter-jdbc` brings `JdbcTemplate` and transaction infrastructure into the application; `h2` supplies the test database; `spring-boot-starter-test` provides JUnit 5 and `@SpringBootTest`. With a compatible JDBC `DataSource` and auto-configured `PlatformTransactionManager` from Boot, `@Transactional` is applied to the service bean.

### 5.2. application.properties and schema.sql

File `src/main/resources/application.properties`:

~~~properties
spring.datasource.url=jdbc:h2:mem:rollback_rules_lab;DB_CLOSE_DELAY=-1
spring.datasource.driver-class-name=org.h2.Driver
spring.datasource.username=sa
spring.datasource.password=
spring.sql.init.mode=always
~~~

File `src/main/resources/schema.sql`:

~~~sql
CREATE TABLE tx_counter (
    id BIGINT PRIMARY KEY,
    value BIGINT NOT NULL
);
~~~

H2 here is in-memory; `DB_CLOSE_DELAY=-1` keeps the in-memory database alive throughout the JVM lifetime even when connections close. `schema.sql` is executed by Spring Boot to create the table when the context starts. Each test resets the data to `100` before running, so tests have no ordering dependency.

### 5.3. RollbackRulesApplication.java

File `src/main/java/com/example/rollbackrules/RollbackRulesApplication.java`:

~~~java
package com.example.rollbackrules;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class RollbackRulesApplication {
    public static void main(String[] args) {
        SpringApplication.run(RollbackRulesApplication.class, args);
    }
}
~~~

This is the application class in the same package as the service/test; `@SpringBootTest` can locate the bootstrap configuration through this class. The lab does not need manual `@EnableTransactionManagement` since Spring Boot auto-configuration provides transaction management for JDBC. There is no `rollbackOn = ALL_EXCEPTIONS` configuration in the example.

### 5.4. RollbackRuleService.java

File `src/main/java/com/example/rollbackrules/RollbackRuleService.java`:

~~~java
package com.example.rollbackrules;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class RollbackRuleService {
    private final JdbcTemplate jdbc;

    public RollbackRuleService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    // Checked exception: not a RuntimeException.
    public static class CheckedBusinessException extends Exception {
        public CheckedBusinessException(String message) {
            super(message);
        }
    }

    public static final class IgnorableCheckedException
            extends CheckedBusinessException {
        public IgnorableCheckedException(String message) {
            super(message);
        }
    }

    // Unchecked exception: extends RuntimeException.
    public static class BusinessRuntimeException extends RuntimeException {
        public BusinessRuntimeException(String message) {
            super(message);
        }
    }

    public static final class CriticalRuntimeException
            extends BusinessRuntimeException {
        public CriticalRuntimeException(String message) {
            super(message);
        }
    }

    // 1. Default: RuntimeException -> rollback.
    @Transactional
    public void defaultRuntime() {
        increase();
        throw new BusinessRuntimeException("default runtime");
    }

    // 2. Default: checked exception -> no rollback.
    @Transactional
    public void defaultChecked() throws CheckedBusinessException {
        increase();
        throw new CheckedBusinessException("default checked");
    }

    // 3. rollbackFor forces rollback for checked exception.
    @Transactional(rollbackFor = CheckedBusinessException.class)
    public void rollbackOnChecked() throws CheckedBusinessException {
        increase();
        throw new CheckedBusinessException("checked with rollbackFor");
    }

    // 4. noRollbackFor suppresses rollback request for this RuntimeException.
    @Transactional(noRollbackFor = BusinessRuntimeException.class)
    public void noRollbackOnRuntime() {
        increase();
        throw new BusinessRuntimeException("runtime with noRollbackFor");
    }

    // 5. Subclass rule IgnorableCheckedException is more specific than Exception.
    @Transactional(
        rollbackFor = Exception.class,
        noRollbackFor = IgnorableCheckedException.class
    )
    public void checkedRules(boolean ignorable)
            throws CheckedBusinessException {
        increase();
        if (ignorable) {
            throw new IgnorableCheckedException("ignorable checked");
        }
        throw new CheckedBusinessException("other checked");
    }

    // 6. Subclass rule CriticalRuntimeException is more specific than superclass.
    @Transactional(
        noRollbackFor = BusinessRuntimeException.class,
        rollbackFor = CriticalRuntimeException.class
    )
    public void runtimeRules(boolean critical) {
        increase();
        if (critical) {
            throw new CriticalRuntimeException("critical");
        }
        throw new BusinessRuntimeException("noncritical");
    }

    private void increase() {
        int updated = jdbc.update(
            "UPDATE tx_counter SET value = value + 10 WHERE id = ?",
            1L
        );
        if (updated != 1) {
            throw new IllegalStateException("Missing test counter");
        }
    }
}
~~~

**Do not arbitrarily add `@Transactional` to `increase()`.** It is a private helper called **inside** public methods that already have a transaction. The transaction actually begins at the proxy call to `defaultRuntime()`, `checkedRules(...)`, etc. Private methods are not independently proxied, yet their JDBC calls still use the transaction opened by the public method.

Explanation of each group:

- **`defaultRuntime()`**: the increment by 10 runs, throws `BusinessRuntimeException`; Spring rolls back by default, so the DB stays at 100.
- **`defaultChecked()`**: the increment by 10 runs, throws checked `CheckedBusinessException`; Spring does not mark rollback for that exception type by default, so the DB becomes 110 and the exception still propagates to the caller.
- **`rollbackOnChecked()`**: same checked exception, but `rollbackFor` requested rollback → DB returns to 100.
- **`noRollbackOnRuntime()`**: same unchecked type that normally rolls back by default, but `noRollbackFor` changes the decision → DB becomes 110.
- **`checkedRules(true)`**: `IgnorableCheckedException` matches both `Exception.class` on rollback and `IgnorableCheckedException.class` on no-rollback. The more specific subclass wins → DB 110.
- **`checkedRules(false)`**: `CheckedBusinessException` matches `Exception.class` but does not match `IgnorableCheckedException.class` → rolls back → DB 100.
- **`runtimeRules(true)`**: `CriticalRuntimeException` matches both the parent's no-rollback and the subclass's rollback → subclass rule wins → DB 100.
- **`runtimeRules(false)`**: throws only `BusinessRuntimeException`, no-rollback rule applies → DB 110.

Note that exceptions are thrown **after a successful UPDATE statement**, so this is not an artificial difference caused by code never modifying data.

### 5.5. Integration Tests: Proving Outcomes via Post-Transaction Values

File `src/test/java/com/example/rollbackrules/RollbackRuleServiceTest.java`:

~~~java
package com.example.rollbackrules;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import static com.example.rollbackrules.RollbackRuleService.BusinessRuntimeException;
import static com.example.rollbackrules.RollbackRuleService.CheckedBusinessException;
import static com.example.rollbackrules.RollbackRuleService.CriticalRuntimeException;
import static com.example.rollbackrules.RollbackRuleService.IgnorableCheckedException;

@SpringBootTest
class RollbackRuleServiceTest {
    @Autowired
    private RollbackRuleService service;

    @Autowired
    private JdbcTemplate jdbc;

    // DO NOT annotate the test with @Transactional.
    // Seed data must commit before calling the service.
    @BeforeEach
    void resetCounter() {
        jdbc.update("DELETE FROM tx_counter");
        jdbc.update(
            "INSERT INTO tx_counter (id, value) VALUES (?, ?)",
            1L, 100L
        );
    }

    private long readValue() {
        Long value = jdbc.queryForObject(
            "SELECT value FROM tx_counter WHERE id = ?",
            Long.class, 1L
        );
        if (value == null) {
            throw new AssertionError("Missing counter");
        }
        return value;
    }

    @Test
    void runtimeExceptionRollsBackByDefault() {
        assertThrows(
            BusinessRuntimeException.class,
            () -> service.defaultRuntime()
        );
        assertEquals(100L, readValue());
    }

    @Test
    void checkedExceptionCommitsByDefault() {
        assertThrows(
            CheckedBusinessException.class,
            () -> service.defaultChecked()
        );
        assertEquals(110L, readValue());
    }

    @Test
    void rollbackForMakesCheckedExceptionRollBack() {
        assertThrows(
            CheckedBusinessException.class,
            () -> service.rollbackOnChecked()
        );
        assertEquals(100L, readValue());
    }

    @Test
    void noRollbackForAllowsRuntimeExceptionToCommit() {
        assertThrows(
            BusinessRuntimeException.class,
            () -> service.noRollbackOnRuntime()
        );
        assertEquals(110L, readValue());
    }

    @Test
    void moreSpecificNoRollbackForWinsForCheckedChild() {
        assertThrows(
            IgnorableCheckedException.class,
            () -> service.checkedRules(true)
        );
        assertEquals(110L, readValue());
    }

    @Test
    void broadRollbackForStillAppliesToOtherCheckedException() {
        assertThrows(
            CheckedBusinessException.class,
            () -> service.checkedRules(false)
        );
        assertEquals(100L, readValue());
    }

    @Test
    void moreSpecificRollbackForWinsForCriticalRuntimeChild() {
        assertThrows(
            CriticalRuntimeException.class,
            () -> service.runtimeRules(true)
        );
        assertEquals(100L, readValue());
    }

    @Test
    void noRollbackForParentAppliesToNoncriticalRuntime() {
        assertThrows(
            BusinessRuntimeException.class,
            () -> service.runtimeRules(false)
        );
        assertEquals(110L, readValue());
    }
}
~~~

Why **not** put `@Transactional` on the test class or test methods? Spring Test has a mechanism that opens an enclosing transaction and automatically rolls it back after the test. If a test runs inside that transaction, a `REQUIRED` service may simply join the test's transaction; asserting data mid-test or letting the framework roll back at test end can hide the service's real commit point. Here `@BeforeEach` resets via JDBC outside a test transaction, then calls the service proxy, and then **reads back after the proxy has handled commit/rollback**.

`assertThrows` only confirms the **exception type**. `assertEquals(100L/110L, readValue())` is what proves Spring handled the transaction according to policy. If you only test the exception type and omit the DB query, you do not know whether partial data was committed.

Calls must go through Spring's `@Autowired RollbackRuleService` bean; instantiating `new RollbackRuleService(jdbc)` manually will not activate the transaction interceptor in proxy mode.

## 6. Running the Lab and Comparing the Result Matrix

In the `rollback-rules-lab` directory, verify Java/Maven:

~~~bash
java -version
mvn -version
mvn test
~~~

Requires JDK 17+ and Maven installed with dependency download access. If the project includes the Maven Wrapper, replace the last command with `./mvnw test` on Linux/macOS or `.\mvnw.cmd test` on Windows PowerShell.

With the source and configuration above, **8 tests** must pass. Maven Surefire reports 8 tests run, 0 failures/errors (execution order, timing, and environment logs may vary). The verified values are:

| Test / call | Escaping exception | Effective rule | Read-back value |
| --- | --- | --- | ---: |
| `defaultRuntime()` | `BusinessRuntimeException` | Default rolls back unchecked | **100** |
| `defaultChecked()` | `CheckedBusinessException` | Default does not roll back checked | **110** |
| `rollbackOnChecked()` | `CheckedBusinessException` | `rollbackFor` checked | **100** |
| `noRollbackOnRuntime()` | `BusinessRuntimeException` | `noRollbackFor` unchecked | **110** |
| `checkedRules(true)` | `IgnorableCheckedException` | Subclass no-rollback beats superclass rollback | **110** |
| `checkedRules(false)` | `CheckedBusinessException` | Rollback by `Exception.class` | **100** |
| `runtimeRules(true)` | `CriticalRuntimeException` | Subclass rollback beats superclass no-rollback | **100** |
| `runtimeRules(false)` | `BusinessRuntimeException` | Superclass no-rollback applies | **110** |

Each test starts from `value=100`. The only difference is the **exception type** or **rule** declared. No other database writes exist besides adding 10 in the service and the test reset.

### Observing a Checked Error Triggering Commit

~~~text
Test sets value=100 (committed).
  |
  v
proxy.defaultChecked()
  |
  +-- Spring opens JDBC transaction
  +-- UPDATE value = value + 10   (in transaction: 110)
  +-- throw CheckedBusinessException
  |
  v
Transaction interceptor finds no matching rollback rule.
Checked exception does not request rollback by default.
  |
  v
Spring commits transaction, then exception reaches assertThrows.
  |
  v
Test SELECT -> value=110.
~~~

### Same Checked Exception, but rollbackFor Changes the Outcome

~~~text
Test sets value=100 (committed).
  |
  v
proxy.rollbackOnChecked()
  |
  +-- UPDATE value = value + 10   (in transaction: 110)
  +-- throw CheckedBusinessException
  |
  v
rollbackFor=CheckedBusinessException.class matches
  |
  v
Spring requests rollback.
  |
  v
Test SELECT -> value=100.
~~~

Key point: **the exception occurs in both cases**. The difference lies in the **transaction completion outcome**, not whether the method threw an error.

## 7. Selecting Rules with Inheritance: A Systematic Way to Predict

Suppose you define:

~~~text
Exception
└── CheckedBusinessException
    └── IgnorableCheckedException

RuntimeException
└── BusinessRuntimeException
    └── CriticalRuntimeException
~~~

**Case A:**

~~~java
@Transactional(
    rollbackFor = Exception.class,
    noRollbackFor = IgnorableCheckedException.class
)
~~~

When the method throws `IgnorableCheckedException`, both `Exception.class` and `IgnorableCheckedException.class` match. The no-rollback rule of the more specific exception type is chosen. When the method throws `CheckedBusinessException`, the subclass no-rollback rule does **not** match: a superclass does not inherit policies specific to a subclass backward. The `Exception.class` rollback rule takes effect.

**Case B:**

~~~java
@Transactional(
    noRollbackFor = BusinessRuntimeException.class,
    rollbackFor = CriticalRuntimeException.class
)
~~~

When `CriticalRuntimeException` is thrown, the subclass rollback wins. When `BusinessRuntimeException` itself is thrown, no-rollback wins. Do not interpret this as “noRollbackFor always wins” or “rollbackFor always wins”; **the specificity of the matching rule** decides in this example.

**Case C: no related rule applies.** Throwing `NullPointerException` with the configuration in Case B: it does not extend `BusinessRuntimeException`, so it matches neither declared rule; Spring continues using the default rollback for unchecked exceptions.

**Case D: two conflicting rules at the same level.** Do not put the same class in both `rollbackFor` and `noRollbackFor`. Documentation recommends choosing unambiguous rules; relying on declaration order or internal details when specificity is tied makes the policy hard to understand and prone to unintended changes.

### Distinguishing “Thrown Exception Type” from “Wrapped Cause Inside”

If a method catches `IOException` and throws `new IllegalStateException("failed", ioException)`, the exception **exiting outward** is `IllegalStateException`. A `rollbackFor = IOException.class` rule **does not automatically match** the cause inside `getCause()`; Spring inspects the exception received by the interceptor to apply rollback rules.

Conversely, if the method directly throws the declared `IOException` and it escapes through the proxy, `rollbackFor = IOException.class` can apply properly. When choosing rules, identify the exception class **actually crossing the service boundary**, not just lower-layer classes or error codes inside the message.

## 8. When to Use rollbackFor vs. When to Use noRollbackFor?

### Appropriate Cases for rollbackFor

Use when a **checked exception** indicates that updates performed within the transaction **must not be committed**.

For example, a file-processing service writes part of the data first and then encounters an `IOException` or checked business exception signaling the process is incomplete. If the entire batch must be atomic:

~~~java
@Transactional(rollbackFor = IOException.class)
public void importOrders() throws IOException {
    // JDBC updates and input processing belong to the same business operation.
}
~~~

This is a condensed example illustrating the annotation. If the system runs with a default rollback policy for all exceptions, verify the active rules; you can still declare it explicitly when you want the contract visible on the method.

### Cases to Consider noRollbackFor

Use only when the exception **does not invalidate the recorded changes**.

For example, after the database saves a valid state, the method needs to signal a business exception so the caller decides to branch to a follow-up flow. If the changes must still be preserved, `noRollbackFor = SomeBusinessException.class` can be configured.

However, if an operation has two steps—“debit” and “credit”—and throws an exception after the debit step, configuring no-rollback for that exception would **commit a half-finished transaction**. Never use `noRollbackFor` merely to “avoid losing written data” when atomicity must actually be enforced.

**Design suggestion:** if “not found/out of stock” is a normal business outcome, returning a **result type** is often better than overusing an exception with no-rollback. That expresses success/failure semantics and database consequences more clearly.

## 9. Common Limitations and Pitfalls

### 9.1. Catching/Swallowing an Exception Before It Exits the Method

~~~java
@Transactional(rollbackFor = IOException.class)
public void operation() {
    try {
        writeToDatabase();
        readExternalFile();
    } catch (IOException ex) {
        // Swallow exception: method returns normally.
    }
}
~~~

The snippet above is **non-standalone illustrative code**; `writeToDatabase()` and `readExternalFile()` are undeclared and shown to demonstrate the bug. When `IOException` is caught and swallowed, the transaction interceptor **does not see** that exception when the method ends. `rollbackFor` does not activate merely because an exception occurred midway through the code. Rethrow the exception per contract or, where genuinely required, mark rollback-only via Spring's API. Prefer explicit error propagation over manual markers.

### 9.2. Self-Invocation or Instantiating Beans with new

~~~java
public void outer() {
    this.inner(); // Does not go through Spring proxy in default proxy mode.
}

@Transactional(rollbackFor = IOException.class)
public void inner() {
    // ...
}
~~~

This is an **illustrative snippet** and cannot compile standalone. When the target calls `this.inner()`, Spring AOP's interceptor is usually not applied to that internal call. Similarly, `new RollbackRuleService(jdbc)` created manually outside the Spring container has no transaction proxy.

An annotation cannot help if **no transaction is activated**. In the lab, all public methods are called through the `@Autowired` service to avoid this pitfall.

### 9.3. noRollbackFor Does Not Clear Existing Rollback-Only State

Suppose operation A runs inside a larger transaction. An inner operation B already marked the transaction `rollback-only`, or the database put the transaction into an uncommittable state due to a SQL error. Then operation A throws an exception configured with `noRollbackFor`.

The rule “do not roll back for this exception type” **does not clear** the rollback-only flag and **does not** force the database to commit an invalidated transaction. When the outer transaction tries to commit, Spring may detect/throw `UnexpectedRollbackException` or the database may return an error depending on circumstances.

This is especially critical for `DataAccessException` errors emitted by JDBC/the database: the SQL statement and engine themselves can render the transaction uncommittable. Do not use `noRollbackFor` as an “ignore database errors” switch.

### 9.4. Exceptions Occurring After Commit

If a transactional method finishes and the transaction manager **has already committed**, and then the controller or HTTP response serialization throws an exception, rollback rules on the earlier method **cannot undo the completed commit**. Transaction boundaries must enclose data changes that need atomicity, but should not span network calls just to avoid this issue.

If the client loses the response right after commit, the client cannot be sure whether the result was persisted; `rollbackFor`/`noRollbackFor` do not solve idempotency or duplicate retries. Request IDs, business state, and an appropriate retry strategy are needed.

### 9.5. Exceptions Translated or Wrapped in Another Layer

A JDBC exception may be translated by Spring into `DataAccessException` (unchecked) instead of the driver's checked type. A service may wrap a checked exception into an unchecked business exception. Therefore, rules should be written for the **error type actually exiting the transactional method**, not solely based on repository declarations.

If you want to roll back any violated business invariant while “not rolling back” for an exception that permits retaining data, build an appropriate exception hierarchy, choose rules by **type**, and test subtypes individually.

### 9.6. Propagation and Multiple Transaction Managers

`@Transactional` defaults to `Propagation.REQUIRED`: if an outer transaction exists, the method joins it; the commit point is decided by the transaction owner. If a method uses `REQUIRES_NEW`, it gets an independent transaction from the outer scope when supported by the manager. Thus, the effect of a rule on a method depends on which transaction is being processed.

With multiple `DataSource`s, the service must use the appropriate `PlatformTransactionManager`. `rollbackFor` cannot roll back a data source that the active manager does not manage. Database transactions also do not automatically undo emails, message brokers, HTTP calls, or changes in third-party systems.

### 9.7. @Transactional Tests Masking Outcomes

Spring Test can roll back a test's transaction **after the test completes**, even when the service did not manage the transaction as expected. If you want to prove whether the service commits or rolls back, avoid wrapping the test in `@Transactional` or use a test strategy with explicit boundary control. In the lab, `@BeforeEach` resets data outside any test transaction and assertions read the DB after each method.

### 9.8. Misinterpreting noRollbackFor as Catching or Ignoring Exceptions

`noRollbackFor` **does not catch** and **does not suppress** exceptions. The Java method still throws the error, and the caller must still handle it per Java rules. It only affects the **transaction advice's rollback decision**. If code needs to report success with a warning, returning a result type is usually better than throwing an exception while still committing.

### 9.9. Changing Global Defaults and Forgetting to Re-Check

In Spring Framework 6.2+, applications can configure default rollback for all exceptions when using annotation-driven transaction management. If an application enables `rollbackOn = ALL_EXCEPTIONS`, the lab's `defaultChecked()` example will no longer produce 110 without an overriding rule. When QA-ing a real environment, always verify the global transaction configuration and Spring version.

## 10. Comparing Annotation Configuration with XML

This lesson focuses on `rollbackFor`/`noRollbackFor` **by exception type** in Java annotations. You may encounter equivalent configuration in projects using Spring XML:

~~~xml
<tx:advice id="txAdvice" transaction-manager="txManager">
    <tx:attributes>
        <tx:method name="process*"
                   rollback-for="com.example.BusinessCheckedException"
                   no-rollback-for="com.example.NonCriticalException"/>
    </tx:attributes>
</tx:advice>
~~~

This is an **illustrative XML fragment** requiring the `tx` XML namespace, a transaction manager, and a corresponding advisor/pointcut to form a working configuration. In XML, `rollback-for`/`no-rollback-for` are typically **exception name strings/patterns**; do not assume they have the same compile-time type safety as `@Transactional(rollbackFor = Foo.class)`. Especially avoid overly broad pattern names.

For new Java code, whenever the class can be imported, prefer declaring `rollbackFor = FooException.class` and `noRollbackFor = BarException.class` so the compiler assists with checking and prevents accidental name matches.

## 11. Process for Designing Business-Aligned Rules

Before adding an exception to `rollbackFor` or `noRollbackFor`, determine:

1. **What is the post-failure invariant?** If the method already executed one or more writes, is it permissible to keep them?
2. **Which exception actually exits through the Spring proxy?** Is it checked or unchecked, what is its exact type, and is it wrapped?
3. **Was the transaction opened in the right place?** Does the caller go through the proxy, use the right manager, and share the same database resource?
4. **Do other rules or a global policy match?** Consider inheritance, specificity, and override behavior.
5. **Is there an outer transaction or an existing rollback-only flag?** Do not promise commit simply because the method configures `noRollbackFor`.
6. **Does the test read the database back after the method completes?** Tweaking code without measuring persisted state is insufficient.

Systems typically have these error categories:

| Error category | Recommended policy to consider |
| --- | --- |
| Technical exception indicating incomplete operation after partial updates | Roll back the entire operation. |
| Checked business exception indicating invalid business state after partial changes | Use `rollbackFor` or an appropriate global policy. |
| RuntimeException from programming bugs or violated invariants | Keep default rollback; do not arbitrarily disable rollback. |
| Exception purely signaling a validly persisted state needing caller handling | May consider `noRollbackFor`, though evaluate returning a result type. |
| Constraint violation/SQL failure that broke the DB transaction | Do not use `noRollbackFor` to force commit; handle errors, roll back/retry safely. |

Not every checked exception is “minor” and not every unchecked exception is “severe”. That distinction is merely a Java compiler check; Spring provides custom rules to align behavior with business semantics.

## 12. Extended Exercises

**Exercise A — Predict before running:** keep `@Transactional(rollbackFor = CheckedBusinessException.class)` and throw `IgnorableCheckedException` (the subclass). Expected result: **rollback**, because the subclass belongs to the declared checked exception family. Write a test confirming the value 100.

**Exercise B — Configure a specific exception:** add `noRollbackFor = IgnorableCheckedException.class` to the same method from Exercise A. Result for the specific exception: **commit**, because the subclass no-rollback rule is more specific than the superclass rollback rule. For the base `CheckedBusinessException`, it still rolls back.

**Exercise C — Compare wrapping vs. rethrowing:** one method directly throws `CheckedBusinessException`; another catches it and throws `IllegalStateException`. With no custom rules, predict that the checked one commits and the unchecked one rolls back. Write an integration test that reads back the database to verify.

**Exercise D — Try swallowing an exception:** in a copy of the lab, catch and do not rethrow the exception at the end of a service method. Observe that the method returns normally; can the transaction interceptor know an error occurred that needed rollback? Practice only on test H2.

**Exercise E — Read rules as a decision table:** sketch the hierarchy `Exception -> ParentChecked -> ChildChecked`; configure rollback on the parent and no-rollback on the child; determine the outcome for each type before running tests.

**Exercise F — Test combining with an outer transaction:** if another method opens an outer transaction, catches the inner method's exception, and still tries to commit, what can happen when the transaction was already marked rollback-only? Investigate `UnexpectedRollbackException` and the conditions under which the transaction manager throws it; do not assume catching the exception suffices to recover the transaction.

## 13. Self-Assessment Questions

1. **Does `rollbackFor = IOException.class` apply to subclasses of IOException?** — Yes, type-based rules apply to the declared type and its subtypes.
2. **Does `noRollbackFor = IllegalArgumentException.class` catch and suppress the exception?** — No. The exception is still propagated; it only alters the rollback choice caused by that exception.
3. **What does a checked exception without custom rules do by default?** — Under standard configuration, Spring does not request rollback solely for a checked exception, so a new transaction can commit.
4. **If `rollbackFor = Exception.class` and `noRollbackFor = IgnorableCheckedException.class`, what happens when throwing `IgnorableCheckedException`?** — The no-rollback rule of the more specific type wins, assuming the transaction can still commit.
5. **If `noRollbackFor = BusinessRuntimeException.class` and `rollbackFor = CriticalRuntimeException.class`, what happens when throwing `CriticalRuntimeException`?** — The rollback rule of the more specific subclass wins.
6. **Why must methods be called through a Spring-managed bean?** — A Spring proxy needs to intercept calls to apply `@Transactional` and its rollback rules.
7. **Why is checking only `assertThrows` insufficient?** — It does not prove commit or rollback; data must be read back after the call.
8. **If SQL already marked the transaction rollback-only, can `noRollbackFor` rescue the commit?** — No. The rule does not clear rollback-only.
9. **Is `rollbackForClassName` identical to `rollbackFor`?** — No: one relies on exception name patterns; the other relies on Java types.
10. **Can an HTTP error occurring after database commit be rolled back by the service's `rollbackFor`?** — No. The transaction has already ended; idempotency/compensation must be designed if business requirements demand it.

## 14. Summary

- `rollbackFor` tells Spring **which exception types exiting the method should trigger rollback**.
- `noRollbackFor` tells Spring **not to request rollback due to which exception types**, even if they are `RuntimeException`s.
- The standard default is rollback for `RuntimeException`/`Error` and no rollback for checked exceptions, unless the global default policy has been changed.
- When multiple custom rules match, **the most specific rule** wins; prefer class-based rules over string patterns to avoid unintended matches.
- **The error must reach the transaction interceptor**, the transaction must be properly managed, and the database must still be committable. Catching/swallowing exceptions or marking rollback-only elsewhere can alter the outcome.
- **The database state after testing** is the proof of rollback/commit; do not infer it from exception names or the presence of annotations in source code.

> **Practical rule:** before placing an exception into `noRollbackFor`, verify that **every change made prior to the exception is allowed to be kept**. If the answer is no, the transaction must roll back.

### Official Documentation

- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework — Using @Transactional / Settings](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 — @Transactional Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/transaction/annotation/Transactional.html)
- [Spring Framework — Transaction Propagation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html)
- [Spring Framework — Spring Test Transaction Management](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html)