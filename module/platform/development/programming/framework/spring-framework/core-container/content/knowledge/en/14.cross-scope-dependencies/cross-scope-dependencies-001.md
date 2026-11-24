# Why Doesn't a Prototype Injected Directly into a Singleton Change on Every Call?

## 1. The Problem to Understand

In the Spring Framework Core Container, `singleton` is the default scope: for a bean definition, the container holds one bean instance to reuse. `prototype` means that **every time Spring is asked to provide the prototype bean**, the container creates a new instance.

It can sound contradictory when you declare a `prototype` bean, inject it via constructor into a singleton, and then call a method on the singleton multiple times only to still receive the same instance. This behavior **follows the scope rules**.

> **Core answer:** Spring resolves dependencies when it **creates and assembles the singleton**. One prototype instance is created at that time and stored in the singleton's field/constructor parameter. Subsequent method calls on the singleton merely read back that stored Java reference; they do not automatically become new requests to obtain a bean from Spring.

If you want a fresh prototype **each time an operation runs**, you must ask Spring for the bean **at the time the operation executes**, for example by using `ObjectProvider<T>.getObject()` or a lookup method.

### Learning Objectives

After this lesson, you will be able to:

- Distinguish **each time the container is asked to create a bean** from **each Java method invocation**.
- Explain when dependencies are resolved in constructor injection, field injection, and setter injection.
- Observe precisely why a singleton keeps the same prototype and how to obtain a new prototype on demand.
- Choose among direct injection, `ObjectProvider`, `@Lookup`, and a scoped proxy based on the required lifecycle.
- Avoid the bug of retaining mutable state across calls and understand prototype cleanup responsibilities.

## 2. Two Scopes Operating Independently

Consider two bean definitions:

~~~java
@Component
@Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
class CalculationState {
}

@Service
class CalculationService {
    private final CalculationState state;

    CalculationService(CalculationState state) {
        this.state = state;
    }

    CalculationState currentState() {
        return state;
    }
}
~~~

This is **illustrative code**: it requires Spring imports, component scanning, and an application context to run. `CalculationState` is declared as `prototype`; `CalculationService` has no `@Scope`, so it defaults to `singleton`.

| Event | Is Spring asked to provide a new `CalculationState`? | Result |
| --- | --- | --- |
| Container creates `CalculationService` and resolves constructor argument | Yes | Creates prototype P1 and injects it into the service |
| Call `service.currentState()` 1st time | No | Returns the field pointing to P1 |
| Call `service.currentState()` 2nd time | No | Still P1 |
| Call `context.getBean(CalculationState.class)` | Yes | Creates prototype P2 |
| Call `context.getBean(CalculationState.class)` again | Yes | Creates prototype P3 |

A single instance P1 can be used indefinitely inside a singleton without **turning the prototype bean definition into a singleton**. If another caller requests `CalculationState` from the container, each request still receives a new prototype.

**Scope describes how the container returns a bean when asked, not how often methods are called on the object holding that bean.**

## 3. Progression from Singleton Creation to Business Execution

With constructor injection, we can represent the sequence as follows:

~~~text
ApplicationContext starts
        |
        v
Spring reads bean definitions
        |
        v
Spring prepares to create CalculationService (singleton)
        |
        +----> Resolve dependency CalculationState
        |                  |
        |                  v
        |          Prototype P1 is created
        |                  |
        +<-----------------+
        |
        v
new CalculationService(P1)
        |
        v
Container caches singleton CalculationService
        |
        +---- service.currentState() ---> P1
        +---- service.currentState() ---> P1
        +---- service.currentState() ---> P1
        |
        +---- context.getBean(CalculationState) ---> P2
        +---- context.getBean(CalculationState) ---> P3
~~~

Key deciding points:

1. **Dependency resolution happens at singleton creation time.** For a non-lazy singleton, that time is usually during Spring context initialization; for a lazy singleton, it is when the singleton is first created.
2. The constructor runs **only once for that singleton instance**. It receives P1, then stores the reference in the `state` field.
3. `currentState()` is an ordinary Java method. There is no `BeanFactory.getBean(...)`, provider, lookup, or proxy in this call path to make Spring create P2.
4. `@Scope("prototype")` still takes effect whenever Spring receives **a new request** for the prototype bean from a provider, BeanFactory, or another injection point.
5. In Spring, a singleton is one bean instance **per container per bean definition**, not necessarily a single object across the entire JVM.

