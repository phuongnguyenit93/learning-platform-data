# Method Self-Calls and the Self-Invocation Trap

## 1. What Is Self-Invocation?

Self-invocation occurs when a method inside an object directly calls another method on the same object, typically via `this` or an unqualified method call. In Spring, this internal call pattern can bypass behaviors applied through AOP proxies, such as `@Async`, `@Transactional`, `@Cacheable`, or other advice.

A common issue in asynchronous processing is a class having a method annotated with `@Async`, while another method in the same class calls it. The author expects Spring to offload the work to an executor, whereas the call actually goes straight to the target object and runs on the current thread.

Example:

~~~java
@Service
public class ReportService {
    public void generateReport() {
        sendEmailAsync(); // Self-invocation
    }

    @Async
    public void sendEmailAsync() {
        // Expected to send email on a background thread.
    }
}
~~~

If another bean calls `reportService.generateReport()` through the Spring proxy, `generateReport` executes. However, the `sendEmailAsync()` call inside the class is a direct invocation on the target object. The proxy never receives the second call, so the `@Async` interceptor is not triggered.

As a result, `sendEmailAsync()` runs synchronously on the thread calling `generateReport()`. The annotation is still on the method, yet the call path bypassed the proxy.

## 2. Why Can't the Proxy Intercept Internal Calls?

In default proxy mode, Spring wraps the bean in a proxy. When another bean calls a method through the proxy, the proxy can apply interceptors before forwarding the call to the target object.

You can trace it as:

1. Caller invokes `generateReport()` on the proxy.
2. The proxy forwards the call to the real `ReportService` object.
3. Code inside `generateReport` calls `this.sendEmailAsync()`.
4. The second call happens directly on the real object.
5. Execution does not pass through the proxy again, so `@Async` has no opportunity to submit the task to an executor.

Diagram:

~~~text
External calling bean
        |
        v
   Spring Proxy
        |
        v
 ReportService.generateReport()
        |
        | this.sendEmailAsync()
        v
 ReportService.sendEmailAsync()
        |
        v
 Runs on current thread
~~~

For `@Async` to take effect, the call to the async method must pass through the Spring proxy. This explains why calling a method from another bean runs asynchronously, whereas calling the same method via `this` runs synchronously.

## 3. Distinguishing the Two Call Patterns

Assuming `sendEmailAsync()` has `@Async`:

| Call Pattern | Goes through proxy on async call? | Outcome |
|---|---|---|
| Bean A calls `reportService.sendEmailAsync()` | Yes, if `reportService` is a Spring proxy | Task is submitted to executor |
| `ReportService.generateReport()` calls `this.sendEmailAsync()` | No | Method runs on current thread |
| `ReportService.generateReport()` calls another bean `emailWorker.sendEmailAsync()` | Yes, if `emailWorker` is a Spring proxy | Task is submitted to executor |
| Instantiating via `new ReportService()` and calling the method | No Spring proxy | `@Async` is not applied |

What you must verify is whether the receiving object is a Spring-managed proxy bean and whether the invocation actually passes through that proxy. Looking at the annotation on the method alone is not enough to conclude the work will run asynchronously.

## 4. Best Fix: Extract the Async Method to a Separate Bean

The clearest and easiest-to-test solution is moving the asynchronous work into another bean. The calling bean handles orchestration; the worker bean handles background execution.

Example:

~~~java
@Service
public class EmailWorker {
    @Async("taskExecutor")
    public CompletableFuture<Void> sendConfirmation(String orderId) {
        // Send email.
        return CompletableFuture.completedFuture(null);
    }
}
~~~

~~~java
@Service
public class OrderService {
    private final EmailWorker emailWorker;

    public OrderService(EmailWorker emailWorker) {
        this.emailWorker = emailWorker;
    }

    public void createOrder(String orderId) {
        // Save order and complete synchronous business steps.
        emailWorker.sendConfirmation(orderId);
    }
}
~~~

`OrderService` calls a method on the `EmailWorker` bean injected by Spring. The call traverses `EmailWorker`'s proxy, so `@Async` is activated.

This separation brings several benefits:

- Clear boundary between orchestration and background processing.
- Async calls naturally traverse the proxy.
- The worker can be tested independently.
- A dedicated executor can be assigned to the task group.
- No need to retrieve the bean's own proxy or depend on `AopContext`.

If the caller needs to wait for a result, keep the `CompletableFuture` and explicitly decide when to join or attach callbacks. If the caller does not need a result, the Future can be ignored, though background task errors must still be observed.

## 5. Using Self-Injection When Bean Extraction Is Not Yet Feasible

Another approach is injecting the bean's own proxy and invoking through that reference. For example, `@Lazy` can defer reference resolution:

~~~java
@Service
public class ReportService {
    @Autowired
    @Lazy
    private ReportService self;

    public void generateReport() {
        self.sendEmailAsync();
    }

    @Async("taskExecutor")
    public CompletableFuture<Void> sendEmailAsync() {
        // Send email.
        return CompletableFuture.completedFuture(null);
    }
}
~~~

In this example, `self` holds a reference to the proxy. When `generateReport` calls `self.sendEmailAsync()`, the call traverses the proxy and the `@Async` interceptor can run.

However, self-injection introduces a circular dependency between the bean and its own proxy. It can make configuration harder to follow, complicate bean initialization, and blur responsibility boundaries. Use it only when extracting a separate bean does not fit the current design.

If you choose this route, verify that the actual context creates the proxy properly and ensure the injected reference is the proxy, not the target object.

## 6. Using AopContext.currentProxy() in Special Cases

Spring can expose the current proxy via `AopContext.currentProxy()` if proxies are configured to expose it. This requires `exposeProxy=true` and couples code directly to Spring AOP:

~~~java
@EnableAspectJAutoProxy(exposeProxy = true)
@Configuration
class AopConfiguration {
}
~~~

~~~java
public void generateReport() {
    ((ReportService) AopContext.currentProxy()).sendEmailAsync();
}
~~~

This can work around self-invocation because the call is routed through the proxy currently handling the request. However, it makes code harder to read and test, while tightly coupling business classes to AOP infrastructure.

Prefer extracting the worker into a separate bean. Consider `AopContext` only when there is a clear architectural reason and the team accepts that coupling.

## 7. Conditions for @Async to Work

Even when a call goes through a proxy, `@Async` still requires proper setup:

**Enable async processing.** Place `@EnableAsync` on a configuration class loaded into the `ApplicationContext`.

**Spring-managed bean.** The object must be created and managed by the container. Objects created with `new` have no async proxy.

**Call through the proxy.** Callers must use the proxy bean, typically via Spring dependency injection.

**Select an executor.** Use the default executor or specify a bean explicitly with `@Async("taskExecutor")`. For production workloads, configure a bounded thread pool and an appropriate task rejection policy.

**Choose return types.** Methods may return `void`, `Future`, or `CompletableFuture`. With `void`, exceptions on the background thread do not propagate back to the caller. If results or composition across tasks are needed, use `CompletableFuture`.

Configuration example:

~~~java
@Configuration
@EnableAsync
public class AsyncConfiguration {
    @Bean(name = "taskExecutor")
    public ThreadPoolTaskExecutor taskExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(50);
        executor.setThreadNamePrefix("async-");
        return executor;
    }
}
~~~

Pool sizing must fit CPU/I/O characteristics, database limits, and external service constraints. Never raise threads or queue capacity indefinitely to mask overload.

## 8. Self-Invocation Affects @Transactional and Other Annotations Too

Self-invocation is not exclusively an `@Async` trap. Annotations backed by AOP proxies can likewise be bypassed when called directly within the same object.

Example:

~~~java
@Service
public class PaymentService {
    public void processPayment() {
        saveAuditRecord();
    }

    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAuditRecord() {
        // Intended to run in an independent transaction.
    }
}
~~~

If `processPayment` is called through the proxy while `saveAuditRecord` is called via `this`, `saveAuditRecord`'s transaction interceptor does not run. The method may continue in the existing transaction or run without a transaction, depending on the calling context.

