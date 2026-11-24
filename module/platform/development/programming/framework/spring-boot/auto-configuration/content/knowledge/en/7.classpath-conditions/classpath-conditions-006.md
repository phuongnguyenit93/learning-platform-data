# Risk of Placing a Condition on an @Bean Method with a Non-Existent Return Type

> **Topic:** Spring Boot auto-configuration → Classpath conditions.  
> **Example stack:** Java 17, Spring Boot 3.3.x, Spring Framework 6.1; sample Maven project uses Spring Boot **3.3.13**.  
> **Focus:** why `@ConditionalOnClass` placed directly on an `@Bean` method whose **return type belongs to an optional dependency** is not a safe guard, and how to isolate that method inside an `@Configuration` guarded **at the class level**.

## 1. Learning Outcomes

After this lesson, you will be able to:

1. Distinguish **having a class on the compile classpath** from **having it on the runtime classpath** and **the ClassLoader being able to load that class**.
2. Explain why the JVM or Spring may need to inspect a **method signature** before a condition on an `@Bean` method is applied.
3. Recognize `NoClassDefFoundError`, `TypeNotPresentException`, `ClassNotFoundException`, and “Failed to introspect Class” errors, instead of attributing every case to `@ConditionalOnClass` not matching.
4. Write the flawed configuration to understand the risk, then fix it with a **nested static `@Configuration(proxyBeanMethods = false)` bearing `@ConditionalOnClass` at the class level**.
5. Design code so optional classes do not appear in `@Bean` signatures of configurations that are always parsed.
6. Use `ApplicationContextRunner` + `FilteredClassLoader` to test hiding a dependency from the classpath, and distinguish bean instantiation errors from class loading errors during parsing.
7. Apply this mechanism properly in starters or autoconfigure modules integrating optional SDKs.

**Foundational takeaway:** A condition placed **on a method** does not guarantee that Spring/the JVM has not yet inspected that method's return type. If the return type does not exist at runtime, configuration can fail **before** the method-level condition can protect it. Move the condition to a **separate configuration class** or static nested configuration so Spring can evaluate metadata at the class level before inspecting the `@Bean` signatures inside.

## 2. An Example That Looks Right Yet Is Dangerous

Suppose your library integrates a codec from an optional SDK:

```text
com.vendor.codec.OptionalCodec
```

When the SDK is present, you want to create the bean; when the SDK is absent, the application should simply skip the codec feature and continue starting.

A very tempting snippet to write:

```java
// ANTI-PATTERN: illustrative fragment, not a standalone Java file.
@AutoConfiguration
public class CodecAutoConfiguration {

    @Bean
    @ConditionalOnClass(name = "com.vendor.codec.OptionalCodec")
    com.vendor.codec.OptionalCodec optionalCodec() {
        return new com.vendor.codec.OptionalCodec();
    }
}
```

**The issue is not with the annotation syntax.** `@ConditionalOnClass` allows using a string class name. Yet the method's **return signature** still contains `OptionalCodec`. When Spring reads an `@Configuration` class and identifies factory methods, the framework/JVM may need to load, reflect, resolve, or predict types from the method signature. If `OptionalCodec` is absent, a code path can throw an error **before the method condition is evaluated to skip the bean**.

Not every JVM and code path immediately throws the same error. Class resolution can be partially deferred depending on context, and Spring Boot has steps that read annotations via metadata. However, **library safety must not rely on luck that a method-level condition will always be evaluated before the JVM processes the return type**.

### 2.1. Three Claims Commonly Conflated

| Statement | True or false? |
| --- | --- |
| “The codec dependency exists at compile time” | Only proves the module source **can compile** |
| “`@ConditionalOnClass` on a method will always make that class load safely when the codec is absent” | **Cannot be guaranteed** |
| “A class-level configuration can be evaluated by Spring Boot via annotation metadata before loading a class containing optional signatures” | **This is the recommended protection technique** |
| “`@ConditionalOnClass` matching means the codec bean is guaranteed to initialize” | False: bean conditions, factories, linkage, dependencies, and lifecycle still apply |
| “Hiding the return type with `Object` is a clean fix” | False: can break type metadata, dependency injection, and bean conditions |

**Note:** Passing `name = "..."` to the annotation only avoids a direct reference in the **annotation value**. It **does not remove** the `OptionalCodec` reference from the `@Bean` method's **return descriptor**.

## 3. What Happens Before a Bean Is Created?

In Spring Boot, a helpful mental model is:

```text
Classpath / JARs / ClassLoader
       |
       v
Discover auto-configuration classes via
META-INF/spring/...AutoConfiguration.imports
       |
       v
Spring reads configuration metadata and @Conditional
       |
       v
Spring identifies @Bean factory methods / return types
       |
       v
Register valid bean definitions
       |
       v
Resolve dependencies and instantiate bean instances
```

This is a **conceptual diagram**, not a promise that every execution path runs across five strictly separate stack frames. Specifically, Spring can read class metadata using ASM without loading the class yet, yet certain factory method operations, introspection, type prediction, or resolution may go through reflection/JVM loading.

