# `SimpleThreadScope` in Spring: Registration, How It Works, and Resource Cleanup Limitations

## 1. Objective and scope

`SimpleThreadScope` is an implementation of the `org.springframework.beans.factory.config.Scope` interface, located in `org.springframework.context.support`. It keeps **one instance per bean name for each Java thread** within the scope of a single scope object registered with `BeanFactory`. When the same thread requests the bean with the same name again, Spring returns the stored instance; when a different thread requests it, the scope creates or retrieves that thread's own instance.

This lesson focuses on: how to register it because the scope is **not available by default**, how `ThreadLocal` governs the lifecycle, behavior in thread pools and `@Async`, its severe limitation regarding destruction callbacks, how to perform proactive cleanup, and how to choose alternatives.

> Distinguish clearly: **thread-bound** means tied to the identity of the executing thread; it does not mean an HTTP request, a business job, a transaction, or an asynchronous task automatically gets its own isolated scope.

## 2. Mechanism for storing beans per thread

You can visualize the internals of `SimpleThreadScope` as follows (pseudocode, not full source):

```java
// Each SimpleThreadScope has a ThreadLocal holding a Map keyed by bean name.
private final ThreadLocal<Map<String, Object>> storage =
        ThreadLocal.withInitial(HashMap::new);

Object get(String beanName, ObjectFactory<?> factory) {
    Map<String, Object> beansOfCurrentThread = storage.get();
    Object bean = beansOfCurrentThread.get(beanName);
    if (bean == null) {
        bean = factory.getObject();
        beansOfCurrentThread.put(beanName, bean);
    }
    return bean;
}
```

- **Same thread + same bean name:** receives the same object again until the bean is removed from that thread's map.
- **Two different threads:** have two separate maps; each thread's first access normally creates two distinct beans.
- **Two bean names on the same thread:** have two independent entries, even if they share the same Java class.
- **Two Spring contexts:** do not automatically share thread-scoped beans because each context/scope registration has its own lifecycle and storage.
- **Thread terminates:** thread-local data can be garbage-collected when unreferenced, yet that is **not** a Spring event invoking `destroy()` or `@PreDestroy`.

For example, with a `workState` bean: the main thread can hold `workState#1`; a worker thread can hold `workState#2`. When a thread pool runs two consecutive tasks on **the same worker**, both can encounter `workState#2`, even though they are two different business requests.

`SimpleThreadScope`'s `getConversationId()` returns **the current thread name**, which is helpful for diagnostics yet is not a system-wide unique ID: two threads can share the same name.

## 3. Mandatory registration before use

`SimpleThreadScope` **is not automatically registered** under the `"thread"` key in standard Spring `ApplicationContext`s. Declaring `@Scope("thread")` alone is not enough. If the bean is created/accessed when the key does not exist, Spring can throw `IllegalStateException` because no `thread` scope is registered.

**Option A – register directly** with `ConfigurableBeanFactory` before refreshing/creating scoped beans:

```java
AnnotationConfigApplicationContext context =
        new AnnotationConfigApplicationContext();

context.getBeanFactory().registerScope("thread", new SimpleThreadScope());
context.register(AppConfig.class);
context.refresh();
```

This is an illustrative snippet; the full runnable example is in section 5. In other situations, you can call `ConfigurableBeanFactory.registerScope(String, Scope)` on **the context's exact factory**. The `"thread"` key is chosen by the application, yet it must match `@Scope("thread")` exactly; do not reuse built-in names such as `singleton` or `prototype`.

**Option B – declare `CustomScopeConfigurer`** as a `BeanFactoryPostProcessor`:

```java
import org.springframework.beans.factory.config.CustomScopeConfigurer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.support.SimpleThreadScope;

@Configuration(proxyBeanMethods = false)
class ThreadScopeRegistration {
    @Bean
    static CustomScopeConfigurer threadScopeConfigurer() {
        CustomScopeConfigurer configurer = new CustomScopeConfigurer();
        configurer.addScope("thread", new SimpleThreadScope());
        return configurer;
    }
}
```

The configuration class above is an **integration fragment** that must be scanned by Spring or `@Import`ed into the application. The `@Bean static` method registers the post-processor early, before regular beans are created. An application only needs **one intentional registration** for the same key in the same `BeanFactory`; avoid accidentally overwriting an existing scope registration.

Declaring a bean that uses the scope:

```java
@Bean
@Scope("thread")
WorkerState workerState() {
    return new WorkerState();
}
```

The snippet above is also an **illustrative fragment** (assuming the `WorkerState` class and related imports exist).

## 4. Bean scope differs from the scope of the consumer

