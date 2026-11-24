# Catching, Swallowing, or Changing Exception Types Alters Rollback Outcomes in Spring

## 1. Core Rule: Which Error Does Transaction Advice See?

In Spring Framework, a `@Transactional` method does not automatically roll back merely because “an error occurred somewhere inside.” With Spring AOP declarative transactions, **`TransactionInterceptor` evaluates the outcome crossing the boundary of the advised method**. If the method returns normally, advice usually follows the commit path (unless the transaction is already rollback-only, a resource failed, or special completion rules apply). If an exception escapes, advice applies the **rollback rules** to the exception observed at that boundary.

Consequently, three seemingly routine error-handling actions can lead to completely different outcomes:

1. **Catching and swallowing an error** inside the transactional method: the caller sees success, advice never sees that exception, and it may commit data written before the error.
2. **Catching an error outside the proxy**: the error already passed through transaction advice, so the rollback/commit decision has generally already been applied; catching in the caller to build an HTTP response or log does not reverse the completed decision.
3. **Changing the exception type** (wrapping/translating) **before the error crosses the boundary**: advice sees the new exception. Converting a checked `IOException` into an unchecked `IllegalStateException` can turn “commit by default” into “rollback”; converting in the opposite direction can produce the opposite effect.

This lesson focuses on **catch placement, the exception type at the interception point, and rollback-only state**. An annotated method invoked via self-invocation bypassing the proxy will not get its own interception; for the scenarios below to hold, assume calls arrive from another bean through a Spring proxy unless stated otherwise.

### General Decision Diagram

~~~mermaid
flowchart TD
    A["Caller -> Spring proxy"] --> B["TransactionInterceptor opens/joins scope"]
    B --> C["Executes @Transactional method"]
    C --> D{"Does an exception exit the method?"}
    D -->|"No; catch and return"| E{"Rollback-only or resource error?"}
    D -->|"Yes"| F["Determine final exception type at boundary"]
    F --> G{"Does a rollback rule match?"}
    G -->|"Yes, roll back"| H["Roll back or mark rollback-only"]
    G -->|"No / noRollbackFor"| I["Request commit and propagate exception"]
    E -->|"No"| J["Request commit"]
    E -->|"Yes"| H
    J --> K["Complete; caller receives return value"]
    I --> L["Caller receives exception after boundary handling"]
    H --> M["Complete rollback or wait for outer scope"]
~~~

“Commit” in the diagram means **requests commit**, not a guarantee of success in every situation: database constraints, connection failures, rollback-only from an inner scope, or non-transactional resources can produce a different result. With `PROPAGATION_REQUIRED` joining an existing transaction, completing the logical scope also depends on the outer physical transaction.

## 2. Default Rules Table and Limitations

For Spring Framework's `@Transactional` under **standard defaults**:

| Exception exiting the transactional method | Default decision |
| --- | --- |
| `RuntimeException` and subclasses (`IllegalStateException`, `DataAccessException`, ...) | Rollback |
| `Error` and subclasses | Rollback |
| Checked `Exception` (`IOException`, custom checked business exceptions, ...) | Does not roll back automatically; Spring may commit and propagate the exception to caller |
| No exception exits; method returns normally | Usually commits, unless already rollback-only or an error occurs on completion |

**This does not mean checked exceptions “always commit” or `RuntimeException`s “always roll back.”** `rollbackFor`, `noRollbackFor`, global rules, an already rollback-only transaction, and resource state can alter behavior.

The runnable examples in this lesson use **Spring Boot 3.3.5 / Spring Framework 6.1.x** and the default rollback policy so results stay clear. Since **Spring Framework 6.2**, applications can configure `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)`; when enabled, checked exceptions also become a default rollback trigger. Specific method rules still take precedence when matched. Do not guess policy merely from seeing the annotation; you must know the framework version and actual configuration.

**Key perspective:** Spring's default evaluates the exception that the transaction infrastructure **observes when the scope completes**, rather than inspecting a history of exceptions that occurred and were handled inside Java code.

## 3. Catching Inside vs. Outside the Boundary: Same Exception, Different Outcomes

### 3.1. Catching and Swallowing a RuntimeException Inside the Method

~~~java
@Transactional
public void updateThenSwallow() {
    jdbc.update("UPDATE account SET amount = amount + 10 WHERE id = 1");
    try {
        throw new IllegalStateException("business validation failed");
    } catch (IllegalStateException ex) {
        log.warn("Ignored in this example", ex);
    }
    // Method returns normally.
}
~~~

