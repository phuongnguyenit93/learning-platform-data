# Ordering Between Custom Aspects and Spring Infrastructure Advisors

## 1. Central Question

When a Spring service method simultaneously matches a custom `@Aspect` and carries `@Transactional`, `@Cacheable`, Spring Method Security, or `@Async`, **which advice executes first, which executes later, and which advice can prevent the target method from running?**

In **proxy-based Spring AOP**, multiple advisors/interceptors can participate in handling a single method call. What needs to be distinguished is not just the annotation names, but **each advisor's position in the call chain**, the "way in" / "way out" order, where short-circuiting can happen, and **the ordering mechanism of each infrastructure feature**.

For example: with a custom `@Around` audit wrapping **outside** the transaction interceptor, audit can log after `proceed()` completes **including the commit step**. By contrast, with a custom aspect placed **inside** the transaction interceptor, a "method returned" log can appear **before the transaction interceptor commits**. Thus, two "success" logs at different positions **do not carry the same meaning**.

**Scope of this lesson:** Spring `@AspectJ`/Spring AOP proxies, `@Order`/`Ordered`, transaction/cache/method-security/async advisors, and how to observe ordering accurately. Examples focus on Spring Framework without diving into AspectJ weaving or general AOP theory.

## 2. The Nature of Ordering in Spring AOP

A Spring-managed service can be exposed as a proxy. The caller invokes through the proxy reference, and Spring applies the advisors that match the method execution:

```text
Other Spring bean / caller
         |
         | workService.run("A")
         v
Spring AOP proxy
         |
         +--> Custom @Around audit            (order 10)
         |        |
         |        +--> Spring transaction advice (order 20)
         |                  |
         |                  +--> Custom @Around metric (order 30)
         |                            |
         |                            +--> target.run("A")
         |                            |
         |                            +-- return / throw
         |                  |
         |                  +-- commit / rollback
         |        |
         |        +-- audit exit
         v
Result / exception to caller
```

**Smaller order values have higher precedence** per Spring `Ordered` and `@Order`. On the way into the method, higher-precedence advisors are generally invoked **first**. On the way out, higher-precedence wrappers finish **last**, because they sit **outside** lower-precedence wrappers.

If every interceptor lets the chain continue:

```text
Audit.enter    (10)
  Tx.begin     (20)
    Metric.enter (30)
      target.run()
    Metric.exit
  Tx.commit
Audit.exit
```

With an exception triggering Spring transaction's default rollback:

```text
Audit.enter
  Tx.begin
    Metric.enter
      target.run() -> throw RuntimeException
    Metric.throw
  Tx.rollback
Audit.throw -> caller
```

This is an **illustrative diagram**, not the default order of every project. The values 10/20/30 are **explicitly chosen configurations in the demo**, not values Spring assigns automatically to transactions, security, or caching.

### Two Decisive Distinctions

1. **Matches or does not match:** pointcut of a custom `@Aspect`; `@Transactional`, `@Cacheable`, security policy annotations; method/proxy eligibility; runtime conditions. If an advisor does not match, its `order` will not make it appear.
2. **Once matched, who wraps whom:** Spring applies precedence/order; however, certain infrastructure features use their own advisor/BeanPostProcessor addition mechanisms and may create multiple proxy layers. Do not assume every `order` setting is a number on a single flat list.

An outermost advisor can **omit calling downstream** (`@Around` returning early, cache hit, security denial, exception). Thus, a custom aspect deeper in the chain may never see the invocation even when its pointcut matches.

## 3. @Order on Custom Aspects: Meaning and Limits

Example:

```java
@Aspect
@Order(10)
public class AuditAspect {
    @Around("execution(public * com.example.work..*Service.*(..))")
    public Object observe(ProceedingJoinPoint pjp) throws Throwable {
        System.out.println("audit:enter");
        try {
            Object result = pjp.proceed();
            System.out.println("audit:return");
            return result;
        } catch (Throwable error) {
            System.out.println("audit:throw");
            throw error;
        }
    }
}
```

This is an **illustrative sample**, requiring imports, Spring bean registration, and an appropriate application context. `@Order(10)` sets precedence for the **aspect bean/advice** Spring AOP builds from this class. Another aspect with `@Order(30)` typically has lower precedence and is called later on the way in.

Rules:

- Spring allows `@Order(int)` or implementing `org.springframework.core.Ordered` on the aspect.
- **Smaller numbers have higher precedence.** `Ordered.HIGHEST_PRECEDENCE` and `LOWEST_PRECEDENCE` are the two bounds.
- Higher precedence runs **earlier on the way in, later on the way out** for chained wrappers.
- If two aspects share the same order and order truly matters, **do not rely on bean registration order or class names**.
- `@Order` does not change pointcut expressions, does not turn `@Aspect` into a Spring bean by itself, and does not fix self-invocation.
- When multiple advice methods **of the same type in the same `@Aspect`** match, do not assume Java declaration order is fixed. Use separate aspect classes or combine ordered logic in a single advice method.

**Important:** precedence in Spring does not mean "audit always sees every call." Other cache/security/async/transaction advisors can terminate early, change outcomes, or switch threads.

