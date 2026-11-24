# Organizing Source Sets and Custom Source Directories in a Spring Boot Build

## 1. Learning Objectives

Java/Spring Boot projects normally follow the standard structure `src/main/java`, `src/main/resources`, `src/test/java`, and `src/test/resources`. When maintaining legacy systems, working with generated sources, separating resource groups, or adding independent tests, you may need additional directories. The key is to **declare them properly to the build tool**, understand which classpath they belong to, and verify that the Java compiler, test runner, `bootRun`/`spring-boot:run`, and executable JAR all see the required data.

This lesson covers:

- What a **source set** means in Gradle and the corresponding source structure in Maven.
- Distinguishing Java sources, resources, test sources, and test resources.
- Adding or replacing source directories using Gradle Groovy DSL/Kotlin DSL.
- Adding Maven Java source roots and resource roots while preserving the standard layout.
- Verifying the `compileJava`/`processResources`, `test`, and Spring Boot packaging flow.
- Managing generated sources, separate test suites, IDE sync, and common pitfalls.

**Scope:** a single Java Spring Boot application, extensible to multi-module builds. Examples use Java 17 and Spring Boot 3.3.13 as illustrative baselines; real projects should use the versions, JDK, and Gradle Wrapper or Maven version confirmed in the repository. Custom configuration is unnecessary when Maven/Gradle conventions already meet your needs.

## 2. Default Conventions Before Customizing

### 2.1. Standard Directory Tree

~~~text
source-layout-demo/
├── build.gradle                   # Gradle Groovy DSL
│   or build.gradle.kts            # Gradle Kotlin DSL
│   or pom.xml                     # Maven
├── settings.gradle                # Gradle only, if using Groovy DSL
│   or settings.gradle.kts         # Gradle Kotlin DSL
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/demo/LayoutApplication.java
    │   └── resources/
    │       └── application.properties
    └── test/
        ├── java/
        │   └── com/example/demo/LayoutApplicationTest.java
        └── resources/
            └── test-data.txt
~~~

This is an **either/or diagram**; you do not put `pom.xml` and both Gradle build flavors together at once. For Gradle, choose `build.gradle` + `settings.gradle` **or** `build.gradle.kts` + `settings.gradle.kts`; for Maven, choose `pom.xml`.

Directory roles:

| Directory | Role | Where does it usually go? |
| --- | --- | --- |
| `src/main/java` | Production Java source | Main classes; application JAR/WAR after compilation |
| `src/main/resources` | Configuration, templates, classpath data | Main resources; usually packaged into the executable archive |
| `src/test/java` | Test Java code | Test classes and test runtime; not packaged into a standard Boot JAR |
| `src/test/resources` | Test data | Test runtime classpath; not packaged into a standard Boot JAR |

Both Maven and Gradle rely on this convention. **Source files are not class files**: the build tool compiles Java from source directories and places the result in output directories. Resources are generally copied or processed as configured, rather than compiled like Java.

### 2.2. Gradle Calls This a `SourceSet`

With the Gradle Java plugin, two default source sets exist:

- `main`: application code/resources, configurations like `implementation`/`runtimeOnly`, with outputs consumed by `jar`/`bootJar`.
- `test`: test code/resources, configurations like `testImplementation`/`testRuntimeOnly`, with outputs consumed by the `test` task.

Each `SourceSet` consists of distinct parts:

| Part | Example access in Gradle | Contents |
| --- | --- | --- |
| Java source roots | `sourceSets.main.java.srcDirs` | Directories Gradle scans for `.java` files |
| Resource roots | `sourceSets.main.resources.srcDirs` | Directories Gradle pulls resources from |
| Classes output | `sourceSets.main.output.classesDirs` | Compiled classes directory (typically `build/classes/java/main`) |
| Resource output | `sourceSets.main.output.resourcesDir` | Processed resources directory (typically `build/resources/main`) |
| Compile classpath | `sourceSets.main.compileClasspath` | Dependencies and outputs needed during compilation |
| Runtime classpath | `sourceSets.main.runtimeClasspath` | Classes, resources, and runtime dependencies used when running |

In Gradle, creating a new source set usually generates corresponding configurations and compile/resource tasks; however, it **does not automatically create a `Test` task to execute a custom suite** simply by declaring a newly named source set. See section 9.

### 2.3. Maven Does Not Use a `SourceSet` Container Like Gradle

Maven conventions also distinguish main/test, but manage them via **source roots**, `resources`, and plugins/lifecycle phases. For example:

- Main Java from `src/main/java`, compiled by the compiler plugin.
- Main resources from `src/main/resources`, processed by the resources plugin.
- Test Java from `src/test/java`, test resources from `src/test/resources`.
- Additional Java directories via `build-helper-maven-plugin` or suitable configuration; multiple resource directories can be declared under `build/resources`.

Therefore, "adding a source set" must be interpreted per build tool: **Gradle creates/configures a SourceSet; Maven adjusts source roots/resource roots and plugins**. Do not try to write `sourceSets { ... }` in `pom.xml`.

