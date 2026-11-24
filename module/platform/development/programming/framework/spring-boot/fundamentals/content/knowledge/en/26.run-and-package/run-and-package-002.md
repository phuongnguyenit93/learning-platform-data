# Compilation, Testing, and Packaging Are Different Stages

When developing a Spring Boot application, you often encounter commands like `./gradlew compileJava`, `./gradlew test`, `./gradlew bootJar`, `./gradlew build`, `mvn compile`, `mvn test`, and `mvn package`. These commands may invoke one another through a task graph or build lifecycle, yet **compilation, testing, and packaging remain three distinct jobs**.

- **Compilation**: turns Java source into `.class` bytecode, checking syntax, types, and rules the Java compiler can detect.
- **Testing**: runs scenarios written as tests and compares actual outcomes against expectations.
- **Packaging**: creates an artifact, such as a JAR/WAR, from compiled classes, resources, and required dependencies according to the build configuration.

An application that **compiles** can still have logic bugs and failing tests. A project that **produces a JAR** might not have run tests yet. An executable JAR that **packages successfully** can still fail at startup due to missing configuration, an unavailable database, or runtime classpath issues.

Understanding the boundaries of each stage helps you read build logs, choose the right command during development, structure CI/CD pipelines, and avoid confusing "an artifact exists" with "fully tested".

This lesson uses examples with Spring Boot 3.x, Java 17/21, Gradle, and Maven. Commands and build files illustrate common conventions; task graphs or plugin executions may be customized in real projects.

## 1. Three different questions in a build process

When a teammate asks "has the app finished building?", that question can mean three things:

1. **Does the source code compile?** Does the compiler generate bytecode without errors?
2. **Does the application pass the written tests?** Do JUnit tests, integration tests, or other checks pass?
3. **Is there a file ready to run or release?** Did the packaging tool create the proper executable Spring Boot JAR/WAR?

Comparison table:

| Stage | Primary inputs | Output | Does not automatically guarantee |
| --- | --- | --- | --- |
| Compilation | `.java` and compile classpath | `.class`, generated sources/metadata | Correct logic, valid bean wiring, app can run |
| Testing | Test source, compiled classes, test runtime | Pass/fail, test reports | Full bug coverage, production matching test |
| Packaging | Compiled main classes, resources, runtime dependencies | JAR/WAR or other artifact | Tests ran, service starts successfully |

You can visualize the workflow as:

~~~mermaid
flowchart TD
    S["src/main/java"] --> C["Compile main code"]
    R["src/main/resources"] --> RES["Process resources"]
    C --> CL["Main .class files"]
    T["src/test/java"] --> TC["Compile test code"]
    CL --> TC
    TC --> TE["Run test task"]
    TR["src/test/resources"] --> TC
    CL --> PK["Package artifact"]
    RES --> PK
    D["Runtime dependencies"] --> PK
    PK --> J["Plain JAR / Boot executable JAR / WAR"]
    J --> RUN["Run packaged artifact"]
    TE -. "CI quality gate" .-> RUN
~~~

The diagram distinguishes two relationships. Technically, running tests requires compilation; packaging requires compiled classes and resources. However, **packaging does not necessarily require running tests**. A CI pipeline may require tests to pass before publishing; that is an additional policy applied on top.

## 2. Compilation: generating bytecode, not running the application

Java sources are usually placed under:

~~~text
src/main/java/
└── com/example/demo/
    ├── DemoApplication.java
    ├── service/PriceService.java
    └── web/PriceController.java
~~~

During compilation, a tool like `javac` parses the Java source, resolves referenced types, checks language rules, and emits `.class` files.

Example:

~~~java
public class PriceCalculator {
    public long discount(long price, int percent) {
        return price * (100 - percent) / 100;
    }
}
~~~

The Java compiler accepts this method if all references and types are valid. But if `percent = 200`, the method returns a negative result. A successful compile does not confirm this is a business-permitted outcome.

A compiler error:

~~~java
public int totalPrice() {
    return "100";  // String cannot be returned as int.
}
~~~

This is a **compile-time** error. You do not need to start the Spring context or run unit tests to catch it.

### 2.1. What does the compiler check?

The Java compiler can detect:

- Invalid Java syntax, missing punctuation, or illegal declarations.
- Incompatible data types.
- Methods, constructors, or fields not found on the compile classpath.
- Access modifier violations.
- Unhandled checked exceptions per Java rules.
- Certain generic constraints and interface implementations.
- Errors from configured annotation processors.

The compiler **does not automatically verify**:

- Whether Spring has registered enough beans for constructor injection.
- Whether `application-prod.yml` has a valid JDBC URL.
- Whether the database, Redis, or Kafka is running.
- Whether an API returns the right data for all inputs.
- Whether a transaction rolls back as expected.
- Whether HTTP endpoints start up and accept requests.

Those typically surface in tests, startup, or runtime operation.

### 2.2. Compilation output

In a typical Gradle Java project:

~~~text
build/classes/java/main/com/example/demo/service/PriceService.class
~~~

In Maven:

~~~text
target/classes/com/example/demo/service/PriceService.class
~~~

This is compilation output. These `.class` files are not automatically packaged into an executable JAR and do not necessarily have runtime dependencies sitting next to them.

