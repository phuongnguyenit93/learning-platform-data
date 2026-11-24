# Lite Mode and @Configuration(proxyBeanMethods = false) in Spring Core Container

## 1. Learning Objectives

When writing Java configuration for Spring, the two declarations below both create bean definitions, yet **differ in behavior when one `@Bean` method calls another `@Bean` method**:

```java
@Configuration
class FullConfig {
    // @Bean methods
}
```

```java
@Configuration(proxyBeanMethods = false)
class LiteConfig {
    // @Bean methods
}
```

By default, `@Configuration` has `proxyBeanMethods = true`. Spring processes this class in **full configuration mode**: enhancing the configuration object with a CGLIB-based subclass so that a call to a `@Bean` method on the Spring-managed configuration object can be redirected into a request to fetch the bean from the container, thereby preserving scope and related behaviors.

When you write `@Configuration(proxyBeanMethods = false)`, you **disable interception of `@Bean` method calls**. Spring still registers the bean definitions and manages the beans it creates, yet if in Java code you call `anotherBean()` yourself, that is just a **normal Java call**, not an implicit `BeanFactory.getBean(...)`. Spring calls this **lite mode**; `@Bean` methods located inside plain `@Component` classes also fall into the lite category.

After this lesson, you will:

- Distinguish **full `@Configuration`**, **`@Configuration(proxyBeanMethods=false)`**, and **`@Bean` inside a plain `@Component`**.
- Understand exactly when Spring preserves singleton identity, scope, and bean lifecycle, and when a direct call creates an object outside the container.
- Know why **`@Bean` method parameters** are the safe way to express inter-bean dependencies in both modes.
- Know the pros, cons, and technical constraints of CGLIB enhancement.
- Distinguish `proxyBeanMethods` from Spring AOP proxies, `@Lazy`, `@Scope`, and `ObjectProvider`.
- Run a plain Java 17 + Spring Framework example and read verifiable output.
- Migrate full configurations to lite without silently altering behavior.

**Core message:** Lite mode **does not disable Spring bean management**. It simply does not intercept **direct Java calls between `@Bean` methods**. To pass the right container-managed bean, declare dependencies via **factory method parameters** or another appropriate dependency injection mechanism.

## 2. `@Configuration` and `@Bean` Still Work in Lite Mode

`@Configuration` marks a source of Java configuration; `@Bean` declares a factory method that the container uses to create and manage a bean. Illustrative example (requiring `Catalog` and `CatalogConsumer` definitions):

```java
@Configuration(proxyBeanMethods = false)
class CatalogConfig {
    @Bean Catalog catalog() { return new Catalog(); }
    @Bean CatalogConsumer consumer(Catalog catalog) {
        return new CatalogConsumer(catalog);
    }
}
```

Spring still registers two bean definitions and resolves the `Catalog` parameter through the BeanFactory. Distinguish **registering definitions**, **container invoking factory methods**, and **Java code calling factory methods directly**; only the last case is directly affected by `proxyBeanMethods`.

## 3. Full Mode: Foundation for Understanding Lite Mode

`@Configuration` defaults to `proxyBeanMethods=true`; Spring can generate a CGLIB subclass to intercept eligible instance `@Bean` method calls on the enhanced configuration object.

```java
@Configuration
class FullConfig {
    @Bean Catalog catalog() { return new Catalog(); }
    @Bean CatalogConsumer consumer() {
        return new CatalogConsumer(catalog());
    }
}
```

This illustrative example uses two types `Catalog`/`CatalogConsumer`. In full mode, `catalog()` called from `consumer()` on the enhanced config can be turned into a `catalog` bean lookup, preserving the singleton reference or appropriate scope. In lite mode, it is an ordinary Java call and can construct another object.

### Conditions required for interception to occur

Interception is tied to the **Spring-managed and enhanced configuration bean**; `new FullConfig().catalog()` outside the context lacks those semantics. `static @Bean` lacks virtual dispatch for CGLIB to override. This lesson continues with using lite mode and refactoring dependencies; the full-mode lesson and factory-method constraints lesson go deeper into CGLIB.

## 4. What Is Lite Mode?

In Spring, a `@Bean` method is processed in **lite mode** when:

- It resides in a class **without `@Configuration`**, yet that class is a Spring-processed component, such as a `@Component` bean.
- Or it resides in a class with `@Configuration(proxyBeanMethods = false)`.

The clearest lite example:

```java
@Configuration(proxyBeanMethods = false)
class LiteConfig {

    @Bean
    Catalog catalog() {
        return new Catalog();
    }

    @Bean
    CatalogConsumer consumer() {
        return new CatalogConsumer(catalog());
    }
}
```

Spring still registers the two beans `catalog` and `consumer`. Inside `consumer()`, however, the `catalog()` call is not intercepted. When Java executes `new CatalogConsumer(catalog())`, `catalog()` can create **a separate `Catalog`**, outside the instance Spring manages under the bean name `catalog`.

Notable points:

- The container still holds **one `catalog` singleton bean** under the default singleton scope.
- The object created by the direct `catalog()` call inside `consumer()` may **not** be that singleton.
- The directly created object does not automatically receive `BeanPostProcessor`s, proxies, init/destroy callbacks, or the `catalog` bean definition's scope.
- Two objects sharing the `Catalog` class does not make them the same managed bean.
- `@Configuration(proxyBeanMethods=false)` is still a configuration annotation, can still be found by component scanning, and can still declare `@Import`, `@Bean`, or related metadata as usual.

