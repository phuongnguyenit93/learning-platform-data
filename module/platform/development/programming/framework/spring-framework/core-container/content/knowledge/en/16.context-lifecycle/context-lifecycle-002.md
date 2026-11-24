# ApplicationContext Lifecycle: Loading Definitions, Running Post-Processors, and Creating Singletons

## 1. Purpose and significance

A Spring `ApplicationContext` does not simply "scan classes and call constructors." During `refresh()`, the container moves through several ordered steps designed deliberately: **reading and registering bean definitions**, opening opportunities for extension points to modify metadata, **registering processors that run on instances**, and finally **creating non-lazy singletons** and publishing the context refreshed event.

Understanding this sequence helps answer common questions:

- Why does `BeanFactoryPostProcessor` modify metadata before beans are created?
- How does `BeanDefinitionRegistryPostProcessor` differ from `BeanFactoryPostProcessor` in capabilities?
- Why are `BeanPostProcessor` instances registered before business beans are initialized?
- Why do constructor, `@PostConstruct`, `afterPropertiesSet()`, custom init, `SmartInitializingSingleton`, and `ContextRefreshedEvent` appear at different times?
- What exceptions exist to "singletons are created at startup" with `@Lazy`, `prototype`, and `FactoryBean`?
- When does calling `getBean()` early break post-processing expectations?

This lesson focuses on the **Core Container of Spring Framework 6.2**, applicable to 6.x versions sharing the same contract. Spring Boot adds auto-configuration, runners, and some lifecycle events; those sit at a higher layer and do not alter this fundamental principle.

## 2. Four concepts to distinguish

| Concept | What is it? | Example |
| --- | --- | --- |
| **Bean definition** | Metadata/container recipe describing class/factory method, scope, dependencies, lazy, init/destroy callbacks | `BeanDefinition`, `RootBeanDefinition` |
| **Bean instance** | Actual object created by the container or obtained from a factory, with its own lifecycle | `new OrderService(...)` |
| **BeanFactory** | Component holding definitions, creating and looking up beans, managing scopes | `ConfigurableListableBeanFactory`, `DefaultListableBeanFactory` |
| **ApplicationContext** | High-level container integrating BeanFactory with Environment, events, resources, internationalization, and lifecycle | `AnnotationConfigApplicationContext`, `GenericApplicationContext` |

An easily confused phrase: "registered bean" may only mean **the bean definition exists**, with no instance yet. `containsBeanDefinition("orderService")` can return `true` before `OrderService`'s constructor runs.

`BeanDefinition` typically records type/constructor args/property values/scope/lazy flags. Bean definitions may also attach a factory method, parent definition, or configuration requiring post-processing before eventually creating the instance.

## 3. Big picture of refresh()

In `AbstractApplicationContext` subclasses, `refresh()` is the key orchestration point. Simplified diagram keeping the core phases:

```text
refresh()
  |
  +--> prepareRefresh()
  |       - startup state, environment
  |
  +--> obtainFreshBeanFactory()
  |       - obtain/return appropriate BeanFactory
  |       - load bean definitions depending on context type
  |
  +--> prepareBeanFactory()
  |       - class loader, expression resolver,
  |         foundational Aware/processors
  |
  +--> postProcessBeanFactory() [subclass hook]
  |
  +--> invokeBeanFactoryPostProcessors()
  |       - BeanDefinitionRegistryPostProcessor
  |       - BeanFactoryPostProcessor
  |       - process @Configuration, @Bean, @Import,
  |         @ComponentScan, placeholders... as appropriate
  |
  +--> registerBeanPostProcessors()
  |       - prepare processors handling bean instances
  |
  +--> initMessageSource()
  +--> initApplicationEventMulticaster()
  +--> onRefresh() [subclass hook]
  +--> registerListeners()
  |
  +--> finishBeanFactoryInitialization()
  |       - remaining preparation/metadata steps
  |       - preInstantiateSingletons()
  |       - create regular non-lazy singletons
  |       - SmartInitializingSingleton callbacks
  |
  +--> finishRefresh()
          - start appropriate lifecycle processor
          - publish ContextRefreshedEvent
          - notify that context completed refresh
```

This is a study-oriented interpretation, **not a verbatim source copy**. For example, with `GenericApplicationContext` or `AnnotationConfigApplicationContext`, some definitions are already registered **before** `refresh()` via `register(...)`, `registerBean(...)`, or registry APIs. With XML-reading contexts, definitions may be loaded during `obtainFreshBeanFactory()`. Do not claim that every context type "only begins registering definitions after `refresh()` is called."

**Key invariant:** processors handling **BeanFactory metadata** must run before the bulk creation loop of regular singletons. `BeanPostProcessor`s must be registered before business beans are created so they have the opportunity to apply fully.

