# Inferring `close()`, `shutdown()`, and Disabling Inference with `destroyMethod = ""` in Spring

## 1. Goal and Real-World Problem

The Spring Core Container does not only create and inject beans. When the container **truly owns the lifecycle** of a bean, it can also invoke destruction callbacks when the bean is released. For beans declared via `@Bean` methods, Spring supports an important convenience: **destroy method inference**. If the object has an eligible `close()` or `shutdown()` method, the container can register that callback without the developer having to write `@Bean(destroyMethod = "close")` or `@Bean(destroyMethod = "shutdown")`.

This helps resource-managing beans such as clients, pools, executors, factories, or connections get closed when the `ApplicationContext` terminates. However, it can also cause severe bugs if a bean points to **a shared resource or one owned outside Spring**: Spring accidentally closes the resource, disrupting other parts of the application or external systems still using it.

To prevent automatic inference, use:

```java
@Bean(destroyMethod = "")
ExternalClient externalClient() {
    return obtainExternallyManagedClient();
}
```

This snippet merely illustrates configuration; `ExternalClient` and `obtainExternallyManagedClient()` represent application-specific APIs. The core point: **an empty string `""` disables `@Bean`'s inferred destroy-method**, which does not mean it erases every other lifecycle callback.

This lesson explains the exact inference rules, when Spring invokes destruction, the difference between `""` and `"(inferred)"`, interactions with `AutoCloseable`, `DisposableBean`, `@PreDestroy`, scopes, and how to write observable examples.

## 2. The Default Value of @Bean.destroyMethod

In Spring Framework 6.x, the `org.springframework.context.annotation.Bean` annotation has the attribute:

```java
String destroyMethod() default "(inferred)";
```

This is an **abbreviated API signature**, not the full source code. The special string `"(inferred)"` instructs Spring to search **the bean object** for a destruction method matching inference rules.

Example:

```java
@Configuration(proxyBeanMethods = false)
class ResourceConfig {
    @Bean
    ResourcePool pool() {
        return new ResourcePool();
    }
}
```

This is an **illustrative fragment**; it assumes `ResourcePool` has a `public void close()` method. Because `@Bean` defaults to `"(inferred)"`, when the `pool` singleton is destroyed by the container, Spring can call `pool.close()`.

Forms of configuration to distinguish:

| Declaration | Meaning | Effect |
| --- | --- | --- |
| `@Bean` | Uses default `destroyMethod = "(inferred)"` | Spring attempts to find a `close`/`shutdown` callback or matching close contract |
| `@Bean(destroyMethod = "(inferred)")` | Requests inference explicitly | Semantically equivalent to the default value |
| `@Bean(destroyMethod = "close")` | Specifies the method name | Spring calls the configured `close()` method when the bean is destroyed |
| `@Bean(destroyMethod = "shutdown")` | Specifies the method name | Spring calls `shutdown()` as configured |
| `@Bean(destroyMethod = "cleanup")` | Specifies a custom method | Spring calls `cleanup()` when the bean is destroyed |
| `@Bean(destroyMethod = "")` | Configures no custom/inferred destroy method via this attribute | Does not auto-infer `close()`/`shutdown()`; independent callbacks may still run |

The value `""` is an **actual empty string**, not `null`, not a space `" "`, and not a method name. Usually there is also no need to set `initMethod = ""` to disable destroy inference: `initMethod` and `destroyMethod` are two attributes with different rules.

## 3. Which Methods Does Spring Infer?

When using the default `"(inferred)"` mode, Spring inspects the bean for destruction methods with matching signatures, specifically:

- `public close()`, **no parameters**;
- `public shutdown()`, **no parameters**;
- `close()` on types implementing `java.io.Closeable` or `java.lang.AutoCloseable`.

The `AutoCloseable` contract requires `close()` to be public, take no parameters, and optionally declare checked exceptions. A bean does not have to implement `AutoCloseable` for Spring to call `close`: a public method with the same name and matching signature is also an inference candidate.

### 3.1. close() without implementing AutoCloseable

```java
public class LegacyPool {
    public void close() {
        System.out.println("LegacyPool.close");
    }
}

@Configuration(proxyBeanMethods = false)
class PoolConfig {
    @Bean
    LegacyPool legacyPool() {
        return new LegacyPool();
    }
}
```