### Do constructor, field, and setter injection differ?

All three common forms of injection occur while the container is creating/configuring the object:

~~~java
// Constructor injection: the prototype is resolved for the constructor.
public WorkerService(WorkState workState) {
    this.workState = workState;
}

// Field injection: the prototype is resolved when Spring populates the field.
@Autowired
private WorkState workState;

// Setter injection: the prototype is resolved when Spring invokes the setter.
@Autowired
void setWorkState(WorkState workState) {
    this.workState = workState;
}
~~~

The three snippets above illustrate **three alternatives within a class**—do not combine them verbatim at the same time. None of the three causes Spring to re-inject a new prototype **after each** business method call. Calling a setter yourself with a new object is a separate Java action, not an automatic characteristic of prototype scope.

## 4. Runnable Example Using Java 17 and Spring Context 6.1

This is a plain Java application using `AnnotationConfigApplicationContext`. No Spring Boot or HTTP server is needed. The example demonstrates both **direct injection keeping one prototype** and **`ObjectProvider` obtaining a new prototype** through object identity comparisons and deterministic output.

### 4.1. Directory Structure

~~~text
prototype-singleton-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── com/
                └── example/
                    └── demo/
                        └── PrototypeSingletonDemo.java
~~~

### 4.2. `pom.xml`

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.example</groupId>
    <artifactId>prototype-singleton-demo</artifactId>
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
                    <mainClass>com.example.demo.PrototypeSingletonDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

### 4.3. `PrototypeSingletonDemo.java`

~~~java
package com.example.demo;

import java.util.concurrent.atomic.AtomicInteger;

import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.config.ConfigurableBeanFactory;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Scope;

public class PrototypeSingletonDemo {

    public static void main(String[] args) {
        try (AnnotationConfigApplicationContext context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            FixedConsumer fixed = context.getBean(FixedConsumer.class);
            ProviderConsumer dynamic = context.getBean(ProviderConsumer.class);

            JobState fixedFirst = fixed.current();
            JobState fixedSecond = fixed.current();

            JobState dynamicFirst = dynamic.newJob();
            JobState dynamicSecond = dynamic.newJob();

            System.out.println(
                    "Same singleton service: " +
                    (fixed == context.getBean(FixedConsumer.class)));

            System.out.println(
                    "Directly injected prototype reused: " +
                    (fixedFirst == fixedSecond));

            System.out.println(
                    "Direct state counter: " +
                    fixed.process() + ", " + fixed.process());

            System.out.println(
                    "ObjectProvider gives new prototypes: " +
                    (dynamicFirst != dynamicSecond));

            System.out.println(
                    "Two getBean calls give new prototypes: " +
                    (context.getBean(JobState.class) !=
                     context.getBean(JobState.class)));
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        @Scope(ConfigurableBeanFactory.SCOPE_PROTOTYPE)
        public JobState jobState() {
            return new JobState();
        }

        @Bean
        public FixedConsumer fixedConsumer(JobState jobState) {
            return new FixedConsumer(jobState);
        }

        @Bean
        public ProviderConsumer providerConsumer(
                ObjectProvider<JobState> jobStates) {
            return new ProviderConsumer(jobStates);
        }
    }

    public static class JobState {
        private final AtomicInteger steps = new AtomicInteger();

        public int nextStep() {
            return steps.incrementAndGet();
        }
    }

    public static class FixedConsumer {
        private final JobState state;

        public FixedConsumer(JobState state) {
            this.state = state;
        }

        public JobState current() {
            return state;
        }

        public int process() {
            return state.nextStep();
        }
    }

    public static class ProviderConsumer {
        private final ObjectProvider<JobState> jobStates;

        public ProviderConsumer(ObjectProvider<JobState> jobStates) {
            this.jobStates = jobStates;
        }

        public JobState newJob() {
            return jobStates.getObject();
        }
    }
}
~~~

The classes `JobState`, `FixedConsumer`, and `ProviderConsumer` are declared as `public static` nested classes to keep the entire example in a single file; the actual beans are registered via `@Bean` in `AppConfig`. To observe whether two references point to the same Java object, use `==`, not `equals()`, because `equals()` may be overridden for business value equality.

`@Configuration(proxyBeanMethods = false)` is still valid here: each dependency is passed by Spring into **factory method parameters**, with no direct invocation from one `@Bean` method to another `@Bean` method.

### 4.4. Run Command

Install JDK 17+ and Maven 3.9+, open a terminal in the directory containing `pom.xml`, and run:

~~~bash
mvn -q compile exec:java
~~~

Exact output from the `System.out.println` statements:

~~~text
Same singleton service: true
Directly injected prototype reused: true
Direct state counter: 1, 2
ObjectProvider gives new prototypes: true
Two getBean calls give new prototypes: true
~~~

Maven may print additional messages to stderr depending on the environment. The five lines above are the program's explicit stdout and can be compared directly.

### 4.5. Explanation of Each Result

- **`Same singleton service: true`:** two calls to `context.getBean(FixedConsumer.class)` return the same singleton in the context.
- **`Directly injected prototype reused: true`:** `FixedConsumer` stored one `JobState` in its field. Calling `current()` twice simply returns that same reference.
- **`Direct state counter: 1, 2`:** because the same target is retained, the step count accumulates across the two calls to `process()`. If the work requires a clean state each time, this can be a business bug.
- **`ObjectProvider gives new prototypes: true`:** each `getObject()` call is a new request for the prototype, so the two objects differ.
- **`Two getBean calls give new prototypes: true`:** retrieving a prototype bean directly from the Spring context also creates a new instance each time.

`FixedConsumer` holding onto one prototype does not affect requests for `JobState` elsewhere. Instances created by the provider or `context.getBean(...)` do not alter the injected `state` field.

## 5. Real-World Scenario: Per-Execution State Retained Across Multiple Requests

Suppose there is a singleton service managing report exports and a prototype holding the list of errors for one export run:

~~~java
@Component
@Scope("prototype")
class ExportState {
    private final List<String> errors = new ArrayList<>();