### 3.1. Why Must Spring Care About an @Bean's Return Type?

A factory method's return type is essential for Spring to:
- Infer the **bean type** before an instance exists;
- Decide whether an `@Autowired` injection point has a matching candidate;
- Apply `@ConditionalOnBean` or `@ConditionalOnMissingBean` based on type;
- Process `@Primary`, qualifiers, generics, and factory-method metadata;
- Compute bean definitions, wiring, and auto-configuration policies before invoking the method.

For example:

```java
@Bean
OptionalCodec optionalCodec() {
    return new VendorCodec();
}
```

To understand what type this bean has, Spring must process information about `OptionalCodec`. If the type named in the signature is absent at runtime, problems can surface right **during introspection**, rather than when calling the `new VendorCodec()` body.

### 3.2. Why Is a Method Annotation Not Early Enough?

A method-level condition may have sound logic:

```text
If OptionalCodec is on classpath -> create bean
If not                           -> skip bean
```

Yet in order to **reach** the point where the method-level condition is evaluated, the system may already have had to process a class whose method signature references `OptionalCodec`. In other words, the actual sequence may be:

```text
Load or introspect configuration class
      |
      +--> Resolve return type OptionalCodec
              |
              +--> Class absent -> linkage/introspection error
      |
      +--> Too early to apply condition on @Bean
```

Therefore, **guard the class containing the method**: if the class is absent, Spring can discard the configuration based on class metadata without needing to inspect methods with missing return types.

## 4. Separating Compile Classpath and Runtime Classpath

“Optional SDK” does not mean Java source can use SDK types without a compile dependency.

- **Compile classpath:** the compiler needs the `OptionalCodec` type to check return types, constructors, and method calls.
- **Runtime classpath:** the running application only sees the JARs actually supplied at runtime.
- **Test classpath:** often broader than production; the SDK may be present in tests so bugs only explode upon deployment.
- **ClassLoader visibility:** a class inside some JAR is still not necessarily visible to the application's loader (isolation, plugin loaders, server loaders...).

For example:

```text
Library module compiles with SDK           -> OK
Library artifact published                 -> OK
Consumer does not pull SDK at runtime      -> OptionalCodec absent
Spring tries to resolve @Bean return type  -> risk of failure
```

In Maven, `<optional>true</optional>` prevents the dependency from propagating transitively to consumers along that edge. It **does not mean the dependency disappears from the module's own runtime when you run that module**. In Gradle, `compileOnly` is not placed on the source set's runtime classpath by default. Actual packaging behavior must be verified via the dependency graph and final artifact.

**A test scenario never to skip:** the test suite runs on a classpath with the SDK and everything passes, yet production consumers do not install the SDK. This is why you must simulate absence with `FilteredClassLoader` or a real consumer module lacking the SDK.

## 5. The Right Mechanism: Guarding a Separate @Configuration Class

Spring Boot recommends placing `@ConditionalOnClass` on a **configuration class** instead of only on an `@Bean` method whose return type uses an optional SDK.

Structural pattern:

```java
@AutoConfiguration
public class AppAutoConfiguration {

    // Core beans independent of the SDK.

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.vendor.codec.OptionalCodec")
    static class OptionalCodecConfiguration {

        @Bean
        com.vendor.codec.OptionalCodec optionalCodec() {
            // Create real codec if the SDK is present.
            return ...;
        }
    }
}
```

This is **illustrative pseudocode**, not independently compilable because vendor types and `return ...` are undefined. The runnable example in section 8 uses a self-defined `OptionalCodec` to avoid depending on a commercial SDK.

**Why is this structure safer?**

1. The outer `AppAutoConfiguration` does not need to expose optional return types in any of its `@Bean` methods.
2. The nested configuration has `@ConditionalOnClass` **at the class level**.
3. Spring can read the nested class's metadata via ASM and see that the condition does not match **before needing to load / introspect methods inside**.
4. When the SDK is absent, the entire optional branch is skipped; core beans on the outer configuration can still be registered.
5. When the SDK is present, Spring evaluates bean/property conditions and creates the adapter as usual.

### 5.1. Why Must It Be a static Nested Class?

A **static nested configuration** is an independent class at the JVM level, needing no implicit reference to an instance of the outer class. This is a deliberate boundary allowing Spring to scan metadata, evaluate the nested class's condition, and avoid implicit coupling to an outer instance.

Do not use a non-static inner class for an auto-configuration guard; it carries an enclosing instance reference and complicates lifecycle/configuration processing.

### 5.2. When to Use a Separate Top-Level Configuration?

If the optional branch has many beans, many conditions, or needs to be shipped as a major integration, you can use a dedicated class:

```java
// Illustrative code on organization; imports and implementation omitted.
@AutoConfiguration
@ConditionalOnClass(name = "com.vendor.codec.OptionalCodec")
public class VendorCodecAutoConfiguration {

    @Bean
    OptionalCodec optionalCodec() {
        return ...;
    }
}
```

