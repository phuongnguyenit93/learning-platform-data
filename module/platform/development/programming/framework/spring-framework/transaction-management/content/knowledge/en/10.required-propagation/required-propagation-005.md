# UnexpectedRollbackException at the Outer Completion Boundary with PROPAGATION_REQUIRED

## 1. Characteristic Scenario: Inner Signals Failure, Outer Thinks It Can Still Commit

Consider a Spring business flow:

1. A caller invokes `OuterService.execute()` through a Spring proxy. This method has `@Transactional` with the default `REQUIRED` propagation, so Spring opens a physical transaction if none existed beforehand.
2. `execute()` calls `InnerService.change()` on a **different Spring bean**, also annotated with `@Transactional(propagation = REQUIRED)`.
3. Inner encounters a `RuntimeException`. Inner's Spring transaction interceptor sees the exception and marks the shared transaction as **rollback-only**.
4. Outer catches the exception, logs it, continues processing, and finally **returns normally**, thinking the transaction can commit.
5. When the outer proxy requests commit at the outermost boundary, the transaction manager detects that the shared transaction has been marked rollback-only. It performs a rollback instead of a commit and throws **`UnexpectedRollbackException`** to the caller.

This error is not arbitrary erratic behavior by Spring. It protects a critical guarantee: **the caller must not receive a "success" result if the transaction it thought committed actually rolled back**.

The common message line from the manager looks like:

~~~text
Transaction rolled back because it has been marked as rollback-only
~~~

**Important distinction:** "Unexpected" means **rollback occurred when the outer side was attempting to commit**, not that Spring does not know where rollback-only came from. The original error may have been caught; the rollback event at the outer boundary is a distinct outcome from inner's business exception.

This lesson focuses on `PROPAGATION_REQUIRED`, the relationship between **logical transaction scopes** and the **physical transaction**, the rollback-only mechanism, when `UnexpectedRollbackException` appears, and how to inspect/fix the design.

## 2. One Physical Transaction, Multiple Logical Transaction Scopes

In Spring, a method invocation advised by `@Transactional(propagation = REQUIRED)` creates a **logical transaction scope** for that method. When no transaction exists yet, it creates a new physical transaction. When a matching transaction already exists, it **joins** the existing physical transaction.

With two services calling each other through proxies, you can picture it as:

~~~text
Caller
  |
  v
OuterService proxy -- @Transactional(REQUIRED), logical scope OUTER
  |
  |  opens PHYSICAL TRANSACTION T1, connection C1
  v
OuterService.outer()
  |
  v
InnerService proxy -- @Transactional(REQUIRED), logical scope INNER
  |
  |  joins T1, does not create an independent connection/physical transaction
  v
InnerService.inner()
  |
  +-- unchecked error -> INNER marks T1 rollback-only
  |
  v
OuterService.outer() catches error -> returns normally
  |
  v
OUTER interceptor requests commit of T1
  |
  +-- sees T1 rollback-only -> rolls back T1
  |
  v
Caller receives UnexpectedRollbackException
~~~

**There are no two independent commits**: an inner `REQUIRED` cannot commit "its own part" while participating in T1. When inner completes normally, it only ends its logical scope and leaves outer to decide when the physical transaction completes. When inner rolls back while participating in T1, that rollback-only marker prevents outer from committing T1 anymore.

| Concept | Scope | What can it control? |
| --- | --- | --- |
| Logical scope OUTER | The `outer()` invocation passing through transaction advice | Expresses commit/rollback intent at the point where outer returns/throws |
| Logical scope INNER | The `inner()` invocation passing through transaction advice | Produces the outcome of the inner scope, which can make the shared transaction rollback-only |
| Physical transaction T1 | A real resource transaction, e.g., a JDBC connection | Has only one final outcome: commit **or** rollback |
| Rollback-only marker | State attached to transaction/status, depending on manager | Prevents a successful commit once the transaction has been declared must-rollback |

For example, both outer and inner call `JdbcTemplate` using the same `DataSource` with `JdbcTransactionManager`. They can execute multiple SQL statements on the same connection participating in T1. Therefore, a successful UPDATE in outer **is still undone** if inner makes T1 rollback-only and outer continues.

## 3. Sequence Diagram: Why Does the Error Only Surface When Outer Completes?

