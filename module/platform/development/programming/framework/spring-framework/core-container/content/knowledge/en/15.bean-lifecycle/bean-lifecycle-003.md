# InitializingBean.afterPropertiesSet and @Bean(initMethod) in the Spring Bean Lifecycle

## 1. Why Do Beans Need an Initialization Phase?

The Spring IoC Container does not merely call a constructor to create an object. The container also resolves dependencies, injects configuration, runs bean post-processors, and lets the bean perform **initialization after dependencies are ready** (*initialization callbacks*). This is where a bean can validate configuration, build derived data structures, or open resources needed for its own operation.

The two central mechanisms of this lesson:

- `InitializingBean.afterPropertiesSet()`: the bean **implements a Spring interface** and Spring calls this method after properties/dependencies are set.
- `@Bean(initMethod = "methodName")`: configures the bean definition so Spring **invokes a chosen method on the bean returned by the factory method**, without forcing the class to implement a Spring interface.

They are two different ways to participate in **the same initialization phase**. Both can be used on one bean; in that case you must understand the callback order and each callback's responsibility so you do not initialize twice or cause unintended side effects.

Expected outcomes after this lesson:

1. Pinpoint the exact position of both callbacks in the bean lifecycle.
2. Declare and properly use both `InitializingBean` and `@Bean(initMethod = ...)`.
3. Know the order when combining them with `@PostConstruct` and the destruction lifecycle.
4. Write a runnable Spring Framework 6.x/Java 17+ example verifying callback order via stdout.
5. Distinguish initialization callbacks from constructors, `@Bean` factory methods, `BeanPostProcessor`, `@Lazy`, and startup hooks such as `ApplicationRunner`.
6. Diagnose errors such as missing methods, unavailable dependencies, callbacks throwing exceptions, or initialization executing twice.

**Scope:** Spring Framework Core Container. Examples run on Java 17 and Spring Context 6.1.x; Spring Boot or an HTTP server is not required.

## 2. Lifecycle Model: Where Do Callbacks Sit?

A simplified sequence for a standard Spring bean:

~~~text
Read bean definition
        |
        v
Select constructor / factory method
        |
        v
Create Java object
        |
        v
Populate dependencies, properties, and run aware callbacks
        |
        v
BeanPostProcessor before initialization
  (for example processing @PostConstruct)
        |
        v
InitializingBean.afterPropertiesSet()
        |
        v
Custom init method from bean definition
  (for example @Bean(initMethod = "connect"))
        |
        v
BeanPostProcessor after initialization
  (may create an AOP proxy)
        |
        v
Bean is ready to be used through the container
        |
        v
When scope ends: supported destruction callbacks
~~~

The diagram describes the common flow for a bean created successfully by the container. In practice there are various extension points: lazy beans, scoped proxies, circular dependencies, and bean post-processors can change details. The key point to remember is that **init callbacks run after the bean's dependencies have been assigned, before bean initialization completes**.

If all three mechanisms are present **on the same bean** with distinct method names, the order documented by Spring is:

1. Method annotated with `@PostConstruct`.
2. `InitializingBean.afterPropertiesSet()`.
3. Custom init method declared via `@Bean(initMethod = "...")` or equivalent metadata.

`BeanPostProcessor` instances are invoked by Spring before and after the initialization phase, which does not mean every post-processor acts at the exact same moment. For example, processing `@PostConstruct` happens during the *before initialization* step. A bean may be wrapped with AOP after the initialization callbacks, so do not assume calls inside an init method go through the final proxy.

## 3. `InitializingBean.afterPropertiesSet()`

### 3.1. Interface and contract

`InitializingBean` belongs to the package:

~~~java
import org.springframework.beans.factory.InitializingBean;
~~~

The interface defines one method:

~~~java
public interface InitializingBean {
    void afterPropertiesSet() throws Exception;
}
~~~

This is the interface's contract signature to explain the API; you **do not redeclare the interface yourself** in your project. Spring invokes the method once each time **the container initializes that bean instance**, after supplying dependencies/properties via the corresponding bean management mechanism.

Example bean class:

~~~java
import org.springframework.beans.factory.InitializingBean;

public class ReportFormatter implements InitializingBean {
    private String prefix;

    public void setPrefix(String prefix) {
        this.prefix = prefix;
    }

