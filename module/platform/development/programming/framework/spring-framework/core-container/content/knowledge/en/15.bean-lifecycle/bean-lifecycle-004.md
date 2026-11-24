# Ordering When Combining Multiple Bean Initialization Mechanisms in Spring Framework

## 1. The Problem to Solve

In the Spring Core Container, a bean can simultaneously use a **constructor**, dependency injection, `Aware` interfaces, `@PostConstruct`, `InitializingBean.afterPropertiesSet()`, a custom initialization method (`init-method`/`@Bean(initMethod = ...)`), and `BeanPostProcessor`. Each mechanism participates at a different point during bean creation.

The central question is: **when the same bean declares multiple initialization mechanisms, in what order does Spring invoke them, why does that order matter, and which mechanisms can alter the standard flow?**

For a Spring-managed bean with the three common initialization callback mechanisms having **three distinct method names**, Spring guarantees the order:

1. Method annotated with **`@PostConstruct`**.
2. **`InitializingBean.afterPropertiesSet()`**.
3. Custom initialization method, such as **`@Bean(initMethod = "customInit")`** or `init-method` in XML.

This ordering is published in the Spring Framework Reference, in the **Combining Lifecycle Mechanisms** section. This is the **order of initialization callbacks within the same bean**, not a promise that all beans in the application are created in the order of class declarations, `@Bean` methods, or source-code order.

## 2. Bean Initialization Lifecycle: The Big Picture

For a normal bean created and completed by the container without complex dependency cycles, the simplified diagram is as follows:

```text
Register bean definition; process BeanFactory configuration
                  |
                  v
           Create instance
      (constructor / factory method)
                  |
                  v
      Attach dependencies/properties
      (e.g., @Autowired, setters)
                  |
                  v
           BeanNameAware /
        BeanClassLoaderAware /
           BeanFactoryAware
                  |
                  v
 BeanPostProcessor.beforeInitialization
    (in this chain, @PostConstruct is
     processed via an annotation
     post-processor)
                  |
                  v
   InitializingBean.afterPropertiesSet()
                  |
                  v
          Custom init-method
                  |
                  v
  BeanPostProcessor.afterInitialization
       (may wrap with an AOP proxy)
                  |
                  v
           Bean ready for use
```

The diagram depicts **Spring's standard hook points**; it does not claim that every `BeanPostProcessor` implementation runs before `@PostConstruct`. `@PostConstruct` **is itself processed by a post-processor during the before-initialization phase**. Therefore, when adding multiple processors, detailed ordering must account for `PriorityOrdered`, `Ordered`, and their registration rules.

The phases have distinct meanings:

| Phase | What is Spring doing? | What can the bean rely on? |
| --- | --- | --- |
| Instantiate | Invokes constructor or factory method | Constructor parameters; must not assume all field/setter injection is finished |
| Populate properties | Injects dependencies/configuration values | Dependencies resolved per normal wiring |
| Aware callbacks | Supplies container metadata/infrastructure | E.g., bean name or `BeanFactory` |
| Before-initialization processors | Inspects, decorates, triggers annotation lifecycle | `@PostConstruct` may run here |
| `afterPropertiesSet` | `InitializingBean` callback | Required dependencies have been set |
| Custom init method | Configured named callback | Earlier callbacks on the same bean completed successfully |
| After-initialization processors | Finalizes the bean, may return wrapper/proxy | Final exposed instance may be a proxy |

**Do not equate "creating the Java object" with "bean is ready".** The constructor runs before Spring finishes all dependency injection and lifecycle callbacks. A bean instance may already exist while its initialization callbacks have not yet completed.

## 3. The Three Initialization Mechanisms That Can Be Combined

The focus of this lesson is **observing the order** when one bean enables all three callbacks with distinct names. They differ in where they are declared and how they attach to Spring:

| Callback | Where declared | What Spring needs to know |
| --- | --- | --- |
| `@PostConstruct void prepare()` | Method on bean class, `jakarta.annotation.PostConstruct` | Annotation processor supporting Jakarta; no-arg method |
| `InitializingBean.afterPropertiesSet()` | Bean class implements Spring interface | `afterPropertiesSet()` is the interface contract; class depends on Spring API |
| `@Bean(initMethod = "warmUp")` | Bean registration method in Java configuration | Bean instance has a matching no-arg `warmUp()` method |

For a bean with all three hooks, expect the trace `postConstruct → afterPropertiesSet → customInit`. That is the guaranteed order of **three distinct methods** in Spring; declaration order in the Java file or `@Order` does not reorder these three callbacks. If the same method name is configured across multiple mechanisms, Spring has logic to avoid invoking that method repeatedly; do not rely on duplicate declarations to run it multiple times.

`@Bean(initMethod = "warmUp")` can also be declared equivalently via XML `init-method="warmUp"`, though you only need one bean registration path in the experiment. For syntax details and coupling trade-offs, see the `InitializingBean`/`initMethod` lesson; the next section provides a standalone Gradle project to observe the actual trace, including before/after processors.

## 4. Complete Java 17+ Program Observing Exact Ordering

Create a small Gradle project to experiment directly with Spring Framework 6.2.x. This project does not need Spring Boot.

```text
bean-init-order/
├── settings.gradle
├── build.gradle
└── src/main/java/BeanInitOrderDemo.java
```

### settings.gradle

```groovy
rootProject.name = 'bean-init-order'
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
    mainClass = 'BeanInitOrderDemo'
}
```

`jakarta.annotation-api` is explicitly declared to ensure `@PostConstruct` and `@PreDestroy` are on the compile/runtime classpath. The example uses Java 17, Gradle 8+, and network access to download dependencies if not already cached.

### src/main/java/BeanInitOrderDemo.java

```java
import jakarta.annotation.PostConstruct;
import jakarta.annotation.PreDestroy;

import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class BeanInitOrderDemo {

    public static final class Helper {
    }

    public static class ManagedTask
            implements BeanNameAware, InitializingBean, DisposableBean {

        private Helper helper;

        public ManagedTask() {
            System.out.println("01 constructor");
        }

        @Autowired
        public void setHelper(Helper helper) {
            this.helper = helper;
            System.out.println("02 dependency injection");
        }

        @Override
        public void setBeanName(String name) {
            System.out.println("03 BeanNameAware: " + name);
        }

        @PostConstruct
        public void postConstruct() {
            if (helper == null) {
                throw new IllegalStateException("helper not injected");
            }
            System.out.println("04 @PostConstruct");
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println("05 afterPropertiesSet");
        }

        public void customInit() {
            System.out.println("06 customInit");
        }

        @PreDestroy
        public void preDestroy() {
            System.out.println("08 @PreDestroy");
        }

        @Override
        public void destroy() {
            System.out.println("09 DisposableBean.destroy");
        }

        public void customDestroy() {
            System.out.println("10 customDestroy");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean
        public Helper helper() {
            return new Helper();
        }

        @Bean(initMethod = "customInit",
              destroyMethod = "customDestroy")
        public ManagedTask managedTask() {
            return new ManagedTask();
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {
            ManagedTask task = context.getBean(ManagedTask.class);
            System.out.println("07 bean ready: " + (task != null));
        }
    }
}
```

Run in the project directory:

```bash
gradle run --quiet
# If you have generated the Gradle Wrapper, you can also run:
# ./gradlew run --quiet
```

The lines printed by the program via `System.out`, in order:

```text
01 constructor
02 dependency injection
03 BeanNameAware: managedTask
04 @PostConstruct
05 afterPropertiesSet
06 customInit
07 bean ready: true
08 @PreDestroy
09 DisposableBean.destroy
10 customDestroy
```

Logging libraries may emit additional environment info depending on configuration; the lines above are the output explicitly printed by **the program's logic**.

### Why is this order stable?

