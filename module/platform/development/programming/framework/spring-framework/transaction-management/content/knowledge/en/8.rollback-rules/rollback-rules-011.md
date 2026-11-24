# Failed Try or Future: Spring Rollback by Version and Return Timing

In Spring Framework, **`@Transactional`** is often explained by the rule “if the method throws a `RuntimeException`, the transaction rolls back; if the method completes normally, it commits.” That understanding is a starting point, yet incomplete when a method **returns an object representing failure** instead of throwing an exception outward. Two special cases to recognize are **`io.vavr.control.Try`** in a `Failure` state and **`java.util.concurrent.Future` / `CompletableFuture`** already completed exceptionally.

The deciding factors include the **Spring version**, the **state of the value at the moment the transactional interceptor receives the return value**, and **whether the inner exception type matches rollback rules**. A `Future` that completes with an error several seconds after the method returned cannot rewind an already committed JDBC transaction.

This lesson focuses on **Spring declarative transactions with `@Transactional` and `PlatformTransactionManager` (imperative JDBC/JPA)**. To avoid confusion, we will distinguish method calls that throw exceptions, `Try.Failure`, already-failed `Future`s, still-pending `Future`s, and reactive `Publisher`s. A Java 17+ program running with Spring 6.2, H2, and Vavr is included to observe DB numbers after each call.

## 1. Default Rollback Mechanism Without Special Return Types

A Spring service called **through a transactional proxy**:

~~~java
// Illustrative excerpt; must be invoked through a Spring-managed proxy.
@Transactional
public void update() {
    repository.updateA();
    repository.updateB();
    throw new IllegalStateException("failed");
}
~~~

A call through the proxy follows this flow:

~~~text
Caller -> Spring proxy -> TransactionInterceptor
                              |
                              +-- obtains TransactionManager/TransactionDefinition
                              +-- creates or joins transaction
                              +-- invokes business method
                              +-- observes exception or return value
                              +-- evaluates rollback rules
                              +-- requests commit/rollback
                              +-- cleans up, returns connection to DataSource/pool
~~~

Under common default configurations:

- **`RuntimeException`** and **`Error`** escaping across the boundary cause Spring to request rollback.
- Ordinary **checked `Exception`s** do not trigger automatic rollback unless `rollbackFor` or a different default policy is configured.
- **`@Transactional(rollbackFor=SomeCheckedException.class)`** extends the rollback rule to that checked type.
- **`@Transactional(noRollbackFor=SomeRuntimeException.class)`** can request commit even when that runtime exception is thrown.
- If application code catches an exception and returns normally, the interceptor observes no escaping exception; the transaction can commit unless already marked rollback-only.

For `Try` and `Future`, supported Spring versions add a branch that **inspects the return value** before committing. This branch evaluates the **inner error cause** against the same rollback policy, rather than treating every error-bearing object as an unconditional rollback request.

## 2. Version Matrix: When Did Each Feature Appear?

| Failure form | Spring Framework version | How Spring observes it |
| --- | --- | --- |
| Method throws `RuntimeException`/`Error` outward | Traditional declarative transaction behavior | Interceptor catches the exception exiting the method and evaluates rollback rules |
| Method returns **Vavr `Try.Failure`** | **Since Spring Framework 5.2** | Upon return, Spring detects `Try.Failure`, checks its cause against rollback rules, and marks rollback-only if matched |
| Method returns **exceptionally completed `Future`/`CompletableFuture`** | **Since Spring Framework 6.1** | Upon method return, if the `Future` is done, Spring checks the exception cause and marks rollback-only if matched |
| **`Future` only fails after the method has returned and committed** | No retroactive rollback support in this imperative mechanism | Transaction has already ended; late error signals cannot roll back the finished transaction |
| `Mono`/`Flux` returning `Publisher` in a reactive transaction | Uses `ReactiveTransactionManager` with a suitable reactive workflow | Transaction lifecycle binds to subscription/reactive context, not imperative `Future` checks |

**Historical note:** Spring 5.2 and 6.0 documentation described Vavr `Try.Failure` support; failed-return `Future`/`CompletableFuture` handling was only introduced **as of Spring 6.1**. If a project runs Spring 5.x/6.0, do not rely on the newer `Future` rollback branch. Verify the **actual Spring Framework version on the runtime classpath**, not just the Spring Boot version listed in `pom.xml`/`build.gradle`.

**Another change since Spring 6.2:** you can opt into rolling back by default on all exceptions, including checked exceptions, via **`@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)`** when using annotation transaction infrastructure. This affects evaluating the cause of `Try`/`Future` when no specific rule applies; it still does not let a `Future` failing *after the transaction closed* roll back retroactively. The runnable example in section 7 **keeps the default unchecked rollback** so differences remain clear.

The examples below use Spring 6.2.x; read your project's release notes and active policies if upgrading or using custom transaction interceptors.

## 3. Vavr Try: Failure Wrapped Inside the Return Value