    @Override
    public void afterPropertiesSet() {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalStateException("prefix must not be blank");
        }
    }

    public String format(String value) {
        return prefix + value;
    }
}
~~~

This is a **class that compiles if Spring Beans is on the classpath**; for Spring to invoke `afterPropertiesSet()` automatically, the instance must be registered via a Spring bean definition (e.g., `@Bean` or `@Component` with dependency configuration).

Spring guarantees that dependencies from normal assembly have been assigned before the callback. Therefore, `afterPropertiesSet()` is suitable for:

- Validating multiple interdependent properties.
- Converting configuration into a ready-to-use data structure.
- Preparing internal resources that require dependencies to already be supplied.
- Detecting invalid configuration as soon as the container initializes the bean instead of waiting for the first request.

However, **"properties have been set" does not mean the entire application or all other beans have finished initializing**. Avoid treating this as a hook for work requiring all application services to have completed startup.

### 3.2. Throwing exceptions

The interface method declares `throws Exception`. If initialization fails, you can throw a meaningful exception:

~~~java
@Override
public void afterPropertiesSet() {
    if (endpoint == null || endpoint.isBlank()) {
        throw new IllegalStateException("endpoint is required");
    }
    if (retryCount < 0) {
        throw new IllegalArgumentException("retryCount must be >= 0");
    }
}
~~~

This snippet illustrates a method inside a class that already has `endpoint` and `retryCount` fields. It is not a standalone Java file.

When the callback throws an exception, bean creation **does not complete successfully**. For a singleton eagerly created during context refresh, the failure usually causes context startup to fail, wrapped in a bean creation exception with the root cause. For a lazy bean, the error may only surface on the first bean retrieval.

### 3.3. Trade-offs

Advantages:

- Clear method with a uniform name, no method-name string configuration required.
- IDE and compiler verify interface implementation.
- Suitable when the class belongs to a Spring application and you want to express the contract "must be initialized after injection".

Disadvantages:

- Business class depends on a Spring API via `InitializingBean`.
- You cannot add this interface to a third-party library class whose source you cannot modify.
- Calling `afterPropertiesSet()` manually or again during normal logic can cause duplicate side effects; let the container manage the lifecycle alone.

If you need to keep the class free of Spring dependencies, consider a custom init method on the bean definition.

## 4. `@Bean(initMethod = "...")`

### 4.1. Syntax

`@Bean` belongs to `org.springframework.context.annotation.Bean`. The `initMethod` attribute takes **the method name on the bean instance returned by the factory method**.

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FormatterConfig {

    @Bean(initMethod = "prepare")
    public ExternalFormatter externalFormatter() {
        return new ExternalFormatter("ORDER-");
    }
}
~~~

Supporting class:

~~~java
public class ExternalFormatter {
    private final String prefix;
    private boolean prepared;

    public ExternalFormatter(String prefix) {
        this.prefix = prefix;
    }

    public void prepare() {
        if (prefix == null || prefix.isBlank()) {
            throw new IllegalStateException("prefix missing");
        }
        prepared = true;
    }

    public String format(String value) {
        if (!prepared) {
            throw new IllegalStateException("formatter not initialized");
        }
        return prefix + value;
    }
}
~~~

The two snippets above belong to **two class files in the same package**; when `FormatterConfig` is registered in an `ApplicationContext`, Spring calls `externalFormatter()` to create the object and then invokes `prepare()` as a custom init callback. There is no need to write `implements InitializingBean` in `ExternalFormatter`.

A custom initialization method should be declared as a no-arg instance method; a typical example is `public void prepare()`. Avoid designing init methods that take business parameters: inject them beforehand via constructor/setter/factory method and initialize based on existing state.

### 4.2. Which method does Spring invoke?

Distinguish the two methods:

~~~java
@Bean(initMethod = "prepare")
public ExternalFormatter externalFormatter() { // Factory method
    return new ExternalFormatter("ORDER-");
}
~~~

- `externalFormatter()` belongs to the **configuration class**: the factory method that creates and returns the bean object.
- `prepare()` belongs to the **`ExternalFormatter` instance**: the initialization callback invoked by Spring **after the object has been created and assembled**.
- The string `"prepare"` is the method name looked up on the bean instance; it is neither the bean name nor the factory method name.

If the factory method calls `prepare()` itself while still declaring `initMethod = "prepare"`, the same work will likely run **twice**: once manually inside the factory method and once when Spring calls the init callback. Choose one place to be responsible for calling it.