- `new ManagedTask()` runs inside the `@Bean` factory method, creating the object and printing `01`.
- Spring processes `@Autowired` on the `setHelper` setter when populating properties, before lifecycle init callbacks; prints `02`.
- `BeanNameAware.setBeanName` is called by the container after property population and before initialization callbacks; prints `03`. The bean name from the `@Bean managedTask()` method is `managedTask`.
- `CommonAnnotationBeanPostProcessor` detects `@PostConstruct` in the before-initialization processors chain, printing `04`.
- `InitializingBean.afterPropertiesSet` is called afterward, printing `05`.
- `initMethod = "customInit"` triggers the custom method, printing `06`.
- `getBean` after the context has refreshed receives the initialized bean; prints `07`.
- When `try-with-resources` closes the context, Spring invokes destruction callbacks on the **singleton** it manages in the order `@PreDestroy` → `DisposableBean.destroy` → custom destroy, printing `08` through `10`.

The `Helper` bean does not print anything itself, keeping the example focused on the single bean under observation. Spring resolving `Helper` before calling the setter does not change the order measured in this lesson.

## 5. Why Should You Not Skip the Steps Before @PostConstruct?

The same bean can receive dependencies via constructor, field, or setter. With setter/field injection, Spring invokes the constructor first and populates properties afterward. Therefore:

```java
@Component
class BadExample {
    @Autowired
    private DataSource dataSource;

    BadExample() {
        // dataSource is usually still null at this moment.
        // Do not call dataSource.getConnection() here.
    }

    @PostConstruct
    void initialize() {
        // Normal dependency injection has completed.
        // Validate configuration before opening/connecting resources if needed.
    }
}
```

This is an **illustrative anti-example**, omitting required imports/bean definitions. The comment in the constructor describes common field injection behavior, not a rule for constructor injection.

If a dependency is required in the constructor, **constructor-inject** that dependency:

```java
@Component
class BetterExample {
    private final DataSource dataSource;

    BetterExample(DataSource dataSource) {
        this.dataSource = dataSource;
    }
}
```

Spring supplies constructor arguments when creating the bean. This helps the class establish invariants early with fewer half-initialized states; however, you should not arbitrarily call methods on other beans inside a constructor if reverse dependencies or proxy lifecycles are not yet ready.

Inside `@PostConstruct`, normal dependencies have been supplied, but **there is no guarantee the entire context has finished refreshing** or unrelated singletons have finished initializing. If you need an event after all non-lazy singletons have been created, see `SmartInitializingSingleton` in Section 9.

## 6. Where Does BeanPostProcessor Sit Relative to @PostConstruct?

`BeanPostProcessor` defines two hooks:

```java
Object postProcessBeforeInitialization(Object bean, String beanName);
Object postProcessAfterInitialization(Object bean, String beanName);
```

These are **illustrative API signatures**; Spring actually defines them on the `BeanPostProcessor` interface.

At the pipeline level, Spring does the equivalent of:

```java
// PSEUDOCODE illustrating order, not standalone runnable source.
Object bean = instantiateAndPopulate();
invokeAwareInterfaces(bean);
bean = applyBeanPostProcessorsBeforeInitialization(bean);
invokeInitializingBean(bean);
invokeCustomInitMethod(bean);
bean = applyBeanPostProcessorsAfterInitialization(bean);
return bean;
```

**Crucial detail:** `@PostConstruct` does not run in a separate step standing outside every `BeanPostProcessor`. Spring uses `CommonAnnotationBeanPostProcessor` (extending `InitDestroyAnnotationBeanPostProcessor`) to run the annotated method during **before-initialization processing**.

Consequently, a user-defined `BeanPostProcessor.postProcessBeforeInitialization` can observe the bean **before or after `@PostConstruct`**, depending on processor ordering. Do not write down a rigid rule like "all before-processors → `@PostConstruct`". What Spring guarantees when combining the three callbacks is `@PostConstruct` before `afterPropertiesSet` and then before custom init, with distinct method names.

