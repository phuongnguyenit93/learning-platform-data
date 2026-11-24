# Security Interceptor Ordering with `@Transactional` and Other Advice

## 1. Why Does Interceptor Ordering Determine Security Behavior?

A Spring service method can carry `@PreAuthorize`, `@PostAuthorize`, `@Transactional`, and other advice such as logging, auditing, caching, or retries all at once. These annotations are not simply statements executing sequentially in the order they appear in source code. Most are handled by **Spring AOP advisors/interceptors** wrapping the method call.

For a given method, advisor ordering determines:

- **Who runs before the method body?** Does authorization happen before opening a transaction, logging, or performing heavy work?
- **Who runs after the method body?** Does a `@PostAuthorize` check happen before or after the transaction commits?
- **Do exceptions pass through the transaction interceptor?** If an authorization error is thrown after the transaction has already ended, that transaction cannot be rolled back by that exception.
- **Which advice can short-circuit other advice?** Cache hits, unproxied calls, or thread switches with `@Async` can alter the execution path from expectations.

This lesson focuses on **Spring Security method authorization in Spring MVC/servlet applications using Spring AOP in proxy mode**, combined with imperative transactions (JDBC/JPA). For reactive transactions, AspectJ weaving, and other AOP setups, exact mechanics may differ and should be checked separately.

## 2. Spring AOP Forms a Nested Wrapping Chain

When a call enters a service through a proxy, visualize it as:

```text
Client
  |
  v
Spring AOP proxy
  |-- Higher-precedence advice (smaller order) : before
  |    |-- Next advice                        : before
  |    |    |-- Transaction interceptor       : begin
  |    |    |    |-- Method body
  |    |    |-- Transaction interceptor       : commit/rollback
  |    |-- Next advice                        : after
  |-- Higher-precedence advice                : after
  |
  v
Client receives result / exception
```

**Rule:** in Spring AOP, an advisor with a **smaller** `order` has **higher precedence**—it executes earlier on the way into the call and finishes later on the way out. For example, `order=100` is an **outer** wrapper around `order=200`.

For `@Around`-style advice, the sequence works as:

```text
Outer.before
  Inner.before
    Method
  Inner.after
Outer.after
```

Thus, saying "advisor A runs before B" describes only the **inbound** direction. For checks after the method executes, the outbound order is **reversed**. That is the key to understanding how `@PostAuthorize` interacts with transactions.

Distinctions to keep clear:

- **Advisor order**: ordering among interceptors applied to the same join point; configurable via `Ordered`, `@Order`, or infrastructure-specific settings.
- **Annotation order in source**: swapping the lines `@Transactional` and `@PreAuthorize` **does not change advisor order**.
- **Service call order**: calling `serviceA` then `serviceB` is business flow order, distinct from interceptor ordering wrapping a single method.

When two advisors share the same `order` value with no further tie-breaker, do not rely on incidental container registration order.

## 3. Method Security Interceptors and Default Ordering

When enabled:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;

@Configuration
@EnableMethodSecurity
public class MethodSecurityConfig {
}
```

Spring Security registers advisors corresponding to the enabled method security features. With default `@EnableMethodSecurity` settings, `@PreAuthorize`, `@PostAuthorize`, `@PreFilter`, and `@PostFilter` are supported; `@Secured` and JSR-250 must be enabled explicitly via annotation attributes.

According to the order defined by Spring Security in `AuthorizationInterceptorsOrder`, common positions are:

| Relevant advisor | Order | Role |
| --- | ---: | --- |
| `@PreFilter` | 100 | Filters input parameters before the method body |
| `@PreAuthorize` | 200 | Checks permissions before the method body |
| `@Secured`, when enabled | 300 | Checks permissions via `@Secured` annotation |
| JSR-250, when enabled | 400 | Checks `@RolesAllowed` / related annotations |
| `@PostAuthorize` | 500 | Checks permissions based on result after method returns |
| `@PostFilter` | 600 | Filters returned collection |

Some newer releases include additional return-value security advisors (such as `SECURE_RESULT` elsewhere in the same chain). **Only advisors that are enabled and match the method execute**; the table is a mental model for design, not a claim that every method runs all six interceptors. Check your exact Spring Security version when precise order values matter.

For example, if a method is protected by `@PreAuthorize` and `@PostAuthorize`, the two interceptors can be visualized as:

```text
@PreAuthorize  (200): check on entry
  @PostAuthorize (500): wraps call; check on exit
    method body
  @PostAuthorize (500): evaluate returnObject
