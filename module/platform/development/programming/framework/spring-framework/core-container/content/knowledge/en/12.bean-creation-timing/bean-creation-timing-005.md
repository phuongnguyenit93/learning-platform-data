# @DependsOn for Initialization Dependencies Not Expressed via DI in Spring Core Container

## 1. The Problem: Two Beans Do Not Inject Each Other Yet Still Need Initialization Order

In the Spring IoC Container, the best way to express that **one object needs another object** is normally dependency injection (DI): constructor argument, `@Autowired`, or XML `ref`. If `OrderService` needs `OrderRepository`, passing the repository into the constructor lets Spring know it must prepare the repository before creating the service.

However, there is another kind of dependency: bean B **does not accept bean A as a Java parameter**, yet B only works correctly if **A has already been initialized and completed its initialization callbacks**. Examples:

- A component registers a handler into shared infrastructure.
- One bean populates a global registry, while another bean only uses the static/global registry.
- An initializer must run before a consumer bean, yet the consumer does not need to hold the initializer object.
- One bean loads reference data into a shared location before another bean begins its work.

Spring provides **`@DependsOn`** in Java configuration and **`depends-on`** in XML to express this kind of **initialization ordering dependency**.

```java
@Bean
@DependsOn("registryInitializer")
JobDispatcher jobDispatcher() {
    return new JobDispatcher();
}
```

Meaning: Spring must **create and initialize the bean named `registryInitializer` before** creating `jobDispatcher`, even though the `jobDispatcher()` method takes no parameters.

**Important:** `@DependsOn` is not a form of injection; it does not pass the `registryInitializer` object into `JobDispatcher`. It expresses a **lifecycle ordering constraint** in the BeanFactory.

### Learning Objectives

After this lesson, you will:

1. Distinguish **dependencies expressed via DI** from **dependencies requiring only initialization order**.
2. Understand `@DependsOn("beanName")`, `@DependsOn({"beanA","beanB"})`, and XML `depends-on="..."`.
3. Explain accurately what Spring guarantees regarding **initialization** and **destruction** of singleton beans.
4. Distinguish ordering guaranteed by dependency relationships from source code order, classpath scan order, `@Order` annotations, or `@Bean` declaration order.
5. Use `@DependsOn` on `@Bean` methods and on component-scanned `@Component` classes; know the limitation of class-level annotations when registered via XML.
6. Check interactions with `@Lazy`, `lazy-init`, prototypes, and scoped beans.
7. Detect circular depends-on, missing bean names, bean aliases, and cases where side effects are no longer appropriate.
8. Run a Java 17+ / Spring Framework 6.2.19 example using Java configuration, XML, component scanning, and lazy beans, verifying both startup and shutdown order.
9. Know when **not to use @DependsOn** and choose constructor injection, lifecycle hooks, or application events instead.

**Scope:** This topic belongs to **Bean Creation Timing** in Spring Framework Core Container. The goal is synchronizing **creation/initialization order of bean definitions**, not simulating a task scheduler or distributed dependency orchestration mechanism.

## 2. DI Already Expresses Order in Normal Cases

A true dependency using constructor injection:

```java
public final class OrderService {
    private final OrderRepository repository;

    public OrderService(OrderRepository repository) {
        this.repository = repository;
    }
}
```

If Spring creates `OrderService` through a valid bean definition and resolves `OrderRepository`, it must create/prepare the repository before passing it to the constructor. This is a **direct object dependency**, which can be expressed by:

```java
@Bean
OrderService orderService(OrderRepository repository) {
    return new OrderService(repository);
}
```

or XML:

```xml
<bean id="orderRepository" class="com.example.OrderRepository"/>
<bean id="orderService" class="com.example.OrderService">
    <constructor-arg ref="orderRepository"/>
</bean>
```

These snippets require matching `OrderService` and `OrderRepository` Java classes.

### Do Not Add @DependsOn When the Constructor Already Expresses the Dependency

In this case, adding:

```java
@DependsOn("orderRepository")
@Bean
OrderService orderService(OrderRepository repository) {
    return new OrderService(repository);
}
```

is normally **redundant**: the `repository` parameter already tells Spring that the repository is required. `@DependsOn` does not improve type safety and may mislead readers into thinking a separate lifecycle side effect exists.

**Rule:** If bean B **actually needs to hold/operate on object A**, **inject A** instead of merely adding A's name to `@DependsOn`.

## 3. When Can DI Not Express the Dependency?

There are requirements that do not pass an object directly.

### 3.1. Global Registry of a Legacy Library

A `PluginRegistrar` bean calls a plugin registration API in its init callback; a `PluginLauncher` bean later uses a static registry without receiving `PluginRegistrar` in its constructor:

```text
PluginRegistrar.initialize()
    |
    +--> SharedPlugins.register("pdf", PdfPlugin)
    |
    v
PluginLauncher is allowed to begin operating
    |
    +--> SharedPlugins.lookup("pdf")
```

The legacy library does not expose an injectable registry abstraction, so you might need:

```java
@Bean("pluginRegistrar")
PluginRegistrar pluginRegistrar() {
    return new PluginRegistrar();
}

@Bean("pluginLauncher")
@DependsOn("pluginRegistrar")
PluginLauncher pluginLauncher() {
    return new PluginLauncher();
}
```

This is an illustrative structure, not runnable source; Java types and lifecycle code must be supplied. `@DependsOn` forces the registrar to **be initialized first**, giving its initialization callback the opportunity to register the plugin. It does not itself understand plugin registries and does not pass any plugin object to the launcher.

### 3.2. Native/Static Initialization Configuration

A bean performs an initial side effect such as loading a native library, registering a driver, setting up a global registry, or warming up a synchronous mechanism. Bean B depends on that side effect even without holding a reference to the initializer. Spring documentation mentions a similar situation when a **static initializer needs to be triggered**.

