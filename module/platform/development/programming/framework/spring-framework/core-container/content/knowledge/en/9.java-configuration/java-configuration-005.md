# Static @Bean Methods and Container Type Detection Timing in Spring Core Container

## 1. Real-World Problem and Goals

In Spring Java configuration, a `@Bean`-annotated method is normally an **instance method**. However, Spring also supports **static `@Bean` methods**:

```java
@Configuration
class ApplicationConfig {
    @Bean
    static ServiceSettings serviceSettings() {
        return new ServiceSettings();
    }
}
```

This is a structural snippet; `ServiceSettings` is an example class that must be defined in the project, and `@Configuration` and `@Bean` must be imported. Why is `static` sometimes needed, especially with `BeanFactoryPostProcessor` and `BeanPostProcessor`? And why can the **declared return type** on the method determine whether the container detects a special bean **before instance creation**?

After this lesson, you will:

1. Distinguish **bean definition discovery**, **bean type prediction**, **bean instance creation**, and **bean processing in the context lifecycle**.
2. Explain why a static `@Bean` can be invoked **without instantiating the `@Configuration` class**.
3. Know when Spring recommends static `@Bean` for `BeanFactoryPostProcessor` (BFPP) and `BeanPostProcessor` (BPP), and the consequences of using instance methods for those special beans.
4. Explain why factory methods must declare a sufficiently specific return type, especially for `BeanPostProcessor`, `BeanFactoryPostProcessor`, or `FactoryBean<T>`.
5. Understand that **static does not mean eager**, **static does not mean JVM-wide singleton**, and direct calls to a static factory method are **not intercepted by Spring**.
6. Write, run, and verify a Spring Framework 6.2 / Java 17+ example showing the container recognizing metadata, creating processors early, and creating business objects later.

## 2. Separating Four Milestones in the Container Lifecycle

When reading `@Bean`, avoid lumping everything together into "Spring sees the bean". There are at least four distinct events:

| Milestone | What does Spring need to do? | Must the target object already be created? |
| --- | --- | --- |
| **1. Configuration recognition** | Process `@Configuration`, `@Bean`, `@Import`, or other registration mechanisms. | Not yet. |
| **2. Bean definition registration** | Create a `BeanDefinition` holding name, factory method, scope, and data supporting type prediction. | Not yet. |
| **3. Bean type prediction** | Determine whether the bean is a `BeanFactoryPostProcessor`, `BeanPostProcessor`, a type needed for autowiring, etc. | Usually possible from metadata/return type; sometimes cannot be determined early. |
| **4. Instance creation** | Invoke the static/instance factory method, inject dependencies, run init callbacks/post-processing. | Yes, when the target is actually required. |

Example:

```java
@Bean
static Formatter formatter() {
    return new Formatter();
}
```

When the configuration is parsed, Spring knows there is a bean produced by `formatter` whose declared return type is `Formatter`. That **does not require `formatter()` to run immediately when reading the annotation**. If this is an ordinary non-lazy singleton, Spring typically creates the instance during the pre-instantiation phase at the end of refresh; if `@Lazy`, it may be later.

Overall diagram:

```text
Register @Configuration
         |
         v
ConfigurationClassPostProcessor analyzes @Bean
         |
         v
BeanDefinition has factory method + return type
         |
         +--> early type inspection
         |       +--> is bean a BFPP / BPP?
         |       +--> resolve dependencies by type?
         |
         v
Container decides instantiation timing
         |
         +--> invoke static factory directly
         |       (no @Configuration instance needed)
         |
         +--> or invoke instance factory on @Configuration bean
                 (requires suitable configuration instance)
         |
         v
Apply lifecycle / BeanPostProcessor / scope
```

Key point: **Spring may need to know the type much earlier than instance creation**, especially when identifying processors that participate in starting up the container.

## 3. How an Ordinary @Bean Is Invoked

Consider an instance factory method:

```java
@Configuration
class JavaConfig {
    @Bean
    MessageCatalog messageCatalog() {
        return new MessageCatalog("hello");
    }
}
```

`MessageCatalog` is an example class. Spring registers this method as the bean's creation source and normally needs a `JavaConfig` instance to call `messageCatalog()`.

Conversely:

```java
@Configuration
class JavaConfig {
    @Bean
    static MessageCatalog messageCatalog() {
        return new MessageCatalog("hello");
    }
}
```

This is a **static factory method**; Spring can call `JavaConfig.messageCatalog()` without instantiating `JavaConfig` just to run that factory method.

Several important details:

- Both still create a **Spring bean** with a container-managed name, scope, and lifecycle.
- Both can be recognized by Spring at the **bean definition stage**, before the method runs.
- `static` only governs **how the Java method is invoked** and the dependency on a configuration class instance; it does not alter the default scope.
- A static method can receive **Spring-injected parameters** just like other `@Bean` factory methods. For BFPP/BPP, still minimize dependencies to avoid pulling in business beans too early.
- A static `@Bean` method is not overridden by CGLIB, so it cannot receive direct-call interception semantics of instance `@Bean` methods in full `@Configuration`.

## 4. BeanFactoryPostProcessor Needs to Be Created Early