~~~mermaid
sequenceDiagram
    participant C as Caller
    participant OP as Outer proxy
    participant O as OuterService
    participant IP as Inner proxy
    participant I as InnerService
    participant TM as TransactionManager/DB

    C->>OP: outer()
    OP->>TM: begin physical transaction T1
    OP->>O: invoke outer()
    O->>IP: inner()
    IP->>TM: join T1 (logical scope)
    IP->>I: invoke inner()
    I-->>IP: throw RuntimeException
    IP->>TM: mark T1 rollback-only
    IP-->>O: rethrow RuntimeException
    Note over O: catch, handle, then return normally
    O-->>OP: return success
    OP->>TM: commit T1?
    TM->>TM: detect rollback-only
    TM->>TM: rollback T1
    TM-->>OP: UnexpectedRollbackException
    OP-->>C: throw UnexpectedRollbackException
~~~

Here, outer **cannot undo** the fact that inner marked the shared transaction rollback-only merely by catching the exception or returning a success DTO. When the transaction manager executes outer's commit, it cannot silently ignore the marker and commit. The normal behavior is to roll back and throw the exception to the caller.

### "Where" does the error appear?

In the scenario above:

- Inner throws **`IllegalStateException`** from the business method.
- Outer **catches `IllegalStateException`** in a `try/catch` surrounding `inner()`.
- Outer runs to the end of the method and **returns normally**.
- After the outer method returns, the proxy transaction advice performs commit; **`UnexpectedRollbackException` is thrown during proxy completion**, and propagates to the caller outside the proxy.

Therefore, placing a `try/catch (UnexpectedRollbackException)` **inside the outer method body, wrapping only `inner()`**, will usually **fail to catch the exception thrown at the outer commit boundary** under default configuration. The catch must sit in the **caller outside the outer proxy**, or at an error-handling layer enclosing that invocation.

Spring has a fail-early setting in some managers that can make `UnexpectedRollbackException` surface earlier, yet **the default in `AbstractPlatformTransactionManager` is to report at the outermost boundary** once global rollback-only is observed. Do not equate every exception throw site with the same phase of the transaction.

## 4. Why Does Rollback Still Happen Even Though Outer Caught It?

A Java `try/catch` only changes **exception control flow**; it does not clear transaction state already set by the manager. When the inner proxy sees an unchecked exception, it gets the chance to mark the participating physical transaction as rollback-only. Once this global marker is set, outer catching the exception does not restore the transaction to a committable state.

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
            System.out.println("Inner error caught");
        }
        System.out.println("Outer is about to return normally");
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

This is **illustrative code** without imports/application bootstrap, intended to show the two-Spring-bean structure. With a default-configured manager, the inner advice handles the unchecked exception and sets global rollback-only; outer catches and returns; outer advice can then throw `UnexpectedRollbackException`. Do not assume the same happens if the inner bean is replaced with a method in the same class called via `this.fail()`: **self-invocation** bypasses inner's proxy interception in proxy mode, so inner's separate rollback-only marker may not be set.

### The key: "which advice did the exception pass through?"

- If inner is called **through a proxy**, the exception passes through inner's advice before reaching outer's `catch`.
- If inner is a direct `this.inner()` call on the same target, the inner annotation usually does not create a separate interceptor; if outer catches the exception and returns normally, outer's advice can decide to commit if there is no other cause for rollback-only.
- If outer **does not catch** the exception and lets the unchecked exception escape, outer's advice sees the error and can **intentionally roll back**. Along that path the caller typically receives the **original exception**, not necessarily `UnexpectedRollbackException`.
- If inner has `@Transactional(noRollbackFor = IllegalStateException.class)` and the error matches this rule, inner's advice normally does not mark rollback-only solely for that exception; if outer catches the error and completes normally, commit can succeed provided the DB/manager still allow it.

There is no rule of thumb saying "whenever inner throws, `UnexpectedRollbackException` is guaranteed". You must inspect **the rollback rule of each logical scope**, proxy calls, resource state, and what outer does upon completion.

## 5. Three Key Paths: Same Root Error, Different Outcomes

Assume a physical transaction is being created by outer; each case runs independently with identical initial data:

| Scenario | What happens in inner | What does outer do? | What the caller typically sees | Physical transaction |
| --- | --- | --- | --- | --- |
| A — Inner `REQUIRED` throws unchecked | Inner proxy sets rollback-only | Catches and returns normally | `UnexpectedRollbackException` at outer commit | Rollback |
| B — Inner `REQUIRED` throws unchecked | Inner proxy sets rollback-only | Does not catch; exception escapes outer | Original business exception (e.g., `IllegalStateException`) | Rollback |
| C — Inner `REQUIRED` throws unchecked with matching `noRollbackFor` | Inner proxy does not mark rollback due to that rule | Catches and returns normally | Normal return if committable | Commit |
| D — Inner `REQUIRED` only calls `status.setRollbackOnly()` then returns | Inner scope explicitly requests rollback | Outer unaware, returns normally | `UnexpectedRollbackException` at outer commit (typical config) | Rollback |
| E — Outer **marks rollback-only itself** and returns | Outer directly chooses rollback | Returns normally | Usually returns normally, rollback is performed | Rollback |