Declare `VendorCodecAutoConfiguration` as a candidate in `AutoConfiguration.imports`. The class-level guard still protects **return types inside that class itself**. For multiple independent features, splitting top-level auto-configurations also makes excluding and debugging per feature easier.

For a small integration that is a sub-part of a larger feature, a nested `@Configuration(proxyBeanMethods = false)` is a compact choice with the right boundary.

## 6. How Do Class-Valued and Name-Valued Annotations Differ?

Spring Boot's `@ConditionalOnClass` supports two forms:

```java
@ConditionalOnClass(value = OptionalCodec.class)
```

```java
@ConditionalOnClass(name = "com.example.optional.OptionalCodec")
```

Both are **fragments to place at the class level**, not standalone Java files.

When attached directly to an `@Configuration` class, Spring Boot can read the annotation's metadata with ASM before loading the class, so class-literal `value` is also safely supported in that recommended case. However:
- When used in a custom **meta-annotation / composed annotation**, the `name` form avoids issues caused by class references during annotation processing; verify the composition contract.
- When the auto-configuration module wants to avoid requiring a direct import of the optional class in the annotation snippet, `name` lets you write the fully qualified name as a string.
- Whether using `value` or `name`, **never let optional types leak into signatures of a class that is always loaded**.

### 6.1. What Must You Not Conclude?

Do not say “Using `name` on `@Bean` is completely safe”; the risk lies in the **method signature**.

Nor should you say “Every reference to an optional class immediately crashes when a class is loaded”; the JVM has lazy resolution mechanisms. The issue is that **there is no guarantee** Spring will not introspect/resolve the signature before the method condition is processed.

### 6.2. Why Doesn't @ConditionalOnMissingClass Replace This Solution?

`@ConditionalOnMissingClass` enables a configuration when a class is **absent**; this lesson wants to create a codec when the class is **present**. Switching to MissingClass would invert the logic and still fail to protect unsafe signatures if placed at the wrong level.

## 7. Not Just Return Types: Parameters, extends, and Fields Too

Return types stand out because Spring needs bean type metadata, yet other optional references can also make a configuration unsafe:

```java
// RISKY fragments if the SDK is absent.
@Bean
CoreClient client(com.vendor.codec.OptionalCodec codec) {
    return ...;
}
```

```java
// Configuration that is always loaded and extends an optional SDK class.
class UnsafeConfiguration extends com.vendor.sdk.BaseConfiguration {
}
```

```java
// Optional field type on a configuration class that is always parsed.
private com.vendor.codec.OptionalCodec codec;
```

```java
// Static initialization reference that can fail during class init.
private static final Object CLIENT =
        com.vendor.sdk.Factory.create();
```

All of these are **illustrative snippets that do not compile standalone** due to hypothetical vendor packages and incomplete bodies. The general rule is to **keep optional dependency boundaries inside classes that are already guarded**.

### 7.1. A Subtle Case: Neutral Method Return Type

If `@Bean` returns a core interface independent of the SDK, such as `CodecPort`, the external signature does not directly contain `OptionalCodec`. Even so, if the body, method parameters, fields, or static initialization directly use the optional class, you still must design guards in the right places. Furthermore, arbitrarily changing the return type to `Object` to dodge the JVM can deprive Spring of bean type info needed for autowiring and `@ConditionalOnMissingBean`.

Fix the **classpath boundary**, rather than using vague return types that break the API.

## 8. Runnable Java 17 / Spring Boot 3.3.13 Demo

The demo below actually provides:
- **Core service:** always usable, even when the optional codec is hidden.
- **Optional codec:** created only when `OptionalCodec` is present to the evaluated loader.
- **Safe nested configuration:** contains the `@Bean` with return type `OptionalCodec` and is guarded by `@ConditionalOnClass` **at the class level**.
- **FilteredClassLoader test:** simulates `OptionalCodec` being absent at runtime without requiring multiple Maven modules.

**Experimental limitation:** The demo SDK is included in the same project to keep compilation simple, so when running regular `mvn spring-boot:run`, `OptionalCodec` is present. Only when using `FilteredClassLoader` in tests do we simulate class absence. To fully prove the case where an optional JAR is **not** in the production runtime, you need a separate consumer project/module with the corresponding dependency graph.

### 8.1. File Structure

```text
optional-signature-demo/
├── pom.xml
└── src/
    ├── main/
    │   ├── java/com/example/
    │   │   ├── app/DemoApplication.java
    │   │   ├── core/CoreService.java
    │   │   ├── optional/OptionalCodec.java
    │   │   └── autoconfigure/ExampleAutoConfiguration.java
    │   └── resources/META-INF/spring/
    │       └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
    └── test/
        └── java/com/example/autoconfigure/
            └── ExampleAutoConfigurationTest.java
```

