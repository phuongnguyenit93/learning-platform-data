# Parameter-Name Requirement (-parameters) and Compiler Configuration

In Spring Boot, `@ConfigurationProperties` maps externalized configuration into a strongly typed Java object. With **constructor binding**, Spring Boot instantiates the object by invoking a constructor and passing configuration key values into **each parameter**. To know that the `connectTimeout` parameter receives its value from `client.connect-timeout`, the framework must determine **constructor parameter names** at runtime.

For a regular Java class, **having parameter names in source code does not mean they are always retained in bytecode**. The `javac` compiler provides the `-parameters` flag to store parameter-name metadata in `.class` files for reflection. Spring Boot's documentation explicitly specifies compiling with `-parameters` when using constructor binding. Spring Boot's Maven parent and Spring Boot's Gradle plugin typically configure this already, yet projects using custom build setups, BOMs without the parent, library modules, IDE compilers, or other pipelines still need verification.

This lesson explains why parameter names are required, how to enable `-parameters` in Maven and Gradle, how to inspect bytecode, how this relates to Java `record`s, and how to diagnose binding failures caused by compiler configuration.

## 1. Why Does Constructor Binding Need Parameter Names?

Suppose `application.yml` contains:

~~~yaml
gateway:
  base-url: "https://api.example.invalid"
  connect-timeout: 3s
  max-retries: 4
~~~

An immutable properties class:

~~~java
package example.gateway;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "gateway")
public final class GatewayProperties {

    private final URI baseUrl;
    private final Duration connectTimeout;
    private final int maxRetries;

    public GatewayProperties(
            URI baseUrl,
            Duration connectTimeout,
            int maxRetries) {
        this.baseUrl = baseUrl;
        this.connectTimeout = connectTimeout;
        this.maxRetries = maxRetries;
    }

    public URI getBaseUrl() {
        return baseUrl;
    }

    public Duration getConnectTimeout() {
        return connectTimeout;
    }

    public int getMaxRetries() {
        return maxRetries;
    }
}
~~~

In Spring Boot 3.x, when a configuration-properties type has only one eligible parameterized constructor, constructor binding is usually inferred without annotating that constructor with `@ConstructorBinding`.

The Binder needs to know:

| Constructor Parameter | Bound Property | Value After Conversion |
| --- | --- | --- |
| `baseUrl` | `gateway.base-url` | `URI` |
| `connectTimeout` | `gateway.connect-timeout` | `Duration.ofSeconds(3)` |
| `maxRetries` | `gateway.max-retries` | Integer `4` |

The parameter names `baseUrl`, `connectTimeout`, and `maxRetries` enable the Binder to link **Java structure** with **configuration key names** via relaxed binding.

If bytecode lacks parameter-name metadata and no suitable discovery fallback exists, reflection on the constructor may only see `arg0`, `arg1`, `arg2`. Spring Boot then cannot reliably determine that `arg1` should receive `gateway.connect-timeout` and can fail to create or bind the configuration-properties bean.

**Core takeaway:** `-parameters` does not cause Spring Boot to read a different YAML file, generate getters, or auto-register beans. It **preserves parameter names during compilation so the framework can inspect them at runtime**.

## 2. What Does the javac -parameters Flag Actually Do?

Plain Java example:

~~~java
package example;

public class ExampleConstructor {

    public ExampleConstructor(String name, int retries) {
    }
}
~~~

When compiled using `javac` with `-parameters`:

~~~bash
javac -parameters -d out src/main/java/example/ExampleConstructor.java
~~~

the compiler writes `MethodParameters` metadata into the `.class` file. Frameworks using Java reflection can then read the actual declared names.

Reflection:

~~~java
import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class InspectParameters {

    public static void main(String[] args) {
        Constructor<?> constructor =
            ExampleConstructor.class.getDeclaredConstructors()[0];

        for (Parameter parameter : constructor.getParameters()) {
            System.out.println(
                parameter.getName() + " -> " +
                parameter.isNamePresent());
        }
    }
}
~~~

For a regular Java constructor compiled with `-parameters`, expected output is:

~~~text
name -> true
retries -> true
~~~

When compiled **without** the flag and without special metadata mechanisms, reflection can return:

~~~text
arg0 -> false
arg1 -> false
~~~

Java does not guarantee retaining parameter names for regular constructors/methods when `-parameters` is off. Parameter names are part of the source signature, yet runnable bytecode does not inherently need those names for the JVM to invoke a method.

**This is a compile-time option.** Passing `-parameters` to `java -jar ...` at runtime **will not** restore missing metadata. You must recompile the classes whose constructors need binding.

## 3. MethodParameters vs. LocalVariableTable and Debug Symbols

A common misconception: "The compiler has debug info enabled, so variable names are in `.class` and Spring can surely read constructor parameter names."

Different metadata sections serve different purposes:

| Metadata / Option | Purpose |
| --- | --- |
| `-parameters` | Stores formal parameter names for reflection, typically emitted in `MethodParameters` |
| `-g` and debug info | Can generate `LineNumberTable`, `LocalVariableTable`, and debugging details |
| `-g:none` | Omits debug info; does not necessarily disable `MethodParameters` if `-parameters` is used |
| `-source` / `--release` | Controls Java language/bytecode compatibility level; does not replace `-parameters` |

In particular, starting with **Spring Framework 6.1**, earlier parameter-name discovery mechanisms that fell back on the local variable table are no longer treated as a standard fallback as in older versions. Compiling with `-parameters` ensures other parts of Spring can also rely on parameter names consistently.

Do not conclude from seeing `LocalVariableTable` in `javap -v` output that constructor binding has the metadata it needs. Check the `MethodParameters` section and/or test reflection on the exact class in question.