## 4. Loading and building bean definitions

### 4.1. Bean definition sources

Spring can receive metadata from multiple sources:

- XML `<bean>`: class, constructor args, property values, scope, init/destroy methods.
- `@Configuration` and `@Bean`: factory methods become bean definitions; the configuration class also has a definition.
- `@Component`, `@Service`, `@Repository`, and `@Controller`: component scanning discovers classes and creates definitions.
- `@Import`, `ImportSelector`, `ImportBeanDefinitionRegistrar`: add configuration content/definitions per contract.
- Java API: `GenericApplicationContext.registerBean(...)` or `BeanDefinitionRegistry.registerBeanDefinition(...)`.
- Extension points: `BeanDefinitionRegistryPostProcessor` can register additional definitions before business beans are created.

The approaches above do not by default instantiate objects immediately upon registration. `@ComponentScan` also does not "`new` every class at scan time": it puts metadata into the registry for the container to process later.

### 4.2. Class metadata and runtime instance

Example of a programmatic definition:

```java
BeanDefinition definition = BeanDefinitionBuilder
        .genericBeanDefinition(ReportService.class)
        .setScope(BeanDefinition.SCOPE_SINGLETON)
        .setLazyInit(false)
        .getBeanDefinition();

registry.registerBeanDefinition("reportService", definition);
```

This is an **illustrative code snippet**, requiring a `registry` of type `BeanDefinitionRegistry` and an actually existing `ReportService` class; it is not a standalone Java program. `registerBeanDefinition` here primarily puts the *recipe* into the registry. The constructor will run when the bean needs to be created, usually during `preInstantiateSingletons()` if it is a regular non-lazy singleton.

Registering two definitions with the same name, aliases, bean definition overriding, and conditional configuration are separate topics. For production, avoid relying on default overriding rules because they may differ across containers/configurations.

### 4.3. @ConfigurationClassPostProcessor

`ConfigurationClassPostProcessor` is a flagship extension point: it is a `BeanDefinitionRegistryPostProcessor` and interprets `@Configuration`, `@ComponentScan`, `@Import`, `@Bean`, and related configuration constructs. Because it can discover and register **additional** bean definitions, running the configuration processing step must complete before Spring decides the regular singleton initialization loop.

A class:

```java
@Configuration(proxyBeanMethods = false)
class AppConfiguration {
    @Bean
    ServiceA serviceA() {
        return new ServiceA();
    }
}
```

should not be understood as "the moment Spring reads the annotation, it calls `serviceA()` and creates `ServiceA`." The `@Bean` method becomes a factory recipe; Spring invokes the method when the bean is actually requested according to its scope.

This is an illustrative configuration snippet, omitting imports and definitions of `ServiceA`.

## 5. BeanDefinitionRegistryPostProcessor: intervening in the registry

The `org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor` interface extends `BeanFactoryPostProcessor` with an additional method:

```java
void postProcessBeanDefinitionRegistry(
        BeanDefinitionRegistry registry);
```

This is an illustrative signature from the interface. It allows registering or adjusting bean definitions **before regular `BeanFactoryPostProcessor`s are discovered and executed**.

An implementation has two hook points:

```java
class CustomRegistrar implements BeanDefinitionRegistryPostProcessor {

    @Override
    public void postProcessBeanDefinitionRegistry(
            BeanDefinitionRegistry registry) {
        // Registry phase: add/modify definitions.
    }

    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // BeanFactory phase: inspect/modify factory metadata.
    }
}
```

This is an illustrative snippet; imports for `BeanDefinitionRegistryPostProcessor`, `BeanDefinitionRegistry`, and `ConfigurableListableBeanFactory` are needed. The two methods belong to **two different invocation phases** even on the same processor instance.

Legitimate tasks during the registry phase: adding conditional bean definitions, adjusting scope/lazy flags, creating synthetic infrastructure bean definitions, or integrating a custom configuration mechanism. Because this is when the container is still building metadata, **do not call `getBean()` just to "check if the bean works"**: that can cause the instance to be created too early, before other processors are ready.

### A registry processor can register further processors

Spring must handle the case where a `BeanDefinitionRegistryPostProcessor` registers another `BeanDefinitionRegistryPostProcessor`. Therefore, a standard implementation continues looking for unexecuted registry processors before concluding the registry phase. This is one reason why order cannot be inferred simply from the position of Java methods in source files.

When registry processors are auto-detected by Spring as beans, `PriorityOrdered` and `Ordered` help order them **within the appropriate group**; for processors registered directly via `ConfigurableApplicationContext.addBeanFactoryPostProcessor(...)`, programmatic registration order applies to that group, and metadata order is not used in the same way.

## 6. BeanFactoryPostProcessor: modifying definitions before bean creation

