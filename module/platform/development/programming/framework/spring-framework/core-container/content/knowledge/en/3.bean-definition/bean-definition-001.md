# BeanDefinition Describes How to Create and Manage a Bean — Spring Framework Core Container

## 1. Lesson Objectives

When looking at a snippet of Spring `@Bean` or `@Component`, you might think the container simply "sees the annotation and calls `new`". In reality, Spring first registers **descriptive information for a bean** so it knows *what the bean is named, how it can be created, which dependencies it receives, and what scope/lifecycle it has*. That description is represented by the **`BeanDefinition`** interface in the Spring IoC container.

`BeanDefinition` is not a business object. It is the **metadata/recipe** that `BeanFactory` uses when creating and managing a bean. The fact that Spring knows a bean's metadata **does not mean** a bean instance already exists.

By the end of this lesson, you will be able to:

1. Explain accurately the relationship between `BeanDefinition`, `BeanDefinitionRegistry`, `BeanFactory`, `ApplicationContext`, and a bean instance.
2. Read the important metadata fields: bean name, class/factory method, scope, lazy initialization, dependencies, init/destroy callbacks, and constructor/property values.
3. Distinguish between *registering a definition*, *resolving dependencies*, *creating an instance*, *initializing*, and *destroying a bean*.
4. Understand why `@Bean` and component scanning also create definitions, not only API-based registration calls.
5. Run a **plain Spring Framework + Java 17** example featuring both `@Configuration`/`@Bean` and `BeanDefinitionBuilder` to observe metadata, singleton/prototype, injection, and destroy callbacks.
6. Know when to register bean definitions via API, and avoid errors related to names, types, scopes, registration timing, and metadata access.

**Scope:** This lesson covers the **meaning and usage of BeanDefinition in the Core Container**. You do not need Spring Boot, a web server, AOP, a database, or a custom BeanFactory implementation to understand it.

## 2. Four Easily Confused Objects/Mechanisms

| Concept | What is it? | Question it answers |
| --- | --- | --- |
| `BeanDefinition` | Metadata/configuration describing how Spring creates and manages a bean | "How is this bean defined?" |
| `BeanDefinitionRegistry` | Where bean definitions are registered, looked up, and removed by name | "Which definitions does the container hold?" |
| `BeanFactory` | Mechanism for retrieving/creating/resolving beans according to Spring rules | "When a bean is needed, how do we obtain a suitable instance?" |
| Bean instance | Actual Java object managed by the container according to the definition/scope | "Which object is the service using?" |
| `ApplicationContext` | High-level container interface with registration, lifecycle, events, environment, etc., depending on the implementation | "How does the application start up and work with the entire context?" |

Two-tier example:

~~~text
Metadata:
  Bean name: "greetingService"
  Factory:   AppConfig.greetingService(TextFormatter)
  Scope:     singleton (default)
  Depends:   TextFormatter

Runtime:
  Bean instance: GreetingService #1
     |
     +-- field formatter -> UppercaseFormatter #1
~~~

**One BeanDefinition does not equal one object in every scope.** A typical singleton definition corresponds to one instance in the container; a prototype definition can create multiple objects each time it is requested.

**Not every Java object is a Spring bean.** If a business method calls `new StringBuilder()` or `new Helper()`, that object does not automatically become a managed bean just because it was created inside a Spring application.

### Imagining BeanDefinition as a Recipe

- The recipe specifies: what ingredients are needed, how to make it, how many times to create it, and the cleanup step.
- The bean instance is the actual result when the recipe is applied.
- BeanFactory is the engine that uses the recipe to provide the result.
- The registry keeps the recipes under distinct names.

This analogy helps understand the model, but remember that **the container also has extension mechanisms**, post-processors, factory methods, proxies, scopes, and many bean selection rules. Do not deduce the creation process of every bean as a simple `new` operation.

## 3. What Information Does BeanDefinition Store?

Typical attributes (not all are required to have non-null/non-empty values):

