# Classpath, ClassLoader, and Optional Dependency Presence

> **Scope:** Foundational knowledge for understanding Spring Boot auto-configuration, illustrated on Java 17 and Spring Boot 3.3.x. The topic is optional dependency presence at **runtime**: why the same library can auto-configure a bean in one application and not in another; and why checking for class presence alone is sometimes still insufficient.

## 1. Learning objectives

After this lesson, you should be able to answer and practice the following questions:

1. What is the **classpath**? How do compile classpath, runtime classpath, and test classpath differ?
2. What is a **ClassLoader** used for; does a JAR file being present in the build mean the current JVM sees every class inside that JAR?
3. What does an **optional** dependency mean for a library author versus a consuming application?
4. How does Spring Boot evaluate `@ConditionalOnClass` and `@ConditionalOnMissingClass`; when should you use `name` instead of `value`?
5. How do you design and test an optional integration so the application still starts when the integration JAR is absent?

Guiding principle: **The classpath determines which classes can be found; the ClassLoader determines visibility scope and how classes are loaded; auto-configuration uses conditions to decide whether to register beans.** These three concerns are related, not identical.

## 2. What is the classpath?

A Java program is compiled from `.java` into `.class`. To compile and run the program, tools and the JVM must know where to find the relevant classes and resources. The set of paths to directories containing `.class` files and JARs used in a given context is collectively called the **classpath**.

In a project with a build tool, do not think of the classpath as a single immutable list:

| Context | Purpose | Example dependencies that may appear |
| --- | --- | --- |
| **Compile classpath** | `javac` resolves type, method, and field names during compilation | APIs needed for source code to compile |
| **Runtime classpath** | JVM / framework loads classes and resources when the app runs | Implementations, JDBC drivers, SDKs, optional integrations |
| **Test classpath** | Compile/run tests; often extends the classpath | JUnit, AssertJ, test containers, mock libraries |
| **Classpath of a specific ClassLoader** | Scope of classes and resources visible to that loader | May be a subset of the overall app runtime, depending on loader topology |

A class can be present on the compile classpath yet **absent at runtime**. Conversely, a JDBC driver may only be needed on the runtime classpath if the application does not directly reference driver classes in source code.

### 2.1. Standalone Java example, runnable with JDK 17

Create `ClasspathProbe.java`:

```java
public class ClasspathProbe {
    public static void main(String[] args) {
        String target = args.length == 0
                ? "java.time.Instant"
                : args[0];

        ClassLoader loader = Thread.currentThread()
                .getContextClassLoader();

        try {
            Class<?> type = Class.forName(target, false, loader);
            System.out.println("PRESENT: " + type.getName());
        } catch (ClassNotFoundException ex) {
            System.out.println("ABSENT: " + target);
        }
    }
}
```

Run:

```bash
javac ClasspathProbe.java
java ClasspathProbe
java ClasspathProbe example.missing.OptionalClient
```

The two output lines printed by the program, corresponding to the two `java` commands:

```text
PRESENT: java.time.Instant
ABSENT: example.missing.OptionalClient
```

`Class.forName(name, false, loader)` asks the specified loader to locate and link the class while **not proactively running the static initializer** of that class. `false` does not mean all linkage errors are eliminated. If the class exists yet depends on another missing type, a `LinkageError` such as `NoClassDefFoundError` can still occur.

This example only measures whether the current loader can find a class. It **does not** prove a Spring bean is created, an external resource is ready, a database is reachable, or APIs between two libraries are compatible.

### 2.2. Adding a JAR via `-cp` does not automatically enable every feature

Suppose you have a library `vendor-client.jar`:

```bash
java -cp "app.jar:vendor-client.jar" com.example.Main
```

On Linux/macOS, the traditional classpath separator is `:`; on Windows, it is `;`:

```powershell
java -cp "app.jar;vendor-client.jar" com.example.Main
```

This is a **traditional Java classpath** command example. A Spring Boot executable JAR typically stores libraries inside `BOOT-INF/lib` and uses its own launcher mechanism; `java -jar app.jar` does not honor `-cp` to append arbitrary external JARs. When investigating a packaged Spring Boot application, inspect how the launcher and build plugin actually construct the runtime classpath.