`BeanFactoryPostProcessor` defines:

```java
void postProcessBeanFactory(
        ConfigurableListableBeanFactory beanFactory);
```

This is an illustrative API signature. This processor operates on the **BeanFactory and bean definitions**, not on **a bean instance just created by a constructor**.

Valid examples:

- Modifying property values held in a `BeanDefinition`.
- Applying placeholder configuration with `PropertySourcesPlaceholderConfigurer`.
- Registering a custom scope with `CustomScopeConfigurer`.
- Adjusting metadata so beans are created properly later.

General logical order:

```text
Definitions already in registry
    -> registry post-processors run
    -> factory post-processors run
    -> BeanPostProcessors are registered
    -> regular singletons are created
```

**Note**: if code in a `BeanFactoryPostProcessor` actively calls `getBean()`, it **can force early initialization of a bean**. That defeats the benefit of the metadata phase and may leave the bean without full `BeanPostProcessor` handling or AOP proxying. This is an anti-pattern to avoid.

### BeanFactoryPostProcessor vs BeanPostProcessor

| Criterion | BeanFactoryPostProcessor | BeanPostProcessor |
| --- | --- | --- |
| Target processed | BeanFactory and metadata/bean definitions | Bean instance |
| Typical timing | During `invokeBeanFactoryPostProcessors()`, before creating regular singletons | During each bean's initialization |
| Core API | `postProcessBeanFactory(...)` | `postProcessBeforeInitialization(...)` / `postProcessAfterInitialization(...)` |
| Examples | `PropertySourcesPlaceholderConfigurer`, `CustomScopeConfigurer` | `CommonAnnotationBeanPostProcessor`, auto-proxy creators |
| Common mistake | Calling `getBean` too early | Confusing with modifying bean definitions |
| Can add bean definitions? | Not the primary purpose of regular BFPP | Not the role of BPP |
| Ordered by | `PriorityOrdered`/`Ordered` for auto-detected BFPPs, separate rules when added manually | `PriorityOrdered`/`Ordered` depending on BPP registration method |

`BeanDefinitionRegistryPostProcessor` is a specialized case with permission to work with the registry, unlike a regular `BeanFactoryPostProcessor`.

## 7. Registering BeanPostProcessors before singleton creation

`BeanPostProcessor` provides two common hooks:

```java
Object postProcessBeforeInitialization(
        Object bean, String beanName);

Object postProcessAfterInitialization(
        Object bean, String beanName);
```

They run for each bean created by Spring that passes through the corresponding pipeline; the processor can return the original instance or a wrapper/proxy. Spring registers beans implementing `BeanPostProcessor` into the BeanFactory during the `registerBeanPostProcessors()` phase, before `finishBeanFactoryInitialization()` creates regular non-lazy singletons.

### BeanPostProcessor does not mean "after every callback"

On a regular Spring-managed bean:

```text
instantiate
 -> dependency injection/populate properties
 -> BeanNameAware / BeanFactoryAware and basic aware hooks
 -> postProcessBeforeInitialization (chain of processors)
      [may handle @PostConstruct in this chain]
 -> InitializingBean.afterPropertiesSet()
 -> custom init-method
 -> postProcessAfterInitialization (chain of processors)
      [may create AOP proxy]
 -> bean ready to be published
```

`@PostConstruct` is handled by a lifecycle annotation processor (typically `CommonAnnotationBeanPostProcessor`) in the **before-initialization chain**. Hence it is incorrect to say "every user-defined before processor necessarily runs before `@PostConstruct`." Relative ordering among the relevant processors also depends on order/registration.

An AOP proxy is normally created/finalized during the post-processing stages. If you call a method needing advice inside the constructor or `@PostConstruct`, do not assume the call goes through the final proxy.

### Why do processors themselves sometimes miss full AOP?

`BeanPostProcessor`s and the dependencies they require may need to be created **early so the container is capable of processing other beans**. Therefore, they may not be eligible for auto-proxying because the remaining processors have not yet been registered. Spring may log messages like "not eligible for getting processed by all BeanPostProcessors", depending on configuration. This is a signal to inspect the dependency graph and bean creation timing, not to silence logging and ignore it.

## 8. finishBeanFactoryInitialization() and non-lazy singletons

Once metadata processors have run, BeanPostProcessors have been registered, and context supporting components are prepared, Spring executes `finishBeanFactoryInitialization(beanFactory)`. Among its internal steps, the pivotal call is `preInstantiateSingletons()`.

**Goal:** pre-create most `singleton` beans with `lazy-init=false` to detect wiring/configuration errors early and prepare the application to serve.

A regular singleton at this point goes through:

1. Resolving and selecting a constructor or factory method.
2. Resolving constructor arguments and required dependencies.
3. Instantiating the object.
4. Populating property/field/setter dependencies.
5. Invoking appropriate `Aware` callbacks.
6. Running pre-initialization `BeanPostProcessor`s, including lifecycle annotation callbacks.
7. Invoking `InitializingBean.afterPropertiesSet()` if implemented.
8. Invoking custom init method if configured.
9. Running post-initialization `BeanPostProcessor`s; may return an AOP proxy.
10. Storing/exposing the completed singleton in the singleton registry.

Some details here may be optimized by Spring, invoked earlier due to dependencies, or specially handled for FactoryBeans/AOP/circular references. Do not treat the list above as a guarantee that every bean is created identically.

### Which singletons are not necessarily created right away?

- `@Lazy` singletons not yet needed by any eager bean.
- `prototype` beans are not bulk-created merely because a definition exists.
- `request`/`session` beans depend on active scope and context.
- Beans without an independent definition created only by manual `new` code do not belong to the container-managed process.
- With `FactoryBean`, distinguish the singleton **factory object** and the **product** returned by `getObject()`; special cases exist involving `SmartFactoryBean` and eager initialization.

### Depends-on, constructor dependency, and ordering

Spring respects true dependency relationships: a bean with a constructor parameter needing another bean pulls the depended-upon bean into the creation cycle first; `@DependsOn` declares a dependency that must initialize beforehand. This **does not establish a global total order** for unrelated singletons.

Do not rely on `@Bean` method declaration order, class name order, or package scanning order as a startup contract. `@Order` also does not mean all singletons will be instantiated in that order.

## 9. After singleton creation: SmartInitializingSingleton and ContextRefreshedEvent

`SmartInitializingSingleton.afterSingletonsInstantiated()` runs at the end of the regular singleton pre-instantiation loop. It is useful when a singleton must perform validation after **regular eager singletons have already been created**, without accidentally forcing them to be created too early in `@PostConstruct`.

```java
public class RegistryCheck implements SmartInitializingSingleton {
    @Override
    public void afterSingletonsInstantiated() {
        // Verify after non-lazy singleton pre-instantiation loop.
    }
}
```

This is an illustrative snippet, requiring interface imports and the class to be registered as a singleton bean. This callback **does not run on prototypes** and does not automatically run for late-created lazy singletons. It also does not mean all external systems (database, queue, network) are healthy.

At `finishRefresh()`, the container uses the lifecycle processor to start appropriate lifecycle components, then publishes `ContextRefreshedEvent`. Applications can listen to this milestone:

```java
@Component
class RefreshedListener {
    @EventListener
    void ready(ContextRefreshedEvent event) {
        // An ApplicationContext has just finished refreshing.
    }
}
```

This is an illustrative snippet requiring imports for `Component`, `EventListener`, and `ContextRefreshedEvent`. In a context hierarchy, events from a child can propagate to the parent; if you need to handle only a specific context, filter by `event.getApplicationContext()`.

**Do not equate an individual bean's init callback with the context-refreshed event.** During bean A's `@PostConstruct`, other singletons may not have finished yet. After `ContextRefreshedEvent`, that refresh is complete, though lazy beans or prototypes may still be uncreated.

## 10. Hands-on Java 17+ example observing the event sequence

The following example uses Spring Framework 6.2.x without Spring Boot. It intentionally **registers a registry processor, a factory processor, and an instance post-processor via Java API** so the execution flow is observable, then creates a non-lazy singleton and closes the context. Component scanning is omitted in this example to cleanly separate the phases.

Structure:

```text
context-startup-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/ContextStartupDemo.java
```

### settings.gradle

```groovy
rootProject.name = 'context-startup-demo'
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
    implementation 'org.springframework:spring-context:6.2.19'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'ContextStartupDemo'
}
```

### src/main/java/ContextStartupDemo.java

