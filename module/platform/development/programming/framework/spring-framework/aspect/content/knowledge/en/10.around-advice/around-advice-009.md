# Risks of Repeating Operations With Side Effects When Implementing Retry via Aspect in Spring AOP

## 1. Nature of the Problem

In **Spring AOP**, an advice method annotated with `@Around` can call `ProceedingJoinPoint.proceed()` multiple times. This is the basis for building **retry** logic: when the target throws an exception, the advice re-invokes the Spring proxy continuation. However, **each `proceed` call can re-execute the entire target method, including operations that already produced side effects**.

Example payment workflow:

~~~text
Client -> Spring service proxy
          -> RetryAspect @Around
             -> proceed #1
                -> call payment system
                -> system already debited account
                -> response/ACK lost, throws timeout
             -> catch timeout
             -> proceed #2
                -> system may debit again
             -> caller receives one success result
~~~

Seeing **one request return success** does not prove only **one debit** occurred. This is the single greatest hazard when writing retries with `@Aspect`.

After this lesson, you will be able to:

1. Understand precisely what `proceed()` does in Spring AOP and why retries can repeat both the target and inner interceptors.
2. Distinguish failures **before side effects**, **after side effects**, and **when it is unknown whether side effects committed**.
3. Write bounded retries that catch only explicitly classified errors, never swallowing the final error or returning fake success.
4. Understand the difference between **idempotency**, retry attempts, and transaction rollback.
5. Run a plain Spring Framework Java 17+ example comparing an **unguarded** flow and an **in-JVM idempotency-key** flow.
6. Analyze ordering between a Spring retry aspect and transaction advice, self-invocation, pointcuts, concurrency, timeouts, and observability.
7. Know when to require idempotency/reconciliation on the target system rather than retrying blindly.

**Scope:** Covers only `@Around` in **Spring-managed `@Aspect` / Spring AOP proxies**. Idempotency and distributed-systems principles are explained at the level needed to design aspects safely, without replacing dedicated transaction/payment documentation.

## 2. One Proxy Invocation Does Not Equal One Target Execution

Spring AOP uses JDK dynamic proxies or class-based CGLIB proxies. When a client calls a method through the proxy and the pointcut matches, the `@Around` advice controls continuation:

~~~text
Caller
  |
  +--> Spring AOP Proxy
           |
           +--> RetryAspect
                   |
                   +--> pjp.proceed(): attempt 1
                   |          |
                   |          +--> inner advice (if any)
                   |          +--> Target.method()
                   |          +--> side effect may have already occurred
                   |          +--> throws TemporaryFailureException
                   |
                   +--> catch matching exception
                   |
                   +--> pjp.proceed(): attempt 2
                              |
                              +--> inner advice runs again
                              +--> Target.method() runs again
                              +--> side effect may repeat
~~~

According to the Spring Framework documentation, `proceed()` inside `@Around` may be called **zero times, once, or many times**. That is technically valid, yet Spring **does not automatically evaluate whether the target is safe to run twice**.

An illustrative snippet:

~~~java
@Around("execution(* demo.ChargeApi.charge(..))")
public Object retry(ProceedingJoinPoint pjp) throws Throwable {
    try {
        return pjp.proceed();
    } catch (TemporaryFailureException first) {
        return pjp.proceed();
    }
}
~~~

This is a **fragment inside an aspect class**; it requires imports, exception declarations, a service bean, and Spring AOP configuration. It can call the target up to twice, yet lacks idempotency, a full exception policy, backoff, transaction ordering, or an overall time limit. Do not use it directly for real billing or message-sending commands.

Distinguish these counts:

- **Client proxy invocation count:** the caller may have called only once.
- **Retry attempts:** how many times `proceed()` was triggered.
- **Target execution count:** may be greater than one if continuation reaches the target each time.
- **Committed side effects:** does not necessarily equal the attempt count; it may have succeeded on an attempt that reported failure, or been rolled back separately.
- **Advice execution count:** depending on advisor ordering, advice outside retry may run once while advice inside retry runs on every attempt.

## 3. An Exception Does Not Prove the Prior Action Did Not Happen

