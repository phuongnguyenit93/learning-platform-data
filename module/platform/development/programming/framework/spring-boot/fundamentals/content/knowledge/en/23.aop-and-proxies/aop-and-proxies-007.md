# Limitations with Final, Private, and Non-Interceptable Methods

Spring AOP is commonly used to implement cross-cutting concerns such as transactions, logging, metrics, caching, security, or asynchronous execution. With annotations like `@Transactional`, `@Cacheable`, and `@Async`, many developers expect that simply marking a method makes Spring automatically apply the corresponding behavior every time the method runs.

However, Spring AOP in its usual mode is **proxy-based**. A proxy can only intercept calls **passing through the proxy object** and methods that the proxy mechanism can actually intercept. Consequently, a `private` method, a `final` method when using class-based proxies, an internal call via `this`, or a constructor is not handled the same way as a public method invoked through a proxy.

This lesson focuses on those boundaries and how to design code properly, avoiding situations where annotations are present yet have no effect.

## 1. First: how do Spring AOP proxies work?

A normal Spring bean is a Java object:

~~~java
@Service
public class PaymentService {

    public void pay() {
        // Payment logic.
    }
}
~~~

When AOP is applied to a bean, Spring can expose a **proxy object** for external components to use. This proxy receives method calls, executes the interceptor/advice chain, and forwards to the target object's logic via the appropriate mechanism.

~~~text
           OtherService
                |
                | calls paymentService.pay()
                v
        +------------------+
        |  Spring AOP      |
        |  proxy           |
        |------------------|
        | Before advice    |
        | Around advice    |
        | Transaction ...  |
        +------------------+
                |
                v
           Target method
           PaymentService.pay()
                |
                v
        Return / exception
                |
                v
      Proxy completes advice
~~~

Example of an advice:

~~~java
import org.aspectj.lang.ProceedingJoinPoint;
import org.aspectj.lang.annotation.Around;
import org.aspectj.lang.annotation.Aspect;
import org.springframework.stereotype.Component;

@Aspect
@Component
public class TimingAspect {

    @Around("execution(* com.example.payment.PaymentService.pay(..))")
    public Object measure(ProceedingJoinPoint joinPoint)
            throws Throwable {

        long start = System.nanoTime();
        try {
            return joinPoint.proceed();
        } finally {
            long elapsed = System.nanoTime() - start;
            System.out.println("Elapsed nanos: " + elapsed);
        }
    }
}
~~~

When `PaymentService.pay()` is called **through the proxy** and the pointcut matches, the advice can execute. To use `@Aspect`s like this in a Boot application, appropriate AOP infrastructure must be on the classpath and enabled by application configuration.

**Essence:** Proxies intercept calls at the boundary between caller and bean. Proxies do not rewrite the bytecode of every Java method, nor do they become observers of every internal call inside the target.

## 2. Two key proxy strategies

Spring AOP has two common proxy strategies:

1. **JDK dynamic proxy:** creates a proxy implementing the target's interfaces.
2. **Class-based proxy (CGLIB):** creates a subclass of the target class and overrides interceptable methods.

### 2.1. JDK dynamic proxy

Example:

~~~java
public interface PaymentOperations {
    void pay();
}

@Service
public class PaymentService implements PaymentOperations {

    @Override
    public void pay() {
        // Process payment.
    }
}
~~~

JDK proxy implementing `PaymentOperations`:

~~~text
PaymentOperations
      ^
      |
JDK Proxy implements PaymentOperations
      |
      | dispatch / interceptor
      v
PaymentService target
~~~

Importantly, the caller uses the interface type:

~~~java
@Service
public class CheckoutService {

    private final PaymentOperations payments;

    public CheckoutService(PaymentOperations payments) {
        this.payments = payments;
    }

    public void checkout() {
        payments.pay();
    }
}
~~~

With JDK dynamic proxies, only methods exposed through interfaces implemented by the proxy are interceptable call points under this proxy type. Methods existing only on the concrete class and absent from the interface cannot be called directly through a reference typed only to the proxy interface.

### 2.2. Class-based proxy (CGLIB)

If Spring uses a class-based proxy:

~~~text
PaymentService
      ^
      | extends
      |
PaymentService$$SpringCGLIB proxy
      |
      | override pay() and apply advice
      v
PaymentService logic
~~~

The proxy is a subclass of the target class. Subclassing requires Java to allow **extending the class** and **overriding methods**. That is the source of the `final` and `private` restrictions.

### 2.3. Which type does Spring Boot typically choose?

In Spring Boot applications with auto-configured AOP, class-based proxies are typically the default. Where supported by configuration, this can be adjusted with:

~~~properties
spring.aop.proxy-target-class=false
~~~

The value `false` requests preferring JDK interface-based proxies if the target has suitable interfaces. If a class has no appropriate interface, you cannot expect a JDK proxy to expose class-specific methods.

Mechanisms such as transactions, async, and AOP infrastructure may have their own proxy settings or be affected by `@Enable...` settings. Therefore, **check the actual proxy type**, rather than relying solely on the fact that the project uses Spring Boot.

