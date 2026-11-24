# @ConditionalOnClass: Checking for the Presence of Required Types

## 1. Why Does Auto-Configuration Need to Check the Classpath?

A Spring Boot application may add multiple starters without necessarily enabling every integration. For example, an auto-configuration library for JSON needs to know whether the Jackson API is on the classpath; a configuration library for JDBC needs to know whether the corresponding JDBC classes are present. If auto-configuration attempts to create a bean that depends on a library that is **not installed**, the application can encounter class loading or bean creation errors right at startup.

**@ConditionalOnClass** is a condition provided by Spring Boot to check for **the presence of required Java types** before allowing a configuration class or bean-creation method to be processed.

For example:

~~~java
@ConditionalOnClass(name = "com.fasterxml.jackson.databind.ObjectMapper")
~~~

This annotation snippet means: the annotated component is only considered a match when Spring can find the class **com.fasterxml.jackson.databind.ObjectMapper** on the classpath used by the framework.

It does not mean there is already an **ObjectMapper bean**, does not promise that the class will work with every library version, and does not automatically add Jackson to the dependency graph.

### Learning Objectives

After this lesson, you will be able to:

1. Correctly read **@ConditionalOnClass(value = ...)** and **@ConditionalOnClass(name = ...)**.
2. Explain why multiple required types in the same annotation must be **simultaneously present**.
3. Distinguish between **class present**, **bean present**, **dependency declared**, **dependency resolved**, and **API compatibility**.
4. Understand the difference between placing the condition on an **@AutoConfiguration class** versus an **@Bean method**.
5. Isolate references to optional APIs into a nested **@Configuration** to avoid premature type introspection.
6. Use **ApplicationContextRunner** and **FilteredClassLoader** to test when a class is present/absent.
7. Verify **AutoConfiguration.imports**, the JAR, and **runtimeClasspath** in a consuming application.
8. Diagnose why a condition does not match without confusing it with a bean creation failure.

The practical examples use **Java 21, Gradle 8.x, and Spring Boot 3.3.13** as a fixed version set for the lesson, **not** as a claim that these are the latest versions.

## 2. Concept: Checking Whether a Java Type Can Be Found

The **classpath** is the set of paths to classes, JARs, and resources accessible to the JVM/classloader. Depending on build configuration, test and runtime may have different classpaths.

With:

~~~java
@ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
~~~

Spring Boot essentially asks: **“Can the context's appropriate ClassLoader find the requested class?”**.

| Scenario | Classpath condition | Correct conclusion |
| --- | --- | --- |
| The optional-api JAR has the **OptionalCodec** class in runtimeClasspath | Usually matches | Processing of the guarded configuration can proceed. |
| Declared optional-api only in **testImplementation**, production app lacks the JAR | Does not match in production | Should not create beans requiring OptionalCodec. |
| Source code in another project has OptionalCodec, but it is not on the app's classpath | Does not match | Source existence does not mean the runtime sees the class. |
| Class is on the classpath, but no bean is registered yet | Can still match | A class condition is different from a bean condition. |
| A class with the same name exists, but the API changed incompatibly | Can match | The condition only checks presence, not that required methods/constructors are compatible. |

### 2.1. Having a Class Does Not Mean Having a Bean

The following two snippets ask **two different questions**:

~~~java
@ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
~~~

~~~java
@ConditionalOnBean(OptionalCodec.class)
~~~

The second snippet is just an annotation example that **requires the OptionalCodec class on the compile classpath** and has a different meaning: whether an **OptionalCodec** bean already exists in the Spring context according to the condition's semantics. If the goal is to enable the library when the **JAR** is installed, **@ConditionalOnClass** is the right tool. If you want configuration to depend on an already **registered bean**, use a bean condition and consider configuration processing order.

**Do not write @ConditionalOnBean instead of @ConditionalOnClass** just because the names look similar. Having a class does not mean having a bean; having a matching bean also depends on the bean definition registration progress.

### 2.2. Which Classpath Is Checked?

When running **gradle test**, dependencies from **testImplementation** can appear and make the classpath condition match. When running **gradle bootRun**, the application's runtimeClasspath might lack that dependency, so the condition does not match.

Do not conclude based solely on the fact that the IDE can import a type. You must inspect the **actual runtimeClasspath**, especially when using **compileOnly**, **runtimeOnly**, multi-module setups, or transitive dependencies.