@PreAuthorize (200): exit
```

If `@PostFilter` also applies, because `600` sits **inside** `500`, post-method filtering normally runs on the outbound path **before** the `@PostAuthorize` check. Avoid baking assumptions about this order into business logic when using custom interceptor configurations; test in practice.

## 4. Where Does `@Transactional` Sit Under Standard Configuration?

Spring Framework assigns `order = Ordered.LOWEST_PRECEDENCE` by default to the transaction advice enabled by `@EnableTransactionManagement`. That value represents very low precedence compared to method security advisors at 100–600.

Consider a method with `@PreAuthorize`, `@PostAuthorize`, and `@Transactional`, assuming no outer transaction and no other advisor altering order:

```text
Caller
  -> @PreAuthorize (order 200): ALLOW
     -> @PostAuthorize (order 500): enter wrapper
        -> Transaction advice (LOWEST_PRECEDENCE): BEGIN
           -> Method body / repository / write
        <- Transaction advice: COMMIT if method body succeeds
     <- @PostAuthorize: check returnObject, may DENY
  <- Caller receives result or AccessDeniedException
```

**Important consequences:**

1. `@PreAuthorize` can deny before a new transaction is opened; this usually avoids an unnecessary transaction.
2. If a `@PreAuthorize` expression calls a policy bean that queries the DB, that check may execute **outside the protected method's transaction**, because transaction advice sits further inside. Consistency between "permission check" and "write" must be designed deliberately.
3. If `@PostAuthorize` denies **after the transaction has already committed**, that exception cannot go back to roll back the committed changes.
4. If an **outer transaction from the caller** already exists, any measurement or conclusion about active transactions must account for the inherited transaction; the chain above describes opening a new transaction at this method.

Consequently, combining `@PostAuthorize` with **database-writing methods** is a risky choice. Spring Security officially advises against using `@PostAuthorize` on classes/methods performing database writes, especially when the same method also carries `@Transactional`.

### Error-Prone Example

```java
import org.springframework.security.access.prepost.PostAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceService {
    private final InvoiceRepository repository;

    public InvoiceService(InvoiceRepository repository) {
        this.repository = repository;
    }

    // RISK ILLUSTRATION ONLY: do not use as an invoice update design.
    @Transactional
    @PostAuthorize("returnObject.ownerUsername == authentication.name")
    public Invoice updateOwnerNote(Long id, String text) {
        Invoice invoice = repository.findById(id).orElseThrow();
        invoice.setNote(text);
        return invoice;
    }
}
```

This is a **Spring component**, assuming `Invoice` entity and repository exist. Under standard ordering, once the method finishes and the transaction commits, `@PostAuthorize` finally inspects `returnObject`. An unauthorized caller may receive `AccessDeniedException`, **yet the update has already committed**. An HTTP denial does not guarantee data was rolled back.

A sounder design is **checking permissions before the write operation** and scoping update queries by trusted tenant/owner/ACL:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class InvoiceWriteService {
    private final InvoiceRepository repository;

    public InvoiceWriteService(InvoiceRepository repository) {
        this.repository = repository;
    }

    @PreAuthorize(
        "hasAuthority('invoice:write') and " +
        "@invoicePolicy.canEdit(authentication, #invoiceId)"
    )
    @Transactional
    public void editNote(Long invoiceId, String note) {
        Invoice invoice = repository.findById(invoiceId).orElseThrow();
        invoice.setNote(note);
    }
}
```

The snippet above illustrates **only method-level authorization**. In multi-user systems, checking `canEdit` before the transaction opens can suffer a race/TOCTOU if permissions or ownership change between check and write. For sensitive updates, re-verify constraints inside the same transaction or use `UPDATE ... WHERE id = ? AND tenant_id = ? AND owner_id = ?` with appropriate versioning/locking; never trust client-supplied owner/tenant values as the source of truth.

## 5. When Should a Transaction Wrap the Permission Check Too?

