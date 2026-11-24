# Distinguishing Spring Singleton from the GoF Singleton Pattern

## 1. Two concepts with the same name but different guarantee units

**Spring's singleton** is a *bean scope* in the IoC container: for **a specific bean definition within a container**, Spring manages one shared instance. Lookups or dependency injections referencing that same bean receive the same container-provided object. This is Spring's **default** scope.

**The Gang of Four (GoF) Singleton** is a class-design pattern that controls instantiation and provides a global access point to one instance. In the standard Java model, this pattern typically guarantees one instance **per class within the scope of the ClassLoader that loaded it**, provided the implementation is not circumvented by special object-creation mechanisms.

Formula to remember:

- **Spring singleton = one instance per bean definition per Spring IoC container.**
- **GoF Singleton = one instance controlled at the class/ClassLoader level.**

Therefore, **a Spring singleton does not mean there is only one object per Java class across the entire JVM**. The same class can legitimately yield multiple Spring singletons if there are multiple bean definitions or multiple containers.

## 2. Comparison Table

| Aspect | Spring singleton | GoF Singleton |
|---|---|---|
| Unit of management | Bean definition (bean name/identifier) inside an IoC container | Class with self-controlled instantiation logic |
| Typical boundary | Per container, per bean | Per ClassLoader for typical GoF implementations |
| Who manages the instance? | Spring `BeanFactory`/`ApplicationContext` | Class code (static field, factory method, enum, etc.) |
| How to obtain an instance | Dependency injection, or `context.getBean(...)` | Usually calling `MySingleton.getInstance()` or an enum constant |
| Constructor | Can be public and accept dependencies via constructor | Usually private to block external `new` |
| Two beans of the same Java class | **Can be two different instances** if registered as two beans | A GoF implementation typically targets one instance for that class |
| Two different Spring contexts | Each context can manage its own instance | A typical static singleton may be shared if both contexts use the same class loaded by the same ClassLoader |
| Configuration and DI | Built-in dependency management, configuration, initialization, and bean destruction | Must manually design how dependencies, initialization, and cleanup are supplied |
| Replacement in unit tests | Easy to inject mocks/fakes or declare alternative beans | Global static calls make substitution and test isolation harder |
| Thread-safety guarantee for state | **Not automatic** | **Not automatic**; thread-safe initialization alone does not make every method thread-safe |
| When appropriate? | Services, repositories, and collaborators managed by Spring | Framework-independent components that genuinely need a static access point |

`@Singleton` is not the mechanism to choose standard scope in the Spring Framework: the usual approach is leaving the default or declaring `@Scope("singleton")`. If a class is simultaneously a GoF Singleton and registered as a Spring bean, the two mechanisms do not automatically align their boundaries with each other.

## 3. How does a Spring singleton work?

Suppose Spring has a bean named `paymentService`. Within the same `ApplicationContext`, places requesting **that bean** via injection or `getBean("paymentService")` share the Spring-managed reference.

```text
ApplicationContext A
├── bean definition: paymentService  ──> PaymentService object #1
│                                      ↑      ↑       ↑
│                                      |      |       |
│                                  Controller Service Job
└── bean definition: backupService   ──> PaymentService object #2

ApplicationContext B
└── bean definition: paymentService  ──> PaymentService object #3
```

All three objects above can have the exact same type `PaymentService`. The singleton rule is still satisfied: each bean definition belonging to a container has only one managed instance at a time according to its corresponding lifecycle.

### 3.1. Declaration in a Spring application

A bean created with `@Component`, `@Service`, `@Repository`, or a `@Bean` method has the default `singleton` scope unless another scope is declared:

```java
@Service
public class CatalogService {
    private final ProductRepository repository;

    public CatalogService(ProductRepository repository) {
        this.repository = repository;
    }

    public Product findById(long id) {
        return repository.findById(id);
    }
}
```

The snippet above is **an illustration of a component in an application that has `ProductRepository`/`Product`**; it is not a standalone program. No private constructor, static `INSTANCE`, or `getInstance()` is needed. The container creates the bean and passes its dependency via the constructor. Multiple controllers using `CatalogService` will normally be injected with the same bean from the context.

Explicit declaration is also valid, though redundant when using the default scope:

```java
@Bean
@Scope(ConfigurableBeanFactory.SCOPE_SINGLETON)
CatalogService catalogService(ProductRepository repository) {
    return new CatalogService(repository);
}
```

If using this declaration, you must import `Bean`, `Scope`, and `ConfigurableBeanFactory`, place the method in a valid `@Configuration` class, and have a `ProductRepository` bean. This is a configuration illustration; do not combine it directly with the `@Service` example above to avoid unintended duplicate bean definitions.

### 3.2. When is the instance created and reused?

Normally, a singleton bean not marked lazy is initialized when `ApplicationContext` refreshes; `@Lazy` can defer initialization until needed. After creation, the container manages the reference and provides the same object again for subsequent requests for the same bean, instead of calling the constructor again on every `getBean()`.

