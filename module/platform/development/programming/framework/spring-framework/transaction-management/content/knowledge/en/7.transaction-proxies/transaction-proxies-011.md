# Ordering Transaction Advice with Other Advice in Spring Framework

## 1. The Problem: Multiple Advice Wrapping One Method

A `@Transactional` method may simultaneously be subject to advice for logging, profiling, retry, caching, validation, security, or custom aspects. When multiple advice **apply at the same join point** in Spring AOP, their ordering determines:

- Which advice runs before the transaction starts, and which runs inside the transaction.
- Which advice runs after the transaction interceptor commits/rolls back, and which only sees that the method body returned.
- Whether retry creates a new transaction per attempt or repeats inside an already-open transaction.
- Whether an exception is translated/caught or still reaches the transaction interceptor for rollback-rule evaluation.
- Whether profiling measures commit/rollback cost too or only business logic.
- Whether caching or notifications run before data is successfully committed.

**Scope:** Spring AOP **proxy mode** and synchronous imperative transactions (JDBC/JPA). The `order` value orders the **advisor chain on a single call**; it does not determine SQL execution order or commit order across concurrent requests.

Suppose there are three layers:

```text
Caller
  |
  v
Logging advice @Order(10)           [outside]
  |
  v
Transaction advisor order=20        [begin/join transaction]
  |
  v
Metrics advice @Order(30)           [inside]
  |
  v
Target service method
```

On entry, the order is `10 → 20 → 30 → target`. On exit, the order **reverses**: `target → 30 → 20 → 10`. Advice with order 10 wraps the transaction interceptor; advice with order 30 sits inside it.

## 2. Precedence Rules and Entry/Exit Ordering

Spring AOP follows AspectJ-style precedence rules:

1. **Lower order value means higher precedence.** `@Order(10)` comes before `@Order(30)` on entry.
2. **Highest precedence runs first on entry and last on exit.** With `@Around`, code before `proceed()` runs on entry; code after `proceed()` runs while unwinding back to the caller.
3. `@Order` on an **`@Aspect` class** (or an aspect implementing `Ordered`) determines precedence among aspects. The transaction advisor has its own order configured in the transaction infrastructure.
4. If two advisors have undefined or equal precedence, do not rely on whatever arbitrary order happens to appear in logs. Some frameworks also apply their own internal ordering rules; inspect the advisors actually matching the call.
5. If an `@Around` advice **does not call `proceed()`**, inner layers of the chain may not run. If the advice calls `proceed()` multiple times, the target and inner transaction interceptor may also be traversed multiple times.

Clear ordering example:

| Layer | Precedence | On entry | On exit |
| --- | ---: | --- | --- |
| `OuterTrace` | 10 | Before transaction interceptor | After transaction interceptor |
| Transaction advice | 20 | Opens or joins transaction | Commits/rolls back or ends interceptor scope |
| `InnerTrace` | 30 | After interceptor starts handling | Before interceptor completes |
| `target.transfer()` | Not an advisor | Runs last on entry | First to return or throw an exception |

**Important:** if a `REQUIRED` method merely joins a transaction already opened by its caller, the inner method's transaction interceptor finishing **is not the final physical commit**. In that case, advice outside the inner method still cannot claim the outer commit has completed.

## 3. Configuring the Transaction Advisor Order

With Spring annotation-driven transaction management, the primary configuration is:

```java
@Configuration
@EnableTransactionManagement(order = 20)
class TransactionConfig {
    // DataSource, PlatformTransactionManager, service beans...
}
```

This is an illustrative configuration, not standalone runnable code. `order=20` is the **precedence of the transaction advice**, not a 20 ms wait timeout, not a thread priority, and not a transaction manager name.

The **default** of `@EnableTransactionManagement` is `Ordered.LOWEST_PRECEDENCE` (a very large order value, lowest precedence). An `@Order(100)` aspect usually wraps outside the default transaction advice; however, when multiple framework advisors also use lowest precedence, you should not assume a fixed order across all configurations.

Where to adjust order:

| Component | Where Configured |
| --- | --- |
| Transaction annotation advisor | `@EnableTransactionManagement(order = 20)` |
| `@AspectJ`-based aspect | `@Order(10)` on the aspect class or implementing `Ordered` |
| Programmatic advisor | `Ordered` or the corresponding advisor's `setOrder(...)` API |
| XML transaction annotations | `<tx:annotation-driven order="20"/>` |
| XML `<aop:advisor>` | `order` attribute on the advisor |