```java
import org.springframework.beans.factory.BeanNameAware;
import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.SmartInitializingSingleton;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.beans.factory.config.ConfigurableListableBeanFactory;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.beans.factory.support.BeanDefinitionRegistryPostProcessor;
import org.springframework.context.ApplicationListener;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.event.ContextRefreshedEvent;

public class ContextStartupDemo {

    static class Registrar implements BeanDefinitionRegistryPostProcessor {
        @Override
        public void postProcessBeanDefinitionRegistry(
                BeanDefinitionRegistry registry) {
            System.out.println("01 BDRPP.registry");
            registry.registerBeanDefinition(
                    "task",
                    BeanDefinitionBuilder
                            .genericBeanDefinition(TrackedTask.class)
                            .setInitMethodName("customInit")
                            .setDestroyMethodName("customDestroy")
                            .getBeanDefinition()
            );
        }

        @Override
        public void postProcessBeanFactory(
                ConfigurableListableBeanFactory beanFactory) {
            System.out.println("02 BDRPP.factory");
        }
    }

    static class TracingPostProcessor implements BeanPostProcessor {
        @Override
        public Object postProcessBeforeInitialization(
                Object bean, String beanName) {
            if ("task".equals(beanName)) {
                System.out.println("06 BPP.before");
            }
            return bean;
        }

        @Override
        public Object postProcessAfterInitialization(
                Object bean, String beanName) {
            if ("task".equals(beanName)) {
                System.out.println("09 BPP.after");
            }
            return bean;
        }
    }

    public static class TrackedTask
            implements BeanNameAware, InitializingBean,
                       SmartInitializingSingleton,
                       ApplicationListener<ContextRefreshedEvent>,
                       DisposableBean {

        public TrackedTask() {
            System.out.println("04 constructor");
        }

        @Override
        public void setBeanName(String beanName) {
            System.out.println("05 BeanNameAware " + beanName);
        }

        @Override
        public void afterPropertiesSet() {
            System.out.println("07 afterPropertiesSet");
        }

        public void customInit() {
            System.out.println("08 customInit");
        }

        @Override
        public void afterSingletonsInstantiated() {
            System.out.println("10 afterSingletonsInstantiated");
        }

        @Override
        public void onApplicationEvent(ContextRefreshedEvent event) {
            System.out.println("11 ContextRefreshedEvent");
        }

        @Override
        public void destroy() {
            System.out.println("13 DisposableBean.destroy");
        }

        public void customDestroy() {
            System.out.println("14 customDestroy");
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext()) {

            // Register registry/factory processors before refresh().
            context.addBeanFactoryPostProcessor(new Registrar());
            context.addBeanFactoryPostProcessor(
                    beanFactory -> System.out.println(
                            "03 BFPP.definition=" +
                            beanFactory.containsBeanDefinition("task")));

            // Register a manual BPP before business beans are created.
            context.getBeanFactory().addBeanPostProcessor(
                    new TracingPostProcessor());

            context.refresh();

            TrackedTask first = context.getBean(TrackedTask.class);
            TrackedTask second = context.getBean(TrackedTask.class);
            System.out.println("12 sameSingleton=" + (first == second));
        }
    }
}
```

Run from the directory containing `build.gradle`:

```bash
gradle run --quiet
# If Gradle Wrapper is already created in the project:
# ./gradlew run --quiet
```

Lines **printed by the program via System.out**:

```text
01 BDRPP.registry
02 BDRPP.factory
03 BFPP.definition=true
04 constructor
05 BeanNameAware task
06 BPP.before
07 afterPropertiesSet
08 customInit
09 BPP.after
10 afterSingletonsInstantiated
11 ContextRefreshedEvent
12 sameSingleton=true
13 DisposableBean.destroy
14 customDestroy
```

**Why does this order make sense?**

1. `Registrar` is manually registered with the context and runs the registry phase first; that method puts the `task` definition into the registry.
2. `Registrar.postProcessBeanFactory` runs in the registrar's factory processor phase.
3. The BFPP lambda runs after the registrar phase and observes `containsBeanDefinition("task") == true`, proving the definition exists without `task` needing to be instantiated yet.
4. `refresh()` reaches `finishBeanFactoryInitialization()` and creates `TrackedTask` as a default singleton; constructor prints `04`.
5. `BeanNameAware` runs in the bean initialization step; the name assigned by the registry is `task`.
6. `TracingPostProcessor` was added before refresh, so it receives the before callback.
7. `InitializingBean.afterPropertiesSet` runs, followed by the custom init named `customInit` defined in bean metadata.
8. `TracingPostProcessor` receives the after callback.
9. `SmartInitializingSingleton.afterSingletonsInstantiated` runs when regular singleton pre-instantiation concludes.
10. `ContextRefreshedEvent` is published during the finish refresh step. `TrackedTask` is also an `ApplicationListener`, so it is invoked.
11. Both `getBean(TrackedTask.class)` calls return the same singleton.
12. When `try-with-resources` closes the context, `DisposableBean.destroy()` runs before custom destroy on the same bean.

If other beans/processors are added to the program, logs may interleave additional events or indirectly alter order. That is why the program uses simple methods and intentionally prints sequence numbers. Framework logging is not part of the listed `System.out` lines.

## 11. Variation: where does @PostConstruct fit?

`TrackedTask` can be extended with:

```java
import jakarta.annotation.PostConstruct;

@PostConstruct
public void initAnnotated() {
    System.out.println("@PostConstruct");
}
```