Package layout note: main application in `com.example.app`; auto-configuration in `com.example.autoconfigure`. The app's default component scan does not automatically scan the auto-configuration class; the imports list is the explicit discovery path.

### 8.2. pom.xml

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
    <artifactId>optional-signature-demo</artifactId>
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

The project only needs JDK 17+ and Maven 3.x. These two starters supply sufficient basic and test dependencies.

### 8.3. Core Service Independent of the SDK

Create `src/main/java/com/example/core/CoreService.java`:

```java
package com.example.core;

@FunctionalInterface
public interface CoreService {
    String reply(String input);
}
```

This interface does not import optional classes. Even if `OptionalCodec` is hidden, the core portion can still work.

### 8.4. Mock Optional SDK for Compilation

Create `src/main/java/com/example/optional/OptionalCodec.java`:

```java
package com.example.optional;

@FunctionalInterface
public interface OptionalCodec {
    String encode(String text);
}
```

In a real product, this interface would live inside an SDK dependency. In the demo, we place it in source so the method signature can compile too. `FilteredClassLoader` will be used **in tests** to create the “runtime-absent” condition without switching the entire dependency graph.

### 8.5. Safe Auto-Configuration via Nested Class

Create `src/main/java/com/example/autoconfigure/ExampleAutoConfiguration.java`:

```java
package com.example.autoconfigure;

import com.example.core.CoreService;
import com.example.optional.OptionalCodec;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class ExampleAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CoreService.class)
    CoreService coreService() {
        return input -> "core:" + input;
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.example.optional.OptionalCodec")
    @ConditionalOnProperty(
            prefix = "demo.optional",
            name = "enabled",
            havingValue = "true",
            matchIfMissing = true)
    static class OptionalCodecConfiguration {

        @Bean
        @ConditionalOnMissingBean(OptionalCodec.class)
        OptionalCodec optionalCodec() {
            return text -> "ENC:" + text;
        }
    }
}
```

**Key points in this file:**

1. `ExampleAutoConfiguration` is a class **Boot can always evaluate**, regardless of whether the optional codec is present.
2. `coreService()` uses only `CoreService`, with no reference to the optional SDK in its method signature.
3. `OptionalCodecConfiguration` is a static nested `@Configuration`, guarded **at the class level** by the FQCN of `OptionalCodec`.
4. The `optionalCodec()` method has an optional return type, yet **resides inside** the guarded class. When the codec is absent, Spring can skip the nested configuration after reading class metadata rather than entering its method signatures.
5. `@ConditionalOnProperty` lets users explicitly disable the codec integration without affecting core.
6. `@ConditionalOnMissingBean(OptionalCodec.class)` lets consumers supply their own codec. This condition is evaluated when the nested class can be safely processed and the SDK is present.
7. Having the Java import `import com.example.optional.OptionalCodec;` at the top of the file **is not the cause of errors**; danger lies in **bytecode references** (signatures, superclasses, fields, static initialization...) of unguarded classes. Imports in Java source are just naming syntax for the compiler.

**Why not wrap all of ExampleAutoConfiguration with `@ConditionalOnClass`?** Doing so would skip even `CoreService` when the codec is absent. A nested configuration guards strictly the **optional branch** instead of disabling the entire auto-configuration.

### 8.6. Registering the imports Resource

Create the exact path:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Content:

```text
com.example.autoconfigure.ExampleAutoConfiguration
```

You do not need to list `ExampleAutoConfiguration$OptionalCodecConfiguration` here. The nested configuration is processed by Spring as part of the outer configuration; the imports file only publishes the outer candidate in this example.

### 8.7. Main Application to Observe Results

Create `src/main/java/com/example/app/DemoApplication.java`:

```java
package com.example.app;

import com.example.core.CoreService;
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
    ApplicationRunner showResults(
            CoreService coreService, ApplicationContext context) {
        return args -> {
            System.out.println("CORE=" + coreService.reply("ping"));
            System.out.println("OPTIONAL_DEFAULT_BEAN="
                    + context.containsBean("optionalCodec"));
        };
    }
}
```

Here the runner only injects `CoreService`, a type independent of the optional SDK. To observe the default codec, the code **queries existence by bean name**; the runner does not use `OptionalCodec.class` or inject the optional SDK interface, preventing the observer app itself from becoming a source of errors when the SDK is absent.

### 8.8. Default Run and Reading stdout

```bash
mvn test
mvn spring-boot:run
```

With the demo SDK present in the same artifact and default properties, the two lines from `ApplicationRunner` are:

```text
CORE=core:ping
OPTIONAL_DEFAULT_BEAN=true
```

Maven/Spring Boot may print many other startup logs; these are just the two lines produced by the runner. `OPTIONAL_DEFAULT_BEAN=true` means a bean **named "optionalCodec"** is registered, not that all implementations of `OptionalCodec` bear that name.