This is an illustrative snippet (assuming `jdbc`/`log` are injected). The error is caught **before leaving the method**, so advice on this method **never sees** `IllegalStateException`. If the transaction is new, the resource is healthy, and nothing else set rollback-only, Spring commits the +10 change. Emitting an ERROR/WARN log line does not trigger automatic rollback.

Do not generalize this outcome to conclude that every database exception can be swallowed safely. A failing SQL statement can put the DB connection/transaction **into an aborted or rollback-only state**, especially when the DB detects a data error; in that case commit can fail even if Java caught the exception. The example above deliberately throws **after a valid UPDATE**, avoiding reliance on vendor-specific error handling.

### 3.2. Letting the Exception Exit the Method, Catching in the Caller Outside the Proxy

~~~java
// In another Spring bean or entrypoint, with service as a proxied bean:
try {
    service.updateThenThrow();
} catch (IllegalStateException ex) {
    log.warn("Returned user-friendly error", ex);
}
~~~

Assume `service.updateThenThrow()` is `@Transactional`, updates data, and throws an unchecked exception outward. **The Spring proxy sees the exception before the caller**, processes rollback per policy, and then forwards the exception. The caller catching it to build a response or continue does not “flip” a rolled-back transaction back into a commit.

Similarly, if the method throws a **checked exception** and advice chose commit by default, catching it outside in the caller and wrapping it into a `RuntimeException` is **too late** to undo the commit that already occurred. What matters is **the exception type and which boundary the conversion happens before**.

### 3.3. Catching to Clean Up and Then Rethrowing

~~~java
@Transactional
public void updateThenRethrow() {
    try {
        updateRows();
    } catch (IllegalStateException ex) {
        recordLocalDiagnostic(ex);
        throw ex; // Exception still passes through transaction advice.
    }
}
~~~

This is an illustrative snippet with undefined helpers, not a standalone program. Under default rollback, rethrowing the same unchecked exception lets Spring roll back as expected. Ensure `recordLocalDiagnostic` does not accidentally produce non-transactional side effects that business logic assumes rollback will undo (such as sending HTTP requests or emails).

**Practical rule:** if you want the transaction to roll back on an exception, **let an appropriate exception cross the boundary** or intentionally mark rollback-only. Catching merely to format user-facing errors should generally happen **outside** the service transaction.

## 4. Changing the Exception Type Before the Boundary Changes the Applied Rule

### 4.1. Checked to Unchecked

~~~java
@Transactional
public void importFile() {
    jdbc.update("UPDATE account SET amount = amount + 10 WHERE id = 1");
    try {
        callCheckedOperation(); // may throw IOException
    } catch (IOException ex) {
        throw new IllegalStateException("Import failed", ex);
    }
}
~~~

Assume `callCheckedOperation()` is a helper declaring `throws IOException`. If `IOException` directly exited `@Transactional` under 6.1 defaults, the transaction would normally **not roll back** because it is a checked exception. Yet when code converts it into `IllegalStateException` **before exiting the method**, the transaction interceptor sees an **unchecked exception** and requests rollback.

Use the constructor with `cause` to preserve source diagnostics: `new IllegalStateException("...", ex)`. Wrapping **does not inherently make an exception rollbackable under every configuration**; it is the **rule applied to the observed type** that decides. If the method has `noRollbackFor = IllegalStateException.class`, the outcome differs.

### 4.2. Unchecked to Checked

~~~java
@Transactional
public void importWithCheckedApi() throws IOException {
    jdbc.update("UPDATE account SET amount = amount + 10 WHERE id = 1");
    try {
        operationThatThrowsIllegalState();
    } catch (IllegalStateException ex) {
        throw new IOException("Converted to checked error", ex);
    }
}
~~~

This is also an illustrative snippet lacking helper/field definitions; the focus is the exception conversion path. Under 6.1 rollback defaults, Spring sees `IOException` rather than `IllegalStateException`, so it **may commit** and then throw `IOException` to the caller. If business logic demands atomicity, converting exception types to unify an API while neglecting rollback rules is a design bug.

The fix is adding `@Transactional(rollbackFor = IOException.class)` at the appropriate boundary, or using a semantically meaningful unchecked exception if the contract allows. Do not rely on “there used to be a RuntimeException earlier”—that exception was already caught.

### 4.3. Converting Exceptions **After** a Transactional Method Does Not Alter the Past Decision

~~~java
// In controller/facade, assuming service is advised with @Transactional:
try {
    service.importChecked(); // Exits with IOException; Spring already processed the boundary.
} catch (IOException ex) {
    throw new IllegalStateException("API error", ex);
}
~~~

