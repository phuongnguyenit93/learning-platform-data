# Deferring Bean Creation with @Lazy and lazy-init in Spring Core Container

## 1. Problem Statement

When a Spring application starts up, a regular `ApplicationContext` **pre-creates singleton beans not marked lazy** before completing `refresh()`. This is the *eager pre-instantiation* strategy: the container checks constructors, dependency injection, and many configuration errors right at startup, instead of letting failures surface only when a user invokes a feature much later.

However, some beans can be very expensive to create: clients connecting to optional services, large decoders, components used only in rare features, or adapters used in a special workflow. When eager initialization is unnecessary, Spring supports **lazy initialization**:

- Use **`@Lazy`** on a Java `@Bean` method or component class.
- Use **`lazy-init="true"`** on an XML `<bean>`.
- Place **`@Lazy`** on a `@Configuration` class to apply a default to `@Bean` methods in that class.
- Place **`default-lazy-init="true"`** on XML `<beans>` to set a default for bean definitions in that document.
- Use **`@Lazy` at an injection point** to inject a *lazy-resolution proxy* instead of immediately resolving the target bean when creating the consumer.

These options are **not equivalent in effect in all situations**. A bean marked lazy can still be created at startup if a non-lazy singleton requires it. And `@Lazy` placed on a bean definition is not the same as `@Lazy` on an injection parameter.

### Lesson Objectives

After this lesson, you will be able to:

1. Explain the phases **BeanDefinition registration → singleton creation during refresh → lookup/use**.
2. Distinguish eager, lazy, singleton, prototype, and request/session/custom scopes.
3. Configure Java `@Lazy` and XML `lazy-init` in the right places; understand `true`/`false` values.
4. Explain the impact of eager dependencies, `@DependsOn`, XML `depends-on`, injecting into collections, and bootstrap callbacks.
5. Use `@Lazy` at an injection point to defer resolution with a lazy proxy; know its limitations regarding optional dependencies, types/proxies, and error timing.
6. Compare `@Lazy` with `ObjectProvider<T>`, `Provider<T>`, `@Scope`, and background bootstrap mechanisms.
7. Run a Java 17+ example with Spring Framework 6.2.19, observing constructor counters before/after lookup.
8. Decide where to use lazy, weighing first-request latency, delayed error detection, and resource management.

**Context:** This topic belongs to the **Bean Creation Timing** group in Spring Framework Core Container. The lesson focuses on **lifecycle and instantiation timing**, not to be confused with deferred configuration parsing or runtime asynchronous programming.

## 2. What Do Eager and Lazy Actually Control?

A `BeanDefinition` is metadata about name, Java type, scope, factory method, arguments, lazy flag, and lifecycle. It can exist in the registry **before the bean instance is created**.

```text
XML <bean> / Java @Bean / @ComponentScan
                |
                v
       BeanDefinitionRegistry
                |
                v
         Context refresh()
                |
                +--> create non-lazy singleton beans
                |
                +--> keep lazy singleton definitions uncreated
                |
                v
         Context started
                |
          getBean(lazyName) / dependency lookup
                |
                v
         create lazy singleton if needed
                |
                v
         reuse instance in context
```

On a standard `ApplicationContext`:

- **Non-lazy singleton (default):** Spring attempts to pre-instantiate it during container startup.
- **Lazy singleton:** Spring does not pre-instantiate it merely because the definition exists; the bean is created when an actual resolution request occurs.
- **Prototype:** is not pre-instantiated like a regular singleton; the container creates an instance each time the bean is requested, even though a lazy flag may appear in metadata.
- **Scoped beans (request/session/custom):** creation timing depends on the scope implementation and active context; you cannot reason about them the same way as singletons.

With a lazy singleton, two `getBean("reportClient")` calls in the **same context** after the bean has been created normally return **the same instance**. `@Lazy` changes *creation timing*, it does not turn a singleton into a prototype.

### 2.1. Why Does Spring Default to Eager?

Key benefits of pre-instantiation:

1. Catch missing beans and injection conflicts early.
2. Catch constructor/factory method errors early.
3. Validate required configuration/resources before receiving traffic.
4. Avoid shifting initialization cost onto the first request.
5. Make startup diagnostics easier to reason about.

Lazy initialization trades this for the ability to shorten part of startup when beans are not yet needed, but it can **defer errors** and **concentrate latency** onto first use. Therefore, do not enable it for every bean without measuring the effect.

## 3. @Lazy on Java @Bean

A Java configuration:

```java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;

@Configuration(proxyBeanMethods = false)
public class AdapterConfig {
    @Bean
    @Lazy
    ExternalReportClient reportClient() {
        return new ExternalReportClient();
    }

    @Bean
    RequestRouter requestRouter() {
        return new RequestRouter();
    }
}
```

This is a **structural** example; `ExternalReportClient` and `RequestRouter` must be Java classes with suitable constructors included in the project. When the configuration is loaded:

- `reportClient` has a bean definition marked **lazy**.
- `requestRouter` is a non-lazy singleton by default.
- If `requestRouter` does not depend on `reportClient` and no infrastructure retrieves `reportClient` early, Spring can initialize `requestRouter` during refresh while deferring `reportClient`.
- On the first lookup of `reportClient`, Spring invokes the `reportClient()` factory method and manages the result.

**Note:** the annotation must be imported from the exact package `org.springframework.context.annotation.Lazy`. It differs from `Lazy` annotations in third-party libraries or custom annotations.

### 3.1. @Lazy Defaults to true

```java
@Lazy
@Bean
ExternalReportClient reportClient() {
    return new ExternalReportClient();
}
```

is equivalent to:

```java
@Lazy(true)
@Bean
ExternalReportClient reportClient() {
    return new ExternalReportClient();
}
```

`@Lazy(false)` is an explicit way to choose **eager initialization**, especially when inheriting a lazy default from a configuration class or other policies.

### 3.2. Annotation Placement

`@Lazy` can be used on:

- A type annotated with `@Component` or a valid stereotype.
- A `@Bean` method.
- A `@Configuration` class, affecting the lazy default of `@Bean` methods in that configuration class.
- A field, constructor, or parameter at an **injection point** alongside `@Autowired`/`@Inject`, with **lazy-resolution proxy** semantics.

**Do not conflate the two semantics:** `@Lazy` on a **definition** controls whether the target bean is pre-instantiated; `@Lazy` on an **injection point** controls dependency resolution when injecting the consumer.

## 4. @Lazy on a Component Class

Example stereotype-annotated service:

```java
package com.example.report;

import org.springframework.context.annotation.Lazy;
import org.springframework.stereotype.Service;

@Service
@Lazy
public class ReportRenderer {
    public String render() {
        return "report";
    }
}
```

