# Isolating Configuration for Optional Dependencies Using Nested Configuration Classes

## 1. The Problem: A Library Has Optional Features, Yet Not Every App Installs the Dependency

Suppose a Spring Boot library provides a core feature that is always available and an integration that works only when the user installs an external library. For instance, an auto-configuration creates a default **CoreMarker** bean and, if the **OptionalFormatter** class is on the classpath, also creates an **OptionalFormatter** bean.

Reasonable requirements are:

- Applications **without** the optional library still start normally and can use the core feature.
- Applications **with** the optional library get the additional appropriate bean auto-configured by Spring Boot.
- Applications can supply their own bean to replace the default bean.
- When the optional library is **absent**, Spring does not have to load or fully analyze **@Bean** methods whose signatures depend on classes from that library.
- The auto-configuration library is discovered via **AutoConfiguration.imports**, without requiring users to add **@ComponentScan** or **@Import** for internal packages.

Merely placing **@ConditionalOnClass** on a **@Bean** method is not a reliable isolation technique when that method has a **return type or parameter type** belonging to a dependency absent at runtime. To avoid eager class loading/reading risks, Spring Boot recommends **placing the related methods inside a separate @Configuration class, usually a static nested class**, and attaching the classpath condition **onto that nested configuration class itself**.

That is the focus of this lesson. You will see how to design, implement, test, and diagnose that isolation mechanism using a Java 21 / Gradle / Spring Boot 3.3 project.

## 2. Distinguishing Optional Libraries, Auto-Configuration, and Class Loading

An **optional dependency** is a library that an additional feature can use, yet **is not required to exist in every consuming application**. For example, an integration module for a database, message broker, cache, JSON library, or observability tool may work only when that system's API is present.

**Auto-configuration** is the set of configuration classes that Spring Boot can discover, evaluate conditions on, and use to create default beans.

**Class loading and introspection** are actions taken by the JVM/Spring when loading classes and inspecting return types, parameters, annotations, or methods. If a parsed class has signatures or bytecode directly referencing a non-existent class, that process can lead to errors such as **NoClassDefFoundError**, **ClassNotFoundException**, or introspection failures depending on the processing path.

For example, **OptionalFormatter** exists only if the application puts the `optional-api` artifact onto the runtime classpath. The fact that the auto-configuration module's **source** compiled against `optional-api` does not guarantee the **consumer runtime** always has that artifact.

### 2.1. Why Is a Classpath Condition Sometimes Not Enough?

Consider the following **risky** pattern. This is illustrative code showing an approach to avoid, not a standalone Java file:

~~~java
@AutoConfiguration
class RiskyAutoConfiguration {

    @Bean
    @ConditionalOnClass(OptionalFormatter.class)
    OptionalFormatter optionalFormatter() {
        return new OptionalFormatter();
    }
}
~~~

Here the **@ConditionalOnClass** annotation is attached directly to the **@Bean method**. Meanwhile, the method signature returns **OptionalFormatter**, thereby already referencing a type that exists only when the optional dependency is present.

Spring may need to load the configuration and inspect the method signature **before the method condition is evaluated the way we expect**. If the type is absent, the configuration risks failing during class parsing. Therefore, you should not rely on a method-level annotation to protect that very method's signature.

**Conclusion:** a condition placed on a method and a condition placed on a configuration class are **not equivalent** in their ability to isolate optional classes.

### 2.2. Why Does a Nested Configuration Class Solve This?

Instead of leaving the method that uses `OptionalFormatter` directly inside the always-read auto-configuration, separate it out:

~~~java
@AutoConfiguration
public class SafeAutoConfiguration {

