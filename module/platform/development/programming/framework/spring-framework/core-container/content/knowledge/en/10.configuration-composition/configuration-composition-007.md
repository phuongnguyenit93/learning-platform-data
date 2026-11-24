# Registering Definitions with ImportBeanDefinitionRegistrar in Spring Core Container

## 1. Scope and Objectives

In Spring Framework, most beans are declared using `@Component`/`@Service`, `@Bean` methods inside a `@Configuration` class, or XML configuration. However, infrastructure libraries, starters, integration modules, and `@Enable...` annotations sometimes need to **programmatically generate configurable and conditional bean definitions** right while Spring processes Java configuration.

The **`ImportBeanDefinitionRegistrar`** interface is an extension point designed for that purpose. A class implementing a registrar can be plugged into configuration via `@Import`. Spring invokes the registrar while parsing configuration classes and passes it:

- `AnnotationMetadata`: annotation metadata of the class importing the registrar.
- `BeanDefinitionRegistry`: the current container's registry, used to inspect and add bean definitions.
- In the three-parameter overload, a `BeanNameGenerator` used by Spring for imported beans.

A registrar only defines **how a bean should be created by Spring**; it should not execute business logic itself, spin up another ApplicationContext, or treat `registerBeanDefinition` as an immediate instance-creation call.

After this lesson, you will be able to:

1. Understand where `ImportBeanDefinitionRegistrar` fits in the `@Configuration` + `@Import` pipeline.
2. Know when to choose a registrar over `@Bean`, `@ComponentScan`, `ImportSelector`, or `BeanDefinitionRegistryPostProcessor`.
3. Implement both `registerBeanDefinitions(...)` overloads for their intended purposes.
4. Read custom annotation values via `AnnotationMetadata`.
5. Build `BeanDefinition`s with `BeanDefinitionBuilder` and register them via `BeanDefinitionRegistry.registerBeanDefinition`.
6. Control bean names, collisions, constructor arguments, roles, scopes, qualifiers, and dependency injection.
7. Run a Java 17/Spring Framework example with custom `@EnableGreetings` registering two beans injected into a standard `@Bean`.
8. Test the difference between **registered bean definitions** and **instances created by BeanFactory**.
9. Recognize lifecycle/early-initialization constraints, especially not registering `BeanDefinitionRegistryPostProcessor` from a registrar.
10. Design concise, deterministic registrars with clear failure behavior.

**Core message:** A registrar is **infrastructure for registering metadata into the IoC container**, not a Service Locator or business factory. Let Spring manage instantiation, dependency resolution, and lifecycle after definitions are added.

## 2. What Is BeanDefinition? What Part Does a Registrar Change?

A Spring bean does not necessarily originate from a `new` call in your code. The container processes **bean definitions**, which can contain:

- Bean class name or reference.
- Constructor arguments or property values.
- Scope (`singleton`, `prototype`, or a registered scope).
- Lazy initialization flag.
- Qualifiers and autowire candidate flags.
- Init/destroy callbacks and origin/role metadata.
- Factory method or supplier when using advanced creation mechanisms.

Typical Java config example:

```java
@Configuration(proxyBeanMethods = false)
class AppConfig {
    @Bean
    EmailClient emailClient() {
        return new EmailClient();
    }
}
```

Spring reads `@Bean` and builds a definition for `emailClient`. A registrar operates at a **lower level**: you decide programmatically which definitions should exist, under what names, and with what metadata, without writing a fixed `@Bean` method for every case.

Conceptual flow:

```text
@Configuration AppConfig
       |
       | has @Import(MyRegistrar.class)
       v
ConfigurationClassPostProcessor parses Java config
       |
       v
MyRegistrar.registerBeanDefinitions(...)
       |
       | AnnotationMetadata + BeanDefinitionRegistry
       v
Create BeanDefinition metadata
       |
       | registry.registerBeanDefinition(beanName, definition)
       v
BeanFactory receives added definition
       |
       | resolve dependencies / scopes / lifecycle
       v
Bean instance created by container on demand
```

**Very common misconception:** `registerBeanDefinition("x", def)` **does not mean** `new X()` executes immediately at call time. Instantiation usually happens later, when the container pre-instantiates non-lazy singletons or when the application requests the bean per its scope/lifecycle.

Registrars are called **during the configuration processing phase**, so they should focus on metadata decisions. Operations such as running migrations, calling remote APIs, opening connection pools, or processing invoices do not belong here.

## 3. The Interface and Related APIs

The interface resides in:

```java
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
```

Two methods are of interest:

```java
// Illustrative signature, omitting full generic imports:
default void registerBeanDefinitions(
        AnnotationMetadata importingClassMetadata,
        BeanDefinitionRegistry registry) {
}

default void registerBeanDefinitions(
        AnnotationMetadata importingClassMetadata,
        BeanDefinitionRegistry registry,
        BeanNameGenerator importBeanNameGenerator) {
    registerBeanDefinitions(importingClassMetadata, registry);
}
```

In Spring 6.2, both methods are **default methods**; the three-parameter overload by default **delegates** to the two-parameter overload. Therefore, overriding only the two-parameter method suffices for standard cases.

### 3.1. AnnotationMetadata

`org.springframework.core.type.AnnotationMetadata` represents metadata of **the imported/importing class**, not an instance of that class. You can inspect directly present or meta-present annotations through the appropriate APIs.

Example:

```java
Map<String, Object> values =
        importingClassMetadata.getAnnotationAttributes(
                EnableGreetings.class.getName());
```

Here `EnableGreetings` is a custom annotation; the full example is in section 7. The method returns `null` if the annotation is not found under that query policy. Do not blindly cast `null` or assume every place importing the registrar carries the expected annotation.

**Advantage:** You can make bean-registration decisions from metadata without instantiating the configuration class or running its constructors or business code.

### 3.2. BeanDefinitionRegistry

`org.springframework.beans.factory.support.BeanDefinitionRegistry` is the API for:

- `registerBeanDefinition(String, BeanDefinition)`: registers a definition under a specific name.
- `containsBeanDefinition(String)`: checks whether the registry already holds a definition with that name.
- `getBeanDefinition(String)`: retrieves a registered definition.
- `getBeanDefinitionNames()`: lists existing definition names.
- Other registry operations in appropriate infrastructure scenarios.

The API also participates in alias handling; when generating names dynamically, check for collisions with aliases as well as other definitions in the registry when designing your collision policy.

Do not treat the registry like an `ApplicationContext` to call `getBean` and run use cases. It primarily manipulates metadata during bootstrap.

### 3.3. BeanDefinitionBuilder

`org.springframework.beans.factory.support.BeanDefinitionBuilder` helps build definitions relatively safely and readably:

```java
BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(GreetingHandler.class)
                .addConstructorArgValue("email")
                .getBeanDefinition();
registry.registerBeanDefinition("greeting.email", definition);
```