| When the failure happens | Example | Conclusion before retrying |
| --- | --- | --- |
| Before side effect | Invalid input validation, failure before sending request | Side effect likely did not happen, though validation errors usually shouldn't be retried |
| After side effect | DB already committed, failure on next step; payment debited yet response lost | Retrying can **duplicate the effect** |
| Unknown state | Network timeout after sending request, unknown whether remote processed it | Cannot be safe based on exception alone |
| Confirmed transaction rollback | Failure inside a local DB transaction rolled back by rules | Local DB side effect may not have committed, yet remote side effects outside the transaction can still exist |

**A timeout does not mean the operation failed to complete.** If a payment API returns a timeout, the client has no proof "no charge occurred." To retry safely, the receiving API needs an idempotency key or the client must query the status by operation ID before retrying.

Other common examples:

- Email sent successfully, then an exception occurs while logging the result.
- Event published to a broker successfully, yet the publish acknowledgment is lost.
- Database write succeeds, then a secondary service call fails.
- Incrementing a counter or deducting a balance before throwing a runtime exception.
- Sending a resource-creation request with a fresh request ID on every attempt.

A retry loop blind to side-effect boundaries can make visible errors **fewer** while making duplicate behavior **more frequent**.

## 4. Bounded Retry Is Necessary, Not Sufficient

Example of a bounded retry structure:

~~~java
@Around("execution(* demo.ExternalOperation.execute(..))")
public Object retry(ProceedingJoinPoint pjp) throws Throwable {
    final int maxAttempts = 3;

    for (int attempt = 1; attempt <= maxAttempts; attempt++) {
        try {
            return pjp.proceed();
        } catch (TemporaryFailureException ex) {
            if (attempt == maxAttempts) {
                throw ex;
            }
        }
    }

    throw new IllegalStateException("Unreachable");
}
~~~

This is a **fragment**; `TemporaryFailureException`, `ExternalOperation`, and a valid Spring aspect class are required.

Key rules:

- `maxAttempts = 3` means at most **three total attempts including the initial one**, not three additional retries.
- `proceed()` must sit inside the loop; calling it outside the loop will not re-execute the target.
- Catch only **classified** errors; never retry every `RuntimeException` or `Throwable` by default.
- When attempts are exhausted, **rethrow the last exception**; never report a fake success result.
- On success, return the exact result of `pjp.proceed()`, preserving the method's return contract.
- If each attempt can produce a side effect, **a 3-attempt bound only caps the maximum number of duplicated effects**—it does not guarantee a single side effect.
- If the caller has a deadline, attempts plus backoff must not exceed the designed budget.

Determine **whether the operation is idempotent** before applying retry. Never treat bounded retry as a solution against double charging.

## 5. How Does Idempotency Differ From Retry?

**Retry** repeats an operation upon failure. **Idempotency** ensures that submitting the same logical operation multiple times does not multiply the intended business effect.

Example:

~~~text
logicalPayment = charge(order-12, amount=100)
    |
    +-- attempt 1 (key=order-12-charge)
    |
    +-- attempt 2 (key=order-12-charge)
    |
    +-- attempt 3 (key=order-12-charge)
~~~

All three attempts share **the same idempotency key**. If each attempt generates a fresh key, the receiving system may treat them as three independent operations.

Mandatory considerations:

1. The key identifies a **logical operation**, not an individual HTTP call.
2. The key must be reused when retrying the same operation, yet never shared across two genuinely distinct operations.
3. The key may need to be scoped by tenant/account, operation type, and a fingerprint of the request body.
4. When the same key arrives with a different body, return an explicit conflict rather than accidentally returning another operation's result.
5. Idempotency must be enforced **where the side effect is decided** or by a receiver honoring a matching contract.
6. Handle **in-progress**, completed, failed, and unknown states, plus TTL/retention policies.
7. If multiple replicas can receive the key, coordination or durable storage is required. A per-JVM cache is insufficient.
8. If recording the key and applying the external effect are not atomic, a failure window remains; reconciliation or target-system support is needed.