| Metadata Group | Example | What is it used for? |
| --- | --- | --- |
| Bean name | `"greetingService"` | Registry/lookup uses it as the registration key; **the name is typically managed by the registry**, not a fixed bean name field inside every `BeanDefinition` |
| Bean class or creation method | `HealthProbe.class` or factory method `greetingService` | Instructs Spring how to instantiate/obtain the object |
| Scope | `singleton`, `prototype` | Rules for retaining/reusing an instance or creating on demand |
| Lazy initialization | `true/false` | Whether to defer bean creation until needed, depending on context |
| Constructor arguments | Values or bean references | Provides arguments when a constructor is used |
| Property values | Values for matching setters/properties | Configures the instance after creation |
| Depends-on | `@DependsOn("bootstrap")` | Explicit initialization/destruction ordering constraint by bean name |
| Autowire candidate / primary | Injection candidate rules | Helps the container choose a collaborator when multiple options exist |
| Init/destroy method | `init`, `shutdown` | Lifecycle callbacks when the bean is appropriately created/destroyed |
| Role/source/description | Metadata about the declaration source | Supports tooling, diagnostics, or infrastructure |

**Important:** `BeanDefinition` supports multiple **bean creation forms**. With `@Bean` methods, Spring can record a **factory bean/factory method** instead of a plain bean class. Therefore, do not assume `getBeanClassName()` of every definition is the actual runtime instance class name. With `FactoryBean` or proxies, runtime type information can be more complex.

### Default Scope Is Not Necessarily Written as the Literal String "singleton"

When a definition does not explicitly specify a scope, `BeanDefinition.getScope()` may hold an empty string or default metadata depending on the registration path. Spring **treats the default scope as singleton** for ordinary application beans. Do not check `"singleton".equals(def.getScope())` to conclude whether every default bean is non-singleton.

In the runnable program, we use:

~~~java
context.isSingleton("greetingService");
context.isPrototype("healthProbe");
~~~

This is a **snippet** taken from a program with a valid `context` variable. The two methods above query the **effective scope of the bean according to the container**; `getScope()` remains useful for reading the explicitly configured value in metadata.

### Constructor Injection and Metadata

With:

~~~java
@Bean
GreetingService greetingService(TextFormatter formatter) {
    return new GreetingService(formatter);
}
~~~

Spring records the factory method and must **resolve a `TextFormatter` bean** to pass into the parameter when creating `GreetingService`. That differs from code directly calling `greetingService(new UppercaseFormatter())` as an ordinary Java method. BeanDefinition guides the container; the constructor remains a normal Java mechanism.

## 4. Where Does BeanDefinition Come From?

Three common paths:

**(A) Java configuration:** Spring processes `@Bean` methods in a registered configuration class, thereby generating bean definitions for factory methods.

~~~java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    TextFormatter textFormatter() {
        return new UppercaseFormatter();
    }
}
~~~

**(B) Component scanning:** `@Component`, `@Service`, `@Repository`, and stereotypes scanned under the appropriate configuration are also converted into bean definitions. An annotation on a class in an unscanned package does **not** automatically make that class appear in the context.

**(C) Programmatic registration:** call `registerBeanDefinition(beanName, definition)` on a supporting registry/container. You build metadata using `BeanDefinitionBuilder`, `RootBeanDefinition`, or appropriate APIs and register it under an explicit name.

~~~java
BeanDefinition definition = BeanDefinitionBuilder
        .genericBeanDefinition(HealthProbe.class)
        .setScope(BeanDefinition.SCOPE_PROTOTYPE)
        .setLazyInit(true)
        .getBeanDefinition();

context.registerBeanDefinition("healthProbe", definition);
~~~

This is a **snippet**, requiring imports and classes from the full runnable example below. It does not call `new HealthProbe()`; it only registers the recipe. Only when the prototype bean is requested does Spring use the definition to create an object.

~~~mermaid
flowchart TD
    A["Metadata sources"] --> B["BeanDefinitionRegistry"]
    A1["@Bean / JavaConfig"] --> A
    A2["@ComponentScan"] --> A
    A3["Programmatic API registration"] --> A
    B --> C["BeanDefinition metadata"]
    C --> D["BeanFactory: resolve and create"]
    D --> E["Bean instance"]
    E --> F["Init / usage / destruction by scope"]
~~~

**Ordering note:** Registration/metadata changes for an application should be performed **before context refresh** (or at an extension point designed for that purpose). Dynamic registration after beans have already been created does not automatically re-initialize existing singletons and easily leads to unpredictable state.

## 5. Standalone Runnable Java 17+ Program

This is a plain Spring Framework Core Container example using **JDK 17+, Maven, and `spring-context` version `6.2.19`** (pinned for reproducibility, not a claim of being the latest). No Spring Boot or web server is needed.

