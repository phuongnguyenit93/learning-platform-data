# Avoiding Swallowing Exceptions or Returning Out-of-Contract Default Values in Spring AOP @Around

## 1. The Problem: Advice Can Alter a Spring Service's Contract

`@Around` is the **Spring AOP advice type using @AspectJ syntax** with the authority to wrap a proxied method execution, call or skip `ProceedingJoinPoint.proceed()`, observe the outcome, and ultimately decide **what value or exception the caller receives**.

This power is useful for measuring latency, recording audit trails, implementing retries, or providing a designed fallback mechanism. Yet it also easily introduces silent bugs: a `catch` block inside the advice logs and returns `null`, `0`, or `new Object()`, turning a **real failure** into a **normal return** or breaking the method's return type.

Contract-breaking example:

```java
@Around("execution(* com.example.orders.OrderService.submit(..))")
public Object unsafe(ProceedingJoinPoint pjp) {
    try {
        return pjp.proceed();
    } catch (Throwable error) {
        System.err.println(error.getMessage());
        return null; // Swallows the error, even though submit() may not allow null.
    }
}
```

This snippet is an **anti-pattern illustration** requiring an `@Aspect` class, imports, and Spring AOP setup to run; it is not part of the complete demo later on. If the target method declares `String submit(...)` and callers expect **a confirmation code or an exception**, the advice above secretly adds a `null` outcome. If the return type is primitive `int`, `null` can trigger an unboxing error when returning through the proxy, hiding the root cause.

**The lesson goal** is writing Spring AOP `@Around` advice so that:

1. **Contracts are preserved by default**: call `proceed()` once, return the exact result, and rethrow the exact original `Throwable`.
2. When implementing a fallback, **it has an explicit specification**: which errors are converted, valid types/values, retry scope, transactions, and tests.
3. Outcomes are verified **through a real Spring proxy**, not merely unit tests invoking the aspect method directly.
4. **Normal returns**, `null`, `void`, boxed primitives, checked/unchecked exceptions, and async handles are clearly distinguished.

Per the module's scope, content focuses solely on **Spring Aspect and Spring AOP proxies**, without extending to AspectJ weaving or general AOP.

## 2. What Is a Method's Observable Contract?

For a public Spring service operation, the contract covers much more than the Java signature:

| Contract element | Example in a Spring service | Risk when advice gets it wrong |
| --- | --- | --- |
| Return type | `Receipt`, `String`, `int`, `void`, `Optional<Receipt>` | Returning the wrong object type causes `ClassCastException`; `null` on primitives can cause unboxing failure. |
| Normal value | Issued transaction code, remaining stock count | Default values like `0`/`false` fake success or misreport business state. |
| Nullability | Whether the method permits `null` | Undeclared `null` causes caller NPEs or lost data. |
| Failure types | `IllegalArgumentException`, `PaymentDeclinedException` | Advice swallows errors or changes exception types, preventing callers from matching `catch` blocks. |
| Side effects | Database writes, message sends, remote API calls | Retries or repeated `proceed()` execute business actions multiple times. |
| Transactions | Write commands needing rollback on specific errors | Turning exceptions into success can alter rollback semantics depending on advisor order. |
| Security | Denying unauthorized callers or propagating auth errors | Broad fallbacks can mask access-control failures. |
| Async/reactive | Returning `CompletableFuture<T>`/`Mono<T>` | Advice sees only wrapper return; does not automatically observe final completion. |

**Rule:** you have no right to "swallow an error and return an arbitrary value" merely because the advice signature is `Object around(...)`. `Object` is the **advice's** return type, while the proxied Java method still keeps its own return type and semantics.

### 2.1. Why Seeing HTTP 200 in Tests Is Not Enough

An outer controller can:

- Use response mapping that converts `null` into another response shape.
- Have exception handlers that trigger only when the right exception type propagates.
- Return HTTP 200 for a fallback while business persistence/sending was skipped.
- Record a "success" metric on the proxy's normal return even though the target failed.
- Retry because no exception surfaced, leading to unwanted data state.

Therefore, Spring AOP tests must assert **results or exceptions at the method boundary**, and then verify side effects (DB/messages/transactions/security) when the business requires it.

## 3. Spring Proxies and Where @Around Controls the Outcome

```text
External caller / other Spring bean
                |
                | orderService.submit("A")
                v
       Spring AOP proxy
                |
                v
     @Around advice invoked
                |
                +-- pjp.proceed()
                |      |
                |      v
                |  target service method
                |      |
                |      +-- return value ----> advice ----> caller
                |      |
                |      +-- throw failure ---> advice ----> caller
                |
                +-- advice does not proceed():
                |      +-- chosen return value or chosen exception
                |
                +-- advice catches failure:
                       +-- throw original failure (preserve contract)
                       +-- transform / return fallback (ONLY when contract permits)
```

Spring AOP is **proxy-based**; `@Around` does not automatically apply to a service created with `new`, a method called via `this.inner()` inside the target, or non-proxyable classes/methods. For the advice to run, the aspect must be a Spring bean, Spring `@AspectJ` support must be enabled, the target must be a Spring-managed bean, and calls must go through the proxy.