Some class kinds such as Java records carry dedicated structural metadata; parameter-name behavior on a record's canonical constructor can differ from regular classes. Even so, configuring the project build with `-parameters` remains the consistent recommendation per Spring Boot's guide, especially when a codebase contains both records and classes with hand-written constructors.

## 4. Configuring @ConfigurationProperties Properly Before Looking at the Compiler

A class compiled with `-parameters` still must be **registered as a configuration-properties bean**.

Explicit registration example:

~~~java
package example.gateway;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(GatewayProperties.class)
public class GatewayConfiguration {
}
~~~

Or scanning:

~~~java
package example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;

@SpringBootApplication
@ConfigurationPropertiesScan(basePackages = "example.gateway")
public class Application {
    public static void main(String[] args) {
        SpringApplication.run(Application.class, args);
    }
}
~~~

These are **two alternative registration methods** in many cases. There is no need to both scan and enable the same class "just to be safe."

With constructor binding:

- `@ConfigurationProperties(prefix = ...)` defines the configuration root.
- `@EnableConfigurationProperties(...)` or `@ConfigurationPropertiesScan` brings typed properties into the container.
- `-parameters` preserves Java parameter-name metadata for the Binder to inspect.
- Conversion and validation determine whether bound data has valid types and values.

Do not use plain `@Component` as a substitute for registering constructor-bound immutable properties. Beans created through normal Spring mechanisms (such as `@Bean` or `@Component`) are not equivalent to the Binder selecting a configuration-parameter constructor.

## 5. Maven with spring-boot-starter-parent

If the project uses Spring Boot's Maven parent:

~~~xml
<project>
  <modelVersion>4.0.0</modelVersion>

  <parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version><!-- your project's Spring Boot version --></version>
    <relativePath/>
  </parent>

  <!-- dependencies, build... -->
</project>
~~~

In modern Spring Boot releases, the Maven parent already manages many plugin settings for the application, including compiling Java with parameter names. Therefore you **typically do not need** to add `-parameters` manually when using the standard parent without overriding configurations.

However, distinguish between:

- Using `spring-boot-starter-parent`: inherits plugin management and build conventions from the parent.
- Importing only the `spring-boot-dependencies` BOM in `dependencyManagement`: primarily manages dependency versions; **it does not bring along the starter parent's build plugin configurations**.
- Using an organization-managed custom parent: verify whether that parent configures `maven-compiler-plugin` or the `maven.compiler.parameters` property properly.
- A multi-module build: modules may have different parents or plugin overrides.

If the parent already configures it properly, avoid duplicating configuration out of habit. Check the **effective POM** when confirming what actually applies.

## 6. Maven: Explicitly Enabling -parameters

If you are not using the Spring Boot parent or need to guarantee it in a standalone module, configure `maven-compiler-plugin`.

An explicit option in `pom.xml`:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <parameters>true</parameters>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

For compiler plugins supporting the `parameters` option, `<parameters>true</parameters>` instructs the plugin to pass `-parameters` when invoking the Java compiler.

You can set the property:

~~~xml
<properties>
  <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
~~~

The property approach depends on a Maven Compiler Plugin version that supports `maven.compiler.parameters`. If the build uses an older plugin, upgrade or configure the plugin according to your project's version-management strategy.

Another way uses compiler args:

~~~xml
<build>
  <plugins>
    <plugin>
      <groupId>org.apache.maven.plugins</groupId>
      <artifactId>maven-compiler-plugin</artifactId>
      <configuration>
        <compilerArgs>
          <arg>-parameters</arg>
        </compilerArgs>
      </configuration>
    </plugin>
  </plugins>
</build>
~~~

Prefer the dedicated `<parameters>true</parameters>` option when supported by the plugin, as it expresses intent more clearly.

### Should You Declare the Version of maven-compiler-plugin?

If the parent or `pluginManagement` already manages a suitable version, `<version>` on the plugin declaration may be omitted. If nothing manages versions, pin a version approved by your build system rather than relying implicitly on defaults. Examples here focus on flag configuration; no fixed version number is mandated since it must fit your Java, Maven, and project standards.

### Parent and pluginManagement in Multi-Module Maven Builds

In Maven, `pluginManagement` provides **default versions and configurations** for plugins used in modules. It is not automatically equivalent to forcing every module to execute a plugin in every lifecycle phase. `maven-compiler-plugin` normally participates in a Java module's lifecycle, yet what matters is the **effective plugin configuration** of the module containing the source files.

For example, a `shared-config` library containing `GatewayProperties.class`:

~~~text
root/pom.xml
  services/order-service/pom.xml
  libraries/shared-config/pom.xml
~~~

If only `order-service` enables `-parameters` while `shared-config` does not, the `GatewayProperties` constructor packaged inside the library JAR may still lack metadata. You cannot "patch" metadata of an already-compiled library simply by enabling the flag in the consuming module.

## 7. Maven: How to Check the Effective Build Configuration

Use the repository's Maven Wrapper if available:

~~~bash
./mvnw clean compile
~~~

Windows:

~~~powershell
.\mvnw.cmd clean compile
~~~

To inspect the merged POM combining parent, plugin management, and module:

~~~bash
./mvnw help:effective-pom
~~~

You can write it to a file for inspection:

~~~bash
./mvnw help:effective-pom -Doutput=effective-pom.xml
~~~

Search for `maven-compiler-plugin`, `parameters`, or `compilerArgs` in the effective POM of the module being built. Finding a snippet in the root POM alone is not enough; verify the configuration is inherited and applied to the specific module.

To verify metadata after compilation, run `javap -v` on the class (covered in the verification section). This provides direct proof beyond reading the POM, because bytecode is the compiler's final output.

