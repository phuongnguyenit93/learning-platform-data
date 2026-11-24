# Inspecting Registration Resources and Implementation Classes in the Distributed JAR

## 1. Goal and Scope

A Spring Boot library can compile cleanly yet still fail to have its auto-configuration recognized by applications. The root cause does not necessarily lie in annotations or bean logic: the registration file may be missing from the JAR, placed at the wrong path, contain a wrong class name, get overwritten when packaging multiple dependencies, or the implementation classes may not be in the artifact/runtime classpath as expected.

When inspecting an auto-configuration library, verify at least four layers of evidence:

1. **Registration resource:** Does the distributed JAR contain `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` and does it list the exact auto-configuration classes?
2. **Compiled classes:** Are the listed classes and the implementations they reference actually inside the JAR or runtime dependencies?
3. **Artifact structure:** Are you inspecting a plain library JAR, an executable Spring Boot JAR with nested dependency JARs, or a shaded/uber JAR with merged contents?
4. **Real-world usability:** Does a consuming application using that exact distributed JAR discover the auto-configuration and create beans when conditions match?

This lesson uses **Spring Boot 3.3.13, Java 17+, and Maven** for examples. JAR inspection commands use the JDK `jar` tool; PowerShell examples are also provided for Windows. Gradle and shaded JAR packaging are also covered.

**Principle:** seeing files/classes in `target/classes` only proves compilation inside the workspace. You must inspect the packaged artifact and test a consuming application using that artifact to verify the distribution path.

## 2. Auto-Configuration Registration Resources in Spring Boot 3

### 2.1. Required Path

Spring Boot 3 locates the list of auto-configurations in the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

This is a UTF-8 text file where each line contains the **fully qualified class name** of an auto-configuration. For example:

```text
# Auto-configurations provided by the Acme Greeting library
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
com.acme.greeting.autoconfigure.GreetingWebAutoConfiguration
```

Rules to remember:

- Class names must match the compiled package and class name.
- Each class sits on its own line; `#` may be used for comments.
- If an auto-configuration is a nested class, use `$` between the outer and nested classes, such as `com.acme.Outer$NestedAutoConfiguration`.
- Auto-configurations must be loaded by declaring them in the imports file. Placing a class in a component-scanned package is not the recommended registration mechanism.
- Auto-configurations should not enable `@ComponentScan` to scan additional components. Use `@Import` for specific needed configurations.
- One imports file can list multiple auto-configurations; do not create a separate file per class.

### 2.2. Registered Classes Must Be Valid Auto-Configurations

Example:

```java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.DefaultGreetingService;
import com.acme.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
    prefix = "acme.greeting",
    name = "enabled",
    havingValue = "true"
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
```

This is the illustrative class packaged into the sample JAR in Section 6. When inspecting the artifact, verify all of:

- `GreetingAutoConfiguration.class` exists.
- `GreetingService.class` and `DefaultGreetingService.class` exist in the JAR or dependencies required by the auto-configuration.
- The imports file contains the exact name `com.acme.greeting.autoconfigure.GreetingAutoConfiguration`.
- Conditions and bean methods can be processed by Spring when an application consumes the JAR.

**Do not confuse registration with activation conditions:** the imports file puts the class into the candidate set; `@ConditionalOnClass`, `@ConditionalOnProperty`, `@ConditionalOnBean`, and other conditions can still prevent the configuration from applying. Seeing a class in the imports file does not guarantee its beans will appear.

### 2.3. Nested Class Names and Binary Names

If an imports file declares a nested auto-configuration:

```java
@AutoConfiguration
public class AcmeAutoConfiguration {

    @Configuration(proxyBeanMethods = false)
    static class WebConfiguration {
    }
}
```

The nested class's binary name is `com.acme.AcmeAutoConfiguration$WebConfiguration`, not `com.acme.AcmeAutoConfiguration.WebConfiguration`. However, nested configurations imported by an outer auto-configuration usually do not need to be listed as separate auto-configuration candidates. Only list classes genuinely designed as auto-configuration entry points.

When inspecting with `jar tf`, class paths use `/` and nested class parts still use `$`, for example:

```text
com/acme/AcmeAutoConfiguration.class
com/acme/AcmeAutoConfiguration$WebConfiguration.class
```