### 3.3. Legacy Architecture Transition

When code cannot yet be refactored to pure DI, `@DependsOn` is an explicit bridge to eliminate accidental reliance on component scan order or bean declaration order.

However, **do not use @DependsOn to perpetuate global mutable state** if it can be replaced with an injected dependency, a real interface/registry bean, or lifecycle infrastructure with a clear contract.

## 4. What Does @DependsOn Guarantee?

Spring's Javadoc states: beans listed in `@DependsOn` are created by the container **before** the annotated bean. This includes running initialization according to the Spring-managed lifecycle.

```text
bean "appWorker" has @DependsOn("setup")
                 |
                 v
BeanFactory checks "setup"
                 |
                 +--> create setup if not present yet
                 +--> resolve setup's dependencies
                 +--> run setup's synchronous init callbacks
                 |
                 v
BeanFactory creates "appWorker"
                 |
                 +--> resolve appWorker's dependencies
                 +--> run appWorker's init callbacks
                 |
                 v
Both are ready per the bean lifecycle
```

**Important limitation:** if `setup` starts an asynchronous task and `init()` returns **before the task finishes**, Spring only knows that `setup`'s synchronous initialization step finished. `@DependsOn` **does not by default wait for any Future, thread, remote service, or distributed operation** to reach a ready state.

### 4.1. Initialization Order ≠ Method Invocation Order

Spring can guarantee:

```text
setup.init before appWorker.init
```

but does not thereby guarantee:

```text
every appWorker.run() call waits for setup's background task to actually finish
```

If the workload needs an explicit barrier, design a readiness contract (e.g., `CompletableFuture`/latch/health state with timeout) or suitable lifecycle orchestration instead of merely using a bean-name annotation.

### 4.2. The Name Used in @DependsOn Is a Bean Name

```java
@DependsOn("registryInitializer")
```

`registryInitializer` is a **bean name** (or an alias resolvable in the container), not a field name, bare Java type, or package name. When using `@Bean("registryInitializer")`, that name is the declarative contract.

If you rename the bean and forget to update the annotation, the context can fail while creating the dependent bean.

## 5. @DependsOn Syntax on a @Bean Method

Single dependency:

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {

    @Bean("bootstrapState")
    BootstrapState bootstrapState() {
        return new BootstrapState();
    }

    @Bean("reportWorker")
    @DependsOn("bootstrapState")
    ReportWorker reportWorker() {
        return new ReportWorker();
    }
}
```

This illustrative snippet requires `Configuration`, `Bean`, `DependsOn` imports and real Java types. Method `reportWorker()` **does not accept `BootstrapState`**: the relationship is declared via metadata, not a DI parameter.

**Place `@DependsOn` on the bean method that must be created *after***, not on the prerequisite expecting reverse semantics.

### 5.1. Multiple Prerequisites

```java
@Bean("dataReporter")
@DependsOn({"driverRegistration", "schemaValidation"})
DataReporter dataReporter() {
    return new DataReporter();
}
```

Meaning: both named beans must be initialized before `dataReporter`. However, `@DependsOn({"A","B"})` **should not be treated as an API forcing A before B**. If A must precede B, explicitly declare **B depends on A**, and then C depends on B or express the corresponding graph.

### 5.2. An Array of Names, Not Expression Language

```java
@DependsOn({"cacheBootstrap", "metricsBootstrap"})
```

is a literal array of bean names. It does not automatically parse Spring Expression Language into other beans or discover every implementation of an interface. If bean names are dynamic/condition-dependent, consider a different design or programmatic BeanDefinition registration with explicit dependency metadata.

### 5.3. Constructor Injection and @DependsOn Can Coexist

If a consumer needs an actual repository bean **and** needs a bootstrap side effect:

```java
@Bean("orderProcessor")
@DependsOn("globalCodecRegistrar")
OrderProcessor orderProcessor(OrderRepository repository) {
    return new OrderProcessor(repository);
}
```

This is a structural snippet; DI handles the repository object, and `@DependsOn` handles the prerequisite side effect. The two relationships are distinct in nature and can be used together.

## 6. @DependsOn on @Component: Important Limitation

The `@DependsOn` Javadoc allows usage on **TYPE** and **METHOD**. However, class-level annotations have a caveat:

> Class-level @DependsOn only takes effect when component scanning is used to register that class.

Example:

```java
@Component("searchIndexer")
@DependsOn("indexRegistry")
public class SearchIndexer {
    public SearchIndexer() {
    }
}
```

If the scanner finds `SearchIndexer`, `@DependsOn("indexRegistry")` metadata can be applied to the component's bean definition.

**If that class is only declared via XML:**

```xml
<bean id="searchIndexer" class="com.example.SearchIndexer"/>
```

then the class-level `@DependsOn` annotation **is not applied via this XML BeanDefinition path**; configure instead:

```xml
<bean id="searchIndexer"
      class="com.example.SearchIndexer"
      depends-on="indexRegistry"/>
```

Spring's Javadoc states this point very clearly, so you cannot look solely at annotations on a Java class while ignoring the **bean registration path**.

### 6.1. A @Configuration Class Is Also a @Component Specialization

A `@Configuration` class also belongs to the component stereotype family. However, class-level `@DependsOn` should not be viewed as a way to force **all `@Bean` methods** inside that class to depend on the same prerequisite across every registration path.

If the goal is initialization order for a specific bean, the clearest approach is placing `@DependsOn` **directly on the corresponding `@Bean` method**. If the goal is context-wide bootstrap infrastructure, consider the appropriate extension point/lifecycle hook rather than hiding ordering in an annotation on the configuration container.

## 7. XML depends-on="..." Equivalent at the Bean Definition Level

In XML:

```xml
<bean id="initializationRegistry"
      class="com.example.InitializationRegistry"/>