**Idempotent does not mean the target is never called again:** the target may execute twice, while the second call reads the already-completed result and skips applying a second side effect.

## 6. Java 17+ Spring AOP Example: Retrying Twice and Comparing Side-Effect Counts

We build an application using **Spring Framework 6.2.12**, **Java 17+**, and **Maven 3.9+** with a standard Spring context. There is no real DB or network, yet it deterministically reproduces **failing after a side effect has already occurred**.

Two methods on the Spring service:

- `unsafeCharge(requestId)`: each time the target runs, it increments a side-effect counter, **with no deduplication**.
- `guardedCharge(requestId)`: looks up a stored result for the same request ID in a `ConcurrentHashMap`, so the side-effect counter increments **only once within one JVM**.

An `AfterEffectFailureGate` deliberately throws `TemporaryFailureException` **on the first call after the side effect**. `RetryAspect` performs up to two attempts. The output shows **both targets are invoked twice while side-effect counts differ**.

> The `ConcurrentHashMap` mechanism is only a controlled simulation, **not a proper solution for distributed payments or durable persistence**. The goal is to observe retry hazards and where idempotency belongs.

### 6.1. Project Structure

~~~text
spring-aop-retry-side-effects/
├── pom.xml
└── src/main/java/demo/
    ├── ChargeApi.java
    ├── ChargeLedger.java
    ├── TemporaryFailureException.java
    ├── AfterEffectFailureGate.java
    ├── ChargeService.java
    ├── RetryAspect.java
    ├── AppConfig.java
    └── App.java
~~~

### 6.2. pom.xml

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-aop-retry-side-effects</artifactId>
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
            <groupId>org.aspectj</groupId>
            <artifactId>aspectjweaver</artifactId>
            <version>1.9.24</version>
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
                <configuration>
                    <mainClass>demo.App</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

`spring-context` provides `ApplicationContext` and the required Spring AOP modules. `aspectjweaver` provides the annotation/pointcut parser Spring uses for `@AspectJ` style; this example is **proxy-based** and uses neither compile-time nor load-time AspectJ weaving.

### 6.3. ChargeApi.java

~~~java
package demo;

public interface ChargeApi {
    String unsafeCharge(String requestId);
    String guardedCharge(String requestId);
}
~~~

Both methods are exposed via an interface so callers receive a **JDK dynamic proxy** when Spring auto-proxying applies. Going through the proxy is essential: merely calling `new ChargeService(...)` directly will not trigger the aspect.

### 6.4. ChargeLedger.java

~~~java
package demo;

import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.ConcurrentMap;
import java.util.concurrent.atomic.AtomicInteger;
import org.springframework.stereotype.Component;

@Component
public class ChargeLedger {

    private final AtomicInteger unsafeEffects = new AtomicInteger();
    private final AtomicInteger guardedEffects = new AtomicInteger();

    private final ConcurrentMap<String, String> processed =
            new ConcurrentHashMap<>();

    public String unsafe(String requestId) {
        int number = unsafeEffects.incrementAndGet();
        System.out.println("LEDGER unsafe side_effect=" + number);
        return "charged:" + requestId;
    }

    public String guarded(String requestId) {
        return processed.computeIfAbsent(requestId, key -> {
            int number = guardedEffects.incrementAndGet();
            System.out.println("LEDGER guarded side_effect=" + number);
            return "charged:" + key;
        });
    }

    public int unsafeCount() {
        return unsafeEffects.get();
    }

    public int guardedCount() {
        return guardedEffects.get();
    }
}
~~~

`unsafe` increments the side-effect counter **every time it is called**. `guarded` uses `computeIfAbsent`: for the same key while the entry remains in this map, it reuses the cached result without re-running the value-producing lambda. This simulates an **in-process** idempotency ledger, not an atomic commit with a remote API.

`AtomicInteger` makes counter increments atomic, **not `unsafe` idempotent**.

### 6.5. TemporaryFailureException.java

~~~java
package demo;

public class TemporaryFailureException extends RuntimeException {

    public TemporaryFailureException(String message) {
        super(message);
    }
}
~~~