## 3. Other `META-INF` Resources and Their Purposes

A Spring Boot JAR may contain multiple metadata files. They do not replace one another.

| Resource | Purpose | Is it the auto-configuration registration list? |
| --- | --- | --- |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` | Lists auto-configuration candidates | **Yes** |
| `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements` | Maps old auto-configuration classes to replacements when renaming packages/classes | No; supports replacement/migration |
| `META-INF/spring-autoconfigure-metadata.properties` | Condition metadata generated by the annotation processor so Boot filters unmatched auto-configurations early, improving startup | No; supports optimization |
| `META-INF/spring-configuration-metadata.json` | Configuration metadata for IDEs to suggest properties, types, descriptions, and default values | No; supports configuration/IDEs |
| `META-INF/spring.factories` | Registers certain other factories/extension points by key | No longer registers `EnableAutoConfiguration` in Boot 3 |

### 3.1. `spring-autoconfigure-metadata.properties` Is Optional

Spring Boot provides the `spring-boot-autoconfigure-processor` annotation processor to collect condition metadata. When `META-INF/spring-autoconfigure-metadata.properties` is generated, Boot can use that metadata to **eagerly filter** non-matching auto-configurations before full processing, improving startup time.

Distinctions to keep clear:

- `AutoConfiguration.imports` is the candidate list.
- `spring-autoconfigure-metadata.properties` is metadata assisting early candidate filtering.
- The absence of this metadata file **does not mean** the imports file is unread or the auto-configuration cannot run.
- When building a library, configure the annotation processor per Spring Boot's documentation to generate metadata; then verify the resource is packaged into the JAR.

### 3.2. `spring-configuration-metadata.json` Serves Property Metadata

If the library provides `@ConfigurationProperties`, the corresponding annotation processor can generate:

```text
META-INF/spring-configuration-metadata.json
```

This file helps IDEs display property suggestions and descriptions. It does not list auto-configuration classes. When an IDE fails to suggest properties, inspect this file and `spring-boot-configuration-processor`; when an auto-configuration is not discovered, inspect `AutoConfiguration.imports` first.

### 3.3. `spring.factories` and Changes Since Spring Boot 2.7/3.0

Previously, auto-configurations were typically registered in `META-INF/spring.factories` under the key:

```properties
org.springframework.boot.autoconfigure.EnableAutoConfiguration=\
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
```

Spring Boot 2.7 introduced the new imports file while still supporting the legacy mechanism for compatibility. Spring Boot 3 removed auto-configuration registration via the `org.springframework.boot.autoconfigure.EnableAutoConfiguration` key in `spring.factories`; other `spring.factories` keys can still be used for their corresponding extension points.

Therefore:

- For libraries targeting only Spring Boot 3.x, register auto-configurations in `AutoConfiguration.imports`.
- If a library must support both Spring Boot 2.7 and 3.x, keeping registration in both locations may be needed per migration guidance; Boot 2.7 deduplicates entries appearing in both.
- Do not delete all of `spring.factories` just because auto-configuration moved to the imports file. That file may still register `FailureAnalyzer`, `ApplicationListener`, or other extension points.
- Verify the exact Spring Boot versions the library officially supports before concluding the old resource is no longer needed.

### 3.4. `AutoConfiguration.replacements` When Renaming Classes

If you rename the package or class of an already-published auto-configuration, the old class may be referenced by `before`, `after`, `exclude`, or external configs. Spring Boot supports the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.replacements
```

Example:

```text
com.acme.greeting.autoconfigure.GreetingAutoConfiguration=com.acme.greeting.autoconfigure.core.GreetingAutoConfiguration
```

The imports file must be updated to reference only the replacement class. The replacements resource helps Boot resolve references to the old name in supported contexts; it does not replace the imports file and will not automatically register the new class if the imports file lacks it.

## 4. Inspecting Artifacts: Plain Library JAR vs. Executable Boot JAR

### 4.1. Plain Library JAR

A typical Maven/Gradle library JAR looks like:

```text
greeting-autoconfigure-1.0.0.jar
├── META-INF/
│   ├── MANIFEST.MF
│   ├── spring/
│   │   └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
│   └── spring-autoconfigure-metadata.properties
└── com/
    └── acme/
        └── greeting/
            ├── GreetingService.class
            ├── DefaultGreetingService.class
            └── autoconfigure/
                └── GreetingAutoConfiguration.class
```