## 4. What Is an Infrastructure Advisor in This Lesson?

Many Spring features are implemented via **AOP advisor/interceptor infrastructure** (in proxy mode). Do not equate everything with an `@Aspect`-annotated class:

| Feature | Typical Activation / Configuration | Key Advisor / Interceptor | Implication When Coexisting With Custom Aspects |
| --- | --- | --- | --- |
| Declarative transaction | `@EnableTransactionManagement` or corresponding Spring Boot transaction auto-configuration | Transaction advisor / `TransactionInterceptor` | Starts/joins transaction, decides commit/rollback based on the outcome it observes. |
| Spring caching | `@EnableCaching` or Boot caching configuration when enabled | Cache advisor / `CacheInterceptor` | Cache hit can return immediately without calling the target or downstream interceptors. |
| Method security | Spring Security's `@EnableMethodSecurity` | Authorization interceptors for `@PreAuthorize`, `@PostAuthorize`, filters, etc. | Can deny before the method, check results after the method, or filter args/results per policy. |
| Async execution | `@EnableAsync` | `AsyncAnnotationAdvisor`/`AnnotationAsyncExecutionInterceptor`, typically added via `AsyncAnnotationBeanPostProcessor` | Can hand execution off to another executor/thread; its `order` means something different from transaction/cache in configuration. |
| Custom `@Aspect` | `@Aspect` + Spring bean + `@EnableAspectJAutoProxy` / Boot AOP | Advisors generated from `@Around`, `@Before`, ... | Observes or alters calls/results; precedence set on the aspect with `@Order`/`Ordered`. |

**Common prerequisite:** each feature must be enabled in the right Spring context, the method/annotation must qualify, and the call must go through the Spring proxy. Having `@EnableAspectJAutoProxy` **does not automatically enable** caching, transaction management, or Spring Method Security. `@Transactional` also requires a `PlatformTransactionManager` or matching transactional infrastructure. Each feature has its own prerequisites.

## 5. Transaction Advisor: An Example Where Order Can Be Directly Controlled

Spring Framework's `@EnableTransactionManagement` has an `order` attribute for the **transaction advisor**:

```java
@Configuration
@EnableTransactionManagement(order = 20)
@EnableAspectJAutoProxy(proxyTargetClass = true)
class WorkConfiguration {
    // @Bean PlatformTransactionManager transactionManager() ...
    // @Bean custom @Aspect beans ...
}
```

This is an **illustrative configuration snippet**, not a standalone runnable project. Key points:

- `@EnableTransactionManagement(order=20)` sets the priority position of the **transaction advisor** when matching together.
- By default, `@EnableTransactionManagement.order` is `Ordered.LOWEST_PRECEDENCE`. The default does not guarantee transactions wrap outside a custom `@Order(10)` or other advisors with the same precedence; check specifically.
- `@Order(10)` on a custom aspect has higher precedence than a transaction advisor of order 20, **wrapping outside the transaction interceptor**.
- `@Order(30)` on a custom aspect sits inside the order-20 transaction advisor accordingly.
- Transaction semantics and rollback rules remain governed by Spring transaction infrastructure. `@Order` does not create database connections or guarantee successful commits.
- Spring `@Transactional` follows proxy semantics and does not apply automatically when a target calls `this.innerTransactionalMethod()`.

### Observing "After Commit" Properly

Suppose:

```text
@Order(10) Audit.enter
  TransactionInterceptor.begin
    @Order(30) Metrics.enter
      Target returns normally
    @Order(30) Metrics.return   <-- typically before commit
  TransactionInterceptor.commit
@Order(10) Audit.return        <-- after proceed() through tx interceptor finishes
```

In this model, when `AuditAspect` truly sits **outside** the transaction advisor and `proceed()` goes through it, by the time `AuditAspect` receives the normal result the inner transaction interceptor has already handled commit/cleanup as configured. Still, do not generalize this into:

- Every `@AfterReturning` in every Spring aspect being an **after-commit** event;
- A caller's/outer transaction also having committed;
- `REQUIRES_NEW`/`REQUIRED`/nested transactions all sharing the same timing;
- Events processed on another thread having finished;
- Database/business side effects achieving durability under every storage/configuration setup.

If you need processing **only after a successful commit** in the relevant transaction, use Spring `TransactionSynchronization` or `@TransactionalEventListener(phase = AFTER_COMMIT)`, with clear contracts and configuration.

### A `@Transactional` Method Returning Can Still Roll Back

A method may return normally while the transaction interceptor later throws an exception during commit, or the transaction was already marked rollback-only and ends with `UnexpectedRollbackException`. If a metrics aspect **sits inside** the transaction interceptor, it may print `metric:return` before a rollback or commit failure. If an audit aspect **sits outside**, it may see an exception from transaction completion instead of the target's normal return.

**Therefore:** distinguish **target returned** from **transactional invocation completed**.

## 6. @EnableCaching.order and the Risk of Cache Hits Bypassing Advice

Spring caching allows:

```java
@Configuration
@EnableCaching(order = 20)
class CacheConfiguration {
    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("catalog");
    }
}
```