This is an **illustrative code fragment**. `LegacyPool` does not implement `AutoCloseable`, yet `close()` is still a candidate. When the container closes the singleton bean under normal conditions, Spring invokes `close()`.

### 3.2. shutdown() is also a candidate

```java
public class BackgroundService {
    public void shutdown() {
        System.out.println("BackgroundService.shutdown");
    }
}

@Configuration(proxyBeanMethods = false)
class ServiceConfig {
    @Bean
    BackgroundService backgroundService() {
        return new BackgroundService();
    }
}
```

This is an illustrative fragment. If no preferred/matching `close()` method exists and the bean qualifies for inference, Spring detects `shutdown()`. Do not assume methods named `stop()`, `terminate()`, `release()`, or `dispose()` are automatically inferred in all cases. For such custom names, declare `destroyMethod` explicitly.

### 3.3. Signatures must match

```java
class InvalidInference {
    public void close(boolean force) {
        // Has parameter: not the public no-arg close() being sought.
    }

    public void shutdown(String reason) {
        // Has parameter: not a public no-arg shutdown().
    }

    private void close() {
        // Private: not a standard public candidate.
    }
}
```

The snippet above is an **illustrative anti-example**, not a class used in the runnable program in Section 6. Overloaded or private `close` methods do not satisfy the public no-arg inference contract. If an API only provides parameterized cleanup, write a no-arg adapter method and configure it explicitly, or wrap the bean in a lifecycle-managing wrapper.

When a class has **both** `close()` and `shutdown()`, do not build business logic assuming Spring will invoke both. Choose one cleanup API as the official contract and declare `destroyMethod` explicitly if control is needed. Inference does not mean "call every method named like cleanup".

## 4. When Does the Destruction Callback Actually Run?

Spring detecting `close()`/`shutdown()` is not enough by itself. The bean must reside in a lifecycle where the container has authority to manage destruction.

### 4.1. Context-managed singleton

Example:

```java
try (AnnotationConfigApplicationContext context =
             new AnnotationConfigApplicationContext(PoolConfig.class)) {
    LegacyPool pool = context.getBean(LegacyPool.class);
    // Use bean.
}
// context.close() runs via try-with-resources;
// Spring executes callbacks of managed singletons.
```

This is an illustrative fragment; it depends on the `PoolConfig` and `LegacyPool` definitions from Section 3 and requires importing `AnnotationConfigApplicationContext`. When `close()` executes on the context, Spring destroys eligible singletons and fires their callbacks.

In real applications, `ConfigurableApplicationContext.close()`, `registerShutdownHook()`, or the runtime environment's lifecycle management determines when the context closes. **Do not expect Spring to run callbacks automatically just because execution reaches the end of a Java method or an object loses references.**

### 4.2. Prototype