## 3. Exact Syntax of @ConditionalOnClass

Spring Boot provides the annotation:

~~~text
org.springframework.boot.autoconfigure.condition.ConditionalOnClass
~~~

Two core attributes:

- **value**: an array of **Class<?>** that must be present.
- **name**: an array of **fully qualified class names** (**FQCN**) as Strings that must be present.

Common usages:

~~~java
@ConditionalOnClass(ObjectMapper.class)
~~~

~~~java
@ConditionalOnClass(value = {ObjectMapper.class, JsonNode.class})
~~~

~~~java
@ConditionalOnClass(
    name = "com.fasterxml.jackson.databind.ObjectMapper"
)
~~~

~~~java
@ConditionalOnClass(
    name = {
        "com.fasterxml.jackson.databind.ObjectMapper",
        "com.fasterxml.jackson.databind.JsonNode"
    }
)
~~~

These are **illustrative annotation snippets**, not standalone runnable Java files. Examples using class literals **ObjectMapper** and **JsonNode** require the compiled module to see those classes; the **name** form does not need to import them to write the annotation.

### 3.1. value Is a Class Literal, Not a .class Filename

In the code:

~~~java
@ConditionalOnClass(com.fasterxml.jackson.databind.ObjectMapper.class)
~~~

**.class** here is Java syntax for a **class literal**. It differs from a line in the **AutoConfiguration.imports** file, where you must write the **FQCN** without **.class**.

On annotations, the syntax **@ConditionalOnClass(ObjectMapper.class)** is commonly used if there is an import:

~~~java
import com.fasterxml.jackson.databind.ObjectMapper;
~~~

### 3.2. name Is the Exact FQCN

For example:

~~~java
@ConditionalOnClass(
    name = "com.fasterxml.jackson.databind.ObjectMapper"
)
~~~

Do not use **ObjectMapper**, **com.fasterxml.jackson.databind.\***, **ObjectMapper.class** as a string, or a Maven artifact coordinate like **com.fasterxml.jackson.core:jackson-databind**. These values are not fully qualified class names for the framework to look up.

**name** is convenient when the optional library is **not on the compile classpath**, or when creating a composed annotation that needs to avoid class literals.

### 3.3. Multiple Classes Default to AND

Suppose:

~~~java
@ConditionalOnClass(
    name = {
        "com.example.api.Alpha",
        "com.example.api.Beta"
    }
)
~~~

The condition only matches when **both Alpha and Beta** are present. If either class is missing, the result does not match.

| Alpha | Beta | @ConditionalOnClass matches? |
| --- | --- | --- |
| Present | Present | **Yes** |
| Present | Absent | No |
| Absent | Present | No |
| Absent | Absent | No |

This is an **AND** operation, not an OR operation. Likewise, if requirements are declared in both **value** and **name** at the same time, all declared requirements must be satisfied.

### 3.4. What If You Want “A or B”?

You cannot write two values in the same **@ConditionalOnClass** and expect “only one is needed”. When an integration has two interchangeable backends, you can **split them into two separately guarded configurations**, or write a composite condition with OR logic when genuinely needed.

Do not try to turn AND into OR by turning **@ConditionalOnClass** into multiple commented lines, or declaring an imaginary “or” property. Conditional logic must be expressed explicitly.

## 4. Class-Level vs. @Bean Method-Level Conditions

**@ConditionalOnClass** can guard an auto-configuration class:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
public class OptionalCodecAutoConfiguration {
    // @Bean methods are only considered when the configuration class matches.
}
~~~

When the **OptionalCodec** class does not exist, **OptionalCodecAutoConfiguration** is not used to register its beans.

With a condition on a bean method:

~~~java
@Bean
@ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
public String optionalFeatureLabel() {
    return "optional";
}
~~~

In this case the method only returns **String**, with no optional type reference in its signature. Placing the condition on the method can be appropriate when you only want to block **a single bean** rather than the entire class.

### 4.1. An Important Risk When @Bean Returns an Optional Type

A **risky** way to write it:

~~~java
@Bean
@ConditionalOnClass(OptionalCodec.class)
OptionalCodec optionalCodec() {
    return new OptionalCodec();
}
~~~