### 3.1. What Are `Try.Success` and `Try.Failure`?

**Vavr** is an independent Java library commonly used to represent a computation result that can succeed or fail. The **`io.vavr.control.Try<T>`** type has two forms:

- **`Success(value)`:** holds a successful value.
- **`Failure(Throwable)`:** holds the failure cause as a `Throwable`.

Example independent of Spring:

~~~java
import io.vavr.control.Try;

Try<Integer> ok = Try.of(() -> 2 + 3);
Try<Integer> failed = Try.of(() -> {
    throw new IllegalStateException("cannot calculate");
});

System.out.println(ok.isSuccess());       // true
System.out.println(failed.isFailure());    // true
~~~

This is an excerpt for a program with the Vavr dependency, not a standalone Java file since it lacks a class/`main`. Vavr `Try` typically catches exceptions thrown while running a lambda and turns them into `Failure`. Therefore, when a `@Transactional` method returns **`Try.Failure`**, the interceptor **sees no exception escaping the method** via the normal exception path.

### 3.2. How Does Spring Handle `Try.Failure`?

Since Spring 5.2, when a transactional method returns a Vavr `Try`, Spring recognizes this value and inspects `Failure` **before completing the transaction**. Conceptually:

~~~text
@Transactional method
    |
    +-- SQL UPDATE
    +-- return Try.Failure(cause)
    |
transaction interceptor receives result
    |
    +-- is result a Try?
    +-- is it a Failure?
    +-- rollbackOn(cause) per policy?
          |
          +-- true  -> marks transaction rollback-only
          +-- false -> does not mark rollback-only from this Failure
    |
    +-- manager completes transaction per current state
~~~

Example:

~~~java
// Excerpt: Spring-managed service with JdbcTemplate participating in the transaction.
@Transactional
public Try<String> updateAndReturnFailure() {
    jdbcTemplate.update("UPDATE demo_state SET amount=amount+1 WHERE id=1");
    return Try.failure(new IllegalStateException("invalid"));
}
~~~

On supported versions, **`Failure` holding `IllegalStateException`** matches the default rollback rule, so rollback is requested even though the method returned normally. Returning `Success` after an UPDATE usually permits commit, provided there is no rollback-only flag or other failure.

**`Failure` does not automatically mean rollback for every `Throwable`.** For instance, a `Failure` holding **`IOException`** (a checked exception) can still lead to commit under standard defaults:

~~~java
@Transactional
public Try<String> checkedFailure() {
    jdbcTemplate.update("UPDATE demo_state SET amount=amount+1 WHERE id=1");
    return Try.failure(new java.io.IOException("checked failure"));
}
~~~

To roll back on this checked cause, declare:

~~~java
@Transactional(rollbackFor = java.io.IOException.class)
public Try<String> checkedFailureWithRule() {
    jdbcTemplate.update("UPDATE demo_state SET amount=amount+1 WHERE id=1");
    return Try.failure(new java.io.IOException("checked failure"));
}
~~~

Both snippets are illustrative and require imports, class/service setup, and a configured `DataSource`. Under Spring 6.2 with `ALL_EXCEPTIONS`, the checked branch can roll back by default; always know the actual runtime policy.

### 3.3. What About a `Try` State Created *After* the Method Returns?

`Try` normally already holds its `Success`/`Failure` state when returned; Spring can inspect `Failure` right at the boundary. However, if a method returns **`Try.Success` wrapping a `Future`** or a callback that will fail later, Spring **does not unwrap a `Future` nested inside `Success`** to predict the future.

Example:

~~~java
// This is only a sketch of the data type structure.
Try<CompletableFuture<String>> value =
        Try.success(new CompletableFuture<>());

// value.isSuccess() == true even though the inner CompletableFuture is still pending.
~~~

Do not confuse “`Try` wrapping an asynchronous task” with “`Try.Failure` already existing at method return time.” Identify the **exact object directly inspected by the transactional interceptor** and when the failure actually happens.

## 4. Future/CompletableFuture: The Inspection Point Is Method Return Time

### 4.1. Why Does `Future` Differ from `Try`?

The JDK's **`Future<T>`** represents work that may not be finished yet. A **`CompletableFuture<T>`** can be in one of these states:

- **Pending:** no result yet, `isDone() == false`.
- **Completed normally:** has a successful result.
- **Completed exceptionally:** terminated with a `Throwable`.

Since **Spring 6.1**, when an imperative transactional method returns a `Future`, Spring inspects the `Future`'s state **at the moment it receives the return value**. If the `Future` is already **done** and **`get()` indicates it completed exceptionally**, Spring can extract the failure cause, apply rollback rules, mark the transaction rollback-only, and finish the transaction.

Example of a `Future` already failed upon return:

~~~java
// Illustrative excerpt in a Spring service.
@Transactional
public CompletableFuture<String> failedImmediately() {
    jdbcTemplate.update("UPDATE demo_state SET amount=amount+1 WHERE id=1");
    return CompletableFuture.failedFuture(
            new IllegalStateException("failed now"));
}
~~~

In Spring 6.1+, the `IllegalStateException` cause matches the default rollback rule and the `Future` already failed **before the method returned**, so Spring can roll back the UPDATE. The caller receives a `CompletableFuture` in an exceptionally completed state; **the method does not have to throw an exception directly** for rollback to occur.

### 4.2. `Future` Still Pending When the Method Returns

~~~java
@Transactional
public CompletableFuture<String> failedLater() {
    jdbcTemplate.update("UPDATE demo_state SET amount=amount+1 WHERE id=1");
    return new CompletableFuture<>(); // Not yet completed on return.
}
~~~

At the moment the interceptor inspects it, **`isDone() == false`**. It cannot know whether the future will succeed or fail; Spring completes the transaction based on current state. If there is no rollback-only flag or other failure, the JDBC transaction **commits**. After the caller receives the `Future` and calls `completeExceptionally(...)`, the `Future`'s state changes to failed, yet the JDBC transaction **has already ended**.

~~~text
T0: Spring opens transaction
T1: UPDATE succeeds inside transaction
T2: method returns pending CompletableFuture
T3: interceptor sees isDone=false, detects no exceptional completion
T4: manager commits and releases JDBC Connection
T5: caller/another worker completes Future with an exception
T6: Future reports error to caller; T4 data does not automatically roll back
~~~

If a concurrent worker completes the `Future` right around T2/T3, whether it transitions to `done` in time can change commit vs. rollback. **Never build data correctness on a race condition hoping “the Future will fail in time before the transaction closes.”**

### 4.3. Cases of `CompletableFuture.completedFuture(...)` or `failedFuture(...)`

| Value returned by method | State at return time | Rollback meaning in Spring 6.1+ |
| --- | --- | --- |
| `CompletableFuture.completedFuture("ok")` | Done, succeeded | Generates no rollback request from the handle |
| `CompletableFuture.failedFuture(new IllegalStateException(...))` | Done, runtime error | Can roll back per default rules |
| `CompletableFuture.failedFuture(new IOException(...))` | Done, checked error | Usually does not roll back by default; use `rollbackFor=IOException.class` or a matching policy |
| `new CompletableFuture<>()` | Pending | No failure to evaluate at return time, so transaction can commit |
| Pending `Future` then `completeExceptionally(...)` after transaction | Late error | Cannot retroactively roll back an already committed transaction |
| Method directly throws `IllegalStateException` | Does not return `Future` | Handled on normal exception path; default rollback |

**Note:** do not assume Spring always calls `CompletableFuture.isCompletedExceptionally()`. In Spring 6.2's implementation, the general flow checks `Future.isDone()`, calls `Future.get()`, and then evaluates the `ExecutionException` cause against rollback rules. Exact detection details belong to implementation/version; the key contract is **the `Future` has already failed when the method returns**.

Do not equate a **successfully done `Future`** with a **failed done `Future`**. Nor assume cancelling a `Future` with `cancel(...)` shares identical rollback semantics with every `ExecutionException`; cancellation/blocking/interruption have distinct semantics that must be tested on the actual version and API in use.

## 5. Rollback Rules Still Govern Both `Try` and `Future`

Spring evaluates the `Throwable` cause of `Try.Failure` or a failed `Future` against the transaction's policy, not the wrapper's class name.

| Cause | Annotation / policy | Expected behavior in Spring 6.2 |
| --- | --- | --- |
| `IllegalStateException` (`RuntimeException`) | Default `@Transactional` | Rolls back when `Try.Failure` or exceptional `Future` is present at check time |
| `IOException` (checked) | Default `@Transactional`, `rollbackOn` unchanged | Usually commits unless rollback-only for another reason |
| `IOException` (checked) | `@Transactional(rollbackFor=IOException.class)` | Rolls back when cause can be inspected in time |
| `IllegalStateException` | `@Transactional(noRollbackFor=IllegalStateException.class)` | Does not roll back solely from that cause; can commit |
| `IOException` (checked) | Spring 6.2 with `rollbackOn=ALL_EXCEPTIONS` | Rolls back by default, unless overridden by a stronger local rule |
| Any cause | `Future` not done at return time | No cause available to apply rollback rules at that moment |

**Do not treat defaults as absolute.** Spring 6.2 lets you set `ALL_EXCEPTIONS` as default; a project may use XML rollback rules, a custom `TransactionAttributeSource`, or `noRollbackFor`. Specific method rules can override defaults. When an outer transaction is already rollback-only, the manager may still roll back even if the result wrapper's cause does not match.

**Regarding checked exceptions:** a method returning `Try.Failure(new IOException(...))` differs in Java signature from a method directly declaring `throws IOException`, yet in Spring 6.2 they share the **rollback rule evaluation step on `IOException`**. The difference lies in how the error arrives: `Try` is inspected as a return value, whereas thrown exceptions are caught by the interceptor.