Suppose a singleton directly injects a `thread` bean while the singleton is being constructed:

```java
@Service
class ReportService {
    private final WorkerState workerState;

    ReportService(WorkerState workerState) {
        this.workerState = workerState;
    }
}
```

Without a scoped proxy or lazy lookup mechanism, the `workerState` object can be fetched **once when the singleton is created**, and that exact reference is retained by the singleton and used across multiple threads. This breaks the intent of "one instance per thread".

Two ways to handle this:

**Use a scoped proxy** so the singleton's proxy resolves the per-thread target on **each method call**:

```java
@Bean
@Scope(value = "thread", proxyMode = ScopedProxyMode.TARGET_CLASS)
WorkerState workerState() {
    return new WorkerState();
}
```

`ScopedProxyMode.TARGET_CLASS` requires a target suitable for class-based proxying (watch out for `final` classes/methods). With an interface, `ScopedProxyMode.INTERFACES` can be considered. A proxy does not alter thread boundaries: calling from another thread resolves that thread's target, **without automatically carrying over the old thread's instance**.

**Use `ObjectProvider<WorkerState>`**, and call `getObject()` at the exact execution time:

```java
@Service
class ReportService {
    private final ObjectProvider<WorkerState> states;

    ReportService(ObjectProvider<WorkerState> states) {
        this.states = states;
    }

    void execute() {
        WorkerState state = states.getObject();
        // Use state on the current thread.
    }
}
```

The example fragments in this section need to be paired with matching bean definitions/imports; they illustrate the injection problem rather than standalone programs.

## 5. Runnable Java 17+ Example

Minimal Gradle project (JDK 17+, Gradle 8+) with two files:

`build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'ThreadScopeDemo'
}
```

`src/main/java/ThreadScopeDemo.java`:

```java
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;
import org.springframework.context.support.SimpleThreadScope;

public class ThreadScopeDemo {
    static class WorkState implements DisposableBean {
        private static final AtomicInteger NEXT = new AtomicInteger();
        final int id = NEXT.incrementAndGet();

        @Override
        public void destroy() {
            System.out.println("destroy " + id);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class AppConfig {
        @Bean
        @Scope("thread")
        WorkState workState() {
            return new WorkState();
        }
    }

    public static void main(String[] args) throws Exception {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Register the scope before context.refresh().
            context.getBeanFactory()
                    .registerScope("thread", new SimpleThreadScope());
            context.register(AppConfig.class);
            context.refresh();

            WorkState main1 = context.getBean(WorkState.class);
            WorkState main2 = context.getBean(WorkState.class);

            ExecutorService pool = Executors.newSingleThreadExecutor(
                    task -> new Thread(task, "demo-worker"));
            try {
                int workerId1 = pool.submit(
                        () -> context.getBean(WorkState.class).id).get();
                int workerId2 = pool.submit(
                        () -> context.getBean(WorkState.class).id).get();

                System.out.println("mainSame=" + (main1 == main2));
                System.out.println("mainId=" + main1.id);
                System.out.println("workerIds="
                        + workerId1 + "," + workerId2);
                System.out.println("mainDiffWorker="
                        + (main1.id != workerId1));
            } finally {
                pool.shutdown();
                if (!pool.awaitTermination(5, TimeUnit.SECONDS)) {
                    pool.shutdownNow();
                }
            }
        }
    }
}
```

Run from the project directory:

```bash
gradle run --quiet
# Or ./gradlew run --quiet if the project already has a Gradle Wrapper.
```

**Lines printed by the program via `System.out`**:

```text
mainSame=true
mainId=1
workerIds=2,2
mainDiffWorker=true
```

Explanation:

1. Two `getBean` calls on the main thread return the exact same `WorkState#1`.
2. The executor has **one fixed worker**: both sequential tasks receive the same `WorkState#2`.
3. The main thread and the worker thread have separate beans.
4. There is no `destroy 1` or `destroy 2` line despite shutting down the executor and closing the Spring context. This is a critical limitation: destruction callbacks on `SimpleThreadScope` beans **are not executed automatically**. Depending on logging configuration, Spring may log a warning about unsupported callbacks; those are not part of the four `System.out` lines above.

`WorkState implements DisposableBean` was included intentionally to prove: having a destruction callback configured **does not mean** this scope will proactively destroy the object.

## 6. Lifecycle and resource cleanup limitations

Spring delegates callback registration to `Scope.registerDestructionCallback(name, callback)` when a scoped bean needs destruction. However, the `SimpleThreadScope` implementation **does not support running destruction callbacks**: it ignores the request and logs a warning. Therefore you must not rely on the following hooks to automatically release beans in this scope:

- `@PreDestroy`;
- `DisposableBean.destroy()`;
- a `destroyMethod` configured on `@Bean`;
- cleanup expected to run when the bean leaves scope or when the context closes.

### Why is `remove(name)` still not enough?

`Scope.remove("workState")` only **removes the bean reference from the current thread's map** and returns the removed bean (or `null`). This call **does not automatically run** destruction callbacks, does not automatically close `AutoCloseable`, and does not sweep beans belonging to other threads.

Here is a misleading situation:

```java
Object removed = context.getBeanFactory()
        .getRegisteredScope("thread")
        .remove("workState");
// removed is no longer cached in the current thread's map,
// yet DisposableBean.destroy() has not been called automatically.
```

The snippet above is an **illustrative fragment**, assuming an open `context` variable in scope and `workState` not using a scoped proxy.

### Proactive cleanup within application-controlled boundaries

If you still want to use `SimpleThreadScope`, use it only for beans where the application **controls task completion and cleanup itself**. For example, execute on **the exact thread that used the bean**:

```java
try {
    WorkState current = context.getBean(WorkState.class);
    // Use current in this thread's work.
} finally {
    Object removed = context.getBeanFactory()
            .getRegisteredScope("thread")
            .remove("workState");
    if (removed instanceof DisposableBean disposable) {
        disposable.destroy(); // Explicitly called by the application.
    }
}
```

This is a fragment adapted from the section 5 program, **not a standalone Java program**. Calling `destroy()` manually only makes sense with a cleanup contract you truly own. It is **not equivalent** to Spring's full destruction mechanism (such as processing `@PreDestroy` via post-processors). If a resource has an explicit `close()`, prefer `AutoCloseable`/`try-with-resources` so it always closes, and then clear the right thread's cache; be careful not to reuse an already-closed bean.

Cases involving database connections, sockets, streams, locks, large buffers, transaction handles, or native resources requiring guaranteed cleanup **should definitely not be placed into `SimpleThreadScope` by default**. If the requirement is to implement a scope with a complete lifecycle, you must implement a custom `Scope` managing callbacks, scope end points, and cleanup testing across every exit path (normal, error, cancellation).

## 7. Thread pools: the most common source of bugs

Thread pools keep workers alive and **reuse threads**. Because `SimpleThreadScope` keys data by thread, two independent tasks can see **the same bean**, as shown in the runnable example in section 5.

```text
Task A -> pool-worker-1 -> thread-local["workState"] -> bean #2
Task B -> pool-worker-1 -> thread-local["workState"] -> bean #2 (left over from A)
Task C -> pool-worker-2 -> thread-local["workState"] -> bean #3
```

Consequences:

- **Cross-task data leaks:** user state, correlation IDs, or security data from task A can be read by task B if not reset.
- **Retaining resources too long:** workers live for hours/days, so thread-local maps can retain heavy objects even after business work finishes.
- **Unpredictable instances:** a single request may switch workers or a workflow may split across tasks; you cannot deduce "one job = one bean" solely from `thread` scope.
- **Hard global cleanup:** calling `remove` on the main thread does not clear other workers' maps; full cleanup requires a mechanism executing on the right worker and tracking all tasks.

`@Async`, `CompletableFuture.supplyAsync`, and executors do not automatically propagate the caller thread's `ThreadLocal` to the task-executing thread. Using a scoped proxy does not change that either. Specifically, a logical task that switches threads across stages will see different thread-scoped beans.

**Virtual threads (Java 21+)** have their own `ThreadLocal`s yet still **do not turn `SimpleThreadScope` into a true task/request scope**. A dedicated virtual thread per task can reduce worker state reuse, yet it still provides no destruction callbacks; a thread finishing also does not mean resources were closed. Reactive programs can switch threads within one processing flow, so thread scope should not be used to model reactive contexts.

## 8. Comparison with other scopes and alternatives

| Solution | Instance Boundary | Lifecycle / Cleanup | When to Use |
| --- | --- | --- | --- |
| `singleton` | One bean name per Spring container | Spring manages destruction on context close | Stateless services shared safely across threads |
| `prototype` | New instance created per bean request | Spring does not fully manage destruction after handover | Short-lived objects, caller proactively cleans up |
| `SimpleThreadScope` | One bean name / one thread / one scope instance | **No automatic cleanup callbacks** | Thread-local demos, tasks with strict thread ownership and no closable resources |
| `request` | One HTTP request in a web-aware context | Scope integrates request lifecycle and destroy callbacks | State matching HTTP request lifetime |
| `session` | One HTTP session in a web-aware context | Follows session lifecycle | State tied to a user session, not to a thread |
| Method parameters / `new` object + `try-with-resources` | Per task as defined in code | Caller explicitly closes, including on error | Short-lived state or mandatory resource release |
| `TaskDecorator` or dedicated context propagation | Per explicitly propagated execution context | Mechanism-dependent; must reset in `finally` | Propagating request/correlation info across executors when genuinely needed |