    @Bean
    CoreMarker coreMarker() {
        return new CoreMarker("core");
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(OptionalFormatter.class)
    static class OptionalFormatterConfiguration {

        @Bean
        OptionalFormatter optionalFormatter() {
            return new OptionalFormatter();
        }
    }
}
~~~

This is a **short illustrative pattern**, omitting package, imports, and override conditions. The outer class only references core types in its own bean method. The method with the **OptionalFormatter** signature is placed inside a **static nested configuration**. The classpath condition is attached at the **nested class level**, allowing Spring to read that class's annotation metadata and decide **whether to process the nested configuration class at all** before inspecting its methods deeply.

**@Configuration(proxyBeanMethods = false)** suits independent factory-method configurations where proxies are not needed to intercept calls between **@Bean** methods. The **static** keyword on the nested class ensures the nested class does not require an instance of the outer class.

This is the pattern recommended by official Spring Boot documentation whenever a **@Bean** return type belongs to an optional dependency.

## 3. Condition Evaluation Mechanism at the Configuration Class Level

When Spring Boot discovers an auto-configuration from **AutoConfiguration.imports**, Spring processes metadata and conditions of the matching configuration classes.

You can visualize it as:

~~~text
AutoConfiguration.imports
          |
          v
SafeAutoConfiguration (outer class)
          |
          +-----> CoreMarker coreMarker()
          |         does not depend on optional-api
          |
          +-----> OptionalFormatterConfiguration (static nested)
                     |
                     v
             @ConditionalOnClass(OptionalFormatter)
                     |
             +-------+-------+
             |               |
      Class absent       Class present
             |               |
             v               v
      Skip deep parsing    Process nested configuration
      of method signature          |
                                  v
                         @ConditionalOnMissingBean
                                  |
                                  v
                         Register OptionalFormatter
                         when no other bean exists
~~~

This separation keeps the **core branch** free from depending on types present only in the optional branch. When the optional class is absent, the nested configuration is not selected to register its beans.

### 3.1. ASM Metadata and @ConditionalOnClass

Spring Boot documentation describes reading annotation metadata using ASM. Consequently, when **@ConditionalOnClass(OptionalFormatter.class)** is placed **directly on a @Configuration class**, Spring can inspect class metadata without fully loading the configuration class in a way that resolves all method signatures up front. This is why the nested class pattern works.

There are two ways to specify the type:

~~~java
@ConditionalOnClass(OptionalFormatter.class)
~~~

or:

~~~java
@ConditionalOnClass(name = "com.example.optionalapi.OptionalFormatter")
~~~

Both snippets above are **illustrative annotations**, not standalone Java programs. **value/class literal** is typically used when the module has the optional class on its compile classpath; **name** is used when you do not want to reference a class literal or when building a composed annotation.

**Note:** If using **@ConditionalOnClass** as a meta-annotation inside a custom annotation you define, Spring Boot documentation requires using **name** instead of a class literal to ensure proper metadata handling. This differs from placing the annotation directly on a nested configuration as in this lesson's example.

### 3.2. Does the Nested Class Need Its Own @AutoConfiguration?

**No.** In the standard pattern, only the **outer class** is registered as an auto-configuration candidate:

~~~text
com.example.autoconfigure.OptionalFormatterAutoConfiguration
~~~

The nested class is a supporting **@Configuration** inside the outer class, processed by Spring via nested configuration class handling. You do not need to add a second line for **OptionalFormatterAutoConfiguration$OptionalFormatterConfiguration** to imports just for the nested class to take effect.

There are architectures that split optional configuration into a separate **top-level @Configuration** and conditionally import it. However, since this lesson focuses on **static nested @Configuration**, keep imports for the outer class and verify the nested class accordingly.

### 3.3. Do Not Confuse Type Conditions with Bean Conditions

- **@ConditionalOnClass** asks: is the class on the classpath?
- **@ConditionalOnMissingBean** asks: has a matching bean already been registered in the context?
- **@ConditionalOnProperty** asks: does the property match according to the declared semantics?
- **@ConditionalOnWebApplication** asks: does the web application type match?

These are complementary conditions. Having the class present is **not enough** to guarantee the default bean is created. When the user has already declared a bean, **@ConditionalOnMissingBean** can cause the default configuration to *back off*.

## 4. Designing the Example: Three Modules and One Optional Integration

We build the project:

~~~text
optional-config-lab/
├── settings.gradle
├── build.gradle
├── optional-api/
│   ├── build.gradle
│   └── src/main/java/com/example/optionalapi/OptionalFormatter.java
├── optional-autoconfigure/
│   ├── build.gradle
│   ├── src/main/java/com/example/autoconfigure/
│   │   ├── CoreMarker.java
│   │   └── OptionalFormatterAutoConfiguration.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/example/autoconfigure/
│       └── OptionalFormatterAutoConfigurationTests.java
└── demo-app/
    ├── build.gradle
    └── src/main/java/com/example/consumer/
        └── DemoApplication.java
~~~

Roles:

1. **optional-api:** a small JAR containing the **OptionalFormatter** class. It is required only if an application wants to use the integration.
2. **optional-autoconfigure:** a JAR containing **CoreMarker** and the auto-configuration class. This module **compiles** when `optional-api` is visible, yet **does not pull `optional-api` into the runtime** of consuming applications.
3. **demo-app:** a Spring Boot application receiving the auto-configuration via classpath and printing the status of both beans. The first experiment omits `optional-api`; the second adds it.

**Critical constraint:** The auto-configuration module must truly use **compileOnly** for the optional dependency. If you accidentally use **implementation project(':optional-api')**, Gradle will expose `optional-api` on the consumer's `runtimeClasspath`, invalidating the "missing dependency" experiment.

## 5. Complete Gradle Configuration

The example pins Spring Boot **3.3.13** with Java **21** to match a concrete version. That is the lab's version, not a claim about the latest release. JDK 21, a compatible Gradle 8.x, and dependency download access on first run are required.

### 5.1. Root settings.gradle

~~~groovy
rootProject.name = 'optional-config-lab'
include 'optional-api', 'optional-autoconfigure', 'demo-app'
~~~

### 5.2. Root build.gradle

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}

