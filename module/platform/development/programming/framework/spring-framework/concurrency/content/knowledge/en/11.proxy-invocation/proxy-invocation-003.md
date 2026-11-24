# Distinguishing Objects Created with new from Injected Beans

## 1. Goal: Following the Exact Object a Call Actually Goes Through

In the Spring Framework, two variables can have the same type `ReportService` yet behave **completely differently**:

- `new ReportService()` is a Java object created by code calling the constructor directly; it is not automatically managed by the Spring container.
- A `ReportService` received via constructor injection, `@Autowired`, or `ApplicationContext.getBean(...)` is a **bean reference** provided by the container. Depending on configuration, this reference may be a **proxy** rather than the raw target object.

This distinction is especially important in **Spring Framework - concurrency**, because `@Async` in the default mode uses a **Spring AOP proxy** to intercept calls and submit tasks to an executor. A method annotated with `@Async` on a manually instantiated `new` instance typically runs synchronously like an ordinary Java method.

**Learning objectives after this lesson:**

1. Explain the difference between a manually created object, a registered bean, and an injected proxy.
2. Recognize when `@Async` actually hands execution off to an executor, and when the annotation is not intercepted.
3. Distinguish `new` **outside the container** from `new` **inside a `@Bean` method**: both invoke a Java constructor, yet only the second case is registered as a Spring bean.
4. Write constructor injection properly, avoiding manual `new` for services that have dependencies and interceptors.
5. Understand self-invocation, proxy types, method visibility, scopes, and lifecycle.
6. Verify practically with a Java 17+ program running Spring Framework, thread names, proxy detection, and coordinated tests.
7. Choose designs that avoid sharing unsafe mutable state when a Spring singleton is invoked concurrently.

**Scope:** bean management, call paths, and their impact on `@Async`. Examples of `@Transactional`, caching, and scopes serve only to compare mechanisms; they do not replace dedicated lessons on those annotations.

## 2. A Java Object Is Not Automatically a Spring Bean

In Java:

```java
ReportService service = new ReportService();
service.process();
```

Calling `new`:

- Allocates the object under Java semantics and runs the appropriate constructor.
- Does not automatically ask `ApplicationContext` to create/register the object.
- Does not automatically trigger `@Autowired` on fields/setters, `BeanPostProcessor`, init/destroy callbacks, or Spring AOP proxies for the newly created instance.
- Does not automatically read `@Async`, `@Transactional`, or `@Cacheable` and alter method dispatch.
- Ownership of the object's lifecycle, resources, and dependencies belongs to the code that created it and holds its reference.

Conversely, a Spring bean exists through a **bean definition**, which may come from `@Component`/`@Service` and component scanning, `@Bean` in a configuration class, XML, programmatic registration, or Spring Boot auto-configuration. The container is responsible for creating or obtaining the object, resolving dependencies, handling lifecycle, and applying bean post-processors/advice when appropriate.

Example of receiving a bean via constructor injection:

```java
@Service
public class ReportControllerFacade {
    private final ReportService reportService;

    public ReportControllerFacade(ReportService reportService) {
        this.reportService = reportService;
    }

    public void requestReport() {
        reportService.process();
    }
}
```

This is an illustrative fragment: it requires importing Spring annotations and a project with a `ReportService` bean. `ReportControllerFacade` must be Spring-managed so that Spring resolves the constructor dependency automatically. In modern Spring, a class with a **single constructor** usually does not need `@Autowired` on that constructor.

**What matters is not where the `new` keyword appears in source code**, but whether the container **adopts the object as a bean**, applies configuration steps, and returns the corresponding reference to callers.

### 2.1. Three Cases to Distinguish

| How Created / Obtained | Is the Object Spring-Managed? | Does Spring Have an Opportunity to Inject / Apply Post-Processors / Proxy? |
| --- | --- | --- |
| `new ReportService()` inside a business method | No, unless special registration/integration is performed | Not automatically |
| `@Bean ReportService reportService() { return new ReportService(); }` | Yes, the factory method's result is registered as a bean | Yes, depending on configuration and eligibility |
| `@Service class ReportService` injected via constructor | Yes, when the class is scanned/registered | Yes, depending on configuration and eligibility |
| `context.getBean(ReportService.class)` | Yes, retrieves a bean reference from the container | Yes, though it may return a proxy or target depending on configuration |
| `new ReportService(dependency)` with an injected dependency | The **new object** does not thereby become a bean | Only the passed dependency may be a bean; the new instance is not automatically post-processed |
| `ObjectProvider<ReportService>.getObject()` | Yes, asks the container to resolve a bean | According to scope and active post-processors |

In real applications, **not every bean is proxied**. A simple bean without any matching advisor may be injected as the actual object. Conversely, when `@Async`, `@Transactional`, or another advisor is eligible, the reference provided by the container may be a proxy. Do not treat "bean = proxy" as an absolute equivalence.

### 2.2. Call Path Diagram

```text
                Manual object creation
Caller ----------> new ReportService()
                      |
                      +-- calls process() directly
                      +-- @Async is only annotation metadata
                      +-- no Spring async interceptor

                  Spring-managed bean
ApplicationContext -- bean definition --> creates target / injects / initializes
                                            |
                                            +-- BeanPostProcessor/AOP when applicable
                                            |
                                            +-- proxy or reference returned by container
                                                       |
Caller / other bean ------ constructor injection ------+
                                                       |
                                              @Async interceptor
                                                       |
                                                TaskExecutor
                                                       |
                                                worker thread
                                                       |
                                                  target.process()
```

