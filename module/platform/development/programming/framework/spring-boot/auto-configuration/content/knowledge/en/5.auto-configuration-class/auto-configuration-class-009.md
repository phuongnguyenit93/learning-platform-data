# Distinguishing Public Extension Interfaces from Internal Auto-Configuration Implementation Classes in Spring Boot

## 1. Design Question: What May Users Extend, and What Should They Not Depend On?

When a library provides **Spring Boot auto-configuration**, users often only need to add a starter and use the generated beans. However, a solid library must also support scenarios such as replacing the default implementation, altering a processing step, registering callbacks, configuring via properties, or disabling an auto-configuration. To do that, you must distinguish the **public extension contract (public extension API/SPI)** from **internal auto-configuration implementation code**.

- **Public API:** interfaces, classes, annotations, data types, and properties that the library **intentionally publishes for applications to invoke and integrate against**. For example, `GreetingClient` lets an application call `greet(...)` without knowing the specific default class.
- **Public SPI / extension point:** contracts that applications or plugins **are permitted to implement or register themselves** to alter library behavior. For example, `GreetingCustomizer` lets applications register a callback customizing the greeting, or supply their own `GreetingClient` bean to replace the default.
- **Internal implementation:** classes, nested configurations, initialization algorithms, bean factory methods, and bean names that the library uses **to implement the default**. For example, `DefaultGreetingClient` is created inside `AcmeGreetingAutoConfiguration`, yet the application never needs `new DefaultGreetingClient(...)`.

**A Java class declared `public` does not automatically constitute a public contract that the author promises to keep stable.** In Spring Boot, the auto-configuration class itself usually needs a referenceable class name and is listed in the imports file. However, Spring Boot documentation explicitly states: for an auto-configuration class, **the aspect considered public API is the class name for configuration exclusion**; the class's contents (including nested configurations and `@Bean` methods) are internal and not recommended for direct use.

Goal of this lesson: define the API/extension/internal boundaries, build a Java 17+ demo with a **public interface**, **internal default implementation**, **conditional auto-configuration**, and **bean-based extension points**, and understand how to preserve compatibility for users when upgrading the library.

## 2. How to Tell the Two Contract Layers Apart

| Criterion | Published API/SPI for applications | Internal implementation / auto-config class |
| --- | --- | --- |
| Primary consumer | Application, plugin, business code | Spring Boot container and library author |
| Responsibility | Defines **what can be done**, and valid ways to extend/customize | Defines **how the default is created**, and under what conditions |
| Examples | `GreetingClient`, `GreetingCustomizer`, documented configuration properties | `DefaultGreetingClient`, default `@Bean` methods, nested `@Configuration` |
| Should the app call `new` directly? | May instantiate its own implementations conforming to the contract | Should not call `new` on library internal implementations |
| Expected stability | Governed by the library's compatibility/versioning policy; should be explicitly documented | May be refactored without preserving implementation details, except the auto-config class name used for exclusion/ordering |
| Replacement point | Declare a bean of the same API, callback/customizer, property, or designed bean qualifier | `@ConditionalOnMissingBean` lets the default bean back off |
| Consequence if broken | Consumer code may fail to compile, API behavior changes, callbacks stop running | Consumer code breaks only if it depended on implementation details, though breakage can still be a compatibility issue if internals were accidentally exposed |
| What to document? | Methods, semantics, thread safety, lifecycle, ordering, config keys, fallback | Just enough mechanism to explain conditions and troubleshooting; do not advertise as an extension point |

**Distinguishing API and SPI:** an API is typically what consumers **call**; an SPI is what consumers **implement/register**. They can be the same interface. For instance, `GreetingClient` is an API for calling `greet` and also an SPI for providing an alternative implementation. A callback such as `GreetingCustomizer` usually conveys the extension-point role more clearly.

Do not judge solely by package names like `internal` or `impl`. Published intent, Javadoc, documentation, and compatibility commitments determine whether a type is an extension contract. Package separation helps visibility, yet does not replace documentation.

## 3. Why Should You Not Call Methods Inside Auto-Configuration Directly?