Spring uses the word "lite" to refer to **processing factory methods without CGLIB inter-bean interception**, not turning off dependency injection or downgrading beans into "unmanaged objects".

### Lite @Bean in a plain @Component

```java
@Component
class CatalogFactoryComponent {

    @Bean
    Catalog catalog() {
        return new Catalog();
    }

    @Bean
    CatalogConsumer consumer() {
        return new CatalogConsumer(catalog());
    }
}
```

These snippets use `org.springframework.stereotype.Component` and must be **registered or discovered** in the context to take effect. Because the class is only a regular `@Component`, the factory methods are **lite `@Bean`s**. Calling `catalog()` from `consumer()` has plain Java semantics just like `LiteConfig`.

You do not need to turn every class containing `@Bean` into `@Configuration` if it is meant to be an ordinary component, yet when a class primarily serves to configure bean definitions, `@Configuration(proxyBeanMethods=false)` makes intent clearer.

## 5. Comparing Full and Lite by Concrete Contract

| Aspect | Full `@Configuration` | Lite `@Configuration(proxyBeanMethods=false)` or plain `@Component` |
| --- | --- | --- |
| `@Bean` methods registered in container | Yes | Yes |
| Beans managed by Spring when created by container | Yes | Yes |
| Scoped/lifecycle semantics of `context.getBean(...)` | Yes | Yes |
| CGLIB enhances configuration class to intercept bean methods | Yes | Does not use this enhancement |
| One `@Bean` method calls `otherBean()` directly | Can be intercepted via BeanFactory | Just a plain Java call |
| Can create extra objects outside container on direct method call | Yes if called on an **unenhanced instance** or non-intercepted case | Yes, even when called from another factory method |
| Factory method accepts Spring-injected dependency parameters | Yes | Yes |
| Must obey `final`/`private` subclassing constraints on intercepted methods | Yes | Relaxed because no inter-bean subclass is needed |
| Used to define independent beans that do not call each other | Yes | Yes, often a clean choice |
| Suitable for code intentionally using direct inter-bean method calls | Yes, when full-mode conditions are understood | No |

**Note on optimization:** `proxyBeanMethods=false` can avoid the cost of generating a CGLIB subclass for the configuration class, reducing footprint/enhancement overhead. This is often a sensible configuration optimization, yet you should **not** switch merely to be "faster" before auditing all direct calls between `@Bean` methods.

## 6. Writing Properly in Both Full and Lite: Injecting Dependencies via @Bean Parameters

This is the preferred pattern:

```java
@Configuration(proxyBeanMethods = false)
class SafeConfig {

    @Bean
    Catalog catalog() {
        return new Catalog();
    }

    @Bean
    CatalogConsumer consumer(Catalog catalog) {
        return new CatalogConsumer(catalog);
    }
}
```

`Catalog` is an illustrative application class. When Spring invokes the `consumer(Catalog catalog)` factory method, Spring **resolves the `Catalog` parameter through the container**:

1. The container knows `consumer` needs a bean of type `Catalog`.
2. Spring looks up `Catalog` candidates by type, qualifier, primary, generics, and other rules.
3. Under the default singleton scope, it passes the existing `catalog` singleton bean or creates it through the proper mechanism.
4. `CatalogConsumer` receives a reference to the **managed bean**, not another object constructed by a direct method call.

This style works in:

- Full `@Configuration(proxyBeanMethods=true)`.
- Lite `@Configuration(proxyBeanMethods=false)`.
- Lite `@Bean` methods in regular `@Component`s.
- Multi-class configurations when the dependency bean is registered/imported into the same context.

**Major advantage:** dependencies appear right in the method signature, easy to find, easy to test, and without relying on CGLIB to maintain bean identity.

### Pattern to avoid in lite mode

```java
@Bean
CatalogConsumer consumer() {
    return new CatalogConsumer(catalog()); // Plain Java call.
}
```

### Recommended pattern

```java
@Bean
CatalogConsumer consumer(Catalog catalog) {
    return new CatalogConsumer(catalog); // Spring injects the bean.
}
```

Even if code currently runs in full mode, switching from direct calls to method parameters upfront makes configuration safer if you later switch to lite mode.

## 7. Runnable Java 17 Example: Comparing Full, Lite, and @Component

The standalone example below uses Spring Framework 6.2 and needs no Spring Boot. Each mode is created in a **separate ApplicationContext** to avoid bean-name and type collisions.

The program checks three outcomes:

- How many times the `catalog()` factory method actually runs.
- Whether `directConsumer()` receives the container-managed `Catalog` singleton.
- Whether `injectedConsumer(Catalog catalog)` receives the Spring-injected singleton.

### 7.1. Project structure

```text
spring-lite-configuration/
├── pom.xml
└── src/main/java/demo/LiteConfigurationDemo.java
```

### 7.2. POM for Java 17

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>spring-lite-configuration</artifactId>
    <version>1.0-SNAPSHOT</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.18</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
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

### 7.3. Complete source code

Create `src/main/java/demo/LiteConfigurationDemo.java`:

```java
package demo;

import java.util.function.IntSupplier;

import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.stereotype.Component;

public class LiteConfigurationDemo {

    static final class Catalog {
    }

    static final class CatalogConsumer {
        private final Catalog catalog;

        CatalogConsumer(Catalog catalog) {
            this.catalog = catalog;
        }

        Catalog catalog() {
            return catalog;
        }
    }

    private static int fullCalls;
    private static int liteCalls;
    private static int componentCalls;

    @Configuration
    static class FullConfig {

        @Bean
        Catalog catalog() {
            fullCalls++;
            return new Catalog();
        }

        @Bean
        CatalogConsumer directConsumer() {
            return new CatalogConsumer(catalog());
        }

        @Bean
        CatalogConsumer injectedConsumer(Catalog catalog) {
            return new CatalogConsumer(catalog);
        }
    }

    @Configuration(proxyBeanMethods = false)
    static class LiteConfig {

        @Bean
        Catalog catalog() {
            liteCalls++;
            return new Catalog();
        }

        @Bean
        CatalogConsumer directConsumer() {
            return new CatalogConsumer(catalog());
        }

        @Bean
        CatalogConsumer injectedConsumer(Catalog catalog) {
            return new CatalogConsumer(catalog);
        }
    }

    @Component
    static class ComponentFactory {

        @Bean
        Catalog catalog() {
            componentCalls++;
            return new Catalog();
        }

        @Bean
        CatalogConsumer directConsumer() {
            return new CatalogConsumer(catalog());
        }

        @Bean
        CatalogConsumer injectedConsumer(Catalog catalog) {
            return new CatalogConsumer(catalog);
        }
    }

    private static void report(
            String label, Class<?> configurationClass, IntSupplier calls) {

        try (var context = new AnnotationConfigApplicationContext(
                configurationClass)) {

            Catalog managed = context.getBean(Catalog.class);
            CatalogConsumer direct =
                    context.getBean("directConsumer", CatalogConsumer.class);
            CatalogConsumer injected =
                    context.getBean("injectedConsumer", CatalogConsumer.class);

            System.out.println(label + ".factoryCalls=" + calls.getAsInt());
            System.out.println(label + ".directIsManaged=" +
                    (direct.catalog() == managed));
            System.out.println(label + ".parameterIsManaged=" +
                    (injected.catalog() == managed));
        }
    }

    public static void main(String[] args) {
        report("full", FullConfig.class, () -> fullCalls);
        report("lite", LiteConfig.class, () -> liteCalls);
        report("component", ComponentFactory.class, () -> componentCalls);
    }
}
```

**Structural explanation:** Each context registers one configuration/component class and has exactly one `Catalog` bean and two `CatalogConsumer` beans named `directConsumer` and `injectedConsumer`. We look up the consumers **by name with type** to avoid ambiguity because two beans share the `CatalogConsumer` type.

`FullConfig` is not `final`, and its `@Bean` instance methods are not `final`/`private`; thus it can be enhanced by Spring for full mode. `LiteConfig` disables enhancement, while `ComponentFactory` is registered directly in the context so Spring processes its `@Bean` methods in lite mode, even without enabling component scanning in the example.

### 7.4. Run command

Run in the directory containing `pom.xml`:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.LiteConfigurationDemo
```

Requires JDK 17+ and Maven. **Lines printed by the program itself** (excluding Spring/Maven logs if the environment configures logging differently):

```text
full.factoryCalls=1
full.directIsManaged=true
full.parameterIsManaged=true
lite.factoryCalls=2
lite.directIsManaged=false
lite.parameterIsManaged=true
component.factoryCalls=2
component.directIsManaged=false
component.parameterIsManaged=true
```

### 7.5. Why is full.factoryCalls = 1?

In full mode, `catalog()` is intercepted by Spring when called from `directConsumer()` to fetch the singleton bean. The container only needs to run the factory logic to create one managed `Catalog` bean. Creating `injectedConsumer(Catalog catalog)` likewise resolves the existing singleton.

Result:

- `full.directIsManaged=true`.
- `full.parameterIsManaged=true`.
- `full.factoryCalls=1`.

Important point: `true` for the direct call only holds because it happens on the **Spring-enhanced configuration instance** under full semantics. If you call `new FullConfig().catalog()` yourself, CGLIB does not intercept that instance.

### 7.6. Why is lite.factoryCalls = 2?

In lite mode:

1. Spring creates the `catalog` bean through the factory method once under singleton scope.
2. When creating `directConsumer`, code inside the method calls `catalog()` directly in Java, running the factory logic one more time to construct a **different** `Catalog`.
3. When creating `injectedConsumer`, Spring passes the container-managed `Catalog` bean via the parameter.

Therefore:

- `lite.directIsManaged=false`: the consumer built via direct call holds an object outside the managed bean.
- `lite.parameterIsManaged=true`: the consumer via parameter holds the true singleton.
- `lite.factoryCalls=2`: once by BeanFactory creating the bean, once by the direct Java call.

Even if Spring instantiates singletons in a different order, total factory method calls remain 2 in this example, since there is one `Catalog` bean definition and exactly one direct call from `directConsumer`.

### 7.7. Why does @Component also yield lite results?

`ComponentFactory` lacks `@Configuration`. Although it has `@Bean` methods and was registered in the context, Spring does not enhance it to intercept calls between bean methods. Hence it shows the same direct Java call behavior as `LiteConfig`:

- `component.factoryCalls=2`.
- `component.directIsManaged=false`.
- `component.parameterIsManaged=true`.

This example proves **lite mode does not mean "@Bean was not found"**. All three contexts create the `Catalog` bean and both `CatalogConsumer` beans; the difference lies in how references are resolved inside direct method calls.

## 8. Auditing Code Before Switching from Full to Lite

Suppose the current configuration is:

```java
@Configuration
class OriginalConfig {