The application has three beans from `@Bean`:

- `textFormatter`: a `TextFormatter` implemented by `UppercaseFormatter`.
- `greetingService`: a service receiving `TextFormatter` via a factory method parameter.
- `traceSink`: a bean with a `shutdown` method for Spring to invoke when the context closes.

Another bean, `healthProbe`, is registered **via API**, configured with `prototype` and `lazyInit=true`. We will inspect **definition metadata and scope** before/after retrieving instances.

~~~text
bean-definition-demo/
├── pom.xml
└── src/
    └── main/
        └── java/
            └── demo/
                └── BeanDefinitionDemo.java
~~~

### 5.1. `pom.xml` File

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>demo</groupId>
    <artifactId>bean-definition-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework</groupId>
            <artifactId>spring-context</artifactId>
            <version>6.2.19</version>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
            </plugin>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>exec-maven-plugin</artifactId>
                <version>3.5.1</version>
                <configuration>
                    <mainClass>demo.BeanDefinitionDemo</mainClass>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

You only need to declare `spring-context` directly in `pom.xml`; Maven will resolve additional transitive dependencies as needed. `spring-beans` (where `BeanDefinition` and `BeanDefinitionBuilder` are defined) is pulled in transitively via Spring Context.

### 5.2. `src/main/java/demo/BeanDefinitionDemo.java` File

~~~java
package demo;

import java.util.Locale;
import java.util.Objects;

import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

public final class BeanDefinitionDemo {
    private BeanDefinitionDemo() {}

    public interface TextFormatter {
        String normalize(String input);
    }

    public static final class UppercaseFormatter
            implements TextFormatter {
        @Override
        public String normalize(String input) {
            return input.strip().toUpperCase(Locale.ROOT);
        }
    }

    public static final class GreetingService {
        private final TextFormatter formatter;

        public GreetingService(TextFormatter formatter) {
            this.formatter = Objects.requireNonNull(formatter);
        }

        public String greet(String name) {
            return "HELLO " + formatter.normalize(name);
        }

        public TextFormatter formatter() {
            return formatter;
        }
    }

    public static final class HealthProbe {
        public HealthProbe() {}
    }

    public static final class TraceSink {
        public void shutdown() {
            System.out.println("destroy=traceSink");
        }
    }

    @Configuration(proxyBeanMethods = false)
    public static class AppConfig {
        @Bean
        public TextFormatter textFormatter() {
            return new UppercaseFormatter();
        }

        @Bean
        public GreetingService greetingService(TextFormatter formatter) {
            return new GreetingService(formatter);
        }

        @Bean(destroyMethod = "shutdown")
        public TraceSink traceSink() {
            return new TraceSink();
        }
    }

    public static void main(String[] args) {
        AnnotationConfigApplicationContext context =
                new AnnotationConfigApplicationContext();

        try (context) {
            context.register(AppConfig.class);

            BeanDefinition probeDefinition = BeanDefinitionBuilder
                    .genericBeanDefinition(HealthProbe.class)
                    .setScope(BeanDefinition.SCOPE_PROTOTYPE)
                    .setLazyInit(true)
                    .getBeanDefinition();

            context.registerBeanDefinition("healthProbe", probeDefinition);
            context.refresh();

            BeanDefinition serviceDefinition = context.getBeanFactory()
                    .getBeanDefinition("greetingService");
            BeanDefinition savedProbeDefinition = context.getBeanFactory()
                    .getBeanDefinition("healthProbe");

            System.out.println("serviceDefinition=" +
                    context.containsBeanDefinition("greetingService"));
            System.out.println("factoryMethod=" +
                    serviceDefinition.getFactoryMethodName());
            System.out.println("serviceSingleton=" +
                    context.isSingleton("greetingService"));
            System.out.println("probePrototype=" +
                    context.isPrototype("healthProbe"));
            System.out.println("probeLazyMetadata=" +
                    savedProbeDefinition.isLazyInit());

            HealthProbe first = context.getBean(HealthProbe.class);
            HealthProbe second = context.getBean(HealthProbe.class);
            System.out.println("differentProbes=" + (first != second));

            GreetingService service = context.getBean(GreetingService.class);
            TextFormatter formatter = context.getBean(TextFormatter.class);
            System.out.println("injectedSame=" +
                    (service.formatter() == formatter));
            System.out.println("greeting=" + service.greet(" Lan "));
        }

        System.out.println("afterActive=" + context.isActive());
    }
}
~~~