<bean id="backgroundWorker"
      class="com.example.BackgroundWorker"
      depends-on="initializationRegistry"/>
```

The XML `depends-on` attribute describes an **initialization order constraint**. It does not itself create a reference to the registry inside Java `BackgroundWorker`.

### 7.1. Multiple Bean Names in XML

```xml
<bean id="reportWorker"
      class="com.example.ReportWorker"
      depends-on="cacheWarmup, schemaCheck"/>
```

Spring allows separating names with **commas, whitespace, or semicolons** in XML `depends-on`.

Semantic equivalent in Java:

```java
@DependsOn({"cacheWarmup", "schemaCheck"})
```

**Do not put class names into depends-on** if the class is registered under a different bean name. For example, if `@Bean("cacheWarmup")` returns `CacheWarmupService`, the constraint name is `cacheWarmup`.

### 7.2. XML ref Does Not Substitute for depends-on in Side-Effect Cases

```xml
<bean id="reportWorker" class="com.example.ReportWorker">
    <constructor-arg ref="cacheWarmup"/>
</bean>
```

uses `ref` to **pass an object dependency into the constructor**; the Java class must have a matching constructor. If the worker neither receives nor uses that object, creating a dummy constructor parameter merely to control order is an anti-pattern. Using `depends-on` is proper when only an initialization side effect is genuinely required.

### 7.3. Both Can Be Used Together

```xml
<bean id="reportWorker"
      class="com.example.ReportWorker"
      depends-on="bootstrapRegistrar">
    <constructor-arg ref="businessRepository"/>
</bean>
```

DI supplies `businessRepository`, while `depends-on` forces `bootstrapRegistrar` to initialize first. These are two separate kinds of dependencies.

## 8. Consequence on Context Close: Destroying Dependent Before Prerequisite

`@DependsOn("registry")` on bean `worker` establishes that **worker depends on registry**. When both are managed singletons with destruction callbacks, Spring can keep `registry` alive until `worker` has been destroyed:

```text
Initialization: registry -> worker
Destruction:    worker   -> registry
```

This is useful if `worker` needs to unregister a callback or flush through `registry` during `destroy()`. It does not automatically close unmanaged threads, await futures, complete external transactions, or impose a total order across unrelated beans.

Java example: `@Bean @DependsOn("registry") Worker worker()`; XML: `<bean id="worker" depends-on="registry" .../>`. For **prototypes**, the container does not automatically apply full destruction callbacks like singletons. The final lesson of this chapter dives into the dependency registry (`getDependentBeans`, `registerDependentBean`), DI relationships, and graceful shutdown; here it suffices to note the lifecycle consequence of `@DependsOn` metadata.

## 9. @DependsOn with @Lazy: Not a Way to Defer

Suppose:

```java
@Bean("slowSetup")
@Lazy
SlowSetup slowSetup() {
    return new SlowSetup();
}

@Bean("readyWorker")
@DependsOn("slowSetup")
ReadyWorker readyWorker() {
    return new ReadyWorker();
}
```

If `readyWorker` is a non-lazy singleton, Spring must create `slowSetup` **before** `readyWorker`, even though `slowSetup` is marked lazy. That means `depends-on` can **pull a lazy bean into startup**.

A table:

| Prerequisite bean | Dependent bean | Expected outcome |
| --- | --- | --- |
| Non-lazy singleton | Non-lazy singleton | prerequisite initialized before dependent |
| Lazy singleton | Non-lazy singleton with `@DependsOn` | lazy prerequisite created early to satisfy constraint |
| Lazy singleton | Lazy singleton dependent not yet looked up | both can remain uncreated |
| Lazy singleton | Lazy dependent looked up | prerequisite created before dependent |
| Prototype prerequisite | Singleton dependent | prerequisite may be created when dependent is created; destroy semantics differ from singleton |
| Scoped prerequisite | Bean in another scope | also depends on active scope and lookup method; do not treat as global ordering |

**Do not use @DependsOn to optimize startup time.** It adds prerequisites, usually making initialization order and cost stricter. To avoid fetching a dependency too early, use `@Lazy` at the injection point, `ObjectProvider<T>`, or adjust the lifecycle contract per situation — while preserving correctness.

## 10. Java 17+ Example: Java @Bean, XML, Component Scan, and Lazy Prerequisite

The following example verifies via **event order**, without relying on bean registration order or wall-clock timing. All beans in the demo are normal Spring-managed objects.

There are four **independent** contexts for comparison:

1. `JavaConfig`: `@DependsOn` on a `@Bean` method.
2. `xml-depends.xml`: XML `depends-on`.
3. `ScanConfig`: `@DependsOn` on a class discovered by component scanning.
4. `LazyConfig`: an `@Lazy` target still pulled into startup by an eager dependent.

In each context, a `Tracked` class records `construct`, `init`, and `destroy` via `InitializingBean` and `DisposableBean`. `worker` holds no reference to `setup`; the relationship exists solely in `depends-on` metadata.

### 10.1. Directory Tree

```text
depends-on-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── DependsOnDemo.java
        └── resources/
            └── xml-depends.xml
