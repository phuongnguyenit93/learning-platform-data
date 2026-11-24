# Providing Additional Bean Sources with addPrimarySources and setSources

## 1. Why Does SpringApplication Need Multiple Bean Sources?

During startup, `SpringApplication` must know **which bean definition sources** to include in the `ApplicationContext`. The most familiar case is:

```java
SpringApplication.run(MyApplication.class, args);
```

Here, `MyApplication.class` is the **primary source**. When this class is annotated with `@SpringBootApplication`, it typically brings in auto-configuration and component-scanning rules for the startup class's package and its subpackages. When a group of beans is defined in a **package outside the default scan scope**, or provided via configuration classes/XML for a particular launch combination, the application may need to declare additional sources.

`SpringApplication` provides two APIs directly related to this:

- `addPrimarySources(Collection<Class<?>>)`: **adds primary source classes** to the existing set of sources from the constructor. The argument consists of `Class<?>` objects.
- `setSources(Set<String>)`: **sets the collection of string-based additional sources**, which can be **fully qualified class names**, **package names**, or **XML resource locations**. This set is loaded **together with** the primary sources, rather than replacing them.

Only after configuration does `application.run(args)` create and refresh the `ApplicationContext`, during which Spring loads bean definitions from the corresponding sources.

> **Terminology distinction:** `primary source` here means an *application configuration/bean loading source*. It is **not** the `@Primary` annotation used to prioritize one bean when injecting dependencies among multiple beans of the same type. "Adding a source" also does not mean "creating exactly one bean": a `@Configuration` class can declare multiple `@Bean` methods and can import other configurations.

## 2. Three Source Sets and When They Are Used

Picture it like this:

```text
new SpringApplication(App.class)
        │
        ├── Initial primary sources
        │       └── App.class
        │
        ├── addPrimarySources(List.of(ExtraConfig.class))
        │       └── Adds ExtraConfig.class to primary sources
        │
        └── setSources(Set.of("com.example.other.NamedConfig"))
                └── Sets String-based additional sources
                                │
                          getAllSources()
                                │
               App.class + ExtraConfig.class
                     + "com.example.other.NamedConfig"
                                │
                             run(args)
                                │
                     Loads bean definitions
                                │
                        ApplicationContext
```

There are four/five API methods to distinguish:

| API | Parameter / Return Type | Meaning |
|---|---|---|
| `new SpringApplication(App.class)` | `Class<?>...` | Establishes the initial primary source class. |
| `addPrimarySources(...)` | `Collection<Class<?>>` | Adds primary source classes without removing the primary source from the constructor. |
| `setSources(...)` | `Set<String>` | Replaces the set of **string-based additional sources**. Does not remove primary sources. |
| `getSources()` | `Set<String>`, mutable | Inspects/adds/removes string-based additional sources. Does not include primary sources. |
| `getAllSources()` | `Set<Object>`, unmodifiable | Returns the union of primary sources and additional sources; elements can be both `Class` and `String`. |

**Addition and replacement happen on two different sets.** `addPrimarySources(...)` appends to the primary set, whereas calling `setSources(...)` replaces the current additional set with the supplied value. Even if you call `setSources(Set.of())`, the `App.class` source passed to the constructor still remains.

These methods should be called **before `run(args)`**. Once an `ApplicationContext` has been created and refreshed, modifying the source list on the `SpringApplication` object is not a mechanism for dynamically adding beans to a running context.

## 3. Runnable Java 17+ Example: One Primary Source and Two Additional Sources

Practice goal: the launcher class lives in `com.example.launch`, while two configuration classes live in sibling packages `com.example.extra.primary` and `com.example.extra.named`. Thus they are **not within the default scan range** of `@SpringBootApplication` placed in `com.example.launch`. We explicitly bring them into the context using the two corresponding APIs.

Source layout:

```text
source-demo/
├── settings.gradle
├── build.gradle
└── src/main/java/
    └── com/example/
        ├── launch/
        │   └── SourceLaunchApplication.java
        └── extra/
            ├── primary/
            │   └── WarehouseConfiguration.java
            └── named/
                └── FeatureConfiguration.java
```

`settings.gradle`:

```groovy
rootProject.name = 'source-demo'
```

`build.gradle` (Spring Boot 3.3.x example project, compatible Gradle wrapper, Java 17):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
}
```

The application does not need HTTP, so it uses `spring-boot-starter` and sets `WebApplicationType.NONE`. An actual project should retain its preconfigured plugin/Java versions if they differ from this example.

**File `src/main/java/com/example/extra/primary/WarehouseConfiguration.java`:**

```java
package com.example.extra.primary;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class WarehouseConfiguration {

    @Bean("warehouse")
    public String warehouse() {
        return "primary-class";
    }
}
```

**File `src/main/java/com/example/extra/named/FeatureConfiguration.java`:**

```java
package com.example.extra.named;

import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
public class FeatureConfiguration {

    @Bean("feature")
    public String feature() {
        return "string-class-name";
    }
}
```

**File `src/main/java/com/example/launch/SourceLaunchApplication.java`:**

```java
package com.example.launch;

import java.util.List;
import java.util.Set;

import com.example.extra.named.FeatureConfiguration;
import com.example.extra.primary.WarehouseConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.WebApplicationType;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.ConfigurableApplicationContext;

@SpringBootApplication
public class SourceLaunchApplication {

    public static void main(String[] args) {
        SpringApplication application =
                new SpringApplication(SourceLaunchApplication.class);

        // Add a Class to the primary sources group.
        application.addPrimarySources(List.of(WarehouseConfiguration.class));

        // A fully qualified class name is a String in the additional sources group.
        application.setSources(Set.of(FeatureConfiguration.class.getName()));

        // The example does not start a Web server, so the process can exit after printing.
        application.setWebApplicationType(WebApplicationType.NONE);

        System.out.println("Declared sources: " + application.getAllSources().size());

        try (ConfigurableApplicationContext context = application.run(args)) {
            System.out.println("warehouse=" +
                    context.getBean("warehouse", String.class));
            System.out.println("feature=" +
                    context.getBean("feature", String.class));
        }
    }
}
```

If the project has a Gradle Wrapper, run from the project directory:

```bash
./gradlew bootRun
```

Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

The lines printed by **the program itself** are:

```text
Declared sources: 3
warehouse=primary-class
feature=string-class-name
```

Besides those three lines, Spring Boot/Gradle may print the banner and startup/shutdown logs. The value `3` is the **number of declared sources**, not the total number of beans in the context. `WarehouseConfiguration.class` is loaded from `addPrimarySources`; `FeatureConfiguration` is loaded from its **fully qualified class name** in `setSources`. Each configuration class declares a uniquely named `String` bean to keep the verification simple and clear.

Note: the two packages `com.example.extra.*` both start with `com.example` but are not inside `com.example.launch`. Spring does not automatically scan **every package sharing a higher-level prefix**. That is why this example demonstrates the effect of adding sources.

### Observing Each API Through Controlled Changes

- Temporarily remove `application.addPrimarySources(...)` and run again: the `warehouse` bean is not declared by any remaining source. Calling `getBean("warehouse", String.class)` will fail with a bean-not-found error; `feature` remains an additional source. To observe `feature` before the error, swap the order of the two `getBean` lines or check `context.containsBean("feature")`.
- Restore the line above and remove `application.setSources(...)`: `warehouse` is still present because primary sources remain intact; the `feature` bean is not defined by the remaining sources, so `getBean("feature", String.class)` will fail.
- Restore both: both beans are loaded. This is experimental proof that the two source groups are **merged** when Spring starts up.

If you run with arguments or real configuration files that alter the source list or bean creation conditions, inspect those inputs as well before interpreting the results.

## 4. Using addPrimarySources Properly

API signature:

```java
void addPrimarySources(Collection<Class<?>> additionalPrimarySources);
```

`Class<?>` is an object representing a Java class, not a class name string. Use `List.of(...)` or an equivalent `Collection<Class<?>>`:

```java
SpringApplication application = new SpringApplication(App.class);