The table assumes Spring declarative transactions in proxy mode, the same manager/resource, calls going through proxies, and no other SQL/connection/commit errors. `UnexpectedRollbackException` may not be the only exception in a real system; these are the typical paths for reading semantics.

In scenario E, "rollback-only" belongs to the **scope that initiated the transaction**. If the outermost scope itself calls `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`, rollback is an **intentional** decision, not a silent rollback contradicting outer's intent to commit. Therefore, you should not claim every rollback-only case throws `UnexpectedRollbackException`.

## 6. Complete Java 17+ Example: Observing UnexpectedRollbackException and Real Balances

The example uses **Spring Boot 3.3.5 (Spring Framework 6.1.x)**, **Spring JDBC**, **H2 in-memory**, and Maven. No web server, JPA, R2DBC, or multiple databases are used. Methods are called through Spring bean proxies; all UPDATEs run on the same `JdbcTemplate` and `DataSource` managed by `JdbcTransactionManager`.

The application runs five experiments:

1. Inner `REQUIRED` throws unchecked, outer catches and returns: rollback + `UnexpectedRollbackException` at caller.
2. Inner throws unchecked, outer **does not catch**: rollback, caller sees the original exception.
3. Inner `REQUIRED` marks rollback-only itself and returns normally: outer commit fails with `UnexpectedRollbackException`.
4. Inner throws unchecked with a matching `noRollbackFor` rule, outer catches: transaction commits.
5. Happy path: both outer and inner use `REQUIRED`, all UPDATEs commit together at the end.

### 6.1. Create the project

~~~text
required-rollback-demo/
├── pom.xml
└── src/main/java/example/requiredrollback/
    ├── RequiredRollbackApplication.java
    ├── OuterService.java
    └── InnerService.java
~~~

Requires **JDK 17+**, Maven, and access to Maven Central to download dependencies on the first run.

### 6.2. The pom.xml file

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
    <artifactId>required-rollback-demo</artifactId>
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

### 6.3. The RequiredRollbackApplication.java file

~~~java
package example.requiredrollback;

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
public class RequiredRollbackApplication {
    public static void main(String[] args) {
        SpringApplication.run(RequiredRollbackApplication.class, args);
    }

    @Bean
    PlatformTransactionManager transactionManager(DataSource source) {
        return new JdbcTransactionManager(source);
    }

    @Bean
    CommandLineRunner runDemo(JdbcTemplate jdbc, OuterService outer) {
        return args -> {
            jdbc.execute(
                "CREATE TABLE account (id INT PRIMARY KEY, balance INT NOT NULL)"
            );
            jdbc.update(
                "INSERT INTO account (id, balance) VALUES (?, ?)", 1, 100
            );
            System.out.println("START=" + balance(jdbc));

            try {
                outer.catchInnerFailure();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                    "CALLER_UNEXPECTED=" + ex.getClass().getSimpleName()
                );
            }
            System.out.println("AFTER_CATCH=" + balance(jdbc));

            try {
                outer.propagateInnerFailure();
            } catch (IllegalStateException ex) {
                System.out.println("CALLER_ORIGINAL=" + ex.getMessage());
            }
            System.out.println("AFTER_PROPAGATE=" + balance(jdbc));

            try {
                outer.innerMarksOnly();
            } catch (UnexpectedRollbackException ex) {
                System.out.println(
                    "CALLER_UNEXPECTED_MANUAL="
                        + ex.getClass().getSimpleName()
                );
            }
            System.out.println("AFTER_MANUAL=" + balance(jdbc));

            outer.catchesNoRollbackRule();
            System.out.println(
                "AFTER_NO_ROLLBACK_RULE=" + balance(jdbc)
            );

            outer.allSuccess();
            System.out.println("AFTER_HAPPY=" + balance(jdbc));
        };
    }

    private static Integer balance(JdbcTemplate jdbc) {
        return jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = ?", Integer.class, 1
        );
    }
}
~~~

### 6.4. The OuterService.java file