```

A single Java file contains nested static classes, Spring configs, and `main`. XML uses the **binary class name** with a dollar sign for the Java nested class: `demo.DependsOnDemo$Tracked`.

### 10.2. Gradle Configuration

**`settings.gradle`**

```groovy
rootProject.name = 'depends-on-demo'
```

**`build.gradle`**

```groovy
plugins {
    id 'java'
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
    mainClass = 'demo.DependsOnDemo'
}
```

Java 17+ and a Gradle version supporting Java toolchains are sufficient. No Spring Boot, database, Jakarta lifecycle annotations, or web server are needed. Spring Context pulls in Beans/Core and required dependencies.

### 10.3. xml-depends.xml

**`src/main/resources/xml-depends.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- Declare dependent first to show ordering does not rely on line order. -->
    <bean id="xmlWorker"
          class="demo.DependsOnDemo$Tracked"
          depends-on="xmlSetup">
        <constructor-arg value="xmlWorker"/>
    </bean>

    <bean id="xmlSetup"
          class="demo.DependsOnDemo$Tracked">
        <constructor-arg value="xmlSetup"/>
    </bean>

</beans>
```

Both are default singletons. `xmlWorker` is declared **first**, yet `depends-on` forces `xmlSetup` to initialize first.

### 10.4. Complete Java Source

**`src/main/java/demo/DependsOnDemo.java`**

```java
package demo;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Supplier;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ComponentScan;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.FilterType;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.support.ClassPathXmlApplicationContext;
import org.springframework.stereotype.Component;

public final class DependsOnDemo {

    private static final List<String> EVENTS = new ArrayList<>();