The second diagram depicts the **case where async advice is present and the call goes through the proxy**. If async configuration is not enabled, the method is ineligible, or the caller bypasses the proxy, the interceptor will not appear on the execution path.

## 3. Why Does @Async Change a Bean's Behavior, but Not a new Object's?

With `@EnableAsync`, the Framework registers the `@Async` processing infrastructure. In the default `AdviceMode.PROXY` mode:

1. Spring identifies beans/methods that have applicable async advice.
2. When needed, the bean is exposed through a configured proxy.
3. The caller invokes the method **through the proxy reference**.
4. The interceptor selects an `Executor`/`TaskExecutor` and submits the actual call as a task.
5. A worker thread runs the target method; the caller may receive a `Future`/`CompletableFuture` to observe the result.

If the code calls:

```java
ReportService service = new ReportService();
service.generateAsync();
```

then `service` is just an ordinary Java object. Spring does not insert a proxy into that call; `generateAsync()` runs like a normal method on the calling thread, unless **the implementation itself** creates a thread or submits to some executor.

This does not mean every ordinary object always runs synchronously; an object instantiated with `new` can still use `ExecutorService` or `CompletableFuture.supplyAsync(...)` in plain Java code. **Key distinction:** asynchrony decided by the implementation itself differs from **Spring's async advice** via `@Async`.

### 3.1. Three Minimum Conditions for an @Async Call

- **Annotation processing is enabled:** `@EnableAsync` is loaded in the right Spring application context, or an equivalent configuration is present.
- **The object and method are eligible:** the service is a Spring-managed bean and the method has `@Async` in a place the framework recognizes.
- **The call goes through the advice:** typically a call from another bean to the **proxy**, not an internal `this.method()` call.

A solid production system also needs a properly configured executor, error handling, result handling, timeouts, resource management, and lifecycle management. Meeting those three conditions is only a starting point, not a guarantee of thread safety.

### 3.2. Putting @Async on a Method Does Not Mean the Java Compiler Rewrites Method Calls

`@Async` is metadata processed by Spring through its infrastructure. The Java compiler does not automatically rewrite:

```java
service.generateAsync();
```

into an `executor.submit(...)` regardless of how `service` was created. Runtime interception is what makes the difference. That is why unit tests directly using `new` may fail to reproduce the behavior when the application runs with a Spring context.

## 4. Complete Java 17+ Example: Comparing new, getBean, and Constructor Injection

This hands-on example uses **plain Spring Framework**, without Spring Boot, to prove that the container/proxy is the decisive factor.

### 4.1. Project Structure

```text
new-vs-injected-demo/
├── pom.xml
└── src/main/java/demo/NewVsInjectedDemo.java
```

Uses JDK 17+ and Maven, with `spring-context` 6.2.14.

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>new-vs-injected-demo</artifactId>
    <version>1.0.0</version>
    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.14</version>
        </dependency>
    </dependencies>
</project>
```

File `src/main/java/demo/NewVsInjectedDemo.java`:

```java
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

public class NewVsInjectedDemo {
    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AppConfig {
        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor pool = new ThreadPoolTaskExecutor();
            pool.setThreadNamePrefix("lesson-worker-");
            pool.setCorePoolSize(2);
            pool.setMaxPoolSize(4);
            pool.setQueueCapacity(16);
            return pool;
        }

        @Bean
        public Worker worker() {
            return new Worker(); // "new" inside @Bean: Spring manages the result
        }