If `importChecked()` commits by default before throwing a checked exception, having the controller wrap it into an unchecked exception **after the service proxy has already finished** does **not retroactively roll back** the service's transaction. If the controller/facade also has an outermost transaction, that is a **separate boundary** requiring propagation analysis.

### 4.4. Exception Translation in `@Repository`

Spring can translate provider data-access errors (`SQLException`, JPA persistence exceptions, ...) into the **unchecked** `DataAccessException` hierarchy via abstractions like `JdbcTemplate` and repository exception translation when properly configured. That can cause the exception reaching the **service's transactional advice** to be `DataAccessException` instead of the original checked exception.

No single rule covers every library: translation timing, advice ordering, driver, exception type, and DAO/service catch blocks all matter. When analyzing, trace the **final exception leaving each bean proxy** and **which boundaries carry `@Transactional`**. Never catch `Exception` broadly in a repository and return `null` or a default value without signaling failure; doing so can turn a transaction that ought to roll back into a false success.

## 5. Matrix by Catch Location, Error Type, and Outcome

Assuming **no outer transaction, no prior rollback-only flag, committable resources, and Spring Framework 6.1 default rollback policy**:

| Scenario | Exception seen by method's advice | Reasonably expected outcome |
| --- | --- | --- |
| Method UPDATEs, catches `IllegalStateException` itself and returns | No exception | Commit |
| Method UPDATEs then throws `IllegalStateException`, caller catches outside proxy | `IllegalStateException` | Rollback |
| Method UPDATEs then throws `IOException`, caller catches outside proxy | `IOException` | Commit |
| Method catches `IOException`, wraps as `IllegalStateException` before returning | `IllegalStateException` | Rollback |
| Method catches `IllegalStateException`, wraps as `IOException` before returning | `IOException` | Commit |
| Method `@Transactional(rollbackFor=IOException.class)` throws `IOException` | `IOException` | Rollback |
| Method `@Transactional(noRollbackFor=IllegalStateException.class)` throws `IllegalStateException` | `IllegalStateException` | Commit |
| Method catches, calls `setRollbackOnly()`, returns | No exception, yet rollback-only | Rollback |
| Inner `REQUIRED` via proxy throws unchecked, outer catches and returns | Outer sees no exception; inner marked global rollback-only | Shared transaction rolls back; outer may receive `UnexpectedRollbackException` |

This matrix is a **conditional model**, not a promise that all database configurations behave identically. Participation in an outer transaction, a DB-rejected statement, or rollback rules across multiple advices can change the outcome.

## 6. Rollback Rules: Changing Exceptions Requires Checking Specific Rules Too

### 6.1. Choosing Which Checked Exceptions Must Roll Back

~~~java
@Transactional(rollbackFor = IOException.class)
public void processFile() throws IOException {
    // When IOException exits the method through the proxy, Spring marks rollback.
}
~~~

`rollbackFor` accepts an **exception class and its subclasses**, carrying lower risk than string rules like `rollbackForClassName = "Exception"`, whose broad patterns can match unintentionally. When designing a business API that reasonably uses checked exceptions, write rollback rules reflecting **business semantics**, rather than wrapping every error into a `RuntimeException` solely to force rollback.

### 6.2. Allowing an Unchecked Exception Not to Roll Back

~~~java
@Transactional(noRollbackFor = PaymentNoticeException.class)
public void recordPaymentNotice() {
    // Can commit data even though PaymentNoticeException escapes
    // if the specific rule wins and the transaction is still committable.
}
~~~

This is illustrative code; `PaymentNoticeException` is a hypothetical business type. `noRollbackFor` does not guarantee commit in all situations: if the transaction is already rollback-only or the database cannot commit, Spring must still handle the real state.

### 6.3. When Multiple Rules Match Simultaneously

~~~java
@Transactional(
    rollbackFor = Exception.class,
    noRollbackFor = NonFatalBusinessException.class
)
public void settle() {
    // If NonFatalBusinessException is a subclass of Exception,
    // the more specific noRollbackFor takes precedence for this type.
}
~~~

Spring picks the **strongest/most specific matching rule**. If code wraps `NonFatalBusinessException` into `IllegalStateException`, the specific rule for `NonFatalBusinessException` may no longer match the **outer exception** (Spring does not automatically traverse the entire `getCause()` chain to match rules). Preserving `cause` remains valuable for debugging, while default rollback rules match against the **throwable type delivered to advice**.

When defining rules, avoid putting the exact same exception type in both `rollbackFor` and `noRollbackFor`. A clean exception hierarchy and consistent policy are easier to test than overlapping patterns.

## 7. Swallowing Errors Does Not Always Lead to Commit: Inner REQUIRED Already Marked Rollback-Only