### 8.9. Disabling the Optional Branch via Property Without Disabling Core

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--demo.optional.enabled=false"
```

Two lines from the runner:

```text
CORE=core:ping
OPTIONAL_DEFAULT_BEAN=false
```

The property condition on the nested class prevents the entire optional branch from applying; the outer core bean is still registered. This is another reason a codec might not appear, distinct from SDK absence.

## 9. Testing the Exact Risk: FilteredClassLoader

Create `src/test/java/com/example/autoconfigure/ExampleAutoConfigurationTest.java`:

```java
package com.example.autoconfigure;

import com.example.core.CoreService;
import com.example.optional.OptionalCodec;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class ExampleAutoConfigurationTest {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(AutoConfigurations.of(
                            ExampleAutoConfiguration.class));

    @Test
    void optionalClassPresentCreatesBothBeans() {
        runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(CoreService.class);
            assertThat(context).hasSingleBean(OptionalCodec.class);
            assertThat(context.getBean(CoreService.class).reply("ping"))
                    .isEqualTo("core:ping");
            assertThat(context.getBean(OptionalCodec.class).encode("x"))
                    .isEqualTo("ENC:x");
        });
    }

    @Test
    void missingOptionalClassSkipsOnlyGuardedConfiguration() {
        runner.withClassLoader(new FilteredClassLoader(OptionalCodec.class))
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CoreService.class);
                    assertThat(context).doesNotHaveBean("optionalCodec");
                    assertThat(context.getBean(CoreService.class).reply("ping"))
                            .isEqualTo("core:ping");
                });
    }

    @Test
    void optionalFeatureDisabledSkipsCodec() {
        runner.withPropertyValues("demo.optional.enabled=false")
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CoreService.class);
                    assertThat(context).doesNotHaveBean(OptionalCodec.class);
                });
    }

    @Test
    void userCodecMakesDefaultBackOff() {
        runner.withUserConfiguration(UserCodecConfiguration.class)
                .run(context -> {
                    assertThat(context).hasNotFailed();
                    assertThat(context).hasSingleBean(CoreService.class);
                    assertThat(context).hasSingleBean(OptionalCodec.class);
                    assertThat(context.getBean(OptionalCodec.class).encode("x"))
                            .isEqualTo("USER:x");
                    assertThat(context).doesNotHaveBean("optionalCodec");
                });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCodecConfiguration {

        @Bean
        OptionalCodec userCodec() {
            return text -> "USER:" + text;
        }
    }
}
```

Run:

```bash
mvn test
```

The test suite verifies four paths:
- **SDK present:** both core and codec exist and work.
- **SDK hidden by FilteredClassLoader:** core still works, optional bean is not created, **ApplicationContext does not fail**.
- **Property disabled:** codec is not registered even though the type exists.
- **Consumer supplies bean:** default codec backs off; the app-created bean is used.

### 9.1. Why Is This Test Different from Ordinary Tests?

If you only run `mvn test` on a full classpath, any method signature containing `OptionalCodec` resolves easily. That **does not verify** resilience to a missing SDK.

`FilteredClassLoader(OptionalCodec.class)` creates a loader for the context in which the specified class is filtered out; Spring Boot supports using it with `ApplicationContextRunner` to observe auto-configuration when the class is removed from the visible classpath.

Crucially: the missing-class test **does not** directly request `OptionalCodec.class` inside the filtered context callback. It only checks `CoreService.class` (always present) and the bean name `"optionalCodec"`. Thus the test itself does not attempt to load or resolve the SDK type through the filtered loader.

**Limitation:** FilteredClassLoader simulates class visibility during testing; it does not prove behavior on every app server or multi-ClassLoader environment. For a real library, also include a **consumer integration test** using a dependency graph lacking the SDK and running on the actual published artifact.

### 9.2. Inspecting JAR Packaging

```bash
mvn package
jar tf target/optional-signature-demo-0.0.1-SNAPSHOT.jar
```

In a Boot executable JAR, the imports resource normally sits at:

```text
BOOT-INF/classes/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

And the nested class is compiled into a file named:

```text
BOOT-INF/classes/com/example/autoconfigure/ExampleAutoConfiguration$OptionalCodecConfiguration.class
```

The `$` is how the JVM forms a nested class's binary name. Do not replace the imports file's content with this nested class; the outer class is the listed auto-configuration candidate.

## 10. Fixing Errors in a Real Library with Optional Dependencies

In real projects, the optional SDK does not live in the same source tree as in the demo. Common architecture:

```text
library-core.jar
  CodecPort
  ApplicationFeature

library-autoconfigure.jar
  CoreAutoConfiguration
  VendorSdkAutoConfiguration (guarded class)
  META-INF/spring/...AutoConfiguration.imports

vendor-sdk.jar (OPTIONAL on consumer side)
  com.vendor.codec.OptionalCodec

consumer-app.jar
  -> library-core
  -> library-autoconfigure
  -> may or may not include vendor-sdk
```

### 10.1. Maven Optional Dependency Pattern

In `library-autoconfigure/pom.xml` (dependencies fragment):