    @Bean
    DataSource dataSource() {
        return createDataSource();
    }

    @Bean
    UserRepository userRepository() {
        return new JdbcUserRepository(dataSource());
    }

    @Bean
    UserService userService() {
        return new UserService(userRepository());
    }
}
```

This is an **illustrative snippet**, requiring declarations for `DataSource`, `JdbcUserRepository`, `UserRepository`, and `UserService`. It works with full inter-bean method references when properly managed by Spring.

If you merely add `proxyBeanMethods = false` **without fixing** the two calls `dataSource()` and `userRepository()`, you risk creating:

- An out-of-container `UserRepository` while Spring still registers a separate `userRepository` bean.
- An out-of-container `DataSource` for the manually constructed repository instance.
- Objects bypassed by lifecycle handling, transactions/proxies, init/destroy callbacks, or bean definition scopes.
- Multiple unintended connection pools or clients, wasting resources and breaking cleanup.

### Safe refactoring approach

```java
@Configuration(proxyBeanMethods = false)
class SafeConfig {

    @Bean
    DataSource dataSource() {
        return createDataSource();
    }

    @Bean
    UserRepository userRepository(DataSource dataSource) {
        return new JdbcUserRepository(dataSource);
    }

    @Bean
    UserService userService(UserRepository userRepository) {
        return new UserService(userRepository);
    }
}
```

Dependent objects are injected through parameters. This is also a design less coupled to interception mechanics. If a bean needs a parameter from another configuration, Spring still resolves it by type/qualifier within **the same context**, provided the bean definitions are registered.

### Checklist for finding inter-bean direct calls

Before enabling lite mode:

- Search for all `anotherBeanMethod()` calls inside `@Bean` methods.
- Search for similar calls in helper methods invoked from `@Bean`.
- Search for `this.anotherBeanMethod()`, method references, or calls through a reference to the config object.
- Inspect bean methods returning resources like `DataSource`, `Executor`, `Client`, `SessionFactory`, or `ConnectionFactory`, since an extra instance can have major operational consequences.
- Convert dependencies into **`@Bean` parameters**, constructor injection, factories, or `ObjectProvider` when per-use lookup is needed.
- Write integration tests verifying managed bean identity, lifecycle, instance counts, and failure paths.
- Only then change `@Configuration` to `@Configuration(proxyBeanMethods=false)`.

Note: not every method call inside a configuration class is a bug. Calling a **non-`@Bean` helper method** to parse properties or build a value object inside a factory is usually valid; the risky spot is calling a **method used as a Spring bean factory** and assuming the return value is a managed bean.

## 9. Scope: Why Direct Calls Are More Dangerous Than Just Creating Two Singletons

Bean scope is a BeanFactory contract. Even though a Java method always returns `new Catalog()`, the container can manage it as a singleton, prototype, or scoped proxy depending on the bean definition.

### 9.1. Singleton

```java
@Bean
Catalog catalog() {
    return new Catalog();
}
```

By default, this bean has singleton scope within **one ApplicationContext**. Calling `context.getBean(Catalog.class)` twice normally returns the same instance. Yet `catalog()` called directly in lite mode is a Java method call and can construct a new object outside the managed singleton.

So do not conclude: "Any method with `@Bean` always returns a singleton however you call it." Singleton is a rule for **fetching beans through the container**, not a promise that every Java invocation of the factory method returns the same object.

### 9.2. Prototype

```java
@Bean
@Scope("prototype")
TaskWorker taskWorker() {
    return new TaskWorker();
}
```

This is an **illustrative snippet** requiring `TaskWorker`, `@Scope` import, and valid configuration. When Spring resolves a prototype bean through the container, it creates an instance per request. A lite direct call `taskWorker()` can also construct a new object, yet the directly invoked object **does not automatically receive Spring bean management**.

The coincidence that "every call yields a new object" does **not** make the two mechanisms equivalent. For instance, post-processing, dependency injection, bean init callbacks, scope-aware proxies, or Spring type conversion are not automatically applied to directly created objects.

If a singleton service needs a fresh prototype worker on each operation, consider `ObjectProvider<TaskWorker>` or a dedicated factory, rather than relying on direct `@Bean` calls in lite mode.

### 9.3. Request/session scope

When using web scopes or scoped proxies, resolving a bean through the container can depend on the active request/session. A direct method call in lite mode bypasses finding the Spring-managed target/proxy. It not only produces the wrong identity but can also corrupt **business context and lifecycle**, especially when the object holds session state.

For complex scopes, always write code that receives dependencies via injection/`ObjectProvider` honoring the scope contract.

## 10. Lifecycle and BeanPostProcessor

When Spring creates a bean via a `@Bean` method, it can:

- Resolve dependencies and apply applicable callbacks.
- Run `BeanPostProcessor`s before/after initialization.
- Apply AOP proxying if the corresponding infrastructure is enabled.
- Invoke `initMethod` or configured initialization callbacks.
- For eligible singletons, invoke `destroyMethod` when the context closes.
- Enforce relevant scope and lifecycle rules.

Look at:

```java
@Configuration(proxyBeanMethods = false)
class ResourceConfig {