    void addError(String error) {
        errors.add(error);
    }

    int errorCount() {
        return errors.size();
    }
}

@Service
class ExportService {
    private final ExportState state;

    ExportService(ExportState state) {
        this.state = state;
    }

    int export(boolean invalidInput) {
        if (invalidInput) {
            state.addError("Invalid input");
        }
        return state.errorCount();
    }
}
~~~

This snippet is **illustrative code requiring imports for `@Component`, `@Service`, `@Scope`, and `java.util`** in an application with component scanning enabled. If you call:

~~~java
service.export(true);
service.export(false);
~~~

The second call can still return `1`, even though the second input is valid, because the same `ExportState` object is reused. In a web application, multiple requests can share the singleton service, causing data across requests to flow into the same prototype object held long-term by the singleton.

Changing the `@Scope("prototype")` annotation to another string or adding more processing methods in the service does not make Spring automatically re-inject dependencies. You need to change **when the instance is obtained**.

## 6. Recommended Approach: Inject `ObjectProvider<Prototype>`

`ObjectProvider<T>` belongs to `org.springframework.beans.factory`. The container injects a provider, and the singleton requests a new target whenever the logic needs one. This approach preserves constructor injection and is easy to test.

~~~java
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.stereotype.Service;

@Service
public class ExportService {
    private final ObjectProvider<ExportState> states;

    public ExportService(ObjectProvider<ExportState> states) {
        this.states = states;
    }

    public int export(boolean invalidInput) {
        ExportState state = states.getObject(); // Obtain 1 new prototype for this export run.
        if (invalidInput) {
            state.addError("Invalid input");
        }
        return state.errorCount();
    }
}
~~~

This is an **alternative illustrative class** replacing `ExportService` in section 5; do not place two definitions with the same name in one source file. When used, `ExportState` must still be registered with Spring using `@Scope("prototype")`.

If run sequentially:

~~~java
System.out.println(service.export(true));
System.out.println(service.export(false));
~~~

The result will be:

~~~text
1
0
~~~

Because each `export(...)` call starts with a new `ExportState` instance and uses only that instance throughout the run. The key design rule is:

> **Obtain one prototype per unit of work, store it in a local variable, and reuse that variable within that same unit of work.**

Do not call `states.getObject()` repeatedly for individual read/write operations on the same state if those operations need to work on **the same object**:

~~~java
// Wrong if state needs to be shared across two steps:
states.getObject().addError("E1");
int count = states.getObject().errorCount(); // Second object: 0

// Right: obtain once, use throughout one operation:
ExportState state = states.getObject();
state.addError("E1");
int count = state.errorCount(); // 1
~~~

**Note:** `ObjectProvider.getObject()` does not guarantee a new object if the target bean is a singleton: it is **the target's scope** that determines whether one instance or multiple instances are returned. The provider merely defers the lookup action until invocation time.

## 7. Alternative: `@Lookup` Method Injection

Spring can automatically override a method on a container-created bean so that each time the method is called, the container looks up the bean by name or return type. The annotation is `org.springframework.beans.factory.annotation.Lookup`.

~~~java
import org.springframework.beans.factory.annotation.Lookup;
import org.springframework.stereotype.Component;

@Component
public class LookupExportService {