If the class is in a package covered by `@ComponentScan` or XML `<context:component-scan>`, Spring registers the `reportRenderer` bean definition as lazy. The bean is not instantiated merely because the scanner found the class; when `getBean(ReportRenderer.class)` or an eager dependency actually needs it, Spring creates the bean.

### 4.1. @Lazy Does Not Automatically Enable Component Scanning

A class with `@Service @Lazy` that has **not been registered with Spring** has no bean definition to be lazy/eager. You need `@ComponentScan`, XML component-scan, or an appropriate registration path.

### 4.2. @Lazy on a Class Not Created by Spring

```java
ReportRenderer renderer = new ReportRenderer();
```

An object created via `new` in Java code outside the BeanFactory does not have Spring's lazy lifecycle applied. The annotation is metadata interpreted by the container when the class is managed by Spring; it does not intercept Java constructors.

## 5. @Lazy on a @Configuration Class

`@Lazy` placed on a `@Configuration` class sets the lazy default for the `@Bean` methods inside:

```java
@Configuration(proxyBeanMethods = false)
@Lazy
public class OptionalModuleConfig {
    @Bean
    ArchiveReader archiveReader() {
        return new ArchiveReader();
    }

    @Bean
    ReportExporter reportExporter() {
        return new ReportExporter();
    }

    @Bean
    @Lazy(false)
    HealthIndicator healthIndicator() {
        return new HealthIndicator();
    }
}
```

This is an illustrative Java snippet; it requires imports for `@Bean`, `@Configuration`, `@Lazy`, and the three real Java types. Meaning:

- `archiveReader` and `reportExporter` are lazy by default.
- `healthIndicator` overrides to non-lazy via `@Lazy(false)`.
- The `@Configuration` class itself still needs to be **registered/parsed** by Spring in the context.
- Do not equate creating the configuration class instance with executing every `@Bean` factory method. Configuration metadata is processed during startup even though some target bean instances are deferred.

### 5.1. @Lazy on a Component Stereotype with @Bean Methods

Spring supports `@Lazy` on types marked `@Component`. However, if you want a lazy default for **all factory methods**, use `@Configuration @Lazy` as intended and explicitly test imported configurations and method overrides. Do not assume every class brought in by `@Import` from a lazy configuration automatically inherits the lazy flag; annotation scope must be understood per definition.

## 6. XML lazy-init="true" on <bean>

In XML configuration:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="eagerClient" class="com.example.EagerClient"/>

    <bean id="lazyClient"
          class="com.example.ExpensiveClient"
          lazy-init="true"/>
</beans>
```

In this example:

- `eagerClient` is a non-lazy singleton by default.
- `lazyClient` has a lazy bean definition and is normally not created during pre-instantiation.
- `context.getBean("lazyClient")` can cause Spring to create the bean on the first call.
- If another eager singleton requires `lazyClient`, Spring must still create `lazyClient` to satisfy the dependency (see Section 8).

`lazy-init` is an **XML bean-definition attribute**, not a Java field, not a property of the target class, and not a library-specific lazy network connection mechanism.

### 6.1. Explicit false

```xml
<bean id="importantClient"
      class="com.example.ImportantClient"
      lazy-init="false"/>
```

Use `false` when you want to make explicit that this bean needs to be created at startup; it is especially useful for overriding an XML resource's `default-lazy-init`.

### 6.2. Do Not Confuse with scope="prototype"

```xml
<bean id="builder"
      class="com.example.Builder"
      scope="prototype"
      lazy-init="true"/>
```

Prototype scope already has **create on demand** semantics; it has no regular singleton pre-instantiation. Putting `lazy-init` on a prototype usually makes no difference compared to singleton. Two prototype lookups can still create two instances.

## 7. XML default-lazy-init="true"

Spring supports setting a default on the root `<beans>`:

```xml
<beans xmlns="http://www.springframework.org/schema/beans"
       default-lazy-init="true">

    <bean id="optionalClient"
          class="com.example.OptionalClient"/>

    <bean id="criticalMonitor"
          class="com.example.CriticalMonitor"
          lazy-init="false"/>
</beans>
```

This is a structural snippet; in a real file declare `schemaLocation` as in the complete XMLs in the demo section. Any `<bean>` without an override can inherit the XML document's lazy default. `criticalMonitor` is explicitly marked **eager**.

### 7.1. Effect Is Scoped to the XML Resource Metadata

`default-lazy-init` is not a "global JVM flag" applied to every bean in every context. It is a default within the corresponding XML document, per BeanDefinition parsing mechanics. Definitions from Java configuration, programmatic registration, or other XML files can have their own lazy flags.

With multiple XML imports or nested `<beans>`, check the actual configuration of each resource and definition. Do not assume a flag in `settings.xml` automatically changes the metadata of every bean in the application.

### 7.2. Should You Enable It Everywhere?

Only enable it after considering:

- Which beans must fail-fast before the app receives traffic?
- Are there startup event listeners or health checks needing beans immediately?
- Are required resources validated at startup?
- Can the first request to a feature tolerate the initialization time?
- Are lazy beans being pulled into startup by eager dependencies anyway?

If using Spring Boot, there is also `spring.main.lazy-initialization=true`; that is a **Boot feature**, not identical to an XML `default-lazy-init` in plain Spring Framework.

## 8. Important Trap: An Eager Dependency Can Create a Lazy Bean at Startup

Suppose `ExpensiveService` is a `@Lazy` singleton, while `EagerController` is a non-lazy singleton that directly takes `ExpensiveService` in its factory method:

```java
@Bean @Lazy
ExpensiveService expensiveService() { return new ExpensiveService(); }

@Bean
EagerController eagerController(ExpensiveService service) {
    return new EagerController(service);
}
```

When `ApplicationContext.refresh()` creates the controller, Spring **must resolve dependencies** before calling the factory method. Therefore `expensiveService` is created during startup; `@Lazy` on the definition only excludes the bean from automatic pre-instantiation, not from an actual dependency demand.

When debugging, identify which path requests the target: constructor, field/setter, `@Bean` parameter, `depends-on`, component infrastructure, or explicit `getBean`. XML `lazy-init="true"` also cannot avoid an eager `<constructor-arg ref="..."/>`. Do not just move bean declaration order or add `@DependsOn`: those do not defer dependencies.

If the consumer can genuinely run before needing the target, consider **`@Lazy` at the injection point** (a proxy deferring lookup) or `ObjectProvider<T>` (explicit lookup at processing time). The next lesson specifically examines eager→lazy chains across multiple dependency levels; the section below focuses on configuring a lazy-resolution proxy.

## 9. @Lazy at the Injection Point: Lazy-Resolution Proxy

`@Lazy` can be placed on a suitable constructor parameter, field, or method injection point. For example:

```java
@Component
public class CheckoutService {
    private final InvoiceApi invoiceApi;