This is a code snippet to add to the program's class, requiring the `jakarta.annotation:jakarta.annotation-api` dependency on the classpath when needed. When Spring registers the lifecycle annotation processor, this method runs in the `BeanPostProcessor.postProcessBeforeInitialization` chain. It happens **before `afterPropertiesSet` and before custom init**, though the relative position between the manually registered `BPP.before` log and `@PostConstruct` depends on post-processor ordering. Do not paste this snippet and expect the pre-printed output in section 10 to stay unchanged.

For the three differently named init mechanisms on the same bean, Spring specifies:

```text
@PostConstruct
 -> InitializingBean.afterPropertiesSet()
 -> custom init-method
```

That is the order of init callbacks on **each individual bean**, independent of whether unrelated beans are created before or after each other.

## 12. How Spring orders post-processors

### 12.1. Factory-level processors

When the container **auto-detects** a `BeanDefinitionRegistryPostProcessor` or `BeanFactoryPostProcessor` as a bean, the `PriorityOrdered` and `Ordered` interfaces can control ordering **within the corresponding processing group**. Spring must finish the registry phase before proceeding with regular BFPPs.

An important point: `@Order` on a bean class **does not automatically replace** `BeanFactoryPostProcessor` ordering rules. Javadoc states `@Order` is not considered for BFPP beans, whereas `PriorityOrdered` and `Ordered` are used if the processor is auto-detected.

If processors are registered directly via `context.addBeanFactoryPostProcessor(...)`, they are applied in **registration order** per the programmatic mechanism; their `PriorityOrdered`/`Ordered` are not used by Spring as when processors are auto-detected.

### 12.2. Instance-level processors

`BeanPostProcessor` operates on objects. Auto-detected BPPs have an order tied to `PriorityOrdered`/`Ordered` or appropriate registration order. When you call `beanFactory.addBeanPostProcessor(...)` directly, that registration order matters, and newly registered processors can also affect how remaining auto-detected BPPs are invoked.

When you must control the order of multiple BPPs, test on the specific target Spring version, verify the order contract, and do not instantiate business beans before processors are registered.

### 12.3. Do not use @Order to order all singletons

`@Order` has several purposes, such as ordering collection dependencies or extension points that support ordering. It **is not a total instantiation order for all singletons**. If service A needs B ready beforehand, declare a constructor dependency or `@DependsOn` in appropriate cases.

## 13. @Lazy, prototype, request scope, and changing creation timing

| Bean type | Has definition at refresh? | When instance appears |
| --- | --- | --- |
| Regular eager singleton | Yes | Usually during `preInstantiateSingletons()`, possibly earlier if needed by a dependency |
| `@Lazy` singleton | Yes | When actually needed for the first time; may be requested by an eager bean right at refresh |
| Prototype | Yes | Each time BeanFactory creates/resolves a prototype (unless a prototype reference is held fixed inside another bean) |
| Request-scoped | Yes | When request scope is active and the bean is requested |
| Session-scoped | Yes | When session scope is active and the bean is requested |
| `FactoryBean` | Has factory definition | Factory and product have separate lifecycle/cache semantics; see scope and factory contract |

Example:

```java
@Configuration(proxyBeanMethods = false)
class LazyConfig {
    @Bean
    @Lazy
    ExpensiveClient expensiveClient() {
        return new ExpensiveClient();
    }
}
```

This is an illustrative snippet; the `ExpensiveClient` class is not defined. The definition can already exist when context refresh completes while an `ExpensiveClient` instance has never been created. However, if an eager singleton directly depends on `ExpensiveClient` via constructor injection, the bean may be created immediately to satisfy the dependency despite being annotated lazy.

With prototype, the bean also receives BeanPostProcessors/init callbacks each time it is created via the container. Spring does not automatically track complete destruction for prototypes after handing them to the caller; the caller must handle cleanup proactively.

## 14. FactoryBean: factory initialization is not identical to product

`FactoryBean<T>` is a special Spring contract: the bean definition typically represents the **factory**; calling `getBean("name")` can obtain the **product** created by `getObject()`, while `getBean("&name")` obtains the factory.

Hence two questions must be separated:

1. When is the **factory instance** created/initialized?
2. When is the **product** created and whether it is cached, according to `FactoryBean.isSingleton()` and BeanFactory semantics?

Do not claim that "because the factory singleton is eager, all products of every FactoryBean are definitely eager too." `SmartFactoryBean.isEagerInit()` and lookup/type resolution mechanisms can affect specific cases. BeanPostProcessors can process both the factory object and products according to container-supported rules.

When debugging, use the exact bean name/`&` prefix and inspect the bean definition, `FactoryBean` implementation, and lazy/eager conditions of the current version.

## 15. Early bean creation: why is it dangerous?

Warnings such as:

```text
Bean 'x' is not eligible for getting processed by all BeanPostProcessors
```

indicate that instance `x` was created when the processor set was not yet complete (depending on the Spring version and specific circumstances). Possible causes include:

- A `BeanFactoryPostProcessor` calls `getBean("x")` in `postProcessBeanFactory`.
- A `BeanPostProcessor`'s constructor requires too many business beans.
- An auto-proxy creator or related processor initializes dependencies early.
- A bean must be initialized early to process metadata/processors before all infrastructure finishes.

Anti-pattern example:

```java
class BadFactoryProcessor implements BeanFactoryPostProcessor {
    @Override
    public void postProcessBeanFactory(
            ConfigurableListableBeanFactory beanFactory) {
        // Do not do this just to "validate" a business bean.
        Object service = beanFactory.getBean("businessService");
        System.out.println(service);
    }
}
```

This is an illustrative snippet; imports for `BeanFactoryPostProcessor` and `ConfigurableListableBeanFactory` are required. Because BFPP runs in the metadata phase, `getBean` can cause `businessService` to be instantiated before many auto-detected `BeanPostProcessor`s are registered.

Alternative: validate bean definition **metadata** in the factory processor phase; if you must work with instances, move the logic to a post-singleton-initialization callback such as `SmartInitializingSingleton` or an appropriate event, but only when that is the right business milestone.

## 16. Verifying that context actually created the singleton

Some useful observations:

```java
ConfigurableListableBeanFactory factory =
        context.getBeanFactory();

boolean hasDefinition = factory.containsBeanDefinition("task");
boolean hasSingleton = factory.containsSingleton("task");
boolean singletonConfigured = factory.getBeanDefinition("task").isSingleton();
```

This is an illustrative snippet, assuming `context` is an initialized `AnnotationConfigApplicationContext`, and also needing the `ConfigurableListableBeanFactory` import. These answer **different** questions:

- `containsBeanDefinition`: whether the recipe exists in the local BeanFactory.
- `containsSingleton`: whether the singleton instance with the corresponding name is already registered in the singleton cache.
- `BeanDefinition.isSingleton`: whether metadata specifies singleton scope; does not prove an instance already exists.

In particular, before `refresh` on `AnnotationConfigApplicationContext`, do not proactively call arbitrary factory APIs that require an active context just for probing; the safe pattern in the demo is reading registry metadata when appropriate, then reading runtime state after `refresh()`.

If you need to inspect **singleton count**, `getSingletonCount()` counts singleton instances registered in the cache, including many infrastructure beans, and cannot be equated with the total number of `@Component` classes or definitions in the registry.

### Useful logs and breakpoints

Enable debug/trace logging for appropriate Spring beans/context packages in a local environment to track bean definitions, dependency resolution, and bean instantiation. Specific log messages may change across versions; do not write tests relying on fixed internal log text.

Useful debugging points:

- `AbstractApplicationContext.refresh()` to trace the phases.
- `PostProcessorRegistrationDelegate.invokeBeanFactoryPostProcessors(...)`.
- `PostProcessorRegistrationDelegate.registerBeanPostProcessors(...)`.
- `DefaultListableBeanFactory.preInstantiateSingletons()`.
- `AbstractAutowireCapableBeanFactory.createBean(...)` / `doCreateBean(...)`.
- `AbstractAutowireCapableBeanFactory.initializeBean(...)`.
- `AbstractApplicationContext.finishRefresh()`.

Method/class names are references for reading Spring Framework source; they are not APIs that business code should depend on.

## 17. Common misconceptions

| Misconception | More accurate |
| --- | --- |
| "Once scanning finishes, all objects have been `new`ed" | Scanning creates/registers definitions; instance creation is a separate phase |
| "BFPP is a callback running on bean objects" | BFPP operates on the factory/definitions; BPP is what operates on instances |
| "Registry post-processors only read definitions" | BDRPP can add/modify definitions in the registry |
| "Every singleton is only created during finishBeanFactoryInitialization" | That is the general eager loop; dependencies/infrastructure may be created earlier |
| "@Lazy beans are guaranteed not to be created until after startup" | If an eager bean depends on it, the lazy bean may need to be created immediately |
| "@Order always controls constructor order" | No; the dependency graph and lifecycle hooks are what must be examined |
| "A bean having a definition means getBean returns a ready object" | A definition can exist when the object has not yet been instantiated |
| "@PostConstruct is a callback running after every BeanPostProcessor" | It is triggered by a lifecycle processor in the before-initialization chain |
| "SmartInitializingSingleton reports all beans of all scopes have instances" | Only the end milestone of regular singleton pre-instantiation |
| "ContextRefreshedEvent means all external resources are ready" | The event only guarantees that the context's refresh completed |
| "BeanFactoryPostProcessor is for mutating bean state" | It should modify metadata and avoid creating objects early |
| "An eager FactoryBean means the product is always eager" | Factory and product are two objects; behavior also depends on the FactoryBean contract |

