# Exceptions Must Cross the Transaction Boundary for the Interceptor to Observe Them

## 1. Why Does Throwing an Error Not Always Trigger Transaction Rollback?

In Spring Framework, `@Transactional` typically operates via an **AOP proxy**. A caller invokes a Spring bean through the proxy; `TransactionInterceptor` starts or joins a transaction, executes the target method, and observes the **outcome exiting the call**. When the method finishes normally, the interceptor usually requests commit. When an error matching the **rollback rules** exits the method, the interceptor requests rollback or marks the transaction rollback-only.

Therefore, two nearly identical pieces of code can produce different outcomes:

```java
@Transactional
public void silentlyContinue() {
    debit(100);
    try {
        creditMissingAccount(100);
    } catch (IllegalStateException ex) {
        log.warn("Credit failed", ex);
    }
    // Method returns normally: interceptor does not see this error escaping.
}
```

```java
@Transactional
public void failAndRollback() {
    debit(100);
    creditMissingAccount(100);
    // If creditMissingAccount throws a RuntimeException, the error exits through the proxy.
}
```

Both are illustrative snippets; the full application in section 5 defines the actual methods. Assuming both SQL statements participate in the same transaction and the error is thrown by **application logic** after checking affected rows, the first version can **commit the debit**, whereas the second version can **roll back everything**.

Here is the central point:

> An exception created **inside** a method does not automatically become a rollback signal for `TransactionInterceptor`. The interceptor normally applies rollback rules only to exceptions exiting **across the transactional advice boundary** (or receiving an explicit framework-supported signal). If the exception was caught and the method returns normally, the advice cannot infer that the business operation failed.

Still, “an error escapes” is a **necessary condition, not a sufficient one**: the exception type must also match rollback rules; and the transaction may already be marked rollback-only or the DB may have rejected the transaction on its own. This lesson separates those cases step by step.

## 2. Identifying the Exact Position of the Transaction Boundary

Suppose `OrderController` calls `PaymentService.pay()` on a Spring bean:

```text
Controller
  |
  | service.pay()
  v
Spring proxy / TransactionInterceptor
  |
  | begin or join transaction
  v
PaymentService.pay()  [@Transactional method body]
  |
  +-- debit() succeeds
  +-- credit() fails -> throw IllegalStateException
  |
  +-- Option A: catch right here and return
  |       |
  |       v
  |   Interceptor sees "normal return" -> commits if possible
  |
  +-- Option B: exception continues out of the method
          |
          v
      Interceptor receives exception -> checks rollback rules
          |
          +-- Rule requests rollback -> rollback/rollback-only
          +-- Rule does not request rollback -> may commit
          |
          v
      Exception is thrown onward to Controller
```

**Where you catch matters more than whether you catch.** If the Controller catches the exception **after the `service.pay()` call has exited the Spring proxy**, the interceptor already had the chance to process rollback before the Controller converts the error into an HTTP response. Conversely, catching and swallowing the exception **inside the transactional method body** can leave the interceptor seeing only normal completion.

```java
// At the caller layer (illustrative snippet only):
try {
    paymentService.pay(request);
    return successResponse();
} catch (InsufficientBalanceException ex) {
    return rejectedResponse(ex.getMessage());
}
```

If `paymentService` is a proxied bean, the error already passed through the interceptor before reaching the caller's `catch`. The caller is completely free to translate the exception into an API response; **you do not need to let the error crash all the way to the end user** for the transaction to roll back. What matters is that the error reaches the proper transactional boundary before being handled at a higher layer.

### “Boundary” Is Not Necessarily the End of an HTTP Request

A single request may call multiple services. A transaction does not automatically span the entire request if the annotation sits on just one method. If the service already committed successfully and then the controller does something else and throws an error, that exception happens **after the transaction**, and does not undo the completed commit. Identify the **unit of business work that must commit or roll back together**, place the transaction boundary around all of that work, and avoid leaving critical failing steps outside the boundary.

## 3. Default Rules: Which Exception Types Does the Interceptor Watch?

Under the common default `@Transactional` configuration in Spring Framework 6.1/6.2:

| Outcome exiting the method | Default result when the method owns a new transaction |
| --- | --- |
| Method returns normally | Requests commit, unless the transaction is already rollback-only or commit fails |
| `RuntimeException` or subclass escapes | Requests rollback |
| `Error` escapes | Requests rollback under default rules |
| Checked exception (`IOException`, non-`RuntimeException` `Exception`) escapes | **Does not request rollback by default**; the transaction may commit while the exception is still rethrown |
| Exception caught and swallowed inside method | Interceptor usually sees only a normal return; may commit |
| Transaction already marked rollback-only | Will not commit even if method returns normally; error reporting depends on transaction scope |
| Exception occurs outside the boundary after commit | Cannot automatically roll back an already committed transaction |

A checked exception example that often surprises developers:

```java
@Transactional
public void saveAndCheck() throws java.io.IOException {
    writeToDatabase();                   // UPDATE already succeeded
    throw new java.io.IOException("External validation unavailable");
}
```

The method throws an error through the interceptor, yet **`IOException` is not in the default rollback rules**. On a database with no other errors and a committable transaction, Spring may still commit the UPDATE and then propagate `IOException` to the caller.

If business rules require rollback in this case, declare it explicitly:

```java
@Transactional(rollbackFor = java.io.IOException.class)
public void saveAndCheck() throws java.io.IOException {
    writeToDatabase();
    throw new java.io.IOException("External validation unavailable");
}
```

You can use `rollbackFor = Exception.class` when **all checked exceptions** must roll back, though broader rules require clearer understanding. `@Transactional(noRollbackFor = SomeBusinessException.class)` can intentionally allow commit even when `SomeBusinessException` escapes. When multiple rules match, Spring prioritizes the strongest matching rule.

**Version note:** Spring Framework 6.2 includes an option to configure default rollback for **all exceptions** at `@EnableTransactionManagement(rollbackOn = RollbackOn.ALL_EXCEPTIONS)`. Therefore, do not apply the default table above blindly to an application with altered global settings. This lesson's demo uses Spring Boot 3.3.x (typically paired with Spring Framework 6.1.x) and explicit rules, keeping the default checked-exception distinction clear.

## 4. Three Catch Patterns and Their Consequences

### 4.1. Catch Inside, Log, and Return Normally

```java
@Transactional
public void wrongTransfer() {
    decreaseSourceBalance();
    try {
        increaseDestinationBalance();
    } catch (IllegalStateException ex) {
        log.warn("Could not credit destination", ex);
    }
}
```

Call flow:

1. The interceptor starts a transaction.
2. `decreaseSourceBalance` updates one or more rows in the DB.
3. `increaseDestinationBalance` raises an application error.
4. `catch` swallows the error; the method still returns normally.
5. The interceptor sees no exception corresponding to the business failure.
6. If the transaction was not marked rollback-only, Spring can commit the source debit.

Logging an error does not alter rollback state. `@Transactional` has no mechanism to read logs and deduce that a business operation failed. Choose error handling consistent with the method's contract.

### 4.2. Catch to Add Context and Rethrow

```java
@Transactional
public void transfer() {
    decreaseSourceBalance();
    try {
        increaseDestinationBalance();
    } catch (IllegalStateException ex) {
        throw new TransferFailedException(
            "Failed while crediting destination", ex
        );
    }
}
```

With `TransferFailedException extends RuntimeException` and default `@Transactional`, the new exception **escapes** the method, so the interceptor sees the error and handles rollback. When wrapping exceptions, preserve the **cause** to aid diagnostics. Avoid wrapping into a checked exception while forgetting `rollbackFor`, as that can accidentally flip rollback behavior.

**Point about checked/wrapped exceptions:** the interceptor evaluates the **actual exception it receives** against the method's rollback rules. `new RuntimeException(cause)` and `new IOException(cause)` can yield different rollback outcomes without additional rules.

### 4.3. Catch in the Caller After the Proxy Boundary

```java
// Controller or orchestration service not in its own transaction:
public String submit() {
    try {
        transferService.transfer();
        return "OK";
    } catch (TransferFailedException ex) {
        return "REJECTED";
    }
}
```

If `transferService.transfer()` is called through the Spring proxy, rollback has already been decided/processed when the exception exits that method; the caller can return `"REJECTED"` without undoing the rollback. If the caller is **also inside an enclosing outer transaction**, review propagation and rollback-only in section 7.

## 5. Runnable Demo with Java 17+, Spring Boot, and H2

The demo deliberately sets up wallet ID 1 with 1,000 points and wallet ID 2 with 500 points. A debit operation subtracts 100 points from wallet 1, then attempts to credit ID 999 (non-existent). The **credit failure is detected by checking 0 updated rows and throwing `IllegalStateException`**, rather than via a DB SQL error. This matters: we want to verify **whether the exception passes through the interceptor**, without depending on how a DBMS flags a transaction after a SQL error.

Run the demo across independent cases, **resetting balances before each case**, and observe:

| Case | Signal observed by caller | Balances after transaction ends |
| --- | --- | --- |
| Error swallowed inside | Normal return | 1=900, 2=500 (**partial business commit**) |
| `RuntimeException` escapes through interceptor | `IllegalStateException` | 1=1000, 2=500 (**rollback**) |
| Checked `IOException` escapes, default | `IOException` | 1=900, 2=500 (**still commits**) |
| Checked `IOException` with `rollbackFor` | `IOException` | 1=1000, 2=500 (**rollback**) |
| Catch error and `setRollbackOnly()` | Method returns `false` | 1=1000, 2=500 (**intentional rollback**) |
| Inner `REQUIRED` service throws, outer catches | `UnexpectedRollbackException` on outer commit | 1=1000, 2=500 (**rollback**) |

The program consists of five Java files in package `example.rollback`, alongside three Gradle/config/schema files.

### 5.1. `settings.gradle`

```groovy
rootProject.name = 'transaction-exception-boundary'
```

### 5.2. `build.gradle`

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

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

Use the Gradle wrapper generated by Spring Initializr for a Java 17/Spring Boot 3.3.5 project, or a compatible Gradle installation. Run in a terminal via `./gradlew bootRun` on Unix/macOS or `.\gradlew.bat bootRun` on PowerShell. The demo requires no web server.

### 5.3. `src/main/resources/application.yml`

```yaml
spring:
  main:
    web-application-type: none
  datasource:
    url: "jdbc:h2:mem:rollback_demo;DB_CLOSE_DELAY=-1"
    username: sa
    password: ""
  sql:
    init:
      mode: always
```

