# Order of @PostConstruct, InitializingBean, and initMethod in the Bean Lifecycle

A Spring bean is typically **instantiated**, **injected with dependencies**, and then **initialized** before being exposed to other components for normal use. During the initialization phase, Spring supports multiple callback mechanisms: a method annotated with `@PostConstruct`, the `InitializingBean` interface, and a custom initialization method declared via `@Bean(initMethod = "...")` or equivalent metadata.

When a bean **simultaneously** has all three callbacks, each being a separate method, Spring invokes them in this order:

1. **`@PostConstruct`**
2. **`InitializingBean.afterPropertiesSet()`**
3. **Custom `initMethod`**

This order is specified by Spring Framework for **callbacks on the same bean**. It does not mean every `@PostConstruct` across all beans in the application runs before all `afterPropertiesSet()` methods. Different beans may be created based on dependency relationships, component scanning order, lazy configuration, and other container conditions.

This lesson uses Spring Boot 3.3.x and Java 17 or newer. Spring Boot relies on Spring Framework to manage bean lifecycles, so the core rule belongs to the Spring IoC container rather than a separate order defined by `SpringApplication.run()`.

## 1. When are initialization callbacks called?

Simplified flow of **a typical singleton bean**:

~~~text
Spring decides the bean needs to be created
    |
    v
Call constructor or @Bean factory method
    |
    v
Set properties, inject dependencies, and apply required configuration
    |
    v
Pre-initialization BeanPostProcessor
  (@PostConstruct processing runs in this phase)
    |
    v
@PostConstruct
    |
    v
InitializingBean.afterPropertiesSet()
    |
    v
Method declared via initMethod
    |
    v
Post-initialization BeanPostProcessor
  (may create a wrapper/proxy)
    |
    v
Bean ready per the container's contract
~~~

The diagram omits several internal steps such as `Aware` callbacks, various `BeanPostProcessor` types, and bean registration mechanics. For beans using `@Autowired` or `@Value`, injected values are normally ready before the three initialization callbacks run.

Crucially: **“post construct” means after that specific bean is created and configured**, not “after every bean in the application has been created” or “after the application is ready to serve requests”.

### Why do we need callbacks after the constructor?

A constructor is suited for receiving required dependencies and establishing object invariants. However, some values may be assigned by Spring via setters, field injection, configuration binding, or post-processors after the constructor finishes. Initialization callbacks give you a chance to:

- Verify that properties and dependencies have been validly configured.
- Prepare internal data structures based on the bean's final configuration.
- Build a small cache or precompute purely in-memory values.
- Fail fast if the bean cannot operate according to its contract.

Initialization callbacks are **not appropriate by default** for long-running tasks, slow network waits, loading large datasets remotely, or system-wide coordination. Doing so can block startup, hold singleton creation locks, or create hard-to-debug dependency cycles.

## 2. How do the three mechanisms differ?

| Mechanism | How it is declared | Characteristics |
|---|---|---|
| `@PostConstruct` | Annotates a no-argument method on the bean. | Readable, common, uses standard Jakarta annotation in Spring Boot 3. |
| `InitializingBean` | Bean implements `org.springframework.beans.factory.InitializingBean` and overrides `afterPropertiesSet()`. | Spring-specific; callback runs after the container sets required properties. |
| `initMethod` | For example `@Bean(initMethod = "customInit")` in a configuration class. | Keeps business classes independent of Spring annotations/interfaces; callback name lives in bean definition. |

All three are **bean initialization callbacks**, not three separate stages of `SpringApplication` and not three milestones of the entire application.

### `@PostConstruct`

In Spring Boot 3.x, import the annotation:

~~~java
import jakarta.annotation.PostConstruct;
~~~

Example:

~~~java
@PostConstruct
public void validate() {
    System.out.println("Bean dependencies injected");
}
~~~

A typical callback method returns `void`, takes no parameters, and is an instance method. It is only invoked by Spring when **the object is a container-managed bean** and the corresponding annotation processor is enabled. Calling `new MyService()` in plain Java **does not trigger** `@PostConstruct`.