    public int export(boolean invalidInput) {
        ExportState state = createState();
        if (invalidInput) {
            state.addError("Invalid input");
        }
        return state.errorCount();
    }

    @Lookup("exportState")
    protected ExportState createState() {
        // When created and processed properly by Spring, this method
        // is overridden with a lookup performed by the container.
        throw new IllegalStateException("Spring lookup was not applied");
    }
}
~~~

This is an **illustrative snippet placed in an application where the `ExportState` prototype is registered under the name `exportState`** (the default when class `ExportState` is component-scanned); the class must be created by Spring via component scanning or a bean creation mechanism that supports method injection. Do not directly call `new LookupExportService()` and expect Spring to replace the method.

Mechanism:

1. Spring generates a subclass at runtime using CGLIB.
2. The subclass overrides `createState()`.
3. Each time `export(...)` calls `createState()`, the overridden method retrieves `ExportState` from the container.
4. With a `prototype` bean definition, each new lookup returns a new instance.

Limitations to remember:

- The class containing the lookup method and the method itself cannot be `final`, because the subclass must override it.
- Lookup methods **do not work on an instance returned from a `@Bean` factory method**. Spring does not automatically subclass an object that has already been instantiated by a factory method.
- Method injection couples the code to the Spring container and makes dependency provisioning less explicit than constructor-injected `ObjectProvider`.
- The object returned by the method still obeys its declared scope. If `exportState` is a singleton, `@Lookup` can still return the same bean every time.

For applications that need clear code and easy unit testing, `ObjectProvider<T>` is usually easier to understand and control.

## 8. Alternatives: `ObjectFactory`, `Provider`, and `BeanFactory`

The following mechanisms also perform lookup at the time of use:

| Approach | Conceptual syntax | Characteristics |
| --- | --- | --- |
| `ObjectProvider<T>` | `provider.getObject()` | Spring API, supports lazy/optional access, flexible when injecting |
| `ObjectFactory<T>` | `factory.getObject()` | Minimal Spring API; can be injected to obtain beans on demand |
| `jakarta.inject.Provider<T>` | `provider.get()` | Standard Jakarta Inject API, requires matching `jakarta.inject-api` dependency on the classpath |
| `BeanFactory` | `beanFactory.getBean(ExportState.class)` | Works, but makes the service explicitly depend on the container / service locator |
| `ApplicationContext` | `context.getBean(ExportState.class)` | Can retrieve beans, but pulls container responsibilities into the service |

Example with `ObjectFactory`:

~~~java
@Service
class FactoryExportService {
    private final ObjectFactory<ExportState> factory;

    FactoryExportService(ObjectFactory<ExportState> factory) {
        this.factory = factory;
    }

    ExportState createState() {
        return factory.getObject();
    }
}
~~~

This illustrative snippet requires importing `ObjectFactory` from `org.springframework.beans.factory` and the corresponding Spring annotations. The `ExportState` bean must still have prototype scope. Just like `ObjectProvider`, each call to the factory is a new request, so the result depends on the configured scope.

You should not solve this problem by calling `new ExportState()` directly inside the service if `ExportState` needs Spring injection, lifecycle callbacks, AOP, or container facilities. `new` creates a plain Java object and bypasses Spring bean management.

## 9. Scoped Proxy with Prototype: Usable, but You Must Understand Call Scope

One option is to register the prototype with a scoped proxy:

~~~java
@Component
@Scope(
    value = ConfigurableBeanFactory.SCOPE_PROTOTYPE,
    proxyMode = ScopedProxyMode.TARGET_CLASS
)
public class OperationState {
    private String value;

