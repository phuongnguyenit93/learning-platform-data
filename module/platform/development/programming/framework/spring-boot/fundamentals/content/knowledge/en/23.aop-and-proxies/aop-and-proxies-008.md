# @Transactional, @Async, @Cacheable, and Their Required Infrastructure

In Spring Boot, the three annotations `@Transactional`, `@Async`, and `@Cacheable` frequently appear right above service methods. They look like simple directives, yet in reality each annotation requires **its own infrastructure** to take effect:

- `@Transactional` needs transaction processing and an appropriate transaction manager.
- `@Async` needs asynchronous processing enabled and an executor to run tasks.
- `@Cacheable` needs caching enabled and a cache manager to store and look up results.

In Spring's typical proxy configuration, all three also depend on **the method call path**. Annotations do not automatically alter how Java invokes methods; the framework must detect and intercept calls through an appropriate Spring AOP proxy.

This lesson focuses on the activation conditions for each mechanism, how to recognize when infrastructure is not ready, and how to combine them without confusing transaction, thread, or cache boundaries.

## 1. Annotations are metadata, not execution infrastructure

A method may declare:

~~~java
@Transactional
public void placeOrder() {
    // ...
}
~~~

However, when the JVM executes a regular Java method call, it does not read `@Transactional` on its own to start a transaction. A Spring-registered interceptor must exist, determine whether transactions apply to the method, and invoke the transaction manager before/after the business code.

The same mechanism applies to async and caching:

| Annotation | Advice/interceptor required | Core infrastructure components |
|---|---|---|
| `@Transactional` | Open or join transaction; commit/roll back based on outcome | `PlatformTransactionManager` or `ReactiveTransactionManager` |
| `@Async` | Submit call to an executor to run off the calling thread | `Executor` / `TaskExecutor`, async processing enabled |
| `@Cacheable` | Look up key in cache; invoke method on miss; store result per policy | `CacheManager`, caching processing enabled |

You can visualize it as:

~~~text
Bean A calls Bean B
       |
       v
Spring proxy of B
       |
       +--> Matching advisor / interceptor
       |      |
       |      +--> TransactionManager
       |      +--> Executor
       |      +--> CacheManager
       |
       v
Real method of B (target)
~~~

One bean can have multiple advisors applied. Having an annotation on a method is only one condition; infrastructure beans, activation configuration, and proper call paths are also required.

## 2. @Transactional: conditions for managed transactions

`@Transactional` belongs to `org.springframework.transaction.annotation`. It describes transaction boundaries and attributes such as `propagation`, `isolation`, `readOnly`, `timeout`, or `rollbackFor`.

Example:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CheckoutService {

    private final OrderRepository orderRepository;

    public CheckoutService(OrderRepository orderRepository) {
        this.orderRepository = orderRepository;
    }

    @Transactional
    public void checkout(Order order) {
        orderRepository.save(order);
        // Other data operations within the same transaction...
    }
}
~~~

When another bean calls `checkoutService.checkout(order)` through a proxy, the transaction interceptor can ask the transaction manager to start or join a transaction, run the method, and commit/roll back per configuration.

### Required infrastructure

Distinguish the following parts:

1. **Spring transaction infrastructure:** transaction classes and the `@Transactional` processor are present.
2. **Transaction management enabled:** Spring registers the necessary advisors/interceptors.
3. **Transaction manager:** performs real resource transactions, such as for JDBC, JPA, or R2DBC.
4. **Call through proxy:** in proxy mode, advised entry points must pass through the bean proxy.

In plain Spring configuration, annotation support can be enabled via:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.transaction.annotation.EnableTransactionManagement;

@Configuration(proxyBeanMethods = false)
@EnableTransactionManagement
public class TransactionConfiguration {
}
~~~

In Spring Boot applications, transaction auto-configuration normally enables annotation support when conditions match, such as a transaction manager bean being present. Thus not every Boot project needs to declare `@EnableTransactionManagement` manually.

However, **having `@Transactional` on the classpath does not guarantee a transaction manager exists**. If the application does not configure a transactional resource and lacks an appropriate manager bean, Spring cannot guess how to commit data.

### Common transaction managers