## 3. Overview table of limitations

| Case | JDK dynamic proxy | Class-based proxy | Notes |
|---|---|---|---|
| Public method declared in interface | Interceptable | Interceptable if overridable | Call must pass through proxy |
| Public method only on concrete class | Not reachable via normal interface proxy | Interceptable if non-final | Depends on proxy type |
| `final` class | Proxiable via suitable interface | **Cannot subclass** | JDK proxy does not need to extend target class |
| `final` instance method | Interface call interceptable via interface proxy | **Cannot override** | Distinguish final class from final method |
| `private` method | Not exposed via interface | **Cannot override** | Annotations on private methods are not applied by normal proxies |
| `static` method | Not an instance-dispatch method on JDK proxy | Cannot override | Static dispatch does not pass through proxy instance |
| Constructor | Not an interface method | Not an overridable method | Spring AOP does not advise constructor execution |
| `protected`/package-private method | Not exposed as public interface method | May be supported depending on visibility and framework semantics | Do not assume all annotations behave identically |
| Self-invocation, e.g. `this.runTask()` | Does not go through proxy | Does not go through proxy | Internal call on same object |
| Object created via `new` outside Spring | Not automatically proxied by Spring | Not automatically proxied by Spring | Not a Spring-managed bean |

The table covers **proxy-based Spring AOP**. AspectJ weaving is a different mechanism capable of intervening at more kinds of join points.

## 4. Why can't a final class use a class-based proxy?

In Java, `final` on a class forbids other classes from extending it:

~~~java
public final class ReportService {

    public void generate() {
        // ...
    }
}
~~~

CGLIB needs to generate a subclass roughly like:

~~~java
class ReportServiceProxy extends ReportService {
    // Impossible: ReportService is final.
}
~~~

Consequently, an AOP configuration requiring a class-based proxy for `ReportService` cannot create a normal subclass proxy. Depending on the case and AOP mechanism, startup may fail when Spring attempts to proxy a final target.

### 4.1. What if a final class implements an interface?

Subtle point: **a final class does not mean AOP is impossible under every proxy strategy**.

~~~java
public interface ReportOperations {
    void generate();
}

public final class ReportService implements ReportOperations {

    @Override
    public void generate() {
        // ...
    }
}
~~~

A **JDK dynamic proxy** can implement `ReportOperations` and forward calls to `ReportService`, even though the target class is final. The JDK proxy does not extend `ReportService`.

~~~text
             ReportOperations
                    ^
                    |
             JDK interface proxy
                    |
                    v
           final ReportService target
~~~

The prerequisite is that the bean is configured to actually use a JDK proxy, and callers inject `ReportOperations` instead of the concrete type `ReportService`.

~~~java
@Service
public class ExportControllerService {
    private final ReportOperations reports;

    public ExportControllerService(ReportOperations reports) {
        this.reports = reports;
    }
}
~~~

If code injects the concrete type while Spring returns a JDK proxy, a type mismatch error can occur because that proxy **is not an instance of the concrete target class**.

### 4.2. Conclusions for final classes

- Using class-based proxies: the target class must be subclassable.
- Using JDK proxies: the target can be final, provided a suitable interface can be proxied.
- Avoid altering application-wide proxy settings just for one class if that impacts other beans.
- If AOP is needed on many non-interface methods, consider making the target class proxiable or extracting logic into a suitable service.

## 5. Why aren't final methods intercepted by CGLIB?

`final` on a method forbids subclasses from overriding it:

~~~java
@Service
public class InvoiceService {

    public final void issueInvoice() {
        System.out.println("Issuing invoice");
    }
}
~~~

With class-based proxies, Java forbids a subclass from writing:

~~~java
@Override
public void issueInvoice() {
    // Cannot override final method.
}
~~~

Because the method cannot be overridden, CGLIB cannot insert interceptor logic into that method's call path in the usual way.

Example with an annotation:

~~~java
@Service
public class InvoiceService {

    @Transactional
    public final void issueInvoice() {
        // Invoice processing code.
    }
}
~~~

If the application uses class-based proxies, **do not expect `@Transactional` to take effect on a final method**. The annotation remains in source/bytecode, yet the proxy cannot intercept the call to open a transaction for that method.

### 5.1. final methods via JDK proxy

If the method implements an interface method:

~~~java
public interface InvoiceOperations {
    void issueInvoice();
}

@Service
public class InvoiceService implements InvoiceOperations {

    @Override
    @Transactional
    public final void issueInvoice() {
        // ...
    }
}
~~~

With a **JDK interface proxy**, calling `InvoiceOperations.issueInvoice()` passes through the invocation handler before reaching the target. Thus `final` on the target's implementation method does not prevent the JDK proxy from intercepting the interface call.

The outcome depends on proxy config, annotation discovery, and active advisors, yet the technical restriction "cannot override final method" **does not apply to JDK proxies**.

### 5.2. final introduced by code generation or language tools

It is not only classes with an explicit `final` keyword that encounter this limit:

- Java `record`s are final classes.
- Some classes produced by code generators may be final.
- Kotlin classes and methods are final by default unless opened.
- Sealed classes can restrict which subclasses are permitted to extend them.

If a bean will have class-based AOP applied, check these inheritance constraints as well.

## 6. Why can't private methods be intercepted by proxies?

A `private` method is accessible only within the class scope under Java rules. It is not overridden by subclasses like public/protected methods.

~~~java
@Service
public class BillingService {

    public void bill() {
        validateInvoice();
    }

    @Transactional
    private void validateInvoice() {
        // ...
    }
}
~~~

There are two problems here:

1. `validateInvoice()` is private, so a class-based proxy cannot override it to intervene.
2. `bill()` calls `validateInvoice()` directly inside the target, not via a call through the proxy.

Therefore, `@Transactional` on a private method does not start a new transaction when that private method runs under proxy-based AOP.

### 6.1. Is changing private to public enough?

Not necessarily. If code only changes:

~~~java
@Transactional
public void validateInvoice() {
    // ...
}
~~~

while `bill()` still calls:

~~~java
public void bill() {
    validateInvoice(); // self-invocation
}
~~~

then the internal call can still **bypass the proxy**, even though the method is public and non-final. You must account for both **interceptability** and **call path**.

## 7. Self-invocation: internal calls bypass the proxy

This is the most common mistake when using proxy-based AOP.

~~~java
@Service
public class OrderService {

    public void placeOrder() {
        saveAuditLog();
    }

    @Transactional
    public void saveAuditLog() {
        // Write data to DB.
    }
}
~~~

An external caller invokes:

~~~java
orderService.placeOrder();
~~~

Conceptual execution flow:

~~~text
Controller
    |
    v
OrderService proxy
    |
    v
Target OrderService.placeOrder()
    |
    | this.saveAuditLog()
    v
Target OrderService.saveAuditLog()
    |
    v
Does not go through proxy for internal call
~~~

If `placeOrder()` is not covered by transaction advice, `@Transactional` placed solely on `saveAuditLog()` does not automatically create a transaction for that internal call.

### 7.1. What if the outer method already has a transaction?

~~~java
@Transactional
public void placeOrder() {
    saveAuditLog();
}
~~~

If `placeOrder()` is called externally through the proxy, the transaction opened on the outer method can cover the inner logic too. However, the transaction annotation on `saveAuditLog()` **is not re-evaluated for self-invocation**.

This matters especially if the inner method declares:

~~~java
@Transactional(propagation = Propagation.REQUIRES_NEW)
public void saveAuditLog() {
    // ...
}
~~~

When called only internally, `REQUIRES_NEW` does not trigger through the proxy. Code runs in the outer method's transaction (if one exists) or with no transaction created by the inner method.

### 7.2. Other annotations experience the same phenomenon

Not only `@Transactional`:

| Annotation/mechanism | If the method is called internally without going through the proxy |
|---|---|
| `@Transactional` | Transaction advice of the internally called method does not trigger separately |
| `@Async` (proxy mode) | Does not offload internal call to an executor |
| `@Cacheable` | Does not check/cache results for internal call |
| `@CacheEvict` | Does not trigger cache eviction on internal call |
| `@PreAuthorize` via method-security proxy | Does not run security check for self-invocation |
| Custom `@Aspect` advice | Does not apply without a call through the proxy |

Exact behavior depends on individual mechanisms and settings, yet for **proxy mode**, the general rule is no interception if the call does not pass through the proxy.

## 8. Preferred solution: extract the advised method into another bean

Instead of forcing an object to call through its own proxy, we can place the logic needing a transaction in a separate service.

~~~java
@Service
public class AuditLogService {

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void writeAuditLog(Order order) {
        // Write audit log in an independent transaction.
    }
}
~~~

~~~java
@Service
public class OrderService {

    private final AuditLogService auditLogService;

    public OrderService(AuditLogService auditLogService) {
        this.auditLogService = auditLogService;
    }

    public void placeOrder(Order order) {
        // Main business steps.
        auditLogService.writeAuditLog(order);
    }
}
~~~

Execution flow:

~~~text
OrderService.placeOrder()
          |
          | calls injected bean
          v
AuditLogService proxy
          |
          | TransactionInterceptor
          v
AuditLogService.writeAuditLog()
~~~

With proper transaction infrastructure configuration, calls into `AuditLogService` pass through the proxy and can apply `REQUIRES_NEW`.

Advantages:

- Dependencies are explicit via constructor injection.
- The method needing advice has a clear responsibility boundary.
- No direct interaction with `AopContext`.
- Easy to test transaction behavior with integration tests.
- Avoids a service calling into its own proxy.

**Note:** `REQUIRES_NEW` requires a suitable transaction manager and resources; it may need a separate connection. Do not pick this propagation merely to "see a new transaction" without evaluating business semantics.

## 9. Another solution: TransactionTemplate for explicitly controlled transactions