application.addPrimarySources(
        List.of(DatabaseConfig.class, BusinessConfig.class));

application.run(args);
```

This snippet only illustrates API configuration, assuming `App`, `DatabaseConfig`, and `BusinessConfig` are real classes on the classpath. Source classes are typically `@Configuration` classes or classes supported by Spring as bean definition sources. Do not pass arbitrary regular Java classes here expecting just any object to become a useful bean.

Key characteristics:

1. **Appends, does not replace:** `App.class` from the constructor is kept; `DatabaseConfig.class` and `BusinessConfig.class` are added.
2. **Can be called multiple times:** classes are merged into the primary sources set; because set semantics are used, passing the exact same `Class` object multiple times is not intended to create multiple distinct beans.
3. **Compile-time check for class presence:** writing `DatabaseConfig.class` lets the compiler verify that the referenced class is accessible. This is an advantage when configuring statically in Java code.
4. **Does not select default beans:** `primary` in the API does not make beans from this source win over beans of the same type defined in another source; selecting a bean during dependency injection is the responsibility of `@Primary`, `@Qualifier`, bean names, and Spring's resolution rules.
5. **Does not automatically expand application-wide package scanning:** adding a `@Configuration` class outside the scan area is an explicit way to load that configuration; scanning behavior depends on the annotations and actual configuration rules of each source.

The Spring Boot Javadoc notes that in most cases you can consider `getSources()`/`setSources(...)` instead of `addPrimarySources(...)`. However, this API is useful when you need to add **configuration classes via direct Java type references** to the primary set.

## 5. Using setSources Properly

API signature:

```java
void setSources(Set<String> sources);
```

Each `String` element can represent one of the source types supported by Spring Boot:

| Source Type | Example | Condition to Work |
|---|---|---|
| Fully Qualified Class Name (FQCN) | `"com.example.extra.named.FeatureConfiguration"` | The class is on the runtime classpath and can be loaded by Spring as a source. |
| Package name | `"com.example.plugins"` | There are components matching scanning rules in that package and on the actual classpath. |
| XML resource location | `"classpath:extra-beans.xml"` | A valid XML resource readable by `XmlBeanDefinitionReader`. |

### Supplying Configuration Classes by Fully Qualified Name

```java
SpringApplication application = new SpringApplication(App.class);
application.setSources(Set.of(
        "com.example.extra.named.FeatureConfiguration",
        "com.example.extra.audit.AuditConfiguration"));
application.run(args);
```

Here the strings are **class names**, not bean names. Spring must be able to find them on the classpath. When the class is known at coding time, `FeatureConfiguration.class.getName()` is safer than typing the name manually because IDE class renames usually update Java references.

### Supplying a Package Name to Scan

```java
SpringApplication application = new SpringApplication(App.class);
application.setSources(Set.of("com.example.plugins"));
application.run(args);
```

Package-based sources require classes recognized by Spring's scanner (for example classes annotated with `@Component`/`@Service` or `@Configuration`). Simply creating a plain unannotated POJO in that package does not mean Spring will register it as a bean. Consider the scan scope carefully, as broad scanning may load unintended components.

### Supplying an XML Source

With a valid `src/main/resources/extra-beans.xml` file, you can use:

```java
SpringApplication application = new SpringApplication(App.class);
application.setSources(Set.of("classpath:extra-beans.xml"));
application.run(args);
```

Minimal XML example declaring a bean named `externalName`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<beans xmlns="http://www.springframework.org/schema/beans"
       xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
       xsi:schemaLocation="
           http://www.springframework.org/schema/beans
           https://www.springframework.org/schema/beans/spring-beans.xsd">
    <bean id="externalName" class="java.lang.String">
        <constructor-arg value="from-xml"/>
    </bean>
</beans>
```