`BeanFactoryPostProcessor` is an extension point for reading or modifying **bean definition metadata** before the container creates most application beans.

```java
import org.springframework.beans.factory.config.BeanFactoryPostProcessor;

public final class DefinitionInspector implements BeanFactoryPostProcessor {
    @Override
    public void postProcessBeanFactory(
            org.springframework.beans.factory.config.ConfigurableListableBeanFactory factory) {
        System.out.println(factory.containsBeanDefinition("myService"));
    }
}
```

This `DefinitionInspector` class compiles with `spring-beans` on the classpath. The callback body only inspects a bean name and does not instantiate a service bean.

Because a BFPP must run in a **very early phase**, Spring has to find it **before ordinary business singletons are created**. If a BFPP is declared using an instance `@Bean`:

```java
@Configuration
class InfrastructureConfig {
    @Bean
    BeanFactoryPostProcessor definitionInspector() {
        return beanFactory -> {
            // Intervene in BeanDefinition at startup.
        };
    }
}
```

then to create the BFPP, Spring may have to **instantiate `InfrastructureConfig` early** before all annotation injection/lifecycle mechanisms are ready. This can affect `@Autowired`, `@Value`, and `@PostConstruct` located directly on that configuration class or its dependencies.

**Usually preferred approach:**

```java
@Configuration
class InfrastructureConfig {
    @Bean
    static BeanFactoryPostProcessor definitionInspector() {
        return beanFactory -> {
            // Intervene in BeanDefinition at startup.
        };
    }
}
```

Here the factory method is **static**, so Spring can create the BFPP without building an `InfrastructureConfig` instance. This style is especially useful when the configuration also contains business factory methods processed at the normal stage.

Spring 6.2 `@Bean` Javadoc explicitly states that `@Bean` methods returning `BeanFactoryPostProcessor` should be declared static; non-static configurations can emit INFO messages about lifecycle risks.

### 4.1. Why avoid reading @Autowired in @Configuration constructors too early?

An unsafe pattern is having a configuration class constructor or field depend on a business bean, while a BFPP factory method needs the configuration instance to run.

```java
@Configuration
class RiskyConfig {
    @Autowired
    private SomeApplicationService service;

    @Bean
    BeanFactoryPostProcessor earlyProcessor() {
        return factory -> {
            // Easily triggers circular dependency / overly early initialization.
        };
    }
}
```

This is an illustrative snippet: `SomeApplicationService` is a hypothetical type. The problem is not merely whether `@Autowired` is present; the **phase** in which `RiskyConfig` is created may be too early relative to when annotation processors are ready. A static BFPP method reduces the need to instantiate the configuration early.

However, if a static factory method declares a heavy business service as a parameter dependency, resolving that parameter can still instantiate the service early. `static` does not automatically shield against every initialization side effect.

## 5. BeanPostProcessor Also Needs Detection Before Ordinary Beans

`BeanPostProcessor` (BPP) processes **bean instances** during their lifecycle: e.g., inspecting markers, injecting/handling lifecycle metadata, or wrapping objects with proxies.

A BPP must be registered **before the beans it is meant to process are created**. Thus Spring must have a mechanism to **detect which beans are BPPs based on type metadata**.

An appropriate declaration:

```java
@Configuration
class ProcessingConfig {
    @Bean
    static BeanPostProcessor auditProcessor() {
        return new BeanPostProcessor() {
            @Override
            public Object postProcessAfterInitialization(
                    Object bean, String name) {
                return bean;
            }
        };
    }
}
```

This snippet requires importing `org.springframework.beans.factory.config.BeanPostProcessor`, `Bean`, and `Configuration`. The static factory avoids creating the configuration instance prematurely.

**Two important rules, per Spring 6.2 Javadoc:**

1. **Return a type that clearly reveals BPP nature**: the `BeanPostProcessor` interface or a concrete implementation of it, rather than hiding behind `Object` or an unrelated interface.
2. **Mark the factory method `static`**, ideally **with no application-bean dependencies**, to avoid pulling other beans into the post-processor registration phase.

If a BPP is created too late, beans instantiated earlier may **miss processing by all post-processors**, especially auto-proxying. Spring may log a warning like "not eligible for getting processed by all BeanPostProcessors".

### 5.1. Declaring the wrong return type loses early detection

Counter-example:

```java
@Bean
static Object auditProcessor() {
    return new MyAuditBeanPostProcessor();
}
```

`MyAuditBeanPostProcessor` is a hypothetical implementation of `BeanPostProcessor`. Because the declared return type is only `Object`, the container **cannot always determine before instantiation** that this bean is a BPP. Spring has some additional type-prediction techniques, yet you must never rely on accidental inference for critical infrastructure to run in the right phase.

Write instead:

```java
@Bean
static BeanPostProcessor auditProcessor() {
    return new MyAuditBeanPostProcessor();
}
```

or declare the `MyAuditBeanPostProcessor` class itself if exposing that concrete type is appropriate.

The same applies to BFPP: declare `BeanFactoryPostProcessor` or a concrete implementation in the method signature. A factory method returning `Object` that actually constructs a BFPP obscures early type information.