```xml
<dependency>
    <groupId>com.vendor</groupId>
    <artifactId>vendor-codec-sdk</artifactId>
    <version>1.2.3</version>
    <optional>true</optional>
</dependency>
```

This is an **illustrative pattern**, with a hypothetical vendor/version, not a real dependency coordinate. It lets the library module compile against the SDK, while consumers do not transitively receive that dependency by default.

In Gradle you can use `compileOnly("com.vendor:vendor-codec-sdk:1.2.3")` when designing appropriate variant/dependency publication. Inspect the published dependency metadata rather than just looking at the build file.

**Yet this is only half the solution.** Even though the SDK can be absent at runtime, the auto-configuration bytecode still needs guards at the right layer. `optional=true` does not fix a failing return type signature by itself.

### 10.2. Inspecting the Actual Dependency Tree

```bash
mvn dependency:tree
```

Or Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

For deployed applications, distinguish the runtimes of the IDE, Maven test, executable JAR, container, and app server. An SDK thought to be omitted may still arrive through another starter; conversely, a class may compile yet the runtime image lacks the JAR.

### 10.3. Splitting Configuration by Feature, Not Blocking All Beans

Target structure:

```text
CoreAutoConfiguration
  -> @Bean CoreService (does not depend on optional SDK)

VendorSdkAutoConfiguration
  -> @ConditionalOnClass(vendor SDK)
  -> @Bean VendorAdapter / OptionalCodec
```

If you put `@ConditionalOnClass` on a configuration holding both core and vendor, missing the vendor makes **core vanish** unnecessarily. Guard strictly at the feature boundary.

### 10.4. Do Not Leak Optional SDK into Required Core APIs

If the public `CoreService` interface has a method taking/returning `OptionalCodec`, every core consumer may still need to resolve the SDK type even if you split `@Configuration`. Auto-configuration only guards bean registration; **it cannot fix a core API designed to depend on an optional SDK**.

For true separation:
- `core` defines neutral APIs;
- `vendor-adapter` depends on the SDK and implements the core API;
- `vendor-autoconfigure` guards SDK presence before configuring the adapter;
- consumers without the SDK can still use core functionality.

## 11. Error Messages and How to Distinguish Them

Not every missing-dependency error produces the same exception. Depending on where it occurs:

| Error / symptom | Likely cause | What to check |
| --- | --- | --- |
| `java.lang.NoClassDefFoundError: com/vendor/codec/OptionalCodec` | JVM tried to resolve a class the runtime loader cannot see | Method return type, parameter, superclass, static initializer, packaging |
| `ClassNotFoundException: com.vendor.codec.OptionalCodec` | A loader/API explicitly looked up the class and could not find it | Runtime JARs, ClassLoader, reflection code |
| `TypeNotPresentException` | A type in a generic signature/annotation or metadata does not exist | Annotation/generic signature, reflective access |
| `Failed to introspect Class [...]` | Spring reflected methods/fields of a config class and hit a missing type | Read deep `Caused by` chain, class containing `@Bean` |
| `@ConditionalOnClass did not find required class` | **Normal condition non-match** | Condition report; expected behavior if feature is optional |
| `BeanCreationException` | Bean definition was selected; constructor/factory/init failed | Root cause: dependency, config, network, logic |
| `NoSuchMethodError` / `IncompatibleClassChangeError` | Class is present yet binary/API version is incompatible | Dependency convergence, SDK version |
| `UnsatisfiedDependencyException` | Spring could not find a required bean for injection | Is feature enabled; is there a consumer fallback |

A `@ConditionalOnClass` that does not match **properly** should allow the context to start if the feature is optional. If the JVM throws `NoClassDefFoundError` while introspecting a configuration class, you have not isolated the optional type correctly.

### 11.1. Do Not Confuse Condition Non-Match with Bean Creation Failure

- **Condition did not match:** Spring did not register that bean; you can see Negative matches in `ConditionEvaluationReport`.
- **Bean creation failed:** Spring already had a definition and called/instantiated the object, then failed. There is a `BeanCreationException` with a cause chain.
- **Signature/class linkage failed:** May happen **before** the method condition is evaluated; may log “Failed to introspect”, `NoClassDefFoundError`, or another JVM error.
- **Configuration not imported:** The candidate may be missing from imports or excluded; this is completely different from a class being processed yet hitting a signature error.

In practice, classification depends on logs, stack traces, and where the exception occurs; a single symptom like “app won't start” is not enough to draw a conclusion.

## 12. Debugging When Adding a Starter Crashes the App Due to Optional SDK

Follow this order:

1. **Find the missing type.** Read the full `Caused by` chain: what is the binary name in `NoClassDefFoundError` or `ClassNotFoundException`?
2. **Identify the class being introspected.** “Failed to introspect Class” stack traces usually name the configuration; inspect its `@Bean` methods, method arguments, superclass, and fields.
3. **Verify whether the SDK is in runtime.** Compare `mvn dependency:tree` or Gradle runtimeClasspath with artifact contents and the process classloader.
4. **Check where the condition sits.** If `@ConditionalOnClass` is only on the method returning the optional type, move the guard to **class-level**.
5. **Split the configuration.** Move all SDK-dependent signatures into a static nested `@Configuration` or dedicated top-level `@AutoConfiguration` with a class-level condition.
6. **Verify core is unaffected.** Missing SDK must not make core beans without SDK dependencies disappear.
7. **Add FilteredClassLoader tests.** Exercise class-present, class-absent, property-disabled, and consumer-override paths.
8. **Check the imports resource.** A well-guarded configuration class omitted from `AutoConfiguration.imports` still will not activate when a consumer has the SDK.
9. **Compare other exceptions.** If the class exists yet `NoSuchMethodError` occurs, check version compatibility instead of just class existence.
10. **Inspect the condition report.** When the context can run, enable `--debug`; if startup fails early, prioritize the exception chain before looking for the report.

Command for the demo:

```bash
mvn spring-boot:run "-Dspring-boot.run.arguments=--debug"
```

Spring Boot can print Positive/Negative matches, Exclusions, and condition details; however, **the condition report does not replace a full stack trace** when the JVM fails type linkage before context startup completes.

## 13. Why Are These “Quick Fixes” Bad?

### 13.1. “Just switch @ConditionalOnClass value to name”

Misses the point if the method signature is still `OptionalCodec`.

```java
@Bean
@ConditionalOnClass(name = "com.vendor.codec.OptionalCodec")
OptionalCodec optionalCodec() { ... }
```

This is still an anti-pattern fragment. `name` does not make the method return descriptor vanish from bytecode.

### 13.2. “Wrap NoClassDefFoundError in try/catch inside the factory method”

```java
@Bean
OptionalCodec optionalCodec() {
    try {
        return buildCodec();
    } catch (NoClassDefFoundError err) {
        return null;
    }
}
```

The fragment above **is not a fix**: the method might never even be called because the error occurs when the JVM/Spring introspects the signature. `return null` also cannot substitute for proper optional bean design and can cause confusing behavior in Spring.

### 13.3. “Change the return type to Object so the class won't load the SDK”

For example:

```java
@Bean
Object optionalCodec() {
    return buildOptionalCodec();
}
```

This may dodge a specific descriptor, yet bean type metadata is weakened; dependency injection by `OptionalCodec` and type-based conditions may stop working as expected. If the body still loads the missing SDK, the failure merely moves to another moment. **Only do this when the bean contract truly is Object and proper type discovery/design exists**, not as a hack to patch classpath issues.

### 13.4. “Just add @Lazy”

`@Lazy` can defer **instance creation**, yet does not promise to defer **configuration parsing / return type resolution**. If the JVM fails before bean definition registration finishes, lazy cannot help.

### 13.5. “Add @ConditionalOnMissingBean to guard the SDK”

`@ConditionalOnMissingBean` checks bean definitions, not optional SDK classpath availability in a way that protects method return types from JVM resolution. Its role is to back off when a consumer supplies a bean, **not to replace class-level `@ConditionalOnClass`**.

### 13.6. “Put the whole library behind @ConditionalOnClass(vendorSdk)”

That avoids method signature errors yet can accidentally turn off unrelated core beans. Split smaller integration branches so consumers do not lose other functionality.

## 14. Additional Testing: Do Not Confuse Classpath with Version Compatibility

`FilteredClassLoader` answers the question: **“If this class is invisible, is the configuration skipped safely?”**.

Yet a library has other questions too:

| Scenario | What to test? |
| --- | --- |
| SDK completely absent | Context still starts; only the optional branch is skipped |
| SDK present, compatible API | Adapter bean is created and works |
| SDK present, changed method signature | Test specific SDK versions; `@ConditionalOnClass` does not verify method existence |
| SDK transitive from another dependency | Real dependency graph, classpath convergence |
| User property disabled | Feature blocked even if SDK is present |
| Consumer supplies its own bean | Default adapter backs off; no two beans created |
| SDK has failing static initializer | Run lifecycle integration tests; class presence does not guarantee initialization |
| Custom ClassLoader | Test under target loader environment, especially in plugins/containers |
| Class present yet missing endpoint/credentials config | Validation/config tests; do not “patch” with classpath conditions |

A unit test with a custom classloader does not replace testing on the published artifact if the integration has complex classpath dependencies.

### 14.1. Avoid Choosing Too Broad a Condition

If an integration requires both `OptionalCodec` and `VendorTransport`, the class-level condition should reflect the true required dependencies:

```java
@ConditionalOnClass(name = {
        "com.vendor.codec.OptionalCodec",
        "com.vendor.transport.VendorTransport"
})
```

This is a class-level fragment. If you guard only codec while the factory method calls a missing transport API, the class-level condition can match and startup will still fail.

Conversely, do not require the entire vendor SDK for a feature that only needs a small API already present; choose the condition accurately per integration architecture.

## 15. Self-Check Questions