This is an **illustrative snippet**, requiring imports for `CacheManager` and `ConcurrentMapCacheManager` plus appropriate Spring beans. `@EnableCaching.order` sets the order of the **cache advisor**; the default is `Ordered.LOWEST_PRECEDENCE` in Spring Framework.

Suppose `CatalogService.find(..)` has `@Cacheable("catalog")` and a custom `@Around`:

| Assumed Order Chain | Cache Miss | Cache Hit |
| --- | --- | --- |
| Custom audit **outside** cache advisor | Audit.enter → cache → target → cache → audit.exit | Audit.enter → cache returns cached value → audit.exit; target does not run. |
| Cache advisor **outside** custom audit | Cache → audit.enter → target → audit.exit → cache | Cache returns cached value; **custom audit is not called**. |

**This is a critical case:** "Missing audit logs" does not necessarily mean a missing pointcut. A cache hit can **short-circuit before entering the advice** if the advisors are positioned that way.

However, this **does not mean** placing audit outside cache automatically makes every success metric accurate. On a cache hit, audit may measure a **proxy request** rather than a **target business execution**. Name metrics to match the exact quantity measured.

### Caching and Transactions Both Using LOWEST_PRECEDENCE

By default, both the transaction advisor and caching advisor can use `Ordered.LOWEST_PRECEDENCE`. If business behavior depends on which wraps which, **do not treat a tie as a contracted order**. Configure orders intentionally and integration-test:

- Does a cache hit enter a transaction?
- Is cache put/evict executed before or after which outcome?
- If commit fails, does the cache hold stale data?
- Can an advisor replace return values or exceptions?

Those final questions require examining the specific cache manager, transaction semantics, event handling, and feature integrations; a single `@Order` number cannot solve DB-cache consistency by itself.

## 7. Spring Security Method Advisors: Do Not Apply the Same Order Formula Blindly

Spring Security Method Security, when enabled with `@EnableMethodSecurity`, provides **multiple specialized advisors/interceptors**, such as `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter`. They have **default positions in the chain**, rather than one generic "SecurityAspect" with a single order number.

In modern Spring Security documentation, examples show `@PreFilter` at precedence 100 and `@PreAuthorize` at 200; other advisors have their corresponding orders and may be configurable. When versions or configurations change, **read the docs for the exact Security version running**; do not copy numbers from a README as immutable constants for all versions.

`@EnableMethodSecurity(offset = ...)` (in supported versions) can shift the precedence positions of method-security interceptors as configured, yet this is a **Spring Security infrastructure rule**, not advice to arbitrarily tweak offsets to work around proxy bugs.

### Should Security Sit Before or After a Custom @Around?

Suppose a custom `@Around` has higher precedence than the `@PreAuthorize` advisor:

```text
CustomAround.enter
   SecurityAdvisor checks permission
      -> DENIED (throw)
CustomAround.catch/exit
Caller receives denial
```

If the custom aspect **skips `proceed()`** and returns a fallback `"ok"`, the **inner** security advisor **may never execute**. This is especially dangerous if custom advice is used for caching or degradation fallbacks.

If the security advisor wraps outside the custom aspect, authorization can deny **before** the custom aspect receives the invocation. Missing audit logs in the custom aspect on denial may be expected behavior, not security failing to run.

**For security:** rather than only asserting a log sequence, test that **an unauthorized user cannot cause side effects**, including through cache hits, fallbacks, exceptions, async, and other entry paths. Never use arbitrary custom aspect ordering as a substitute for proper method security configuration.

### Post-Authorization Differs from Pre-Authorization

`@PostAuthorize` needs to inspect the result to enforce policy after invocation. Its position and outcome semantics can differ from `@PreAuthorize`; thus do not generalize that "security must always run before the target." A method can finish executing and then be rejected by post-authorization. If the method writes data beforehand, transactions and side effects must be designed around the actual security policy.

## 8. @EnableAsync.order Is Not Like Transaction/Cache Advisor Order

**This is an easy Spring-specific trap.** With:

```java
@EnableAsync(order = Ordered.LOWEST_PRECEDENCE)
```

The `order` attribute on `@EnableAsync` refers to **the application order of `AsyncAnnotationBeanPostProcessor`**, which **does not directly mean the same thing** as `@EnableTransactionManagement(order=...)` or `@EnableCaching(order=...)`.

Spring documentation describes the default `LOWEST_PRECEDENCE` so the Async post-processor runs after other post-processors and can add the async advisor to an existing proxy instead of causing unnecessary double-proxying. Furthermore, `AsyncAnnotationBeanPostProcessor` tends to **place the async advisor ahead of existing advisors** so execution switches to async early in the chain.

Therefore, **do not make a mechanical comparison**:

```text
@Order(10) of custom aspect
vs.
@EnableAsync(order=20)
=> custom aspect definitely wraps outside async interceptor
```

That conclusion **is not guaranteed**, because the two order values here can belong to **different mechanisms** (advisor precedence vs. `BeanPostProcessor` order). When you need to know whether audit code runs on the **caller thread or executor thread**, inspect the actual proxy/advisor structure and test thread names:

- Caller invokes an `@Async` method through the Spring proxy.
- The async interceptor can submit downstream execution to an executor.
- An aspect outside async interception may log at **submission time**, before task completion.
- An aspect inside async execution may log on the worker thread and observe target execution at a different time.
- `CompletableFuture<T>`/`Future<T>` is a handle; a normal return of the wrapper does not guarantee computation succeeded.
- `@EnableAsync` requires an appropriate executor/configuration. Self-invocation (`this.asyncMethod()`) still bypasses the proxy in default proxy mode.

**Do not treat log order across two threads as proof of advisor order within a single synchronous invocation.** Use correlation IDs, completion synchronization, and actual proxy ordering.

## 9. Quick Reference Table of Ordering Mechanisms

| Configuration | What Does It Control? | Default / Semantics to Remember |
| --- | --- | --- |
| `@Order(10)` on Spring `@Aspect` | Precedence of the aspect/advice in the chain | Smaller number means higher precedence; enters first, exits last. |
| `Ordered.getOrder()` on aspect | Precedence read from the bean instance | Same rule: smaller numbers take priority. |
| `@EnableTransactionManagement(order=...)` | Order of the transaction advisor | Defaults to `LOWEST_PRECEDENCE`. |
| `@EnableCaching(order=...)` | Order of the cache advisor | Defaults to `LOWEST_PRECEDENCE`. |
| `@EnableMethodSecurity(offset=...)` | Shifts precedence of the method-security interceptor group in supported versions | Multiple distinct advisors exist; check Spring Security version and actual advisor order. |
| `@EnableAsync(order=...)` | Application order of the Async annotation **BeanPostProcessor** | **Not synonymous** with advisor order; the async advisor may be placed ahead of existing advisors. |
| `@Transactional(propagation=...)` | Transaction participation/creation semantics | **Not** a parameter for choosing AOP advisor position. |
| `@Order` on a normal service class | Bean order in certain Spring collections/processes | Does not automatically order all interceptors on that service by that number. |

When nested proxies or separate post-processors exist, do not force all order settings into a single global sort. Inspect the actual injected instance and advisor/proxy chain.

## 10. Runnable Example: Custom Aspects Flanking a Transaction Advisor

The Spring Framework demo below **uses transaction infrastructure solely** to demonstrate ordering reproducibly. It needs no database: a `TraceTransactionManager` simulates transaction boundaries and **prints begin/commit/rollback events**. This manager **does not manage real resources** and must **never be used in production**; its sole purpose is to observe the Spring transaction interceptor's order.

Configuration:

- Custom `OuterAuditAspect`: `@Order(10)`.
- `@EnableTransactionManagement(order=20)`: transaction advisor.
- Custom `InnerMetricAspect`: `@Order(30)`.
- `WorkService` has two `@Transactional` methods: one returns normally, one throws `IllegalStateException`.
- All beans are created by Spring and method calls go through a class-based proxy.

Environment: **Java 17+**, **Spring Framework 6.2.19**, **AspectJ Weaver 1.9.25.1**, Gradle. This is plain Spring Framework with no Boot auto-configuration dependencies.

### 10.1. Structure

```text
spring-advisor-order-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/advisororder/
    ├── AppConfig.java
    ├── WorkService.java
    ├── OuterAuditAspect.java
    ├── InnerMetricAspect.java
    ├── TraceTransactionManager.java
    └── Main.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-advisor-order-demo'
```

**`build.gradle`**

```gradle
plugins {
    id 'java'
    id 'application'
}

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.19'
    implementation 'org.springframework:spring-aop:6.2.19'
    implementation 'org.springframework:spring-tx:6.2.19'
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.advisororder.Main'
}
```

Spring `spring-tx` provides `@Transactional`, `@EnableTransactionManagement`, and the transaction interceptor; `spring-context` provides context/Java config. `aspectjweaver` is used for Spring `@AspectJ` pointcut parsing and does **not** automatically enable AspectJ weaving.

### 10.2. Target Bean With Two @Transactional Methods

**`WorkService.java`**

```java
package com.example.advisororder;

import org.springframework.transaction.annotation.Transactional;

public class WorkService {
    @Transactional
    public String ok(String id) {
        System.out.println("target:ok");
        return "done:" + id;
    }

    @Transactional
    public String fail() {
        System.out.println("target:fail");
        throw new IllegalStateException("boom");
    }
}
```

The target class/methods are non-final, public, and free of self-invocation. `@Transactional` on each method ensures the transaction advisor has a reason to match both; custom aspects match them too.

### 10.3. Event-Recording Transaction Manager Without a DB

**`TraceTransactionManager.java`**

```java
package com.example.advisororder;

import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.AbstractPlatformTransactionManager;
import org.springframework.transaction.support.DefaultTransactionStatus;

public class TraceTransactionManager
        extends AbstractPlatformTransactionManager {

    @Override
    protected Object doGetTransaction() {
        return new Object();
    }

    @Override
    protected void doBegin(
            Object transaction, TransactionDefinition definition) {
        System.out.println("tx:begin");
    }

    @Override
    protected void doCommit(DefaultTransactionStatus status) {
        System.out.println("tx:commit");
    }

    @Override
    protected void doRollback(DefaultTransactionStatus status) {
        System.out.println("tx:rollback");
    }
}
```