This is an example layout; the metadata file may be absent if no processor generated it. When opening a plain JAR, resources and classes sit directly at the archive root.

### 4.2. Executable Spring Boot JAR

An executable JAR repackaged by the Spring Boot plugin has a different layout:

```text
consumer-app-1.0.0.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   └── com/example/consumer/ConsumerApplication.class
    └── lib/
        ├── spring-boot-autoconfigure-3.3.13.jar
        ├── spring-boot-starter-3.3.13.jar
        └── greeting-autoconfigure-1.0.0.jar
```

Inside an executable JAR:

- Application classes sit under `BOOT-INF/classes/`.
- Dependency JARs sit intact nested inside `BOOT-INF/lib/`.
- The library's `AutoConfiguration.imports` may reside **inside the nested JAR** `BOOT-INF/lib/greeting-autoconfigure-1.0.0.jar`, rather than directly at the root of the executable JAR.
- Therefore, not seeing the imports file at the executable JAR root is insufficient to conclude the library was packaged incorrectly. You must locate and inspect the nested JAR.

**Distinguish packaging structures:** `jar tf app.jar` lists only entries of the outer archive. It does not unpack nested JARs to display every class/resource inside them.

### 4.3. Shaded/Uber JAR

Maven Shade or Gradle Shadow can merge classes and resources from multiple JARs into a single archive. When multiple dependencies contain a resource at the same path—such as multiple `AutoConfiguration.imports` files—the packaging plugin must **append/merge** their contents properly.

If one resource is overwritten by another dependency's file, some auto-configurations can vanish from the final JAR even though every individual source JAR was valid. When using Shade/Shadow, configure a transformer/append rule for the imports file; never assume same-named resources are automatically merged.

## 5. JAR Inspection Workflow Using the JDK

The steps below apply to the plain library JAR in Section 6.

### 5.1. Build the Artifact from Source

In the library module directory:

```bash
mvn clean package
```

Maven produces the JAR in `target/`. Check the exact artifact/version being released so you do not inspect a stale JAR left over from an earlier build. `clean` removes old outputs before packaging.

If another application will consume the artifact through the local Maven repository:

```bash
mvn clean install
```

`install` installs the newly built artifact into the local repository. This step is required for the independent consumer example in Section 6.

### 5.2. List All Entries

```bash
jar tf target/greeting-autoconfigure-1.0.0.jar
```

Filter important entries on Windows PowerShell:

```powershell
jar tf target/greeting-autoconfigure-1.0.0.jar |
    Select-String 'AutoConfiguration.imports|GreetingAutoConfiguration.class|GreetingService.class|DefaultGreetingService.class|spring-autoconfigure-metadata'
```

Or use `findstr` in Windows Command Prompt:

```bat
jar tf target\greeting-autoconfigure-1.0.0.jar | findstr /i "AutoConfiguration.imports GreetingAutoConfiguration.class GreetingService.class DefaultGreetingService.class spring-autoconfigure-metadata"
```

Expected key entries:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
com/acme/greeting/GreetingService.class
com/acme/greeting/DefaultGreetingService.class
com/acme/greeting/autoconfigure/GreetingAutoConfiguration.class
```

If the annotation processor is configured, you may also see:

```text
META-INF/spring-autoconfigure-metadata.properties
```

Entry order in the JAR is not a contract; what matters is that all required entries exist.

### 5.3. Read the Imports File Contents from the JAR

You can extract the resource individually with JDK `jar`. In PowerShell, from the module directory:

```powershell
New-Item -ItemType Directory -Force target\inspect | Out-Null
Push-Location target\inspect
jar xf ..\greeting-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
Get-Content META-INF\spring\org.springframework.boot.autoconfigure.AutoConfiguration.imports
Pop-Location
```

Expected output:

```text
# Acme Greeting auto-configuration
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
```

On macOS/Linux, if `unzip` is available, you can read it directly without extracting to disk:

```bash
unzip -p target/greeting-autoconfigure-1.0.0.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Cross-check class names in the file against compiled packages/classes. Check casing, dots, `$` characters for nested classes, and unintended whitespace.

### 5.4. Verify Implementation Classes with `javap`