If logic sits in a private method and you only want a transaction around that specific block, you can use `TransactionTemplate` instead of expecting an annotation on a private method to work.

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionTemplate;

@Service
public class BillingService {

    private final TransactionTemplate transactionTemplate;

    public BillingService(TransactionTemplate transactionTemplate) {
        this.transactionTemplate = transactionTemplate;
    }

    public void bill(Bill bill) {
        transactionTemplate.executeWithoutResult(status -> {
            performDatabaseChanges(bill);
        });
    }

    private void performDatabaseChanges(Bill bill) {
        // DB changes inside the transaction opened by the template.
    }
}
~~~

Here the transaction is controlled via an explicit API, without needing a proxy to intercept a private method call. The application must have a `TransactionTemplate` bean configured with an appropriate transaction manager.

Propagation can be configured via the template's API when needed:

~~~java
TransactionTemplate template =
        new TransactionTemplate(transactionManager);
template.setPropagationBehavior(
        TransactionDefinition.PROPAGATION_REQUIRES_NEW);
~~~

This is a clean solution when programmatic transactions are clearer. It does not replace every AOP aspect such as caching or security. For complex business flows, extracting a bean may still be the more maintainable design.

## 10. AopContext.currentProxy() and self-injection: why avoid using them casually?

Spring provides a way to access the current proxy under certain configurations:

~~~java
AopContext.currentProxy()
~~~

When proxy exposure is enabled, code inside the target can retrieve the current proxy and call a method through it. However, this directly couples business code to Spring AOP and requires an active proxy invocation context.

Conceptual example:

~~~java
((OrderService) AopContext.currentProxy()).saveAuditLog();
~~~

This comes with several prerequisites:

- The proxy must be configured to expose itself via `AopContext`.
- The call must occur inside an AOP-managed invocation.
- With JDK proxies, the proxy is not necessarily castable to the concrete class `OrderService`.
- Proxy settings and call stack become hidden dependencies in business code.
- Using it does not solve CGLIB limits with final/private methods.

Another technique is injecting the service's own proxy into itself. However, self-injection easily creates circular dependencies and makes design harder to follow. Modern Spring Boot generally discourages relying on circular references as a default architecture.

**Recommendation:** prefer extracting logic needing advice into another bean or using an appropriate programmatic API, rather than overusing self-proxies.

## 11. Static methods are not interception points for instance proxies

Static methods belong to a class, not to instance dispatch the way virtual methods are overridden.

~~~java
public class TokenUtil {

    @Transactional
    public static void resetTokens() {
        // ...
    }
}
~~~

Calling:

~~~java
TokenUtil.resetTokens();
~~~

does not go through a normal Spring bean proxy. Do not expect AOP annotations on static methods to apply.

If processing needs transactions/caching/async, move it to an instance method on a Spring bean with an appropriate scope:

~~~java
@Service
public class TokenMaintenanceService {

    @Transactional
    public void resetTokens() {
        // ...
    }
}
~~~

Then invoke it through the Spring-managed bean.

Pure static helpers—such as string parsing or side-effect-free calculations—can remain static; problems arise only when trying to apply proxy advice to them.

## 12. Constructors and field access lie outside normal Spring AOP proxies

Spring AOP proxies primarily support **method execution join points** on Spring-managed beans. They are not a universal mechanism to intercept:

- Constructor calls or constructor execution.
- Direct field reads/writes.
- Object creation with `new` outside the container.
- Static initialization.
- Other operations that are not method calls passing through a proxy.

Example:

~~~java
@Service
public class InventoryService {

    public InventoryService() {
        initializeState();
    }

    private void initializeState() {
        // Does not pass through an AOP proxy while the constructor runs.
    }
}
~~~

Even if `initializeState()` were made public and annotated with `@Transactional`, calling it from the constructor still occurs while the object is being constructed, before the finished proxy is used by callers.

If initialization needs transactions or depends on other beans, consider an appropriate lifecycle hook or move the operation to another service running once the application is ready.

### 12.1. @PostConstruct also has limitations

~~~java
@Service
public class ReportService {

    @PostConstruct
    void initialize() {
        generateReport();
    }

    @Transactional
    public void generateReport() {
        // ...
    }
}
~~~

`@PostConstruct` typically executes during bean initialization **before a BeanPostProcessor creates the finished AOP proxy and exposes it to callers**. Direct calls to `generateReport()` from this callback bypass the proxy.

If transactional logic must run once the context is ready, you can call another transactional bean from an `ApplicationRunner` or suitable lifecycle event. Avoid placing complex business logic in `@PostConstruct` just to make it run early.

## 13. Protected and package-private methods: distinguish by version

Do not lump all non-public methods into a single "definitely impossible for AOP" bucket. There is an important difference between `private` and `protected` or package-private.

### 13.1. Private always faces an override barrier

Private methods cannot be overridden by subclasses, so class-based proxies cannot intercept them by overriding. JDK proxies also do not expose private methods via interfaces.

### 13.2. Protected and package-private can be supported by class-based proxies