In Spring Framework Java configuration, it is common to use:

```java
@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
class AopConfiguration {
    @Bean
    MonitoringAspect monitoringAspect() {
        return new MonitoringAspect();
    }
}
```

This is an illustrative snippet; `MonitoringAspect` is an `@Aspect` class that must exist. Spring Boot provides AOP auto-configuration, so declaring `@EnableAspectJAutoProxy` manually is usually unnecessary there. Setting `proxyTargetClass=true` does not resolve self-invocation, and CGLIB cannot advise `final` methods.

## 4. Safe Default Pattern: Proceed, Observe, and Return or Rethrow Intact

```java
@Aspect
public class ContractPreservingAspect {
    @Around("execution(public * com.example.orders..*Service.*(..))")
    public Object preserve(ProceedingJoinPoint pjp) throws Throwable {
        try {
            Object result = pjp.proceed();
            recordSuccess(pjp);
            return result; // Preserve the exact object/value returned by proceed().
        } catch (Throwable failure) {
            recordFailureSafely(pjp, failure);
            throw failure; // Preserve the exact type and original Throwable.
        }
    }

    private void recordSuccess(ProceedingJoinPoint pjp) {
        // Record metric without throwing.
    }

    private void recordFailureSafely(
            ProceedingJoinPoint pjp, Throwable failure) {
        // Observe the failure without losing the original Throwable.
    }
}
```

This is an **illustrative pattern**, not a standalone runnable project; helpers need implementations and imports for `@Aspect`, `@Around`, and `ProceedingJoinPoint`. In real code, instrumentation itself can throw. If `recordSuccess` throws, the `catch(Throwable)` block catches that instrumentation error and `recordFailureSafely` may mistakenly treat it as a target failure. To preserve semantics cleanly, **separate the `proceed()` phase from the metric-recording phase**, as in section 7's complete runnable example.

A version with stronger protection against instrumentation errors:

```java
@Around("execution(public * com.example.orders..*Service.*(..))")
public Object preserve(ProceedingJoinPoint pjp) throws Throwable {
    final Object result;
    try {
        result = pjp.proceed();
    } catch (Throwable original) {
        try {
            observeFailure(original);
        } catch (RuntimeException telemetryError) {
            // Per policy: record telemetryError through an independent error channel.
        }
        throw original;
    }

    try {
        observeSuccess(result);
    } catch (RuntimeException telemetryError) {
        // Per policy: do not turn a valid result into a failure if telemetry is best-effort.
    }
    return result;
}
```

This is illustrative code inside an `@Aspect` assuming `observeFailure`/`observeSuccess` exist. Do not treat `catch(RuntimeException)` as a catch-all shield against **every** error: we are intentionally choosing a policy for ordinary instrumentation errors; fatal errors should never be swallowed merely to keep up an illusion of success.

If telemetry/auditing is **mandatory** to persist durably, "best-effort ignore" also violates the contract; in that case design transactional/outbox/reliable auditing rather than changing one `catch` line.

### 4.1. Why Does the Advice Signature Declare throws Throwable?

`ProceedingJoinPoint.proceed()` declares `throws Throwable`. To let all checked and unchecked exceptions matching the target method propagate untouched, the standard Spring `@Around` signature is:

```java
public Object around(ProceedingJoinPoint pjp) throws Throwable
```

`throws Throwable` on the **advice method** does not alter the target's Java source contract into `throws Throwable` for callers. It lets the advice write `throw original` without forcing every error into a `RuntimeException`. With JDK interface proxies and undeclared checked exceptions, proxy/JDK rules can cause wrapping such as `UndeclaredThrowableException`; this does not give advice license to arbitrarily throw new checked exceptions outside the contract.

`@Around` must not convert every `Exception` into `new RuntimeException(error)` just to satisfy the compiler. Changing exception types alters exception handlers, transaction rollback decisions, and log diagnostics. When business mapping is required, define it explicitly and test on the real proxy type.

## 5. Common Anti-Patterns

### 5.1. Logging and Returning null

```java
@Around("execution(* com.example.orders..*Service.*(..))")
public Object swallow(ProceedingJoinPoint pjp) {
    try {
        return pjp.proceed();
    } catch (Throwable error) {
        logger.error("Service failed", error);
        return null;
    }
}
```

Wrong by default because:

- `null` is incompatible with `int`, `boolean`, and other primitive return types.
- For `String`/DTO methods with non-null contracts, callers receive an invalid outcome.
- Outer exception handlers never know the call actually failed.
- Other transaction/cache/metrics interceptors may observe a normal return depending on chain position.
- The advice catches `Throwable`, including `Error`, without propagating it.

This is **non-standalone illustrative code** since logger and aspect infrastructure are omitted.

### 5.2. Returning a Default Value "To Be Safe"

```java
catch (Exception error) {
    return 0;
}
```