Spring also manages dependency injection and lifecycle callbacks (such as `@PostConstruct`, `@PreDestroy`) according to bean lifecycle rules. When the container closes properly, corresponding destruction callbacks can be invoked. An object created directly with `new` outside Spring does not naturally become a singleton bean.

Note: Spring may return a **proxy** generated by mechanisms such as AOP. When saying `getBean()` returns the same instance, we are comparing the bean reference **provided by the container**; you should not infer from that that the object is always literally the raw implementation class instance without a proxy.

## 4. A GoF Singleton controls object creation itself

A common implementation in Java 17+ is the *initialization-on-demand holder*. The JVM ensures class initialization is properly synchronized, so this approach is lazy and initializes safely without manually adding `synchronized` around every call:

```java
public final class SettingsRegistry {
    private SettingsRegistry() {
    }

    private static final class Holder {
        private static final SettingsRegistry INSTANCE =
                new SettingsRegistry();
    }

    public static SettingsRegistry getInstance() {
        return Holder.INSTANCE;
    }
}
```

Every place using the `SettingsRegistry` class from the same ClassLoader will normally receive the same object when calling `getInstance()`. The private constructor prevents ordinary `new SettingsRegistry()` calls from outside the class. This is a **self-provided singleton class**; no Spring container is needed to call it.

However, `static` does not mean unique across every process/JVM/ClassLoader. Special interactions with reflection, serialization, cloning, or Java instrumentation must also be considered when designing a strict Singleton. A single-element Java `enum` is a stronger choice for certain singleton identity guarantees, yet it still exists per class/ClassLoader rather than becoming a single instance across a distributed system.

A GoF Singleton that needs a `DataSource`, HTTP client, or environment-dependent configuration must design its own way of supplying those dependencies. Therefore, in a Spring application, forcing every service into a GoF Singleton typically forfeits dependency injection benefits and makes substituting objects in tests difficult.

## 5. Runnable experiment: same bean, different beans, different containers, and GoF

The following example creates **two beans of the same type** in the first context, **the same bean name** in the second context, and then compares them against a GoF Singleton. It does not require Spring Boot, a servlet container, or a database.

Requirements: JDK 17+ and Maven 3.9+.

Structure:

```text
singleton-demo/
├── pom.xml
└── src/main/java/example/SingletonComparison.java
```

File `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>singleton-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.0</version>
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
                <version>3.5.0</version>
            </plugin>
        </plugins>
    </build>
</project>
```

File `src/main/java/example/SingletonComparison.java`:

```java
package example;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public class SingletonComparison {

    public static void main(String[] args) {
        try (var contextA = new AnnotationConfigApplicationContext(AppConfig.class);
             var contextB = new AnnotationConfigApplicationContext(AppConfig.class)) {

            Service a1 = contextA.getBean("primaryService", Service.class);
            Service a2 = contextA.getBean("primaryService", Service.class);
            Service backup = contextA.getBean("backupService", Service.class);
            Service b1 = contextB.getBean("primaryService", Service.class);

            System.out.println("Same bean in context A: " + (a1 == a2));
            System.out.println("Different beans, same class: " + (a1 == backup));
            System.out.println("Same name, different contexts: " + (a1 == b1));

            var global1 = GlobalSettings.getInstance();
            var global2 = GlobalSettings.getInstance();
            System.out.println("GoF getInstance twice: " + (global1 == global2));

            System.out.println("Spring bean scope: " +
                    contextA.isSingleton("primaryService"));
        }
    }

    public static class Service {
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public Service primaryService() {
            return new Service();
        }

        @Bean
        public Service backupService() {
            return new Service();
        }
    }

    public static final class GlobalSettings {
        private GlobalSettings() {
        }

        private static final class Holder {
            private static final GlobalSettings INSTANCE =
                    new GlobalSettings();
        }

        public static GlobalSettings getInstance() {
            return Holder.INSTANCE;
        }
    }
}
```

In the directory containing `pom.xml`, run:

```bash
mvn -q compile exec:java -Dexec.mainClass=example.SingletonComparison
```

Program stdout (ignoring Maven-specific logs if shown by your environment):

```text
Same bean in context A: true
Different beans, same class: false
Same name, different contexts: false
GoF getInstance twice: true
Spring bean scope: true
```

**Explanation of each comparison:**

1. `a1 == a2` is `true`: two requests for the same `primaryService` in `contextA` retrieve the same Spring singleton.
2. `a1 == backup` is `false`: `primaryService` and `backupService` are two **bean definitions** even though both return `Service`. Each distinct bean still has singleton scope.
3. `a1 == b1` is `false`: two independent `ApplicationContext` instances create each container's own bean of the same name.
4. Two calls to `GlobalSettings.getInstance()` yield `true`: the GoF Singleton uses the same static holder of the loaded class.
5. `isSingleton("primaryService")` is `true`: the container confirms this bean's scope.