Do not place `@Order` on a **service class or a `@Transactional` method** intending to replace `@EnableTransactionManagement(order=...)`; those serve different purposes.

## 4. Complete Example: Observing the Transaction Precisely Between Two Aspects

This example runs with **Java 17+, Spring Framework 6.2.5, Spring AOP, H2 2.2.224, and Maven**. The goal is to observe ordering and commit/rollback effects on two sample accounts. Neither Spring Boot nor a Jakarta application server is needed.

File structure:

```text
tx-order-demo/
  pom.xml
  src/main/java/demo/App.java
  src/main/java/demo/LedgerService.java
  src/main/java/demo/OuterTrace.java
  src/main/java/demo/InnerTrace.java
```

### 4.1. `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>tx-order-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-aop</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-jdbc</artifactId>
            <version>6.2.5</version>
        </dependency>
        <dependency>
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.22</version>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <version>2.2.224</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-context` supplies the container, `spring-aop` supplies AOP proxies, `aspectjweaver` is needed for `@AspectJ` pointcut parsing, and `spring-jdbc` supplies `JdbcTemplate` and brings in Spring transaction support. The in-memory H2 database is recreated each time the process runs.

### 4.2. `src/main/java/demo/App.java`

```java
package demo;

import javax.sql.DataSource;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.datasource.DriverManagerDataSource;
import org.springframework.jdbc.support.JdbcTransactionManager;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

public class App {
    public static void main(String[] args) {
        try (var context = new AnnotationConfigApplicationContext(Config.class)) {
            JdbcTemplate jdbc = context.getBean(JdbcTemplate.class);
            jdbc.execute(
                "CREATE TABLE account (id INT PRIMARY KEY, balance INT NOT NULL)");
            jdbc.update(
                "INSERT INTO account (id, balance) VALUES (1, 100), (2, 100)");

            LedgerService service = context.getBean(LedgerService.class);

            service.transfer(10, false);
            printBalances("after_success", jdbc);

            try {
                service.transfer(20, true);
            } catch (IllegalStateException ex) {
                System.out.println("caller.caught=" + ex.getMessage());
            }
            printBalances("after_failure", jdbc);
        }
    }