### 5.2. Static @Bean and BeanPostProcessor are not mandatory for every bean

For example, a simple object:

```java
@Bean
static Clock clock() {
    return Clock.systemUTC();
}
```

This snippet is valid once `java.time.Clock` is imported, yet using `static` here does not bring the same lifecycle benefit as with BFPP/BPP. Most business beans can be declared as instance `@Bean` methods with parameter injection. **There is no need to turn every `@Bean` into static**.

## 6. Complete Java 17+ Example: Observing Early Type vs. Late Instance

We use **Spring Framework 6.2.9** with `AnnotationConfigApplicationContext`, needing no Spring Boot or server. The example includes:

- A **static `@Bean BeanFactoryPostProcessor`** printing observations during the metadata processing phase.
- A **static `@Bean BeanPostProcessor`** tracking a business bean after initialization.
- A **static `@Bean Catalog`** as a regular bean.
- An **instance `@Bean Gateway`** receiving `Catalog` via a factory method parameter.
- A constructor on `Config` counting how many times the configuration instance is created.
- A direct Java call to the static factory to demonstrate it is **not a container lookup**.

### 6.1. Project structure

```text
static-bean-demo/
├── settings.gradle
├── build.gradle
└── src/
    └── main/
        └── java/
            └── demo/
                └── StaticBeanDemo.java
```

**`settings.gradle`**

```groovy
rootProject.name = 'static-bean-demo'
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
    implementation 'org.springframework:spring-context:6.2.9'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

application {
    mainClass = 'demo.StaticBeanDemo'
}
```

**`src/main/java/demo/StaticBeanDemo.java`**

```java
package demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.config.BeanFactoryPostProcessor;
import org.springframework.beans.factory.config.BeanPostProcessor;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class StaticBeanDemo {

    public static final class Catalog {
        private final String value;

        public Catalog(String value) {
            this.value = value;
        }

        public String value() {
            return value;
        }
    }

    public static final class Gateway {
        private final Catalog catalog;

        public Gateway(Catalog catalog) {
            this.catalog = catalog;
        }

        public String message() {
            return catalog.value() + "-gateway";
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {
        private static final AtomicInteger CREATED = new AtomicInteger();
        private static final AtomicInteger GATEWAYS_SEEN =
                new AtomicInteger();

        public Config() {
            CREATED.incrementAndGet();
        }

        // BFPP must be recognized and created during the metadata phase.
        @Bean
        static BeanFactoryPostProcessor earlyInspector() {
            return factory -> {
                System.out.println("early:config-count="
                        + CREATED.get());
                System.out.println("early:catalog-definition="
                        + factory.containsBeanDefinition("catalog"));
                System.out.println("early:catalog-type="
                        + factory.getType("catalog").getSimpleName());
                System.out.println("early:catalog-instantiated="
                        + factory.containsSingleton("catalog"));
            };
        }

        // Return type helps Spring recognize the BPP before creating Gateway.
        @Bean
        static BeanPostProcessor observer() {
            return new BeanPostProcessor() {
                @Override
                public Object postProcessAfterInitialization(
                        Object bean, String beanName) {
                    if ("gateway".equals(beanName)) {
                        GATEWAYS_SEEN.incrementAndGet();
                    }
                    return bean;
                }
            };
        }

        // Ordinary objects can also be created from static @Bean.
        @Bean
        static Catalog catalog() {
            return new Catalog("demo");
        }

        // Instance factory method; dependency is injected via parameter.
        @Bean
        Gateway gateway(Catalog catalog) {
            return new Gateway(catalog);
        }
    }

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            Catalog first = context.getBean(Catalog.class);
            Catalog second = context.getBean(Catalog.class);
            Gateway gateway = context.getBean(Gateway.class);

            System.out.println("context-ready");
            System.out.println("config-count=" + Config.CREATED.get());
            System.out.println("gateway=" + gateway.message());
            System.out.println("bpp-saw-gateway="
                    + (Config.GATEWAYS_SEEN.get() == 1));
            System.out.println("managed-catalog-same=" + (first == second));

            Catalog direct = Config.catalog();
            System.out.println("direct-call-is-managed=" + (direct == first));
        }
    }
}
```

The program places `Config` as a static nested class so Spring can register it cleanly. `Config.CREATED` increments only when a **`Config` instance** is created; invoking the static factories `earlyInspector()`, `observer()`, or `catalog()` does not increment the counter.

### 6.2. Run

From the `static-bean-demo` directory:

```bash
gradle run --quiet
```

If the project has the Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows. Running `javac StaticBeanDemo.java` alone is insufficient without providing Spring JARs on the classpath; the Gradle task handles dependencies and classpath.

**`System.out.println` lines from the program:**

```text
early:config-count=0
early:catalog-definition=true
early:catalog-type=Catalog
early:catalog-instantiated=false
context-ready
config-count=1
gateway=demo-gateway
bpp-saw-gateway=true
managed-catalog-same=true
direct-call-is-managed=false
```

The program spawns no separate logging threads; Gradle or logging framework output may appear depending on environment configuration, separate from the ten lines above.

### 6.3. Explaining the output lines