~~~java
package example.requiredrollback;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class OuterService {
    private final JdbcTemplate jdbc;
    private final InnerService inner;

    public OuterService(JdbcTemplate jdbc, InnerService inner) {
        this.jdbc = jdbc;
        this.inner = inner;
    }

    @Transactional
    public void catchInnerFailure() {
        add(10);
        try {
            inner.failRequired(); // Called via another bean's proxy.
        } catch (IllegalStateException ex) {
            System.out.println("INNER_CAUGHT=" + ex.getMessage());
        }
        System.out.println(
            "ROLLBACK_ONLY_IN_OUTER="
                + TransactionAspectSupport.currentTransactionStatus()
                    .isRollbackOnly()
        );
        add(30);
        // Normal return yet T1 is already rollback-only.
        // UnexpectedRollbackException occurs AFTER return, inside the proxy.
    }

    @Transactional
    public void propagateInnerFailure() {
        add(11);
        inner.failRequired();
        // Not reached when inner throws.
    }

    @Transactional
    public void innerMarksOnly() {
        add(3);
        inner.markRollbackOnly();
        System.out.println(
            "MANUAL_ROLLBACK_ONLY="
                + TransactionAspectSupport.currentTransactionStatus()
                    .isRollbackOnly()
        );
        add(5);
    }

    @Transactional
    public void catchesNoRollbackRule() {
        add(1);
        try {
            inner.nonFatal();
        } catch (IllegalStateException ex) {
            System.out.println(
                "INNER_NONFATAL_CAUGHT=" + ex.getMessage()
            );
        }
        System.out.println(
            "NO_ROLLBACK_RULE_FLAG="
                + TransactionAspectSupport.currentTransactionStatus()
                    .isRollbackOnly()
        );
        add(3);
    }

    @Transactional
    public void allSuccess() {
        add(10);
        inner.success();
    }

    private void add(int delta) {
        jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = 1",
            delta
        );
    }
}
~~~

### 6.5. The InnerService.java file

~~~java
package example.requiredrollback;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.interceptor.TransactionAspectSupport;

@Service
public class InnerService {
    private final JdbcTemplate jdbc;

    public InnerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void failRequired() {
        add(20);
        throw new IllegalStateException("inner-failure");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void markRollbackOnly() {
        add(40);
        TransactionAspectSupport.currentTransactionStatus()
            .setRollbackOnly();
        // Returns normally; shared physical transaction is marked.
    }

    @Transactional(
        propagation = Propagation.REQUIRED,
        noRollbackFor = IllegalStateException.class
    )
    public void nonFatal() {
        add(2);
        throw new IllegalStateException("nonfatal-inner");
    }

    @Transactional(propagation = Propagation.REQUIRED)
    public void success() {
        add(20);
    }

    private void add(int delta) {
        jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = 1",
            delta
        );
    }
}
~~~

### 6.6. Run and compare results

From the `required-rollback-demo` directory:

~~~bash
mvn -q spring-boot:run
~~~

Lines printed by **the program itself**, ignoring Spring Boot/Hikari startup logs:

~~~text
START=100
INNER_CAUGHT=inner-failure
ROLLBACK_ONLY_IN_OUTER=true
CALLER_UNEXPECTED=UnexpectedRollbackException
AFTER_CATCH=100
CALLER_ORIGINAL=inner-failure
AFTER_PROPAGATE=100
MANUAL_ROLLBACK_ONLY=true
CALLER_UNEXPECTED_MANUAL=UnexpectedRollbackException
AFTER_MANUAL=100
INNER_NONFATAL_CAUGHT=nonfatal-inner
NO_ROLLBACK_RULE_FLAG=false
AFTER_NO_ROLLBACK_RULE=106
AFTER_HAPPY=136
~~~

### 6.7. Explanation per actual transaction

**Case 1 — Outer catches, outer cannot commit:**

- T1 starts at `outer.catchInnerFailure()`. Outer UPDATEs `+10`.
- Inner `REQUIRED` joins T1, UPDATEs `+20`, then throws `IllegalStateException`. Inner interceptor encounters the unchecked exception and marks T1 rollback-only.
- Outer catches; `isRollbackOnly()` returns true; outer still UPDATEs `+30`. Those SQL statements may have executed, **which does not mean they will commit**.
- Outer returns. Outer interceptor wants to commit T1 yet must roll back; the caller outside receives `UnexpectedRollbackException`. Balance returns to 100, not 160.

**Case 2 — Original exception escapes outer:**

- A new T1 opens; outer UPDATEs `+11`, inner UPDATEs `+20` then throws `IllegalStateException`.
- Outer does not catch. Outer interceptor receives that same unchecked exception and handles rollback instead of taking the commit path. Caller catches `IllegalStateException("inner-failure")`.
- Balance remains 100. Not seeing `UnexpectedRollbackException` does not mean rollback failed; on the contrary, **rollback here matched the exception escaping outer**.

**Case 3 — Inner calls setRollbackOnly itself and returns:**

