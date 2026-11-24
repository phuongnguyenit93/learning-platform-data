# Declaring @EnableAsync in a Configuration Class

## 1. Lesson Objectives

In the Spring Framework, adding `@Async` to a method is **not enough** to ensure that the call runs asynchronously. The application must enable async annotation processing in the **Spring application context**. The standard way to declare this is to place `@EnableAsync` on a `@Configuration` class.

After this lesson, you should be able to:

1. Properly declare `@Configuration` + `@EnableAsync` and the required imports.
2. Explain what is enabled: the `@Async` interception infrastructure, **not** a promise to create a bounded thread pool.
3. Define a `ThreadPoolTaskExecutor` bean and target that bean with `@Async("...")`.
4. Understand why methods must be called through a Spring-managed proxy; recognize self-invocation, manually instantiated (`new`) objects, and proxy limitations.
5. Distinguish between minimal configuration, Spring Framework defaults, and Spring Boot's conditional auto-configuration support.
6. Properly receive `Future`/`CompletableFuture`, handle exceptions, and control threads and lifecycle.
7. Run a compilable Java 17+ example and verify that the method actually executes on the designated executor.

**Scope:** This lesson focuses on the act of **declaring `@EnableAsync` in a configuration class** and the conditions required for that declaration to take effect; it does not turn it into an overview of all concurrency or scheduling models.

## 2. Minimal Spring Framework Configuration

`@EnableAsync` resides in the `org.springframework.scheduling.annotation` package. `@Configuration` resides in `org.springframework.context.annotation`.

Minimal example:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class AsyncConfig {
}
```

This is a valid configuration class once it is **registered in the Spring application context** (via component scanning, `@Import`, or direct registration). This snippet alone is not a standalone program: it requires an application context and beans containing `@Async` methods.

Role of each annotation:

- `@Configuration` tells Spring that this class provides bean definitions; typically combined with `@Bean` methods.
- `@EnableAsync` imports the infrastructure that supports asynchronous method execution. In the default `PROXY` mode, Spring registers the appropriate components to intercept methods annotated with `@Async` on **Spring-managed beans**.
- `@Async` is placed on a method or class that should run asynchronously; eligible invocations are dispatched as tasks to an executor.
- **Enabling annotation processing** and **selecting the actual executor** are two separate responsibilities.

There is no need to place `@EnableAsync` on every service. Normally, one configuration class loaded into the appropriate context is enough to activate the mechanism for the beans belonging to that context.

### 2.1. Visualizing the Call Flow

```text
Spring ApplicationContext
   |
   +-- receives @Configuration + @EnableAsync class
   |         |
   |         +-- registers async/proxy infrastructure
   |
   +-- manages WorkService bean
   |         |
Caller --> Spring proxy --> @Async interceptor
                              |
                              +-- selects Executor
                              |
                              +-- submits task
                                      |
                                      +-- executes method on worker thread
                                      |
                                      +-- completes Future/CompletableFuture
```

The diagram illustrates the call path when the proxy works normally. A call that does not go through the proxy, such as `this.work()` inside the bean itself, does not automatically become asynchronous just because the method has the annotation.

### 2.2. Why Does the Application Need Both Components?

The following two snippets are not equivalent:

```java
// Method declaration only: does not prove async infrastructure is enabled.
@Async
public CompletableFuture<String> work() {
    return CompletableFuture.completedFuture("ok");
}
```

```java
// Enables infrastructure for the context containing eligible beans.
@Configuration
@EnableAsync
class AsyncConfig {
}
```

An `@EnableAsync` configuration does not make **every** method in the application run asynchronously on its own. Only calls matching the annotation and interception rules are dispatched. Conversely, if a method has `@Async` but the context does not enable async processing, the annotation typically does not change the call behavior in a standard Framework setup.

## 3. Complete Example: Creating Configuration, Executor, and Service

The following template uses **Java 17+, Spring Framework 6.2.14, and Maven**; it runs standalone without Spring Boot. It declares `@EnableAsync` on a configuration class, creates a bounded executor, and invokes a method through a Spring-managed bean.

Directory structure:

```text
enable-async-demo/
├── pom.xml
└── src/main/java/demo/EnableAsyncDemo.java
```

### 3.1. File pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>enable-async-demo</artifactId>
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

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

### 3.2. File EnableAsyncDemo.java

```java
package demo;