    public CheckoutService(@Lazy InvoiceApi invoiceApi) {
        this.invoiceApi = invoiceApi;
    }

    public String issueInvoice() {
        return invoiceApi.issue();
    }
}
```

This is an illustrative snippet; `InvoiceApi` must be an appropriate interface/bean type with `@Component` and `@Lazy` imported. When Spring creates `CheckoutService`, it can inject a **lazy-resolution proxy** instead of instantiating the target immediately.

### 9.1. Two Different Ways to Place @Lazy

**Placed on the target bean definition:**

```java
@Bean
@Lazy
InvoiceApi invoiceApi() {
    return new DefaultInvoiceApi();
}
```

affects **pre-instantiation of the target**.

**Placed at the injection point:**

```java
@Bean
CheckoutService checkoutService(@Lazy InvoiceApi invoiceApi) {
    return new CheckoutService(invoiceApi);
}
```

affects **when the dependency is resolved/the real target is supplied to the consumer**.

For the real target to remain uncreated at startup in a simple program, you normally need to ensure **both the target definition is lazy** *and* **the consumer receives a lazy proxy**, while no other eager bean forces target creation.

### 9.2. When the Proxy Is Used for the First Time

Calling a business method on the proxy causes Spring to resolve the real target. For a singleton target, subsequent resolutions normally reuse the created singleton target. For non-singleton scopes, the proxy can re-resolve the target on appropriate calls according to scope/lifecycle.

The proxy is not the target instance; checking `proxy.getClass() == target.getClass()` is not a way to verify whether the target has been initialized. And calling certain methods on the proxy can trigger target resolution, even when you only intend to log or inspect the proxy.

### 9.3. Do Not Use a @Lazy Injection Proxy as an Optional Dependency Detector

Spring's Javadoc states clearly that a lazy-resolution proxy is **always injected** at a matching injection point. If the target dependency does not actually exist, an error may only occur when calling a method on the proxy, meaning checks like `invoiceApi != null` will not detect a missing dependency.

For optional/conditional dependencies, Spring recommends clearer APIs such as:

```java
public CheckoutService(ObjectProvider<InvoiceApi> invoiceApiProvider) {
    this.invoiceApiProvider = invoiceApiProvider;
}
```

or a corresponding `Provider<T>` interface when supported by dependencies and the stack. With `ObjectProvider`, you explicitly call `getIfAvailable()`/`getObject()`, checking absence and fallback policy. You need to import `org.springframework.beans.factory.ObjectProvider` in complete Java code.

### 9.4. What Design Limitations Does a Proxy Have?

- Interface injection points generally work with JDK proxies; injecting by concrete class may require class-based proxies.
- Final classes, final methods, visibility, and module access can make proxies difficult or impossible to create.
- Using proxies with methods relying on identity/`equals`/`hashCode` requires understanding proxy semantics.
- You should not have the consumer bean's constructor immediately call a method on the lazy proxy if your goal is to defer the target.
- If the target bean is eager due to another configuration, a lazy proxy **does not guarantee the target has not been created**.
- A proxy can cause exceptions to occur on the first request instead of at startup.

**Principle:** a lazy proxy is a **deferred dependency resolution** mechanism, not magic that makes every class lazy-safe.

## 10. Hands-on Example in Java 17+ with Spring Framework 6.2.19

The lab demonstrates:

1. **XML bean lazy-init:** compare eager and lazy singletons.
2. **XML default-lazy-init:** apply default laziness and override one bean to eager.
3. **Java @Bean @Lazy:** see Java config equivalent to XML.
4. **Eager consumer forcing lazy dependency initialization:** prove the key anti-assumption.
5. **@Lazy at the injection point:** create an eager consumer while instantiating the target only when a method is actually called.

So that observations are **not distorted by logging or wall-clock timing**, each Java class is instrumented with an `AtomicInteger` counter incremented in its constructor. The program prints counter values right after `refresh()`, after `getBean()`, or after method invocation.

### 10.1. Project Structure

```text
spring-lazy-timing-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        ├── java/
        │   └── demo/
        │       └── LazyTimingDemo.java
        └── resources/
            ├── xml-lazy.xml
            └── xml-default-lazy.xml
```

All Java demo code lives in **one source file**, using nested static classes for easy copy/paste. In XML, the binary name of nested classes is `demo.LazyTimingDemo$NestedClass`. The `$` character here represents the dollar sign in the Java binary name; in the two complete XML files below, the syntax uses the exact nested class names.

### 10.2. Gradle Build

**`settings.gradle`**

```groovy
rootProject.name = 'spring-lazy-timing-demo'
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
    mainClass = 'demo.LazyTimingDemo'
}
```

Use Java 17+, a Gradle version compatible with Java toolchains, and Maven Central access when fetching the dependency for the first time. No Spring Boot, servlet container, or database is involved.

### 10.3. XML #1 — One Eager, One Lazy Singleton

**`src/main/resources/xml-lazy.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">

    <bean id="xmlEager" class="demo.LazyTimingDemo$XmlEager"/>

    <bean id="xmlLazy"
          class="demo.LazyTimingDemo$XmlLazy"
          lazy-init="true"/>
</beans>
```

`XmlEager` should be created when the context starts, while `XmlLazy` will remain uncreated until lookup if no dependency forces initialization.

### 10.4. XML #2 — default-lazy-init and Explicit Override

**`src/main/resources/xml-default-lazy.xml`**

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd"
       default-lazy-init="true">

    <bean id="xmlDefaultLazy"
          class="demo.LazyTimingDemo$XmlDefaultLazy"/>

    <bean id="xmlOverrideEager"
          class="demo.LazyTimingDemo$XmlOverrideEager"
          lazy-init="false"/>
</beans>
```

Because of `default-lazy-init="true"`, `xmlDefaultLazy` is not pre-instantiated; because of explicit `lazy-init="false"`, `xmlOverrideEager` is created during refresh.

### 10.5. Complete Java Source

**`src/main/java/demo/LazyTimingDemo.java`**

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Lazy;
import org.springframework.context.support.ClassPathXmlApplicationContext;

public final class LazyTimingDemo {

    private static final AtomicInteger XML_EAGER = new AtomicInteger();
    private static final AtomicInteger XML_LAZY = new AtomicInteger();
    private static final AtomicInteger XML_DEFAULT = new AtomicInteger();
    private static final AtomicInteger XML_OVERRIDE = new AtomicInteger();

    private static final AtomicInteger JAVA_EAGER = new AtomicInteger();
    private static final AtomicInteger JAVA_LAZY = new AtomicInteger();
    private static final AtomicInteger FORCED = new AtomicInteger();
    private static final AtomicInteger PROXY_TARGET = new AtomicInteger();