- Outer UPDATEs `+3`, inner UPDATEs `+40`, then inner calls `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()`.
- Inner throws no exception, yet when the logical scope participating in T1 finishes, the shared transaction is marked rollback-only.
- Outer still UPDATEs `+5` and returns. Outer commit is rejected with rollback + `UnexpectedRollbackException`. Balance remains 100.

**Case 4 — Inner has its own no-rollback rule:**

- Outer UPDATEs `+1`, inner UPDATEs `+2` then throws `IllegalStateException`.
- Inner's annotation has `noRollbackFor = IllegalStateException.class`. Under this policy, inner advice does not request rollback **solely for that exception**, and physical transaction T1 remains valid.
- Outer catches, prints flag false, UPDATEs `+3` more, and returns. Commit succeeds; balance is 100 + 1 + 2 + 3 = **106**.
- This rule makes sense only when business logic permits continuing; do not use `noRollbackFor` casually to hide data or infrastructure errors.

**Case 5 — Both logical scopes complete normally:**

- Outer UPDATEs `+10`, inner UPDATEs `+20`. No rollback-only.
- Outer completes the physical transaction, committing once; balance becomes **136**.

**Why is this example trustworthy?** All services are Spring-injected, and `OuterService` calls `InnerService` through a different bean rather than `this.inner()`; `JdbcTemplate` and the transaction manager use the same H2 `DataSource`. The `CommandLineRunner` caller has no `@Transactional`, so each `outer.*` method has its own physical boundary. Data is read **after the proxy finishes** to observe real commits/rollbacks, rather than relying solely on logs.

## 7. Distinguishing Inner Marking Rollback-Only from Outer Intentionally Rolling Back

The following two snippets are easily conflated:

~~~java
// A: InnerService joins the shared transaction via REQUIRED.
@Transactional(propagation = Propagation.REQUIRED)
public void inner() {
    TransactionAspectSupport.currentTransactionStatus()
        .setRollbackOnly();
}
~~~

~~~java
// B: OuterService is where the physical transaction starts.
@Transactional
public void outer() {
    TransactionAspectSupport.currentTransactionStatus()
        .setRollbackOnly();
}
~~~

Both are **illustrative excerpts**, lacking Spring classes/bootstrap setup. In A, the **inner logical scope** chooses rollback-only, while outer may still naively propose committing: that is the path leading to `UnexpectedRollbackException`. In B, the **outer scope owning the transaction** itself said "I want to roll back": the manager can roll back and outer can return normally, without necessarily reporting "unexpected".

When propagation joins a transaction already started by a **higher-level caller**, even a method that looks "outer" in one service is merely an inner logical scope relative to the true physical transaction. Thus the word "outer" in a method name **does not determine** the physical boundary; you must find which entry point originally opened the transaction and which manager completes it.

## 8. When Is Rollback-Only Set?

Common causes:

- **An unchecked exception leaves an inner `@Transactional(REQUIRED)`**: the default rollback rule marks the shared transaction; the exception may be caught in outer **after** the marker has been set.
- **A checked exception with matching `rollbackFor`**: although checked exceptions do not trigger rollback by default, an explicit rule can set the marker.
- **Code calls `setRollbackOnly()`** on a scope participating in the transaction.
- **An inner transaction template or advised repository layer** decides to roll back, given the same physical transaction and matching rules.
- **Infrastructure or the database** renders the transaction uncommittable (for example, a SQL error causing the DB transaction to abort). This requires inspecting the exact resource state and exception rather than automatically attributing every SQL error to a single Spring marker.

On many transaction managers extending `AbstractPlatformTransactionManager`, `globalRollbackOnParticipationFailure` defaults to true: a participating scope failing with a rollback decision can mark the whole transaction rollback-only. Some managers/resources have distinct semantics; you must know the actual manager before predicting behavior.

### What do isRollbackOnly and transactionActive tell you?

~~~java
boolean rollbackOnly =
    TransactionAspectSupport.currentTransactionStatus()
        .isRollbackOnly();
~~~

The API above is valid only when matching transaction advice is active for the current thread; calling it outside a proxy context can fail. When called in the JDBC outer scope in the example, it helps confirm that rollback-only state has reached the current scope. However, a `false` result at check time **does not promise** a later commit will succeed, because other resources/logic can still fail afterward.

Similarly, `TransactionSynchronizationManager.isActualTransactionActive()` indicates a transaction is active in the current **imperative** context, yet it does not tell you whether the transaction is rollback-only, whether inner was separately intercepted, or whether the final commit will succeed.

## 9. Cases You Should Not Infer as UnexpectedRollbackException