    @Bean(initMethod = "open", destroyMethod = "close")
    ResourceClient resourceClient() {
        return new ResourceClient();
    }

    @Bean
    WorkService workService(ResourceClient client) {
        return new WorkService(client);
    }
}
```

This is an illustration requiring definitions for `ResourceClient.open()/close()` and `WorkService`. When Spring creates `resourceClient`, the bean runs its init callback and can then be passed into `workService`. Later, Spring runs the destroy callback when the container closes if the bean is a container-owned singleton.

**Counter-example:**

```java
@Bean
WorkService workService() {
    return new WorkService(resourceClient());
}
```

In lite mode, `resourceClient()` inside `workService()` runs the factory code itself; the created object **is not automatically processed by BeanFactory as the `resourceClient` bean**. If `open` must run before use, the extra object may remain uninitialized; if it holds resources that must be closed, that object may miss the bean definition's destroy callback. This is why lifecycle bugs are often harder to spot than singleton identity bugs.

### Does lite disable lifecycle for @Bean?

**No.** When Spring directly calls `resourceClient()` to create the `resourceClient` bean definition, that instance **still receives** full configured lifecycle handling. Only objects created through **Java calls not resolved by the container as beans** miss management under that bean definition.

## 11. proxyBeanMethods Is Not a Spring AOP Switch

The attribute name `proxyBeanMethods` easily misleads learners into thinking it "turns all proxies on/off". In reality it only controls **proxying `@Bean` methods on the configuration class**; it does not directly govern:

- Whether Spring AOP creates proxies for services.
- Whether `@Transactional` is applied to services.
- Whether scoped proxies are generated.
- Whether JDK dynamic proxies or class-based proxies are used for a business bean.
- Whether method security is enabled.

Example of a `@Service` receiving an object supplied by `@Bean`:

```java
@Configuration(proxyBeanMethods = false)
class DatabaseConfig {

    @Bean
    DataSource dataSource() {
        return createDataSource();
    }
}
```

Disabling configuration method proxying by itself **does not disable** Spring AOP/transaction proxies on another service. Those proxies depend on annotations, advisors, transaction managers, and actual infrastructure.

Conversely, even if full config has `proxyBeanMethods=true`, you cannot infer that every business method in every bean is AOP-intercepted. These are **two proxy mechanisms with different purposes**.

### Self-invocation in two different contexts

- In **full `@Configuration`**, a call from one `@Bean` method to another `@Bean` method on the enhanced configuration instance can be intercepted by configuration CGLIB to return a managed bean.
- In regular **Spring AOP proxy mode**, self-invocation from one target method to another method on the same target can **bypass advice** because the call does not go through the external proxy.

Do not take AOP self-invocation rules and claim full `@Configuration` always skips interception; conversely, do not take `@Bean` interception to infer that `@Transactional` self-invocation will work.

## 12. CGLIB: Benefits and Constraints

Full mode requires subclassing/method interception, bringing notable constraints:

### Configuration class cannot be final

```java
// Counter-example in full mode:
@Configuration
public final class FinalFullConfig {
    @Bean
    Catalog catalog() {
        return new Catalog();
    }
}
```

CGLIB cannot subclass a `final` class. If full interception is genuinely needed, the configuration class and any instance `@Bean` methods needing override must satisfy Spring/CGLIB constraints.

### Private/final @Bean methods

```java
// Counter-example for a method requiring full interception:
@Configuration
class FullConfig {
    @Bean
    private final Catalog catalog() {
        return new Catalog();
    }
}
```

A `private` or `final` method cannot be overridden by CGLIB in the way required for an intercepted bean method; in full mode the configuration can be invalid. Do not use them assuming Spring can still intercept the method call normally.

### Lite mode relaxes subclassing constraints

When `proxyBeanMethods` is disabled, Spring **does not need to subclass the configuration class to intercept bean methods**, so several enhancement restrictions are relaxed. This helps with immutable/final classes or code generated by other compilers, provided Java, `@Bean` factory method, and container rules are still met.

Usable example:

```java
@Configuration(proxyBeanMethods = false)
public final class ImmutableConfig {
    @Bean
    public Catalog catalog() {
        return new Catalog();
    }
}
```

This is a **separate illustration**, not part of the full runnable Java file. Lite mode allows `final` from the standpoint of not needing CGLIB subclassing. However, do not use this as a reason to justify direct calls between bean factory methods; lifecycle/DI constraints from earlier still apply.

### No need to manually add external CGLIB dependencies

Spring Framework already bundles/repackages the needed CGLIB components inside `spring-core`. You do not have to add a separate CGLIB library just to make full `@Configuration` work. What matters is that classes/methods are valid for enhancement and Spring/JDK versions are compatible.

## 13. Lite Mode and static @Bean

Spring permits declaring certain `@Bean` methods as `static`. Static methods do not require a config instance to invoke, nor are they targets for instance-method interception:

```java
@Configuration(proxyBeanMethods = false)
class InfrastructureConfig {