The same applies to `@Cacheable`, `@Retryable`, and other proxy-based advice. Verify whether an annotation relies on proxies or another mechanism before assuming its runtime behavior.

For `@Transactional`, extracting operations needing a separate transaction into another bean is usually the cleanest solution:

~~~java
@Service
public class AuditService {
    @Transactional(propagation = Propagation.REQUIRES_NEW)
    public void saveAuditRecord() {
        // Write audit in a new transaction.
    }
}
~~~

~~~java
@Service
public class PaymentService {
    private final AuditService auditService;

    public PaymentService(AuditService auditService) {
        this.auditService = auditService;
    }

    public void processPayment() {
        auditService.saveAuditRecord();
    }
}
~~~

Calling through the `AuditService` proxy lets Spring apply `REQUIRES_NEW` propagation as configured.

## 9. Proxy Types and Method Restrictions

Spring AOP generally uses JDK dynamic proxies when a bean implements suitable interfaces, or class-based proxies when a concrete class must be proxied. The proxy mechanism governs which methods can be intercepted.

- With JDK dynamic proxies, callers access methods declared on the proxied interfaces.
- With class-based proxies, Spring generates a subclass of the target class; classes and methods that cannot be overridden—such as `final` classes or `final` methods—cannot be intercepted by subclass proxies.
- `private` methods are not interception points through proxies under this model.
- Self-invocation still bypasses the proxy regardless of which proxy type Spring uses.

When designing async APIs, prefer `public` methods, explicit Spring beans, and constructor-injected dependencies. That makes proxy call boundaries obvious to readers and avoids proxy-type pitfalls.

## 10. Complete Runnable Example

This example uses Java 17 and Spring Framework 6.2.0. The program invokes the same task in two ways: self-invocation within one bean, and delegation to a separate worker bean.

Expected outcome:

- Self-invocation runs on the `main` thread.
- Calling through `AsyncWorker` runs on a thread prefixed with `async-`.

Create `src/main/java/demo/SelfInvocationAsyncDemo.java`:

~~~java
package demo;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

import java.util.concurrent.CompletableFuture;

