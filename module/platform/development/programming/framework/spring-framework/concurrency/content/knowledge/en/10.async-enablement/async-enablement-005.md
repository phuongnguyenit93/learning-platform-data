# Limitations of Using @Async on Methods Inside a @Configuration Class

## 1. Objective and Key Distinction

In the Spring Framework, `@Configuration` is responsible for **declaring and configuring beans**, whereas `@Async` is used to **invoke a bean's method asynchronously** via Spring's processing mechanism. Both annotations can appear in the same application, but there is an easily misunderstood limitation:

> **Spring does not support `@Async` on methods declared within a `@Configuration` class.**

This is stated directly in the Javadoc of `org.springframework.scheduling.annotation.Async` (including both Spring 5.3 and 6.x documentation). Do not infer that a method inside a configuration class will switch to a worker thread merely because `@Async` is attached and `@EnableAsync` is enabled.

After this lesson, you will be able to:

- Distinguish **`@EnableAsync` placed on a `@Configuration` class (correct, supported)** from **`@Async` placed on a method inside that class itself (unsupported)**.
- Understand the responsibility of `@Configuration`/`@Bean` when creating beans versus the responsibility of `@Async` when handling business calls.
- Move asynchronous work into a separate `@Service`/`@Component` bean managed by Spring and called **through a proxy**.
- Create a truly runnable Spring Framework 6.1.3, Java 17+ example and verify the executing thread.
- Distinguish this limitation from other issues: self-invocation within the same instance, calling too early in the lifecycle, not enabling async processing, or picking the wrong executor.
- Check error handling, `Future`/`CompletableFuture` return types, and plan refactors without breaking bean initialization.

**Scope:** Spring Framework, Java-based configuration, and `@Async` in the common proxy mode. Examples use Java 17+ and Spring Framework 6.1.3, though the rule **not supporting `@Async` on methods declared within `@Configuration`** has been in the Spring 5.3 Javadoc and remains in Spring 6.x. Even if an application uses AspectJ weaving, you should still organize separate business beans and check the version's documentation; do not treat weaving as a way to bypass an explicitly documented annotation restriction.

## 2. Core Rule: Where to Enable vs. Where to Execute

### 2.1. Correct Approach: `@EnableAsync` on the Configuration Class

~~~java
@Configuration
@EnableAsync
public class AsyncConfig {
    // @Bean definitions configuring executors or other dependencies.
}
~~~

This is an **illustrative fragment**, not a complete Java file (imports for both annotations are needed). `@EnableAsync` activates asynchronous call processing in the **Spring application context**. Placing it on a `@Configuration` class is the approach recommended by Spring documentation.

`@EnableAsync` **does not automatically run all methods of the configuration class on worker threads**. It registers the annotation-processing components so that eligible `@Async` methods **on other beans** have the configured interceptor/proxy applied by Spring.

### 2.2. Incorrect Approach: `@Async` on a Method Declared in `@Configuration`

~~~java
import java.util.concurrent.CompletableFuture;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;

@Configuration
@EnableAsync
public class WrongConfig {
    @Async
    public CompletableFuture<String> generateReport() {
        return CompletableFuture.completedFuture("report");
    }
}
~~~

The snippet above is an **organizational counterexample**, even though the Java syntax looks valid. By Spring's annotation contract, `@Async` **is not supported on methods declared inside a `@Configuration` class**. Do not rely on it to guarantee `generateReport()` runs asynchronously, and do not treat an accidental run as proof of support.

A related counterexample is attaching `@Async` to a **`@Bean` factory method**:

~~~java
// Counterexample: @Async should not be on a @Bean method
@Configuration
class WrongFactoryConfig {
    @Bean
    @Async
    public ReportService reportService() {
        return new ReportService();
    }
}
~~~

This is **not standalone code** and does not provide the `ReportService` definition. `@Bean` is a method that **creates an object for the container to register**; placing `@Async` on the initialization method itself does not turn the returned bean's business methods async. Moreover, `@Async` requires the method return type to be `void` or a supported `Future` type; in the example above, returning `ReportService` does not even satisfy that contract. Attach `@Async` to **methods of the returned service** if the service genuinely needs background processing.

### 2.3. What Is Still Allowed?