With `@Scope("prototype")`, Spring creates and initializes a new bean every time the bean is requested. However, after returning the prototype to the caller, the container **does not actively track the full destruction lifecycle of each prototype**.

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
LegacyPool temporaryPool() {
    return new LegacyPool();
}
```

This fragment requires importing `Scope` and `ConfigurableBeanFactory`. Even though `LegacyPool` has a public `close()` and the `@Bean` method uses the default `"(inferred)"`, the caller **must not expect Spring to automatically close each prototype on context shutdown**. The caller must close resources itself.

### 4.3. Request/session/custom scopes

In other scopes, cleanup depends on the lifecycle and destruction-callback execution support of the **scope implementation**. A custom scope might not support destruction callbacks; hence `@Bean(destroyMethod = "close")` cannot work magic if the scope has no teardown hook.

### 4.4. Externally shared beans

If an object is a shared resource owned by JNDI, another application, or external infrastructure, the fact that "Spring can see a `close()` method" **does not mean** "Spring has the right to close that resource". This is the classic case requiring `destroyMethod = ""`.

## 5. What Exactly Does `destroyMethod=""` Affect?

`@Bean(destroyMethod = "")` disables inference via the `@Bean.destroyMethod` attribute, even when the class implements `AutoCloseable`/`Closeable`. However:

- `@PreDestroy` is a lifecycle callback processed independently by an annotation processor.
- `DisposableBean.destroy()` is Spring's destruction callback contract, also processed independently.
- Custom bean post-processors or external scope/container mechanisms may have their own cleanup.
- **Other code closing the object itself** is not prevented by the annotation attribute value.

Illustrative table:

| Bean actually has | Default `@Bean` | `@Bean(destroyMethod = "")` |
| --- | --- | --- |
| Only `public close()` | Can call `close()` on destroy | Does not auto-infer calling `close()` |
| Only `public shutdown()` | Can call `shutdown()` on destroy | Does not auto-infer calling `shutdown()` |
| Implements `AutoCloseable`, only `close()` | `close()` is detected | Does not auto-infer calling `close()` |
| Has `@PreDestroy void cleanup()` | `@PreDestroy` callback is processed | `@PreDestroy` is still processed |
| Implements `DisposableBean` | Spring calls `destroy()` per interface | Spring still calls `destroy()` |
| Has unannotated `cleanup()` method | Not inferred from arbitrary names | Not inferred from arbitrary names |
| Prototype holding resources | Init runs on creation; destroy usually caller-managed | Caller still must manage destruction |

Key takeaway: **"Disabling inference" is not "disabling all destruction".** If the goal is keeping an external resource from being closed, you must also inspect `@PreDestroy`, `DisposableBean`, other hooks, and manual close logic.

## 6. Complete Java 17+ Example: Comparing Six Mechanisms

The program below proves via **observable results**:

1. A bean with `close()` is inferred by default.
2. A bean with `shutdown()` is inferred by default.
3. A bean with `close()` but `destroyMethod = ""` is not auto-closed by Spring.
4. A differently named custom destroy method is invoked when explicitly configured.
5. `DisposableBean.destroy()` **still runs** despite `destroyMethod = ""`.
6. `@PreDestroy` **still runs** despite `destroyMethod = ""`.
7. A prototype retrieved from the container is not automatically destroyed when the context closes.

Minimal project:

```text
destroy-inference-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/DestroyInferenceDemo.java
```

### settings.gradle

```groovy
rootProject.name = 'destroy-inference-demo'
```

### build.gradle

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-context:6.2.18'
    implementation 'jakarta.annotation:jakarta.annotation-api:2.1.1'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'DestroyInferenceDemo'
}
```

### src/main/java/DestroyInferenceDemo.java

```java
import java.util.ArrayList;
import java.util.List;

import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public class DestroyInferenceDemo {

    private static final List<String> EVENTS = new ArrayList<>();

    public static final class CloseResource implements AutoCloseable {
        private final String name;

        public CloseResource(String name) {
            this.name = name;
        }

        @Override
        public void close() {
            EVENTS.add("close:" + name);
        }
    }

    public static final class ShutdownResource {
        private final String name;

        public ShutdownResource(String name) {
            this.name = name;
        }

        public void shutdown() {
            EVENTS.add("shutdown:" + name);
        }
    }

    public static final class CustomResource {
        public void release() {
            EVENTS.add("release:explicit");
        }
    }

    public static final class DisposableResource
            implements DisposableBean, AutoCloseable {

        @Override
        public void destroy() {
            EVENTS.add("destroy:contract");
        }

        @Override
        public void close() {
            EVENTS.add("close:disposable");
        }
    }

    public static final class AnnotatedResource implements AutoCloseable {
        @PreDestroy
        public void beforeDestroy() {
            EVENTS.add("preDestroy:annotation");
        }

        @Override
        public void close() {
            EVENTS.add("close:annotated");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public CloseResource inferredClose() {
            return new CloseResource("inferred");
        }

        @Bean
        public ShutdownResource inferredShutdown() {
            return new ShutdownResource("inferred");
        }

        @Bean(destroyMethod = "")
        public CloseResource externalOwned() {
            return new CloseResource("external");
        }

        @Bean(destroyMethod = "release")
        public CustomResource explicitRelease() {
            return new CustomResource();
        }

        @Bean(destroyMethod = "")
        public DisposableResource contractStillRuns() {
            return new DisposableResource();
        }

        @Bean(destroyMethod = "")
        public AnnotatedResource annotationStillRuns() {
            return new AnnotatedResource();
        }

        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public CloseResource prototypeResource() {
            return new CloseResource("prototype");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            // Create at least one prototype; caller does not close it itself.
            context.getBean("prototypeResource", CloseResource.class);

            System.out.println("eventsBeforeClose=" + EVENTS.size());
        } // Context closes automatically, running singletons' destruction callbacks.

        EVENTS.stream().sorted().forEach(System.out::println);
    }
}
```