**Why this example is worth studying:**

- `context.register(AppConfig.class)` points to the JavaConfig source; `context.registerBeanDefinition("healthProbe", ...)` places programmatically registered metadata into the same registry **before `refresh()`**.
- `BeanDefinitionBuilder` builds the `HealthProbe` bean description rather than **creating a HealthProbe instance** directly in that statement.
- `serviceDefinition.getFactoryMethodName()` returns the `@Bean` method name: `greetingService`. Do not equate it with the runtime object's constructor.
- `savedProbeDefinition.isLazyInit()` reads the metadata you set in the builder; meanwhile, `context.isPrototype("healthProbe")` checks the effective scope according to the container.
- Two calls to `getBean(HealthProbe.class)` return **two distinct instances**, because the probe has `prototype` scope. The program compares object identity directly rather than relying on arbitrary hash codes.
- The `greetingService` bean defaults to singleton; `TextFormatter` is passed into the factory method, so the service holds the exact same instance that the context returns.
- When `try (context)` ends, Spring handles shutdown and invokes `TraceSink.shutdown()` due to `@Bean(destroyMethod="shutdown")`. Only afterward does the code outside the block print `afterActive=false`.

### 5.3. Maven Command and Expected Stdout

From the `bean-definition-demo` directory:

~~~bash
java -version
javac -version
mvn -version
mvn -q clean compile exec:java
~~~

**Exact 10 lines of stdout printed by the application code upon a successful run:**

~~~text
serviceDefinition=true
factoryMethod=greetingService
serviceSingleton=true
probePrototype=true
probeLazyMetadata=true
differentProbes=true
injectedSame=true
greeting=HELLO LAN
destroy=traceSink
afterActive=false
~~~

Version check commands and any logs generated by Maven/the framework are not part of the 10 lines of stdout printed by this program. `-q` reduces Maven output without changing the `System.out.println` statements.

### 5.4. Running Directly with `javac` and `java`

Because the source imports Spring classes, the classpath needs the Spring JARs and transitive dependencies. You can have Maven build a classpath file:

~~~bash
mvn -q dependency:build-classpath -Dmdep.outputFile=classpath.txt
~~~

**Linux/macOS (bash/zsh):**

~~~bash
mkdir -p out
javac --release 17 -encoding UTF-8 \
  -cp "$(cat classpath.txt)" \
  -d out src/main/java/demo/BeanDefinitionDemo.java
java -cp "out:$(cat classpath.txt)" demo.BeanDefinitionDemo
~~~

**Windows PowerShell:**

~~~powershell
$deps = (Get-Content -Raw classpath.txt).Trim()
New-Item -ItemType Directory -Force out | Out-Null
javac --release 17 -encoding UTF-8 -cp "$deps" -d out src/main/java/demo/BeanDefinitionDemo.java
java -cp "out;$deps" demo.BeanDefinitionDemo
~~~

The classpath separator is `:` on Unix and `;` on Windows. Both ways of running execute the **same `main`** and print the corresponding 10 lines.

## 6. Interpreting Results by Metadata Category

| Output | What does it verify? | What can you NOT infer from it? |
| --- | --- | --- |
| `serviceDefinition=true` | The registry contains a bean definition named `greetingService` | Does not mean all beans have already been used |
| `factoryMethod=greetingService` | The service bean metadata specifies the factory method configured for Spring | Does not mean the service has a business method of the same name |
| `serviceSingleton=true` | The service bean in this context has singleton scope | Does not mean only one GreetingService exists across the entire JVM |
| `probePrototype=true` | The probe is a prototype bean | Does not prove all beans have prototype scope |
| `probeLazyMetadata=true` | The lazy-init metadata is set to true | Does not mean every dependency will never be initialized |
| `differentProbes=true` | Two requests for the probe create two different references | Does not rely on a custom `equals()` implemented by the class |
| `injectedSame=true` | The service collaborator holds the exact same reference as the existing formatter bean | Does not guarantee business logic is correct for every input |
| `greeting=HELLO LAN` | The service uses the formatter to normalize data | No service logic runs automatically just from having a definition |
| `destroy=traceSink` | The callback is invoked by Spring when destroying a managed singleton | Does not mean prototypes are also automatically destroyed |
| `afterActive=false` | The context is closed after leaving try-with-resources | Does not mean Java objects have been immediately garbage-collected |