## 18. Design and testing checklist

Before creating a custom extension point:

1. Do you want to **add bean definitions** or only modify metadata of existing definitions? Choose `BeanDefinitionRegistryPostProcessor` or `BeanFactoryPostProcessor` accordingly.
2. Do you want to modify an instance right when it is created? Choose `BeanPostProcessor`.
3. Do you want init logic **on a single bean after dependency injection**? Use `@PostConstruct`, `InitializingBean`, or a custom init method, avoiding long/blocking logic calling many other beans.
4. Do you need work to run **after non-lazy singletons**? Consider `SmartInitializingSingleton`.
5. Do you need the milestone when the context finishes refreshing? Listen to `ContextRefreshedEvent`, accounting for hierarchies/repeated emissions.
6. Is the bean an eager singleton, lazy singleton, prototype, or custom scope? Scope determines instance creation and ownership.
7. Does any processor call `getBean()` in a constructor/BFPP and push a business bean onto the early initialization path?
8. Is there a real dependency edge/`@DependsOn`, or are you relying on unguaranteed class scanning order?
9. Does the bean have lifecycle state, socket resources, pools, executors, or AOP proxies that must be ready before use?
10. Are there tests confirming event order, number of instances, and cleanup?

### Recommended test cases

- After the registry processor, `containsBeanDefinition("task") == true` yet the constructor has not run.
- BFPP runs before `TrackedTask` constructor.
- `task` BPP before/after run around init callbacks.
- Retrieving the `task` singleton twice yields the same reference.
- After singleton pre-instantiation, `SmartInitializingSingleton` runs before `ContextRefreshedEvent`.
- Closing the context invokes singleton destruction callbacks per contract.
- When switching the bean to `@Lazy`, instance creation can be deferred until the first `getBean`.
- When switching to prototype, two independent `getBean` calls produce two instances.
- Calling `getBean` early inside a BFPP can skew expected behavior and should not be treated as a standard initialization pattern.

## 19. Connecting to application design

In a web application or service, understanding the pipeline directly impacts code quality:

**Configuration**: use `@Bean`, `@Configuration`, `@ComponentScan`, and classpath scanners to load metadata; avoid side effects in configuration class constructors.

**Metadata processors**: mechanisms such as placeholder resolution, custom scopes, or configuration registration should execute before the singleton instantiation phase. This gives the container accurate metadata for stable wiring.

**Instance processors**: annotation support, lifecycle callbacks, and AOP need to be attached to the container before beans are created; design processors to avoid broad dependencies on business services.

**Business singletons**: constructor injection makes the dependency graph explicit and verifies invariants early; `@PostConstruct` should only validate and prepare local state, avoiding launching background threads or long network queries while the container is still creating beans.

**Readiness**: if an application startup step is needed after all singletons are present, choose a hook at the right milestone such as `SmartInitializingSingleton`, `ContextRefreshedEvent`, or `SmartLifecycle`. Spring Core lifecycle milestones do not equate to load balancer liveness/readiness or external system state.

**Shutdown**: context refresh and context close are two different halves of the lifecycle. Singleton destruction, `@PreDestroy`, `DisposableBean`, and `destroyMethod` occur during container-managed teardown; prototypes do not automatically have container-managed destruction after being handed to the caller.

## 20. Standard reference documentation

- [Spring Framework Reference — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): `BeanFactoryPostProcessor` and `BeanPostProcessor` sections, metadata vs. instance differences, early initialization, and ordering.
- [Spring Framework Reference — Annotation-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/annotation-config.html): registering annotation processors and lifecycle handling.
- [Spring Framework Reference — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): component scanning, stereotypes, and registration.
- [Spring Framework 6.2 Javadoc — BeanDefinitionRegistryPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistryPostProcessor.html): registry phase contract.
- [Spring Framework 6.2 Javadoc — BeanFactoryPostProcessor](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/BeanFactoryPostProcessor.html): processing metadata before instance creation and ordering semantics.
- [Spring Framework 6.2 Javadoc — SmartInitializingSingleton](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/SmartInitializingSingleton.html): callback at the end of the singleton pre-instantiation loop.
- [Spring Framework 6.2 Javadoc — AbstractApplicationContext](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/support/AbstractApplicationContext.html): `refresh` and context lifecycle phases.
- [Spring Framework 6.2 Javadoc — DefaultListableBeanFactory](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/support/DefaultListableBeanFactory.html): singleton pre-instantiation and BeanFactory API.

**Key sequence to remember:** **bean definitions → registry/factory post-processors → register BeanPostProcessors → initialize eager singletons → SmartInitializingSingleton → ContextRefreshedEvent**. Each step has a distinct responsibility; understanding these boundaries correctly helps implement Spring Core Container safely and accurately diagnose startup errors.