Because the application uses `spring-boot-starter-jdbc`, Spring Boot auto-configures `DataSource`, `JdbcTemplate`, and the JDBC transaction manager when conditions are met. `spring.sql.init.mode=always` runs the schema at startup. This in-memory H2 database is for testing, not a substitute for a durable production DB setup.

### 5.4. `src/main/resources/schema.sql`

```sql
CREATE TABLE wallets (
    id BIGINT PRIMARY KEY,
    balance BIGINT NOT NULL CHECK (balance >= 0)
);

INSERT INTO wallets (id, balance) VALUES (1, 1000);
INSERT INTO wallets (id, balance) VALUES (2, 500);
```

### 5.5. `src/main/java/example/rollback/WalletService.java`

```java
package example.rollback;

import java.io.IOException;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class WalletService {
    private final JdbcTemplate jdbc;

    public WalletService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    private void debit() {
        int rows = jdbc.update(
            "UPDATE wallets SET balance = balance - 100 " +
            "WHERE id = 1 AND balance >= 100"
        );
        if (rows != 1) {
            throw new IllegalStateException("Insufficient source balance");
        }
    }

    private void creditMissingWallet() {
        int rows = jdbc.update(
            "UPDATE wallets SET balance = balance + 100 WHERE id = 999"
        );
        if (rows != 1) {
            throw new IllegalStateException("Destination missing");
        }
    }

    @Transactional
    public void swallowedInside() {
        debit();
        try {
            creditMissingWallet();
        } catch (IllegalStateException ignored) {
            // Error was swallowed inside the method; interceptor sees a normal return.
        }
    }

    @Transactional
    public void escapedOutside() {
        debit();
        creditMissingWallet();
        // RuntimeException exits the method and is observed by the interceptor.
    }

    @Transactional
    public void checkedDefault() throws IOException {
        debit();
        throw new IOException("External validation failed");
    }

    @Transactional(rollbackFor = IOException.class)
    public void checkedWithRollbackRule() throws IOException {
        debit();
        throw new IOException("External validation failed");
    }

    @Transactional
    public boolean markRollbackOnlyAfterCatch() {
        debit();
        try {
            creditMissingWallet();
            return true;
        } catch (IllegalStateException ex) {
            TransactionAspectSupport.currentTransactionStatus()
                .setRollbackOnly();
            return false;
        }
    }
}
```

**How to read the code properly:**

- `debit()` and `creditMissingWallet()` are **private helpers** running inside the same `WalletService` call wrapped by a transaction. They do not open their own transactions and need no extra annotation.
- `swallowedInside()` can commit `debit()`'s change, because the exception from `creditMissingWallet()` **does not escape outward**.
- `escapedOutside()` lets the unchecked exception proceed to the interceptor: Spring rolls back by default.
- `checkedDefault()` throws **checked `IOException`**. It escapes to the caller, yet under Spring Boot 3.3.x defaults it still does not trigger rollback, so the debit can commit.
- `checkedWithRollbackRule()` differs only in the `rollbackFor = IOException.class` metadata, telling the interceptor to roll back.
- `markRollbackOnlyAfterCatch()` shows an option when internal handling is mandatory: explicitly setting the transaction rollback-only. It returns `false` so the caller knows the operation **failed**, even without rethrowing. This solution couples directly to Spring's transaction API; prefer letting errors reach the interceptor when design allows.

Note: do not put `@Transactional` directly on private `debit()` and expect the proxy to intercept `this.debit()`. Here the transaction starts at the **public method entrypoint** called through a Spring bean, and helpers execute within the opened transaction.

### 5.6. `src/main/java/example/rollback/InnerService.java`

```java
package example.rollback;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void debitThenFail() {
        int rows = jdbc.update(
            "UPDATE wallets SET balance = balance - 100 " +
            "WHERE id = 1 AND balance >= 100"
        );
        if (rows != 1) {
            throw new IllegalStateException("Insufficient source balance");
        }
        throw new IllegalStateException("Inner failure");
    }
}
```

### 5.7. `src/main/java/example/rollback/OuterService.java`

```java
package example.rollback;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OuterService {
    private final InnerService inner;

    public OuterService(InnerService inner) {
        this.inner = inner;
    }

    @Transactional
    public void catchesInner() {
        try {
            inner.debitThenFail();
        } catch (IllegalStateException ignored) {
            // Only swallows the exception; cannot clear the transaction's rollback-only flag.
        }
    }
}
```

The two services are separate beans so the `outer -> inner` call **passes through `InnerService`'s proxy**. Both use default `Propagation.REQUIRED`, so they participate in the **same physical transaction** when the call starts from outside.

Unlike `WalletService.swallowedInside()`, the exception from `InnerService.debitThenFail()` **already passed through the inner service's transaction interceptor**. The inner interceptor marks the shared transaction rollback-only. Catching the exception outside the inner proxy does not reverse that decision.

When `OuterService.catchesInner()` finishes normally and the outer proxy tries to commit, the physical transaction is already rollback-only. Because the caller did not intentionally request rollback at the outer scope, Spring throws `UnexpectedRollbackException` so the caller is not misled into believing the commit succeeded. Section 7 explains this in detail.

### 5.8. `src/main/java/example/rollback/RollbackDemoApplication.java`

