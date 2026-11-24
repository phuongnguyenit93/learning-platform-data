# Verifying Auto-Configuration Libraries on JVM and Native Within Supported Scope

## 1. Goal: Test the Library Inside an Application That Actually Consumes It

A Spring Boot auto-configuration library may run fine on the JVM yet fail when an application is AOT-processed or compiled into a GraalVM Native Image. The root cause usually lies in differences between the JVM runtime and native environments: the classpath is fixed at build time, some reflection operations need runtime hints, classpath resources may not be packaged unless declared, and bean-deciding conditions are evaluated during AOT.

Therefore, native verification is not merely re-running unit tests with a different build flag. You must prove that the library is discovered from its distributed artifact, auto-configuration applies in the right environment, AOT can process the consuming application's context, required runtime hints are generated, and the native executable delivers the behavior the library publishes.

This lesson uses **Spring Boot 3.3.13, Spring Framework 6.1.21, Java 17+, and Maven**. Scope includes:

1. Testing auto-configuration and bean conditions on the JVM.
2. Testing the contents of RuntimeHints registered by the library.
3. Creating a separate consumer project to test the packaged library JAR.
4. Running Spring AOT processing and verifying the generated application on the JVM.
5. Compiling and running the native executable.
6. Running native integration tests via Native Build Tools.
7. Precisely defining the versions, dependencies, operating systems, and architectures the library claims to support.

**Principle:** unit tests on the JVM test most behavior; consumer integration tests verify how the library is used; AOT/native tests focus on areas that can differ when running native. Do not declare "native supported" solely because code compiles or JVM unit tests pass.

## 2. Distinguishing Three Testing Environments

| Environment | How to Run | Evidence Obtained | Limitations |
| --- | --- | --- | --- |
| Standard JVM | `mvn test`, `ApplicationContextRunner`, `@SpringBootTest` | Auto-configuration conditions, default/override beans, binding, service logic | Does not prove AOT code or native reachability |
| JVM using AOT-generated code | Build with AOT, run `java -Dspring.aot.enabled=true -jar ...` | Generated initialization code can start and run on the JVM | Does not replace GraalVM native compilation/runtime |
| Native Image | Compile with GraalVM/Native Build Tools, run binary or native tests | Reachability, reflection/resource hints, startup and behavior in native executable | Confirms only the tested combination of versions, dependencies, OS/architecture |

Spring Boot recommends continuing to use the JVM for developing most unit and integration tests due to fast build times and strong IDE support. Native testing should focus on native-specific differences, such as AOT processing, reflection, resources, proxies, and serialization.

### 2.1. Why Must There Be a Consumer Application?

An auto-configuration library is an artifact brought into another application's dependency graph. The library itself does not determine all of:

- Main application class and component scanning.
- Actual dependencies present on the runtime classpath.
- Application property sources and profiles.
- User-defined beans that cause auto-configurations to back off.
- Which conditions match when Spring AOT prepares the BeanFactory.
- Which library code paths the application actually calls.

Therefore, testing the library inside its own module is necessary but insufficient. You should have an **independent consumer project** depending on the `install`ed or published JAR, then test auto-configuration through Spring Boot's actual discovery mechanism.

The consumer project is also the right place to run `process-aot`, `native:compile`, and `nativeTest`. A Native Image is an artifact of a complete application, not an isolated compilation of a library JAR.

## 3. What Does Spring AOT Change?

### 3.1. AOT Analyzes the ApplicationContext at Build Time

Spring AOT analyzes the ApplicationContext during the build and produces optimization resources, which may include:

- Generated Java sources and bytecode.
- Bean registration/initialization code.
- Runtime hints for reflection, resource loading, serialization, and JDK proxies.
- Resources supporting context initialization in a native image.

AOT is a mandatory step to run a Spring ApplicationContext inside GraalVM Native Image. The Spring Boot Maven Plugin provides `process-aot` for application code and `process-test-aot` for JUnit 5 tests using the Spring TestContext Framework.

### 3.2. Conditions Are Evaluated at Build Time

This is the most critical difference for auto-configuration libraries.

During AOT, the BeanFactory is fully prepared and conditions are evaluated. Example:

~~~java
@ConditionalOnProperty(
    prefix = "acme.greeting",
    name = "enabled",
    havingValue = "true"
)
@Bean
GreetingService greetingService() {
    return new DefaultGreetingService();
}
~~~

If `acme.greeting.enabled=false` during AOT, the bean definition may not enter the generated application. Changing the property to `true` when the native executable runs will not automatically make that bean definition reappear.

Limitations to remember:

- The classpath is fixed and fully determined at build time.
- The set of created beans cannot change arbitrarily at runtime.
- `@Profile` and profile-specific configurations must be selected at build time.
- Properties affecting bean presence via `@Conditional` are evaluated only at build time.
- Bean definitions registered via instance suppliers or direct singletons via `registerSingleton` have limitations during AOT transformation.

If an application needs two different sets of beans per environment, build two AOT/native artifacts with the corresponding build-time environments. If you only need to toggle behavior while the application is running, consider keeping the bean in the context and having it read a runtime property instead of using that property to exclude the bean from the context.

### 3.3. The Classpath Is Fixed Too

A dependency present only on a developer machine or in test runtime, but absent from the dependency graph during native build, cannot be dynamically loaded after the binary is built.

For auto-configuration libraries:

- Declare required dependencies with the proper scope/runtime configuration.
- Avoid relying on arbitrary classpath scanning or class loading without corresponding native design.
- Guard optional dependencies via `@ConditionalOnClass` and structure configurations safely when classes are absent.
- Do not use reflection or dynamic proxies without providing appropriate hints.
- Test every dependency variant the library claims to support.

## 4. Runtime Hints: The Bridge for Native Operations Not Inferable Automatically

### 4.1. Cases Commonly Needing Hints

Native Image uses reachability analysis to decide which code and resources go into the executable. Certain operations are hard to infer completely at build time, such as:

- Reflection using class, method, or constructor names computed at runtime.
- Reading classpath resources by dynamic names.
- Java serialization.
- Creating JDK dynamic proxies.
- DTO binding via reflection in certain JSON flows.

Spring AOT automatically infers many hints from familiar Spring constructs. However, libraries with custom logic or using reflection/resources in ways not statically analyzable may need supplemental declarations.

### 4.2. RuntimeHintsRegistrar

Spring Framework provides `RuntimeHintsRegistrar` so libraries can register native requirements:

~~~java
package com.acme.greeting.autoconfigure;

import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.RuntimeHintsRegistrar;

public final class GreetingRuntimeHints
        implements RuntimeHintsRegistrar {

    @Override
    public void registerHints(
            RuntimeHints hints,
            ClassLoader classLoader) {

        hints.resources().registerPattern(
            "templates/greeting.txt"
        );
    }
}
~~~

This example declares that resource `templates/greeting.txt` must be present in the native image. The API also supports registering reflection, serialization, and JDK proxies when the library actually needs them.

Example registering a method for reflection:

~~~java
Method method = ReflectionUtils.findMethod(
    GreetingTemplate.class,
    "render",
    String.class
);
hints.reflection().registerMethod(method, ExecutableMode.INVOKE);
~~~

Example registering a proxy or serialization:

~~~java
hints.proxies().registerJdkProxy(GreetingExtension.class);
hints.serialization().registerType(GreetingSnapshot.class);
~~~

The snippets above illustrate the API; add hints only for types/members actually used by the library. Redundant hints can bloat image size and obscure poorly understood dynamic dependencies.

### 4.3. Attaching Hints to Auto-Configuration

A library can enable a registrar with `@ImportRuntimeHints` on a configuration class or bean factory method:

~~~java
package com.acme.greeting.autoconfigure;

import org.springframework.context.annotation.ImportRuntimeHints;
import org.springframework.boot.autoconfigure.AutoConfiguration;

@AutoConfiguration
@ImportRuntimeHints(GreetingRuntimeHints.class)
public class GreetingAutoConfiguration {
    // Beans of the library.
}
~~~

The `@ImportRuntimeHints` annotation belongs to package `org.springframework.context.annotation` in Spring Framework 6.1. The registrar is discovered and invoked by Spring AOT during the build. There is no need to create a `GreetingRuntimeHints` bean to invoke it at application startup.

### 4.4. Testing Hints with RuntimeHintsPredicates

You can directly test the hint contents declared by a registrar:

~~~java
package com.acme.greeting.autoconfigure;

import org.junit.jupiter.api.Test;
import org.springframework.aot.hint.RuntimeHints;
import org.springframework.aot.hint.predicate.RuntimeHintsPredicates;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingRuntimeHintsTests {

    @Test
    void registersGreetingTemplateResource() {
        RuntimeHints hints = new RuntimeHints();

        new GreetingRuntimeHints().registerHints(
            hints,
            getClass().getClassLoader()
        );

        assertThat(
            RuntimeHintsPredicates.resource()
                .forResource("templates/greeting.txt")
        ).accepts(hints);
    }
}
~~~

This test confirms the registrar declared the resource hint. It does not prove GraalVM included the resource in the binary or that the application can read the resource in native runtime. A native integration test is required to verify those two steps.

### 4.5. When to Use @RegisterReflectionForBinding?

For DTOs requiring serialization/deserialization, Spring typically infers reflection hints from controller request/response models. When working directly with `WebClient`, `RestClient`, or `RestTemplate`, some data types may need explicit binding declarations via `@RegisterReflectionForBinding`.

For `@ConfigurationProperties`, Spring AOT generates reflection hints automatically in many cases. Nested configuration properties that are not inner classes must be annotated with `@NestedConfigurationProperty` in the proper position so AOT recognizes the nested structure and supports binding in native images.

### 4.6. Tracing Agent and Static Hints

If you do not yet know which hints are missing, the GraalVM Native Image tracing agent can record reflection, resource, and proxy usage while running the application on the JVM:

~~~bash
java -Dspring.aot.enabled=true \
  -agentlib:native-image-agent=config-output-dir=target/native-agent-config/ \
  -jar target/native-consumer-1.0.0.jar
~~~

Once the application is running, invoke the business flows to inspect and then stop the application so the agent writes configuration files.

Note:

- The tracing agent only records code paths that actually executed.
- If running tests, output may contain hints serving only JUnit/Mockito/test infrastructure.
- Review and filter results before adding them into the library.
- Do not treat agent-generated files as complete proof for every runtime flow.

If manual GraalVM JSON hints are needed, place files in `src/main/resources/META-INF/native-image/*/*/`. Avoid overwriting the metadata directory generated by Spring AOT at `META-INF/native-image/{groupId}/{artifactId}/`; use a separate supplemental directory, such as `META-INF/native-image/com.acme/greeting-additional-hints/`.

## 5. Building a Testing Matrix for the Library

A responsible test suite should be divided by objective:

| Test Group | Where to Place | What It Must Prove |
| --- | --- | --- |
| JVM unit tests | Library module | Pure logic, formatters, parsers, algorithms, and error handling |
| Auto-configuration tests | Library module | Conditions, default beans, user overrides, missing/disabled properties |
| Runtime hints tests | Library module | Registrar declared the right reflection/resource/proxy/serialization hints |
| Consumer integration tests | Consumer application | Library JAR is discovered and beans work through Spring Boot |
| AOT JVM smoke test | Consumer application | Generated initialization code can start |
| Native integration tests | Consumer application | Context, beans, and business flows work inside a native image |
| Dependency/platform compatibility tests | CI matrix | Supported combinations of Boot, JDK, GraalVM, dependencies, OS/architecture |

You do not need to put every unit test into a native image. Native compilation is time-consuming and is usually suited for integration tests with Spring TestContext or flows needing native-specific verification.

### 5.1. Testing Auto-Configuration on JVM with ApplicationContextRunner

Example auto-configuration:

~~~java
package com.acme.greeting.autoconfigure;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.ImportRuntimeHints;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
    prefix = "acme.greeting",
    name = "enabled",
    havingValue = "true"
)
@ImportRuntimeHints(GreetingRuntimeHints.class)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    GreetingService greetingService() {
        return new ClasspathGreetingService();
    }
}
~~~

`GreetingService` is the library's interface:

~~~java
package com.acme.greeting.autoconfigure;

public interface GreetingService {
    String greet(String name);
}
~~~

Implementation reading a template from the classpath:

~~~java
package com.acme.greeting.autoconfigure;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

import org.springframework.core.io.ClassPathResource;
import org.springframework.util.StreamUtils;