This is an **illustrative snippet** requiring `GreetingHandler`, `registry`, and matching imports. We do not call `new GreetingHandler("email")` ourselves; Spring uses the definition to invoke the constructor when creating the bean.

You can also choose `RootBeanDefinition` directly when deeper metadata control is needed:

```java
RootBeanDefinition definition =
        new RootBeanDefinition(GreetingHandler.class);
definition.getConstructorArgumentValues()
        .addGenericArgumentValue("email");
registry.registerBeanDefinition("greeting.email", definition);
```

The two examples illustrate two ways to create a definition for the same idea; do not put both side-by-side in the same registrar to register duplicate names.

## 4. Registrars Are Activated via @Import

A registrar must be **discovered by Spring's configuration processing**. The most common way:

```java
@Configuration(proxyBeanMethods = false)
@Import(GreetingRegistrar.class)
public class AppConfig {
}
```

Spring parses `AppConfig`, sees `@Import` pointing to a class implementing `ImportBeanDefinitionRegistrar`, and invokes its definition-registration method. This is not component scanning and not a method call developers invoke manually.

### 4.1. Using @Import Directly

```java
@Import(GreetingRegistrar.class)
class AppConfig {
}
```

Suitable for experimentation or when importing the registrar is an infrastructure detail the application configuration is expected to see.

### 4.2. Creating a Custom @Enable Annotation

Libraries usually prefer a cleaner API:

```java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Documented
@Import(GreetingRegistrar.class)
public @interface EnableGreetings {
    String[] value();
}
```

Then users write:

```java
@Configuration(proxyBeanMethods = false)
@EnableGreetings({"email", "sms"})
class AppConfig {
}
```

Spring detects `@Import` on the **meta-annotation `@EnableGreetings`**, invokes the registrar, and lets the registrar read the channel list from `AppConfig`'s metadata. Users do not need to touch BeanFactory or write N `@Bean` methods.

This `@Enable...` composition pattern fits features with compact configuration that need to register a variable number of beans driven by an annotation.

### 4.3. @Import Does Not Instantiate the Registrar as a Business Bean

The framework instantiates and uses the registrar during configuration processing. You should not assume the registrar is a business singleton service sharing the lifecycle of regular application beans, or put side effects in its constructor.

A registrar can also be **returned by an `ImportSelector`**; that is an advanced configuration case, though the core point stays the same: Spring invokes the registrar when processing the corresponding configuration class.

## 5. Processing Order: Why Shouldn't a Registrar Grab Beans Right Away?

A typical sequence when `AnnotationConfigApplicationContext` refreshes:

```text
register(AppConfig.class)
        |
        v
refresh()
        |
        v
ConfigurationClassPostProcessor
        |
        v
Parse @Configuration, @Import, @Bean, component metadata
        |
        v
Invoke ImportBeanDefinitionRegistrar
        |
        v
Registry receives added bean definitions
        |
        v
BeanFactoryPostProcessor / BeanPostProcessor per lifecycle
        |
        v
Pre-instantiate non-lazy singletons
        |
        v
Dependency injection, initialization, and post-processing
        |
        v
Context ready for application code
```

The diagram shows only **conceptual ordering**, not a full description of every internal algorithm. Certain post-processors participate very early; never rely on exact ordering details across arbitrary definitions without an API contract.

At the moment the registrar runs:

- Many bean definitions may already exist; many beans have still **not been created**.
- Decisions such as bean names, constructor values, scopes, and candidate metadata should be written into definitions.
- Resolving `@Autowired` or invoking business methods may not yet be safe.
- Do not try to fetch a bean to ask for configuration values if you can read them from `AnnotationMetadata` or `Environment`.
- Do not spin up a secondary `AnnotationConfigApplicationContext` from a registrar just to instantiate objects.

Specifically, **Spring's Javadoc warns** against registering `BeanDefinitionRegistryPostProcessor` bean types via `ImportBeanDefinitionRegistrar` due to lifecycle constraints in configuration class processing. If you truly need a registry post-processor, use the dedicated extension point/registration path instead of bypassing it through a registrar registering its own post-processor.

## 6. When Should You Choose a Registrar?

| Need | Preferred Tool to Consider | Reason |
| --- | --- | --- |
| A fixed bean built in Java | `@Bean` | Clear types and dependencies |
| Application class with stereotypes | `@Component`/`@Service` + component scan | Less boilerplate |
| Splitting Java configuration into modules | `@Import(Config.class)` | Direct composition |
| Conditionally selecting one/a set of configuration classes | `ImportSelector` | Decides which classes are imported |
| Creating multiple bean definitions driven by annotation metadata | `ImportBeanDefinitionRegistrar` | Flexible definition registration |
| Inspecting/modifying definitions in BeanFactory post-processing | `BeanDefinitionRegistryPostProcessor`/`BeanFactoryPostProcessor` | Dedicated extension point; requires understanding ordering/lifecycle |
| Programmatically choosing name, scope, constructor args on a context | `BeanDefinitionRegistry` or `GenericApplicationContext.registerBean` | API registration, does not necessarily require `@Import` |
| Importing XML into Java config | `@ImportResource` | Reads bean definitions from XML |
| Selecting a concrete strategy at runtime | Business registry/factory or qualifiers | Not a reason to default to a registrar |

**A registrar earns its keep when bean count or metadata depends on annotations/configuration** that a handful of `@Bean` methods cannot express cleanly. It is a framework/infrastructure-level extension point; avoid adding one merely to make code “more flexible” when the app only needs a simple bean.

### When Not to Use It

Do not use a registrar just to register:

```java
@Bean
PaymentGateway paymentGateway() {
    return new DefaultPaymentGateway();
}
```

when there is no dynamic condition/naming/metadata requirement. `@Bean` is clearer, compile-time type references are obvious, there is less coupling to framework internals, and registration conflict risk is lower.

Never use a registrar to send emails, migrate data, or open network connections while Spring is processing configuration definitions.

## 7. Runnable Java 17 Project: Custom @EnableGreetings Registering Two Beans

This example runs with **JDK 17 + Spring Framework 6.2.x**, without Spring Boot. The goal is to trace end-to-end:

1. `@EnableGreetings({"email", "sms"})` holds the feature configuration.
2. Meta-present `@Import(GreetingRegistrar.class)` lets Spring invoke the registrar.
3. The registrar reads `AnnotationMetadata` and registers two bean definitions named `greeting.email` and `greeting.sms`.
4. `@Bean GreetingDashboard` has `GreetingHandler` injected by Spring via `@Qualifier("greeting.email")`, proving definitions created by a registrar participate normally in dependency resolution.
5. `getBeanNamesForType` and `getBeanDefinition` verify exact definitions, names, and roles.
6. No component scanning and no per-handler `@Bean`; creating them is driven entirely by registrar metadata registration.