**`early:config-count=0`.** The container creates `earlyInspector` from a **static `@Bean`** without needing to instantiate `Config`. Because the BFPP runs in an early phase, the `Config()` constructor call count is still 0.

**`early:catalog-definition=true`.** Metadata for `@Bean Catalog catalog()` has already been registered as a bean definition when the BFPP inspects the registry. **Registering a definition does not mean the target has been instantiated.**

**`early:catalog-type=Catalog`.** Spring can predict the bean type from the static factory method signature `static Catalog catalog()`. `getType("catalog")` returns the predicted type **without invoking the factory method to construct `Catalog`**.

**`early:catalog-instantiated=false`.** At that point `catalog` does not yet exist in the singleton cache. This cleanly separates **type visibility** from **instance availability**.

**`config-count=1`.** During refresh, the container instantiates `Config` to invoke the instance factory method `gateway(Catalog)`. Static `@Bean` methods were able to serve early needs without pulling in the configuration instance.

**`bpp-saw-gateway=true`.** BeanPostProcessor `observer` was already created/registered before the `gateway` bean completed initialization, so `postProcessAfterInitialization` receives `gateway` exactly once in the example.

**`managed-catalog-same=true`.** `catalog` is a default singleton bean; two `getBean` calls return the same instance in the context.

**`direct-call-is-managed=false`.** `Config.catalog()` is a **direct static Java call**, creating a new object outside the Spring container. Static `@Bean` methods are not intercepted by CGLIB; only invocations orchestrated by the bean factory are subject to scope and lifecycle management.

> The output illustrates two distinct axes: **knowing the bean type** does not mean **having created the object**, and a **static factory method** does not mean every Java call to that method is container-managed.

## 7. Why Must the Return Type "Expose" the Right Type to Spring?

Consider a factory method:

```java
@Bean
static Object earlyProcessor() {
    return new MySpecialBeanPostProcessor();
}
```

`MySpecialBeanPostProcessor` is an example class implementing `BeanPostProcessor`. Looking at metadata, the container only knows for sure that the minimal return type is `Object`. Before the actual instance exists, Spring may **not yet know** it is a BPP that must be registered ahead of other beans.

Change the signature:

```java
@Bean
static BeanPostProcessor earlyProcessor() {
    return new MySpecialBeanPostProcessor();
}
```

and the container has declared proof that the bean is of type `BeanPostProcessor`. When Spring searches for BPPs early, the bean definition is much more reliably recognized at the right moment.

**This rule applies more broadly than BPP/BFPP:**

```java
@Bean
PaymentGateway gateway() {
    return new DefaultPaymentGateway();
}
```

If code injects `PaymentGateway` into other beans, the declared type is sufficient. Yet if code injects `DefaultPaymentGateway` before the bean is created and the method only declares `PaymentGateway`, Spring may not know the concrete type during **type prediction**. Some candidates only become clear once the singleton has actually been created; autowiring outcomes can then depend on timing and initialization order.

Therefore, Spring recommends declaring factory method return types **at least as specific as injection points truly need**. You do not always need to declare a concrete class if the system consistently uses interfaces; however, avoid `Object` for important beans and avoid obscuring extension point types that the container must find early.

### 7.1. The FactoryBean<T> case vs. @Bean factory methods

Two similar-sounding names are easy to confuse:

- **`@Bean` factory method:** a method that creates a Spring bean object.
- **`FactoryBean<T>`:** a special interface whose implementation produces a **product object** when the container looks up the bean; to obtain the factory itself, use the `&` prefix on the bean name.

Suppose:

```java
@Bean
FactoryBean<MyClient> myClientFactoryBean() {
    return new MyClientFactoryBean();
}
```

This is a structural snippet assuming `MyClientFactoryBean implements FactoryBean<MyClient>` and `MyClient` is a business class.

The container can use generic information `FactoryBean<MyClient>` and the factory's `getObjectType()` to deduce the type of the **product bean**. If the `@Bean` return type is only raw `FactoryBean` or `Object`, type prediction can be harder. In some cases, determining a `FactoryBean`'s object type also depends on metadata/how `getObjectType()` is implemented, and Spring may have to distinguish non-eager lookups (`allowEagerInit=false`) from lookups permitted to instantiate factories.

**Point to remember:** this is an additional type-prediction layer, not a guarantee that `@Bean static` automatically makes every product type known early.

## 8. static Does Not Automatically Make a Bean Eager or a JVM Singleton

All three statements below are false:

1. "A `@Bean static` method runs as soon as the class is loaded."
2. "A static `@Bean` is always invoked only once across the entire JVM."
3. "A static `@Bean` cannot create prototypes."

### 8.1. Bean definition differs from class initialization

Java loads classes and executes static initializers according to JVM rules, whereas Spring has its own bean lifecycle. `@Bean static` does not mean Spring invokes that method when the JVM loads the class.

A static initializer:

```java
static {
    System.out.println("java-class-init");
}
```

is a Java mechanism completely separate from Spring calling a `@Bean`-annotated method during bean instantiation. Do not use static initializers as an indirect substitute for BeanFactory lifecycle logic.