In the demo, this exception is simply a failure signal designed for the retry aspect to catch. In real applications, naming an exception "Temporary" **does not prove the operation is safe to retry**.

### 6.6. AfterEffectFailureGate.java

~~~java
package demo;

import java.util.Set;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.stereotype.Component;

@Component
public class AfterEffectFailureGate {

    private final Set<String> failedKeys =
            ConcurrentHashMap.newKeySet();

    public void failAfterEffectOnce(String method, String requestId) {
        String key = method + ":" + requestId;

        if (failedKeys.add(key)) {
            System.out.println("GATE lost-ack " + method);
            throw new TemporaryFailureException(
                    "Simulated acknowledgement loss after effect");
        }
    }
}
~~~

The first time a `method:requestId` pair appears, the gate prints `GATE lost-ack` and throws an exception. Subsequent calls with the same key do not throw. The gate exists solely to simulate failure **after the ledger already applied the side effect**, with no real network or random latency.

### 6.7. ChargeService.java

~~~java
package demo;

import org.springframework.stereotype.Service;

@Service
public class ChargeService implements ChargeApi {

    private final ChargeLedger ledger;
    private final AfterEffectFailureGate gate;

    public ChargeService(ChargeLedger ledger,
                         AfterEffectFailureGate gate) {
        this.ledger = ledger;
        this.gate = gate;
    }

    @Override
    public String unsafeCharge(String requestId) {
        System.out.println("TARGET unsafeCharge " + requestId);
        String result = ledger.unsafe(requestId);
        gate.failAfterEffectOnce("unsafeCharge", requestId);
        return result;
    }

    @Override
    public String guardedCharge(String requestId) {
        System.out.println("TARGET guardedCharge " + requestId);
        String result = ledger.guarded(requestId);
        gate.failAfterEffectOnce("guardedCharge", requestId);
        return result;
    }
}
~~~

Each method performs three steps: print `TARGET`, execute the ledger side effect (or dedupe), and then the gate **may throw an exception**. An exception in the final step does not erase the side effect from the previous step. Retrying re-runs the entire method.

There is no circular dependency: `RetryAspect` does not inject `ChargeService` or the ledger; it only declares a pointcut. The ledger and gate Spring beans are not matched by `ChargeApi.*(..)`.

### 6.8. RetryAspect.java

~~~java
package demo;

import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class RetryAspect {

    @Around("execution(* demo.ChargeApi.*(..))")
    public Object retry(ProceedingJoinPoint pjp) throws Throwable {
        String methodName = pjp.getSignature().getName();
        final int maxAttempts = 2;

        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            System.out.println(
                    "RETRY " + methodName + " attempt=" + attempt);

            try {
                return pjp.proceed();
            } catch (TemporaryFailureException ex) {
                System.out.println(
                        "RETRY caught " + methodName +
                        " attempt=" + attempt);

                if (attempt == maxAttempts) {
                    throw ex;
                }
            }
        }

        throw new IllegalStateException("Unreachable retry state");
    }
}
~~~

Key points:

- `@Aspect` describes the advice, `@Component` registers the bean during component scanning.
- `@Around` selects only methods belonging to the `ChargeApi` contract.
- `pjp.proceed()` **sits inside the loop** and can re-invoke the target.
- Does not catch every exception type: retries only `TemporaryFailureException`.
- Does not swallow errors on the final attempt; the exception propagates to the caller.
- Does not alter arguments between attempts; the request ID remains identical.
- The return value from the target is returned to the caller on success.
- No delay is added in the demo so output ordering stays deterministic.

In production, also bound total duration/backoff and ensure the operation genuinely supports idempotency. This aspect is **intentionally unsafe** for `unsafeCharge` to illustrate the hazard.

### 6.9. AppConfig.java

~~~java
package demo;

import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration
@ComponentScan(basePackages = "demo")
@EnableAspectJAutoProxy
public class AppConfig {
}
~~~

`@ComponentScan` registers the service, ledger, gate, and aspect. `@EnableAspectJAutoProxy` enables the Spring AOP auto-proxy infrastructure. Having `@Aspect` without making the class a Spring-managed bean does not apply the advice.