### 7.1. Directory Structure

```text
registrar-demo/
├── pom.xml
└── src/main/java/
    └── demo/
        └── RegistrarDemo.java
```

### 7.2. pom.xml

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="
             http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <groupId>demo</groupId>
    <artifactId>registrar-demo</artifactId>
    <version>1.0-SNAPSHOT</version>

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

### 7.3. Complete RegistrarDemo.java File

Create `src/main/java/demo/RegistrarDemo.java`:

```java
package demo;

import java.lang.annotation.Documented;
import java.lang.annotation.ElementType;
import java.lang.annotation.Retention;
import java.lang.annotation.RetentionPolicy;
import java.lang.annotation.Target;
import java.util.Arrays;
import java.util.HashSet;
import java.util.Map;
import java.util.Set;

import org.springframework.beans.factory.annotation.Qualifier;
import org.springframework.beans.factory.config.BeanDefinition;
import org.springframework.beans.factory.support.BeanDefinitionBuilder;
import org.springframework.beans.factory.support.BeanDefinitionRegistry;
import org.springframework.context.annotation.AnnotationConfigApplicationContext;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.context.annotation.ImportBeanDefinitionRegistrar;
import org.springframework.core.type.AnnotationMetadata;

public class RegistrarDemo {

    // Service object managed by Spring after the registrar
    // registers the corresponding BeanDefinition.
    public static final class GreetingHandler {
        private final String channel;

        public GreetingHandler(String channel) {
            this.channel = channel;
        }

        public String greet(String name) {
            return channel + ":Hello, " + name;
        }
    }

    public static final class GreetingDashboard {
        private final GreetingHandler email;

        public GreetingDashboard(GreetingHandler email) {
            this.email = email;
        }

        public String headline(String name) {
            return "dashboard=" + email.greet(name);
        }
    }

    @Target(ElementType.TYPE)
    @Retention(RetentionPolicy.RUNTIME)
    @Documented
    @Import(GreetingRegistrar.class)
    public @interface EnableGreetings {
        String[] value();
    }

    public static final class GreetingRegistrar
            implements ImportBeanDefinitionRegistrar {

        @Override
        public void registerBeanDefinitions(
                AnnotationMetadata importingClassMetadata,
                BeanDefinitionRegistry registry) {

            Map<String, Object> attributes =
                    importingClassMetadata.getAnnotationAttributes(
                            EnableGreetings.class.getName());

            if (attributes == null) {
                throw new IllegalStateException(
                        "@EnableGreetings is required");
            }

            String[] channels = (String[]) attributes.get("value");
            Set<String> seen = new HashSet<>();

            for (String channel : channels) {
                if (channel == null ||
                        !channel.matches("[a-z][a-z0-9-]*")) {
                    throw new IllegalArgumentException(
                            "Invalid channel: " + channel);
                }

                if (!seen.add(channel)) {
                    throw new IllegalArgumentException(
                            "Duplicate channel: " + channel);
                }

                String beanName = "greeting." + channel;
                if (registry.containsBeanDefinition(beanName) ||
                        registry.isAlias(beanName)) {
                    throw new IllegalStateException(
                            "Bean name already used: " + beanName);
                }

                BeanDefinition definition = BeanDefinitionBuilder
                        .genericBeanDefinition(GreetingHandler.class)
                        .addConstructorArgValue(channel)
                        .getBeanDefinition();

                definition.setRole(BeanDefinition.ROLE_APPLICATION);
                registry.registerBeanDefinition(beanName, definition);
            }
        }
    }

    @Configuration(proxyBeanMethods = false)
    @EnableGreetings({"email", "sms"})
    public static class AppConfig {

        @Bean
        public GreetingDashboard greetingDashboard(
                @Qualifier("greeting.email") GreetingHandler email) {
            return new GreetingDashboard(email);
        }
    }

    public static void main(String[] args) {
        try (var context =
                     new AnnotationConfigApplicationContext(AppConfig.class)) {

            String[] beanNames =
                    context.getBeanNamesForType(GreetingHandler.class);
            Arrays.sort(beanNames);

            System.out.println("handlers=" + Arrays.toString(beanNames));
            System.out.println("email=" +
                    context.getBean("greeting.email",
                                    GreetingHandler.class).greet("Lan"));
            System.out.println("sms=" +
                    context.getBean("greeting.sms",
                                    GreetingHandler.class).greet("Lan"));
            System.out.println(
                    context.getBean(GreetingDashboard.class).headline("Mai"));
            System.out.println("roleIsApplication=" +
                    (context.getBeanDefinition("greeting.email").getRole()
                            == BeanDefinition.ROLE_APPLICATION));
        }
    }
}
```

### 7.4. Running the Program

From the directory containing `pom.xml`, with JDK 17+ and Maven:

```bash
mvn -q compile exec:java -Dexec.mainClass=demo.RegistrarDemo
```

Output **printed by the program** (excluding Maven/Spring logging if configured differently by the environment):

```text
handlers=[greeting.email, greeting.sms]
email=email:Hello, Lan
sms=sms:Hello, Lan
dashboard=email:Hello, Mai
roleIsApplication=true
```

### 7.5. Why Does It Produce That Output?

**`handlers=[greeting.email, greeting.sms]`:** The registrar registers two bean definitions of class `GreetingHandler`. Spring created/can resolve them by type. `getBeanNamesForType(GreetingHandler.class)` returns the primary names of candidate beans matching the type, and `Arrays.sort` keeps display order independent of internal registry ordering.

**`email=email:Hello, Lan`** and **`sms=sms:Hello, Lan`:** Each `BeanDefinition` carries its corresponding channel string as a constructor argument. BeanFactory calls `GreetingHandler(String)` to create instances as needed, rather than the registrar pre-creating objects. Both beans share the same class yet hold different constructor state.

**`dashboard=email:Hello, Mai`:** `GreetingDashboard` is created by a Java `@Bean`. The `@Qualifier("greeting.email") GreetingHandler` parameter is resolved by Spring to the registrar-registered bean. Thus a normal Java config bean can depend on programmatically registered beans.

**`roleIsApplication=true`:** The registrar set `BeanDefinition.ROLE_APPLICATION` on the `greeting.email` definition; querying the metadata back confirms that value. Role is primarily a classification hint for tools/containers, **not** a mandatory rule governing singleton behavior, injection, or bean priority.

### 7.6. Why Use Public Static Nested Classes?

All classes in the example live in one Java file for easy copying. `GreetingHandler`, `GreetingDashboard`, and `GreetingRegistrar` are all **public static nested classes**, so no outer `RegistrarDemo` instance is needed when Spring instantiates them.

`GreetingHandler` has a public constructor accepting `String channel`; `BeanDefinitionBuilder.addConstructorArgValue(channel)` supplies that exact constructor argument. If changed to a non-static inner class, Spring would also require an outer instance and the bean definition pattern would no longer be as simple.