Adding `vendor-client.jar` only makes the classes visible. Spring Boot still has to pick up the auto-configuration, class/bean/property conditions must match, and the bean must instantiate successfully.

## 3. ClassLoader: who sees which classes?

`ClassLoader` is the JVM mechanism for locating bytecode, defining classes, and finding resources. Standard loaders in modern Java follow a bootstrap, platform, and application hierarchy; additionally, frameworks, application servers, or plugin systems may create custom loaders.

Common model:

```text
Bootstrap loader
  -> foundational Java classes
         |
         v
Platform loader
  -> platform modules managed by the platform loader
         |
         v
Application / System ClassLoader
  -> application classpath, runtime dependencies
         |
         v
Custom loader (when used)
  -> plugin JARs, submodules, isolated scopes
```

**Parent delegation** is the common behavior: a loader typically asks its parent to find a class before searching itself. This is not a rigid rule for every custom loader. In containers or plugin systems, two loaders can see different sets of JARs.

A class in the JVM is not identified solely by its fully qualified name such as `com.vendor.Client`; **the defining loader is also part of the type's identity**. Two different loaders defining the same class name create two distinct types, leading to confusing cast or injection errors. Never assume "same class name" means the same type in every environment.

### 3.1. Thread Context ClassLoader

Many frameworks use `Thread.currentThread().getContextClassLoader()` (TCCL) to discover libraries and resources according to the calling thread's context. It may differ from the loader of the currently executing class.

APIs to distinguish:

| API | What does it tell you? | Point to remember |
| --- | --- | --- |
| `SomeType.class.getClassLoader()` | Loader that defined `SomeType` | May return `null` for classes defined by the bootstrap loader |
| `Thread.currentThread().getContextClassLoader()` | Context loader of the thread | May change across environments; not necessarily the loader that defined the current class |
| `Class.forName(name, false, loader)` | Requests finding/linking the class with the chosen loader | Can throw `ClassNotFoundException` or other linkage errors |
| `loader.loadClass(name)` | Finds/loads the class via the loader | Does not trigger static initialization by default |
| `loader.getResource("META-INF/...")` | Searches for a resource by path | Finding a resource does not prove all related classes can be loaded successfully |

Spring Boot also has abstractions that read metadata **without initializing classes upfront**; this is critical for libraries with optional dependencies.

### 3.2. Loading, linking, and initialization are not the same thing

Overview of class lifecycle:

1. **Loading:** locate bytecode and create the `Class` representation.
2. **Linking:** verify bytecode, prepare state, and resolve references per JVM rules; not every reference must be resolved at the exact same moment.
3. **Initialization:** run static initializers and static field initialization.

Placing `SomeOptionalType.class` or `new SomeOptionalType()` where it gets loaded too early can prevent the application from evaluating conditions in time. Conversely, reading annotation metadata with an appropriate parser avoids loading optional types before needed.

## 4. What does an optional dependency actually mean?

There are two separate questions:

- **Dependency resolution:** Does the build tool place that artifact onto the classpath of the **consuming application**?
- **Runtime condition:** At the time Spring Boot evaluates conditions, does the relevant loader see the feature's marker class?

Declaring a dependency optional affects how the dependency is propagated to consumers. It **does not** automatically create a Spring condition, nor does it prevent your own library from using that class while being compiled or tested.

### 4.1. Maven: `optional=true`

In the POM of an integration library:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <optional>true</optional>
</dependency>
```

Within the **project itself** that declares the dependency, Jackson still participates in the dependency's scopes (the default is `compile`, so it is also present in that project's runtime). When another application adds your library as a dependency, Maven **does not propagate Jackson as a transitive dependency** across this edge marked optional. An application that wants the Jackson feature must declare the appropriate dependency or use a starter that intentionally provides it.

Therefore, never interpret `optional=true` as "this JAR is absent even when running tests inside this project" or "Spring automatically knows to skip the bean". Spring needs classpath conditions to decide about beans.

### 4.2. Gradle: `compileOnly`, `implementation`, `runtimeOnly`

Gradle Groovy DSL example for an **autoconfigure module**:

```groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'
    compileOnly 'com.fasterxml.jackson.core:jackson-databind'
    testImplementation 'com.fasterxml.jackson.core:jackson-databind'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