### 6.10. App.java

~~~java
package demo;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public class App {

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            ChargeApi charges = context.getBean(ChargeApi.class);
            ChargeLedger ledger = context.getBean(ChargeLedger.class);

            System.out.println(
                    "IS_PROXY " + AopUtils.isAopProxy(charges));

            System.out.println("=== UNSAFE ===");
            String unsafe = charges.unsafeCharge("U-1");
            System.out.println("RESULT unsafe=" + unsafe);
            System.out.println("UNSAFE_EFFECTS " + ledger.unsafeCount());

            System.out.println("=== GUARDED ===");
            String guarded = charges.guardedCharge("G-1");
            System.out.println("RESULT guarded=" + guarded);
            System.out.println("GUARDED_EFFECTS " + ledger.guardedCount());
        }
    }
}
~~~

Run from the directory containing `pom.xml`:

~~~bash
mvn -q clean compile exec:java
~~~

### 6.11. Expected Logical Stdout

~~~text
IS_PROXY true
=== UNSAFE ===
RETRY unsafeCharge attempt=1
TARGET unsafeCharge U-1
LEDGER unsafe side_effect=1
GATE lost-ack unsafeCharge
RETRY caught unsafeCharge attempt=1
RETRY unsafeCharge attempt=2
TARGET unsafeCharge U-1
LEDGER unsafe side_effect=2
RESULT unsafe=charged:U-1
UNSAFE_EFFECTS 2
=== GUARDED ===
RETRY guardedCharge attempt=1
TARGET guardedCharge G-1
LEDGER guarded side_effect=1
GATE lost-ack guardedCharge
RETRY caught guardedCharge attempt=1
RETRY guardedCharge attempt=2
TARGET guardedCharge G-1
RESULT guarded=charged:G-1
GUARDED_EFFECTS 1
~~~

These lines represent **expected logical stdout from the sample code**, excluding separate Maven and Spring logs. The program runs both scenarios sequentially, so there is no nondeterministic ordering between them.

**UNSAFE:** One caller invocation, two `proceed()` calls, two target executions, **two side effects**. The first attempt already recorded a side effect before the exception escaped. The eventual success result did not erase the first execution.

**GUARDED:** One caller invocation, two `proceed()` calls, two target executions, **one side effect counted**. The `G-1` key stayed intact; on the second pass the map returned the prior result. This is **simulated idempotency within a single JVM**, not a guarantee that a real payment system will never double-charge.

## 7. Why Is an In-Memory Guard Not Enough for Production?

The `ConcurrentHashMap` in the example protects keys only within the running process:

- After a **restart**, key data is lost.
- When running **two replicas**, each process has its own map.
- If a side effect occurs on a remote service and the JVM crashes before storing the key's result, the app has no record of completion.
- If a different request body arrives with the same key, the map may return a result from an unrelated operation.
- Once a key expires or is evicted, a late retry can re-execute the operation.
- If multiple downstream systems are called without a shared transaction, an application-layer key cannot make all side effects atomic.

The safeguard must live at the **execution boundary**:

| Side-effect type | Design direction to evaluate |
| --- | --- |
| Internal DB operations | Unique constraints, transactions, and results stored by operation ID |
| External payment APIs | Idempotency keys **supported by the receiver's contract** |
| Messages/events | Outbox pattern, message keys, idempotent consumers, deduplication |
| Sending emails/SMS | Tracking message IDs, send/ACK status, and resend rules |
| Multi-system workflows | Reconciliation, state machines, and handling unknown states |

None of these solutions should be labeled absolute "exactly-once." Always document the **side-effect boundary**, where uniqueness is enforced, and real crash/replay scenarios.

## 8. Transaction Advice and Retry Aspect Ordering

This is a special **Spring AOP** concern when a service has `@Transactional`.

### 8.1. Retry Wrapping Outside Transaction Advice

~~~text
RetryAspect (outer)
  |
  +-- proceed attempt 1
  |       |
  |       v
  |    TransactionInterceptor
  |       |
  |       +-- begin transaction #1
  |       +-- target throws error
  |       +-- rollback per policy
  |
  +-- proceed attempt 2
          |
          v
       TransactionInterceptor
          |
          +-- begin transaction #2
          +-- target runs again
          +-- commit if valid