Suppose Spring Boot has an auto-config:

```java
@AutoConfiguration
public class ExampleAutoConfiguration {
    @Bean
    @ConditionalOnMissingBean(Transport.class)
    Transport transport() {
        return new DefaultTransport();
    }
}
```

This is **illustrative code**: `Transport` and `DefaultTransport` are not defined, so it is not a standalone compilable program.

Boundary-respecting usage:

```java
@Service
public class ShippingService {
    private final Transport transport;

    public ShippingService(Transport transport) {
        this.transport = transport;
    }
}
```

The application depends on the **`Transport` interface** and receives the bean from the container. Auto-configuration may choose the default, or the user may register a custom implementation.

Usage **to avoid**:

```java
// Do not treat an auto-configuration class as an application factory API.
Transport transport = new ExampleAutoConfiguration().transport();
```

Problems:

1. A direct Java call bypasses `@ConditionalOnMissingBean`, dependency injection, bean lifecycle, and proxies/transformations applied by the container.
2. With Boot 3.x `@AutoConfiguration`, the configuration has `proxyBeanMethods=false`; calling a `@Bean` method directly is not intercepted as a bean container lookup.
3. The `transport()` method may be renamed, split up, or moved into a nested configuration without altering the library's **public** contract.
4. Even if the auto-config class is declared `public`, that is still **not an invitation** for consumers to invoke internal initialization logic directly.
5. If the library switches implementation from `DefaultTransport` to another implementation, business code should continue working as long as `Transport` behavior upholds its contract.

**Principle:** Consumers talk to **beans via interfaces**; the container and auto-config decide **how beans are supplied**. When the default decision needs changing, consumers use designed extension points instead of hardcoding imports of internal classes into business code.

## 4. The Auto-Configuration Class Name Is a Notable Exception

Spring Boot documentation confirms that even though an auto-configuration class has `public` visibility, the **class name** is the part considered public API because applications may want to **exclude the auto-configuration**:

```properties
spring.autoconfigure.exclude=com.acme.greeting.autoconfigure.AcmeGreetingAutoConfiguration
```

Another approach:

```java
@SpringBootApplication(excludeName =
    "com.acme.greeting.autoconfigure.AcmeGreetingAutoConfiguration")
public class DemoApplication {
}
```

These are **two alternative examples**; do not simultaneously exclude the auto-config in the demo when testing defaults. The class name in `excludeName` and the property must be the exact class name, not a bean name.

However, **merely because referencing the name for exclusion is permitted** does not mean you should treat the auto-config's `@Bean` methods, nested classes, or constructors as API. Authors may need to refactor:
- `@ConditionalOnClass` / `@ConditionalOnProperty` condition logic;
- method order and how nested configurations are split;
- implementation classes behind beans;
- method names and generated bean names (unless the library explicitly published a bean name as a separate contract).

When a **published public auto-configuration class changes name/package**, the ecosystem may still reference the old name via `before/after`, `spring.autoconfigure.exclude`, or `excludeName`. Spring Boot supports the file:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
```

Example:

```properties
com.acme.greeting.autoconfigure.LegacyGreetingAutoConfiguration=com.acme.greeting.autoconfigure.AcmeGreetingAutoConfiguration
```

The `AutoConfiguration.imports` file must be updated to list only the **new class**. `AutoConfiguration.replacements` informs Spring Boot of the relationship between old and new names in supported ordering/exclusion paths; it is not a mechanism that fixes every API change or every compiled Java reference.

If an application contains:
```java
import com.acme.greeting.autoconfigure.LegacyGreetingAutoConfiguration;
```
and directly compiles against the old class, adding a replacements file does not guarantee that Java code will compile once the old class is deleted. That illustrates why consumers should not treat auto-config classes as business types.

## 5. Library Architecture: Publish the Contract, Keep Defaults Internal

An extensible layout:

```text
acme-greeting/
├── api/
│   ├── GreetingClient.java       # Public API/SPI
│   └── GreetingCustomizer.java   # Public extension callback
└── autoconfigure/
    ├── AcmeGreetingAutoConfiguration.java  # Internal logic; class name can be excluded
    └── DefaultGreetingClient.java          # Internal default implementation