Some operations must verify permissions before writing using the same snapshot/transaction, or need `@PostAuthorize` exceptions to be seen by the transaction interceptor before deciding to commit. In those cases, you can configure transaction advice with **higher** precedence than security advice:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.security.config.annotation.method.configuration.EnableMethodSecurity;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration
@EnableTransactionManagement(order = 0)
@EnableMethodSecurity
public class TxAndSecurityConfig {
}
```

With `order=0`, the transaction advisor sits outside `@PreAuthorize(200)` and `@PostAuthorize(500)` on the same join point:

```text
Caller
  -> Transaction advice (0): BEGIN
     -> @PreAuthorize (200): ALLOW or DENY
        -> @PostAuthorize (500): enter
           -> Method body
        <- @PostAuthorize (500): check result
  <- Transaction advice: COMMIT if everything succeeds,
                         ROLLBACK if matching exception propagates
```

If `@PostAuthorize` throws `AccessDeniedException`, that is a runtime exception; under default rollback rules and while the transaction is still active at the point where the interceptor observes the exception, the transaction rolls back.

**However, do not switch to `@EnableTransactionManagement(order = 0)` merely to "patch" a post-write permission check:** configuring order affects transaction advisors registered by this infrastructure across the context, causing transactions to start **even before authorization checks**. That adds overhead, changes transaction lifecycles, and alters interactions with logging, caching, retries, and lazy loading. Transaction rollback also **cannot undo** emails already sent, events published outside the transaction, changes committed in separate `REQUIRES_NEW` transactions, or external side effects.

Prefer authorizing **before mutating data**. If you need post-processing permission checks on pure read results, `@PostAuthorize` fits better. When you must combine transactions and post-authorization, write integration tests verifying both the result **and** database state, not just the exception.

### What Does `@EnableMethodSecurity(offset)` Mean?

`@EnableMethodSecurity(offset = n)` (since Spring Security 6.3) adds `n` to the default orders of the security interceptor group activated by this annotation. For example:

```java
@Configuration
@EnableMethodSecurity(offset = 50)
class OffsetMethodSecurityConfig {
}
```

Then `@PreFilter` shifts from 100 to 150, `@PreAuthorize` from 200 to 250, `@PostAuthorize` from 500 to 550, etc. This **shifts the entire group** relative to other advisors; it does not alter relative ordering among security advisors in that group. Do not pick arbitrary huge offsets or collide with other advisors; inspect the actual order after configuring.

**Key distinction:** `@EnableTransactionManagement(order = ...)` sets the order for the **transaction advisor**. `@EnableMethodSecurity(offset = ...)` shifts the **security advisors**. Placing `@Order` on a service class is **not** the standard way to change either of these two orders.

## 6. Tuning Other `@Aspect`s: Audit, Logging, Metrics

For custom advice written with `@Aspect`, you can put `@Order` on the aspect bean. The example below uses `@Order(250)`, meaning on a method protected only by `@PreAuthorize(200)` and the default transaction advisor, the audit advice runs **after entry check succeeds** yet **before the transaction begins**:

```java
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.core.annotation.Order;
import org.springframework.stereotype.Component;

@Aspect
@Component
@Order(250)
public class ServiceAuditAspect {
    @Around("execution(* com.example.application.service.*.*(..))")
    public Object audit(ProceedingJoinPoint invocation) throws Throwable {
        String operation = invocation.getSignature().getName();
        try {
            return invocation.proceed();
        } finally {
            // Send audit record through a trusted application component.
            // Do not log tokens, credentials, or full sensitive data.
            System.out.println("operation-finished=" + operation);
        }
    }
}
```

This is a **component class**: the pointcut matches only when the package structure aligns, Spring AOP is enabled, and the bean is registered. `finally` runs even if the inner method throws an exception; it does not prove the transaction committed and must not emit an "operation succeeded" event without knowing the real outcome.

If you need to record **every invocation attempt**, including calls denied by `@PreAuthorize`, place auditing **outside** authorization, such as an order below 200. In exchange, outer advice can see arguments from unauthenticated/unauthorized callers, so log minimally, control sensitive data, and distinguish `attempt`, `denied`, and `success`.

Do not deduce that `@Order(250)` always runs after **all** security checks: `@Secured(300)` and JSR-250 (400), if enabled, sit **inside** it. To make auditing run after all "pre-method" checks, inspect which advisors are actually active, check custom orders, and consider placing auditing at an already-protected business boundary.

### Order Diagram with Custom Advice

With `@PreAuthorize(200)`, audit `@Order(250)`, `@PostAuthorize(500)`, and default transaction:

```text
PreAuthorize: check
  Audit: enter
    PostAuthorize: enter
      Transaction: begin
        Method
      Transaction: commit
    PostAuthorize: check
  Audit: exit