**Reading metadata differs from reading an instance:** In the example, the probe definition can be looked up from the registry before the application calls `getBean(HealthProbe.class)`. Metadata exists independently of whether a concrete instance has been created.

### Do You Need to Instantiate a Bean to Inspect Its BeanDefinition?

**No.** You can use `getBeanDefinition("beanName")` on the registry/factory to read metadata. Even so, some type-lookup or candidate-matching operations in Spring can trigger dynamic mechanisms (for example `FactoryBean`), so you should not claim that *every bean inspection API can never cause instantiation*.

**Do not arbitrarily mutate metadata after the context is serving the application.** Initial metadata may already have been processed/merged/cached, and already-created singleton instances will not automatically change because a definition was modified. Prefer clear configuration at bootstrap time.

## 7. Bean Name, Class, and Factory Method

Three names should be distinguished:

- **Bean name:** the registry key, for example `greetingService`.
- **Java class of the instance:** `GreetingService`.
- **Factory method:** `AppConfig.greetingService(TextFormatter)`.

In Spring JavaConfig, the default bean name is usually taken from the `@Bean` method name; an explicit name can be specified:

~~~java
@Bean("primaryFormatter")
TextFormatter textFormatter() {
    return new UppercaseFormatter();
}
~~~

**Illustrative snippet—do not add a duplicate** method with the same signature to the main configuration simultaneously. If you rename a definition, string-based name lookup must use `primaryFormatter`; injection by `TextFormatter` still depends on matching candidate selection rules.

For beans created directly via constructor using `genericBeanDefinition(HealthProbe.class)`, the metadata may know the class that creates the object. For `@Bean` methods or other factory mechanisms, it may store the factory bean/method name and an inferred type. You must not assume every definition will print the exact runtime class via `getBeanClassName()`.

**BeanDefinitionRegistry does not manage only application beans.** The context may contain internal definitions needed by Spring to process configuration. Therefore, `context.getBeanDefinitionCount()` can be larger than the number of `@Bean` methods you wrote; check **target names** to see whether the configuration you want is present.

## 8. Additional Metadata: Constructor, Property, Depends-On, and Lifecycle

### Constructor Arguments and Property Values

When registering a definition programmatically, a builder can carry **constructor arguments** or **property values**. Illustrative example:

~~~java
BeanDefinition workerDefinition = BeanDefinitionBuilder
        .genericBeanDefinition(JobWorker.class)
        .addConstructorArgValue("daily")
        .getBeanDefinition();

// registry.registerBeanDefinition("jobWorker", workerDefinition);
~~~

**Non-standalone illustrative code:** `JobWorker` is not defined and `registry` must be a `BeanDefinitionRegistry` object. The class must have a constructor matching the type/value you declare. Metadata instructs Spring how to create the object, but if no constructor matches, bean creation will fail.

Similarly, `addPropertyValue("enabled", true)` is meaningful when the bean has a matching writable property. Do not assume property values directly assign arbitrary private Java fields.

### Name-Based Dependency vs. Type-Based Injection

`@DependsOn("startupLogger")` sets an **initialization ordering constraint** of one bean on the bean named `startupLogger`; it does not automatically inject that bean as a constructor argument. By contrast, the `TextFormatter formatter` parameter on `@Bean greetingService(...)` is a **true injection point**: Spring must resolve an appropriate instance.

Both relationships can affect bean creation order, but they serve different purposes. Use explicitly declared dependencies if the consumer truly needs the collaborator; use depends-on when an init side effect must happen first, not to replace a hidden dependency.

### Init/Destroy Method

You can declare:

~~~java
@Bean(initMethod = "start", destroyMethod = "stop")
ResourceManager resourceManager() {
    return new ResourceManager();
}
~~~

**Non-standalone snippet:** requires a `ResourceManager` with matching method signatures. When the container creates and initializes the bean appropriately, the init callback runs as part of the lifecycle; when a singleton is destroyed on context close, the destroy callback runs under the appropriate conditions.

For `prototype`, Spring normally only manages steps up through handing the bean to the caller, and **does not track and execute full destruction callbacks** for all prototypes afterward. Code using a prototype that holds resources must have its own closing strategy.

An object created with `new` outside the container does not automatically receive any lifecycle callbacks simply because it shares the same class as a managed bean.