import java.util.concurrent.CompletableFuture;
import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class EnableAsyncDemo {
    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class AsyncConfig {
        @Bean("lessonExecutor")
        public ThreadPoolTaskExecutor lessonExecutor() {
            ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
            executor.setThreadNamePrefix("lesson-worker-");
            executor.setCorePoolSize(2);
            executor.setMaxPoolSize(4);
            executor.setQueueCapacity(16);
            return executor;
        }

        @Bean
        public ReportService reportService() {
            return new ReportService();
        }
    }

    public static class ReportService {
        @Async("lessonExecutor")
        public CompletableFuture<Boolean> onWorker(String callerThread) {
            String current = Thread.currentThread().getName();
            boolean result =
                    current.startsWith("lesson-worker-")
                    && !current.equals(callerThread);
            return CompletableFuture.completedFuture(result);
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AsyncConfig.class)) {
            ReportService service = context.getBean(ReportService.class);
            String callerThread = Thread.currentThread().getName();

            CompletableFuture<Boolean> result =
                    service.onWorker(callerThread);

            System.out.println("async-on-configured-pool="
                    + result.get(5, TimeUnit.SECONDS));
        }
    }
}
```

### 3.3. Compiling and Running

In the directory containing `pom.xml`:

```bash
mvn -q compile org.codehaus.mojo:exec-maven-plugin:3.3.0:java -Dexec.mainClass=demo.EnableAsyncDemo
```

Output from the `System.out.println` line under normal conditions:

```text
async-on-configured-pool=true
```

Maven or the environment may print additional messages. The example intentionally checks the **thread name** rather than inferring from execution time; `result.get(5, TimeUnit.SECONDS)` waits up to five seconds for the result and throws an error if the task fails or times out.

### 3.4. Step-by-Step Explanation

1. `AnnotationConfigApplicationContext` registers `AsyncConfig`, meaning the class containing `@Configuration` and `@EnableAsync` is actually loaded by Spring.
2. The `lessonExecutor` bean is a `ThreadPoolTaskExecutor`. The values core=2, max=4, queueCapacity=16 merely illustrate a bounded pool, not an optimal universal configuration for all workloads.
3. The `reportService` bean is created by Spring. When needed, Spring applies an async proxy to the `onWorker(...)` method.
4. The client obtains the bean from the context, **not** via `new ReportService()`, because a manually instantiated object will not receive interception.
5. `@Async("lessonExecutor")` explicitly specifies the target executor name instead of relying on default lookup.
6. The worker reads the name of the thread running the method. The `lesson-worker-` prefix along with the thread differing from the caller confirms the expected execution path.
7. The method returns `CompletableFuture.completedFuture(...)` **inside the worker**. The interceptor provides a future to the caller to observe completion.
8. When the context closes, Spring manages the lifecycle of the registered executor bean; caller code does not call `shutdown()` itself on an executor shared across services.

If you change `@Async("lessonExecutor")` to `@Async`, you must inspect the context's default executor selection rules. If you remove `@EnableAsync` and there is no other async configuration, the call may run directly on the caller thread; in that case, the prefix check will fail.

## 4. Declaring in a Spring Boot Application

Spring Boot uses the Spring Framework as its foundation. In a Boot application, you can place `@EnableAsync` directly on the main class or in a separate `@Configuration` class.

### 4.1. On the Main Class

This is a **Spring Boot application fragment** requiring Spring Boot dependencies, not a standalone program compiled with `javac` alone:

```java
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.scheduling.annotation.EnableAsync;

@SpringBootApplication
@EnableAsync
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
```

`@SpringBootApplication` is not a synonym for `@EnableAsync`. Typically, you still must intentionally enable async annotation processing when you want to use `@Async`. Boot may create a default executor via **conditional** auto-configuration, but **having an executor** and **enabling the annotation interceptor** are two distinct things.

### 4.2. On a Separate Configuration Class

An appropriate option when you want to separate concurrency configuration from the startup entry point:

```java
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncInfrastructureConfig {
}
```

Ensure that `AsyncInfrastructureConfig` is within component scan range or imported into the context:

```java
@SpringBootApplication
@Import(AsyncInfrastructureConfig.class)
public class Application {
    // Imports and main method are declared in the project.
}
```

This is also a fragment; `@Import` is an option when the configuration is not picked up by component scanning. Do **not** place the same configuration in multiple places if doing so confuses readers about the context or creates duplicate beans. In applications with multiple contexts (for example, parent and child), `@EnableAsync` takes effect in the context where it is declared; do not assume it automatically covers all child contexts.

### 4.3. Boot Auto-Configuring an Executor Does Not Mean Auto-Configuring All Custom Beans

A Spring Boot project might use properties such as:

```yaml
spring:
  task:
    execution:
      thread-name-prefix: app-async-
      pool:
        core-size: 4
        max-size: 8
        queue-capacity: 64