| Annotation Placement | Supported? | Meaning |
| --- | --- | --- |
| `@Configuration` + `@EnableAsync` on configuration class | **Yes** | Enables `@Async` processing support for the application context |
| `@Bean` creating `ThreadPoolTaskExecutor` in `@Configuration` | **Yes** | Configures a Spring-managed executor |
| `@Async` on a method declared inside the `@Configuration` class itself | **No** | Outside the annotation's supported scope |
| `@Async` on a `@Bean` method to try running the factory method in background | **Do not use** | Wrong responsibility for a bean factory method |
| `@Async` on a method of a Spring-managed `@Service` or `@Component` | **Yes**, if called via proper path | Method is routed to an executor by Spring proxy/interceptor |
| A `@Bean` method returning a service that has its own `@Async` methods | **Yes** for eligible services | The factory method is synchronous; methods on the **returned bean** can be async |
| `@Async` at the `@Configuration` class level | **Do not use to async-ify config** | Class-level `@Async` also does not turn config methods into supported async APIs |

The distinction is the **class where the method is actually declared**. If `AppConfig` declares `@Bean ReportService reportService()` and `buildReport()` resides inside **`ReportService`**, the "methods declared within `@Configuration`" restriction does not apply to `buildReport()` merely because `ReportService` was instantiated by a `@Bean` method.

## 3. Why Are the Two Mechanisms Different?

### 3.1. Role of `@Configuration` and `@Bean`

A `@Configuration` class expresses **metadata and bean definitions**. The container uses `@Bean` methods to instantiate dependencies, assign names, determine scopes, and manage lifecycles. With the default `@Configuration(proxyBeanMethods=true)`, Spring may **enhance** the class using a CGLIB subclass so inter-`@Bean` method calls respect singleton/scoping semantics.

That enhancement serves **bean management**; it does not mean Spring `@Async` wraps configuration methods like business methods on a service. Even less should a factory method invoked while the container is initializing beans become a background call returning before the bean is built.

### 3.2. Role of `@Async` and the Async Interceptor

Once Spring enables `@EnableAsync`, in the default `AdviceMode.PROXY` mode, calls to valid `@Async` methods **passing through the Spring proxy** are dispatched to a `TaskExecutor`. Callers receive a result matching the declared return type; actual work runs on a worker thread.

~~~text
             AT CONTEXT STARTUP
@Configuration -- @Bean --> Spring registers / creates executor and service
      |
      +-- @EnableAsync --> registers async annotation processing

             AT BUSINESS INVOCATION
Controller / caller
      |
      v
Service bean retrieved from Spring context
      |
      v
Spring proxy / async interceptor
      |
      +-- submit task --> TaskExecutor --> worker thread
      |
      +-- caller receives void / Future / CompletableFuture
~~~

**There is no "Spring async-ifies methods inside `@Configuration`" step in the diagram above.** Configuration only **enables the mechanism and provides beans**; business logic lives in a separate bean that the interceptor can process according to the contract.

### 3.3. Can One Class Be Both Config and Service?

In Java syntax, you can put many methods with many annotations into a single class, but in Spring you should not turn a `@Configuration` class into a home for `@Async` business methods. The core reason is that **the `@Async` API explicitly states it does not support methods declared there**. Separating responsibilities also keeps bootstrapping clear, makes testing easier, and avoids coupling to config-class proxying/initialization details.

Setting `@EnableAsync(proxyTargetClass=true)` does not lift this restriction: that attribute only changes the proxy strategy in `PROXY` mode. Likewise, `@Configuration(proxyBeanMethods=false)` adjusts proxying of `@Bean` methods; it **does not turn** `@Async` methods inside config into supported cases.

## 4. Proper Structure: Config Creates Executor, Service Declares @Async

Architectural example:

~~~text
demo
├── AppConfig.java
│   ├── @Configuration
│   ├── @EnableAsync
│   └── @Bean("lessonExecutor"): ThreadPoolTaskExecutor
├── ReportService.java
│   └── @Service + @Async("lessonExecutor") on generate()
└── AsyncConfigurationDemo.java
    └── retrieves ReportService from Spring context and calls generate()
~~~

