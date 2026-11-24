# Beans Must Be Container-Managed for Annotations to Be Processed

## 1. Main Takeaway in One Sentence

In the Spring Framework, putting **`@Async` on a Java method does not by itself make that method run on another thread**. In the default mode, Spring must **manage the bean**, enable asynchronous processing with **`@EnableAsync`**, create or attach an appropriate **proxy**, and have **the call go through the proxy**. If you create an object yourself with `new` and call the method, the annotation is merely metadata; Spring will not step in to intercept the call.

~~~text
Correct: caller ---> Spring-managed proxy ---> @Async interceptor
                                           |
                                           v
                                      TaskExecutor ---> worker thread
                                           |
                                           v
                                      target.method()

Unexpected: caller ---> new Service().method()
                              |
                              v
                       ordinary Java call
                       (bypasses proxy)
~~~

**Distinguish two conditions:**

1. **The bean must belong to the Spring IoC container** so the context's BeanPostProcessors can discover and process its annotations.
2. **The call must go through the appropriate interception mechanism**. In the default `AdviceMode.PROXY` mode, internal calls like `this.asyncMethod()` can bypass the proxy even when the object is already a bean.

This lesson belongs to the topic **Enabling @Async**. The focus is the container-managed bean requirement, proxy formation, proper invocation, and signs for diagnosing when `@Async` appears not to work. Thread pools, queues, transactions, and propagation are mentioned insofar as they help clarify the exact boundaries of the annotation.

## 2. Why Must Spring Manage the Object?

### 2.1. Java Annotations Do Not Execute Logic on Their Own

`@Async` is a marker annotation indicating that a method or class can run asynchronously. It is not a Java keyword that forces the JVM to spawn a thread, nor does it automatically rewrite the bytecode of an object you instantiate with `new`.

In the default proxy configuration, Spring uses annotation-processing and AOP infrastructure to apply an interceptor to **beans registered in the ApplicationContext**. A caller receives a reference to the processed bean (typically a proxy). When the caller invokes an `@Async` method through this reference, the interceptor selects an executor and submits the work to run on a worker.

**Misleading** example:

~~~java
public class EmailService {
    @Async
    public void send(String address) {
        System.out.println(Thread.currentThread().getName());
    }
}

// In another class:
EmailService service = new EmailService();
service.send("user@example.test"); // runs synchronously on the current thread
~~~

These are **illustrative code snippets**, not a standalone program (imports for `@Async` and placing the call inside a method are required). The object created by `new EmailService()` is **not registered/managed by Spring**, so it is not automatically proxied by the context's `@Async` infrastructure.

As a result, `send()` runs like ordinary Java code. It may print the main thread or request thread name; having the annotation in source code does not alter this execution path.

### 2.2. How Is a Container-Managed Bean Different From Just an Object in the JVM?

| Situation | Is It a Spring-Managed Bean? | Does `@Async` Have a Chance to Be Processed? |
| --- | --- | --- |
| Class annotated with `@Component`/`@Service` within an active `@ComponentScan` area | Yes | Yes, when `@EnableAsync` is enabled in the same context and called via proxy |
| Object returned by a `@Bean` method and registered in the context | Yes | Yes, provided proxy/lifecycle conditions are met |
| Object registered via a valid Spring bean registration mechanism | Yes | Yes, if passed through the required post-processors |
| Object created with `new MyService()` inside a controller and called directly | **No** | **No**, not via the `@Async` annotation |
| Object stored in a static field without being registered as a Spring bean | No | No |
| Bean lives in another ApplicationContext where async processing is not enabled | Yes in that context | Not necessarily; `@EnableAsync` is scoped per context |
| Bean has `@Async`, but is called via `this.method()` from inside the same bean | Yes | Internal calls are typically **not intercepted** in proxy mode |

The phrase "**managed by Spring**" does not strictly mean you must write `@Service`. Spring has multiple ways to create and register beans. **What determines the outcome is whether the instance used for the call passes through the context's management and AOP mechanisms.**

## 3. Registering Beans Properly So @Async Is Processed