```

Those properties apply when the corresponding **Boot-managed executor** type is actually auto-configured and its conditions match. If you declare `@Bean("lessonExecutor") ThreadPoolTaskExecutor` and invoke setters directly, Boot does not automatically force this custom bean to inherit all `spring.task.execution.*` values. Adding a custom `Executor` bean can also affect the conditions under which Boot creates its default executor; verify the bean list for your exact Boot version.

Conclusion of this section: in either **plain Spring Framework** or **Spring Boot**, `@EnableAsync` still performs the job of **enabling async interception**. Boot merely adds execution resource auto-configuration with conditional defaults.

## 5. What Mechanism Does @EnableAsync Actually Enable?

In the common `AdviceMode.PROXY` mode, enabling support registers the appropriate async advisor/interceptor and post-processor infrastructure. When a managed bean has a method recognized as async, calls **through the proxy** are intercepted before executing the actual logic.

Concepts to distinguish:

| Concept | Role |
| --- | --- |
| `@Configuration` | Defines a Spring configuration class |
| `@EnableAsync` | Activates async annotation processing for the context |
| `@Async` | Marks a method/class whose eligible calls should be dispatched asynchronously |
| `AsyncConfigurer` | Customizes the default executor and exception handler for `void`-returning async methods |
| `@Async("executorName")` | Selects an executor by bean name or qualifier |
| `ThreadPoolTaskExecutor` | An executor implementation managing workers/queue |
| `CompletableFuture<T>` | A handle for observing the completion state and result of an async call |
| Spring AOP proxy | The intermediary layer required in the default advice mode |
| `AdviceMode.ASPECTJ` | Advanced weaving mode; requires additional AspectJ setup |

Do not confuse `@EnableAsync` with `@EnableScheduling`: the first serves `@Async`, while the second serves `@Scheduled` methods. If the application needs both, both can be declared on a single configuration class, though they enable two different kinds of annotation processing.

### 5.1. Why Does Calling Through a Proxy Matter?

In the default mode, Spring typically creates a proxy wrapping the async bean. For an eligible method, the caller invokes the **proxy**, the proxy submits a task to the executor, and then the original method runs on a worker.

```text
Bean A ---> proxy(Bean B) ---> executor.submit ---> Bean B.work()
Bean B ---> this.work() ---------------------------> Bean B.work()
              (bypasses proxy)