`AbstractPlatformTransactionManager` handles the transaction demarcation flow; four hooks are implemented to create a minimal transaction object and log events.

**Intentional limitations:** the manager does not bind a JDBC connection or resource to the thread, performs no real database commit/rollback, and does not represent a storage engine's rollback capability. Because `doGetTransaction()` creates a new object and never reports an existing transaction, the demo targets only **isolated external invocations**. Do not use this implementation to verify DB propagation, nested transactions, isolation, read-only semantics, or recovery.

In real applications, use `DataSourceTransactionManager`/`JdbcTransactionManager`, `JpaTransactionManager`, or the appropriate manager and verify database state.

### 10.4. High-Precedence Audit Aspect Outside the Transaction

**`OuterAuditAspect.java`**

```java
package com.example.advisororder;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(10)
public class OuterAuditAspect {
    @Around("execution(public * com.example.advisororder.WorkService.*(..))")
    public Object audit(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();
        System.out.println("audit:enter:" + method);
        try {
            Object result = pjp.proceed();
            System.out.println("audit:return:" + method);
            return result;
        } catch (Throwable error) {
            System.out.println("audit:throw:" + method);
            throw error;
        }
    }
}
```

`@Order(10)` is smaller than the transaction advisor's order 20: audit enters before `tx:begin`; when `proceed()` completes normally, it prints `audit:return` after `tx:commit` in this setup. `throw error` preserves the original exception.

### 10.5. Low-Precedence Metrics Aspect Inside the Transaction

**`InnerMetricAspect.java`**

```java
package com.example.advisororder;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;

@Aspect
@Order(30)
public class InnerMetricAspect {
    @Around("execution(public * com.example.advisororder.WorkService.*(..))")
    public Object metric(ProceedingJoinPoint pjp) throws Throwable {
        String method = pjp.getSignature().getName();
        System.out.println("metric:enter:" + method);
        try {
            Object result = pjp.proceed();
            System.out.println("metric:return:" + method);
            return result;
        } catch (Throwable error) {
            System.out.println("metric:throw:" + method);
            throw error;
        }
    }
}
```

Here, `metric:return` happens **before `tx:commit`**. Consequently, if commit fails, a "target returned" event in metrics is insufficient to conclude the transaction succeeded. This aspect intentionally only observes and preserves results/exceptions without short-circuiting or retrying.

### 10.6. AppConfig: Enabling Both Spring AOP and Transaction Management

**`AppConfig.java`**

```java
package com.example.advisororder;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
@EnableTransactionManagement(order = 20)
public class AppConfig {
    @Bean
    WorkService workService() {
        return new WorkService();
    }

    @Bean
    OuterAuditAspect outerAuditAspect() {
        return new OuterAuditAspect();
    }

    @Bean
    InnerMetricAspect innerMetricAspect() {
        return new InnerMetricAspect();
    }

    @Bean
    PlatformTransactionManager transactionManager() {
        return new TraceTransactionManager();
    }
}
```

No `@ComponentScan` is needed because beans are created via `@Bean`. The explicit `transactionManager` name helps Spring locate the manager bean for declarative transactions. `@EnableAspectJAutoProxy` and `@EnableTransactionManagement` participate in the proxy/advisor infrastructure of the same context; there is no self-invocation.

### 10.7. Main: Observing the Real Call Path Through the Spring Proxy

**`Main.java`**

```java
package com.example.advisororder;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            WorkService service = context.getBean(WorkService.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("case=ok");
            System.out.println("result=" + service.ok("A"));

            System.out.println("case=fail");
            try {
                service.fail();
            } catch (IllegalStateException error) {
                System.out.println("caught=" + error.getMessage());
            }
        }
    }
}
```

Run at the project root with JDK 17+ and Gradle installed:

```bash
gradle run --quiet
```

If a Gradle Wrapper is present: `./gradlew run --quiet` (Linux/macOS) or `gradlew.bat run --quiet` (Windows).

**The demo's `System.out` lines in order** (excluding external JVM/Gradle/Spring logging):

```text
proxy=true
case=ok
audit:enter:ok
tx:begin
metric:enter:ok
target:ok
metric:return:ok
tx:commit
audit:return:ok
result=done:A
case=fail
audit:enter:fail
tx:begin
metric:enter:fail
target:fail
metric:throw:fail
tx:rollback
audit:throw:fail
caught=boom
```

### 10.8. Proving Three Positions in One Invocation

Normal case:

1. `audit:enter:ok` before `tx:begin` because the `@Order(10)` aspect sits **outside** the order-20 transaction advisor.
2. `tx:begin` before `metric:enter:ok` because the transaction advisor has higher precedence than `@Order(30)` metrics.
3. `metric:enter:ok` before `target:ok` because the target sits deepest.
4. `metric:return:ok` after target yet **before the commit hook**: at this point the transaction interceptor has not finished.
5. `tx:commit` prints after downstream returns normally.
6. `audit:return:ok` appears after transaction interceptor `proceed()` completes.
7. Caller receives `result=done:A`.