        @Bean
        public Caller caller(Worker worker) {
            return new Caller(worker); // worker resolved by Spring
        }
    }

    public static class Worker {
        @Async("lessonExecutor")
        public CompletableFuture<String> currentThreadName() {
            return CompletableFuture.completedFuture(
                    Thread.currentThread().getName());
        }

        public CompletableFuture<String> selfInvocation() {
            return this.currentThreadName(); // Bypasses proxy on internal call
        }
    }

    public static class Caller {
        private final Worker worker;

        public Caller(Worker worker) {
            this.worker = worker;
        }

        public CompletableFuture<String> viaInjection() {
            return worker.currentThreadName();
        }
    }

    public static void main(String[] args) throws Exception {
        String callerThread = Thread.currentThread().getName();

        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {
            Worker raw = new Worker();
            Worker managed = context.getBean(Worker.class);
            Caller caller = context.getBean(Caller.class);

            String directThread = raw.currentThreadName()
                    .get(5, TimeUnit.SECONDS);
            String managedThread = managed.currentThreadName()
                    .get(5, TimeUnit.SECONDS);
            String injectedThread = caller.viaInjection()
                    .get(5, TimeUnit.SECONDS);
            String selfThread = managed.selfInvocation()
                    .get(5, TimeUnit.SECONDS);

            System.out.println("new-on-caller="
                    + directThread.equals(callerThread));
            System.out.println("managed-on-executor="
                    + managedThread.startsWith("lesson-worker-"));
            System.out.println("injected-on-executor="
                    + injectedThread.startsWith("lesson-worker-"));
            System.out.println("self-on-caller="
                    + selfThread.equals(callerThread));
            System.out.println("managed-is-proxy="
                    + AopUtils.isAopProxy(managed));
            System.out.println("distinct-object=" + (raw != managed));
        }
    }
}
```

Compile and run in the directory containing the POM:

```bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.NewVsInjectedDemo
```

Six lines produced by `System.out.println`, when the environment loads and is configured as in the example:

```text
new-on-caller=true
managed-on-executor=true
injected-on-executor=true
self-on-caller=true
managed-is-proxy=true
distinct-object=true
```

Maven may write separate logs. The result checks **thread names and proxy status** rather than depending on an assumption that the worker must be slower than the caller.

### 4.2. Exact Explanation of the Six Results

**(1) `new-on-caller=true`**

`raw = new Worker()` creates the object manually outside the container. It has a method annotated with `@Async`, but it has not been wrapped by Spring in an async proxy. Therefore, the method runs on the caller thread and returns `CompletableFuture.completedFuture(...)` right within the call.

**(2) `managed-on-executor=true`**

`managed = context.getBean(Worker.class)` is a reference provided by Spring. Because the context loads `@EnableAsync` and the `public` method has `@Async("lessonExecutor")`, calls through this reference are intercepted; the target method executes on a thread with the prefix `lesson-worker-`.

**(3) `injected-on-executor=true`**

`Caller` is a bean created by `@Bean`, and the `Worker worker` parameter in the factory method is resolved by Spring. It receives the appropriate proxy reference and calls `worker.currentThreadName()`, so the async advice still applies.

**(4) `self-on-caller=true`**

`managed.selfInvocation()` does not have `@Async`. The proxy forwards this call to the target; inside the target, `this.currentThreadName()` invokes the method directly on `this`, bypassing the proxy; the annotation on the target method is not intercepted.

**(5) `managed-is-proxy=true`**

`AopUtils.isAopProxy(managed)` checks a runtime indicator. In this specific example, the async annotation causes Spring to provide a proxy. In another application, a bean might **not** have a proxy, or a proxy might exist due to a different advice. A single `true` result does not prove all calls pass through the async interceptor.

**(6) `distinct-object=true`**

`raw` and the bean provided by the context are two distinct references. They do not share a lifecycle or dependency injection simply because they have the same `Worker` type.

### 4.3. Why Is return new Worker() Inside @Bean Different?

This is the most important point:

```java
@Bean
Worker worker() {
    return new Worker();
}
```

Spring calls the factory method to **create a bean according to the bean definition**. After receiving the object, the container can inject properties, invoke initialization callbacks, and apply `BeanPostProcessor`s to return the **final bean reference**, which may be an AOP proxy. `new` inside the method is merely an allocation step; it does not determine whether the object subsequently becomes a bean.

Meanwhile:

```java
void businessMethod() {
    Worker worker = new Worker();
    worker.currentThreadName();
}
```

has no bean definition or bean registration for the `worker` variable, so Spring does not intercept that call automatically.

Do not conclude "never use `new` in Spring." Spring itself can invoke constructors or factories to create beans. The right question is: **has the container taken ownership of managing the instance, and is the reference held by the caller the reference supplied by Spring?**

## 5. Constructor Injection, @Autowired, and Uninjected Objects

### 5.1. Constructor Injection: The Default Choice for Required Dependencies

Spring fragment (each public class placed in its respective file):

```java
@Service
public class InvoiceFacade {
    private final BillingWorker worker;

    public InvoiceFacade(BillingWorker worker) {
        this.worker = worker;
    }

    public CompletableFuture<String> invoice(String id) {
        return worker.generate(id);
    }
}

@Service
public class BillingWorker {
    @Async("billingExecutor")
    public CompletableFuture<String> generate(String id) {
        return CompletableFuture.completedFuture("invoice:" + id);
    }
}
```

Assuming `@EnableAsync`, a `billingExecutor` bean, and imports for `@Service`/`@Async`/`CompletableFuture`. When `InvoiceFacade` is created by Spring, `BillingWorker` is resolved via DI. If `BillingWorker` has a suitable proxy, the `worker` field in the facade typically holds that proxy reference. Calls from the facade to the worker pass through async interception.

Conversely:

```java
public CompletableFuture<String> invoice(String id) {
    BillingWorker worker = new BillingWorker();
    return worker.generate(id);
}
```

is a **counterexample fragment**: the service is instantiated manually and does not have a Spring proxy applied. The method is called synchronously if the implementation simply returns `completedFuture` as in the example.

One nuance: you *can* pass an injected dependency into the constructor of a `new` object in plain Java. However, doing so only supplies the dependency—it does **not** turn the new object into a Spring-managed and proxied bean.

### 5.2. Why Do @Autowired Fields on new Objects Easily Become null?

Consider this fragment:

```java
@Service
class NotificationService {
    @Autowired
    private MailGateway gateway;

    void send(String id) {
        gateway.send(id);
    }
}
```

If `NotificationService` is created by Spring and the `MailGateway` bean is resolved, injection can succeed. If code calls `new NotificationService()` itself, `gateway` keeps its default value `null` unless you intervene manually; calling `send` can cause a `NullPointerException`.

That is one reason to prefer constructor injection:

```java
@Service
class NotificationService {
    private final MailGateway gateway;

    NotificationService(MailGateway gateway) {
        this.gateway = gateway;
    }