```java
package example.rollback;

import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.jdbc.core.JdbcTemplate;

@SpringBootApplication
public class RollbackDemoApplication {

    @FunctionalInterface
    interface ThrowingJob {
        void run() throws Exception;
    }

    public static void main(String[] args) {
        SpringApplication.run(RollbackDemoApplication.class, args);
    }

    private static void reset(JdbcTemplate jdbc) {
        jdbc.update("UPDATE wallets SET balance = 1000 WHERE id = 1");
        jdbc.update("UPDATE wallets SET balance = 500 WHERE id = 2");
    }

    private static String balances(JdbcTemplate jdbc) {
        return String.join(", ", jdbc.query(
            "SELECT id, balance FROM wallets ORDER BY id",
            (rs, rowNum) ->
                rs.getLong("id") + "=" + rs.getLong("balance")
        ));
    }

    private static void scenario(
            String label, JdbcTemplate jdbc, ThrowingJob job) {
        reset(jdbc);
        String signal = "completed";

        try {
            job.run();
        } catch (Exception ex) {
            signal = ex.getClass().getSimpleName();
        }

        System.out.println(
            label + " | signal=" + signal + " | " + balances(jdbc)
        );
    }

    @Bean
    ApplicationRunner demo(
            WalletService wallets,
            OuterService outer,
            JdbcTemplate jdbc) {
        return args -> {
            scenario("Caught inside", jdbc, wallets::swallowedInside);
            scenario("Escaped", jdbc, wallets::escapedOutside);
            scenario("Checked default", jdbc, wallets::checkedDefault);
            scenario("Checked rule", jdbc, wallets::checkedWithRollbackRule);

            reset(jdbc);
            boolean result = wallets.markRollbackOnlyAfterCatch();
            System.out.println(
                "Manual rollback | result=" + result +
                " | " + balances(jdbc)
            );

            scenario(
                "Inner REQUIRED caught by outer",
                jdbc,
                outer::catchesInner
            );
        };
    }
}
```

This is a **complete runnable application in a Gradle/Spring Boot project with the files above**. `ApplicationRunner` invokes `WalletService`/`OuterService` injected via the Spring container, so calls pass through proxies. The `JdbcTemplate` updates inside `reset()` execute **outside** the service transactions and restore the fixture to its initial state.

### 5.9. Running and Expected Output

```bash
./gradlew bootRun
```

On Windows:

```powershell
.\gradlew.bat bootRun
```

Ignoring Spring/Gradle startup logs, the lines printed by the application itself are expected to be:

```text
Caught inside | signal=completed | 1=900, 2=500
Escaped | signal=IllegalStateException | 1=1000, 2=500
Checked default | signal=IOException | 1=900, 2=500
Checked rule | signal=IOException | 1=1000, 2=500
Manual rollback | result=false | 1=1000, 2=500
Inner REQUIRED caught by outer | signal=UnexpectedRollbackException | 1=1000, 2=500
```

Each case is reset independently, so debits do not accumulate across cases. These are **results deduced from the presented code flow and configuration**, not a claim of having executed this exact project. When switching to another DBMS, preserve the same business invariants and test against the actual database/transaction manager in use.

### 5.10. Meaning of Each Case

**Caught inside:** `debit()` changes source wallet from 1,000 to 900. `creditMissingWallet()` cannot find wallet 999; the method catches the error and returns normally. The interceptor sees no escaping unchecked exception and commits. This is typically a business bug needing a fix.

**Escaped:** the same SQL statements run, yet `IllegalStateException` is not swallowed. The interceptor sees the unchecked exception and rolls back. Only afterward does `ApplicationRunner` catch the error to print `IllegalStateException`. This is the clearest illustration of the “exception must cross the boundary” rule.

**Checked default:** `IOException` escapes, yet default rollback rules do not mark rollback for checked exceptions. Spring can commit the debit while the caller still receives `IOException`.

**Checked rule:** same `IOException`, with `rollbackFor` added, so the interceptor rolls back as requested.

**Manual rollback:** the method caught the exception yet called `setRollbackOnly()`, returning `false` to indicate the business operation failed. In the demo case where the method **owns a new transaction**, Spring rolls back when the method finishes instead of committing.

**Inner REQUIRED:** the inner interceptor observes the unchecked exception and marks the shared transaction rollback-only. The outer method catches the error yet cannot turn the shared transaction back into “committable”. `UnexpectedRollbackException` is thrown at the outer boundary upon attempting commit.

## 6. Redesigning try/catch So the Interceptor Knows About Failure

In practice, catching errors has real value: adding context, mapping business error codes, cleaning up non-DB resources, or emitting logs. The key issue is **where you catch and whether the failure signal is preserved**.

### 6.1. Rethrow the Same Exception

```java
@Transactional
public Receipt finalizePayment(long paymentId) {
    try {
        return savePaymentAndLedger(paymentId);
    } catch (RuntimeException ex) {
        log.error("Payment {} failed", paymentId, ex);
        throw ex;
    }
}
```

`throw ex` preserves both the exception type and stack trace, so default rules for unchecked exceptions still apply. This illustrative example requires application `Receipt`, repository, and logger dependencies; it is not a standalone file.

### 6.2. Throw a New Domain Exception

```java
public final class PaymentRejectedException extends RuntimeException {
    public PaymentRejectedException(String message, Throwable cause) {
        super(message, cause);
    }
}

@Transactional
public void settlePayment(long paymentId) {
    try {
        performSettlement(paymentId);
    } catch (IllegalStateException ex) {
        throw new PaymentRejectedException("Settlement failed", ex);
    }
}
```