~~~

Spring Framework includes an example of a **retry aspect with higher precedence than transaction advice** so each attempt gets a fresh transaction. Order can be configured with `@Order` or `Ordered`, yet the outcome still depends on propagation mode and any caller-existing transaction. Never just add `@Order` and assume every attempt definitely opens a new transaction.

### 8.2. Transaction Wrapping Outside Retry Advice

~~~text
TransactionInterceptor (outer)
  |
  +-- one transaction context
           |
           +-- RetryAspect (inner)
                   |
                   +-- attempt 1: error
                   +-- attempt 2: retry
~~~

In this layout, retries can share **the same transaction**. After the first error, the transaction or database resource may already be marked rollback-only or left in an unsafe state to continue. A second attempt succeeding at the method level **is unlikely** to let the outer transaction commit.

At the same time, **a DB rollback cannot recall a remote charge, sent email, or completed HTTP request**. Thus placing retry outside transaction may be necessary, yet **is not enough** to protect external side effects.

### 8.3. Ordering Declaration Pattern

~~~java
@Aspect
@Component
@Order(Ordered.HIGHEST_PRECEDENCE)
public class RetryAspect {
    // ...
}
~~~

This is an **illustrative fragment showing how ordering is declared**, requiring `org.springframework.core.Ordered` and `org.springframework.core.annotation.Order`. Do not add a second `RetryAspect` class to section 6's sample project. Precedence is not a deduplication mechanism; it only determines the advice's position in the chain.

## 9. Logging, Metrics, and Transactions May Repeat at Different Attempt Counts

If `MetricsAspect` sits **outside** `RetryAspect`:

~~~text
MetricsAspect
  |
  +-- RetryAspect
         |
         +-- proceed #1 -> target
         +-- proceed #2 -> target
~~~

Metrics may measure one logical invocation while the target runs twice.

If `MetricsAspect` sits **inside** retry:

~~~text
RetryAspect
  |
  +-- proceed #1 -> MetricsAspect -> target
  +-- proceed #2 -> MetricsAspect -> target
~~~

Metrics advice may run twice. Therefore, track **request counts**, **retry attempt counts**, and **committed effect counts** separately. Never infer side-effect counts solely from one aspect's log lines without understanding advisor ordering.

An inner `@AfterThrowing` or transaction advisor can also execute on each attempt. An outer advice may see only the **final** result or exception returned from the retry aspect. Spring does not guarantee order across distinct aspects unless explicitly configured.

## 10. Which Errors Should Be Caught and How Should It End?

An anti-pattern:

~~~java
try {
    return pjp.proceed();
} catch (Exception anything) {
    return pjp.proceed();
}
~~~

This is an **unsafe** fragment. It retries validation errors, permission denials, non-retryable duplicate keys, and programming bugs. If the operation has side effects, this catch block amplifies them.

A retry policy must define:

1. **Exception allowlist or predicate** for genuinely transient failures.
2. **Maximum attempts** and an overall deadline; never retry infinitely.
3. **Backoff/jitter** to prevent synchronized requests from hammering an overloaded service.
4. **Idempotency/reconciliation** for unknown-outcome states.
5. **Final outcome** when attempts are exhausted: transparent exception or failure status, never a fabricated success string.
6. **Observability**: correlation ID and attempt number.
7. **Cancellation/interruption**: do not swallow cancellation or thread interruption state.
8. **Narrow pointcut scope** limited to business operations reviewed as retryable.

Do not use `catch(Throwable)` by default to retry fatal errors. Even an exception named "Transient" thrown by a library must still be evaluated against **the method's actual side effects**.

## 11. Backoff, Timeout Budgets, and Retry Storms

Suppose 100 client calls hit network errors simultaneously. If each invocation immediately performs 3 retry attempts, target load can spike to 300 calls in a short window, slowing an already overloaded service even further.

Mitigations:

- Use bounded retries, never infinite retries.
- Consider exponential backoff and jitter when many clients retry concurrently.
- Allocate an overall **timeout budget** across all retries rather than summing per-attempt timeouts unboundedly.
- When failure rates are high, consider circuit breakers or rate limiting.
- Avoid long `Thread.sleep` calls on HTTP handler threads inside synchronous `@Around` advice.
- Check whether upstream/downstream layers also retry to prevent **multi-layer retry amplification**.

Backoff primarily regulates **load and recovery probability**—it does not prevent duplicate side effects; idempotency still must be designed separately.

## 12. Proxy Boundaries and Self-Invocation

Spring AOP advises only eligible calls **passing through the proxy**. If a method inside the target calls a retryable method via `this.method()`:

~~~java
public void process(String id) {
    this.unsafeCharge(id);
}
~~~

this internal call does not go back through the Spring AOP proxy, so `RetryAspect` may **not trigger** for `unsafeCharge`. That differs from an around advice that already ran and called `proceed` twice.

Limitations to keep in mind:

- **JDK dynamic proxies** expose matching public interface methods.
- **CGLIB** can advise overridable instance methods when called through the class proxy, yet cannot override `private`/`final` methods.
- Beans instantiated manually with `new` are not auto-proxied by Spring AOP.
- Overly broad pointcuts can match helpers, recorders, and gateways invoked by the advice itself, causing nested recursion/retries.
- If internal calls need retries, prefer extracting the operation to another Spring bean and injecting its proxy rather than relying casually on `AopContext.currentProxy()`.

In section 6's example, the pointcut selects only methods on `ChargeApi` to avoid affecting `ChargeLedger` and `AfterEffectFailureGate`.

## 13. Required Tests

| Scenario | Must verify |
| --- | --- |
| Target succeeds on first attempt | Target runs exactly once, zero retries |
| Failure before side effect, then success | Retries within configured exceptions/attempt budget |
| **Failure after side effect**, then success | Detects multiplied side effects when unguarded |
| Same key retried with guard | Committed effect count does not increase within guaranteed scope |
| Non-allowlisted exception | Does not retry |
| All attempts fail | Final exception escapes; no fake success reported |
| Same key with different payload | Explicit conflict rule applies |
| Two distinct logical operations | Not falsely deduplicated |
| Concurrent calls with same key | Verifies real atomicity in storage/receiver |
| Multiple replicas or restart | Verifies durability without relying on a single-JVM map |
| Transaction advice present | Verifies advisor order and per-attempt boundaries |
| Self-invocation | Does not assume retry triggers |
| Retries nested across layers | Measures amplification and deadlines |

For the runnable example, add in `App.main` after both scenarios:

~~~java
if (ledger.unsafeCount() != 2) {
    throw new AssertionError("Unsafe operation should have run twice");
}
if (ledger.guardedCount() != 1) {
    throw new AssertionError("Guarded effect should be recorded once");
}
~~~

This is a **test fragment**, not a standalone Java file. Both assertions represent intentional comparison outcomes for the lesson, **not a recommendation to tolerate double charges in real systems**.

## 14. Common Mistakes When Writing RetryAspect

| Symptom | Typical cause | Fix |
| --- | --- | --- |
| Payment charged twice | Retrying after side effect when ACK was lost | Provider-side idempotency or reconciliation |
| Service returns success yet DB/events duplicated | Caller sees final attempt's result, missing first attempt's side effect | Track committed effects and operation IDs |
| `maxAttempts=2` still causes duplicate actions | Bounded retry does not deduplicate | Add idempotency |
| Each attempt generates a new idempotency UUID | Downstream treats each attempt as a separate operation | Keep a stable key per logical operation |
| Guard works locally but fails in cluster | Per-JVM in-memory map | Durable shared store or receiver-side idempotency |
| Validation errors get retried | Overly broad catch block | Retry only classified exceptions |
| Method succeeds yet transaction rolls back | Retry ran inside a rollback-only transaction | Inspect transaction advice order/boundaries |
| DB rolls back yet email still goes out | External side effect sits outside the transaction | Use outbox/idempotency and reconciliation |
| Retry skips internal calls | Self-invocation bypassed proxy | Refactor to another Spring bean |
| Retry aspect runs on the recorder too | Pointcut too broad | Restrict to service API/package/annotation |
| Logging aspect counts one request while target runs twice | Logging sits outside retry | Count logical requests and attempts separately |
| Overload worsens after failures | Retry storm without backoff/budget | Add backoff/jitter/circuit breaker and request limits |
| Attempts exhausted yet caller gets OK | Advice swallowed exception or returned bad fallback | Propagate clear error/status |