    private static void printBalances(String prefix, JdbcTemplate jdbc) {
        int a = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = 1", Integer.class);
        int b = jdbc.queryForObject(
            "SELECT balance FROM account WHERE id = 2", Integer.class);
        System.out.printf("%s A=%d B=%d%n", prefix, a, b);
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAspectJAutoProxy(proxyTargetClass = true)
    @EnableTransactionManagement(order = 20)
    public static class Config {
        @Bean
        public DataSource dataSource() {
            var ds = new DriverManagerDataSource();
            ds.setDriverClassName("org.h2.Driver");
            ds.setUrl("jdbc:h2:mem:tx_advice_order;DB_CLOSE_DELAY=-1");
            ds.setUsername("sa");
            ds.setPassword("");
            return ds;
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
        public LedgerService ledgerService(JdbcTemplate jdbc) {
            return new LedgerService(jdbc);
        }

        @Bean
        public OuterTrace outerTrace() {
            return new OuterTrace();
        }

        @Bean
        public InnerTrace innerTrace() {
            return new InnerTrace();
        }
    }
}
```

The two annotations must be understood distinctly: `@EnableAspectJAutoProxy` enables processing of `@Aspect` classes; `@EnableTransactionManagement` enables the transaction advisor. `proxyTargetClass = true` ensures the service is proxied by class, retrievable via `context.getBean(LedgerService.class)`. In this demo, the caller has no pre-opened transaction.

### 4.3. `src/main/java/demo/LedgerService.java`

```java
package demo;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public class LedgerService {
    private final JdbcTemplate jdbc;

    public LedgerService(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Transactional
    public void transfer(int amount, boolean failAfterDebit) {
        System.out.println("target.tx=" +
                TransactionSynchronizationManager.isActualTransactionActive());

        jdbc.update(
            "UPDATE account SET balance = balance - ? WHERE id = 1", amount);

        if (failAfterDebit) {
            throw new IllegalStateException("simulated");
        }

        jdbc.update(
            "UPDATE account SET balance = balance + ? WHERE id = 2", amount);
    }
}
```

The first call transfers 10 from account A to B and commits successfully. The second throws `IllegalStateException` **after subtracting 20**, so the transaction interceptor rolls back by default (runtime exception). Both JDBC statements belong to the same transaction because `JdbcTemplate` and the transaction manager share the same `DataSource`.

### 4.4. `src/main/java/demo/OuterTrace.java`

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Aspect
@Order(10)
public class OuterTrace {
    @Around("execution(* demo.LedgerService.transfer(..))")
    public Object around(ProceedingJoinPoint point) throws Throwable {
        System.out.println("outer.enter tx=" + active());
        try {
            Object result = point.proceed();
            System.out.println("outer.exit tx=" + active());
            return result;
        } catch (Throwable ex) {
            System.out.println("outer.error tx=" + active());
            throw ex;
        }
    }

    private boolean active() {
        return TransactionSynchronizationManager.isActualTransactionActive();
    }
}
```

`OuterTrace` has order **10**, smaller than the transaction advisor's **20**. On entry, it logs before the new transaction starts. When `point.proceed()` returns, the inner transaction interceptor has already committed or thrown after rollback.

### 4.5. `src/main/java/demo/InnerTrace.java`

```java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Aspect
@Order(30)
public class InnerTrace {
    @Around("execution(* demo.LedgerService.transfer(..))")
    public Object around(ProceedingJoinPoint point) throws Throwable {
        System.out.println("inner.enter tx=" + active());
        try {
            Object result = point.proceed();
            System.out.println("inner.exit tx=" + active());
            return result;
        } catch (Throwable ex) {
            System.out.println("inner.error tx=" + active());
            throw ex;
        }
    }

    private boolean active() {
        return TransactionSynchronizationManager.isActualTransactionActive();
    }
}
```

`InnerTrace` has order **30**, greater than **20**. Therefore `inner.enter` runs after the transaction interceptor opens the transaction, and `inner.exit`/`inner.error` runs before the interceptor commits/rolls back.

### 4.6. Run command and expected output

In the `tx-order-demo` directory, execute:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.App
```

Main lines printed by the program (excluding Maven/Spring logs):

```text
outer.enter tx=false
inner.enter tx=true
target.tx=true
inner.exit tx=true
outer.exit tx=false
after_success A=90 B=110
outer.enter tx=false
inner.enter tx=true
target.tx=true
inner.error tx=true
outer.error tx=false
caller.caught=simulated
after_failure A=90 B=110
```

Phase-by-phase explanation:

1. `outer.enter tx=false` runs **before** the transaction interceptor; in the demo, there is no outer transaction yet.
2. The interceptor opens a transaction; `inner.enter tx=true` and `target.tx=true` run inside the transaction.
3. **Success:** target returns; `inner.exit tx=true` prints while the transaction is still open; the interceptor commits and releases the thread-bound transaction; finally `outer.exit tx=false` prints.
4. **Failure:** target throws an exception; `inner.error tx=true` prints before rollback; the transaction interceptor rolls back and cleans up; `outer.error tx=false` prints afterward, and the caller receives the exception.
5. After the failure, A remains 90 and B remains 110; the debit of 20 was rolled back.

`TransactionSynchronizationManager.isActualTransactionActive()` only reports an active transaction on the thread; it **does not by itself prove a successful commit**. When an outer transaction exists, advice outside an inner service's transaction interceptor can still see `tx=true` because the outer transaction remains active.

## 5. Why Is the Exit Order Reversed from the Entry Order?

`@Around` advice nests like `try/finally` blocks:

```text
OuterTrace(10):
  before
  TransactionInterceptor(20):
    begin or join transaction
    InnerTrace(30):
      before
      target.transfer()
      after / error
    commit / rollback as appropriate
  after / error
```

This is **pseudocode to visualize ordering**, not Spring's internal source code: the real engine includes rollback-only handling, synchronization callbacks, `beforeCommit`, `afterCommit`, cleanup, and special logic when joining an outer transaction.

You can remember it with a diagram:

```text
Caller
  -> Outer(10) BEFORE
    -> TX(20) OPEN/JOIN
      -> Inner(30) BEFORE
        -> Target
      <- Inner(30) AFTER
    <- TX(20) COMPLETE
  <- Outer(10) AFTER
Caller
```

If `OuterTrace` uses `@Around` and **returns a result immediately without calling `proceed()`**, the transaction advisor does not run for that call. This is intentional behavior for certain cache advice; if writing custom aspects, understand the consequence.

If a retry advice outside the transaction calls `proceed()` multiple times, each invocation can pass through the transaction advisor and start an independent transaction. If the retry advice sits inside the transaction, multiple attempts can share a transaction already marked rollback-only. Choose ordering based on desired behavior, not arbitrary round numbers.

## 6. `@Before`, `@AfterReturning`, `@AfterThrowing`, and `@After`

These advice types also follow precedence along the advisor chain:

| Advice | **Outside** transaction advice | **Inside** transaction advice |
| --- | --- | --- |
| `@Before` | Runs before the interceptor starts the call's transaction | Runs after the call's transaction has started |
| `@AfterReturning` | Runs only when the inner chain returns normally; for a transaction owned by the interceptor, usually already committed | Can run when the target returns yet **before commit** |
| `@AfterThrowing` | Can observe exceptions raised from flush/commit inside the transaction interceptor | Does not see commit exceptions occurring after the inner advice already completed |
| `@After` | Runs in the finally phase after the inner transaction scope | Runs before the transaction interceptor completes its scope |
| `@Around` | Can wrap commit/rollback if it calls `proceed()` | Wraps target, yet outer commit has not run yet |

**Common mistake:** `@AfterReturning` inside a transaction logs `"SUCCESSFULLY_COMMITTED"`. At that moment the target returned normally, yet flush/commit can still fail. A more accurate log label is `"METHOD_RETURNED"`. If you want to record **a successful commit**, use Spring's commit hook (`TransactionSynchronization.afterCommit()`) or `@TransactionalEventListener(phase = TransactionPhase.AFTER_COMMIT)` where appropriate.

Even when `@AfterReturning` sits outside the transaction interceptor, if the interceptor only **joined** the caller's transaction, the outer commit still lies in the future. Distinguish an interceptor boundary from the final physical commit.

Spring also defines ordering among advice types within the **same `@Aspect`**, where `@After` has `finally`-like semantics. Do not rely on declaration order of two methods of the same `@Before` or `@Around` kind inside one aspect to force order; when control is needed, combine logic or split into separate aspects with explicit orders.

## 7. Designing Order Around Business Goals

### 7.1. Logging and profiling

If you want to measure the **entire transactional call** including synchronous commit/rollback, place profiling advice **outside** transaction advice (lower order number). Spring's official documentation shows a profiler example that starts before the transaction and finishes measuring once commit completes.

If you want to measure only the business logic inside the transaction, place profiling advice **inside** the transaction; results typically **exclude commit cost**.

| Observation goal | Suitable placement | Limitation to remember |
| --- | --- | --- |
| Method invocation duration including transaction | Outer advice | If an outer transaction already exists, it does not capture the final commit. |
| Business logic execution time | Inner advice | Excludes flush/commit after the target returns. |
| Notification only upon successful commit | `afterCommit`/transaction-bound event | Do not treat logs inside the target as proof of commit. |
| Trace ID/MDC across the entire call | Usually an outer layer | Always clean up context in `finally`. |

### 7.2. Retry

For transient errors, a common design places **retry advice outside transaction advice**, so each attempt starts a fresh transaction:

```text
Retry outer:
  attempt #1: TX begin -> target throws -> rollback
  attempt #2: TX begin -> target succeeds -> commit
```

If transaction advice sits outside retry advice, multiple attempts may share one physical transaction, even after it becomes `rollback-only`. With Spring Retry or custom retry aspects, check the **actual advisor order**, propagation, outer transactions, and whether retrying could duplicate operations.

**Crucially:** a connection drop at the exact moment of commit can leave the client uncertain whether commit succeeded; never blindly retry payment/order writes. Use an idempotency key or status check when needed.

### 7.3. Caching

If `@Cacheable` sits **outside** transaction advice and hits the cache, cache advice can return the result without running the service target or the transaction interceptor. Conversely, placing caching inside the transaction can start a transaction even when serving from cache.

`@CachePut`/`@CacheEvict` combined with `@Transactional` require careful ordering; updating or evicting cache **before the DB commits** can leave cache stale/inconsistent if the transaction rolls back. When consistency matters, use transaction-aware caches or post-commit invalidation, plus rollback integration tests.

### 7.4. Security, validation, and exception translation

Method security can involve several advisors (`@PreAuthorize`, `@PostAuthorize`, and other interceptors), with ordering governed by Spring Security configuration. Validation may run before or inside the transaction. Decide based on whether DB reads are needed, resource limits, and whether exceptions should trigger rollback.

Exception translation is also order-sensitive: if an exception is translated **before** reaching the transaction interceptor, rollback rules evaluate the translated exception; if translation sits outside, the transaction interceptor sees the underlying exception. Under default runtime-exception rollback, many cases match anyway, yet custom `rollbackFor`/`noRollbackFor` rules can behave differently. Write tests for key exception types.

### 7.5. `@Async` and reactive

`@Async` moves execution to another thread; imperative transactions are normally thread-bound. Changing order does not automatically carry transaction context to the new thread. If an async task needs a transaction, design the transaction boundary on the service invoked on the executing thread and verify the proxy properly.

Reactive transactions use `ReactiveTransactionManager` with Reactor context; do not reason using thread-bound `TransactionSynchronizationManager.isActualTransactionActive()` from the JDBC demo.

## 8. What Changes When You Change the Order?

In the demo:

```text
OuterTrace(10) -> Transaction(20) -> InnerTrace(30) -> Target
```

If you only change `@EnableTransactionManagement(order = 40)`, you get:

```text
OuterTrace(10) -> InnerTrace(30) -> Transaction(40) -> Target
```

On a fresh call with no outer transaction, `inner.enter` would now also print `tx=false`, and `inner.exit` would run after the transaction interceptor finishes. If you change the transaction order to `5`:

```text
Transaction(5) -> OuterTrace(10) -> InnerTrace(30) -> Target
```

Then both `outer.enter` and `inner.enter` sit inside the target's transaction and are expected to see `tx=true`; both exit logs run **before commit**.

These are **predictions based on precedence rules**, not stdout captured from running those two variants. You can edit one number, rerun the demo program, and compare results to verify for yourself.

There is no single optimal order for every application. Decide explicitly whether "advice must wrap the whole transaction" or "advice only operates inside the transaction", then set precedence and guard it with tests.

## 9. Inspecting the Advisor Chain in a Real Application

When logs do not match expectations, check:

1. **Is there a proxy?** Objects created with `new` bypass Spring; `this.method()` self-invocation does not trigger the inner method's own transaction advice in proxy mode.
2. **Do pointcuts match the same join point?** Two advice applying to different methods share no common chain to order.
3. **New transaction or joining transaction?** `Propagation.REQUIRED` may simply reuse an outer transaction.
4. **Are there multiple proxies or multiple framework advisors?** Ordering among infrastructure advisors must be checked on the actual chain.
5. **Can the method be proxied?** JDK proxies usually intercept interface methods, while class-based proxies have limits with `final`/`private`; design clear public methods.
6. **Are there commit failures, rollback-only flags, or callbacks?** A log showing the target returned does not prove a DB commit.

You can use AOP APIs to check whether a bean is proxied and list its advisors:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.framework.Advised;
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean(LedgerService.class);
System.out.println("isProxy=" + AopUtils.isAopProxy(bean));

if (bean instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getSimpleName()
                + " -> " + advisor.getAdvice().getClass().getSimpleName());
    }
}
```

This is an **optional illustrative snippet**; you can place it in `App.main` to explore, though it is **not part of the demo's fixed stdout**. Advisor class names may depend on Spring version. Use integration tests to verify actual business ordering rather than relying solely on advisor names.

You can raise logging for `org.springframework.transaction` in test environments to watch transaction start/completion. For "committed" events, use proper transaction synchronization; for requests with outer transactions, trace all the way to the **outermost boundary**.

## 10. Common Mistakes and How to Avoid Them

| Mistake | Consequence | Resolution |
| --- | --- | --- |
| Assuming "higher order number runs first" | Reverses the chain and mispredicts commit | Lower order number has higher precedence; first on entry, last on exit. |
| Treating `@Order` on a service as transaction order | Transaction advice is not ordered as expected | Use `@EnableTransactionManagement(order=...)`. |
| Relying on default order with equal-precedence advisors | Behavior may depend on configuration/version | Set explicit orders and test. |
| Calling `@AfterReturning` inside a transaction "committed" | Commit may fail afterward | Use `afterCommit` or accurate log names. |
| Retrying inside a transaction already rollback-only | Retries run yet final commit fails | Design attempts with fresh transactions where appropriate. |
| Forgetting `proceed()` in `@Around` | Target and inner interceptors never run | Only short-circuit intentionally and test all branches. |
| `this.inner()` expecting inner advice to run | Self-invocation bypasses proxy | Extract boundary to another Spring bean. |
| Updating cache before DB commit | Cache and DB diverge after rollback | Invalidate after commit or use transaction-aware cache. |
| Seeing `tx=true` and concluding commit succeeded | May just be an open transaction | Check after outer transaction and verify DB state. |
| Expecting `@Async` to inherit transactions | Work on another thread lacks boundary | Create transaction on the executing thread. |
| Thinking transaction order dictates SQL order | Misunderstands concurrency and locking | Distinguish AOP precedence from DB isolation and locks. |

## 11. Self-Check Questions

**Question 1.** `AuditAspect @Order(5)`, transaction advisor order 50, `MetricAspect @Order(100)`. Describe entry and exit order.

**Answer:** Entry: audit 5 -> transaction 50 -> metric 100 -> target. Exit: target -> metric 100 -> transaction 50 -> audit 5. For a new transaction owned by the interceptor, audit finishes after the interceptor completes.

**Question 2.** Why can `@AfterReturning` inside a transaction run even if the final commit fails?

**Answer:** Inner advice sees the **target returning normally**, after which the transaction interceptor performs flush/commit and may throw an exception. An outer `@AfterReturning` will not run if the transaction interceptor throws a commit error.

**Question 3.** Retry advisor order 10, transaction advice order 20. Is every attempt guaranteed a separate transaction?

**Answer:** That holds when retry calls `proceed()` through the interceptor and the interceptor **creates a new transaction per attempt**, not wrapped in an outer transaction. If an outer transaction exists or propagation differs, re-evaluate.

**Question 4.** `ServiceA` already has `@Transactional` and calls `ServiceB` `@Transactional(REQUIRED)`. Does advice outside B's interceptor run after A's transaction commits?

**Answer:** No. B normally joins A's transaction; A decides the final physical commit when A's scope completes.

**Question 5.** If transaction order changes from 20 to 5 in the demo, where do `outer.enter` and `inner.enter` sit?

**Answer:** Both sit inside the target's transaction for calls with no outer transaction. Both are expected to print `tx=true`; commit occurs after both finish.

**Question 6.** Does `@Order(10)` on an aspect advising `checkout()` cause service `sendEmail()` to run before service `reserveStock()` on different threads?

**Answer:** No. Advisor order only governs precedence within the AOP chain of join points matched by the aspect; it is not a global scheduler across tasks or threads.

## Key Takeaways

- **Lower order number = higher precedence = runs earlier on entry and later on exit.**
- `@EnableTransactionManagement(order=...)` controls the **transaction advisor**; default is `Ordered.LOWEST_PRECEDENCE`.
- `@Order` on an aspect controls the aspect's advice; sitting inside vs. outside the transaction determines whether it sees an open or completed transaction.
- When **joining an outer transaction**, the inner interceptor finishing does not mean final commit.
- Logging/profiling, retry, caching, and exception translation must be placed relative to actual transaction milestones. To act **after successful commit**, consider appropriate after-commit callbacks/events.
- Verify with proxy traces, rollback tests, DB state, and checks on both success and failure branches.

## Official Documentation

1. Spring Framework — [Advising Transactional Operations](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/applying-more-than-just-tx-advice.html): profiling example wrapping transactions.
2. Spring Framework — [Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): entry/exit precedence rules.
3. Spring Framework — [Using `@Transactional`](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): default `order` and proxy mode.
4. Spring Framework — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): self-invocation and proxy limits.
5. Spring Framework — [Declarative Transaction Implementation](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/tx-decl-explained.html): transaction interceptor.
6. Spring Framework — [Transaction-bound Events](https://docs.spring.io/spring-framework/reference/data-access/transaction/event.html): post-commit handling.