### Test Sources May Also Need Metadata

When Spring uses reflection on constructors or methods in test classes, test compilation matters too. `maven-compiler-plugin` normally covers both compile and testCompile goals, yet if a build uses custom plugin executions or profiles, confirm both.

Do not confuse `maven.compiler.testSource` or test source directories with `-parameters`. Parameter metadata must reside in the bytecode of the **classes reflected upon at runtime or test runtime**, not just in an arbitrary build target.

## 8. Gradle with the Spring Boot Plugin

A Gradle project with:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
}
~~~

For Java compilation tasks configured by the Spring Boot Gradle plugin under its standard conventions, `-parameters` is typically added automatically. This behavior is documented by Spring Boot, yet **do not infer from the presence of the plugin in a different subproject** that every `JavaCompile` task receives the flag.

Things to verify:

- Does the module that actually compiles the properties class apply the plugin or convention setup?
- Does a multi-project Gradle build declare the plugin at the root with `apply false` without applying it in the subproject?
- Is there a manually created `JavaCompile` task, custom compiler, or override of `options.compilerArgs` after the plugin runs?
- Do CI and the IDE invoke the same Gradle task or use separate compilers?
- Does the final `.class` file inside the JAR actually contain `MethodParameters`?

If you are unsure whether the convention takes effect, enable it explicitly for all `JavaCompile` tasks in the module.

## 9. Gradle Groovy DSL: build.gradle

Configuration:

~~~groovy
plugins {
    id 'java'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

`configureEach` configures tasks of type `JavaCompile`, including tasks registered later. For a project that does not apply the Spring Boot plugin yet contains Java sources with constructor-bound properties, this is an explicit way to set the flag.

If the project already sets other compiler args, `+=` appends instead of overwriting the entire list:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += [
        '-parameters',
        '-Xlint:deprecation'
    ]
}
~~~

Avoid configuring:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs = ['-parameters']
}
~~~

when the project already has required flags supplied by plugins or conventions; assigning a brand-new list can accidentally wipe out earlier compiler arguments.

Use the Gradle Wrapper to build:

~~~bash
./gradlew clean classes
~~~

On Windows:

~~~powershell
.\gradlew.bat clean classes
~~~

For a `shared-config` subproject, ensure the Gradle configuration applies to **that subproject**, not just the root project.

## 10. Gradle Kotlin DSL: build.gradle.kts

An equivalent configuration:

~~~kotlin
import org.gradle.api.tasks.compile.JavaCompile

plugins {
    java
}

tasks.withType<JavaCompile>().configureEach {
    options.compilerArgs.add("-parameters")
}
~~~

Kotlin DSL uses `options.compilerArgs.add(...)` to append the flag. If the Spring Boot Gradle plugin is already applied and its convention takes effect, this block may be redundant; just be careful not to add duplicate `-parameters` arguments or overwrite other compiler options.

A multi-project Gradle build can share this via a convention plugin so library and application modules use identical compile rules. Still, having a convention at the root does not prove every subproject applies it. Check where the class is actually built.

### Do Not Confuse the Java Plugin and Kotlin Compiler

If the properties class is written in **Java**, `-parameters` must go to the Java compiler. For **Kotlin** code, Kotlin's parameter-name discovery and metadata behave differently; do not take a `JavaCompile` snippet and assume it configures `KotlinCompile`. A mixed-language project must inspect each compiler and plugin version appropriately.

This lesson focuses on Java, Java constructors, and Java records.

## 11. Java Records and Parameter Names

Java `record`s are well suited for immutable configuration:

~~~java
package example.report;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "reporting")
public record ReportingProperties(
        boolean enabled,
        int batchSize,
        Duration timeout
) {}
~~~

YAML:

~~~yaml
reporting:
  enabled: true
  batch-size: 100
  timeout: 5s
~~~

Registration:

~~~java
package example.report;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ReportingProperties.class)
public class ReportingConfiguration {
}
~~~

In Spring Boot 3.x, a record's canonical constructor is normally used for constructor binding. If a record has a single standard canonical constructor, there is no need to place `@ConstructorBinding` just to ask Spring to use it.

**Subtlety:** records have **record component metadata** defined by Java. Some record constructors can retain parameter names under Java record rules even when regular class constructors behave differently. Do not extrapolate from the behavior of **one record** to conclude that `-parameters` is unnecessary across the entire project.

Spring Boot documentation still states the general requirement to compile constructor-bound classes with `-parameters`. To ensure different Java types—records, immutable classes, library classes, and framework injection—work consistently, keeping the compiler flag in your build system is a verifiable practice.

### A Record Does Not Replace Registration

A record having component names **does not make it a Spring bean**. Without `@EnableConfigurationProperties(ReportingProperties.class)` or appropriate scanning, a service injecting `ReportingProperties` can still fail due to a missing bean.

A complete three-part example:

~~~java
@ConfigurationProperties(prefix = "reporting")
public record ReportingProperties(
        boolean enabled, int batchSize
) {}
~~~

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(ReportingProperties.class)
class ReportingConfiguration {}
~~~

~~~java
@Service
class ReportService {

    private final ReportingProperties properties;

    ReportService(ReportingProperties properties) {
        this.properties = properties;
    }
}
~~~

Distinguish the constructor parameter names of `ReportingProperties`—used for binding—from the `properties` parameter name of `ReportService`—which may participate in Spring container autowiring in certain other scenarios.

## 12. Hand-Written Constructors and Multiple Constructors

Example of a class with two constructors:

~~~java
package example.worker;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.ConstructorBinding;

@ConfigurationProperties(prefix = "worker")
public final class WorkerProperties {

    private final int maxThreads;
    private final Duration pollingInterval;