    public static final class XmlEager {
        public XmlEager() {
            XML_EAGER.incrementAndGet();
        }
    }

    public static final class XmlLazy {
        public XmlLazy() {
            XML_LAZY.incrementAndGet();
        }
    }

    public static final class XmlDefaultLazy {
        public XmlDefaultLazy() {
            XML_DEFAULT.incrementAndGet();
        }
    }

    public static final class XmlOverrideEager {
        public XmlOverrideEager() {
            XML_OVERRIDE.incrementAndGet();
        }
    }

    public static final class JavaEager {
        public JavaEager() {
            JAVA_EAGER.incrementAndGet();
        }
    }

    public static final class JavaLazy {
        public JavaLazy() {
            JAVA_LAZY.incrementAndGet();
        }
    }

    public static final class ForcedDependency {
        public ForcedDependency() {
            FORCED.incrementAndGet();
        }
    }

    public static final class ForcedConsumer {
        private final ForcedDependency dependency;

        public ForcedConsumer(ForcedDependency dependency) {
            this.dependency = dependency;
        }

        public boolean ready() {
            return dependency != null;
        }
    }

    public interface JobWorker {
        String work();
    }

    public static final class RealWorker implements JobWorker {
        public RealWorker() {
            PROXY_TARGET.incrementAndGet();
        }

        @Override
        public String work() {
            return "work-done";
        }
    }

    public static final class JobConsumer {
        private final JobWorker worker;

        public JobConsumer(JobWorker worker) {
            this.worker = worker;
        }

        public String run() {
            return worker.work();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class JavaBasicConfig {
        @Bean
        JavaEager javaEager() {
            return new JavaEager();
        }

        @Bean
        @Lazy
        JavaLazy javaLazy() {
            return new JavaLazy();
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class JavaForcedConfig {
        @Bean
        @Lazy
        ForcedDependency forcedDependency() {
            return new ForcedDependency();
        }

        @Bean
        ForcedConsumer forcedConsumer(ForcedDependency dependency) {
            return new ForcedConsumer(dependency);
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class ProxyConfig {
        @Bean
        @Lazy
        JobWorker jobWorker() {
            return new RealWorker();
        }

        @Bean
        JobConsumer jobConsumer(@Lazy JobWorker worker) {
            return new JobConsumer(worker);
        }
    }

    public static void main(String[] args) {

        // 1. XML: eager bean created during refresh, lazy created on lookup.
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext("xml-lazy.xml")) {

            System.out.println("xml.eager.after-refresh="
                    + XML_EAGER.get());
            System.out.println("xml.lazy.after-refresh="
                    + XML_LAZY.get());

            XmlLazy first = context.getBean("xmlLazy", XmlLazy.class);
            System.out.println("xml.lazy.after-get=" + XML_LAZY.get());
            System.out.println("xml.lazy.singleton="
                    + (first == context.getBean(XmlLazy.class)));
        }

        // 2. XML: default lazy and eager override.
        try (ClassPathXmlApplicationContext context =
                     new ClassPathXmlApplicationContext(
                             "xml-default-lazy.xml")) {

            System.out.println("xml.default.after-refresh="
                    + XML_DEFAULT.get());
            System.out.println("xml.override.after-refresh="
                    + XML_OVERRIDE.get());

            context.getBean(XmlDefaultLazy.class);
            System.out.println("xml.default.after-get="
                    + XML_DEFAULT.get());
        }

        // 3. Java @Bean @Lazy.
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             JavaBasicConfig.class)) {

            System.out.println("java.eager.after-refresh="
                    + JAVA_EAGER.get());
            System.out.println("java.lazy.after-refresh="
                    + JAVA_LAZY.get());

            context.getBean(JavaLazy.class);
            System.out.println("java.lazy.after-get="
                    + JAVA_LAZY.get());
        }

        // 4. Non-lazy consumer forces lazy dependency to be created early.
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             JavaForcedConfig.class)) {

            System.out.println("forced.after-refresh="
                    + FORCED.get());
            System.out.println("forced.consumer.ready="
                    + context.getBean(ForcedConsumer.class).ready());
        }

        // 5. Lazy bean + @Lazy injection point: proxy defers target.
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(
                             ProxyConfig.class)) {

            System.out.println("proxy.target.after-refresh="
                    + PROXY_TARGET.get());

            JobConsumer consumer = context.getBean(JobConsumer.class);
            System.out.println("proxy.result=" + consumer.run());
            System.out.println("proxy.target.after-use="
                    + PROXY_TARGET.get());
            System.out.println("proxy.again=" + consumer.run());
            System.out.println("proxy.target.after-second-use="
                    + PROXY_TARGET.get());
        }
    }
}
```

### 10.6. Compile/Run Command

In the `spring-lazy-timing-demo` directory:

```bash
gradle run --quiet
```

If using the Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

Running `javac LazyTimingDemo.java` alone is **not sufficient** because Spring libraries must be provided on the compile/runtime classpath. Gradle's `application` plugin handles building, running, and copying `src/main/resources` onto the classpath.

### 10.7. Expected Program Stdout

```text
xml.eager.after-refresh=1
xml.lazy.after-refresh=0
xml.lazy.after-get=1
xml.lazy.singleton=true
xml.default.after-refresh=0
xml.override.after-refresh=1
xml.default.after-get=1
java.eager.after-refresh=1
java.lazy.after-refresh=0
java.lazy.after-get=1
forced.after-refresh=1
forced.consumer.ready=true
proxy.target.after-refresh=0
proxy.result=work-done
proxy.target.after-use=1
proxy.again=work-done
proxy.target.after-second-use=1
```

The program intentionally prints these **17 lines** using `System.out.println`. Gradle/framework may print extra logs depending on the environment; logs are not part of the results computed by the program.

### 10.8. Exact Explanation of Each Result Group

**XML single lazy bean group:** `XmlEager` has no lazy flag, so its constructor runs during refresh and the counter is 1. `XmlLazy` has `lazy-init="true"`, so the counter stays 0 after refresh. The first lookup creates the instance (counter 1), and the second lookup returns **the same singleton**.

**XML default group:** `default-lazy-init="true"` leaves `xmlDefaultLazy` uncreated after refresh; the `lazy-init="false"` override causes `xmlOverrideEager` to initialize early. Fetching `XmlDefaultLazy` afterwards brings the count to 1.

**Java group:** `JavaEager` is a non-lazy singleton and `JavaLazy` is marked `@Lazy`. After refresh the counters are 1 and 0 respectively; after `getBean(JavaLazy.class)` the lazy count becomes 1.

**Required dependency group:** `forcedDependency` is marked `@Lazy`, but `forcedConsumer` is an eager singleton with a factory method parameter requiring `ForcedDependency`. Spring must create the dependency during refresh, so `forced.after-refresh=1`. The consumer holds a non-null dependency.

**Proxy group:** `jobWorker` has `@Lazy` on its bean definition; `jobConsumer` injects `@Lazy JobWorker worker` at the **factory method parameter**. The consumer is created early with a lazy-resolution proxy, while the target `RealWorker` has not been created yet (`counter=0`). Calling `consumer.run()` resolves `jobWorker` for the first time, incrementing the counter to 1. Calling it a second time reuses the already created singleton target, so the counter remains 1.

### 10.9. Limitations of This Example

The counters only record constructors of the instrumented classes. They do **not** claim Spring created zero infrastructure beans or configuration class instances during startup. `@Configuration` metadata is still processed, and the container still needs processors/registry.

Do not use counter snapshots to estimate production performance: actual time also depends on I/O, DNS, network handshakes, classloading, AOT, GC, caching, and thread scheduling. For production, measure with profiling/metrics rather than counting constructors.

## 11. @Lazy(false) When You Want Explicit Eagerness

In Java config:

```java
@Configuration(proxyBeanMethods = false)
@Lazy
public class MostlyLazyConfig {
    @Bean
    Formatter formatter() {
        return new Formatter();
    }