### 4.3. How does it differ from `@PostConstruct`?

`@PostConstruct` is placed directly on a method of the bean class:

~~~java
import jakarta.annotation.PostConstruct;

public class ExternalFormatter {
    @PostConstruct
    public void validate() {
        // Invoked during the before-initialization phase if the processor is registered.
    }
}
~~~

This snippet illustrates **a different class or an alternative version** of the example; to run it requires the Jakarta Annotation API and the corresponding processor in the Spring context.

`@PostConstruct` is useful when you own the class and want to declare lifecycle behavior right on the class. `@Bean(initMethod)` is useful when you want to keep the class pure Java or when the class comes from an external library whose source you cannot annotate.

In Spring Framework 6.x, the standard package is `jakarta.annotation.PostConstruct`. Do not mistakenly import `javax.annotation.PostConstruct` from legacy applications without checking compatibility.

## 5. Complete Java 17 + Spring Context 6.1 Example: Observing All Three Callbacks

This example places all Java code into a single `LifecycleDemo.java` file and uses Maven to download dependencies. It demonstrates:

- The `@Bean` factory method runs when the container needs to create the bean.
- The constructor runs when the Java object is created.
- `@PostConstruct` runs before `afterPropertiesSet()`.
- `afterPropertiesSet()` runs before `@Bean(initMethod = "open")`.
- Only after these callbacks do we retrieve the ready bean from the context.
- When the context closes, the custom destroy callback runs.

### 5.1. Structure

~~~text
lifecycle-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── lifecycle/
                        └── LifecycleDemo.java
~~~

### 5.2. File `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>lifecycle-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.1.13</version>
        </dependency>
        <dependency>
            <groupId>jakarta.annotation</groupId>
            <artifactId>jakarta.annotation-api</artifactId>
            <version>2.1.1</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.3.0</version>
                <configuration>
                    <mainClass>com.example.lifecycle.LifecycleDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 5.3. File `src/main/java/com/example/lifecycle/LifecycleDemo.java`

~~~java
package com.example.lifecycle;

import jakarta.annotation.PostConstruct;
import org.springframework.beans.factory.InitializingBean;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class LifecycleDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(Config.class)) {

            ManagedClient client = context.getBean(ManagedClient.class);
            System.out.println("5. Application uses ready bean: " + client.isReady());
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class Config {

        @Bean(initMethod = "open", destroyMethod = "shutdown")
        public ManagedClient managedClient() {
            System.out.println("0. @Bean factory method");
            return new ManagedClient("demo-endpoint");
        }
    }

    public static class ManagedClient implements InitializingBean {
        private final String endpoint;
        private boolean postConstructDone;
        private boolean afterPropertiesSetDone;
        private boolean ready;

        public ManagedClient(String endpoint) {
            this.endpoint = endpoint;
            System.out.println("1. Constructor");
        }

        @PostConstruct
        public void annotatedInit() {
            if (endpoint == null || endpoint.isBlank()) {
                throw new IllegalStateException("Endpoint is required");
            }
            postConstructDone = true;
            System.out.println("2. @PostConstruct");
        }

        @Override
        public void afterPropertiesSet() {
            if (!postConstructDone) {
                throw new IllegalStateException("@PostConstruct was not called");
            }
            afterPropertiesSetDone = true;
            System.out.println("3. InitializingBean.afterPropertiesSet");
        }

        public void open() {
            if (!afterPropertiesSetDone) {
                throw new IllegalStateException("Properties are not ready");
            }
            ready = true;
            System.out.println("4. @Bean(initMethod = open)");
        }

        public boolean isReady() {
            return ready;
        }

        public void shutdown() {
            ready = false;
            System.out.println("6. @Bean(destroyMethod = shutdown)");
        }
    }
}
~~~

`Config` is registered via `AnnotationConfigApplicationContext(Config.class)`. The `ManagedClient` bean is created by the `managedClient()` method. `AnnotationConfigApplicationContext` also registers standard annotation processors; when `jakarta.annotation.PostConstruct` is on the classpath, the `annotatedInit()` callback is processed by `CommonAnnotationBeanPostProcessor`.

`ManagedClient` is a `static` nested class, so it does not depend on an outer instance. All methods and imports are contained in the file, requiring no servlet container, database, or network connection to run.

