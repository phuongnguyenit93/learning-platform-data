# Dependency Relationships and Singleton Destruction Order in Spring Core Container

## 1. Why Does Bean Destruction Order Matter?

When building Spring applications, we usually focus on **how beans are created** and **how dependencies are injected**. However, if multiple singleton beans hold resources, the order in which they are **stopped and released** is equally important.

Suppose:

- `dataStore` represents a shared client/connection pool.
- `reportWriter` needs `dataStore` to write remaining results during `destroy()`.
- `jobCoordinator` needs `reportWriter` to finish or trigger a flush before closing.

The dependency relationship is:

```text
jobCoordinator --> reportWriter --> dataStore
       "uses"          "uses"
```

During creation, the dependency must be ready before the dependent:

```text
dataStore.init
reportWriter.init
jobCoordinator.init
```

During destruction, the desired order is **the reverse**:

```text
jobCoordinator.destroy
reportWriter.destroy
dataStore.destroy
```

If `dataStore` is closed before `reportWriter`, the writer's flush call during shutdown can fail. That is why Spring manages **dependency relationships** and uses them for both **initialization** and **destruction** of singleton beans.

**Core rule:**

> If bean A depends on bean B according to a relationship known to Spring, Spring strives to initialize B before A and, for appropriately managed singletons, destroy A before B.

This rule is specifically documented for **`@DependsOn` and XML `depends-on`**. The container also tracks many relationships arising when resolving dependency injection. However, not **every Java reference outside the container** automatically becomes a relationship known to Spring.

### Learning Objectives

After this lesson, you will be able to:

1. Distinguish **logical dependency**, **injection dependency**, and **registered dependency relationship**.
2. Understand why creation order normally runs from dependency to dependent, while destruction order runs in reverse.
3. Use `@DependsOn` and XML `depends-on` to express lifecycle constraints not represented by DI.
4. Understand relationships recorded by Spring via constructor/method injection and the `registerDependentBean` API.
5. Use `getDependentBeans(name)` and `getDependenciesForBean(name)` to diagnose the dependency graph.
6. Grasp the roles of `@PreDestroy`, `DisposableBean`, `destroyMethod`, and `ApplicationContext.close()`.
7. Distinguish singletons from prototypes, lazy singletons, custom scopes, inner beans, and objects outside the IoC Container.
8. Understand what Spring **does not** promise: global order among unrelated beans, closing self-spawned threads, readiness of remote services, or ordering across independent ApplicationContexts.
9. Run a Java 17+/Spring Framework 6.2.19 example verifying **dependency chains, DI, XML, lazy, and prototype**.
10. Design testable shutdown, avoiding data loss and errors from using resources after they have closed.

## 2. Three Kinds of Relationships to Distinguish

### 2.1. Real Object Relationship: Dependency Injection

```java
public final class ReportWriter {
    private final DataStore store;

    public ReportWriter(DataStore store) {
        this.store = store;
    }
}
```

This is an illustrative snippet requiring a `DataStore` class/interface. The constructor clearly expresses that a `ReportWriter` object needs a `DataStore` object. When Spring resolves this dependency, the container must prepare a suitable candidate before passing it to the constructor.

Java configuration example:

```java
@Bean
ReportWriter reportWriter(DataStore store) {
    return new ReportWriter(store);
}
```

Or XML:

```xml
<bean id="reportWriter" class="com.example.ReportWriter">
    <constructor-arg ref="dataStore"/>
</bean>
```

Spring can also record the relation when resolving the dependency in order to manage destruction ordering. This differs from a reference that Java code creates and holds outside the bean factory, because Spring cannot infer every object across the JVM.

### 2.2. Side-Effect Dependency: @DependsOn

```java
@Bean("reportWriter")
@DependsOn("registryInitializer")
ReportWriter reportWriter(DataStore store) {
    return new ReportWriter(store);
}
```

Here there are **two** relations:

- `reportWriter` directly receives `DataStore` via DI.
- `reportWriter` must wait for `registryInitializer` to perform initialization even without holding a reference to the initializer.

`@DependsOn` is the way to declare a **bean lifecycle ordering** constraint by name when there is no corresponding object injection. When both are singletons with destroy callbacks, this relation also affects destruction order.

### 2.3. Relationship Existing Only in Business Code

```java
public void run() {
    GlobalRegistry.getInstance().publish("report");
}
```

If `GlobalRegistry` is self-managed by a library, Spring may **not know** which bean needs to outlive which. Similarly, calling `new ExternalClient()` inside a business method does not turn the external client into a Spring-managed singleton.

**Do not confuse:** "one class uses another class" at runtime does not mean Spring stored a dependency edge to destroy them in the right order. If the lifetime of a dependency matters, inject a managed bean or declare a proper ordering relation.

## 3. From Bean Creation Graph to Bean Destruction Graph

Consider three singletons:

```text
service -> repository -> connectionPool
```

Each arrow `A -> B` means **A depends on B**. We can model this:

| Bean | Dependencies needed beforehand |
| --- | --- |
| `connectionPool` | None |
| `repository` | `connectionPool` |
| `service` | `repository` |

Given the relationships known to the container, a valid creation order is:

```text
connectionPool -> repository -> service
```

When the context closes, a valid destruction order is:

```text
service -> repository -> connectionPool
```

Spring is not required to establish a **single unique linear order** for completely independent beans. For example, adding an unrelated `metricsFormatter`, you should not write tests requiring the formatter to strictly destroy before or after the pool if no relation was declared.

### 3.1. Why Is the Order Reversed?

The dependent bean needs its dependency to remain alive during cleanup. A shutdown example:

```text
service.destroy():
    send remaining reports via repository
repository.destroy():
    flush unwritten data via connectionPool
connectionPool.destroy():
    close the pool
```

If `connectionPool` were closed first, the two callbacks above might no longer be able to use it. Reversing the dependency direction keeps resources alive long enough for dependent cleanup.

### 3.2. What Exactly Is "Destroy"?

In Spring, bean destruction can trigger mechanisms such as:

- `@PreDestroy` when the corresponding Jakarta annotations infrastructure is registered.
- The `org.springframework.beans.factory.DisposableBean` interface with its `destroy()` method.
- Custom/inferred destroy methods, such as `@Bean(destroyMethod="close")` or `destroy-method="close"`.
- Destruction-aware BeanPostProcessors and callbacks of special scopes.

Which mechanisms run, callback order **within the same bean**, and destroy method inference depend on metadata/version. **Ordering across beans** is a different concern from **callback order within one bean**.

## 4. Where Does Spring Execute Destruction Order?

`ConfigurableApplicationContext.close()` triggers the context closing process. In Spring Core Container, singleton destruction runs through the `BeanFactory`/singleton registry, where `DefaultSingletonBeanRegistry` manages cached singletons, disposable bean registrations, and dependency relations.