subprojects {
    apply plugin: 'java'
    apply plugin: 'io.spring.dependency-management'

    group = 'com.example'
    version = '1.0.0'

    java {
        toolchain {
            languageVersion = JavaLanguageVersion.of(21)
        }
    }

    repositories {
        mavenCentral()
    }

    dependencyManagement {
        imports {
            mavenBom 'org.springframework.boot:spring-boot-dependencies:3.3.13'
        }
    }

    tasks.withType(Test).configureEach {
        useJUnitPlatform()
    }
}
~~~

The root file applies the Java plugin and BOM to subprojects. **apply false** on the Spring Boot plugin at root merely declares the plugin; only **demo-app** applies the plugin to gain **bootRun** and **bootJar**. Library modules produce plain JARs.

### 5.3. optional-api/build.gradle

~~~groovy
plugins {
    id 'java-library'
}
~~~

### 5.4. optional-autoconfigure/build.gradle

~~~groovy
plugins {
    id 'java-library'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-autoconfigure'

    compileOnly project(':optional-api')

    testImplementation project(':optional-api')
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

The key points are:

- **compileOnly project(':optional-api')**: allows the Java compiler to resolve `OptionalFormatter` in the nested configuration without placing `optional-api` onto the consumer's runtime classpath.
- **testImplementation project(':optional-api')**: makes `OptionalFormatter` visible to tests, while still letting tests deliberately **hide** it using `FilteredClassLoader` to verify the missing-class branch.
- **implementation spring-boot-autoconfigure**: supplies the annotations and Spring Boot APIs required by the configuration class.
- **spring-boot-starter-test**: supplies JUnit 5, AssertJ, Spring Boot test, and `ApplicationContextRunner` for tests.

Do not replace **compileOnly** with **runtimeOnly** in the autoconfigure module: the library needs to see `OptionalFormatter` **when compiling the method signature**. Conversely, do not use **implementation** if the goal is ensuring `optional-api` does not propagate into every consumer's runtime.

### 5.5. demo-app/build.gradle

~~~groovy
plugins {
    id 'org.springframework.boot'
}

dependencies {
    implementation project(':optional-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

This application **does not declare** `optional-api`. The base starter provides a normal Spring Boot runtime without needing a web server to run `ApplicationRunner`.

## 6. Implementing Standalone optional-api

File **optional-api/src/main/java/com/example/optionalapi/OptionalFormatter.java**:

~~~java
package com.example.optionalapi;

public final class OptionalFormatter {

    public String format(String name) {
        return "Optional: " + name;
    }
}
~~~

This is a standalone Java class requiring no Spring. It simulates an external library API. Putting this class in a separate module lets us **actively vary `runtimeClasspath`** and verify whether Spring Boot isolates configuration properly when the class is absent.

If this class were written inside the autoconfigure module itself, it would always be on the classpath alongside the library and would no longer be a real optional dependency.

## 7. Creating CoreMarker and Auto-Configuration with a Nested Class

### 7.1. CoreMarker.java

File **optional-autoconfigure/src/main/java/com/example/autoconfigure/CoreMarker.java**:

~~~java
package com.example.autoconfigure;

public record CoreMarker(String name) {
}
~~~

`CoreMarker` does not depend on `optional-api`. It serves as the core bean proving the application still has baseline functionality when the optional integration is skipped.

### 7.2. OptionalFormatterAutoConfiguration.java

File **optional-autoconfigure/src/main/java/com/example/autoconfigure/OptionalFormatterAutoConfiguration.java**:

~~~java
package com.example.autoconfigure;

import com.example.optionalapi.OptionalFormatter;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class OptionalFormatterAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(CoreMarker.class)
    public CoreMarker coreMarker() {
        return new CoreMarker("core");
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(OptionalFormatter.class)
    static class OptionalFormatterConfiguration {

        @Bean
        @ConditionalOnMissingBean(OptionalFormatter.class)
        OptionalFormatter optionalFormatter() {
            return new OptionalFormatter();
        }
    }
}
~~~

This is the complete source of the configuration class. **@AutoConfiguration** on the outer class tells Spring Boot it is an auto-configuration candidate; **@ConditionalOnClass** is placed directly on the nested configuration.

**Why place OptionalFormatter.class inside the nested class?** The outer class has no **@Bean** returning `OptionalFormatter`. Method signatures using the optional type are confined inside **OptionalFormatterConfiguration**; Spring can skip this class based on metadata when `OptionalFormatter` is absent. This avoids introspection hazards when the optional JAR is missing.

**Why is @ConditionalOnMissingBean(OptionalFormatter.class) still needed?** When `optional-api` is present, the application can register its own custom `OptionalFormatter`. This condition prevents registering a second default bean. Classpath conditions and bean conditions serve two different purposes.

**Why is the nested class static?** A static nested class does not need an instance of the outer class. It fits the role of a small independent configuration used only when conditions pass.

**Why proxyBeanMethods = false?** The nested class does not call other **@Bean** methods via Java method calls. No proxy subclass is needed to route internal calls to beans through the container; this setting reduces overhead and expresses intent clearly.

**Can `@ConditionalOnClass(name = "...")` be used?** Yes. If replaced with:

~~~java
@ConditionalOnClass(
    name = "com.example.optionalapi.OptionalFormatter"
)
~~~

then Spring uses the string FQCN. This example uses the direct class literal to demonstrate compile-time type checking. Placing the condition at the configuration level makes it safe under the metadata mechanism documented by Spring Boot.

### 7.3. Adding Exactly One Line to AutoConfiguration.imports

Create the file:

~~~text
optional-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Exact contents:

~~~text
com.example.autoconfigure.OptionalFormatterAutoConfiguration
~~~

**Register only the outer class**; do not add the nested class to imports. The nested class is evaluated by Spring when processing the outer configuration. Do not add commas, **.class** syntax, or Java import statements.

Spring Boot 3.x uses the **AutoConfiguration.imports** resource to discover auto-configuration classes. Because the file lives in main resources, it gets packaged into the library JAR on a proper build.

## 8. Testing with ApplicationContextRunner

A solid design should verify at least three scenarios:

1. `OptionalFormatter` present -> context has both the core bean and the optional bean.
2. `OptionalFormatter` absent -> context still creates core, does not create the optional bean, and throws no class-loading error.
3. User already registered `OptionalFormatter` -> auto-configuration backs off and does not create the default.

**ApplicationContextRunner** is the right tool for running lightweight `ApplicationContext`s under different conditions without booting a web server.

File **optional-autoconfigure/src/test/java/com/example/autoconfigure/OptionalFormatterAutoConfigurationTests.java**:

~~~java
package com.example.autoconfigure;

import com.example.optionalapi.OptionalFormatter;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class OptionalFormatterAutoConfigurationTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    OptionalFormatterAutoConfiguration.class
                )
            );

    @Test
    void createsOptionalBeanWhenDependencyExists() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(CoreMarker.class);
            assertThat(context).hasSingleBean(OptionalFormatter.class);
            assertThat(
                context.getBean(OptionalFormatter.class).format("An")
            ).isEqualTo("Optional: An");
        });
    }

    @Test
    void startsWithoutOptionalDependency() {
        runner.withClassLoader(
            new FilteredClassLoader("com.example.optionalapi")
        ).run(context -> {
            assertThat(context).hasSingleBean(CoreMarker.class);
            assertThat(context.containsBean("optionalFormatter"))
                .isFalse();
            assertThat(context.getBean(CoreMarker.class).name())
                .isEqualTo("core");
        });
    }

    @Test
    void backsOffWhenUserSuppliesOptionalBean() {
        runner.withUserConfiguration(UserFormatterConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(OptionalFormatter.class);
                assertThat(context.containsBean("optionalFormatter"))
                    .isFalse();
                assertThat(context.containsBean("customFormatter"))
                    .isTrue();
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserFormatterConfiguration {

        @Bean
        OptionalFormatter customFormatter() {
            return new OptionalFormatter();
        }
    }
}
~~~

### 8.1. Explaining Each Test

**createsOptionalBeanWhenDependencyExists:** Tests use **testImplementation project(':optional-api')**, so `OptionalFormatter` is on the test classpath. The nested configuration is allowed, and auto-configuration registers a default `OptionalFormatter` bean.

**startsWithoutOptionalDependency:** **FilteredClassLoader** hides classes in the `optional-api` package while the context runs. The test does not call **getBean(OptionalFormatter.class)** in the missing-class branch because that call itself would depend on the hidden type. Instead, it asserts by bean name. If Spring processes the method signature directly at the wrong moment, this test can expose context startup failures.

**backsOffWhenUserSuppliesOptionalBean:** The test registers an application **@Configuration** class first. When the nested auto-configuration is evaluated, **@ConditionalOnMissingBean(OptionalFormatter.class)** does not match, so the default **optionalFormatter** bean is not registered. The user's **customFormatter** bean remains present.

### 8.2. Running Tests

In the root project directory:

~~~bash
gradle :optional-autoconfigure:test
~~~

If the project includes the Gradle Wrapper, run **./gradlew :optional-autoconfigure:test** on macOS/Linux or **.\gradlew.bat :optional-autoconfigure:test** on Windows.

**Expected result:** The test task succeeds; Gradle/JUnit prints console details per local and test-logging settings. There is no fixed stdout to copy verbatim. Each assertion is concrete proof of a bean's presence or absence.

### 8.3. What Scope Unit Tests Prove

Testing with **AutoConfigurations.of(OptionalFormatterAutoConfiguration.class)** passes the auto-configuration directly to the runner. It **verifies condition logic and safety when the optional class is hidden**.

It **does not prove** that **AutoConfiguration.imports** is packaged into the JAR and that Spring Boot auto-discovers the class when a consumer merely adds the dependency. You need an extra consumer-application verification step; do not confuse condition tests with discovery tests.

## 9. Running the Consuming Application and Proving the Dependency Is Truly Optional

File **demo-app/src/main/java/com/example/consumer/DemoApplication.java**:

~~~java
package com.example.consumer;

import com.example.autoconfigure.CoreMarker;
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
    ApplicationRunner inspectBeans(ApplicationContext context) {
        return args -> {
            System.out.println(
                "Core bean: " + !context.getBeansOfType(CoreMarker.class)
                    .isEmpty()
            );
            System.out.println(
                "Optional bean: " + context.containsBean("optionalFormatter")
            );
        };
    }
}
~~~