public final class ClasspathGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        ClassPathResource resource =
            new ClassPathResource("templates/greeting.txt");

        try (InputStream input = resource.getInputStream()) {
            String prefix = StreamUtils.copyToString(
                input,
                StandardCharsets.UTF_8
            ).trim();

            return prefix + ", " + name;
        }
        catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }
}
~~~

Resource `src/main/resources/templates/greeting.txt` has contents:

~~~text
Hello
~~~

Register the auto-configuration in the JAR via file:

~~~text
src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
~~~

File contents:

~~~text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
~~~

### 5.2. Testing Conditions and User Overrides

Place tests in module `greeting-autoconfigure`:

~~~java
package com.acme.greeting.autoconfigure;

import org.junit.jupiter.api.Test;

import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GreetingAutoConfigurationTests {

    private final ApplicationContextRunner contextRunner =
        new ApplicationContextRunner()
            .withConfiguration(
                AutoConfigurations.of(
                    GreetingAutoConfiguration.class
                )
            );

    @Test
    void createsDefaultServiceWhenEnabled() {
        this.contextRunner
            .withPropertyValues("acme.greeting.enabled=true")
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(GreetingService.class);

                assertThat(context.getBean(GreetingService.class)
                    .greet("Ada"))
                    .isEqualTo("Hello, Ada");
            });
    }

    @Test
    void doesNotCreateServiceWhenDisabled() {
        this.contextRunner
            .withPropertyValues("acme.greeting.enabled=false")
            .run(context ->
                assertThat(context)
                    .doesNotHaveBean(GreetingService.class)
            );
    }

    @Test
    void backsOffWhenUserProvidesService() {
        this.contextRunner
            .withPropertyValues("acme.greeting.enabled=true")
            .withUserConfiguration(CustomGreetingConfiguration.class)
            .run(context -> {
                assertThat(context)
                    .hasSingleBean(GreetingService.class);

                assertThat(context.getBean(GreetingService.class)
                    .greet("Ada"))
                    .isEqualTo("Custom, Ada");
            });
    }

    @Configuration(proxyBeanMethods = false)
    static class CustomGreetingConfiguration {

        @Bean
        GreetingService customGreetingService() {
            return name -> "Custom, " + name;
        }
    }
}
~~~

These tests confirm behavior on the JVM:

- Property enabled and no user bean: starter creates default service.
- Property disabled: service is not registered.
- User bean present: default service backs off and custom implementation is used.

These are fast, isolated tests suitable for running frequently during development.

## 6. Consumer Application: Inspecting the Packaged Library Artifact

### 6.1. Why Must the Consumer Be a Separate Project?

If tests run directly inside the library module, the classloader may use `target/classes` and source resources instead of the released JAR. A separate consumer project verifies:

- The auto-configuration imports resource is present in the JAR.
- Runtime dependencies resolve properly.
- The application discovers the configuration via `@SpringBootApplication`.
- `@ConditionalOnProperty` and `@ConditionalOnMissingBean` produce expected results.
- Resources inside the dependency JAR can be read.

### 6.2. Consumer POM

Project `native-consumer` uses Spring Boot 3.3.13 and a dependency on the `install`ed library:

~~~xml
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
    <artifactId>native-consumer</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>greeting-autoconfigure</artifactId>
            <version>1.0.0</version>
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

            <plugin>
                <groupId>org.graalvm.buildtools</groupId>
                <artifactId>native-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Both plugins in `build/plugins` are required: `spring-boot-maven-plugin` handles AOT/application packaging, while `native-maven-plugin` provides native image goals. `spring-boot-starter-parent` manages plugin versions and supplies configuration for the `native` and `nativeTest` profiles.

### 6.3. Build-Time Configuration

Consumer file `src/main/resources/application.properties`:

~~~properties
acme.greeting.enabled=true
~~~

This property must have the proper value when `process-aot` runs, because bean-deciding conditions are evaluated at build time. If the build-time property is `false`, the generated application may not include the default service.

### 6.4. Main Application

File `src/main/java/com/example/consumer/NativeConsumerApplication.java`:

~~~java
package com.example.consumer;

import com.acme.greeting.autoconfigure.GreetingService;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class NativeConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(
            NativeConsumerApplication.class,
            args
        );
    }

    @Bean
    CommandLineRunner printGreeting(GreetingService service) {
        return args -> System.out.println(service.greet("Ada"));
    }
}
~~~