    @ConstructorBinding
    public WorkerProperties(int maxThreads, Duration pollingInterval) {
        this.maxThreads = maxThreads;
        this.pollingInterval = pollingInterval;
    }

    public WorkerProperties() {
        this(4, Duration.ofSeconds(5));
    }

    public int getMaxThreads() {
        return maxThreads;
    }

    public Duration getPollingInterval() {
        return pollingInterval;
    }
}
~~~

In Spring Boot 3.x, when a class has multiple constructors and you want to choose a specific one, `@ConstructorBinding` can be placed on the selected constructor using the API in `org.springframework.boot.context.properties.bind`.

**The annotation does not invent missing parameter names.** If the class was compiled without the required metadata, adding `@ConstructorBinding` only tells Spring **which constructor to pick**, not that `maxThreads` maps to a particular key.

Do not conflate three separate questions:

1. Which constructor creates the properties object?
2. What are that constructor's parameter names when the framework inspects bytecode?
3. Are there properties supplying values for each parameter, and can they be converted?

`@ConstructorBinding` answers the first question when multiple options exist. `-parameters` supports the second question. Configuration files, the Binder, and converters answer the third.

## 13. @DefaultValue, Nested Objects, and Parameter Names

For immutable properties, default values can be declared on constructor parameters or record components using `@DefaultValue`:

~~~java
package example.worker;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.DefaultValue;

@ConfigurationProperties(prefix = "worker")
public record WorkerProperties(
        @DefaultValue("4") int maxThreads,
        @DefaultValue("5s") Duration pollingInterval,
        @DefaultValue("false") boolean enabled
) {}
~~~

With YAML:

~~~yaml
worker:
  enabled: true
~~~

when fields are missing from configuration sources, the Binder can apply `maxThreads=4` and `pollingInterval=5s` per the declared defaults.

This is completely separate from `-parameters`:

- `-parameters` lets the framework **know parameter names**.
- `@DefaultValue` supplies a value when **the corresponding property is absent**.
- ConversionService/Binder converts the default string to the Java type.
- Validation can subsequently check the resulting value.

Do not use defaults as a way to ignore invalid types, such as `worker.max-threads: "many"`. Even with `@DefaultValue("4")`, data that is present yet cannot convert to a number still causes a binding error.

### Nested Values

~~~java
@ConfigurationProperties(prefix = "client")
public record ClientProperties(
        String name,
        Retry retry
) {
    public record Retry(int attempts, Duration delay) {}
}
~~~

With:

~~~yaml
client:
  name: "warehouse"
  retry:
    attempts: 3
    delay: 250ms
~~~

The name of the root constructor parameter `retry` also matters for locating the nested structure. Inside it, `attempts` and `delay` must likewise be mapped by the Binder. Having consistent parameter-name metadata for types using constructor binding makes nested configuration predictable.

## 14. How to Inspect .class Files Using javap

**Inspecting bytecode after a build** is the most direct way to confirm the compiler actually retained metadata.

Suppose you have:

~~~text
target/classes/example/gateway/GatewayProperties.class
~~~

Run:

~~~bash
javap -v -p target/classes/example/gateway/GatewayProperties.class
~~~

With Gradle:

~~~bash
javap -v -p build/classes/java/main/example/gateway/GatewayProperties.class
~~~

Depending on your JDK and platform, you can also specify the class name with a classpath:

~~~bash
javap -classpath target/classes -v -p example.gateway.GatewayProperties
~~~

In the output, locate the method/constructor:

~~~text
public example.gateway.GatewayProperties(
    java.net.URI, java.time.Duration, int);
...
MethodParameters:
  Name                 Flags
  baseUrl
  connectTimeout
  maxRetries
~~~

The excerpt above **illustrates the relevant section**, not the complete raw output of `javap`. What matters is finding `MethodParameters` with the expected parameter names for the constructor.

If the output only shows debug metadata, or `MethodParameters` lacks the expected names, review your build setup. If the class is a record, remember records have their own metadata rules; also inspect a regular class constructor when verifying whether `-parameters` applies broadly.

**Do not use stale files in `target/classes` to claim the current configuration is correct.** Run a clean build first, then inspect the freshly produced artifact.

## 15. Verifying via Reflection Instead of Just Reading the POM

A simple Java check:

~~~java
package example.gateway;

import java.lang.reflect.Constructor;
import java.lang.reflect.Parameter;

public class ConstructorMetadataCheck {

    public static void main(String[] args) {
        Constructor<?> constructor =
            GatewayProperties.class.getDeclaredConstructors()[0];

        for (Parameter parameter : constructor.getParameters()) {
            System.out.printf(
                "%s: present=%s%n",
                parameter.getName(),
                parameter.isNamePresent()
            );
        }
    }
}
~~~

If the class was truly compiled with the flag and parameter names were recorded properly, output looks like:

~~~text
baseUrl: present=true
connectTimeout: present=true
maxRetries: present=true
~~~

For a regular class without metadata, you may see:

~~~text
arg0: present=false
arg1: present=false
arg2: present=false
~~~

In real code, select the specific constructor rather than relying blindly on index `[0]` when a class has multiple constructors. For records, you can look up the canonical constructor by component types or inspect `getRecordComponents()` to observe record-specific metadata.

In a CI build, a reflection test on **a class containing a configuration-properties constructor** can catch a module accidentally compiled without the flag.

## 16. Unit Tests Are Not Enough If They Only Call new

Example test:

~~~java
@Test
void createsObjectDirectly() {
    GatewayProperties properties =
        new GatewayProperties(
            URI.create("https://api.example.invalid"),
            Duration.ofSeconds(3),
            4
        );

    assertEquals(4, properties.getMaxRetries());
}
~~~