If `int remainingStock()` defines `0` as genuinely out of stock, a fake `0` from a database failure leads to wrong business decisions. If the contract is `boolean authorized()`, a fake `false` can mask a system outage—even under an intentional "fail closed" policy, "denied" must be distinguished from "authorization service unavailable."

Never pick fallbacks simply because a value compiles easily. Distinguish clearly:

- **Valid no-data:** perhaps `Optional.empty()` or an explicitly defined result type.
- **Business failure:** exception or explicit failure result per contract.
- **Infrastructure failure:** timeout, DB unavailable; may retry, trip a circuit breaker, fail to caller, or apply a policy-approved fallback.
- **Fatal error:** never silently convert into business success.

### 5.3. Catching and Throwing a New Error Without Preserving the Cause

```java
catch (Exception original) {
    throw new IllegalStateException("failed");
}
```

This snippet loses the cause chain unless the cause is attached. When an exception **must** be translated for a boundary contract, at minimum do:

```java
catch (RemoteServiceException original) {
    throw new OrderGatewayException("Remote order gateway failed", original);
}
```

This is an illustrative example; `RemoteServiceException` and `OrderGatewayException` are domain/infrastructure types to be defined in the application. Every type translation must be deliberate, because callers, transactions, and security can branch on exception classes.

Without a translation policy, **`throw original;`** preserves information far better.

### 5.4. Throwing an Exception at the Wrong Time

```java
Object result = pjp.proceed();
doAudit(); // May throw and replace a normal return with an exception
return result;
```

If auditing is defined as **best-effort**, `doAudit()` throwing breaks the contract of a method that already succeeded. If auditing is defined as **must-succeed**, that is not inherently a bug, yet it must be reflected in the business/transaction contract.

Specify the audit mode (best-effort vs. mandatory) and failure handling explicitly; never assume auditing should "break regardless" or "always be ignored."

### 5.5. Not Calling proceed()

```java
@Around("execution(* com.example.orders..*Service.*(..))")
public Object skip(ProceedingJoinPoint pjp) {
    return "ok";
}
```

`@Around` has the authority to omit `proceed()`, yet then **the target never runs**: DB updates, validation, auditing, or message publishing inside the target do not occur. Without an explicit short-circuit contract (cache hit, access denial, or idempotency), this is a severe bug.

`@Before` or `@AfterReturning` is more suitable when you only need observation without controlling the call path.

### 5.6. Calling proceed() Twice Accidentally

```java
Object a = pjp.proceed();
Object b = pjp.proceed();
return b;
```

This code can cause **the target to execute twice** under around advice semantics; if the method is not idempotent, it can charge twice, publish two events, or insert into the DB twice. Never abuse Spring AOP `@Around` for blind retries.

Retries are valid only when:

- The operation is confirmed idempotent or backed by an idempotency key/deduplication.
- There is an explicit policy retrying only **transient** failures.
- Attempt count, backoff, timeout/deadline, and cancellation are well bounded.
- Transaction boundaries, request scope, security context, and side effects are verified.
- Integration tests verify the exact number of downstream invocations.

## 6. Returning the Right Type and Value: Primitives, void, null, Optional

### 6.1. Primitive-Returning Methods

Suppose the target has:

```java
public int available() {
    return 12;
}
```

In `@Around`, `pjp.proceed()` returns an `Object` containing a boxed `Integer` (or a compatible value produced by another interceptor). The safe pattern is **returning that exact `Object`** so the Spring proxy unboxes it to `int`.

```java
Object result = pjp.proceed();
return result;
```

**Do not return `null`**, string `"0"`, or an arbitrary `Integer` when the contract requires the real count. For a `boolean`-returning target, `null` likewise cannot unbox to a primitive.

### 6.2. Void-Returning Methods

For a target:

```java
public void refresh() {
    // Perform actual work.
}
```

`proceed()` in around advice typically returns `null` on normal completion of a `void` method; this is **not a fallback**. Returning `null` from `@Around` after `proceed()` succeeds is valid for a `void` method, completely different from deliberately returning `null` inside `catch` after a target failure.

### 6.3. Methods Intentionally Permitting null

```java
public String findNullable(String id) {
    return null;
}
```

If the contract states `null` can be returned, around advice must **preserve `null`** when the target returns normally. Never convert `null` into `"UNKNOWN"` if consumers rely on `null` to mean "no data."

### 6.4. Optional and Result Types

```java
public Optional<Order> find(String id) {
    // Optional.empty() is defined as "not found".
}
```

When the contract is `Optional<Order>`, `Optional.empty()` is valid; returning `null` is completely different and usually violates the contract.

A result wrapper like `OperationResult<T>` can express `SUCCESS`/`NOT_FOUND`/`FAILED` explicitly if the business API is designed that way. Yet advice must not secretly replace a `throws`-based service with `Result.fail(...)` when the method signature does not support it or callers are not updated.

### 6.5. Generics and Runtime Casts