### 2.3. Compile classpath differs from runtime classpath

The compiler needs to see classes referenced by the source code. At runtime, the JVM also needs implementations and runtime dependencies.

Gradle example:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
~~~

Meaning:

| Configuration | Role |
| --- | --- |
| `implementation` | Main code dependency in Gradle Java's compile/runtime model |
| `compileOnly` | Needed at compile time, not automatically included at runtime |
| `annotationProcessor` | Runs processors inside the compiler |
| `runtimeOnly` | Needed at runtime, not necessarily at compile time |
| `testImplementation` | Used for compiling and running tests |
| `testRuntimeOnly` | Provides runtime dependencies only for tests |

For example, the PostgreSQL driver may only be needed at runtime because the source code uses JDBC abstractions instead of directly importing the driver implementation.

A project that compiles can still fail with `ClassNotFoundException` or `NoClassDefFoundError` if a dependency needed at runtime is missing.

### 2.4. Annotation processing still belongs to compilation

Lombok, MapStruct, or the Spring Boot configuration processor can generate sources/metadata during compilation:

~~~groovy
dependencies {
    annotationProcessor 'org.springframework.boot:spring-boot-configuration-processor'
}
~~~

Running a processor does not mean JUnit tests have run. It is an activity within the build/compile pipeline.

## 3. Testing: executing code and comparing against expectations

Tests do not just verify that Java source is valid—they **execute** behavior.

Example of a fee-calculation service:

~~~java
package com.example.demo.service;

public class ShippingCalculator {

    public long calculate(int distanceKm) {
        if (distanceKm <= 10) {
            return 10_000L;
        }
        return 10_000L + (distanceKm - 10) * 500L;
    }
}
~~~

The class above compiles, yet may violate the requirement "negative distance must be rejected".

JUnit 5 test:

~~~java
package com.example.demo.service;

import static org.junit.jupiter.api.Assertions.assertThrows;
import org.junit.jupiter.api.Test;

class ShippingCalculatorTest {

    @Test
    void rejectsNegativeDistance() {
        ShippingCalculator calculator = new ShippingCalculator();

        assertThrows(
                IllegalArgumentException.class,
                () -> calculator.calculate(-1)
        );
    }
}
~~~

This test fails against the current implementation because the method returns `10_000` instead of throwing `IllegalArgumentException`.

Points to remember:

- **Compiling main code** can succeed.
- **Compiling test code** can succeed.
- **Running tests** can fail because an assertion fails.

You cannot substitute the first two steps for the third.

### 3.1. Compiling tests vs. executing tests

Tests are also Java sources that need compilation:

~~~text
src/test/java/com/example/demo/service/ShippingCalculatorTest.java
~~~

A typical testing flow:

~~~mermaid
flowchart TD
    A["Main source"] --> B["Compile main"]
    B --> C["Main classes"]
    T["Test source"] --> D["Compile tests"]
    C --> D
    D --> E["Test classes"]
    E --> F["JUnit Platform / test runner"]
    F --> G{"Assertions"}
    G -->|Pass| H["Test result: passed"]
    G -->|Fail / exception| I["Test result: failed"]
~~~

With Gradle:

~~~bash
./gradlew compileTestJava
~~~

typically compiles test sources and prerequisite tasks, **without running assertions**.

Whereas:

~~~bash
./gradlew test
~~~

typically compiles the required sources and executes the test task as configured.

With Maven:

~~~bash
mvn test-compile
~~~

runs phases up to test compilation; whereas:

~~~bash
mvn test
~~~

runs the test phase, normally via the Maven Surefire Plugin.

### 3.2. Passing tests have scope

Passing tests prove that **the executed assertions** hold in the current test environment. They do not guarantee that:

- All edge cases are checked.
- Every external service in production is healthy.
- There are no race conditions or timing-dependent bugs.
- Performance meets requirements under heavy load.
- An artifact was packaged from the exact revision being tested.

If you want those guarantees, you need additional test types and corresponding release processes.

## 4. Test types in Spring Boot

| Test type | Goal | Needs Spring context? |
| --- | --- | --- |
| Unit test | An isolated class/function | Not required |
| MVC slice test | Controller, mapping, serialization within the slice | Yes, scoped down |
| JPA slice test | Repository and persistence slice | Yes, scoped down |
| Integration test | Multiple components working together | Potentially yes |
| Contract test | Contract between service/provider/client | Depends on tool |
| End-to-end test | Complete flow across multiple layers | Usually needs realistic environment |
| Smoke test | Minimal functionality after starting/deploying | Usually runs against started artifact |
| Performance/load test | Latency, throughput, resources | Runs with load and dedicated environment |

### 4.1. Unit tests do not need a Boot context

For `ShippingCalculator`, you can instantiate the class with `new` and test it directly. Starting the entire Spring container just to test a calculation usually adds time and coupling.

### 4.2. SpringBootTest checks wiring and runtime context

~~~java
import static org.assertj.core.api.Assertions.assertThat;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class ApplicationContextTest {

    @Autowired
    private PriceService service;

    @Test
    void loadsService() {
        assertThat(service).isNotNull();
    }
}
~~~

This test can catch bean wiring or property binding errors when starting the Spring context. However, it typically runs with test-environment profiles and resources, and does not automatically guarantee production configuration is right.