This test verifies that **the Java constructor can be called**. It does not need the Spring Binder to discover parameter names, so it can pass even when bytecode lacks `-parameters`. Therefore, such a test **does not prove constructor binding works**.

To test binding, you must start an appropriate context/Binder and supply a property source.

## 17. Testing Binding with ApplicationContextRunner

With Spring Boot Test, you can use `ApplicationContextRunner`:

~~~java
package example.gateway;

import java.time.Duration;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

import static org.assertj.core.api.Assertions.assertThat;

class GatewayPropertiesBindingTest {

    private final ApplicationContextRunner runner =
        new ApplicationContextRunner()
            .withUserConfiguration(TestConfiguration.class);

    @Test
    void bindsConstructorParameters() {
        runner
            .withPropertyValues(
                "gateway.base-url=https://api.example.invalid",
                "gateway.connect-timeout=3s",
                "gateway.max-retries=4"
            )
            .run(context -> {
                assertThat(context).hasSingleBean(
                    GatewayProperties.class);

                GatewayProperties properties =
                    context.getBean(GatewayProperties.class);

                assertThat(properties.getConnectTimeout())
                    .isEqualTo(Duration.ofSeconds(3));
                assertThat(properties.getMaxRetries())
                    .isEqualTo(4);
            });
    }

    @Configuration(proxyBeanMethods = false)
    @EnableConfigurationProperties(GatewayProperties.class)
    static class TestConfiguration {
    }
}
~~~

This test requires Spring Boot Test and matching assertions in the project. It exercises the real path:

1. Context loads the configuration registering `GatewayProperties`.
2. Property source supplies values.
3. Binder resolves the constructor and parameter names.
4. Converter transforms types.
5. Bean is created with the expected values.

If the context fails before creating the bean, inspect the root cause rather than assuming `-parameters` is to blame. It could be registration, prefix, converter, validation, or another dependency error.

### How Can a Test Missing Metadata Manifest?

A Java module compiled without `-parameters` can cause a constructor-binding test to fail when the Binder tries to resolve constructor parameter names. Depending on the Spring Boot version, the message may state that parameter names could not be determined or that compiling with `-parameters` is required.

When encountering such an error, check bytecode before changing YAML. If key names and the Java constructor are right yet the class lacks metadata, editing YAML will not fix it.

## 18. Spring Framework 6.1 and Parameter-Name-Based Autowiring

There is a related issue that should be kept distinct. In certain dependency injection scenarios involving **multiple beans of the same type**, Spring can use **constructor parameter names** to match a bean by name when no qualifier or priority is given. Starting in Spring Framework 6.1, this parameter-name matching requires `-parameters` metadata.

Example:

~~~java
@Configuration(proxyBeanMethods = false)
class ClientBeans {

    @Bean
    HttpClient primaryClient() {
        return new HttpClient("primary");
    }

    @Bean
    HttpClient archiveClient() {
        return new HttpClient("archive");
    }
}
~~~

A consumer:

~~~java
@Service
class ArchiveService {

    private final HttpClient archiveClient;

    ArchiveService(HttpClient archiveClient) {
        this.archiveClient = archiveClient;
    }
}
~~~

`HttpClient` here is a hypothetical class. With two beans of the same type, the framework can use the `archiveClient` parameter name to disambiguate when metadata and conditions align. Without `-parameters`, the application may report bean ambiguity in situations that previously relied on parameter names.

However, **dependency injection by bean name** is not the same as **constructor binding from externalized properties**:

| Case | What Are Parameter Names Used For? |
| --- | --- |
| `@ConfigurationProperties` constructor binding | Maps parameters to property keys |
| Regular constructor injection | Can assist in selecting among same-type beans when bean names match |
| Calling a Java constructor with `new` | Does not require Spring to discover parameter names |
| Parsing `application.yml` | Does not depend on Java class compiler flags |

When selecting one bean among several of the same type, `@Qualifier` or explicit bean-name design is generally more reliable than relying solely on parameter names.

## 19. Why Does Running from the IDE Succeed While Running the JAR Fails?

A common phenomenon:

~~~text
Running main class from IDE: succeeds.
Packaging via CI / Maven / Gradle: fails at startup.
Or vice versa.
~~~

The cause can be **two compilation paths using different settings**:

- The IDE uses its own compiler with parameter-name retention enabled.
- A Maven or Gradle task does not enable `-parameters`.
- A dependency module was pre-built using an older configuration.
- CI uses a different JDK, Gradle, Maven parent, or compiler plugin version.
- A cached JAR contains `.class` files compiled before the flag was added.
- A custom source-generation or compilation task does not inherit the flag.
- The IDE runs from `out/production` while the JAR packages bytecode from `target/classes` or `build/classes/java/main`.

The proper approach:

1. Identify **which artifact** is actually being launched.
2. Identify which JAR/module the `@ConfigurationProperties` class is loaded from.
3. Inspect `MethodParameters` on **the class inside that artifact**.
4. Verify the build system actually invokes the Java compiler with `-parameters`.
5. Fix the build configuration in the module owning the source.
6. Clean, rebuild dependencies/modules, and re-run the exact same artifact.

Do not just toggle "Store information about method parameters" in the IDE if CI produces the production artifact. The source of truth must be the repository's reproducible build.

## 20. How to Inspect a JAR or External Library

For a Java application packaged as a JAR, classes inside the archive may sit at different paths than in `target/classes`. A Spring Boot executable JAR typically packages application classes under a specific layout (such as `BOOT-INF/classes`) and dependencies in a libs folder.

You can list JAR contents:

~~~bash
jar tf target/app.jar
~~~

Then locate the target class and extract it to a temporary directory for bytecode inspection if needed. For regular library JARs, you can use `javap -classpath <library.jar> -v -p ...` directly when the classpath and class layout allow.