`@Around` usually declares `Object` because `proceed()` returns `Object`. The Java compiler cannot verify every service return type at compile time; Spring/JDK proxies cast/unbox according to the declared return type. A `List<Order> findAll()` method cannot accept `"error"`; a type mismatch error may surface **after** the advice returns.

To reduce risk:

- Default to returning `pjp.proceed()` directly.
- Never coerce every result with `String.valueOf(...)`.
- When transformation is truly needed, narrow the pointcut to specific methods and test return types.
- Use typed results/contracts in services rather than a global aspect trying to "normalize" all return values.

## 7. Java 17+ Spring AOP Demo: Preserving Normal Returns and Exceptions

The demo includes one Spring-managed target, one Spring-managed aspect, and a client retrieving the target bean from `AnnotationConfigApplicationContext`. It verifies:

- `String` normal return unchanged;
- `int` primitive unboxing unchanged;
- `void` normal completion;
- valid `null` from a nullable method not replaced;
- `IllegalArgumentException` propagated intact to the caller;
- advice observes **4 normal returns and 1 exceptional exit**.

The demo uses Java 17+, Spring Framework 6.2.19, and AspectJ Weaver 1.9.25.1. This is plain Spring Framework, not relying on Spring Boot auto-configuration.

### 7.1. Project Structure

```text
spring-around-contract/
├── settings.gradle
├── build.gradle
└── src/main/java/com/example/contract/
    ├── Main.java
    ├── AppConfig.java
    ├── OrderService.java
    └── ContractAspect.java
```

**`settings.gradle`**

```gradle
rootProject.name = 'spring-around-contract'
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
    implementation 'org.aspectj:aspectjweaver:1.9.25.1'
}

application {
    mainClass = 'com.example.contract.Main'
}
```

`spring-context` provides the container/Java config; `spring-aop` and `aspectjweaver` support `@AspectJ` pointcuts. `@EnableAspectJAutoProxy` enables Spring proxy AOP, not AspectJ load-time weaving. In a Spring Boot project, use the BOM matching your Boot major version rather than pinning the demo versions.

### 7.2. Target Service With Deterministic Outcomes

**`OrderService.java`**

```java
package com.example.contract;

public class OrderService {
    public String accept(String id) {
        return "accepted:" + id;
    }

    public int quantity() {
        return 12;
    }

    public void refresh() {
        System.out.println("target:refresh");
    }

    public String findNullable(String id) {
        return null;
    }

    public String reject(String id) {
        throw new IllegalArgumentException("invalid:" + id);
    }
}
```

All methods are public and non-final, and the class is non-final. Those are simple conditions for Spring CGLIB proxying to intercept. `reject(..)` deliberately throws an exception from the target to verify the advice does not swallow errors.

### 7.3. Contract-Preserving @Around Advice

**`ContractAspect.java`**

```java
package com.example.contract;

import java.util.concurrent.atomic.AtomicInteger;
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;

@Aspect
public class ContractAspect {
    private final AtomicInteger normalReturns = new AtomicInteger();
    private final AtomicInteger exceptionalExits = new AtomicInteger();

    @Around("execution(public * com.example.contract.OrderService.*(..))")
    public Object preserve(ProceedingJoinPoint pjp) throws Throwable {
        final Object result;
        try {
            result = pjp.proceed();
        } catch (Throwable original) {
            exceptionalExits.incrementAndGet();
            throw original;
        }
        normalReturns.incrementAndGet();
        return result;
    }

    public int normalCount() {
        return normalReturns.get();
    }

    public int failureCount() {
        return exceptionalExits.get();
    }
}
```

In the example, the two `AtomicInteger` counters do not normally throw errors, so the instrumented outcome matches the number of `proceed()` calls that completed or threw. Spring AOP may have **other interceptors** in the chain; name the counter "outcome observed at `proceed()`" in real applications that also have retry/transaction/security interceptors.

Key points:

1. `proceed()` is called **once** per invocation.
2. On normal completion, `result` is returned **intact**, including boxed primitives or `null`.
3. On failure, the advice increments a counter and executes `throw original;`, creating no new exception.
4. `throws Throwable` on the advice signature allows propagation without forcing exception wrapping.
5. No logic turns failures into `null`, `0`, `false`, or fake objects.

### 7.4. Registering the Aspect and Target With Spring

**`AppConfig.java`**

```java
package com.example.contract;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@EnableAspectJAutoProxy(proxyTargetClass = true)
public class AppConfig {
    @Bean
    OrderService orderService() {
        return new OrderService();
    }

    @Bean
    ContractAspect contractAspect() {
        return new ContractAspect();
    }
}
```

`@Aspect` does not register a bean automatically; `@Bean` on the configuration registers `ContractAspect` and `OrderService`. `proxyTargetClass=true` selects a class-based proxy so `context.getBean(OrderService.class)` is valid and convenient for the demo. Component scanning is unnecessary since all beans are declared explicitly.

### 7.5. Running and Verifying Outcomes at the Client

**`Main.java`**