A conceptual model:

```text
ApplicationContext.close()
             |
             v
        Context shutdown
             |
             v
      Destroy registered singletons
             |
             +--> If X has dependent beans:
             |       destroy dependent beans first
             |
             +--> X's destroy callback
             |
             +--> handle containment/dependency links
             |
             v
       Singleton registry cleanup
```

**Important:** destruction order is not determined simply by reversing the order of XML lines, class names, or `@Bean` method declarations. The dependency graph recorded in the container plays the primary role.

### 4.1. What Data Does DefaultSingletonBeanRegistry Store?

The `DefaultSingletonBeanRegistry` API includes these methods:

```java
registerDependentBean(String beanName, String dependentBeanName);
getDependentBeans(String beanName);
getDependenciesForBean(String beanName);
```

How to read them:

- `registerDependentBean("store", "writer")`: **writer is a dependent of store**. When destroying `store`, `writer` must be destroyed first.
- `getDependentBeans("store")`: returns the names of beans depending on `store` known to the registry.
- `getDependenciesForBean("writer")`: returns the names of beans that `writer` depends on per registered dependency relations.

This is **Spring container metadata**. These are not methods of the application-domain `DataStore`, nor do they automatically inspect every Java field reference.

### 4.2. Reading in Both Directions

Given `writer depends on store`:

```text
getDependentBeans("store")          -> ["writer"] (direct relationship)
getDependenciesForBean("writer")    -> ["store"]  (direct relationship)
```

Exact lists also depend on other registrations in the context. Do not rely on **element order in the returned arrays** to construct a global shutdown schedule; the purpose of both APIs is inspecting relation names, not providing a complete schedule for every bean.

### 4.3. Do Not Confuse the Dependency API with the DI Candidate API

`getBeanNamesForType(ReportWriter.class)` finds beans **by type**. `getDependentBeans("store")` reads **registered relations**. A type can exist and be managed by Spring without depending on `store`; conversely, a `depends-on` relation does not require the Java class to contain a `store` field.

## 5. Declaring depends-on in Java Configuration

A common configuration:

```java
@Configuration(proxyBeanMethods = false)
public class ReportsConfig {

    @Bean("store")
    DataStore store() {
        return new DataStore();
    }

    @Bean("writer")
    @DependsOn("store")
    ReportWriter writer() {
        return new ReportWriter();
    }
}
```

This is a structural snippet requiring `Bean`, `Configuration`, `DependsOn` imports and two Java types with suitable constructors.

`@DependsOn("store")` placed on the **writer** bean means `writer` must not be initialized before `store`. If both are managed singletons with destroy callbacks, Spring also needs to destroy `writer` before `store`.

### 5.1. Do Not Reverse the Arrow

If the goal is **writer must close before store**, write:

```java
@Bean("writer")
@DependsOn("store")
ReportWriter writer() {
    return new ReportWriter();
}
```

**Not:**

```java
@Bean("store")
@DependsOn("writer")
DataStore store() {
    return new DataStore();
}
```

The second snippet says **store depends on writer** and inverts the semantics. Memory aid: the *dependent* is the bean carrying `@DependsOn`; the bean listed inside is the **prerequisite**.

### 5.2. Multiple Dependency Names

```java
@Bean("reportProcessor")
@DependsOn({"metricsRegistry", "writeAheadLog"})
ReportProcessor reportProcessor() {
    return new ReportProcessor();
}
```

Both prerequisites must initialize before `processor`. When destroying singletons, `processor` is destroyed before both prerequisites.

**Do not infer** that Spring must destroy `metricsRegistry` before or after `writeAheadLog` merely because the two names appear in a certain order in the array. If the two prerequisites have their own ordering relation, express that relation directly.

### 5.3. Class-Level Annotation and Component Scanning

`@DependsOn` can be placed on a class registered by component scanning:

```java
@Component("reportWorker")
@DependsOn("metricsRegistry")
public class ReportWorker {
}
```

**Limitation:** the `@DependsOn` Javadoc states that class-level annotations **only take effect when component scanning is used**. If the class is registered solely via XML `<bean>`, Spring honors XML `depends-on` rather than the class-level annotation. This is a trap when migrating Java/annotation config to legacy XML.

## 6. Declaring depends-on in XML

XML has `depends-on` on the `<bean>` element:

```xml
<bean id="reportWriter"
      class="com.example.ReportWriter"
      depends-on="dataStore"/>

<bean id="dataStore"
      class="com.example.DataStore"/>
```

Even though `writer` appears **before store in the XML file**, `store` is still the prerequisite bean. For two singletons with destroy callbacks:

```text
Initialization: dataStore -> reportWriter
Destruction:    reportWriter -> dataStore
```

When there are multiple prerequisite names:

```xml
<bean id="reportWriter"
      class="com.example.ReportWriter"
      depends-on="metricsRegistry, dataStore"/>
```

Spring supports lists of names separated by **commas, semicolons, or whitespace**.

### 6.1. ref and depends-on Are Not the Same

XML reference:

```xml
<bean id="reportWriter" class="com.example.ReportWriter">
    <constructor-arg ref="dataStore"/>
</bean>
```

will inject the **`dataStore` bean object** into the constructor.

XML depends-on:

```xml
<bean id="reportWriter" class="com.example.ReportWriter"
      depends-on="dataStore"/>
```

only adds an **ordering constraint**. It does not pass the `dataStore` object into `ReportWriter`. If `writer` actually needs to use `store`, constructor/setter injection expresses the dependency properly in Java types.

### 6.2. Which Bean Name Does XML Declare?

`depends-on="dataStore"` uses a **valid bean name or alias**, not an arbitrary class name. If XML declares `<bean id="primaryStore" class="com.example.DataStore"/>`, you cannot guess the name `dataStore` from the Java type and expect Spring to resolve it. Choose a stable canonical name and document the relationship.

## 7. If DI Already Exists, Do You Still Need @DependsOn?

Not always. Example:

```java
@Bean
DataStore store() {
    return new DataStore();
}

@Bean
ReportWriter writer(DataStore store) {
    return new ReportWriter(store);
}
```

Spring must resolve `DataStore` before calling `writer(DataStore store)`. On standard DI paths, the framework also registers the corresponding dependent relationship to support destruction management.

However, **do not claim** that merely because class A has a field of type B, the framework definitely records a relationship: only dependencies **actually resolved and registered** by the container can be observed in the registry. If you manually call `new B()` or invoke a static accessor outside Spring, no such guarantee exists.

### 7.1. When Does Adding @DependsOn Make Sense Despite DI?

For example, a service injects `DataStore` yet also needs `globalCodecRegistrar` to register a static codec not expressed via constructor:

```java
@Bean
@DependsOn("globalCodecRegistrar")
ReportWriter writer(DataStore store) {
    return new ReportWriter(store);
}
```