### 8.2. Scope is still decided by the bean definition

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
static TaskToken taskToken() {
    return new TaskToken();
}
```

This is an illustrative snippet: `TaskToken` is an example class requiring `Scope` and `ConfigurableBeanFactory` imports. The container can invoke the static factory **each time a new prototype is needed**. Conversely, a singleton static `@Bean` is created by the container per the singleton policy of **one context**, not as a JVM-global static variable.

**Important:** if code outside Spring calls `Config.taskToken()` directly, that Java call does not obey bean-scope lookup; it executes the factory method directly.

### 8.3. @Lazy still applies to singletons

```java
@Bean
@Lazy
static HeavyClient heavyClient() {
    return new HeavyClient();
}
```

`HeavyClient` is an illustrative type. For a lazy singleton, the container can defer executing the method until the bean is requested. Being static does not force the bean to be created at refresh. If another eager bean depends on `HeavyClient`, Spring may still need to create the client early to satisfy that dependency.

BFPP/BPP are **special cases** that need early creation to intervene in the lifecycle; they are unlike ordinary business singletons.

## 9. Does static @Bean Receive Inter-Bean Method Interception?

In full `@Configuration(proxyBeanMethods=true)`, Spring can use a CGLIB subclass to intercept calls between **instance** `@Bean` methods, enforcing container-lookup semantics for those calls.

However, **Java static methods cannot be overridden by a subclass**, so static `@Bean` methods are **not intercepted**, even when the configuration class has `proxyBeanMethods=true`.

Example:

```java
@Configuration
class CatalogConfig {
    @Bean
    static Catalog catalog() {
        return new Catalog("demo");
    }

    @Bean
    Gateway gateway() {
        return new Gateway(catalog()); // Direct Java call.
    }
}
```

`Catalog`/`Gateway` are the two classes from the runnable example in section 6. `gateway()` calls static `catalog()` and can create a new object, **not obtaining the managed singleton bean**. Enabling enhancement for instance methods of `CatalogConfig` cannot change the static nature of `catalog()`.

**The right way to wire beans:**

```java
@Configuration(proxyBeanMethods = false)
class CatalogConfig {
    @Bean
    static Catalog catalog() {
        return new Catalog("demo");
    }

    @Bean
    Gateway gateway(Catalog catalog) {
        return new Gateway(catalog);
    }
}
```

Spring resolves `Catalog` in the parameter according to bean definition and scope. This works cleanly for both static and instance `@Bean` methods, reducing dependence on proxy/configuration enhancement.

### 9.1. @Configuration(proxyBeanMethods=false) and @Component lite mode

When `@Configuration(proxyBeanMethods=false)`, even **instance** calls between `@Bean` methods have ordinary Java semantics rather than CGLIB interception as in full mode.

`@Bean` methods placed in `@Component` classes (not full `@Configuration`) are also typically processed in **lite mode** and do not receive full-configuration interception. Thus the habit of using **factory method parameters** is better than relying on calling other methods directly.

### 9.2. Do not confuse static @Bean with a stateful static field

`@Bean static Catalog catalog()` is a **static method**. It does not require a static field holding the `Catalog` singleton. Spring can manage multiple `ApplicationContext`s in one JVM and create a distinct `catalog` singleton per context; using a mutable static field to cache an object globally is a separate mechanism prone to state leaks and test contamination.

## 10. Two Common Startup Bugs Related to Return Type and Early Initialization

### 10.1. BPP hidden behind Object

```java
@Bean
static Object metricsBean() {
    return new MetricsBeanPostProcessor();
}
```

If `MetricsBeanPostProcessor` implements `BeanPostProcessor` yet the method declares only `Object`, Spring's type-based search for BPPs can miss the bean before it is instantiated.

**Fix:**

```java
@Bean
static BeanPostProcessor metricsBean() {
    return new MetricsBeanPostProcessor();
}
```

These are illustrative snippets; the implementation must be defined. Spring docs recommend declaring the return type as the concrete implementation or at least the `BeanPostProcessor` interface so early type detection works reliably.

### 10.2. Non-static @Bean creating a BPP forces early @Configuration creation

```java
@Configuration
class RiskyConfig {
    @Autowired
    SomeApplicationService service;