public class SelfInvocationAsyncDemo {
    public static void main(String[] args) {
        try (var context =
                 new AnnotationConfigApplicationContext(AppConfig.class)) {
            String callerThread = Thread.currentThread().getName();

            String selfThread = context
                .getBean(SelfInvokingService.class)
                .callInternally()
                .join();

            String workerThread = context
                .getBean(DelegatingService.class)
                .callThroughWorker()
                .join();

            System.out.println("Caller thread: " + callerThread);
            System.out.println("Self-invocation thread: " + selfThread);
            System.out.println("Separate-bean thread: " + workerThread);

            if (!callerThread.equals(selfThread)) {
                throw new AssertionError(
                    "Self-invocation unexpectedly used another thread"
                );
            }
            if (callerThread.equals(workerThread)) {
                throw new AssertionError(
                    "Separate bean did not execute asynchronously"
                );
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    static class AppConfig {
        @Bean(name = "taskExecutor")
        ThreadPoolTaskExecutor taskExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("async-");
            executor.setWaitForTasksToCompleteOnShutdown(true);
            executor.setAwaitTerminationSeconds(5);
            return executor;
        }

        @Bean
        SelfInvokingService selfInvokingService() {
            return new SelfInvokingService();
        }

        @Bean
        AsyncWorker asyncWorker() {
            return new AsyncWorker();
        }

        @Bean
        DelegatingService delegatingService(AsyncWorker worker) {
            return new DelegatingService(worker);
        }
    }

    public static class SelfInvokingService {
        public CompletableFuture<String> callInternally() {
            return asyncOperation();
        }

        @Async("taskExecutor")
        public CompletableFuture<String> asyncOperation() {
            return CompletableFuture.completedFuture(
                Thread.currentThread().getName()
            );
        }
    }

    public static class AsyncWorker {
        @Async("taskExecutor")
        public CompletableFuture<String> asyncOperation() {
            return CompletableFuture.completedFuture(
                Thread.currentThread().getName()
            );
        }
    }

    public static class DelegatingService {
        private final AsyncWorker worker;

        public DelegatingService(AsyncWorker worker) {
            this.worker = worker;
        }

        public CompletableFuture<String> callThroughWorker() {
            return worker.asyncOperation();
        }
    }
}
~~~

Create `pom.xml` at the project root:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>self-invocation-async-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                    <mainClass>demo.SelfInvocationAsyncDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Run in the directory containing `pom.xml`:

~~~bash
mvn -q compile exec:java
~~~

Expected stdout:

~~~text
Caller thread: main
Self-invocation thread: main
Separate-bean thread: async-1
~~~

Explanation:

1. `AnnotationConfigApplicationContext` loads `AppConfig` and enables `@EnableAsync`.
2. Spring creates proxies for `SelfInvokingService` and `AsyncWorker` because both beans have `@Async` methods.
3. `callInternally()` is invoked through the bean proxy, but inside it calls `asyncOperation()` directly on the target object. Therefore, the call bypasses the proxy and returns the `main` thread name.
4. `DelegatingService` calls `asyncOperation()` on the injected `AsyncWorker` bean. That call goes through the proxy, so the task runs on the executor and returns thread name `async-1`.
5. `join()` waits for each `CompletableFuture` to finish so the program can print and compare thread names.
6. The context is closed via try-with-resources; the executor is managed by Spring according to its lifecycle.

## 11. Testing Self-Invocation

Do not merely check whether a method carries `@Async`. Test observable runtime behavior through the proxy.

Useful testing techniques:

- Capture the thread name or thread identifier to compare caller vs. worker.
- Use `CountDownLatch` or `CompletableFuture` to synchronize tests instead of arbitrary sleeps.
- Verify that a method called through another bean actually executes on the configured executor.
- Verify that self-invocation runs synchronously when proving the bug.
- Test exceptions and timeouts of async tasks.

For integration tests, bootstrap a real `ApplicationContext` so Spring creates proxies and executors. Unit tests instantiating classes with `new` only exercise plain Java logic and cannot verify whether `@Async` is applied by proxies.

Do not assert a fixed log ordering across threads if the program lacks synchronization. Use Futures, latches, or thread-identity assertions for stable checks.

## 12. Common Mistakes and Resolutions

- Calling `this.asyncMethod()`: internal calls bypass the proxy; extract the method to another bean and invoke via dependency injection.
- Thinking `@Async` spawns threads for every call: the annotation only takes effect when invocations pass through the async proxy.
- Instantiating via `new`: objects are not Spring-managed and therefore have no proxy.
- Marking methods `private` or `final` and expecting class proxies to intercept them: use proxy-interceptable methods and check proxy mode.
- Adding `@Async` without `@EnableAsync`: configure async annotation processing in the `ApplicationContext`.
- Calling through a target reference instead of the bean proxy: obtain dependencies from the Spring container or constructor injection.
- Ignoring the returned Future: if results matter, retain the `CompletableFuture` and handle completion/errors.
- Using `void` return and expecting exceptions to propagate to the caller: configure `AsyncUncaughtExceptionHandler` or handle errors in background listeners/services.
- Using self-injection everywhere: prefer bean extraction for clean proxy boundaries.
- Confusing `@Async` with `@Transactional`: the two annotations serve different purposes, yet both can be bypassed by self-invocation in proxy mode.

## 13. Adoption Workflow

1. Identify the method that needs to run asynchronously and its actual callers.
2. Check whether callers invoke through a Spring proxy or directly within the same class.
3. If self-invocation exists, extract the async work into a separate bean and inject it via constructor.
4. Enable `@EnableAsync` and configure a bounded executor.
5. Choose `void` or `CompletableFuture` based on result-retrieval and error-handling needs.
6. Verify that the method and proxy type allow interception.
7. Write integration tests verifying execution thread, outcomes, and exceptions.
8. Apply the same check to other proxy-based annotations like `@Transactional` and `@Cacheable`.

Self-invocation is a consequence of how Spring AOP uses proxies to apply interceptors. When one method calls another on the same object, the internal call goes straight to the target and bypasses the proxy. Extracting asynchronous work to a separate bean generally establishes the clearest boundary for `@Async` to work as intended.