Return / exception
```

If `PostAuthorize` denies, `Audit` observes the exception in `finally`; however, the inner transaction has already completed. This shows that **where logging happens, where permission is checked, and where commit happens are three independent concerns**.

## 7. Other Advice and Hard-to-Spot Effects

| Advice/feature | Why ordering matters | What to verify |
| --- | --- | --- |
| `@Cacheable` | A cache hit can return a result without calling `proceed()`; if the cache advisor sits outside permission checks, inner method security may be skipped on cache hits | Permissions must be checked on every access path; cache keys must scope by principal/tenant when data varies per user |
| `@Retryable` / retry advice | Retries outside a transaction normally open a fresh transaction per attempt; security position determines whether checks run once or per retry | Can permissions change between retries, are side effects idempotent, and does each attempt truly get a fresh transaction |
| `@Async` | Crosses an executor/thread boundary; imperative `SecurityContext` and transactions are normally thread-bound | Which thread runs security advice, how `SecurityContext` is propagated, and where transactions open |
| Logging/metrics `@Around` | Outside authorization measures denied requests too; inside sees only calls passing outer checks | Never log sensitive arguments; distinguish success/failure/deny |
| Event/audit side effects | May fire before commit or before post-method checks | Use transaction-aware outbox/event timing; never report completion before commit |
| Custom `AuthorizationManager` advisor | Can be positioned elsewhere in the chain, replacing or combining built-in advisors | Test ordering, pointcut scope, duplicate or skipped checks |

**Caching is an especially dangerous case:** if user A's result is cached under a key lacking tenant/principal, user B can receive A's data. Even when cache ordering is tuned, multi-tenant data still needs proper keys, data partitioning, and source-level access policies. `@Cacheable` on the same method as `@PostAuthorize` must be tested on both cache hit and cache miss because short-circuiting the chain can bypass part of the advice.

For retries, Spring Framework documentation notes that the default configuration of `@Retryable` with `@Transactional` allows retry to wrap outside so each attempt runs in its own transaction; however, specific versions, order configs, and retry frameworks must be verified. **Do not extrapolate** this to arbitrary custom retry advisors.

For async, **you cannot reason solely from a numeric order table** once execution hops to a worker thread. With Spring Security, you can use dedicated executors/decorators to propagate `SecurityContext` safely; you must still verify the service enforces authorization at the right point. Imperative transactions do not automatically follow threads across executors.

## 8. Proxies and Self-invocation: Even the Right Order May Not Apply

In standard proxy mode, advice runs when a call **goes through the Spring proxy**. Calling `this.otherMethod()` within the same instance typically jumps straight to the method without re-entering the proxy, even when `otherMethod()` carries `@Transactional` or `@PreAuthorize`.

**Anti-pattern** example:

```java
import org.springframework.security.access.prepost.PreAuthorize;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class TransferService {
    public void processTransfer(Long accountId) {
        // Self-invocation: does not pass through the current bean's proxy.
        this.persistTransfer(accountId);
    }

    @PreAuthorize("@accountPolicy.canTransfer(authentication, #accountId)")
    @Transactional
    public void persistTransfer(Long accountId) {
        // Execute data update. This is a component example.
    }
}
```

If callers only invoke `processTransfer` and that method is not protected at an appropriate entry point, `persistTransfer` may miss its expected security/transaction advice. Rather than "changing order" to fix this:

- Place authorization checkpoints at **service entry points called through proxies**.
- Extract the protected operation into **another Spring bean** and invoke it via dependency injection.
- Use authorization checks in data logic and real transactions as an additional defense layer.

You must consider proxyability for `private`, `final`, non-public methods, JDK/CGLIB proxies, and annotation placement. Spring Framework supports some non-public methods for class-based transactional proxies, yet you must not assume method security behaves identically in every case. The easiest-to-verify approach: guard public service methods called through Spring beans and write integration tests over real call paths.

## 9. Standalone Java 17 Example: Comparing Two Transaction Positions

The program below **simulates an interceptor chain in plain Java**, without Spring, SQL, or real transactions. It intentionally highlights the difference in where `post-check` and `commit` happen. Save as `AdvisorOrderDemo.java`:

```java
public class AdvisorOrderDemo {

    static void preAuthorize(boolean allowed, Runnable next) {
        System.out.println("pre.check");
        if (!allowed) {
            throw new SecurityException("denied before");
        }
        next.run();
    }