| Data access technology | Example transaction manager | Notes |
|---|---|---|
| JDBC | `JdbcTransactionManager` / `DataSourceTransactionManager` | Manages JDBC transactions on a DataSource |
| JPA | `JpaTransactionManager` | Manages transactions via JPA EntityManager |
| R2DBC | `R2dbcTransactionManager` | Reactive transactions using Reactor context |
| Special resources or systems | Manager provided by integration | Must be configured for the actual resource |

With JDBC/JPA, imperative transactions are typically bound to the current thread. With reactive transactions, transaction state is carried in the reactive context and should not be inferred from imperative `ThreadLocal` behavior.

Gradle dependency example when using JPA:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    runtimeOnly 'org.postgresql:postgresql'
}
~~~

This dependency provides related JPA/transaction infrastructure. The application must still provide datasource configuration, driver, and valid connectivity for transactions to actually work.

### Default rollback behavior and common attributes

~~~java
@Transactional(
        readOnly = true,
        timeout = 5
)
public Order getOrder(Long id) {
    return orderRepository.findById(id)
            .orElseThrow();
}
~~~

`readOnly = true` is a hint to the transaction manager and data-access infrastructure; it is **not an absolute guard** ensuring every write operation on every database fails.

Under typical default rules, Spring rolls back transactions when the advised method throws a `RuntimeException` or `Error`; checked exceptions do not automatically trigger rollback unless explicitly configured or governed by custom rules:

~~~java
@Transactional(rollbackFor = BusinessCheckedException.class)
public void importData() throws BusinessCheckedException {
    // ...
}
~~~

If a method catches an exception itself and returns normally, the interceptor usually has no way of knowing the code wanted a rollback. When needed, let exceptions propagate or apply an explicit rollback strategy.

## 3. @Async: requires async processing enabled and an executor

`@Async` belongs to `org.springframework.scheduling.annotation`. It instructs Spring to execute matching calls through an executor instead of running all the work on the caller's thread.

The most critical condition is **enabling async processing**:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfiguration {
}
~~~

Spring Boot can auto-configure an executor when task-execution auto-configuration conditions match. However, having an executor bean **does not automatically enable** `@Async`. `@EnableAsync` (or equivalent integration configuration) is what activates the components recognizing the annotation and creating advice.

### Asynchronous service example

~~~java
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportGenerator {

    @Async("reportsExecutor")
    public CompletableFuture<String> generate(String reportId) {
        // Illustrative report generation work.
        String result = "report-" + reportId;
        return CompletableFuture.completedFuture(result);
    }
}
~~~

Configuring a dedicated executor for report tasks:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class ReportsAsyncConfiguration {

    @Bean("reportsExecutor")
    ThreadPoolTaskExecutor reportsExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("reports-");
        return executor;
    }
}
~~~

The `"reportsExecutor"` value in `@Async` selects the executor with the matching qualifier/name. If the qualifier is omitted, Spring applies default executor lookup rules or fallbacks based on actual async configuration.

Another bean calls:

~~~java
CompletableFuture<String> result =
        reportGenerator.generate("daily-sales");
~~~

When the call passes through the async proxy, the body of `generate()` runs on the executor. The caller receives a `CompletableFuture` to track completion. Immediately calling `result.join()` makes the caller wait and can negate the timing benefits of async execution.

### Return types and exception handling

In standard `@Async` mechanics, methods can return `void`, `Future<T>`, or `CompletableFuture<T>`.

- With `CompletableFuture`, the caller can handle success/failure via stages such as `thenApply` or `exceptionally`.
- With `void`, the caller receives no future to observe failures. Uncaught exceptions go to `AsyncUncaughtExceptionHandler` if properly configured.
- Exceptions in async tasks do not automatically become synchronous exceptions on the caller's call once the work has been submitted to the executor.

Issues like full executor queues, shutdown, or task rejection also need explicit handling policies. Do not assume every async task is always accepted.

### @Async does not automatically carry over the caller's transaction

A standard imperative transaction uses thread-bound state. `@Async` tasks run on executor-managed threads and therefore **do not automatically inherit the caller's thread-bound transaction**.

Example:

~~~java
@Transactional
public void submitOrder() {
    orderRepository.save(order);
    emailService.sendConfirmation(order);
}
~~~

If `emailService.sendConfirmation()` runs via `@Async`, the email task can start before the outer transaction commits. If the transaction rolls back, the email may still have been sent.