Exception case:

1. Entry remains `audit → tx:begin → metric → target`.
2. `target:fail` throws `IllegalStateException`.
3. `metric:throw:fail` sees the exception before the transaction interceptor handles rollback.
4. `tx:rollback` is called due to the runtime exception (and default rollback rules).
5. `audit:throw:fail` sees the exceptional outcome of the transaction-wrapped invocation.
6. Caller catches `IllegalStateException("boom")`.

**Boundary of the demo:** `tx:commit`/`tx:rollback` are events printed by a **dummy transaction manager**, not proof of a DB commit/rollback. What is demonstrated is **advisor execution ordering**. For real data, use a real manager and database integration tests.

### 10.9. What If `@EnableTransactionManagement(order=20)` Is Omitted?

By default, the transaction advisor usually uses `Ordered.LOWEST_PRECEDENCE`. Then `@Order(10)` and `@Order(30)` on the two custom aspects have higher precedence than the transaction advisor in numeric order: both can **wrap outside transaction interception**, so `metric:return` can appear **after the commit hook**, no longer matching the sequence in section 10.7.

That is the point of this lesson: **never assume "transactions always wrap every custom aspect."** If ordering must be part of the contract, configure `order` intentionally and test.

Do not remove `@EnableTransactionManagement(order=20)` in the demo code while expecting the exact same stdout; whenever order changes, recalculate and re-verify.

## 11. How to Inspect the Advisors Actually Attached to a Proxy

### 11.1. AopUtils Proves a Proxy Exists, Not Its Order

```java
Object bean = context.getBean("workService");
System.out.println(AopUtils.isAopProxy(bean));
```

This is an illustrative snippet using the demo's Spring context. A `true` result confirms the bean is proxied, yet **does not show** which advisor sits ahead of or behind another.

### 11.2. Inspecting `Advised.getAdvisors()`

Many Spring AOP proxies implement `org.springframework.aop.framework.Advised`. You can use:

```java
Object bean = context.getBean("workService");

if (bean instanceof org.springframework.aop.framework.Advised advised) {
    for (var advisor : advised.getAdvisors()) {
        System.out.println(advisor.getClass().getName()
                + " -> " + advisor.getAdvice().getClass().getName());
    }
}
```

This is an **illustrative diagnostic snippet**; do not add it to `Main` if you want to keep the stdout in section 10.7. `Advised.getAdvisors()` shows the advisors on the proxy being inspected; if nested proxies exist, trace the structure carefully instead of assuming every advisor lives in one list.

Notes:

- `getAdvisors()` only lists components attached to the proxy; pointcuts may still have **runtime matching conditions**.
- An interceptor can short-circuit so an inner advisor **never receives the invocation**, even though it appears in the list.
- `Advised` is an infrastructure API; do not mutate the advisor list in production just to force order.
- Some proxy configs are `frozen`/unmodifiable; reading for diagnosis is usually safer than mutating.
- Other beans or a child `ApplicationContext` can use different advisor infrastructure; inspect **the exact bean injected into the caller**.

### 11.3. Use an Event Recorder Instead of println in Tests

You can replace `System.out` with a Spring bean `EventRecorder`:

```java
public final class EventRecorder {
    private final java.util.List<String> events =
            new java.util.concurrent.CopyOnWriteArrayList<>();

    public void record(String event) {
        events.add(event);
    }

    public java.util.List<String> snapshot() {
        return java.util.List.copyOf(events);
    }
}
```

This is **separate illustrative code**; to integrate into the demo, define `@Bean EventRecorder` and inject it into both aspects, the target, and the dummy manager. Synchronous ordering can be asserted via `List<String>`; do not mix events from multiple threads/requests into one global sequence and infer advisor precedence from that.

## 12. Common Design Mistakes

### 12.1. "`@Order(0)` Is Always Outside Everything"

False. Some infrastructure advisors have `HIGHEST_PRECEDENCE` or numeric orders less than 0; the async `BeanPostProcessor` uses a different mechanism for adding advisors; multiple proxies can be nested. `@Order(0)` does not automatically guarantee a custom aspect wraps Spring Security/cache/transactions in every environment.

**Right approach:** use explicit configured orders, inspect advisors/proxies, and test.

### 12.2. Using Transaction Order to Fix Self-Invocation

`@Transactional` on `inner()` is bypassed if `outer()` on the same target calls `this.inner()`. Changing `@EnableTransactionManagement(order=5)` does not create a proxy hop. Extract a collaborator bean and call through the injected Spring proxy, or choose the right operation boundary.

### 12.3. Expecting an Unenabled Feature to Appear in the Chain

`@Aspect` does not automatically enable `@Transactional`, `@Cacheable`, `@Async`, or Method Security. Each feature needs its own activation, required dependencies, and infrastructure beans.

### 12.4. Thinking `@Order` Controls Commit

`@Order` controls relative interceptor positions; commit/rollback also depends on transaction semantics, propagation, rollback rules, manager implementation, and exceptions/outcomes. Order cannot replace business transaction contracts.