The application's package is **com.example.consumer**, distinct from **com.example.autoconfigure**. Thus, default component scanning from **DemoApplication** does not accidentally pick up the auto-configuration. Spring Boot discovers it through **AutoConfiguration.imports** in the library module's JAR.

### 9.1. Run A: Only autoconfigure, Without optional-api

Keep **demo-app** dependencies as in section 5, without adding **optional-api**. Inspect `runtimeClasspath`:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
~~~

Confirm that **optional-api** does not appear as a resolved runtime dependency. If that artifact shows up, trace which dependency edge pulled it in, because the experiment loses meaning if the class is actually present.

Then run:

~~~bash
gradle :demo-app:bootRun
~~~

When configured correctly, the two lines printed by `ApplicationRunner` are expected to be:

~~~text
Core bean: true
Optional bean: false
~~~

The application still boots without `OptionalFormatter`. That is the key behavior to prove: **the core branch exists, and the branch depending on the optional type is safely skipped**.

### 9.2. Run B: Adding optional-api to Runtime

Add **only this line** inside the `dependencies` block of **demo-app/build.gradle**:

~~~groovy
runtimeOnly project(':optional-api')
~~~

Because `DemoApplication` does not directly import or reference `OptionalFormatter` in source code, **runtimeOnly** is sufficient to place the optional class onto the consumer's runtime.