## 3. Example Application Adding Non-Standard Directories

Suppose we want to keep the standard directories and add:

~~~text
source-layout-demo/
├── src/
│   ├── main/
│   │   └── java/com/example/demo/LayoutApplication.java
│   ├── custom/
│   │   ├── java/com/example/demo/ExtraGreeting.java
│   │   └── resources/greeting.txt
│   └── test-support/
│       ├── java/com/example/demo/ExtraGreetingTest.java
│       └── resources/test-marker.txt
├── build.gradle          # or build.gradle.kts
└── settings.gradle       # or settings.gradle.kts
~~~

Here:

- `LayoutApplication.java` stays in the standard root of the `main` source set.
- `ExtraGreeting.java` lives in the **additional main Java root** `src/custom/java`.
- `greeting.txt` lives in the **additional main resource root** `src/custom/resources`.
- `ExtraGreetingTest.java` and `test-marker.txt` are **test-only**; they must not accidentally be packaged into the production archive.
- Neither Java files nor resources should require manual copying into an output directory before each build.

Verification goal: when the application runs, Spring Boot can instantiate the `ExtraGreeting` bean and read `greeting.txt`; when tests run, JUnit discovers the test class from the extra directory and reads `test-marker.txt`.

## 4. Gradle: Adding Source Roots Without Losing Default Paths

### 4.1. Groovy DSL — Complete `build.gradle`

File `settings.gradle`:

~~~groovy
rootProject.name = 'source-layout-demo'
~~~

File `build.gradle`:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '1.0.0'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