    // No field dependency to any other setup bean.
    public static class Tracked
            implements InitializingBean, DisposableBean {

        private final String name;

        public Tracked(String name) {
            this.name = name;
            EVENTS.add(name + ".construct");
        }

        @Override
        public void afterPropertiesSet() {
            EVENTS.add(name + ".init");
        }

        @Override
        public void destroy() {
            EVENTS.add(name + ".destroy");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class JavaConfig {

        // Deliberately declared before its prerequisite.
        @Bean("javaWorker")
        @DependsOn("javaSetup")
        Tracked javaWorker() {
            return new Tracked("javaWorker");
        }

        @Bean("javaSetup")
        Tracked javaSetup() {
            return new Tracked("javaSetup");
        }
    }

    // Class-level annotation is honored on a scanned component.
    @Component("scanWorker")
    @DependsOn("scanSetup")
    public static class ScanWorker extends Tracked {
        public ScanWorker() {
            super("scanWorker");
        }
    }

    @Configuration(proxyBeanMethods = false)
    @ComponentScan(
        basePackageClasses = DependsOnDemo.class,
        useDefaultFilters = false,
        includeFilters = @ComponentScan.Filter(
            type = FilterType.ASSIGNABLE_TYPE,
            classes = ScanWorker.class
        )
    )
    public static class ScanConfig {
        @Bean("scanSetup")
        Tracked scanSetup() {
            return new Tracked("scanSetup");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class LazyConfig {
        @Bean("lazySetup")
        @Lazy
        Tracked lazySetup() {
            return new Tracked("lazySetup");
        }

        @Bean("activeWorker")
        @DependsOn("lazySetup")
        Tracked activeWorker() {
            return new Tracked("activeWorker");
        }
    }

    private static void exercise(
            String label,
            Supplier<? extends ConfigurableApplicationContext> factory) {

        EVENTS.clear();
        int beforeClose;

        try (ConfigurableApplicationContext context = factory.get()) {
            // Construct + init callbacks run during refresh().
            System.out.println(label + ".start="
                    + String.join(" > ", EVENTS));

            beforeClose = EVENTS.size();

            // Do not actively getBean() prerequisites here.
            // Context close() will invoke destroy callbacks.
        }

        System.out.println(label + ".destroy="
                + String.join(" > ",
                    EVENTS.subList(beforeClose, EVENTS.size())));
    }

    public static void main(String[] args) {
        exercise("java",
                () -> new AnnotationConfigApplicationContext(
                        JavaConfig.class));

        exercise("xml",
                () -> new ClassPathXmlApplicationContext(
                        "xml-depends.xml"));

        exercise("scan",
                () -> new AnnotationConfigApplicationContext(
                        ScanConfig.class));

        exercise("lazy",
                () -> new AnnotationConfigApplicationContext(
                        LazyConfig.class));
    }
}
```

### 10.5. Run

In the `depends-on-demo` directory:

```bash
gradle run --quiet
```

If a Gradle Wrapper is already in the project, use `./gradlew run --quiet` (Linux/macOS) or `gradlew.bat run --quiet` (Windows). Running `javac DependsOnDemo.java` alone is insufficient without Spring libraries on the compile/runtime classpath; Gradle configures dependencies and copies XML onto the classpath.

### 10.6. Expected Stdout

```text
java.start=javaSetup.construct > javaSetup.init > javaWorker.construct > javaWorker.init
java.destroy=javaWorker.destroy > javaSetup.destroy
xml.start=xmlSetup.construct > xmlSetup.init > xmlWorker.construct > xmlWorker.init
xml.destroy=xmlWorker.destroy > xmlSetup.destroy
scan.start=scanSetup.construct > scanSetup.init > scanWorker.construct > scanWorker.init
scan.destroy=scanWorker.destroy > scanSetup.destroy
lazy.start=lazySetup.construct > lazySetup.init > activeWorker.construct > activeWorker.init
lazy.destroy=activeWorker.destroy > lazySetup.destroy
```

The program prints eight lines via `System.out.println`. Gradle/framework may print logs depending on the environment, not counted among these eight intentional lines.

### 10.7. Analysis of Java Config Results

- `javaWorker` is declared in `JavaConfig` **before** the `javaSetup` method.
- `@DependsOn("javaSetup")` instructs the BeanFactory to create/initialize the prerequisite before the worker.
- `Tracked` records constructor and `afterPropertiesSet()`; thus `javaSetup.init` is printed before `javaWorker.construct`.
- When the context closes, `javaWorker.destroy` comes before `javaSetup.destroy`.
- `javaWorker` holds no reference to `javaSetup`; the relationship lives entirely in bean definition metadata.

This illustrates the exact scenario of an **initialization dependency not expressed via DI**.

### 10.8. Analysis of XML Results

- `xmlWorker` appears before `xmlSetup` in the XML.
- The BeanFactory still must create `xmlSetup` first to satisfy `depends-on="xmlSetup"`.
- Because both implement `InitializingBean` and `DisposableBean`, the demo records init/destroy via Spring interfaces without needing Java `@PostConstruct` or `@PreDestroy`.
- Shutdown order is the reverse of the startup relationship.

### 10.9. Analysis of Component Scan Results

- `ScanConfig` enables `@ComponentScan` yet **disables default filters** so the demo only scans the `ScanWorker` class via an assignable-type include filter.
- `ScanWorker` is a public static nested class with `@Component("scanWorker")` and `@DependsOn("scanSetup")` at the **class level**.
- `scanSetup` is registered by a `@Bean` method of `ScanConfig`.
- When the scanner registers `ScanWorker`, the class-level constraint is recognized and applied; the lifecycle shows `setup` init running before `worker` constructor.
- This differs from declaring `<bean class="...ScanWorker"/>` directly in XML, as Javadoc notes class-level annotations are not applied to BeanDefinitions registered solely via XML.

### 10.10. Analysis of Lazy Prerequisite Results

- `lazySetup` carries `@Lazy`, which would normally skip pre-instantiation.
- `activeWorker` is a **non-lazy singleton** and has `@DependsOn("lazySetup")`.
- Spring must create `lazySetup` **during refresh**, so it executes `lazySetup.construct` and `lazySetup.init` before `activeWorker`.
- This example proves **`@Lazy` does not override dependency ordering**.
- When closing the context, `activeWorker` is destroyed before `lazySetup`.

### 10.11. Why Use Counters/Events Instead of Timestamps?

Timestamps and thread scheduling produce unstable results. `List<String> EVENTS` in the demo has no concurrent mutation because these configs use normal synchronous startup and `exercise` runs sequentially. Printing exact callback names and order verifies the `depends-on` contract.

If switching the demo to background initialization or async init, a thread-safe recorder and appropriate assertions would be needed, without assuming callbacks always run on the same thread.

## 11. @DependsOn vs @Order and @Priority

This is a group of annotations frequently confused:

| Annotation | What is it for? | Does it guarantee prerequisite inits first? |
| --- | --- | --- |
| `@DependsOn` | Creates an initialization relationship between bean definitions by names | Yes, within Spring BeanFactory lifecycle scope |
| XML `depends-on` | Equivalent ordering metadata for XML beans | Yes |
| `@Order` | Precedence of ordered components, lists of injected beans, or matching extension points | Not a general-purpose bean initialization dependency |
| `@Priority` | Priority selection/ordering in corresponding framework APIs | Not a general-purpose init dependency |
| `@Primary` | Prefer a candidate during type-based dependency injection | No |
| `@Qualifier` | Narrow/select a dependency candidate | Not directly |
| `@Lazy` | Defer eager singleton pre-instantiation | No; can be pulled into startup by depends-on |
| `@DependsOn` with `@Bean` | Force named target beans to init before the method's target bean | Yes |
| `@Import` / `DeferredImportSelector` | Select configuration classes participating in parsing | Not bean instance ordering |
| `@Conditional` | Decide whether a definition is registered | No |
| `@Bean(bootstrap=BACKGROUND)` | Support concurrent bean initialization in Spring 6.2 when a bootstrap executor exists | Ordering/awaiting has its own rules, not synonymous with @DependsOn |

**Specifically:** `@Order(1)` on service A and `@Order(2)` on service B is not a reliable way to ensure A is instantiated before B. If B must initialize after A, use **DI** or **`@DependsOn("A")`** according to the nature of the relationship.

## 12. When Does the BeanDefinition Reader Apply depends-on?

It is not a processor looking up runtime annotations on every business method call. The `depends-on` declaration becomes **BeanDefinition metadata**. The BeanFactory knows the names to resolve before creating the dependent bean.

Conceptual flow:

```text
Read @DependsOn on @Bean or scanned component
   / read depends-on from XML
                  |
                  v
   BeanDefinition.setDependsOn("setup", ...)
                  |
                  v
       BeanFactory.getBean("dependent")
                  |
                  +-- check registered prerequisite names
                  +-- detect dependency cycle in graph
                  +-- getBean("setup") first
                  +-- then instantiate dependent
                  |
                  v
         register dependency relationship
                  |
                  v
       destruction order for singletons
```

Do not use this diagram to infer every internal step/version behaves identically; it describes the **relationship contract** and why dependency order does not require injecting an object directly.

### 12.1. Reading BeanDefinition Metadata When Debugging

In an `AnnotationConfigApplicationContext`:

```java
var definition =
        context.getBeanFactory().getBeanDefinition("javaWorker");
String[] required = definition.getDependsOn();
```

In the demo, this array contains `"javaSetup"`. `getDependsOn()` can return `null` if the bean has no explicit depends-on. This is a way to verify metadata without printing constructor timestamps.

### 12.2. Bean Names and Aliases

Spring's BeanFactory has an alias resolution mechanism. Use the exact registered bean name or valid alias in `@DependsOn`. However, for maintainability, point to a stable **canonical bean name**, especially when multiple XML sources and Java configs are combined into one context.

If the prerequisite is registered under the name `"pluginRegistry"` yet `@DependsOn("PluginRegistry")` mistakenly uses a Java short class name, the context will not guess the type automatically. Check the actual names using `getBeanDefinitionNames()` or metadata.

## 13. Multiple Prerequisites and Ordering Among Them

Example:

```java
@Bean("worker")
@DependsOn({"cacheSetup", "metricsSetup"})
Worker worker() {
    return new Worker();
}
```

Required relationships:

```text
cacheSetup -----+
                +--> worker
metricsSetup ---+
```

There is no business requirement saying `cacheSetup` must happen before `metricsSetup` unless you additionally declare that relationship. If in reality you need:

```text
cacheSetup --> metricsSetup --> worker
```

then **metricsSetup** must depend on `cacheSetup`, and **worker** must depend on `metricsSetup`. Do not merely put two names in an array and rely on listing order as a mandatory policy between the two prerequisites.

### 13.1. Dependency Graph Design Principles

- Each relationship should exist only when there is a real invariant.
- Avoid making "every bean depend on globalSetup" when unrelated.
- The dependency graph should be a directed acyclic graph.
- Clearly identify who owns initialization side effects.
- Treat ordering metadata as a configuration API needing regression tests.

### 13.2. Why Not Just Order @Bean Methods?

Java source order is not a dependency graph management mechanism an application should rely on. Spring can parse metadata, resolve constructor dependencies, prioritize infrastructure, and behave differently across versions. Use `depends-on`/DI to express **mandatory conditions**, not source line order.

## 14. Circular depends-on Dependency Errors

Constraint cycle:

```java
@Bean("alpha")
@DependsOn("beta")
Alpha alpha() {
    return new Alpha();
}

@Bean("beta")
@DependsOn("alpha")
Beta beta() {
    return new Beta();
}
```

is an unsatisfiable graph: alpha requires beta to be created first, and beta requires alpha to be created first. Spring can report a circular depends-on/circular dependency error at startup or lookup. Do not try to fix it by reordering method declarations: **you must break the design cycle**.

A valid chain:

```text
driverRegistration --> registrySetup --> worker
```

Whereas a cycle:

```text
A --> B --> C --> A
```

cannot have a total init order.

### 14.1. Circular DI and Circular depends-on Differ

Circular constructor injection between A and B is also a problem, yet there constructors require object instances of each other. With circular depends-on, both classes might even have no-arg constructors and still fail solely because ordering metadata forms a cycle. The two kinds of cycles have different causes and remedies.

### 14.2. Debugging the Graph

When encountering an exception related to `Circular depends-on relationship`, inspect `@DependsOn`/XML `depends-on` across **all bean names in the cycle**, including alias resolution and registrations from multiple config sources. Do not look only at Java fields because depends-on may not be reflected in the type-level dependency graph.

## 15. Missing Bean and Registration Conditions

`@DependsOn("registry")` requires the bean name `registry` to exist when the dependent is created. If `registry` is not registered (not scanned, profile disabled, excluded by `@Conditional`, missing XML import), Spring does not automatically create a matching bean by searching for a class with a similar name.

### Example with @Profile

```java
@Configuration
class FeaturesConfig {
    @Bean("optionalRegistry")
    @Profile("reporting")
    Registry optionalRegistry() {
        return new Registry();
    }

    @Bean("reportWorker")
    @DependsOn("optionalRegistry")
    ReportWorker reportWorker() {
        return new ReportWorker();
    }
}
```

This is an illustrative snippet requiring imports and matching types. If the `reporting` profile is inactive, `optionalRegistry` is not registered while `reportWorker` remains active, so creating `reportWorker` will fail due to the missing required `depends-on` bean. If the worker only makes sense when the feature is enabled, apply appropriate profiles/conditions to **both**, or design an explicit optional dependency contract.

**Do not use @DependsOn to point to an *optional* bean that might not exist.** It is a hard prerequisite.

## 16. @DependsOn and Spring Singleton Destruction

Restating the rule:

```text
A depends on B
Init: B before A
Destroy (singletons): A before B
```

This is especially helpful when A wants to use infrastructure B inside `destroy()`:

```java
final class ClientSession implements DisposableBean {
    private final Registry registry;

    ClientSession(Registry registry) {
        this.registry = registry;
    }

    @Override
    public void destroy() {
        registry.unregister(this);
    }
}
```

In this snippet **DI already expresses the dependency** via the constructor, so Spring can track dependent registration when resolving dependencies and does not automatically need `@DependsOn` just to clarify order. If a legacy client uses static `Registry.global()` (with no injected reference), `@DependsOn("registry")` can add value to guide destruction order.

### 16.1. What Is Not Guaranteed

- Does not manage shutdown order of self-spawned threads if they sit outside the Spring lifecycle.
- Does not guarantee resource closing order across a distributed system of multiple JVMs/Pods.
- Does not transfer resource ownership between two different contexts.
- Does not establish a strict total destruction order across all unrelated beans.
- Does not replace `SmartLifecycle` phase semantics when multi-step startup/shutdown coordination is needed.
- Does not automatically guarantee an external database or broker is genuinely ready when bean init finishes.

## 17. Difference Between Init Callbacks and Async Readiness

Suppose:

```java
class AsyncWarmup {
    public void initialize() {
        new Thread(this::loadCache).start();
    }

    private void loadCache() {
        // Load expensive data on another thread.
    }
}
```

This is illustrative code; spawning unmanaged threads in an initializer is not recommended. If `initialize()` returns right away, Spring may consider the bean finished initializing per callback contract and proceed to create the dependent bean, even though `loadCache()` is still running.

### When Real Readiness Is Needed

Consider:

- A synchronous init operation with an explicit timeout, if startup must wait.
- `SmartLifecycle` and phase ordering when start/stop management is needed.
- `ApplicationListener<ContextRefreshedEvent>` or `@EventListener` if logic should only run after refresh.
- A readiness signal/health check measured separately from bean creation.
- Dependency injection via a service exposing `awaitReady()` or an explicit API, if callers must wait for readiness.
- External orchestration if depending on a database, Kafka broker, or other network service.

**Do not treat `@DependsOn` as a distributed readiness barrier.** It only manages lifecycle ordering known and executed by Spring.

## 18. Spring 6.2 Background Initialization and Dependencies

Spring Framework 6.2 supports the `@Bean(bootstrap=BACKGROUND)` option for certain singleton bean initializations when a suitable bootstrap executor infrastructure is present. This is a **concurrent startup** mechanism, distinct from `@Lazy` and `@DependsOn`.

If a background bean has a prerequisite, Spring must satisfy dependency constraints before a valid dependent instance is actually available. Spring docs state background initialization and `@DependsOn` work together so a required bean is initialized before background initialization of the dependent bean starts, per startup infrastructure.

However, due to thread concurrency, you **should not rely on log/timestamp ordering of two unrelated background beans** as a contract. For real dependencies, use DI or depends-on; for completion of asynchronous external work, use an explicit readiness contract. The Section 10 demo deliberately uses **synchronous startup** for deterministic output.

## 19. @DependsOn Is Not a Global @Order for All Beans

A common anti-pattern:

```java
@DependsOn("allInfrastructureReady")
@Component
public class EveryService {
}
```

If every service depends on a "mega initializer" without clear lifecycle ownership, it turns application startup into a rigid chain that is hard to test and prone to cycles as it grows.

A better design:

- Annotate only **the beans that truly need the side effect**.
- If multiple consumers use a resource/API, expose an injectable service instead of global shared mutable state.
- Use infrastructure-specific lifecycle hooks when an overall phase is needed.
- Break feature dependencies into small, understandable graphs.
- Use integration tests measuring exact order for a few critical beans.

### @DependsOn Does Not Guarantee a Bean Finished Business Workflows

If `OrderConsumer` is created after `PaymentGateway`, that does not mean `PaymentGateway` has finished processing all outstanding payments. Bean initialization only pertains to basic instance readiness per callback contract, not controlling all runtime workflows.

## 20. Checklist When Using @DependsOn

1. Is there a prerequisite side effect **truly needed** before the dependent bean is initialized?
2. If the dependency is a real object, can it be replaced with constructor injection?
3. Does the prerequisite bean already have a **stable name** in the context?
4. Is the target registered via `@Bean`, component scan, or XML? Choose the right annotation/attribute location.
5. Have you avoided mistakenly putting class-level `@DependsOn` on a bean registered only via XML?
6. Does the dependency relationship cause a lazy prerequisite to initialize early?
7. Are there multiple prerequisites? If they depend on each other, have you expressed separate edges?
8. Does the graph have any cycles?
9. If beans are profile-/condition-dependent, are prerequisite and dependent active under consistent conditions?
10. Does the prerequisite's initialization callback **synchronously** finish the required side effect?
11. Is singleton bean shutdown order needed/semantically right?
12. Are there threads/remote systems needing separate readiness outside the BeanFactory lifecycle?
13. Have you tested both startup **and** shutdown order using recorded events?
14. During code review, does the annotation document "why ordering is needed"?

## 21. How to Debug When @DependsOn Does Not Behave as Expected

### 21.1. Wrong Bean Name

If `@DependsOn("cacheInit")` is used while the actual bean is named `cacheInitializer`, Spring does not select the target by Java type. Inspect registered names, including aliases.

### 21.2. Class-Level Annotation Not Applied

If `@DependsOn` is placed on a class and the class is registered via XML `<bean>`, use XML `depends-on`. The Javadoc highlights this distinction.

### 21.3. Bean Not Registered Yet

If the target has not been processed by component scan, XML import, or Java config, `depends-on` cannot "automatically find the class on the classpath".

### 21.4. Dependency Cycle

Trace graph constraints by names. Break the cycle rather than rearranging source code order.

### 21.5. Lazy Bean Still Initializes Early

That is the correct semantics if a non-lazy dependent needs it. To achieve true laziness, remove unnecessary ordering constraints or design a different resolution approach.

### 21.6. Init Callback Returns Before Side Effect Is Ready

Synchronize readiness explicitly, switch lifecycle hooks, or redesign the API. `Depends-on` only guarantees that the synchronous callback returned.

### 21.7. Multiple Contexts Present

`Depends-on` only applies within the BeanFactory/context where names are resolved. Root and child contexts are not a single global mutable registry; cross-context object ownership and shutdown order require separate design.

### 21.8. Testing with Unstable Logs

Use a recorder in constructor/`afterPropertiesSet`/`destroy` as in the demo. Assertions can verify `setup.init < worker.construct` and `worker.destroy < setup.destroy` (for singletons).

### 21.9. Not Actually Using the Container to Create the Bean

If Java code calls `new Worker()` directly, `@DependsOn` metadata does not control the constructor. Bean lifecycle ordering requires Spring to manage the objects.

### 21.10. @Order Added Yet Issue Persists

`@Order` does not create `depends-on` metadata. Use the right annotation or constructor injection.

## 22. Review Questions with Answers

**Question 1.** When is `@DependsOn` more appropriate than constructor injection?

**Answer:** When the relationship is strictly a prerequisite side effect / initialization order without needing to pass an object dependency into the constructor.

**Question 2.** What does `@DependsOn("setup")` placed on bean A mean?

**Answer:** Bean `setup` must be created/initialized by Spring before A, per container lifecycle.

**Question 3.** Does `@DependsOn` inject the `setup` object into A?

**Answer:** No. For A to hold the `setup` object, you must use DI.

**Question 4.** Given A depends on B, what is the singleton destruction order?

**Answer:** A is destroyed before B; the init order is B before A.

**Question 5.** Do `@Order(1)` on A and `@Order(2)` on B guarantee A initializes before B?

**Answer:** No. `@Order` is not a lifecycle dependency declaration.

**Question 6.** How is XML `depends-on` written for two prerequisites?

**Answer:** `depends-on="registry,metrics"` or a list of names using a valid delimiter.

**Question 7.** Does class-level `@DependsOn` apply when the class is only registered via XML `<bean>`?

**Answer:** Per the Javadoc, no; use XML `depends-on`.

**Question 8.** If a prerequisite bean has `@Lazy` yet its dependent is an eager singleton, can the prerequisite initialize during refresh?

**Answer:** Yes. The ordering constraint forces Spring to create the prerequisite before the dependent.

**Question 9.** An initializer spawns a background thread and returns immediately; does `@DependsOn` wait for that thread to finish?

**Answer:** Not automatically. You need to synchronize readiness using another contract.

**Question 10.** Does `@DependsOn({"A","B"})` require A to be initialized before B?

**Answer:** Its primary purpose is that both A and B initialize before the dependent. If A must precede B, also declare that B depends on A.

**Question 11.** Why is a cycle A depends on B, B depends on A an error even when constructors have no parameters?

**Answer:** Because ordering metadata creates an impossible constraint.

**Question 12.** Can `@DependsOn` be placed on an `@Bean` method?

**Answer:** Yes, this is a placement supported by the Javadoc and suitable when controlling a specific bean's order.

**Question 13.** Why is `@DependsOn` not a way to check whether a network service is ready?

**Answer:** It manages Spring bean initialization, without verifying external service health or asynchronous task completion.

**Question 14.** If a BeanDefinition's `getDependsOn()` metadata is null, what does that indicate?

**Answer:** The definition has no explicit `depends-on` names in that metadata; it does not mean there are no constructor/setter DI dependencies.

**Question 15.** When is it useful for a singleton dependent to be destroyed before its prerequisite?

**Answer:** When the dependent needs the prerequisite infrastructure to unregister/flush/clean up during shutdown.

**Question 16.** If JavaConfig declares `worker` before `setup` in source, can you rely on line order to create them in the right order?

**Answer:** No. Placing `@DependsOn("setup")` or using DI is the way to express the constraint explicitly.

## 23. Hands-On Practice Exercises

### Exercise 1 — Remove @DependsOn

Delete `@DependsOn("javaSetup")` from `javaWorker`. Predict whether ordering is still guaranteed. Run the demo to see the result in your environment, remembering: **one run accidentally placing setup before worker does not mean a contract exists**.

### Exercise 2 — Point to a Non-Existent Bean Name

Change `@DependsOn("javaSetup")` to `@DependsOn("wrongSetup")`. Predict context creation failure because the prerequisite bean does not exist.

### Exercise 3 — Create a Cycle

Add `@DependsOn("javaWorker")` onto the `javaSetup` method. Predict a dependency cycle error. Do not attempt to fix it by changing declaration order.

### Exercise 4 — XML Multiple Prerequisites

Add a `xmlMetrics` bean and set `depends-on="xmlSetup,xmlMetrics"` on `xmlWorker`. Verify both prerequisites emit init events before `worker`. Do not use this output to infer business-level order between two unrelated prerequisites.

### Exercise 5 — Move Scan to XML

Try loading `ScanWorker` using XML `<bean id="scanWorker"...>`, without component scanning and **without** setting XML `depends-on`. Compare behavior with the scanner-based case; then add `depends-on="scanSetup"` in XML to restore the constraint.

### Exercise 6 — Lazy Prerequisite

Change `activeWorker` to `@Lazy` and do not call `getBean("activeWorker")` immediately. Observe whether `lazySetup` is still created during refresh. Then look up `activeWorker` and observe the order of the two constructors.

### Exercise 7 — Async Initializer

Have the prerequisite's `Tracked.afterPropertiesSet()` start an async task that returns immediately, then simulate the dependent needing data from that task. Redesign synchronization/readiness so there is no race. Avoid arbitrary `Thread.sleep()` as a production solution.

### Exercise 8 — Separate Side Effects from Business Beans

If you have a static `GlobalRegistry`, try refactoring it into a `Registry` interface and injecting it into the consumer via constructor. Explain why type-safe DI is easier to test and can eliminate unnecessary `@DependsOn`.

## 24. Official References

- [Spring Framework Reference — Using depends-on](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-dependson.html): rationale, XML syntax, multiple prerequisites, and shutdown order.
- [Spring Framework 6.2.19 Javadoc — DependsOn](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/DependsOn.html): annotation targets, constructor/initialization semantics, and caveat with class-level XML registration.
- [Spring Framework Reference — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html): DI dependencies suffice to express initialization order.
- [Spring Framework Reference — Java @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): factory methods and dependency method parameters.
- [Spring Framework Reference — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-lazy-init.html): lazy singletons can be pulled into startup by eager dependencies.
- [Spring Framework Reference — Composing Java-based Configurations](https://docs.spring.io/spring-framework/reference/core/beans/java/composing-configuration-classes.html): `@DependsOn` and background initialization in Spring 6.2.
- [Spring Framework Reference — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): `InitializingBean`, `DisposableBean`, lifecycle ordering.
- [Spring Framework 6.2.19 Javadoc — BeanDefinition](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html): `getDependsOn()` and bean metadata.

**Conclusion:** `@DependsOn` (Java) and `depends-on` (XML) are meant for **initialization dependencies not directly expressed by object injection**. Spring creates prerequisite beans before the dependent bean and, for singleton relationships, destroys the dependent before the prerequisite. This is **bean lifecycle ordering**, not DI, `@Order`, background-task completion, or distributed system readiness. Prefer constructor injection for real object dependencies; only use `depends-on` when there is a clear prerequisite side effect and verify it with integration tests.