Run (Gradle 8+, JDK 17+):

```bash
gradle run --quiet
# Or ./gradlew run --quiet if the project has a wrapper generated.
```

**Lines printed by the program to `System.out`**:

```text
eventsBeforeClose=0
close:inferred
destroy:contract
preDestroy:annotation
release:explicit
shutdown:inferred
```

The order of lines **after `eventsBeforeClose=0` is sorted** via `stream().sorted()` so output does not depend on the destruction order of multiple singletons that have no dependency relationship with each other. That is an important technique when writing examples or tests: the destruction order across separate beans **differs** from callback ordering within **a single bean**.

Explanation of each case:

- `inferredClose`: Spring sees `CloseResource implements AutoCloseable` with `close()`; logs `close:inferred`.
- `inferredShutdown`: Spring detects `public shutdown()`; logs `shutdown:inferred`.
- `externalOwned`: despite being the same `CloseResource`, this bean specifies `destroyMethod = ""`; **there is no** `close:external` log.
- `explicitRelease`: `release()` is not an auto-inferred name; configuring `destroyMethod = "release"` makes `release:explicit` appear.
- `contractStillRuns`: `DisposableResource implements DisposableBean`; `destroy:contract` still appears, while **there is no** `close:disposable` because inferred close was disabled.
- `annotationStillRuns`: `@PreDestroy` method is still invoked; logs `preDestroy:annotation`, while **there is no** `close:annotated`.
- `prototypeResource`: retrieved from the container yet not automatically destroyed by Spring; **there is no** `close:prototype`.

If you remove `destroyMethod = ""` on `externalOwned`, that bean will appear in the destruction callbacks list and get `close()` called. If you replace it with `@Bean(destroyMethod = "close")`, Spring also uses the explicit close hook.

## 7. When a Bean Combines Multiple Destruction Callbacks

Spring allows a bean to simultaneously have:

- `@PreDestroy`;
- `DisposableBean.destroy()`;
- A custom destroy method configured on the bean definition (including an inferred method).

With **distinct methods** when the container executes bean destruction, the general order within the same bean is:

```text
@PreDestroy
   ↓
DisposableBean.destroy()
   ↓
custom destroy-method (e.g., close, shutdown, cleanup)
```

This is the specified order for **lifecycle callbacks within the same bean**. Do not confuse it with the order in which bean A and bean B are destroyed: that depends on the dependency graph, container implementation, and other lifecycle relationships.

If the same method is detected by Spring through multiple mechanisms, the container has logic to avoid mechanically calling the duplicate lifecycle method twice. Even so, do not mix `DisposableBean.destroy()` with another custom method that itself calls `destroy()` inside, because your application calling it twice can still trigger double side effects.

When a bean implements `DisposableBean`, Spring recognizes the `destroy()` contract independently of `@Bean.destroyMethod`. Disabling inference **does not remove the `destroy()` method required by the Spring interface**. Likewise, `@PreDestroy` is supported by `DestructionAwareBeanPostProcessor`; that callback does not disappear due to an attribute on `@Bean`.

### When @PreDestroy explicitly calls close()

```java
@PreDestroy
void cleanup() {
    close();
}
```

This fragment illustrates a class with its own `close()` method. Even if the bean has `@Bean(destroyMethod = "")`, `cleanup()` still runs and **your own code still calls `close()`**. When external ownership applies, audit method bodies too, not just annotations.

## 8. Distinguishing `initMethod` and `destroyMethod`

`@Bean` has both `initMethod` and `destroyMethod`. Although both take method names, **their timing and defaults differ**:

| Attribute | Common default | When is it called? | Auto-infers close/shutdown? |
| --- | --- | --- | --- |
| `initMethod` | `""` | When the bean is initialized after dependency injection and prior init callbacks | No |
| `destroyMethod` | `"(inferred)"` | When the container manages destroying the bean | Yes, when eligible |

Example:

```java
@Bean(initMethod = "connect", destroyMethod = "close")
Client client() {
    return new Client();
}
```

This is an illustrative fragment; class `Client` needs matching `connect()` and `close()` methods. Goal:

- `connect()` runs when Spring finishes initializing the bean in its lifecycle.
- `close()` runs when Spring destroys the singleton/container-owned bean at the right time.
- Do not infer that `connect()` would be called automatically if you omitted `initMethod = "connect"` just because the method is named `connect`.

If the goal is disabling inferred destroy, you must write **precisely**:

```java
@Bean(destroyMethod = "")
Client externalClient() {
    return externalClientFromRegistry();
}
```

The example fragment above assumes the client comes from a registry with an external lifecycle.

## 9. Distinguishing @Bean and Other Bean Registration Approaches

### 9.1. @Bean methods

`@Bean` defaults to `destroyMethod = "(inferred)"`. This is the mechanism emphasized in this lesson, used in Java configuration.

### 9.2. Component scanning

A bean registered via `@Component` can have destruction handled by the container via `@PreDestroy`, `DisposableBean`, and other special contracts. However, **do not mechanically copy the claim "every component-scanned bean has @Bean(destroyMethod='(inferred)')"**, because `@Component` has no `destroyMethod` attribute.

If a requirement specifically states "do not let the container call close by inference", inspect **the actual bean definition type and ownership** instead of putting `@Bean(destroyMethod = "")` on an unrelated method. For beans returned by `@Bean`, placing the attribute on the factory method is the direct approach.

### 9.3. XML configuration

In XML, there is per-`<bean>` `destroy-method` and `<beans>`-level `default-destroy-method`. The special value `(inferred)` can also be used to enable inference.

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
         http://www.springframework.org/schema/beans
         https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="pool"
          class="example.ResourcePool"
          destroy-method="(inferred)"/>