### 4.3. Slice tests do not replace full integration tests

Example:

~~~java
@WebMvcTest(PriceController.class)
class PriceControllerTest {
    // Tests the MVC slice, mocking required dependencies.
}
~~~

`@WebMvcTest` narrows initialization scope compared to `@SpringBootTest` in common configurations. Passing controller slice tests does not prove every bean and integration across the whole application can start.

### 4.4. Integration tests are often a separate task

Some projects run only unit tests in Gradle `test`, keeping integration tests in an `integrationTest` task. Maven may use Surefire for unit tests and Failsafe for integration tests.

Therefore, saying "tests ran" requires context: **which task/test suite ran**? If `integrationTest` is not wired into the build quality gate, it will not run automatically just because you ran `./gradlew build`.

## 5. Packaging: turning output into an artifact

Packaging produces a file for distribution or execution, usually a JAR/WAR.

A plain JAR contains classes/resources:

~~~text
demo-app.jar
├── META-INF/MANIFEST.MF
├── com/example/demo/DemoApplication.class
├── com/example/demo/service/PriceService.class
└── application.yml
~~~

A file ending in `.jar` is **not automatically** an executable Spring Boot JAR with all dependencies included.

### 5.1. Executable Spring Boot JAR

When using the Spring Boot Gradle plugin's `bootJar` or the Spring Boot Maven Plugin's `repackage` properly, the artifact can have this structure:

~~~text
demo-app.jar
├── META-INF/
│   └── MANIFEST.MF
├── org/springframework/boot/loader/...
└── BOOT-INF/
    ├── classes/
    │   ├── com/example/demo/...
    │   └── application.yml
    └── lib/
        ├── spring-boot-....jar
        ├── spring-context-....jar
        ├── spring-web-....jar
        └── ...
~~~

Main parts:

- `BOOT-INF/classes`: application classes and resources.
- `BOOT-INF/lib`: runtime dependency JARs.
- Spring Boot loader and manifest: starts the application and loads nested dependency JARs.

An executable Boot JAR can be run with:

~~~bash
java -jar build/libs/demo-app-1.0.0.jar
~~~

The filename depends on the project version/classifier/packaging configuration.

### 5.2. Plain JAR vs. executable Boot JAR

| Property | Plain JAR | Boot executable JAR |
| --- | --- | --- |
| Main classes/resources | Present | Present, usually in `BOOT-INF/classes` |
| Runtime dependencies | Usually not packaged into the same archive | Usually in `BOOT-INF/lib` |
| Boot launcher | Not by default | Present per Boot executable layout |
| Standalone `java -jar` run | Not guaranteed | Designed to run this way |
| Purpose | Java library/artifact | Standalone runnable Spring Boot application |

If running a plain JAR with `java -jar` gives `no main manifest attribute` or missing dependencies, it is not necessarily a compiler error. You may have picked the wrong artifact.

### 5.3. Successful packaging does not guarantee runtime startup

A validly created executable JAR can still fail when:

- Database or Kafka is unreachable.
- The port is already in use by another process.
- Required environment variables/secrets are missing.
- Spring property binding or bean configuration fails.
- The runtime Java version is incompatible.
- The classpath has missing or conflicting libraries.
- An external file or certificate does not exist.

To catch those issues, you need to run/smoke-test the artifact in an appropriate environment.

## 6. Gradle: independent tasks connected by a dependency graph

In a project using the Java plugin and Spring Boot plugin, common tasks include:

| Task | Meaning | Runs JUnit tests? | Produces executable Boot JAR? |
| --- | --- | --- | --- |
| `compileJava` | Compiles main source | No | No |
| `processResources` | Prepares main resources | No | No |
| `classes` | Finalizes main classes/resources output | No | No |
| `compileTestJava` | Compiles test source | Does not run assertions | No |
| `test` | Executes the test task | Yes | Not needed |
| `jar` | Creates plain JAR | Not required | No |
| `bootJar` | Creates executable Spring Boot JAR | Not required | Yes |
| `assemble` | Artifact assembly tasks | Usually no | Usually yes when bootJar is wired |
| `check` | Verification tasks | Usually includes `test` | Not required |
| `build` | Assembly + verification | Usually includes `test` | Usually yes |
| `bootRun` | Runs app from runtime classpath | Not by default | No |
| `clean` | Deletes build outputs | No | No |

The "usually" caveats matter because build scripts can disable tasks, add integration tests, or alter dependencies.

### 6.1. Compiling main code

~~~bash
./gradlew compileJava
~~~

Main Java output is typically placed in:

~~~text
build/classes/java/main/
~~~

This command does not need to build an executable JAR. Nor does it start the Spring container.

### 6.2. Compiling tests and running tests

~~~bash
./gradlew compileTestJava
./gradlew test
~~~

`test` typically triggers prerequisite tasks such as compiling main/test code and processing resources. You do not necessarily need to call both commands in your daily loop; the example shows them separately to clarify their roles.

### 6.3. Creating an executable JAR

~~~bash
./gradlew bootJar
~~~

`bootJar` needs compiled main classes/resources and runtime dependencies. In a typical setup, **this task does not depend on `test`**, so you can produce a JAR even when tests have not run.