This is valid design if callers need a specific domain error and `PaymentRejectedException` is **unchecked**. Preserve the cause rather than creating `new RuntimeException("failed")` and discarding root details. The class and method are illustrative snippets; in a real project, place the class in its proper file.

### 6.3. What If You Want to Recover and Continue?

Not every caught exception must abort the transaction. Some workflows allow fallback—for instance, a **non-essential** lookup fails while all invariants still hold. Catching and continuing can then be right, **provided you intentionally accept committing what succeeded** and confirm the DB state remains valid.

However, for multi-step **all-or-nothing** work, catching an error after an intermediate step and returning success is dangerous. Such cases should:

- let an appropriate exception exit through the interceptor;
- use `rollbackFor` for critical checked exceptions;
- explicitly call `setRollbackOnly()` and return a clear failure `Result` if handled locally;
- or design separate smaller transactions, savepoints, or compensating workflows if partial recovery is genuinely needed.

You cannot both demand “all steps succeed together” and silently commit after a mandatory step fails.

## 7. Exceptions Crossing an Inner Service Boundary: Why Outer Catch Still Rolls Back

A common mistake is assuming:

> “I caught the exception in the outer service, so Spring must commit the outer transaction.”

That reasoning misses one step: **did the exception already pass through the inner service's interceptor?**

With `Propagation.REQUIRED`:

```text
Caller
  |
  v
Outer proxy: creates physical transaction T
  |
  v
OuterService.catchesInner()
  |
  v
Inner proxy: joins T, creates inner logical transaction scope
  |
  v
InnerService.debitThenFail()
  |
  +-- UPDATE source wallet
  +-- throw IllegalStateException
  |
  v
Inner interceptor sees error
  |
  +-- marks T rollback-only
  +-- rethrows exception
  |
  v
OuterService catches exception and returns normally
  |
  v
Outer interceptor tries to commit T
  |
  +-- T is already rollback-only -> rolls back
  +-- reports UnexpectedRollbackException
```

Two logical `@Transactional` scopes can share **the same physical transaction**. `REQUIRED` joins the caller's transaction if one exists. Hence, there is no “private commit” for the inner method. The rollback-only flag set by the inner advice affects the final outcome at the outer scope.

`UnexpectedRollbackException` serves as a safety guard: a caller promised that the method completed must not silently believe it **committed** when the physical transaction was actually rolled back by an inner scope.

### Contrast with `REQUIRES_NEW` and `NESTED`

| Inner method propagation | What can happen when inner fails | Things to note |
| --- | --- | --- |
| `REQUIRED` | Inner and outer share one physical transaction; inner rollback-only can cause outer commit to fail with `UnexpectedRollbackException` | Shown in section 5 demo |
| `REQUIRES_NEW` | Inner runs in an independent physical transaction; inner rollback does not necessarily roll back outer | May need a separate connection; does not guarantee joint atomicity |
| `NESTED` | With a manager/driver supporting savepoints, inner can roll back to a savepoint and outer continues | Do not assume universal support across all DBs/JPA/managers |

Do not switch to `REQUIRES_NEW` merely to avoid `UnexpectedRollbackException` if data from both operations **must** commit/roll back together. The proper fix is usually letting the failure exit the **outer transactional boundary**, or designing explicit recovery matching invariants.

### Catching in the Controller vs. Catching in an Outer Transaction

In the demo, `ApplicationRunner` calls `outer.catchesInner()` and catches `UnexpectedRollbackException` **after the outer proxy already finalized the rollback decision**. Catching there does not make the transaction commit again. Likewise, an HTTP controller can map the error to status 409/422/500 after the transaction has ended.

## 8. Using and Understanding `rollbackOnly` Properly

A transactional method can explicitly request rollback without throwing an exception:

```java
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Transactional
public OperationResult tryProcess() {
    try {
        performOperation();
        return OperationResult.success();
    } catch (KnownBusinessException ex) {
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        return OperationResult.failure(ex.getMessage());
    }
}
```

This snippet assumes application types `OperationResult`, `KnownBusinessException`, and `performOperation()`; the method cannot compile standalone with `javac`.

If the method owns a new transaction and sets **local rollback-only**, the interceptor rolls back upon exit. When a participating transaction or inner scope sets **global rollback-only** on a shared physical transaction, the outer scope may receive `UnexpectedRollbackException` when attempting to commit. Do not expect a “clearRollbackOnly()” API to restore the transaction. If the DB already considers the transaction broken, do not keep using it as if nothing happened.

`TransactionAspectSupport.currentTransactionStatus()` is only valid inside a call managed by Spring's transaction advice; calling it outside a transactional scope may find no active status. It also couples the service directly to Spring's transaction API, so prefer declarative mechanisms when possible.

Another programmatic option is `TransactionTemplate`:

```java
TransactionTemplate template = new TransactionTemplate(transactionManager);

OperationResult result = template.execute(status -> {
    try {
        performOperation();
        return OperationResult.success();
    } catch (KnownBusinessException ex) {
        status.setRollbackOnly();
        return OperationResult.failure(ex.getMessage());
    }
});
```

This snippet merely illustrates the API inside a class that already has `transactionManager` and business types; it is not a standalone program. Both approaches must **return a transparent failure status** to the caller. Never set rollback-only and then return a misleading “success” object to upper layers.