## 6. Why Doesn't `@Async` Solve Late Rollbacks?

Spring 6.1+ documentation describes `Future`-return handling to support **`@Transactional` + `@Async`** signatures returning `CompletableFuture`. A concise example:

~~~java
// Excerpt; requires @EnableAsync and @EnableTransactionManagement
// along with corresponding Spring bean/proxy, transaction manager, and repository.
@Async
@Transactional
public CompletableFuture<String> writeAsync() {
    try {
        repository.persist();
        return CompletableFuture.completedFuture("ok");
    } catch (DataAccessException ex) {
        return CompletableFuture.failedFuture(ex);
    }
}
~~~

Here the method must return a handle per the `@Async` contract, yet the DB error occurred **inside the transactional method call itself** and it returned an **already failed `Future`**. Spring can detect the failure before ending the transaction on the method's execution thread.

**Important limitations:**

1. `PlatformTransactionManager` transactions propagate along the **thread's** execution context. Do not assume an open transaction on the caller thread automatically propagates to every worker thread.
2. `@Async` changes **where and when the method runs**; the transaction manager must wrap the part where SQL actually runs, with proper advisor/proxy ordering.
3. If the method merely calls `CompletableFuture.supplyAsync(...)` to **schedule SQL to run later** and returns a pending `Future`, the method's transaction can commit **before the worker SQL even runs**. The worker normally uses a different connection/transaction.
4. Do not hold a JDBC transaction open indefinitely until a `Future` finishes simply because the method returns `CompletableFuture`.
5. If the goal is a workflow with multiple async tasks, design separate transaction boundaries per task and consistency mechanisms between them.

**Common design mistake:** a service writes to the DB, returns an incomplete `Future`, then sends HTTP requests or publishes messages in a callback expecting an exception in the callback to roll back the service's JDBC transaction. A callback executing after commit cannot undo that transaction. You may need a transactional outbox, saga/compensation, or redesigned business boundaries.

## 7. Java 17+ Program Verifying Both `Try` and `Future`

This example uses **Spring Framework 6.2.12**, **Vavr 0.10.5**, and **H2 2.3.232**. All methods are invoked **through a Spring bean proxy**; the same `DataSource` and `JdbcTransactionManager` are used. The `amount` column starts at 0. Each method increments `amount` by 1 before returning its result; the remaining committed count shows whether Spring rolled back.

Demo goals:

- Runtime `Try.Failure` → rollback, `amount` does not increase.
- Checked `Try.Failure` under default → commit, `amount` increases.
- Checked `Try.Failure` + `rollbackFor` → rollback.
- Runtime `Try.Failure` + `noRollbackFor` → commit.
- Already-failed runtime `Future` → rollback.
- Already-failed checked `Future` under default → commit.
- Already-failed checked `Future` + `rollbackFor` → rollback.
- `Future` pending at return → commit; `completeExceptionally` afterward cannot roll back.
- `Try.Success` → commit.

### 7.1. Structure and `pom.xml`

~~~text
return-value-rollback-demo/
├── pom.xml
└── src/main/java/demo/ReturnValueRollbackDemo.java
~~~

**`pom.xml`**

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>return-value-rollback-demo</artifactId>
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
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.12</version>
        </dependency>
        <dependency>
            <groupId>io.vavr</groupId>
            <artifactId>vavr</artifactId>
            <version>0.10.5</version>
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
                    <mainClass>demo.ReturnValueRollbackDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Real Spring Boot apps should use proper dependency management/BOM rather than hardcoding every version from the demo. Vavr must actually be present on the runtime classpath for Spring to detect the `Try` type; using a custom `Result` or `Either` **does not inherit** Vavr `Try` detection.

### 7.2. Complete Spring Program

**`src/main/java/demo/ReturnValueRollbackDemo.java`**

~~~java
package demo;

import io.vavr.control.Try;
import java.io.IOException;
import java.util.concurrent.CompletableFuture;
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

public final class ReturnValueRollbackDemo {
    private ReturnValueRollbackDemo() {}

    private static int amount(JdbcTemplate jdbc) {
        Integer result = jdbc.queryForObject(
                "SELECT amount FROM demo_state WHERE id = 1",
                Integer.class);
        if (result == null) {
            throw new IllegalStateException("Row not found");
        }
        return result;
    }

    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            DemoService service = context.getBean(DemoService.class);

            jdbc.execute("CREATE TABLE demo_state ("
                    + "id INT PRIMARY KEY, amount INT NOT NULL)");
            jdbc.update(
                    "INSERT INTO demo_state(id, amount) VALUES (?, ?)", 1, 0);

            System.out.println("start=" + amount(jdbc));

            Try<String> r1 = service.tryRuntimeFailure();
            System.out.printf("try runtime: failure=%s, amount=%d%n",
                    r1.isFailure(), amount(jdbc));

