# Isolating Optional Integrations and Testing Missing Dependencies with `FilteredClassLoader`

**Topic:** Spring Boot Auto Configuration  
**Knowledge Group:** Integrated Practice  
**Goal:** Design an optional integration activated only when an external library is on the runtime classpath; isolate references to optional APIs so the application still starts when the dependency is absent; and test both states using `FilteredClassLoader` with `ApplicationContextRunner`.

## 1. Problem: A Library with an Optional Integration Feature

Suppose a library provides an abstraction to convert objects to JSON:

```java
public interface JsonCodec {
    String encode(Object value);
}
```

The library can use Jackson for an implementation:

```java
ObjectMapper objectMapper;
```

However, not every application needs Jackson. An application might use a different JSON codec, or might not need the library's JSON functionality at all. If auto-configuration always references `ObjectMapper`, an application without Jackson can encounter class-loading errors when Spring processes the configuration.

Design goals:

- Application has Jackson and enables the feature: register the default `JsonCodec`.
- Application lacks Jackson: skip only the Jackson integration and still start normally.
- Application disables the feature: do not register integration beans.
- Application supplies its own `JsonCodec`: auto-configuration backs off.
- Application has its own `ObjectMapper`: the default mapper bean is not created.

This is a classic optional integration case: the library can compile against a dependency, yet must not force every consumer to carry that dependency at runtime.

## 2. Distinguishing Compile Classpath and Runtime Classpath

A dependency may be needed to compile the auto-configuration module without necessarily being passed transitively to consuming applications.

| Phase | Question to answer |
| --- | --- |
| Module compile | Does the library source need the `ObjectMapper` API to compile? |
| Module test | Do tests need Jackson to test the branch where the integration is present? |
| Consumer runtime | Does the end application actually install Jackson? |
| Auto-configuration | When Jackson is absent, does Spring safely skip the branch referencing Jackson? |

With Maven, a dependency marked `<optional>true</optional>` is still used to compile and test the current module. Being optional means that dependency is not automatically propagated transitively to consumers.

For example:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
    <optional>true</optional>
</dependency>
```

Applications using the library may obtain Jackson from another starter, declare Jackson directly, or not have Jackson at all. Auto-configuration must handle both cases.

With Gradle, a dependency needed only to compile the library's source can be declared with `compileOnly`; tests add that dependency to `testImplementation`:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-autoconfigure")
    compileOnly("com.fasterxml.jackson.core:jackson-databind")

    testImplementation("com.fasterxml.jackson.core:jackson-databind")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}
```

If the library's public API exposes Jackson types in public methods, constructors, or generic signatures, carefully review the publication contract. `compileOnly` does not provide the dependency to the consumer's compile classpath. Best practice is keeping optional APIs inside adapters and publishing only independent abstractions like `JsonCodec`.

## 3. Why a Missing Dependency Can Fail Before Conditions Are Applied

Suppose the main configuration class contains a method:

```java
@Bean
JsonCodec jsonCodec(ObjectMapper objectMapper) {
    return new JacksonJsonCodec(objectMapper);
}
```

If Jackson is not on the runtime classpath, the `ObjectMapper` type in the method signature can force the JVM or Spring to resolve a non-existent class while introspecting the configuration. An error can then occur before the condition guarding the bean method is even evaluated.

Common errors:

```text
java.lang.NoClassDefFoundError:
com/fasterxml/jackson/databind/ObjectMapper
```

or:

```text
java.lang.ClassNotFoundException:
com.fasterxml.jackson.databind.ObjectMapper
```

The two errors are not identical:

- `ClassNotFoundException` typically occurs when code explicitly asks a classloader to find a class and cannot locate it.
- `NoClassDefFoundError` is a linkage error when the JVM requires a class that loading/linking cannot supply.

Another error such as `NoSuchMethodError` usually indicates the class was loaded, yet the runtime version lacks a method called by bytecode; this is a binary compatibility/version mismatch issue.

**Key point:** the condition must guard the entire configuration branch containing references to optional types. Placing `@ConditionalOnMissingBean` or `@ConditionalOnProperty` only on the method is insufficient if Spring must read the method signature before knowing whether the dependency is present.