## 15. Safe Spring AOP Retry Implementation Checklist

- Have all side effects been listed: DB, remote APIs, brokers, emails, caches, counters?
- Can we prove the exception happened **before** the effect? If not, treat state as unknown.
- Does the operation carry a stable idempotency key across attempts?
- Is idempotency honored and durably persisted by the party **performing the side effect**?
- Are same-key/different-body conflicts and in-progress operations handled?
- Are attempt limits, overall deadlines, and backoff configured where needed?
- Are only classified retryable exceptions caught?
- Once retries are exhausted, does the real exception/status reach the caller?
- Has advisor ordering relative to `@Transactional` been verified?
- Do remote side effects lie outside local transactions?
- Do calls actually pass through the Spring proxy rather than self-invocation?
- Does the pointcut exclude recorders, infrastructure, and non-retryable methods?
- Is there an explicit test for **failure after side effect** checking counters or system state?
- Are concurrency, restarts, and multi-layer retries tested?
- Are separate metrics tracked for **attempts** and **committed side effects**?

## 16. Self-Check Questions

**1. Why can calling `pjp.proceed()` twice be dangerous?**

Because Spring AOP's continuation can forward the call to the target twice, repeating data writes or external requests inside the target.

**2. Does a timeout prove the previous transaction definitely failed?**

No. The response may have been lost after the receiver already committed.

**3. What does `maxAttempts=2` guarantee, and what does it not guarantee?**

It caps the maximum attempts made by that retry aspect, yet **does not guarantee only one side effect per logical operation**.

**4. Should the idempotency key change on the second attempt?**

No. Retries of the same logical operation must keep the same key per contract.

**5. Why is `ConcurrentHashMap` in the demo insufficient for production?**

It lives in one process, is lost on restart, is not synchronized across replicas, and is not atomic with remote side effects.

**6. When retry sits outside Spring transaction advice, can each attempt get a new transaction?**

Potentially yes, if ordering and transaction boundaries align; verify with real propagation and caller setup.

**7. Does a DB rollback recall an already sent email?**

Normally no; that is a side effect outside the DB transaction.

**8. Does the retry aspect work for `this.method()` inside the same target?**

Not via ordinary self-invocation, because that call bypasses the Spring AOP proxy.

**9. What is the best proof that the guard works?**

Inspect **committed side-effect counts or system state**, not just responses or advice log lines.

**10. If a remote operation lacks idempotency and times out in an unknown state, what should you do?**

Do not retry blindly; query/reconcile state first or design idempotency with the receiver.

## 17. Official Reference Sources

- Spring Framework — **Declaring Advice / Around Advice**, how `proceed()` can be called multiple times: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html
- Spring Framework — **An AOP Example**, retry aspect and precedence ahead of transaction advice: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/example.html
- Spring Framework — **Proxying Mechanisms**, JDK/CGLIB and self-invocation: https://docs.spring.io/spring-framework/reference/core/aop/proxying.html
- Spring Framework — **Declarative Transaction Management**, transaction advice: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — **@AspectJ Support**: https://docs.spring.io/spring-framework/reference/core/aop/ataspectj.html

**Conclusion:** With Spring `@Around`, retrying by calling `ProceedingJoinPoint.proceed()` again can re-trigger the target and inner advice. If the first pass produced a side effect before failing, the caller sees a single success result while the business action may have executed multiple times. Exception classification, attempt bounds, transaction advisor control, and backoff matter; **idempotency and reconciliation at the exact site of the side effect** are what truly eliminate duplicate-execution risk.
