# Using `bootTestRun` or Configuring Test Classpath Execution When Appropriate

## 1. When Do You Need to Run the Application with the Test Classpath?

During Spring Boot development, you sometimes want to **start the real application** while allowing components that exist only in test scope:

- A launcher for previewing features, located in `src/test/java`.
- Beans simulating external services, demo data, or adapters dedicated to the developer workstation.
- A dependency declared only in `testImplementation`, such as a test fixture generation library.
- Resources in `src/test/resources`, such as sandbox config or sample datasets.
- Development helpers such as Testcontainers, when the project intentionally designs their startup/cleanup lifecycle.

The Spring Boot Gradle Plugin provides the **`bootTestRun`** task out of the box for this use case. With Maven, the Spring Boot Maven Plugin provides **`spring-boot:test-run`**; the `spring-boot:run` goal also offers `useTestClasspath` when you only want to add the test classpath.

This is a **development-time application run** feature, not a replacement for automated tests. This lesson explains the differences between running with the main runtime classpath vs. the test runtime classpath, selecting the right main class, and artifact distribution.

After this lesson, you will be able to:

1. Explain why `bootRun` and `bootTestRun` produce different results.
2. Create a launcher under `src/test/java` to start the application with development-only config/beans.
3. Configure `bootTestRun` in both Gradle Groovy DSL and Kotlin DSL.
4. Define a custom `BootRun` task or configure an IDE with the test runtime classpath when needed.
5. Choose equivalent Maven commands, contrast with the test runner, and verify that the Boot JAR excludes test-only components.
6. Avoid mistakes involving main classes, classpaths, profiles, ports, test dependencies, and run lifecycles.

**Version context:** the examples use Spring Boot `3.3.13`, Gradle with the Java plugin, and Java 17. These numbers keep the examples consistent and do not imply the latest release. In real projects, consult your build wrapper and documentation for your exact Spring Boot Gradle/Maven Plugin version.

## 2. Distinguishing Three Easily Confused Activities

| Activity | Gradle | Typical Classpath | Purpose |
| --- | --- | --- | --- |
| Standard development app launch | `bootRun` | `sourceSets.main.runtimeClasspath` | Runs the app's main class and runtime dependencies |
| Test/dev variant launch | `bootTestRun` | `sourceSets.test.runtimeClasspath` | Runs a main class found in test output, with test dependencies/resources |
| Running automated tests | `test` | Test runtime classpath | JUnit/TestNG test runner executes test methods and reports pass/fail |

**`bootTestRun` is a `BootRun` task, not a `Test` task.** It starts a Java process and can keep running like a normal web application until stopped. It does not discover or execute methods annotated with `@Test`.

Spring Boot 3.3 describes `bootTestRun` as a task registered alongside `bootRun` when the plugin reacts to the Java plugin. The task uses a **main class from the test source set's output** and the **test runtime classpath**. With `bootRun`, Spring Boot looks for the main class in main output and uses the main runtime classpath.

### 2.1. How Do Main and Test Classpaths Differ?

Under the Gradle Java plugin, the typical layout is:

~~~text
src/main/java       → compileJava          → build/classes/java/main
src/main/resources  → processResources     → build/resources/main

src/test/java       → compileTestJava      → build/classes/java/test
src/test/resources  → processTestResources → build/resources/test
~~~

Conceptually, the two runtime classpaths are:

~~~text
main.runtimeClasspath
  = main classes + main resources + runtime dependencies

test.runtimeClasspath
  = test classes + test resources
    + main classes/resources + test runtime dependencies
    + related runtime dependencies
~~~

This is a logical diagram, not a manual classpath command; real Gradle configurations can add or exclude dependencies. The test runtime classpath includes visibility into main code because test code needs to call the code under test.

A dependency declared in `testImplementation` does not automatically appear on the main runtime classpath. Hence `bootRun` typically does not see it, whereas `bootTestRun` can.

### 2.2. Difference Between "Library on the Classpath" and "Active Bean"

The classpath only determines **which classes and resources Java can see**. It does not automatically:

- Register arbitrary classes as Spring beans.
- Import a specific `@Configuration` class.
- Activate a Spring profile named `test`.
- Replace production beans with mocks.
- Execute JUnit test methods.

To get a preview variant, you must have **explicit configuration rules**: a dedicated launcher, `@Import`, `@Configuration`, profiles, or intentional bean overrides. This distinction prevents assuming that "using the test classpath automatically switches the app to mocks."

## 3. Practical Example: Production Returns One Value, Preview Returns Another

We will create a Spring Boot web application with a `GET /greeting` endpoint. Normally, the endpoint returns:

~~~text
production
~~~

When running `bootTestRun`, the application is started by a launcher under the test source set using a preview-only `@Primary` bean; the endpoint returns:

~~~text
preview-from-test
~~~

The observed difference proves that the launcher and test-only configuration took effect. At the same time, we will confirm that `bootJar` contains neither the launcher nor the preview configuration from the test source set.

### 3.1. Directory Structure

~~~text
boot-test-run-demo/
├── settings.gradle               # or settings.gradle.kts
├── build.gradle                  # or build.gradle.kts
└── src/
    ├── main/
    │   └── java/com/example/demo/
    │       ├── DemoApplication.java
    │       ├── GreetingService.java
    │       ├── ProductionGreetingService.java
    │       └── GreetingController.java
    └── test/
        └── java/
            ├── com/example/preview/
            │   ├── PreviewLauncher.java
            │   └── PreviewConfiguration.java
            └── com/example/demo/
                └── ProductionGreetingServiceTest.java
~~~

`PreviewConfiguration` is placed in package `com.example.preview`, outside `DemoApplication`'s default component scan package `com.example.demo`. Thus it is only registered when the preview launcher explicitly supplies it. This intentional choice prevents a normal main launch from accidentally activating preview beans.

In a real repository, you do not need both sets of Gradle DSL files. Pick one of the two file pairs in Section 4; they are equivalent representations.

## 4. Two Complete Gradle Configurations

### 4.1. Groovy DSL

File `settings.gradle`:

~~~groovy
rootProject.name = 'boot-test-run-demo'
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

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}

tasks.named('bootTestRun') {
    mainClass = 'com.example.preview.PreviewLauncher'
}
~~~

When `java` and the Spring Boot Gradle Plugin are applied, Spring Boot registers `bootRun`/`bootTestRun`. The `tasks.named('bootTestRun')` block selects the test launcher **explicitly**. Without it, the Gradle Plugin scans test output for a main class; if multiple classes declare `public static void main(String[])`, setting `mainClass` avoids relying on default discovery.

### 4.2. Kotlin DSL

File `settings.gradle.kts`:

~~~kotlin
rootProject.name = "boot-test-run-demo"
~~~

File `build.gradle.kts`:

~~~kotlin
import org.springframework.boot.gradle.tasks.run.BootRun

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

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
}

tasks.named<Test>("test") {
    useJUnitPlatform()
}

tasks.named<BootRun>("bootTestRun") {
    mainClass.set("com.example.preview.PreviewLauncher")
}
~~~

In Kotlin DSL, `BootRun` belongs to `org.springframework.boot.gradle.tasks.run.BootRun`; importing it at the top enables `tasks.named<BootRun>`. Changing `mainClass` does not alter the task's classpath: `bootTestRun` still uses the default test runtime classpath.

**A Gradle wrapper or compatible installed Gradle is required.** The configuration files above do not generate `gradlew`/`gradlew.bat` by themselves. Projects generated by Spring Initializr usually include a wrapper; use the wrapper provided by the repository. Spring Boot 3.3 supports JDK 17+; verify your actual Gradle version and JVM before building.

### 4.3. Why Is the Test Dependency Only in `testImplementation`?

The example uses `spring-boot-starter-test` to make JUnit Jupiter and Spring Boot Test utilities available for test compilation. It belongs in test scope and is not needed as a runtime dependency for the production app. Spring context and core annotations used in `main` already come from `spring-boot-starter-web`.

If the test launcher uses additional external libraries strictly for previewing, declare them under `testImplementation` or `testRuntimeOnly` depending on compile vs. runtime needs. Do not move all test dependencies into `implementation` just so `bootRun` can see them; doing so bloats the main runtime classpath and can affect packaging.

## 5. Production Java Code: Main Class, Service, and Endpoint

### 5.1. Main Class