```java
package com.example.contract;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class Main {
    public static void main(String[] args) {
        try (var context =
                new AnnotationConfigApplicationContext(AppConfig.class)) {
            OrderService service = context.getBean(OrderService.class);
            ContractAspect aspect = context.getBean(ContractAspect.class);

            System.out.println("proxy=" + AopUtils.isAopProxy(service));
            System.out.println("accepted=" + service.accept("A"));
            System.out.println("quantity=" + service.quantity());

            service.refresh();

            System.out.println(
                "nullableIsNull=" + (service.findNullable("missing") == null)
            );

            try {
                service.reject("X");
            } catch (IllegalArgumentException ex) {
                System.out.println("caught=" + ex.getMessage());
            }

            System.out.println("normalReturns=" + aspect.normalCount());
            System.out.println("exceptionalExits=" + aspect.failureCount());
        }
    }
}
```

Run from the project root with JDK 17+ and Gradle installed:

```bash
gradle run --quiet
```

If using the Gradle wrapper: `./gradlew run --quiet` on Linux/macOS, `gradlew.bat run --quiet` on Windows.

**Demo `System.out` lines in exact order** (excluding extra Gradle/Spring/JVM logs):

```text
proxy=true
accepted=accepted:A
quantity=12
target:refresh
nullableIsNull=true
caught=invalid:X
normalReturns=4
exceptionalExits=1
```

### 7.6. Mapping Results Against the Contract

| Call | Target result | What caller actually receives | Counter |
| --- | --- | --- | --- |
| `accept("A")` | `"accepted:A"` | Identical string | normal +1 |
| `quantity()` | `12` of type `int` | `12`, not altered to `0`/`null` | normal +1 |
| `refresh()` | `void` normal completion | No return value | normal +1 |
| `findNullable("missing")` | `null` as a valid outcome | `null` preserved | normal +1 |
| `reject("X")` | Throws `IllegalArgumentException("invalid:X")` | Caught with exact type and message | exceptional +1 |
| **Total** | 5 method calls | **4 normal, 1 exception** | normal=4, exceptional=1 |

This demo does not directly illustrate `@AfterThrowing`; it shows that **`@Around` can preserve exceptional flow** via `throw original`. Never treat these counters unconditionally as "business success/failure": `findNullable` returns `null` normally yet may represent "not found."

## 8. Why Should Exceptions Not Be Replaced With Fallbacks Unconditionally?

Suppose a method declares:

```java
public Receipt charge(String orderId)
        throws PaymentGatewayException;
```

The contract may state that a `Receipt` exists only when the transaction is confirmed, while `PaymentGatewayException` signals that status could not be confirmed. If an advice catches all errors and returns `new Receipt("fake")`, the caller may treat the transaction as processed even though no payment was recorded.

This is an **illustrative business example**; `Receipt` and `PaymentGatewayException` must be defined in a real project. The Spring-specific point to remember is that **`@Around` permits changing both returns and throws**. That very capability demands contract discipline.

### 8.1. Intentional Fallbacks Require Three Conditions

1. **Clear policy:** which errors are handled and which must propagate. Never catch all `Throwable` and treat everything as "not found."
2. **Valid value/type:** the fallback belongs to the return domain published by the API, such as `Optional.empty()` for a lookup allowing missing data.
3. **Safe side effects:** know for certain whether the target committed, whether retries are safe, and how cache/transaction/security advisors observe the outcome.

Only when all three conditions hold is short-circuiting or falling back inside `@Around` a **designed business behavior**, rather than exception evasion.

### 8.2. Pattern for Falling Back Only on a Specific Error

```java
@Around("execution(* com.example.catalog.CatalogService.find(..))")
public Object cacheFallback(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (CatalogUnavailableException ex) {
        return Optional.empty();
    }
}
```

**This is an illustrative snippet**, not standalone runnable: `CatalogService` and `CatalogUnavailableException` must be defined, `find(..)` **must declare `Optional<...>`** as a valid return type, and policy must permit treating "catalog unavailable" as "not found"—a choice many systems **forbid** because the two states are not equivalent.

This example shows only **how to restrict a catch block by exception type**. Do not take it as automatic production advice to conflate `unavailable` and `absent`. In most cases, propagating the exception or returning a result type with an explicit **UNAVAILABLE** status is more accurate.

### 8.3. Fallback Return Types Must Be Java-Compatible

`Optional.empty()` is valid when the target method returns `Optional<T>`. It is **invalid** when the target method returns `T`, `String`, or `int`. With generic types and runtime erasure, a mismatch may explode only in the caller, so test both compile-time contracts and runtime proxy behavior.

### 8.4. Never "Fix" Types With Reckless Casts

```java
return (Receipt) (Object) "fallback";
```

This illustrates broken behavior that throws `ClassCastException`. It does not produce a valid `Receipt`. If a fallback for `Receipt` is needed, construct a **genuine `Receipt`** matching the contract instead of faking success just to satisfy the compiler.

## 9. Retry and proceed(): One Change Can Duplicate Side Effects