### 5.4. Run command

Requirements: JDK 17 or newer, Maven 3.9.x. From the `lifecycle-demo` directory, run:

~~~bash
mvn -q compile exec:java
~~~

The program's `System.out.println` lines, in exact order:

~~~text
0. @Bean factory method
1. Constructor
2. @PostConstruct
3. InitializingBean.afterPropertiesSet
4. @Bean(initMethod = open)
5. Application uses ready bean: true
6. @Bean(destroyMethod = shutdown)
~~~

Maven, logging frameworks, and plugins may emit extra logs outside the lines above; this is **stdout produced by the methods in the example**. This sequence clearly shows both initialization methods `afterPropertiesSet()` and `open()` being invoked by the container before `context.getBean(...)` hands the fully initialized bean to `main`.

### 5.5. Why does `shutdown()` only run when closing the context?

The example uses `try-with-resources` because `AnnotationConfigApplicationContext` implements `AutoCloseable`. At the end of the block, `context.close()` is invoked automatically; for a singleton bean with `destroyMethod = "shutdown"`, Spring executes the custom destroy method. In a continuously running application, destruction callbacks run when the context is closed, such as during a graceful shutdown.

`initMethod` and `destroyMethod` are two independent callbacks. Do not infer that a prototype bean is automatically destroyed by the container at the end of a request/task: Spring **does not track prototypes handed out to callers in order to destroy them** the way it does for singletons. Bean scope determines how often initialization occurs and where destruction is managed.

## 6. Comparing the Two Main Mechanisms

| Criterion | `InitializingBean.afterPropertiesSet()` | `@Bean(initMethod = "...")` |
| --- | --- | --- |
| Where is it declared? | Inside the bean class via `implements InitializingBean` | On the bean factory method/bean definition in a configuration class |
| Method name | Fixed: `afterPropertiesSet()` | Any name, as a string in `initMethod` |
| Dependency on Spring API inside class | Yes | Not required |
| Can it be configured for external library classes without editing source? | Not directly | Yes |
| When is it called? | After the instance's dependencies/properties are assembled | After `afterPropertiesSet()` if present, in the same init phase |
| Compiler validation | Guarantees implementing the interface method properly | Method name string is not checked by the compiler during Java build |
| Typically used for | Project-owned beans wanting an explicit lifecycle contract | Library beans, pure Java beans, configuring init outside the class |
| Applies to `@Component`? | Yes, if the class implements the interface and is managed by Spring | `@Bean(initMethod)` is only placed on `@Bean` methods; for components you can use `@PostConstruct` or other metadata |

**There is no rule that you must always combine both.** If you only need to validate dependencies, choosing a single callback is enough. Combine multiple callbacks only when there is a clear reason for each stage; avoid scattering one initialization protocol across too many hard-to-test methods.

### Difference between "factory creates object" and "init finishes object"

Example:

~~~java
@Bean(initMethod = "initialize")
public CacheIndex cacheIndex() {
    CacheIndex index = new CacheIndex();
    index.setCapacity(100);
    return index;
}
~~~

Spring calls `cacheIndex()` to obtain the object, and then calls `initialize()` according to the bean metadata. This is an **illustrative snippet**; the `CacheIndex` class needs a matching constructor, setter, and `initialize()` method.

If you write:

~~~java
@Bean(initMethod = "initialize")
public CacheIndex cacheIndex() {
    CacheIndex index = new CacheIndex();
    index.setCapacity(100);
    index.initialize();
    return index;
}
~~~

Then `initialize()` is already called in the factory and will be called again by the container as the init method. Do not write both unless the method is truly designed to be idempotent and there is a reason for repeated invocation (usually this indicates a configuration mistake).

## 7. Consistency: `@PostConstruct`, `afterPropertiesSet`, and Custom Init

When combining the three approaches, they should have **distinct method names** so responsibilities stay clear:

~~~java
public class IndexBuilder implements InitializingBean {
    @PostConstruct
    public void validateConfiguration() {
        // 1. Validate injected values.
    }

    @Override
    public void afterPropertiesSet() {
        // 2. Compute data structures based on configuration.
    }

    public void warmUp() {
        // 3. Prepare data needed to serve requests.
    }
}
~~~

Configuration:

~~~java
@Bean(initMethod = "warmUp")
public IndexBuilder indexBuilder() {
    return new IndexBuilder();
}
~~~