sourceSets {
    main {
        java {
            srcDir 'src/custom/java'
        }
        resources {
            srcDir 'src/custom/resources'
        }
    }

    test {
        java {
            srcDir 'src/test-support/java'
        }
        resources {
            srcDir 'src/test-support/resources'
        }
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
~~~

This script **keeps** `src/main/java`/`src/main/resources` and `src/test/java`/`src/test/resources` because `srcDir` **appends a root** to the default set. `spring-boot-starter` is used for a console application with no web server required; the test starter provides JUnit/Spring Test.

### 4.2. Kotlin DSL — Equivalent `build.gradle.kts`

File `settings.gradle.kts`:

~~~kotlin
rootProject.name = "source-layout-demo"
~~~

File `build.gradle.kts`:

~~~kotlin
plugins {
    id("java")
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

group = "com.example"
version = "1.0.0"

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

repositories {
    mavenCentral()
}

sourceSets {
    named("main") {
        java.srcDir("src/custom/java")
        resources.srcDir("src/custom/resources")
    }

    named("test") {
        java.srcDir("src/test-support/java")
        resources.srcDir("src/test-support/resources")
    }
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}
~~~

The two Gradle configurations differ only in DSL syntax, sharing the same Java 17 toolchain, dependency management, and source roots. In Kotlin DSL, `named("main")`/`named("test")` references existing source sets; use the typed `Test` task configuration for `useJUnitPlatform()`.

**Fair behavior comparison:** use the same Gradle Wrapper version, JDK, dependency repository, and Spring Boot plugin when comparing both scripts. Do not place `build.gradle` and `build.gradle.kts` side by side in the same module expecting them to run sequentially as two build sources.

## 5. Java/Resource Code to Verify the Configuration Works

### 5.1. Main Class in the Standard Directory

Create `src/main/java/com/example/demo/LayoutApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class LayoutApplication {

    public static void main(String[] args) {
        SpringApplication.run(LayoutApplication.class, args);
    }

    @Bean
    CommandLineRunner verifyExtraSource(ExtraGreeting greeting) {
        return args -> System.out.println("CUSTOM_SOURCE=" + greeting.getMessage());
    }
}
~~~

`ExtraGreeting` is not in `src/main/java`, so if you forget to register `src/custom/java`, the compiler will fail to find the class when compiling `LayoutApplication`. This provides **concrete proof** to test the source root configuration.

### 5.2. Class in the Custom Main Java Root

Create `src/custom/java/com/example/demo/ExtraGreeting.java`:

~~~java
package com.example.demo;

import java.io.IOException;
import java.io.InputStream;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;

import org.springframework.stereotype.Component;

@Component
public class ExtraGreeting {

    public String getMessage() {
        try (InputStream stream =
                 ExtraGreeting.class.getResourceAsStream("/greeting.txt")) {
            if (stream == null) {
                throw new IllegalStateException("greeting.txt is not on the classpath");
            }
            return new String(stream.readAllBytes(), StandardCharsets.UTF_8).strip();
        } catch (IOException ex) {
            throw new UncheckedIOException(ex);
        }
    }
}
~~~

Java 17 supports `InputStream.readAllBytes()` and `String.strip()`. `@Component` lets Spring Boot component scanning pick up the class once compiled and located in a subpackage of `com.example.demo`. If a source file is in a custom root but its declared package is outside the component scan scope, compilation may succeed while Spring still does not create the bean; keep these two issues distinct.

### 5.3. Main Resource from the Custom Directory

Create a UTF-8 text file `src/custom/resources/greeting.txt` with a single line:

~~~text
xin-chao-tu-custom
~~~

In the code, `getResourceAsStream("/greeting.txt")` looks up the resource **by name on the classpath**, not by the physical path `src/custom/resources/greeting.txt`. `processResources` copies this file into the resource output root; when packaged into a Boot JAR, it is placed on the application classpath.

Because `.strip()` is used, a trailing newline in the file still yields the exact same message.

### 5.4. Additional Test Java and Test Resource

Create `src/test-support/java/com/example/demo/ExtraGreetingTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

@SpringBootTest
class ExtraGreetingTest {

    @Autowired
    private ExtraGreeting greeting;

    @Test
    void loadsExtraJavaAndMainResource() {
        assertEquals("xin-chao-tu-custom", greeting.getMessage());
    }

    @Test
    void loadsAdditionalTestResource() {
        assertNotNull(getClass().getResourceAsStream("/test-marker.txt"));
    }
}
~~~

In the second test, the resource stream is opened only to check existence; in production code, close streams after use to avoid leaks. To practice proper resource management in tests as well, replace the second method with:

~~~java
@Test
void loadsAdditionalTestResource() throws Exception {
    try (var stream = getClass().getResourceAsStream("/test-marker.txt")) {
        assertNotNull(stream);
        assertEquals(
                "TEST_ONLY",
                new String(stream.readAllBytes(), java.nio.charset.StandardCharsets.UTF_8).strip()
        );
    }
}
~~~

**Use only one version of `loadsAdditionalTestResource` in the test class**: the first demonstrates the quick idea; the second is the version to keep in the real file. File `src/test-support/resources/test-marker.txt`:

~~~text
TEST_ONLY
~~~

If you want a single complete test file, use the class above and replace just the resource-checking method with the `try-with-resources` version. Do not include two methods with the same name and parameter signature.

### 5.5. Running and Expected Results

Using the project's Gradle Wrapper if available (Linux/macOS):

~~~bash
./gradlew clean test
./gradlew bootRun
~~~

The second command starts the application without a web server; startup logs include many lines, and you should see **one line printed by the application itself**:

~~~text
CUSTOM_SOURCE=xin-chao-tu-custom
~~~

If you want to verify the production artifact:

~~~bash
./gradlew bootJar
java -jar build/libs/source-layout-demo-1.0.0.jar
~~~

The filename comes from the project name/version and Boot JAR convention in the example configuration. On Windows PowerShell, use `.\gradlew.bat`. If the project has no wrapper yet, set up a valid wrapper or use a compatible installed Gradle. Do not assume `gradlew` exists merely because `build.gradle` is present.

When running `./gradlew test`, JUnit should discover **2 test methods** in `ExtraGreetingTest`. When running `bootRun` or the executable JAR, the application output still contains `CUSTOM_SOURCE=...`. `test-marker.txt` is strictly for test runtime and is not packaged into the Boot JAR under standard configuration.

## 6. `srcDir` vs. `setSrcDirs`: Append or Replace All?

This is the most common configuration-breaking mistake.

### 6.1. Appending a Path

**Groovy:**

~~~groovy
sourceSets {
    main {
        java.srcDir 'src/custom/java'
        resources.srcDir 'src/custom/resources'
    }
}
~~~

**Kotlin:**

~~~kotlin
sourceSets {
    named("main") {
        java.srcDir("src/custom/java")
        resources.srcDir("src/custom/resources")
    }
}
~~~

`srcDir` is an **append** operation, so Gradle retains the existing convention paths in `main`. If multiple roots are needed:

~~~groovy
sourceSets {
    main {
        java {
            srcDir 'src/custom/java'
            srcDir 'src/legacy/java'
        }
    }
}
~~~

Both extra paths are added to the Java source roots; Java files in those roots are compiled as part of the same `main` source set.

### 6.2. Replacing the Default Roots

**Groovy:**

~~~groovy
sourceSets {
    main {
        java.srcDirs = ['code/java', 'generated/java']
        resources.srcDirs = ['config/resources']
    }
}
~~~

**Kotlin:**

~~~kotlin
sourceSets {
    named("main") {
        java.setSrcDirs(listOf("code/java", "generated/java"))
        resources.setSrcDirs(listOf("config/resources"))
    }
}
~~~

`srcDirs = ...` (Groovy) or `setSrcDirs(...)` (Kotlin) **replaces** the list. If you omit `src/main/java`/`src/main/resources`, Gradle **will no longer scan those default roots** for `main`.

Replacing is useful when migrating entirely to a different layout; if you only want to add paths, use `srcDir`. Do not use `setSrcDirs` and then wonder why `LayoutApplication.java` vanished from compilation.

### 6.3. Do Not Create a New Source Set When You Only Want a New Directory

A new source set named `custom` does not mean the same thing as adding `src/custom/java` to `main`:

~~~groovy
sourceSets {
    custom {
        java.srcDir 'src/custom/java'
    }
}
~~~

The snippet above **creates an independent source set** named `custom` instead of adding classes to `main`. It has its own outputs, classpaths, and configurations and does not automatically become part of `main` or `bootJar`. If `LayoutApplication` uses `ExtraGreeting` from `custom` without configuring dependencies between source sets, main compilation will fail to find the class.

**Rule of thumb:** for code belonging to the same application/production classpath, add the root to `main`; only create an independent source set when you genuinely need a separate classpath or lifecycle model.

## 7. From Source Roots to Outputs: Which Task Does What?

In the Gradle Java plugin:

~~~text
main.java.srcDirs
    ↓ compileJava
build/classes/java/main/
    ↓
    ├───────────────┐
main.resources      │
    ↓ processResources
build/resources/main/
    ↓               │
    └─ classes ◄────┘       (lifecycle task depending on required outputs)
         ↓
main.output + runtimeClasspath
         ↓
bootRun / bootJar
~~~

This relationship illustrates the output flow; the actual task graph includes additional dependencies and optimizations. `classes` aggregates compilation and resource processing rather than being a task that "directly reads all Java/resource files".

For the `test` source set:

~~~text
test.java.srcDirs       → compileTestJava → build/classes/java/test/
test.resources.srcDirs  → processTestResources → build/resources/test/
                      ↓
              test.output + test.runtimeClasspath
                      ↓
                    test
~~~

The test classpath normally includes main outputs and test dependencies. Thus tests can access `ExtraGreeting` and `greeting.txt` on the main classpath, plus `test-marker.txt` in test resources.

When the Spring Boot Gradle Plugin builds `bootJar`, it takes classes/resources and runtime dependencies of the **main source set** under standard configuration. `test` outputs are not automatically packaged into the executable archive. `bootRun` also defaults to the main runtime classpath. Putting source roots under `test` by mistake can result in passing tests while the production `bootJar` is missing classes or resources.

### 7.1. Where Outputs Typically Live

| Artifact type | Gradle | Maven |
| --- | --- | --- |
| Main compiled Java | `build/classes/java/main` | `target/classes` |
| Main processed resources | `build/resources/main` | `target/classes` |
| Test compiled Java | `build/classes/java/test` | `target/test-classes` |
| Test processed resources | `build/resources/test` | `target/test-classes` |
| Spring Boot executable JAR | `build/libs/*.jar` from `bootJar` | `target/*.jar` after `repackage` |

These are conventions for common plugins; `outputDirectory`/`destinationDirectory`, classifiers, and custom plugins can change them. **Do not place build outputs inside a source root**, as doing so can cause generated classes or resources to be picked up again by compiler/resource tasks on subsequent builds.

### 7.2. Verifying on the Command Line

~~~bash
./gradlew clean compileJava processResources
./gradlew compileTestJava processTestResources
./gradlew test
./gradlew bootJar
~~~

Then inspect:

~~~text
build/classes/java/main/com/example/demo/ExtraGreeting.class
build/resources/main/greeting.txt
build/classes/java/test/com/example/demo/ExtraGreetingTest.class
build/resources/test/test-marker.txt
~~~

With the example named `source-layout-demo`, the executable JAR is typically `build/libs/source-layout-demo-1.0.0.jar`. Inspect the JAR contents:

~~~bash
jar tf build/libs/source-layout-demo-1.0.0.jar
~~~

Look for entries `BOOT-INF/classes/com/example/demo/ExtraGreeting.class` and `BOOT-INF/classes/greeting.txt`. Neither `ExtraGreetingTest.class` nor `test-marker.txt` should be in the production Boot JAR. If they are, check whether test sources were mistakenly added to `main` or copied manually into the archive.

The `jar tf` command requires the JDK's `jar` tool, and the file path must match the actual output. If the file was renamed, list `build/libs` first.

## 8. Maven: Adding Equivalent Source and Resource Directories

### 8.1. Core Difference from Gradle

By default, Maven reads Java code from `src/main/java` and `src/test/java`. In the POM, `build/sourceDirectory` and `build/testSourceDirectory` allow specifying **a single main source root and a single test source root**, so setting them generally **replaces** the standard paths. To keep `src/main/java` while **adding** `src/custom/java`, use a plugin that registers additional source roots in the proper lifecycle phase, such as `build-helper-maven-plugin`.

For resources, Maven allows listing multiple `<resource>` entries under `build/resources` and multiple `<testResource>` entries under `build/testResources`. When declaring a resources collection manually, remember to **include the standard root if still needed**.

### 8.2. Complete Maven `pom.xml` Configuration

This example uses Spring Boot starter parent 3.3.13, JDK 17, and Build Helper Maven Plugin 3.6.2. It applies to **the same source/data tree from sections 3–5**:

~~~xml
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
    <artifactId>source-layout-demo</artifactId>
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
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <resources>
            <resource>
                <directory>src/main/resources</directory>
            </resource>
            <resource>
                <directory>src/custom/resources</directory>
            </resource>
        </resources>

        <testResources>
            <testResource>
                <directory>src/test/resources</directory>
            </testResource>
            <testResource>
                <directory>src/test-support/resources</directory>
            </testResource>
        </testResources>

        <plugins>
            <plugin>
                <groupId>org.codehaus.mojo</groupId>
                <artifactId>build-helper-maven-plugin</artifactId>
                <version>3.6.2</version>
                <executions>
                    <execution>
                        <id>extra-main-java</id>
                        <phase>generate-sources</phase>
                        <goals>
                            <goal>add-source</goal>
                        </goals>
                        <configuration>
                            <sources>
                                <source>src/custom/java</source>
                            </sources>
                        </configuration>
                    </execution>

                    <execution>
                        <id>extra-test-java</id>
                        <phase>generate-test-sources</phase>
                        <goals>
                            <goal>add-test-source</goal>
                        </goals>
                        <configuration>
                            <sources>
                                <source>src/test-support/java</source>
                            </sources>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

This is a **complete POM** usable with the example's Java sources and resources. It differs from Gradle in how roots are added, yet achieves the same result: including custom Java sources in main/test compilation and placing resources on the corresponding classpaths.

**Why choose the `generate-sources` and `generate-test-sources` phases?** Build Helper registers the roots before the `compile`/`test-compile` phases, so the compiler sees the sources when the lifecycle runs. Likewise, resources are processed by the Maven Resources Plugin during the corresponding resource phases.

**Why declare `spring-boot-maven-plugin`?** The Spring Boot parent provides the `repackage` plugin configuration/execution; the application module declares the plugin so Maven builds an executable archive during `package`. Do not look for Gradle's `bootJar` goal in a Maven project.

**Remember resource filtering:** when you write `<build><resources>...` manually, you replace the inherited/default POM resources configuration. Applications that filter `application.properties`/`application.yml` or have special exclusions must replicate those rules. This example uses plain text resources that require no filtering.

### 8.3. When Is `sourceDirectory` Enough, and When Is a Plugin Needed?

If you want to **move** main Java completely from `src/main/java` to `code/java`, Maven can use:

~~~xml
<build>
    <sourceDirectory>code/java</sourceDirectory>
</build>
~~~

This is just a POM snippet added to an existing build. Consequence: the compiler primarily reads `code/java` as the main source root; do not expect `src/main/java` to still be compiled just because it exists on disk.

If you want to **add** `code/java` while keeping `src/main/java`, `sourceDirectory` cannot express multiple roots; use `build-helper:add-source` or a plugin with an equivalent contract.

Similarly, `testSourceDirectory` replaces the standard test source root, whereas `build-helper:add-test-source` appends a root. Consider test naming and Maven Surefire/Failsafe when adding another test directory: adding a test source root **does not automatically create a separate test suite lifecycle**.

### 8.4. Running Maven and Checking Outputs

In the directory containing `pom.xml`:

~~~bash
mvn -version
mvn clean test
mvn package
java -jar target/source-layout-demo-1.0.0.jar
~~~

If the repository includes a Maven Wrapper, replace `mvn` with `./mvnw` (Linux/macOS) or `.\mvnw.cmd` (PowerShell). `pom.xml` itself does not generate a Maven Wrapper.

When the classes are added properly, Maven compiles `ExtraGreeting.java` and test-compiles `ExtraGreetingTest.java`. Expected outputs:

~~~text
target/classes/com/example/demo/ExtraGreeting.class
target/classes/greeting.txt
target/test-classes/com/example/demo/ExtraGreetingTest.class
target/test-classes/test-marker.txt
target/source-layout-demo-1.0.0.jar
~~~

After the application runs, the line printed by `CommandLineRunner` is:

~~~text
CUSTOM_SOURCE=xin-chao-tu-custom
~~~

Run `jar tf target/source-layout-demo-1.0.0.jar` and look for `BOOT-INF/classes/com/example/demo/ExtraGreeting.class` and `BOOT-INF/classes/greeting.txt`. `ExtraGreetingTest.class`/`test-marker.txt` should not be in the application JAR.

To inspect the POM model after inheritance:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
~~~

The effective POM helps verify plugin executions and resource definitions. However, source roots registered by Build Helper happen **when the goal executes in the lifecycle**, so reading the POM alone is not sufficient proof; inspect the `build-helper:add-source`/`add-test-source` logs and compiled class outputs after `mvn clean test`.

## 9. Separate Source Set for Integration Tests

So far, `src/test-support/java` in the example is an **extra directory of the `test` source set**. It runs alongside unit tests in the `test` task. When a group of tests needs its own dependencies or lifecycle (such as integration tests requiring a database or Testcontainers), consider a **separate source set**.

### 9.1. Adding a Test Root vs. Creating a New Suite

| Need | Suitable Gradle approach | Extra setup needed? |
| --- | --- | --- |
| Test helpers sharing classpath with unit tests | Add `src/test-support/java` to `sourceSets.test` | No new `Test` task needed |
| Integration tests with separate classpath/lifecycle | Create an `integrationTest` source set and matching `Test` task, or use the JVM Test Suite plugin | Yes; dependency classpath and task |
| Test Java compiled but never executed | Create a new source set only | No runner task exists yet; must configure one |
| Gradle tests expected to run during `build` | Wire `integrationTest` into `check` | Yes; do not assume it happens automatically |

An example **Kotlin DSL fragment** added after the Java/Spring Boot plugins in `build.gradle.kts`:

~~~kotlin
val integrationTest by sourceSets.creating {
    java.setSrcDirs(listOf("src/it/java"))
    resources.setSrcDirs(listOf("src/it/resources"))
    compileClasspath += sourceSets["main"].output
    runtimeClasspath += output + compileClasspath
}

configurations[integrationTest.implementationConfigurationName]
    .extendsFrom(configurations["testImplementation"])

configurations[integrationTest.runtimeOnlyConfigurationName]
    .extendsFrom(configurations["testRuntimeOnly"])

tasks.register<Test>("integrationTest") {
    description = "Runs integration tests"
    group = "verification"

    testClassesDirs = integrationTest.output.classesDirs
    classpath = integrationTest.runtimeClasspath
    shouldRunAfter(tasks.named("test"))
    useJUnitPlatform()
}

tasks.named("check") {
    dependsOn(tasks.named("integrationTest"))
}
~~~

Prerequisites: the build applies the Java plugin, has `main`/`test` source sets, and includes appropriate test engine/dependencies. Creating a suite named `integrationTest` creates configurations such as `integrationTestImplementation` and `integrationTestRuntimeOnly`. The snippet above inherits existing test dependencies; real projects may prefer separate dependencies and databases.

`shouldRunAfter` is a **soft ordering constraint**, not a dependency: the integration task still only runs when requested or when `check` depends on it. `dependsOn` is what makes integration tests participate in the `check` lifecycle. If you do not want integration tests running on every `build`, omit the `check` dependency and invoke `./gradlew integrationTest` explicitly.

This is an **optional extension configuration** and is not needed for the custom source example in sections 4–5. It can also be implemented using the Gradle JVM Test Suite Plugin; pick one approach that fits your testing policy rather than layering multiple definitions for the same source set/task name.

### 9.2. Maven Integration Tests Differ from Gradle Source Sets

Maven uses Surefire/Failsafe and lifecycle phases to separate unit and integration tests. `build-helper:add-test-source` only adds a source root to **test compilation**; it does not create a Gradle-style source set task/phase or configure Failsafe to match `*IT.java`. If a project needs a dedicated test suite, configure Failsafe executions, naming patterns, profiles, and runtime environments accordingly.

Do not put integration tests into a main source root just so the compiler finds imports. Doing so can pull test code/dependencies into the executable JAR and blur the boundary between production and test sources.

## 10. Generated Sources and Generated Resources

Code or resources produced by annotation processors, OpenAPI generators, protobuf, template engines, or custom tasks generally **should not be committed directly into `src/main/java` or generated inside human-maintained source roots**. Put outputs under `build/generated/...` (Gradle) or `target/generated-sources/...` (Maven), and let the task/plugin register the source root before compilation.

### 10.1. Gradle: Output Paths Must Carry Task Dependencies

Example of **generated resources** that can be added to `build.gradle.kts`:

~~~kotlin
val prepareGeneratedResources by tasks.registering(Copy::class) {
    from("src/templates")
    into(layout.buildDirectory.dir("generated/resources/main"))
}

sourceSets.named("main") {
    resources.srcDir(prepareGeneratedResources)
}
~~~

This is a fragment for a project with the Java plugin; create the input directory `src/templates` containing permitted files to copy. Passing a `TaskProvider` to `resources.srcDir` gives Gradle the producer and output metadata to manage task dependencies. The destination `build/generated/resources/main` belongs to build output; do not write outputs back into `src/main/resources`.

Groovy equivalent:

~~~groovy
def prepareGeneratedResources = tasks.register('prepareGeneratedResources', Copy) {
    from 'src/templates'
    into layout.buildDirectory.dir('generated/resources/main')
}

sourceSets {
    main {
        resources.srcDir prepareGeneratedResources
    }
}
~~~

If the generator produces **Java files**, register the producer directory on `sourceSets.main.java` and ensure `compileJava` depends properly on the generating task. Use `TaskProvider`/task outputs rather than passing a plain path to an ungenerated directory; passing a string path alone can cause out-of-order execution and missing-class errors.

### 10.2. Maven: Code-Generation Plugins Before Compile

Maven provides the `generate-sources` and `generate-test-sources` phases before `compile`/`test-compile`. Many generator plugins register their source roots automatically; if one does not, use `build-helper:add-source` pointing to `target/generated-sources/...`. Adding a root alone **does not execute the generator**; you still must configure the generation goal and execution order.

Do not run a code generator via a manual script before `mvn compile` and treat that as a reliable build process: on a clean CI machine, those outputs will not exist. The goal is for a **clean build from input sources** to generate all required sources and resources automatically.

## 11. Spring Boot Configuration and Resource Overrides

### 11.1. Classpath Resource Names Are Not Source Paths

With `src/custom/resources/greeting.txt`, runtime code calls `getResourceAsStream("/greeting.txt")`. In Spring Boot, `application.properties` or `application.yml` files also usually live on the classpath (or in an external config location supported by Spring Boot), and **source directory paths are not part of the resource name**.

For example, adding `src/custom/resources` to `main` may bring `src/custom/resources/application.yml` onto the same classpath as `src/main/resources/application.yml`. If two roots contain the **same relative path**, the copy task may handle duplicates via a strategy or fail depending on Gradle/Maven/plugins; do not rely on ambiguous root ordering to pick a "winning file".

For Spring Boot configuration, keep **one clear source** for each logical resource whenever possible, or design profiles/config imports properly. Do not accidentally place two `application.properties` files in two roots and guess precedence inside the archive.

### 11.2. Resource Filtering and Secrets

- Gradle `processResources` primarily copies resources by default; if template substitution is desired, explicitly configure `processResources` and the inputs it must track.
- Maven Resources Plugin supports filtering via `<filtering>true</filtering>`; the starter parent may define default rules. If you replace `build/resources`, verify the project's filtering and exclusion rules.
- Never place tokens, passwords, private keys, or sensitive environment config in `src/main/resources` or a custom main resource root packaged into a Boot JAR.
- Test fixtures and mock credentials belong only in `test resources` and must never be copied into main outputs.

Packaging an executable JAR/WAR embeds resources directly into the archive; anyone with the JAR can extract and read its contents. "Not exposed in source" does not make packaged contents secret.

## 12. IDEs, Build Caches, and Machine-Specific Paths

Gradle/Maven IDE integrations typically read source roots from the **synced build model**, not just from folders marked manually in the UI.

- **IntelliJ IDEA:** Run Reload All Gradle Projects or Reload Maven Projects after editing DSL/POM; verify that module sources/resources and test roots are recognized by the IDE.
- **Eclipse/STS:** Run Refresh Gradle Project (Buildship) or Maven Update Project (m2e); verify the Java Build Path after the build tool updates.
- **VS Code:** Allow Java/Maven/Gradle extensions to finish importing; check Java Projects and extension logs if custom directories show errors.

Never edit IDE classpaths manually and forget to update the build script. Manual IDE tweaks may clear red squiggles temporarily while `./gradlew clean build` or `mvn clean verify` continues to fail in CI.

When relocating directories, avoid absolute paths like `C:\Users\me\project\src\custom` or `/home/me/work` in `build.gradle`/`pom.xml`. Use paths relative to the module root or Gradle layout/Maven project directory so teammates and CI can reproduce the build. A path like `../shared/src` pointing into another module is a sign you should consider a **project/module dependency** instead of cross-compiling sources.

## 13. Common Issues and How to Find the Root Cause

| Symptom | Possible cause | Verification and fix |
| --- | --- | --- |
| Java class in `src/custom/java` is not compiled | Forgot `main.java.srcDir` or Build Helper `add-source` | Inspect build script/POM, check `compileJava`/`mvn compile` and compiled class output |
| Classes in `src/main/java` vanish after adding a custom root | Used `srcDirs = ...`/`setSrcDirs(...)` instead of `srcDir` | Re-add the default root or switch to append |
| `greeting.txt` cannot be found | Placed in a Java root instead of a resource root; wrong relative path | Inspect `processResources`/`target/classes` and the `/greeting.txt` lookup path |
| Gradle tests do not see test classes in a custom directory | Forgot `sourceSets.test.java.srcDir` | Configure test roots properly and inspect `compileTestJava` |
| Tests pass, but test-only files appear in the Boot JAR | Added test resources to `main` | Move resources to a test root, run a clean rebuild, and inspect the JAR |
| Integration test task does not run | Created a new source set without a `Test` task or lifecycle dependency | Register the task, set `testClassesDirs`/`classpath`, and wire to `check` if needed |
| Maven `sourceDirectory` points to custom dir; default source is missing | `sourceDirectory` sets a single replacement root | Use Build Helper to add the new Java root if keeping both |
| Maven custom resources cause old config to disappear | Declared `<resources>` without `src/main/resources` | List all required resource roots and verify filtering rules |
| IDE sees the code, but CLI build fails | Folder marked manually in IDE without updating the build model | Put source roots in the script/POM and resync |
| CLI builds fine, but IDE cannot resolve classes | IDE import/sync is stale | Reload the Gradle/Maven project and verify the JDK |
| Generated sources only build after running a separate script | Generator is not wired to a task/phase | Declare producer outputs and task dependencies/phases properly |
| `bootJar` lacks classes even though `compileTestJava` has them | Code placed in the test source set instead of `main` | Move production code to `main` and rebuild |
| Duplicate resource appears unexpectedly | Multiple roots share the same relative path | Check duplicate handling and resource structure |
| Works on one machine, fails on CI | Used an absolute path or ungenerated files | Use relative/layout paths and clean builds from a fresh checkout |

Do not wipe IDE/Gradle/Maven caches immediately on error. Use **build commands and actual outputs** to see which source directories are visible first, then fix the right root or task. Clearing caches is justified only when you have evidence that stale cache state is causing the mismatch.

## 14. Verification Workflow After Adding Source Roots

Perform these checks in a clean repository or a practice copy.

**With Gradle:**

1. Read `build.gradle`/`build.gradle.kts` and determine whether code belongs in `main` or `test`.
2. Add `src/custom/java` and `src/custom/resources` to `main` with `srcDir`; add test-only roots to `test`.
3. Run `./gradlew clean compileJava processResources` and inspect outputs under `build/classes/java/main` + `build/resources/main`.
4. Run `./gradlew clean test`, confirming `ExtraGreetingTest` is discovered and both test methods pass.
5. Run `./gradlew bootJar` followed by `jar tf`, verifying that production classes/resources are in the Boot JAR and test-only resources are excluded.
6. Run `java -jar` and check for the line `CUSTOM_SOURCE=xin-chao-tu-custom`.
7. Resync the IDE; ensure the IDE uses the same build model as the wrapper/CLI.

**With Maven:**

1. Keep `src/main/java` and `src/test/java`; use Build Helper for additional source roots.
2. Declare both default and custom resource directories under `build/resources`/`build/testResources`.
3. Run `mvn clean test`, inspecting Build Helper logs and `target/classes`/`target/test-classes`.
4. Run `mvn package`, locate the executable archive, and inspect the files inside the JAR.
5. Run `java -jar`, verify the exact application output line, then reload the Maven project in your IDE.

**Success criteria:** you can explain why each root belongs to `main` or `test`, what gets compiled/copied onto which classpath, why the Boot archive only needs `main` outputs, and verify everything using clean builds, tests, and the packaged archive.

## 15. Self-Check Questions

**Question 1.** In Gradle, what is the difference between `java.srcDir("src/custom/java")` and `java.setSrcDirs(listOf("src/custom/java"))`?

**Answer:** `srcDir` appends a root while keeping existing roots. `setSrcDirs` replaces all roots with the new collection, which can drop `src/main/java`.

**Question 2.** Does a new Gradle source set named `experimental` automatically become part of the executable Spring Boot JAR?

**Answer:** No. Under standard configuration, Boot JAR packages `main` outputs and `runtimeClasspath`. The `experimental` source set has its own outputs and classpaths and only enters the JAR if the build explicitly wires it in as required.

**Question 3.** If you put `application.yml` under `src/custom/java`, add that Java root, and run `bootJar`, is the application guaranteed to read that config file?

**Answer:** No. Java source directories are primarily for `.java` files; YAML must live in a resource root to be copied by resource processing, or be supplied via a supported external config setup.

**Question 4.** In Maven, if you want to keep `src/main/java` and add `src/legacy/java`, should you set `<sourceDirectory>src/legacy/java</sourceDirectory>`?

**Answer:** Not if you want to keep both. `sourceDirectory` sets a single main root; use Build Helper `add-source` in `generate-sources` or an equivalent mechanism to add another Java root.

**Question 5.** Why does a test in `src/test-support/java` pass, yet the test class does not appear in the Boot JAR?

**Answer:** Test sources compile into the test output/classpath, whereas Boot JAR packages main classes/resources and runtime dependencies. This is the intended separation.

**Question 6.** If generated Java files are written under `build/generated/sources` but `compileJava` does not see them, what should be fixed?

**Answer:** Wire the generator task's output directory into the main Java source set and ensure the compiler depends on the producer task; do not rely on having run the generator manually beforehand.

**Question 7.** Why should `<resources>` in a POM not list only `src/custom/resources` when the project still uses `src/main/resources`?

**Answer:** Doing so can replace the default/inherited resource roots collection. To keep legacy resources, declare both `src/main/resources` and the custom path, while also checking filtering and exclusions.

## 16. Official Documentation

- Gradle Java Plugin: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle Building Java & JVM Projects — Source Sets: https://docs.gradle.org/current/userguide/building_java_projects.html
- Gradle Testing in Java & JVM Projects — Configuring Integration Tests: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle JVM Test Suite Plugin: https://docs.gradle.org/current/userguide/jvm_test_suite_plugin.html
- Spring Boot Gradle Plugin — Running Your Application: https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html
- Spring Boot Gradle Plugin — Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Maven Standard Directory Layout: https://maven.apache.org/guides/introduction/introduction-to-the-standard-directory-layout.html
- Maven Resources Plugin — Specifying Resource Directories: https://maven.apache.org/plugins/maven-resources-plugin/examples/resource-directory.html
- MojoHaus Build Helper Maven Plugin — Add Source/Test Source: https://www.mojohaus.org/build-helper-maven-plugin/usage.html

Gradle "current" documentation can evolve across versions. In real projects, cross-check against the exact **Gradle Wrapper, Java plugin, Spring Boot plugin, and Maven plugin versions** your project uses. A sustainable layout keeps clear production/test boundaries, defines source/resource roots in the build, and proves correctness with clean builds, tests, and actual archive inspection.