### 7.7. Why Is Spring Boot Not Needed?

`AnnotationConfigApplicationContext`, `@Import`, `ImportBeanDefinitionRegistrar`, `BeanDefinitionRegistry`, and `BeanDefinitionBuilder` are all Spring Framework APIs. The `spring-context` dependency pulls in the necessary core/beans modules, so this example runs as a plain console application.

If you later place a custom `@EnableGreetings` inside a Spring Boot application, the registrar mechanism still belongs to the underlying Spring Framework; Boot is not a prerequisite for registrars to work.

## 8. Reading AnnotationMetadata Safely and Correctly

A registrar is often imported through a composed annotation with attributes like:

```java
@EnableGreetings({"email", "sms"})
class AppConfig {
}
```

Inside the registrar:

```java
Map<String, Object> attributes =
        importingClassMetadata.getAnnotationAttributes(
                EnableGreetings.class.getName());

if (attributes == null) {
    throw new IllegalStateException("Missing @EnableGreetings");
}
String[] channels = (String[]) attributes.get("value");
```

This is code excerpted from the full example. `importingClassMetadata` represents the configuration class that declared the annotation. With `@EnableGreetings` in the example, `value` is declared as `String[]`, so casting to `String[]` works.

### Mistake: Reading Metadata from the Registrar Instead of the Importing Class

`GreetingRegistrar.class.getAnnotation(EnableGreetings.class)` will not give you the channel list from `AppConfig`, because `@EnableGreetings` is on **AppConfig**, not on the registrar. Spring passes the registrar the metadata of **the importing configuration class** specifically to solve this.

### When Annotations Are Meta-Annotated Across Multiple Layers

If a custom annotation composes additional meta-annotations or attribute aliases, use Spring's annotation metadata/`MergedAnnotations` APIs appropriately rather than walking raw Java reflection yourself. The goal is reading configuration metadata **without instantiating the configuration class**.

### Validating Before Registering

Values from annotations can determine bean names, class names, constructor args, or definition counts. Validate:

- Empty/null/invalid values.
- Duplicate values or name collisions after normalization.
- Bean naming rules and characters forbidden by **application contracts**.
- How many beans will be created, avoiding accidentally generating thousands of definitions from an oversized list.
- Whether feature-flag conditions are deterministic and have sufficient information at bootstrap time.

For instance, `channel.matches("[a-z][a-z0-9-]*")` is **this demo's own convention**, not a global bean-naming restriction imposed by Spring.

## 9. BeanDefinitionBuilder and Definition Metadata

A builder can configure multiple attributes:

```java
BeanDefinitionBuilder builder =
        BeanDefinitionBuilder.genericBeanDefinition(Worker.class)
                .addConstructorArgValue("batch")
                .setScope("prototype")
                .setLazyInit(true);

BeanDefinition definition = builder.getBeanDefinition();
definition.setRole(BeanDefinition.ROLE_SUPPORT);
registry.registerBeanDefinition("worker.batch", definition);
```

This is an **illustrative snippet** requiring a `Worker` class with a matching constructor. You can use `BeanDefinition.SCOPE_PROTOTYPE` or `ConfigurableBeanFactory.SCOPE_PROTOTYPE` to avoid hardcoded scope strings. Keep in mind:

- `setScope("prototype")`: the bean factory creates a new instance on each prototype resolution.
- `setLazyInit(true)`: meaningful especially for singletons; prototypes are already created on demand.
- `ROLE_SUPPORT`: a role hint, not a component-scanning annotation.
- `addConstructorArgValue(...)`: stores constructor argument values for Spring to resolve during instantiation.

### 9.1. Do Not Confuse BeanDefinition with a Bean Instance

Executing:

```java
registry.registerBeanDefinition("worker.batch", definition);
```

does not mean `new Worker("batch")` has run. For a normal non-lazy singleton, the container may instantiate it during refresh; for a prototype, an instance is created when requested.

If you pass an actual object instance into the builder via `addConstructorArgValue`, that object is an argument value; the container does not turn that pre-built object into an independently managed bean lifecycle.

### 9.2. Property Values

If the target class has a matching setter:

```java
BeanDefinition definition =
        BeanDefinitionBuilder
                .genericBeanDefinition(ExampleClient.class)
                .addPropertyValue("endpoint", "http://localhost")
                .getBeanDefinition();
registry.registerBeanDefinition("exampleClient", definition);
```

This is illustrative; `ExampleClient` must have `setEndpoint(String)`. `addPropertyValue` creates metadata for property injection; the bean is still created later by Spring.

### 9.3. Dependency on Another Bean

To reference a bean whose name is known, you can use `RuntimeBeanReference`:

```java
import org.springframework.beans.factory.config.RuntimeBeanReference;

BeanDefinition definition = BeanDefinitionBuilder
        .genericBeanDefinition(ReportService.class)
        .addConstructorArgValue(
                new RuntimeBeanReference("reportRepository"))
        .getBeanDefinition();

registry.registerBeanDefinition("reportService", definition);
```

This is an illustration requiring `ReportService(ReportRepository)` and an existing `reportRepository` bean. `RuntimeBeanReference` is not a plain string passed as a constructor value; it is metadata instructing Spring to resolve a **bean reference** at bean creation time.

When dependencies can be expressed via standard constructor autowiring, you can also let Spring resolve them by type, checking the proper API, autowire mode, and metadata. Never call `BeanFactory.getBean` inside a registrar to stuff an object early into a definition.

### 9.4. Role and autowire-candidate

`BeanDefinition.ROLE_APPLICATION`, `ROLE_SUPPORT`, and `ROLE_INFRASTRUCTURE` are hints describing a bean's role. They do not by themselves dictate whether a bean is autowirable; autowire eligibility follows separate metadata and dependency rules.

If a registrar creates a helper bean that must not become a regular injection candidate, consider `definition.setAutowireCandidate(false)`. Ensure doing so does not break a dependency that genuinely needs that helper bean. Do not set `ROLE_INFRASTRUCTURE` expecting Spring to automatically disable autowiring.

## 10. Two Overloads of registerBeanDefinitions

### 10.1. Two-Parameter Overload

```java
@Override
public void registerBeanDefinitions(
        AnnotationMetadata importingClassMetadata,
        BeanDefinitionRegistry registry) {
    // Read metadata and register bean definitions.
}
```

This is the simplest option and what the full runnable example uses. It fits when you **assign explicit names** such as `greeting.email` and do not need the framework's `BeanNameGenerator`.

### 10.2. Three-Parameter Overload

```java
@Override
public void registerBeanDefinitions(
        AnnotationMetadata importingClassMetadata,
        BeanDefinitionRegistry registry,
        BeanNameGenerator importBeanNameGenerator) {
    // Can use naming strategy for imported beans.
}
```