            Try<String> r2 = service.tryCheckedDefault();
            System.out.printf("try checked default: failure=%s, amount=%d%n",
                    r2.isFailure(), amount(jdbc));

            Try<String> r3 = service.tryCheckedExplicit();
            System.out.printf("try checked rollbackFor: failure=%s, amount=%d%n",
                    r3.isFailure(), amount(jdbc));

            Try<String> r4 = service.tryRuntimeNoRollback();
            System.out.printf("try runtime noRollbackFor: failure=%s, amount=%d%n",
                    r4.isFailure(), amount(jdbc));

            CompletableFuture<String> f1 = service.futureImmediateRuntimeFailure();
            System.out.printf("future runtime immediate: exceptional=%s, amount=%d%n",
                    f1.isCompletedExceptionally(), amount(jdbc));

            CompletableFuture<String> f2 = service.futureImmediateCheckedDefault();
            System.out.printf("future checked default: exceptional=%s, amount=%d%n",
                    f2.isCompletedExceptionally(), amount(jdbc));

            CompletableFuture<String> f3 = service.futureImmediateCheckedExplicit();
            System.out.printf("future checked rollbackFor: exceptional=%s, amount=%d%n",
                    f3.isCompletedExceptionally(), amount(jdbc));

            CompletableFuture<String> pending = service.futureStillPending();
            System.out.printf("future pending on return: done=%s, amount=%d%n",
                    pending.isDone(), amount(jdbc));

            pending.completeExceptionally(
                    new IllegalStateException("completed after transaction"));
            System.out.printf("future failed later: exceptional=%s, amount=%d%n",
                    pending.isCompletedExceptionally(), amount(jdbc));

            Try<String> success = service.trySuccess();
            System.out.printf("try success: success=%s, amount=%d%n",
                    success.isSuccess(), amount(jdbc));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableTransactionManagement(proxyTargetClass = true)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            DriverManagerDataSource dataSource = new DriverManagerDataSource();
            dataSource.setDriverClassName("org.h2.Driver");
            dataSource.setUrl("jdbc:h2:mem:return_demo;DB_CLOSE_DELAY=-1");
            dataSource.setUsername("sa");
            dataSource.setPassword("");
            return dataSource;
        }

        @Bean
        public JdbcTemplate jdbcTemplate(DataSource dataSource) {
            return new JdbcTemplate(dataSource);
        }

        @Bean
        public PlatformTransactionManager transactionManager(DataSource dataSource) {
            return new JdbcTransactionManager(dataSource);
        }

        @Bean
        public DemoService demoService(JdbcTemplate jdbcTemplate) {
            return new DemoService(jdbcTemplate);
        }
    }

    public static class DemoService {
        private final JdbcTemplate jdbc;

        public DemoService(JdbcTemplate jdbc) {
            this.jdbc = jdbc;
        }

        private void increment() {
            jdbc.update(
                    "UPDATE demo_state SET amount = amount + 1 WHERE id = 1");
        }

        @Transactional
        public Try<String> tryRuntimeFailure() {
            increment();
            return Try.failure(new IllegalStateException("runtime"));
        }

        @Transactional
        public Try<String> tryCheckedDefault() {
            increment();
            return Try.failure(new IOException("checked"));
        }

        @Transactional(rollbackFor = IOException.class)
        public Try<String> tryCheckedExplicit() {
            increment();
            return Try.failure(new IOException("checked with rule"));
        }

        @Transactional(noRollbackFor = IllegalStateException.class)
        public Try<String> tryRuntimeNoRollback() {
            increment();
            return Try.failure(new IllegalStateException("no rollback rule"));
        }

        @Transactional
        public CompletableFuture<String> futureImmediateRuntimeFailure() {
            increment();
            return CompletableFuture.failedFuture(
                    new IllegalStateException("future runtime"));
        }

        @Transactional
        public CompletableFuture<String> futureImmediateCheckedDefault() {
            increment();
            return CompletableFuture.failedFuture(
                    new IOException("future checked"));
        }

        @Transactional(rollbackFor = IOException.class)
        public CompletableFuture<String> futureImmediateCheckedExplicit() {
            increment();
            return CompletableFuture.failedFuture(
                    new IOException("future checked with rule"));
        }

        @Transactional
        public CompletableFuture<String> futureStillPending() {
            increment();
            return new CompletableFuture<>();
        }

        @Transactional
        public Try<String> trySuccess() {
            increment();
            return Try.success("ok");
        }
    }
}
~~~

**Why is this program sufficient to verify rollback conditions?**