The executor is configured **once**; the business service is managed by Spring. Crucially, the caller **retrieves the bean from the context**, avoiding `new ReportService()` while expecting annotation processing. Creating the service via `@Bean` is also valid when returning the bean properly; the example chooses `@Service` to make the separation of concerns easy to see.

### 4.1. Standalone Runnable Maven Project

Uses **JDK 17+**, Maven, and Spring Framework 6.1.3. The program needs no Spring Boot server; plain Spring Framework suffices to demonstrate proxying.

File structure:

~~~text
async-config-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                ├── AppConfig.java
                ├── ReportService.java
                └── AsyncConfigurationDemo.java
~~~

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>async-config-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.3</version>
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
                <version>3.3.0</version>
                <configuration>
                    <mainClass>demo.AsyncConfigurationDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The `spring-context` dependency pulls in the Spring dependencies needed for `@EnableAsync`, AOP, and `ThreadPoolTaskExecutor` in this example. Real Spring Boot applications should let the BOM/parent manage consistent Spring versions.

### 4.2. Configuration in `AppConfig.java`

~~~java
package demo;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration
@EnableAsync
public class AppConfig {

    @Bean("lessonExecutor")
    public ThreadPoolTaskExecutor lessonExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(1);
        executor.setMaxPoolSize(1);
        executor.setQueueCapacity(10);
        executor.setThreadNamePrefix("lesson-");
        return executor;
    }
}
~~~

`@EnableAsync` sits in **the right place**, on the configuration class. `@Bean` creates a `ThreadPoolTaskExecutor` managed by the Spring container. Notably: **there is no `@Async` on `lessonExecutor()`**; this method only instantiates and configures the executor.

Here the pool is small for illustration, not default parameters for production use. In real projects, configure worker counts, queues, rejection, and shutdown according to workload.

### 4.3. Business Method in `ReportService.java`

~~~java
package demo;

import java.util.Locale;
import java.util.concurrent.CompletableFuture;

import org.springframework.scheduling.annotation.Async;
import org.springframework.stereotype.Service;

@Service
public class ReportService {

    @Async("lessonExecutor")
    public CompletableFuture<String> generate(String name) {
        boolean onWorker =
                Thread.currentThread().getName().startsWith("lesson-");

        String value = name.toUpperCase(Locale.ROOT)
                + "|worker=" + onWorker;

        return CompletableFuture.completedFuture(value);
    }
}
~~~

The `generate` method itself resides on **`ReportService`**, a bean independent from `AppConfig`. `@Async("lessonExecutor")` selects the executor named `lessonExecutor`. We set a thread prefix to verify the method ran on the configured worker thread.

**Why does the target method return `CompletableFuture.completedFuture(...)`?** With `@Async`, the Spring proxy submits the method invocation to the executor and returns a `CompletableFuture` representing execution at the proxy level. The target method actually running on the worker can return a temporary already-completed future. That does **not** mean the caller executed the target method synchronously. Spring extracts the target method's result via the interceptor mechanism.

### 4.4. Bootstrapping in `AsyncConfigurationDemo.java`

~~~java
package demo;

import java.util.concurrent.TimeUnit;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;

public final class AsyncConfigurationDemo {

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             AppConfig.class,
                             ReportService.class)) {

            ReportService service = context.getBean(ReportService.class);

            String result =
                    service.generate("spring").get(5, TimeUnit.SECONDS);

            System.out.println(result);
        }
    }
}
~~~

In the `async-config-demo` directory, run:

~~~bash
mvn -q compile exec:java
~~~

Output printed by the Java program (excluding build logs if Maven/plugins display any):

~~~text
SPRING|worker=true
~~~

**Why is this output trustworthy?** The program creates an executor bean with thread prefix `lesson-`, obtains `ReportService` **from the Spring context** (thus receiving async interception), invokes the `@Async("lessonExecutor")` method, and awaits the future with `get(5, TimeUnit.SECONDS)`. Inside the task, the current thread's name starts with that prefix, so `worker=true` is produced **on the worker**. `get` awaits the result with a timeout so the demo does not hang indefinitely if an error occurs.

In an overly slow environment, `get(5, ...)` may throw `TimeoutException`; that is a timing/unavailability issue to investigate, not a second output line. When creating a context manually in `main`, `try-with-resources` closes the context and lets the container clean up the executor bean; **never call `shutdown()` yourself inside `generate`**.