This is an **illustrative configuration snippet**, not a standalone Gradle file: versions must be managed via the Spring Boot BOM/plugin or version constraints in a real project. In this module, `compileOnly` lets integration code compile against Jackson without putting Jackson on the runtime classpath from that declaration alone; `testImplementation` puts Jackson in the test environment. If the consuming application wants the feature, the application or starter must provide the runtime dependency.

| Gradle configuration | Typical meaning for `java-library` |
| --- | --- |
| `api` | Dependency exposed in the public API that consumers also need to compile |
| `implementation` | Internal dependency to compile/run the module, included in the consumer's runtime dependencies per published metadata |
| `compileOnly` | Needed only when compiling the module; does not mean consumers receive the dependency automatically |
| `runtimeOnly` | Needed at runtime, not used directly to compile source code |
| `testImplementation` | Dependency used for module tests; does not mean consumer runtime |

**Note:** Maven `optional` and Gradle `compileOnly` are not keywords with identical metadata-publishing semantics. Always inspect the published POM/Gradle Module Metadata and the **actual consumer classpath**.

### 4.3. "Having the dependency" is not enough to enable auto-configuration

| Situation | Possible outcome |
| --- | --- |
| Jackson is on the compile classpath, absent at runtime | Code compiles, yet `@ConditionalOnClass(ObjectMapper)` does not match at runtime; or linkage error if code references it improperly |
| Jackson is present at runtime, yet `demo.json.enabled=false` | Class condition matches; property condition prevents the default configuration |
| Jackson is present at runtime and no app-supplied bean exists | Auto-configuration can create the bean if all other conditions match |
| Jackson is present at runtime and the app already provides `MessageEncoder` | `@ConditionalOnMissingBean` causes the default bean to back off |
| JAR sits somewhere on disk, not on the loader's classpath | Cannot conclude the class is present to Spring Boot |
| A class has the right name, yet an incompatible API version | Initial class condition may match, then linkage/instantiation/usage fails |

## 5. How does Spring Boot check class presence?

Spring Boot uses conditions while processing auto-configurations. Relevant annotations:

```java
@ConditionalOnClass(name = "com.vendor.OptionalClient")
@ConditionalOnMissingClass("com.vendor.LegacyClient")
```

These two lines are **syntactically standalone annotation patterns placed on a configuration class**, not a runnable `.java` file. `@ConditionalOnClass` requires the class to be present; `@ConditionalOnMissingClass` requires it to be absent. These conditions check class names in the loader, not whether a bean was created or a method succeeded.

### 5.1. `value` vs. `name`

Spring Boot 3.3 reads **annotation metadata of configuration classes using ASM**. Consequently, for `@ConditionalOnClass` placed **directly on a configuration class**, using a class literal can be safe even when the type is absent at runtime:

```java
@ConditionalOnClass(com.vendor.OptionalClient.class)
```

When a type is genuinely optional, use the string name to make the boundary explicit and avoid a compile-time reference on the outer class:

```java
@ConditionalOnClass(name = "com.vendor.OptionalClient")
```

**Important exception:** If you write a **custom meta-annotation** containing `@ConditionalOnClass` or `@ConditionalOnMissingClass`, use the `name` attribute instead of relying on `value`; metadata handling differs from an annotation placed directly on a configuration class.

### 5.2. Do not leave all the risk on the `@Bean` method

Pattern likely to fail when `OptionalClient` is absent at runtime:

```java
// WRONG ILLUSTRATION: for analysis only, not a standalone compilable file.
@Bean
@ConditionalOnClass(name = "com.vendor.OptionalClient")
com.vendor.OptionalClient optionalClient() {
    return new com.vendor.OptionalClient();
}
```