1. `@EnableTransactionManagement(proxyTargetClass=true)` enables a transactional proxy for the `DemoService` class.
2. The caller retrieves **`DemoService` from `ApplicationContext`** instead of instantiating it with `new`; calls to public transactional methods go through the proxy.
3. `JdbcTransactionManager` and `JdbcTemplate` share the **same `DataSource`**.
4. Each method executes one UPDATE before returning its result, so `amount` increases only if the transaction commits.
5. Calls to `amount(...)` occur after the method returns through the proxy, meaning that call's local transaction has completed.
6. The pending `Future` is `completeExceptionally`-completed **outside the method and after the proxy returns**, making the timing comparison deterministic without relying on a scheduler.
7. The demo uses default rollback behavior for checked exceptions; methods wanting to alter policy declare `rollbackFor`/`noRollbackFor` directly on the method.

### 7.3. Run Command and Expected Output

In the **`return-value-rollback-demo`** directory, run:

~~~bash
mvn -q compile exec:java
~~~

**Expected stdout printed by the program itself** (library or Maven logs are excluded here):

~~~text
start=0
try runtime: failure=true, amount=0
try checked default: failure=true, amount=1
try checked rollbackFor: failure=true, amount=1
try runtime noRollbackFor: failure=true, amount=2
future runtime immediate: exceptional=true, amount=2
future checked default: exceptional=true, amount=3
future checked rollbackFor: exceptional=true, amount=3
future pending on return: done=false, amount=4
future failed later: exceptional=true, amount=4
try success: success=true, amount=5
~~~

Reading line by line:

- **Runtime `Try.Failure`** returns a failure result while SQL rolls back; `amount` stays 0.
- **Default checked `Try.Failure`** returns a failure result, yet the `IOException` cause is not in default rollback rules, so `amount` increments to 1.
- **Checked `Try` with `rollbackFor`** keeps `amount` at 1.
- **Runtime `Try` with `noRollbackFor`** returns `Failure` yet `amount` rises to 2 because the rule requests no rollback for that cause.
- **Already-done failed runtime `Future`** is detected by Spring 6.2 at the return boundary; `amount` stays 2.
- **Default already-done failed checked `Future`** is detected yet does not match rollback rules; `amount` rises to 3.
- **Failed checked `Future` with `rollbackFor`** rolls back; `amount` stays 3.
- **Pending `Future`** at method return time: interceptor sees no failure yet, transaction commits, `amount` becomes 4.
- Caller completes that future exceptionally after return: `Future` reports error yet `amount` stays 4, proving **there is no retroactive rollback**.
- **`Try.Success`** commits normally; `amount` becomes 5.

The stdout above is deterministic for the declared data/transactions in a sequential run. If a project adds custom beans/aspects, changes the global rollback policy, or swaps managers, outcomes may differ and must be explained against the real configuration.

## 8. Verifying with Logs and Transaction Status

When troubleshooting an application, logs help corroborate when the interceptor decides rollback. In Spring Boot, try:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
logging.level.org.springframework.jdbc.support=DEBUG
~~~

Clues you may see:

~~~text
Getting transaction for [demo.DemoService.futureImmediateRuntimeFailure]
Creating new transaction ...
Completing transaction for [demo.DemoService.futureImmediateRuntimeFailure]
Initiating transaction rollback
Rolling back JDBC transaction on Connection [...]
Releasing JDBC Connection [...] after transaction
~~~

Exact wording and loggers vary by implementation/version. With **`Try.Failure`/failed `Future` returns**, the method can finish **without throwing an exception directly**, yet the manager still sees the transaction as rollback-only before completion.

If the pending `Future` case logs **`Initiating transaction commit`** and then an external callback logs an error later, that matches the timeline described above. Never use callback logs as evidence that Spring rolled back the earlier transaction.

You can also inspect inside a snippet:

~~~java
// Use only inside a @Transactional method currently managed by the interceptor.
boolean active =
        org.springframework.transaction.support.TransactionSynchronizationManager
                .isActualTransactionActive();
System.out.println("transaction active=" + active);
~~~

**`active=true`** only proves there is an active transaction context; it does not confirm whether the method will commit or roll back. Reading committed data from an independent connection/transaction remains stronger proof.

## 9. Situations That Must Not Be Assumed to Auto-Roll Back

### 9.1. `Future` Failing After a Long-Running Operation

~~~java
// Conceptual illustration: work inside the supplier may run after the method returns.
@Transactional
public CompletableFuture<String> scheduleWork() {
    return CompletableFuture.supplyAsync(() -> {
        // Task runs on another worker.
        return externalOperation();
    });
}
~~~

This snippet is not a standalone runnable program. The transaction bound to the current method call can end before the supplier runs; JDBC code inside the supplier will not automatically reuse an already closed transaction. Move the transaction boundary onto the bean/task that actually executes SQL.

### 9.2. `Try.Success` Containing an Async Failure Inside

~~~java
Try<CompletableFuture<String>> result =
        Try.success(new CompletableFuture<>());
~~~

Here `Try` is **`Success`**, so Spring does not mark rollback based on Vavr `Failure`. The inner `Future` is not processed by direct return-type `Future` detection; you must design transactions explicitly for the async work.