This example has three Java files compiled in the same package. The counterexamples in section 2 are analytical fragments **not** belonging to this project.

## 5. Distinguishing Three Commonly Confused Issues

### 5.1. Special Restriction of `@Configuration`

**Rule:** Methods **declared inside `@Configuration`** are not supported by Spring `@Async`. This is a condition based on **the kind of class containing the declaration**, not merely a caller forgetting to use a proxy.

**Fix:** Move the business method to a service/component bean, keeping `@Configuration` to enable `@EnableAsync` and define executors/dependencies. Call that service through the Spring proxy.

### 5.2. Self-Invocation on a Normal Bean

Even on an eligible `@Service` class, calling one method from another **within the same instance** normally bypasses the Spring proxy when using the default `AdviceMode.PROXY`.

~~~java
@Service
public class DataService {
    public void start() {
        calculate(); // this.calculate(), does not go through proxy
    }

    @Async
    public void calculate() {
        // Does not switch threads when called directly from start() as above.
    }
}
~~~

This is an **illustrative fragment**, requiring imports for `Service` and `Async`; not a standalone program. Unlike the `@Configuration` restriction, `calculate()` here *can be supported* when another bean calls it through the **`DataService` proxy**. The usual fix is extracting the call to another bean and injecting the Spring-managed service, or designing an interface for the async boundary.

For self-invocation on a regular service, Spring also offers `AdviceMode.ASPECTJ` and weaving as an advanced option. It requires separate dependencies/configuration and must not be treated as a reason to keep business `@Async` methods in `@Configuration`.

### 5.3. Lifecycle and Bean Initialization

Do not place `@Async` directly on `@PostConstruct` expecting it to run in the background: Spring documentation explicitly states the two mechanisms must not be combined. During bean initialization, proxies and dependencies may not yet be ready to perform asynchronous calls as designed.

If warm-up or post-startup processing is needed, have **another initializer bean** listen for a lifecycle/event and call the `@Async` method on an injected **service bean**. With Spring Boot, an `ApplicationReadyEvent` listener can be used when work genuinely must start after the application is ready; choose events and error policies per application needs. Never call an async method inside the object's own constructor or `@PostConstruct` expecting proxy interception.

### Diagnostic Table

| Symptom | Causes to Check | Resolution |
| --- | --- | --- |
| `@Async` placed on a method in `@Configuration` | Method belongs to an unsupported area | Move to a service bean |
| `@Async` service method still runs on caller | Self-invocation, object created with `new`, missing `@EnableAsync`, or proxy bypassed | Retrieve bean from Spring context, call via proxy, verify configuration |
| `@Async("name")` does not use expected thread pool | Executor bean has wrong name/qualifier or different config | Check `@Bean("name")`, injection, and thread prefix |
| `@Async` method fails while running | Exception in task and how errors are received via `Future`/`CompletableFuture` | Observe future or `AsyncUncaughtExceptionHandler` if `void` |
| Async method rejected before running | Executor overloaded or already shut down | Handle `TaskRejectedException` at submit point, inspect queue and lifecycle |
| Calling async during bean construction | Lifecycle not suitable yet | Call from another bean after context is ready |

## 6. Return Types and Error Handling for @Async

Spring `@Async` supports methods returning `void` or a valid `Future`, including `CompletableFuture<T>`. Methods meant to return business data should use `CompletableFuture<T>` so callers can wait, combine results, and handle errors.

~~~java
// Fragment inside @Service with configured async proxy and executor.
@Async("lessonExecutor")
public CompletableFuture<Integer> calculate(int x) {
    if (x < 0) {
        throw new IllegalArgumentException("x must be non-negative");
    }
    return CompletableFuture.completedFuture(x * 2);
}
~~~

This is a **fragment**, not a standalone class. If the task is accepted but throws an exception on the worker, the `CompletableFuture` received by the caller completes exceptionally. Callers use `get()` to receive `ExecutionException` (inspect cause) or `join()` to receive `CompletionException`; respect interrupts when using `get()`.