When the XML is on the classpath and parsed successfully, you can retrieve `context.getBean("externalName", String.class)`. Verify actual dependencies and XML resource readability when applying this to a specific project. This mechanism is intended for applications needing to integrate legacy XML configuration; for new Spring Boot applications, Java configuration is usually simpler.

## 6. Replacement vs. Appending: The Most Common Misconception

`setSources(...)` **sets the current additional sources set**, rather than meaning "append on every call".

```java
SpringApplication application = new SpringApplication(App.class);

application.setSources(Set.of("com.example.config.OneConfig"));
application.setSources(Set.of("com.example.config.TwoConfig"));

// Current additional sources: only "TwoConfig".
// Primary source App.class still remains.
```

If you want to append string sources while keeping existing ones, use the mutable set returned by the API:

```java
SpringApplication application = new SpringApplication(App.class);

application.setSources(Set.of("com.example.config.OneConfig"));
application.getSources().add("com.example.config.TwoConfig");

// Both OneConfig and TwoConfig are in additional sources.
```

Or gather all sources to load and call `setSources(...)` **once**:

```java
application.setSources(Set.of(
        "com.example.config.OneConfig",
        "com.example.config.TwoConfig"));
```

In all three snippets, `App`/`OneConfig`/`TwoConfig` are illustrative names; they must actually exist if you use them to run. Calling `getSources().add(...)` modifies the **additional sources set**, not the primary sources set.

To inspect them, you can use:

```java
System.out.println(application.getSources());
System.out.println(application.getAllSources());
```

In the simple model from section 3, `getSources()` contains one **string** with the `FeatureConfiguration` class name; `getAllSources()` contains three sources consisting of two `Class` objects and one `String`. `getAllSources()` is a combined read-only view that cannot be modified directly; to change sources, use the appropriate API **before running**.

## 7. A Loaded Bean Source Does Not Guarantee the Bean Is Ready to Use

Adding a source only gives Spring the opportunity to **read and register bean definitions**. Beans still depend on Spring's conditions and lifecycle:

- **`@Profile`:** a configuration or bean annotated with `@Profile("dev")` may be skipped when the `dev` profile is inactive.
- **`@Conditional...`:** a bean definition may only be registered when its condition is satisfied.
- **Constructor/`@Bean` dependencies:** the source was found, yet instantiation can still fail due to missing dependent beans, missing configuration, or service connection failures.
- **Duplicate bean names:** two sources introducing the same bean name can cause a duplicate definition error (Spring Boot normally disallows bean definition overriding by default). Do not resolve conflicts by arbitrarily enabling global overriding.
- **Classpath:** a declared FQCN or XML resource that is missing from the runtime package will cause source loading to fail; declaring a string does not automatically add a dependency or copy a resource into the JAR.

To check whether **a bean is present in the context**, use `containsBean(...)` or `getBean(...)` after `run(args)` finishes:

```java
try (ConfigurableApplicationContext context = application.run(args)) {
    System.out.println(context.containsBean("warehouse"));
}
```

When the project has no bean named `warehouse`, `containsBean` returns `false`; when it does, it returns `true`. Conversely, `getAllSources()` only proves the application is **declaring sources**, not that a specific bean was created successfully.

## 8. Comparison with Other Ways of Adding Beans

| Need | Common Mechanism | Difference from Modifying SpringApplication Sources |
|---|---|---|
| Add a `@Configuration` class outside component scan | `addPrimarySources(List.of(Config.class))` or `setSources(Set.of(Config.class.getName()))` | Loads the configuration directly during the bootstrap step. |
| Configuration known ahead of time from a configuration class | `@Import(Config.class)` | The import relationship lives in Spring configuration, requiring no imperative calls in `main`. |
| Scan a fixed package area | `@ComponentScan(basePackages = "...")` or a package-based source | Component scan can broaden the number of discovered components. |
| Declare a bean constructed by code | `@Bean` inside `@Configuration` | The `@Bean` method itself defines the bean; the source merely helps Spring find the configuration containing it. |
| Change runtime configuration values | `application.properties`, environment, command-line properties | These are configuration data (properties), not a list of classes/packages/XML used to load beans. |
| Register beans after the context is already running | Dedicated dynamic registration mechanism, if truly needed | Calling `setSources` after `run` cannot be treated as hot-reloading beans. |