    public void setValue(String value) {
        this.value = value;
    }

    public String getValue() {
        return value;
    }
}
~~~

This snippet is an illustrative class; it requires importing `Component`, `Scope`, `ScopedProxyMode`, and `ConfigurableBeanFactory`.

When `OperationState` is injected into a singleton, the retained dependency is usually a **proxy**, not a single prototype target. The proxy resolves the target according to the scope when forwarding method calls. With prototype, each target lookup can create a different object; therefore:

~~~java
// Code illustrating a common pitfall with prototype scoped proxies.
operationState.setValue("READY");
String result = operationState.getValue();
~~~

**You must not assume `result` is `"READY"`**. The calls to `setValue` and `getValue` can be forwarded to two different prototype targets. This differs significantly from `@RequestScope` or `@SessionScope`: within the same request/session, the corresponding scope normally retains the same target across calls, whereas prototype has no concept of caching per business operation.

If one execution needs **an isolated state that remains stable across multiple method calls**, obtain a single object from `ObjectProvider` and store it in a local variable. A prototype scoped proxy is better suited when each individual method call needs an independent target without relying on state saved from a previous call.

Class-based proxies have restrictions with `final` classes/methods; interface-based proxies require a compatible injection point. Adding a proxy does not automatically make a mutable target thread-safe.

## 10. What About `@Lazy`?

`@Lazy` typically controls **initialization timing**, not redefining the scope from `prototype` to another scope. For example:

~~~java
@Component
@Lazy
class ExpensiveService {
    // ...
}
~~~

This snippet delays bean creation (depending on how the bean is registered/retrieved); you cannot infer that every method call on that bean creates a new object.

`@Lazy` placed on an injection point can create a proxy that resolves the dependency upon use, but that is a **separate lazy-resolution proxy mechanism** and its behavior must be evaluated based on the target bean. Use `ObjectProvider` when your intent is to **deliberately request a new prototype on each processing run**, because the code explicitly states the lookup point and creation count.

Do not confuse three questions:

- **When is it created?** — lazy/eager initialization.
- **How many instances are obtained per container lookup?** — bean scope.
- **When does the program perform a new lookup?** — direct injection, provider, lookup method, or proxy.

## 11. Lifecycle and Performance Trade-offs

### 11.1. Prototypes Are Not Automatically Destroyed by Spring After Handing Off to the Client

Spring manages creation, dependency injection, and initialization callbacks for prototypes, but **does not automatically run destruction callbacks on each prototype handed off to the client** as it does for singletons upon closing the context.

~~~java
@Component
@Scope("prototype")
class FileProcessingSession implements AutoCloseable {
    // Assumes the class holds a resource that needs to be released.