### 12.5. Mistaking a Cache Hit for Missing Advice

When the cache advisor sits outside, it can return from cache and keep an inner custom aspect from running. Count proxy invocations, cache hits, and target executions **separately** to interpret metrics accurately.

### 12.6. Security Advisor Sitting Inside a Short-Circuiting `@Around`

A custom `@Around` returning early without `proceed()` can bypass downstream method security checks. Unless explicitly intended, this is a serious security bug; never return a fallback `"ok"` for authorization exceptions.

### 12.7. Using `@EnableAsync(order=...)` as If It Were `@Order(aspect)`

The `order` attribute on `@EnableAsync` is a `BeanPostProcessor` order. Comparing it directly against `@Order` on a custom aspect to predict execution threads is wrong. Check `AsyncAnnotationBeanPostProcessor`, the proxy chain, and actual behavior.

### 12.8. Two Advisors Both Having `LOWEST_PRECEDENCE`

Do not claim transactions always run before caching or vice versa solely from two equal default order values. When behavior depends on order, configure explicitly, regression-test, and verify the context properly enabled both features.

### 12.9. Calling an Advisor Getter "Proof of Advising"

`getAdvisors()` shows the proxy contains the advisor; it does not guarantee a runtime call matches a dynamic pointcut or reaches an advisor deep in the chain. You need event traces capturing method/args/outcome.

### 12.10. Fake Success When Outer Advice Swallows an Exception

```java
@Around("execution(* com.example.advisororder.WorkService.*(..))")
public Object unsafe(ProceedingJoinPoint pjp) {
    try {
        return pjp.proceed();
    } catch (Throwable error) {
        return null; // can hide rollback/security/caching failure
    }
}
```

This is an **illustrative anti-pattern**, not in the runnable demo. If an inner transaction advisor already rolled back, outer advice returning `null` can mislead the caller into thinking it got a normal result. If it sits inside the transaction, the outcome the transaction advisor sees becomes a normal return. Never guess commit consequences without checking advisor positions and testing real transactions.

## 13. Quick Debugging Workflow on Real Spring Systems

### Step 1 — Pin Down the Exact Entry Method and Call Path

Note which Spring bean is injected into the caller, the method signature, target annotations, and where the call originates. Confirm no raw `new` object or self-invocation is involved.

### Step 2 — List Features Actually Enabled

Check custom `@Aspect` beans, `@EnableAspectJAutoProxy`/Boot AOP, `@EnableTransactionManagement`, `@EnableCaching`, `@EnableAsync`, `@EnableMethodSecurity`, and corresponding manager/executor/security config beans. Do not treat an annotation in source code as proof that its advisor is registered.

### Step 3 — Document Each Ordering Mechanism

Build a table for the project: aspect `@Order`, transaction advisor `order`, cache advisor `order`, security interceptors/offset, and async `BeanPostProcessor`/advisor placement. When defaults use `LOWEST` values, do not assume a tied order.

### Step 4 — Observe Actual Order in a Single Invocation

Instrument `enter`, `target`, `return/throw`, and `commit/rollback` with a test recorder. For async, attach correlation IDs and synchronize futures when asserting. Do not treat aggregate multithreaded log order as a single call chain.

### Step 5 — Test Short-Circuiting

Test cache hits, denied permissions, `@Around` skipping `proceed()`, target exceptions, and commit exceptions. Each branch can stop at a different advisor.

### Step 6 — Verify Business Outcomes

If guaranteeing transactions, check DB state and synchronization callbacks; if guaranteeing authorization, prove unauthorized callers cause no side effects; if guaranteeing cache correctness, test stale caches, evictions, and concurrent calls.

### Step 7 — Lock Behavior with Integration Tests

Write tests running on exact production Spring/Boot/Security versions and proxy modes. Avoid hardcoding a "universal order" from documentation across projects with different infrastructure.

## 14. Recommended Test Cases

| Case | What to Assert | Why |
| --- | --- | --- |
| Custom outer aspect, transaction advisor, custom inner aspect | `outer.enter → tx.begin → inner.enter → target → inner.exit → tx.commit → outer.exit` | Confirms precedence and nesting. |
| Target throws RuntimeException | Inner throw → rollback → outer throw → caller receives error | Confirms exceptional flow and default rollback behavior. |
| Target returns yet commit fails | Outer sees exception after tx commit attempt; inner logged return | Avoids confusing target success with a committed transaction. |
| Cache miss | Target runs, cache populates as configured | Avoids confusing cache advisor with custom aspect. |
| Cache hit | Target does not run; outer vs. inner custom aspects differ | Accurately counts proxy calls vs. target executions. |
| Method security deny | Target produces no side effects beyond policy | Proves security advisor is not bypassed by custom short-circuiting. |
| Async completion | Caller thread vs. worker thread, future failure | Distinguishes advisor order from BeanPostProcessor/threading. |
| Self-invocation | Inner method advice does not appear automatically | Confirms Spring proxy boundary. |
| Two aspects with same order | Do not assert uncontracted order | Avoids brittle tests. |
| JDK vs. CGLIB proxy | Methods are exposed/overridable | Avoids blaming ordering when interception does not occur. |