**Question 1.** Does `@ConditionalOnClass(name="com.vendor.Optional")` placed on `@Bean com.vendor.Optional optional()` guarantee the app runs when the class is absent?

**Answer:** No. The method signature references the optional type; Spring/the JVM may need to resolve it before the method-level condition is applied. Move the method into a configuration guarded at the class level.

**Question 2.** Why does Spring need the return type before creating the bean?

**Answer:** Spring needs bean type metadata for registering bean definitions, type matching, dependency injection, and bean-based conditions, so it may introspect the method before the factory body runs.

**Question 3.** Does simply having a Java import for the SDK in a file mean the JVM always loads that class immediately?

**Answer:** No. `import` in Java source is a compiler syntax convenience; runtime behavior depends on bytecode references, class loading, and resolution. The risk lies in signatures/fields/superclasses/static initializers in unguarded classes.

**Question 4.** Why use a nested static `@Configuration` instead of only putting the condition on the method?

**Answer:** A nested class provides a boundary with class-level metadata for Spring to evaluate before loading/introspecting its methods that carry optional return types.

**Question 5.** If the entire outer auto-configuration is guarded with `@ConditionalOnClass`, will core beans still exist when the SDK is absent?

**Answer:** No, if core beans reside inside the skipped class. Move the guard into the optional branch so core operates independently.

**Question 6.** What does `FilteredClassLoader(OptionalCodec.class)` prove?

**Answer:** It simulates the class being hidden from the ApplicationContext's ClassLoader. The test confirms guarded code does not fail when the class is absent, though it does not replace full consumer runtime dependency tests.

**Question 7.** Does `@Lazy` fix class linkage errors when Spring introspects configuration?

**Answer:** Not guaranteed. Lazy primarily defers bean instantiation; metadata/signature errors can happen beforehand.

**Question 8.** Does a matching `@ConditionalOnClass` mean the factory method is guaranteed to succeed?

**Answer:** No. The SDK may have the class yet lack compatible methods, lack credentials, have invalid config, or throw an exception in the factory method.

**Question 9.** Can `@ConditionalOnMissingBean` replace `@ConditionalOnClass`?

**Answer:** No. One checks existing beans to back off; the other checks the classpath to decide whether to activate the integration.

**Question 10.** Will Spring Boot tests running with all dependencies present catch bugs that only occur when the SDK is absent?

**Answer:** Usually not. You must intentionally write tests with `FilteredClassLoader` or a consumer runtime lacking the SDK.

## 16. Auto-Configuration Review Checklist for Optional Dependencies

When reviewing a starter pull request, verify:

- [ ] Optional integration has a **class-level `@ConditionalOnClass`** covering all SDK types appearing in signatures inside?
- [ ] `@Bean` methods in always-parsed configurations have **no** return/parameter types from the optional SDK?
- [ ] No unguarded superclasses, interfaces, fields, or static initializers reference the SDK?
- [ ] Core functionality still exists when the SDK is hidden?
- [ ] `@ConditionalOnMissingBean` is used appropriately so consumers can replace beans themselves?
- [ ] Enable/disable properties are scoped specifically to the integration?
- [ ] `AutoConfiguration.imports` lists the exact candidate FQCN and is packaged in the JAR?
- [ ] `FilteredClassLoader` tests prove the context does not fail when the SDK is absent?
- [ ] Tests with the SDK and consumer-override tests both pass?
- [ ] Optional/compile-only dependencies are published with correct metadata?
- [ ] When multiple optional SDK types exist, all required dependencies of the branch are guarded?
- [ ] Linkage exceptions are not treated as ordinary negative conditions before reading the root cause?

## 17. Summary and Official Documentation

**One-line mental model:**

```text
WRONG: @Bean OptionalSdkType method() + @ConditionalOnClass on method
RIGHT: @Configuration + @ConditionalOnClass on CLASS
       containing @Bean OptionalSdkType method()
       (core beans live outside the guarded optional class)
```

Spring Boot can evaluate class-level conditions via metadata without loading the configuration class and resolving optional signatures. Conversely, a method-level condition does not guarantee avoiding class loading/introspection of a method with a non-existent return type. To design a safe starter, **isolate optional APIs at the configuration class boundary**, test both class-absent and class-present scenarios, and distinguish compile dependencies from runtime dependencies.

**Official reference sources:**

- Spring Boot 3.3 — Creating Your Own Auto-configuration, *Class Conditions* and *Testing* sections: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3 — `ConditionalOnClass` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html
- Spring Boot 3.3 — `FilteredClassLoader` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/FilteredClassLoader.html
- Spring Boot 3.3 — `ApplicationContextRunner` Javadoc: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/test/context/runner/ApplicationContextRunner.html
- Spring Framework 6.1 — `Configuration` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Configuration.html
- Spring Framework 6.1 — `Bean` Javadoc: https://docs.spring.io/spring-framework/docs/6.1.x/javadoc-api/org/springframework/context/annotation/Bean.html