    @Override
    public void close() {
        // Close the actual resource here.
    }
}
~~~

In consuming code, the recipient must manage the resource after finishing the work, for example with `try-with-resources` if the bean implements `AutoCloseable`:

~~~java
try (FileProcessingSession session = sessions.getObject()) {
    // process using session
}
~~~

This illustrative snippet requires an `ObjectProvider<FileProcessingSession> sessions` and a registered prototype bean; specific resource-closing logic depends on the business case. Do not rely on `@PreDestroy` on a prototype to run automatically after each `getObject()` call.

### 11.2. Each Lookup Has a Cost

Each new prototype may have to execute constructor invocation, dependency injection, bean post-processing, and initialization. If the object is just a small POJO with no Spring dependencies, consider creating a **plain Java object** directly at the business layer instead of making it a Spring prototype bean. Conversely, if you need the container to manage dependencies/AOP, use an appropriate factory/provider.

### 11.3. Not Automatically Thread-Safe

A singleton can be used concurrently by multiple requests/threads. If a singleton directly holds a prototype with mutable state, that state is still **shared across calls on the same singleton**, making race conditions very likely. `prototype` does not guarantee thread-safety on its own.

`ObjectProvider.getObject()` can help each execution obtain an independent state, but if you store that new state in a shared field of the singleton, the risk of a race remains. Local variable scope and how objects are passed between threads still determine safety.

## 12. Which Approach Should You Choose?

| Practical requirement | Suitable approach | Why |
| --- | --- | --- |
| Shared dependency without per-execution state | Inject a singleton directly | Simple, avoids unnecessary object creation |
| Create a prototype dependency **once when the singleton is initialized** and keep it long-term | Inject the prototype directly | Correct if the intent is to retain that instance |
| Each business call needs a new prototype, used across multiple steps | Inject `ObjectProvider<T>` and obtain once into a local variable | Clear creation point and usage scope |
| Need lookup in a method on a Spring-created bean | `@Lookup` | Spring overrides the method to supply the bean on call |
| Minimal factory-style abstraction already desired | `ObjectFactory<T>` or `Provider<T>` | Requests the bean only when needed |
| Each individual method call must resolve target by scope | Scoped proxy | Suitable when scope semantics match the need |
| Object is pure Java data/computation | Create via ordinary Java constructor/factory | Avoids unnecessary container coupling |

Be especially cautious with `@Scope("prototype", proxyMode = ScopedProxyMode.TARGET_CLASS)` if the work involves multiple consecutive read/write operations on one state. The target object may change between methods.

## 13. Diagnostic Checklist When a Prototype "Doesn't Change"

When a bean is marked prototype yet multiple calls appear to use the same object, check in order:

1. **Who performs the new lookup?** Does the invoked Java method actually call `ObjectProvider.getObject()`, `@Lookup`, or `BeanFactory.getBean(...)`, or does it merely read a field?
2. **Is the target scope truly prototype?** `@Scope` must apply to the bean definition being injected, not just a class that hasn't been registered with the container.
3. **When is the singleton initialized?** Standard constructor/field/setter injection resolves dependencies at singleton creation time.
4. **How many instances are retrieved?** Do not equate calling a business method multiple times with calling the container multiple times.
5. **Is there a proxy?** You must distinguish proxy identity from target identity; a stable proxy does not mean every method runs on the same target.
6. **Is the target stored in a singleton field after lookup?** Even if the provider fetches a new target once, storing it long-term in the singleton reintroduces sharing.
7. **Is scope being confused with Java equality?** Check using `==` or appropriate identity, not relying solely on `equals()` or a data field that happens to match.
8. **Was bean management bypassed?** Objects created with `new` outside the container do not receive Spring scoping or injection.

A short check in Java:

~~~java
JobState fromProvider1 = provider.getObject();
JobState fromProvider2 = provider.getObject();

System.out.println(fromProvider1 == fromProvider2); // false if prototype.
~~~

This illustrative snippet requires `provider` to be an `ObjectProvider<JobState>` supplied by Spring and `JobState` to be registered as prototype. If you get `true`, inspect the bean definition, how the provider is initialized, and the code actually executing.

## 14. Self-Check Questions

**Question 1:** `@Scope("prototype")` is placed on `ExportState`, and singleton `ExportService` injects `ExportState` via constructor. Calling `export()` 100 times creates how many states for that constructor field?

**Answer:** One `ExportState` instance for that creation of singleton `ExportService`; ordinary calls to `export()` do not cause Spring to re-inject the dependency.

**Question 2:** Switch to injecting `ObjectProvider<ExportState>`. If `getObject()` is called 3 times within one method, how many objects are there?

**Answer:** Three distinct instances when the `ExportState` bean is a prototype and there is no proxy/other instance-returning mechanism; if you want just one instance for the entire method, call the provider once and use a local variable.

**Question 3:** Can `@Lookup` on a `final` method or a method of an instance created by a `@Bean` factory be resolved?

**Answer:** Not under standard lookup-method injection: the method/class must allow Spring to create a subclass and override it; for an instance returned from a `@Bean` factory method, Spring does not proactively subclass that instance.

**Question 4:** Why doesn't `@Scope("prototype")` prevent a singleton service from accidentally sharing state across multiple threads?

**Answer:** Scope only governs object creation behavior at lookup time. A singleton can hold and share the same prototype reference in a field, so all threads accessing that field can still read/write the same object together.

## 15. Official Spring Documentation

- [Spring Framework Reference — Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): `singleton`, `prototype`, and interactions between a singleton and a prototype dependency.
- [Spring Framework Reference — Method Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-method-injection.html): lookup method injection, `@Lookup`, CGLIB, and limitations with `@Bean` factory methods.
- [Spring Framework Reference — Dependency Injection](https://docs.spring.io/spring-framework/reference/core/beans/dependencies/factory-collaborators.html): when container-managed dependencies are assembled.
- [Spring Framework Reference — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): how beans are registered via annotations and semantics related to `@Bean`.