**For web applications:** if you need a bean once per request, use `@RequestScope` instead of `@Scope("thread")`. One HTTP request can switch threads; meanwhile, one servlet worker can serve many different HTTP requests.

**For background processing:** if state lives only for one job, it is usually clearer and safer to create the state at the start of the job, pass it as parameters to functions, and close it in `finally` or `try-with-resources`. If a custom scope is needed, design explicit "job started/job completed" boundaries and cleanup.

## 9. Testing a custom thread scope

If thread scope must be used in an application or test suite, include these behavioral checks:

1. **Unregistered:** accessing `@Scope("thread")` must fail due to missing scope; registering with the right key and timing resolves it.
2. **Same thread:** two `getBean` calls with the same name return the same reference.
3. **Different threads:** two threads receive different objects.
4. **Thread pool reuse:** two tasks on one worker still receive the same bean unless removed/reset.
5. **Removing a bean:** running `remove` on that worker causes the next access to create a new object, yet the destructor does not run automatically.
6. **Closing context:** testing `@PreDestroy`/`DisposableBean` must confirm you cannot rely on callbacks from `SimpleThreadScope`.
7. **Mid-flight failure:** ensure cleanup runs in `finally`, not only on the happy path.
8. **Singleton dependency:** verify a scoped proxy or `ObjectProvider` resolves the target matching the executing thread.

A "resource released" test must observe `close/destroy` actually being invoked or the resource actually closed; **clearing the map reference or possible GC is not sufficient proof**.

## 10. Common errors and how to handle them

| Symptom | Typical Cause | How to Check or Fix |
| --- | --- | --- |
| `No Scope registered for scope name 'thread'` or `IllegalStateException` | Not registered before bean creation | Register via `registerScope` before `refresh`, or configure `CustomScopeConfigurer` early |
| Two different requests read shared state | Servlet/worker thread was reused | Use `request` scope or manage state per request/job |
| A singleton always sees the same instance | Scoped bean injected directly at singleton initialization | Use `ObjectProvider` or scoped proxy; check resolution timing |
| Bean is not closed after work finishes | `SimpleThreadScope` ignores destruction callbacks | Close manually in `finally` on the right thread, or switch to a lifecycle-aware scope |
| `remove` has no effect on a worker | `remove` was called on a different thread | Call cleanup on the right thread or design an active job scope |
| `@Async` does not see caller's state | Switched to an executor thread with its own thread-local | Pass needed data explicitly, or use an appropriate context propagation mechanism |
| Logs show a destruction callback warning | Bean has destroy config yet the scope does not support it | Do not rely on that callback; redesign lifecycle management |
| Same thread name yet different beans | `getConversationId()` only reflects thread name | Use identity/references and real ownership model, not name as unique key |

## 11. Pre-adoption decision checklist

- Is the `thread` scope registered properly in the `BeanFactory` managing the bean?
- Does the business flow guarantee **one task always lives strictly on one Java thread**?
- Could an executor/thread pool, `@Async`, virtual threads, or reactive pipeline redistribute work?
- Might a worker reuse state from a prior task and cause data leaks?
- Does the bean hold resources needing `close()`/`destroy()`/`@PreDestroy`? If so, where is the **enforceable cleanup point**?
- Is a singleton holding the instance directly instead of a proxy/provider?
- Have success, exception, timeout, cancellation, and context shutdown cases been tested separately?

**Decision rule:** `SimpleThreadScope` is great for learning custom `Scope` mechanics and `ThreadLocal`, or for controlled thread-bound state. If the real goal is "per HTTP request", "per async task", "per transaction", or "automatic resource destruction", choose an abstraction reflecting that exact lifecycle.

## 12. Official reference sources

- Spring Framework — [Bean Scopes and Using a Custom Scope](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html).
- Spring Framework Javadoc — [SimpleThreadScope](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/support/SimpleThreadScope.html).
- Spring Framework Javadoc — [Scope interface](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/config/Scope.html).
- Spring Framework Javadoc — [CustomScopeConfigurer](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/beans/factory/config/CustomScopeConfigurer.html).

These sources confirm that `SimpleThreadScope` is not registered by default and does not support full lifecycle cleanup. The thread pool execution examples show why Java thread scope does not replace request or job scope.