### 3.1. @Service or @Component and Component Scanning

Common approach in a Spring Boot application:

~~~java
@Service
public class InvoiceService {
    @Async("invoiceExecutor")
    public CompletableFuture<String> generate(long invoiceId) {
        // Runs on the specified executor when called through the proxy.
        return CompletableFuture.completedFuture("invoice-" + invoiceId);
    }
}
~~~

This is an illustrative snippet requiring the appropriate imports, `@EnableAsync`, and a bean named `invoiceExecutor`. When the app's component scan covers the package containing `InvoiceService`, the bean is registered by Spring. **Inject this bean** into another bean instead of instantiating it manually.

~~~java
@Service
public class BillingFacade {
    private final InvoiceService invoiceService;

    public BillingFacade(InvoiceService invoiceService) {
        this.invoiceService = invoiceService;
    }

    public CompletableFuture<String> startInvoice(long id) {
        return invoiceService.generate(id);
    }
}
~~~

The call from `BillingFacade` to `InvoiceService` goes through the Spring-injected reference; under a proper proxy configuration, `generate()` is dispatched to the executor. **Constructor injection** makes dependencies explicit and reduces the risk of accidentally calling an unmanaged object.

However, merely writing `@Service` on a class is **not enough** if the package is not scanned, the scan configuration is wrong, the bean is excluded by a profile/condition, or the caller still uses `new InvoiceService()`. When diagnosing, verify that **the bean actually exists in the ApplicationContext** and that the reference in use originates from the context.

### 3.2. @Bean Can Return an Object Created With new — Still Managed

A common misconception is "wherever you see the `new` keyword, `@Async` won't work." What actually matters is **what owns the object after creation**:

~~~java
@Configuration
@EnableAsync
public class WorkerConfig {
    @Bean
    public ExportWorker exportWorker() {
        return new ExportWorker(); // the return value is registered as a Spring bean
    }
}
~~~

This is an illustrative configuration snippet, not standalone. The object is created with `new` **inside a `@Bean` method** and then taken over by Spring to be managed as a bean. That differs from a controller calling `new ExportWorker()` itself and holding a private reference outside the context.

Do not **call the factory method directly** via `new WorkerConfig().exportWorker()` expecting the returned object to have gone through post-processing. Inject the bean or retrieve it from the context properly.

**Another note:** placing `@Async` directly on a **method declared inside a `@Configuration` class** is not a Spring-supported way to run business logic asynchronously. Put `@Async` on methods of **service beans**, while `@Configuration` handles declaring infrastructure and beans.

### 3.3. Which Context Enables @EnableAsync?

Minimal configuration:

~~~java
@Configuration
@EnableAsync
public class AsyncConfig {
    // A TaskExecutor can be declared here.
}
~~~

Once loaded by Spring into an ApplicationContext, `@EnableAsync` turns on annotation-driven asynchronous method execution for that corresponding context. In Spring Boot, this annotation can be placed on an appropriate `@Configuration` or startup class.

If an application has **multiple ApplicationContexts** (for example, a root context and a separate DispatcherServlet context in certain architectures), `@EnableAsync` in one context **does not automatically apply to all beans in other contexts**. You must determine accurately which context owns the service and where the async infrastructure is active.

## 4. Two Layers That Must Be Right: Bean Registration and Proxy Invocation

Imagine Spring contains:

~~~text
ApplicationContext
    |
    +-- Async infrastructure: @EnableAsync
    |
    +-- Bean definition: invoiceService
            |
            +-- Creates target InvoiceService
            +-- BeanPostProcessor inspects @Async
            +-- Provides proxy reference to consumer
                    |
Caller ---------> proxy.generate(42)
                    |
                    +-- selects TaskExecutor
                    +-- submits execution
                              |
                              v
                         worker thread
                              |
                              v
                         InvoiceService.generate(42)
~~~

This is a **conceptual diagram**, not a promise that Spring always uses one exact proxy shape or that every phase occurs in this simplified order. Spring AOP may use a **JDK dynamic proxy** or a **class-based proxy** depending on interfaces, configuration, and existing proxies.