~~~java
// Fragment in caller, method declares throws InterruptedException.
CompletableFuture<Integer> future = service.calculate(21);
try {
    System.out.println(future.get()); // 42
} catch (java.util.concurrent.ExecutionException ex) {
    System.err.println("Task failed: " + ex.getCause());
}
~~~

Do not put `@Async` on a method returning `String`/`int` directly expecting Spring to wrap the value in a Future; that is not a supported return type under the annotation contract.

With `@Async void` methods, callers have no Future to receive worker errors. Spring allows configuring `AsyncUncaughtExceptionHandler` via `AsyncConfigurer`; by default, errors are typically logged. In production applications, never let critical tasks fail without an observation/status-reporting mechanism.

Another failure occurs **at task submission time**: the executor may throw `TaskRejectedException` if the pool is overloaded or shut down. When that happens, no work was accepted; `future.exceptionally(...)` alone does not replace catching rejection at the caller boundary. Queue/backpressure configuration and overload handling policies are separate parts of async design.

## 7. Safe Refactoring: From Mixed Business Config to Two Beans

Suppose a legacy project has a business method `sendInvoice()` inside `@Configuration` annotated with `@Async`. Fix it in order:

1. **Reassign responsibilities:** Keep `@Configuration` for bean definitions and `@EnableAsync`. Move invoice-sending logic to `InvoiceSender` or an appropriate service.
2. **Preserve data contracts:** Use `CompletableFuture<Result>` on the service method if results are needed, or `void` if genuinely fire-and-forget with separate error handling. Do not change public signatures arbitrarily.
3. **Define the executor:** Create/reuse a `ThreadPoolTaskExecutor` bean with a stable name, sizing, and rejection suited to the workload.
4. **Update call sites:** Callers inject the Spring-managed `InvoiceSender`; do not instantiate with `new` or keep self-calls inside the config class.
5. **Check transactions/context:** The caller thread's transaction/MDC/security context is not automatically shared with workers. Pass required data, configure context propagation, and set transaction boundaries appropriately.
6. **Test actual behavior:** Verify executing threads via worker thread prefixes/IDs, inspect Future results, and test errors when the pool rejects tasks.
7. **Keep post-startup logic explicit:** If work must run at startup, have a separate initializer/event listener call the service through its proxy at the right time.

### Before and After Sketches

**Before — unsupported approach:**

~~~java
@Configuration
@EnableAsync
public class InvoiceConfig {
    @Async
    public CompletableFuture<String> sendInvoice() {
        return CompletableFuture.completedFuture("sent");
    }
}
~~~

**After — supported approach:**

~~~java
@Configuration
@EnableAsync
public class InvoiceConfig {
    // @Bean executor and other configuration dependencies.
}

// In a separate file, Spring-managed class:
@Service
public class InvoiceSender {
    @Async("invoiceExecutor")
    public CompletableFuture<String> sendInvoice() {
        return CompletableFuture.completedFuture("sent");
    }
}
~~~

The two snippets above are **architectural sketches**: they require annotation imports, an executor bean named `invoiceExecutor`, and callers going through the proxy. Only the Maven project in section 4 is a complete program runnable as-is.

### When the Service Is Created via `@Bean`

You are **not forced** to use `@Service` for every service. For example:

~~~java
@Configuration
@EnableAsync
class InvoiceBeans {
    @Bean
    InvoiceSender invoiceSender() {
        return new InvoiceSender();
    }

    @Bean("invoiceExecutor")
    ThreadPoolTaskExecutor invoiceExecutor() {
        ThreadPoolTaskExecutor executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(2);
        return executor;
    }
}
~~~

This is a **configuration fragment**, requiring imports and a **separate `InvoiceSender` class** containing the `@Async` method. `InvoiceSender` is managed by Spring because it is returned by `@Bean`; after container post-processing, the async proxy can apply to that object's methods. **The factory method `invoiceSender()` does not need `@Async`.**

Separating classes by responsibility is the essential requirement; how the bean is registered (`@Service` vs. `@Bean`) is a configuration choice.

## 8. Common Misconceptions