When you want events dispatched only after commit, consider `@TransactionalEventListener(phase = AFTER_COMMIT)`, the outbox pattern, or reliable messaging. Do not mechanically combine `@Async` and `@Transactional` assuming transactions propagate across threads.

## 4. @Cacheable: requires caching enabled and a CacheManager

`@Cacheable` belongs to `org.springframework.cache.annotation`. It specifies that Spring may look up method results by key, skip the method body on a cache hit, or invoke the method and store the result on a cache miss.

Common activation point:

~~~java
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class CachingConfiguration {
}
~~~

Having `spring-boot-starter-cache` on the classpath **is not enough** if caching processing has not been enabled. `@EnableCaching` registers the annotation-processing infrastructure; `CacheManager` provides the actual caches.

Gradle example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-cache'
    implementation 'com.github.ben-manes.caffeine:caffeine'
}
~~~

When dependencies and conditions match, Spring Boot can auto-configure a `CacheManager` backed by a cache provider such as Caffeine. Without a specific provider, defaults may use a simple in-memory cache depending on environment and version. Production should pick an explicit provider and storage policy.

### @Cacheable example

~~~java
import org.springframework.cache.annotation.Cacheable;
import org.springframework.stereotype.Service;

@Service
public class ProductLookup {

    private final ProductRepository productRepository;

    public ProductLookup(ProductRepository productRepository) {
        this.productRepository = productRepository;
    }

    @Cacheable(cacheNames = "products", key = "#sku")
    public Product findBySku(String sku) {
        return productRepository.findBySku(sku)
                .orElseThrow();
    }
}
~~~

The first time a caller calls `findBySku("A-100")` through the proxy:

1. The cache interceptor computes the key from `#sku`.
2. If the key is absent from the `products` cache, the interceptor calls the real method.
3. The result can be stored in the cache under the current policy.
4. The caller receives the result.

On subsequent calls with the same key, the interceptor can return the cached value without calling the repository.

Illustrative Caffeine configuration:

~~~yaml
spring:
  cache:
    type: caffeine
    cache-names: products
    caffeine:
      spec: maximumSize=1000,expireAfterWrite=10m
~~~

`cache-names` specifies caches to create depending on the provider; `caffeine.spec` defines size and expiration in this example. Consider stale data, eviction, and multiple instances maintaining separate local caches.

### Related cache annotations

| Annotation | Role |
|---|---|
| `@Cacheable` | Looks up and can skip method invocation on cache hit |
| `@CachePut` | Always invokes the method, then updates the cache with the result |
| `@CacheEvict` | Removes an entry or clears the cache per configuration |
| `@Caching` | Combines multiple cache annotations on one method |

`@Cacheable` supports `key`, `condition`, `unless`, and other options. Example:

~~~java
@Cacheable(
        cacheNames = "products",
        key = "#sku",
        condition = "#sku != null",
        unless = "#result == null"
)
public Product findBySku(String sku) {
    // ...
}
~~~

`condition` is evaluated before calling the method; `unless` can inspect the result afterward to decide whether not to cache. Avoid caching if results depend on access permissions, request context, or volatile data not captured in the key.

## 5. Where do the three annotations differ?

| Criterion | @Transactional | @Async | @Cacheable |
|---|---|---|---|
| Problem solved | Transactional consistency | Offloading work to an executor | Avoiding repeated computation/queries |
| Common enabling mechanism | `@EnableTransactionManagement` or Boot auto-configuration when applicable | `@EnableAsync` | `@EnableCaching` |
| Required infrastructure | Transaction manager | Executor | Cache manager |
| Effect | Commit/rollback per transaction boundary | Can change execution thread and timing | Can skip method body on hit |
| Common risks | Missing manager, wrong propagation, self-invocation | Running synchronously, lost thread context, rejected tasks | Stale cache, bad keys, caching not enabled |
| Relation to self-invocation | Internal calls bypass transactional advice | Internal calls bypass async advice | Internal calls bypass cache advice |

All three can use Spring AOP proxies, yet **do not share the same transaction manager, executor, or cache manager**. Having one of these infrastructure pieces does not imply the other two appear automatically.

## 6. Infrastructure conditions in Spring Boot

Spring Boot has multiple auto-configurations providing defaults based on classpath and existing beans. Still, distinguish **creating infrastructure** from **enabling annotation processing**.

### Transaction