What matters is not the specific command, but **inspecting bytecode from the exact artifact executed at runtime**. A `shared-config` module published to an internal repository might differ from the `shared-config` source currently in your working tree.

If a third-party dependency was compiled without metadata and you do not own its source/build, adding `-parameters` to your main module will not retroactively add parameter names to that dependency. You need a properly compiled dependency version, a library update, or an alternative binding design.

## 21. Errors Commonly Mistaken for Missing -parameters

Not every `Failed to bind properties` error is a compiler issue. Categorize them:

| Symptom | Cause Worth Checking |
| --- | --- |
| No `GatewayProperties` bean exists | Missing `@EnableConfigurationProperties` or scan |
| Binder reports constructor parameter names could not be resolved | `-parameters` metadata, class kind, compiled artifact |
| `gateway.timeout` does not bind | Wrong prefix/key, missing property source, different Java name |
| `"many"` fails to bind to `int` | Conversion error, not parameter-name metadata |
| `-1` is invalid under `@Min(1)` | Validation |
| Nested object is null | Missing nested values or missing default/validation |
| Multiple same-type beans make constructor injection ambiguous | Needs `@Qualifier` or proper precedence |
| IDE runs fine yet CI fails | Different compiler args/artifact/dependency |
| `-parameters` is present yet constructor binding is not used | Bean may be created via `@Component`/`@Bean`, wrong registration |
| Class has multiple constructors with unclear choice | Needs explicit constructor-binding selection |

An easily confused example:

~~~yaml
gateway:
  max-retries: "several"
~~~

Java:

~~~java
public GatewayProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxRetries) {
    // ...
}
~~~

Even if the class has `-parameters`, the Binder cannot convert `"several"` into an `int` under normal rules. Fix the data or define a custom converter; adding the compiler flag again will not help.

Conversely, if the property is valid:

~~~yaml
gateway:
  max-retries: 4
~~~

yet the Binder cannot determine constructor parameter names, the failure occurs before key matching and conversion; inspecting bytecode is then the right direction.

## 22. Do Not Try to Fix This by Adding @Component

A dangerous "fix":

~~~java
@Component
@ConfigurationProperties(prefix = "gateway")
public final class GatewayProperties {
    public GatewayProperties(
            URI baseUrl, Duration connectTimeout, int maxRetries) {
        // ...
    }
}
~~~

`@Component` can cause Spring to instantiate the object through regular dependency injection. Constructor arguments like `URI`, `Duration`, and `int` are **property values**, not pre-registered Spring beans. The error may simply shift from "cannot bind property" to "cannot autowire dependency."

Use:

~~~java
@ConfigurationProperties(prefix = "gateway")
public record GatewayProperties(
        URI baseUrl,
        Duration connectTimeout,
        int maxRetries
) {}
~~~

and register it:

~~~java
@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(GatewayProperties.class)
class GatewayConfiguration {}
~~~

**Proper registration** and **parameter-name metadata** are two independent requirements. Do not use an annotation from one mechanism to mask an issue in the other.

## 23. Is -parameters Needed When Using Setter Binding?

A mutable JavaBean-style class:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "legacy.client")
public class LegacyClientProperties {

    private int retries = 3;

    public int getRetries() {
        return retries;
    }

    public void setRetries(int retries) {
        this.retries = retries;
    }
}
~~~

When using setter binding properly, the Binder primarily relies on **JavaBean property names** (getters/setters), not parameter names of a multi-argument constructor. Thus, missing constructor parameter names are not the central issue for this pattern.

However:

- The project may still need `-parameters` for other framework features.
- You should not turn an immutable properties class into a mutable one just to "avoid a compiler flag" when constructor binding is the right design.
- Getters and setters must follow JavaBean conventions so the Binder recognizes them.
- Types with many fields still need proper validation and defaults.

Registration for JavaBean types can differ from constructor-bound records, yet both aim for typed configuration. Choose based on immutability needs, validation, and codebase style—not to dodge a build issue that can be fixed at the root.

## 24. @Name and Keys That Cannot Be Used as Java Identifiers

Sometimes a property key matches a Java keyword, for example:

~~~yaml
service:
  import: "catalog"
~~~

You cannot declare a Java constructor parameter named `import` because `import` is a reserved keyword. Spring Boot provides `@Name` in the binding API to specify the property name to use instead of the Java parameter name:

~~~java
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.context.properties.bind.Name;

@ConfigurationProperties(prefix = "service")
public record ServiceProperties(
        @Name("import") String importValue
) {}
~~~

This is a special case **intentionally mapping a name that cannot be written as a Java identifier**. Do not overuse `@Name` on every parameter to bypass `-parameters` for the rest of the application.

If the configuration naming is under your project's control, it is best to pick clear keys compatible with naming conventions such as `service.import-mode` and use parameter `importMode`. `@Name` is valuable when an existing property contract or mandatory key cannot be changed.

## 25. Lombok, Code Generation, and Generated Constructors

With Lombok or code generators, the source file might contain only fields:

~~~java
@Getter
@RequiredArgsConstructor
public class GeneratedLikeProperties {
    private final String name;
    private final int maxRetries;
}
~~~

The actual constructor is generated by the tool during compilation. If that class is used for constructor binding, what matters is still whether **the bytecode of the used constructor** has matching parameter names.

Some risks:

- The IDE's annotation processor differs from the Maven/Gradle build.
- The generated constructor has an unintended signature.
- An extra constructor prevents the Binder from inferring a single constructor.
- A plugin or build step generates sources after compiler flags were configured on another task.
- A published dependency contains bytecode out of sync with the source open in the IDE.