The application package is `com.example.consumer`; the auto-configuration resides in `com.acme.greeting.autoconfigure`. Default component scanning does not need to scan the library package. Boot discovers the library via `AutoConfiguration.imports`.

### 6.5. Consumer Integration Test

File `src/test/java/com/example/consumer/GreetingNativeIntegrationTests.java`:

~~~java
package com.example.consumer;

import com.acme.greeting.autoconfigure.GreetingService;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest
class GreetingNativeIntegrationTests {

    @Autowired
    private GreetingService greetingService;

    @Test
    void autoConfiguredServiceCanLoadLibraryResource() {
        assertThat(greetingService)
            .isNotNull();

        assertThat(greetingService.greet("Ada"))
            .isEqualTo("Hello, Ada");
    }
}
~~~

This test runs inside the consumer context, using the library's dependency JAR and resources. When run on the JVM, it confirms discovery, bean creation, and resource loading in a normal JVM environment. When processed by test AOT and run inside a native image, it also verifies the generated test context and resource hint.

## 7. Layered Build and Verification Process

### 7.1. Step 1 — Build/Install Library and Run JVM Tests

In the `greeting-autoconfigure` directory:

~~~bash
mvn clean install
~~~

Expected results:

- Library compiles successfully.
- `GreetingAutoConfigurationTests` passes.
- `GreetingRuntimeHintsTests` passes.
- Artifact `com.acme:greeting-autoconfigure:1.0.0` is installed in the local Maven repository.

If the library has multiple modules, build required modules in dependency order.

### 7.2. Step 2 — Run Consumer JVM Tests

In the `native-consumer` directory:

~~~bash
mvn clean test
~~~

Expected results:

- Consumer context starts.
- Auto-configuration is discovered from the dependency JAR.
- Bean `GreetingService` is registered.
- `templates/greeting.txt` is read successfully.
- Assertion returns `Hello, Ada`.

If tests fail, inspect the dependency tree, resolved artifact versions, and `AutoConfiguration.imports` contents inside the JAR before moving to AOT.

### 7.3. Step 3 — Generate AOT Assets and Package Executable JAR

With Maven, `spring-boot-starter-parent` provides the `native` profile. When both plugins are declared in the consumer POM, this profile activates `process-aot` and supplies appropriate configuration for Native Build Tools.

Run:

~~~bash
mvn -Pnative clean package
~~~

This command creates an executable JAR containing generated AOT assets. The generated directory typically has the structure:

~~~text
target/
├── native-consumer-1.0.0.jar
└── spring-aot/
    └── main/
        ├── classes/
        ├── resources/
        └── sources/
~~~

Generated paths and file counts may vary by plugin configuration. Do not assert internal generated class names as part of a library's public contract.

### 7.4. Step 4 — Run AOT-Generated Code on the JVM

Before compiling the native image, run the executable JAR on the JVM with AOT initialization enabled:

~~~bash
java -Dspring.aot.enabled=true -jar target/native-consumer-1.0.0.jar
~~~

Line printed by the sample program:

~~~text
Hello, Ada
~~~

This is a valuable check because it executes generated AOT code on the JVM. If the AOT-generated context is missing beans, evaluated conditions wrongly, or lacks part of generated initialization, errors can surface before waiting for native compilation.

**Note:** the JAR must be built with AOT assets, e.g., via `mvn -Pnative clean package`. Running a normally built JAR with `spring.aot.enabled=true` does not prove AOT was generated.

### 7.5. Step 5 — Compile the Native Executable

If GraalVM Native Image and Native Build Tools are installed, run in the consumer project:

~~~bash
mvn -Pnative native:compile
~~~

The native executable is created in `target/`. The filename usually follows the artifact name; on Windows it may carry a `.exe` extension.

Run on Linux/macOS:

~~~bash
./target/native-consumer
~~~

Run on Windows PowerShell:

~~~powershell
.\target\native-consumer.exe
~~~

Line printed by the sample program:

~~~text
Hello, Ada
~~~

If the native build fails, classify errors into categories:

- AOT could not process a bean definition or configuration.
- Missing reflection/resource/proxy/serialization hint.
- Third-party dependency lacks reachability metadata.
- Dependency or class exists only in compile/test scope.
- Incompatible native compiler, toolchain, OS, or architecture.

Do not blindly add broad hints just to make the build pass. Identify the code path and the missing metadata type.

### 7.6. Step 6 — Run Spring Native Integration Tests

Spring Boot 3.3 supports AOT processing for JUnit 5 tests using the Spring TestContext Framework. `process-test-aot` generates `ApplicationContextInitializer` code for eligible test contexts.

If the consumer uses `spring-boot-starter-parent` and declares both `spring-boot-maven-plugin` and `native-maven-plugin`, you can run the `nativeTest` profile:

~~~bash
mvn -PnativeTest test
~~~

In this profile:

1. Test contexts are analyzed to determine required ApplicationContexts.
2. AOT processes test contexts and generates assets.
3. GraalVM builds the native test image.
4. JUnit TestEngine is included in the image along with discovered tests.
5. The native image executes tests and reports results.

`GreetingNativeIntegrationTests` is an example of a Spring TestContext test suited for this flow. Pure unit tests such as registrar tests or parser tests should continue running on the JVM; there is no need to force every test into a native image.

Native tests take much longer than JVM tests. You can run them regularly in nightly CI or a separate pipeline, while JVM tests run on every pull request.

## 8. Properly Testing Build-Time and Runtime Conditions

### 8.1. Which Property Is Used During AOT?

In the example, `acme.greeting.enabled=true` is in the consumer's `application.properties`. When `process-aot` creates the BeanFactory, the condition matches and the default `GreetingService` enters the generated context.

If built with:

~~~properties
acme.greeting.enabled=false
~~~

the condition does not match; the bean may not appear in AOT output. When running the native binary, setting the property to `true` will not make Spring re-process auto-configurations to create a new bean.

### 8.2. Feature Flags That Must Change at Runtime

If a product requirement is toggling a feature after deployment, consider this design:

- Include the service bean stably in the context at build time.
- Bind runtime properties into `@ConfigurationProperties`.
- Have the service read runtime values and decide behavior inside methods.
- Use `@ConditionalOnProperty` only when bean presence/absence can genuinely be fixed for the artifact.

If deployments need different bean sets, build separate native artifacts with corresponding build-time profiles/properties and test each artifact.

### 8.3. Profiles and Classpath

`@Profile` and the dependency classpath also participate in build-time decisions. If a consumer has multiple profiles:

- Select the profile before running `process-aot`.
- Do not expect the native binary to dynamically load a new profile to create ungenerated bean definitions.
- Build/test each supported profile.
- Explicitly document profiles and dependency sets in the support matrix.

## 9. Evaluating Dependencies and Native Support Scope

### 9.1. Native Support Is a Property of the Dependency Graph

An auto-configuration may use only native-supported Spring APIs, yet a dependency whose bean it creates might use dynamic reflection or resource loading without hints. In that case, the entire consumer app can still fail native compilation.

Spring Boot does not supply out-of-the-box hints for every third-party library; the GraalVM Reachability Metadata ecosystem provides metadata for many dependencies. Verify whether specific dependency versions have native metadata.

### 9.2. Support Matrix That Should Be Published

Example support matrix table for a library:

| Component | Tested Scope per Boot 3.3.13 Docs | Must Be Specified in CI |
| --- | --- | --- |
| Spring Boot | 3.3.13 | Minor/patch line and minimum version |
| Spring Framework | 6.1.21 or higher as required by Boot 3.3.13 | Actual version selected by dependency management |
| Java | 17 to 23 | Specific JDK vendor and patch |
| GraalVM Community | 22.3 or higher | Distribution, patch, and native-image version |
| Native Build Tools | 0.10.6 | Actual plugin version |
| Maven | 3.6.3 or higher | CI Maven wrapper/version |
| Gradle | 7.x from 7.5 or 8.x | Actual wrapper version |
| OS/architecture | Only built and executed targets | Linux x64, Linux ARM64, Windows x64... per reality |

The table lists baseline requirements per Spring Boot 3.3.13 documentation, not a claim that the sample library was run on every combination. Fill in actual CI results.