In JDBC/JPA apps, when dependencies and connection settings are present, Boot can create a `PlatformTransactionManager`. When transaction management conditions match, Boot enables `@Transactional` handling without explicit configuration code.

With multiple transaction managers, a call may need to pick a manager via qualifier or transaction management config:

~~~java
@Transactional("ordersTransactionManager")
public void updateOrder() {
    // ...
}
~~~

The name must match the actual manager bean. Do not assume Spring always picks the right manager when multiple datasources or transaction models exist.

### Async

Boot has `TaskExecutionAutoConfiguration` to provide a suitable executor conditionally. However, having an executor bean does not automatically enable async annotation processing; **`@EnableAsync` remains the decisive step** in normal proxy-based async setup.

An executor governs more than thread count: consider queue capacity, concurrency limits, task rejection, shutdown, and error observability. Use separate executors for workloads with sharply different behaviors.

### Caching

Boot has cache auto-configuration to create a `CacheManager` matching the provider and conditions. `@EnableCaching` provides the interceptor recognizing `@Cacheable`; when cache infrastructure is missing, startup may fail or annotations may have no effect depending on configuration.

Explicit cache manager configuration example:

~~~java
import org.springframework.cache.CacheManager;
import org.springframework.cache.concurrent.ConcurrentMapCacheManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableCaching
public class LocalCacheConfiguration {

    @Bean
    CacheManager cacheManager() {
        return new ConcurrentMapCacheManager("products");
    }
}
~~~

`ConcurrentMapCacheManager` is suitable only for demos or simple local caching. It does not offer distributed policies, multi-instance synchronization, or time-based eviction like dedicated cache providers.

### @SpringBootApplication does not enable everything automatically

`@SpringBootApplication` activates auto-configuration and component scanning, yet do not interpret that as meaning every framework annotation already has full infrastructure ready. Every feature depends on its own conditions.

An application configuration can explicitly enable async and caching:

~~~java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cache.annotation.EnableCaching;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
@EnableCaching
public class ShopApplication {

    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
~~~

This example **does not automatically create a database or transaction manager**. If services use `@Transactional`, the application still needs transaction infrastructure matching its storage technology.

## 7. Proxies and self-invocation: why do annotations still not run?

In proxy-based AOP, advice applies when a caller invokes a method **through a Spring proxy**.

~~~text
Controller
    |
    v
OrderService proxy
    |
    +--> Transaction advice
    |
    v
OrderService target.placeOrder()
~~~

However, if the target calls another method on itself:

~~~java
@Service
public class ProductService {

    public Product loadForOrder(String sku) {
        return findCached(sku);
    }

    @Cacheable(cacheNames = "products", key = "#sku")
    public Product findCached(String sku) {
        return loadProduct(sku);
    }
}
~~~

Calling `findCached(sku)` inside `loadForOrder()` is equivalent to `this.findCached(sku)`. It does not go back through the proxy, so `findCached()`'s caching advice is skipped for this call.

The same rule applies to:

~~~java
public void doWork() {
    saveInNewTransaction(); // @Transactional does not create a new boundary here
    sendAsync();            // @Async does not dispatch to an executor here
    readFromCache();        // @Cacheable does not check cache here
}
~~~

For transactions, if the outer method already opened a transaction, the inner method can still run **inside the existing transaction**. What gets skipped is the inner method's own advice, such as `REQUIRES_NEW` or a custom timeout.

Other limitations to keep in mind:

- `private` methods are not intercepted under class-based proxy rules because they cannot be overridden.
- `final` methods cannot be overridden by class-based proxies.
- JDK interface proxies expose only methods through proxied interfaces.
- Calls inside constructors or certain early initialization steps may occur before the proxy is ready for the intended usage.

Switching from JDK dynamic proxies to CGLIB does not fix self-invocation. The core issue remains **whether the call path passes through the proxy**.

## 8. Solution: place advice boundaries between beans

The clearest solution is usually moving the capability needing advice into an independent bean and injecting that bean into the caller.

For example, a workflow creating an order in a transaction and sending a notification asynchronously:

~~~java
@Service
public class CheckoutService {

    private final OrderWriter orderWriter;
    private final NotificationSender notificationSender;

    public CheckoutService(
            OrderWriter orderWriter,
            NotificationSender notificationSender) {
        this.orderWriter = orderWriter;
        this.notificationSender = notificationSender;
    }