This experiment intentionally creates two independent contexts. With a **parent/child context** hierarchy, the child can delegate bean lookup to the parent, so you must verify which container actually owns the bean before concluding that two lookups create two instances.

## 6. Why isn't Spring's singleton scope a thread synchronization mechanism?

A Spring singleton is commonly invoked concurrently by multiple requests, workers, or threads. **Only one instance** is a statement about object identity; **thread-safe** is a statement about correctness under concurrent access.

Example of a dangerous design:

```java
@Service
public class CheckoutService {
    private long currentOrderId; // Shared mutable state across all callers

    public void checkout(long orderId) {
        currentOrderId = orderId;
        // Another thread can overwrite this field before processing finishes.
        charge(currentOrderId);
    }

    private void charge(long orderId) {
        // Call the actual payment gateway here.
    }
}
```

This is **code illustrating a design flaw**, not a standalone runnable example. Request A sets `currentOrderId = 10`; before A calls `charge`, request B can change the field to `20`. A risks processing the wrong order. Switching to a GoF Singleton scope does not solve the issue either.

How to fix when state sharing is unnecessary:

```java
@Service
public class CheckoutService {
    public void checkout(long orderId) {
        charge(orderId); // Use parameters/local variables per invocation.
    }

    private void charge(long orderId) {
        // Call the actual payment gateway here.
    }
}
```

Rule of thumb: keep singleton services **stateless** whenever possible; per-request state should live in parameters, local variables, or an object with the appropriate request lifetime. If shared mutable state is unavoidable, proper synchronization and consistency guarantees (`Atomic*`, locks, immutable design, database/transactions, etc.) are needed regardless of whether you choose Spring or GoF.

## 7. Common misconceptions and how to check

### "Does a singleton `@Service` mean there is only one object of that class in the application?"

Not necessarily. `@Service` normally registers one singleton bean in the actual container scanning the component. However, you can still create an object with `new`, define another bean via `@Bean`, or create another container. What Spring controls is **managed beans**, not every object of the same class.

### "Are `@Scope("singleton")` and GoF's private constructor equivalent?"

No. `@Scope` tells Spring how to manage the bean; a private constructor is a Java design measure to restrict external object instantiation. A Spring singleton bean can have a public constructor, and `@Scope("singleton")` does not make that constructor private.

### "Does a Spring singleton automatically exist across every server/pod?"

No. Each application JVM/container has its own objects and registry. In a system with multiple replicas, a singleton neither stores shared state across replicas nor ensures a cluster-wide task runs only once. Distributed problems require external storage, locks, or another coordination mechanism.

### "If a `prototype` is injected into a `singleton`, will each method call receive a new prototype?"

No. With normal constructor/field injection, the `prototype` dependency is resolved **when Spring builds the singleton**, so the singleton retains the initially injected instance. If a fresh instance is needed per operation, you can inject `ObjectProvider<PrototypeType>` and call `getObject()` when needed. This is dependency injection and bean scope behavior, not a property of the GoF Singleton.

### "Does calling `getBean()` twice always return the same object?"

Only in qualified contexts: **same container and same singleton bean**, with no special overriding logic. For `prototype` or a different context, you must not assume so. Do not test with `equals()` when you need to check reference identity: use `==`. `context.isSingleton(beanName)` checks scope, while `==` checks whether two retrieved references point to the same object.

### "Are Spring singletons always initialized right when the application starts?"

Not entirely. By default, singletons are normally eager-initialized during context refresh, yet `@Lazy` can defer them. Creation time and instance count are **two different conceptual axes**.

## 8. Which solution should you choose in practice?

In a Spring project, prefer letting Spring manage `@Service`, `@Repository`, `@Component`, or objects returned by `@Bean`, passing dependencies via constructor, and using the default singleton when the service holds no per-request state. This makes lifecycle, environment-specific configuration, and test substitution clear.

Only choose a GoF Singleton intentionally when you need an entity independent of the IoC container with a static API and have weighed the impacts on testability, lifecycle, concurrency, and ClassLoaders. There is no need to implement `private static INSTANCE` inside every Spring `@Service`: it usually creates **two confusing layers of instance management** while bypassing DI.

**Self-check checklist:**

- Same **bean name**, same **container**, singleton scope → same reference provided by Spring.
- Two **bean names** with two instantiations of the same class → can be two different singletons.
- Two **independent containers** → each container has its own singleton registry.
- A class implementing **GoF Singleton** → class/ClassLoader-level logic decides the instance, independent of Spring bean names.
- Both mechanisms → require dedicated thread-safety design if the object shares mutable state.

## Official References

- Spring Framework — [Bean Scopes](https://docs.spring.io/spring-framework/reference/core/beans/factory-scopes.html): singleton, prototype, container and bean boundaries.
- Spring Framework — [Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html): declaring and configuring bean scope.
- Spring Framework — [Bean Overview](https://docs.spring.io/spring-framework/reference/core/beans/definition.html): bean definitions and metadata components.