</beans>
```

This is illustrative XML requiring a real `example.ResourcePool` class. Do not assume every XML declaration without `destroy-method` shares the exact same default as `@Bean`. To enable inference in XML, configure it explicitly per XML rules.

### 9.4. Programmatic bean definitions

Registering a `RootBeanDefinition` or bean factory programmatically can also declare a destroy method or inferred mode. However, configuration depends on the specific bean definition API, unlike the `@Bean` annotation. To keep the lesson focused, simply remember that **inference comes from bean definition metadata**, not from a special Java method automatically invoked when the garbage collector runs.

## 10. Disabling Inference When the Context Does Not Own the Bean

The clearest scenario for using `destroyMethod = ""` is a **borrowed resource**:

- A client/pool retrieved from JNDI owned by the application server.
- A shared executor managed by external infrastructure.
- A singleton object obtained from a library's global registry, shared across multiple containers.
- A resource wrapper returned by a provider with its own lifecycle.
- A facade bean merely providing a reference to an externally initialized and managed service/client.

Example:

```java
@Configuration(proxyBeanMethods = false)
class ExternalResources {
    @Bean(destroyMethod = "")
    SharedConnectionPool sharedPool(ExternalPoolRegistry registry) {
        return registry.getSharedPool();
    }
}
```

This fragment requires importing `Configuration`/`Bean` and application-defined `SharedConnectionPool`/`ExternalPoolRegistry` types. If `SharedConnectionPool` has `close()`, you must not let the container unexpectedly invoke that method when one of several contexts closes while other parties still share the pool.

**Ownership rules:**

- **Spring owns the resource** and is where teardown is created/decided: let the inferred callback run or use an explicit destroy method.
- **Application receives a borrowed external resource**: consider `destroyMethod = ""` and audit all other callbacks.
- **Caller creates a prototype and receives ownership:** the caller must close it itself.
- **Multiple potential owners exist:** clearly designate a single owner responsible for closing; avoid closing multiple times or too early.

Never use `destroyMethod = ""` merely to silence shutdown errors if the pool/socket/executor genuinely needs cleanup. That turns a configuration bug into a hard-to-detect resource leak.

## 11. Comparing Disabling Inference vs Closing via AutoCloseable

A bean implementing `AutoCloseable` does not mean Spring has the right to close that object in every case. `AutoCloseable` only defines the **closing API**, while lifecycle ownership depends on design.

### Spring-owned resource

```java
@Bean
MySocketClient ownedClient() {
    return new MySocketClient();
}
```

Assume `MySocketClient implements AutoCloseable`. Default inference lets the context execute cleanup when destroying the singleton. Let Spring close it if the bean only lives inside the context and nothing uses it after shutdown.

### Borrowed resource

```java
@Bean(destroyMethod = "")
MySocketClient borrowedClient(ResourceRegistry registry) {
    return registry.borrowSharedClient();
}
```

The container only manages **the bean reference** and should not decide when to close the borrowed client. Still, if the bean itself has `@PreDestroy` or `DisposableBean` closing the client, you must update the code/ownership contract accordingly.

### Prototype using try-with-resources

```java
try (MySocketClient oneTaskClient = context.getBean(MySocketClient.class)) {
    oneTaskClient.send();
}
```

This fragment assumes the bean is configured as prototype and implements `AutoCloseable`. The caller proactively closes it at the exact task boundary. Avoid placing the same reference in a shared singleton and closing it from multiple callers if its lifecycle was not designed to be shared.

## 12. Common Errors and How to Diagnose Them

| Symptom | Possible cause | How to check/fix |
| --- | --- | --- |
| `close()` is called even though `destroyMethod` was not written | `@Bean` defaults to `"(inferred)"` and class has public no-arg `close` or `AutoCloseable` | Inspect bean definition; if externally owned, use `destroyMethod = ""` |
| `shutdown()` runs when context closes | Bean has public no-arg `shutdown()` and inference is enabled | If Spring is the owner, behavior may be intended; otherwise disable inference |
| `close(boolean)` is not called by Spring | Method has parameters, does not match no-arg signature | Create a no-arg adapter or explicit lifecycle logic |
| `release()` is not called | `release` is not a standard inference candidate | `@Bean(destroyMethod = "release")` |
| Wrote `destroyMethod = ""` yet `destroy()` still runs | Bean implements `DisposableBean` | This is an independent callback; fix ownership/lifecycle contract |
| Wrote `destroyMethod = ""` yet `@PreDestroy` still runs | Independent lifecycle annotation | Review `@PreDestroy` and what it calls |
| Inferred cleanup does not run on prototype | Container does not track destruction of individual prototypes handed to callers | Caller handles cleanup itself |
| Context never closes so bean stays alive | No container lifecycle termination | Close context properly, use shutdown hook/managed runtime |
| External bean gets closed, breaking other services | Shared resource without disabling Spring callback | Identify a single owner; set `destroyMethod = ""` and check independent callbacks |
| Destroy method throws an exception | Cleanup execution failed; may affect shutdown and leave unreleased resources | Inspect root cause, log usefully, design safe and idempotent cleanup |
| Two destroy callbacks both call `close()` | User code stacks `@PreDestroy` with explicit/inferred close | Assign clear responsibilities, avoid calling the same action twice |
| Test does not observe Spring callback | Test instantiated object with `new` or never closed context | Instantiate through Spring and call `context.close()`/try-with-resources |
| Disabled inference on the wrong bean | `@Bean` configured is not the bean definition actually in use | Check bean name, class, context, qualifier, and registration source |

## 13. Testing Lifecycle Without Depending on Bean Destruction Order

When writing tests, check for the **presence/absence of events** rather than asserting the global destruction order across all singletons when no explicit dependency order exists.

Conceptual JUnit 5 example:

```java
assertTrue(events.contains("close:inferred"));
assertTrue(events.contains("shutdown:inferred"));
assertTrue(events.contains("destroy:contract"));
assertTrue(events.contains("preDestroy:annotation"));