    public void checkout(Order order) {
        orderWriter.save(order);
        notificationSender.sendAsync(order.getId());
    }
}
~~~

Bean with the transaction boundary:

~~~java
@Service
public class OrderWriter {

    private final OrderRepository repository;

    public OrderWriter(OrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void save(Order order) {
        repository.save(order);
    }
}
~~~

Bean with the async boundary:

~~~java
@Service
public class NotificationSender {

    @Async("reportsExecutor")
    public void sendAsync(Long orderId) {
        // Send notification using configured executor.
    }
}
~~~

In this example, `CheckoutService` invokes both dependencies through Spring beans, allowing `OrderWriter` and `NotificationSender`'s individual advice to execute.

However, calling `save()` and then `sendAsync()` **does not guarantee the notification is sent only after an outer transaction commits**. If atomicity with notification delivery is needed, design around actual commit boundaries, such as a transactional outbox or post-commit events.

## 9. Combining @Transactional and @Async

Placing both annotations on a single method can make advice ordering and thread context hard to reason about. For example:

~~~java
@Async
@Transactional
public void processInBackground() {
    // ...
}
~~~

The intent may be opening a transaction on the background thread, yet knowing for sure which infrastructure intervenes before/after requires checking proxy/advisor configuration and the executor.

A design that is usually easier to reason about is:

~~~text
Caller
  |
  v
AsyncCoordinator proxy
  |
  v
Executor thread
  |
  v
TransactionWorker proxy
  |
  v
Transaction opens on executor thread
  |
  v
Data operations
~~~

Example:

~~~java
@Service
public class AsyncCoordinator {

    private final TransactionWorker worker;

    public AsyncCoordinator(TransactionWorker worker) {
        this.worker = worker;
    }

    @Async("reportsExecutor")
    public CompletableFuture<Void> process(String id) {
        worker.processTransaction(id);
        return CompletableFuture.completedFuture(null);
    }
}
~~~

~~~java
@Service
public class TransactionWorker {