## 4. Placing `@ConditionalOnClass` on a Separate Configuration

Spring Boot provides `@ConditionalOnClass` to check whether a class exists on the classpath.

For optional integrations, isolate references to the optional library inside a nested static configuration:

```java
@AutoConfiguration
public class JsonCodecAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "com.fasterxml.jackson.databind.ObjectMapper"
    )
    static class JacksonConfiguration {

        // @Bean methods referencing ObjectMapper go here.
    }
}
```

Two important details:

1. `JacksonConfiguration` is a separate class guarded by a class-level condition.
2. The `name` attribute uses the fully qualified String name, avoiding forcing the classloader to resolve `ObjectMapper.class` just to read the annotation.

Spring Boot reads class condition metadata while analyzing configurations. When the class is absent, the nested configuration is skipped before its inner bean methods need to be processed.

`@ConditionalOnClass(SomeOptionalType.class)` can be used where appropriate when the type is guaranteed to be resolvable. For optional types and classes spanning varying runtimes, `name = "..."` avoids referencing the class literal directly in the annotation.

### 4.1. Do not leak optional types into the outer configuration class

The outer class should avoid:

- Fields of type `ObjectMapper`.
- Constructors taking `ObjectMapper`.
- Superclasses or interfaces depending on Jackson.
- `@Bean` methods returning or accepting `ObjectMapper`.
- Static initializers calling Jackson.
- Annotations on the outer class containing class literals of optional APIs.

Example of what not to write:

```java
@AutoConfiguration
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
public class JsonCodecAutoConfiguration {

    private ObjectMapper mapper;

    @Bean
    JsonCodec jsonCodec() {
        return new JacksonJsonCodec(this.mapper);
    }
}
```

Even with a condition on the class, the field signature still makes the outer class depend on the optional API. Move fields, methods, and all Jackson references into a guarded nested configuration.

### 4.2. Nested configurations must be `static`

Use a `static` nested class:

```java
@Configuration(proxyBeanMethods = false)
static class JacksonConfiguration {
}
```

A static nested configuration does not require an instance of the outer class. This lets Spring register the configuration independently and avoids coupling to an outer auto-configuration object instance.

## 5. Organizing the Module and Jackson-Independent API

The example uses three parts:

```text
json-codec-autoconfigure/
├── src/main/java/demo/json/
│   ├── JsonCodec.java
│   ├── autoconfigure/
│   │   ├── JsonCodecAutoConfiguration.java
│   │   └── JacksonJsonCodec.java
│   └── config/
│       └── JsonCodecProperties.java
├── src/main/resources/META-INF/spring/
│   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── src/test/java/demo/json/
    └── JsonCodecAutoConfigurationTests.java
```

Responsibilities:

| Component | Depends on Jackson? | Role |
| --- | --- | --- |
| `JsonCodec` | No | Contract used by consumers |
| `JacksonJsonCodec` | Yes | Adapter implementing the contract with Jackson |
| `JsonCodecAutoConfiguration` | Should not | Feature condition and imports integration branch |
| `JacksonConfiguration` | Yes, but guarded | Registers mapper and codec when Jackson is present |
| Test | Yes in test runtime | Tests branch with dependency and filtered branch |

If there are several major optional integrations—such as Jackson, Gson, protobuf, and a vendor SDK—each adapter can be split into its own module. The core module publishes only interfaces; adapter modules depend on their respective libraries and register their own auto-configurations.

Splitting modules keeps the consumer's dependency graph clean: only add the adapter the application truly needs.

## 6. Creating the `JsonCodec` Abstraction

File `JsonCodec.java`:

```java
package demo.json;

public interface JsonCodec {

    String encode(Object value);
}
```

The interface makes no mention of Jackson. Controllers, services, or other modules depend solely on this contract.

Consumer example:

```java
package demo.app;

import demo.json.JsonCodec;

public class AuditService {

    private final JsonCodec jsonCodec;

    public AuditService(JsonCodec jsonCodec) {
        this.jsonCodec = jsonCodec;
    }

    public String createAuditPayload(Object event) {
        return this.jsonCodec.encode(event);
    }
}
```

`AuditService` does not need to know whether the implementation uses Jackson, Gson, or an internal serializer. This allows the application to swap implementations without modifying business services.

