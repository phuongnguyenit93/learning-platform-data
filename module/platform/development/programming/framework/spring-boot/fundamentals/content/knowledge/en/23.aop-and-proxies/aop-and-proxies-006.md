# Self-Invocation and Internal Calls That Bypass the Proxy

In Spring Boot, many features such as `@Transactional`, `@Async`, `@Cacheable`, and AOP advice are implemented using **proxies**. Therefore, merely having an annotation on a method is not enough to guarantee advice always runs: the call must pass through the proper Spring-managed proxy object.

A very easy-to-hit bug is **self-invocation**: a bean method invokes another method on the same object via `this.method()` or an equivalent unqualified call. This internal call normally **does not pass through the proxy**, so advice intended specifically for the called method is not triggered.

This lesson explains the mechanism, symptoms, consequences, and ways to reorganize code so AOP behaves as expected.

## 1. How do AOP proxies intercept calls?

Aspect-Oriented Programming (AOP) separates cross-cutting concerns from business code, such as:

- Starting, committing, or rolling back transactions.
- Running tasks through an executor rather than on the calling thread.
- Looking up and updating caches.
- Logging, measuring execution time, checking access permissions.
- Applying custom advices declared by the application.

In **proxy-based Spring AOP**, Spring creates an intermediary object (proxy) in front of the business-executing object (target). Other components obtaining the bean from the `ApplicationContext` typically receive a reference to the proxy. When a matching method is invoked through the proxy, the proxy gets to run advice before, after, or around the target's method.

~~~text
Controller / another bean
         |
         v
  Spring AOP proxy
         |
         +--> Advice: open transaction / cache / log ...
         |
         v
    Target object
         |
         v
   Business method
         |
         v
  Advice completes / commits / handles errors
~~~

If a method does not match a pointcut or advice condition, the proxy can forward the call without applying that advice. If the call does not go through the proxy in the first place, advice on the target method never gets a chance to run.

## 2. What is self-invocation?

Suppose a Spring bean has two methods:

~~~java
import org.springframework.stereotype.Service;

@Service
public class InvoiceService {

    public void processInvoice() {
        validateInvoice();

        // Invoice processing logic ...
    }

    public void validateInvoice() {
        // Invoice data validation ...
    }
}
~~~

Inside `processInvoice()`, calling `validateInvoice()` is equivalent to `this.validateInvoice()`. Here `this` points to the **target object** executing the method, not a fresh lookup of the bean through the container.

If `validateInvoice()` has AOP advice, the internal call does not pass through the proxy interception point under normal proxy-based AOP mechanics.

Compare the two call paths:

~~~text
(1) Call from another bean

OrderController
      |
      v
InvoiceService proxy
      |
      v
Advice for validateInvoice()
      |
      v
InvoiceService target.validateInvoice()


(2) Internal call within the same bean

OrderController
      |
      v
InvoiceService proxy.processInvoice()
      |
      v
InvoiceService target.processInvoice()
      |
      +--> this.validateInvoice()
                  |
                  v
        Target.validateInvoice()
        DOES NOT pass through proxy again
~~~

Path (2) can have `processInvoice()`'s advice applied if that method matches a pointcut. However, **advice specific to `validateInvoice()` does not run just because the target calls itself**.

This is the difference between *a call on the bean proxy* and *a call on the object itself to which the proxy already delegated execution*.

## 3. Classic example with @Transactional