A special pitfall in Spring is that multiple **logical transaction scopes** can share the same **physical transaction** under `REQUIRED` propagation.

Diagram:

~~~mermaid
flowchart TD
    A["Caller"] --> B["OuterService proxy<br/>@Transactional REQUIRED"]
    B --> C["OuterService.outer()"]
    C --> D["InnerService proxy<br/>@Transactional REQUIRED"]
    D --> E["InnerService.inner()"]
    E --> F["Throws RuntimeException"]
    F --> G["Inner interceptor marks<br/>shared transaction rollback-only"]
    G --> H["Outer catches exception<br/>and returns normally"]
    H --> I["Outer interceptor requests commit"]
    I --> J["Cannot commit due to rollback-only"]
    J --> K["Rolls back and may throw<br/>UnexpectedRollbackException"]
~~~

Example with two separate Spring beans:

~~~java
@Service
class OuterService {
    private final InnerService inner;

    OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void outer() {
        try {
            inner.fail(); // Goes through InnerService proxy.
        } catch (IllegalStateException ex) {
            // Outer handles the error and wants to continue.
        }
        // Finishes normally, yet the shared transaction is already rollback-only.
    }
}

@Service
class InnerService {
    @Transactional(propagation = Propagation.REQUIRED)
    public void fail() {
        throw new IllegalStateException("inner failed");
    }
}
~~~

This is **illustrative code lacking imports/bootstrapping**, not a standalone program. Under default behavior, inner advice marks the shared physical transaction rollback-only when an unchecked exception passes through the inner proxy. The outer catch **cannot clear that marker**; when outer tries to commit, it can throw `UnexpectedRollbackException` so the caller does not mistake a rollback for a successful commit.

This differs from **self-invocation** within a single bean: if `outer()` calls `this.inner()`, inner advice is not executed separately; pure Java throw/catch may not mark rollback-only unless outer advice later sees an exception or other code/resources explicitly set it.

It also differs from inner `REQUIRES_NEW`: inner rollback can be independent of the outer transaction, depending on resource and propagation configuration. Never switch propagation just to hide `UnexpectedRollbackException`; choose atomicity matching business requirements.

## 8. Catching Yet Still Wanting Rollback: Ways to Express Intent

### 8.1. Rethrow an Appropriate Exception

Most common when business rules treat the failure as a failure of the entire transaction:

~~~java
@Transactional
public void transfer() {
    try {
        performTransfer();
    } catch (RuntimeException ex) {
        recordDiagnostic(ex);
        throw ex;
    }
}
~~~

This is an illustrative snippet with undefined helpers. Callers can handle the exception **after** the service proxy completes rollback. Do not swallow exceptions in the service and hope `@Transactional` somehow guesses the transfer failed.

### 8.2. `rollbackFor` for Meaningful Checked Exceptions

~~~java
@Transactional(rollbackFor = ValidationException.class)
public void validateAndSave() throws ValidationException {
    // ValidationException is a custom checked exception.
}
~~~

This is an illustrative snippet; `ValidationException extends Exception` must be defined in a real application. This keeps the checked exception API contract alongside an explicit commit/rollback policy.

### 8.3. Explicitly Mark Rollback-Only and Return

Sometimes you must catch an exception to return a business result without throwing an error. Spring provides an API for that:

~~~java
@Transactional
public Result saveAndReturnResult() {
    try {
        performWrites();
        return Result.success();
    } catch (BusinessException ex) {
        TransactionAspectSupport.currentTransactionStatus().setRollbackOnly();
        return Result.failed(ex.getMessage());
    }
}
~~~

This is an **illustrative snippet** with hypothetical `Result`, `BusinessException`, and `performWrites()`. `TransactionAspectSupport.currentTransactionStatus()` is only valid when the current call has a Spring-interceptor-managed transaction status; calling it outside advice can fail. `setRollbackOnly()` marks the scope for rollback and relies on the manager executing it at completion; it **does not immediately roll back at the line of the call**. If the method is participating in another transaction, the marker can make the outer transaction roll back and trigger `UnexpectedRollbackException` at the outer boundary.

If you prefer not to couple business code to `TransactionAspectSupport`, consider splitting a service boundary that lets exceptions reach the caller, or using `TransactionTemplate` with `status.setRollbackOnly()` inside its callback.

### 8.4. Returning an Error Object Is Not Throwing an Exception