    void send(String id) {
        gateway.send(id);
    }
}
```

The constructor forces callers to supply a valid dependency; in a Spring application, the container resolves the `MailGateway` bean and passes it in. If you want to unit test with `new NotificationService(fakeGateway)`, that is completely valid: it tests Java logic directly, though you should **not** infer from that test that AOP async/transaction behavior works.

### 5.3. @Autowired Does Not Replace @Bean or Component Scanning

`@Autowired` is an instruction to **resolve dependencies** when Spring creates/manages a bean. It does not automatically discover every object with annotated fields across the entire JVM.

- `@Service`/`@Component` marks a class so component scanning can register a bean.
- `@Bean` defines a bean from a factory method when a configuration class is loaded.
- `@Autowired`, constructor parameters, and `@Qualifier` indicate dependencies to resolve at injection points.
- `@EnableAsync` turns on async infrastructure; `@Async` marks where interception is needed.

If a class has `@Service` but sits outside component scan or is not imported/registered, the annotation alone is not enough to guarantee a bean exists. If a class is instantiated with `new` in business code, having the annotation does not automatically make Spring manage that object.

## 6. Spring Proxies: Injection May Yield a Proxy, but Not Always

### 6.1. JDK Dynamic Proxies and Class-Based Proxies

Spring AOP typically uses:

| Proxy Strategy | Principle | Consequence When Injecting |
| --- | --- | --- |
| JDK dynamic proxy | The proxy implements the required interface(s) | Should inject via the interface; cannot necessarily be cast to the concrete class |
| Class-based proxy (CGLIB) | The proxy creates a subclass of the target class | Can inject via an eligible concrete class; `final` classes/methods cannot be advised via subclassing |
| No proxy | No advice applies, or infrastructure is not enabled | Spring can still inject the target bean normally, but methods have no AOP interception |

The default proxy type depends on Framework/Boot configuration, bean interfaces, advisors, and versions. Do not hard-code assumptions on `bean.getClass() == Worker.class`: the runtime class may be a generated proxy class.

**Important limitations with class-based proxies:**

- A `final` class cannot be subclassed to create this proxy type.
- A `final` method cannot be overridden to apply advice.
- A `private` method cannot be advised via the overriding mechanism.
- Methods without suitable visibility can face similar limitations.
- `static` methods are not instance calls going through a Spring proxy.

A straightforward, verifiable rule for `@Async`: put `public` methods on a Spring-managed service, avoid `final`, and call them through another bean.

### 6.2. Interface Injection Example

Fragment:

```java
public interface ExportPort {
    CompletableFuture<String> export(String id);
}

@Service
class ExportService implements ExportPort {
    @Async("exportExecutor")
    public CompletableFuture<String> export(String id) {
        return CompletableFuture.completedFuture(id);
    }
}

@Service
class ExportControllerFacade {
    private final ExportPort exportPort;

    ExportControllerFacade(ExportPort exportPort) {
        this.exportPort = exportPort;
    }

    CompletableFuture<String> run(String id) {
        return exportPort.export(id);
    }
}
```

This is a Spring project fragment with appropriate imports and executor bean; it will not run standalone with `javac` alone. Injecting by `ExportPort` decouples code from the concrete proxy type. If you want concrete-class injection, you must verify the proxy strategy and class compatibility rather than casting from a JDK proxy.

### 6.3. How to Tell Whether a Proxy Exists

In a Spring test where the bean exists:

```java
import org.springframework.aop.support.AopUtils;

Object bean = context.getBean("exportService");

System.out.println(AopUtils.isAopProxy(bean));
System.out.println(bean.getClass().getName());
```

This fragment requires an appropriate `context`. Using `AopUtils.isAopProxy` and inspecting the bean class name is a diagnostic step, **not** sufficient to confirm which specific method is being advised. Verify annotations, call paths, and actual thread names/runtime results.

## 7. Distinguishing Unmanaged Instances from Self-Invocation

An object manually instantiated in business code and a Spring-managed bean calling its own method can both bypass `@Async`, yet **they are two independent causes**:

| Situation | Why Is There No Async Advice? | Fix |
| --- | --- | --- |
| `new ExportWorker().exportAsync(id)` in business code | This instance is not registered, post-processed, or exposed via a proxy by Spring. | Inject the `ExportWorker` bean or retrieve a managed bean via a provider/factory. |
| `this.exportAsync(id)` inside a target that is already a Spring bean | The internal call does not pass through the proxy of the method needing advice. | Call from a collaborating bean through a Spring-managed reference or use an explicit executor. |

Example of a container-managed bean still suffering from self-invocation:

```java
@Service
class CsvExportService {
    public void start(String id) {
        this.exportAsync(id); // Direct call inside target in PROXY mode.
    }