Spring Boot 3 uses the `jakarta.annotation` namespace. Legacy code using `javax.annotation.PostConstruct` from earlier Java/Spring versions may need import and dependency updates when upgrading. Do not assume modern JDKs bundle Jakarta APIs out of the box; the project's dependencies must provide this annotation.

### `InitializingBean.afterPropertiesSet()`

When a bean implements the interface:

~~~java
import org.springframework.beans.factory.InitializingBean;

public class SettingsVerifier implements InitializingBean {

    @Override
    public void afterPropertiesSet() throws Exception {
        System.out.println("Properties are ready");
    }
}
~~~

Spring calls `afterPropertiesSet()` after setting required bean properties and processing relevant `Aware` callbacks. Because the interface comes from Spring, the class has a direct dependency on Spring Framework; libraries or domain classes aiming to stay decoupled often prefer `@PostConstruct` or a custom init method.

The name `afterPropertiesSet` **does not** mean all system work is complete. Only initialization belonging to this bean and its required dependencies has reached the appropriate stage.

### Custom `initMethod`

With Java configuration:

~~~java
@Bean(initMethod = "validateConfiguration")
SettingsVerifier settingsVerifier() {
    return new SettingsVerifier();
}
~~~

Spring finds and calls `validateConfiguration()` on **the bean returned** by the factory method, not on the configuration class itself. This snippet is illustrative only: to run it in practice, you must add a no-argument `validateConfiguration()` method to `SettingsVerifier` and declare the bean inside a `@Configuration` class.

In classic XML definitions, the equivalent concept is the `init-method="validateConfiguration"` attribute on `<bean>`. In Java code using Spring Boot, `@Bean(initMethod = "...")` is generally easier to follow.

There is no default `@InitMethod` annotation in Spring for this case. `initMethod` is **an attribute on `@Bean`** (or on the bean definition), and the method name string must match an actual existing callback.

## 3. Complete example: observing the exact order

Create a **Spring Boot 3.3.x** project, Java 17 or newer, with the `spring-boot-starter` dependency. Place the following code in:

`src/main/java/com/example/lifecycle/InitOrderApplication.java`

~~~java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class InitOrderApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(InitOrderApplication.class);
        app.setWebApplicationType(WebApplicationType.NONE);

        try (ConfigurableApplicationContext context = app.run(args)) {
            System.out.println(
                    "4. main: context active = " + context.isActive());
        }
    }

    @Bean(initMethod = "customInit")
    InitProbe initProbe() {
        return new InitProbe("billing");
    }

    public static final class InitProbe implements InitializingBean {

        private final String name;

        public InitProbe(String name) {
            this.name = name;
            System.out.println("0. constructor: " + name);
        }

        @PostConstruct
        public void postConstruct() {
            System.out.println("1. @PostConstruct: " + name);
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println(
                    "2. InitializingBean.afterPropertiesSet: " + name);
        }

        public void customInit() {
            System.out.println("3. @Bean(initMethod): " + name);
        }
    }
}
~~~

In this example:

- `@SpringBootApplication` puts the root class into Boot configuration and enables `@Bean` processing.
- `@Bean(initMethod = "customInit")` creates the `initProbe` bean. `new InitProbe("billing")` prints the constructor line before lifecycle callbacks are called.
- `InitProbe` has **three differently named callback methods**; they demonstrate all three mechanisms coexisting on **one instance**.
- `WebApplicationType.NONE` disables web server initialization, making the bean lifecycle easier to observe.
- `try-with-resources` calls `close()` on the context when exiting the try block; this lets the console program terminate cleanly.

### How to run

Use the Gradle wrapper of a Spring Boot project with the main class configured:

~~~bash
./gradlew bootRun
~~~

On Windows:

~~~powershell
.\gradlew.bat bootRun
~~~

Or with a Maven project that has the Spring Boot Maven plugin:

~~~bash
./mvnw spring-boot:run
~~~

If the project has multiple main classes, specify `com.example.lifecycle.InitOrderApplication` as the main class for `bootRun`/the corresponding plugin. This code requires Spring Boot/Spring Framework on the classpath, so **it cannot be run standalone with just `javac InitOrderApplication.java`**.

Ignoring the banner and Spring Boot log lines, the lines printed by the program itself in order are:

~~~text
0. constructor: billing
1. @PostConstruct: billing
2. InitializingBean.afterPropertiesSet: billing
3. @Bean(initMethod): billing
4. main: context active = true
~~~

**Why is this order deterministic?**

1. The factory method `initProbe()` instantiates `InitProbe`, so the constructor prints `0`.
2. After Spring handles configuration and dependencies for the bean, the `@PostConstruct` method is called, printing `1`.
3. The container detects the instance implements `InitializingBean`, calls `afterPropertiesSet()`, and prints `2`.
4. The bean definition specifies `customInit` as the init method, so Spring calls it after the interface callback, printing `3`.
5. Once startup and startup runners (if any) complete normally, `app.run(args)` returns an active context; `main` prints `4`.

Note that line **4** is not a bean initialization callback. It is ordinary Java code in `main` after Boot finishes its startup sequence. System logs may interleave between printed lines, but they do not alter the `0`–`4` ordering relationship in the example.

## 4. Key differences between the three points in time

To distinguish what can be done in each callback, consider a bean using the following configuration:

~~~java
public class ConnectionSettings implements InitializingBean {

    private String endpoint;

    public void setEndpoint(String endpoint) {
        this.endpoint = endpoint;
    }

    @PostConstruct
    public void verifyEndpoint() {
        if (endpoint == null || endpoint.isBlank()) {
            throw new IllegalStateException("endpoint is required");
        }
    }

    @Override
    public void afterPropertiesSet() {
        // Can verify additional invariants after properties have been set.
    }

    public void prepare() {
        // Prepare internal data from the validated endpoint.
    }
}
~~~

This is an illustrative class; it requires importing `jakarta.annotation.PostConstruct` and `InitializingBean`. For the callbacks to run, the object must be registered as a Spring bean, and `prepare()` must be declared as a custom init method if you want Spring to invoke it automatically.

**There is no magic here:**

- `verifyEndpoint()`, `afterPropertiesSet()`, and `prepare()` all see `endpoint` already assigned by the container, assuming the bean is configured properly.
- `@PostConstruct` runs first **among these three callbacks**. It does not necessarily have fewer dependencies than the other callbacks; dependencies injected into that bean are normally already present.
- `afterPropertiesSet()` does not wait for the entire ApplicationContext refresh to finish before running.
- `prepare()` runs after the two preceding callbacks if you configure `initMethod = "prepare"`, but does not run automatically just because the method is named `prepare`.

If your goal is simply to validate `endpoint` and build an internal data structure, **choosing just one callback** is usually easier to maintain than spreading the same work across all three.

## 5. Within what scope does Spring guarantee this order?

The **`@PostConstruct` → `afterPropertiesSet()` → `initMethod`** rule applies when:

1. An instance is created and managed as a Spring bean.
2. The corresponding callbacks are validly declared and annotation processing is active.
3. The three mechanisms point to **distinct methods** on the bean.

Spring Framework also specifies that if multiple mechanisms point to **the same initialization method name**, that method is not invoked multiple times just because it was registered repeatedly across mechanisms. Still, it is best to avoid declaring the same callback redundantly in multiple places because it makes code harder to read.

Confusing example:

~~~java
public class DuplicateInitExample {

    @PostConstruct
    public void initialize() {
        System.out.println("initialize");
    }
}
~~~

If this bean is also declared with `@Bean(initMethod = "initialize")`, you **should not rely on reasoning like “two declarations = two runs”**. Spring has a mechanism to avoid invoking the same initialization method twice per its lifecycle contract. More importantly, one method should not shoulder duplicate responsibilities simply because config registered it twice.