Even though `@ConditionalOnClass` is on the method, Spring/the JVM may need to inspect the configuration class structure and the `@Bean` method's **return type** before the method-level condition is applied. When the type is absent, `NoClassDefFoundError` or a metadata parsing failure can occur before the configuration is excluded.

**Correct design:** isolate beans that depend on optional libraries inside **a separate `@Configuration` class or static nested configuration**, and place the class condition on that guard class itself. The outer auto-configuration class must not force the JVM to load optional types the moment it is discovered.

### 5.3. When do you need class, property, and bean conditions together?

- `@ConditionalOnClass`: the API is available so the integration **can** work.
- `@ConditionalOnProperty`: the application **allows** the integration to run per configuration choice.
- `@ConditionalOnMissingBean`: the application **has not supplied** its own bean, so the library provides the default.
- Other conditions such as `@ConditionalOnWebApplication`, `@ConditionalOnResource`: add only when genuinely required by the feature.

Do not use class conditions as a substitute for checking API version compatibility or service reachability. A class can exist with changed constructor/method signatures; a bean can instantiate while an external endpoint refuses connections.

## 6. Complete demo: Jackson present or absent on the runtime classpath

We will build a small application with `MessageEncoder` as the **core contract independent of Jackson**. When Jackson is present, auto-configuration creates a default encoder; when Jackson is absent or disabled, the application still starts and reports that the feature is unavailable. The app can also supply its own encoder without relying on the library default.

### 6.1. Source layout

```text
optional-classpath-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   └── optional/
    │   │       ├── MessageEncoder.java
    │   │       └── autoconfigure/OptionalJacksonAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/java/com/example/optional/autoconfigure/
        └── OptionalJacksonAutoConfigurationTest.java
```

In the demo, a single Maven project keeps execution quick. When publishing a real library, split API/core, autoconfigure, and starter into appropriate artifacts. The application package `com.example.app` **does not cover** `com.example.optional.autoconfigure`, letting us cleanly observe Spring Boot discovering configuration via the imports file.

### 6.2. Build file with optional Jackson dependency

Create `pom.xml`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
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
    <artifactId>optional-classpath-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>
        <dependency>
            <groupId>com.fasterxml.jackson.core</groupId>
            <artifactId>jackson-databind</artifactId>
            <optional>true</optional>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
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

The Spring Boot parent manages the Jackson version compatible with the Boot 3.3 line. `optional=true` only prevents Jackson from propagating transitively to **other applications**; it is still on the runtime classpath of **this demo project**. To test "Jackson absent", we use `FilteredClassLoader` instead of pretending that marking a dependency optional makes Jackson vanish from the current project.

### 6.3. Core API without mentioning Jackson

Create `src/main/java/com/example/optional/MessageEncoder.java`:

```java
package com.example.optional;

@FunctionalInterface
public interface MessageEncoder {
    String encode(String message);
}
```

This interface depends only on the JDK. Consumers can use the API without being forced to have `ObjectMapper`; that boundary is vital if Jackson integration is genuinely optional.

### 6.4. Auto-configuration isolating the Jackson portion

Create `src/main/java/com/example/optional/autoconfigure/OptionalJacksonAutoConfiguration.java`:

```java
package com.example.optional.autoconfigure;

import com.example.optional.MessageEncoder;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Map;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class OptionalJacksonAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
    @ConditionalOnProperty(
            prefix = "demo.json",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean(MessageEncoder.class)
        MessageEncoder messageEncoder() {
            ObjectMapper mapper = new ObjectMapper();

            return message -> {
                try {
                    return mapper.writeValueAsString(Map.of("message", message));
                } catch (JsonProcessingException ex) {
                    throw new IllegalStateException("Cannot encode message", ex);
                }
            };
        }
    }
}
```

Detailed breakdown:

- The outer `OptionalJacksonAutoConfiguration` class does not use Jackson in its constructor, superclass, interfaces, or `@Bean` methods. Spring Boot can discover this class even when Jackson is absent.
- The nested `JacksonConfiguration` class is where Jackson imports and calls live; it is **guarded at the configuration-class level** with `@ConditionalOnClass(name=...)`.
- `@ConditionalOnProperty` lets users disable the integration via `demo.json.enabled=false`. When the key is omitted, it is enabled by default **if** Jackson is present.
- `@ConditionalOnMissingBean(MessageEncoder.class)` ensures the library does not register the default encoder if the application provides its own encoder.
- JSON is produced using `ObjectMapper` over a single-entry `Map`. The checked `JsonProcessingException` is converted into a runtime exception to satisfy the interface, which declares no checked exceptions.
- Because the demo instantiates `ObjectMapper` with `new`, this is only a minimal encoder to illustrate class conditions. In a production library, consider reusing an application-configured `ObjectMapper` if that is the desired contract, while carefully evaluating bean conditions and general configuration policy.

**Important note:** This is an example of using Jackson when *the library is present*, not a mechanism guaranteeing every Jackson version is compatible. If code compiles against a newer version yet a consumer runs an older version missing a method, the class condition can still match and a linkage error will occur at runtime.

### 6.5. Publishing the auto-configuration per Spring Boot 3.x standards

Create the file with the exact name:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

```text
com.example.optional.autoconfigure.OptionalJacksonAutoConfiguration
```

Spring Boot reads this metadata to locate candidate auto-configurations. `@AutoConfiguration` alone is not sufficient to ensure the auto-configuration is discovered in another application without an imports file. In a multi-JAR library, this file must be packaged inside the JAR containing the auto-configuration. Avoid `@ComponentScan` over the library's entire package, as that can bypass condition boundaries or pick up unwanted beans.

### 6.6. Consuming application handling when the feature is absent

Create `src/main/java/com/example/app/DemoApplication.java`:

```java
package com.example.app;

import com.example.optional.MessageEncoder;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.boot.ApplicationRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @Bean
    ApplicationRunner printMessage(ObjectProvider<MessageEncoder> providers) {
        return args -> {
            MessageEncoder encoder = providers.getIfAvailable();
            System.out.println(encoder == null
                    ? "JSON integration disabled"
                    : encoder.encode("Hello"));
        };
    }
}
```

`ObjectProvider<MessageEncoder>` allows the application **not to require** an encoder bean immediately when constructing `ApplicationRunner`. That lets the demo demonstrate both Jackson-present and Jackson-absent cases. If you replaced `ObjectProvider` with a mandatory `MessageEncoder` parameter, when the condition did not match and no custom bean existed, the application would fail injection: that is a contract mismatch between consumer and optional feature, not a bug in `@ConditionalOnClass`.

Run from the directory containing `pom.xml` with Maven and JDK 17+:

```bash
mvn test
mvn spring-boot:run
```

Because Jackson exists on the **demo project's** runtime classpath and `demo.json.enabled` is not disabled by default, `ApplicationRunner` prints **one line**:

```text
{"message":"Hello"}
```

This is the line printed by the program; startup logs and Maven logs may appear additionally. To test the property condition, create `src/main/resources/application.properties` with:

```properties
demo.json.enabled=false
```

Then run `mvn spring-boot:run` again. The line from `ApplicationRunner` changes to:

```text
JSON integration disabled
```

To let the application provide its own encoder, remove `demo.json.enabled=false`, and then **add the following method inside `DemoApplication`**:

```java
@Bean
MessageEncoder applicationEncoder() {
    return value -> "App: " + value;
}
```

This is an **addition snippet**, not a standalone Java file. The single-line output from the runner becomes:

```text
App: Hello
```

Thanks to `@ConditionalOnMissingBean`, the auto-configuration's default bean backs off. Even with Jackson on the classpath, the application can supply its own encoder.

## 7. Testing both classpath states accurately with FilteredClassLoader

The demo application only has one real set of dependencies at a time. To test both "Jackson present" and "Jackson absent" behavior without constantly editing the POM, Spring Boot provides `FilteredClassLoader`. The test loader intentionally hides a class or package; conditions observe the resulting environment.