`postProcessAfterInitialization` runs after the init callbacks in the standard pipeline and may return a proxy. An AOP proxy created here can change the object clients receive via `getBean`, without causing the target's `@PostConstruct` callback to run again.

### Example custom processor just for observation

```java
import org.springframework.beans.factory.config.BeanPostProcessor;

class TraceProcessor implements BeanPostProcessor {
    @Override
    public Object postProcessBeforeInitialization(
            Object bean, String beanName) {
        if ("managedTask".equals(beanName)) {
            System.out.println("before-init processor");
        }
        return bean;
    }

    @Override
    public Object postProcessAfterInitialization(
            Object bean, String beanName) {
        if ("managedTask".equals(beanName)) {
            System.out.println("after-init processor");
        }
        return bean;
    }
}
```

This class is a **standalone illustrative snippet**, not yet registered in the Section 4 example. If integrated, output will add extra lines and the position of `before-init processor` relative to `@PostConstruct` will depend on ordering among post-processors; do not assume the Section 4 output remains unchanged.

When you need precise control over processor order, look into `PriorityOrdered`, `Ordered`, and `@Order` on **processor beans**, along with programmatic registration rules. Registering a processor too late will fail to affect beans already created.

## 7. When All Three Mechanisms Declare the Same Method

The Spring Reference explicitly states: if multiple init mechanisms **reference the same method name**, Spring does not invoke that method repeatedly just to satisfy each declaration. For example:

```java
public class SharedInit {
    @PostConstruct
    public void initialize() {
        System.out.println("initialize");
    }
}

@Configuration
class SharedInitConfig {
    @Bean(initMethod = "initialize")
    SharedInit sharedInit() {
        return new SharedInit();
    }
}
```

This is an illustrative snippet needing the corresponding imports. The point is to clarify that *the same `initialize` method* is annotated with `@PostConstruct` and simultaneously configured as `initMethod = "initialize"`; Spring detects this and avoids invoking the method twice when callbacks overlap.

Do not use duplicate method names to infer that every callback runs twice. If you want to measure ordering, use **distinct** names like `postConstruct`, `afterPropertiesSet`, and `customInit` in Section 4.

If one method simply calls another method written by the developer, that is an **ordinary Java call** and can repeat logic. The deduplication behavior above applies only to container lifecycle callback handling.

## 8. Destruction Ordering When Combining Multiple Mechanisms

Although this topic focuses on initialization, do not confuse the symmetric sequence when closing a bean. For a **container-managed singleton**, there are three destruction callbacks with distinct names:

1. `@PreDestroy`.
2. `DisposableBean.destroy()`.
3. Custom destroy method, e.g., `@Bean(destroyMethod = "customDestroy")`.

That is the order shown in the Section 4 program. Destruction callbacks are invoked when the context closes normally (or in certain scenarios when the container destroys a bean). Do not assume **all scopes** have destruction managed by Spring like singletons.

| Scope | Init callback | Destruction callback |
| --- | --- | --- |
| `singleton` | Runs when the container creates the bean | Managed by Spring when context closes or bean is destroyed |
| `prototype` | Runs every time Spring creates a new bean | Spring **does not automatically manage** prototype destruction after handing it to caller |
| `request` / `session` | Runs when creating an instance in an active scope | Depends on scope lifecycle in a web-aware context |
| Custom scope | Depends on scope implementation | Must check whether that scope invokes destruction callbacks |

For a prototype holding `AutoCloseable`/sockets/file streams, the caller must proactively clean up (for example via `try-with-resources`), regardless of whether the prototype's init callback ran.

For `@Bean`, Spring can also **infer a destroy method** such as `close` or `shutdown` when applicable. If exact control is required, configure an explicit name or disable inference per the API rules instead of guessing whether Spring will call a method.

## 9. Distinguishing Init Callbacks from Context-Ready Signals

The three callbacks `@PostConstruct`, `afterPropertiesSet`, and custom init run when **each individual bean** initializes. They do not mean the whole application has started.

### SmartInitializingSingleton