### No global callback order across different beans

Suppose bean A and bean B both have `@PostConstruct`, `afterPropertiesSet()`, and `initMethod`. Spring makes no guarantee like:

~~~text
@PostConstruct(A)
@PostConstruct(B)
afterPropertiesSet(A)
afterPropertiesSet(B)
initMethod(A)
initMethod(B)
~~~

Instead, Spring typically creates and **fully initializes the bean currently being built**, then moves on to other beans as required by demand and dependency relationships. A dependency B can finish initializing before bean A finishes injection.

If you want A to be created only after B, express the **actual dependency** via constructor/factory method injection. When you need an initialization ordering relationship without direct injection, you can intentionally use `@DependsOn("beanB")`. `@DependsOn` controls ordering **between beans**, not reversing the three callbacks on the same bean.

The `@Order` annotation or `Ordered` interface also **does not change** the order of `@PostConstruct`, `afterPropertiesSet()`, and `initMethod` on a bean.

## 6. A trap: `@PostConstruct` is not when everything is ready

The name `@PostConstruct` easily leads beginners to think the callback runs after Spring Boot has finished starting up. In reality, it happens during **bean creation**, typically **before context refresh completes**.

Compare different milestones:

| Milestone | Scope and purpose |
|---|---|
| Constructor | Initializes the Java object, receives dependencies via constructor. |
| `@PostConstruct` | Validates and prepares the bean itself after injection. |
| `InitializingBean.afterPropertiesSet()` | Spring-specific callback after bean configuration has been applied. |
| `@Bean(initMethod = "...")` | Custom callback on the bean per the bean definition. |
| `SmartInitializingSingleton.afterSingletonsInstantiated()` | Runs after the pre-instantiation phase of regular non-lazy singletons. |
| `ContextRefreshedEvent` | Published when the context finishes a refresh. |
| `ApplicationRunner` / `CommandLineRunner` | Spring Boot startup logic after context refresh. |
| `ApplicationReadyEvent` | Boot signals that normal startup has completed runners. |

For example, if you need to **validate a bean's properties**, `@PostConstruct` is appropriate. If you need to **perform an application startup step after the entire context has refreshed**, a runner or event listener may be more appropriate.

Caveat: `SmartInitializingSingleton` pertains only to the lifecycle of singletons that were eagerly initialized during pre-instantiation. It does not mean all lazy/prototype beans were created, nor does it guarantee external systems are ready.

### Why shouldn't you access many other beans from `@PostConstruct`?

Initialization callbacks can run while Spring holds synchronization/locks related to singleton creation. If a callback starts another thread and **waits** for that thread to retrieve beans from the same container, you can deadlock yourself. If a callback hangs because a database or network does not respond, the entire startup can stall or fail.

Keep this callback for short, synchronous tasks close to the bean's internal state. For work requiring many beans to be ready, consider `SmartInitializingSingleton` or `ContextRefreshedEvent`; for Spring Boot business startup work, consider `ApplicationRunner`/`CommandLineRunner`. The final choice depends on whether the work should run **per bean**, **per context refresh**, or **per Boot startup**.

## 7. Consequences when a callback throws an exception

A lifecycle callback can actively reject bean initialization if configuration is invalid.

Example:

~~~java
@PostConstruct
public void validate() {
    if (connectionTimeoutMillis <= 0) {
        throw new IllegalStateException(
                "connectionTimeoutMillis must be positive");
    }
}
~~~

This code belongs inside a bean that already has the `connectionTimeoutMillis` field and `PostConstruct` import. When a non-lazy singleton bean is created during startup, the exception may be wrapped by Spring in `BeanCreationException` and cause context refresh/startup to fail. High-level messages can vary depending on where the error was thrown; when debugging, find the **root cause**.

Comparison:

- Error in `@PostConstruct`: Spring does not proceed to call `afterPropertiesSet()` and `initMethod` for the same bean as if initialization succeeded.
- Error in `afterPropertiesSet()`: `@PostConstruct` may have run, while custom `initMethod` has not run.
- Error in custom `initMethod`: the first two callbacks may have run, yet the bean has still not initialized successfully according to the container.
- For `@Lazy` beans, the exception may only appear the first time the bean is retrieved and needs to be created, **after initial startup has already finished**.

Do not catch and swallow all exceptions just to “let the app start” if that bean actually cannot serve business requests. If a fallback mechanism is needed, represent the degraded state intentionally and let downstream code know when a dependency is unavailable.

## 8. Effect of scope and lazy initialization

**Non-lazy (regular) singleton:** Spring creates and invokes callbacks during refresh if the bean belongs to the set of singletons to be pre-instantiated. Whenever a singleton is successfully created in a context, those callbacks run once for that instance.

**Lazy singleton:** A bean marked `@Lazy` may not be created during startup. Callbacks only run when Spring actually creates the bean, such as on the first `getBean()` call. If a non-lazy singleton has a required dependency on a lazy bean, that dependency may still need to be created early.

**Prototype:** Each time Spring creates a prototype instance, it runs injection and initialization callbacks for the new instance. However, Spring does not track the entire destroy lifecycle of a prototype after handing the bean to the caller. Do not confuse initializing every time with automatically closing resources every time.

**Multiple ApplicationContexts:** The same bean class declared in two independent contexts can produce two singleton instances and run callbacks on each instance. The three-callback rule still applies **per bean instance**, not per JVM.

Illustrative lazy bean example:

~~~java
@Bean(initMethod = "customInit")
@Lazy
InitProbe initProbe() {
    return new InitProbe("billing");
}
~~~

This replaces the `@Bean` method of the main example and requires importing `org.springframework.context.annotation.Lazy`. If no other bean requires `InitProbe` during startup, lines `0`–`3` do not appear right when `app.run(args)` runs, but can appear when code first calls `context.getBean(InitProbe.class)`.

## 9. Initialization callbacks and proxies/AOP/transactions

A bean may be wrapped by Spring in a proxy to support AOP features like `@Transactional` or `@Async`. However, initialization callbacks typically run **on the bean being created**, before the final proxy is handed to other components.

Therefore:

- Do not expect `@Transactional` on `@PostConstruct` or an `initMethod` to run in a transaction the same way an external caller invokes it through a proxy.
- Do not expect `@Async` on a callback method to turn the callback into an async task like a post-startup proxy call.
- A call from one method inside a bean to another method on **the same bean** can bypass the Spring proxy (self-invocation), even during normal application operation.
- The callback receives Spring-injected dependencies, but the bean is not guaranteed ready to use every facility involving other beans or external layers.

If an operation needs full managed transaction support, consider calling another service through its proxy at the right time from a runner/listener; keep initialization callbacks for validation and preparing internal state.

## 10. Besides init there is destroy, but that is a different phase

All three callbacks in this topic belong to **initialization**. When the context closes, Spring supports corresponding destruction callbacks, such as:

| Initialization | Destruction/cleanup |
|---|---|
| `@PostConstruct` | `@PreDestroy` |
| `InitializingBean.afterPropertiesSet()` | `DisposableBean.destroy()` |
| `@Bean(initMethod = "...")` | `@Bean(destroyMethod = "...")` |

If multiple distinct destroy mechanisms exist on the same bean, Spring also has rules for destruction callback order. Do not treat initialization callbacks as the place to close resources. For instance, a bean that creates a cache during init should clear the cache or close connections in a corresponding destroy callback if resources need reclaiming.

Certain resource types like connection pools, executors, or clients with `close()`/`shutdown()` methods may benefit from Spring's destroy-method inference in bean definitions. However, cleanup depends on how the bean is declared and its scope; an object you create yourself with `new` outside Spring is not automatically managed by the container.

## 11. Common misconceptions

**Mistake 1 — “`@PostConstruct` runs right after the constructor”.**