Create `src/test/java/com/example/optional/autoconfigure/OptionalJacksonAutoConfigurationTest.java`:

```java
package com.example.optional.autoconfigure;

import com.example.optional.MessageEncoder;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class OptionalJacksonAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            OptionalJacksonAutoConfiguration.class));

    @Test
    void createsEncoderWhenJacksonPresent() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(MessageEncoder.class);
            assertThat(context.getBean(MessageEncoder.class)
                    .encode("Lan")).isEqualTo("{\"message\":\"Lan\"}");
        });
    }

    @Test
    void skipsEncoderWhenJacksonAbsent() {
        runner.withClassLoader(new FilteredClassLoader(ObjectMapper.class))
                .run(context -> assertThat(context)
                        .doesNotHaveBean(MessageEncoder.class));
    }

    @Test
    void skipsEncoderWhenDisabledByProperty() {
        runner.withPropertyValues("demo.json.enabled=false")
                .run(context -> assertThat(context)
                        .doesNotHaveBean(MessageEncoder.class));
    }

    @Test
    void applicationBeanOverridesLibraryDefault() {
        runner.withUserConfiguration(UserEncoderConfiguration.class)
                .run(context -> {
                    assertThat(context).hasSingleBean(MessageEncoder.class);
                    assertThat(context.getBean(MessageEncoder.class)
                            .encode("Lan")).isEqualTo("App: Lan");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserEncoderConfiguration {

        @Bean
        MessageEncoder appEncoder() {
            return message -> "App: " + message;
        }
    }
}
```

Run:

```bash
mvn test
```

The four tests correspond to four contracts:

| Test | Simulation / setup | What must hold |
| --- | --- | --- |
| `createsEncoderWhenJacksonPresent` | Jackson loaded in test runtime | Exactly one default encoder exists |
| `skipsEncoderWhenJacksonAbsent` | `FilteredClassLoader` hides `ObjectMapper` | Context still runs; no default encoder |
| `skipsEncoderWhenDisabledByProperty` | Property disables integration | No default encoder |
| `applicationBeanOverridesLibraryDefault` | App defines its own encoder | Only the application's encoder exists |

`ApplicationContextRunner` is great for testing individual condition combinations, yet **does not run in native-image test mode**. Furthermore, `withConfiguration(AutoConfigurations.of(...))` names the class directly; these tests **do not verify** `AutoConfiguration.imports` discovery when packaged as a JAR. To test external publication, add an integration test in a consuming project or inspect the resource inside the built JAR.

### 7.1. Checking the classpath at both build time and runtime

In Maven:

```bash
mvn dependency:tree -Dincludes=com.fasterxml.jackson.core:jackson-databind
mvn dependency:build-classpath
```

In Gradle with the Java plugin:

```bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
```

The Gradle commands assume a project with the wrapper; on Windows use `gradlew.bat`. Inspect the test classpath separately when tests see Jackson yet the production application does not.

These commands report how dependencies **are resolved by the build tool**. With executable JARs, containers, custom classloaders, or varying runtimes, you must still inspect the actual packaged artifact and loading mechanism. `mvn dependency:tree` does not completely replace evidence that the JVM's loader actually found the class.

## 8. Why do ClassNotFoundException or NoClassDefFoundError still happen?

These two errors typically appear at different stages:

- **`ClassNotFoundException`:** commonly occurs when code actively looks up a class by name, such as `Class.forName("com.vendor.Client")`, and the loader cannot find the class definition. It is a checked exception.
- **`NoClassDefFoundError`:** a runtime linkage error (a subclass of `LinkageError`), typically occurring when the JVM tries to use a class whose required definition is unavailable; it can also happen after a class's static initialization previously failed. It is **not simply another name for `ClassNotFoundException`**.
- **`NoSuchMethodError` / `NoSuchFieldError`:** the class exists, yet the runtime API lacks a method/field expected by compiled bytecode; usually due to version incompatibility.
- **`ClassCastException`:** incompatible types; in plugin systems, one cause can be the same class name defined by two different ClassLoaders.