### 9.1. Outer intentionally throws an unchecked exception

If outer lets `IllegalStateException` escape and rollback rules decide to roll back, the caller typically receives the **original exception**, not `UnexpectedRollbackException`, because outer **did not request commit**. The resource can still throw another error during rollback; hence "typically" matters.

### 9.2. Inner fails yet is caught **before reaching inner transaction advice**

~~~java
@Service
class InnerService {
    @Transactional
    public void inner() {
        try {
            throw new IllegalStateException("handled locally");
        } catch (IllegalStateException ex) {
            // No rethrow, no setRollbackOnly.
        }
    }
}
~~~

If there is no other cause for rollback-only, inner's advice sees a **normal return** and does not mark global rollback-only just because a Java exception was caught. Outer can commit.

### 9.3. Self-invocation bypasses the inner proxy

~~~java
@Service
class OneBean {
    @Transactional
    public void outer() {
        try {
            this.inner();
        } catch (IllegalStateException ignored) {
            // No inner advice on self-call.
        }
    }

    @Transactional
    public void inner() {
        throw new IllegalStateException("failure");
    }
}
~~~

In default proxy mode, `this.inner()` does not run inner's interceptor, so Spring **does not automatically mark rollback-only at an inner logical scope**. Because outer catches and returns normally, the physical transaction can commit. Do not treat this as a "fix" for errors: it accidentally bypasses the transaction semantics declared on the inner method.

### 9.4. Inner REQUIRES_NEW instead of REQUIRED

`PROPAGATION_REQUIRES_NEW` opens an independent physical transaction, suspending the outer transaction when supported. If inner rolls back and outer catches the exception and continues, the outer transaction **is not automatically marked rollback-only just because the independent inner failed**. However, a successful inner commit is also **not rolled back** if outer fails later—a business-consistency change requiring serious evaluation. The JDBC pool must have enough connections while outer holds a connection and inner needs another resource.

### 9.5. Inner NESTED with savepoints when supported

`PROPAGATION_NESTED` can create a savepoint within the same physical transaction, roll back the inner work to the savepoint, and let outer continue and commit the rest. It depends on the transaction manager/driver, typically fitting JDBC with savepoint support; you cannot assume JPA/JTA/R2DBC all provide equivalent support.

### 9.6. Manager with fail-early configuration

`AbstractPlatformTransactionManager.setFailEarlyOnGlobalRollbackOnly(true)` can make `UnexpectedRollbackException` surface earlier at an inner boundary once the manager knows the global marker. The default is false, so errors usually surface only at the outermost boundary. Adjusting this setting aims at **earlier diagnostics**, not making a rollback-only transaction committable.

## 10. Wrong or Dangerous "Fixes"

### 10.1. Catching UnexpectedRollbackException inside the outer method

In the basic example, the exception occurs **after the outer method body has returned**, inside `TransactionInterceptor`. A `try/catch` inside outer around inner cannot catch the outer completion failure. If you want to handle the exception to produce an appropriate response, place the handler in the **caller/API layer outside the outer proxy**, while also fixing the root cause of rollback-only rather than hiding the message.

### 10.2. Removing @Transactional from inner to avoid the rollback marker

This may eliminate `UnexpectedRollbackException` on one call path, yet changes inner's semantics altogether, potentially leading to partial commits or lack of rollback when called standalone. Clarify atomicity requirements first.

### 10.3. Changing every inner method to REQUIRES_NEW

This no longer guarantees outer + inner succeed/fail together. The independent transaction can commit even if outer rolls back, and consumes an extra connection. Use it only when the business logic genuinely requires an independent commit—such as writing an audit log independent of the main transaction—and you have verified the consequences are acceptable.

### 10.4. Disabling globalRollbackOnParticipationFailure

Some managers based on `AbstractPlatformTransactionManager` allow `setGlobalRollbackOnParticipationFailure(false)`. When enabled, a participating scope failing with an exception may defer the rollback decision to the transaction originator if the resource is still committable. **This is not a safe default fix**: a Hibernate session or database transaction after a data error may not be able to continue, and an explicit `setRollbackOnly()` still expresses a rollback decision that should not be ignored. Changing this flag solely to suppress exceptions is not recommended.

### 10.5. "Clearing" rollback-only by catching again

There is no general business API to clear a global rollback-only marker and commit as if no error occurred. The right approach is to **redesign boundaries**, handle errors before a transactional scope decides on rollback, or roll back completely and retry in a **new transaction** if the operation is idempotent and safe.

### 10.6. Relying on INSERT/UPDATE success logs