The constructor relation guarantees `DataStore`; `@DependsOn` guarantees the initializer. This makes sense if the initializer is genuinely required and has a managed lifecycle.

### 7.2. Avoid Redundant @DependsOn

Adding `@DependsOn("store")` to every bean that already constructor-injects `store` just "to be sure" creates noise and leads to string-name coupling. Type-safe DI already expresses the object dependency. Only declare separate ordering metadata when it carries **additional meaning**.

## 8. Lifecycle Callbacks Participating in Destruction

### 8.1. DisposableBean

```java
import org.springframework.beans.factory.DisposableBean;

public final class FileWriterService implements DisposableBean {
    @Override
    public void destroy() {
        // Flush then close the file writer.
    }
}
```

The container calls `destroy()` when the managed singleton is destroyed per its lifecycle. The interface depends on Spring APIs, yet is a clear choice for demos verifying order.

### 8.2. @PreDestroy

```java
import jakarta.annotation.PreDestroy;

public final class NetworkClient {
    @PreDestroy
    void shutdown() {
        // Signal closing of the resource.
    }
}
```

This is an illustrative snippet. With Spring 6+, `jakarta.annotation-api` is needed on the classpath if source uses `jakarta.annotation.PreDestroy` and the context has the appropriate post-processor. Java 17 does not bundle all Jakarta annotations automatically.

`@PreDestroy` is **one bean's callback**, not a way to declare that one bean must be destroyed before another bean. To constrain ordering **between beans**, use DI/`depends-on` appropriately.

### 8.3. @Bean(destroyMethod = "...")

```java
@Bean(destroyMethod = "close")
ClientConnection clientConnection() {
    return new ClientConnection();
}
```

Spring can call `close()` when the singleton shuts down if the method is valid and the bean is container-managed. This configuration avoids requiring the class to implement Spring's `DisposableBean`.

### 8.4. XML destroy-method

```xml
<bean id="fileClient"
      class="com.example.FileClient"
      destroy-method="close"/>
```

The container knows the cleanup method. If `reportWorker` still uses `fileClient` during destruction, ensure the relation via DI or:

```xml
<bean id="reportWorker"
      class="com.example.ReportWorker"
      depends-on="fileClient"/>
```

### 8.5. AutoCloseable Is Not the Entire Contract

Spring can infer destroy methods such as `close` or `shutdown` in many cases where bean factory methods have default destroy-method inference; however, metadata and how the bean is registered determine which callback is actually invoked. Do not look at a Java object implementing `AutoCloseable` and assume every container/scope will automatically close it. For critical resources, explicitly configure and test the destruction path.

### 8.6. Callbacks Running Within One Bean

One bean can simultaneously have `@PreDestroy`, implement `DisposableBean`, and have a custom destroy method. Spring has a well-defined callback order, yet this lesson focuses on **destruction order across beans**. Do not infer "bean A's destroy callback already ran" merely because bean B uses a different annotation.

## 9. Complete Example: Java 17+ Observing Both Initialization and Destruction

The following example uses plain **Spring Framework 6.2.19** (no Boot), Gradle, and two ApplicationContext APIs.

It creates **five independent cases**:

1. A chain of three singletons with `@DependsOn`.
2. Two singletons declared via XML `depends-on`.
3. Two singletons connected via **constructor/method-parameter DI**.
4. A `@Lazy` singleton still pulled into startup by a non-lazy dependent.
5. A prototype bean created, yet **not automatically receiving a destroy callback when the context closes**.

Beans record events via `InitializingBean`/`DisposableBean`. The program prints **the actual callback order of the configured relationships**, without guessing from timestamps or XML line ordering.

### 9.1. Directory Tree

```text
singleton-shutdown-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── ShutdownDemo.java
        └── resources/
            └── beans.xml
```

A single Java file with nested `public static` classes and one XML resource. The nested class name in XML uses the **Java binary name** `demo.ShutdownDemo$Tracked`.

### 9.2. settings.gradle

```groovy
rootProject.name = 'singleton-shutdown-demo'
```

### 9.3. build.gradle

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
    mainClass = 'demo.ShutdownDemo'
}
```

The project only needs Spring Context with its transitive dependencies, Java 17+, and a Gradle version supporting Java toolchains. No database, network, or extra Jakarta libraries are needed since the demo uses Spring lifecycle interfaces.

### 9.4. beans.xml

**`src/main/resources/beans.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <!-- Worker appears first in XML yet depends on store. -->
    <bean id="xmlWorker"
          class="demo.ShutdownDemo$Tracked"
          depends-on="xmlStore">
        <constructor-arg value="xmlWorker"/>
    </bean>

    <bean id="xmlStore"
          class="demo.ShutdownDemo$Tracked">
        <constructor-arg value="xmlStore"/>
    </bean>

</beans>
```

Both beans are default singletons. `depends-on="xmlStore"` forces the XML store to initialize before `worker`, and `worker` to be destroyed before `store`.

### 9.5. ShutdownDemo.java

**`src/main/java/demo/ShutdownDemo.java`**

```java
package demo;

import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import java.util.function.Supplier;