## 7. Writing the Adapter Dedicated to the Jackson Branch

File `JacksonJsonCodec.java`:

```java
package demo.json.autoconfigure;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;

import demo.json.JsonCodec;

final class JacksonJsonCodec implements JsonCodec {

    private final ObjectMapper objectMapper;

    JacksonJsonCodec(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    @Override
    public String encode(Object value) {
        try {
            return this.objectMapper.writeValueAsString(value);
        }
        catch (JsonProcessingException exception) {
            throw new IllegalArgumentException(
                    "Cannot encode value as JSON",
                    exception
            );
        }
    }
}
```

The adapter class references Jackson directly. This is intentional: the class is used only when the Jackson branch is confirmed present.

The adapter has package visibility rather than public because consumers only need `JsonCodec`. This avoids making optional Jackson types part of the library's public API.

Do not place `@Component` on the adapter in this example. Auto-configuration will register it via `@Bean` when the Jackson branch matches.

## 8. Writing Auto-Configuration with an Optional Branch

File `JsonCodecAutoConfiguration.java`:

```java
package demo.json.autoconfigure;

import com.fasterxml.jackson.databind.ObjectMapper;

import demo.json.JsonCodec;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.json",
        name = "enabled",
        havingValue = "true"
)
public class JsonCodecAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(
            name = "com.fasterxml.jackson.databind.ObjectMapper"
    )
    static class JacksonConfiguration {

        @Bean
        @ConditionalOnMissingBean(ObjectMapper.class)
        ObjectMapper jsonObjectMapper() {
            return new ObjectMapper();
        }

        @Bean
        @ConditionalOnMissingBean(JsonCodec.class)
        JsonCodec jsonCodec(ObjectMapper objectMapper) {
            return new JacksonJsonCodec(objectMapper);
        }
    }
}
```

**Structural note:** in real source, the `ObjectMapper` import and methods referencing it belong to the guarded nested configuration. To maintain the strictest classloading boundary, you can move `JacksonConfiguration` into a separate top-level configuration class in the `autoconfigure` package, and have the main auto-configuration import it via `@Import` with a class-level condition. Whether nested or top-level, never place `ObjectMapper` in signatures or fields of the outer class.

If using a nested class as above, keep all required methods, imports, and Jackson-dependent adapters inside the nested branch; verify with `FilteredClassLoader` tests to catch any leaked references early.

Each condition has its own role:

- `@ConditionalOnProperty` turns the entire feature on/off based on application configuration.
- `@ConditionalOnClass` activates the Jackson branch only when `ObjectMapper` is on the classpath.
- `@ConditionalOnMissingBean(ObjectMapper.class)` allows applications to supply their own mapper.
- `@ConditionalOnMissingBean(JsonCodec.class)` allows applications to replace the entire codec.

### 8.1. When should you use a top-level optional configuration?

If you want the cleanest classloading boundary, use two classes:

```java
@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.json",
        name = "enabled",
        havingValue = "true"
)
@Import(JacksonJsonCodecConfiguration.class)
public class JsonCodecAutoConfiguration {
}
```

File `JacksonJsonCodecConfiguration.java`:

```java
package demo.json.autoconfigure;

import com.fasterxml.jackson.databind.ObjectMapper;

import demo.json.JsonCodec;

import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@ConditionalOnClass(
        name = "com.fasterxml.jackson.databind.ObjectMapper"
)
class JacksonJsonCodecConfiguration {

    @Bean
    @ConditionalOnMissingBean(ObjectMapper.class)
    ObjectMapper jsonObjectMapper() {
        return new ObjectMapper();
    }

    @Bean
    @ConditionalOnMissingBean(JsonCodec.class)
    JsonCodec jsonCodec(ObjectMapper objectMapper) {
        return new JacksonJsonCodec(objectMapper);
    }
}
```

In this example, the configuration class containing optional types has its own class-level condition. This pattern is easy to test and usually fits well when the integration branch has multiple beans or supporting classes.

When using `@Import`, the outer class only references the library's own configuration class; it does not reference `ObjectMapper`. When the class condition is no-match, the optional branch creates no beans.

## 9. Registering Auto-Configuration in the JAR