`SmartInitializingSingleton.afterSingletonsInstantiated()` is invoked once the container finishes **pre-instantiating normal (non-lazy) singletons**. It fits when a bean needs to act after ordinary singletons are constructed, such as auditing a registry.

```java
import org.springframework.beans.factory.SmartInitializingSingleton;

class RegistryVerifier implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Runs after the pre-instantiation pass of normal singletons.
        // Does not mean prototype/lazy beans have been created.
    }
}
```

The class above is an illustrative snippet; it must be registered as a bean. Do not treat this callback as a promise that every lazy singleton, prototype, or request bean already has an instance. Nor is it a callback that re-runs every time a prototype is created.

### ContextRefreshedEvent

`ContextRefreshedEvent` is published after an `ApplicationContext` completes the corresponding refresh. It operates at the **context level**, may occur on subsequent refreshes depending on context type, and in context hierarchies may require filtering the event source.

```java
import org.springframework.context.event.ContextRefreshedEvent;
import org.springframework.context.event.EventListener;

class ReadyListener {
    @EventListener
    public void onReady(ContextRefreshedEvent event) {
        // Handle context refresh milestone if truly needed.
    }
}
```

This is an illustrative snippet not registered as a bean. Do not move all `@PostConstruct` init logic into events merely to avoid understanding ordering; context-level events serve a different purpose. Spring Boot adds runners/availability events, but those belong to the **Spring Boot application lifecycle**, outside Spring Core's init callback contract.

### Lifecycle / SmartLifecycle

`Lifecycle.start/stop` and `SmartLifecycle` are meant for components needing service start/stop control (consumers, listeners, worker loops). They do not replace `@PostConstruct` when you merely need configuration validation. `SmartLifecycle` auto-startup and `phase` belong to **orchestration**; do not mix them into the order of a single bean's three init callbacks.

## 10. @DependsOn and @Order Do Not Reorder the Three Init Callbacks

Two annotations commonly misused to try to "fix ordering":

- `@DependsOn("databaseClient")` sets a dependency relationship between **beans**: before initializing the dependent bean, the container must create and initialize the depended-on bean. It **does not** alter the `@PostConstruct` → `afterPropertiesSet` → custom init order inside each bean.
- `@Order`/`Ordered` affects ordering in Spring mechanisms that support ordering (such as certain bean collections and processors); it does **not** by default guarantee creation order for all singleton beans regardless of dependencies.

Example diagram:

```text
DatabaseClient:
    constructor -> inject -> @PostConstruct -> afterPropertiesSet -> init

OrderService (@DependsOn("databaseClient")):
    constructor -> inject -> @PostConstruct -> afterPropertiesSet -> init
```

`@DependsOn` affects **which bean must finish first**, whereas **the callback order inside each bean** stays the same.

If you want to ensure one bean runs after another because it uses that dependency's API, constructor injection usually already expresses the proper relationship. `@DependsOn` is useful when a dependency is not directly expressed via injection yet still has an initialization constraint. Avoid using this annotation to hide circular dependency flaws or create unclear coupling.

## 11. Where Can the Sequence Change?

### Beans created by a factory method

A `@Bean` method creating an instance with `new` **still has Spring apply injection, Aware, and init callbacks** after the method returns. The Section 4 example proves this. However, **logic you call yourself inside the factory method body** runs before the method returns and cannot be automatically moved by Spring to the `@PostConstruct` phase.

If you write:

```java
@Bean(initMethod = "customInit")
ManagedTask managedTask() {
    ManagedTask task = new ManagedTask();
    task.customInit(); // Caller invokes manually right inside factory method.
    return task;
}
```

This is an **anti-example** and should not be merged into the main program. With this setup, `customInit` is invoked manually before Spring finishes injection, and then the container may also call the configured init callback afterward. Do not mistake that for "Spring automatically running init twice". Let the container manage lifecycle callbacks.

### BeanPostProcessor creating proxies or replacing references