Class-based proxies can override protected or package-private methods when Java access rules and the generated subclass's package permit. In Spring Framework 6, proxy-based `@Transactional` supports protected and package-private methods by default on class-based proxies in applicable cases.

Spring Framework 6 example:

~~~java
@Service
public class BillingService {

    @Transactional
    protected void settleInvoice() {
        // ...
    }
}
~~~

However, simply because a method can be overridden by a proxy does not mean every call to it goes through the proxy. If a public method on the same target calls `settleInvoice()` via self-invocation, the protected method's transaction advice still does not trigger separately.

In addition:

- JDK interface proxies expose only matching interface methods, typically public ones.
- A package-private method cannot be overridden by a subclass in a different package under Java rules.
- Other annotations/infrastructure may impose their own visibility requirements.
- In older Spring versions, default transaction proxies had stricter visibility rules.

### 13.3. Safe coding style for broad compatibility

For a business API with cross-cutting behavior, using **public non-final methods** called from another bean through a proxy is usually the most predictable approach.

If a project needs to proxy protected/package-private methods, verify the exact Spring Framework version, proxy strategy, and integration tests. Do not see one case working under CGLIB and assume it also works with JDK proxies or every other annotation.

## 14. Spring Boot and Kotlin: classes are final by default

In Kotlin, classes and member functions are final by default unless declared `open` or automatically opened by an appropriate compiler plugin.

Example:

~~~kotlin
@Service
class EmailService {

    @Transactional
    fun sendEmail() {
        // ...
    }
}
~~~

If the class and method remain final in bytecode, class-based proxies may fail to subclass/override them. In Spring Boot + Kotlin projects, many applications use the `kotlin-spring` plugin (built on the all-open compiler plugin) to automatically open classes/members carrying matching Spring annotations.

Gradle Kotlin DSL configuration example (plugin versions per your project build):

~~~kotlin
plugins {
    kotlin("jvm")
    kotlin("plugin.spring")
    id("org.springframework.boot")
}
~~~

Do not put placeholder versions into production code without aligning with your project's Kotlin/Boot versions. The goal of this snippet is recognizing **which plugin must be enabled**, not prescribing a specific version tuple.

### 14.1. When do Kotlin issues still happen?

- The class lacks an annotation recognized by the all-open plugin.
- A method is explicitly marked final in actual config/bytecode.
- A class is not Spring-managed and is created via a regular constructor call.
- Self-invocation bypasses the proxy even though the class is open.
- The proxy is a JDK proxy yet the caller injects by concrete type.

Thus enabling `kotlin-spring` solves final-subclass proxy issues, yet **does not eliminate all Spring AOP limits**.

## 15. Java records, final classes, and sealed classes

Java records are final classes and therefore cannot serve as superclasses for class-based proxies:

~~~java
public record ExchangeRate(String currency, double value) {
}
~~~

Records are well suited as DTOs or immutable value objects, **not service beans holding methods needing transactions/AOP**. If you register a record as a Spring bean and require a CGLIB proxy, examine the final constraint immediately.

Sealed classes also restrict which classes may extend/implement them; dynamic proxies and subclass generation can run into constraints around permitted subclasses/interfaces. When designing services using AOP, avoid letting domain-model inheritance constraints accidentally become proxy blockers.

A sound pattern keeps DTOs/value objects immutable while placing behavior requiring transactions/caching/async in appropriate Spring services.

## 16. JPMS modules and class visibility

Even when a class is not `final`, class-based proxies can still encounter limits from the Java module system and access rules.

For example:

- Insufficient class or method visibility for the generated proxy subclass.
- Package not opened in a named module when the framework needs reflection or proxy-definition access.
- Class belongs to a system module/package with access restrictions.
- Class loader or runtime environment restricts bytecode generation.

In environments with `module-info.java`, design appropriate module exports/opens for Spring Framework and proxy libraries if genuinely needed. Do not react to proxy errors by opening entire modules or adding overly broad JVM flags without pinpointing the cause.

Spring Boot apps on a standard classpath rarely deal with JPMS directly, yet visibility rules still matter for package-private methods and target classes.

## 17. @Transactional: easily confused scenarios

Consider this class:

~~~java
@Service
public class AccountService {