File `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class DemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

Default component scanning starts at `com.example.demo`. Production code for this lesson lives inside this package.

### 5.2. Shared Interface

File `src/main/java/com/example/demo/GreetingService.java`:

~~~java
package com.example.demo;

public interface GreetingService {
    String message();
}
~~~

A public interface so both production code and the test-only launcher in another package can use it.

### 5.3. Production Bean

File `src/main/java/com/example/demo/ProductionGreetingService.java`:

~~~java
package com.example.demo;

import org.springframework.stereotype.Service;

@Service
public class ProductionGreetingService implements GreetingService {

    @Override
    public String message() {
        return "production";
    }
}
~~~

When running the application normally, component scanning picks up this bean. It is the default implementation of `GreetingService`.

### 5.4. Controller

File `src/main/java/com/example/demo/GreetingController.java`:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    private final GreetingService greetingService;

    public GreetingController(GreetingService greetingService) {
        this.greetingService = greetingService;
    }

    @GetMapping("/greeting")
    public String greeting() {
        return greetingService.message();
    }
}
~~~

Spring uses constructor injection to supply the `GreetingService` bean. Normally only `ProductionGreetingService` exists, so `GET /greeting` returns the body `production`.

**Note:** each Java example is a separate file matching its public class name. Do not paste them all into a single Java file.

## 6. Test-Only Java Code: Launcher and Preview Configuration

### 6.1. A Bean Configuration Living Only in `src/test/java`

File `src/test/java/com/example/preview/PreviewConfiguration.java`:

~~~java
package com.example.preview;

import com.example.demo.GreetingService;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Primary;

@Configuration(proxyBeanMethods = false)
public class PreviewConfiguration {

    @Bean
    @Primary
    GreetingService previewGreetingService() {
        return () -> "preview-from-test";
    }
}
~~~

`@Configuration` defines another `GreetingService` bean, and `@Primary` instructs Spring to prefer this bean when a constructor asks for a single `GreetingService` among multiple candidates. `DemoApplication`'s component scan only scans `com.example.demo`, so it **does not automatically scan `com.example.preview`**. We register the preview configuration explicitly in the launcher.

Placing this class under the test source root means the normal main runtime classpath and Boot JAR do not contain it; only environments including test classes see this class.

### 6.2. Launcher for Test Runtime

File `src/test/java/com/example/preview/PreviewLauncher.java`:

~~~java
package com.example.preview;

import com.example.demo.DemoApplication;
import org.springframework.boot.SpringApplication;

public class PreviewLauncher {

    public static void main(String[] args) {
        SpringApplication.run(
                new Class<?>[] {
                    DemoApplication.class,
                    PreviewConfiguration.class
                },
                args
        );
    }
}
~~~

`SpringApplication.run(new Class<?>[] {...}, args)` passes both the production application and the preview configuration as Spring Boot sources. Spring still scans production controllers and services, while the preview configuration contributes an additional bean prioritized by `@Primary`.

This is a **plain Java `main` method**, with no `@Test` annotation and no dependency on the JUnit runner. When `bootTestRun` executes, the Java process invokes `PreviewLauncher.main` and keeps the web server running until stopped by the user. Because the launcher resides in test output, regular `bootRun` will not select it and cannot rely on test classes.

### 6.3. A Separate JUnit Test Proving the Two Concepts Are Distinct

File `src/test/java/com/example/demo/ProductionGreetingServiceTest.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ProductionGreetingServiceTest {

    @Test
    void productionMessage() {
        GreetingService service = new ProductionGreetingService();
        assertEquals("production", service.message());
    }
}
~~~

This test uses JUnit 5 and runs when the `test` task runs; it **is not executed by `bootTestRun` as a test method**. When `bootTestRun` is invoked, Gradle may compile test sources to build the test classpath, yet compiling test files is not the same as running the JUnit `Test` task.

## 7. Running and Observing Both Outcomes

### 7.1. Preparation and Checking Tasks

In the project directory containing the build script:

~~~bash
java -version
./gradlew --version
./gradlew tasks --all
./gradlew clean test
~~~

On Windows PowerShell, use `.\gradlew.bat` instead of `./gradlew`. Use the wrapper only if the repository actually contains `gradlew`/`gradlew.bat` and `gradle/wrapper`.

Locate `bootRun`, `bootTestRun`, and `test` in the task list. If `bootTestRun` is missing, verify that both the Spring Boot Gradle Plugin and Java plugin are applied to the module, Gradle sync succeeded without errors, and your plugin version supports the task.

`clean test` runs the declared JUnit tests; in this sample, `ProductionGreetingServiceTest.productionMessage` should pass.

### 7.2. Running Production Main via `bootRun`

~~~bash
./gradlew bootRun --args='--server.port=18080'
~~~

In another terminal:

~~~bash
curl -s http://localhost:18080/greeting
~~~

Expected body:

~~~text
production
~~~

`bootRun` uses the main runtime classpath and selects `DemoApplication` from main output. `PreviewConfiguration` is absent because it sits in the test source set/package and is not registered.

Stop with Ctrl+C. If you want to run both variants side by side, you can keep this terminal open and use a different port for preview as shown below.

### 7.3. Running the Test Launcher via `bootTestRun`

~~~bash
./gradlew bootTestRun --args='--server.port=18081'
~~~