`@Around` permits calling `proceed()` multiple times. This mechanism can implement AOP-level retries, yet **only when semantics are explicitly defined**.

Dangerous example:

```java
@Around("execution(* com.example.payment.PaymentService.charge(..))")
public Object badRetry(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (RuntimeException ex) {
        return pjp.proceed(); // Re-executes, potentially charging again.
    }
}
```

If the first pass committed to the DB yet the network response was lost, the second pass can create a duplicate transaction. Spring AOP does not automatically distinguish "failed before side effect" from "failed after side effect." Retrying can also interact with `@Transactional`/`@Cacheable`/`@Async` interceptors depending on advisor order.

**Instead of blind retries**, ensure:

- Classification of transient vs. permanent errors.
- Idempotency keys or deduplication mechanisms.
- Bounded attempts, backoff, and timeouts.
- Attention to transaction boundaries; avoid retrying inside a transaction already marked rollback-only.
- Final exception still returned to the caller if attempts are exhausted.
- Integration tests measuring downstream call counts and DB/message state.
- Proper propagation of user/request context and security identity when async.

If the problem requires only logging, timing, or counters, **do not retry**; calling `proceed()` once is the safest default.

## 10. Transactions and @Around: Swallowing Exceptions Can Alter Rollback Semantics

Suppose a Spring service uses a transaction interceptor:

```java
@Service
public class LedgerService {
    @Transactional
    public void transfer(String from, String to, long amount) {
        // Business operation with transaction rules.
    }
}
```

This is illustrative code, omitting dependencies and the transaction manager. If the target method throws a `RuntimeException` yet `@Around` catches it and returns normally, transaction rollback behavior depends on **advisor ordering**, existing transaction state, failure location, and propagation:

- If Spring transaction advice observes the **exception** before an outer aspect swallows it, the transaction may already be marked rollback-only or terminated per its rules.
- If the transaction interceptor observes a **normal return** because an inner aspect in the chain converted the error into a fallback, behavior can differ.
- `@Transactional` itself requires a transaction manager and configuration; it is not enabled merely by `@EnableAspectJAutoProxy`.

**Never conclude "swallowing errors always commits" or "always rolls back."** What is true is that **the Spring transaction advisor decides based on the outcome/exception it actually observes**, and `@Around` can alter that outcome. To confirm, inspect the transaction manager, `@Order`, rollback rules, and actual database state after integration tests.

### Is After-Commit Different From After-Returning?

Yes. An `@Around` observing a normal target return or an `@AfterReturning` executing does not guarantee the DB transaction committed. When reliable post-commit side effects are needed, use transaction synchronization or `@TransactionalEventListener(phase = AFTER_COMMIT)` as appropriate; never use an aspect `catch` block to simulate commit confirmation.

## 11. Spring Security, Caching, and Async: Never Turn Failures Into "Success"

### 11.1. Method Security

If Spring Method Security applies `@PreAuthorize` or another interceptor to a service, an overly broad `@Around` can accidentally wrap the security policy. Never catch authorization exceptions and return a `true` fallback or default DTO. **Security denials must be preserved unless an explicit security contract and policy specify otherwise.**

Check the order between custom aspects and method security advisors; if an advice placed outside the security interceptor skips `proceed()`, it can **prevent the security interceptor from running**, breaking the boundary. Avoid broad pointcuts matching framework beans or security methods.

### 11.2. Caching

A cache aspect or `@Cacheable` interceptor can short-circuit a method per its cache contract. If you add an `@Around` that returns a default value when a backend fails, that value might get cached depending on advisor chain order and configuration—leaving a "fake success" cached even after the backend recovers.

Distinguish "cache miss," "data legitimately absent," and "backend unavailable." Never collapse all three into the same `null`.

### 11.3. CompletableFuture and Async Handles

For a method:

```java
public CompletableFuture<String> loadAsync(String id) {
    // Returns future immediately; work may finish later.
}
```

`@Around` sees `pjp.proceed()` return a `CompletableFuture` **normally**, even if that future completes exceptionally later. `catch(Throwable)` around `proceed()` does not automatically catch exceptions thrown asynchronously inside the future. If policy requires completion-time error handling, use `whenComplete`/`handle` or appropriate async tooling.

**Never replace a failed future with `CompletableFuture.completedFuture("ok")`** unless the API contract/policy explicitly defines that fallback.

### 11.4. Reactor Mono/Flux

For reactive methods returning `Mono<T>` or `Flux<T>`, the proxy advice sees a **publisher object** on return. Errors may occur **upon subscription**, after `proceed()` has already returned normally. Use Reactor operators like `onErrorResume`/`doOnError` per reactive semantics and explicit policy; do not expect synchronous `try/catch` inside `@Around` to catch reactive errors.

## 12. Are @AfterThrowing and @AfterReturning Better Choices?

When the requirement is solely to **observe** outcomes without altering return values or exceptions:

- `@AfterReturning`: runs when method execution finishes normally; can bind the return value via `returning`.
- `@AfterThrowing`: runs when method execution exits via an exception; can bind the thrown exception via `throwing`.
- `@After`: provides finally semantics.
- `@Around`: wraps and has authority to actively change outcomes, so it requires the most care.

Spring Framework recommends preferring **the least powerful advice that meets the requirement**, avoiding entire classes of bugs like forgetting `proceed()` or returning the wrong value. If you only need to count exceptions, `@AfterThrowing` is safer by design than an `@Around` with a hand-rolled `catch`.

Example observers with `returning` and `throwing` (do not merge into the demo if you want to preserve its stdout):

```java
@AfterReturning(
    pointcut = "execution(* com.example.contract.OrderService.*(..))",
    returning = "result",
    argNames = "result"
)
public void afterResult(Object result) {
    // Observe the return value without replacing it.
}

@AfterThrowing(
    pointcut = "execution(* com.example.contract.OrderService.*(..))",
    throwing = "error",
    argNames = "error"
)
public void afterError(Throwable error) {
    // Observe the error without turning an exceptional exit into success.
}
```

These are illustrative snippets inside a Spring-managed `@Aspect` with appropriate imports. The set of methods matched when binding `Object result` may differ from advice that does not bind a return value, especially for `void`/primitives/generics; verify with integration tests on your Spring version.

When intentional recovery is required, `@Around` or a domain-level handler has the necessary authority, yet the policy must be explicit and thoroughly tested.

## 13. Separate Business Fallbacks From Infrastructure Advice When Possible

A resilient design lets the Spring service express domain outcomes directly:

```java
public Optional<InventoryItem> findAvailable(String sku) {
    // Optional.empty(): item genuinely does not exist.
    // InventoryBackendUnavailableException: backend failed.
}
```

This lets Spring AOP `@Around` **preserve either the returned `Optional` or the thrown backend exception**. Callers distinguish legitimate absence from infrastructure failure without guessing from `null`/`false`.

This is an illustrative snippet; `InventoryItem`/`InventoryBackendUnavailableException` must be defined in a real app. If a client wants a fallback when the backend is unavailable, place it at a **named boundary with an explicit contract**, such as `InventoryQueryFacade.findCachedOrUnavailable()`, and test:

- Fresh value or stale cache?
- What timeout applies?
- Which errors fall back, and which must fail?
- Are permission checks still enforced?
- Does the response express degraded status?
- Which side effects did or did not occur?

This avoids a "catch-all" `@Around` silently governing every method across the system.

## 14. Why Might the Same @Around Run or Not Run?

Even a contract-preserving advice is useless if Spring AOP never intercepts the call.

| Symptom | Explanation in Spring | How to check |
| --- | --- | --- |
| `@Aspect` exists yet no advice runs | Aspect class is not a bean or AOP support is disabled | `@Aspect` + `@Component` in scan, or `@Bean` + `@EnableAspectJAutoProxy`/Boot AOP starter |
| Method called via `this.method()` inside target | Self-invocation does not go through Spring proxy | Extract to an injected collaborator bean or move advice to outer entry |
| Client uses `new Service()` | Bypassed Spring container | Inject the service bean from context |
| `final` class with CGLIB | Cannot be subclassed | Use interface/JDK proxy if compatible or redesign |
| `final` method with CGLIB | Method cannot be overridden | Use an interceptable entry method and test |
| Spring returns JDK proxy yet caller invokes method missing from interface | Proxy does not expose that method | Add to interface or choose suitable proxy strategy |
| `AopUtils.isAopProxy(bean)=true` yet advice skips one method | Advisor/pointcut mismatch or different call path | Check pointcut expression, target bean type, actual advice invocation |
| Exception disappears after adding `@Around` | Advice caught and returned fallback/wrong exception type | Trace catch/return branches; assert expected throwable at caller |
| Service returns wrong type after advice | Advice produced default incompatible with target declared type | Return original proceed result; test primitive/generic/null branches |

### Minimal Probe

```java
OrderService bean = context.getBean(OrderService.class);
System.out.println(AopUtils.isAopProxy(bean));
bean.reject("probe");
```

This illustrative snippet **will throw `IllegalArgumentException`**, so wrap it in try/catch if you do not want the test to abort with an exception; it uses `OrderService` and `AopUtils` from the demo. `proxy=true` proves only that a Spring AOP proxy exists, not that the specific aspect's pointcut applies—verify counters or exception outcomes.

## 15. Writing Integration Tests to Lock Down the Contract

### 15.1. Do Not Unit-Test the Aspect Alone and Assume Spring AOP Is Verified

`new ContractAspect().preserve(fakePjp)` tests the advice's Java logic, yet does not verify:

- Whether `@Aspect` is registered as a Spring bean;
- Whether `@EnableAspectJAutoProxy` is active;
- Whether the target method is proxied;
- Whether the pointcut matches;
- Whether exceptions/return types traverse JDK/CGLIB proxies cleanly.

You need at least one integration test using a real `ApplicationContext` and invoking the bean via its Spring reference.

### 15.2. Foundational Assertions