## 9. Database Errors Can Prevent Commit Even When Exceptions Are Caught

Do not interpret the opening rule as:

> “Catching any exception inside a transaction guarantees the DB will commit.”

That conclusion is wrong. The caught exception may come from the **DBMS**, not only from application checks.

For instance, on PostgreSQL, many SQL statement errors (constraint violations, syntax errors inside a transaction, etc.) put the current transaction into an **aborted** state; subsequent statements are rejected until `ROLLBACK` or proper savepoint handling. Spring or the transaction manager may also mark the transaction rollback-only. Simply swallowing the exception in Java does not heal the transaction.

Distinguish carefully:

1. **Application-level exception after valid SQL:** e.g., `UPDATE ... WHERE id = 999` updates **0 rows**, and JDBC reports no error. The service throws `IllegalStateException`; if swallowed and not rollback-only, the DB can still commit earlier statements. The demo uses this category.
2. **Database-level SQL error:** e.g., a duplicate key causes the DBMS to reject the statement. Post-error transaction state depends on the DBMS, driver, savepoints, and manager. Catching in Java is **not** proof of committability.
3. **An inner transactional interceptor already saw the exception:** it may have marked the transaction rollback-only even if the outer service catches the error afterward.
4. **Prior transaction timeout/rollback-only:** the method may return normally, yet commit still fails or converts into rollback.

Therefore, when debugging, verify **where the error originated**, **which interceptors it passed through**, **transaction status**, and **DBMS behavior**—not just the number of `catch` blocks in source code.

## 10. Scenarios Outside Synchronous Method Flow

### 10.1. Self-Invocation: Exceptions May Never Pass Through the Needed Proxy

```java
@Service
public class OrderService {
    public void createOrder() {
        saveOrder();
    }

    @Transactional
    public void saveOrder() {
        // Data operations; may throw an exception.
    }
}
```

This is an illustrative snippet. `createOrder()` calls `saveOrder()` via `this`, not via the Spring AOP proxy for `saveOrder`. Therefore, `@Transactional` on the internally called method **does not trigger a new interceptor**. Even if `saveOrder()` throws an unchecked exception, no transaction is created by that annotation if no other boundary exists.

Solution: place the transaction at the public entrypoint callers invoke through the proxy, or extract the transactional method into another Spring bean and call that bean. **Switching from JDK proxy to CGLIB does not solve self-invocation.**

If `createOrder()` is already covered by an outer transaction, SQL inside `saveOrder()` can still join the outer transaction; however, **custom rollback rules on `saveOrder()`** are not applied by that method's interceptor.

### 10.2. `@Async`, Other Threads, and Post-Commit Interactions

Imperative transactions are normally bound to a Spring-managed thread/transaction context. If a transactional method spawns an asynchronous task and returns immediately, an exception raised in the task **after the method has returned** generally cannot make the interceptor roll back an already completed transaction.

```java
@Transactional
public void launchTask(Executor executor) {
    saveToDatabase();
    executor.execute(() -> {
        throw new IllegalStateException("Late async failure");
    });
}
```

This example only illustrates the timing issue and does not guarantee the executor task shares the transaction. Avoid launching fire-and-forget tasks as mandatory steps inside an ACID business operation. If another task needs a transactional unit, it needs its own boundary/manager and cross-process/resource consistency strategy where required.

**Conditional exceptions:** Spring Framework 6.1+ includes special handling for `Future`/`CompletableFuture` instances **already completed exceptionally at the moment the method returns**, as well as documented Vavr `Try.Failure` support. These cases do **not** mean Spring tracks arbitrary future async failures and rolls back already committed transactions. For normal synchronous flows, the rule about exceptions exiting the method remains foundational.

### 10.3. Reactive Publishers: Let `onError` Signals Cross the Transaction Boundary

With `ReactiveTransactionManager`, execution timing is tied to subscribing to a `Mono`/`Flux`. Spring's transaction interceptor/operator observes terminal signals of the publisher. If you turn an error into completion before the transactional boundary, the transaction can commit:

```java
// Illustrative snippet: work is Mono<Void>, tx is TransactionalOperator.
Mono<Void> unsafe = work
    .onErrorResume(ex -> Mono.empty())
    .as(tx::transactional);
```

Here the transaction operator receives completion; it no longer sees `onError` from the business failure.

When you need to handle errors after rollback:

```java
Mono<Void> safer = work
    .as(tx::transactional)
    .onErrorResume(ex -> handleAfterRollback(ex));
```

This lets the transaction operator observe the error and process rollback before downstream fallback runs. `handleAfterRollback` is an application method that must accurately reflect the failed business outcome. Reactive stream cancellation also has its own rollback semantics; do not infer it from imperative try/catch behavior.

## 11. Testing Actual Rollback Instead of Only Checking Exceptions

A test that only runs `assertThrows(IllegalStateException.class, ...)` is **not enough**. It does not prove the DB rolled back; in a method throwing a checked exception without `rollbackFor`, the test still receives the exception while the DB may commit the change.

Verify both the caller signal and **the DB state after the method finishes**.

### 11.1. JUnit 5 Tests for Key Behaviors

File `src/test/java/example/rollback/RollbackDemoTest.java`:

```java
package example.rollback;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertThrows;

import java.io.IOException;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.UnexpectedRollbackException;

@SpringBootTest
class RollbackDemoTest {
    @Autowired WalletService wallets;
    @Autowired OuterService outer;
    @Autowired JdbcTemplate jdbc;

    @BeforeEach
    void reset() {
        jdbc.update("UPDATE wallets SET balance = 1000 WHERE id = 1");
        jdbc.update("UPDATE wallets SET balance = 500 WHERE id = 2");
    }

    private long balanceOf(long id) {
        Long value = jdbc.queryForObject(
            "SELECT balance FROM wallets WHERE id = ?",
            Long.class,
            id
        );
        return value;
    }

    @Test
    void catchingInsideCanCommitPartialBusinessOperation() {
        wallets.swallowedInside();
        assertEquals(900L, balanceOf(1L));
        assertEquals(500L, balanceOf(2L));
    }

    @Test
    void escapingRuntimeExceptionTriggersRollback() {
        assertThrows(IllegalStateException.class, wallets::escapedOutside);
        assertEquals(1000L, balanceOf(1L));
        assertEquals(500L, balanceOf(2L));
    }

    @Test
    void checkedExceptionDefaultCanCommit() {
        assertThrows(IOException.class, wallets::checkedDefault);
        assertEquals(900L, balanceOf(1L));
    }

    @Test
    void checkedExceptionWithRuleRollsBack() {
        assertThrows(IOException.class, wallets::checkedWithRollbackRule);
        assertEquals(1000L, balanceOf(1L));
    }

    @Test
    void manualRollbackOnlyReportsFailure() {
        assertFalse(wallets.markRollbackOnlyAfterCatch());
        assertEquals(1000L, balanceOf(1L));
    }

    @Test
    void innerRollbackOnlyCannotBeClearedByOuterCatch() {
        assertThrows(UnexpectedRollbackException.class, outer::catchesInner);
        assertEquals(1000L, balanceOf(1L));
    }
}
```

With the `spring-boot-starter-test` dependency in `build.gradle`, run:

```bash
./gradlew test
```

`@BeforeEach` resets fixtures for each test. The demo's `ApplicationRunner` may execute when `@SpringBootTest` starts the context; each test resets balances to their baseline before asserting. Test methods are **not annotated with `@Transactional`** in this example, so a test-framework transaction does not mask whether the service truly committed or rolled back.

If running tests in parallel against a shared H2 database, fixture resets can overwrite one another. For parallel integration tests, use isolated databases/schemas or appropriate test resources. Do not rely solely on Mockito for rollback conclusions, because mocked repositories do not verify physical transactions.

### 11.2. What Must Be Proven?

| Check | Why it is needed |
| --- | --- |
| Whether the exception exits to the caller | Shows the proxied call emitted an error signal |
| Actual exception type and rollback rules | Checked and unchecked may differ |
| Which transaction manager coordinates the DB | Same annotation name does not mean same connection |
| Data after the service finishes | Proof of real commit/rollback |
| Which transaction the caller is in | Propagation can alter the outcome |
| Whether there was a prior DB error/rollback-only | Catching does not promise commit |
| Whether the annotation was actually applied by the interceptor | Self-invocation/unproxied beans can bypass metadata |

Strong evidence is **independent data state after the transaction**, combined with exception checks and transaction logs when needed. For concurrency or serialization failure scenarios, add multi-connection and retry tests.

## 12. Recommended Business Handling Patterns

### Pattern A — Failure Must Abort the Whole Operation

```java
@Transactional
public void placeOrder(CreateOrderCommand cmd) {
    reserveStock(cmd);
    debitWallet(cmd);
    saveOrder(cmd);
}
```

If a mandatory step throws a `RuntimeException` out of the method, Spring rolls back participating DB operations by default. The helpers merely illustrate business steps and require real implementations checking affected rows/constraints. Place the transaction at a layer encompassing all three steps.

### Pattern B — Checked Business Exception Also Forces Abort

```java
@Transactional(rollbackFor = InsufficientInventoryException.class)
public void placeOrder(CreateOrderCommand cmd)
        throws InsufficientInventoryException {
    reserveStock(cmd);
    debitWallet(cmd);
    saveOrder(cmd);
}
```

`InsufficientInventoryException` is assumed to be an application checked exception. `rollbackFor` accurately expresses the condition requiring rollback; not all other exceptions have to change rules.

### Pattern C — Controller Maps Exception to HTTP Response

```java
@PostMapping("/orders")
public ResponseEntity<?> create(@RequestBody CreateOrderCommand cmd) {
    try {
        orderService.placeOrder(cmd);
        return ResponseEntity.status(201).build();
    } catch (InsufficientInventoryException ex) {
        return ResponseEntity.unprocessableEntity().body(ex.getMessage());
    }
}
```

The controller sits outside the transactional service; the error already passed through the interceptor before being caught. This is a snippet for a Spring MVC app with complete imports/classes/DTOs, **not a standalone Java program**.

### Pattern D — Optional Error Explicitly Recovered

```java
@Transactional
public Receipt saveWithOptionalLabel(Order order) {
    Receipt receipt = persistOrder(order);
    try {
        enrichOptionalLabel(receipt);
    } catch (OptionalLabelException ex) {
        recordNonCriticalWarning(ex);
    }
    return receipt;
}
```