The two snippets above illustrate declaring them on the same bean; running them requires importing `InitializingBean`, `PostConstruct`, and `Bean`, along with an annotation-aware context. Spring guarantees the order **`validateConfiguration()` → `afterPropertiesSet()` → `warmUp()`** provided the callbacks are properly registered and do not throw exceptions.

If the same method is declared under multiple lifecycle mechanisms, Spring has deduplication handling according to the lifecycle contract; however, do not abuse that to create hard-to-read configurations. It is better **not to mark the exact same method as both `@PostConstruct` and `initMethod`**.

### When should a class NOT implement `InitializingBean`?

For a domain model or Spring-independent library, extract initialization behavior into a plain method:

~~~java
public class RuleEngine {
    public void prepare() {
        // Pure Java logic, independent of the framework.
    }
}
~~~

Then attach the method to the bean definition:

~~~java
@Bean(initMethod = "prepare")
public RuleEngine ruleEngine() {
    return new RuleEngine();
}
~~~

This design still allows testing the class with `new RuleEngine()` in unit tests by calling `prepare()` explicitly. Spring only triggers the method automatically when the object is created by the container as a bean.

## 8. Lifecycle Dependency on Scope and Lazy Initialization

### 8.1. Default singleton

A non-lazy singleton bean is normally initialized by Spring during context refresh. Consequently, `afterPropertiesSet()` and custom `initMethod` usually run during application startup. Subsequent calls to `getBean(...)` return the already-initialized singleton; they **do not repeat the init callbacks**.

~~~java
@Bean(initMethod = "initialize")
public ServiceRegistry serviceRegistry() {
    return new ServiceRegistry();
}
~~~

This is an illustrative example; the `ServiceRegistry` class has a no-arg `initialize()` method. Calling `context.getBean(ServiceRegistry.class)` 100 times does not make `initialize()` run 100 times if there is only one singleton bean definition in that context.

### 8.2. Prototype

For prototype scope, each time the container is asked to supply a new target, it creates a new instance and runs initialization on that instance:

~~~java
@Bean(initMethod = "prepare")
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
public WorkSession workSession() {
    return new WorkSession();
}
~~~

This bean requires importing `Scope` and `ConfigurableBeanFactory`; the `WorkSession` class must have a `prepare()` method. If `context.getBean(WorkSession.class)` is called twice, Spring initializes two distinct objects and `prepare()` runs for each one.

**Note:** Spring does not automatically execute destroy callbacks for prototypes after handing out the object. If `prepare()` opens resources that must be closed, the caller obtaining the prototype must actively manage resources and cleanup, for instance using `AutoCloseable` when appropriate.

### 8.3. Lazy singleton

~~~java
@Bean(initMethod = "prepare")
@Lazy
public ExpensiveIndex expensiveIndex() {
    return new ExpensiveIndex();
}
~~~

This is an illustrative snippet requiring importing `Lazy` and a corresponding `ExpensiveIndex` class. When the lazy singleton is actually created for the first time, the callback runs. However, if another non-lazy singleton needs this dependency during startup, Spring may still create it early to satisfy that dependency.

**Distinction:** Scope determines *how many instances*, while lazy initialization determines *when an instance is created*. Callbacks run per instance creation, not per normal method invocation.

### 8.4. Request/session and scoped beans

The initialization callback of a request-scoped or session-scoped target runs when the actual target is created in the corresponding scope, not merely because a singleton holds a scoped proxy. With `@RequestScope`, each request can create its own target and run its own init callback.

If a singleton's init method tries to fetch a request-scoped target at startup when no request scope is active, it can trigger `ScopeNotActiveException`. Do not open a fake HTTP request or change the scope globally just to make the callback run: move the initialization into the proper context.

## 9. Common Mistakes with `@Bean(initMethod)`

### 9.1. Missing method or typo in name

~~~java
@Bean(initMethod = "intialize") // Typo: missing the letter "i".
public WorkerClient workerClient() {
    return new WorkerClient();
}
~~~

If `WorkerClient` only has an `initialize()` method, the configuration points to a nonexistent method name. Spring may fail when creating the bean, with a cause reflecting that no valid init method was found.

Because `initMethod` is a **string literal**, IDEs do not always catch this error at compile time. When renaming a method, remember to update the bean definition and have an integration test that starts the context.

### 9.2. Init method requiring business parameters