Concrete flow:

```text
autoconfigure.jar
    |
    +-- OptionalJacksonAutoConfiguration
    |       |
    |       +-- @ConditionalOnClass("ObjectMapper")
    |               |
    |               +-- Jackson absent -> skip JacksonConfiguration
    |               |
    |               +-- Jackson present -> continue checking property/bean
    |
    +-- MessageEncoder API (no Jackson dependency)
```

If Jackson is missing yet startup still fails with `NoClassDefFoundError: com/fasterxml/jackson/databind/ObjectMapper`, investigate **which reference is being loaded too early**—especially `@Bean` return types, superclasses/interfaces, static initializers, and un-isolated configuration classes—rather than mechanically adding conditions onto methods.

If the class is present yet `NoSuchMethodError` occurs, inspect the resolved version, dependency conflicts, and actual method signatures. `@ConditionalOnClass` only verifies class presence, not API compatibility with the compile-time version.

## 9. Investigation workflow when auto-configuration does not work

Read evidence in a logical order instead of guessing from a starter's name alone:

1. **Verify the exact artifact:** which build version is the app running, and was the latest image/JAR deployed? Is the optional dependency included at runtime?
2. **Inspect the dependency path:** `mvn dependency:tree` or Gradle `runtimeClasspath`; check for exclusions, `provided`, `compileOnly`, `runtimeOnly`, version conflicts, and `test` scope.
3. **Inspect the imports file:** the library JAR must contain `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` with the exact auto-configuration class name.
4. **Inspect the actual loader:** what is loading the app—are there custom loaders, containers, plugin layers, or TCCL differences? Is the JAR path visible to that loader?
5. **Read the condition report:** start Spring Boot with `--debug` and inspect positive/negative matches. Or use `ConditionEvaluationReport` in tests. Keep class, property, and bean conditions distinct.
6. **Check application-defined beans:** `@ConditionalOnMissingBean` may have backed off. That is expected behavior, not necessarily a bug.
7. **If startup fails:** read the root *cause* in the stack trace. `ClassNotFoundException`, `NoClassDefFoundError`, and `NoSuchMethodError` point to different fixes.
8. **Test both classpaths:** write a `FilteredClassLoader` test for the missing dependency and a normal test for when it is present; add tests for application overrides and property disabling.
9. **Check package/module boundaries:** auto-configurations should not be accidentally picked up by component scanning; avoid leaking optional library types into non-optional core/API layers.

Spring Boot supports the condition report via `--debug` or appropriate logging settings. You can also use the Actuator `/actuator/conditions` endpoint if Actuator is present and the endpoint is configured for access; avoid exposing diagnostic details broadly in production.

### 9.1. How to read a negative match result

Suppose the report shows:

```text
OptionalJacksonAutoConfiguration.JacksonConfiguration did not match:
    - @ConditionalOnClass did not find required class
      'com.fasterxml.jackson.databind.ObjectMapper'
```

This is a **meaning-level illustration**, not a promise of exact character-for-character log formatting across every patch version. Appropriate conclusion: for the current loader/context, the Jackson class condition failed. There is not yet sufficient basis to conclude the POM lacks the dependency, because the wrong artifact might be deployed, the classpath may be isolated, or a test might be using `FilteredClassLoader`.

Conversely, if the class condition matches while the property condition does not, adding Jackson will not help. If the bean condition does not match because the app already defines an encoder, do not delete the app's bean just to force the library to create its default.

## 10. Common design pitfalls

### 10.1. Putting optional types into required APIs

Example public API:

```java
// ILLUSTRATION OF HARD-TO-REUSE DESIGN:
public interface MessageEncoder {
    com.fasterxml.jackson.databind.ObjectMapper mapper();
}
```

Consumers using `MessageEncoder` now also need Jackson's types when compiling the related code. If Jackson is optional, design a neutral core interface and keep Jackson types in a separate adapter. This is a design choice; in a Jackson-specific API, a direct dependency can be reasonable, in which case **do not describe Jackson as optional for the entire API**.

### 10.2. Placing class conditions too deep