    @Bean
    static CustomRegistryPostProcessor customRegistryPostProcessor() {
        return new CustomRegistryPostProcessor();
    }
}
```

This illustrative snippet requires defining `CustomRegistryPostProcessor`; it is not a standalone program. Static `@Bean` is useful for infrastructure beans needed **very early** during container bootstrap, especially eligible `BeanFactoryPostProcessor`/`BeanDefinitionRegistryPostProcessor` types.

Reason: Spring can call the static factory method **without forcing early instantiation of the configuration instance**, avoiding certain issues with dependency injection or BeanPostProcessors on the configuration class itself.

Still, `static` does not automatically make a bean singleton/prototype or turn it into an unmanaged object. The container continues to rely on bean definitions, scope, and lifecycle. Only calls like `InfrastructureConfig.customRegistryPostProcessor()` invoked directly by Java code are direct static factory calls rather than managed singleton lookups.

Do not convert all bean methods to static just because you use lite mode. This is an infrastructure technique for specific scenarios.

## 14. @Import, @ComponentScan, and Multiple Configuration Classes

Lite mode does not restrict composing configurations with `@Import`:

```java
@Configuration(proxyBeanMethods = false)
class RepositoryConfig {

    @Bean
    OrderRepository orderRepository() {
        return new InMemoryOrderRepository();
    }
}

@Configuration(proxyBeanMethods = false)
@Import(RepositoryConfig.class)
class ServiceConfig {

    @Bean
    OrderService orderService(OrderRepository repository) {
        return new OrderService(repository);
    }
}
```

This is an illustrative example requiring the corresponding interfaces/implementations and importing `org.springframework.context.annotation.Import`. When registering `ServiceConfig`, Spring imports `RepositoryConfig` and can inject `OrderRepository` via `orderService(...)`'s parameter.

Here, there is **no need** to write:

```java
// Counter-example with an unmanaged config:
@Bean
OrderService orderService() {
    return new OrderService(new RepositoryConfig().orderRepository());
}
```

That snippet constructs `RepositoryConfig` outside the container and calls the factory directly, risking creating a repository outside managed bean identity/lifecycle.

`@ComponentScan` also remains meaningful:

```java
@Configuration(proxyBeanMethods = false)
@ComponentScan(basePackages = "com.example.application")
class ApplicationConfig {
}
```

Stereotyped classes within the scan area are registered as usual; lite mode **does not disable component scanning**. Distinguish whether a configuration class is **registered in the context** from whether Spring intercepts `@Bean` methods on that class.

## 15. Optional Dependencies and Multiple Beans in Lite Mode

`@Bean` method parameters are resolved by Spring using standard dependency injection. You can use:

### Required dependency

```java
@Bean
PaymentService paymentService(PaymentGateway gateway) {
    return new PaymentService(gateway);
}
```

Missing a matching `PaymentGateway` bean is a configuration error; Spring typically fails when creating `paymentService`.

### Optional dependency

```java
@Bean
ReportService reportService(
        java.util.Optional<AuditSink> auditSink) {
    return new ReportService(auditSink);
}
```

If no `AuditSink` bean exists, the `Optional` can be empty, provided the dependency is genuinely optional in business logic. Lite mode does not automatically turn every dependency into optional.

### Multiple candidates

```java
@Bean
Pipeline pipeline(java.util.List<PipelineStep> steps) {
    return new Pipeline(steps);
}
```

Spring can gather multiple `PipelineStep` beans into a list per collection injection rules. If the pipeline needs explicit ordering, configure `@Order`/`Ordered` and test; if dynamic lookup of 0..n beans is needed, consider `ObjectProvider<PipelineStep>`.

**Key point:** Constructor/factory-method parameter injection works in both full and lite. `proxyBeanMethods=false` does not make Spring ignore `@Qualifier`, generic types, `@Primary`, dependency resolution, or lifecycle.

## 16. Understanding Performance and Bootstrapping Accurately

A common reason to use lite configuration is avoiding CGLIB enhancement for configuration classes when inter-bean calls are unnecessary. This can:

- Reduce the number of proxy/enhanced classes generated at startup.
- Reduce overhead during the configuration phase.
- Avoid subclassing constraints with `final` classes/methods.
- Make wiring contracts more consistent by always using method parameter injection.

However, there is **no universal speedup number** across all applications. Startup time also depends on classpath scanning, bean count, connection pool creation, I/O, and other components. An application with only a few `@Bean` methods may see no noticeable difference.

More importantly, switching full to lite **can alter behavior** if existing code relies on inter-bean method interception. Prioritize correct semantics first; measure performance afterward with real benchmarks.

### About Spring Boot

Spring Boot uses many Java configurations, and several auto-configurations are declared with `proxyBeanMethods=false` because their bean factory methods can be designed independently and accept dependencies via parameters. That does not turn the entire Boot application into lite mode automatically; each configuration class carries its own metadata.

`@SpringBootApplication(proxyBeanMethods = false)` is a Boot option configuring how bean methods are processed on **the annotated application class**, not a global switch toggling all Spring AOP or forcing the flag onto every imported configuration class. That is a conceptual boundary; the main Maven example in section 7 uses plain Spring Framework only.

## 17. Common Errors and How to Diagnose Them

| Symptom | Common Cause | Fix |
| --- | --- | --- |
| Two objects of the same class have `==` false despite singleton bean | Lite config calls a `@Bean` method directly inside another factory | Use method parameter injection and compare with `context.getBean(...)` |
| Init callback ran on only one instance | The other instance was created by a direct Java method call, bypassing BeanFactory | Ensure consumers receive the managed bean |
| Resources opened twice or not all closed | Direct call in lite mode creates a resource unmanaged by the context | Refactor dependency via parameter/factory; verify lifecycle |
| `@Configuration` fails enhancement | Full mode with improper `final` or `private` class/method | Remove enhancement-blocking modifiers or use lite with proper wiring |
| Switched `proxyBeanMethods=false` and tests fail | Legacy code relied on CGLIB redirecting inter-bean calls | Audit and replace direct calls with injection |
| `@Bean` inside `@Component` creates beans yet direct call gives wrong identity | Plain component is already lite mode | Do not call one bean method from another to get a managed bean |
| `NoSuchBeanDefinitionException` on parameter injection | Dependency bean not registered/imported/scanned | Check configuration class, type, qualifier, bean definitions |
| `NoUniqueBeanDefinitionException` | Multiple candidates of the same type without a selection rule | Use `@Qualifier`/`@Primary` or accept a collection if appropriate |
| Bean not lazy despite using provider | Singleton was eagerly initialized by Spring via another mechanism | Check `@Lazy`, scope, eager dependencies |
| Thinking `proxyBeanMethods=false` disables `@Transactional` | Confusing configuration method proxy with AOP proxy | Inspect AOP/transaction infrastructure separately |
| Prototype direct call appears to create new objects yet lifecycle is wrong | Java method returns a new object outside bean post-processing | Resolve prototype via BeanFactory/`ObjectProvider` |
| Test only calls `new LiteConfig().catalog()` | Bypasses container, so managed identity is never tested | Use `AnnotationConfigApplicationContext` in integration tests |

Ordered debugging workflow:

1. Identify whether the class uses **full** (default `@Configuration`), **lite** (`proxyBeanMethods=false`), or plain `@Component`.
2. Locate all `@Bean` factory methods and any direct calls between them.
3. Verify whether the bean obtained via `context.getBean(...)` matches the reference held by the consumer.
4. Distinguish **container singleton beans** from Java objects manually created via `new` or direct method calls.
5. Check lifecycle callbacks and whether the bean is proxied/scoped.
6. Move inter-bean dependencies into factory method parameters.
7. Re-run integration tests before measuring startup optimizations.

## 18. Testing to Prevent Regressions

Key tests when migrating full to lite:

### Testing bean identity

For the section 7 example, assert:

```java
// Verification snippet inside report(...) while context is still open:
Catalog managed = context.getBean(Catalog.class);