    @Bean
    @Lazy(false)
    CriticalHealthCheck criticalHealthCheck() {
        return new CriticalHealthCheck();
    }
}
```

This is a snippet with illustrative `Formatter`/`CriticalHealthCheck` types. `criticalHealthCheck` remains a non-lazy singleton even though the configuration class has `@Lazy`; `formatter` is lazy by default. This is analogous to XML `default-lazy-init="true"` with a `<bean lazy-init="false">`.

### When Should You Override?

- A health-check validator that needs to prove configuration is valid before the service accepts requests.
- Data schema/migration preflight that needs to fail fast before traffic.
- Security policy/key validation that should not be deferred until the first request.
- Publishers/background schedulers that need to be initialized proactively, not the first time someone calls `getBean()`.
- Components that must register callbacks/event handlers before the context begins emitting critical events.

To avoid surprises, beans with bootstrap roles should be documented and explicitly tested for initialization timing.

## 12. Eager Dependencies and @DependsOn

### 12.1. Real Dependency via Constructor/Factory Method

If an eager `CheckoutService` requires a lazy `PricingClient` in its constructor, Spring creates `pricingClient` before `CheckoutService` is created. This is a normal **dependency graph**.

### 12.2. depends-on Is an Explicit Initialization Constraint

```xml
<bean id="metricsRegistry"
      class="com.example.MetricsRegistry"
      lazy-init="true"/>

<bean id="appCoordinator"
      class="com.example.AppCoordinator"
      depends-on="metricsRegistry"/>
```

Assuming `appCoordinator` is a non-lazy singleton, Spring must initialize `metricsRegistry` first to satisfy `depends-on`, even though the target registry is lazy. With `@DependsOn("metricsRegistry")` on the corresponding bean/configuration, the meaning is the same.

`depends-on` does not supply an object reference like constructor injection; it expresses an **initialization prerequisite**. If the consumer actually uses the object, express the dependency directly rather than merely controlling order.

### 12.3. Does @DependsOn Help Lazy Defer Further?

No. `@DependsOn` usually forces **more** beans to initialize earlier, not fewer. If you want deferral, identify why an eager bean is requiring the target instead of adding `depends-on` arbitrarily.

## 13. How Does @Lazy Differ from ObjectProvider<T>?

Both mechanisms are useful for avoiding fetching a dependency too early, but they work differently.

### 13.1. Lazy-Resolution Proxy

```java
public ReportJob(@Lazy ReportClient reportClient) {
    this.reportClient = reportClient;
}
```

Spring injects a proxy so the consumer holds a dependency with the same API; when a method is called, the proxy resolves the target. This approach changes business method signatures minimally, but hides lookup timing and comes with proxy caveats.

### 13.2. ObjectProvider

```java
public ReportJob(ObjectProvider<ReportClient> provider) {
    this.provider = provider;
}