For Spring Boot 2.7 and above, create the file:

```text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Content:

```text
demo.json.autoconfigure.JsonCodecAutoConfiguration
```

Register only the primary auto-configuration. Do not list `JacksonJsonCodecConfiguration` as a standalone auto-configuration if it is already imported from the primary class.

For Boot 2.6 and older, registration uses the `EnableAutoConfiguration` key in `META-INF/spring.factories`. If a library supports multiple Boot lines, maintain compatible registration and test annotations/APIs for each baseline. The example here uses `@AutoConfiguration`, so it targets Boot 2.7+.

## 10. Declaring Optional Dependencies in Maven

Example POM using Java 17 and Spring Boot 3.3.13:

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

    <groupId>demo</groupId>
    <artifactId>json-codec-autoconfigure</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
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
</project>
```

`jackson-databind` is present on this module's compile/test classpath so the adapter source compiles. Because the dependency is marked optional, consumers do not automatically receive Jackson just by adding `json-codec-autoconfigure`.

Applications wishing to use the Jackson integration can declare:

```xml
<dependency>
    <groupId>com.fasterxml.jackson.core</groupId>
    <artifactId>jackson-databind</artifactId>
</dependency>
```

Or Jackson can come from another starter. Applications without Jackson can still use the parts independent of the adapter.

Do not place Jackson in `test` scope only if the adapter's production source needs to import `ObjectMapper`: main source must compile against that API. Also do not make optional dependencies required at runtime for every consumer if the goal is allowing applications to omit the integration.

## 11. Gradle Equivalent

When using the Gradle Java plugin and Spring dependency management, you can declare:

```groovy
plugins {
    id 'java'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencyManagement {
    imports {
        mavenBom 'org.springframework.boot:spring-boot-dependencies:3.3.13'
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    compileOnly 'com.fasterxml.jackson.core:jackson-databind'
    testImplementation 'com.fasterxml.jackson.core:jackson-databind'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

`compileOnly` lets the module compile the adapter without publishing that dependency as a regular runtime dependency to consumers. `testImplementation` brings Jackson back onto the test runtime to test the branch when present.

Inspect the dependency graph:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

Expected result:

- Jackson appears on the module's compile classpath.
- Jackson is present in test runtime to test the integration branch.
- Consumers do not automatically receive Jackson via the library's runtime dependencies unless another source provides it.

If the library must expose Jackson types in its public API, `compileOnly` may not suffice for consumer compilation. Keep optional types inside the adapter implementation or choose a configuration publication matching the actual contract.

## 12. What Is `FilteredClassLoader`?

`FilteredClassLoader` is a Spring Boot test utility in the package:

```java
org.springframework.boot.test.context.FilteredClassLoader
```

It creates a classloader that intentionally hides a class or package from the context under test. This allows tests to simulate a consuming application that has not installed an optional dependency, even though that dependency remains on the test runtime classpath to compile and run other tests.

Example hiding the entire Jackson Databind package:

```java
new FilteredClassLoader("com.fasterxml.jackson.databind")
```

Or hiding a specific class:

```java
new FilteredClassLoader(SomeOptionalClient.class)
```

`FilteredClassLoader` is strictly a testing tool. It does not replace declaring dependencies with proper scopes and does not remove dependencies from the Maven/Gradle graph. In production, the optional dependency must genuinely be absent from the runtime classpath to confirm consumers do not need to install it.

## 13. Testing with `ApplicationContextRunner`

`ApplicationContextRunner` creates a small ApplicationContext per test and lets you vary:

- Property values.
- User configuration.
- Context classloader.
- Applied auto-configurations.

This is the right way to verify conditions and bean registration without starting a full web server or production application.

### 13.1. Test structure

```text
src/test/java/demo/json/
└── JsonCodecAutoConfigurationTests.java
```

### 13.2. Four-scenario test suite

```java
package demo.json;

import java.util.Map;

import org.junit.jupiter.api.Test;