The `importBeanNameGenerator` parameter is supplied so a registrar can honor the naming strategy when creating definitions following framework conventions. If you override the three-parameter overload, Spring invokes it directly; you do not have to call the two-parameter overload yourself unless you want to.

**Note:** The naming strategy for imported beans has a default and can be customized via `ConfigurationClassPostProcessor` configuration. Do not assume every registrar must run `AnnotationBeanNameGenerator` for every bean, or that `BeanNameGenerator` applies when you intentionally build domain names like `greeting.email`.

### Avoid Empty Overrides or Wrong Overloads

Because both methods are default methods in Spring Framework 6.2, you must **override at least one meaningful method**. Implementing the interface without overriding either method compiles cleanly while registering zero definitions—tricking users into thinking the feature is active.

Do not put your code in the two-parameter overload and also add an empty three-parameter override: your three-parameter method intercepts the default delegation and prevents your registration logic from running.

## 11. Ensuring Bean Names Do Not Collide

Because registrars generate names programmatically, define a **collision policy** before registering.

Conservative pattern:

```java
String name = "greeting." + channel;

if (registry.containsBeanDefinition(name) || registry.isAlias(name)) {
    throw new IllegalStateException(
            "Bean name already used: " + name);
}

registry.registerBeanDefinition(name, definition);
```

**Scope of the check:** `containsBeanDefinition` checks whether a definition already exists in the registry **at that point in time**. Another bean name might be registered later; therefore, a registrar's collision policy must align with the container's overriding policy and integration tests. A pre-check alone does not guarantee immunity from every future conflict.

### Overriding Existing Bean Definitions?

Some BeanFactories permit overriding. Yet registry-level customization should not rely on “last registration wins”, because ordering and override policies can vary across environments, Boot settings, and versions.

If you want an extension point users can override:

- Define fixed bean names or a clear contract.
- Document when the registrar backs off from an existing definition and when it throws an error.
- Ensure deterministic behavior under different config import orders.
- Write integration tests covering a user-defined custom bean with the same name.
- Never silently replace a business-critical bean with another implementation without warning.

**The demo uses a fail-fast policy** on duplicate definition/alias names. That is an intentional choice of the demo library, not a mandatory rule for all registrars.

## 12. Multiple Configuration Classes Importing the Same Registrar

Suppose multiple classes carry `@EnableGreetings` or import the registrar via different paths:

```java
@Configuration
@EnableGreetings({"email"})
class EmailConfig {
}

@Configuration
@EnableGreetings({"sms"})
class SmsConfig {
}
```

This situation needs **dedicated tests** for how Spring processes imports, deduplication, and metadata in the actual application context being used. Never design a library assuming “the registrar is guaranteed to run exactly once per JVM”.

If a registrar can be invoked multiple times:

- Never use a mutable static counter to determine bean names.
- Define whether the same bean name with identical config is idempotent or an error.
- When different importing classes supply different attributes, process each metadata set per framework mechanics or enforce a clear aggregated configuration.
- If two sources register the same name, enforce a consistent collision policy.
- Never rely on import order as business priority.

In the full example, there is only **one `AppConfig`** carrying `@EnableGreetings({"email","sms"})`. That keeps output straightforward to verify and avoids untested assumptions about multiple import chains.

## 13. Aware Interfaces, Constructor Injection, and Environment

A registrar may need environment configuration or a resource loader **at definition-registration time**. Spring's Javadoc allows registrars to implement several `Aware` interfaces:

- `EnvironmentAware`.
- `BeanFactoryAware`.
- `BeanClassLoaderAware`.
- `ResourceLoaderAware`.

Spring invokes the corresponding callbacks **before** running `registerBeanDefinitions(...)`. Alternatively, a registrar may declare **a single constructor** taking one or more parameters of the supported types:

- `Environment`.
- `BeanFactory`.
- `ClassLoader`.
- `ResourceLoader`.

### Example Reading Environment

```java
// Illustrative snippet inside a registrar, not a standalone project.
final class FeatureRegistrar
        implements ImportBeanDefinitionRegistrar, EnvironmentAware {

    private Environment environment;

    @Override
    public void setEnvironment(Environment environment) {
        this.environment = environment;
    }

    @Override
    public void registerBeanDefinitions(
            AnnotationMetadata importingClassMetadata,
            BeanDefinitionRegistry registry) {
        boolean enabled = environment.getProperty(
                "features.reporting.enabled", Boolean.class, false);
        if (!enabled) {
            return;
        }

        BeanDefinition definition = BeanDefinitionBuilder
                .genericBeanDefinition(ReportAdapter.class)
                .getBeanDefinition();
        registry.registerBeanDefinition("reportAdapter", definition);
    }
}
```

This example requires `ReportAdapter` and related imports. Reading `Environment` during configuration processing can make sense when the result is **stable for that context startup** and does not require instantiating business beans beforehand.

### Do Not Use BeanFactoryAware to Execute Business Logic

Receiving `BeanFactory` does not mean every bean has been instantiated. Avoid calling `getBean` from a registrar to open connections, run migrations, or trigger workflows. If a bean created later genuinely needs a dependency, use constructor arguments, references, qualifiers, or BeanFactory resolution at creation time.

### ClassLoader and ResourceLoader

These can be used when you need to inspect metadata/resources to drive registration decisions. Be careful with dynamic class loading and AOT/native images. If class lists come from untrusted sources, validate against an allowlist and never let raw user configuration instantiate arbitrary classes.

## 14. Comparing ImportBeanDefinitionRegistrar with BeanDefinitionRegistryPostProcessor

The names of these two extension points look very similar, yet they operate in **different contexts and phases**.

| Criterion | `ImportBeanDefinitionRegistrar` | `BeanDefinitionRegistryPostProcessor` |
| --- | --- | --- |
| Typical participation | `@Import(Registrar.class)` or `ImportSelector` | BeanFactory/registry-level post-processor bean |
| Key input | Importing class's `AnnotationMetadata` + registry | `BeanDefinitionRegistry` during post-processing callback |
| Focus | Add definitions driven by imported configuration metadata | Inspect/modify/register definitions during post-process phase |
| `@Enable` annotation fit | Very strong fit | Not the primary interface for composed `@Enable` |
| Can add bean definitions | Yes | Yes, within its lifecycle |
| Registered by a registrar as a new post-processor | **Should not / must not per Javadoc** | Must enter via the proper lifecycle path, not via a registrar |

Most importantly: the Javadoc of `ImportBeanDefinitionRegistrar` explicitly states that **`BeanDefinitionRegistryPostProcessor` types may not be registered here**, due to lifecycle constraints while Spring processes `@Configuration` classes. Never ignore this warning or try to register a special infrastructure post-processor directly from a registrar.