### 9.3. Custom `Result`/`Either`/`Optional`/`ResponseEntity`

Support for Vavr `Try` and `Future` here **does not mean** any object with `isFailure()`, `isError()`, or HTTP status 500 makes Spring roll back automatically. For example, a service returning **`Either.Left(error)`** or **`ResponseEntity.status(500)`** without throwing an exception or marking rollback-only can still commit. When using custom result types, convert failures to exceptions at the right boundary or use explicit transaction APIs.

### 9.4. Swallowing an Exception and Returning a Succeeded `Future`

~~~java
// Illustrative snippet: if no other rollback-only flag exists, Spring may commit.
@Transactional
public CompletableFuture<String> silentlyRecover() {
    try {
        repository.write();
        repository.operationThatFails();
    } catch (RuntimeException ex) {
        return CompletableFuture.completedFuture("recovered");
    }
    return CompletableFuture.completedFuture("ok");
}
~~~

If the exception is caught, Spring sees no escaping error. The returned `Future` completed **normally**, so there is no `Future` exceptional failure to mark rollback. On the other hand, if an inner repository transaction scope already marked the physical transaction rollback-only, outer may still roll back or receive `UnexpectedRollbackException`; never claim it always commits.

### 9.5. `Future` Succeeds at Method Return, Error Happens Elsewhere Later

You cannot conclude a transaction “must roll back” simply because a downstream consumer, webhook, or UI later fails. A local transaction has a boundary that already ended. To coordinate DB and messages/events, use transactional outbox, idempotency, compensation, or proper workflows rather than expecting `Future` exceptional completion to undo an old commit.

### 9.6. Missing Proxy or Appropriate Manager

`@Transactional` by itself is just metadata. Calling `this.method()` within the same object in Spring proxy mode can bypass transaction advice. Creating objects via `new` outside the Spring context behaves similarly. `Future`/`Try` handling requires **actual transactional interception**; verify the bean is called via its Spring proxy with the right transaction manager and `DataSource`.

## 10. Distinguishing from Reactive Transactions

With **`ReactiveTransactionManager`** (e.g., R2DBC), Spring handles `Mono`/`Flux` based on **reactive subscription and Reactor Context**. Work can start after the reactive method has returned a `Publisher` while the transaction still properly wraps publisher subscription.

This differs from **`PlatformTransactionManager` imperative JDBC** covered in this lesson. Do not take “a `Future` failing after method return does not roll back” and deduce a similar rule for `Mono.error` or `Flux` errors. Nor assume blocking JDBC code running inside a reactive chain participates in an R2DBC transaction.

If an application uses `@Transactional` with reactive return types and `ReactiveTransactionManager`, consult the corresponding reactive transaction documentation. If it uses blocking JDBC and returns `Future`, understand precisely when and on which thread the JDBC transaction opens.

## 11. Diagnostic Table for Error-Prone Cases

| Symptom | Possible cause | What to verify |
| --- | --- | --- |
| `Try.Failure(RuntimeException)` still commits | Spring prior to 5.2, bypassed proxy, `noRollbackFor`, wrong manager, another transaction committed | Spring version, rollback rules, bean/proxy, `DataSource` |
| `Try.Failure(IOException)` commits | Checked cause did not match default rollback rule | `rollbackFor`, `ALL_EXCEPTIONS`, and other policies |
| `CompletableFuture.failedFuture(RuntimeException)` still commits | Spring prior to 6.1, `Future` was not the direct intercepted return value, wrong proxy/manager | Version, actual return type, interceptor trace |
| `Future` fails seconds later yet DB does not roll back | `Future` was pending at return; transaction already committed | Timeline of return vs. `completeExceptionally`; DB readback |
| Already-done failed `Future` yet DB still persisted | Checked cause, `noRollbackFor`, different outer context, or transaction manager not covering SQL | Actual cause and rollback rule, resource mapping |
| `Future.isCompletedExceptionally()` is true in caller yet data committed | `Future` may have completed *after* return; caller saw later state | Timestamp right at the transactional boundary |
| `@Async` method running SQL does not join caller transaction | Imperative context is thread-bound; `@Async` switches execution thread | Advisor/proxy, thread, manager inside worker |
| `@Transactional` returns `Either.Left` yet DB still commits | Not Vavr `Try.Failure`; no exception/rollback-only | Return type and supported rollback mechanisms |
| Rollback occurs yet caller still receives `Try.Failure`/failed `Future` | Spring can preserve the return value and still roll back | DB data after transaction and handle state |
| `UnexpectedRollbackException` at outer | Inner `REQUIRED` marked rollback-only | Logical scopes, rollback-only, and transaction owner |

An effective debugging workflow:

1. **Identify the actual Spring Framework version** on the application runtime.
2. **Confirm the method is intercepted**; rule out self-invocation, `@Async` thread hops, and non-Spring beans.
3. **Identify the real return type**: directly thrown `Throwable`, Vavr `Try`, `Future`, nested `Future`, or custom result.
4. **Identify the timing** when the result became `Failure`/exceptionally completed: before or after the transactional method returned.
5. **Check the `Throwable` cause and rollback rules**: runtime, checked, `rollbackFor`/`noRollbackFor`, `ALL_EXCEPTIONS`.
6. **Identify transaction ownership and resources**, especially when `REQUIRED` propagation joined an outer transaction.
7. **Read back data from an independent transaction/connection** after completion to confirm commit or rollback.
8. **Inspect logs/metrics** if questions remain about SQL, connection pool, async threads, or commit failure.

## 12. Self-Check Questions

**Question 1.** A `@Transactional` method in Spring 6.2 returns `Try.failure(new IllegalStateException(...))` after an UPDATE. Does it need to throw the exception outward to roll back?  
**Answer:** No, if Vavr `Try.Failure` is the direct value observed by the interceptor and rollback rules match, Spring marks rollback-only while inspecting the return value.

**Question 2.** Is `Try.Failure(new IOException(...))` guaranteed to roll back by default?  
**Answer:** No. Under unchecked-only defaults, `IOException` is checked and can commit. Add `rollbackFor=IOException.class` or configure `ALL_EXCEPTIONS` in Spring 6.2 if appropriate.

**Question 3.** Does Spring 6.0 automatically detect `CompletableFuture.failedFuture(...)` to roll back under the new mechanism?  
**Answer:** Do not rely on that; failed-return `Future`/`CompletableFuture` support is documented since Spring 6.1. Throw an appropriate exception or use explicit transaction APIs on older versions.

**Question 4.** A Spring 6.2 method returns a pending `new CompletableFuture<>()` and the caller calls `completeExceptionally` after the method returns. Does the earlier transaction automatically roll back?  
**Answer:** No. When the interceptor checked, the `Future` was not done, so there was no cause; the local transaction may have already committed. Completing the `Future` later does not reverse data.

**Question 5.** Why might `isCompletedExceptionally=true` appear on the `Future` in the caller while the DB still committed?  
**Answer:** The caller may inspect the `Future` after it finished, whereas at the original return moment it was still pending. Additionally, the cause might not match rollback rules or another transaction committed.

**Question 6.** A `Future` already failed with `IOException` at return time on a `@Transactional(rollbackFor=IOException.class)` method. What happens in Spring 6.2?  
**Answer:** Spring retrieves the `IOException` cause because the `Future` is done and can mark rollback-only, rolling back the transaction when the manager completes.

**Question 7.** Does `@Async` automatically propagate the caller thread's JDBC transaction to every worker?  
**Answer:** No. You must open a transaction at the boundary running SQL inside the worker using the appropriate manager/resource. `@Async` and `@Transactional` must be applied with proper proxy/advisor and runtime context.

**Question 8.** Is `Mono.error(...)` equivalent to `CompletableFuture.failedFuture(...)` in the logic above?  
**Answer:** Do not extrapolate. `Mono`/`Flux` use reactive transactions with `ReactiveTransactionManager` and subscription context; the `Future`-at-return rule belongs to imperative transactions.

## 13. Practical Takeaways

- **Vavr `Try.Failure`:** Spring supports detection since **5.2**; the cause must match rollback rules.
- **Failed `Future`/`CompletableFuture`:** Spring supports return-value inspection since **6.1**; the `Future` must **already be completed exceptionally at the moment the method returns** and the cause must match rules.
- **Pending `Future` that fails later:** does not retroactively roll back a completed local transaction.
- **Rollback rules always matter:** `RuntimeException`/`Error` differ from checked `Exception`; `rollbackFor`, `noRollbackFor`, and since Spring 6.2 `ALL_EXCEPTIONS` can configure behavior.
- **Infrastructure must actually run:** Spring proxy/interceptor, `TransactionManager`, and `DataSource` covering the right resources.
- **Verify via DB state after the transaction:** logs, `isFailure`/`isCompletedExceptionally`, and caller exceptions are supporting signals, not standalone proof that changes committed or rolled back.

## References

- [Spring Framework 6.2 — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html)
- [Spring Framework 6.2 — Using @Transactional and rollbackOn=ALL_EXCEPTIONS](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 — Transaction Management](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction.html)
- [Spring Framework 5.2 — Data Access: Vavr Try rollback support](https://docs.spring.io/spring-framework/docs/5.2.24.RELEASE/spring-framework-reference/data-access.html)
- [Spring Framework 6.2.12 — TransactionAspectSupport implementation](https://github.com/spring-projects/spring-framework/blob/v6.2.12/spring-tx/src/main/java/org/springframework/transaction/interceptor/TransactionAspectSupport.java)
- [Vavr — Try documentation](https://docs.vavr.io/#_try)
- [Java SE 17 — CompletableFuture API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/util/concurrent/CompletableFuture.html)