SQL executed successfully is still not committed. Some providers even defer flushing until near commit. When the transaction eventually rolls back, previously successful updates are undone. Inspecting from another connection/transaction **after the boundary completes** is the right way to verify.

## 11. Choosing the Right Behavior for Business Needs

| Need | Suitable design direction |
| --- | --- |
| Every step must be atomic: if inner fails, abort everything | Keep `REQUIRED`, let the appropriate error propagate out of outer; caller handles after rollback |
| Inner reports a skippable business error and other steps should commit | Avoid setting rollback-only when the error truly needs no rollback; verify rollback rules and DB state; never swallow dangerous infrastructure errors |
| Inner must commit/roll back separately from outer | Consider `REQUIRES_NEW` and separate proxy boundaries properly, accepting independent resources/outcomes |
| Want to undo only part of SQL while keeping the outer transaction | Consider `NESTED`/savepoints when supported by manager and JDBC driver |
| Already marked rollback-only yet want to proceed "successfully" | Cannot guarantee committing that transaction; complete rollback, return a proper failure result, or start a new transaction |
| Want earlier error notification instead of waiting for outer boundary | Check `failEarlyOnGlobalRollbackOnly` on the corresponding manager; only changes detection timing, not the final outcome |

The most important takeaway is that **propagation rules are consistency rules**, not tricks to suppress exceptions. If you want a "best-effort" step whose failure does not affect the rest, design around business meaning and resource viability; do not simply catch in outer and assume the marker vanishes.

## 12. Process for Debugging UnexpectedRollbackException in a Real Application

1. **Identify where the physical transaction begins.** Which proxy call created the new transaction, and does the "outer" method actually own the physical transaction? Is there `@Transactional` on the caller or test framework?
2. **Identify all logical REQUIRED scopes** called by outer. Pay special attention to Spring Data repositories, injected services, transaction templates, and the difference between proxy calls and `this.method()`.
3. **Find inner's root exception.** Before outer caught the error and commit failed, was there a `RuntimeException`, exception translation from a DAO, a checked exception with `rollbackFor`, or `setRollbackOnly()`?
4. **Locate where catching/translation happens.** Did the catch occur inside inner before the interceptor, or in outer after the inner interceptor already processed it? Does any code rethrow as-is or translate exception types?
5. **Check rollback rules and status.** `rollbackFor`, `noRollbackFor`, custom global rules (if any), and rollback-only flags. Enable logging only in test environments, avoiding exposing SQL/PII.
6. **Read the stack trace carefully.** `UnexpectedRollbackException` on the commit path does not necessarily hold the causal exception in `getCause()`; search logs for the **first error** that was caught or logged earlier.
7. **Inspect the transaction manager and resources.** What behavior and connection source do JDBC `DataSourceTransactionManager`/`JdbcTransactionManager`, JPA `JpaTransactionManager`, or another manager have? Do not assume all DAOs share a transaction just because they share a DB URL.
8. **Write an integration test with a failure case.** Invoke outer through the Spring proxy from a test client not wrapped in a test transaction; after completion, read data from another session and assert all modifications rolled back.
9. **Check test-environment boundaries.** Spring TestContext normally rolls back `@Transactional` tests by default; a test transaction can turn the application's "outer" method into merely a participating logical scope.
10. **Fix boundaries according to business semantics.** Keep an atomic transaction and let errors propagate, or intentionally choose independent/nested transactions; do not merely catch and discard exceptions.

You can temporarily enable logs:

~~~properties
logging.level.org.springframework.transaction.interceptor=TRACE
logging.level.org.springframework.jdbc.datasource=DEBUG
~~~

Actual log output varies by manager/version. When using reactive transactions, status may be attached to **Reactor subscriber Context** rather than an imperative ThreadLocal; do not copy a JDBC `TransactionSynchronizationManager` check verbatim to reason about R2DBC. The common core remains logical scopes, propagation, and the physical transaction being marked rollback-only.

## 13. Common Confusions