Spring Boot 3.3.13 requires Java 17 and is compatible up to Java 23; native image requirements include GraalVM 22.3 or higher and Native Build Tools 0.10.6. Minimum Maven is 3.6.3; Gradle supports 7.x (from 7.5) and 8.x. Third-party dependencies may have their own or higher requirements.

### 9.3. Native Images Depend on Target Platform

A native executable is produced for a target operating system and architecture. Do not infer that a binary built on Linux x64 can run on Windows or ARM64.

For libraries claiming native support:

- Build on each key target platform.
- Run the binary on that target.
- Check resources, file paths, charsets, TLS, native libraries, and dependencies with OS-dependent behavior.
- Save build logs and toolchain versions for reproducibility.
- Do not claim platform support solely from a successful native compilation on another platform.

## 10. Common Mistakes When Moving Auto-Configuration to Native

| Mistake / Misconception | Why It Happens | Fix |
| --- | --- | --- |
| JVM tests pass so native is guaranteed to pass | JVM allows dynamic reflection/resource lookups absent in native | Add hints tests, AOT smoke tests, and native integration tests |
| Testing only the library module | Fails to test consumer dependency graph and main application | Use an independent consumer project depending on the published JAR |
| Expecting `@ConditionalOnProperty` to toggle beans after deploy | Condition was evaluated when AOT created the BeanFactory | Set property at build time or move feature decision into a runtime service |
| AOT build uses the wrong profile | Bean definitions for another profile were not generated | Select profile before process AOT and build separate artifacts |
| Resource present in JVM JAR yet missing in native | Resource was not included in the native image reachability set | Register resource hint and run native tests |
| Reflection works on JVM yet fails in native | GraalVM does not know which members are invoked via reflection | Register exact reflection hints |
| Dynamic proxy is not created | Proxy interface was not declared for native | Register JDK proxy hint |
| JSON DTO fails to bind in native | Reflection metadata for nested or dynamic types missing | Check `@RegisterReflectionForBinding`, nested configuration properties, and hints |
| Adding hints for an entire package | Expands reachability and masks real root causes | Register exact needed types/members/resources |
| Running only tracing agent and copying all output files | Agent may record test infrastructure and non-product code paths | Filter, review, and re-test each hint |
| Third-party dependency lacks reachability metadata | Native compiler misses reflection/resources needed by dependency | Check version, metadata repository, and vendor support |
| Native tests run via JVM Surefire | Only runs JVM tests without building a native test image | Use `nativeTest` profile or Gradle `nativeTest` |
| Building native on one OS and claiming support for all OSes | Native binaries are tied to the target platform | CI matrix builds and runs each supported target |

## 11. QA Process Before Publishing a Native-Compatible Library

1. **Define the support matrix:** Spring Boot, Java, GraalVM, Native Build Tools, build tools, OS, and architecture.
2. **Build the library artifact:** run compile/tests, verify imports resource, and package JAR.
3. **Test auto-configuration on JVM:** condition match/no-match, default bean, custom bean override, missing properties, and optional classpath.
4. **Test runtime hints:** use `RuntimeHintsPredicates` for resources/reflection/proxies/serialization registered by the library.
5. **Test consumer project:** depend on installed/published JAR and run `@SpringBootTest`.
6. **Run application AOT:** use exact build-time profiles and properties; resolve any generation errors.
7. **Run AOT on JVM:** `spring.aot.enabled=true` to check generated initialization.
8. **Build native image:** use exact GraalVM/Native Build Tools versions and target platform.
9. **Run native smoke/integration tests:** confirm beans, resources, and critical business flows.
10. **Verify dependency metadata:** confirm third-party dependencies have native reachability support.
11. **Retain evidence:** build logs, test reports, artifact checksums, toolchain versions, and target platforms.
12. **Publish limitations:** state verified versions/features/platforms explicitly; do not extrapolate claims beyond CI evidence.

## 12. Self-Check Exercises

**Question 1.** Why are `ApplicationContextRunner` tests on the JVM insufficient to claim an auto-configuration is native-compatible?  
**Answer:** They test conditions and bean behavior on the JVM, but do not test AOT-generated code, native reachability, reflection hints, or resource inclusion.

**Question 2.** When does Spring AOT evaluate `@ConditionalOnProperty`?  
**Answer:** During build-time AOT processing when the BeanFactory is prepared. Properties affecting bean presence must be set properly at build time.