Calling only `bootJar` means you asked for packaging, not full verification.

### 6.4. What does Gradle build do?

~~~bash
./gradlew build
~~~

In a typical Java/Spring Boot project, `build` depends on `assemble` and `check`:

~~~mermaid
flowchart TD
    BUILD["build"] --> ASSEMBLE["assemble"]
    BUILD --> CHECK["check"]
    ASSEMBLE --> JAR["jar"]
    ASSEMBLE --> BOOTJAR["bootJar, if present"]
    CHECK --> TEST["test"]
    JAR --> CLASSES["classes"]
    BOOTJAR --> CLASSES
    TEST --> TESTCLASSES["testClasses"]
    TESTCLASSES --> CLASSES
~~~

So `build` typically creates artifacts **and** runs tests wired into `check`. However, custom integration tests, security scans, or E2E tests only run if you configure them in the task graph/pipeline.

### 6.5. assemble vs. check

~~~bash
./gradlew assemble
~~~

typically creates artifacts without needing to run tests.

~~~bash
./gradlew check
~~~

runs verification tasks, usually including `test`, without necessarily packaging.

These two responsibilities can live in separate CI jobs: one job builds the artifact, another verifies quality; publishing happens only when both succeed.

## 7. Example Gradle build.gradle for Spring Boot

Groovy DSL example using Spring Boot 3.3.x and Java 21:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
}

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

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Parts:

- `java` creates the basic compile, test, jar, and lifecycle tasks.
- The Spring Boot plugin adds `bootJar` and `bootRun`.
- Dependency management/BOM aligns Spring Boot library versions.
- Toolchain selects the JDK for compilation.
- `spring-boot-starter-web` brings the web stack into runtime.
- `spring-boot-starter-test` provides JUnit and test support.
- `useJUnitPlatform()` lets the Gradle test task execute tests on the JUnit Platform.

The version is just an example for the Spring Boot 3.3 line; in a real project, use the version controlled by your repository.

### 7.1. When there are two JAR files

With the Boot Gradle plugin and Java plugin, a project can often generate:

~~~text
build/libs/
├── demo-app-1.0.0.jar
└── demo-app-1.0.0-plain.jar
~~~

The file without a classifier is typically the executable Boot JAR from `bootJar`; the `-plain.jar` file is typically generated by the `jar` task. Project configuration may rename or disable one of them.

Do not blindly use wildcards to select the deployment artifact: if you accidentally pick `-plain.jar`, the application may not run with `java -jar` as expected.

### 7.2. Library modules vs. application modules

A multi-module project might consist of:

~~~text
project/
├── common-model/
├── business-core/
└── api-app/
~~~

`common-model` and `business-core` usually only need plain library JARs. Only `api-app` needs an executable Boot JAR.

Example in `api-app/build.gradle`:

~~~groovy
dependencies {
    implementation project(':common-model')
    implementation project(':business-core')
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
~~~

Running:

~~~bash
./gradlew :api-app:bootJar
~~~

can compile the required dependency modules, but **does not automatically prove that unit tests in all modules ran**. A release pipeline needs verification gates covering all relevant modules.

## 8. Maven: running by lifecycle phases

Maven defines a default lifecycle with multiple phases. Common milestones:

~~~mermaid
flowchart LR
    A["validate"] --> B["process-resources"]
    B --> C["compile"]
    C --> D["test-compile"]
    D --> E["test"]
    E --> F["package"]
    F --> G["integration-test"]
    G --> H["verify"]
    H --> I["install"]
    I --> J["deploy"]
~~~

This is a simplified diagram, not every intermediate phase. Maven only performs actions corresponding to plugin goals bound to phases.

Unlike Gradle's `bootJar` which is an independent task, `mvn package` invokes a **lifecycle phase**. Maven runs the phases preceding `package`.

### 8.1. mvn compile

~~~bash
mvn compile
~~~

Typically processes main resources and compiles main sources. Output is usually under `target/classes`.

### 8.2. mvn test-compile

~~~bash
mvn test-compile
~~~

Runs phases up to test compilation, without executing the test phase itself.

### 8.3. mvn test

~~~bash
mvn test
~~~

Typically compiles main code, compiles test code, and then runs tests via the Surefire Plugin.

### 8.4. mvn package

~~~bash
mvn package
~~~

By default executes phases up to `package`, **including `test`**. However, tests can be skipped or plugin bindings customized.

For a Spring Boot app using `jar` packaging, the Maven JAR Plugin can create a JAR. Turning it into an executable Spring Boot JAR requires the Spring Boot Maven Plugin's `repackage` goal to be configured properly.

### 8.5. mvn verify

~~~bash
mvn verify
~~~

Runs phases after `package`, usually where projects bind integration tests and verification plugins. For example, the Maven Failsafe Plugin can run integration tests in `integration-test` and check results in `verify`.

However, if the project has not configured integration tests, `verify` does not synthesize an integration test suite on its own.

### 8.6. install and deploy do not mean deploying to a server

`mvn install` places the artifact into the local Maven repository by convention. `mvn deploy` can publish the artifact to a remote artifact repository as configured.

They **do not mean** automatically deploying the Spring Boot app to Kubernetes, a VM, or a service runtime. Deploying the application is a separate step in CI/CD.

## 9. Example Spring Boot pom.xml

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>demo-app</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>21</java.version>
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

With the Spring Boot starter parent, declaring the Spring Boot Maven Plugin by convention usually activates the appropriate `repackage` configuration. With a custom Maven parent or just importing a dependency BOM, you must verify the plugin version and goal executions; not every `mvn package` automatically creates an executable Boot JAR.

### 9.1. Comparing Gradle and Maven commands

| Goal | Common Gradle | Common Maven |
| --- | --- | --- |
| Compile main | `./gradlew compileJava` | `mvn compile` |
| Compile test | `./gradlew compileTestJava` | `mvn test-compile` |
| Run unit tests | `./gradlew test` | `mvn test` |
| Package Boot app | `./gradlew bootJar` | `mvn package` with repackage configured |
| Verification + assemble | `./gradlew build` | `mvn package` / `mvn verify` per quality gates |
| Run app from build output | `./gradlew bootRun` | `mvn spring-boot:run` |
| Clean output | `./gradlew clean` | `mvn clean` |

Commands with similar goals do not always run the same number of stages. Maven `package` normally runs tests beforehand; Gradle `bootJar` does not require tests by default.

## 10. Do not confuse running from source with running a packaged artifact

Spring Boot supports:

~~~bash
./gradlew bootRun
~~~

and:

~~~bash
mvn spring-boot:run
~~~

Both approaches typically run the application from compiled classes/resources plus the project's runtime classpath. Creating an executable JAR first is not required.

Running an artifact:

~~~bash
java -jar build/libs/demo-app-1.0.0.jar
~~~

uses the packaged JAR, manifest, Boot loader, and nested libraries.

### 10.1. Key differences

| Characteristic | bootRun/spring-boot:run | java -jar |
| --- | --- | --- |
| Source of classes | Project output | Classes inside the artifact |
| Runtime dependencies | Runtime classpath provided by build tool | Dependencies packaged inside executable archive |
| Needs executable Boot JAR | No | Yes |
| Classpath resources | Often output directory | May be entries inside JAR |
| Verifies exact deploy artifact | Not necessarily | Yes, if running the exact deployed file |

Code example:

~~~java
Resource resource =
        new ClassPathResource("data/catalog.json");

File file = resource.getFile();
~~~

might work when the resource sits in `build/resources/main`, yet fail when the packaged JAR contains `BOOT-INF/classes/data/catalog.json`. A layout-independent approach:

~~~java
try (InputStream input = resource.getInputStream()) {
    // Parse content.
}
~~~

Therefore, `bootRun` succeeding does not replace testing the artifact with `java -jar`.

## 11. Common output directories

| Content | Common Gradle | Common Maven |
| --- | --- | --- |
| Main class files | `build/classes/java/main` | `target/classes` |
| Main resources | `build/resources/main` | `target/classes` |
| Test class files | `build/classes/java/test` | `target/test-classes` |
| Test results | `build/test-results/test` | `target/surefire-reports` |
| HTML test report | `build/reports/tests/test` | Depends on reporting plugin |
| Package JAR | `build/libs` | `target` |

Do not hard-code these directories into runtime logic. They are build tool conventions and can be customized.

In particular, `src/main/resources` is a **source directory**, not a location a deployed application can always access directly. Files packaged onto the classpath should be read through a resource abstraction.

## 12. Inspecting the executable JAR after packaging

Basic checks:

### 12.1. Identify the right file

Example:

~~~text
build/libs/demo-app-1.0.0.jar
~~~

If both `-plain.jar` and the executable JAR exist, clearly distinguish which artifact is used for release.

### 12.2. Inspect contents

The JDK provides:

~~~bash
jar tf build/libs/demo-app-1.0.0.jar
~~~

In a Boot JAR, you usually see:

~~~text
BOOT-INF/classes/
BOOT-INF/lib/
META-INF/MANIFEST.MF
org/springframework/boot/loader/...
~~~

### 12.3. Inspect the manifest

An example Spring Boot 3.x manifest may contain:

~~~text
Manifest-Version: 1.0
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.demo.DemoApplication
Spring-Boot-Version: 3.3.5
~~~

Actual contents depend on Boot version and plugin settings. `Main-Class` is usually the Spring Boot launcher; `Start-Class` is the application entry point.

### 12.4. Smoke-test the artifact

A minimal smoke test after packaging:

1. Run the executable JAR in a test environment.
2. Pass the appropriate profile and external configuration.
3. Wait for startup to complete within a defined timeout.
4. Call the health endpoint or a simple check API.
5. Inspect exit code/logs if startup fails.
6. Stop the process through normal shutdown.

Example:

~~~http
GET /actuator/health
~~~

Response might be:

~~~json
{"status":"UP"}
~~~

If Spring Boot Actuator is present and the endpoint is configured, `UP` only indicates configured health checks are reporting healthy; it does not guarantee every business flow passes.

## 13. Why can one task trigger several other tasks?

Gradle relies on a **task dependency graph**. For example:

~~~bash
./gradlew test
~~~

does not immediately run a JUnit method in isolation; Gradle needs compiled main/test classes and test resources, so it runs the appropriate prerequisite tasks.

Similarly:

~~~bash
./gradlew bootJar
~~~

needs main classes and dependencies for packaging.

However, **task dependencies do not mean every verification runs automatically**. If `bootJar` does not depend on `test`, it can finish without any JUnit assertions running.

### 13.1. UP-TO-DATE and FROM-CACHE

Gradle may display:

~~~text
> Task :compileJava UP-TO-DATE
> Task :processResources UP-TO-DATE
> Task :test UP-TO-DATE
> Task :bootJar
~~~

This is an illustrative log only.

`UP-TO-DATE` means Gradle believes the current outputs reflect the inputs according to task up-to-date rules. `FROM-CACHE` can appear when outputs are fetched from the build cache. Both differ from "the task just actually ran every test from scratch".

When interpreting CI results, know which tasks executed, which were skipped, and whether cache usage complies with the build policy.

### 13.2. clean is not required every time

~~~bash
./gradlew clean build
~~~

deletes outputs and rebuilds them. Useful when verifying a clean build or clearing stale outputs, though it sacrifices incremental build speed. In daily development, running only the needed tasks may suffice.

## 14. Skipping tests: producing an artifact does not mean tests pass

Several commands allow packaging without running tests.

### 14.1. Gradle -x test

~~~bash
./gradlew build -x test
~~~

`-x test` excludes the `test` task from the requested task graph. The command can still run compile and package, as well as other tasks if configured.

If the project has a separate `integrationTest` task, `-x test` does not automatically exclude all other test tasks.

### 14.2. Maven -DskipTests

~~~bash
mvn package -DskipTests
~~~

Usually skips **test execution**, while test sources may still be compiled.

### 14.3. Maven -Dmaven.test.skip=true

~~~bash
mvn package -Dmaven.test.skip=true
~~~

In the common Maven model, this property is used by Compiler/Surefire/Failsafe to skip both test compilation and execution.

### 14.4. Consequences

| Situation | Outcome |
| --- | --- |
| Main compilation succeeds | Main source compiles cleanly |
| Test source compilation succeeds | Test source is syntactically/type-valid |
| Test execution skipped | No evidence that new assertions pass |
| bootJar/package succeeds | Artifact created per build configuration |
| Artifact startup succeeds | Passed partial runtime verification |
| Integration/E2E tests pass | Executed integration/E2E cases met expectations |

Never report "tests passed" if tests were actually skipped. For safe releases, quality gates should check verification results per project standards.

## 15. Comparing Maven package and Gradle bootJar

One common misconception:

> "Both create a JAR, so they definitely run the same test steps."

Incorrect.

In Maven, `mvn package` goes through preceding phases, which usually includes `test`. In Gradle, `./gradlew bootJar` is a packaging task and does not depend on `test` by default. To make Gradle run standard lifecycle verification, `./gradlew build` is more appropriate, provided the project wires test tasks into `check`.

Even with Maven, `-DskipTests` or custom plugin configurations can prevent tests from running. Always base conclusions on the actual task graph/lifecycle and reports.

## 16. Integration tests do not appear automatically in a build

A project might separate tests:

~~~text
src/test/java/                    # Unit tests and tests belonging to the test task
src/integrationTest/java/         # Integration test source set if configured manually
~~~

Gradle does not automatically treat `integrationTest` as a task simply because the directory exists. Proper source set/task setup and wiring are required.

A build might have:

~~~bash
./gradlew test
./gradlew integrationTest
~~~

If `integrationTest` is not wired into `check`, running `./gradlew build` might not execute it.

With Maven, a common choice is:

- Surefire Plugin runs unit tests in the `test` phase.
- Failsafe Plugin runs integration tests in `integration-test` and checks results in `verify`.

When properly configured:

~~~bash
mvn verify
~~~

can run integration tests as well. However, `mvn package` stops before `integration-test`, so it does not automatically run tests bound after `package`.

**Lesson:** to know what was tested, inspect task/phase/plugin configuration and test reports, not just aggregate command names.

## 17. Multi-module: compile dependencies differ from test dependencies

Suppose a project has:

~~~text
project/
├── common-model/
├── business-core/
└── api-app/
~~~

`api-app` depends on `business-core` and `common-model`:

~~~groovy
dependencies {
    implementation project(':common-model')
    implementation project(':business-core')
}
~~~

When running:

~~~bash
./gradlew :api-app:bootJar
~~~

Gradle can build the required outputs of dependency modules. However, **you cannot infer** that `:business-core:test` or `:common-model:test` ran just because the app artifact was created.

A multi-module release pipeline should define:

- Which modules have mandatory tests.
- Which integration tests cover the whole system.
- Which app modules build executable JARs.
- Which library modules only need plain JARs.
- Which conditions must pass before publishing artifacts.

You do not need to enable the Spring Boot plugin for every library module. A library can use the `java-library` plugin, while the app module uses `bootJar`.

## 18. CI/CD: building the artifact and the release gate are two different things

A pipeline can be organized into two parallel jobs:

~~~mermaid
flowchart TD
    C["Commit"] --> T["Job A: test / verification"]
    C --> P["Job B: package"]
    T --> G{"Quality gate"}
    P --> G
    G -->|Both succeed| U["Publish artifact"]
    G -->|Either fails| X["Block release"]
    U --> ST["Deploy staging / smoke test"]
    ST --> PR["Promote production per policy"]
~~~

A hypothetical configuration:

~~~yaml
jobs:
  test:
    steps:
      - run: ./gradlew test

  package:
    steps:
      - run: ./gradlew bootJar

  publish:
    needs: [test, package]
    steps:
      - run: echo "Publish only after both jobs pass"
~~~

This is **pseudo YAML**, not a complete workflow for any specific CI provider. In practice, you also need source checkout, JDK setup, artifact storage/transfer, credentials, and publish permissions.

Key point: **an artifact being created** does not mean **the artifact is allowed to be published**.

### 18.1. Using the same source revision

If the test job runs commit A while the package job runs commit B, test results from A do not prove artifact B meets requirements.

CI should bind together:

- Commit SHA/source revision.
- Build tool and JDK version.
- Dependency resolution.
- Artifact version/checksum.
- Test/verification results.
- The environment used to run smoke tests.

### 18.2. Promote one artifact instead of rebuilding arbitrarily

In a pipeline with staging and production, promoting the same immutable artifact reduces the risk that production differs from what was tested due to dependency or generated-resource changes on rebuild.

If reproducible builds are needed, control timestamps, versions, toolchains, generated inputs, and other factors affecting output.

## 19. Which stage failed?

| Symptom | Stage | How to investigate |
| --- | --- | --- |
| `cannot find symbol` | Compile | Misspelled class/method name or missing compile dependency |
| `incompatible types` | Compile | Check types, generics, method signature |
| Processor did not emit generated class | Annotation processing/compile | Check processor path and config |
| `No tests found` | Test discovery | Check JUnit engine, filters, source sets |
| `AssertionFailedError` | Test execution | Read expected/actual and business logic |
| `Failed to load ApplicationContext` in test | Test runtime | Check bean wiring/test profile/config |
| `Could not resolve dependencies` | Dependency resolution | Check repositories, versions, network |
| `Main class name has not been configured` in `bootJar` | Packaging | Check main class detection/config |
| `no main manifest attribute` on run | Artifact execution | Possibly picked plain JAR by mistake |
| `ClassNotFoundException` when running JAR | Runtime/classpath | Check runtime deps/Boot loader |
| `Port already in use` | Runtime startup | Check port config/running processes |
| `Failed to bind properties` | Runtime configuration | Check config values, profile, validation |
| App runs but HTTP does not respond | Runtime/deployment | Check server, routing, health, network |

### 19.1. "BUILD FAILED" is only a summary conclusion

If the log shows:

~~~text
> Task :compileJava FAILED
~~~

that is a compilation error.

If:

~~~text
> Task :test FAILED
~~~

that is a test task failure.

If:

~~~text
> Task :bootJar FAILED
~~~

that is a packaging task or prerequisite failure. Read **the first task that actually failed**, not just the `BUILD FAILED` line.

For instance, running `./gradlew bootJar` when `:compileJava` fails means the compile prerequisite failed; the Boot JAR may not have been created at all.

### 19.2. Build reported success does not mean the right goal was met

If you run `compileJava` and see success when you actually needed an executable JAR, you chose **the wrong task** for that goal. The compiler did nothing wrong; it simply was not asked to package.

Similarly, a Maven project with `pom` packaging will not necessarily produce an app JAR just because `mvn package` succeeded.

## 20. Artifact existence does not mean tests passed

A concrete case:

~~~bash
./gradlew bootJar
~~~

can produce `build/libs/demo-app-1.0.0.jar` even when the unit test:

~~~java
@Test
void shouldRejectNegativeDistance() {
    assertThrows(
            IllegalArgumentException.class,
            () -> new ShippingCalculator().calculate(-1)
    );
}
~~~

is failing. The packaging command does not necessarily execute tests.

Another case:

~~~bash
mvn package -DskipTests
~~~

can create an artifact even though test execution was skipped.

Therefore, when reviewing a pull request or CI report, explicitly state:

- Compile task/phase: succeeded or failed?
- Test task/phase: ran, skipped, or loaded from cache?
- Test counts, failures, ignored tests.
- Packaging task: created the right artifact type?
- Artifact smoke test: was it executed?
- Quality gate: does it block publishing when verification fails?

## 21. When is a clean build needed?

Commands like:

~~~bash
./gradlew clean build
~~~

or:

~~~bash
mvn clean verify
~~~

can be useful when you want to verify from a clean output state. However, `clean` discards incremental build benefits, so you do not need it every time you edit a method.

When debugging unusual artifacts, a clean build helps rule out stale outputs. When editing simple logic, running the relevant unit tests is faster.

### 21.1. Wrappers keep build tools aligned

Gradle wrapper:

~~~bash
./gradlew build
~~~

Maven wrapper, if present in the repository:

~~~bash
./mvnw verify
~~~

Wrappers ensure developers and CI use the project-specified build tool version, though they do not automatically pin every dependency or JDK version. Build reproducibility also depends on toolchains and dependency locking/management.

## 22. Using one example to compare all three stages

Suppose you have:

~~~text
src/main/java/com/example/demo/ShippingCalculator.java
src/test/java/com/example/demo/ShippingCalculatorTest.java
src/main/resources/application.yml
build.gradle
~~~

Steps to observe:

### 22.1. Step A: compile

~~~bash
./gradlew compileJava
~~~

Expected output: `ShippingCalculator.class` and other main classes. Whether negative input is handled properly is not yet established.

### 22.2. Step B: test

~~~bash
./gradlew test
~~~

Expected output: the test task runs and produces reports, passing or failing based on JUnit assertions. A failing test causes the task to fail unless ignore-failures is configured.

### 22.3. Step C: package

~~~bash
./gradlew bootJar
~~~

Expected output: an executable JAR with main classes, resources, and runtime libraries. The task can succeed even if tests fail when tests are not part of the packaging dependency graph.

### 22.4. Step D: run the artifact

~~~bash
java -jar build/libs/demo-app-1.0.0.jar
~~~

Expected output: the JVM uses the Spring Boot loader to start the application. This step may uncover other issues like missing config or an unavailable database.

These four steps answer **four different questions**, even though later steps consume outputs from earlier ones.

## 23. Testing packaged artifacts and test reports

A test run from an IDE/Gradle typically uses main/test classes from output directories. Production artifacts may package classpath resources inside a JAR. Thus, some errors only appear when running the JAR.

A rigorous pipeline might:

1. Run unit tests.
2. Run required integration tests.
3. Build the executable Boot JAR.
4. Inspect the manifest/structure.
5. Start the artifact.
6. Run health/smoke tests.
7. Publish/promote the artifact once all gates pass.

Unit test results may be stored in:

~~~text
build/test-results/test/
build/reports/tests/test/
target/surefire-reports/
~~~

Coverage reports (such as JaCoCo) are separate outputs requiring dedicated plugins. High coverage alone does not prove assertion quality; having a test report does not automatically prove every scenario is covered.

## 24. Practice exercises

### Exercise 1 — Distinguish compile and test

Create a fee-calculation class with a method that compiles cleanly yet handles negative input incorrectly. Write a JUnit test expecting an exception for negative input. Run `compileJava` and `test` separately and note the difference.

### Exercise 2 — Compile tests without running tests

Create a JUnit test with a failing assertion. Run `compileTestJava` and then `test`. Explain why test sources can compile while test execution fails.

### Exercise 3 — bootJar does not necessarily run tests

Use a project with an intentionally failing test. Run `bootJar` and inspect the task graph. Distinguish artifact creation from verification results.

### Exercise 4 — jar vs. bootJar

Create both a plain JAR and an executable Boot JAR. Use `jar tf` to inspect `BOOT-INF/classes`, `BOOT-INF/lib`, and the manifest. Identify which artifact is designed to run with `java -jar`.

### Exercise 5 — Gradle build vs. check

Run `./gradlew check` and `./gradlew assemble` in an example project. Record which task performs verification and which performs assembly.

### Exercise 6 — Maven lifecycle

In a Maven Spring Boot project, compare `mvn compile`, `mvn test`, `mvn package`, and `mvn verify`. Identify which phase invokes the test plugin and packaging plugin.

### Exercise 7 — Compare ways of skipping tests

Compare `./gradlew build -x test`, `mvn package -DskipTests`, and `mvn package -Dmaven.test.skip=true`. Note which test steps are skipped and what still runs.

### Exercise 8 — Running from bootRun and JAR

Place a resource at `src/main/resources/data/catalog.json` and read it via `ClassPathResource.getInputStream()`. Run via `bootRun` and via executable JAR; explain the classpath layout differences.

### Exercise 9 — Multi-module

Create `common-model` and `api-app`. Run `:api-app:bootJar` and check whether the common module's tests are required. Propose an appropriate quality gate for release.

### Exercise 10 — CI release gate

Design a pseudo-pipeline with unit test, package, and publish jobs. Allow publish to run only when both test and package succeed. Include artifact digest/source commit tracking to ensure the verified file is deployed.

### Exercise 11 — Smoke-test the artifact

Run an executable Spring Boot JAR in a test environment with a specific profile. Call a safe endpoint or `/actuator/health` and verify startup. Explain why this step adds value beyond unit tests.

### Exercise 12 — Classify build errors

Given three logs containing `compileJava FAILED`, `test FAILED`, and `bootJar FAILED`, identify the stage that actually failed and choose where to inspect diagnostics/test reports.

## 25. Key takeaways

**Compilation, testing, and packaging have different goals.** Compilation turns Java source into bytecode and detects syntax/type errors. Testing executes scenarios with assertions and reports pass/fail in the test environment. Packaging creates a JAR/WAR from classes, resources, and dependencies per build configuration. Success in one does not imply success in the others.

With **Gradle**, `compileJava`, `test`, `jar`, `bootJar`, `check`, and `build` are tasks connected by a dependency graph. `bootJar` does not normally require running tests; `build` normally combines verification and assembly, though custom test suites only run if explicitly wired.

With **Maven**, `compile`, `test`, `package`, and `verify` are lifecycle phases. Invoking `mvn package` normally runs tests before packaging unless skipped or customized. Creating an executable Spring Boot JAR requires the right plugin/goal, not just a `.jar` extension.

Ultimately, **an artifact existing does not mean tests passed; tests passing does not mean production will work; a successful deployment does not mean every business flow was verified**. Choose the right command for the question you want to answer and establish transparent quality gates before releasing.