import demo.json.autoconfigure.JsonCodecAutoConfiguration;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class JsonCodecAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    JsonCodecAutoConfiguration.class
                            )
                    );

    @Test
    void createsJsonCodecWhenJacksonIsPresentAndFeatureIsEnabled() {
        this.runner
                .withPropertyValues("acme.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(JsonCodec.class);

                    String json = context.getBean(JsonCodec.class)
                            .encode(Map.of("name", "Ada"));

                    assertThat(json).isEqualTo("{\"name\":\"Ada\"}");
                });
    }

    @Test
    void skipsOptionalIntegrationWhenJacksonIsAbsent() {
        this.runner
                .withClassLoader(
                        new FilteredClassLoader(
                                "com.fasterxml.jackson.databind"
                        )
                )
                .withPropertyValues("acme.json.enabled=true")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(JsonCodec.class);
                });
    }

    @Test
    void skipsIntegrationWhenFeatureIsDisabled() {
        this.runner
                .withPropertyValues("acme.json.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).doesNotHaveBean(JsonCodec.class);
                });
    }

    @Test
    void applicationProvidedCodecReplacesDefaultCodec() {
        this.runner
                .withPropertyValues("acme.json.enabled=true")
                .withUserConfiguration(UserJsonCodecConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(JsonCodec.class);

                    String json = context.getBean(JsonCodec.class)
                            .encode(Map.of("name", "Ada"));

                    assertThat(json).isEqualTo("custom-json");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserJsonCodecConfiguration {

        @Bean
        JsonCodec customJsonCodec() {
            return value -> "custom-json";
        }
    }
}
```

The second test is the heart of this guide. Jackson is still in the test dependency graph, yet `FilteredClassLoader` hides the package from the ApplicationContext. If an optional class were referenced from the outer class or an unguarded method, the test could fail with a class-loading error. The expected result is that the context still starts and the default `JsonCodec` is not registered.

The fourth test verifies back-off: the application provides its own `JsonCodec`, so the auto-configuration does not create an extra default implementation.

### 13.3. Running the tests

```bash
mvn test
```

Expected output from Maven Surefire:

```text
Tests run: 4, Failures: 0, Errors: 0, Skipped: 0
```

This is the expected test count for the test class above. Execution time and other build lines depend on the Maven/Surefire version.

## 14. Result Matrix

| Scenario | Jackson visible? | `acme.json.enabled` | User `JsonCodec` | Result |
| --- | --- | --- | --- | --- |
| Default integration | Yes | `true` | No | One Jackson-backed codec present |
| Missing dependency | No | `true` | No | Context runs, no default codec |
| Feature disabled | Yes | `false` | No | No default codec |
| User override | Yes | `true` | Yes | Only the application's codec is used |

This matrix separates three decisions:

1. Is the dependency on the runtime classpath?
2. Did the user enable the feature?
3. Did the application provide a replacement implementation?

A test checking only "bean exists" is not enough. Assert the actual implementation used or its output to confirm correct wiring.

## 15. Testing a Consumer When the Dependency Is Truly Absent

`FilteredClassLoader` tests Spring's behavior when a class cannot be seen. In addition, there should be a consumer smoke test whose runtime dependency graph does not contain Jackson.

Maven consumers can check:

```bash
mvn dependency:tree -Dscope=runtime
```

Verify that `jackson-databind` is not pulled in through the auto-configuration module. Then run a consuming application that depends on the library without declaring Jackson.

With Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

If Jackson still appears, trace which dependency pulled it in. Another starter in the application might have supplied Jackson; that does not mean the auto-configuration module requires the dependency.

A consumer integration test can launch with `@SpringBootApplication`/`@EnableAutoConfiguration`, adding only the library artifact without adding Jackson. This test verifies both dependency publication and the registration resource. The `ApplicationContextRunner` above passes the auto-configuration class directly, so it tests conditions/wiring rather than proving the `AutoConfiguration.imports` file was packaged properly.

## 16. When Should You Split Into Separate Integration Modules?

If an optional integration has many classes or heavy dependencies, split the modules:

```text
acme/
├── acme-core/
│   └── JsonCodec API and business contracts
├── acme-jackson-autoconfigure/
│   ├── JacksonJsonCodec
│   ├── JacksonJsonCodecConfiguration
│   └── AutoConfiguration.imports
├── acme-gson-autoconfigure/
│   └── Gson adapter and registration
└── acme-starter/
    └── Dependencies that applications choose to use
```

Benefits:

- Core does not need to know about Jackson or Gson.
- Consumers add only the matching adapter.
- Optional dependencies do not leak into core's public API.
- Each adapter can have its own conditions, properties, and tests.
- Upgrading one integration library has minimal impact on other modules.

If there is only one small adapter, a single auto-configuration module with an optional dependency and a guarded nested configuration can suffice. Choose module boundaries based on the dependency graph and reasons for change, rather than splitting a module for a single class.

## 17. Diagnosing When the Missing-Dependency Test Still Fails

If the `FilteredClassLoader` test still throws `NoClassDefFoundError`, check in order:

1. Does the optional type appear in the superclass, interfaces, fields, or constructors of the outer auto-configuration?
2. Does any method on the outer class return or accept the optional type?
3. Is `@ConditionalOnClass` placed on an isolated configuration class?
4. Does the annotation use `name` instead of a class literal when avoiding resolving the optional type?
5. Is the optional adapter picked up by component scan or imported in an unguarded place?
6. Is there a static initializer calling the optional library?
7. Is the test actually applying `withClassLoader(new FilteredClassLoader(...))` on the runner starting the configuration?
8. Does another dependency or test setup cause the optional class to be loaded via an unexpected classloader?

If the context starts yet the bean does not appear, enable debug to read the Condition Evaluation Report:

```bash
java -jar app.jar --debug
```

Look for the `OnClassCondition` and property condition of the auto-configuration. The report shows which branches matched/did not match and typically states the missing class.

Distinguish two situations:

- A class condition no-match is the expected result when an optional dependency is absent.
- A class loading failure is a design or dependency graph bug that must be fixed.

Do not catch `Throwable` or `NoClassDefFoundError` and ignore it to let the application continue. Doing so hides linkage errors and leaves the integration in an unpredictable state.

## 18. Common Mistakes

**Mistake 1 — Placing `@ConditionalOnClass` only on a `@Bean` method with an optional return type.**  
Spring may need to resolve the method signature before the method condition is applied. Isolate the optional branch in a configuration class with a class-level condition.

**Mistake 2 — Putting optional types in fields of the outer auto-configuration.**  
The outer class still depends on the optional library when the JVM loads/introspects it. Move references into the guarded branch.

**Mistake 3 — Using a class literal in annotations on a class that must load when the class is absent.**  
`ObjectMapper.class` requires the type to be resolvable. For optional classes, use `name = "..."` on the appropriate configuration class.

**Mistake 4 — Thinking Maven `optional=true` excludes the dependency from the current module.**  
Incorrect. The current module still compiles/tests with the dependency; optional only prevents automatically propagating that dependency to consumers.

**Mistake 5 — Using `test` scope for a dependency that main source needs to compile.**  
Main source cannot import types present only on the test classpath. Use a Maven optional compile dependency or Gradle compileOnly.

**Mistake 6 — Testing only the dependency-present branch.**  
Passing tests do not prove consumers lacking the dependency can start. Add `FilteredClassLoader`.

**Mistake 7 — Using only `FilteredClassLoader` and ignoring the production dependency graph.**  
The classloader test simulates class absence; the consumer's runtime dependency tree must still be verified.

**Mistake 8 — Using `@ComponentScan` to auto-detect optional adapters.**  
Scanning can load components depending on optional types outside the guarded branch. Register adapters via conditional configuration.

**Mistake 9 — Forgetting `@ConditionalOnMissingBean`.**  
Applications cannot cleanly replace the default implementation and may run into multiple candidates of the same type.

**Mistake 10 — Unintentionally exposing optional types in the public API.**  
Consumers may need the dependency just to compile even when not using the adapter. Keep the public contract independent of optional libraries.

**Mistake 11 — Assuming `ApplicationContextRunner` tests the registration file.**  
When using `AutoConfigurations.of(...)`, tests pass the class directly. An integration test via `@EnableAutoConfiguration` is needed to verify discovery.

**Mistake 12 — Catching class-loading errors and returning `null`.**  
This masks errors and leaves beans in invalid states. Use conditions to exclude the branch before beans are created.

## 19. Review Checklist

- [ ] Identify which dependencies are truly optional for consumers.
- [ ] Use Maven `optional=true` or the appropriate Gradle configuration.
- [ ] Keep optional types out of the public API unless consumers must depend on them directly.
- [ ] Place `@ConditionalOnClass` on an isolated configuration class.
- [ ] Use String class names when guarding optional types.
- [ ] Keep optional types out of outer class fields, constructors, superclasses, or method signatures.
- [ ] Separate adapters from business contracts.
- [ ] Use `@ConditionalOnProperty` for feature switches when needed.
- [ ] Use `@ConditionalOnMissingBean` so consumers can override defaults.
- [ ] Test when the dependency is present.
- [ ] Test when the dependency is hidden via `FilteredClassLoader`.
- [ ] Test feature disabled.
- [ ] Test user-provided implementation.
- [ ] Inspect the consumer's runtime dependency graph.
- [ ] Include discovery integration tests and check the registration resource in the JAR.
- [ ] Read the Condition Evaluation Report when conditions do not match as expected.

## 20. Self-Check Questions

**Question 1.** Why does a library need optional integrations?  
**Answer:** So consumers only need to add dependencies for features they use; applications lacking optional libraries can still start and use the independent parts.

**Question 2.** What does Maven `<optional>true</optional>` mean?  
**Answer:** The dependency can still be used to compile/test the current module, yet is not automatically passed transitively to consumers.

**Question 3.** Where should `@ConditionalOnClass` be placed to guard methods referencing optional types?  
**Answer:** On a separate configuration class / static nested configuration containing those methods, so Spring skips the entire branch when the class is absent.

**Question 4.** Why use `name = "com.fasterxml.jackson.databind.ObjectMapper"`?  
**Answer:** Using a String name avoids requiring class literal resolution when the annotation is read in an environment that may lack the dependency.

**Question 5.** What does `FilteredClassLoader` do?  
**Answer:** Creates a test classloader that hides a class or package from the ApplicationContext to simulate a runtime missing the dependency.

**Question 6.** Does `FilteredClassLoader` remove a dependency from the Maven runtime graph?  
**Answer:** No. It only simulates class absence in tests; the consumer's dependency tree must be checked separately.

**Question 7.** When an optional class is absent, what is the expected outcome?  
**Answer:** The condition does not match, optional beans are not created, and the ApplicationContext still starts.

**Question 8.** Why is `@ConditionalOnMissingBean(JsonCodec.class)` necessary?  
**Answer:** It allows applications to provide their own implementation and makes the default codec back off.

**Question 9.** Does `ApplicationContextRunner` with `AutoConfigurations.of(...)` test the imports file?  
**Answer:** No. It passes the class directly to the runner; discovery must be tested via `@EnableAutoConfiguration` and JAR inspection.

**Question 10.** If a missing-dependency test throws `NoClassDefFoundError`, what should you do?  
**Answer:** Find where the optional type is referenced outside the guarded configuration class, fix the classloading boundary, and preserve the original error for diagnosis.

## 21. Principles to Remember

- Optional integrations activate only when the required dependency is on the runtime classpath.
- Separate public contracts from adapters depending on external libraries.
- Maven `optional=true` and Gradle `compileOnly` help control dependencies passed to consumers.
- Place `@ConditionalOnClass` on configuration classes isolating methods that use optional types.
- Use String `name` attributes to avoid class literals of dependencies that might be absent.
- Do not let optional types leak into the outer auto-configuration or unnecessary public APIs.
- `FilteredClassLoader` tests the missing-dependency branch inside an ApplicationContext.
- Test dependency present/absent, property disabled, and user override cases.
- Inspect the consumer dependency graph in addition to classloader tests.
- Distinguish expected condition no-matches from actual class-loading errors.

### Official References

- [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [Spring Boot 3.3 API — `@ConditionalOnClass`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
- [Spring Boot 3.3 API — `FilteredClassLoader`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html)
- [Spring Boot 3.3 API — `ApplicationContextRunner`](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html)
- [Apache Maven — Optional Dependencies and Dependency Exclusions](https://maven.apache.org/guides/introduction/introduction-to-optional-and-excludes-dependencies.html)
- [Gradle — Declaring Dependencies](https://docs.gradle.org/current/userguide/declaring_dependencies.html)