Run again:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
gradle :demo-app:bootRun
~~~

Expected output lines:

~~~text
Core bean: true
Optional bean: true
~~~

Now `OptionalFormatter` is on the classpath, so the nested configuration passes **@ConditionalOnClass**. No user-supplied `OptionalFormatter` bean exists yet, so the default bean is created.

### 9.3. An Experiment to Compare Different Root Causes

Keep `optional-api` on `runtimeClasspath`, then exclude the library's entire auto-configuration via argument:

~~~bash
gradle :demo-app:bootRun --args='--spring.autoconfigure.exclude=com.example.autoconfigure.OptionalFormatterAutoConfiguration'
~~~

Both the core bean and the optional bean created by the library are no longer auto-configured. This is **outer auto-configuration exclusion**, not equivalent to simply missing an optional dependency; it highlights the difference between **a nested class condition** and **excluding the entire outer auto-configuration**.

To disable only the optional branch while keeping core, you can add **@ConditionalOnProperty** on the nested configuration with a dedicated enablement property. There is no need to write a custom `AutoConfigurationImportFilter` for this common scenario.

## 10. Inspecting the Library JAR and Imports File

Package the autoconfigure module:

~~~bash
gradle :optional-autoconfigure:jar
~~~

With the root version, the default JAR is:

~~~text
optional-autoconfigure/build/libs/optional-autoconfigure-1.0.0.jar
~~~

List its contents:

~~~bash
jar tf optional-autoconfigure/build/libs/optional-autoconfigure-1.0.0.jar
~~~

Check three entry groups:

~~~text
com/example/autoconfigure/CoreMarker.class
com/example/autoconfigure/OptionalFormatterAutoConfiguration.class
com/example/autoconfigure/OptionalFormatterAutoConfiguration$OptionalFormatterConfiguration.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

The bytecode filename of the nested class has a **$** between the outer class name and nested class name. This is normal for a **static nested class**.

**The autoconfigure JAR must not contain OptionalFormatter.class**, because that class belongs to **optional-api**. Keep `optional-api` in a separate JAR so that when an application does not install it, the nested condition branch genuinely has a chance to be skipped.

Also inspect the contents of the imports resource inside the JAR if a ZIP reader tool is available:

~~~bash
unzip -p optional-autoconfigure/build/libs/optional-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Output must contain the outer class FQCN. If the environment lacks `unzip`, use an equivalent ZIP/JAR tool. Passing `ApplicationContextRunner` tests while missing imports can still prevent consumers from auto-discovering the library.

## 11. Why Is a Nested Configuration Better Than a Condition on @Bean?

Comparison:

| Design | If OptionalFormatter is absent | Safety assessment |
| --- | --- | --- |
| **@ConditionalOnClass** directly on the method returning `OptionalFormatter` in an always-processed config class | Spring may have to introspect the method signature before applying the condition | Risks type-loading errors; not the recommended pattern. |
| **@ConditionalOnClass** placed on a **static nested @Configuration** containing the method returning `OptionalFormatter` | Class-level condition is evaluated before the nested configuration needs full processing | Isolation pattern documented by Spring Boot. |
| Condition using only **@ConditionalOnMissingBean** | Depends on bean state; does not prove the optional class is present | Insufficient protection against missing libraries. |
| Using **name** in the classpath condition while keeping the method in the outer class | Avoids class literal in the annotation, yet the method signature still references the optional type | Does not completely solve introspection risk. |
| Forcing `optional-api` to be a required runtime dependency | Avoids missing class by pulling the library in unconditionally | No longer meets the optional-dependency goal. |

The right design question is: **Which class can the framework inspect when the optional dependency is absent?** Then place every method signature directly using optional types inside a configuration guarded by a class-level condition.

### 11.1. Considerations When the Nested Class Has Complex Dependencies

Real libraries may use method parameters, constructor parameters, fields, static initializers, generic types, and annotations containing optional classes. Each reference can trigger different class-loading interactions.

Therefore:

- Do not let the **outer class** hold a **field of type OptionalFormatter** or use optional classes in static initializers.
- Do not declare a bean method on the outer class with an optional class as its **return type** or parameter.
- Keep optional dependencies inside the **nested configuration** and implementation classes instantiated only after conditions match.
- If optional APIs are used across multiple groups, consider isolating each group in its own appropriately conditioned nested configuration.
- Place **@ConditionalOnMissingBean** on auto-configuration beans when defaults must back off.
- Verify version compatibility of the optional library: **class presence** does not guarantee the methods/constructors your code invokes remain compatible. Version checks or separate integration modules may be needed when APIs change substantially.

Nested configuration helps manage dependency boundaries; it does not replace proper dependency declarations or testing against supported versions.

## 12. Real-World Troubleshooting

### Case A — @ConditionalOnClass Is Present, Yet NoClassDefFoundError Still Occurs

Check where the annotation is placed. If it sits on a **@Bean** method returning the missing class itself, code still risks failing when Spring introspects the method. Move **all related methods** into a nested **@Configuration(proxyBeanMethods = false)** and place the condition on the nested class.

If the error persists, look for other optional references in the outer class, constructors, fields, static initializers, or eagerly loaded classes. Class-loading failures can stem from another reference rather than just the method you are looking at.

### Case B — Optional Class Is Present, Yet the Bean Is Not Created

Read the Condition Evaluation Report by running the app with:

~~~bash
gradle :demo-app:bootRun --args='--debug'
~~~

Check these possibilities:

1. Was the auto-configuration candidate discovered via imports?
2. Is an exclusion rule filtering out the outer class?
3. Is the optional class truly on `demo-app`'s **runtimeClasspath**, or only on `compileClasspath`/`testRuntimeClasspath`?
4. Did **@ConditionalOnMissingBean** back off for a user-declared bean?
5. Are properties, profiles, other conditions, or bean creation errors interfering?

Inspect beans by **type and name**, rather than glancing only at startup logs.

### Case C — Tests Pass, Consuming App Still Fails

**ApplicationContextRunner** supplies configuration classes directly and can mask errors in the imports file. Use **jar tf** to verify the resource, check the class name inside the imports file, and inspect the consumer's dependency graph.

If the consumer uses a different version of the optional API, tests running against the module's version might not cover that case. Add an integration test targeting that version when needed.

### Case D — optional-api Always Appears Even Though compileOnly Was Used

**Another** dependency may be pulling `optional-api` into runtime transitively. Run:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
gradle :demo-app:dependencyInsight --configuration runtimeClasspath --dependency optional-api
~~~

In this lab project, both `optional-api` and the other subprojects live in the same Gradle build, yet dependencies enter runtime strictly per each project's configuration. **compileOnly on `optional-autoconfigure`** does not mean "never packaged" across every other build system, so inspect the actual artifact and `runtimeClasspath` instead of inferring from one label.

### Case E — Two OptionalFormatter Beans Exist

Check user-declared beans and **@ConditionalOnMissingBean(OptionalFormatter.class)** in the nested class. If both beans exist, inspect bean definition registration order, whether types match, and whether a configuration class was imported twice via another path. Do not rush to enable global bean definition overriding to mask conflicts.

## 13. When to Use a Separate Top-Level Configuration Instead of a Nested Class?

Nested static **@Configuration** is convenient when the optional feature is small, has one group of beans, and naturally belongs to an outer auto-configuration. For larger integrations, you can extract an independent **top-level configuration** (or separate auto-configuration module), place the classpath condition on that class, and manage imports/ordering explicitly.

Whether nested or top-level, the principle remains the same: **do not let always-processed configuration eagerly reference types that exist only on an optional classpath**.

Do not add package-wide **@ComponentScan** inside auto-configurations to pick up all library beans. Doing so makes dependency boundaries hard to control and can register beans when dependencies or conditions do not fit.

## 14. Extension Exercises