```

The second line is **self-invocation**: a method inside Bean B itself calls another method on the same instance via `this`, bypassing the proxy in the default `PROXY` mode. Therefore, even if the target method has `@Async`, it may execute synchronously on the current thread.

Appropriate solutions:

- **Preferred:** extract the async method into a separate bean, inject it, and call it through the Spring-managed bean.
- You can design the caller to use a service interface/proxy if it fits the project structure.
- For specialized needs, consider AspectJ mode with proper weaving; that is a separate setup, not just changing an enum.
- Do not recommend self-injection as a default solution, as it easily causes circular dependencies and makes the API hard to understand.

### 5.2. Which Beans Are Eligible for Processing?

An async method should be a method invoked through a Spring-managed proxy. Check the following:

- **Does the object belong to the container?** `new MyService()` created manually by the application is not automatically proxied by Spring.
- **Does the call go through the proxy?** `this.method()` usually does not.
- **Can the proxy intercept the method?** With class-based proxies, private/final methods have limitations; public methods are the clearest and least risky choice for this lesson.
- **Is the annotation placed where the framework recognizes it?** Place it on the appropriate implementation method/class; when using interfaces/proxies, verify according to the actual structure.
- **Does the context have async enabled?** `@EnableAsync` must be loaded in the right application context.

Do not conclude "Spring is ignoring `@Async`" merely because no new thread log appears: you must also inspect the selected executor, invocation path, and method restrictions.

## 6. Important Attributes of @EnableAsync

The standard syntax requires no arguments:

```java
@Configuration
@EnableAsync
public class AsyncConfig {
}
```

For advanced requirements, the annotation allows tuning how advice is applied:

| Attribute | Meaning | Recommendation When Learning |
| --- | --- | --- |
| `mode` | How async advice is applied: `PROXY` (default) or `ASPECTJ` | Use `PROXY` unless you have a reason and weaving infrastructure |
| `proxyTargetClass` | With `PROXY`, prefers class-based proxies over interface-based proxies | Do not enable indiscriminately; affects other proxies in the context |
| `order` | Registration order of the async post-processor/advisor in the proxy chain | Keep default unless there is a special AOP ordering requirement |
| `annotation` | Specifies a custom async annotation type beyond the default annotations | Only needed in systems with custom conventions |

Example illustrating explicit configuration of the default mode:

```java
import org.springframework.context.annotation.AdviceMode;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync(mode = AdviceMode.PROXY, proxyTargetClass = false)
public class AsyncConfig {
}
```

This is a **configuration class fragment**; writing `mode`/`proxyTargetClass` is not mandatory. The default values are already equivalent. Note that Boot or another AOP mechanism may choose the proxy type according to its own configuration; do not rely on this attribute to infer with certainty whether the final object is a JDK proxy or a class proxy in every application.

### 6.1. When Is AspectJ Needed?

`@EnableAsync(mode = AdviceMode.ASPECTJ)` is only meaningful when full AspectJ weaving and the required dependencies are configured. It can handle local invocation cases that proxies bypass, but it increases build/runtime complexity and has specific environment requirements. Do not enable it just to fix a simple self-invocation; extracting a bean is easier to understand and test.

## 7. Declaring an Executor Alongside the Configuration Class

`@EnableAsync` only enables processing; the executor determines threads, queuing, load limits, and lifecycle. For applications needing control, declare a `ThreadPoolTaskExecutor` bean:

```java
import java.util.concurrent.ThreadPoolExecutor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncConfig {
    @Bean("ioExecutor")
    public ThreadPoolTaskExecutor ioExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setThreadNamePrefix("io-task-");
        executor.setCorePoolSize(4);
        executor.setMaxPoolSize(8);
        executor.setQueueCapacity(50);
        executor.setRejectedExecutionHandler(
                new ThreadPoolExecutor.AbortPolicy());
        executor.setWaitForTasksToCompleteOnShutdown(true);
        executor.setAwaitTerminationSeconds(20);
        return executor;
    }
}
```

This is a **Spring configuration fragment**, not a standalone program. The numbers 4/8/50/20 are examples to illustrate structure; in production, you must measure actual load, CPU, downstream connection limits, deadlines, and wait times to choose values.

To bind a method to this pool:

```java
import java.util.concurrent.CompletableFuture;
import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class EmailService {
    @Async("ioExecutor")
    public CompletableFuture<String> prepare(String emailId) {
        return CompletableFuture.completedFuture(
                "prepared:" + emailId);
    }
}
```

This is a **Spring project fragment**: the sample method only concatenates a string, so in practice it would not need to be async. It illustrates how to select an executor by **bean name**: `@Async("ioExecutor")`. Ensure there are no multiple beans with the same name in the context and that the caller does not invoke the method directly from within `EmailService` itself.

### 7.1. Thread Counts and Queues Must Not Be Left at Defaults Unthinkingly

With `ThreadPoolTaskExecutor` backed by an underlying `ThreadPoolExecutor`:

1. The pool may create a worker for a new task when currently below `corePoolSize`.
2. Once core workers are full, tasks are usually placed in the queue if queue space remains.
3. When the queue accepts no more tasks and the worker count has not reached `maxPoolSize`, the pool may expand.
4. When there is no remaining capacity to accept the task, the rejection policy is applied.

Therefore, increasing `maxPoolSize` while keeping an unbounded queue does **not** necessarily cause the pool to use more workers. Having `@EnableAsync` present does not solve queue pressure; you must choose an executor policy suited to the load.

When using `AbortPolicy`, the caller may receive an exception at task submission time if the pool cannot accept it. This is an important distinction between a **submission failure** and a **business failure inside the task** (typically observed through a future). The system must handle both.

### 7.2. What If No Executor Is Explicitly Declared?

With the Spring Framework, async support has a mechanism to look up a suitable executor, for example based on a matching `TaskExecutor` or an `Executor` conventionally named `taskExecutor`; if none is found, there is a fallback like `SimpleAsyncTaskExecutor` depending on the version/framework setup.

This fallback is not equivalent to a production-ready bounded thread pool. Do not rely on it for heavy workloads without understanding its concurrency and resource limits.

Spring Boot may auto-configure an executor bean, but the conditions, bean name, and bean type depend on the version, existing custom executors, virtual-thread mode, and integrations in use. When you need to know with certainty which pool a method uses, `@Async("ioExecutor")` is the least ambiguous approach.

## 8. Choosing a Default via AsyncConfigurer

Within the same ApplicationContext, if many methods use `@Async` **without a qualifier**, `AsyncConfigurer.getAsyncExecutor()` can return an intentionally chosen default `Executor`. This is a configuration point of the infrastructure already enabled by `@EnableAsync`; it does not replace the annotation that enables async and does not force `@Async("ioExecutor")` calls to use the same pool.

`AsyncConfigurer` also allows registering an `AsyncUncaughtExceptionHandler` to observe errors from `@Async void` methods. If you want to use a `ThreadPoolTaskExecutor`, you should manage it as a Spring bean and verify its initialize/shutdown lifecycle; a class implementing `AsyncConfigurer` may be instantiated early, so avoid circular injection or unready dependencies.

In the **mechanism enablement** step of this lesson, you only need to know where the default executor configuration lives and that it does not alter the effect of `@EnableAsync`. When designing multiple executors, you must test which pool executes each method; core/max/queue settings depend on load and downstream limits.

## 9. Return Type Contracts and Errors to Verify Immediately When Enabling Async

When going through a Spring async proxy, methods support `void`, `Future<T>`, or `CompletableFuture<T>`. Methods returning `String` or `int` directly are not supported return value contracts for the interceptor. The following example sits inside a service bean that has an `ioExecutor`; this is a fragment, not a standalone runnable class:

```java
@Async("ioExecutor")
public CompletableFuture<Integer> calculate(int value) {
    if (value < 0) throw new IllegalArgumentException("negative");
    return CompletableFuture.completedFuture(value * 2);
}
```

The caller receives a handle from the proxy to compose or wait with a timeout; errors inside the worker of a Future-returning method are reflected via exceptional completion. With `void`, errors have no Future channel and require an appropriate `AsyncUncaughtExceptionHandler`/logging. Executor rejection at submission time, by contrast, can happen immediately on the call path before a handle is returned.

Successfully placing `@EnableAsync` does not automatically guarantee timeouts, interruption, transaction/context propagation, retries, or durability. Verify those contracts separately according to business needs.

## 10. Conditions You Must Not Overlook When Declaring @EnableAsync

### 10.1. The Annotation Must Be Loaded by Spring

If `@EnableAsync` is placed on a class that is not part of component scanning, not imported via `@Import`, or not directly registered, Spring does not see that configuration. The existence of the Java file in source does not prove the context has async enabled.

You can verify by retrieving the configuration bean from the context, inspecting conditions/bean definitions, and testing that the method actually runs on the executor. In Spring Boot, enabling debug logs appropriately helps reveal auto-configuration, though you must still verify the Framework's annotation infrastructure.

### 10.2. The Method Must Be Called Through a Proxy

When running in `AdviceMode.PROXY`, self-invocation does not go through the proxy. Consider this case:

```java
@Service
class ExportService {
    public void start() {
        exportAsync(); // Internal call: bypasses proxy in PROXY mode
    }