Return types such as `Result.failure(...)` or returning `null` **are not treated as exceptions** by traditional `@Transactional`. However, Spring has **certain special integrations**: Spring's rollback documentation describes support for `Vavr Try.Failure` and, since Spring Framework 6.1, `Future`/`CompletableFuture` instances **already exceptionally completed at the moment the method returns** in supported cases. Do not infer that **every** error-representing return object is interpreted by Spring as rollback. For a `CompletableFuture` that completes exceptionally **after** the synchronous transaction boundary has closed, Spring cannot retroactively roll back that transaction.

## 9. Runnable Java 17+ Example: One Table, Eight Error-Handling Styles

The example below runs a Spring Boot 3.3.5 / Spring Framework 6.1.x CLI app with in-memory H2. It keeps the policy at defaults and uses a `JdbcTransactionManager` managing one `DataSource`. It runs each scenario sequentially, printing the balance **after the transaction boundary completes** to distinguish commit from rollback. No server or external DB setup is needed.

**Complete structure (four files):**

~~~text
exception-outcome-demo/
├── pom.xml
└── src/main/java/example/txexceptions/
    ├── ExceptionOutcomeApplication.java
    ├── ScenarioService.java
    └── NestedService.java
~~~

### 9.1. pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>
    <groupId>example</groupId>
    <artifactId>exception-outcome-demo</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-aop</artifactId>
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
~~~

### 9.2. src/main/java/example/txexceptions/ExceptionOutcomeApplication.java

~~~java
package example.txexceptions;

import java.io.IOException;
import javax.sql.DataSource;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.UnexpectedRollbackException;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@SpringBootApplication
@EnableTransactionManagement
public class ExceptionOutcomeApplication {
    public static void main(String[] args) {
        SpringApplication.run(ExceptionOutcomeApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource dataSource) {
        return new JdbcTransactionManager(dataSource);
    }

    @Bean
    CommandLineRunner demo(JdbcTemplate jdbc, ScenarioService scenario) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE ledger (id INT PRIMARY KEY, amount INT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO ledger (id, amount) VALUES (?, ?)", 1, 100
            );
            System.out.println("START=" + amount(jdbc));

            scenario.swallowRuntime();
            System.out.println("AFTER_SWALLOW=" + amount(jdbc));

            try {
                scenario.throwRuntime();
            } catch (IllegalStateException ex) {
                System.out.println("RUNTIME_CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_RUNTIME=" + amount(jdbc));

            try {
                scenario.throwChecked();
            } catch (IOException ex) {
                System.out.println("CHECKED_CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_CHECKED=" + amount(jdbc));

            try {
                scenario.wrapChecked();
            } catch (IllegalStateException ex) {
                System.out.println(
                    "WRAPPED_CAUGHT=" + ex.getClass().getSimpleName()
                    + "/cause=" + ex.getCause().getClass().getSimpleName()
                );
            }
            System.out.println("AFTER_WRAPPED=" + amount(jdbc));

            try {
                scenario.checkedRollback();
            } catch (IOException ex) {
                System.out.println("RULE_CAUGHT=" + ex.getMessage());
            }
            System.out.println("AFTER_RULE=" + amount(jdbc));

            try {
                scenario.runtimeNoRollback();
            } catch (IllegalStateException ex) {
                System.out.println(
                    "NO_ROLLBACK_CAUGHT=" + ex.getMessage()
                );
            }
            System.out.println("AFTER_NO_ROLLBACK=" + amount(jdbc));

            scenario.swallowAndMarkRollbackOnly();
            System.out.println("AFTER_MARK_ONLY=" + amount(jdbc));

            try {
                scenario.outerCatchesInner();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                    "OUTER_END=" + ex.getClass().getSimpleName()
                );
            }
            System.out.println("AFTER_OUTER=" + amount(jdbc));
        };
    }

    private static Integer amount(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT amount FROM ledger WHERE id = ?", Integer.class, 1
        );
    }
}
~~~

### 9.3. src/main/java/example/txexceptions/ScenarioService.java

~~~java
package example.txexceptions;