In another terminal:

~~~bash
curl -s http://localhost:18081/greeting
~~~

Expected body:

~~~text
preview-from-test
~~~

Why the difference?

1. `bootTestRun` picks `PreviewLauncher` from compiled test output.
2. The task classpath includes test classes, main classes/resources, and test dependencies.
3. `PreviewLauncher` calls `SpringApplication.run` with `PreviewConfiguration` among its sources.
4. The Spring context has both the production bean and the preview bean; `@Primary` selects the preview bean when injecting into the controller.
5. The endpoint is still `/greeting` defined by the production controller; only the injected implementation changed.

The two outputs shown are the **HTTP bodies** from the sample app when the build/run succeeds; Gradle and Spring Boot also print startup logs. If a port is busy, change `server.port` and query that port. `curl -s` does not append a trailing newline to the response.

### 7.4. Why Doesn't `bootTestRun` Require Calling `test` First?

`bootTestRun` consumes test output and the test runtime classpath; Gradle wires task/producer dependencies to build the required classes and resources. When invoked, Gradle may execute `compileTestJava`, `processTestResources`, `testClasses`, and related prerequisite tasks. This does not mean Gradle runs the `test` task. To ensure JUnit tests pass before previewing, run `./gradlew test` separately or declare an explicit dependency per project policy.

Never cite "the task compiled test classes" as proof that "JUnit tests passed."

## 8. Further Configuring `bootTestRun` in Groovy/Kotlin DSL

`bootTestRun` is a `BootRun` task and inherits Gradle `JavaExec` capabilities. You can configure `mainClass`, `args`, JVM system properties, environment variables, and the working directory.

### 8.1. Specifying the Main Class Explicitly

**Groovy — fragment added to `build.gradle` with Spring Boot + Java plugin:**

~~~groovy
tasks.named('bootTestRun') {
    mainClass = 'com.example.preview.PreviewLauncher'
}
~~~

**Kotlin — fragment added to `build.gradle.kts` importing `BootRun`:**

~~~kotlin
tasks.named<BootRun>("bootTestRun") {
    mainClass.set("com.example.preview.PreviewLauncher")
}
~~~

Do not copy the fragment a second time if the complete build file from Section 4 already defines it.

Setting `mainClass` explicitly is valuable whenever test output contains multiple `public static void main(String[])` methods, such as multiple experimental launchers. If the package or class name is wrong, Gradle can fail with class-not-found or main-class-not-found errors.

### 8.2. Setting Default Arguments for a Preview Port

**Groovy:**