This is an illustrative snippet to avoid in a configuration class that gets processed even when OptionalCodec is absent. **The return type of the method** already references OptionalCodec. Spring/the JVM may need to introspect the signature **before the method condition can be properly applied**, causing the missing class to trigger an error.

Spring Boot documentation recommends **isolating such methods in a separate configuration class**, typically a static nested class, and placing **@ConditionalOnClass at the class level**.

### 4.2. Safer Nested @Configuration Pattern

~~~java
@AutoConfiguration
public class ExampleAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
    static class OptionalCodecConfiguration {

        @Bean
        OptionalCodec optionalCodec() {
            return new OptionalCodec();
        }
    }
}
~~~

This is a **sample snippet**, not yet including package/imports or bean overrides. The nested class keeps the method signature depending on OptionalCodec inside a class that only needs to be processed when the class-level condition passes.

**static** ensures the nested class does not require an instance of the outer class. **proxyBeanMethods=false** is suitable when @Bean methods do not need to call each other to obtain beans through a proxy.

Placing **@ConditionalOnClass** on a nested configuration allows Spring to use annotation metadata to discard invalid branches before deeply processing method signatures. This is a key pattern in auto-configuration libraries serving optional dependencies.

## 5. Why Can @ConditionalOnClass Check Without Loading Classes Too Early?

Spring Boot documentation states that a configuration class's annotation metadata can be processed using **ASM**, so **@ConditionalOnClass** placed directly on a class can be inspected without having to load the annotated class in a way that forces all bean method types to be resolved beforehand.

Benefits:

- Does not force the runtime to have the **entire optional integration** just to evaluate a condition.
- Guards each configuration branch within the library.
- Helps the framework eliminate non-matching candidates and reduce unnecessary configuration processing.
- Allows core features to keep working when optional dependencies are absent.

However:

- **@ConditionalOnClass** does not automatically fix an outer configuration that has static initializers, fields, superclasses, or other signatures referencing the optional class.
- A class that is present can still encounter **NoSuchMethodError/NoClassDefFoundError** at runtime if the binary API is incompatible or a required transitive dependency is missing.
- Metadata processing and class loading belong to the framework/JVM; do not guess “which classes have definitely never been loaded” from ordinary logs alone.

### 5.1. Composed Annotations Should Use name

When **@ConditionalOnClass** is used as a meta-annotation in a custom composite annotation created by a library author, Spring Boot documentation notes that you should use **name** instead of a class literal. For example:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
public @interface ConditionalOnOptionalCodec {
}
~~~

This is an **illustrative Java annotation snippet**, requiring imports for **java.lang.annotation.Target**, **ElementType**, **Retention**, **RetentionPolicy**, and the **ConditionalOnClass** type. For a complete annotation, you can add **@Documented** when you want the annotation to appear in JavaDoc.

Do not misunderstand **name** as making the condition “stronger”. In terms of class presence semantics, value/name both express the existence requirement. The difference lies in how the name is provided and how metadata/class literals are handled.

## 6. Hands-On Example: A Class Truly Present or Absent

We create three modules:

~~~text
classpath-condition-lab/
├── settings.gradle
├── build.gradle
├── optional-api/
│   ├── build.gradle
│   └── src/main/java/com/example/optionalapi/OptionalCodec.java
├── optional-autoconfigure/
│   ├── build.gradle
│   ├── src/main/java/com/example/autoconfigure/
│   │   ├── BaseMarker.java
│   │   └── CodecAutoConfiguration.java
│   ├── src/main/resources/META-INF/spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── src/test/java/com/example/autoconfigure/
│       └── CodecAutoConfigurationTests.java
└── demo-app/
    ├── build.gradle
    └── src/main/java/com/example/demo/
        └── DemoApplication.java
~~~

In this design:

1. **optional-api** contains the **OptionalCodec** class without depending on Spring.
2. **optional-autoconfigure** defines a foundational **BaseMarker** bean, and **a nested configuration branch** that only creates OptionalCodec if optional-api is present.
3. **demo-app** initially depends only on the auto-configuration and Spring Boot starter; afterwards it explicitly adds optional-api at runtime to observe the different outcome.

The key point is that the dependency on optional-api must be **compileOnly** in the autoconfigure module. If **implementation** were used, consumers would normally receive optional-api transitively and the missing-class experiment would no longer be valid.

### 6.1. The settings.gradle File