## 9. Things BeanDefinition Does NOT Guarantee on Its Own

1. **Does not guarantee an immediate instance.** Lazy/prototype settings and request timing govern when creation happens.
2. **Does not prove dependencies are valid by itself.** If a bean needs a formatter and no candidate exists, creation can fail.
3. **Does not guarantee a unique type selection.** Multiple `TextFormatter` beans can cause ambiguity; use qualifiers/primary or redesign.
4. **Does not automatically execute business methods.** Only the bean is created; `GreetingService.greet` runs because a caller invokes it.
5. **Does not manage objects created outside the container.** A `new HealthProbe()` in code normally does not belong to the registry.
6. **Does not guarantee all beans share the same scope.** Singleton/prototype/custom scopes differ.
7. **Does not guarantee all resource cleanup completes.** Destroy callbacks depend on scope/ownership and bean code.
8. **Does not necessarily describe a simple "final instance class".** Factory methods, proxies, and `FactoryBean` have their own semantics.
9. **Is not an initialization-order convention by name.** Dependency edges and initialization mechanisms matter more than alphabetical/declaration order.
10. **Is not synonymous with annotations.** XML, programmatic registration, and component scanning also produce metadata.

## 10. Common Errors and How to Diagnose Them

| Symptom | Possible Cause | How to Check |
| --- | --- | --- |
| `NoSuchBeanDefinitionException` | Definition not registered or looked up with wrong name/type | Check registry, `@Bean`/scan, bean name/condition |
| `UnsatisfiedDependencyException` | Bean definition exists but a dependency cannot be resolved | Identify which factory/constructor parameter lacks a candidate |
| `NoUniqueBeanDefinitionException` | Multiple candidates for single-bean injection | `@Qualifier`, `@Primary`, reduce duplicate beans |
| `BeanCreationException` | Constructor/factory/init method failed | Read the `Caused by` chain, identify bean and metadata |
| `BeanCurrentlyInCreationException` | Circular constructor/factory dependency | Trace A→B→A, split responsibilities |
| Unexpected scope when checking `getScope()` | Default metadata may be left empty | Ask the container `isSingleton`/`isPrototype` for the specific bean name |
| `@Bean` method returns a class but `getBeanClassName()` is empty/unexpected | Definition may be based on a factory method rather than a direct bean class | Check `getFactoryMethodName()` and registration type |
| `getBeanDefinitionCount()` is greater than the beans you wrote | Spring adds infrastructure definitions | Check only the application bean names you care about |
| Registration API called after refresh | Wrong timing relative to lifecycle and caches | Register before `refresh()` or use the proper extension point |
| A prototype behaves like a singleton | A singleton consumer holds the dependency injected when it was created | Use a provider/lookup per operation if truly needed |
| Bean has `@Bean(destroyMethod=...)` but callback is not seen | Context was not closed, bean was not created, or different scope | Check lifecycle and method name |
| `package org.springframework... does not exist` | Classpath lacks compile dependencies | Check Maven `spring-context` and `javac -cp` |

**Do not directly modify BeanDefinition per request** to "reconfigure" a running service. In many cases, the instance is already created/cached, and changing metadata will not make Spring re-inject or rebuild the entire graph.

## 11. When Should You Manipulate BeanDefinition via API?

Most applications can use `@Configuration`, `@Bean`, and component scanning. The BeanDefinition API is suitable when:

- Writing framework starters/infrastructure that integrate user-supplied classes.
- Generating many bean definitions from other metadata/schemas while still wanting Spring to manage the lifecycle.
- Creating controlled dynamic registrations **before bootstrap** when expressing them as a few `@Bean` methods is inconvenient.
- Writing tooling that needs to inspect definition names/roles/sources/types/attributes.
- Customizing metadata prior to instantiation via designed extension points, such as `BeanFactoryPostProcessor` or `BeanDefinitionRegistryPostProcessor`.

**Distinguishing two prominent extension points:**

| Extension point | Target of operation | When |
| --- | --- | --- |
| `BeanDefinitionRegistryPostProcessor` | Can register/modify additional bean definitions | Bootstrap phase before creating application beans |
| `BeanFactoryPostProcessor` | Adjusts metadata of already-registered bean definitions | Before the normal bean instantiation phase |
| `BeanPostProcessor` | Operates on **bean instances** during initialization | Not a tool merely for editing metadata |