public void execute() {
    ReportClient reportClient = provider.getObject();
    reportClient.send();
}
```

Illustrative snippet, requiring importing `org.springframework.beans.factory.ObjectProvider` and appropriate types. `ObjectProvider` acts as an explicit **lookup point**. It supports `getIfAvailable()`, `ifAvailable(...)`, and `getIfUnique()` for optional/multiple-candidate cases.

### 13.3. Comparison Table

| Aspect | @Lazy at injection point | ObjectProvider<T> |
| --- | --- | --- |
| What consumer receives | Proxy implementing/extending the appropriate type | Provider object |
| When target is looked up | When the proxy is invoked (possibly on first method call) | When caller invokes the provider API |
| Optional target | May receive proxy even if target is absent; late failure | Provides `getIfAvailable()` API |
| Prototype scope | May re-resolve on each proxy interaction | Can call `getObject()` whenever needed |
| Proxy limitations | Yes: final classes, methods, proxy types | Normally no target proxy injection needed |
| Explicitness | Easy to use but timing is hidden | Explicit lookup in code |
| When appropriate | Stable API, dependency usually present | Optional/conditional/sophisticated runtime lookup |

**Important:** neither necessarily keeps the target uncreated if the target's bean definition **is still eager** and the context already pre-instantiated it during startup. When genuine deferral is needed, examine both the **target definition** and the **consumer graph**.

## 14. Lazy, Prototype, Scoped Proxy, and Singleton Are Not the Same

### Lazy Singleton

One instance per container created when the target is first constructed, then reused. The bean definition is still registered from the start.

### Prototype

Each `BeanFactory.getBean(...)` request normally creates a new instance. Scope is not synonymous with the lazy annotation, although both relate to timing.

### Request/Session Scopes

Web scopes require web context/request/session infrastructure. Scoped proxies can be used for injection into singletons; the proxy delegates to the active scoped instance. This is a different mechanism from a simple lazy-resolution proxy. Do not put `@Lazy` and assume request scope works by itself in a standalone `AnnotationConfigApplicationContext` without a web context.

### FactoryBean and SmartFactoryBean

Beans implementing `FactoryBean<T>` or `SmartFactoryBean<T>` have distinct semantics regarding factory/product, type prediction, and eager-init hints. A type/metadata lookup operation can have side effects in some cases. If lazy behavior is unexpected when using a FactoryBean, inspect factory vs product and the infrastructure performing lookups.

## 15. How Does Lazy Affect the Lifecycle?

### 15.1. Constructor and Init Callbacks

If a lazy bean has not yet been created, the target's constructor and initialization callbacks have not run. When the bean is retrieved for the first time, Spring creates the instance, resolves dependencies, and applies BeanPostProcessors/init callbacks before returning the appropriate managed instance.

### 15.2. @PostConstruct

`@PostConstruct` does not run during context startup if the lazy bean genuinely has not been created. When the bean is created, the callback runs if the Jakarta annotations API and corresponding `CommonAnnotationBeanPostProcessor` infrastructure are present.

**Do not conflate**: having the annotation on a class is not enough for the callback to work. And `@Lazy` does not automatically trigger `@PostConstruct`.

### 15.3. Destroy Callbacks

A **lazy singleton that has never been created** has no target instance for Spring to destroy. A lazy singleton **that was created and is managed by the context** can receive its destroy callback when the context closes, if it has a corresponding destroy-method/`@PreDestroy`/interface and appropriate infrastructure.

Prototype beans normally have different lifecycle destruction responsibilities than singletons; do not assume the container automatically destroys every prototype on close just because it carries `@Lazy`.

### 15.4. Resource Ownership

If a bean opens network connections, files, executors, or pools in its constructor/init:

- Deferring the constructor can shift when resources are acquired.
- Network errors can shift from startup to the first request.
- Once the target is created, resources still need to be closed properly.
- Explicit warm-up after the container is ready can be used if the feature is critical.

### 15.5. Thread Safety

A lazy singleton is managed by the BeanFactory with container-level thread-safe singleton registration/creation. However, the business class itself must still guarantee thread safety of mutable state. `@Lazy` does not automatically turn a class with unsynchronized mutable fields into a thread-safe one.

## 16. Should You Enable Lazy for Infrastructure Beans?

Do not enable it blanket-wise for all beans. In particular, BeanFactoryPostProcessors/BeanPostProcessors and certain framework infrastructure beans must run before regular singleton creation for the container to function properly. Some infrastructure types have early registration mechanics or must be initialized even when other beans might be lazy.

If you want to defer an expensive resource that an infrastructure bean needs to manage the whole container, design clear bootstrap boundaries rather than trying to force every processor to be lazy. Do not rely on "marked lazy" as an absolute contract when framework internals or eager dependencies are involved.

### BeanPostProcessor and the Eager Creation Problem

A custom BeanPostProcessor should not constructor-inject too many business services, because doing so can create them before normal autoproxy/processor phases. Separate configuration metadata from runtime collaborators when needed. This is not just a lazy issue; it also affects **eligibility for processing by all post-processors**.

## 17. Spring Boot Lazy Initialization: Point of Comparison

If an application uses **Spring Boot** (unlike the plain Spring Framework demo), Boot supports:

```properties
spring.main.lazy-initialization=true
```

to request broader lazy initialization via `SpringApplication` mechanics. It can be toggled via API or property, and overridden for specific beans with `@Lazy(false)`.

However:

1. This is a **Boot feature**, not a property automatically handled by plain Spring Framework Core Container.
2. It does not guarantee that every bean across all infrastructure/versions waits until the first request.
3. Eager dependencies and bootstrap requirements can still cause targets to be created early.
4. It can make **startup faster** in some systems while shifting cost/errors to first use.
5. You need to monitor memory usage because once live traffic triggers many beans, the heap must still hold all instances.
6. Global enabling should be paired with monitoring, appropriate warm-up, and a fail-fast plan for critical resources.

If a project only declares the `spring-context` dependency like the demo, putting `spring.main.lazy-initialization=true` in a properties file does not activate Boot's mechanism because Boot is not on the runtime classpath.

## 18. Lazy vs Commonly Confused Mechanisms

| Mechanism | Primary function | Does it replace @Lazy? |
| --- | --- | --- |
| `@Lazy` on bean definition | Skip singleton eager pre-instantiation | This is the mechanism being studied |
| XML `lazy-init="true"` | Skip eager singleton creation for XML bean | Equivalent mechanism in XML |
| `@Lazy` at injection point | Inject lazy-resolution proxy | Complementary, not identical to target definition |
| `ObjectProvider<T>` | Lookup when consumer calls provider API | Choice for dynamic/optional lookup |
| `@Scope("prototype")` | Create object on each lookup | Different scope, not just timing |
| `@DependsOn` | Enforce prerequisite initialization order | Usually causes earlier init |
| `DeferredImportSelector` | Defer **parse/import selection** in configuration processing | Does not directly defer bean instantiation |
| `@Bean(bootstrap=BACKGROUND)` in Spring 6.2 | Support initialization on a background thread during startup | Different from lazy, has its own interactions |
| `@Async` | Execute method invocation asynchronously via proxy/executor | Does not control bean pre-instantiation |
| Application event listener | React to lifecycle/events | Not a default way to defer beans |
| Request/session scope | Define object lifecycle by web scope | Different from lazy flag |

### 18.1. DeferredImportSelector Is Not @Lazy

`DeferredImportSelector` controls **when an imported config class is selected** while Spring analyzes metadata, whereas `@Lazy` controls **bean instance creation**. A deferred imported configuration can still contain eagerly instantiated singletons.

### 18.2. Background Initialization in Spring Framework 6.2

Spring Framework 6.2 has a `@Bean(bootstrap=BACKGROUND)` option for background initialization of certain beans. This is a mechanism to **perform creation on a background thread during startup**, rather than merely deferring until first lookup; dependencies and awaiting results have their own rules. Only use it after reviewing the documentation/version capabilities and managing the executor/lifecycle properly.

Do not turn on background bootstrap simply because a bean starts up slowly without first identifying the root cause and thread safety.

## 19. Common Mistakes

### Mistake 1 — Putting @Lazy Yet the Bean Still Creates at Startup

Usually because a non-lazy singleton requires it via constructor, method parameter, field, or `depends-on`. Inspect the dependency graph.

### Mistake 2 — Thinking @Lazy on a Bean Definition Automatically Injects a Proxy

No. A lazy target bean does not mean the consumer receives a proxy. With an eager consumer and a direct dependency, the container can still create the target right away. To get a proxy, place `@Lazy` at the appropriate injection point.

### Mistake 3 — Assuming @Lazy at the Injection Point Always Leaves the Target Uncreated

If the target definition is still eager or looked up by another bean, the target may already have been created during refresh. Check both the bean definition lazy flag and the dependency graph.

### Mistake 4 — Failing to Register @Component So @Lazy Has No Effect

The annotation does not create a bean on its own. You need component scan/`@Import`/Java `@Bean`, or programmatic registration.

### Mistake 5 — Writing lazy-init="true" on a Prototype-Scoped Bean

Prototypes are not pre-instantiated like singletons anyway. The flag usually does not bring the same optimization meaning as on singletons; understand scope when measuring.

### Mistake 6 — Enabling default-lazy-init System-Wide Without Warm-Up

Can make startup look better while making the first request very slow; resource errors also surface late. Keep critical beans eager or perform dedicated warm-up.

### Mistake 7 — Calling getBean in Tests/Bootstrapping and Concluding Spring Is Not Lazy

`getBean` is a request to create/lookup the target. If called in a startup hook/test setup, you have triggered the lazy bean. To measure right after refresh, use constructor counters or `containsSingleton` appropriately before lookup.

### Mistake 8 — Confusing containsBean with an Already Created Instance

`context.containsBean("lazyClient")` can be true because the definition exists even though the target instance has not been created. Do not use `containsBean` as a measure of constructor execution.

### Mistake 9 — Configuring @Lazy(false) Yet Creation Still Happens Late

Check scope, configuration registration, outer lazy lifecycle, or whether the actual target is a different bean. `@Lazy(false)` relates to eager singleton pre-instantiation in bean factories that support startup pre-instantiation; it does not force a prototype into a singleton.

### Mistake 10 — Lazy Proxy Failing on a final Class

A lazy-resolution proxy may need to create a subclass if the injection type is not an interface. Final types/final methods, visibility, or module boundaries can make the proxy unusable. Prefer an interface or `ObjectProvider<T>` depending on the case.

### Mistake 11 — Using a @Lazy Proxy to Check Optional Dependencies

A proxy can still be injected even if the target does not exist, with failure occurring only when invoking a method. For optional targets, use `ObjectProvider.getIfAvailable()` or an explicit nullable/conditional contract.

### Mistake 12 — Reading println in Constructors Without Understanding Contexts

Two independent ApplicationContexts have separate singleton caches; if both start up, each context can create its own corresponding bean. Do not infer "JVM-wide singleton".

### Mistake 13 — Lazy Bean Has @PostConstruct Yet Callback Does Not Run at Startup

That is expected behavior if the target has not been created yet. The callback executes when the bean is initialized, given proper annotation processing.

### Mistake 14 — Calling a Method on the Proxy Just for Logging

A method invocation can trigger target resolution. To observe state, use metrics/counters or BeanFactory metadata APIs appropriately, avoiding changing timing through the act of measuring.

### Mistake 15 — Deferring Critical Resources Causing Misleading Readiness

Health checks may return UP while a bean only used upon request cannot connect to the database/remote service. If the service cannot function without the resource, consider eager creation/validation or adding genuine readiness checks.

### Mistake 16 — Assuming Lazy Always Saves Long-Term Memory

Lazy only avoids creating a bean while it is **unused**. Once used, the singleton remains alive and occupies memory until context close. It can reduce startup memory without necessarily reducing steady-state heap.

### Mistake 17 — Using @DependsOn to "Fix" Lazy

`@DependsOn` forces the dependency to initialize earlier, often causing the lazy target to be created even sooner. Use it only to express genuine initialization prerequisites.

### Mistake 18 — Confusing Spring Boot Properties with Core XML

`spring.main.lazy-initialization` is a Boot feature. Plain XML configuration still uses `lazy-init`, or Java `@Lazy`/custom registry APIs.

### Mistake 19 — Mistaking @Lazy for Asynchronous Startup

`@Lazy` does not create background threads; it defers instantiation until needed. `@Async`/background init are different mechanisms.

### Mistake 20 — Neglecting to Test Dependency Errors Until First Use

A lazy bean can fail due to a missing class, wrong password, constructor exception, unresolved property, or unavailable resource when called for the first time. Integration tests/health checks should actively exercise critical paths.

## 20. Debugging Whether a Bean Is Truly Lazy

### 20.1. Inspect Metadata Without Creating an Instance

With `AnnotationConfigApplicationContext` or a `ConfigurableApplicationContext` with an accessible BeanFactory:

```java
var factory = context.getBeanFactory();
var definition = factory.getBeanDefinition("javaLazy");