    @Async("exportExecutor")
    public void exportAsync(String id) {
        // Task runs on the executor when called through the proxy.
    }
}
```

This snippet is a Spring fragment, requiring imports, `@EnableAsync`, and the `exportExecutor` bean. If `start()` is called through the proxy, the internal `this.exportAsync()` call still does not turn into a new submission. Adding threads or changing bean scope will not fix the bug. The focus of this lesson is **instance origin and ownership**, whereas the previous lesson analyzed self-calls and exception semantics in depth.

## 8. Bean Scope: Spring Managing an Object Does Not Mean Every Call Gets a New Instance

Do not infer from "injected" to "one object per request" or "no shared mutable state." Scope is independent of whether a proxy exists and of calling `new`.

| Scope | General Behavior | Key Point Under Concurrency |
| --- | --- | --- |
| `singleton` (default) | Typically one instance per bean definition in a container | Multiple requests/workers can access the same state; Spring does not automatically lock mutable fields |
| `prototype` | Creates an instance when the container is asked to supply the bean | A prototype injected **once** into a singleton does not automatically change instances per method call |
| `request` | Instance tied to request lifecycle in a web-aware context | Should not retain request beans/references for background processing after the request |
| `session` | Instance tied to an HTTP session | One session can have concurrent requests; mutable state still needs control |
| Custom scope | Defined by application/container | Must understand exact lifetime, owner, and thread safety |

**Counterintuitive example:** a singleton facade's constructor takes `@Scope("prototype") Worker worker`. The prototype worker is typically resolved when the facade is created; the facade keeps that reference, rather than receiving a fresh worker on every `facade.process()` call.

If you truly want to request a prototype bean per invocation, use `ObjectProvider<Worker>` or an appropriate factory/lookup:

```java
@Service
class TaskStarter {
    private final ObjectProvider<Worker> workers;

    TaskStarter(ObjectProvider<Worker> workers) {
        this.workers = workers;
    }

    void start() {
        Worker worker = workers.getObject();
        worker.execute();
    }
}
```

This is a fragment, requiring a `Worker` bean and imports. If `execute()` needs `@Async`, ensure the prototype bean is appropriately post-processed/proxied by Spring; merely changing scope does not solve self-invocation. Spring's destruction handling for prototype beans also has limits: Spring manages creation/init, yet the container typically **does not manage all destruction callbacks** for issued prototype instances as it does for singletons; callers must clean up long-lived resources themselves when needed.

### 8.1. Why Can an @Async Singleton Cause a Race Condition?

A singleton `@Service` with a field:

```java
@Service
class LastOrderService {
    private String lastOrderId;

    @Async("orderExecutor")
    public CompletableFuture<String> record(String id) {
        lastOrderId = id;
        return CompletableFuture.completedFuture(lastOrderId);
    }
}
```

If multiple tasks run concurrently on the same singleton, `lastOrderId` is shared mutable state that can be overwritten between two tasks. Even with a proxy, `@Async` does not automatically make fields thread-safe. Use immutable commands/DTOs, local variables, and per-invocation results; if shared state is required, design atomicity/locking and ownership appropriately.

Creating `new LastOrderService()` per request might accidentally reduce field sharing in this example, yet it is **not** a sensible solution to dodge concurrency: it bypasses DI, AOP, lifecycle, and may still share dependencies/static state. The proper fix is designing state and responsibility boundaries.

## 9. @Transactional, @Cacheable, and Other Advice: Same Principle, Different Semantics

The difference between `new` and an injected bean does not only affect `@Async`.

| Spring Capability | When Called Through an Eligible Bean/Proxy | When Called on a Plain new Object |
| --- | --- | --- |
| `@Async` | Interceptor can submit method to an executor | Does not switch threads automatically |
| `@Transactional` (proxy mode) | Interceptor can open/attach a transaction with matching semantics | Annotation does not open a transaction automatically |
| `@Cacheable` (proxy mode) | Advice can check/cache the return value | Annotation does not cache automatically |
| Custom `@Aspect` | Matching advice can run before/after/around the method | Not intercepted unless another mechanism is applied |
| DI `@Autowired` | Container can resolve dependencies | Not injected automatically |
| Lifecycle callbacks | Can run when the bean initializes/closes under applicable conditions | Not invoked automatically by Spring |

This is the **typical proxy-based model**. Some capabilities can use AspectJ weaving or another technique, and Spring provides special mechanisms to autowire/configure objects outside the container when an application intentionally sets them up. Do not conclude from advanced exceptions that every `new` object is treated by Spring as a bean.

### 9.1. @Transactional Does Not Automatically Follow @Async Across Threads

Suppose a caller has an active transaction and invokes an `@Async` method on an injected bean: the worker typically runs on a **different thread**. The caller's thread-bound transaction context does not automatically travel with it. If the worker needs a transaction, place an explicit transaction boundary on the code running in the worker and invoke it through an appropriate proxy. Furthermore, the task may execute after the caller's transaction has already finished.

Do not explain this situation as "caused by using `new`" when the error actually originates from a **thread boundary**. Distinguish clearly:

1. Not Spring-managed → no async advice.
2. Async advice active → code runs on a worker; the caller thread's transaction context does not flow across automatically.
3. Inside the worker, a `this.transactionalMethod()` call can still bypass the transaction proxy if it is a self-invocation.

### 9.2. Spring Should Not Be Used as a Service Locator Everywhere

Turning every `new` into `applicationContext.getBean(...)` in business code generally reduces the clarity of the dependency graph. Prefer constructor injection with typed interfaces, and use `ObjectProvider`/factories only when you genuinely need runtime bean lookup or repeated prototype retrieval.

## 10. Special Situations with @Bean, @Configuration, and new

### 10.1. Returning new Inside @Bean Is **Not** an Error

```java
@Configuration(proxyBeanMethods = false)
class TaskConfig {
    @Bean
    NotificationWorker notificationWorker(MailClient mailClient) {
        return new NotificationWorker(mailClient);
    }
}
```

Spring invokes `notificationWorker(...)` and registers the returned object under a bean definition. It receives constructor dependencies from the container, and then appropriate lifecycle/post-processing steps are applied. `new` here is simply a factory method implementation detail, not business code creating a service outside Spring.

### 10.2. Yet Calling a @Bean Method Directly Does Not Necessarily Yield a Managed Bean

With configuration in `proxyBeanMethods=false` mode, a direct Java call from one method to another `@Bean` method is **not** intercepted by Spring to return the container-managed singleton. Anti-pattern example:

```java
@Configuration(proxyBeanMethods = false)
class WrongFactoryConfig {
    @Bean
    Worker worker() {
        return new Worker();
    }