Not quite accurate. Spring still must set dependencies/properties and run pre-initialization mechanisms. The callback only runs when the bean reaches the appropriate phase in the container. If you call `new` directly, the annotation has no automatic trigger.

**Mistake 2 — “`afterPropertiesSet()` runs after context refresh finishes”.**

False. It is a **per-bean** callback during that bean's initialization. Many other beans and refresh steps may still be incomplete.

**Mistake 3 — “Just write a method named `init` and Spring will call it automatically”.**

Not sufficient. The method must be configured as a custom init method, recognized by an appropriate lifecycle mechanism, or called explicitly by your code. `@Bean(initMethod = "init")` is one clear way to declare it.

**Mistake 4 — “Declaring all three mechanisms runs them in random order”.**

Incorrect for three **differently named callbacks on the same bean**: Spring clearly specifies `@PostConstruct`, then `afterPropertiesSet()`, and finally custom `initMethod`.

**Mistake 5 — “You can use `@Order` to change the order of the three callbacks”.**

No. `@Order` does not alter the initialization callback contract. If you want to change the sequence of a bean's own tasks, consolidate the logic into one callback and invoke the steps in explicit order.

**Mistake 6 — “`@PostConstruct` is a good place to run heavy data migrations”.**

Usually not. The callback can run during singleton creation and cause slowdowns, deadlocks, or blocked startup. Use an appropriate startup mechanism for application-wide work and design dedicated timeouts/retries.

**Mistake 7 — “In Spring Boot 3 you still use `javax.annotation.PostConstruct` as before”.**

Boot 3 uses the corresponding Jakarta APIs; the standard import is `jakarta.annotation.PostConstruct`. Check dependencies instead of assuming annotations are bundled in the JDK.

**Mistake 8 — “I saw the bean print output once, meaning the callback runs once in the entire program”.**

Not always true. There may be two contexts, prototype beans, or multiple refreshes/bean creations. A callback's scope is the container-created instance, not a fixed once-per-JVM execution.

## 12. Verification hands-on exercises

Use the `InitOrderApplication` example in Section 3 and try:

1. **Remove `@PostConstruct`** from `postConstruct()`: line `1` is no longer called automatically by Spring, while lines `2` and `3` still run.
2. **Remove `implements InitializingBean`** and `afterPropertiesSet()`: line `2` disappears. The other two mechanisms keep working.
3. **Remove `initMethod = "customInit"`** from `@Bean`: line `3` disappears. Merely having a method named `customInit` does not make Spring call it.
4. **Change `initMethod` to a non-existent name**: observe the bean creation error at startup. Trace the root cause instead of reading only the generic “Application failed to start” message.
5. **Add `@Lazy` to `@Bean`**, then call `context.getBean(InitProbe.class)` in `main` after `run`: observe the callbacks shifting to the moment the bean is actually created.
6. **Directly create `new InitProbe("manual")`** outside the container: the constructor runs, but the callbacks are not called automatically by Spring.

Each experiment should change **one condition** and re-run to see the causal relationship. For the `@Lazy` experiment, remember that having another non-lazy dependency require the bean can still force early initialization.

### References

- Spring Framework – Customizing the Nature of a Bean, section *Combining Lifecycle Mechanisms*: https://docs.spring.io/spring-framework/reference/6.1/core/beans/factory-nature.html
- Spring Framework 6.1 – `InitializingBean` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/InitializingBean.html
- Spring Boot 3.3 – Features, SpringApplication: https://docs.spring.io/spring-boot/3.3/reference/features/spring-application.html

**Remember:** When **the same Spring bean** declares three callbacks with **different methods**, Spring initializes them in the order **`@PostConstruct` → `InitializingBean.afterPropertiesSet()` → `@Bean(initMethod = "...")`**. They occur **after the bean is configured and before the bean finishes initialization**, not as startup milestones of the entire application. Choosing a single mechanism suited to the bean's work is usually clearer and easier to maintain than using all three for the same task.