For ordinary applications, a `@SpringBootApplication` class in a well-chosen root package, with related `@Configuration` classes scanned or `@Import`ed, is usually easier to understand and maintain. Use the two APIs covered here when **the decision on which sources to load must live in bootstrap code** or when sources must be assembled per environment/module.

## 9. Diagnosing Errors When Declaring Additional Sources

| Symptom | Possible Cause | How to Verify |
|---|---|---|
| `NoSuchBeanDefinitionException` for expected bean | Source not loaded, bean condition unsatisfied, or wrong bean name/type | Inspect `getAllSources()`; check annotations, profiles/conditions, bean names, and packages. |
| Class not found when loading string source | Typo in FQCN or class/dependency missing on classpath | Check `setSources` strings, verify class/path in build output and JAR. |
| XML parsing failure | Wrong resource location, invalid XML, or missing supporting dependency | Confirm the file under `src/main/resources` and `classpath:...` path; read the root exception. |
| More beans loaded than intended | Package source / component scan is too broad | Narrow the package; use `@Import`/specific configuration classes if appropriate. |
| Duplicate bean names or bean definition conflict | Two configurations declare the same bean name or are scanned redundantly by another mechanism | Cross-check all sources and component scan ranges, fix duplicate names/configurations. |
| Called `setSources` twice and lost the first source | The second call **replaces** the additional sources set | Use a single complete `Set` or `getSources().add(...)`. |
| Treating `getAllSources().size()` as the bean count | Source != bean; one source can produce many beans | Use `context.getBeanDefinitionNames()` or query specific beans after startup. |
| Modified sources while the application is running with no effect | Context has already been refreshed | Set sources before `run` and restart when needed. |

Do not rely on the element order of the sources set to control dependency injection priority or conflict resolution. Even if a `LinkedHashSet` preserves iteration order, that does not create a guarantee that "beans from later sources beat earlier ones". Use proper Spring mechanisms for bean selection.

## 10. Self-Verification Exercises

Perform these using the project in section 3, changing only one factor at a time:

1. Run with both `addPrimarySources(...)` and `setSources(...)`; confirm the source count is `3` and both `warehouse` and `feature` beans exist together.
2. Temporarily remove `addPrimarySources(...)`. Replace `getBean("warehouse", ...)` with `containsBean("warehouse")` so the application does not stop with an exception; verify `false`. Keep `getBean("feature", ...)` to see the remaining bean.
3. Restore the primary source, temporarily remove `setSources(...)`. Verify `containsBean("feature") == false` while `warehouse` still appears.
4. Replace the string source of `FeatureConfiguration` with a mistyped FQCN, then observe the source loading failure. Restore the correct name; consider using `FeatureConfiguration.class.getName()` when code directly references the class.
5. Try calling `setSources(...)` twice with two different sources; print `getSources()` before `run` to verify only the final set is kept, then fix it to a single call with the complete set.

If you can explain these three points in your own words, you have mastered the mechanism: **(a)** how primary sources differ from additional sources, **(b)** why `setSources` does not remove the class passed to the constructor, and **(c)** why a source present in `getAllSources()` still does not guarantee that the expected bean is created.

## References

- Spring Boot 3.3 API, `SpringApplication`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/SpringApplication.html
- Read the JavaDoc directly for `addPrimarySources`, `setSources`, `getSources`, and `getAllSources` to verify signatures, valid source types, and the meaning of each source set before applying them to another Spring Boot version.