    @Bean
    Caller caller() {
        return new Caller(worker()); // Direct Java call to @Bean method
    }
}
```

In this case, `Caller` may hold a `Worker` created during the direct method call rather than the bean reference that the container post-processed/proxied. Having `@Bean` on `worker()` does not turn **every direct call to that method** into a container lookup.

**Better** is to ask Spring to inject the parameter:

```java
@Configuration(proxyBeanMethods = false)
class GoodFactoryConfig {
    @Bean
    Worker worker() {
        return new Worker();
    }

    @Bean
    Caller caller(Worker worker) {
        return new Caller(worker);
    }
}
```

These snippets are fragments and assume matching `Worker` and `Caller` classes exist. When using `@Configuration(proxyBeanMethods=true)` (full configuration), Spring has a mechanism to intercept certain inter-bean method calls to return the container bean; however, it depends on enhancement mechanics and coding style. **Constructor/method parameter injection** remains clearer, especially when moving classes to lite/`proxyBeanMethods=false` mode.

### 10.3. @ComponentScan Does Not Turn Already-Created Objects into Beans

`@ComponentScan` scans classes to register bean definitions. If inside a method you write `new ComponentClass()`, that individual object is not "picked up" into the container after scanning, even though it shares the same class as a registered bean.

### 10.4. Prototype Beans and new Objects Are Not Synonymous

Both prototype lookup and `new` can produce fresh instances, yet they differ in that a **prototype is still created and post-processed by the container**, whereas a plain `new` is not. If a worker needs a proxy/lifecycle, request a prototype from the container instead of substituting `new` arbitrarily.

## 11. Spring Boot Does Not Automatically Fix Wrong Call Paths

Spring Boot adds auto-configuration and conventions, yet it does not change the Spring Framework container/proxy principles:

- `@SpringBootApplication` typically enables component scanning and auto-configuration within the appropriate scope; classes outside the scan may not be registered.
- Boot may conditionally create an executor, yet `@EnableAsync` is still required for annotation processing to run in typical configurations.
- Having an executor bean does not turn `new Worker()` into a managed bean.
- Having `@EnableAsync` does not route `this.work()` self-invocation through a proxy.
- Having `@Service` on a class while code directly calls `new Service()` still produces a separate instance outside the container.

Boot fragment example:

```java
@SpringBootApplication
@EnableAsync
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}

@Service
class DocumentWorker {
    @Async("documentExecutor")
    public CompletableFuture<String> parse(String id) {
        return CompletableFuture.completedFuture("parsed:" + id);
    }
}

@Service
class DocumentFacade {
    private final DocumentWorker worker;

    DocumentFacade(DocumentWorker worker) {
        this.worker = worker;
    }

    CompletableFuture<String> request(String id) {
        return worker.parse(id);
    }
}
```

This is a structural example, **not a standalone program**, as it requires a `documentExecutor` bean definition, imports, and a Spring Boot project. It illustrates the path `DocumentFacade → injected DocumentWorker → async proxy`. If you replace `worker` with `new DocumentWorker()`, code calling the exact same method name is no longer intercepted by Spring `@Async`.

To know which pool executes it, inspect `@Async("documentExecutor")`, the `Executor` bean type, the Spring context status, and thread names. Do not assume a custom bean automatically picks up Boot's `spring.task.execution.*` properties.

## 12. When Is Using new the Right Choice?

Using `new` is completely normal for **value objects, DTOs, collections, domain models, and pure Java algorithms**, when you **do not need** the container to manage that object:

```java
record ExportCommand(String requestId, String path) {}

ExportCommand command =
        new ExportCommand("R-123", "/reports/summary.csv");