    @Transactional
    public void transfer() {
        debit();
        credit();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    private void debit() {
        // ...
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    private void credit() {
        // ...
    }
}
~~~

With proxy-based transaction management:

- `transfer()` called through the proxy can be wrapped in **one** transaction.
- `debit()` and `credit()` are private, so they are not intercepted by the proxy.
- The two `REQUIRES_NEW` annotations do not create two independent transactions when private methods are called like this.

If business rules truly require each step to have an independent transaction, extract them into separate services with public methods called through proxies, or use `TransactionTemplate` with explicit propagation.

### 17.1. Transactions do not depend only on annotations

Even for public methods intercepted by proxies, whether transactions behave as expected depends on:

- Whether transaction infrastructure is enabled and a suitable transaction manager exists.
- Whether calls pass through the right proxy.
- Whether exceptions and rollback rules are configured properly.
- Whether where the method runs (another thread, async boundary, etc.) preserves transaction context per semantics.
- Whether the method is an appropriate transaction entry point for the data/DB model.

Do not blame every transaction failure on `final` or `private` while overlooking these factors.

## 18. @Async: having the annotation does not automatically run on another thread

Example:

~~~java
@Service
public class EmailService {

    public void notifyCustomer() {
        sendEmail();
    }

    @Async
    public void sendEmail() {
        // ...
    }
}
~~~

If `notifyCustomer()` calls `sendEmail()` internally, that call normally runs as a regular Java method call; the async proxy interceptor is not applied. Do not expect the method to switch to an executor automatically in that case.

Cleaner design:

~~~java
@Service
public class AsyncEmailSender {

    @Async
    public void sendEmail() {
        // ...
    }
}
~~~

~~~java
@Service
public class NotificationService {

    private final AsyncEmailSender sender;

    public NotificationService(AsyncEmailSender sender) {
        this.sender = sender;
    }

    public void notifyCustomer() {
        sender.sendEmail();
    }
}
~~~

Async support must be enabled and a suitable executor configured. Furthermore, `@Async` in proxy mode cannot make a private/static/final method on a class-based proxy interceptable.

## 19. @Cacheable: self-invocation prevents caching from being used

Example:

~~~java
@Service
public class ProductService {

    public Product getProduct(String sku) {
        return loadFromDatabase(sku);
    }

    @Cacheable("products")
    public Product loadFromDatabase(String sku) {
        // ...
    }
}
~~~

Calling `loadFromDatabase(sku)` from `getProduct()` within the same target does not pass through the cache proxy. As a result, the database may be queried repeatedly even though `@Cacheable` is present.

To make caching work in proxy mode:

~~~java
@Service
public class CachedProductLookup {

    @Cacheable("products")
    public Product loadFromDatabase(String sku) {
        // ...
    }
}
~~~

~~~java
@Service
public class ProductService {
    private final CachedProductLookup lookup;

    public ProductService(CachedProductLookup lookup) {
        this.lookup = lookup;
    }

    public Product getProduct(String sku) {
        return lookup.loadFromDatabase(sku);
    }
}
~~~

The call goes through another bean's proxy, where the caching interceptor can perform cache lookups and store results.

## 20. When a Spring bean is not proxied because it was created with new

A class carrying `@Service` is merely metadata. If code explicitly uses `new`:

~~~java
PaymentService service = new PaymentService();
service.pay();
~~~

that object is neither created nor wrapped by the Spring container. It does not automatically receive a Spring AOP proxy.

To benefit from proxy advice, obtain the bean from the Spring container via dependency injection:

~~~java
@Service
public class CheckoutService {

    private final PaymentService payments;

    public CheckoutService(PaymentService payments) {
        this.payments = payments;
    }

    public void checkout() {
        payments.pay();
    }
}
~~~

The example assumes the target can be proxied under the active strategy. With JDK proxies, inject the corresponding interface.

Similarly, if another framework instantiates objects without going through appropriate Spring integration, AOP annotations on the class do not guarantee interceptors will run.

## 21. Can a proxy be created too late?

Spring typically applies proxies via `BeanPostProcessor`s. Therefore, early phases such as constructors and `@PostConstruct` differ from calls made to the bean after context initialization finishes.

~~~text
Instantiate target
      |
      v
Dependency injection
      |
      v
@PostConstruct / initialization callbacks
      |
      v
BeanPostProcessor after initialization
      |
      v
Finished proxy exposed to callers
      |
      v
External calls through proxy -> interceptable by advice
~~~

This is the usual general flow; scenarios such as circular dependencies or special framework extensions can be more complex. Do not use initialization callbacks to "test" a `@Transactional` method on the same bean and conclude AOP is working.

A bean initialized too early before all `BeanPostProcessor`s are registered may also fail to be processed fully by required infrastructure. That is a lifecycle issue distinct from final/private limits, yet produces the same symptom: annotations failing to produce their expected effect.

## 22. How to check which proxy a bean is using

Spring provides `AopUtils` to inspect a bean once the context is created:

~~~java
import org.springframework.aop.support.AopUtils;
import org.springframework.context.ApplicationContext;

public class ProxyDiagnostics {

    public static void print(ApplicationContext context) {
        Object bean = context.getBean("paymentService");

        System.out.println(AopUtils.isAopProxy(bean));
        System.out.println(AopUtils.isJdkDynamicProxy(bean));
        System.out.println(AopUtils.isCglibProxy(bean));
        System.out.println(bean.getClass().getName());
    }
}
~~~

Meaning:

| API | Reports |
|---|---|
| `AopUtils.isAopProxy(bean)` | Whether the object is a Spring AOP proxy |
| `AopUtils.isJdkDynamicProxy(bean)` | Whether it is a JDK dynamic proxy used by Spring AOP |
| `AopUtils.isCglibProxy(bean)` | Whether it is a CGLIB class-based proxy used by Spring AOP |
| `bean.getClass()` | Actual runtime type of the injected object |

Not every Spring bean has a proxy. Seeing no proxy is not necessarily an error if no advisor/annotation applies to the bean.

### 22.1. Do not look only at the class name

Class names with suffixes like `$$SpringCGLIB$$` can serve as clues, yet should not be rigid test conditions. Using `AopUtils` and observing actual behavior is clearer.

### 22.2. Interface proxies and casting

A JDK proxy can be injected by interface type:

~~~java
PaymentOperations operations =
        context.getBean(PaymentOperations.class);
~~~

However, casting it to the concrete class:

~~~java
PaymentService implementation = (PaymentService) operations;
~~~

can fail because a JDK proxy does not extend `PaymentService`. Designing dependencies around interfaces avoids coupling to proxy types.

## 23. How does AspectJ weaving differ from proxy-based Spring AOP?

Spring AOP proxies intercept only method executions passing through a proxy. **AspectJ weaving** can modify bytecode at compile time or load time, supporting more join points.

| Feature | Spring AOP proxy | AspectJ weaving |
|---|---|---|
| Mechanism | Runtime JDK/CGLIB proxy | Bytecode weaving |
| Self-invocation calls | Usually not intercepted | Can be advised if pointcut/weaving match |
| Constructor join points | No | Can be supported |
| Field get/set join points | No | Can be supported |
| Private method execution | Not via proxy-based method interception | Advisable with appropriate AspectJ setup |
| Final method execution | Not with class-based proxies | Advisable with appropriate weaving |
| Setup complexity | Usually simpler | Requires compiler/weaver config, class loading, and careful testing |

Distinguish **AspectJ annotation syntax** from **AspectJ weaving**. Using `@Aspect` in a regular Spring Boot project **does not mean** bytecode weaving is enabled. An `@Aspect` discovered by Spring AOP still runs under the proxy model and shares proxy limitations.

For `@Transactional`, an AspectJ transaction mode exists when configuration supports it, yet that is a separate architectural choice requiring corresponding dependency/weaving setup. You cannot bypass private/final method limits simply by adding an AspectJ dependency while keeping everything else unchanged.

## 24. Should you refactor or choose AspectJ?

For most Spring Boot business applications:

- If a method needs transaction/cache/async, **extract it to a separate bean** or ensure callers go through a proxy.
- If a method is `private`, consider an appropriate public service boundary rather than making every helper public just to "carry an annotation."
- If a class/method is `final` without compelling reason, adjust the design so class-based proxies work.
- If a class must stay final yet has a suitable interface, JDK proxies may be an option.
- If an explicit transaction is needed inside a method, `TransactionTemplate` can fit.
- Consider AspectJ weaving only when join point needs truly exceed proxy limits and the team can operate a weaving setup.

Extracting beans does more than "get past the proxy": it clarifies dependencies, transaction boundaries, and business responsibilities.

## 25. Testing interception boundaries

For AOP behavior, **unit tests calling target methods directly** are not enough to prove advice works. You need a Spring context containing proxies, advisors, and real dependencies or appropriate test doubles.

### 25.1. Checking proxy strategy

~~~java
import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.aop.support.AopUtils;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ProxyTypeTest {

    @Autowired
    PaymentOperations payments;

    @Test
    void paymentServiceIsProxied() {
        assertThat(AopUtils.isAopProxy(payments)).isTrue();
    }
}
~~~

The example assumes `PaymentService` has an advisor that actually applies and AOP infrastructure is enabled. If no advisor matches, Spring has no reason to create a proxy.

### 25.2. Testing @Transactional via actual behavior

One way to observe is checking transaction state inside a method called through a proxy:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionSynchronizationManager;

@Service
public class TransactionProbe {

    @Transactional
    public boolean isTransactionActive() {
        return TransactionSynchronizationManager
                .isActualTransactionActive();
    }
}
~~~

Test:

~~~java
@SpringBootTest
class TransactionProbeTest {

    @Autowired
    TransactionProbe probe;

    @Test
    void externalCallRunsInsideTransaction() {
        assertThat(probe.isTransactionActive()).isTrue();
    }
}
~~~

The test requires a properly configured transaction manager. It checks behavior when calling a public method through a Spring bean, not merely annotation presence. If the test class itself has `@Transactional`, an outer transaction can keep the assertion from proving the probe's advice worked; avoid that when designing this test.

### 25.3. Testing self-invocation

You can add a method:

~~~java
@Service
public class TransactionProbe {

    @Transactional
    public boolean isTransactionActive() {
        return TransactionSynchronizationManager
                .isActualTransactionActive();
    }

    public boolean internalCall() {
        return isTransactionActive();
    }
}
~~~

When `internalCall()` is invoked externally while that method has no transaction advice and no other transaction is active, `isTransactionActive()` inside typically returns `false`: self-invocation does not trigger the inner method's transaction advice.

Testing this requires controlling the transaction environment so it does not run inside a transaction already opened by the test runner.

### 25.4. Testing final/private behavior

With class-based proxies, write tests demonstrating:

- A public, non-final method called through the proxy receives advice as expected.
- Final methods are not intercepted by class-based proxies.
- Private methods are not proxy interception points.
- JDK proxies can intercept interface calls even when target implementation methods are final.
- Self-invocation does not run separate advice.

Do not assert only annotation names; observe aspect counters, transaction activity, cache lookup counts, or execution threads depending on what is being tested.

## 26. Common errors

| Symptom | Possible cause | Resolution |
|---|---|---|
| `@Transactional` on private method does not work | Proxy cannot intercept private method | Put transaction boundary on proxiable method called via another bean, or use TransactionTemplate |
| `@Async` method runs on caller thread | Self-invocation, non-interceptable method, async disabled, or executor config | Move method to another bean, verify proxy/async setup |
| `@Cacheable` fails to reduce DB calls | Method called internally, bypassing cache proxy | Extract cached lookup bean and call via proxy |
| Final class bean fails to create CGLIB proxy | Class cannot be subclassed | Use interface JDK proxy if suitable or refactor class |
| Final method receives no advice under CGLIB | Cannot override method | Remove final if design permits, extract bean, or pick another model |
| Injecting concrete type fails when JDK proxy is enabled | Proxy implements only interfaces | Inject interface or review proxy strategy |
| Public annotated method still gets no advice | Bean not Spring-managed, advisor does not match, or call bypasses proxy | Check bean wiring, pointcut, AopUtils, and call path |
| `@PostConstruct` calling transactional method has no effect | Proxy not ready; self-invocation | Use later lifecycle hook and call another transactional bean |
| Final Kotlin service causes proxy error | Kotlin defaults to final, missing all-open plugin | Use kotlin-spring plugin or design compatible proxy |
| Protected method works in one project but not another | Different Spring version/proxy strategy/annotation support | Check specific semantics, prefer public non-final for AOP APIs |
| Need to advise constructors or fields | Spring AOP proxies do not support those join points | Refactor or evaluate AspectJ weaving if genuinely needed |
| Aspect uses `@Aspect` yet self-calls still skip advice | Still using proxy-based Spring AOP, not weaving | Understand difference between `@Aspect` syntax and weaving |

## 27. Solution selection guide

| Practical requirement | Approach to consider |
|---|---|
| Transaction for business method | Public non-final method on Spring bean, called via proxy |
| Internal method needing independent transaction | Extract to another service or use TransactionTemplate |
| Internally called async task | Extract worker bean with `@Async` and call via proxy |
| Cache a method's result | Use dedicated bean with `@Cacheable`, called by caller via proxy |
| Target class must be final | Use JDK interface proxy if a suitable interface exists |
| Target method is final yet needs interface advice | Verify JDK proxy and active annotation/advisor behavior |
| Kotlin bean using class-based AOP | Enable and configure kotlin-spring/all-open appropriately |
| Need to intercept constructors or field access | Consider AspectJ weaving or redesign |
| Just want a shared helper | Keep pure private/static when AOP is unnecessary |
| Need to know which proxy type is active | `AopUtils.isAopProxy/isJdkDynamicProxy/isCglibProxy` and integration tests |

## 28. Design principles to remember

1. **Spring AOP proxies require calls to go through the proxy.** Annotations alone do not change every method call in the JVM.
2. **JDK dynamic proxies rely on interfaces; CGLIB class proxies rely on subclassing and overriding.**
3. **Final classes** cannot serve as targets of normal class-based proxies; if a suitable interface exists, JDK proxies can still work.
4. **Final instance methods** cannot be overridden by CGLIB, though they can be intercepted via an interface proxy if calls pass through a matching JDK proxy.
5. **Private/static methods and constructors** are not interception points for regular Spring AOP proxies.
6. **Self-invocation** bypasses proxies even when the method is public, non-final, and annotated.
7. Annotations `@Transactional`, `@Async`, `@Cacheable`, and `@PreAuthorize` all require checking call paths and matching proxy models.
8. With Spring Framework 6 and class-based proxies, some protected/package-private methods can be supported; do not equate them with private.
9. Do not use `@PostConstruct` or constructors to invoke AOP-annotated methods on the same bean expecting advice to run.
10. Prefer **separating beans by responsibility**, interface injection, and clear transaction boundaries. Use self-proxies or bytecode weaving only for strong technical reasons.
11. Test advice behavior in a real context; inspect proxies with `AopUtils` when needed.
12. When debugging failures, check **proxy type → method visibility/finality → Spring bean ownership → call path → advisor/pointcut → lifecycle** before editing annotations.

**Conclusion:** Limitations with `final`, `private`, and non-interceptable methods stem from Spring AOP's proxy mechanism, not from Spring "ignoring annotations randomly." A class-based proxy cannot extend a final class or override final/private methods; JDK proxies intercept only calls through interfaces; self-invocation and constructor/static calls bypass proxies. Designing clean boundaries between beans and choosing suitable transaction/AOP mechanisms keeps cross-cutting behavior explicit, testable, and consistent as the application grows.