    @Bean
    BeanPostProcessor processor() {
        return new CustomProcessor();
    }
}
```

`SomeApplicationService` and `CustomProcessor` are illustrative types. To construct the BPP via an instance method, Spring must create `RiskyConfig` first, which can pull in the application service early. That bean may **fail to be processed by all post-processors**, and Spring may log a WARN saying the bean is "not eligible for getting processed by all BeanPostProcessors".

**Fix:**

```java
@Configuration
class SaferConfig {
    @Bean
    static BeanPostProcessor processor() {
        return new CustomProcessor();
    }
}
```

And do not inject heavy application beans into the processor itself unless necessary.

**Do not misunderstand:** making a method static does not guarantee every misconfiguration is instantly fixed. If a custom processor still actively calls `getBean("service")` in its constructor/initialization, it can still instantiate the service prematurely.

## 11. Early Type Detection Differs from "Pre-Creation" and "Pre-Injection"

To predict accurately, distinguish three APIs/capabilities:

- `BeanFactory.getType(beanName)`: attempts to determine the type of the bean returned on lookup, using metadata, factory methods, or `FactoryBean` mechanisms. Some types cannot be determined reliably before the instance exists.
- `BeanFactory.containsBeanDefinition(beanName)`: reports whether a definition is directly registered in the current bean factory; **does not mean the instance has been created**.
- `SingletonBeanRegistry.containsSingleton(beanName)`: checks the current singleton cache; **does not check bean definitions**.

In the runnable example, the startup output:

```text
early:catalog-definition=true
early:catalog-type=Catalog
early:catalog-instantiated=false
```

is completely consistent. Spring knows how to create `Catalog` and predicts its type, yet has not created the instance. If an injection point needs `Catalog` during an early phase, resolving that dependency can trigger bean creation and flip the third state to true.

### 11.1. Overly broad return type

Suppose:

```java
@Bean
PaymentProcessor paymentProcessor() {
    return new StripePaymentProcessor();
}
```

`PaymentProcessor` and `StripePaymentProcessor` are hypothetical business types. Metadata guarantees the bean at least satisfies the `PaymentProcessor` interface. Before the factory method executes, the container does not always know the concrete implementation to match an injection point requiring `StripePaymentProcessor`.

If Spring must determine candidates before the singleton is created, a component injecting the concrete type might not be selected. Conversely, once the singleton is instantiated, the runtime type may become known and lead to a different matching outcome. Hence:

- If consumers only need the interface, injecting `PaymentProcessor` and returning the interface is clean.
- If a concrete type is genuinely needed, consider returning `StripePaymentProcessor`, along with sound API design and proxying.
- For Spring extension points, you must expose the appropriate interface/concrete type (e.g., `BeanPostProcessor`), never `Object`.

### 11.2. Do not "probe" beans with early getBean() just to inspect types

A BFPP should not call `getBean()` on a business bean merely to inspect its class or properties. Doing so can trigger premature instantiation before all BPPs/advisors are registered, causing incorrect behavior or missed proxies.

Prefer reading `BeanDefinition`, `getType()`, and metadata; if determining a `FactoryBean` product type, carefully consider the right API and the side effects of eager initialization.

## 12. Declaring Post-Processors Clearly in Real Projects

For BFPP:

```java
@Configuration(proxyBeanMethods = false)
class InfrastructureConfig {

    @Bean
    static BeanFactoryPostProcessor definitionPolicy() {
        return beanFactory -> {
            // Modify registered metadata, if genuinely needed.
        };
    }
}
```

For BPP:

```java
@Configuration(proxyBeanMethods = false)
class InfrastructureConfig {