System.out.println("lazy-flag=" + definition.isLazyInit());
System.out.println("created=" + factory.containsSingleton("javaLazy"));
```

This snippet uses the `JavaBasicConfig` Java context from the demo project. `isLazyInit()` reports the BeanDefinition lazy flag. `containsSingleton(name)` observes whether a singleton instance is in the cache, without calling `getBean`. Both provide helpful debugging info, though with `FactoryBean`, aliases, and special scopes you must distinguish factory cache vs product bean semantics.

### 20.2. Do Not Use getBean to Check "Not Yet Created"

```java
context.getBean("javaLazy");
```

**This operation itself is a bean creation/lookup request.** If the target does not yet exist, it can be created immediately. The demo program deliberately reads counters **before** this call.

### 20.3. Inspection Sequence

1. Is the bean name registered?
2. Is the scope singleton, prototype, or custom?
3. Is the BeanDefinition lazy flag set properly?
4. Was the bean looked up before measuring?
5. Does any non-lazy singleton or post-processor require the target?
6. Is there a required `@DependsOn`/`depends-on`/constructor dependency?
7. Is an injection-point proxy enabled?
8. Does the configuration class carry `@Lazy` while the method has `@Lazy(false)`?
9. Are framework-specific startup policies/Boot global lazy options active?
10. Can constructor/initialization callbacks be measured clearly in an integration test?

### 20.4. Inspecting the First Request

If a lazy bean holds an expensive client, separately measure timing for:

- overall app startup;
- the lazy target creation step;
- the first business call;
- subsequent business calls;
- memory/threads after warm-up;
- behavior under concurrent first use.

A configuration that shortens startup while dramatically increasing first-request tail latency may not meet operational requirements.

## 21. Extended Practice

### Exercise 1 — Try Java @Lazy(false)

Put `@Lazy` on the `JavaBasicConfig` class, then add `@Lazy(false)` to the `javaEager()` method. Re-run. Explain why `JavaEager` is still pre-instantiated while `JavaLazy` is deferred.

### Exercise 2 — Remove lazy-init in XML

Change `xmlLazy` to `lazy-init="false"` in `xml-lazy.xml`. Expect `xml.lazy.after-refresh=1`; `xml.lazy.after-get` remains 1 due to singleton reuse.

### Exercise 3 — XML default-lazy-init

In `xml-default-lazy.xml`, remove `lazy-init="false"` on `xmlOverrideEager`. Expect `xml.override.after-refresh=0`. Then call `getBean(XmlOverrideEager.class)` and verify the constructor counter increments to 1.

### Exercise 4 — Directly Inject into an Eager Consumer

In `ProxyConfig`, remove `@Lazy` from the parameter of `jobConsumer(...)` while keeping `@Lazy` on `jobWorker()`. Predict `proxy.target.after-refresh=1` because the eager consumer requires the real target. This is a key exercise for distinguishing a lazy target from a lazy injection point.

### Exercise 5 — Change JobWorker to a Concrete final Class

Change the `JobConsumer` constructor to take a concrete `RealWorker` declared `final` and put `@Lazy` on the parameter. Consider why a class-based proxy may fail to be created, and try switching to the `JobWorker` interface or `ObjectProvider<RealWorker>`. Do not use `final` types by default when designing targets that require proxying.

### Exercise 6 — Use ObjectProvider

Change `JobConsumer` to accept `ObjectProvider<JobWorker>`. Call `getObject().work()` inside `run()`, observing target creation timing. Try `getIfAvailable()` for an optional target to understand semantics when the bean does not exist.

### Exercise 7 — Measure Readiness

Add a critical bean simulating startup configuration validation and an optional bean with expensive initialization. Decide which bean must be eager to fail fast and which can be lazy, then write an integration test confirming failures occur at the intended time.

### Exercise 8 — Prototype

Change `jobWorker` to prototype while still using a proxy or ObjectProvider. Track the number of constructor calls across multiple uses. Distinguish the lifetime of the singleton proxy/consumer from the scoped target instances.

## 22. Review Questions with Answers

**Question 1.** By default, which beans does `ApplicationContext` typically create right during startup?

**Answer:** Regular non-lazy singletons; special scopes and infrastructure follow their own rules.

**Question 2.** Does `@Lazy` on a `@Bean` method create the bean on another thread?

**Answer:** No. It defers pre-instantiation until the bean is actually requested.

**Question 3.** Is `lazy-init="true"` an XML attribute of the Java class itself?

**Answer:** No. It is metadata on the XML `<bean>` processed by Spring's BeanFactory.

**Question 4.** If a `@Lazy` bean is still created during refresh, is Spring malfunctioning?

**Answer:** No. If an eager singleton needs that bean as a dependency, Spring must create the target to satisfy the dependency.

**Question 5.** How does `@Lazy` at an injection point differ from `@Lazy` on a bean definition?

**Answer:** Injection-point `@Lazy` creates a lazy-resolution proxy; bean-definition `@Lazy` prevents normal singleton pre-instantiation. To defer the target when the consumer is eager, both may be needed.

**Question 6.** How does `@Lazy` on `@Configuration` affect `@Bean` methods?

**Answer:** It sets the lazy default for `@Bean` methods in the class; a `@Lazy(false)` method can override it.

**Question 7.** Does `<beans default-lazy-init="true">` make every bean in the JVM lazy?

**Answer:** No. It sets the default for definitions parsed within that XML resource; other registration sources have their own metadata.

**Question 8.** Does a lazy singleton become a prototype?

**Answer:** No. Once created, the singleton is still reused within the container.

**Question 9.** Why can `containsBean("lazy")` be true when the constructor has not run yet?

**Answer:** The bean definition is registered, while the instance has not needed to be created yet.

**Question 10.** Why is a lazy proxy unsuitable for checking optional dependencies with `!= null`?

**Answer:** A proxy can be injected even if the target is absent; errors occur on invocation. Use `ObjectProvider.getIfAvailable()` when explicit optional semantics are needed.

**Question 11.** Does `@DependsOn` generally make a lazy bean be created later?

**Answer:** No. It forces the dependency to initialize before the dependent bean, so it can pull a lazy bean into startup.

**Question 12.** If a bean has never been created, does Spring invoke destroy callbacks on a target instance?

**Answer:** There is no target instance to destroy. If a lazy singleton was created and is managed, the appropriate callback can run when the context closes.

**Question 13.** Does `spring.main.lazy-initialization=true` work in a project that only has `spring-context`?

**Answer:** Not automatically. That property is processed by Spring Boot.

**Question 14.** Does DeferredImportSelector mean the same thing as @Lazy?

**Answer:** No. DeferredImportSelector relates to import selection during configuration parsing; `@Lazy` relates to bean instantiation.

**Question 15.** What operational impacts can enabling global lazy cause?

**Answer:** It can reduce some startup work, but defers errors, increases first-use latency, alters readiness assessment, and affects memory footprint after warm-up.

## 23. Practical Implementation Checklist

- [ ] Identify which beans are **not needed** for startup/health-critical workflows.
- [ ] For Java beans, place `@Lazy` appropriately on definitions or `@Configuration` scope.
- [ ] For XML beans, set `lazy-init="true"`; consider `default-lazy-init` and overrides.
- [ ] Check whether the target is directly required by another eager singleton.
- [ ] If an eager consumer needs a lazy dependency, consider `@Lazy` at the injection point or `ObjectProvider`.
- [ ] Use interfaces/proxy-friendly types when choosing lazy proxies.
- [ ] Do not use a lazy proxy as an optional dependency existence test.
- [ ] Check bean scope before assuming singleton identity.
- [ ] Do not assume the lazy flag guarantees nobody calls `getBean()` during startup.
- [ ] Ensure critical configuration/resources fail fast when required.
- [ ] Verify initialization/destruction lifecycle behavior with lazy targets.
- [ ] Use real integration tests to measure state **after refresh, before lookup, and after lookup**.
- [ ] Measure startup, first-use latency, and memory under realistic workloads.
- [ ] Distinguish Core `@Lazy`/XML lazy-init from Spring Boot properties, background bootstrap, and deferred parsing.

## 24. Official References

- [Spring Framework 6.2 — Lazy-initialized Beans](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-lazy-init.html): eager singleton default, `@Lazy`, `lazy-init`, `default-lazy-init`, and eager dependencies.
- [Spring Framework 6.2.19 — Lazy Javadoc](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Lazy.html): TYPE/METHOD/CONSTRUCTOR/PARAMETER/FIELD, config-class defaults, lazy-resolution proxies.
- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): `@Bean`, injection-point `@Lazy`, and `ObjectProvider`.
- [Spring Framework 6.2 — Using depends-on](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-dependson.html): initialization dependencies, destroy ordering.
- [Spring Framework 6.2 — Dependency Injection](https://docs.spring.io/spring-framework/reference/6.2/core/beans/dependencies/factory-collaborators.html): eager singleton pre-instantiation and graph injection.
- [Spring Framework 6.2 — Java Config Composition](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/composing-configuration-classes.html): `@Lazy`, `@DependsOn`, and background initialization options in Spring 6.2.
- [Spring Boot — SpringApplication Lazy Initialization](https://docs.spring.io/spring-boot/reference/features/spring-application.html): `spring.main.lazy-initialization` property, startup/first-use trade-offs.

**Summary:** Spring normally pre-instantiates **non-lazy singleton beans** during startup. `@Lazy` and XML `lazy-init="true"` defer **target bean instance creation**, but a dependency from an eager singleton can still cause the target to be created early. `@Lazy` at an **injection point** creates a lazy-resolution proxy and should be clearly distinguished from `@Lazy` on a **bean definition**. Test with lifecycles/counters, and weigh fail-fast guarantees, resources, and first-use latency before applying lazy widely.