**Question 3.** If `acme.greeting.enabled=false` during process AOT, and then the property is set to true when running the native image, will the bean appear automatically?  
**Answer:** No. The bean definition was excluded from AOT output; runtime properties do not make Spring re-analyze auto-configurations.

**Question 4.** What is `RuntimeHintsRegistrar` used for?  
**Answer:** Registering reflection, resources, serialization, and JDK proxy requirements for AOT/native image.

**Question 5.** Does a passing `RuntimeHintsPredicates` test prove the native binary runs properly?  
**Answer:** No. It proves the registrar declared hints as expected. Native compilation and native runtime tests are needed to verify the final image.

**Question 6.** Why should native integration tests live inside a consumer application?  
**Answer:** Because a native image is built from a complete application with an actual dependency graph, main configuration, properties, profiles, and auto-configuration discovery.

**Question 7.** Which command runs an AOT-generated JAR on the JVM?  
**Answer:** Build the JAR with AOT assets, then run `java -Dspring.aot.enabled=true -jar target/...jar`.

**Question 8.** Which Maven command runs native tests with the Spring Boot parent and Native Build Tools declared?  
**Answer:** `mvn -PnativeTest test`.

**Question 9.** Why should you not copy the entire tracing agent output into a library?  
**Answer:** Output may include hints for test infrastructure or unnecessary code paths; it must be reviewed, filtered, and verified.

**Question 10.** Can native support be claimed for Windows ARM64 if CI only builds Linux x64?  
**Answer:** No. You must build and run on the advertised target OS/architecture or have reliable equivalent test evidence.

## 13. Takeaways and Reference Materials

- JVM tests verify most logic and conditions; consumer tests verify the artifact used as a real application.
- AOT processes the ApplicationContext at build time; conditions and classpath determine a fixed bean set for the artifact.
- `RuntimeHintsRegistrar` and `@ImportRuntimeHints` declare reflection/resource/proxy/serialization requirements that Spring cannot infer automatically.
- `RuntimeHintsPredicates` verifies hint contents; native executable tests confirm results in GraalVM.
- A consumer application is the most valuable place for native testing of an auto-configuration library.
- `mvn -Pnative clean package` produces AOT assets; `spring.aot.enabled=true` lets you test generated code on the JVM; `mvn -Pnative native:compile` builds the native executable; `mvn -PnativeTest test` runs native tests.
- `@Conditional` rules affecting bean presence must be configured at build time; runtime feature toggles need a separate design.
- Native support must be published strictly against the tested matrix of versions, dependencies, and target platforms.

Official Spring Boot 3.3.13 / Spring Framework 6.1 Documentation:

1. [Testing GraalVM Native Images](https://docs.spring.io/spring-boot/3.3/how-to/native-image/testing-native-applications.html) — strategy for JVM tests and native tests.
2. [Ahead-of-Time Processing — Maven Plugin 3.3.13](https://docs.spring.io/spring-boot/3.3/maven-plugin/aot.html) — `process-aot`, `process-test-aot`, native and nativeTest profiles.
3. [Advanced Native Images Topics](https://docs.spring.io/spring-boot/3.3/reference/packaging/native-image/advanced-topics.html) — RuntimeHintsRegistrar, @ImportRuntimeHints, tracing agent, and known limitations.
4. [Spring Framework Ahead-of-Time Optimizations](https://docs.spring.io/spring-framework/reference/core/aot.html) — build-time conditions, generated assets, and runtime hints.
5. [Spring Boot 3.3.13 System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html) — Java, Maven, Gradle, GraalVM, and Native Build Tools versions.
6. [Spring Boot 3.3 Maven Plugin — Using the Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html) — parent POM, plugin, and native profile.
7. [Spring Boot 3.3 — Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html) — auto-configuration structure and testing.
8. [Spring Boot 3.3.13 — RuntimeHintsRegistrar Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/aot/hint/RuntimeHintsRegistrar.html).
9. [Spring Boot 3.3.13 — RuntimeHintsPredicates Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/aot/hint/predicate/RuntimeHintsPredicates.html).
10. [GraalVM Reachability Metadata Repository](https://github.com/oracle/graalvm-reachability-metadata) — native metadata for third-party dependencies.