Use only when `enrichOptionalLabel` is **truly optional**, the DB state remains committable, and saving the receipt does not require the label to satisfy invariants. If the label is mandatory, this is a design bug. Never use this pattern to mask exceptions from database constraints or inner transactions that already set rollback-only.

### Pattern E — Non-DB Side Effects Need Dedicated Design

If a service already called a payment HTTP endpoint, sent an email, or published an event, DB rollback does not automatically erase external side effects. When cross-system consistency is required, consider transactional outbox, idempotency keys, or saga/compensation. Exceptions exiting through the interceptor only coordinate resources that the transaction manager actually manages.

## 13. Common Debugging Lookup Table

| Symptom | What to investigate | Fix |
| --- | --- | --- |
| DB still commits despite logging error | Exception caught inside transactional method | Rethrow or mark rollback-only if business requires abort |
| Method throws `IOException` yet DB commits | Checked exception did not match rollback rules | Declare `rollbackFor` or adjust policy intentionally |
| `@Transactional` present yet no rollback occurs | Call bypassed proxy, e.g., self-invocation | Move transaction to entrypoint or split into another bean |
| Outer method catches yet still gets `UnexpectedRollbackException` | Inner `REQUIRED` interceptor marked rollback-only | Let error exit outer boundary or design proper recovery |
| SQL error caught yet transaction remains aborted | DBMS/driver marked transaction broken | Roll back/retry entire transaction per DB semantics |
| Test throws exception yet data is still lost/corrupted | Test only asserted thrown type, not DB | Assert data after transaction ends |
| Wrapping exception changed rollback behavior | Changed `RuntimeException` to checked or vice versa | Review rollback rules on the actual exiting exception |
| Set `noRollbackFor` yet expected rollback | Rule configured opposite to requirements | Fix rule and write regression test |
| Async task failed after caller returned | Task runs outside transaction lifetime/scope | Design separate transaction and eventual failure handling |
| Success logged yet DB rolled back | Rollback-only was set earlier | Inspect transaction status and `UnexpectedRollbackException` |
| Used `try/finally` expecting auto-rollback | `finally` does not replace exception propagation | Let interceptor see the error or mark rollback-only |

## 14. Knowledge Self-Check

1. Inside a `@Transactional` public method, code catches `IllegalStateException`, logs it, and returns normally. Does Spring automatically know the error happened? **No, in standard synchronous exception-handling interceptor flow**; unless the DB/manager marked rollback-only through another path, the transaction can commit.
2. A controller catches an exception thrown by `service.pay()`. Does the transaction still roll back? **Possibly yes**, if the exception passed through the service's proxy and matched rollback rules; catching in the controller does not reverse rollback.
3. Does `IOException` escaping default `@Transactional` in Spring 6.1 normally cause rollback? **No**; an additional rule is needed if business logic requires rollback.
4. What does `@Transactional(rollbackFor=IOException.class)` change? **It tells the interceptor to roll back when `IOException` exits across the boundary.**
5. If an inner `REQUIRED` transaction already marked rollback-only, does an outer catch returning normally guarantee commit? **No**, the outer commit may throw `UnexpectedRollbackException`.
6. What is `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` for? **Requesting an intentional rollback even when the method handles the error internally.**
7. After catching a SQL error, is the DB guaranteed to remain committable? **No**; the DBMS may have put the transaction into an error state.
8. Does calling a `@Transactional` method via `this.method()` in the same object trigger a new interceptor? **No, in standard proxy mode.**
9. Does an exception in a background task occurring after the transactional method already committed roll back the old transaction? **No**.
10. Why does a test using only `assertThrows` fail to prove rollback? **Because a checked exception can escape while the transaction still commits; data must be checked after completion.**

## 15. Rollback Policy Design Checklist

1. Identify **all mandatory steps** that must commit or roll back together; place `@Transactional` on the public service boundary invoked through a Spring proxy.
2. For each exception type, explicitly decide **rollback vs. allowed to commit**; never rely on the intuition that “throwing an error auto-aborts”.
3. If an error must abort, let an appropriate exception pass through the transaction interceptor; for checked exceptions, declare `rollbackFor`.
4. If catching to log or reformat messages, **rethrow** an appropriate exception and preserve the cause. If handling in the caller, catch after the proxy.
5. If catching without rethrowing, verify the failed step is genuinely optional; if aborting is required, mark rollback-only and return a transparent failure result.
6. Check propagation and outer/inner transactional scopes; understand how shared rollback-only leads to `UnexpectedRollbackException`.
7. Distinguish **application exceptions** from **DB SQL errors**; do not assume catching restores database transaction state.
8. Do not split mandatory steps into fire-and-forget tasks or external side effects without a dedicated consistency strategy.
9. Test **errors crossing the boundary**, **applied rules**, **the right transaction manager**, and **post-completion DB state**.
10. Record the Spring version and actual default rollback configuration when upgrading systems.

## Official References

- Spring Framework — Declarative Transaction Implementation: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-decl-explained.html
- Spring Framework — Rolling Back a Declarative Transaction: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/rolling-back.html
- Spring Framework — Using `@Transactional` and rollback rules: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html
- Spring Framework — Transaction Propagation, `REQUIRED` and `UnexpectedRollbackException`: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/tx-propagation.html
- Spring Framework — Programmatic Transaction Management: https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/programmatic.html
- Spring Framework — Proxying Mechanisms: https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html