    @Async
    public void exportAsync() {
        // This code does not switch threads automatically because start() calls it internally.
    }
}
```

This is a fragment (annotation imports required). Usually the best fix is: extract `exportAsync()` into a separate bean and inject that bean into the caller, or design an entry point from outside the proxy. Do not rely on `this.exportAsync()`.

### 10.3. Do Not Call @Async Directly From @PostConstruct

`@PostConstruct` runs during the initialization lifecycle phase; do not assume the async proxy is ready to handle a callback on the same bean. Do not use `@Async` on a lifecycle callback expecting it to switch threads. If you need to kick off an async task, have another initializing Spring-managed bean call it through the service's proxy at the right time, or use a properly chosen application lifecycle/event mechanism.

### 10.4. Do Not Treat the Annotation as a Thread-Safety Solution

`@EnableAsync` only enables how execution happens; it does not protect shared mutable state. If a singleton service holds mutable fields and two tasks modify them concurrently, race conditions can still occur. Separate immutable inputs/outputs, use locks/atomics when needed, and avoid per-request state in singletons.

### 10.5. Do Not Assume Thread Context Follows the Task

Spring transaction context, security context, `ThreadLocal`, MDC, request attributes, and persistence context do not automatically transfer from caller to worker. For instance, `@Transactional` on the caller does not mean operations inside an `@Async` method run in the caller's transaction. When needed, open a separate transaction in the worker, pass immutable data/IDs, and configure context propagation explicitly for each allowed context type.

## 11. Four Common Configuration Scenarios

| Scenario | @EnableAsync | Executor | Conclusion |
| --- | --- | --- | --- |
| Bean has `@Async` but context does not enable async processing | No | Present or absent | The annotation does not necessarily produce an async invocation |
| Context has `@EnableAsync`, service is called through proxy | Yes | Valid executor | Task is offloaded according to executor selection |
| Context has `@EnableAsync` but method is called via `this` | Yes | Yes | Self-invocation may run synchronously |
| Boot auto-configures executor but annotation is not enabled | No | Yes | Having an executor does not mean `@Async` is active |
| `@EnableAsync` + `@Async("missingExecutor")` | Yes | Named bean missing | Async call will fail when resolving the executor |
| `@EnableAsync` + bean with unbounded pool/queue | Yes | Yes | Risks of growing load, memory usage, and latency remain |
| `@EnableAsync` placed in parent context | In parent | Context-dependent | Does not imply child context infrastructure is enabled too |
| `@EnableAsync(mode=ASPECTJ)` without proper weaving | On paper | Depends | Cannot expect advice to work properly from the annotation alone |

In every case, distinguish between **declaration** and **observed runtime behavior**.

## 12. Debugging: How to Know Whether @EnableAsync Is Working?

This is a diagnostic checklist to perform before tuning thread pools:

1. **Verify the context:** is the `@Configuration` class scanned/imported? Is `@EnableAsync` in the right context?
2. **Verify the bean:** is the service injected by Spring or did you use `new`?
3. **Verify the call path:** does the caller invoke through the bean/proxy or call `this.method()` inside the same class?
4. **Verify the annotation:** does the method/class have `@Async`? Is the method compatible with the proxy type and return type?
5. **Verify the executor:** which bean does `@Async("...")` point to? Is there an `AsyncConfigurer` or another default executor?
6. **Verify execution:** log caller/worker thread names; prefer testing with the executor's thread-name prefix and a future.
7. **Measure overload:** active count, pool size, queue depth, rejected tasks, timeouts, queue wait; a method not running immediately may be due to queuing rather than a missing `@EnableAsync`.
8. **Check Boot when relevant:** with Boot, inspect auto-configuration conditions, profiles, runtime bean types, and property binding.
9. **Check errors:** does the future complete exceptionally? Does a `void` method have an appropriate handler/log?
10. **Check shutdown:** are new tasks rejected because the context/executor is shutting down?

Logging inside an async method and printing the thread name is a good step, but you should not rely solely on "different thread name" to conclude the architecture is right. Especially if the method touches shared data, test both correctness and lifecycle.

### 12.1. Checking Proxies With Spring AOP

In test or diagnostic code that includes Spring AOP:

```java
Object bean = context.getBean(ReportService.class);
System.out.println(
        org.springframework.aop.support.AopUtils.isAopProxy(bean));