import java.io.IOException;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class ScenarioService {
    private final JdbcTemplate jdbc;
    private final NestedService nested;

    public ScenarioService(JdbcTemplate jdbc, NestedService nested) {
        this.jdbc = jdbc;
        this.nested = nested;
    }

    // 1: Exception is caught inside method -> advice sees return.
    @Transactional
    public void swallowRuntime() {
        add(10);
        try {
            throw new IllegalStateException("internal-failure");
        } catch (IllegalStateException ex) {
            System.out.println("INSIDE_CAUGHT=" + ex.getMessage());
        }
    }

    // 2: RuntimeException passes through proxy -> rollback.
    @Transactional
    public void throwRuntime() {
        add(20);
        throw new IllegalStateException("runtime-leaked");
    }

    // 3: Checked IOException passes through proxy -> default commit.
    @Transactional
    public void throwChecked() throws IOException {
        add(30);
        throw new IOException("checked-leaked");
    }

    // 4: Wrap checked exception into unchecked before boundary.
    @Transactional
    public void wrapChecked() {
        add(40);
        try {
            throw new IOException("io-problem");
        } catch (IOException ex) {
            throw new IllegalStateException("wrapped-runtime", ex);
        }
    }

    // 5: Keep checked exception yet explicitly request rollback.
    @Transactional(rollbackFor = IOException.class)
    public void checkedRollback() throws IOException {
        add(50);
        throw new IOException("explicit-check");
    }

    // 6: Unchecked exception, yet explicit rule requests no rollback.
    @Transactional(noRollbackFor = IllegalStateException.class)
    public void runtimeNoRollback() {
        add(60);
        throw new IllegalStateException("keep-change");
    }

    // 7: Swallow error and mark rollback-only.
    @Transactional
    public void swallowAndMarkRollbackOnly() {
        add(70);
        try {
            throw new IllegalStateException("handled-but-failed");
        } catch (IllegalStateException ex) {
            TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
            System.out.println(
                "MARKED_ROLLBACK_ONLY="
                + TransactionAspectSupport.currentTransactionStatus()
                    .isRollbackOnly()
            );
        }
    }

    // 8: Inner REQUIRED already passed through proxy and marked rollback-only.
    @Transactional
    public void outerCatchesInner() {
        add(80);
        try {
            nested.requiredThrows();
        } catch (IllegalStateException ex) {
            System.out.println("OUTER_CAUGHT=" + ex.getMessage());
        }
        add(5);
    }

    private void add(int delta) {
        jdbc.update(
            "UPDATE ledger SET amount = amount + ? WHERE id = 1", delta
        );
    }
}
~~~

### 9.4. src/main/java/example/txexceptions/NestedService.java

~~~java
package example.txexceptions;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class NestedService {
    private final JdbcTemplate jdbc;

    public NestedService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void requiredThrows() {
        jdbc.update(
            "UPDATE ledger SET amount = amount + ? WHERE id = 1", 90
        );
        throw new IllegalStateException("nested-runtime");
    }
}
~~~

**Run in `exception-outcome-demo` directory** (JDK 17+ and Maven installed; Maven downloads dependencies if needed):

~~~bash
mvn -q spring-boot:run
~~~

The lines **printed by the program**, in exact order, ignoring Spring/Hikari startup logs:

~~~text
START=100
INSIDE_CAUGHT=internal-failure
AFTER_SWALLOW=110
RUNTIME_CAUGHT=runtime-leaked
AFTER_RUNTIME=110
CHECKED_CAUGHT=checked-leaked
AFTER_CHECKED=140
WRAPPED_CAUGHT=IllegalStateException/cause=IOException
AFTER_WRAPPED=140
RULE_CAUGHT=explicit-check
AFTER_RULE=140
NO_ROLLBACK_CAUGHT=keep-change
AFTER_NO_ROLLBACK=200
MARKED_ROLLBACK_ONLY=true
AFTER_MARK_ONLY=200
OUTER_CAUGHT=nested-runtime
OUTER_END=UnexpectedRollbackException
AFTER_OUTER=200
~~~

### 9.5. Exact Explanation of Each Data Milestone

| Case | Balance before | Action in transaction | Reason for outcome | Balance after |
| --- | ---: | --- | --- | ---: |
| Swallow unchecked | 100 | +10 | Advice sees only return; commits | 110 |
| Unchecked escapes | 110 | +20 | Default rollback | 110 |
| Checked escapes | 110 | +30 | 6.1 default does not roll back checked | 140 |
| Wrap checked into unchecked | 140 | +40 | Advice sees `IllegalStateException`; rolls back | 140 |
| `rollbackFor = IOException.class` | 140 | +50 | Explicit rule makes checked roll back | 140 |
| `noRollbackFor = IllegalStateException.class` | 140 | +60 | Explicit rule allows commit, exception still thrown | 200 |
| Catch and `setRollbackOnly()` | 200 | +70 | Method returns, yet transaction is rollback-only | 200 |
| Outer catches inner `REQUIRED` | 200 | outer +80, inner +90, outer +5 | Inner proxy sets rollback-only; outer commit fails | 200 |

A few important details of the example:

- `CommandLineRunner` has Spring inject the **`ScenarioService` proxy**, rather than creating the service via `new`. For the inner case, `NestedService` is a separate Spring bean injected into `ScenarioService` so calls **pass through the nested proxy**.
- All UPDATEs use `JdbcTemplate` and the same `DataSource` managed by `JdbcTransactionManager`. There are no external HTTP calls or second databases, so rollback/commit is verified directly via the balance.
- `IOException` is thrown **after a valid UPDATE**, separating Spring rollback policy logic from vendor SQL errors.
- In the `noRollbackFor` case, the exception still exits to the caller even though the database committed. **Caller seeing an error does not mean the transaction rolled back.**
- With `setRollbackOnly()` on a new transaction, the method can return normally and rollback occurs at completion; not every local `setRollbackOnly()` call throws `UnexpectedRollbackException`.
- In the inner `REQUIRED` case, inner advice sees the unchecked exception and marks the **shared transaction** rollback-only. Outer catch does not clear the marker. When outer tries to commit, `UnexpectedRollbackException` is the expected outcome of this model.
- These results assume Spring Framework 6.1.x, default rules, a healthy H2 driver, and no external or test-level transaction wrapping the runner.

## 10. Guidelines for Handling Errors While Preserving Atomicity

### 10.1. Identify Who Owns the Transaction Boundary

Place `@Transactional` on service methods that other callers invoke **through a Spring proxy**. If a bean's `outer()` calls `this.inner()` where the annotation sits only on `inner()`, the inner proxy advice is bypassed; reasoning about inner rollback rules then no longer applies. Extract another bean or move the transaction boundary to the appropriate entrypoint when needed.

### 10.2. Decide Business Policy Before Choosing Catch/Wrap

Three scenario patterns:

- **Error fails the whole operation:** rethrow an exception recognized by rollback rules, or declare `rollbackFor` for checked exceptions.
- **Minor error allowed to continue:** catch intentionally, but only if the system accepts **committing prior changes** and resources have not been marked rollback-only.
- **Error handled to return a result, yet data must be discarded:** catch and mark rollback-only, or organize another service boundary that returns the result after the transaction rolls back.

Do not convert to unchecked solely because you want a “serious error” while forgetting the public API contract; nor convert to checked solely to avoid rollback while forgetting data consistency.

### 10.3. Place Catch Outside the Transaction When Building Responses

Example REST controller or adapter:

~~~java
try {
    paymentService.pay(request);
    return ResponseEntity.ok().build();
} catch (PaymentRejectedException ex) {
    return ResponseEntity.unprocessableEntity().build();
}
~~~

This is a **non-standalone excerpt**. `paymentService.pay()` needs a rollback policy matching `PaymentRejectedException` **before** the exception reaches the controller. If `PaymentRejectedException` is checked and the service lacks `rollbackFor` (or a matching global default), the controller returning HTTP 422 **does not mean** the database rolled back. The API layer and the transaction layer have distinct responsibilities.

### 10.4. Avoid Swallowing Every Exception in Repositories

An anti-pattern:

~~~java
try {
    repository.save(entity);
} catch (Exception ex) {
    return false; // Illustrative structure; risks hiding failures.
}
~~~

With a transaction in the caller, returning `false` can make the outer transaction commit incomplete data. On the other hand, if the repository proxy already marked the shared transaction rollback-only, the outer scope may still receive `UnexpectedRollbackException`. Distinguish **business validation** that can be checked before writing from **persistence failures** that require explicit rollback.

### 10.5. Non-DB Side Effects Do Not Roll Back Alongside JDBC

If code already sent an email, made an HTTP call, or published a message to an independent broker before rolling back the database, those side effects are usually not automatically recalled. Catching/wrapping exceptions **does not change resource boundaries**. When DB state and events must stay synchronized, consider a transactional outbox and post-commit handling. Do not use `noRollbackFor` to “save” an already sent side effect at the cost of consistency.

## 11. Debugging a Case of “Exception Thrown, Yet Data Still Committed”

Trace in **chronological order** instead of just grepping exception names:

1. **Identify the boundary:** which method was actually called through a Spring proxy, which annotation/rules applied, and which manager governs the database?
2. **Identify where the exception arose:** before or after SQL, inside which `try` block, and did a library/repository translate its type?
3. **Trace the catch path:** is the catch inside the transactional method, inside a transactional inner bean, or in a controller outside the proxy?
4. **Record the exception type exiting the boundary:** checked or unchecked; what is the outermost object? Are there `getCause()` objects present only for debugging rather than driving rollback?
5. **Check rules:** `rollbackFor`, `noRollbackFor`, strongest matching rule, and global `rollbackOn` if supported by framework/config.
6. **Check rollback-only:** did an inner scope mark global rollback-only? If outer returned normally yet still rolled back, suspect `UnexpectedRollbackException`.
7. **Observe real commit/rollback:** enable transaction manager logs and check data from outside the transaction after the method finishes.
8. **Rule out test transactions:** in Spring TestContext, a `@Transactional` test can create an outer transaction that rolls back by default after the test, misleading observations about service commits.
9. **Check resources:** do the repository and manager use the exact same `DataSource`/`ConnectionFactory`? Did a DB error leave the transaction uncommittable?