If you need to mutate definitions already registered by multiple sources or participate in post-processor ordering, study `BeanDefinitionRegistryPostProcessor` separately. If your goal is implementing an `@EnableFeature` API driven by annotation attributes to add beans, a registrar is usually the more direct choice.

## 15. Relationship with @ImportSelector and DeferredImportSelector

`@Import` can process:

- Regular `@Configuration` classes.
- Eligible component classes.
- Classes implementing `ImportSelector`.
- Classes implementing `ImportBeanDefinitionRegistrar`.

`ImportSelector` returns **class names** to import, such as conditional configuration classes. It does not call `registry.registerBeanDefinition(...)` directly in its main interface. A registrar, by contrast, **creates bean definitions directly** from metadata.

Conceptual example:

```java
// API illustration, not a runnable example.
public class MySelector implements ImportSelector {
    @Override
    public String[] selectImports(AnnotationMetadata importingClassMetadata) {
        return new String[]{SpecificConfig.class.getName()};
    }
}
```

`DeferredImportSelector` also differs in processing timing/order, often useful for configuration sets chosen after regular configuration parsing steps; in Spring Boot, more intricate auto-configuration mechanisms build on those corresponding extension points.

Do not swap selectors and registrars mechanically. Choose based on **the kind of output you need to produce**:

- Selecting configuration classes: selector.
- Registering definitions driven by metadata: registrar.
- Declaring 1–2 fixed beans: `@Bean` is usually enough.

An `ImportSelector` can also return a registrar class name so Spring continues processing it through the import pipeline. That fits libraries that genuinely need to pick a registrar conditionally.

## 16. Working with Scopes and Lazy Beans

A registrar can register definitions with different scopes. Still, that is metadata, not Java constructor behavior.

### Singleton (Default)

```java
BeanDefinition def =
        BeanDefinitionBuilder.genericBeanDefinition(Worker.class)
                .getBeanDefinition();
registry.registerBeanDefinition("worker", def);
```

Without changing scope, the default is singleton. Within one `ApplicationContext`, repeated calls to `context.getBean("worker")` typically return the same object.

### Prototype

```java
BeanDefinition def = BeanDefinitionBuilder
        .genericBeanDefinition(Worker.class)
        .setScope("prototype")
        .getBeanDefinition();
registry.registerBeanDefinition("worker", def);
```

BeanFactory creates a fresh instance each time it resolves the prototype. If a singleton injects the prototype once into its constructor, the singleton keeps that single instance; to obtain a prototype per job, use `ObjectProvider<Worker>` or a dedicated factory.

### Lazy Singleton

```java
BeanDefinition def = BeanDefinitionBuilder
        .genericBeanDefinition(Worker.class)
        .setLazyInit(true)
        .getBeanDefinition();
registry.registerBeanDefinition("worker", def);
```

A lazy singleton may not be created during the pre-instantiation phase; however, another eager dependency can still force earlier creation. Do not confuse `setLazyInit(true)` with “the definition will not exist in the registry yet”: the definition is already registered; only **instantiation** can be deferred.

**Note:** `BeanDefinitionBuilder` configures metadata. Never call `new Worker()` inside a registrar and stash objects in a static map; that bypasses intended IoC semantics.

## 17. Bean Names, Qualifiers, and Candidate Counts

Suppose a registrar registers two beans of the same class:

```text
greeting.email -> GreetingHandler("email")
greeting.sms   -> GreetingHandler("sms")
```

An injection point:

```java
GreetingDashboard(GreetingHandler handler) {
    this.handler = handler;
}
```

is ambiguous unless Spring has a winning candidate under selection rules. Whereas:

```java
GreetingDashboard(
        @Qualifier("greeting.email") GreetingHandler handler) {
    this.handler = handler;
}
```

requests a specific bean. In the sample project, the qualifier is placed right on the `@Bean` method parameter to illustrate selection.

If the goal is using **all** handlers, another bean can inject `List<GreetingHandler>` or `Map<String, GreetingHandler>`. When ordering is needed, configure `@Order`/`Ordered` metadata or an equivalent policy and test it. Never assume “registered earlier” by a registrar guarantees business ordering.

### Bean Role Does Not Resolve Ambiguity

`definition.setRole(BeanDefinition.ROLE_INFRASTRUCTURE)` only marks an infrastructure role. It does not mark a bean as primary or create a qualifier. To pick a single candidate, use proper selection metadata/logic such as `@Primary`, qualifiers, autowire-candidate flags, or dedicated interfaces.

### Aliases Are Not New Definitions

`BeanDefinitionRegistry`/`BeanFactory` support names and aliases per contract. When legacy name compatibility is needed, you can register an alias, but **aliases do not increase the number of bean definitions**. Multiple names for one bean are different from two definitions sharing the same class.

## 18. Testing That a Registrar Truly Works

A common mistake is testing only:

```java
new GreetingRegistrar();
```

That call has no real `AnnotationMetadata`, no context `BeanDefinitionRegistry`, and runs none of Spring's configuration processing. It does not prove `@EnableGreetings` works.

### Context-Level Tests

In `RegistrarDemo`, you can add:

```java
// Additional snippet inside try with context.
if (!context.containsBeanDefinition("greeting.email")) {
    throw new AssertionError("Registrar did not register email");
}
if (!context.containsBeanDefinition("greeting.sms")) {
    throw new AssertionError("Registrar did not register sms");
}
if (context.getBeanNamesForType(GreetingHandler.class).length != 2) {
    throw new AssertionError("Unexpected GreetingHandler bean count");
}
if (!"email:Hello, Lan".equals(
        context.getBean("greeting.email", GreetingHandler.class).greet("Lan"))) {
    throw new AssertionError("Wrong constructor argument");
}
```

Assertions print no extra stdout when passing. They verify multiple layers:

1. Spring actually invoked the registrar via `@Import`.
2. Bean definitions were written into the registry.
3. BeanFactory created the right instances by type.
4. Each bean's constructor argument was applied as expected.

### Testing Failure Cases

Add dedicated test scenarios:

| Configuration | Expected Outcome to Verify |
| --- | --- |
| `@EnableGreetings({"email","sms"})` | Two definitions created and injectable by qualifier |
| `@EnableGreetings({"email","email"})` | Fails fast, reporting duplicate channel per demo policy |
| `@EnableGreetings({"Email"})` | Fails fast per demo's lowercase regex |
| Bean name `greeting.email` already exists before registrar runs | Does not silently override; verifies error or designed policy |
| Neither registrar imported nor handler declared | Zero handler beans |
| Registrar imported directly without `@EnableGreetings` | Clear failure due to missing metadata |
| Bean class constructor does not match arguments | Bean creation fails with clear root cause |
| Singleton vs prototype | Identity and lifecycle match scope |
| Multiple import chains | Definition count and collision/idempotency match contract |

In integration tests, use `AnnotationConfigApplicationContext` with configuration classes crafted specifically for each test case. Never mutate the BeanFactory of a live request-serving context to simulate bootstrap when the test just needs a fresh context.