    @Bean
    static BeanPostProcessor decoratorProcessor() {
        return new MyDecoratorPostProcessor();
    }
}
```

`MyDecoratorPostProcessor` is an illustrative class that must implement `BeanPostProcessor`. The two examples are standalone configurations; in real code they can be combined if method names differ and imports are right.

**Infrastructure checklist:**

1. Method returns a concrete type or at least `BeanFactoryPostProcessor`/`BeanPostProcessor`.
2. Method should be `static` to avoid early `@Configuration` instantiation.
3. Minimize parameters that are business beans.
4. If the processor needs ordinary properties/sources, check whether it can safely use metadata/`Environment`/config values early; do not force clients/network/services to initialize before the BPP cycle completes.
5. If the processor creates proxies, verify which beans are actually eligible for proxying and the ordering of related post-processors.
6. Write an integration test building a small context and observing bean definitions, type prediction, callbacks, and key event ordering.

### When should you NOT write a custom post-processor?

Most applications do not need custom BFPP/BPPs. Spring already provides built-in infrastructure for property placeholders, autowiring, lifecycle, transactions, caching, async, and validation. Only write a new processor when you have a requirement to hook into metadata or bean instances that cannot be expressed with built-in configuration, and you understand the lifecycle well enough to avoid early-instantiation bugs.

## 13. Practicing Variations on the Example

### 13.1. Changing static Catalog to instance @Bean

In `StaticBeanDemo.Config`, replace:

```java
@Bean
static Catalog catalog() {
    return new Catalog("demo");
}
```

with:

```java
@Bean
Catalog catalog() {
    return new Catalog("demo");
}
```

The `earlyInspector` BFPP is still created from a static method and can recognize `catalog`'s return type from configuration/factory method metadata once Spring parses the configuration. However, **creating `Catalog`** now requires a `Config` instance, whereas previously it did not. This is a difference in **instantiation mechanism**, not scope rules.

Do not assume rigidly that every way of probing types on an instance factory in every variant never instantiates the configuration: the outcome can depend on type/method prediction infrastructure, how the factory bean is defined, and query timing.

### 13.2. Changing the BPP return type to Object

Change `static BeanPostProcessor observer()` to `static Object observer()`. In Java, the method still returns an instance implementing BPP, yet Spring may fail to detect this bean as a `BeanPostProcessor` during the search **before** initialization, so `bpp-saw-gateway` is no longer guaranteed evidence.

This experiment is only to observe the effect of type metadata; **never use `Object` in real applications** if you want Spring to auto-detect the processor.

### 13.3. Changing static BFPP to instance BFPP

Replace `static BeanFactoryPostProcessor earlyInspector()` with an instance method. Because Spring must invoke the method on `Config`, this can cause `Config.CREATED` to increment before the BFPP callback, making `early:config-count` non-zero and emitting lifecycle warnings. This demonstrates why the static recommendation exists; do not treat the changed output as a "Spring bug".

### 13.4. Making Catalog a prototype

Add `@Scope("prototype")` to static `@Bean Catalog catalog()`. Then each regular `context.getBean(Catalog.class)` creates a new instance, even though the method remains static. `managed-catalog-same` becomes false. For the `Gateway` singleton, the catalog injected into `gateway(Catalog)` remains **one fixed instance** resolved when `Gateway` was created; it does not change on every call to `message()`.

### 13.5. Calling the Catalog factory method directly

`main` already includes:

```java
Catalog direct = Config.catalog();
System.out.println(direct == context.getBean(Catalog.class));
```

The result is false in the demo config because the direct call creates a new object. That is a **Java call**, not a Spring bean lookup. For static methods returning a hand-rolled singleton cache, a Java call might happen to return the same object, yet that is governed by factory code and **not** guaranteed by the container.

## 14. Common Misconceptions

### Misconception 1: "static @Bean is created right at class startup"

`static` lets the method be invoked without a configuration class instance. When **Spring invokes the method** is still governed by bean lifecycle/scope/early infrastructure; `static` alone does not create eager behavior.

### Misconception 2: "Static @Bean has only one singleton across the whole JVM"

Singleton scope belongs to **each ApplicationContext**, not the static Java class. Two separate contexts can invoke the same static factory and get two distinct singleton beans. Calling the static method directly can also yield an instance completely outside any context.

### Misconception 3: "Every @Bean should be static for speed"

Static does not automatically optimize arbitrary application beans. Instance `@Bean` methods with constructor/factory-method injection are usually clear enough. The clearest benefit of static is **avoiding early instantiation of the configuration class when creating BFPP/BPP infrastructure beans**.

### Misconception 4: "Returning Object is fine because the runtime object is a BeanPostProcessor"

The container needs to detect BPPs **before** the runtime object exists. An overly broad declared return type can prevent special beans from being registered into the processing pipeline in the proper phase.

### Misconception 5: "Having the right return type means the bean is already created"

Bean definition and type prediction do not mean the singleton has been instantiated. Use `containsSingleton` or observe factory/callbacks to distinguish timing.

### Misconception 6: "Static @Bean benefits from interception via @Configuration"

Static methods cannot be overridden; direct calls to a static factory execute ordinary Java. Only calls coordinated by the Spring bean factory follow bean scope and lifecycle.

### Misconception 7: "A non-static BFPP cannot run"

It **can** run, yet it instantiates the configuration bean early and risks lifecycle issues. Spring recommends static to avoid those risks, not because Java forbids an instance factory method from returning a BFPP.

### Misconception 8: "A static BPP depending on an application service is still safe"

The factory may not need a `@Configuration` instance, yet when Spring resolves dependency parameters, the service can still be pulled into an early phase. Prefer processors that do not pull in beans needing proxying/lifecycle processing.

### Misconception 9: "Using getType() is guaranteed never to have side effects"

In common cases, a specific enough return type lets Spring predict the type from metadata. However, FactoryBean, proxies, custom factory metadata, or eager-init options can complicate things. Do not treat `getType()` as an absolute promise that no bean will be instantiated.

### Misconception 10: "Spring sees the keyword static and knows the bean is a BFPP/BPP"

No. To recognize a special bean kind, Spring needs appropriate **type information** and a bean definition registered in the right phase. `static` solves **calling the factory without a configuration instance**, whereas **return type** solves **identifying the bean by type**. The two properties serve two different needs.

## 15. How to Debug in Real Applications

When a BPP does not run or warnings appear about beans not being eligible for auto-proxying, check:

- Is the `@Bean` method declared **static**, or is Spring forced to instantiate the configuration early?
- Is the return type on the method **specific enough** (BFPP/BPP/implementation) for pre-instantiation detection?
- Does the processor have fields/constructors/factory parameters requiring **business beans**?
- Are business beans requested via `getBean()` inside a BFPP or configuration/BPP constructor?
- Was any processor registered very late, after services were already created?
- Is the configuration running in `AnnotationConfigApplicationContext`, a web child context, or another Spring Boot context?
- Were beans created manually with `new` or via direct static factory calls instead of from the container?

Checking bean definitions/types once the context is loaded:

```java
ConfigurableListableBeanFactory factory = context.getBeanFactory();