List<String> lines = new ArrayList<>();
```

This is a fragment with the necessary Java imports. These short-lived data objects do not automatically need `@Component` or `@Service`. Injecting every DTO into the Spring container usually makes identity, state, and scope harder to manage.

**You should inject a Spring bean** when the object:

- Holds a shared business service with multiple dependencies needing DI.
- Needs AOP advice such as `@Async`, `@Transactional`, or `@Cacheable`.
- Holds resources requiring container lifecycle management (executors, datasources, configured clients, schedulers).
- Needs centralized configuration, implementation swapping via interfaces, scope management, or metrics integration.
- Needs unified ownership and Spring integration testing.

**No need to inject** merely because "there is a Java class." A plain object can be instantiated with `new` inside a Spring-managed service; the Spring service remains a bean while the DTO it creates remains an ordinary object. That is a completely valid design.

### 12.1. A Factory Creating Domain Objects Can Be a Bean

You can inject a factory bean that holds dependencies/configuration, while the objects produced by the factory remain normal domain objects:

```java
@Component
class ExportCommandFactory {
    ExportCommand create(String id, String path) {
        return new ExportCommand(id, path);
    }
}
```

This fragment shows that not every object created by a bean becomes a bean. **Spring manages the factory**, not each individual `ExportCommand` by default.

## 13. Verifying with Tests: Unit Tests Differ from Integration Tests

### 13.1. Unit Tests for Java Logic

If you instantiate a service with `new` and pass mock/fake dependencies yourself, you are testing method logic. This is a valid, fast, and easily controlled test. However, a passing assertion in that unit test **does not prove `@Async`, transaction advice, or bean lifecycle are active**, because there is no corresponding container/proxy.

Example with a plain method:

```java
var worker = new BillingWorker();
var result = worker.generate("INV-1").join();