Therefore, do not treat "uses Lombok" or "uses record" as proof that `-parameters` is unnecessary across all cases. Identify which code generator and compiler produce the final class.

When developing typed externalized configuration, a record or a small hand-written constructor class is often easier to inspect than a stack of constructor-generating annotations.

## 26. Maven, Gradle, IDE, and CI: A Single Build Contract

A well-maintained project avoids letting each environment produce different bytecode.

| Build Location | What to Ensure |
| --- | --- |
| Local Maven | `maven-compiler-plugin` / parent supplies `-parameters` |
| Local Gradle | `JavaCompile` tasks have `-parameters` |
| IDE | Ideally delegate build/run to Maven/Gradle or sync compiler settings |
| CI | Uses the same wrapper, toolchain, and version-controlled build logic |
| Library module | Compiles itself with the flag if it contains constructor-bound properties |
| Packaging/release | Verify the latest artifact contains the right classes |
| Unit/integration tests | Have tests using the real Binder, not only `new Properties(...)` |

In a multi-module project, setting the flag in one place **only affects tasks/modules that actually inherit it**. Inspect build conventions alongside the dependency graph rather than inferring from a root POM or root Gradle script.

### Why Is a Clean Build Helpful?

Incremental builds can reuse class files compiled before you updated plugin settings. After adding `-parameters`, clean and recompile the modules containing configuration classes. Then inspect `MethodParameters` in the newly built artifact.

You do not need to wipe system-wide caches blindly. The goal is ensuring the affected classes are genuinely recompiled with the new setting.

## 27. Distinguishing Compiler Flags from Annotation Processors

Another confusion:

- `-parameters` is a **javac flag** that emits parameter-name metadata.
- `spring-boot-configuration-processor` is an **annotation processor** typically used to generate configuration metadata for tools and IDE key autocompletion.

For example, the `spring-boot-configuration-processor` dependency can generate `META-INF/spring-configuration-metadata.json` for property autocompletion and documentation, yet **it does not replace `MethodParameters` metadata on Java constructors**.

Conversely, having `-parameters` does not generate configuration metadata JSON for IDEs if the project does not configure that annotation processor.

These are two separate metadata layers:

~~~text
javac -parameters
      |
      v
.class -> MethodParameters
      |
      v
Reflection / Spring Binder can observe constructor parameter names

spring-boot-configuration-processor
      |
      v
META-INF/spring-configuration-metadata.json
      |
      v
IDE can autocomplete key names, descriptions, types
~~~

Do not attempt to fix a startup failure caused by missing constructor parameter names merely by adding the `spring-boot-configuration-processor` dependency.

## 28. Distinguishing -parameters from -D... or Runtime Options

A command like:

~~~bash
java -Dspring.profiles.active=prod -jar app.jar
~~~

sets a **Java system property** for the Spring Environment. It alters runtime configuration per profile.

The command:

~~~bash
javac -parameters ...
~~~

changes **metadata written by the compiler into class files**. The two are completely different.

Non-equivalent changes:

| Change Made | Can Fix Missing Constructor Parameter Names? |
| --- | --- |
| Add `-parameters` to `javac` and rebuild | Yes, for classes needing metadata |
| Pass `--spring.profiles.active=prod` at runtime | No |
| Edit `application.yml` | No, unless the actual bug is a property key/value |
| Add `spring-boot-configuration-processor` | Does not replace the compiler flag |
| Add `@Component` to a record | No; may introduce a different registration error |
| Enable Java debug symbols `-g` | Not a reliable substitute |
| Move `getProperty` to `@Value` in another service | Does not fix constructor metadata on typed properties |

Remember that `-parameters` applies to **compiled classes**, not to the entire JVM process after launch.

## 29. A Complete Module-Level Maven Example

Suppose a `config-model` module contains `GatewayProperties` and does not use the starter parent:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
                             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <groupId>example</groupId>
    <artifactId>config-model</artifactId>
    <version>1.0.0</version>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <maven.compiler.parameters>true</maven.compiler.parameters>
    </properties>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.14.1</version>
                <configuration>
                    <parameters>true</parameters>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

The POM excerpt above is an **illustrative build-section sample**, not a complete configuration with dependencies to compile every Spring Boot example. In a real project, appropriate dependencies and parent/plugin versions are needed. `release=17` is merely an example for a Spring Boot 3.x project on Java 17; match your project's Java target.

Setting both `maven.compiler.parameters=true` and `<parameters>true</parameters>` is **redundant**; you do not need both. Pick one style matching your conventions. The sample intentionally shows it can live in either the property or plugin configuration, while real builds should keep one clear path.

After compiling, inspect:

~~~bash
./mvnw clean compile
javap -classpath target/classes -v -p example.gateway.GatewayProperties
~~~

If the properties class lives in another module, run the command for that module and point to that module's classpath.

## 30. A Multi-Module Gradle Example

Suppose the layout is:

~~~text
root/
  settings.gradle
  build.gradle
  config-model/
    build.gradle
    src/main/java/example/gateway/GatewayProperties.java
  web-app/
    build.gradle
    src/main/java/example/Application.java
~~~

In `config-model/build.gradle`:

~~~groovy
plugins {
    id 'java-library'
}

tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

In `web-app/build.gradle`, the app can apply the Spring Boot plugin and depend on the configuration module:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '<spring-boot-version>'
}

dependencies {
    implementation project(':config-model')
}
~~~

This example illustrates that **the flag belongs where the class is compiled**. If `GatewayProperties` lives in `config-model`, `web-app`'s configuration cannot retroactively add metadata to classes already compiled by `config-model`.

In real projects, Gradle plugin/dependency versions, repositories, and conventions are often centralized. The goal here is clearly seeing each module's responsibility rather than providing a full build skeleton.

