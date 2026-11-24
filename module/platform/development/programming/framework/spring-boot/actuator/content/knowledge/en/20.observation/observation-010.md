# Propagating Context Across Threads, Async Tasks, and Reactor

## 1. Why Does Switching Threads Lose the Relationship Between Operations?

An HTTP request may be observed on the initial handling thread, then submit work to an executor or continue inside a Reactor chain. Business code still runs properly, yet the operation in the new location may not know which request it belongs to. In that case, child measurements or spans can lack parent–child relationships; logs can also miss correlation information if logging infrastructure relies on the current context.

Observation context is the information identifying the running operation and its relationship to other operations. Three things must be distinguished:

- **Creating an observation:** starting an observation for an operation.
- **Putting an observation in scope:** making that observation the current observation within an execution block.
- **Propagating context:** carrying existing context information across an execution boundary, then restoring it where it is needed.

Propagating context does not automatically create another measurement for every task. If you need to measure child work separately, create a child observation once the parent context has been restored. Micrometer also clearly separates context propagation from creating observations. [Micrometer: instrumentation and context propagation](https://docs.micrometer.io/micrometer/reference/1.13/observation/instrumenting.html).

In synchronous code, the current observation is usually accessed via thread-bound state. On another thread, you cannot assume that state is already present. In Reactor, a single chain can run across multiple threads, and a single thread can serve multiple subscriptions. Therefore, choosing the right place to store context is decisive.

## 2. Three Context Storage Mechanisms to Distinguish

| Mechanism | Where does context attach? | Key point to note |
| --- | --- | --- |
| `ThreadLocal` | Currently running thread | Switching threads does not automatically carry the submitting thread's value; thread pools also reuse threads |
| `ContextSnapshot` | Values captured at a point in time | Holds only information readable by registered accessors; must be restored in a properly closed scope |
| Reactor `Context` | Subscriber/subscription in a reactive chain | Data travels with the processing chain, independent of a single fixed thread |

`ObservationRegistry` and `ContextRegistry` are also two distinct registries:

- `ObservationRegistry` serves observations: handlers, configuration, and the current observation.
- `ContextRegistry` knows how to read/write context types via accessors.
- `ObservationThreadLocalAccessor` is the bridge for the current observation.
- `ContextSnapshotFactory` uses registered accessors to create snapshots.
- `ContextSnapshot.Scope` bounds how long restored values remain on the target thread.

A snapshot does not scan and copy every `ThreadLocal` in the JVM. Nor is it a deep copy of all business objects: a carried value can still be a reference to the same object. Do not treat propagation as a synchronization mechanism for shared mutable data. [Purpose and components of Context Propagation](https://docs.micrometer.io/context-propagation/reference/1.1/purpose.html).

Do not use `InheritableThreadLocal` as a general fix for thread pools: inheritance at thread creation differs from propagating context per task submitted to an existing thread. Switching to virtual threads also does not replace defining context boundaries and lifecycles.

## 3. The Proper Flow: capture → submit task → restore → clean up scope

```text
Submitting thread, currently holding context A
  -> capture snapshot A at the work submission boundary
  -> submit wrapped task

Executing thread
  -> remember previous state
  -> restore A
  -> run work
  -> finally: restore previous state

Next task on the same thread
  -> must not see A left behind by the previous task
```

### 3.1. Capture While the Desired Context Is Still Current

Simply calling `Observation.start(...)` does not mean that observation has become current on the thread. In imperative code, an open scope—or a call like `observe(...)` that manages scope—is needed before capturing current values.

Core example, used inside a method that already has `parent`, `factory`, and an executor:

```java
try (Observation.Scope scope = parent.openScope()) {
    var snapshot = factory.captureAll();
    executor.submit(snapshot.wrap(task));
}
```

This snippet illustrates the capture boundary, not a standalone program. Waiting on the task and managing `parent`'s lifecycle must be decided by the enclosing layer; do not infer that closing the scope on the submitting thread ends the async work.

Do not capture a snapshot once at application startup and reuse it for all requests. The factory and executor can be long-lived, yet each request's context snapshot must be taken at the appropriate point.

### 3.2. Scope Must Be Opened and Closed at the Execution Site

You can let `snapshot.wrap(...)` manage scope or restore manually with:

```java
try (var restored = snapshot.setThreadLocals()) {
    runBusinessWork();
}
```

`snapshot` and `runBusinessWork()` belong to the enclosing code. Upon exiting the block, the thread's previous values are restored; if there was no prior value, the propagated value must not remain behind. The block must still close when the work throws an exception. Do not open a scope on thread A and pass that same scope object to thread B to close. [Examples of capture and scope restoration](https://docs.micrometer.io/context-propagation/reference/1.1/usage.html).

Depending on policy, the factory can use `clearMissing(true)` to temporarily clear values of registered accessors that are absent in the snapshot. That prevents a new task from accidentally seeing a stale value on the target thread within the restored scope. It does not replace closing the scope, and does not clear arbitrary `ThreadLocal`s outside accessors known to the factory.

### 3.3. Scope and Observation Lifetime Are Two Different Things

Closing a scope is not `stop()`ing the observation. A snapshot also does not extend an observation's lifetime, end it automatically, or record business errors automatically.

If a task must belong to a live parent observation, the coordinator must wait or arrange for the parent observation to stop at the right time. For work genuinely detached from the request lifecycle, design a separate observation and appropriate causal link. Do not hold a request object or request snapshot indefinitely just to keep the same correlation ID in logs.

When multiple tasks run concurrently, do not mutate the same `Observation.Context` arbitrarily like a shared map. Propagation helps locate context; it does not make arbitrary updates thread-safe under concurrency.

## 4. Executor, CompletableFuture, and @Async

### 4.1. A Raw Executor Does Not Mean Context Is Wired

Submitting a `Runnable` or `Callable` to a plain `ExecutorService` merely submits work. The lambda may capture a reference to the registry, yet `registry.getCurrentObservation()` is still evaluated on the executing thread.

There are two common approaches:

- Capture a snapshot on the submitting side, then wrap each task.
- Use an executor or decorator that captures on each work submission.

Micrometer provides executor wrappers; with Spring Framework 6.1, `ContextPropagatingTaskDecorator` provides snapshot-based task wrapping. You must attach the decorator to the executor actually in use. Merely creating a decorator object without wiring it into the executor changes nothing about the execution path. [ContextPropagatingTaskDecorator API](https://docs.spring.io/spring-framework/docs/6.1.5/javadoc-api/org/springframework/core/task/support/ContextPropagatingTaskDecorator.html).

### 4.2. CompletableFuture Has Multiple Distinct Boundaries

`CompletableFuture.supplyAsync(...)` does not propagate context merely because the caller has an active observation. When no executor is specified, it typically uses the JDK default pool; that pool knows nothing about an application's custom decorator config.

The example below specifies the executor explicitly; `raw`, `factory`, and `work` are already declared in surrounding code:

```java
Executor propagated = task -> raw.execute(factory.captureAll().wrap(task));
CompletableFuture<String> result =
        CompletableFuture.supplyAsync(work, propagated);
```

Here, a snapshot is captured each time `execute` receives a task, on the thread calling `execute`.

For chained callbacks such as `thenApplyAsync`, you must also consider **which thread submits the callback to the executor**. A callback may be registered while context A is open, yet only submitted to the executor later by the thread completing the source future. Capturing when the executor receives the task reflects the submitting thread's context at that moment, not automatically context A from callback registration time.

If the requirement is preserving context at registration time, capture explicitly at that moment and restore inside the callback:

```java
var captured = factory.captureAll();
var next = source.thenApplyAsync(value -> {
    try (var scope = captured.setThreadLocals()) {
        return transform(value);
    }
}, raw);
```

This is illustrative code in a method that already has `source`, `factory`, `raw`, and `transform`. The coordinator must still ensure the referenced context's lifecycle is appropriate.

Callbacks without the `Async` suffix are also not guaranteed to always run on the thread that registered them: they may run on the thread completing the future. Test the actual execution path rather than inferring from method names.

### 4.3. @Async Must Point to the Configured Executor

With Spring, `@Async` normally works via proxy. You must invoke the method from another bean or through a bean retrieved from the context; a `this` self-invocation does not turn into a proxied async call on its own.

Configuring an explicit executor name and using `@Async("observedExecutor")` ensures the right execution path. A decorator on executor A does not automatically apply to executor B, `new Thread(...)`, the common pool, every Reactor scheduler, or every `parallelStream()` call.

Propagation also does not handle `CompletableFuture` results and exceptions for you. The caller still needs to observe the returned future. If catching exceptions on the caller side, do not assume the parent observation was automatically marked with an error just because context was restored.

## 5. Experiment 1: Thread Pool, CompletableFuture, and @Async

### 5.1. Preparing Dependencies

The two programs in this lesson use JDK 21, Spring Framework 6.1.8, Micrometer 1.13.0, Context Propagation 1.1.1, and Reactor 3.6.6. These versions belong to the Boot 3.3.0 library generation, pinned for a standalone lab directory.

Create `pom.xml` in a separate directory:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>context-demo</artifactId>
    <version>1.0.0</version>
    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.8</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>micrometer-observation</artifactId>
            <version>1.13.0</version>
        </dependency>
        <dependency>
            <groupId>io.micrometer</groupId>
            <artifactId>context-propagation</artifactId>
            <version>1.1.1</version>
        </dependency>
        <dependency>
            <groupId>io.projectreactor</groupId>
            <artifactId>reactor-core</artifactId>
            <version>3.6.6</version>
        </dependency>
    </dependencies>
</project>
```

Maven resolves transitive dependencies such as `micrometer-commons` and `reactive-streams`. This is a plain Spring experiment to show the mechanism clearly. In an existing Boot application, use Boot's dependency management rather than copying this full version list.

### 5.2. Complete ThreadContextDemo.java

Save in the same directory as `pom.xml`, with no package declaration:

```java
import java.util.concurrent.Callable;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Executor;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;

import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.Async;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

public class ThreadContextDemo {
    public static void main(String[] args) throws Exception {
        try (var context = new AnnotationConfigApplicationContext(Config.class);
             var raw = Executors.newSingleThreadExecutor()) {
            var registry = context.getBean(ObservationRegistry.class);
            var factory = context.getBean(ContextSnapshotFactory.class);
            var asyncWork = context.getBean(AsyncWork.class);

            System.out.println("worker.before=" + await(raw.submit(() -> name(registry))));
            Observation parent = Observation.start("request.a", registry);
            try (var scope = parent.openScope()) {
                System.out.println("caller=" + name(registry));
                System.out.println("worker.raw=" + await(raw.submit(() -> name(registry))));

                var snapshot = factory.captureAll();
                Callable<String> read = () -> name(registry);
                System.out.println("worker.snapshot="
                        + await(raw.submit(snapshot.wrap(read))));

                Executor propagated = task ->
                        raw.execute(factory.captureAll().wrap(task));
                System.out.println("future.raw=" + await(CompletableFuture
                        .supplyAsync(() -> name(registry), raw)));
                System.out.println("future.propagated=" + await(CompletableFuture
                        .supplyAsync(() -> name(registry), propagated)));
                System.out.println("async=" + await(asyncWork.currentName()));

                try {
                    await(raw.submit(snapshot.wrap((Callable<String>) () -> {
                        throw new IllegalStateException("demo");
                    })));
                    throw new AssertionError("Expected task failure");
                } catch (ExecutionException ex) {
                    System.out.println("failure=" + ex.getCause().getClass().getSimpleName());
                }
                String after = await(raw.submit(() -> name(registry)));
                System.out.println("worker.after.failure=" + after);
                if (!"<none>".equals(after)) {
                    throw new AssertionError("Worker context leaked");
                }
            } finally {
                parent.stop();
            }
            String nextTask = await(asyncWork.currentName());
            System.out.println("async.next.task=" + nextTask);
            System.out.println("caller.after=" + name(registry));
            if (!"<none>".equals(nextTask) || registry.getCurrentObservation() != null) {
                throw new AssertionError("Unexpected next task context");
            }
        }
    }

    static String name(ObservationRegistry registry) {
        Observation current = registry.getCurrentObservation();
        return current == null ? "<none>" : current.getContext().getName();
    }

    static <T> T await(Future<T> future) throws Exception {
        return future.get(5, TimeUnit.SECONDS);
    }

    public static class AsyncWork {
        private final ObservationRegistry registry;

        public AsyncWork(ObservationRegistry registry) {
            this.registry = registry;
        }

        @Async("observedExecutor")
        public CompletableFuture<String> currentName() {
            return CompletableFuture.completedFuture(name(registry));
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableAsync
    public static class Config {
        @Bean
        ObservationRegistry observationRegistry() {
            var registry = ObservationRegistry.create();
            registry.observationConfig().observationHandler(
                    new ObservationHandler<Observation.Context>() {
                        @Override
                        public boolean supportsContext(Observation.Context context) {
                            return true;
                        }
                    });
            return registry;
        }

        @Bean
        ContextSnapshotFactory snapshots(ObservationRegistry registry) {
            var contexts = new ContextRegistry();
            contexts.registerThreadLocalAccessor(
                    new ObservationThreadLocalAccessor(registry));
            return ContextSnapshotFactory.builder()
                    .contextRegistry(contexts).clearMissing(true).build();
        }

        @Bean
        ThreadPoolTaskExecutor observedExecutor(ContextSnapshotFactory factory) {
            var executor = new ThreadPoolTaskExecutor();
            executor.setCorePoolSize(1);
            executor.setMaxPoolSize(1);
            executor.setQueueCapacity(10);
            executor.setThreadNamePrefix("observed-");
            executor.setTaskDecorator(new ContextPropagatingTaskDecorator(factory));
            return executor;
        }

        @Bean
        AsyncWork asyncWork(ObservationRegistry registry) {
            return new AsyncWork(registry);
        }
    }
}
```

The minimal handler makes the registry actually process observations in the experiment; it exports no metrics or traces to a monitoring system. A separate `ContextRegistry` registers only the observation accessor, making it clear which data type is being propagated.

The program awaits tasks inside the parent scope and stops the observation in `finally`. Consequently, tasks in the experiment are not left running after the parent observation has stopped.

### 5.3. Run Commands and Stdout

In PowerShell, select JDK 21 for both `javac` and `java`, then run each command once the previous one succeeds:

```powershell
mvn org.apache.maven.plugins:maven-dependency-plugin:3.7.0:build-classpath "-Dmdep.outputFile=classpath.txt"
$demoClasspath = (Get-Content -Raw classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp "$demoClasspath" ThreadContextDemo.java
java -cp ".;$demoClasspath" ThreadContextDemo
```

The first run downloads dependencies from Maven repositories. `;` is the classpath separator on Windows; Linux/macOS uses `:`.

Program stdout, excluding Maven output:

```text
worker.before=<none>
caller=request.a
worker.raw=<none>
worker.snapshot=request.a
future.raw=<none>
future.propagated=request.a
async=request.a
failure=IllegalStateException
worker.after.failure=<none>
async.next.task=<none>
caller.after=<none>
```

Evidence to read together:

| Result | What is verified |
| --- | --- |
| `caller=request.a` yet `worker.raw=<none>` | The current observation on the submitting thread is not automatically present on the executor thread |
| `worker.snapshot=request.a` | A snapshot wrapping the callable restores the observation |
| `future.raw=<none>`, `future.propagated=request.a` | CompletableFuture using an executor with propagation finds the context |
| `async=request.a` | Calls through the `@Async` proxy use the decorated executor |
| `failure=IllegalStateException` | Task exceptions still reach the caller awaiting the future |
| `worker.after.failure=<none>` | The next raw task on the same executor does not see a leaked observation after a failure |
| `async.next.task=<none>` | An `@Async` task submitted after the parent scope closes does not carry the previous request's context |
| `caller.after=<none>` | Scope on the submitting thread was closed |

Do not include thread names or run durations in fixed stdout expectations: they depend on the environment. Results about observations and scopes are what the experiment needs to prove.

## 6. Applying a Configured Executor in Spring Boot

In a Boot application, use the registry provided by Actuator infrastructure. Do not copy the experiment's `observationRegistry()` bean to replace the registry Boot already wired to metrics/tracing.

With a build already using Boot's plugin/BOM, ensure the matching dependencies are present:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:context-propagation'
}
```

Applications using Reactor also need Reactor dependencies from their reactive stack selection. You do not need to switch an application to WebFlux just to use the task decorator.

Configuration example within the application's component-scan scope:

```java
package example.context;

import io.micrometer.context.ContextRegistry;
import io.micrometer.context.ContextSnapshotFactory;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.task.support.ContextPropagatingTaskDecorator;
import org.springframework.scheduling.annotation.EnableAsync;
import org.springframework.scheduling.concurrent.ThreadPoolTaskExecutor;

@Configuration(proxyBeanMethods = false)
@EnableAsync
public class AsyncObservationConfig {
    @Bean("observedExecutor")
    ThreadPoolTaskExecutor observedExecutor(ObservationRegistry observations) {
        var contexts = new ContextRegistry();
        contexts.registerThreadLocalAccessor(
                new ObservationThreadLocalAccessor(observations));
        var snapshots = ContextSnapshotFactory.builder()
                .contextRegistry(contexts)
                .clearMissing(true)
                .build();

        var executor = new ThreadPoolTaskExecutor();
        executor.setCorePoolSize(2);
        executor.setMaxPoolSize(4);
        executor.setQueueCapacity(100);
        executor.setThreadNamePrefix("observed-");
        executor.setTaskDecorator(new ContextPropagatingTaskDecorator(snapshots));
        return executor;
    }
}
```

In another service bean, use `@Async("observedExecutor")` like `AsyncWork` in the experiment. Spring manages initializing and shutting down `ThreadPoolTaskExecutor` when it is a bean; do not call `initialize()` again inside the bean factory method above.

The factory here uses a dedicated `ContextRegistry`, explicitly registering the accessor with Boot's registry. This configuration proactively propagates **observations** for this executor. If the application uses the global registry with multiple pre-configured accessors, an appropriate shared factory/decorator may be used; verify in practice that all required accessors are present.

Do not assume every MDC value, security context, transaction, or request object is copied. Log correlation requires matching tracing/logging integration; other context types require their own mechanisms or properly designed accessors. Propagating an observation does not open a database transaction on the new thread.

Pool sizes and queue parameters in the example are solely illustrative configuration. Adjust them to the workload type and the application's overload handling. Capturing/restoring has overhead; measure the impact under realistic task volume, especially with very many tiny tasks.

## 7. Reactor Context and the Bridge to ThreadLocal

### 7.1. Subscription Context Differs from Assembly-Thread Context

In Reactor, a subscription is one execution run of a chain; a subscriber is the consumer receiving signals. Use `Context`/`ContextView` to carry information along a subscription. `Context` is immutable in the sense that add/remove operations return a new context; values stored inside can still be mutable objects.

`Mono.deferContextual(...)` reads context at subscribe time. `contextWrite(...)` enriches context for upstream operators within the corresponding chain range. Operator placement therefore matters; a variable placed on a ThreadLocal when building a `Mono` does not automatically become data for every subsequent subscription.

`publishOn` and `subscribeOn` can change where execution happens, yet do not turn ThreadLocal into reliable context storage for the entire pipeline. Context references must travel with the subscription and be restored when imperative code needs to read them.

### 7.2. Default Mode and Automatic Mode

When a compatible `context-propagation` library is present, Reactor provides a bridge between Reactor Context and registered ThreadLocals.

- In the limited default mode, some operators such as `handle` and `tap` support restoration; do not assume every callback in every operator has the right ThreadLocal.
- Automatic mode is enabled via `Hooks.enableAutomaticContextPropagation()`, or the corresponding Boot property. This mechanism restores registered ThreadLocals based on Reactor Context across supported Reactor boundaries.

In Boot 3.3.x, configuration:

```yaml
spring:
  reactor:
    context-propagation: auto
```

This property is for the Reactor bridge; it does not automatically attach a task decorator to every executor the application creates itself. [Spring Boot: context propagation](https://docs.spring.io/spring-boot/3.3/reference/actuator/observability.html).

In a standalone Reactor program, enable the hook once at startup, before subscriptions that need it. The hook acts JVM-wide and applies to new subscriptions; do not toggle it on/off per request. [Reactor 3.6.6: context propagation](https://projectreactor.io/docs/core/3.6.6/reference/#context.propagation).

### 7.3. contextWrite and contextCapture Serve Two Opposite Directions

| Operator | Data source | Timing and purpose |
| --- | --- | --- |
| `contextWrite` | Known value or existing context | Puts data into Reactor Context for the corresponding upstream scope |
| `contextCapture` | Registered ThreadLocals on the subscribing thread | Captures at subscribe time and puts values into Reactor Context |

When placing a known observation into Reactor Context, use the key understood by the accessor, such as `ObservationThreadLocalAccessor.KEY`. When crossing from imperative code with an active scope into Reactor, `contextCapture()` is an option to bring current values into context.

Distinguish pipeline assembly time from subscribe time. If a scope was only open when constructing the `Mono` and closed before subscription, `contextCapture()` cannot travel back in time to find the old context.

In automatic mode, blocking operators such as `Mono.block()` support implicit capture. That can make an example using `block()` pass even while another subscribe boundary in the application still lacks data. Do not assume an arbitrary `subscribe()` call has the same implicit capture mechanism. In WebFlux, return the reactive chain so the framework subscribes and preserves existing context, rather than spawning a detached `subscribe()`.

If you only need to read information from Reactor Context with `deferContextual`, you do not necessarily have to bridge everything back to ThreadLocal. The bridge is useful when calling imperative libraries that expect a current observation on the thread.

## 8. Experiment 2: Same Reactor Context, Two Different Modes

The following program uses the dependencies from Section 5. It runs in a separate JVM so it can intentionally toggle the hook for comparison without affecting another application.

### 8.1. Complete ReactorContextDemo.java

Save alongside `pom.xml`:

```java
import java.time.Duration;

import io.micrometer.context.ContextRegistry;
import io.micrometer.observation.Observation;
import io.micrometer.observation.ObservationHandler;
import io.micrometer.observation.ObservationRegistry;
import io.micrometer.observation.contextpropagation.ObservationThreadLocalAccessor;
import reactor.core.publisher.Hooks;
import reactor.core.publisher.Mono;
import reactor.core.scheduler.Scheduler;
import reactor.core.scheduler.Schedulers;

public class ReactorContextDemo {
    public static void main(String[] args) {
        var registry = ObservationRegistry.create();
        registry.observationConfig().observationHandler(
                new ObservationHandler<Observation.Context>() {
                    @Override
                    public boolean supportsContext(Observation.Context context) {
                        return true;
                    }
                });

        var accessor = ObservationThreadLocalAccessor.getInstance();
        accessor.setObservationRegistry(registry);
        ContextRegistry.getInstance().registerThreadLocalAccessor(accessor);

        Scheduler worker = Schedulers.newSingle("reactor-demo");
        Observation parent = Observation.start("reactor.parent", registry);
        try {
            String limited = read(registry, worker)
                    .contextWrite(ctx -> ctx.put(ObservationThreadLocalAccessor.KEY, parent))
                    .block(Duration.ofSeconds(5));
            System.out.println("limited: " + limited);

            Hooks.enableAutomaticContextPropagation();

            String automatic = read(registry, worker)
                    .contextWrite(ctx -> ctx.put(ObservationThreadLocalAccessor.KEY, parent))
                    .block(Duration.ofSeconds(5));
            System.out.println("automatic: " + automatic);

            try (var scope = parent.openScope()) {
                String captured = read(registry, worker)
                        .contextCapture()
                        .block(Duration.ofSeconds(5));
                System.out.println("captured: " + captured);
            }

            String clean = Mono.fromCallable(() -> name(registry))
                    .subscribeOn(worker)
                    .block(Duration.ofSeconds(5));
            System.out.println("worker.next.subscription=" + clean);
            System.out.println("caller.after=" + name(registry));

            if (!"context=reactor.parent, current=<none>".equals(limited)
                    || !"context=reactor.parent, current=reactor.parent".equals(automatic)
                    || !"<none>".equals(clean)
                    || registry.getCurrentObservation() != null) {
                throw new AssertionError("Unexpected Reactor context");
            }
        } finally {
            parent.stop();
            worker.dispose();
            Hooks.disableAutomaticContextPropagation();
            ContextRegistry.getInstance()
                    .removeThreadLocalAccessor(ObservationThreadLocalAccessor.KEY);
        }
    }

    static Mono<String> read(ObservationRegistry registry, Scheduler worker) {
        return Mono.deferContextual(ctx -> Mono.fromCallable(() -> {
            Observation fromContext = ctx.get(ObservationThreadLocalAccessor.KEY);
            return "context=" + fromContext.getContext().getName()
                    + ", current=" + name(registry);
        }).subscribeOn(worker));
    }

    static String name(ObservationRegistry registry) {
        Observation current = registry.getCurrentObservation();
        return current == null ? "<none>" : current.getContext().getName();
    }
}
```

The registry is attached to the accessor so `getCurrentObservation()` calls and the bridge share the same observation system. Registering the accessor and toggling the hook here is explicit setup for a standalone program. In Boot, use the integration and registry the application already configured; do not run global hook cleanup operations during request handling.

`read(...)` reads the observation from Reactor Context via `deferContextual`; the callable runs on a dedicated scheduler and simultaneously reads the current observation from the registry. The returned string thus shows both data in Context and ThreadLocal state at the execution site.

### 8.2. Compiling and Running

Use `classpath.txt` generated in the previous experiment:

```powershell
$demoClasspath = (Get-Content -Raw classpath.txt).Trim()
javac --release 21 -encoding UTF-8 -cp "$demoClasspath" ReactorContextDemo.java
java -cp ".;$demoClasspath" ReactorContextDemo
```

Stdout:

```text
limited: context=reactor.parent, current=<none>
automatic: context=reactor.parent, current=reactor.parent
captured: context=reactor.parent, current=reactor.parent
worker.next.subscription=<none>
caller.after=<none>
```

Explanation:

1. **Limited:** Context already held the observation, so reading directly from `ContextView` succeeds. The callable callback on another thread does not automatically have a current observation in this mode.
2. **Automatic:** On new subscriptions after enabling the hook, the observation in Context is restored so code in the callback can read it via the registry.
3. **Captured:** Scope was open at subscribe time; `contextCapture()` places the current observation into Context. In automatic mode, `block()` also performs implicit capture, so this line illustrates a valid capture boundary rather than proving `contextCapture()` is always mandatory before `block()`.
4. **Next subscription:** The next subscription on the same scheduler, supplying no parent observation, reads `<none>`. An earlier subscription's observation is never used as a default context.
5. **Caller after:** The imperative scope was closed and the calling thread has no current observation.

The example only propagates an existing observation; it does not create a new observation per operator. Reading the same name twice is not proof that two extra spans were created.

## 9. Boundaries That Propagation Does Not Handle Automatically

### 9.1. Errors, Cancellation, and Completion Timing

A propagation scope must be cleaned up even on errors. In reactive code, cancellation signals also matter. If creating your own observation for a subscription, design creation per subscription and stop it properly on completion, error, or cancel; do not reuse one mutable pre-created observation outside the pipeline across all subscriptions.

Do not open an imperative scope, return an unexecuted `Mono`, and assume that scope stays alive until the chain completes. Use Reactor Context and appropriate reactive instrumentation. Where the framework already manages the observation, avoid adding a competing lifecycle.

Restoring context also does not automatically cancel child tasks when a request is canceled, does not apply timeouts, and does not automatically turn future failures into observation errors. Those require separate coordination policies and instrumentation.

### 9.2. Logging, Tracing, Transactions, and Security Are Separate Contracts

Seeing the same observation on a new thread only proves that context was propagated. Having spans appear in a backend also requires a tracing bridge, handlers, exporter, and sampling config. Having correlation IDs in logs also requires the corresponding logging integration.

Do not treat an observation snapshot as a way to carry arbitrary permissions, login sessions, or transactions onto a new thread. If the application needs to propagate other context types, configure and test the mechanism for those types separately.

Across network boundaries or message brokers, you also need context injection/extraction via headers/carriers and protocol instrumentation. An in-JVM `ContextSnapshot` does not automatically send info over HTTP or Kafka.

## 10. Testing and Isolating Failures

A realistic test suite should cover:

- Request A propagates the right context across every boundary that must be supported.
- Request B running next on the same pool/scheduler receives B, not A.
- A task with no context does not pick up values from the prior request.
- A task throwing an exception still restores thread state.
- Nested scopes return the outer context after closing.
- Reactor chains re-subscribed, failing, and canceled all have proper lifecycles when the app manages observations itself.
- A future callback completing on another thread still follows the chosen capture policy.

Use explicit synchronization, timeouts, and observation/context assertions; avoid using `Thread.sleep(...)` as proof that propagation works.

| Symptom | What to check |
| --- | --- |
| Submitting thread has observation yet executor lacks it | Was the task captured/wrapped, and was the right executor used? |
| Snapshot lacks the expected observation | Did capture happen while scope was open; does accessor point to the right registry? |
| @Async runs yet loses context | Actual executor name and attached decorator; do not check the annotation alone |
| @Async does not switch threads | Was it called via proxy, is async enabled, was it a `this` self-invocation? |
| Initial future is right yet downstream callbacks are wrong | Thread submitting the callback and capture timing at each stage |
| Reactor Context has value yet registry returns null | Restoration mode, accessor, operator, and location needing ThreadLocal |
| Reactor works with block sometimes yet fails on other subscribes | Capture at subscribe time and implicit capture by `block` in automatic mode |
| Previous request's data appears in next request | Unclosed scope, snapshot reused out of scope, or shared mutable state |
| Automatic Reactor mode enabled yet custom executor still fails | Two independent mechanisms; custom executors still need propagation wired |
| Context exists yet no span appears in backend | Check tracing configuration and export separately |

## 11. Practice Exercises

1. Run both programs as-is and verify stdout.
2. Remove `setTaskDecorator(...)` in Experiment 1. Predict and check the `async` line specifically; leave the snapshot and wrapped-executor paths unchanged.
3. Capture the snapshot before opening the parent scope. Explain why wrapped work does not receive the expected observation.
4. Add an observation `request.b`, submit a task to the same pool, and then submit an unscoped task. Verify B and `<none>` in sequence.
5. In the Reactor experiment, keep `contextWrite` without enabling the hook. Explain why reading Context still succeeds while reading current observation in the callback can be `<none>`.
6. Design a `thenApplyAsync` callback registered on thread A while the source future completes on thread B. Compare capturing at registration time versus capturing when the executor accepts the task.

When evaluating results, state clearly where the context came from, when it was captured, in which scope it was restored, and where it was cleaned up.