`javap` is the JDK tool for inspecting signatures and bytecode of compiled classes. Example:

```bash
javap -classpath target/greeting-autoconfigure-1.0.0.jar -p com.acme.greeting.autoconfigure.GreetingAutoConfiguration
javap -classpath target/greeting-autoconfigure-1.0.0.jar -p com.acme.greeting.GreetingService
javap -classpath target/greeting-autoconfigure-1.0.0.jar -p -c com.acme.greeting.DefaultGreetingService
```

Flags:

- `-p`: shows non-public members as well.
- `-c`: shows method bytecode.
- `-v`: shows more details, including annotations and the constant pool when needed.

Example checking annotations on the auto-configuration:

```bash
javap -classpath target/greeting-autoconfigure-1.0.0.jar -v com.acme.greeting.autoconfigure.GreetingAutoConfiguration
```

`javap` is not a decompiler that reconstructs original Java source. If you need to read source, locate the matching `-sources.jar` and verify the version/class matches the binary under inspection. For nested classes, use the binary name with `$`, for example:

```powershell
javap -classpath target\greeting-autoconfigure-1.0.0.jar -p 'com.acme.AcmeAutoConfiguration$WebConfiguration'
```

### 5.5. Check External Dependency JARs

Plain library JARs usually **do not embed all of their dependencies**. If `GreetingAutoConfiguration` references classes from another artifact, inspect the dependency graph:

```bash
mvn dependency:tree
```

Or filter for the artifact of interest:

```bash
mvn dependency:tree -Dincludes=org.springframework.boot:spring-boot-autoconfigure
```

A class may not sit inside `greeting-autoconfigure-1.0.0.jar` yet still be valid if provided by a runtime dependency. Conversely, a class present on the compile classpath whose dependency has the wrong scope or is excluded from runtime can cause errors when the application runs. Verify scopes/configurations and deployed artifacts.

## 6. Complete Example: Building the Library and Testing from a Consuming Application

This example uses **two independent Maven projects**. The `greeting-autoconfigure` project builds the library JAR. The `consumer` project resolves that dependency from the local Maven repository and boots Spring Boot to prove the imports file inside the JAR is discovered.

### 6.1. Directory Structure

```text
jar-inspection-demo/
├── greeting-autoconfigure/
│   ├── pom.xml
│   └── src/main/
│       ├── java/com/acme/greeting/
│       │   ├── GreetingService.java
│       │   ├── DefaultGreetingService.java
│       │   └── autoconfigure/GreetingAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── consumer/
    ├── pom.xml
    └── src/
        ├── main/java/com/example/consumer/ConsumerApplication.java
        └── test/java/com/example/consumer/GreetingPackagingTests.java
```

### 6.2. Project `greeting-autoconfigure/pom.xml`

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

    <groupId>com.acme</groupId>
    <artifactId>greeting-autoconfigure</artifactId>
    <version>1.0.0</version>
    <name>greeting-autoconfigure</name>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <annotationProcessorPaths>
                        <path>
                            <groupId>org.springframework.boot</groupId>
                            <artifactId>spring-boot-autoconfigure-processor</artifactId>
                            <version>3.3.13</version>
                        </path>
                    </annotationProcessorPaths>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

The processor generates `META-INF/spring-autoconfigure-metadata.properties` when suitable condition metadata exists. Even if you only want to verify the imports file, the registration resource remains the primary item to check.

### 6.3. Interface `GreetingService.java`

Path `src/main/java/com/acme/greeting/GreetingService.java`:

```java
package com.acme.greeting;

public interface GreetingService {
    String greet(String name);
}
```

### 6.4. Implementation `DefaultGreetingService.java`

Path `src/main/java/com/acme/greeting/DefaultGreetingService.java`:

```java
package com.acme.greeting;

public final class DefaultGreetingService implements GreetingService {

    @Override
    public String greet(String name) {
        return "Hello, " + name;
    }
}
```

### 6.5. Auto-Configuration `GreetingAutoConfiguration.java`

Path `src/main/java/com/acme/greeting/autoconfigure/GreetingAutoConfiguration.java`:

```java
package com.acme.greeting.autoconfigure;

import com.acme.greeting.DefaultGreetingService;
import com.acme.greeting.GreetingService;
import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnClass;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnClass(GreetingService.class)
@ConditionalOnProperty(
    prefix = "acme.greeting",
    name = "enabled",
    havingValue = "true"
)
public class GreetingAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean(GreetingService.class)
    public GreetingService greetingService() {
        return new DefaultGreetingService();
    }
}
```

The auto-configuration has two groups of conditions:

- `GreetingService` class must be present on the classpath.
- Property `acme.greeting.enabled` must be `true`.
- If the application already declared a `GreetingService` bean, the default bean backs off.

### 6.6. Registration Resource

Create file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Content:

```text
# Acme Greeting auto-configuration
com.acme.greeting.autoconfigure.GreetingAutoConfiguration
```

The name in the file must match the compiled package/class in Section 6.5 exactly.

### 6.7. Consumer Project `consumer/pom.xml`

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
    <artifactId>consumer</artifactId>
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
        </plugins>
    </build>
</project>
```

Because `consumer` inherits from `spring-boot-starter-parent`, declare `spring-boot-maven-plugin` under `build/plugins`; the parent already configures the `repackage` execution for the plugin, so there is no need to repeat the goal in this example. See [Spring Boot 3.3 Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html).

Keeping two independent projects ensures `consumer` resolves the artifact installed in the local Maven repository. Do not place them in the same Maven reactor when the lab's goal is verifying the packaged JAR used by a consumer.

### 6.8. `ConsumerApplication.java`

Path `src/main/java/com/example/consumer/ConsumerApplication.java`:

```java
package com.example.consumer;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class ConsumerApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConsumerApplication.class, args);
    }
}
```

The application package is `com.example.consumer`; the auto-configuration resides in `com.acme.greeting.autoconfigure`. The application's default component scan does not scan the library package; auto-configuration is discovered through the imports file.

### 6.9. Tests Verifying Resources and Beans from the JAR

Path `src/test/java/com/example/consumer/GreetingPackagingTests.java`:

```java
package com.example.consumer;

import java.io.BufferedReader;
import java.io.IOException;
import java.io.InputStreamReader;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.Enumeration;
import java.util.List;

import com.acme.greeting.GreetingService;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
    classes = ConsumerApplication.class,
    properties = "acme.greeting.enabled=true"
)
class GreetingPackagingTests {

    private static final String IMPORTS_RESOURCE =
        "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports";

    private static final String AUTO_CONFIGURATION =
        "com.acme.greeting.autoconfigure.GreetingAutoConfiguration";

    @Autowired
    private GreetingService greetingService;

    @Test
    void autoConfigurationIsDiscoveredFromDependencyJar() {
        assertThat(greetingService).isNotNull();
        assertThat(greetingService.getClass().getName())
            .isEqualTo("com.acme.greeting.DefaultGreetingService");
        assertThat(greetingService.greet("Ada"))
            .isEqualTo("Hello, Ada");
    }

    @Test
    void importsResourceContainsAutoConfigurationClass() throws IOException {
        ClassLoader classLoader =
            Thread.currentThread().getContextClassLoader();

        Enumeration<URL> resources =
            classLoader.getResources(IMPORTS_RESOURCE);

        List<URL> locations = Collections.list(resources);
        assertThat(locations).isNotEmpty();

        boolean found = false;

        for (URL location : locations) {
            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(
                        location.openStream(),
                        StandardCharsets.UTF_8
                    ))) {

                if (reader.lines()
                        .map(String::trim)
                        .anyMatch(AUTO_CONFIGURATION::equals)) {
                    found = true;
                    break;
                }
            }
        }

        assertThat(found).isTrue();
    }
}
```

The two tests verify two distinct pieces of evidence:

1. **Resource presence:** the class loader finds at least one imports resource containing an entry matching the auto-configuration name.
2. **Actual discovery:** Spring Boot boots the consumer context, creates the bean from auto-configuration, and invokes the implementation.

Iterating over all resource URLs is intentional: multiple dependency JARs may each supply an `AutoConfiguration.imports` file. Do not assume the class loader finds only a single resource.

### 6.10. Build and Run Tests in the Proper Order

First, build and install the library JAR:

```bash
cd greeting-autoconfigure
mvn clean install
```

Next, run the consumer in its separate project directory:

```bash
cd ../consumer
mvn clean test
```

Expected result: Maven `BUILD SUCCESS`, with both tests in `GreetingPackagingTests` passing. If tests cannot find the bean or resource, inspect the JAR installed in the local repository, the dependency tree, and the imports file contents inside the artifact.

After tests pass, package the consumer into an executable Boot JAR:

```bash
mvn package
```

Inspect the packaged dependencies:

```bash
jar tf target/consumer-1.0.0.jar
```

On Windows, you can filter entries:

```powershell
jar tf target\consumer-1.0.0.jar |
    Select-String 'BOOT-INF/lib/greeting-autoconfigure|BOOT-INF/classes'