## 31. Short Diagnostic Checklist in Order

When encountering a constructor-binding failure, check:

1. **Source:** does the properties class have the right `@ConfigurationProperties(prefix = ...)`?
2. **Registration:** is there `@EnableConfigurationProperties` or `@ConfigurationPropertiesScan`, and is that configuration class loaded?
3. **Constructor:** does the class have one clear constructor, or multiple constructors needing `@ConstructorBinding`?
4. **Parameter names:** do source parameter names match the properties to bind?
5. **Bytecode:** does `javap -v -p` show the corresponding `MethodParameters`?
6. **Build task:** does the module owning the class enable `-parameters`?
7. **Artifact:** are you running the newly built JAR/classes or a stale dependency?
8. **Property source:** are valid keys present in active profiles and config imports?
9. **Conversion:** can values convert to `int`, `Duration`, `URI`, enum, etc.?
10. **Validation:** do bound values satisfy all constraints?
11. **CI/IDE:** are local and pipeline compiler args consistent?
12. **Tests:** is there a test that actually instantiates the configuration-properties bean via the Binder?

Decision tree:

~~~text
Service fails to inject Properties?
    |
    +-- Yes --> Check registration and context composition
    |
    +-- No, yet binding fails
         |
         +-- Binder cannot determine constructor parameter names?
         |      |
         |      +-- Yes --> Check -parameters and bytecode
         |
         +-- Names present yet keys do not match?
         |      |
         |      +-- Yes --> Check prefix/naming/source
         |
         +-- Value cannot convert to Java type?
         |      |
         |      +-- Yes --> Fix data/converter
         |
         +-- Value has valid type yet violates constraint?
                |
                +-- Yes --> Fix validation/config contract
~~~

## 32. Practice Exercise

**Requirement:** create an immutable properties object representing HTTP client configuration; use constructor binding and verify the class file retains parameter names.

### Step 1 — Write YAML

~~~yaml
pricing:
  endpoint: "https://pricing.example.invalid/v1"
  timeout: 2s
  retry-count: 3
~~~

### Step 2 — Write a Regular Java Class

~~~java
package example.pricing;

import java.net.URI;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "pricing")
public final class PricingProperties {

    private final URI endpoint;
    private final Duration timeout;
    private final int retryCount;

    public PricingProperties(
            URI endpoint, Duration timeout, int retryCount) {
        this.endpoint = endpoint;
        this.timeout = timeout;
        this.retryCount = retryCount;
    }

    public URI getEndpoint() {
        return endpoint;
    }

    public Duration getTimeout() {
        return timeout;
    }

    public int getRetryCount() {
        return retryCount;
    }
}
~~~

### Step 3 — Register

~~~java
package example.pricing;

import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Configuration;

@Configuration(proxyBeanMethods = false)
@EnableConfigurationProperties(PricingProperties.class)
class PricingConfiguration {}
~~~

### Step 4 — Enable the Compiler Flag

With Maven:

~~~xml
<properties>
    <maven.compiler.parameters>true</maven.compiler.parameters>
</properties>
~~~

Or Gradle Groovy DSL:

~~~groovy
tasks.withType(JavaCompile).configureEach {
    options.compilerArgs += ['-parameters']
}
~~~

### Step 5 — Clean Compile and Inspect the Class

Maven:

~~~bash
./mvnw clean compile
javap -classpath target/classes -v -p example.pricing.PricingProperties
~~~

Observe whether the constructor's `MethodParameters` section contains `endpoint`, `timeout`, and `retryCount`.

### Step 6 — Bind in a Spring Context

Start an application that loads `PricingConfiguration` or write an `ApplicationContextRunner` test supplying `pricing.*` keys. Read the `PricingProperties` bean and verify:

~~~text
endpoint   = https://pricing.example.invalid/v1
timeout    = 2 seconds
retryCount = 3
~~~

### Step 7 — Change One Factor at a Time

Try in order:

- Remove `-parameters` from the module containing `PricingProperties`, clean compile, observe parameter names in bytecode and binding outcome.
- Keep `-parameters` yet change YAML to `retry-count: "many"`; identify the error category.
- Change `@ConfigurationProperties(prefix = "pricing")` to another prefix without editing YAML; observe the outcome.
- Remove `@EnableConfigurationProperties` without adding another scan; locate the bean-registration error.
- Convert the class to a record, then compare record metadata with a regular class.

From these scenarios, learn to separate **compiler metadata**, **bean registration**, **binding data**, and **validation**.

## 33. Takeaways

When using constructor binding for `@ConfigurationProperties`, Spring Boot must determine constructor parameter names to map `baseUrl` to `base-url`, `retryCount` to `retry-count`, and other configuration values. For regular Java classes, **`javac -parameters`** stores parameter names in `MethodParameters` metadata inside `.class` files so reflection can read them.

Spring Boot's Maven parent or Spring Boot's Gradle plugin typically configures this option; projects using BOMs, custom parents, multi-module layouts, libraries, or custom compile pipelines must confirm the flag on **the module producing the bytecode**. Maven can use `<parameters>true</parameters>`; Gradle can add `"-parameters"` to `JavaCompile`; `javap -v -p` and reflection verify the final artifact.

**Do not confuse `-parameters` with `@ConstructorBinding`, `@EnableConfigurationProperties`, `@DefaultValue`, or annotation processors.** Each mechanism solves a distinct problem: selecting constructors, registering beans, supplying defaults, emitting metadata, and converting properties.

References: Spring Boot Reference Guide — Externalized Configuration (Constructor Binding); Apache Maven Compiler Plugin — parameters; Gradle CompileOptions — compilerArgs; Spring Framework Reference — Annotation-based Autowiring.