```

In a real release, the packages may live in separate modules:

- `acme-greeting-core` or `acme-greeting-api`: defines the API/SPI and public data types.
- `acme-greeting-autoconfigure`: selects default beans, checks conditions, and applies configuration.
- `acme-greeting-spring-boot-starter`: convenience dependency aggregator for quick application adoption.

This is **just one option**. Spring Boot does not force every starter into three modules; for a small library, a single module combining API + auto-config can work well. What matters is the **usage boundary**, not the number of artifacts.

**API/SPI should specify:**
- input/output shapes, nullability, exceptions, concurrency/thread-safety;
- when callbacks are invoked, frequency, and ordering;
- behavior when multiple implementations/callbacks exist;
- fallback when no implementation is provided;
- how to replace the default with a matching bean.

**Internal implementation may:**
- change algorithms, internal classes, constructors;
- reorganize factory methods or nested configurations;
- add caching, thread pools, instrumentation;
- swap supporting libraries as long as the public contract and behavior are preserved.

To avoid accidentally creating unnecessary API surface, implementations used solely inside the configuration package can be **package-private**. Java compilation prevents consumers in other packages from referencing that class directly; technical boundaries and documentation commitments reinforce each other.

## 6. Complete Example: Java 17+ and Spring Boot 3.3.13

The following example is a **single-module** Maven project you can copy and run. It fully demonstrates:

1. `GreetingClient` as an API for applications to call or implement.
2. `GreetingCustomizer` as an extension point registerable via `@Bean`.
3. `DefaultGreetingClient` as a **package-private** class unknown to the app.
4. `AcmeGreetingAutoConfiguration` as an `@AutoConfiguration` class in a separate package, creating the default bean via `@ConditionalOnMissingBean(GreetingClient.class)`.
5. `DemoApplication` importing only the API, never internal classes.
6. Three run modes: default, **decorate via callback**, and **override the entire implementation**.

### 6.1. Directory Structure

```text
public-spi-demo/
├── pom.xml
└── src/main/
    ├── java/
    │   ├── com/acme/greeting/
    │   │   ├── api/
    │   │   │   ├── GreetingClient.java
    │   │   │   └── GreetingCustomizer.java
    │   │   └── autoconfigure/
    │   │       ├── AcmeGreetingAutoConfiguration.java
    │   │       └── DefaultGreetingClient.java
    │   └── com/example/app/
    │       ├── DemoApplication.java
    │       └── UserGreetingConfiguration.java
    └── resources/
        ├── application.properties
        └── META-INF/spring/
            └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Package `com.example.app` **does not enclose** `com.acme.greeting.autoconfigure`. This lets us observe auto-config picked up by Spring Boot from the imports file rather than accidentally brought in by the application's component scan.

### 6.2. `pom.xml`

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>public-spi-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

`spring-boot-starter` suffices for the non-web example and `ApplicationRunner`. In a real starter, API/third-party dependencies can be separated by required vs. optional status so applications are not forced to pull in every integration.

### 6.3. `src/main/java/com/acme/greeting/api/GreetingClient.java`

```java
package com.acme.greeting.api;

/**
 * Public contract for producing greeting messages.
 */
@FunctionalInterface
public interface GreetingClient {
    String greet(String name);
}
```

Applications can call `GreetingClient.greet` or write their own implementation. The contract here is minimal: accept `name` and return a message. In a real library, clearly document whether `null` is allowed, thread safety, and errors on invalid input.

**No `@Component`** on the interface: it is a Java contract and does not create a Spring bean by itself. The bean will be supplied by auto-config or user configuration.

### 6.4. `src/main/java/com/acme/greeting/api/GreetingCustomizer.java`

```java
package com.acme.greeting.api;

/**
 * Public extension hook that can transform a greeting.
 */
@FunctionalInterface
public interface GreetingCustomizer {
    String customize(String message);
}
```

This is an **SPI/callback** for users to customize a processing step without reimplementing `GreetingClient`. This design illustrates one extension point; not every library needs callbacks if a replaceable interface suffices.