1. **Move the condition from class to method:** In an experimental branch, move the optional method to the outer class and place `@ConditionalOnClass` only on the method. Run the `FilteredClassLoader` test; observe the result and explain why the new layout poses class-loading risks.
2. **Add an enable/disable property:** Place **@ConditionalOnProperty(prefix="demo.formatter", name="enabled", havingValue="true", matchIfMissing=true)** on the nested configuration. Write two tests for `enabled` true/false while keeping missing-class behavior working.
3. **Replace the default bean:** Write a custom `OptionalFormatter` bean in the consumer with a different format implementation. Verify only one bean of that type is used.
4. **Inspect runtimeClasspath:** Intentionally change **compileOnly** to **implementation** in the library (in an experimental branch) and re-read the dependency graph. Explain why the application loses the ability to demonstrate absence of the optional library.
5. **Extract top-level config:** Extract the nested class into a separate configuration class with equivalent conditions and intentional import. Compare how metadata, code, and verification are managed.
6. **Missing imports:** In an experimental branch, temporarily remove `AutoConfiguration.imports`. Compare `ApplicationContextRunner` tests with `demo-app` to distinguish condition logic from JAR discovery.

When experimenting, change only one factor at a time. Before running, write down a **prediction**, then record the **output**, **root cause**, and **conclusion** from the evidence.

## 15. Common Misconceptions

**"Putting @ConditionalOnClass on any method is safe."** False. A method whose return type belongs to an absent dependency can be analyzed before the method condition is processed. The nested-configuration isolation pattern is safer.

**"Using name instead of value eliminates class-loading errors."** Not necessarily. `name` avoids referencing a class literal inside the annotation, yet does not remove method/field signatures referencing the optional type on a class that must be loaded.

**"The nested class must be listed in AutoConfiguration.imports."** Not in this lesson's pattern. Only the outer auto-configuration needs registration; Spring processes nested `@Configuration` classes inside its structure.

**"compileOnly guarantees no consumer has optional-api."** False. It only prevents that dependency from being carried into runtime by the autoconfigure module under normal configurations. The consumer or another library can still add `optional-api`.

**"Having the optional class guarantees the bean exists."** False. Bean conditions, properties, exclusions, and runtime errors still decide.

**"A static nested class is an auto-created bean."** No. It is a configuration class Spring can process; the `@Bean` methods and conditions inside it determine which business beans are registered.

**"Auto-configuration can download missing dependencies itself."** No. Dependency resolution happens at build/runtime packaging; Spring Boot conditions decide based on the existing classpath and do not download JARs from Maven Central at startup.

**"Lightweight context tests prove the real JAR works."** Insufficient. You must check imports and run a consuming app that auto-discovers the configuration.

**"Class existence means API compatibility."** False. Different versions can share the same class name yet differ in methods/constructors; verify which versions the library supports.

## 16. Completion Checklist

- [ ] Can explain the issue of method signatures referencing an absent class before method conditions apply.
- [ ] Can distinguish `@ConditionalOnClass` at configuration class level vs. `@Bean` method level.
- [ ] Can write a static nested **@Configuration(proxyBeanMethods = false)** with **@ConditionalOnClass**.
- [ ] Keep core beans in the outer class and optional beans in the nested class.
- [ ] Use **@ConditionalOnMissingBean** to back off in favor of user beans when the integration is present.
- [ ] Understand why the autoconfigure module uses **compileOnly** for optional APIs.
- [ ] Pass context tests both when the optional dependency is present and when hidden via `FilteredClassLoader`.
- [ ] Pass back-off tests when the application defines its own bean.
- [ ] Verify in `demo-app` that without `optional-api`, the core bean exists and the optional bean does not.
- [ ] Add `optional-api` at runtime and verify the optional bean is created.
- [ ] Inspect the JAR and outer class FQCN inside `AutoConfiguration.imports`.
- [ ] Use dependency graphs and the Condition Evaluation Report to distinguish classpath, discovery, and bean condition issues.

## Conclusion

**Isolating configuration for optional dependencies with nested configuration classes** is a crucial technique when writing Spring Boot auto-configuration for reusable libraries. Place **@ConditionalOnClass** at the **static nested @Configuration** level, keep `@Bean` methods with signatures depending on optional types inside that class, and use **@ConditionalOnMissingBean** so applications can override defaults.

As a result, applications without the optional library can still boot and use core functionality, while applications with that library receive additional beans when conditions match. Complete evidence includes **classloader tests hiding the dependency**, **tests with the dependency present**, **custom bean tests**, **consumer `runtimeClasspath`**, and **the imports resource inside the JAR**.

## References

- [Spring Boot — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/reference/features/developing-auto-configuration.html)
- [Spring Boot — ConditionalOnClass API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