import org.springframework.beans.factory.DisposableBean;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.ConfigurableApplicationContext;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.DependsOn;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.annotation.Scope;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class ShutdownDemo {

    private static final List<String> EVENTS = new ArrayList<>();

    public static class Tracked
            implements InitializingBean, DisposableBean {

        private final String name;

        public Tracked(String name) {
            this.name = name;
            EVENTS.add(name + ".new");
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

    public static class Client
            implements InitializingBean, DisposableBean {

        private final Tracked store;

        public Client(Tracked store) {
            this.store = store;
            EVENTS.add("diClient.new");
        }

        @Override
        public void afterPropertiesSet() {
            if (store == null) {
                throw new IllegalStateException("missing store");
            }
            EVENTS.add("diClient.init");
        }

        @Override
        public void destroy() {
            EVENTS.add("diClient.destroy");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ChainConfig {

        @Bean("service")
        @DependsOn("repository")
        Tracked service() {
            return new Tracked("service");
        }

        @Bean("repository")
        @DependsOn("cache")
        Tracked repository() {
            return new Tracked("repository");
        }

        @Bean("cache")
        Tracked cache() {
            return new Tracked("cache");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class DiConfig {

        @Bean("diStore")
        Tracked diStore() {
            return new Tracked("diStore");
        }

        @Bean("diClient")
        Client diClient(Tracked diStore) {
            return new Client(diStore);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class LazyConfig {

        @Bean("lazyStore")
        @Lazy
        Tracked lazyStore() {
            return new Tracked("lazyStore");
        }

        @Bean("lazyWorker")
        @DependsOn("lazyStore")
        Tracked lazyWorker() {
            return new Tracked("lazyWorker");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class PrototypeConfig {

        @Bean("prototype")
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        Tracked prototype() {
            return new Tracked("prototype");
        }
    }

    private static void run(
            String label,
            Supplier<? extends ConfigurableApplicationContext> supplier) {

        EVENTS.clear();
        int cutoff;

        try (ConfigurableApplicationContext context = supplier.get()) {
            System.out.println(label + ".init="
                    + String.join(",", EVENTS));

            if ("chain".equals(label)) {
                var factory = context.getBeanFactory();

                boolean cacheHasRepository = Arrays.asList(
                    factory.getDependentBeans("cache")
                ).contains("repository");

                boolean serviceNeedsRepository = Arrays.asList(
                    factory.getDependenciesForBean("service")
                ).contains("repository");

                System.out.println("chain.relations="
                    + cacheHasRepository + ","
                    + serviceNeedsRepository);
            }

            if ("di".equals(label)) {
                var factory = context.getBeanFactory();
                boolean clientDependsOnStore = Arrays.asList(
                    factory.getDependentBeans("diStore")
                ).contains("diClient");

                System.out.println("di.relation="
                    + clientDependsOnStore);
            }

            cutoff = EVENTS.size();
        }

        System.out.println(label + ".destroy="
            + String.join(",",
                EVENTS.subList(cutoff, EVENTS.size())));
    }

    public static void main(String[] args) {

        run("chain", () -> new AnnotationConfigApplicationContext(
            ChainConfig.class));

        run("xml", () -> new ClassPathXmlApplicationContext(
            "beans.xml"));

        run("di", () -> new AnnotationConfigApplicationContext(
            DiConfig.class));

        run("lazy", () -> new AnnotationConfigApplicationContext(
            LazyConfig.class));

        EVENTS.clear();

        try (AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext(
                    PrototypeConfig.class)) {

            context.getBean("prototype");
            System.out.println("prototype.init="
                + String.join(",", EVENTS));
        }

        System.out.println("prototype.destroy-after-close="
            + EVENTS.contains("prototype.destroy"));
    }
}
```

### 9.6. Run

From the `singleton-shutdown-demo` directory:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper:

```bash
./gradlew run --quiet
```

On Windows use:

```bat
gradlew.bat run --quiet
```

Running `javac ShutdownDemo.java` standalone will lack Spring classes unless dependencies are placed on the classpath. Gradle automatically compiles, resolves libraries, and copies `src/main/resources/beans.xml` onto the runtime classpath.

### 9.7. Expected Stdout from println Calls

```text
chain.init=cache.new,cache.init,repository.new,repository.init,service.new,service.init
chain.relations=true,true
chain.destroy=service.destroy,repository.destroy,cache.destroy
xml.init=xmlStore.new,xmlStore.init,xmlWorker.new,xmlWorker.init
xml.destroy=xmlWorker.destroy,xmlStore.destroy
di.init=diStore.new,diStore.init,diClient.new,diClient.init
di.relation=true
di.destroy=diClient.destroy,diStore.destroy
lazy.init=lazyStore.new,lazyStore.init,lazyWorker.new,lazyWorker.init
lazy.destroy=lazyWorker.destroy,lazyStore.destroy
prototype.init=prototype.new,prototype.init
prototype.destroy-after-close=false
```

These are the lines actively printed by the program via `System.out.println`; logs from Gradle/framework, if any, are not part of these lines. The recorder only tracks `Tracked`/`Client` classes in the demo and does not claim to capture all Spring infrastructure events.

### 9.8. Explaining the @DependsOn Chain Case

Relationships:

```text
service depends on repository
repository depends on cache
```

cause callbacks to run in sequence:

```text
cache.new -> cache.init
repository.new -> repository.init
service.new -> service.init
```

Even though `@Bean("service")` is **written before** `repository` and `cache` in source, the bean graph dictates prerequisite ordering.

When closing the context:

```text
service.destroy -> repository.destroy -> cache.destroy
```

This is **reverse dependency order**, not accidentally reversing source code order.

`chain.relations=true,true` confirms the registry knows `repository` depends on `cache` and `service` depends on `repository`. Both APIs only inspect metadata relations; they do not construct a global shutdown list.

### 9.9. Explaining the XML Case

`xmlWorker` is written before `xmlStore`, yet has `depends-on="xmlStore"`. Spring initializes `store` before `worker`. On close:

```text
xmlWorker.destroy
xmlStore.destroy
```

This example shows that **XML line order does not substitute for dependency declarations**.

### 9.10. Explaining the DI Case

`DiConfig.diClient(Tracked diStore)` requires a `Tracked` bean. In the `DiConfig` context there is only one bean of type `Tracked`, which is `diStore`; Spring resolves the parameter and records the dependency relationship.

Thus `di.relation=true` from `getDependentBeans("diStore")` proves the BeanFactory recorded `diClient` as a dependent of `diStore`. On close, `diClient.destroy` runs before `diStore.destroy`.

This relationship arises from **DI resolution**, without needing a redundant `@DependsOn("diStore")`. Do not extend this conclusion to every way of obtaining objects outside the container.

### 9.11. Explaining the Lazy Case

`lazyStore` carries `@Lazy`, yet `lazyWorker` is an eager singleton with `@DependsOn("lazyStore")`. When the BeanFactory creates `lazyWorker` during refresh, it is forced to create `lazyStore` first; thus `lazy.init` shows both beans already initialized before `main` prints.

On close, dependent `lazyWorker` is destroyed before prerequisite `lazyStore`. **`@Lazy` does not disable destruction relations**.

### 9.12. Explaining the Prototype Case

`PrototypeConfig` declares `Tracked` with prototype scope. `context.getBean("prototype")` creates the instance and invokes its init callback; however, Spring **does not automatically register destroy callbacks for prototype instances the way it does for the managed singleton cache**.

Therefore, after `context.close()`, `prototype.destroy-after-close=false`. If a prototype holds resources needing cleanup, the code owning the object or an appropriate custom mechanism must release them; do not expect singleton destruction ordering.

### 9.13. Why Does the Example Use One Shared Event List?

The five contexts run **sequentially**, each case calling `EVENTS.clear()` before creating its context, so events remain isolated. Beans in the example use synchronous constructors/init/destruction without extra threads; no background bootstrap or custom threads are configured.

In a real application, concurrent startup/background init may exist; in that case a test recorder needs thread-safe collections/proper synchronization and must not assert ordering across unrelated beans.

## 10. Interaction with @Lazy and lazy-init

A lazy singleton that has never been created **has no instance to destroy**. If the context only registered the bean definition:

```java
@Bean
@Lazy
OptionalClient optionalClient() {
    return new OptionalClient();
}
```

without anyone looking up or mandatorily injecting that bean, the target's cleanup callback may never run because no target instance ever existed.

However:

```java
@Bean
@DependsOn("optionalClient")
CriticalWorker criticalWorker() {
    return new CriticalWorker();
}
```

when `criticalWorker` is an eager singleton, the dependency relation causes `optionalClient` to be created early despite being marked lazy. When these singletons are destroyed, `criticalWorker` is destroyed before `optionalClient`.

**Do not design cleanup assuming all `@Lazy` beans were definitely instantiated.** If a bean needs to run init/destroy unconditionally during the lifecycle, it usually should not be lazy, or it needs an explicit initialization/warm-up mechanism.

## 11. Do Singleton and Prototype Follow the Same Destruction Rules?

No. `singleton` and `prototype` have different lifecycle management.

| Case | Instance creation | Automatically destroyed on `ApplicationContext.close()`? |
| --- | --- | --- |
| Created eager singleton | During refresh/when requested | Yes, if an appropriate destruction callback is registered |
| Uncreated lazy singleton | No instance yet | No target to destroy |
| Created lazy singleton | When requested | Yes, if an appropriate callback exists |
| Looked-up prototype | Each request creates a new instance | Container by default **does not automatically call configured destruction callbacks** for prototypes |
| Web request/session scope | Per active scope | Per the scope implementation's semantics and callback management |
| Manually `new`-ed object | Created by Java code | Not managed by Spring |
| Inner bean | When creating the enclosing bean per corresponding semantics | Lifecycle/containment has its own rules, not identical to top-level singletons |

### 11.1. Prototypes Need Explicit Cleanup

If a prototype implements `AutoCloseable`, the caller retrieving it via `getBean()` may hold responsibility for calling `close()`. Or the application uses a custom scope/post-processor to register destruction per contract. `ApplicationContext.close()` is not a garbage collector that automatically closes every prototype instance ever created.

### 11.2. Singleton Injecting Prototype

A singleton consumer injected with a prototype dependency **once when the consumer is constructed** normally keeps that same prototype instance. The BeanFactory does not swap the prototype on each business call; if a new object is needed per call, use `ObjectProvider<T>` or an appropriate lookup method. Destroying the singleton also does not automatically clean up resources of every prototype as if they were all top-level singleton resources.

### 11.3. Inner Beans Are Not Simply Prototypes

A `<bean>` nested inside XML `<constructor-arg>`/`<property>` is an inner bean, tied to the enclosing bean. Spring also has **containment relationships** in the singleton registry; do not confuse them with top-level prototypes carrying public names. When an inner bean holds resources needing destruction, inspect the exact metadata/lifecycle and test actual ownership.

## 12. Shutdown Callbacks and Order Within a Single Bean

How the BeanFactory picks **which bean is destroyed first** differs from how Spring invokes **callbacks inside that bean**.

For example, a bean having:

```java
@PreDestroy
void preDestroy() {
}

@Override
public void destroy() {
}

public void close() {
}
```

This snippet merely illustrates the callback types: it requires importing `jakarta.annotation.PreDestroy`, implementing `DisposableBean`, and custom `close` metadata for full semantics.

A context can invoke lifecycle callbacks according to Spring's processing rules; do not write application logic relying on a callback "happening to be present" when the context lacks the matching processor/metadata.

### 12.1. Do Not Call Destroy Methods Manually When Managed by the Container

If you fetch a singleton from Spring and manually invoke `destroy()` while the application is still running, Spring may still consider the bean alive in the container, and later invoke its destroy callback at close. This can cause a **double-close** or leave other consumers using a closed resource.

If the application needs to stop/start a service multiple times explicitly, design a lifecycle interface/service with an appropriate contract; do not treat `DisposableBean.destroy()` as a business method to call arbitrarily at runtime.

### 12.2. Idempotent Cleanup

Even though Spring coordinates destruction, critical resource cleanup code should still be designed to be **idempotent** where possible: calling close twice should not lose/overwrite data or throw unrecoverable errors. For non-idempotent libraries, use a wrapper managing stopped state.

## 13. registerDependentBean: API for Advanced Infrastructure

Beyond `@DependsOn` and XML metadata, `ConfigurableBeanFactory`/`DefaultSingletonBeanRegistry` provides an API to register relationships dynamically:

```java
factory.registerDependentBean("store", "writer");
```

Meaning **writer depends on store**, so `writer` must be destroyed before `store`.

This is an API intended for infrastructure/container integration code, not a default recommendation for every service. Calling it arbitrarily can cause hard-to-diagnose side effects; declare relations early, before destruction begins, and consistent with the actual graph.

### 13.1. registerDependentBean Does Not Inject Objects

Registering a relation does not execute:

```java
writer.store = store;
```

or call a setter automatically. It is metadata for the dependency graph and cleanup ordering. If the object actually needs to be passed into the consumer, you must still use DI or explicit lookup.

### 13.2. Relation Direction Must Be Exact

```java
factory.registerDependentBean("store", "writer");
```

is right for **writer → store**.

Reversing it:

```java
factory.registerDependentBean("writer", "store");
```

describes **store → writer**, inverting the expected shutdown order. In code reviews, write clear comments stating "dependent = X, prerequisite = Y".

### 13.3. Cyclic Relationships

Do not create a cycle such as:

```text
A depends on B
B depends on A
```

The framework has mechanisms to detect many circular dependency/depends-on relationships and can fail when creating beans. When using low-level registry APIs, do not rely on the framework guessing how to fix the graph. **A lifecycle cannot have a valid before/after order for a cycle.**

### 13.4. Factory.getDependenciesForBean Is a Diagnostic Tool

```java
String[] deps = factory.getDependenciesForBean("writer");
```

If the array contains `store`, the container knows this relation. It does not mean `writer` has a Java field named `store`, nor does it describe the entire call graph of the program.

## 14. @Order Does Not Control Singleton Destruction Order

`@Order`, `Ordered`, `@Priority`, or ordered bean lists serve **specific extension points**; they are not general-purpose shutdown ordering metadata.

Example:

```java
@Order(1)
@Component
class FirstHandler {
}

@Order(2)
@Component
class SecondHandler {
}
```

You cannot infer Spring will destroy `SecondHandler` before `FirstHandler` merely because of `@Order` values. If two handlers have no dependency relation, do not build cleanup logic around accidental log order observed in one version.

To coordinate lifecycles when they have a real dependency, use **DI** or **`@DependsOn`**. For a group of components needing startup/shutdown phase orchestration, use `SmartLifecycle` instead of forcing a `@Order` sequence.

## 15. @DependsOn Compared to SmartLifecycle

`@DependsOn` and `SmartLifecycle` solve two different classes of problems:

| Mechanism | Responsibility |
| --- | --- |
| `@DependsOn` | Prerequisite bean **initialized before** dependent; destroy dependent before prerequisite for singletons |
| XML `depends-on` | Same meaning in XML bean definitions |
| Constructor injection | Supplies object dependency and ensures proper resolution |
| `SmartLifecycle` | Manages **start/stop phases** of components with start/stop lifecycles |
| `@Order` | Ordering/precedence for appropriate extension points, not the bean shutdown graph |
| `ApplicationContext.close()` | Triggers context shutdown and bean destruction |
| `@PreDestroy`/`DisposableBean` | Cleanup callback of **one bean instance** |
| `ObjectProvider<T>` | Dynamic dependency lookup, can defer resolution |
| Kubernetes preStop/SIGTERM | Coordination outside the JVM, does not directly alter the bean dependency graph |

### 15.1. When You Need to Stop First Without Destroying Immediately

A web server, message listener, and queue consumer often need to **stop accepting new work**, **drain in-flight work**, and only then **close databases/pools**. `SmartLifecycle` provides phased start/stop and callbacks better suited for **coordinated stop**.

`@DependsOn` helps manage bean construction/destruction order, yet does not replace logic for **draining**, **timeouts**, or stopping worker threads.

### 15.2. Shutdown of Complex Applications Has Multiple Stages

```text
1. Stop accepting new traffic/messages
2. Wait for in-flight work to finish within timeout
3. Flush writers/buffers
4. Close dependent clients/pools
5. Release remaining infrastructure
```

In a Spring application, you may need to combine:
- lifecycle stop phases;
- registered `depends-on` relationships;
- bean destroy callbacks;
- timeouts/retries/error handling for external resources.

Do not assume simply declaring `depends-on` names fulfills every graceful shutdown requirement of a distributed system.

## 16. Does Destruction Order Apply Across Two ApplicationContexts?

Not like a **global singleton registry**.

Example:

```java
var parent = new AnnotationConfigApplicationContext(ParentConfig.class);
var child = new AnnotationConfigApplicationContext();
child.setParent(parent);
child.register(ChildConfig.class);
child.refresh();
```

This is an illustrative snippet requiring real `ParentConfig` and `ChildConfig`. Root/child contexts have separate lifecycles and BeanFactories. A child bean can look up a parent bean via the hierarchy, yet that does not establish a JVM-wide shutdown order if someone closes `parent` before `child`.

If a child consumer still needs a parent resource during destruction, the application should close **child before parent** and maintain clear lifecycle ownership. For completely independent contexts, a bean-name relation in context A creates no dependency relation in context B's registry.

**Do not attach @DependsOn to coordinate shutdown across two microservices or multiple JVMs.** That is a matter of orchestration/distributed protocols.

## 17. Depending on a @Lazy Singleton

A `@Lazy` bean has a bean definition yet has not been created. If it is never requested, there will be no target instance on which to invoke a destroy callback.

```java
@Bean("optionalIndex")
@Lazy
IndexClient optionalIndex() {
    return new IndexClient();
}
```

If no consumer or `getBean` call requests `optionalIndex`, the context can close without ever constructing `IndexClient`.

Conversely:

```java
@Bean("activeSearch")
@DependsOn("optionalIndex")
SearchService activeSearch() {
    return new SearchService();
}
```

If `activeSearch` is an eager singleton, the BeanFactory will create `optionalIndex` before `activeSearch` to satisfy `depends-on`. When closing the context, `activeSearch` must be destroyed before `optionalIndex`.

### 17.1. Lazy Does Not Mean Arbitrary Destruction Order

Lazy only affects **instantiation timing**. Once the bean has been created and the relation is registered, destruction order is still governed by the container graph. Do not use `@Lazy` as a tool to "keep resources alive longer during shutdown".

### 17.2. @Lazy at an Injection Point

`@Lazy` placed at an injection point can create a lazy-resolution proxy instead of resolving the target immediately. If the target is resolved late, when the **dependency relationship is registered** and destruction semantics may differ from direct eager injection; inspect proxy/scope types and the relations recorded by the container. When resources require guaranteed cleanup ordering, do not rely on a proxy happening to touch the target earlier or later.

## 18. FactoryBean, Aliases, and Bean Names at Shutdown

### 18.1. An Alias Is a Reference Name, Not a Separate Bean Instance

```xml
<bean id="primaryStore" class="com.example.Store"/>
<alias name="primaryStore" alias="reportStore"/>
```

`primaryStore` and `reportStore` normally resolve to **one bean definition**. Singleton identity and destroy callbacks belong to the target bean; there is no independent destroy callback merely from adding an alias.

### 18.2. FactoryBean Has Both Factory and Product

A `FactoryBean<T>` produces a product bean, and `&factoryName` is normally used to look up the factory instance itself. This is not an ordinary alias. If product and factory hold distinct resources, inspect bean definitions, scopes, and lifecycle callbacks rather than looking solely at names passed to `getBean()`.

### 18.3. Synthetic/Infrastructure Beans

Some bean definitions registered automatically by the framework have early/special lifecycles. `@DependsOn` on a business service should not be treated as a mechanism to alter the entire processor registration pipeline. To manage framework extensions, use published extension points and test startup/shutdown.

## 19. Diagnostic Practice with BeanFactory APIs

From the `AnnotationConfigApplicationContext` in the example:

```java
var factory = context.getBeanFactory();

System.out.println(
    Arrays.toString(factory.getDependentBeans("cache")));

System.out.println(
    Arrays.toString(factory.getDependenciesForBean("repository")));
```

In `ChainConfig`, what matters is:

- `getDependentBeans("cache")` contains `repository`.
- `getDependenciesForBean("repository")` contains `cache`.

Do not hard-code an exact string representation of the array if the context has extra dependent registrations or a different element order. Use:

```java
boolean relationExists = Arrays.asList(
    factory.getDependentBeans("cache")
).contains("repository");
```

### 19.1. Inspecting BeanDefinition Metadata

```java
var definition =
    factory.getBeanDefinition("service");

String[] explicitNames = definition.getDependsOn();
```

With `ChainConfig`, `explicitNames` includes `repository`. However, `getDependsOn()` is **explicit metadata** from the bean definition; being null/empty does not mean the bean has no injection dependencies at all. To see registered runtime relationships, use `getDependenciesForBean`/`getDependentBeans`.

### 19.2. Checking Whether a Singleton Was Created

```java
boolean created = factory.containsSingleton("cache");
```

This can be used when debugging `@Lazy`: the bean definition may exist while the instance has not yet been created. Do not call `getBean("cache")` merely to "verify it is not created yet", because that call itself can **trigger bean creation**.

### 19.3. Do Not Forget to Close the Context in Tests

If you simply construct an `AnnotationConfigApplicationContext` and drop the reference without closing the context, do not expect Spring to run destroy callbacks automatically right away. Use `try-with-resources` or `context.close()` in tests to trigger the lifecycle as in the example.

## 20. Common Mistakes and Misconceptions

### Mistake 1 — Reading the Wrong Direction of depends-on

`@DependsOn("store")` on bean `writer` means **writer depends on store**, not store depends on writer. Init: store before writer. Destroy: writer before store.

### Mistake 2 — Using @Order to Force Destruction Order

`@Order` does not create a bean dependency relationship. It is intended for ordering at supported extension points.

### Mistake 3 — Relying on @Bean/XML Declaration Order

Source order is not a lifecycle contract. If ordering genuinely matters, declare DI or `depends-on`.

### Mistake 4 — Looking Only at Java Fields and Guessing the Container Knows the Dependency

If a field is set by code outside Spring or through a static holder, the BeanFactory may have no registered relation. Inspect the container's dependency graph.

### Mistake 5 — Adding @DependsOn When DI Is Already Clear

If the constructor already injects the dependency, `@DependsOn` with the same name is usually redundant. Only add it when there is a separate prerequisite side effect.

### Mistake 6 — Swapping registerDependentBean Parameters

`registerDependentBean("store","writer")` records **writer depends on store**. Swapping the arguments reverses the relation.

### Mistake 7 — Class-Level @DependsOn on a Bean Registered via XML

The Javadoc states class-level annotations require component scanning to take effect. For pure XML beans, use the `depends-on` attribute.

### Mistake 8 — Depends-on Pointing to a Non-Existent Bean

If the name is wrong, a profile/condition excludes the target, or a resource is not loaded, creation of the dependent can fail. `@DependsOn` does not discover Java classes by type.

### Mistake 9 — Cycle: A Depends on B, B Depends on A

This is an unsatisfiable ordering constraint. Changing declaration order cannot fix it; the dependency graph design must change.

### Mistake 10 — Thinking @Lazy Prevents All Initialization

An eager singleton with `@DependsOn` pointing to a lazy bean can still force the lazy bean to be created during refresh.

### Mistake 11 — Expecting Prototype Destruction on Close

Prototypes are created by Spring, yet the container by default does not track destruction callbacks like singletons. Callers must manage resources.

### Mistake 12 — Leaving the Context Unclosed

Without closing the context, there is no guarantee shutdown callbacks will execute at the expected time. When running applications, configure proper shutdown/close handling.

### Mistake 13 — Having @PreDestroy Yet Missing Processor/API

With Spring 6+, proper Jakarta annotation dependencies and annotation processing are needed. If the callback is not registered, the ordering graph will not make shutdown code run.

### Mistake 14 — Closing Resources Manually Before Spring Destroys Consumers

A pool managed as a singleton yet closed early by business code calling `close()` leaves active consumers pointing at a closed resource. Pick a single lifecycle owner.

### Mistake 15 — Believing Destruction Order Solves Async Readiness

`@DependsOn` does not wait for all background tasks to finish. A bean's init callback may return before the task does. On stop, drain/await with timeouts.

### Mistake 16 — Believing Two Contexts Synchronize Shutdown Automatically

Root/child contexts are not a single bean factory. Close contexts according to proper ownership, usually child before parent when the child depends on the parent.

### Mistake 17 — Testing String Order of Unrelated Beans

If two beans have no registered dependency edge, there is no reason to force them to destroy in a fixed order in tests. Assert only contracted relations.

### Mistake 18 — Using Static/Global Registries Unconditionally

`@DependsOn` can patch ordering for legacy code, yet a type-safe object graph via DI is usually clearer and easier to test.

### Mistake 19 — Treating @PreDestroy as Complete Graceful-Shutdown Orchestration

A callback is only one object's cleanup step. For message listeners, HTTP servers, and thread pools, you need stop/drain/lifecycle strategies before closing critical resources.

### Mistake 20 — Holding Resources in Unmanaged Threads

Spring can destroy beans in the right order while another thread still accesses a closed singleton. Thread ownership and shutdown coordination must be designed separately.

### Mistake 21 — Assuming Callbacks Always Run During Abnormal Shutdown

If the JVM receives `kill -9`, crashes, or the host stops abruptly, Spring callbacks may have no chance to run. Critical persistence needs proper transactions/durable queues/flush guarantees rather than relying solely on shutdown hooks.

### Mistake 22 — Confusing Callback Failures with Graph Failures

If `dependent.destroy()` throws an exception, Spring may still attempt to clean up other beans per the container's contract; do not expect one exception to halt all cleanup completely. Log and handle cleanup errors carefully without masking earlier root causes.

## 21. Designing Graceful Shutdown for Real-World Services

An application receiving messages and persisting to a database typically has:

```text
MessageListener --> JobExecutor --> TransactionalWriter --> DataSource
```

Desired steps:

1. Stop accepting new messages so no new work is generated.
2. Wait for in-flight jobs to finish or cancel within a timeout.
3. Flush buffered writes.
4. Destroy writers/adapters that have stopped using the `DataSource`.
5. Close the `DataSource`/pool last.

Bean destruction order from DI/`depends-on` can assist with steps **4 → 5**. However, steps **1 → 3** need lifecycle APIs or application-specific draining policies.

### 21.1. Use SmartLifecycle When Appropriate

`SmartLifecycle` supports phases for starting/stopping components. If a listener must stop before a pool is destroyed, bring the listener under lifecycle orchestration instead of relying entirely on `destroy()`.

Note that **stop phase order is not automatically identical to bean destruction order**. Each mechanism has its own contract and place during closing. Test both stopping incoming work and resource closing order.

### 21.2. Ensure Idempotent Destroy

`destroy()` should tolerate an already closed/stopped state if the library permits, and avoid letting a cleanup failure erase the original error information. Use clear logging, single resource ownership, and bounded timeouts.

### 21.3. External Resources Are Not Spring Beans

A broker or database server running on another machine will not be shut down by Spring following the in-JVM bean graph. Spring only closes **client/session/pool wrappers** owned by the application; external service availability must be managed at another layer.

## 22. Testing Patterns to Verify Order

### 22.1. Assert Relations Rather Than Source Order

If bean B depends on A, you can check:

```java
int aInit = events.indexOf("A.init");
int bInit = events.indexOf("B.init");

if (!(aInit >= 0 && bInit > aInit)) {
    throw new AssertionError("B initialized before A");
}
```

This is an illustrative snippet; `events` is a `List<String>` recording callback events. For a singleton chain, you can check similarly:

```java
int bDestroy = events.indexOf("B.destroy");
int aDestroy = events.indexOf("A.destroy");

if (!(bDestroy >= 0 && aDestroy > bDestroy)) {
    throw new AssertionError("A destroyed before B");
}
```

### 22.2. Tests Must Trigger context.close()

To test destruction callbacks, force an actual context close:

```java
try (var context =
         new AnnotationConfigApplicationContext(TestConfig.class)) {
    // assert initialization / relations
}
// assert destruction events AFTER close
```

`TestConfig` is an illustrative test class requiring a real implementation. Do not assert destroy events **before** closing the context.

### 22.3. Test Startup Graph and Shutdown Graph

Do not only assert `A.init < B.init`. Also verify `B.destroy < A.destroy` if cleanup order is critical. A configuration might initialize in the right order by coincidence while lacking a registered relation, leaving teardown with no proper guarantee.

### 22.4. Integration Tests When Dependencies Are Scanned

If using `@DependsOn` on a `@Component` class, test with actual component scanning. If switching to XML `<bean>`, re-test using XML `depends-on` to avoid the class-level annotation being ignored.

### 22.5. Prototype Test

Create a prototype, verify constructor/init ran; close the context and verify destroy did not run automatically. If the prototype holds resources, separately test cleanup performed by its owner.

## 23. Review Questions with Answers

**Question 1.** Given A depends on B, which bean initializes first?

**Answer:** B before A.

**Question 2.** Given two singletons where A depends on B, which bean is destroyed first?

**Answer:** A before B.

**Question 3.** Does `@DependsOn("store")` automatically inject `store` into a bean's field?

**Answer:** No. It declares an initialization/destruction relationship by name without supplying an object reference.

**Question 4.** Can constructor injection affect shutdown order?

**Answer:** Yes. For dependencies resolved and registered in relationships by the BeanFactory, the container can use those relations to destroy the dependent before the dependency.

**Question 5.** How does `getDependentBeans("store")` differ from `getDependenciesForBean("store")`?

**Answer:** The former lists beans that depend on `store`; the latter lists beans that `store` depends on.

**Question 6.** Why is `@Order(1)` insufficient for managing shutdown?

**Answer:** `@Order` does not create an explicit bean dependency relationship for the destruction registry.

**Question 7.** Does XML `depends-on="cache,metrics"` require `cache` to be destroyed before `metrics`?

**Answer:** Not in the sense of imposing a total order between the two prerequisites; it forces the dependent bean to be destroyed before each prerequisite.

**Question 8.** Does a bean with `@Lazy` that was never created run destroy?

**Answer:** There is no instance to destroy.

**Question 9.** Eager singleton A depends on lazy singleton B; can B be created during startup?

**Answer:** Yes. A must wait for B to initialize.

**Question 10.** Does a prototype bean implementing `DisposableBean` automatically destroy on context close?

**Answer:** By default, no. The client/appropriate management mechanism must clean up prototype instances.

**Question 11.** Which direction does `registerDependentBean("pool","worker")` represent?

**Answer:** `Worker` depends on `pool`; destroy `worker` before `pool`.

**Question 12.** Can `getDependenciesForBean("worker")` return null due to missing `depends-on`?

**Answer:** The API returns an array of names or an empty array when there are no registered dependencies; it is `BeanDefinition.getDependsOn()` that can return null when no explicit `depends-on` metadata is declared.

**Question 13.** Do `@PreDestroy` and `@DependsOn` serve the same purpose?

**Answer:** No. `@PreDestroy` is a cleanup callback for a single bean; `@DependsOn` specifies ordering between beans.

**Question 14.** Can you rely on bean declaration order in a Java file?

**Answer:** Not to guarantee lifecycle ordering. You need DI or explicit `depends-on`.

**Question 15.** Why is a static global registry hard to make shutdown-safe?

**Answer:** The container may not see relationships between consumers and the registry. Prefer DI or declare explicit dependency relationships when appropriate.

**Question 16.** If a background task has not finished when an initializer returns, does `@DependsOn` wait automatically?

**Answer:** No. It waits for bean initialization per the Spring lifecycle, not all external tasks.

**Question 17.** Does Spring automatically control bean destruction order across two independent ApplicationContexts?

**Answer:** No. Close order across contexts must be managed separately.

**Question 18.** When is `SmartLifecycle` needed rather than destroy callbacks alone?

**Answer:** When start/stop/drain stages, phase ordering, and coordinated shutdown are needed before singleton resources are destroyed.

## 24. Application Checklist

- [ ] Drawn the "A uses B" graph for critical singletons.
- [ ] Used constructor injection when B is a real object dependency of A.
- [ ] Used `@DependsOn`/`depends-on` for side effects/init prerequisites not expressed via DI.
- [ ] Checked direction: dependent carries the annotation, prerequisite sits in the list of names.
- [ ] Created no cycles in the graph.
- [ ] Used stable bean names; accounted for aliases/profiles/conditions.
- [ ] Verified beans are truly container-managed, not manually `new`-ed.
- [ ] Checked cleanup beans have valid `@PreDestroy`/`DisposableBean`/`destroyMethod`.
- [ ] Tested both initialization **and** destruction relations.
- [ ] Did not assert ordering for unrelated beans.
- [ ] Checked prototype/lazy/custom scopes separately from singletons.
- [ ] Did not overlook parent-child contexts and resource ownership.
- [ ] Used `getDependentBeans`/`getDependenciesForBean` to debug the actual graph.
- [ ] For async tasks/web consumers, designed stop/drain and timeouts alongside destroy callbacks.
- [ ] Did not rely on shutdown callbacks to replace data durability on process crash.
- [ ] Monitored logs, resource leaks, and warnings during real deploy/stop cycles.

## 25. Official Documentation

- [Spring Framework 6.2 — Using depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html): guaranteed initialization and reverse singleton destruction.
- [Spring Framework 6.2.19 — DependsOn Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/DependsOn.html): definition, TYPE/METHOD targets, class-level limitation when registered via XML.
- [Spring Framework 6.2.19 — DefaultSingletonBeanRegistry Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/support/DefaultSingletonBeanRegistry.html): `registerDependentBean`, `getDependentBeans`, `getDependenciesForBean`, `destroySingletons`.
- [Spring Framework 6.2.19 — ConfigurableBeanFactory Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/config/ConfigurableBeanFactory.html): inspecting registered bean dependencies and managing destruction.
- [Spring Framework — Lifecycle Callbacks](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): init/destroy methods, `InitializingBean`, `DisposableBean`, and annotation callbacks.
- [Spring Framework 6.2 — Bean Scopes](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-scopes.html): singleton, prototype, and prototype destruction limits.
- [Spring Framework — ApplicationContext Shutdown](https://docs.spring.io/spring-framework/reference/6.2/core/beans/factory-nature.html): lifecycle when closing the container.
- [Spring Framework — SmartLifecycle](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/SmartLifecycle.html): phase-based startup/shutdown orchestration.

**Conclusion:** Spring does not merely create beans following the dependency graph; for managed singletons with dependency relationships recognized by the container, it also **destroys the dependent before its dependency** so prerequisite resources remain alive during dependent cleanup. `@DependsOn`/XML `depends-on` is the explicit declaration for relationships not expressed via DI; `getDependentBeans` and `getDependenciesForBean` help verify the graph. Do not confuse singleton destruction order with prototype destruction, `@Order` ordering, or graceful shutdown of threads and external services. Let **DI express object dependencies, `depends-on` express lifecycle constraints, and lifecycle APIs handle stop/drain**.