In the demo, customizers are invoked in `ObjectProvider.orderedStream()` order and expected to return a non-null string. A real-world SPI should explicitly document ordering, side effects, null policy, and exception policy before public release.

### 6.5. `src/main/java/com/acme/greeting/autoconfigure/DefaultGreetingClient.java`

```java
package com.acme.greeting.autoconfigure;

import java.util.List;

import com.acme.greeting.api.GreetingClient;
import com.acme.greeting.api.GreetingCustomizer;

final class DefaultGreetingClient implements GreetingClient {
    private final List<GreetingCustomizer> customizers;

    DefaultGreetingClient(List<GreetingCustomizer> customizers) {
        this.customizers = List.copyOf(customizers);
    }

    @Override
    public String greet(String name) {
        String result = "Hello, " + name + "!";
        for (GreetingCustomizer customizer : customizers) {
            result = customizer.customize(result);
        }
        return result;
    }
}
```

**This is the internal implementation:**

- The class has package-private visibility (no `public`), so code in `com.example.app` cannot `import DefaultGreetingClient`.
- It implements the public API `GreetingClient` and invokes any provided extension callbacks.
- Users see only the result of `greet`, without depending on this internal class.
- The class can change structure in an update as long as the public contract is honored.

Do not put `@Component` on this class, because we want **conditional auto-configuration** to explicitly decide whether to register the default.

### 6.6. `src/main/java/com/acme/greeting/autoconfigure/AcmeGreetingAutoConfiguration.java`

```java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.api.GreetingClient;
import com.acme.greeting.api.GreetingCustomizer;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeGreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingClient.class)
    GreetingClient greetingClient(
            ObjectProvider<GreetingCustomizer> customizers) {
        return new DefaultGreetingClient(
                customizers.orderedStream().toList());
    }
}
```

There are three key decisions here:

1. `@AutoConfiguration`: this class is a configuration candidate imported by Spring Boot via `AutoConfiguration.imports`, not a component the app discovers via package scan.
2. `@ConditionalOnMissingBean(GreetingClient.class)`: if the application already declared a bean compatible with the `GreetingClient` API, **the default is not registered**. This is the designed extension replacement point.
3. `ObjectProvider<GreetingCustomizer>`: collects zero or more callbacks. `orderedStream()` applies Spring's bean ordering mechanism for customizers; if a specific order is required in a library, document and test it.

The `greetingClient` method returns `GreetingClient`, i.e. **the public contract type**. In this lesson, the condition also checks `GreetingClient.class` itself, so the type metadata matches. For complex auto-configs whose conditions distinguish concrete subtypes, weigh Spring Boot's guidance on sufficiently specific `@Bean` return types while avoiding accidentally turning internal classes into public API.

**Why must `AcmeGreetingAutoConfiguration` still be `public`?** It needs to be recognized/loaded as an independent configuration class, and its class name can be used for exclusion. Still, application code should not call `greetingClient(...)` directly. To support users, the library author publishes `GreetingClient` and `GreetingCustomizer` as API/SPI.

### 6.7. `src/main/java/com/example/app/UserGreetingConfiguration.java`

```java
package com.example.app;

import com.acme.greeting.api.GreetingClient;
import com.acme.greeting.api.GreetingCustomizer;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class UserGreetingConfiguration {

    @Bean
    @ConditionalOnProperty(prefix = "demo", name = "mode",
            havingValue = "decorate")
    GreetingCustomizer vietnameseCustomizer() {
        return message -> message.replace("Hello,", "Xin chào,");
    }

    @Bean
    @ConditionalOnProperty(prefix = "demo", name = "mode",
            havingValue = "override")
    GreetingClient customGreetingClient() {
        return name -> "CUSTOM: " + name;
    }
}
```

Both methods belong to **application configuration**, inside the package scanned by `@SpringBootApplication`. They create two forms of extension:

- `demo.mode=decorate`: the user provides a `GreetingCustomizer` callback. Auto-configuration still supplies the default `GreetingClient`, while the implementation runs an extra user-extended step.
- `demo.mode=override`: the user provides **an entire custom `GreetingClient`**. The missing-bean condition makes the auto-config's default factory back off.

Note: the application **only imports the two interfaces in the `api` package**, never importing `DefaultGreetingClient` or instantiating `AcmeGreetingAutoConfiguration`. Both customization paths have clear meaning without touching internal details.

### 6.8. `src/main/java/com/example/app/DemoApplication.java`

```java
package com.example.app;

import com.acme.greeting.api.GreetingClient;
import com.acme.greeting.api.GreetingCustomizer;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ApplicationContext;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner report(
            GreetingClient client,
            ObjectProvider<GreetingCustomizer> customizers,
            ApplicationContext context) {
        return args -> {
            System.out.println("CLIENT=" + client.greet("Spring"));
            System.out.println("DEFAULT="
                    + context.containsBean("greetingClient"));
            System.out.println("CUSTOM="
                    + context.containsBean("customGreetingClient"));
            System.out.println("CUSTOMIZERS="
                    + customizers.orderedStream().count());
        };
    }
}
```

`GreetingClient` is injected by Spring into the `report` factory method. The runner uses the **public contract** without knowing which default implementation is behind it. `containsBean(...)` is purely for illustration to show which bean factory is active; production code should not rely on these internal bean names when a stable SPI already exists.

### 6.9. `src/main/resources/application.properties`

```properties
spring.main.banner-mode=off
spring.main.web-application-type=none
logging.level.root=OFF
demo.mode=default
```

`demo.mode` here is a **sample application property**, not a built-in Spring Boot feature and not required to be a library public property. Condition annotations on the application's `UserGreetingConfiguration` interpret it themselves.

`spring.main.web-application-type=none` lets the app print its lines and exit; `logging.level.root=OFF` keeps example output clean.