| Wrong conclusion | Correct understanding |
| --- | --- |
| "Outer caught the exception so it must commit." | Catching does not clear global rollback-only already set by the inner proxy. |
| "Inner `REQUIRED` rolls back on its own while outer commits the rest." | REQUIRED joins the **same physical transaction**; there is no independent inner commit/rollback. |
| "UnexpectedRollbackException originates right inside outer's body." | Usually it is raised **at the proxy when outer tries to commit after returning**, if fail-early is not enabled. |
| "UnexpectedRollbackException is inner's original exception itself." | It is a notice that the transaction rolled back contrary to commit intent; the original exception may have been caught. |
| "Rollback happened so UnexpectedRollbackException must occur." | Outer can intentionally roll back when an unchecked exception escapes or when it sets rollback-only itself; this exception need not be thrown. |
| "Having `isActualTransactionActive() == true` guarantees commit succeeds." | Active does not mean committable; rollback-only may already be true. |
| "Inner's UPDATE already succeeded so rollback-only has no effect." | An UPDATE that succeeded before commit can still be rolled back completely. |
| "Disabling failEarly will allow the transaction to commit." | That flag only governs **notification timing**, not fixing rollback-only state. |
| "Switching to `REQUIRES_NEW` is always a good fix." | It changes atomicity, commits independently, and carries connection-pool risks. |
| "A catch block in outer catches every error of the outer method." | Commit errors after return happen in the transaction interceptor, outside the method body. |
| "Inner `@Transactional` in the same class always creates a separate logical scope." | Self-invocation in proxy mode usually bypasses inner's interception. |
| "Only JDBC has rollback-only." | Many other Spring transaction managers also have the rollback-only concept; resource management differs. |

## 14. Exercises to Test Understanding of the Completion Boundary

**Question 1.** Outer `@Transactional(REQUIRED)` calls another bean's `@Transactional(REQUIRED)` inner method; inner throws `IllegalArgumentException`, and outer catches and returns. Default manager, no other errors. What does the caller outside the outer proxy see?

**Answer:** Inner advice marks the shared transaction rollback-only; outer attempts to commit after returning, resulting in rollback and typically `UnexpectedRollbackException`.

**Question 2.** Same setup, except outer does not catch inner's error and lets the exception escape past the proxy. What does the caller see?

**Answer:** Typically receives the original `IllegalArgumentException`, because outer's advice already handled rollback according to the escaping exception; it does not always throw `UnexpectedRollbackException` by default.

**Question 3.** Outer catches checked `IOException` from inner. Inner has no `rollbackFor` and there are no other DB errors/markers. What can happen?

**Answer:** Under traditional default policies prior to newer global rollback options, inner advice **does not require rollback for IOException**, so outer can commit. You must check the framework/config and rollback rules to conclude.

**Question 4.** Inner `REQUIRED` calls `TransactionAspectSupport.currentTransactionStatus().setRollbackOnly()` and returns normally. Outer returns normally. Must inner throw an exception for outer to roll back?

**Answer:** No. The marker is sufficient to make the physical transaction uncommittable. Outer's commit typically leads to `UnexpectedRollbackException`.

**Question 5.** Outer inside a `@Transactional` method catches `UnexpectedRollbackException` via `try { inner(); } catch (UnexpectedRollbackException e)` while inner is just `REQUIRED`? Is that guaranteed to be outer completion failure by default?

**Answer:** Not guaranteed. By default, global rollback-only is reported at the **outermost boundary**. An early exception could be due to fail-early config, a nested call with another physical boundary, or an error in a different transaction manager. You must inspect the call graph and stack trace.

**Question 6.** Inner is switched from `REQUIRED` to `REQUIRES_NEW`, and the exception is caught in outer. Are inner and outer still guaranteed to be atomic together?

**Answer:** No. Two independent physical transactions exist; inner rollback does not automatically roll back outer, and an inner commit is not undone if outer rolls back later.

## 15. Core Takeaways

**`UnexpectedRollbackException` at the outermost boundary is the signal that Spring had to roll back a physical transaction that the outer side wanted to commit.** The typical root pattern: inner `PROPAGATION_REQUIRED` passes through a proxy, encounters an exception matching rollback rules or marks rollback-only; outer catches the error and returns normally.

Read situations in the sequence **proxy boundary → logical scopes → rollback-only → physical commit/rollback**, not by counting annotations or executed SQL statements. Errors must be resolved in **transaction decisions and business design**, not by swallowing additional exceptions.

## References

- [Spring Framework — Transaction Propagation: REQUIRED, REQUIRES_NEW, NESTED](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-propagation.html): logical vs physical transactions, rollback-only, and causes of `UnexpectedRollbackException`.
- [Spring Framework — Declarative Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative.html): annotation advice and rollback policy.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): propagation attributes and rollback rules.
- [Spring Framework — Rolling Back a Declarative Transaction](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/rolling-back.html): checked/unchecked exceptions, `rollbackFor`, and `noRollbackFor`.
- [Spring Framework — AbstractPlatformTransactionManager API](https://docs.spring.io/spring-framework/docs/6.1.15/javadoc-api/org/springframework/transaction/support/AbstractPlatformTransactionManager.html): `globalRollbackOnParticipationFailure` and `failEarlyOnGlobalRollbackOnly`.