The exact invocation order/mechanics depend on Spring's internals; for this lesson it is enough to recognize **registry metadata** and **instance processing** as two distinct levels.

If you only need to wire two services together in an app, using `BeanDefinitionBuilder` directly is usually **more complex than necessary**. Simple Java configuration will be clearer and easier to maintain.

## 12. Exercises with Answers

**Exercise 1 — Definition and instance.** Register a `prototype` bean without calling `getBean`. Have you created an instance?

**Answer:** Not yet; registration primarily creates/stores metadata. Prototype instances are generally created upon an appropriate request.

**Exercise 2 — Why is scope empty?** `@Bean GreetingService greetingService(...)` has no `@Scope`. If `definition.getScope()` is an empty string, is the bean a prototype?

**Answer:** No. The default scope for ordinary beans is singleton. Check the effective scope with `context.isSingleton("greetingService")` instead of concluding from an empty string.

**Exercise 3 — Retrieving a prototype twice.** If `healthProbe` is a prototype, do two calls to `context.getBean(HealthProbe.class)` share the same reference?

**Answer:** Not in this example: Spring creates two instances, so `differentProbes=true`.

**Exercise 4 — Factory method.** Why does the service definition have `getFactoryMethodName()=="greetingService"`?

**Answer:** The service bean is registered from `@Bean greetingService(TextFormatter)`, so the metadata knows the factory method providing the bean. This is not the business method name `greet`.

**Exercise 5 — Destroy callback.** Why does `destroy=traceSink` appear before `afterActive=false`?

**Answer:** Exiting `try (context)` invokes `close()`. Spring destroys the singleton bean with `destroyMethod="shutdown"` before execution continues to the statement after the block.

**Exercise 6 — Missing collaborator.** If you remove the `textFormatter` bean while keeping `greetingService(TextFormatter)`, what happens?

**Answer:** The context can fail when creating the service because it cannot resolve the required parameter. Having a definition present does not by itself guarantee instantiation.

**Exercise 7 — Registry vs. lookup.** Is `containsBeanDefinition("name")` completely identical to `containsBean("name")`?

**Answer:** No. The first asks whether a bean definition is directly registered in the corresponding registry; the second asks whether the container recognizes a bean under that name via its lookup mechanism (which may include aliases/parent/other registrations depending on the context). In simple cases the two results match, but they are not the same API.

## 13. Completion Checklist

- [ ] Distinguish `BeanDefinition`, registry, factory, and instance.
- [ ] Understand bean name as a registry key and know the bean creation paths (class vs. factory method).
- [ ] Know singleton/prototype scopes and the effect of lazy metadata.
- [ ] Understand constructor/factory args, property values, and lifecycle callbacks.
- [ ] Know that `@Bean`/component scanning/registration APIs all create metadata.
- [ ] Create a context with JavaConfig and register a programmatic definition before refresh.
- [ ] Run Java 17+ with `mvn -q clean compile exec:java`, matching the exact 10 lines of stdout.
- [ ] If running `javac`/`java` manually, prepare the full Spring classpath.
- [ ] Distinguish reading metadata with `getBeanDefinition` from retrieving an instance with `getBean`.
- [ ] Do not infer default scope solely from `definition.getScope()`, which can be empty.
- [ ] Do not arbitrarily mutate metadata after beans have already been initialized.
- [ ] Know how to diagnose missing/ambiguous bean errors, circular dependencies, and factory/init failures.
- [ ] Distinguish lifecycle-managed beans from objects created by Java code outside the container.

**Conclusion:** `BeanDefinition` is the **metadata contract** describing what Spring knows about a bean: how to create it, how to resolve dependencies, and its scope/lifecycle settings. The container uses that metadata to provide **actual bean instances** when needed. Grasping this helps you understand why the same Spring API can produce singletons, prototypes, lazy beans, or beans via factory methods — and why **registering a definition is different from instantiating an object**.

### Further Reading

- [Spring IoC Container](https://docs.spring.io/spring-framework/reference/core/beans/introduction.html)
- [Bean Overview / Definition](https://docs.spring.io/spring-framework/reference/core/beans/definition.html)
- [Java Configuration — @Bean](https://docs.spring.io/spring-framework/reference/core/beans/java/bean-annotation.html)
- [Spring BeanDefinition API](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/beans/factory/config/BeanDefinition.html)