If an optional class appears directly as the return type of an `@Bean` method inside an always-processed configuration, a condition on the method itself may arrive too late. Using a guarded nested configuration class is the safe approach in Spring Boot.

### 10.3. Confusing "optional dependency" with "feature flag"

`optional=true` controls transitive dependency propagation for Maven consumers; `demo.json.enabled=false` controls a runtime property condition; `@ConditionalOnClass` controls type presence. The three solve three different problems and often work together.

### 10.4. Checking class presence by instantiating it

`new OptionalClient()` is not a "safe if JAR missing" check; it forces the runtime to load the type and execute its constructor. In Spring Boot, use `@ConditionalOnClass` at the proper level and test with `FilteredClassLoader`. If you must check manually, avoid early initialization and handle resolution errors explicitly.

### 10.5. Thinking passing tests mean production has all JARs

Tests often have their own dependencies and sometimes different versions from production runtime. Always distinguish the test classpath, the packaged artifact's classpath, the container's classpath, and the classloading environment of the running application.

### 10.6. Thinking "having the class" means it works

Even if the condition matches, the bean can still fail due to API mismatches, missing configuration, network issues, credentials, or external resources. A class condition only verifies the *necessary condition of type presence*, not that executing the task will succeed.

## 11. Self-check understanding

**Question 1.** A Maven library declares Jackson `optional=true`, and the library's unit tests pass. A consumer declares only the library, without Jackson. Is the consumer guaranteed to have `ObjectMapper`?

**Answer:** No. Optional prevents Jackson from propagating transitively along that dependency edge; Jackson might still come from another dependency. Inspect the actual runtime classpath.

**Question 2.** Why is `@ConditionalOnClass` on a guard configuration class safer than `@ConditionalOnClass` on an `@Bean` method returning an optional type?

**Answer:** When Spring/the JVM inspects the method signature, the optional type can be loaded before the method-level condition is evaluated. Separating the configuration class allows excluding the entire section containing the method before references to the optional type are processed.

**Question 3.** `@ConditionalOnClass(ObjectMapper.class)` matches, yet there is no `MessageEncoder`. Is this definitely a Spring bug?

**Answer:** No. A property might disable it, another class condition might fail, a bean condition might back off, imports might not be published properly, or bean initialization might fail. Check the condition report and stack trace.

**Question 4.** Is a class with the same name defined by two independent custom ClassLoaders the same JVM type?

**Answer:** Not necessarily. Type identity includes both the binary name and the defining classloader; `ClassCastException` can occur.

**Question 5.** You want Jackson integration without breaking consumers that only use the core module. What boundaries are needed?

**Answer:** Core/API must not force consumers to depend on Jackson; adapters must be guarded by class-level conditions; artifacts/metadata must be published accurately; consumers decide whether to include the dependency; test missing/present classes, property toggles, and bean overrides.

## 12. Takeaways and references

An optional dependency is only truly "optional" for applications when **the dependency graph, API boundaries, class loading, and bean registration mechanism** are all designed to allow its absence.

- **Classpath** answers: in which context can the library/class potentially be found?
- **ClassLoader** answers: which classes does a specific loader see and load?
- **`@ConditionalOnClass`** answers: is the required class present to attempt enabling the auto-configuration?
- **`@ConditionalOnProperty` and `@ConditionalOnMissingBean`** answer: does the application want this feature and has it already supplied its own bean?
- **Actual testing** answers: when the JAR is missing, the feature is disabled, or a custom bean exists, does the application behave according to contract?

Further reading from official documentation:
- Spring Boot 3.3 — Creating Your Own Auto-configuration (Class Conditions, Testing): https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — Using Auto-configuration: https://docs.spring.io/spring-boot/3.3/reference/using/auto-configuration.html
- Maven — Dependency Mechanism (`optional` and dependency scopes): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle — Dependency Configurations: https://docs.gradle.org/current/userguide/dependency_configurations.html
- Java 17 — `Class.forName` and `ClassLoader`: https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/Class.html and https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/ClassLoader.html