`@Transactional` is the most common illustration of the self-invocation problem.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {

    public void placeOrder() {
        // Some checks and calculations...
        saveOrder();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveOrder() {
        // Write order to database...
    }
}
~~~

Another bean calls:

~~~java
orderService.placeOrder();
~~~

The call passes through the `OrderService` proxy if Spring manages the bean. However, `placeOrder()` is not marked transactional, and then the target directly invokes `saveOrder()`. Consequently, `saveOrder()`'s transaction interceptor does not run for this internal call.

As a result, `@Transactional(propagation = REQUIRES_NEW)` **does not automatically create a new transaction** during that call. If the write has a transaction, it may come from another layer or data-access library behavior, not from `saveOrder()`'s advice.

On the other hand, if another bean obtains `OrderService` from Spring and calls directly:

~~~java
orderService.saveOrder();
~~~

then the call can pass through the transactional proxy, and `saveOrder()`'s advice executes, provided transaction management is configured properly.

### What if the outer method also has @Transactional?

Consider another version:

~~~java
@Service
public class OrderService {

    @Transactional
    public void placeOrder() {
        saveOrder();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveOrder() {
        // Write data...
    }
}
~~~

When another bean calls `placeOrder()` through the proxy, **`placeOrder()`'s transaction applies**. The internal call to `saveOrder()` still bypasses the inner method's advice.

This means `saveOrder()` can run inside the existing transaction from `placeOrder()`, yet `saveOrder()`'s own `REQUIRES_NEW` attribute **has no effect at the internal call boundary**. It does not suspend the outer transaction to create a new one.

Similarly, attributes like `readOnly`, `timeout`, `isolation`, or rollback rules on the inner method are not applied as an independent transaction without going through the corresponding interceptor.

This is why you cannot verify by asking only "is a transaction active right now?" You must distinguish **an existing transaction from an outer call** from **whether the inner method's transaction advice was actually invoked**.

## 4. Impact on @Async and @Cacheable

Self-invocation does not affect only transactions. Other proxy-based mechanisms follow the exact same rule.

### @Async: internal calls still run synchronously

~~~java
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    public void requestReport() {
        generateReport();
    }

    @Async
    public void generateReport() {
        // Long-running report processing...
    }
}
~~~

Suppose the application has async execution enabled, e.g., with `@EnableAsync`, and another bean calls `reportService.requestReport()`.

The internal call `generateReport()` bypasses the async proxy, so processing executes on the current thread instead of being submitted to an executor via `@Async` advice. `requestReport()` may therefore block until `generateReport()` finishes.

If another bean calls `reportService.generateReport()` through the proxy, `@Async` advice gets a chance to submit the task to the configured executor.

### @Cacheable: bypassing cache lookup and updates

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductService {

    public Product loadForCheckout(String id) {
        return findProduct(id);
    }

    @Cacheable(cacheNames = "products", key = "#id")
    public Product findProduct(String id) {
        // Query data...
        return loadProductFromDatabase(id);
    }

    private Product loadProductFromDatabase(String id) {
        // Illustrative example.
        return new Product(id);
    }
}
~~~

Suppose caching is enabled, e.g., with `@EnableCaching`, and a suitable cache manager is present.

When `loadForCheckout()` internally calls `findProduct()`, the call does not pass through caching advice. That means:

- No cache lookup occurs in `findProduct()`'s interceptor.
- No cached result is used to skip the query.
- No result is written to the cache by this call's interceptor.

If another bean calls `productService.findProduct(id)` through the proxy, `@Cacheable` can operate according to the current cache configuration.

Annotations such as `@CachePut`, `@CacheEvict`, or custom `@Aspect` advices must be evaluated similarly when they operate via proxies.

## 5. Do JDK dynamic proxies and CGLIB make self-invocation behave differently?

Spring AOP commonly uses two ways to create proxies:

| Type | Characteristics | Points to note |
|---|---|---|
| JDK dynamic proxy | Proxy implements interfaces provided by the target | Calls typically pass through methods declared on the interface |
| Class-based proxy (CGLIB) | Proxy is based on a subclass of the target class | Can proxy eligible methods on the class, but has limits with `final`, `private`, and overridability |

Whether using JDK dynamic proxies or CGLIB, **self-invocation inside the target still bypasses advice for calls to itself** under the Spring AOP proxy model.

Switching from JDK proxies to CGLIB is not a cure for self-invocation. Proxy type selection mainly affects the proxy's runtime type, bean access via interface or class, and which methods can be advised.

For example, configuring:

~~~yaml
spring:
  aop:
    proxy-target-class: true
~~~

can request class-based proxies in a supporting Spring Boot environment. However, this setting **does not turn `this.method()` into a proxied call**.

### Restrictions on final, private, and non-public methods

Beyond self-invocation, Spring AOP has interception limits:

- `private` methods cannot be overridden by class-based proxies, so they cannot be advised this way.
- `final` methods cannot be overridden; class-based proxies cannot apply advice to them.
- With interface-based JDK proxies, calls are intercepted through methods exposed by the proxy interfaces.
- Each annotation's policy may impose additional visibility rules, such as which methods transaction advice supports.

Thus, when debugging an inactive annotation, check **both proxy boundaries and method properties**. Yet even a `public`, non-`final` method with a valid annotation will skip advice if invoked internally.

## 6. Symptoms of a self-invocation bug

Common signs:

1. Calling an annotated method directly from a controller works, while calling it via another method in the same service does not.
2. `@Transactional(propagation = REQUIRES_NEW)` fails to create an independent transaction as expected.
3. `@Async` runs on the request thread instead of an executor when invoked from a method in the same class.
4. `@Cacheable` fails to reduce query counts when invoked through a helper method in the same bean.
5. Logging aspects or metrics advice fail to record calls to the inner method.
6. Switching to CGLIB changes nothing.

Internal vs. external calls can be pictured as:

~~~text
service.outer() -> this.inner()      : skips advice for inner()
caller         -> service.inner()   : goes through proxy, advice can run
~~~

What decides the outcome is not that the methods share a class, but **which object receives the call at invocation time**.

## 7. Preferred solution: extract the advised capability into another bean

The clearest and usually most maintainable approach is moving the method needing advice into a separate Spring bean. The outer bean injects the inner bean; calls through that dependency pass through the injected bean's proxy.

Transaction example:

~~~java
import org.springframework.stereotype.Service;

@Service
public class CheckoutService {

    private final OrderWriter orderWriter;

    public CheckoutService(OrderWriter orderWriter) {
        this.orderWriter = orderWriter;
    }

    public void checkout() {
        // Validate order...
        orderWriter.saveOrder();
    }
}
~~~

Bean responsible for writing data:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderWriter {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveOrder() {
        // Data write operations...
    }
}
~~~

Execution flow:

~~~text
Controller
   |
   v
CheckoutService proxy / target
   |
   v
orderWriter.saveOrder()
   |
   v
OrderWriter proxy
   |
   v
Transaction advice (REQUIRES_NEW)
   |
   v
OrderWriter target.saveOrder()
~~~

This brings several benefits:

- Clear transaction boundaries via a dependency between services.
- No reliance on a bean looking up its own proxy.
- `CheckoutService` business logic can be tested independently of `OrderWriter`.
- Clear separation of responsibility between orchestration and data persistence.

Similarly, with `@Async` you can extract `ReportGenerator` into its own bean; with `@Cacheable` you can create a `ProductLookup` bean used by other services.

### Mind the business boundaries

You do not need to split every tiny method into its own bean. Split only when the method needs a **separate advice boundary** or has an independent responsibility. If two methods truly belong in the same transaction, you can put the annotation on the outer method and keep normal internal calls.

Example:

~~~java
@Transactional
public void checkout() {
    validate();
    reserveStock();
    saveOrder();
}
~~~

If all three steps should run inside the same transaction, placing `@Transactional` on the `checkout()` entry point can be cleaner than annotating each helper method.

## 8. Solution: use TransactionTemplate when explicit transaction boundaries are needed

If you prefer not to extract another bean yet need transaction control over a block of code, use programmatic transaction management with `TransactionTemplate`.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class OrderService {

    private final TransactionTemplate requiresNewTransaction;

    public OrderService(PlatformTransactionManager transactionManager) {
        this.requiresNewTransaction =
                new TransactionTemplate(transactionManager);

        this.requiresNewTransaction.setPropagationBehavior(
                TransactionDefinition.PROPAGATION_REQUIRES_NEW
        );
    }

    public void placeOrder() {
        // Pre-transaction logic...

        requiresNewTransaction.executeWithoutResult(status -> {
            // Write data that must run in a new transaction...
        });
    }
}
~~~

In this approach, code invokes `TransactionTemplate` directly; opening the transaction does not depend on whether the method was called through a proxy.

The advantage is that the transaction boundary is immediately visible at the point of use. The trade-off is tighter coupling between business code and Spring's transaction management API. This fits well when a transaction is needed specifically for a small scope and creating an extra service is unwarranted.

This solution addresses only transaction needs. It does not replace `@Async` or `@Cacheable` mechanisms.

## 9. Calling through the bean's own proxy: possible, but weigh carefully

Technically, an application can arrange for a call to go through the bean's own proxy instead of `this`. For example, a variant using Spring AOP's `AopContext`:

~~~java
import org.springframework.aop.framework.AopContext;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AccountService {

    public void updateAccount() {
        AccountService proxy =
                (AccountService) AopContext.currentProxy();

        proxy.saveAuditRecord();
    }

    @Transactional
    public void saveAuditRecord() {
        // Write audit...
    }
}
~~~

For `AopContext.currentProxy()` to work, the proxy must be configured with `exposeProxy = true` and the current call must already be going through an AOP proxy on the same execution thread. For example, in Spring's AspectJ auto-proxy configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.EnableAspectJAutoProxy;

@Configuration(proxyBeanMethods = false)
@EnableAspectJAutoProxy(exposeProxy = true)
public class AopConfiguration {
}
~~~

This approach has drawbacks:

- Business code depends directly on Spring AOP.
- Requires proxy exposure configuration.
- `AopContext.currentProxy()` can fail if there is no active proxy on the current thread.
- Under JDK interface proxies, casting to a concrete class can be invalid.
- Logic is harder to read and test compared to a boundary between two beans.

Therefore, this is usually a last resort when refactoring beans is impractical. Do not use it as the default way to make `@Transactional` work.

Solutions that self-inject the bean via `ObjectProvider` or a lazy proxy can also route calls through a proxy, yet introduce self-dependencies and require careful understanding of bean lifecycles. Extracting responsibilities into another bean is generally much cleaner.

## 10. AspectJ weaving differs from proxy-based AOP

Spring supports proxy-based AOP, whereas AspectJ can **weave** advice into bytecode via compile-time weaving or load-time weaving when fully configured.

With weaving, advice does not depend solely on calls entering an external proxy. Thus AspectJ can handle certain self-invocation scenarios that proxy-based Spring AOP cannot.

For example, Spring transaction management can be configured to use AspectJ mode when the application has the required dependencies and weaving infrastructure:

~~~java
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement(mode = AdviceMode.ASPECTJ)
public class TransactionConfiguration {
}
~~~

**Declaring AspectJ mode alone is not enough.** The application needs supporting libraries and the corresponding weaving setup, such as configuring AspectJ load-time weaving for the runtime environment. Without those pieces, do not expect self-invocation to be intercepted.

For most standard Spring Boot applications, reorganizing bean boundaries is simpler and carries lower operational risk than switching the entire interception mechanism to AspectJ weaving.

| Mechanism | How advice is applied | Self-invocation |
|---|---|---|
| Spring AOP proxy | Calls into the bean pass through a proxy | Bypasses advice on internally called methods |
| AspectJ weaving | Advice is woven into matching join points in bytecode | Can handle internal calls depending on pointcuts and weaving configuration |

The two mechanisms cannot be swapped simply by enabling CGLIB. CGLIB is still a form of **proxy**, not AspectJ weaving.

## 11. Verifying with transaction state

One illustrative check uses `TransactionSynchronizationManager` to inspect whether an actual transaction is active on the running thread.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class DiagnosticService {

    public void outer() {
        System.out.println("outer before: " + active());
        inner();
        System.out.println("outer after: " + active());
    }

    @Transactional
    public void inner() {
        System.out.println("inner: " + active());
    }

    private boolean active() {
        return TransactionSynchronizationManager
                .isActualTransactionActive();
    }
}
~~~

Assuming a suitable `PlatformTransactionManager` exists, transaction management is enabled, and code retrieves the bean from the context on a thread without an existing transaction:

~~~java
diagnosticService.outer();
diagnosticService.inner();
~~~

With proxy-based transaction management, the expected conceptual output is:

~~~text
outer before: false
inner: false
outer after: false
inner: true
~~~

Calling `inner()` inside `outer()` does not pass through the proxy, so it creates no new transaction. Calling `diagnosticService.inner()` directly from outside passes through the proxy and is handled by the transaction interceptor.

This is a diagnostic illustration. In a real application, a transaction might already exist from another caller, or a data-access component might manage its own transaction. Therefore, when testing `REQUIRES_NEW`, verify actual transaction boundaries and commit/rollback behavior rather than relying solely on a boolean.

### Checking @Async via thread names

With `@Async`, you can log the thread name:

~~~java
@Async
public void generateReport() {
    System.out.println(Thread.currentThread().getName());
}
~~~

Compare the two call paths:

~~~java
reportService.requestReport(); // Internally calls generateReport()
reportService.generateReport(); // Called externally via proxy
~~~

If async execution is enabled and configured properly, the internal call can execute directly on the caller thread, whereas the proxied call executes on an executor. Exact results depend on the configured executor; the goal is observing the call boundary, not assuming every application uses identical thread names.

## 12. Common mental pitfalls

### Having an annotation means advice definitely runs

False in proxy-based AOP. Advice depends on pointcuts, method eligibility, and calls passing through a proxy. Annotations merely describe conditions and configuration for a handler.

### Calling a public method in the same class goes through the proxy

False. `public` visibility does not change the receiver of the call. `this.publicMethod()` is still an internal call on the target.

### Switching to CGLIB fixes self-invocation

False. CGLIB is a class-based proxy with the same interception boundary. The issue is not whether the proxy uses an interface or subclass, but whether the call path passes through the proxy.

### @Transactional on an internal method never has a transaction

This phrasing is inaccurate. If the outer method already participates in a transaction, the inner method may run **inside that existing transaction**. What is skipped is the inner method's own advice, such as `REQUIRES_NEW`, a different timeout, or custom rollback rules.

### A private method with @Transactional gets advised when called via this

False. Under proxy mechanics, private methods are not suitable interception points for class-based proxies. Being an internal call on the same bean guarantees it bypasses the proxy even further.

### Calling a method during bean initialization receives full advice

Inside constructors or certain early bean lifecycle callbacks, the AOP proxy may not yet be ready for the desired call pattern. Do not treat internal calls during construction/init as proxied entry points.

### Putting @Async on an internal method makes it run in the background automatically

If the caller invokes the method via `this`, the async interceptor does not trigger. For background tasks, place the method in a separate bean or use an explicit executor.

## 13. Design guidance and choosing a solution

When you discover advice is not running, decide in this order:

1. **Identify the entry point:** does another bean call the method through a Spring bean, or does the target call `this.method()`?
2. **Identify the needed advice:** transaction, async, cache, security, or custom aspect?
3. **If the entire workflow shares one advice:** consider placing the annotation on the entry-point method called through the proxy.
4. **If the inner method needs its own boundary:** extract it into another bean and inject that bean into the caller.
5. **If a very specific transaction scope is needed:** consider `TransactionTemplate` for explicit control.
6. **If refactoring is impossible:** carefully evaluate self-proxy access, understanding `exposeProxy` requirements and proxy types.
7. **If weaving advice into self-invocation is truly required:** evaluate AspectJ mode and weaving configuration costs.
8. **Test at the right level:** verify side effects, execution threads, cache hit counts, or transaction boundaries; do not rely solely on seeing the annotation.

### Example solution selection

| Scenario | Typically suitable option |
|---|---|
| A workflow with several helpers must share one transaction | Place `@Transactional` on the entry point called through the proxy |
| One step must use `REQUIRES_NEW` independently of the workflow | Extract to another bean and call through the dependency |
| A task must run asynchronously | Extract a bean with an `@Async` method or use an explicit executor |
| A query must utilize `@Cacheable` | Move the query into a dedicated lookup bean and call through the proxy |
| Transaction needed only for a small block | Use `TransactionTemplate` |
| Architecture cannot change and internal calls need advice | Evaluate AspectJ weaving after weighing deployment requirements |

## 14. Summary: the critical boundary is the proxy

In Spring Boot, the core sign of a self-invocation bug is an AOP-annotated method being called via `this.method()` or an equivalent internal call. When that happens:

- The call **does not re-enter the Spring AOP proxy**.
- Advice dedicated to the inner method **is not triggered**.
- Any transaction already active from the outer method can persist, yet propagation or custom rules on the inner method are not applied as a separate interception.
- CGLIB does not solve this on its own.
- Extracting the method needing advice into a separate Spring bean is usually the cleanest solution.

Understanding exact call paths helps prevent subtle bugs such as `@Transactional` failing to open a new transaction, `@Async` running synchronously, or `@Cacheable` skipping the cache. Design advice boundaries at entry points genuinely invoked through bean proxies, while keeping business logic readable and testable.