### Simple Regression Test for the Demo

An integration test can replace console prints with a recorder and assert ordered events after calling `ok("A")`:

```java
java.util.List<String> expected = java.util.List.of(
    "audit:enter:ok",
    "tx:begin",
    "metric:enter:ok",
    "target:ok",
    "metric:return:ok",
    "tx:commit",
    "audit:return:ok"
);
```

This is **illustrative test data**, requiring `EventRecorder` wired into the components to capture actual events. Do not try asserting this list from `System.out` when the app has concurrent multithreaded logging.

More importantly, with a real transaction manager, test database/state outcomes rather than using `tx:commit` from a dummy manager to claim business correctness.

## 15. Spring Boot and Scoping Order Properly

With Spring Boot having Spring AOP auto-configuration and appropriate starters:

- Custom `@Aspect` classes still must become Spring beans via `@Component`/`@Bean`.
- `@Order` still determines relative precedence between custom aspects and advisors in the same chain.
- `@Transactional`, `@Cacheable`, `@Async`, and method security have their own activations/configurations; Boot does not activate every feature just because the AOP starter is present.
- Do not override Spring Framework versions in a Boot project against the Boot BOM. Resulting advisors/proxies can be affected by auto-configuration order and other `BeanPostProcessor`s.
- Spring Boot 3.x typically uses `spring-boot-starter-aop`, while Spring Boot 4.x uses `spring-boot-starter-aspectj` when the matching AspectJ starter is needed. Those two options are **by major version**, not copied together.
- `spring.aop.proxy-target-class` affects class proxy vs. interface proxy selection. `final` classes/methods and interface method exposure must be checked, yet switching proxy mode **does not fix self-invocation**.
- For Spring Security, consult documentation for the project's exact version; `@EnableMethodSecurity(offset=...)` is an ordering policy for Security advisors in supported versions, not a generic "how to enable AOP" setting.

**Important point:** `@EnableTransactionManagement(order=20)`/`@Order(10)`/`@Order(30)` in this README illustrate one specific setup. In production, never copy those numbers blindly without verifying how they interact with advisors from your libraries.

## 16. Application Checklist

- [ ] Confirmed custom aspects and target beans are Spring-managed, and AOP proxying is active?
- [ ] Are transaction/cache/security/async features **enabled independently** with appropriate managers/executors/configs?
- [ ] Do you know whether each `order` belongs to an **aspect, advisor, or BeanPostProcessor**?
- [ ] Do `@Order` values on custom aspects have distinct numeric precedence without tying advisors that require ordering?
- [ ] Understood that smaller numbers mean higher precedence, **entering first and exiting last** in nested interceptor wrappers?
- [ ] Checked transaction/cache `LOWEST_PRECEDENCE` defaults instead of assuming transactions always sit outside?
- [ ] Avoided comparing `@EnableAsync.order` directly against aspect `@Order`?
- [ ] When method security is present, checked advisors/offsets on the actual Spring Security version?
- [ ] Avoided treating an inner aspect's normal return as equivalent to transaction committed?
- [ ] Accounted for cache hits/security denials short-circuiting and skipping advisors deeper in the chain?
- [ ] Checked that `@Around` does not skip `proceed()` or swallow security/transaction exceptions outside policy?
- [ ] Checked self-invocation, `new` objects, `final` methods, and JDK/CGLIB proxies when advice is missing?
- [ ] Diagnosed actual `Advised.getAdvisors()` / event recorder instead of only `AopUtils.isAopProxy=true`?
- [ ] Written integration tests covering success, failure, commit failure, rollback, cache hit, access denial, and async completion if used?
- [ ] Avoided turning multithreaded log order into claims about single-invocation advisor ordering?
- [ ] Treated order/configuration changes as behavioral changes backed by regression tests?

**Key takeaway:** In Spring AOP, **the order between custom `@Aspect` beans and infrastructure advisors can change what each advice actually observes**: target return, transaction commit/rollback, cache hit, security denial, or async scheduling. Smaller `@Order` numbers carry higher precedence, yet **not every `order` setting refers to the same kind of advisor number**; in particular, `@EnableAsync.order` belongs to a `BeanPostProcessor`. The right approach is setting order intentionally on features that support it, inspecting Spring proxies/advisors, and locking behavior with integration tests.

## Official References

- [Spring Framework 6.2 — Advice Ordering in @AspectJ](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — Advising Transactional Operations](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/applying-more-than-just-tx-advice.html)
- [Spring Framework 6.2 — @Transactional: proxy mode, order, and rollback](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/declarative/annotations.html)
- [Spring Framework 6.2 — Annotation-driven Caching: @EnableCaching and advisor order](https://docs.spring.io/spring-framework/reference/6.2/integration/cache/annotations.html)
- [Spring Framework 6.2 — AsyncAnnotationBeanPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/AsyncAnnotationBeanPostProcessor.html)
- [Spring Framework 6.2 — @EnableAsync and BeanPostProcessor order](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Security — Method Security: advisor ordering and offset](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html)
- [Spring Framework 6.2 — Proxying Mechanisms and self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