With the demo `AppConfig`:

```java
try (var context = new AnnotationConfigApplicationContext(AppConfig.class)) {
    OrderService service = context.getBean(OrderService.class);
    ContractAspect aspect = context.getBean(ContractAspect.class);

    if (!"accepted:X".equals(service.accept("X"))) {
        throw new AssertionError("String return changed");
    }
    if (service.quantity() != 12) {
        throw new AssertionError("Primitive result changed");
    }
    service.refresh();
    if (service.findNullable("missing") != null) {
        throw new AssertionError("Nullability changed");
    }

    try {
        service.reject("Y");
        throw new AssertionError("Expected IllegalArgumentException");
    } catch (IllegalArgumentException ex) {
        if (!"invalid:Y".equals(ex.getMessage())) {
            throw new AssertionError("Wrong failure propagated", ex);
        }
    }

    if (aspect.normalCount() != 4 || aspect.failureCount() != 1) {
        throw new AssertionError("Wrong @Around outcome observations");
    }
}
```

This snippet is an **illustrative test variation** using the demo classes and importing `AnnotationConfigApplicationContext`; do not merge into `Main` if you want to preserve section 7.5's stdout.

### 15.3. Verifying the Exact Same Exception Object When Needed

When you want strict confirmation that `throw original` preserves object identity, configure the target to throw a preconstructed `RuntimeException` instance (instead of allocating inside the method), and compare with `==` in the caller. Keep this in an isolated test fixture; never share stale-stack-trace exception singletons in production.

`==` proves reference identity; comparing messages/types proves observable behavior partially. Both have value when testing the right goal.

### 15.4. Tests for Short-Circuiting / Retry / Fallback

When an application **intentionally** alters returns/exceptions:

- Assert which condition skips `proceed()`, with target call count = 0 on that branch.
- Assert retry attempts are bounded and side-effect counts are accurate.
- Assert "permanent" errors do not retry and still propagate.
- Assert timeouts/cancellations are not turned into fake successes.
- Assert fallbacks match API type, nullability, and business status.
- Assert real transaction rollback/commit and security denials.
- Assert future/reactive completion behavior with async/reactive tests rather than relying solely on synchronous advice output.

Never accept tests covering only the happy path as proof that an aspect is safe.

## 16. Code Review Checklist for @Around

- [ ] Are the `@Aspect` class and target service Spring-managed beans, does the pointcut match, and do callers use the proxy?
- [ ] Does `@Around` declare `ProceedingJoinPoint`, return `Object`/compatible type, and declare `throws Throwable`?
- [ ] When not intentionally short-circuiting, does it always call `proceed()` **once**?
- [ ] Are normal returns preserved intact (`String`/DTO/`int`/`boolean`/`void`/`null`/`Optional`)?
- [ ] Are target exceptions rethrown **with original type, message, and cause** when no explicit translation policy applies?
- [ ] If `catch(Throwable)` is present, does it avoid unconditionally doing `return null`/`0`/`false`?
- [ ] Does it avoid converting authorization/transaction exceptions into out-of-contract normal returns?
- [ ] Does best-effort instrumentation have a clear error policy so it cannot fabricate exceptions that alter outcomes?
- [ ] If transforming/falling back, do the API contract and return type permit it, and is it tested?
- [ ] If retrying, are idempotency keys, bounded attempts, and side-effect/transaction tests present?
- [ ] Are legitimate nulls distinguished from swallowed-error nulls, and normal voids from short-circuits?
- [ ] Have Spring proxy kind and self-invocation/`final`-method limits been checked?
- [ ] For future/reactive methods, is "method returned wrapper" not mistaken for "task completed successfully"?
- [ ] Do integration tests use a real Spring context and assert return values, exceptions, counters, and side effects?
- [ ] Is the pointcut narrow enough to avoid matching security/framework beans by mistake?

**Remember:** `@Around` in Spring AOP is a **boundary capable of changing results and exceptions**. The safe observation-only pattern is **`return pjp.proceed()` or preserving the result; catch and `throw original` if logging failures**. Never return defaults just to "avoid errors" when the API contract forbids it. Short-circuit, retry, fall back, or translate exceptions only when **business requirements explicitly demand it and tests cover it thoroughly**.

## Official Spring Documentation

- [Spring Framework 6.2 — Declaring Advice / Around Advice](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/advice.html)
- [Spring Framework 6.2 — AOP Concepts and Advice Types](https://docs.spring.io/spring-framework/reference/6.2/core/aop/introduction-defn.html)
- [Spring Framework 6.2 — Proxying Mechanisms and Self-invocation](https://docs.spring.io/spring-framework/reference/6.2/core/aop/proxying.html)
- [Spring Framework 6.2 — Enabling @AspectJ Support](https://docs.spring.io/spring-framework/reference/6.2/core/aop/ataspectj/aspectj-support.html)
- [Spring Framework 6.2 — Transaction-bound Events](https://docs.spring.io/spring-framework/reference/6.2/data-access/transaction/event.html)