**Frequently confused points:**

- **A bean having the annotation** does not guarantee **every** call to it runs asynchronously.
- **A method running on a different thread** is not necessarily proof that `@Async` ran; the caller could also have used an `ExecutorService` itself.
- **Having a TaskExecutor** in the context does not mean `@EnableAsync` is enabled or that `@Async` is definitely using that pool.
- **Calling through a proxy** determines whether interception occurs in the default mode; singleton/prototype scope does not fix interception issues by itself.

An application can suffer from both mistakes at once: manually calling `new` on a service and forgetting to enable `@EnableAsync`. Diagnostics must check each condition independently.

## 5. Self-Invocation Pitfall

This is a common mistake **even when the bean is already managed by Spring**:

~~~java
@Service
public class ImportService {
    public void startImport() {
        this.importAsync(); // internal call, typically bypasses proxy
    }

    @Async
    public void importAsync() {
        // Task expected to run in background, but may run synchronously.
    }
}
~~~

This snippet is illustrative code requiring imports and `@EnableAsync`. When `startImport()` is running inside the bean's **target**, `this.importAsync()` is an internal Java call. It does not pass through the Spring proxy held by callers, so `@Async` advice is typically not triggered.

**Recommended design:** extract the async task into a separate bean and inject it via constructor:

~~~java
@Service
public class ImportWorker {
    @Async("importExecutor")
    public CompletableFuture<Void> runAsync() {
        // Execute task.
        return CompletableFuture.completedFuture(null);
    }
}

@Service
public class ImportFacade {
    private final ImportWorker worker;

    public ImportFacade(ImportWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<Void> startImport() {
        return worker.runAsync(); // called through injected proxy
    }
}
~~~

The classes above are **illustrative code requiring imports and executor configuration**, distinct from the standalone demo in section 8. Separating beans makes the async boundary explicit, easy to test, and avoids circular dependencies.

Techniques like self-injection, grabbing `AopContext.currentProxy()`, or enabling circular references to call through a proxy are **not recommended default choices**. They couple code to AOP internals, hurt maintainability, and can cause lifecycle issues.

If you choose **`@EnableAsync(mode = AdviceMode.ASPECTJ)`** with spring-aspects and properly configured compile-time/load-time weaving, Spring can intercept self-invocation as well; this is a **different mode** from the default proxy mode, not a fix where flipping one attribute makes it work immediately.

## 6. Private, Final, Static, Constructors, and Lifecycle Callbacks

Proxy-based AOP has technical boundaries. When designing `@Async` methods, the simplest and most predictable approach is:

- Use **public, non-final methods** on **Spring-managed beans**.
- Call that method **from another bean through an injected reference**.
- Ensure the class can be proxied if Spring needs a class-based proxy.
- Avoid expecting advice for **private methods**, **static methods**, **constructors**, or code running **before the proxy is ready**.

Incorrect example:

~~~java
@Service
public class StartupService {
    @PostConstruct
    void init() {
        initializeAsync(); // lifecycle timing, internal call
    }