~~~groovy
tasks.named('bootTestRun') {
    args '--server.port=18081'
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<BootRun>("bootTestRun") {
    args("--server.port=18081")
}
~~~

These are supplementary fragments. Once default args are configured in the script, avoid passing duplicate options on the CLI without knowing how Spring handles repeated keys. In this lesson, using `--args` on the CLI to switch ports per run is sufficient and avoids altering the build script.

### 8.3. Passing a Preview-Specific System Property

**Groovy:**

~~~groovy
tasks.named('bootTestRun') {
    systemProperty 'demo.preview', 'true'
}
~~~

**Kotlin:**

~~~kotlin
tasks.named<BootRun>("bootTestRun") {
    systemProperty("demo.preview", "true")
}
~~~

`System.getProperty("demo.preview")` or Spring property resolution can read this value when the app is configured to use it. Do not confuse a JVM system property with a Gradle project property `-Pdemo.preview=true`: passing `-P` to Gradle does not automatically forward it into the app JVM.

### 8.4. Running with a Spring Profile

~~~bash
./gradlew bootTestRun --args='--spring.profiles.active=local'
~~~

This activates the `local` Spring profile for the application; it only has an effect if the app has configuration or beans tied to that profile. **Using the test classpath does not automatically enable a `test` profile**. Similarly, `@ActiveProfiles` on a JUnit class does not automatically apply when invoking a `main` method via `bootTestRun`.

To enable a fixed profile, design the launcher or task configuration to pass the appropriate args/properties. Check the active profiles log before assuming a profile took effect.

## 9. Optional: Running Production Main with the Test Runtime Classpath

Sometimes you simply want the standard main class `DemoApplication` to see test dependencies or resources (such as an experimental driver) without writing another launcher. You can register a **custom `BootRun` task** and set its classpath to `sourceSets.test.runtimeClasspath`.

### 9.1. Groovy DSL

Fragment for `build.gradle`:

~~~groovy
tasks.register(
    'runMainWithTestClasspath',
    org.springframework.boot.gradle.tasks.run.BootRun
) {
    group = 'application'
    description = 'Runs the production main with test runtime classpath'
    mainClass = 'com.example.demo.DemoApplication'
    classpath = sourceSets.test.runtimeClasspath
}
~~~

### 9.2. Kotlin DSL

Fragment for `build.gradle.kts` with `BootRun` imported:

~~~kotlin
tasks.register<BootRun>("runMainWithTestClasspath") {
    group = "application"
    description = "Runs the production main with test runtime classpath"
    mainClass.set("com.example.demo.DemoApplication")
    classpath = sourceSets["test"].runtimeClasspath
}
~~~

Run:

~~~bash
./gradlew runMainWithTestClasspath --args='--server.port=18082'
~~~

With this lesson's sample application, `GET /greeting` still returns:

~~~text
production
~~~

Why didn't the result become `preview-from-test` even though test classes are on the classpath? `DemoApplication` does not import `PreviewConfiguration`, and component scanning does not scan `com.example.preview`. The classpath only makes the class visible; it **does not automatically register preview beans**.

To get the preview behavior, choose `PreviewLauncher` as the main class or add controlled activation/configuration logic. A custom task like this fits cases where you need **test dependencies or resources** while preserving production startup behavior.

### 9.3. Should You Modify `bootRun`'s Classpath Directly?

You could configure `bootRun` itself to use the test runtime classpath. However, doing so changes the familiar meaning of `bootRun` and may mislead teammates into thinking they are running with the production runtime. When you need both modes side by side, a separately named task like `runMainWithTestClasspath` is clearer.

If a team decides to configure `bootRun` to use the test classpath, document that behavior clearly, specify `mainClass`, and review its impact on development workflows. Never copy test classes/resources into `src/main` just so `bootRun` finds them.

## 10. Maven: Equivalent Options

Maven does not have a Gradle task named `bootTestRun`. In Spring Boot Maven Plugin 3.3, the corresponding goals/options are:

| Need | Maven | Meaning |
| --- | --- | --- |
| Start normal production main | `spring-boot:run` | Main output and runtime of the application |
| Start with test runtime and prefer test main | `spring-boot:test-run` | Goal dedicated to the test/development variant |
| Keep `run` goal but add test classpath | `spring-boot:run -Dspring-boot.run.useTestClasspath=true` | Adds test dependencies/classpath; not equivalent to auto-picking a test launcher |
| Run JUnit | `test` | Maven Surefire/JUnit runner; not a Spring Boot run goal |

Spring Boot Maven Plugin 3.3 documentation notes that `test-run` resolves the main class in order: **configured `mainClass`**, then a main class found in the test classes directory, then the main classes directory. In an example containing `PreviewLauncher`, specify the main class explicitly rather than relying on entrypoint counts.

### 10.1. Minimal Maven POM for the Same Application

If the project uses Maven instead of Gradle, you can use the following `pom.xml` together with **the Java files from Sections 5–6**:

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
    <artifactId>boot-test-run-demo</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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
~~~

This is a **complete POM** in a standalone Maven project. Do not mix Gradle and Maven commands sequentially in the same pipeline if the repository uses only one build tool. If a Maven wrapper is present, use `./mvnw`/`.\mvnw.cmd`; otherwise use a compatible installed Maven CLI.

### 10.2. Running Production and Test Launchers

Run the production app:

~~~bash
mvn spring-boot:run -Dspring-boot.run.arguments=--server.port=18080
~~~

Run the test launcher:

~~~bash
mvn spring-boot:test-run -Dspring-boot.run.main-class=com.example.preview.PreviewLauncher -Dspring-boot.run.arguments=--server.port=18081
~~~

With the sample app and valid environment setup, `/greeting` returns `production` and `preview-from-test` respectively. The `test-run` goal uses the test classpath and test main as configured; it still starts the **Java application**, not replacing `mvn test`.

If you only want the production main to have the test runtime classpath:

~~~bash
mvn spring-boot:run -Dspring-boot.run.useTestClasspath=true -Dspring-boot.run.main-class=com.example.demo.DemoApplication -Dspring-boot.run.arguments=--server.port=18082
~~~

`spring-boot:run`'s `useTestClasspath` option defaults to `false`. In this example, it makes test dependencies/classes available without importing the preview bean because `DemoApplication` still starts. Expected endpoint output remains `production`.

When using a different Maven plugin/version, verify goal names and user properties in the corresponding docs; do not assume Maven has an option named `bootTestRun` like Gradle.

## 11. IDE: Running with the Test Classpath Without Adding a Build Task

You may want an IDE run configuration to debug the test launcher quickly:

1. Import the project via Maven/Gradle from the right root and sync dependencies.
2. Select Java main class **`com.example.preview.PreviewLauncher`**; do not choose `DemoApplication` when you need the preview bean.
3. Select the **test source set / test output** module/classpath, including both test dependencies and main output.
4. Select a compatible JDK and program arguments `--server.port=18081`; keep a valid working directory.
5. Run/Debug, call `/greeting`, confirm `preview-from-test` is returned, and inspect active profiles/beans logs when needed.

Exact UI labels vary across IntelliJ IDEA, Eclipse/STS, and VS Code:

- **IntelliJ IDEA:** create an Application run configuration, select the main class and appropriate "Use classpath of module"; for Gradle projects, verify which test module/classpath the IDE maps. You can also launch Gradle task `bootTestRun` directly from the Gradle tool window to match the build configuration.
- **Eclipse/STS:** create a Java Application run configuration for `PreviewLauncher`, verifying that the project Build Path includes test output/dependencies after a Gradle/Maven refresh.
- **VS Code:** the Java extension provides Java launch configurations; verify that target main class and classpath/module resolution pick up the test source root. Run the Gradle/Maven goal in a terminal if the IDE is out of sync.

**Final check:** the IDE letting you pick `PreviewLauncher` does not prove the run config uses the exact test runtime dependencies. Run the standard task/goal from the terminal and compare main class, JDK, args, active profiles, and output. Never add test-only dependencies to production runtime as a "quick fix" for the IDE.

## 12. Notes on Spring Test Configuration, Resources, and Testcontainers

### 12.1. Do Not Confuse `@TestConfiguration` with Normal Launchers

In Spring Boot tests, `@TestConfiguration` adds test-specific configuration, usually combined with `@Import` or Spring Boot Test mechanisms. It does not mean every `@TestConfiguration` on the test classpath automatically joins every application context.

This lesson's example uses a plain `@Configuration` class under the **test source root outside component scan**, and the launcher registers it explicitly. This design makes the boundary easy to demonstrate: production run does not scan the config, preview launcher adds it, and `@Primary` resolves injection.

When using `@TestConfiguration`, make sure your import or startup setup actually applies it. Never let an app appear to "work" merely by accidental classpath scanning.

### 12.2. Test Resources Can Affect Runtime Configuration

`src/test/resources` belongs to the test runtime classpath. If it contains `application.properties` or `application.yml`, an app launched via `bootTestRun` may resolve different properties than `bootRun`, depending on which resources exist on the classpath and Spring Boot's precedence rules.

Avoid relying on duplicate resource paths and ambiguous classpath ordering to control configuration. Prefer distinctly named files, `spring.config.import`, or explicit profile properties, plus explicit profiles and arguments. Always check effective configuration and active profiles if behavior surprises you.

Development-only test resources should never be mixed into `src/main/resources` or packaged inside the executable Boot JAR.

### 12.3. Testcontainers and Mock Services

A dev application running on the test classpath can use Testcontainers or fixture libraries declared only in `testImplementation`. However:

- Having Testcontainers classes on the classpath **does not start containers automatically**; you need lifecycle management code or Spring Boot service connection support.
- Testcontainers typically requires an available Docker/container runtime.
- A dev launcher stays running longer, so check how containers are stopped when the app exits to avoid resource leaks.
- Never use endpoints, secrets, or sandbox credentials from another environment without clear authorization and purpose.

For this foundational lesson, a lambda-based preview bean is enough to understand classpaths and launchers; no Docker or database is needed to run the example.

## 13. `bootTestRun` Does Not Alter Production Packaging

One boundary to verify carefully: **running with the test classpath does not package test code into the release artifact**.

Under standard Java/Spring Boot Gradle Plugin configuration:

- `bootJar` packages classes and resources from the **main source set** along with production runtime dependencies.
- `src/test/java`, `src/test/resources`, and `testImplementation` serve testing/dev and do not automatically enter the Boot JAR.
- `bootTestRun` launches from test classes/runtime during development; it does not replace `bootJar` or create a deployable executable JAR.

To verify:

~~~bash
./gradlew clean test
./gradlew bootJar
jar tf build/libs/boot-test-run-demo-1.0.0.jar
~~~

In the archive, look for:

~~~text
BOOT-INF/classes/com/example/demo/DemoApplication.class
BOOT-INF/classes/com/example/demo/GreetingController.class
BOOT-INF/classes/com/example/demo/ProductionGreetingService.class
~~~

Typically **absent**:

~~~text
BOOT-INF/classes/com/example/preview/PreviewLauncher.class
BOOT-INF/classes/com/example/preview/PreviewConfiguration.class
BOOT-INF/classes/com/example/demo/ProductionGreetingServiceTest.class
~~~

The archive name reflects root project `boot-test-run-demo` and version `1.0.0` in the example; if your project customizes classifiers or `archiveFileName`, inspect the real output rather than hardcoding paths.

Test the packaged application:

~~~bash
java -jar build/libs/boot-test-run-demo-1.0.0.jar --server.port=18083
~~~

Call `GET http://localhost:18083/greeting`; the expected body is `production`. If the packaged file outputs `preview-from-test` or contains preview classes, check whether test source sets or test dependencies were inadvertently added to `bootJar` or main runtime.

Maven Spring Boot Plugin `repackage` also normally packages the production artifact; `spring-boot:test-run` does not automatically move test-only classes into the deployable JAR.

## 14. When Should You Choose Which Approach?

| Situation | Appropriate Choice | Why |
| --- | --- | --- |
| Run app like production while debugging easily | `bootRun` or `spring-boot:run` | Standard main output and runtime |
| Need a main class in `src/test/java` | `bootTestRun` or `spring-boot:test-run` | Test output and test runtime classpath are used directly |
| Only need test dependencies at runtime while keeping normal main | Custom `BootRun` task with `test.runtimeClasspath`; Maven `run` + `useTestClasspath` | Avoids writing a new launcher unnecessarily |
| Want to verify JUnit assertions | `gradlew test` or `mvn test` | Runs the test runner and reports pass/fail |
| Want integration tests with a real DB/container | Configured test task/suite; optionally a test launcher for demos | Requires setup/teardown contracts and assertions |
| Want to build the deployable artifact | `bootJar`/`bootWar` or Maven `package` + `repackage` | Production packaging does not use test launchers |
| Want to preview app with dev fixtures/mocks | `bootTestRun` with explicitly imported test-only config | Preserves production/test boundary |
| Project has a custom `integrationTest` source set instead of default `test` | Custom `BootRun` task with `integrationTest.runtimeClasspath` | `bootTestRun` targets the `test` source set by default |

If you only need to enable a `local` profile without any test dependencies or test classes, `bootRun --args='--spring.profiles.active=local'` may suffice. Add the test classpath only when there is a **genuine need for test-only classes, resources, or dependencies**.

## 15. Common Errors and How to Verify

| Symptom | Likely Cause | How to Fix |
| --- | --- | --- |
| `Task 'bootTestRun' not found` | Spring Boot Gradle Plugin or Java plugin not applied to module; unsupported plugin version | Check `plugins`, `./gradlew tasks --all`, and plugin version |
| `Could not find or load main class PreviewLauncher` | Test files uncompiled, wrong package/class, or incorrect `mainClass` | Check `src/test/java`, `build/classes/java/test` output, and `mainClass` value |
| Multiple main methods and wrong launcher runs | Relying on auto-detection | Set `mainClass` explicitly in the `BootRun` task |
| `bootTestRun` still returns `production` | Has test classpath, but preview config not imported or bean not selected | Check launcher, package scan, `@Import`/sources, `@Primary` |
| `bootRun` cannot see test dependency | Test scope is not part of main runtime classpath | Use `bootTestRun` or a `BootRun` task with test classpath; do not casually move deps to production |
| `bootTestRun` does not run JUnit tests | It is an app launch task, not a test runner | Run `gradlew test` or `mvn test` separately |
| Preview startup fails with port already in use | Both apps use the same default port | Pass distinct `--server.port` values per process |
| `@ActiveProfiles("test")` has no effect | Annotation on JUnit tests does not control a Java `main` launcher | Pass `--spring.profiles.active=test` or configure the launcher |
| IDE runs differently from Gradle | IDE uses different main/test classpath, JVM, or args | Compare run config with CLI `bootTestRun` task |
| Preview works, production JAR fails | Production relies on a test-only bean or dependency | Inspect `bootRun`, `bootJar`/`java -jar`, and production dependencies |
| `ClassNotFoundException` only in `java -jar` | Release code accidentally calls a test-scoped class | Move valid runtime dependency to main or remove test-only coupling |
| Test resource fails to load | File not in `src/test/resources` or wrong path | Check `processTestResources`, test output, and classpath |
| `bootTestRun` with Testcontainers hangs/fails to start | Docker or container lifecycle not configured | Check launcher/service-connection code, Docker availability, logs |
| New `integrationTest` source set ignored by `bootTestRun` | Task targets `test` by default, not arbitrary source sets | Create a custom `BootRun` task with `integrationTest` runtime classpath |
| Maven `test-run` unrecognized | Invalid plugin prefix/version or project setup | Check Spring Boot Maven Plugin in POM and compatible version |

**Do not confuse "compiled test sources" with "passing tests" or "clean release artifact."** All three require verification through three distinct paths.

## 16. Practical Verification Workflow

A repeatable workflow whenever a project adds a preview/test-runtime mode:

1. **Clarify the need:** do you need a launcher in test sources, a test dependency, or just a Spring profile?
2. **Keep dependencies in proper scopes:** production in `implementation`/`runtimeOnly`, test-only in `testImplementation`/`testRuntimeOnly`.
3. **Configure the launcher transparently:** set `mainClass` explicitly and import test-only configuration intentionally.
4. **Verify tasks:** `./gradlew tasks --all` confirms `bootRun`/`bootTestRun` exist in the application module.
5. **Run unit tests:** `./gradlew clean test` and record results. If only a launcher exists without JUnit tests, do not claim tests pass just because `bootTestRun` runs.
6. **Run production:** `bootRun` on a dedicated port, confirm production endpoint output.
7. **Run preview:** `bootTestRun` on a dedicated port, confirm test-only endpoint output.
8. **Verify release:** `bootJar`/`java -jar` must exhibit production behavior; use `jar tf` to confirm test-only classes are absent from the artifact.
9. **Align IDE and CI:** document which task serves demo/dev, which runs tests, and which builds release packages.

### Exercise 1: Reading Tasks and Classpaths Correctly

**Question:** `bootTestRun` uses `sourceSets.test.runtimeClasspath`, so does it automatically run every JUnit test class it finds?

**Answer:** No. The task executes the application's `main` method, not a JUnit runner. To run assertions, use `test` and the testing framework.

### Exercise 2: Adding a Test-Only Dependency

In the Gradle variant, suppose the preview launcher needs a mocking library declared only in `testImplementation`. It compiles in `src/test/java` and runs via `bootTestRun`. Why doesn't `bootRun` see that library?

**Answer:** `bootRun` uses the main runtime classpath. Test dependencies are not included there by default; only the test runtime classpath includes them. Choose the task/classpath matching your goal.

### Exercise 3: Distinguishing Classpath from Bean Activation

**Question:** `runMainWithTestClasspath` has `PreviewConfiguration.class` visible, yet `/greeting` still returns `production`. Is this a Gradle missing-dependency bug?

**Answer:** No. The class exists on the classpath, but the Spring context was never told to import it. The preview launcher calls `SpringApplication.run` with `PreviewConfiguration.class` as an extra source, allowing `@Primary` to take effect.

### Exercise 4: Maven

**Question:** What is the difference between `spring-boot:test-run` and `spring-boot:run -Dspring-boot.run.useTestClasspath=true`?

**Answer:** `test-run` is designed to launch with the test runtime and prioritize a main class from test classes; `run` with `useTestClasspath=true` keeps the `run` goal while adding the test classpath. When you want a test main class, choose `test-run` or specify `mainClass` explicitly.

### Exercise 5: Production Packaging

**Question:** If a published JAR contains `PreviewLauncher.class` or a test-only dependency, what should you inspect?

**Answer:** Inspect `sourceSets.main`, `bootJar.classpath`, custom copy/packaging logic, dependency scopes, and whether anyone pulled test output into the production archive. Never treat a working `bootTestRun` as proof of a clean release JAR.

**Completion criteria:** you can start production and preview on two ports, observe `production`/`preview-from-test` respectively, run the JUnit test separately, explain how the test runtime classpath differs from main runtime, and prove the release Boot JAR excludes the preview launcher.

## 17. Official References

- Spring Boot 3.3 — Gradle Plugin, Running your Application / Using a Test Main Class: https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html
- Spring Boot 3.3 — Maven Plugin, Running your Application / `spring-boot:test-run` / `useTestClasspath`: https://docs.spring.io/spring-boot/3.3/maven-plugin/run.html
- Gradle Java Plugin — Source Sets: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle `JavaExec` task: https://docs.gradle.org/current/dsl/org.gradle.api.tasks.JavaExec.html
- Spring Boot 3.3 — Packaging Executable Archives with Gradle: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 — Testing: https://docs.spring.io/spring-boot/3.3/reference/testing/index.html

When applying this in real projects, consult the documentation for your exact Gradle wrapper and Spring Boot plugin version. **`bootTestRun` is a tool for running a development variant on the test runtime classpath; test correctness and production artifact cleanliness must still be verified independently.**