// Checks business result logic, not Spring async advice.
assertEquals("invoice:INV-1", result);
```

This is a JUnit fragment, assuming `BillingWorker` can be constructed with a no-arg constructor as in the earlier example and JUnit is imported. If the worker requires mandatory dependencies, supply fakes/mocks via its constructor rather than bypassing the object's contract.

### 13.2. Integration Tests Must Use a Spring Context

For tests verifying AOP:

1. Load configuration containing `@EnableAsync` and executor beans.
2. Inject the service from Spring; do not `new` it in the test.
3. Verify the received reference has a proxy when you expect advice.
4. Invoke the method via the bean from the context/another bean.
5. Verify the target thread name, future result, exception, and timeout.
6. Instantiate a `new` object as a control group to demonstrate the different execution paths.
7. Test self-invocation: a method inside the target runs on the caller even when the outer bean is injected.
8. Close the context to verify executor lifecycle and timely resource shutdown.

### 13.3. Avoid Timing Tests with Thread.sleep

Use `CountDownLatch` to coordinate events instead of calling `Thread.sleep(50)` and hoping the worker has not finished yet:

```java
// Illustrative fragment inside an @Async method called through the proxy:
started.countDown();
release.await();
return CompletableFuture.completedFuture("finished");
```

The caller can wait on `started.await(timeout, unit)`, verify the task has not completed yet, then call `release.countDown()` and await the future. Handle `InterruptedException`, use timeouts so tests do not hang, and ensure latches are released in `finally`.

A stress test can help uncover races, yet it does **not** replace understanding bean scopes, state ownership, and thread boundaries.

## 14. Debugging an @Async Method That "Does Not Run Async"

Answer these in order instead of guessing pool settings:

1. **Where did the instance come from?** Trace `new`, `@Bean`, `@Service`, constructor injection, `getBean`, or factories.
2. **Does the context manage the instance?** Is there an actual bean definition and was the object supplied by Spring? Where was the object manually recreated?
3. **Does the bean have a proxy?** Check `AopUtils.isAopProxy(...)` and the proxy type (JDK/interface or class-based) as applicable.
4. **Is async infrastructure enabled?** Is `@EnableAsync` loaded in the right context?
5. **Is the method eligible?** Where is `@Async` placed (method/class); is the method `public`/non-`final`? Is the return type `void`/`Future`/`CompletableFuture`?
6. **Which reference is the call made through?** A reference from DI/proxy or `this`? Is there reflection, a private helper, or manual instantiation?
7. **Which executor is selected?** `@Async("...")`, `AsyncConfigurer`, default resolver, bean name, prefix.
8. **Is the task being rejected or stopped?** Are the pool/queue bounded? Is the executor still alive?
9. **Which thread does the task actually run on?** Print caller and worker thread names; do not infer merely from having a `CompletableFuture`.
10. **If using Spring Boot:** which beans are auto-configured by Boot vs declared by you; do properties bind to the right executor?
11. **If the problem is wrong data:** check singleton shared mutable state, context propagation, and transaction boundaries—not only the proxy.
12. **If the problem is shutdown:** inspect executor ownership, queued tasks, and the graceful shutdown strategy.

Quick table:

| Symptom | Possible Cause | How to Verify |
| --- | --- | --- |
| Service created with `new` runs `@Async` synchronously | No Spring interception | Compare against injected bean, check threads |
| Async method runs synchronously within the same bean | Self-invocation | Draw call graph, split bean, retest |
| `@Autowired` field is null | Instance created outside the container | Find the `new` site; use constructor injection |
| `@Transactional` does not open a transaction | Did not pass through proxy or missing infrastructure | Verify bean, advice, and call path |
| Injecting bean by concrete class fails | JDK dynamic proxy only exposes interface(s) | Inject interface, check proxy strategy |
| Bean injects fine, yet has no proxy | Advisor did not apply or infrastructure not enabled | `AopUtils`, annotations, conditions/config |
| `@Async("pool")` cannot find executor | Wrong bean name/qualifier or bean not registered | List `Executor` beans in the context |
| Unit test using `new` passes, yet runtime behaves differently | Unit test bypasses AOP/lifecycle | Add a Spring context integration test |
| One request sees another request's data | Mutable field in singleton/shared dependency | Change state to local/immutable or synchronize properly |
| Increasing thread count does not speed things up | Queue/backpressure/downstream bottleneck | Measure active/queue/rejection/latency metrics |

## 15. Integration Exercises: Identify Who Manages Each Object

### Exercise 1: Classify Six References

Given the following fragments in an application with `@EnableAsync` enabled:

```java
Worker a = new Worker();
Worker b = context.getBean(Worker.class);
Worker c = injectedWorker;
Worker d = factory.createWorker();
Worker e = provider.getObject();
Worker f = new Worker(injectedDependency);
```

For each variable, note: **creation source**, **container-managed?**, **could it be a proxy?**, **will `@Async` apply if a method is called through that reference?**, **who manages the lifecycle?**. For `d`, do not guess: read the factory's implementation to see whether it uses `new` or the Spring container. For `e`, know which bean `ObjectProvider` retrieves and what its bean scope is. For `f`, the fact that the dependency is a bean does not automatically make `f` a bean.

### Exercise 2: Fix Proxy Bypass

Refactor:

```java
@Service
class ExportFacade {
    public void start(String id) {
        ExportWorker worker = new ExportWorker();
        worker.exportAsync(id);
    }
}
```

into a facade that constructor-injects `ExportWorker` and calls `worker.exportAsync(id)`; enable `@EnableAsync` and provide an executor bean. Explain why this change **only** solves one problem: you still need to check actual proxy invocation, result/error handling, and thread safety.

### Exercise 3: Self-Invocation

Add a `startInternal()` method to `ExportWorker` and have it call `this.exportAsync(id)`. Record the executing thread. Move `startInternal()` into a separate facade bean and repeat. Compare why both cases use a Spring-created bean yet only the call from the facade goes through the proxy.

### Exercise 4: @Bean with new

Write two configuration versions:

1. `@Bean Worker worker() { return new Worker(); }`, then `@Bean Caller caller(Worker worker) { return new Caller(worker); }`.
2. With `proxyBeanMethods=false`, `@Bean Caller caller() { return new Caller(worker()); }`.

Observe the injected object, proxy status, and `@Async` behavior. Explain why factory methods should only obtain bean dependencies via parameters to avoid bypassing the container.

### Exercise 5: Concurrency and Scope

Create a singleton `@Service` with a mutable field `lastRequestId`, make two `@Async` calls write different values to the field, and use a coordinating latch to prove results can mix. Fix it using a stateless/immutable input approach rather than merely replacing it with `new` or `prototype`. Clarify who owns the state and when a request ends.

### Exercise 6: Control-Group Testing

Create a unit test using `new Worker()` and an integration test loading a Spring context. Both tests check business output; the integration test additionally checks `AopUtils.isAopProxy` and the thread prefix when invoked through the bean. Explain why the unit test is not proof of async advice.

## 16. Knowledge Checklist Before Moving to the Next Lesson

- [ ] I can explain why `new Service()` outside the container does not automatically receive Spring DI/AOP.
- [ ] I can distinguish `new` inside a `@Bean` method from `new` inside a business method.
- [ ] I know `@Service` only produces a bean when the class is actually scanned/registered.
- [ ] I know constructor injection supplies a bean reference, which may be a Spring AOP proxy.
- [ ] I know an injected bean does not always have a proxy, and a proxy does not mean a new instance per call.
- [ ] I can explain the conditions `@EnableAsync` + `@Async` + invocation through a proxy.
- [ ] I can distinguish manually created objects from self-invocation: two distinct causes of advice bypass.
- [ ] I understand the limitations of JDK interface proxies, class-based proxies, and `final`/`private` methods.
- [ ] I can verify behavior using `ApplicationContext`, `AopUtils`, thread names, and futures.
- [ ] I know async advice does not automatically fix race conditions, transaction contexts, or shared mutable state.
- [ ] I choose `new` for DTOs/value objects when appropriate, and inject services/resources requiring Spring management.
- [ ] I know a prototype bean still differs from a `new` instance and does not automatically change on every call from a singleton.
- [ ] I do not use Spring Boot auto-configuration as an excuse to ignore proxy call paths.
- [ ] I write dedicated Spring integration tests to verify concurrency behavior is configured properly.

**Conclusion:** `new` is Java's way of creating an object; **DI is Spring's way of providing a bean reference from the container**. The most important distinction when studying Spring concurrency is **which object the call runs on, whether that reference goes through a proxy, and which executor actually receives the task**. Once you accurately trace the path from caller → injected proxy → interceptor → executor → target, you can explain why `@Async` takes effect or does not, while avoiding confusion between bean scope, lifecycle, and thread safety.

## 17. Official References for Further Lookup

- Spring Framework — [Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html): container dependency creation/resolution and constructor injection.
- Spring Framework — [Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): bean definitions and object management.
- Spring Framework — [Proxying Mechanisms](https://docs.spring.io/spring-framework/reference/core/aop/proxying.html): JDK proxies, class-based proxies, and self-invocation.
- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, executor qualification, and exception handling.
- Spring Framework — [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype, and lifecycle.
- Spring Framework Javadoc — [@Bean](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/context/annotation/Bean.html): factory method creating a managed bean.
- Spring Framework Javadoc — [@EnableAsync](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): proxy advice mode and async configuration.

Default proxy details and auto-configuration may vary across releases. In practice, check the **exact Spring Framework/Spring Boot version of your project** rather than extrapolating from a single example.