~~~groovy
rootProject.name = 'classpath-condition-lab'
include 'optional-api', 'optional-autoconfigure', 'demo-app'
~~~

### 6.2. The Root build.gradle File

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

The root unifies the toolchain and versions for all three modules. The Spring Boot plugin is declared **apply false** at the root and will be applied in demo-app. The two library modules use regular Java JARs.

### 6.3. optional-api/build.gradle

~~~groovy
plugins {
    id 'java-library'
}
~~~

### 6.4. optional-autoconfigure/build.gradle

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

**compileOnly** allows writing **OptionalCodec.class**, calling its constructor, and compiling method signatures without **including this dependency at runtime** in another project merely because it added the auto-configuration module.

**testImplementation** makes the OptionalCodec class appear on the regular test classpath; tests for missing classes use **FilteredClassLoader** to simulate the case where the optional dependency is not visible.

### 6.5. demo-app/build.gradle

~~~groovy
plugins {
    id 'org.springframework.boot'
}

dependencies {
    implementation project(':optional-autoconfigure')
    implementation 'org.springframework.boot:spring-boot-starter'
}
~~~

There is no **optional-api** dependency on the application's runtimeClasspath yet.

## 7. Complete Java Classes

### 7.1. Optional API: OptionalCodec.java

File **optional-api/src/main/java/com/example/optionalapi/OptionalCodec.java**:

~~~java
package com.example.optionalapi;

public final class OptionalCodec {

    public String encode(String text) {
        return "encoded:" + text;
    }
}
~~~

This class has no Spring annotations; it is an external library type that auto-configuration will check for.

### 7.2. Foundational Type: BaseMarker.java

File **optional-autoconfigure/src/main/java/com/example/autoconfigure/BaseMarker.java**:

~~~java
package com.example.autoconfigure;

public record BaseMarker(String value) {
}
~~~

BaseMarker does not reference OptionalCodec, so it can be created even when optional-api is absent.

### 7.3. Auto-Configuration with Nested Condition: CodecAutoConfiguration.java

File **optional-autoconfigure/src/main/java/com/example/autoconfigure/CodecAutoConfiguration.java**:

~~~java
package com.example.autoconfigure;

import com.example.optionalapi.OptionalCodec;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@AutoConfiguration
public class CodecAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(BaseMarker.class)
    public BaseMarker baseMarker() {
        return new BaseMarker("core");
    }

    @Configuration(proxyBeanMethods = false)
    @ConditionalOnClass(OptionalCodec.class)
    static class OptionalCodecConfiguration {

        @Bean
        @ConditionalOnMissingBean(OptionalCodec.class)
        OptionalCodec optionalCodec() {
            return new OptionalCodec();
        }
    }
}
~~~

**Breakdown:**

- **@AutoConfiguration**: the outer class is a candidate discovered by Spring Boot.
- **@Bean BaseMarker**: provides the core bean when the application has not declared one.
- **@Configuration(proxyBeanMethods=false)**: the nested class is a separate configuration with the required bean method.
- **@ConditionalOnClass(OptionalCodec.class)**: only enables the nested branch when OptionalCodec is found at runtime.
- **@ConditionalOnMissingBean(OptionalCodec.class)**: the application takes precedence if it has already registered its own OptionalCodec bean.

**Why not put OptionalCodec in a method signature of the outer class?** Because the outer class must work even when optional-api is absent. A nested configuration serves as a boundary to avoid introspecting methods that depend on optional types when the JAR is missing.

### 7.4. Registering the Candidate via AutoConfiguration.imports

File **optional-autoconfigure/src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports**:

~~~text
com.example.autoconfigure.CodecAutoConfiguration
~~~

List only the **outer** auto-configuration class; do not add **CodecAutoConfiguration$OptionalCodecConfiguration** to the imports file. Spring processes nested configurations according to its configuration class mechanism.

Place the file strictly in **src/main/resources**. If accidentally placed in **src/test/resources**, tests might see it, but a consumer running from the main JAR will not auto-discover it.

## 8. Testing @ConditionalOnClass with ApplicationContextRunner

Use **ApplicationContextRunner** to create lightweight contexts to verify:

1. OptionalCodec class present → both core and default optional beans exist.
2. OptionalCodec class hidden → only the core bean exists, and the context starts normally.
3. OptionalCodec class present, but the application defines its own bean → auto-configuration **backs off**.
4. Another required class hidden in a multi-class condition → the guarded branch does not match.