```

This is a fragment, assuming `context` and `ReportService` exist in the project. A `true` value indicates the bean is an AOP proxy, but **does not by itself prove** the method is offloaded by the async advice. Combine it with thread and executor checks. A bean can be proxied for other reasons, such as `@Transactional`.

### 12.2. Testing Without Depending on Thread.sleep()

If you need to prove a task runs on a worker and the caller can proceed, use `CountDownLatch` or a future with a timeout, not `Thread.sleep(100)` followed by guessing whether the task has finished. Latches coordinate ordering in tests, making tests far less dependent on machine speed.

A solid test contract should verify: the configuration class was loaded; the bean was retrieved from the context; the `@Async("lessonExecutor")` method actually runs on a worker; results and exceptions are observable; and tasks are not silently dropped on shutdown.

## 13. Hands-On Exercises: From Minimal Setup to Verification

### Exercise 1 — Enable the Annotation

Create `AsyncConfig` with `@Configuration` and `@EnableAsync`. Declare a `WorkService` bean with an `@Async` method returning `CompletableFuture<String>`. Call the method from another Spring-managed bean.

- Print the caller thread name and worker thread name.
- Explain why it must be called through a Spring bean.
- Remove `@EnableAsync` in an isolated test environment and observe the difference.

### Exercise 2 — Specify the Executor Explicitly

Add `@Bean("workExecutor") ThreadPoolTaskExecutor` with prefix `work-`, core=2, max=4, queue=10. Use `@Async("workExecutor")`. Test that the handling thread has the configured prefix. Then intentionally misspell the qualifier name and observe the exception when Spring cannot find the executor.

### Exercise 3 — Reproduce Self-Invocation

In the same service, create `start()` calling `this.runAsync()`, where `runAsync()` has `@Async`. Identify the executing thread. Then move `runAsync()` into a separate bean, inject that bean into the caller, and verify async behavior returns. Explain using the proxy model.

### Exercise 4 — Return Types and Errors

Have an `@Async` method return `CompletableFuture<Integer>` and intentionally throw an exception. Use `get()` or a completion handler to receive the error; next, try a `void` method and configure an exception handler to record the error properly. Check the difference between an exception when submission is rejected and an exception thrown inside the task.

### Exercise 5 — Spring Boot

Declare `@EnableAsync` on `@SpringBootApplication` and then move it to a separate `@Configuration` class; verify both approaches take effect when loaded in the context. Try adding a custom executor bean and check whether `spring.task.execution.*` properties actually configure the bean the task uses. Do not treat YAML as the sole proof.

### Exercise 6 — Lifecycle

Close `ApplicationContext` while the executor has running tasks. Check how tasks are handled/cancelled according to configuration and deadlines. State clearly why work that must survive a JVM restart needs a durable job/queue, not just `@EnableAsync`.

## 14. Production Readiness Checklist

- [ ] There is a `@Configuration` loaded by Spring with `@EnableAsync` in the right context.
- [ ] All intended async methods are called through Spring-managed beans and proxies.
- [ ] Self-invocation, private/final methods, initialization callbacks, and return types have been reviewed.
- [ ] Executors are chosen intentionally: name, type, core/max/queue, and rejection policy.
- [ ] Do not assume Spring Boot automatically enables `@Async` or applies properties to every custom executor.
- [ ] Callers observe errors: via futures/handlers, logs, and metrics as required by the business logic.
- [ ] Timeouts, cooperative cancellation, and resource limits exist for I/O and downstream calls.
- [ ] Do not rely on the caller's transaction/ThreadLocal automatically appearing on the worker.
- [ ] Singleton beans do not hold per-request mutable state that causes races between tasks.
- [ ] Spring-managed executors have an appropriate shutdown policy; durable tasks have an external mechanism outside the JVM.
- [ ] Tests verify exact threads, executors, exceptions, and load scenarios; do not rely on `sleep`.
- [ ] APIs and defaults have been verified against the actual Spring Framework / Spring Boot version in use.

**Conclusion:** Declaring `@EnableAsync` in a `@Configuration` class is the step that **enables the async annotation processing infrastructure**. For `@Async` to work correctly and safely, you must also ensure the configuration is loaded, calls go through a Spring proxy, executors have appropriate bounds, and lifecycle/errors/results are observable. Success is not merely "the method runs on another thread," but executing with the right resources and verifiable behavior.

## 15. Official References

- Spring Framework — [Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, executor qualification, exception handling, and proxy principles.
- Spring Framework Javadoc — [@EnableAsync](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): annotation attributes, context scope, `AsyncConfigurer`, and advice modes.
- Spring Framework Javadoc — [@Async](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/scheduling/annotation/Async.html): return types and annotation purpose.
- Spring Boot — [Task Execution and Scheduling](https://docs.spring.io/spring-boot/reference/features/task-execution-and-scheduling.html): executor components auto-configured by Boot and cases interacting with `@EnableAsync`.

When upgrading the framework, use the documentation links for the **exact version** in your project, because auto-configuration and default executor selection may differ across releases.