### Low-Level Registrar Tests

You can test metadata registration logic against a mock registry or `DefaultListableBeanFactory`, but because custom annotations and `@Import` are processed by Spring at the configuration-class level, **integration tests with a real context** are the best way to verify the full pipeline.

## 19. Warnings on AOT, Native Images, and Over-Dynamic Behavior

When using Spring AOT/native images, bean definition registration behavior must align with how Spring analyzes configuration at build time and runtime. Deciding bean classes or bean structures based on runtime data unknown at build time can require explicit AOT design, hints, or customization.

A deterministic registrar driven by constant annotation attributes like `@EnableGreetings({"email","sms"})` is much simpler to analyze than:

- Fetching class names over the network at startup.
- Randomly scanning arbitrary packages based on external data.
- Changing the bean list based on an uncontrolled runtime API call.
- Generating unstable bean names from timestamps or randomness.
- Relying on dynamic proxies/reflection without supplying necessary native image hints.

**Do not assume `ImportBeanDefinitionRegistrar` automatically guarantees native compatibility.** If your target includes Spring AOT, test the corresponding build/runtime and consult AOT documentation for your exact framework version.

## 20. Performance and Security When a Registrar Adds Many Definitions

A registrar runs early. Even though it only registers metadata, creating large numbers of beans during refresh impacts memory, startup time, and the dependency graph.

Best practices:

- Keep operations inside a registrar **fast and deterministic**.
- Bound definition counts according to explicit requirements.
- Never fetch external data or make network calls from a registrar to decide dynamic beans, unless governed by a very specific, controlled bootstrap contract.
- Use namespaced/prefixed names such as `greeting.email` rather than an overly generic `handler`.
- Validate annotation attributes, class names, resource paths, and bean naming before writing to the registry.
- Never let untrusted values dictate arbitrary classes to instantiate without an allowlist/strict validation.
- Separate configuration logic from business side effects and verify lifecycle behavior.
- When creating beans holding secrets/resources, let BeanFactory manage constructor injection and cleanup; never put sensitive data into bean names or logs.

You can log the count of registered definitions at an appropriate level in dev/test, while avoiding logging sensitive configuration values.

## 21. Common Errors and How to Diagnose Them

| Symptom | Common Cause | Resolution |
| --- | --- | --- |
| Registrar is never called | Configuration class carrying `@Import`/`@Enable...` is not registered with Spring | Check root `@Configuration`, `@Import`, and bootstrap context |
| Registrar runs but no beans appear | Wrong overload/empty override; null metadata; `registerBeanDefinition` not called | Debug exact interface method and registry calls |
| `getAnnotationAttributes(...)` returns null | Annotation is on another class, registrar imported directly, or wrong annotation name | Read importing class metadata, validate, and fail clearly |
| `NoSuchBeanDefinitionException` | Bean name/type not registered or injection needs another bean | Check `containsBeanDefinition`, names, exposed types, and qualifiers |
| `NoUniqueBeanDefinitionException` | Registrar creates multiple beans of the same type while injection asks for one | Use qualifier/primary/collection as intended |
| `BeanCreationException` / constructor mismatch | Constructor args do not match bean class or dependency missing | Fix `BeanDefinitionBuilder` arguments and constructor |
| Bean name collision | Multiple registrars/configs generate the same name | Fail fast or apply a documented/tested override policy |
| Registrar runs repeatedly and fails | Duplicate imports or multiple different feature annotations | Define idempotency/deduplication and test import chains |
| Bean not yet initialized when registrar runs | Registrar operates in the definition phase | Do not invoke business beans from a registrar; use proper lifecycle hooks |
| Infrastructure-role bean still gets autowired | Role does not control candidate selection | Use autowire-candidate flag or qualifiers properly |
| Java `@Bean` cannot see handler | Registrar not imported into context or wrong qualifier name | Write an integration test with the real configuration |
| Duplicate bean definition despite pre-check | Another definition registered after the pre-check | Align with container override policy and add tests |
| Native image lacks bean or reflection metadata | Registration incompatible with AOT/runtime metadata | Review AOT hints, deterministic registration, and native tests |
| Registering `BeanDefinitionRegistryPostProcessor` from registrar hits lifecycle issues | Wrong extension point | Use the proper lifecycle registration mechanism for post-processors |
| Tests pass only with broad component scan | Registrar was omitted; scanner happened to create an alternate bean | Narrow test context and verify bean definition sources and names |

### Practical Debugging Sequence

1. Confirm the configuration class is present in `ApplicationContext`.
2. Confirm `@Import(Registrar.class)` is present directly or meta-present on a custom enable annotation.
3. Confirm the right `registerBeanDefinitions(...)` overload is overridden and executed.
4. Inspect `AnnotationMetadata` for expected annotation keys/values.
5. Inspect generated names, collisions, and skip/fail-fast conditions.
6. Check that `BeanDefinition` has the right class, scope, constructor args, and role.
7. Distinguish **definition present** from **instance created**.
8. Test `getBean(...)` and injection by type/qualifier in a real context.
9. Read the root cause of `BeanCreation`/`UnsatisfiedDependency` exceptions.
10. For AOT/Boot issues, verify extension points and lifecycle behavior for your exact framework version.

## 22. Exercises with Guided Answers

### Exercise 1 — When to Use a Registrar?

You only need to create `InvoiceService` with two fixed dependencies. Do you need `ImportBeanDefinitionRegistrar`?

**Answer:** Usually no. `@Bean InvoiceService invoiceService(Repository r, Policy p)` or `@Service`/constructor injection is clearer with less boilerplate. A registrar makes sense when dynamic metadata registration is driven by configuration/annotations.

### Exercise 2 — Where Does @Import Go?

An `AppConfig` class wants to enable `GreetingRegistrar`. Can you write:

```java
@Configuration(proxyBeanMethods = false)
@Import(GreetingRegistrar.class)
class AppConfig { }
```

If the main example's registrar reads `@EnableGreetings`, will this run cleanly?

**Answer:** Spring will import the registrar, but because `AppConfig` lacks `@EnableGreetings`, the demo logic sees `attributes == null` and fails fast. For it to work, use `@EnableGreetings({"email","sms"})` or update the registrar contract to support direct import.

### Exercise 3 — Creating a Definition or Creating an Instance?

Has `registry.registerBeanDefinition("x", def)` already invoked the bean class constructor?

**Answer:** Not by default. The registrar registers metadata; BeanFactory creates the instance later according to scope, eager/lazy initialization, and dependency resolution.

### Exercise 4 — Bean Names

With `@EnableGreetings({"email","sms"})`, which bean names does the demo registrar create?

**Answer:** `greeting.email` and `greeting.sms`. Both share the `GreetingHandler` class, yet have different constructor arguments. They are two bean definitions, not aliases.