    static void postAuthorize(boolean allowed, Runnable next) {
        next.run();
        System.out.println("post.check");
        if (!allowed) {
            throw new SecurityException("denied after");
        }
    }

    static void transaction(Runnable next) {
        System.out.println("tx.begin");
        try {
            next.run();
            System.out.println("tx.commit");
        } catch (RuntimeException ex) {
            System.out.println("tx.rollback");
            throw ex;
        }
    }

    static void write() {
        System.out.println("write");
    }

    static void defaultOrder() {
        System.out.println("-- default order --");
        try {
            preAuthorize(true,
                () -> postAuthorize(false,
                    () -> transaction(AdvisorOrderDemo::write)));
        } catch (SecurityException ex) {
            System.out.println("caller: " + ex.getMessage());
        }
    }

    static void transactionOuter() {
        System.out.println("-- transaction outer --");
        try {
            transaction(
                () -> preAuthorize(true,
                    () -> postAuthorize(false, AdvisorOrderDemo::write)));
        } catch (SecurityException ex) {
            System.out.println("caller: " + ex.getMessage());
        }
    }

    public static void main(String[] args) {
        defaultOrder();
        transactionOuter();
    }
}
```

Compile and run with JDK 17 or higher:

```bash
javac AdvisorOrderDemo.java
java AdvisorOrderDemo
```

Exact stdout:

```text
-- default order --
pre.check
tx.begin
write
tx.commit
post.check
caller: denied after
-- transaction outer --
tx.begin
pre.check
write
post.check
tx.rollback
caller: denied after
```

In the first case, `post.check` occurs **after** `tx.commit`, so the exception from post-checking is no longer inside the transaction call. The second case shows that when the transaction wraps outside, the exception from `postAuthorize` passes through the transaction wrapper and triggers the rollback branch. **Do not treat this simulation as proof that your application's transaction rolled back**: JPA flushing, propagation, exception handling, outer transactions, and side effects must all be tested directly.

## 10. How to Verify Real Spring Advisor Ordering

### 10.1 Inspecting the Registered Chain on a Proxy

In an application with Spring AOP proxies, you can inspect a bean's advisor list via test code or debugging tools:

```java
import org.springframework.aop.Advisor;
import org.springframework.aop.framework.Advised;
import org.springframework.core.Ordered;

// Illustrative snippet in a Spring test with an ApplicationContext named context.
Object bean = context.getBean("invoiceWriteService");

if (bean instanceof Advised advised) {
    for (Advisor advisor : advised.getAdvisors()) {
        String order = (advisor instanceof Ordered ordered)
            ? Integer.toString(ordered.getOrder())
            : "not-explicit";
        System.out.println(advisor.getClass().getSimpleName()
            + " order=" + order);
    }
}
```

This snippet is **not a standalone program**: it requires a real bean and `ApplicationContext`. Some systems have nested proxies, advisors appearing under different types/instances, or infrastructure not fully revealed by printing class names. The key is to **observe** rather than hard-coding assertions on internal Spring bean names that can change across versions.

### 10.2 Measuring When a Transaction Is Active

In integration tests or custom logging **containing no sensitive data**, you can check inside a service/policy:

```java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
    TransactionSynchronizationManager.isActualTransactionActive();