```

You will see the nested dependency named similarly to:

```text
BOOT-INF/lib/greeting-autoconfigure-1.0.0.jar
```

To inspect the imports file inside the nested dependency:

```powershell
New-Item -ItemType Directory -Force target\inspect | Out-Null
Push-Location target\inspect
jar xf ..\consumer-1.0.0.jar BOOT-INF/lib/greeting-autoconfigure-1.0.0.jar
jar tf BOOT-INF/lib/greeting-autoconfigure-1.0.0.jar
Pop-Location
```

Then follow the procedure in Section 5.3 to extract the resource from the nested JAR. That way you have verified both the **plain library JAR** and the **final application JAR**.

## 7. Inspecting JARs When Packaging Multiple Libraries

### 7.1. Resource Path Collision Problem

Suppose two dependencies both contain:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

If a shade plugin keeps only one file without merging contents, entries from the other dependency can be lost. Classes from both libraries may still exist inside the JAR, yet one library's auto-configurations are not registered.

This bug is especially common when migrating from separate nested JARs to **a single shaded/uber JAR**.

### 7.2. Maven Shade Plugin: Appending the Imports Resource

With the Maven Shade Plugin, use `AppendingTransformer` for the imports file:

```xml
<transformer implementation="org.apache.maven.plugins.shade.resource.AppendingTransformer">
    <resource>META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports</resource>