~~~java
public void initialize(String path) {
    // This method is not suitable for a name-specified initMethod.
}
~~~

A configured custom init method should be a **no-arg method**. Pass `path` via constructor or dependency injection:

~~~java
public WorkerClient(String path) {
    this.path = path;
}

public void initialize() {
    // Use the already-set this.path.
}
~~~

Both snippets illustrate the same `WorkerClient` class with a `path` field and the corresponding imports/configuration.

### 9.3. Not registering the bean with Spring

~~~java
WorkerClient client = new WorkerClient("logs");
client.doWork();
~~~

This snippet creates the object using Java `new`. Spring does not see the instance and therefore **does not run** `InitializingBean.afterPropertiesSet()` or `@Bean(initMethod)` on it. If you want Spring to manage initialization, retrieve the bean via a Spring context/bean definition instead of instantiating it yourself and expecting callbacks to run automatically.

### 9.4. Calling the initialization method manually twice

~~~java
@Bean(initMethod = "initialize")
public WorkerClient workerClient() {
    WorkerClient client = new WorkerClient("logs");
    client.initialize(); // Manual call #1.
    return client;        // Spring calls it a 2nd time via initMethod.
}
~~~

This snippet illustrates an **anti-pattern**. When initialization has side effects such as opening connections, registering listeners, or writing data, calling it twice can leak resources, create duplicate registrations, or produce unpredictable state mutations.

### 9.5. Callback throws an exception whose root cause gets obscured

Some errors surface as `BeanCreationException`, `UnsatisfiedDependencyException`, or a context refresh failure. Trace `Caused by` down to the exception thrown inside `afterPropertiesSet()` or the custom init method.

Do not handle this by catching all exceptions and silently letting the container keep an unready bean. If a bean strictly requires valid configuration, **failing fast with a clear error** is usually safer.

### 9.6. Using callbacks for long work or system-wide startup dependencies

It is not recommended to run minute-long jobs, call network APIs without timeouts, or launch unbounded background threads directly inside `afterPropertiesSet()`. This delays bean/container creation and complicates shutdown.

Depending on the problem, distinguish:

- **Bean-internal** initialization: `@PostConstruct`, `afterPropertiesSet`, custom `initMethod`.
- Behavior **after a Spring Boot application has created the context**: consider `ApplicationRunner`/`CommandLineRunner` (if using Boot).
- Managing start/stop of background services tied to the application context lifecycle: `Lifecycle`/`SmartLifecycle` when appropriate.

These are contracts with different purposes. Do not equate `afterPropertiesSet()` with "the application is completely ready to serve all requests".

## 10. When a Bean Uses Injected Dependencies

A fitting use case is an object created by `@Bean` that needs a constructor dependency and then initializes a structure using that dependency.

~~~java
public class PriceRuleIndex {
    private final RuleRepository repository;
    private List<String> rules;

    public PriceRuleIndex(RuleRepository repository) {
        this.repository = repository;
    }

    public void rebuild() {
        this.rules = List.copyOf(repository.loadRuleNames());
    }

    public List<String> rules() {
        return rules;
    }
}
~~~

Configuration:

~~~java
@Configuration(proxyBeanMethods = false)
class PriceRuleConfig {

    @Bean(initMethod = "rebuild")
    PriceRuleIndex priceRuleIndex(RuleRepository repository) {
        return new PriceRuleIndex(repository);
    }
}
~~~

This is **illustrative assembled code**, not a standalone program: it needs a `RuleRepository` interface with `loadRuleNames()`, Java/Spring imports, and a Spring-registered repository implementation.

Spring resolves `RuleRepository` into the `priceRuleIndex(...)` parameter before creating the index. After the factory method returns the index, Spring invokes `rebuild()` to build the snapshot. If `rebuild()` throws an exception, bean creation fails.

Real-world consideration: if `repository.loadRuleNames()` calls a database/network during startup, you need timeouts, a retry policy, and infrastructure readiness considerations. An init callback is not a default transaction boundary; if transaction/AOP behavior is needed, check when proxies are created and how to interact with the corresponding service.

### Why not call a transaction-proxied method via `this` inside init?

Early lifecycle callbacks operate on the target bean before certain AOP proxies are finalized. Calling `this.transactionalMethod()` inside `afterPropertiesSet()` cannot rely on `@Transactional` advice from an outer proxy.