### 6.10. `src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.acme.greeting.autoconfigure.AcmeGreetingAutoConfiguration
```

In Spring Boot 3.x, this class name must appear in the imports file for the library to supply the auto-configuration candidate. A class in the file is **evaluated** yet may produce no bean if conditions do not match. This resource contains the auto-config class name, not the names of the public interface `GreetingClient`, callback `GreetingCustomizer`, or internal class `DefaultGreetingClient`.

### 6.11. Build and Run Three Scenarios

From the directory containing `pom.xml`, using Java 17+ and Maven:

```bash
mvn -q -DskipTests package
java -jar target/public-spi-demo-1.0.0.jar
```

**A. Default, with no callback and no user implementation**:

```text
CLIENT=Hello, Spring!
DEFAULT=true
CUSTOM=false
CUSTOMIZERS=0
```

The `greetingClient` bean is registered by auto-config using `DefaultGreetingClient`. The consumer receives only `GreetingClient`.

**B. Provide a public SPI callback without replacing the default client**:

```bash
java -jar target/public-spi-demo-1.0.0.jar --demo.mode=decorate
```

Lines printed by the program itself:

```text
CLIENT=Xin chào, Spring!
DEFAULT=true
CUSTOM=false
CUSTOMIZERS=1
```

This time `vietnameseCustomizer` is created because the property matches; `DefaultGreetingClient` applies the callback to the initial string `Hello, Spring!`. The default class remains managed by Spring. The user never touches internal constructors or methods of the auto-config.

**C. Provide a custom `GreetingClient` to replace the entire default**:

```bash
java -jar target/public-spi-demo-1.0.0.jar --demo.mode=override
```

Lines printed by the program itself:

```text
CLIENT=CUSTOM: Spring
DEFAULT=false
CUSTOM=true
CUSTOMIZERS=0
```

`@ConditionalOnMissingBean(GreetingClient.class)` sees the `customGreetingClient` bean declared by the application, so it **does not register** the default. The runner receives the user bean via DI. Replacing the bean by the `GreetingClient` interface requires no subclassing or copy-pasting of internal code.

All three cases prove: the exact same **public contract** serves business code, while auto-config/implementation varies according to defined conditions and extension points.

## 7. Why Is `@ConditionalOnMissingBean` a Crucial SPI Design Tool?

For a library providing defaults, the extension boundary is commonly defined as:

```java
@Bean
@ConditionalOnMissingBean(GreetingClient.class)
GreetingClient greetingClient(...) {
    // return default implementation
}
```

The meaning is not "Spring Boot always overrides beans", but rather: **if a matching `GreetingClient` bean exists at evaluation time, auto-config does not add the default**.

Spring Boot's bean conditions are sensitive to **bean definition processing order**. Spring Boot documentation recommends placing `@ConditionalOnBean` / `@ConditionalOnMissingBean` in auto-configurations because application-declared definitions are processed first. That keeps the SPI clear: consumer supplies a bean, default backs off.

To define the extension point properly, decide **what is checked**:

| Condition | What makes the default back off? | Risk if misused |
| --- | --- | --- |
| `@ConditionalOnMissingBean(GreetingClient.class)` | A bean matching the API/SPI type already exists | If the user only supplies a callback, it does not replace the entire client |
| `@ConditionalOnMissingBean(name = "greetingClient")` | A bean with that exact name already exists | A user implementation with another name can leave both beans registered |
| `@ConditionalOnMissingBean(DefaultGreetingClient.class)` | A matching **internal** implementation already exists | May fail to notice consumers creating a different `GreetingClient` implementation |
| `@ConditionalOnProperty(...)` | Property toggles conditionally | A property is not an interface for consumers to implement |
| `@ConditionalOnClass(...)` | Library class is present on the classpath | Having a class does not mean a bean or extension point exists |

Therefore, if the goal is allowing users to **supply a custom implementation**, the missing-bean condition should normally anchor on the **public SPI** (the interface users can implement), not on a specific internal class.

Even so, there is no single universal formula. In multi-feature auto-configs, consider candidates, subtypes, generics, annotations, and `ApplicationContext` scopes. Designs must explicitly test cases where the app has one or multiple matching beans.

### 7.1. `@Primary` and `@Qualifier` Do Not Replace API Design

An application with two `GreetingClient` beans can use `@Primary` or `@Qualifier` to pick one during DI, yet that differs from `@ConditionalOnMissingBean`:

- A missing-bean condition decides **whether to create the default**.
- `@Primary` and `@Qualifier` decide **which bean to select** when multiple candidates exist.
- A `GreetingCustomizer` callback is a **different extension point**, not directly selecting a client implementation.

When a custom client already exists, the demo's default is never registered in the first place; it is not created and then replaced afterward.

## 8. When to Use Callbacks vs. Replacing the Whole Bean?

Not every customization need should be solved by subclassing an internal implementation.

**Choose a public configuration property** when only a value needs changing (timeout, endpoint, flag), with the library providing `@ConfigurationProperties` and validation. Users do not have to write Java code for simple adjustments.

**Choose a callback/customizer SPI** when users need to alter a specific step in a pipeline, such as changing message formatting, adding headers, registering codecs, or adding a strategy. The callback contract should specify ordering and invocation timing; the demo uses `GreetingCustomizer`.

**Choose a public interface + user bean override** when users need to substantially replace the implementation, such as switching transport/messaging backends. `@ConditionalOnMissingBean` on the public interface lets the default back off.

**Choose an annotation/property toggle for an auto-config** when wanting to disable a default feature. `spring.autoconfigure.exclude` or `excludeName` provides exclusion at the auto-config level, though it **does not automatically supply replacement beans** for dependencies the application still requires.

**Do not choose to subclass an internal implementation** merely because its constructor happens to be `public` or you spotted its name in logs. If the library did not publish the class as an extension point, future releases may alter constructors/fields and break consumer code.

## 9. Version Compatibility Notes for Starter Authors

When evolving a library while avoiding breaking changes for users:

1. **Protect public interface contracts:** adding abstract methods to interfaces implemented by consumers risks source/binary compatibility. Consider `default` methods, new interfaces, or versioned SPIs depending on the situation.
2. **Preserve callback semantics:** changing ordering, invocation counts, or concurrency can alter plugin behavior even if method signatures stay identical.
3. **Test back-off:** every release should verify that when the app supplies its own bean, the default does not appear, and when it does not, the default works.
4. **Do not accidentally leak implementation types through APIs:** public methods accepting/returning internal classes, internal exception types, or docs instructing users to call implementation constructors create coupling.
5. **Separate bean names from type contracts:** if a bean name is part of public documentation, treat it as a contract. Otherwise, prefer guiding consumers toward DI by published interfaces or qualifiers.
6. **Mind auto-config class names:** changing an auto-config package/class affects exclusion/ordering and requires reviewing `AutoConfiguration.replacements` alongside updating imports.
7. **Document property schemas:** if `@ConfigurationProperties` exists, published keys are also a configuration interface; changing keys or defaults can cause breaking behavior.
8. **When optional dependencies are needed:** isolate integrations behind `@ConditionalOnClass`; do not force public APIs to mention optional library classes if users do not necessarily install that library.
9. **Respect scope/proxies/lifecycle:** user beans may be proxies or specially scoped; auto-config should receive beans via DI/`ObjectProvider`, never calling `new` on an internal class and bypassing the container.

**An auto-configuration class is not the library's public facade.** It is wiring code. Published API/SPI types and documented configuration properties are the intentional integration points.

## 10. Mistakes and Fixes

| Mistake | Impact | Fix by |
| --- | --- | --- |
| Application imports `DefaultGreetingClient` | Coupled to internal implementation; package-private demo won't even compile | Inject `GreetingClient` or supply a user implementation |
| Calling `new AcmeGreetingAutoConfiguration()` and invoking `greetingClient` | Bypasses bean conditions and lifecycle; won't compile if factory isn't public | Let Spring Boot import and inject the bean |
| Putting `@ConditionalOnMissingBean(DefaultGreetingClient.class)` on an overridable extension | Another user `GreetingClient` may fail to make the default back off | Check the interface `GreetingClient.class` itself |
| Treating an undocumented bean name as API | Renaming the factory method can break consumers | DI by designed type/qualifier; document the name if it must stay stable |
| Creating a customizer while expecting the default to vanish | Callbacks do not replace the client | To replace it, register a `GreetingClient` bean |
| Only excluding auto-config while still requiring its bean | Startup fails with missing dependency | Provide a replacement bean or stop using the feature |
| Auto-config sits inside `@ComponentScan` scope | May load at the wrong time or violate design | Keep in a separate package and use `AutoConfiguration.imports` |
| Library has a public API yet omits null/order/thread-safety docs | Different implementations interpret contracts differently | Clearly document contracts and write integration tests |
| Editing internal `@Bean` method bodies while promising undocumented bean names | Consumers depending on implementation details are affected | Allow customization only via public API/SPI |
| Renaming an auto-config class without updating imports and replacements | Exclusion/ordering by old name stops working | Update imports and provide appropriate replacement support |

### 10.1. What If `DefaultGreetingClient` Is Already Used Directly by an Application?

This happens when a library accidentally published an implementation class and consumers have relied on it for a long time. You should not treat it as an "unimportant detail" and delete the class immediately. Practical compatibility still depends on what users relied upon. You may need to:

- publish a replacement SPI;
- keep an adapter/deprecated compatibility class during a transition period;
- provide a migration guide;
- test both old and new paths before releasing a major version.

Distinguish "should be considered internal" from "can be deleted arbitrarily without affecting anyone". Accidentally exposed public surface may already have real downstream dependents.

## 11. Testing Contracts Instead of Testing Wiring Details

For a starter, verify **behavior observable from the consumer's perspective**:

| Case | What to verify |
| --- | --- |
| No extensions declared | Exactly one default `GreetingClient` bean exists; `greet` works properly |
| `GreetingCustomizer` present | Default client still runs and actually invokes the callback |
| Custom `GreetingClient` bean declared | Default backs off; consumer receives user implementation |
| Multiple callbacks present | Execution order matches docs and output is deterministic |
| Excluding auto-config | Default is not created; app knows how to supply a bean when needed |
| Optional SDK absent | Auto-config does not attempt to load classes tied to missing libraries |
| Upgrading internal implementation | Consumers compiled solely against API/SPI keep working |

Spring Boot provides `ApplicationContextRunner` in the test module to exercise many small context setups, while the `DemoApplication` illustration above uses actual runs for easy observation.

Manual verification example:

```bash
java -jar target/public-spi-demo-1.0.0.jar
java -jar target/public-spi-demo-1.0.0.jar --demo.mode=decorate
java -jar target/public-spi-demo-1.0.0.jar --demo.mode=override
```

Compare the three outputs in section 6.11. For libraries shipping across multiple versions, put those scenarios into automated tests to catch regressions in missing-bean conditions, callbacks, and compatibility.

## 12. Knowledge Check

**Question 1.** Why is `AcmeGreetingAutoConfiguration` a `public class`, yet applications should not call `greetingClient()`?

**Answer:** Spring Boot treats the **auto-configuration class name** as public API for exclusion. Nested configurations and `@Bean` methods are **internal**; they can change and direct calls bypass container mechanisms.

**Question 2.** If an application wants to alter the greeting format while still using the default client, which extension point makes sense?

**Answer:** Register `@Bean GreetingCustomizer`. The default client reads callbacks via `ObjectProvider` and applies them when `greet` is called.

**Question 3.** If an application wants to completely replace the `greet` algorithm, what should it do?

**Answer:** Create a bean implementing the public `GreetingClient`. The auto-config's `@ConditionalOnMissingBean(GreetingClient.class)` backs off the default under normal conditions.

**Question 4.** In the example, does `DefaultGreetingClient` not being `public` prevent Spring from creating the bean?

**Answer:** No. `AcmeGreetingAutoConfiguration` in the same package can invoke the package-private constructor; the `@Bean` method returns the public `GreetingClient` type and the container manages the returned object. The application never needs to know the concrete type name.

**Question 5.** If users simply rely on the bean name `greetingClient`, is that always a stable public contract?

**Answer:** No. It is a contract only when the library **explicitly publishes and commits** to that name. By default, prefer depending on the public interface.

**Question 6.** Why is `@ConditionalOnMissingBean(DefaultGreetingClient.class)` unsuitable for "allowing users to replace the client with their own implementation"?

**Answer:** Custom implementations are normally **not** `DefaultGreetingClient`, so the condition may miss the user's bean. Checking the public interface `GreetingClient.class` matches the intent.

**Question 7.** When renaming `AcmeGreetingAutoConfiguration`, what must you watch out for?

**Answer:** Update `AutoConfiguration.imports`, consider `AutoConfiguration.replacements` for old ordering/exclusion references, and do not expect the replacements file to fix direct Java imports in consumer code.

**Question 8.** What is the difference between API and SPI in the example?

**Answer:** API is the contract for code to **call** (`GreetingClient.greet`); SPI allows code to **extend/implement** (`GreetingCustomizer` or a user implementation of `GreetingClient`). One interface can serve both roles.

## 13. References

- [Spring Boot — Auto-configuration](https://docs.spring.io/spring-boot/reference/using/auto-configuration.html): the auto-config exclusion section explains **only the auto-config class name is public API**, while nested configs/bean methods are internal.
- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html): publishing auto-config in imports, `@ConditionalOnMissingBean`, class conditions, replacement files, starter modules, and callback interfaces.
- [Spring Framework — Java-based Container Configuration](https://docs.spring.io/spring-framework/reference/core/beans/java.html): `@Configuration`, `@Bean`, and how the container creates/injects beans.
- [Spring Boot — Testing Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html#features.developing-auto-configuration.testing): introduces `ApplicationContextRunner` for testing conditions.

**Takeaway:** publish **appropriate interfaces/callbacks/properties for applications to extend**, let the Spring container supply beans under those contracts, and let the auto-configuration class handle **conditional default wiring**. An `@AutoConfiguration` class can be `public` because its name is needed for exclusion, yet **its `@Bean` methods, nested configurations, and internal implementations are not extension APIs for applications to call directly**.