CatalogConsumer injected =
        context.getBean("injectedConsumer", CatalogConsumer.class);

if (injected.catalog() != managed) {
    throw new AssertionError(
            "Factory method parameter did not inject managed Catalog");
}
```

This is an additional snippet, not a standalone class. It proves the consumer receives **the exact container-managed instance**, not just an object of the same type.

### Testing lifecycle callbacks

Create a test resource bean with `initMethod` and `destroyMethod`, and verify how many times the managed bean opens/closes on context startup/close. If code constructs an extra resource via direct calls, the test will expose leak risks or missing initialization.

### Testing bean definitions and scope

Call `context.getBean(Catalog.class)` twice to confirm singleton behavior in the context. This **does not replace** testing the identity of the object held inside the consumer: the container singleton remains valid even if a consumer accidentally holds a different unmanaged object.

### Testing multi-module configuration

If a `@Configuration(proxyBeanMethods=false)` depends on a bean from another `@Import`, integration tests should bootstrap the proper root configuration class rather than mocking with `new` and assuming dependency resolution works.

### Testing fail-fast on required dependencies

With parameter `@Bean Consumer consumer(RequiredRepository repo)`, the context must detect a missing `RequiredRepository` when creating the consumer. This is desirable behavior; do not convert required dependencies into `getIfAvailable()` and ignore absence just to make startup tests pass.

## 19. Exercises and Answers

### Exercise 1: Where do the two modes differ?

Both `@Configuration` and `@Configuration(proxyBeanMethods=false)` have `@Bean` methods. Do both create bean definitions? What is the core difference?

**Answer:** Both create bean definitions; beans created by the container are managed normally. The core difference is that full configuration can intercept inter-bean method calls on the enhanced config instance, whereas in lite mode direct calls are ordinary Java method invocations.

### Exercise 2: Predicting identity

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    Worker worker() { return new Worker(); }

    @Bean
    Manager manager() { return new Manager(worker()); }
}
```

Is `Manager` guaranteed to hold the exact singleton `worker` bean returned by `context.getBean(Worker.class)`?

**Answer:** No. `worker()` is called directly inside `manager()`, creating a separate Java object per the method body. Fix by writing `Manager manager(Worker worker) { return new Manager(worker); }`.

### Exercise 3: Working inside @Component

A `@Component` class has two `@Bean` methods and one calls the other. Does Spring automatically intercept it like full `@Configuration`?