    @Async
    private void initializeAsync() {
        // Should not be expected to be intercepted by Spring proxy.
    }
}
~~~

This is an illustrative snippet (requiring Jakarta `@PostConstruct`, `@Service`, `@Async` imports). It is both a private method and called internally inside a lifecycle callback. `@Async` **must not be used as an async mechanism for the `@PostConstruct` callback itself**.

If you truly need to start a background task after the app is ready, you can use **ApplicationReadyEvent** in Spring Boot or a separate coordinator bean to invoke an `@Async` method on another bean, while clearly defining when the system considers initialization complete. Do not launch background tasks before dependencies/context are in an appropriate state.

**Final and proxies:** class-based proxies cannot override final methods; a final class also restricts subclass proxies. JDK dynamic proxies primarily expose methods via the corresponding interface, so injecting by concrete class may not work. Do not treat `proxyTargetClass=true` as a way around final/private; it only changes the proxy mechanism.

## 7. @EnableAsync, Executor, and Return Type Must Be Compatible

Spring selects an executor according to the qualifier on `@Async("beanName")`, async configuration, and the version/context's executor lookup rules. For applications with multiple pools, specify explicitly:

~~~java
@Bean("reportExecutor")
public ThreadPoolTaskExecutor reportExecutor() {
    ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
    executor.setCorePoolSize(2);
    executor.setMaxPoolSize(2);
    executor.setQueueCapacity(20);
    executor.setThreadNamePrefix("report-");
    return executor;
}
~~~

This is a configuration snippet inside a `@Configuration` class with appropriate imports. A Spring-managed `ThreadPoolTaskExecutor` bean is initialized according to the container lifecycle. Avoid calling `new ThreadPoolTaskExecutor()` outside the container and forgetting to call initialize/shutdown.

Valid return types of an `@Async` method are typically **`void`**, **`Future<T>`**, or **`CompletableFuture<T>`**. For Future-returning methods, the caller receives a Future provided by the async mechanism. The method body usually creates a completed handle/suitable placeholder value for the interceptor to wrap the result.

~~~java
@Async("reportExecutor")
public CompletableFuture<String> createReport(long id) {
    // This method runs on a worker when properly called through the proxy.
    return CompletableFuture.completedFuture("report-" + id);
}
~~~

This is an illustrative method in another bean, not code inside `@Configuration`. Calling `createReport(...).get()` waits for the result and can block the caller; to preserve asynchronicity, design composition/continuations instead of waiting immediately on the request thread unless necessary.

With `@Async void`, errors running on the worker cannot automatically be thrown back to a caller that has already returned; you need a logger/`AsyncUncaughtExceptionHandler` or another contract. With a Future, callers must observe completion/exceptions and timeouts. Executors can become overloaded/reject tasks; `@Async` is **not a durable queue** and does not promise tasks will always execute.

## 8. Complete Example: new, Bean Proxy, Self-Invocation, Calling Through Another Bean

This demo **runs with Java 17+, Gradle, and Spring Framework 6.1.14**, without Spring Boot or a web server. We intentionally use the same `ReportWorker` class along four paths:

1. `new ReportWorker()`: outside the container, `@Async` is ignored.
2. `context.getBean(ReportWorker.class)`: returns a Spring-processed reference; calling the `@Async` method goes through the proxy.
3. Calling `selfCall()` on the managed bean: the ordinary method calls `this.threadNameAsync()` inside the target, bypassing the proxy.
4. Another bean injects `ReportWorker` and calls it through the injected reference: proper proxy boundary.

### 8.1. File Structure

~~~text
async-bean-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/demo/AsyncBeanDemo.java
~~~

File **settings.gradle**:

~~~groovy
rootProject.name = 'async-bean-demo'
~~~

File **build.gradle**:

~~~groovy
plugins {
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
    implementation 'org.springframework:spring-context:6.1.14'
}

application {
    mainClass = 'demo.AsyncBeanDemo'
}
~~~

File **src/main/java/demo/AsyncBeanDemo.java**:

~~~java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.aop.support.AopUtils;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public final class AsyncBeanDemo {

    public static void main(String[] args) throws Exception {
        try (var context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            String callerThread = Thread.currentThread().getName();

            // Plain Java object: annotation is not processed.
            ReportWorker unmanaged = new ReportWorker();
            String unmanagedThread = unmanaged.threadNameAsync()
                    .get(5, TimeUnit.SECONDS);
            System.out.println("new runs on caller: " +
                    callerThread.equals(unmanagedThread));

            // Bean processed and returned by the Spring container.
            ReportWorker managed = context.getBean(ReportWorker.class);
            System.out.println("managed is proxy: " +
                    AopUtils.isAopProxy(managed));

            // External call through proxy triggers @Async.
            String managedThread = managed.threadNameAsync()
                    .get(5, TimeUnit.SECONDS);
            System.out.println("external call uses pool: " +
                    managedThread.startsWith("demo-worker-"));

            // Call to this.threadNameAsync() inside the same target.
            String selfThread = managed.selfCall()
                    .get(5, TimeUnit.SECONDS);
            System.out.println("self-call stays on caller: " +
                    callerThread.equals(selfThread));

            // Another bean receives the managed proxy via constructor injection.
            DelegatingCaller caller = context.getBean(DelegatingCaller.class);
            String delegatedThread = caller.call()
                    .get(5, TimeUnit.SECONDS);
            System.out.println("injected caller uses pool: " +
                    delegatedThread.startsWith("demo-worker-"));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {

        @Bean("demoExecutor")
        public ThreadPoolTaskExecutor demoExecutor() {
            ThreadPoolTaskExecutor executor =
                    new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(2);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("demo-worker-");
            return executor;
        }

        // Uses 'new' here, but the return value is a Spring-managed bean.
        @Bean
        public ReportWorker reportWorker() {
            return new ReportWorker();
        }

        @Bean
        public DelegatingCaller delegatingCaller(ReportWorker worker) {
            return new DelegatingCaller(worker);
        }
    }

    public static class ReportWorker {

        @Async("demoExecutor")
        public CompletableFuture<String> threadNameAsync() {
            String current = Thread.currentThread().getName();
            return CompletableFuture.completedFuture(current);
        }

        public CompletableFuture<String> selfCall() {
            return this.threadNameAsync(); // Bypasses proxy on self-invocation.
        }
    }

    public static class DelegatingCaller {
        private final ReportWorker worker;

        public DelegatingCaller(ReportWorker worker) {
            this.worker = worker;
        }

        public CompletableFuture<String> call() {
            return worker.threadNameAsync();
        }
    }
}
~~~

### 8.2. Running and Output

From the `async-bean-demo` directory, with JDK 17+ and Gradle installed:

~~~bash
gradle run
~~~

If using Gradle Wrapper, run `./gradlew run` on Linux/macOS or `gradlew.bat run` on Windows.

Assuming the executor operates normally and tasks complete before the five-second timeout, the **five lines printed by the program** are:

~~~text
new runs on caller: true
managed is proxy: true
external call uses pool: true
self-call stays on caller: true
injected caller uses pool: true
~~~

Gradle and libraries may print additional build/log messages. The example uses boolean checks instead of printing worker numbers so the output does not depend on whether the pool creates `demo-worker-1` or `demo-worker-2`. If a task is rejected or the system is overloaded, `get(timeout)` may throw an exception; the demo assumes normal runtime operation.

### 8.3. What to Observe

- `unmanaged` is an object created directly in code; Spring knows nothing about it. The method still returns a `CompletableFuture`, but it is created **right on the caller thread**. Merely seeing a Future return type does not prove the method was dispatched to an executor.
- `managed` retrieved from `ApplicationContext` is a post-processed bean. Because `ReportWorker` declares no interface, Spring uses an appropriate class-based proxy in the demo; `AopUtils.isAopProxy(managed)` returns true.
- `managed.threadNameAsync()` is an external call through the proxy, so the method body runs on a thread with the `demo-worker-` prefix.
- `managed.selfCall()` does not have `@Async`; the method runs synchronously, and the `this.threadNameAsync()` call inside the target **does not go through the proxy**, so `threadNameAsync()` runs on the caller.
- `DelegatingCaller` is another bean; it receives the Spring-injected `ReportWorker` and calls the method through the proxy, so async works.
- A `@Bean` method creating an object with `new` **does not make the object unmanaged**: the difference is that the returned instance is registered and post-processed by the container.
- `try-with-resources` closes the context after the Futures complete, letting Spring manage the executor's lifecycle.

The code in section 8 is a **complete program**; the short snippets in earlier sections are **illustrations requiring additional context/imports** and should not be copied individually expecting them to run on their own.

## 9. Calling the Right Bean in Web and Multi-Layer Applications

In a Spring MVC or Spring Boot application, a controller is normally already a Spring-managed bean. However, if the controller creates a service using `new`, that service still sits outside annotation processing:

~~~java
@RestController
public class ExportController {
    @GetMapping("/export")
    public String wrong() {
        ExportService service = new ExportService();
        service.exportAsync(); // @Async is not intercepted by Spring.
        return "submitted";
    }
}
~~~

This is an **intentionally wrong** example, not complete code. A Spring-managed controller does not make every object instantiated by that controller **automatically become a bean**.

The right way is to inject the service:

~~~java
@RestController
public class ExportController {
    private final ExportService service;

    public ExportController(ExportService service) {
        this.service = service;
    }

    @PostMapping("/export")
    public ResponseEntity<Void> start() {
        service.exportAsync(); // reference to Spring-managed proxy
        return ResponseEntity.accepted().build();
    }
}
~~~

This snippet is also illustrative, requiring the `ExportService` definition, `@EnableAsync`, and imports. An HTTP 202 should only promise "**request accepted**" if the system has a corresponding contract. `@Async` with an in-memory executor does **not** automatically guarantee work is persisted across restarts, so production endpoints must clearly define what "accepted" means.

If a method is slow, do not simply slap `@Async` onto a controller handler without reviewing MVC contracts, return types, and async request handling. It is usually better to extract background work into a service bean with a clear interface and then choose how to return results appropriately.

## 10. Why Does @Async Still Not Work Even With a Bean?

There are several independent causes to inspect:

| Symptom | Possible Cause | How to Handle |
| --- | --- | --- |
| Method prints request/main thread name | Service instantiated with `new` outside context | Inject the registered bean |
| `@Service` present but bean missing at startup | Package outside `@ComponentScan`, mismatching profile/condition | Check scan and bean registration |
| Bean exists but method runs synchronously | Missing `@EnableAsync` in the bean's context | Enable async in the right context |
| Method called from same class via `this` | Self-invocation bypasses default proxy | Extract worker into another bean and inject |
| Private/final/static method or unproxiable class | Proxy cannot intercept the method | Use public non-final instance methods and a proxiable structure |
| `@Async` placed on a `@Configuration` method | Not supported there as an async service method | Move logic to a service bean |
| Called during `@PostConstruct` | Lifecycle/self-invocation before proper proxy boundary | Coordinate from another bean after initialization |
| Expected executor prefix not seen | Method chose another executor, wrong qualifier, or bypassed proxy | Specify `@Async("executorName")`, verify bean and call flow |
| Injecting concrete class fails with JDK proxy | Proxy exposes interface, not concrete type | Inject the interface or configure class-based proxying when compatible |
| `@Async` runs but request still waits long | Caller immediately calls `get()`/`join()` or other logic blocks | Review result strategy and waiting point |
| Background error not thrown to caller | `void` method and exception occurs on worker | Use Future and track errors, or `AsyncUncaughtExceptionHandler` |

**Step-by-step diagnosis:**

1. Print the thread name at the **start of the method** (for diagnostics only; never use thread names in business conditions).
2. Confirm `@EnableAsync` was processed in the bean's actual context.
3. Check that the bean appears in the context and is injected from the context, not created with `new`.
4. Check the call path: is it **another bean -> proxy.method()** or **this.method()**?
5. Confirm the method can be intercepted by a proxy (public/non-final is the common safe choice).
6. Inspect the selected executor and signs of task rejection/overload.
7. Observe exceptions/completion on the `Future` if applicable.
8. Do not overlook test setup: unit tests instantiating objects with `new` do not reflect AOP behavior; to test proxies, run tests with an appropriate ApplicationContext.

With `AopUtils.isAopProxy(obj)` in a running Spring example, `true` proves the reference is an AOP proxy, but is **not sufficient alone** to prove a specific call is intercepted by `@Async`. A bean might be proxied for other advices; check `@EnableAsync`, the method, and the call path as well.

## 11. Related Boundaries: Transactions, Context, and Thread Safety

When an `@Async` method is successfully dispatched:

- The worker is typically a **different thread** from the caller. **ThreadLocals** such as request attributes, MDC, or security context **are not automatically copied** without a propagation mechanism.
- **Transactions bound to the caller thread** do not automatically follow the worker. If an async method needs its own transaction, establish the boundary on a service called by the worker on that thread—for instance `@Transactional` invoked through a proxy—and scope transactions narrowly around DB operations. Do not hold a transaction open during slow API calls or file generation.
- **Singleton beans** are shared across workers: `@Async` does not make mutable fields inside a bean thread-safe; prefer stateless services, immutable data, and synchronization where necessary.
- **Executors have finite capacity**. Under overload, tasks may be rejected; use bounded queues, explicit rejection policies, and job state tracking.
- **Contexts have a lifecycle**. Async tasks depending on beans may execute during shutdown if not properly configured/controlled; do not treat the annotation as a guarantee that tasks finish after process termination.

The issues above **do not negate** the lesson's core rule: for the annotation to work under the default proxy mechanism, the instance must live in the Spring container and the call must pass through the proxy. Once those two conditions are met, concurrency design still requires independent scrutiny.

## 12. Checklist Before Using @Async in Code Review

- [ ] `@EnableAsync` is enabled in the **right ApplicationContext**.
- [ ] Service class is registered via `@Service`/`@Component`, `@Bean`, or an appropriate bean registration mechanism.
- [ ] Caller **injects** the service bean rather than calling `new` for another instance.
- [ ] Async calls go through the **proxy**; never via `this.asyncMethod()`.
- [ ] Methods are proxy-friendly: public, non-final; `@Async` is not placed on lifecycle callbacks or `@Configuration` methods.
- [ ] Executor is selected correctly via qualifier or async configuration; queue/thread/rejection limits are defined.
- [ ] Return type `void`/`Future`/`CompletableFuture` and error handling strategy are chosen intentionally.
- [ ] Do not assume transactions, ThreadLocals, request context, or security context follow the worker automatically.
- [ ] Do not store request-specific mutable state on shared singleton fields.
- [ ] Tests run **within an ApplicationContext** to verify that the proxy actually executes.

## 13. Self-Check Questions

1. **A class has `@Service` but is instantiated manually with `new`—does `@Async` take effect?** Not via Spring AOP on that object. For Spring to process it, you must use a Spring-managed instance.
2. **Why is `return new ReportWorker()` inside a `@Bean` method different from `new ReportWorker()` inside a controller?** The object returned by `@Bean` goes through context registration and bean post-processing; one created with `new` in a controller does not.
3. **If a bean is already managed by Spring, is `this.runAsync()` asynchronous?** Usually not in default `AdviceMode.PROXY` because self-invocation bypasses the proxy.
4. **Is `@EnableAsync` required?** Yes, to turn on annotation-driven async processing in the corresponding Spring configuration, unless equivalent infrastructure is explicitly configured another way.
5. **Does `@Async` create a new thread every time?** Not necessarily. It submits the task to an executor; `ThreadPoolTaskExecutor` can reuse workers.
6. **Does returning `CompletableFuture` prove the method ran asynchronously?** No. A regular Java method can also return an already-completed Future synchronously.
7. **Should `@Async` be placed on a private method within the same bean?** Do not expect proxy mode to intercept it; extract to a public method on another bean.
8. **Can AspectJ mode intercept self-invocation?** Yes, when weaving and required dependencies are properly configured; this is not the default behavior.
9. **Why don't unit tests calling `new SomeService()` observe async behavior?** Because the test only invokes a plain Java object with no Spring proxy/interceptor.
10. **Does a successful `@Async` call guarantee transactions, request data, and business completion?** No; each contract must be designed and controlled separately.

**Conclusion:** Spring treats `@Async` as a capability of **container-managed beans**, not as a Java instruction active on arbitrary objects. With the default proxy mode, the two easiest rules to remember are **register the service as a bean** and **call the service through a Spring-injected reference from another bean**. This is the foundation before tuning executors or optimizing concurrency.

### Official Documentation

- [Spring Framework — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html)
- [Spring Framework — EnableAsync API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html)
- [Spring Framework — Async API](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/scheduling/annotation/Async.html)
- [Spring Framework — Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Spring Framework — Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html)