    @Transactional
    public void processTransaction(String id) {
        // Data operations on the calling thread.
    }
}
~~~

When `AsyncCoordinator.process()` is invoked via the async proxy, its body runs on an executor thread; calling the `TransactionWorker` bean passes through the transactional proxy and opens a transaction on that thread.

Handle exceptions in the future and avoid sharing mutable non-thread-safe data across tasks. If business logic demands synchronous results and strict consistency, not every operation should use `@Async`.

## 10. Combining @Transactional and @Cacheable

Caches and databases have different consistency models. Database transactions commit/roll back; caches store or evict entries depending on advice and provider.

Example:

~~~java
@Cacheable(cacheNames = "products", key = "#sku")
@Transactional(readOnly = true)
public Product getProduct(String sku) {
    return productRepository.findBySku(sku)
            .orElseThrow();
}
~~~

On a cache hit, the caching interceptor can return the result without invoking the method body. Therefore, do not assume every call to `getProduct()` runs a query or enters the method body's transaction behavior.

In what order the cache advisor and transaction advisor wrap each other depends on advisor ordering configuration. For data updates, never assume cache writes always occur **after database commit**.

A common pattern:

~~~java
@Transactional
public void updateProduct(Product product) {
    productRepository.save(product);
    // Cache update/eviction requires its own consistency policy.
}
~~~

If using `@CacheEvict` or `@CachePut`, determine when the cache mutates relative to transaction commit and how rollbacks are handled. Consider transaction-aware caches or publishing post-commit events when strong consistency is required.

Also note: if a method is called multiple times within the same instance via self-invocation, cache advice is skipped even if the cache manager exists and cache names are correct.

## 11. Not every call needing advice fits @Async or caching

Some important design limits:

**Transaction:** meaningful only across resources managed by the transaction manager. A single JDBC transaction cannot automatically guarantee atomicity for an HTTP request or an external system not participating in the transaction.

**Async:** does not magically make CPUs faster. It moves work to an executor; if task rates exceed capacity, queues grow and tasks may be rejected. Concurrency, timeouts, and shutdown must be managed.

**Cache:** boosts repeated reads yet introduces stale data problems. When source data changes, invalidation policies or TTLs are needed. If cache keys omit tenant/user/context, the wrong data can be returned to another caller.

**Proxy:** not everything created with `new` is a Spring bean. If an object is instantiated manually outside the `ApplicationContext`, do not expect Spring to apply transaction, async, or caching advice to its methods.

## 12. Diagnosing when an annotation has no effect

When `@Transactional`, `@Async`, or `@Cacheable` fails to behave as expected, separate **infrastructure** issues from **call-path** issues.

| Symptom | What to check |
|---|---|
| Has `@Transactional` yet no transaction | Transaction manager, annotation support, bean proxy, self-invocation |
| `REQUIRES_NEW` does not create an independent transaction | Internal call, selected transaction manager, caller boundary |
| Has `@Async` yet runs on request thread | `@EnableAsync`, whether caller goes through proxy, executor |
| Async task does not run or gets dropped | Executor rejection, shutdown, exception handling |
| Has `@Cacheable` yet always queries | `@EnableCaching`, `CacheManager`, cache name/key, self-invocation |
| Cache returns stale or wrong data | TTL/invalidation, cache provider, keys and request context |
| Bean has annotation yet is not advised | Whether Spring manages the bean, method visibility, final/private, proxy type |

### Checking the proxy

In an appropriate test or diagnostic check, you can use:

~~~java
import org.springframework.aop.support.AopUtils;

boolean proxied = AopUtils.isAopProxy(someServiceBean);
~~~

A `true` result shows the bean is a Spring AOP proxy, **not proof** that a specific method is handled by a transaction, async, or cache interceptor. Observe actual behavior and applied advisors.

### Checking the current transaction

~~~java
import org.springframework.transaction.support.TransactionSynchronizationManager;

boolean active =
        TransactionSynchronizationManager.isActualTransactionActive();
~~~

This is useful for imperative transactions on the current thread, not a general check for reactive transactions. If the call already sits inside a transaction opened by another caller, `true` does not prove the tested method's own interceptor ran.

### Observing async threads and cache hits

Inside an `@Async` method, you can log the thread name to distinguish caller threads from executor threads. Inside a `@Cacheable` method, you can count repository calls to see whether the method body is skipped on cache hits.

Keep such checks in tests or diagnostic logs, avoiding logging sensitive data or putting unnecessary verbose logs into production.

## 13. Testing suggestions for each infrastructure

A Spring Boot test suite can verify:

1. **Transaction:** invoke a service from another bean and verify transactions work and roll back on matching exceptions.
2. **Propagation:** test `REQUIRES_NEW` across two separate beans, not through `this.method()`.
3. **Async:** invoke a method through a Spring bean, receive the future, verify work ran on the executor and errors follow the contract.
4. **Cache:** call the same key twice through the proxy, verify the repository ran the expected number of times; change key and observe cache miss.
5. **Missing infrastructure:** in minimal test setups, observe the effect when activation annotations or managers are omitted.
6. **Integration:** verify post-commit events, cache invalidation, and executor shutdown when multiple advisors coexist.

Do not conclude AOP works merely because a test calls methods directly on an object created with `new`. A plain unit test without an `ApplicationContext` lacks the Spring proxies present in the real app.

When using `@SpringBootTest` or context runners, remember tests themselves may run inside a transaction, altering outcomes if test transaction boundaries are unclear.

## 14. Step-by-step checklist for choosing and using them properly

When adding an AOP annotation to a Spring Boot service:

1. Identify the actual requirement: transaction, async, or caching.
2. Verify the dependency for that mechanism is on the classpath.
3. Ensure the feature is enabled: transaction management, async processing, or caching.
4. Configure the proper manager/executor/cache provider; specify bean names if multiple options exist.
5. Place the method at an entry point callable through a Spring proxy, avoiding self-invocation.
6. Check return types, exception handling, and thread context if using `@Async`.
7. Check transaction boundaries, propagation, and rollback semantics if using `@Transactional`.
8. Design cache keys, expiration, and invalidation if using `@Cacheable`.
9. When combining multiple annotations, evaluate advisor ordering, transaction commits, and data consistency.
10. Test actual behavior through Spring-managed beans rather than just checking annotation presence.

The key point to remember is that **annotations, proxies, and execution infrastructure are three separate parts**. `@Transactional` needs a transaction manager; `@Async` needs async processing and an executor; `@Cacheable` needs caching processing and a cache manager. In proxy mode, all three can intervene only when calls pass through the appropriate proxy. Separating bean boundaries cleanly and configuring explicit infrastructure helps avoid subtle bugs in Spring Boot applications.