**Answer:** No. That is lite `@Bean` processing. Use method parameter injection when the consumer needs a managed bean.

### Exercise 4: Does changing proxyBeanMethods remove @Bean?

You change `@Configuration` to `@Configuration(proxyBeanMethods=false)` and change nothing else. Are the `@Bean` methods still registered?

**Answer:** Yes, provided the configuration class is still loaded properly. However, **direct method call behavior** can change, so audit the code instead of assuming zero impact.

### Exercise 5: Full mode and new Config()

Does `new FullConfig().catalog()` guarantee getting the context's singleton bean?

**Answer:** No. An instance created with `new` is not the container-managed enhanced configuration bean.

### Exercise 6: Prototype

Does a prototype bean obtained by calling a `@Bean` method directly in lite mode automatically receive Spring lifecycle and post-processors?

**Answer:** No. It is only an object created by a Java method. To get a managed prototype, resolve the bean through the container/`ObjectProvider`.

### Exercise 7: Comparing with Spring AOP

Does `proxyBeanMethods=false` mean disabling `@Transactional` proxies?

**Answer:** No. It only disables CGLIB interception for the configuration class's bean factory methods. AOP transaction proxies are a separate mechanism with their own activation conditions.

### Exercise 8: Startup optimization

You have a config with no direct inter-bean calls, and all dependencies are injected via factory method parameters. Which flag can you consider?

**Answer:** `@Configuration(proxyBeanMethods=false)` can reduce enhancement overhead while preserving the exact wiring. Test both managed instances and critical behaviors after switching.

### Exercise 9: static @Bean

Is a `static @Bean` method overridden/intercepted by CGLIB like an instance method in full configuration?

**Answer:** No. Static methods are not virtual instance methods. The container can still manage the bean created via the bean definition, yet direct static calls are plain Java.

### Exercise 10: Fixing multi-tier configuration

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    A a() { return new A(); }

    @Bean
    B b() { return new B(a()); }

    @Bean
    C c() { return new C(b()); }
}
```

Fix it so `B` and `C` use the proper managed dependencies.

**Guided answer:**

```java
@Configuration(proxyBeanMethods = false)
class Config {
    @Bean
    A a() { return new A(); }

    @Bean
    B b(A a) { return new B(a); }

    @Bean
    C c(B b) { return new C(b); }
}
```

Classes `A`, `B`, and `C` are illustrative types; the exercise needs concrete definitions if you want to compile it.

## 20. Pre-Adoption Project Checklist

- [ ] Determine whether CGLIB inter-bean references are genuinely needed.
- [ ] If choosing lite, never write `@Bean x() { return new X(y()); }` just to obtain bean `y`.
- [ ] Move dependencies into factory method parameters or constructor injection.
- [ ] Use `@Qualifier` when multiple beans share the same type.
- [ ] For prototype/scoped beans, resolve via the container/provider rather than calling factory methods directly.
- [ ] Do not assume `proxyBeanMethods=false` disables AOP proxies or lifecycle callbacks.
- [ ] Verify the configuration class is still imported/scanned/registered into the context.
- [ ] When `final` classes/methods are needed, verify the config is processed as lite and all other constraints remain valid.
- [ ] Write tests for identity, initialization, destruction, and critical beans.
- [ ] Verify expensive resources like connection pools, HTTP clients, or executors are not duplicated.
- [ ] Report performance improvements only when backed by measurements, without guessing a fixed speedup.

## Conclusion

**Full `@Configuration`** uses CGLIB to preserve inter-bean method references when `@Bean` methods are called on the Spring-managed enhanced configuration bean. **Lite mode**, including `@Configuration(proxyBeanMethods=false)` and `@Bean` methods inside plain `@Component` classes, does not intercept such direct calls: they behave like ordinary Java methods.

Both modes still provide **bean definitions, dependency resolution, singleton/prototype scopes, and full lifecycles for objects created and managed by Spring**. Bugs arise when code inadvertently creates extra objects via direct factory-method calls and treats them as managed beans.

The most durable rule to apply: **each `@Bean` method should strictly do its own factory job, while dependencies needed from the container should be passed as parameters**. Following this rule lets you adopt lite mode cleanly and reduce the need for CGLIB enhancement without changing dependency identity or lifecycle.

## Official References

- [Spring Framework 6.2 — Basic Concepts: @Bean and @Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/basic-concepts.html): full/lite mode and inter-bean method calls.
- [Spring Framework 6.2 — Using the @Configuration Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/configuration-annotation.html): CGLIB enhancement, scopes, and usage conditions.
- [Spring Framework 6.2 — Using the @Bean Annotation](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java/bean-annotation.html): factory methods, lifecycle, scope, and lite mode.
- [Spring Framework 6.2 — @Configuration Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/Configuration.html): `proxyBeanMethods` contract and subclass constraints.
- [Spring Framework 6.2 — @Bean Javadoc](https://docs.spring.io/spring-framework/docs/6.2.18/javadoc-api/org/springframework/context/annotation/Bean.html): how `@Bean` is processed in full/lite classes.
- [Spring Framework 6.2 — Classpath Scanning and Managed Components](https://docs.spring.io/spring-framework/reference/6.2/core/beans/classpath-scanning.html): `@Bean` inside plain `@Component` and differences from `@Configuration`.