### Exercise 5 — Reading AnnotationMetadata

Why not use `GreetingRegistrar.class.getAnnotation(EnableGreetings.class)` to get the channels?

**Answer:** Because the annotation is placed on the importing configuration class `AppConfig`. Spring supplies that class's `AnnotationMetadata` to the registrar. The registrar class's own metadata is not the configuration source to read.

### Exercise 6 — Constructor Injection

To register a `Worker` bean with constructor `Worker(String name)`, is this conceptually valid?

```java
BeanDefinition def = BeanDefinitionBuilder
        .genericBeanDefinition(Worker.class)
        .addConstructorArgValue("batch")
        .getBeanDefinition();
registry.registerBeanDefinition("worker.batch", def);
```

**Answer:** Reasonable; this supplies constructor argument metadata. `Worker` must have a matching constructor, and `BeanDefinition` and registry types must come from Spring APIs.

### Exercise 7 — Bean Alias or Second Bean?

If you call `registerBeanDefinition("greeting.email", def)` and then register an alias `legacyGreeting` pointing to `greeting.email`, do you have two definitions?

**Answer:** No. An alias is just another name for the same definition; the definition count remains one. Only registering **a second definition** under `greeting.legacy` adds another bean definition.

### Exercise 8 — BeanDefinitionRegistryPostProcessor

Can a registrar register a bean implementing `BeanDefinitionRegistryPostProcessor` so that it runs as a new post-processor?

**Answer:** You should not do this; the registrar Javadoc warns against registering these types from a registrar due to lifecycle constraints in configuration processing. Choose the proper extension point/post-processor registration path.

### Exercise 9 — Choosing an Implementation in a Java @Bean

There are two `GreetingHandler` beans, `greeting.email` and `greeting.sms`. A Java bean wants only email. How should the factory parameter be written?

```java
@Bean
GreetingDashboard dashboard(
        @Qualifier("greeting.email") GreetingHandler handler) {
    return new GreetingDashboard(handler);
}
```

**Answer:** Use `@Qualifier("greeting.email")` to select the candidate. Writing only `GreetingHandler handler` would be ambiguous because two candidates share that type.

### Exercise 10 — Validation

With `@EnableGreetings({"email","Email"})` in the demo, what should happen?

**Answer:** The registrar validates against regex `[a-z][a-z0-9-]*`, so `Email` is rejected (uppercase letter). This is a demo convention, not a mandatory Spring bean-naming rule.

### Exercise 11 — Aware/Constructor Injection on Registrars

A registrar needs `Environment` to decide whether to enable a feature. Must you create a Spring business bean just to read a property?

**Answer:** No. You can implement `EnvironmentAware` or declare a constructor with an `Environment` parameter from the supported types for registrars. Read stable values and register definitions; avoid initializing business beans early.

### Exercise 12 — Designing @EnableFeature

You want `@EnableDataAdapters({"mysql","postgres"})` to create one adapter bean per name. List the main components.

**Guided answer:**

1. Declare `@interface EnableDataAdapters` with `@Target(TYPE)`, `@Retention(RUNTIME)`, and `@Import(DataAdapterRegistrar.class)`.
2. Have the registrar read the names array from the importing class's `AnnotationMetadata`.
3. Validate the list and build stable names like `adapter.mysql`/`adapter.postgres`.
4. Build each adapter's `BeanDefinition` with a builder, setting constructor args/metadata appropriately.
5. Check the collision policy and call `registerBeanDefinition` for each entry.
6. Write integration tests creating an `AnnotationConfigApplicationContext` to verify definitions, injection, invalid values, and duplicate names.
7. If adapters connect to real DBs, avoid connecting inside the registrar; let BeanFactory and proper lifecycle hooks manage connections.

## 23. Checklist Before Putting a Registrar into a Library

- [ ] There is a genuine need for dynamic bean definition generation; `@Bean`/component scan cannot express it more cleanly.
- [ ] The registrar is wired into Spring configuration via direct `@Import` or a custom `@Enable...`.
- [ ] The right `registerBeanDefinitions` overload is overridden without accidentally shadowing default delegation.
- [ ] Configuration classes or business services are never instantiated to read annotation values; `AnnotationMetadata` is used instead.
- [ ] Annotation attributes are validated before registering definitions.
- [ ] Bean names are deterministic, namespaced, and governed by an explicit collision policy.
- [ ] `BeanDefinition` accurately sets class, constructor values, scope, role, autowire-candidate flag, and qualifiers if needed.
- [ ] Role metadata is not misused as a substitute for `@Primary`/`@Qualifier`.
- [ ] No resources are initialized, external services called, or child contexts created inside the registrar.
- [ ] No attempt is made to register `BeanDefinitionRegistryPostProcessor` from the registrar.
- [ ] Tests cover single/multiple beans, duplicate names, invalid values, and missing annotations.
- [ ] Real Spring context tests prove type/qualifier injection works.
- [ ] The distinction between definition registration and instance creation is well understood.
- [ ] For Spring AOT/native, determinism and required reflection/proxy metadata have been evaluated.
- [ ] Documentation explains how applications enable/disable the module and which public bean names it provides.

## Summary

`ImportBeanDefinitionRegistrar` is an extension point for **infrastructure layers needing to register `BeanDefinition`s from configuration-class metadata**. It pairs with `@Import` and is often packaged as a custom `@Enable...` annotation. The registrar reads `AnnotationMetadata`, builds definitions with `BeanDefinitionBuilder`/`RootBeanDefinition`, and adds them through `BeanDefinitionRegistry`. Instance management, scopes, dependency injection, and lifecycles **still belong to Spring BeanFactory**.

Use registrars to express **dynamic bean structures at startup** — not to execute business logic. Sound designs use stable bean names, validate metadata, guard against collisions, never touch uninitialized beans, and include integration tests proving actual behavior. For fixed beans, `@Bean` or stereotypes are usually simpler and more durable.

## Official Documentation

- [Spring Framework 6.2 — ImportBeanDefinitionRegistrar API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/ImportBeanDefinitionRegistrar.html): registrar contract, overloads, Aware/constructor injection, and warning regarding `BeanDefinitionRegistryPostProcessor`.
- [Spring Framework 6.2 — @Import API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/context/annotation/Import.html): import types supported by Spring.
- [Spring Framework 6.2 — BeanDefinitionRegistry API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionRegistry.html): registering and inspecting definitions.
- [Spring Framework 6.2 — BeanDefinitionBuilder API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/beans/factory/support/BeanDefinitionBuilder.html): building definitions with constructor args, scopes, and property values.
- [Spring Framework 6.2 — AnnotationMetadata API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/core/type/AnnotationMetadata.html): reading annotation data without creating instances.
- [Spring Framework 6.2 — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/6.2/core/beans/java.html): `@Configuration`, `@Bean`, `@Import`, and composition.