With Spring Boot, in test environments you can enable:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
~~~

Log messages vary by version/manager. Do not treat “no exception at the end of the method” as sufficient proof of a successful commit; flushing, DB constraints, and the commit phase still follow. Conversely, seeing no rollback log on an inner scope joining an outer transaction does not mean the database committed.

### Distinguishing Outcomes During Investigation

| Observation | What to check next |
| --- | --- |
| Caller catches RuntimeException, data still increased | `noRollbackFor`? Caught/translated before advice? Wrong transaction manager/resource? UPDATE outside transaction? |
| Caller catches checked IOException, data still increased | Is `rollbackFor=IOException.class` present? Is global `ALL_EXCEPTIONS` enabled? |
| Method returns normally, data did not increase | `setRollbackOnly()`? Inner `REQUIRED`? Database rolled back itself? |
| Outer catches inner, then receives `UnexpectedRollbackException` | Did inner proxy mark the shared physical transaction rollback-only? |
| Controller converts IOException to RuntimeException, service data still commits | Did controller convert type **after** service proxy already committed? |
| `@Transactional` present yet no advice runs on method | Self-invocation, non-Spring-managed bean, proxy limitations, transaction infrastructure not enabled? |

## 12. Practice Questions: Identifying the Right Exception at the Boundary

**Question 1.** A `@Transactional` method UPDATEs +10 and executes `throw new IllegalStateException()`. The method catches `IllegalStateException` itself and returns an error DTO. No inner proxy/rollback-only/DB error. Does the transaction roll back? **No, by default: advice sees a normal return and can commit +10.**

**Question 2.** A `@Transactional` service UPDATEs +10 and throws checked `IOException`. The controller catches it and throws `IllegalStateException`. Spring Framework 6.1 uses default rules, with no outer transaction. Does the service transaction roll back? **No: service advice sees checked `IOException` and can commit before the controller wraps it.**

**Question 3.** The service catches `IOException` inside the method and wraps it into `IllegalStateException` with a cause. No custom rules. Outcome? **Rolls back because an unchecked exception crosses advice**, even though the root cause is a checked exception.

**Question 4.** Outer `@Transactional` calls inner bean `@Transactional(REQUIRED)`; inner throws unchecked, outer catches and returns. Why can outer receive `UnexpectedRollbackException`? **Because the inner proxy marked the shared physical transaction rollback-only before outer caught it.**

**Question 5.** Outer in the same class calls `this.inner()`, where inner has `@Transactional(rollbackFor=IOException.class)`. Why might the custom rollback rule not run? **Because self-invocation in proxy mode bypasses inner interception; verify the actual transaction boundary.**

**Question 6.** A service has `@Transactional(noRollbackFor = IllegalArgumentException.class)`, yet JDBC already hit an error leaving the transaction in an aborted state. It throws `IllegalArgumentException` and exits. Is commit guaranteed? **No.** The rule permits **attempting commit** for that exception; it cannot repair resource/rollback-only state.

## 13. Conclusions on Error-Path Design

When predicting `@Transactional` outcomes, put your finger on **the exact point where transaction advice regains control**: did the Java method return, throw unchecked, throw checked, or does the transaction already carry rollback-only? Then inspect the manager, propagation, and DB state.

**Catching and swallowing errors** can turn a transaction that should roll back into a commit. **Wrapping/translating exceptions** can change the error type matched by rollback rules. **Catching outside the proxy** cannot undo a decision already completed at the inner boundary. **Outer catching after an inner `REQUIRED` marked rollback-only** does not restore committability.

Place rollback policies at the right service boundary, preserve causes when converting exception types, and verify with failure integration tests checking data after the transaction. That ensures outcomes never depend accidentally on where a `try/catch` sits.

## Official References

- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): checked/unchecked defaults, rollback rules, strongest match, rollback-only, Vavr Try, and Future.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): `rollbackFor`/`noRollbackFor`, transaction metadata, and `ALL_EXCEPTIONS` default since 6.2.
- [Spring Framework — Understanding PROPAGATION_REQUIRED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): logical/physical scopes, rollback-only, `UnexpectedRollbackException`.
- [Spring Framework — Understanding Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction AOP proxy and interceptor.
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html): overview of declarative and programmatic transactions.