If initialization requires transactional work, extract that part into a container-managed component invoked at an appropriate time, or use programmatic APIs like `TransactionTemplate` per your transaction design, instead of assuming self-invocation goes through a proxy.

## 11. Distinguishing Callbacks from `BeanPostProcessor`

`InitializingBean` is an **interface implemented by the bean itself**, whereas `BeanPostProcessor` is an extension point applying processing to other beans.

The two general methods:

~~~java
Object postProcessBeforeInitialization(Object bean, String beanName);
Object postProcessAfterInitialization(Object bean, String beanName);
~~~

These are conceptual signatures of `BeanPostProcessor`; the actual API includes default methods and nullable contracts depending on the version, so the snippet only illustrates the processing points, not the full interface definition.

For a normal bean:

1. Spring invokes `BeanPostProcessor.postProcessBeforeInitialization(...)` implementations.
2. A processor handles `@PostConstruct` if present.
3. Spring invokes `InitializingBean.afterPropertiesSet()`.
4. Spring invokes the custom init method from the bean definition.
5. Spring invokes `BeanPostProcessor.postProcessAfterInitialization(...)` implementations.

In practice there is internal ordering and machinery across multiple processors; the goal here is to distinguish responsibilities. Never call `afterPropertiesSet()` manually inside a `BeanPostProcessor` if the container will call it anyway, to avoid duplicate callbacks.

If you need to verify the full pipeline, write an integration test with a processor logging events and assert the expected order; in this lesson, the `LifecycleDemo` example already demonstrated the order of the three initialization mechanisms.

## 12. How to Test Initialization Effectively

### 12.1. Testing the class's own contract

For a pure Java bean, instantiate the object and call the custom init method to test validation or internal state:

~~~java
ExternalFormatter formatter = new ExternalFormatter("ORDER-");
formatter.prepare();
System.out.println(formatter.format("42"));
~~~

Output of the Section 4 class example:

~~~text
ORDER-42
~~~

Running this snippet requires the `ExternalFormatter` class from Section 4. It is a pure Java behavior test and **does not** prove Spring automatically invokes `prepare()`.

### 12.2. Testing through a real Spring container

To verify `@Bean(initMethod)` is actually configured, initialize an `AnnotationConfigApplicationContext` containing the `@Configuration` class, call `getBean(...)`, and assert state:

~~~java
try (var context =
         new AnnotationConfigApplicationContext(FormatterConfig.class)) {
    ExternalFormatter bean = context.getBean(ExternalFormatter.class);
    if (!"ORDER-42".equals(bean.format("42"))) {
        throw new AssertionError("Initialization callback did not run");
    }
}
~~~

The snippet above can be placed in `main` or a test method and requires importing `AnnotationConfigApplicationContext`. It uses `FormatterConfig` and `ExternalFormatter` from Section 4.

### 12.3. Verifying invocation counts

For a singleton bean, initialization happens only **when the instance is created**, not after every `getBean()`. For a prototype, each instance created by Spring has its own initialization lifecycle.

If you want to assert invocation count without relying on logs, create a `CounterBean` class with an instance counter field incremented in the init callback and assert it. However, avoid `static` counters shared across multiple tests/contexts without proper resetting; they can make tests non-independent.

### 12.4. Testing the failure path

Create a bean with missing required configuration, such as a blank endpoint in `afterPropertiesSet()`, then start the context and assert it fails with a meaningful cause. This is more valuable than only checking "context starts" because it verifies the **fail-fast** policy on misconfiguration.

## 13. Frequently Asked Questions

**Why use `@Bean(initMethod)` when you already have a constructor?**

The constructor should ensure the object is created validly and assign required dependencies. Custom init is useful when you need a dedicated step **after Spring has assembled the bean**, especially with setter injection or external library bean classes. If the logic is simple and all data is available in the constructor, no extra init callback is needed.

**Is `afterPropertiesSet()` called after "every bean in the whole application" is ready?**

No. It guarantees that assembling **the current bean** has reached the initialization phase. Many other beans may not have been created yet, especially lazy beans. Do not use this method as a signal that the entire application is ready.

**What if a class implements `InitializingBean` but is instantiated with `new`?**

It is just a plain Java object. `afterPropertiesSet()` does not run automatically. A Spring bean factory must directly manage the instance via a bean definition and execute its lifecycle.