`postProcessAfterInitialization` may return a different object (often an AOP proxy) than the original instance. Therefore:

- Init callbacks normally run on the target, before the final proxy is handed out.
- If you inspect the runtime class from `getBean()`, you may see a proxy type.
- Do not call business methods relying on advice inside `@PostConstruct` expecting advice to run like a call through the bean proxy.
- Avoid publishing `this` to threads/global registries in a constructor or init callback, because the object may not have completed its lifecycle or been proxied yet.

### Early bean creation and circular dependencies

`BeanPostProcessor` beans are registered early; if a processor configuration creates other dependencies too early, those beans might not be processed completely by all processors, leading to auto-proxying warnings. Circular dependencies also cause different behavior or failures when the container cannot resolve them. Prioritize fixing dependency structure; do not rely on declaration order to "get lucky".

### @Lazy and prototype

- A `@Lazy` singleton runs its init callbacks when actually created, **not necessarily at context refresh time**.
- A prototype runs its init callbacks each time the container creates an instance, but destruction is not called automatically like for a singleton.
- Dependency injection can pull a lazy bean in early if another bean needs it immediately.
- `@PostConstruct` does not re-run on every business method call; callbacks belong to **creating the bean instance**.

## 12. Common Errors and How to Fix Them

| Symptom | Misconception/cause | Resolution |
| --- | --- | --- |
| `@PostConstruct` does not run | Instance created with `new` outside Spring; missing Jakarta annotation processing; wrong namespace | Register bean in the right container; use `jakarta.annotation.PostConstruct` in Spring 6+, with annotation API and processor |
| `NullPointerException` in constructor | Reading an `@Autowired` field before injection has run | Use constructor injection or move logic to an init callback |
| Custom init runs "early" or twice | Developer called it manually in `@Bean` method while also configuring `initMethod` | Configure only one lifecycle call site, remove manual call |
| Before-processor and `@PostConstruct` differ from expectation | `@PostConstruct` is itself executed via a before-initialization processor | Check registration order/`Ordered` of post-processors |
| `afterPropertiesSet` runs before custom init | Expected behavior per Spring contract, even if custom init appears earlier in the file | Structure init methods to follow Spring's ordering |
| Lazy bean has not run init at startup | Nothing has requested creating that bean yet | Check `@Lazy` and when `getBean`/dependency resolution happens |
| Prototype does not run `@PreDestroy` on context close | Spring does not track destruction of individual prototypes | Caller cleans up itself |
| Init logic calls `@Transactional` method without a transaction | Internal call before final AOP proxy completes | Move work to a ready service after context startup; design transactions explicitly |
| Expecting `@Order` to order singleton initialization | `@Order` is not a dependency graph | Use dependency injection or `@DependsOn` |
| Using `SmartInitializingSingleton` expecting lazy/prototype beans to exist | Callback only follows pre-instantiation of normal singletons | Redefine the appropriate readiness milestone |
| Calling network/DB in init prevents whole context from starting | Exception escaping callback stops Spring from completing bean creation | Validate config, separate verification and appropriate retry/health; do not swallow required errors |

## 13. Practical Design Guidelines

**Use only one init mechanism per responsibility whenever possible.** For example: keep `@PostConstruct` to validate injected state, and use a dedicated business method `startPolling()` to start a worker at the application-ready phase. If combining multiple mechanisms is unavoidable (often when integrating legacy libraries), assign each callback a clear responsibility and document the order so maintainers do not accidentally rely on implementation details.

An easy-to-control division of responsibilities:

1. **Constructor**: establish object invariants from constructor arguments; do not publish `this`.
2. **Dependency injection**: container provides beans/configuration.
3. **`@PostConstruct`**: validate that config is complete, prepare local state.
4. **`afterPropertiesSet`** (if the interface is already a library contract): check/ensure the specific state promised by the interface.
5. **Custom init** (if needed): execute remaining legacy integration step.
6. **After-initialization**: let post-processors/proxies finalize.
7. **Context-level readiness**: run work requiring the full context at the right milestone, never assuming one bean's init means all beans are ready.
8. **Destruction**: manage shutdown/cleanup in scopes that actually support it, clearly identifying resource ownership.