</transformer>
```

If the application also packages management-context auto-configurations, consider appending the corresponding resource per Spring Boot guidance. Do not configure only one file when the artifact merges other registration resources as well.

### 7.3. Gradle Shadow Plugin: Appending the Imports Resource

Groovy DSL example per Spring Boot 2.7 guidance:

```groovy
tasks.withType(ShadowJar).configureEach {
    append("META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports")
}
```

Exact configuration may depend on plugin version and project task layout. Check the Shadow Plugin documentation for your version, then inspect the resulting JAR with `jar tf` and read the imports file contents.

### 7.4. Do Not Misapply Merging to Standard Executable Boot JARs

A standard Spring Boot executable JAR keeps dependencies as nested JARs inside `BOOT-INF/lib`; each dependency's imports resource stays inside its own nested archive. This differs from a shaded JAR that flattens dependencies into a single archive.

Therefore, before adding transformers, identify the artifact type:

- **Plain library JAR:** resource resides inside the library JAR.
- **Executable Boot JAR:** resource usually resides inside a nested dependency JAR.
- **Shaded/uber JAR:** colliding resource paths must be merged/appended.

## 8. Diagnostic Workflow When Auto-Configuration Is Not Discovered

Proceed from artifact to runtime in order to pinpoint the root cause.

### 8.1. Is the Imports File Inside the Distributed JAR?

- Check `target/classes/META-INF/spring/...` after compile/`process-resources`.
- Run `jar tf` on the exact release JAR.
- Extract and read the imports file contents.
- Confirm class names are exact FQCNs.
- If it is a nested class, verify the `$` character.
- If it is a shaded JAR, verify all entries were appended/merged.

If the resource is missing, check the source resource path, `resources` configuration, `excludes`, `filtering`, packaging plugins, and which artifact is being inspected.

### 8.2. Are the Listed Classes on the Runtime Classpath?

For each class in the imports file:

- Confirm the corresponding class exists inside the JAR.
- If the class belongs to another dependency, check `mvn dependency:tree` or Gradle `runtimeClasspath`.
- Check scope/configuration: `compileOnly`/`provided`/`test` do not guarantee runtime availability.
- If the consumer JAR has nested dependencies, verify the nested JAR is actually packaged.
- If the class is optional, ensure conditions and configuration structure do not force the JVM to load missing classes prematurely.

All implementation classes do not have to live in the same autoconfig JAR; they can reside in separate dependencies. What must be verified is that all required dependencies are present at runtime when the feature is enabled.

### 8.3. Imports Entry Correct Yet Conditions Do Not Match?

After confirming the resource and classes:

- Check `@ConditionalOnClass`/`@ConditionalOnMissingClass`.
- Check `@ConditionalOnBean`/`@ConditionalOnMissingBean`.
- Check properties via `@ConditionalOnProperty`.
- Check `@ConditionalOnWebApplication` if the configuration depends on context type.
- Check whether the auto-configuration is excluded via annotation or `spring.autoconfigure.exclude`.
- Use `--debug` or `ConditionEvaluationReport` to see matched/unmatched reasons.

The imports file only identifies candidates; conditions still decide whether the configuration is applied.

### 8.4. Class Is in the JAR Yet the Bean Is Still Missing?

Possible causes:

- The class is not listed in the imports file.
- The imports file was overwritten in a shaded JAR.
- A condition did not match.
- The user already provided a bean causing `@ConditionalOnMissingBean` to back off.
- Auto-configuration was not loaded into the context because the application did not enable `@EnableAutoConfiguration`/`@SpringBootApplication`.
- The class was component-scanned via another path or registered improperly.
- The bean method was not processed due to configuration, linkage, or dependency initialization failures.

Separate conclusions across three layers: **resource candidate**, **condition outcome**, and **bean registration/creation**.

### 8.5. Verify the Actual Artifact Used by the Application

It is possible to build the right JAR while the consumer still resolves an older version from a repository/cache or another dependency. Check:

```bash
mvn dependency:tree -Dincludes=com.acme:greeting-autoconfigure
```

Compare the version in the dependency tree against the artifact you just installed/published. If needed, check the manifest, checksum, or JAR location inside the executable app. Do not infer that runtime uses the new artifact solely because the library's `mvn package` succeeded.

## 9. Common Mistakes and How to Fix Them

| Mistake | Why it is wrong | How to fix |
| --- | --- | --- |
| Placing file at `META-INF/AutoConfiguration.imports` | Wrong resource path | Use `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports` exactly |
| Writing bean names instead of class names | Imports file needs the FQCN of the auto-configuration | Write `com.acme...MyAutoConfiguration` |
| Writing nested class names with a dot | Binary name of a nested class uses `$` | Use `Outer$Nested` |
| Class exists in `target/classes` yet missing in JAR | Resource/class may be excluded during packaging | Run `jar tf` on the release artifact |
| Inspecting only the outer executable JAR | Dependency JARs sit under `BOOT-INF/lib` | Extract the nested JAR and inspect further |
| Shaded JAR keeps only one imports file | Same-path resource was overwritten | Use `AppendingTransformer`/Shadow `append` |
| Using `spring.factories` `EnableAutoConfiguration` key on Boot 3 | That registration mechanism was removed | Move to `AutoConfiguration.imports` |
| Deleting all of `spring.factories` | Other factory keys may still be required | Migrate only the auto-configuration key; keep other entries |
| Assuming `spring-autoconfigure-metadata.properties` is required | It is optimization metadata, not the candidate list | Check the imports file first; configure the processor for metadata when needed |
| Assuming `spring-configuration-metadata.json` registers auto-configurations | That file describes configuration properties for IDEs | Distinguish property metadata resources from the imports file |
| Imports entry is correct yet condition is false | Candidate does not mean configuration is applied | Read condition report and property/classpath/bean states |
| Checking class names only with `javap` | `javap` does not prove Boot imported the configuration | Run a consumer integration test against the packaged artifact |
| Consumer test runs in same reactor using `target/classes` | May not test the actual published JAR | Use a separate consumer project depending on the installed artifact |
| Inspecting the wrong JAR version in local repository | Consumer may resolve a stale artifact | Inspect dependency tree and actual resolved version |

## 10. Auto-Configuration Library Release Checklist

Before releasing a starter/library, verify:

- [ ] Auto-configuration class has `@AutoConfiguration` and an appropriate package.
- [ ] Imports file is at the exact path and lists all FQCNs accurately.
- [ ] Class names in the imports file match compiled binaries; nested classes use `$`.
- [ ] Required implementation classes and dependencies are on the runtime classpath.
- [ ] Class/property/bean/web conditions are tested for both match and no-match.
- [ ] `spring-boot-autoconfigure-processor` is configured if condition metadata is desired.
- [ ] `spring-configuration-metadata.json` is generated if the library provides `@ConfigurationProperties` and needs IDE metadata.
- [ ] If renaming a published auto-configuration, `AutoConfiguration.replacements` has been considered.
- [ ] Auto-configuration package is not component-scanned; use the imports file and explicit `@Import`.
- [ ] Release JAR is checked with `jar tf`, reading the imports file, and inspecting classes.
- [ ] If building a shaded JAR, imports resources are appended/merged.
- [ ] An independent consumer project tested discovery from the installed/published artifact.
- [ ] The final executable Boot JAR has been checked including nested `BOOT-INF/lib`.
- [ ] Dependency tree and artifact version resolved by the consumer are verified.

## 11. Self-Check Questions

**Question 1.** In Spring Boot 3.3, which resource lists auto-configuration candidates?  
**Answer:** `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`. Each line is the FQCN of an auto-configuration.

**Question 2.** The imports file has the right entry and the class exists. Does that guarantee the bean is created?  
**Answer:** No. The class is only a candidate; conditions, exclusions, and bean registration/creation still determine the outcome.

**Question 3.** How is a nested class `Outer.NestedAutoConfiguration` written in the imports file?  
**Answer:** Using the binary name with `$`: `Outer$NestedAutoConfiguration`.

**Question 4.** Does `spring-autoconfigure-metadata.properties` replace `AutoConfiguration.imports`?  
**Answer:** No. The imports file lists candidates; metadata assists early condition filtering and improves startup.

**Question 5.** Why does `jar tf app.jar` not directly show a dependency's imports file in an executable Boot JAR?  
**Answer:** Dependencies are stored as nested JARs under `BOOT-INF/lib`; you must extract the nested JAR and inspect inside it.

**Question 6.** Why does a shaded JAR need to append imports resources?  
**Answer:** Multiple dependencies may contain resources at the same path; if the file is overwritten, entries for some auto-configurations will be lost.

**Question 7.** Does Spring Boot 3 still read the `EnableAutoConfiguration` key in `spring.factories` to register auto-configurations?  
**Answer:** No. Boot 3 requires the imports file for auto-configuration; other `spring.factories` keys can still be used.

**Question 8.** How do you prove a published JAR is discovered by another application?  
**Answer:** Build/install the library JAR, create an independent consumer project depending on that exact artifact, boot a context with `@SpringBootApplication`, and assert beans provided by the auto-configuration; also verify the imports resource in the classloader.

## 12. Takeaways and References

- **The imports file** is the candidate registration point: right path, right FQCN, right content.
- **Class files** are the compiled implementations; inspect them with `jar tf` and `javap`.
- **The dependency graph** determines which external classes exist at runtime.
- **Condition reports and consumer tests** confirm candidates are applied and beans actually appear.
- **Plain JARs, executable Boot JARs, and shaded JARs** have different layouts; inspect the right archive layer.
- In Boot 3, use `AutoConfiguration.imports`; `spring.factories` may still hold other factory entries.
- Testing the packaged artifact in a separate consumer project is stronger evidence than testing only sources in the library module.

Official documentation:

1. Spring Boot 3.3.13 — [Creating Your Own Auto-configuration](https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html), sections *Locating Auto-configuration Candidates*, *The autoconfigure Module*, and *Testing your Auto-configuration*.
2. Spring Boot 3.3.13 — [AutoConfiguration Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html).
3. Spring Boot 3.3.13 — [AutoConfigurationImportSelector Javadoc](https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurationImportSelector.html).
4. Spring Boot 3.0 — [Migration Guide: Auto-configuration Files](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide), migration from `spring.factories` to the imports file.
5. Spring Boot 2.7 — [Release Notes: Auto-configuration Registration and Shade/Shadow configuration](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-2.7-Release-Notes).
6. Apache Maven — [Maven Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html).
7. Java 17 — [The jar Command](https://docs.oracle.com/en/java/javase/17/docs/specs/man/jar.html) and [javap](https://docs.oracle.com/en/java/javase/17/docs/specs/man/javap.html).