System.out.println(factory.containsBeanDefinition("catalog"));
System.out.println(factory.getType("catalog"));
System.out.println(factory.containsSingleton("catalog"));
```

This snippet requires importing `org.springframework.beans.factory.config.ConfigurableListableBeanFactory` and the `context` variable from the example. To observe **before instantiation**, place it inside a BFPP as in the demo; running after `refresh()` normally shows the singleton bean has already been created.

If Spring logs that a bean is not eligible for processing by **all** BeanPostProcessors, trace which components forced early creation and remove that dependency/call path. Do not disable auto-proxying altogether or suppress logs to treat only the symptom.

## 16. Testing Early Behavior Without Guessing Uncontracted Order

An integration test can build an `AnnotationConfigApplicationContext` with only the infrastructure configuration under test, then use a recorder/counter:

1. The BFPP records how many times the configuration instance was created **when its callback runs**; with a static factory needing no config instance, it can be 0 in a simple fixture.
2. The BFPP checks the bean definition and `getType()` while the target bean has not yet been created.
3. The BPP records bean names received in `postProcessAfterInitialization`.
4. After `refresh()`, the test verifies singleton beans and dependency injection.
5. A direct static factory method call is compared against `context.getBean(...)` to prove the difference.

Example check in the main program:

```java
if (Config.GATEWAYS_SEEN.get() != 1) {
    throw new AssertionError("Gateway was not observed by BPP");
}
```

This snippet uses `Config` from `StaticBeanDemo` and is only valid where Java visibility rules allow accessing the field. This assertion guards the crucial expectation that the target bean was observed by the BPP. In production tests, use JUnit assertions and isolated fixtures, avoiding reliance on logs not guaranteed stable by Spring.

**Warning about experiments:** if you change the fixture's BFPP/BPP from static to instance or change the declared return type to `Object`, do not keep expecting the original output as an absolute baseline. The point of the variation is to observe **lifecycle differences**, not to force it to stay identical to the valid version.

## 17. Self-Practice Questions and Answers

**Question 1.** Does a static `@Bean` returning `Catalog` force `Catalog` to be created before every other bean?

**Answer:** No. Static only allows the factory method to run without a configuration instance. When `Catalog` is created depends on scope, laziness, and dependencies.

**Question 2.** Why should a BFPP `@Bean` usually be static?

**Answer:** BFPPs are discovered and created very early by the container. A static factory can be invoked without instantiating the configuration class prematurely, thereby avoiding conflicts with annotation injection and lifecycle callbacks.

**Question 3.** Why should a BPP factory method not declare return type `Object`?

**Answer:** The container needs to detect BPPs by type before creating regular beans. An overly broad return type can prevent type prediction from recognizing it as a BPP.

**Question 4.** Is a static `@Bean` a JVM-wide static singleton?

**Answer:** No. Spring's default singleton scope belongs to each context. Direct Java method calls can still construct independent objects.

**Question 5.** How do `Config.catalog()` and `context.getBean(Catalog.class)` differ?

**Answer:** The first is an ordinary Java static call without Spring scope/lifecycle management. The second retrieves the bean managed by the container.

**Question 6.** In the demo, why are `early:catalog-type=Catalog` and `early:catalog-instantiated=false` both true?

**Answer:** The container already has a definition with a determinable return type, yet has not executed the factory to create the singleton target.

**Question 7.** Is there any problem with return type `PaymentGateway` returning a `StripePaymentProcessor` implementation?

**Answer:** No problem if consumers only need `PaymentGateway`. If a consumer requires the concrete implementation during early type matching, the container may not yet recognize that type before the instance is created.

**Question 8.** Does changing a static BFPP to non-static always throw an exception?

**Answer:** Not necessarily. However, it can force early creation of the configuration instance and trigger INFO/warning logs or lifecycle side effects; use static per Spring's recommendation.

**Question 9.** Does a static BPP method receiving `MyService` as a parameter completely avoid early bean creation?

**Answer:** No. Spring may have to instantiate `MyService` to supply the parameter, causing the exact risk that `static` aims to avoid. Minimize application dependencies for early processors.

**Question 10.** Distinguish `BeanFactoryPostProcessor` and `BeanPostProcessor`.

**Answer:** BFPP processes bean definitions/metadata before most application beans are instantiated. BPP processes bean instances during initialization and can wrap/proxy instances.

## 18. Official Documentation

- [Spring Framework 6.2 — @Bean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/context/annotation/Bean.html): static BFPP/BPP factory methods, type visibility, full/lite mode, scoping, and lifecycle.
- [Spring Framework 6.2 — BeanPostProcessor Javadoc](https://docs.spring.io/spring-framework/docs/6.2.x/javadoc-api/org/springframework/beans/factory/config/BeanPostProcessor.html): BPP registration phase, static factory recommendation.
- [Spring Framework — Container Extension Points](https://docs.spring.io/spring-framework/reference/core/beans/factory-extension.html): BFPP/BPP, early type detection, early initialization warnings.
- [Spring Framework — Using @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): factory method return types and type prediction.
- [Spring Framework — Using @Configuration Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/configuration-annotation.html): full configuration, inter-bean calls, and proxy semantics.
- [Spring Framework — Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): bean definitions, factory methods, and `BeanFactory.getType`.

**Core takeaway:** `static @Bean` lets Spring create a bean **without instantiating the `@Configuration` class first**, which is especially crucial for **BFPP/BPPs that must be created very early**. **Declared return type** helps the container **identify a bean by type before it is created**. Both factors complement each other: static addresses when the factory can be called, while return type addresses finding the right extension point. Neither factor turns every bean into an eager bean or a JVM-wide singleton.