1. **"`@EnableAsync` on `@Configuration` is wrong because async isn't allowed in configuration."** False. Spring recommends putting `@EnableAsync` on `@Configuration`; the restriction applies only to **`@Async` on methods declared there**.
2. **"`@Async` on a `@Bean` method makes the created bean asynchronous."** Misuse. `@Bean` serves bean creation lifecycle; async business processing belongs on methods of the service bean.
3. **"You can set `proxyBeanMethods=false` so `@Async` inside config works."** No. That option changes `@Bean` method interception; it does not make config methods supported async methods.
4. **"Turning on `proxyTargetClass=true` solves everything."** No. It only changes proxy type; it does not alter `@Async`'s contract regarding `@Configuration`.
5. **"If a service is created via `@Bean`, its `@Async` methods are also forbidden."** False. The restriction is based on **where the method is declared**; the returned bean can be processed by Spring like any other bean.
6. **"An `@Async` method in `@Service` always runs in the background, even when called as `this.method()`."** False in default proxy mode: self-invocation bypasses the proxy.
7. **"`@Async` works automatically on objects created with `new`."** No. The bean must pass through container management/proxying or configured weaving.
8. **"Enabling `@EnableAsync` guarantees all tasks run smoothly regardless of executor."** No. Queues, worker counts, timeouts, rejection, data, and errors still must be designed.
9. **"Returning a Future means the method ran synchronously."** No. The proxy may return a Future representing the task; the method on the worker may return a completed future wrapping the actual result.
10. **"In-task errors and submission rejection follow the same path."** No. Rejection may throw before a Future is returned, whereas worker errors go into the Future or handler depending on the return type.

## 9. Self-Check Questions

**Q1.** Can you write `@Configuration @EnableAsync` on the same class?  
**A:** Yes. `@EnableAsync` is placed on configuration classes to enable asynchronous annotation processing.

**Q2.** Can you put `@Async` on a `generate()` method declared directly inside `@Configuration` and guarantee it runs in the background?  
**A:** No. Spring Javadoc explicitly states that methods inside `@Configuration` are not supported by `@Async`.

**Q3.** If a `@Bean` in config returns `ReportService`, and `ReportService.generate()` has `@Async`, does the restriction apply?  
**A:** Not in that way; `generate()` is declared on `ReportService`. The bean must be Spring-managed and called through the async proxy for interception to occur.

**Q4.** A `@Service` calls `this.calculateAsync()` within the same class. Why might it run synchronously?  
**A:** With `AdviceMode.PROXY`, internal calls bypass the proxy. Call the method through the bean proxy from another class.

**Q5.** Why does Spring use a CGLIB proxy for `@Configuration`, yet methods inside it still shouldn't have `@Async`?  
**A:** CGLIB enhancement of config handles `@Bean`/scoping. It does not change the `@Async` annotation's support contract for methods declared in config.

**Q6.** If you want asynchronous warm-up after the application is ready, how should you organize it?  
**A:** Use an appropriate initializer/listener bean that calls an `@Async` method on another service bean through the Spring proxy; do not put `@Async` directly on `@PostConstruct` or on methods inside `@Configuration`.

## 10. Official References

- [Spring Framework 6.2.7 — Async Javadoc](https://docs.spring.io/spring-framework/docs/6.2.7/javadoc-api/org/springframework/scheduling/annotation/Async.html): explicitly specifies `@Async` is not supported on methods declared in `@Configuration` classes; `void`/`Future`/`CompletableFuture` return types.
- [Spring Framework 5.3.36 — Async Javadoc](https://docs.spring.io/spring-framework/docs/5.3.36/javadoc-api/org/springframework/scheduling/annotation/Async.html): confirms the same restriction exists in the 5.3 branch.
- [Spring Framework 6.1.11 — EnableAsync Javadoc](https://docs.spring.io/spring-framework/docs/6.1.11/javadoc-api/org/springframework/scheduling/annotation/EnableAsync.html): placing `@EnableAsync` on `@Configuration`, proxy mode, and self-invocation.
- [Spring Framework 6.1.3 — Configuration Javadoc](https://docs.spring.io/spring-framework/docs/6.1.3/javadoc-api/org/springframework/context/annotation/Configuration.html): `@Bean`, config class enhancement, `proxyBeanMethods`, and bootstrapping.
- [Spring Framework Reference — Task Execution and Scheduling](https://docs.spring.io/spring-framework/reference/integration/scheduling.html): `@EnableAsync`, `@Async`, executor selection, return types, and exception handling.