Keep in mind that init callbacks can throw exceptions. If an exception goes unhandled, the container may fail bean creation and destroy previously completed singletons. Avoid attaching irreversible side effects to init callbacks without rollback/compensation and restart handling.

## 14. Self-Verification of This Lesson

You can modify the Section 4 program and test one change at a time:

1. **Remove `@PostConstruct`**: output no longer has `04 @PostConstruct`; `afterPropertiesSet` and custom init still run in their order.
2. **Remove `implements InitializingBean`** and its override method: `05 afterPropertiesSet` disappears; custom init still runs.
3. **Remove `initMethod = "customInit"`**: Spring no longer invokes the custom method automatically, unless your code calls it manually elsewhere.
4. **Change `@Bean` to prototype scope**: every instance retrieval runs the init chain; when closing the context, do not expect Spring to invoke destruction for that prototype.
5. **Add `@Lazy` to the singleton**: observe that callbacks can be deferred until the bean is actually requested.
6. **Add a custom BeanPostProcessor**: log before/after; compare relative positions and observe that `@PostConstruct` lives in the before-chain.
7. **Make `customInit()` throw an exception**: context initialization fails; the bean is not published as successfully initialized.

When writing JUnit tests, check an **event list** rather than just eyeballing logs. For instance, use a `List<String> events` test dependency to record `"postConstruct"`, `"afterPropertiesSet"`, and `"customInit"`, then assert the exact order. For multi-threaded tests, do not use a plain shared list without synchronization.

## 15. Remembering Key Boundaries

| Question | Accurate answer |
| --- | --- |
| In what order do three differently named init callbacks run? | `@PostConstruct` → `afterPropertiesSet()` → custom `initMethod` |
| Where is the constructor? | Before property injection and before the three init callbacks |
| Does `@Autowired` run before `@PostConstruct`? | Yes, in the normal injection lifecycle of a container-managed bean |
| Where is `BeanNameAware`? | After property population and before the standard initialization callbacks chain |
| Do all `postProcessBeforeInitialization` calls precede `@PostConstruct`? | **No**; `@PostConstruct` is triggered by a post-processor inside the before-chain |
| Is the AOP proxy already finalized when `@PostConstruct` runs? | Usually not; post-processors may proxy after init |
| Will declaring the same init method in multiple mechanisms invoke it twice? | Spring detects and avoids duplicate lifecycle invocation for the same method |
| Are different beans created in the line order of `@Configuration`? | No general guarantee; depends on wiring relationships, lazy/eager, and custom processors |
| Destruction order of three differently named callbacks? | `@PreDestroy` → `DisposableBean.destroy()` → custom destroy method |
| Are prototypes automatically destroyed when the context closes? | No; the caller is responsible for lifecycle after receiving a prototype |

## 16. Official References

- Spring Framework Reference — [Lifecycle Callbacks / Combining Lifecycle Mechanisms](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): order of `@PostConstruct`, `afterPropertiesSet`, custom init, and order of the three destroy callbacks.
- Spring Framework Reference — [Container Extension Points: BeanPostProcessor](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): before/after initialization, processor ordering, early instantiation, and proxying.
- Spring Framework Reference — [Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/annotation-config.html): annotation processors registered by `AnnotationConfigApplicationContext`.
- Spring Framework Reference — [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): prototype init callbacks, destruction limits, and singleton dependencies.
- Maven Central — [spring-context 6.2.18](https://central.sonatype.com/artifact/org.springframework/spring-context/6.2.18): dependency version used in the Java 17 program.

When combining multiple mechanisms on **the same bean**, simply remember the standard axis **`@PostConstruct` → `afterPropertiesSet()` → custom init**; any deeper analysis must also examine injection timing, `BeanPostProcessor` ordering, bean scope, and when the application/context is genuinely ready.