```

Record `active` at **the exact points of interest**: before the method, inside the body, after the method, and inside custom advice. `isActualTransactionActive()` indicates whether a transaction is active on the current thread; it does not prove SQL statements committed/rolled back or that a given resource enlisted in the transaction.

If a call is already inside an outer transaction, measurements may return `true` even if the method's own transaction advice has not run. Test separately with a caller having no transaction and a caller with an outer `@Transactional`.

### 10.3 Minimum Integration Test Suite

| Scenario | What to assert |
| --- | --- |
| `@PreAuthorize` denies before write | Method body and repository write do not run |
| Valid permission, method succeeds | Data commits as expected |
| `@PostAuthorize` denies after write with inner transaction | May receive `AccessDeniedException` **after commit**; assert DB state to catch it |
| Transaction intentionally configured outside post-authorization | Runtime exception before commit rolls back participating DB changes per rollback rules |
| `this.securedMethod()` call | Reproduce and fix skipping of security/tx advice |
| Cache miss/cache hit with two users/tenants | Never leaks wrong data; security still enforced as designed |
| Retry hits transient failure | Retry count, transaction state, and side effects are correct |
| `@Async` or executor | `SecurityContext` and transaction boundaries are correct on worker thread |

Use `@SpringBootTest` with a real test database or Testcontainers to verify commit/rollback; pure mock tests will not prove whether data committed. When asserting security, invoke the service **via a bean retrieved from the Spring context**. `@WithMockUser` sets up a test security context but does not substitute for testing the real proxy path.

To test audit ordering, record an event list in the test capturing `preAuth`, `audit.before`, `tx.active`, `audit.after`, and `deny`. Avoid testing ordering from vague logs or checking only HTTP 403 responses.

## 11. Recommended Design Rules

1. **Check permissions before causing side effects:** use `@PreAuthorize` or `AuthorizationManager` and policies at trusted service points. For sensitive writes, keep owner/tenant/ACL conditions inside the transaction/query to reduce races.
2. **Use post-authorization mainly for reads:** `@PostAuthorize` fits returned resources that must be inspected; never treat post-method exceptions as a default rollback mechanism.
3. **Define transaction boundaries explicitly:** account for order, propagation, outer transactions, commits, rollback rules, and non-DB events.
4. **Clarify custom advice intent:** do you want to audit all attempts or only authorized operations? Should metrics count denials or only successful calls?
5. **Treat cache, retry, and async as real flow changers:** verify cache hits, second attempts, and worker threads.
6. **Ensure calls pass through proxies:** avoid self-invocation on methods relying on AOP annotations.
7. **Adjust advisor order only with a concrete requirement and proving tests:** Spring version upgrades can alter registered advisors; never treat order numbers as unverified formulas.

## 12. Common Pitfalls and Fixes

| Wrong assumption | Possible consequence | Proper understanding / fix |
| --- | --- | --- |
| "Writing `@Transactional` above `@PreAuthorize` makes the transaction run first" | Wrong order prediction | Advisor order is determined by AOP, not annotation position |
| "`@PostAuthorize` throwing an exception always rolls back" | Writes commit while API returns 403 | Check transaction position; prefer checking before writes |
| "Smaller order runs first on both entry and exit" | Reversed understanding of post-check timing | Smaller order runs earlier on entry, **later** on exit |
| "`@Order(250)` means after all security checks" | Advice can run before `@Secured`/JSR-250 | Inspect all enabled advisors |
| "Putting `@Order` on the service changes transaction order" | Config fails to take effect | Use `@EnableTransactionManagement(order=...)` or proper advisor config |
| "Policy check before transaction is always consistent" | Race between permission check and write | Scope data/locking/tx appropriately; test races |
| "Cache hits still run inner method security" | Can bypass checks and leak cache across tenants | Check order, keys, and permissions on both hits and misses |
| "`@Async` preserves `SecurityContext` and transactions" | Missing identity or transaction on worker thread | Design explicit propagation and integration tests |
| "`this.method()` still activates annotations" | Bypasses authorization/transactions | Call via Spring bean/proxy or redesign services |
| "HTTP 403 proves no DB change happened" | False negative in security tests | Assert real DB state and side effects after requests |

**Key review question:** "When the method updates data, have permissions already been verified using trusted data? When post-checks run, is the transaction still open or already committed? If an advice short-circuits or switches threads, do permission checks still run?"

## Official References

- [Spring Security — Method Security](https://docs.spring.io/spring-security/reference/servlet/authorization/method-security.html): per-annotation interceptors, `AuthorizationInterceptorsOrder`, `@EnableMethodSecurity(offset)`, and `@PostAuthorize` warning for write operations.
- [Spring Security API — AuthorizationInterceptorsOrder](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/authorization/method/AuthorizationInterceptorsOrder.html): security advisor names and orders.
- [Spring Security API — EnableMethodSecurity](https://docs.spring.io/spring-security/reference/api/java/org/springframework/security/config/annotation/method/configuration/EnableMethodSecurity.html): method security configuration and offset.
- [Spring Framework — AOP Advice Ordering](https://docs.spring.io/spring-framework/reference/core/aop/ataspectj/advice.html): inbound and outbound precedence rules, `@Order`, and `Ordered`.
- [Spring Framework — Using @Transactional](https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html): transaction proxies, default `LOWEST_PRECEDENCE` order, self-invocation, rollback rules, and retry interaction.
- [Spring Framework — Understanding AOP Proxies](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): proxies, self-invocation mechanics, and their limits.