assertFalse(events.contains("close:external"));
assertFalse(events.contains("close:disposable"));
assertFalse(events.contains("close:annotated"));
assertFalse(events.contains("close:prototype"));
```

This is an **illustrative assertion fragment**, assuming `events` and JUnit static imports already exist. It is not a full test class.

For multiple callbacks on **the same bean**, you can record them in an ordered list and assert `@PreDestroy` occurs before `DisposableBean.destroy`, followed by the configured method. In the Section 6 example, callbacks live on different beans, so `sorted()` simply makes output deterministic for presentation.

Useful scenarios to test:

1. A bean with only public `close()`, implementing no interfaces.
2. A bean with only public `shutdown()`.
3. An `AutoCloseable` bean using inferred/default mode.
4. That same bean switched to `@Bean(destroyMethod = "")`.
5. A bean both implementing `DisposableBean` and having `close()`.
6. A bean with `@PreDestroy`.
7. A bean retrieved from prototype scope, followed by closing the context.
8. A bean obtained from an external registry—verifying whether another context closed it.
9. Cleanup failing or invoked multiple times: is the resource idempotent?

**Separate unit and integration tests**: unit tests can call `close()` directly to verify class internals, whereas verifying that Spring **infers and invokes the method** requires starting/closing a real `ApplicationContext`.

## 14. Caveats for Executors, Connection Pools, and Background Services

For an executor or thread pool, `shutdown()` may just begin stopping acceptance of new tasks, while waiting for active tasks to finish may require `awaitTermination` or a controlled stop mechanism. Inference picking a `shutdown()` method **does not guarantee every task has stopped, every thread has joined, or every in-flight request has completed**.

Similarly:

- A database pool's `close()` may close connections; ensure traffic has stopped and active transactions are coordinated.
- An HTTP client's `close()` may release sockets; do not close before background jobs complete.
- A message consumer's `shutdown()` may require ack/flush; distinguish closing resources from draining workload.
- `SmartLifecycle.stop()` and `phase` belong to lifecycle orchestration; they can execute during the stop phase before singleton destruction, without removing the role of inferred destroy callbacks at the end of the lifecycle.

If an application needs complex graceful shutdown, a single inferred callback may **not suffice**. Explicitly design stop accepting → finish/drain tasks → close resources, test real startup/shutdown, and choose `Lifecycle`/`SmartLifecycle` when appropriate. Use `destroyMethod = "shutdown"` when the target API name is explicit; do not rely on inference in systems where shutdown ordering impacts reliability.

## 15. Checklist Before Enabling or Disabling Inference

- Was the bean actually created by a `@Bean` method or another registration mechanism?
- Is `@Bean.destroyMethod` currently default `"(inferred)"`, an explicit name, or `""`?
- Does the runtime class have `public close()`, `public shutdown()`, or implement `Closeable`/`AutoCloseable`?
- Which scope manages the bean? For prototype, who is responsible for closing?
- Is the resource created and fully owned by Spring, or borrowed from JNDI, a shared registry, or an external pool?
- Is there a `@PreDestroy` or `DisposableBean.destroy()` that still triggers despite `destroyMethod = ""`?
- Is there custom callback logic manually calling `close()`/`shutdown()` or closing the resource elsewhere?
- Is the context properly closed? Is there a shutdown hook or managed runtime environment?
- Does cleanup run in the right order relative to active workloads?
- Have you tested all cases: callback runs **once**, does not run when externally owned, and failure during shutdown?

## 16. Official Further Reading

1. [Spring Framework Reference — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): default `close`/`shutdown` detection, disabling via `destroyMethod = ""`, and externally managed resource examples.
2. [Spring Framework Reference — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): singleton destruction, `DisposableBean`, inferred destroy methods, XML `(inferred)`, and `AutoCloseable`.
3. [Spring Framework 6.2 Javadoc — @Bean](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/Bean.html): default `destroyMethod = "(inferred)"`, method signatures, and bean lifecycle conditions.
4. [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): why prototypes do not have container-managed destruction lifecycles after handoff.
5. [Maven Central — spring-context 6.2.18](https://central.sonatype.com/artifact/org.springframework/spring-context/6.2.18): Spring Framework dependency used in the example.

Rule of thumb: **let inferred destruction work when Spring owns the resource; configure `@Bean(destroyMethod = "")` when Spring only borrows a resource with a close method; and check `@PreDestroy` and `DisposableBean` separately because neither callback is disabled by an empty string.**