**Can `@Bean(initMethod)` be placed on a `@Component` class?**

Do not put `@Bean(initMethod)` on a class; `@Bean` is an annotation on a **bean factory method**. For a component class, you typically use `@PostConstruct` or implement `InitializingBean`. A custom init name can also be declared via programmatic/XML bean definitions if the design requires it.

**If a class has `@PostConstruct`, `InitializingBean`, and a custom `initMethod`, what is the order?**

`@PostConstruct` first, then `afterPropertiesSet()`, and finally the custom init method, provided the callbacks are registered and have distinct names.

**Do callbacks run through a Spring AOP proxy or `@Transactional`?**

You should not assume so. Initialization normally runs on the target before AOP proxies are finalized. If init logic needs a transaction, structure the execution flow to match when proxies and the transaction manager are active.

**Can `@Bean(initMethod)` be used to build a custom connection pool?**

You can configure callbacks on third-party classes, though most pooling libraries/frameworks have their own lifecycle and factory config. You must understand ownership and destroy callbacks to avoid opening the pool twice or failing to close resources on time.

## 14. Common Errors and Troubleshooting Guide

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| `afterPropertiesSet()` does not run | Class created with `new` or not registered as a bean | Register in the Spring context and retrieve from the container |
| Spring reports init method not found | Typo in `initMethod` string or method lacks matching signature | Check method name, parameters, accessibility, and actual bean class |
| Callback runs twice | Factory method calls init manually while also declaring `initMethod` | Let Spring call it once; avoid overlapping responsibility |
| Exception at context startup | Init callback throws an exception on an eager singleton | Inspect the root cause, check configuration and dependencies |
| Error only surfaces on first `getBean()` | `@Lazy` bean | Also test the lazy retrieval path |
| Init result differs across prototype lookups | Each lookup creates and initializes a new instance | Review scope if sharing was expected |
| `@Transactional` has no effect inside init | Target has not gone through proxy or uses self-invocation | Move transactional logic to an appropriate invocation flow |
| Bean holds open sockets/files after context close | Missing cleanup or using prototype expecting container destruction | Use destroy lifecycle for singletons or manual cleanup for prototypes |
| One bean needs another bean to have "finished startup" | Treating init callback as a global startup hook | Use an appropriate startup orchestration mechanism; avoid implicit dependencies |
| `@PostConstruct` does not run | Missing processor/annotation dependency or wrong API import | Check `jakarta.annotation` and Spring bean post-processing |

## 15. Practical Project Checklist

Before adding lifecycle initialization, check yourself:

1. **Is the bean managed by Spring?** If created only with `new`, Spring callbacks will not run automatically.
2. **Do you truly need a post-injection hook?** If the constructor suffices, keep the logic in the constructor.
3. **Have you chosen one clear mechanism?** `InitializingBean` when Spring coupling is acceptable; `@Bean(initMethod)` when wanting a pure class or third-party library class.
4. **Is the init callback idempotent?** Avoid accidentally registering two mechanisms or calling it manually again.
5. **Have required dependencies been injected?** Validate state and fail fast with a clear message.
6. **Is there out-of-process I/O?** Configure timeouts and an error policy to avoid hanging startup indefinitely.
7. **Does it depend on AOP/transactions?** Remember the callback runs in the lifecycle before the final proxy is returned.
8. **What is the scope?** Singleton, prototype, lazy, and request/session all dictate when and how many times initialization occurs.
9. **Who cleans up resources?** Configure an appropriate destroy method, especially if the bean is a prototype.
10. **Do you have a test that actually starts a Spring context?** Unit tests calling init manually do not substitute for testing annotations/bean definitions.

## 16. Official Documentation

- [Spring Framework — Customizing the Nature of a Bean](https://docs.spring.io/spring-framework/reference/core/beans/factory-nature.html): initialization callbacks, `InitializingBean`, custom init methods, and ordering when combining lifecycle mechanisms.
- [Spring Framework 6.1 — `InitializingBean` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/beans/factory/InitializingBean.html): API and semantics of `afterPropertiesSet()`.
- [Spring Framework 6.1 — `@Bean` Javadoc](https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Bean.html): `initMethod` and `destroyMethod`.
- [Spring Framework — Using the `@Bean` Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): how factory methods register bean definitions.
- [Spring Framework — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): lifecycle differences across singleton, prototype, and other scopes.