In this lesson, the first three tests verify the whole project. The fourth case is explained with an additional class so we do not mix too many configurations into the demo.

### 8.1. The CodecAutoConfigurationTests.java File

File **optional-autoconfigure/src/test/java/com/example/autoconfigure/CodecAutoConfigurationTests.java**:

~~~java
package com.example.autoconfigure;

import com.example.optionalapi.OptionalCodec;
import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.FilteredClassLoader;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class CodecAutoConfigurationTests {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(CodecAutoConfiguration.class)
            );

    @Test
    void createsOptionalBeanWhenClassPresent() {
        runner.run(context -> {
            assertThat(context).hasSingleBean(BaseMarker.class);
            assertThat(context).hasSingleBean(OptionalCodec.class);
            assertThat(context.getBean(OptionalCodec.class).encode("An"))
                .isEqualTo("encoded:An");
        });
    }

    @Test
    void skipsOptionalBeanWhenClassAbsent() {
        runner.withClassLoader(
            new FilteredClassLoader("com.example.optionalapi")
        ).run(context -> {
            assertThat(context).hasSingleBean(BaseMarker.class);
            assertThat(context.containsBean("optionalCodec")).isFalse();
            assertThat(context.getBean(BaseMarker.class).value())
                .isEqualTo("core");
        });
    }

    @Test
    void backsOffWhenApplicationSuppliesBean() {
        runner.withUserConfiguration(UserCodecConfiguration.class)
            .run(context -> {
                assertThat(context).hasSingleBean(OptionalCodec.class);
                assertThat(context.containsBean("optionalCodec")).isFalse();
                assertThat(context.containsBean("customCodec")).isTrue();
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class UserCodecConfiguration {

        @Bean
        OptionalCodec customCodec() {
            return new OptionalCodec();
        }
    }
}
~~~

**Key point about the missing-dependency test:** In the **FilteredClassLoader** branch, the test does not call **getBean(OptionalCodec.class)** because doing so directly references the type being simulated as missing. Instead, the test checks by **bean name**. Spring can read the nested class metadata and skip it without trying to create the OptionalCodec bean.

**Key point about the back-off test:** The classpath condition matched, but **@ConditionalOnMissingBean** sees the **customCodec** bean. Therefore **only one bean** exists. This does not negate the **@ConditionalOnClass** result; it simply demonstrates an additional required condition.

### 8.2. Running Tests with Gradle

~~~bash
gradle :optional-autoconfigure:test
~~~

Or with the Gradle Wrapper, if generated:

~~~bash
./gradlew :optional-autoconfigure:test
~~~

On Windows PowerShell: **.\gradlew.bat :optional-autoconfigure:test**.

When tests pass, Gradle reports the task as successful; console logging depends on machine configuration. There is no single fixed stdout to memorize.

### 8.3. Direct Tests Do Not Replace Discovery Verification

**AutoConfigurations.of(CodecAutoConfiguration.class)** passes the configuration class directly into the context runner. This tests **conditional logic**, but **does not prove** the class is auto-discovered via the **AutoConfiguration.imports** resource in the published JAR.

A complete project needs a consumer application and artifact inspection, as shown in the next two sections.

## 9. Running the Consuming Application in Two Classpath States

File **demo-app/src/main/java/com/example/demo/DemoApplication.java**:

~~~java
package com.example.demo;

import com.example.autoconfigure.BaseMarker;
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
    ApplicationRunner inspect(ApplicationContext context) {
        return args -> {
            System.out.println(
                "BaseMarker present: " +
                !context.getBeansOfType(BaseMarker.class).isEmpty()
            );
            System.out.println(
                "OptionalCodec bean present: " +
                context.containsBean("optionalCodec")
            );
        };
    }
}
~~~

The application is in the **com.example.demo** package, separate from the **com.example.autoconfigure** configuration package. The default component scan of **@SpringBootApplication** does not scan the library in this package. Therefore the **CodecAutoConfiguration** class is only applied thanks to auto-configuration discovery via imports.

### 9.1. When optional-api Is Absent

Keep **demo-app/build.gradle** as in section 6.5 and run:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
gradle :demo-app:bootRun
~~~

Checking the dependency tree shows that **optional-api** is not a resolved runtime dependency of demo-app. The two lines printed by ApplicationRunner are expected to be:

~~~text
BaseMarker present: true
OptionalCodec bean present: false
~~~

Spring Boot logs may surround the lines above. The important result is that **the application starts normally**, BaseMarker is present, and OptionalCodec is not created. If optional-api still appears in the dependency tree, look for a transitive dependency rather than concluding that **@ConditionalOnClass** is broken.

### 9.2. When optional-api Is Present

Add the following **single line** to the dependencies block of **demo-app/build.gradle**:

~~~groovy
runtimeOnly project(':optional-api')
~~~

Run again:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
gradle :demo-app:bootRun
~~~

Expected two lines:

~~~text
BaseMarker present: true
OptionalCodec bean present: true
~~~

This difference comes from the **classpath**, not from Spring Boot dynamically downloading dependencies. The dependency was placed on the runtime classpath by Gradle at startup.

### 9.3. Nature of the @ConditionalOnClass Condition

~~~text
Is OptionalCodec on classpath?
            |
      +-----+-----+
      |           |
      No         Yes
      |           |
      v           v
Skip nested       Also evaluate
configuration     @ConditionalOnMissingBean
                        |
                 +------+------+
                 |             |
            Bean exists   No bean yet
                 |             |
                 v             v
              Back off      Create bean
              default      OptionalCodec
~~~

**Do not infer** from this diagram that every class/configuration in Spring Boot must pass through these exact steps in a simple loop. This is the logical model of the auto-configuration pattern being introduced.

## 10. Multiple Required Types: Checking All, Not Just One

Sometimes an integration needs **two different APIs**:

~~~java
@ConditionalOnClass(
    name = {
        "com.example.optionalapi.OptionalCodec",
        "com.example.metrics.Meter"
    }
)
~~~

If OptionalCodec is present but Meter is missing, the configuration still **does not match**. The condition requires both.

**Truth table:**

| OptionalCodec | Meter | Result |
| --- | --- | --- |
| Present | Present | Match |
| Present | Absent | No match |
| Absent | Present | No match |
| Absent | Absent | No match |

If two libraries are interchangeable, do not combine them in a single **@ConditionalOnClass**. Create two configuration classes with independent conditions, each registering a corresponding implementation; if true OR is needed, design a composite condition and test the case where **both are present** to avoid conflicting bean registrations.

### 10.1. Combining @ConditionalOnClass with Other Conditions

For example:

~~~java
@AutoConfiguration
@ConditionalOnClass(name = "com.example.optionalapi.OptionalCodec")
@ConditionalOnProperty(
    prefix = "example.codec",
    name = "enabled",
    havingValue = "true"
)
public class CodecFeatureAutoConfiguration {
}
~~~

The snippet above illustrates that **both conditions must be satisfied**: the OptionalCodec class is present **and** the property **example.codec.enabled=true** is set. Even if the class is present, when the feature is disabled the configuration still does not apply.

In the hands-on lab, **@ConditionalOnMissingBean** on the @Bean method is also an additional condition. **@ConditionalOnClass** does not take absolute precedence to bypass other conditions.

## 11. Inspecting the JAR and Registration Resource

Run:

~~~bash
gradle :optional-autoconfigure:jar
~~~

With version **1.0.0** at the root:

~~~text
optional-autoconfigure/build/libs/optional-autoconfigure-1.0.0.jar
~~~

List contents:

~~~bash
jar tf optional-autoconfigure/build/libs/optional-autoconfigure-1.0.0.jar
~~~

Look for:

~~~text
com/example/autoconfigure/BaseMarker.class
com/example/autoconfigure/CodecAutoConfiguration.class
com/example/autoconfigure/CodecAutoConfiguration$OptionalCodecConfiguration.class
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

Only the **outer class** is listed in imports:

~~~text
com.example.autoconfigure.CodecAutoConfiguration
~~~

Even though OptionalCodec is **not inside the autoconfigure JAR**, the nested configuration's class bytecode can still be packaged because it was compiled against optional-api as **compileOnly**. Spring simply needs to avoid trying to process that branch when the dependency is missing at runtime.

To read the contents of imports from the JAR (when unzip is available):

~~~bash
unzip -p optional-autoconfigure/build/libs/optional-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

If **unzip** is unavailable, use an equivalent ZIP/JAR inspection tool. Cross-check the FQCN against the compiled package/class to rule out resource naming errors.

## 12. Diagnosing When @ConditionalOnClass Behaves Unexpectedly

### 12.1. Class Is Definitely in Source, but Condition Does Not Match

Inspect **runtimeClasspath**, not just source:

~~~bash
gradle :demo-app:dependencies --configuration runtimeClasspath
gradle :demo-app:dependencyInsight --configuration runtimeClasspath --dependency optional-api
~~~

In the sample project, optional-api was initially only **compileOnly** in the library, so it **does not propagate** to the app runtime. Only after adding **runtimeOnly project(':optional-api')** does the class become available at runtime.

You should also check the context's **ClassLoader**, especially when there is a plugin architecture, custom classloader, or test isolation.

### 12.2. Class Is Present, but No Bean Is Created

That may be the expected behavior. Check **@ConditionalOnMissingBean**, **@ConditionalOnProperty**, or other conditions. If the application already has a bean of the same type, auto-config normally backs off; this is not because @ConditionalOnClass is wrong.

Enable diagnostic output when running the application:

~~~bash
gradle :demo-app:bootRun --args='--debug'
~~~

Read the **Condition Evaluation Report** to find non-matching branches. Displayed details may vary by version and the point at which a candidate is excluded; do not treat the absence of a specific log line as the sole proof.

### 12.3. NoClassDefFoundError Occurs Despite Having the Condition

Identify which class throws the error. If an @Bean method in the outer class has a return type/parameter belonging to optional-api, a method-level condition may fail to guard signature introspection. Move that method group into a nested **@Configuration** with **@ConditionalOnClass** at the class level.

In addition, review superclasses, interfaces, fields, static initializers, or constructors that directly require the optional class. **@ConditionalOnClass does not replace proper dependency boundary design**.

### 12.4. Condition Matches, but Runtime Still Throws NoSuchMethodError

Class existence does not mean version compatibility. An application might install a different OptionalCodec version with the same FQCN, where the **encode(String)** method was removed or had its signature changed. **@ConditionalOnClass** may match and bean creation or invocation can still fail.

Check the selected dependency version with **dependencyInsight**, verify the supported API, and use integration tests across important versions. Do not treat classpath conditions as complete binary compatibility validation.

### 12.5. Annotation value vs. name Does Not Yield Expected Results

Check whether the class literal belongs to **compileOnly** and is required in a method signature on an unguarded class. On regular class-level annotations, Spring Boot supports reading metadata to check class literals, whereas in **meta-annotations** you should use **name** as guided by the documentation.

Do not use **name="OptionalCodec"** without a package. Also do not use the string **"com.example.optionalapi.OptionalCodec.class"** because the **.class** suffix is not part of the FQCN.

### 12.6. Tests Pass, but Consuming Application Does Not Pick Up Configuration

**ApplicationContextRunner** with **AutoConfigurations.of** directly imports known configuration classes. It does not prove the imports file is discovered from the JAR. Verify **src/main/resources**, the JAR contents, and the consumer's classpath.

Separate three steps when diagnosing:

1. **Discovery**: is the auto-configuration class found as a candidate?
2. **Condition**: are the required classes present and do other bean conditions match?
3. **Creation**: does Spring create the bean with the expected type/name and valid dependencies?

## 13. Common Misconceptions

**Myth 1: “Having @ConditionalOnClass means Spring has already registered that class as a bean.”** No. This is a check for the presence of a **Java type**, not the existence of a bean.

**Myth 2: “In the value list, only one class needs to be present.”** No. All listed types must be present.

**Myth 3: “When a class is missing, Spring Boot downloads the JAR automatically.”** No. Dependency resolution is determined by build/deployment. The condition only reads the existing classpath.

**Myth 4: “Using name in @ConditionalOnClass eliminates any need for isolation.”** No. Even if the annotation uses a string, method signatures or fields in a loaded class can still reference the missing optional type.

**Myth 5: “Putting @ConditionalOnClass on an @Bean returning an optional type is always safe.”** No. Method signature introspection can happen before the method condition skips the bean. Use a nested configuration with a class-level condition.

**Myth 6: “Class presence means a valid API/version.”** No. Class existence does not guarantee compatible methods, transitive dependencies, or required native resources are present.

**Myth 7: “Just add @ComponentScan to find auto-configuration.”** Incorrect for how Boot 3.x libraries publish auto-configuration; use **AutoConfiguration.imports**.

**Myth 8: “I added testImplementation, so the runtime app has the class.”** No. You must inspect the app's runtimeClasspath or deployed artifact.

**Myth 9: “Importing a class means the bean is guaranteed to be created.”** No. Other bean conditions can still back off, properties might not match, or bean creation can fail.

**Myth 10: “Direct AutoConfigurations.of unit tests are enough to prove the published JAR is valid.”** No. Consumer tests and JAR resource inspection are also required.

## 14. Practice Exercises

1. **Predict two classes:** Given **@ConditionalOnClass(name={"com.example.A","com.example.B"})**, build a truth table as A/B are present or absent. Explain why only one class being present is not enough.
2. **Using value and name:** Compile one configuration using class literals in **value**, and one using FQCNs in **name**. Ensure both express the same presence condition in a valid context; explain the compile dependency difference.
3. **Misplacing the condition:** On an experimental branch, move the OptionalCodec factory method to the outer class and guard only the method with **@ConditionalOnClass**. Observe the missing-class classloader test and explain the risk.
4. **Add a property:** Place **@ConditionalOnProperty(prefix="example.codec",name="enabled",havingValue="true")** on the nested config. Test class present/property false, class absent/property true, and both true.
5. **Custom bean back-off:** Create an OptionalCodec bean from the app and confirm that auto-config does not register the default bean of the same type.
6. **Version mismatch:** Simulate OptionalCodec still existing while a method changes in a new version; explain why the condition matches yet invocation fails. Inspect the selected dependency version.
7. **JAR inspection:** Temporarily remove imports on a separate branch, keeping code and the test runner. Compare direct unit tests with demo-app to understand discovery failures.
8. **No optional-api at runtime:** Read the Gradle dependency tree to prove **compileOnly** does not pull the dependency into the consumer; then add **runtimeOnly** and verify.
9. **Design two alternative backends:** Create two nested configurations, one requiring CodecA and one requiring CodecB. Write tests for A-only, B-only, both, and neither. Clearly specify the precedence mechanism to avoid two beans of the same type when both are installed.

## 15. Lesson Completion Checklist

- [ ] Can explain that **@ConditionalOnClass** checks **classes**, not beans.
- [ ] Can distinguish **value** and **name** in the annotation, using exact FQCNs with name.
- [ ] Know that multiple specified classes must **all be present** to match.
- [ ] Understand that a class-level condition blocks the entire configuration, while a method condition only blocks one bean method.
- [ ] Understand why an @Bean method returning an optional type may need a separate nested configuration.
- [ ] Know how to use **@Configuration(proxyBeanMethods=false)** and **@ConditionalOnClass** on a nested class.
- [ ] Can create a Java 21/Gradle multi-module sample with **compileOnly optional-api**.
- [ ] Can run **ApplicationContextRunner** with **FilteredClassLoader** to simulate missing classes.
- [ ] Can write a test where a custom bean causes **@ConditionalOnMissingBean** to back off.
- [ ] Can run demo-app both when optional-api is absent and when it is present.
- [ ] Can inspect **AutoConfiguration.imports** and compiled bytecode classes inside the JAR.
- [ ] Can read runtimeClasspath and the Condition Evaluation Report for diagnostics.
- [ ] Do not confuse class presence with API compatibility or bean presence.

## Conclusion

**@ConditionalOnClass** lets Spring Boot apply auto-configuration only when **all required Java types are present on the classpath**. It is a dependency/classpath condition, **not** a check for bean existence. With **value**, declare class literals; with **name**, declare string FQCNs. If multiple classes are required, **all of them must be present**.

When optional APIs appear in an **@Bean** method signature, isolate that method inside a **static nested @Configuration** guarded by **@ConditionalOnClass at the class level**. Test with a dependency-excluding classloader, context runner, and real consuming app; also inspect the JAR/AutoConfiguration.imports and dependency graph to distinguish discovery, condition, and bean creation issues.

## References

- [Spring Boot 3.3 — Developing Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html)
- [ConditionalOnClass — Spring Boot 3.3 API](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/condition/ConditionalOnClass.html)
