# Running from main, IDE, bootRun, or the Equivalent Maven Command

A Spring Boot application can be started in several ways: calling the `main(...)` method directly, clicking **Run** in an IDE, running Gradle's **`bootRun`** task, or using Maven's **`spring-boot:run`**. These approaches look different in terms of external actions, but they usually lead to the same starting point: **`SpringApplication.run(...)`** initializes the Spring application context.

Distinguishing between these ways of running helps you handle real-world situations: running quickly during development, setting breakpoints for debugging, passing profiles and command-line arguments, selecting the right module in a multi-module project, or explaining why running from an IDE succeeds while running the JAR fails.

**Lesson objectives:**

- Understand the role of the class with `main` and the `@SpringBootApplication` annotation.
- Run an application from Java `main` and from an IDE.
- Run with Gradle `bootRun` or Maven `spring-boot:run`.
- Pass application arguments, JVM options, environment variables, and Spring profiles properly.
- Distinguish between running directly from the classpath and running a packaged artifact with `java -jar`.
- Diagnose issues such as missing main class, wrong module, missing dependency, occupied port, or working directory differences.

The examples use Spring Boot with Java and a small web endpoint. Task names, plugin configurations, and default behaviors may differ across Spring Boot, Gradle, or Maven versions; when applying them, use the compatible versions managed by your project.

## 1. Where does a Spring Boot application start?

The typical Java entry point is the method:

```java
public static void main(String[] args)
```

In Spring Boot, this method usually calls:

```java
SpringApplication.run(OrdersApplication.class, args);
```

Complete example:

```java
package com.example.orders;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Components to understand:

| Component | Role |
|---|---|
| `OrdersApplication` | The bootstrap class of the application |
| `main(String[] args)` | The entry point invoked by the Java launcher or runner tool |
| `@SpringBootApplication` | Combines Spring Boot configuration, auto-configuration, and component scanning |
| `SpringApplication.run(...)` | Prepares the environment, creates/refreshes the context, and completes startup |
| `args` | Application arguments passed to Spring Boot |
| `ApplicationContext` | Container managing beans and the application lifecycle |

Note: `@SpringBootApplication` does not impose a required class name. You can name it `CatalogApplication`, `BillingServer`, or something else. What matters is that the package, annotations, classpath, and bootstrap logic are configured consistently.

## 2. What does SpringApplication.run(...) do?

When Java calls `main`, Spring Boot proceeds through several steps. At a high level:

```text
Java launcher / IDE / Gradle / Maven
                 │
                 ▼
        main(String[] args)
                 │
                 ▼
       SpringApplication.run(...)
                 │
                 ▼
       Prepare Environment
       (properties, profiles, args)
                 │
                 ▼
       Select ApplicationContext
       NONE / SERVLET / REACTIVE
                 │
                 ▼
         Register configuration
         and bean definitions
                 │
                 ▼
      Refresh ApplicationContext
      initialize required beans
                 │
                 ▼
     Start server if web app
                 │
                 ▼
      ApplicationRunner and
      CommandLineRunner
                 │
                 ▼
       ApplicationReadyEvent
                 │
                 ▼
       Application runs normally
```

The milestones above are simplified for learning startup thinking. Detailed lifecycle behavior and event timing may vary depending on the web/non-web context.

**Key takeaway:** Gradle or Maven does not replace `SpringApplication`. They prepare the classpath, compiler/runtime, and invoke the application as configured; Spring Boot still performs the process of creating the Spring context.

## 3. A minimal Spring Boot project

Suppose the application structure is:

```text
orders-service/
├── build.gradle               # If using Gradle
├── settings.gradle
├── gradlew
├── gradlew.bat
├── pom.xml                    # If using Maven, instead of Gradle files
├── mvnw
├── mvnw.cmd
└── src/
    ├── main/
    │   ├── java/
    │   │   └── com/example/orders/
    │   │       ├── OrdersApplication.java
    │   │       └── GreetingController.java
    │   └── resources/
    │       └── application.yml
    └── test/
        └── java/
```

A real project usually **chooses either Gradle or Maven**, not necessarily both. The diagram combines the filenames so you can recognize them when working with each build tool.

Controller to confirm the application is serving HTTP:

```java
package com.example.orders;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class GreetingController {

    @GetMapping("/hello")
    public String hello() {
        return "Hello Spring Boot";
    }
}
```

Configuration:

```yaml
# src/main/resources/application.yml
spring:
  application:
    name: orders-service

server:
  port: 8080
```

This example requires a Spring MVC/Servlet web starter compatible with your Boot version. If the project only has the base starter, the application may run as a non-web application and not expose an HTTP endpoint.

Once the server is ready, you can check:

```bash
curl http://localhost:8080/hello
```

Expected body:

```text
Hello Spring Boot
```

If running with a different profile or port, adjust the test URL accordingly.

## 4. Running directly from main(String[] args)

The most basic way is to run a Java class's `main` method. This can be done by an IDE, a build tool, or the Java launcher with a fully prepared classpath.

Example:

```java
@SpringBootApplication
public class OrdersApplication {

    public static void main(String[] args) {
        SpringApplication.run(OrdersApplication.class, args);
    }
}
```

Suppose the application receives arguments:

```text
--spring.profiles.active=dev
--server.port=8081
```

`args` in `main` will contain the two corresponding strings if they are passed as application arguments.

You can store the context object:

```java
public static void main(String[] args) {
    ConfigurableApplicationContext context =
            SpringApplication.run(OrdersApplication.class, args);

    // No further context operations needed in a simple web app.
}
```

You need to import `ConfigurableApplicationContext` from Spring. For a typical web service, you only need to call `SpringApplication.run(...)` without holding onto this reference.

### 4.1. Do not manually instantiate services with new in main

Do not do this:

```java
public static void main(String[] args) {
    OrderService service = new OrderService();
    service.run();
}
```

if `OrderService` depends on Spring bean injection, transactions, configuration, or container-managed proxies. An object created directly with `new` does not automatically participate in the Spring lifecycle.

If you need to execute a task after the context starts up, consider a `CommandLineRunner` or `ApplicationRunner` as a Spring bean.

```java
@Component
public class StartupNotice implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Startup arguments: " + args.length);
    }
}
```

Runners are invoked by Spring Boot during the startup phase, with the application arguments passed into `SpringApplication.run`.

## 5. Running from an IDE: IntelliJ IDEA, Eclipse, and VS Code

IDEs typically recognize a Java class with `main` and provide Run/Debug actions. Button placement and menu names may differ across IDEs or extensions, but the configuration components are essentially similar.

Common workflow:

1. Open the project in the directory containing `pom.xml` or `build.gradle`.
2. Let the IDE import/sync dependencies and select the right JDK.
3. Open the `OrdersApplication` class.
4. Run the `main(String[] args)` method via the Run button.
5. Observe the startup log in the Run console.
6. Access the test endpoint if this is a web application.

An IDE can compile Java classes into an output directory and then run the Java launcher with a classpath generated by the project model. It does not require building a JAR first.

### 5.1. Common fields in a Run Configuration

| Field | Used for | Example |
|---|---|---|
| Main class | Class containing the entry point | `com.example.orders.OrdersApplication` |
| Module/classpath | Selecting source set and dependencies | Module `orders-service` |
| JDK/JRE | Java runtime for the process | Project-supported JDK |
| Program arguments | Passed into `main(String[] args)` | `--spring.profiles.active=dev` |
| VM options | JVM flags and system properties | `-Xmx512m -Duser.timezone=UTC` |
| Environment variables | Process environment variables | `SPRING_PROFILES_ACTIVE=dev` |
| Working directory | Location for resolving relative paths | Module root directory |

Do not confuse the three input groups:

- **Program arguments** go into `main` and then to `SpringApplication.run`.
- **VM options** are processed by the JVM, such as `-Xmx` and `-Dkey=value`.
- **Environment variables** are available via `System.getenv(...)` and can be exposed by Spring Boot in `Environment`.

### 5.2. How do Run and Debug differ?

Running with **Run** normally starts the application as usual. Running with **Debug** allows the IDE to attach a debugger, set breakpoints, and inspect variables/threads/stack.

Example placing a breakpoint in:

```java
@GetMapping("/hello")
public String hello() {
    return "Hello Spring Boot";
}
```

This breakpoint will pause execution when an HTTP request hits the endpoint and the method runs, not necessarily right when the server starts.

If a breakpoint in `main` is not hit, check that the IDE is running the right main class and debug configuration rather than a test or another application.

### 5.3. IDEs can delegate running to the build tool

Some IDEs allow delegating build/run to Gradle or Maven. When that option is enabled, the Run button in the IDE may invoke a build tool task/goal instead of using a direct Java launch managed by the IDE.

Therefore, "Run from IDE" is a developer action, not a completely separate runtime mechanism. When behavior differs from expectations, check whether the IDE is using the **IDE runner** or **Gradle/Maven delegated run**.

## 6. What is Gradle bootRun?

If a project applies the Spring Boot Gradle plugin and required plugins, Gradle provides the **`bootRun`** task to run the Spring Boot application from the project's classpath.

In a project using the Gradle wrapper, from the directory containing `gradlew`:

```bash
./gradlew bootRun
```

On Windows PowerShell:

```powershell
.\gradlew.bat bootRun
```

In projects using Kotlin DSL, the filename is usually `build.gradle.kts` instead of `build.gradle`, but the task is still `bootRun` when the plugin is configured.

`bootRun` is typically a task based on `JavaExec`: it launches the application with a **runtime classpath** consisting of classes/resources and required dependencies.

**You do not need to create an executable JAR before calling `bootRun`.** Gradle will handle the necessary prerequisite tasks such as compiling and processing resources according to the project configuration.

## 7. Minimal Gradle build.gradle for the example

An illustrative Gradle Groovy DSL configuration:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'com.example'
version = '0.0.1-SNAPSHOT'

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
```

**Note:** the version numbers and Java requirement in this snippet are an example combination for the Boot 3.x line, not a recommendation to choose the latest version or a mandatory version for every project. In real projects, use the plugin/dependency versions managed by and compatible with your runtime.

If the build was generated by Spring Initializr, you usually do not need to rewrite this entire configuration. You just need to identify the module applying the Spring Boot plugin and run the task in the right place.

### 7.1. Why might the bootRun task not exist?

Example error:

```text
Task 'bootRun' not found in root project
```

Common causes:

- Running from a project/module that does not apply the Spring Boot Gradle plugin.
- The project only uses Maven.
- Multi-module build: the root project is an aggregator, while the application lives in a subproject.
- The plugin has not been applied or the build configuration fails before the task is created.
- Typo in the task name or wrong Gradle project selected.

Check the build file and target module rather than trying to run `bootRun` in every directory.

## 8. Passing application arguments to bootRun

A common need is enabling a profile and changing the port:

```bash
./gradlew bootRun --args="--spring.profiles.active=dev --server.port=8081"
```

With Windows PowerShell:

```powershell
.\gradlew.bat bootRun '--args=--spring.profiles.active=dev --server.port=8081'
```

In this example, the part after `--args` is **application arguments** forwarded by Gradle to `main(String[] args)`, not arguments to the Gradle build itself.

The difference:

```text
./gradlew bootRun
    │      │
    │      └── Gradle task
    └── Gradle launcher

--args="--spring.profiles.active=dev --server.port=8081"
    │
    └── Args for the program launched by bootRun
```

Conceptually, the Spring Boot application can receive:

```text
args[0] = --spring.profiles.active=dev
args[1] = --server.port=8081
```

**Quoting note:** how shells parse quotes differs across Bash, PowerShell, and CMD. If Gradle reports an option error or the program receives an unexpected combined string, check the quoting rules for the shell you are using.

### 8.1. Configuring arguments directly in the build script

Groovy DSL:

```groovy
tasks.named('bootRun') {
    args '--spring.profiles.active=dev'
    args '--server.port=8081'
}
```

This is useful for fixed development configurations. However, do not hard-code production secrets or deployment-specific settings in the repository.

If you want flexible arguments per environment, pass them from the terminal or CI runner.

## 9. Passing JVM arguments to bootRun

You must distinguish JVM arguments from application arguments. For example:

- `-Xmx512m`: JVM heap limit.
- `-Duser.timezone=UTC`: JVM system property.
- `--server.port=8081`: Spring Boot application argument.

In Gradle Groovy DSL, you can configure JVM options for the task:

```groovy
tasks.named('bootRun') {
    jvmArgs '-Xmx512m', '-Duser.timezone=UTC'
}
```

These options apply to the JVM running the application in the task, not arbitrary options for the Gradle daemon.

Conversely, setting a `-D...` when invoking the Gradle launcher may set a system property for the **Gradle process** or task configuration, which does not necessarily guarantee that property is forwarded to the forked/launched application JVM. Configure it through the mechanism `bootRun` supports when targeting the application JVM.

In practice, check:

1. Which Java process is the option set for?
2. Does Spring Boot read it from `System.getProperty` or `args`?
3. Does the run configuration use a Gradle daemon with its own JVM?

## 10. Running Gradle from a multi-module project

Example:

```text
workspace/
├── settings.gradle
├── build.gradle
├── common-domain/
│   └── build.gradle
├── orders-app/
│   └── build.gradle
└── billing-app/
    └── build.gradle
```

Here `orders-app` and `billing-app` are executable Spring Boot modules, while `common-domain` is a library.

From the root project, you can run:

```bash
./gradlew :orders-app:bootRun
```

Or:

```bash
./gradlew :billing-app:bootRun --args="--spring.profiles.active=dev"
```

The `:` in the task name indicates the subproject path according to Gradle project paths.

Do not use:

```bash
./gradlew bootRun
```

and assume the project will pick the application you want, because the root project might not have a `bootRun` task or task resolution may not fit a multi-module setup.

### 10.1. Main class in a module with multiple entry points

If the same module contains multiple classes with `main`, the Boot Gradle plugin may not be able to automatically determine a unique main class.

You can configure it explicitly, for example in Groovy DSL:

```groovy
springBoot {
    mainClass = 'com.example.orders.OrdersApplication'
}
```

Or on the task:

```groovy
tasks.named('bootRun') {
    mainClass = 'com.example.orders.OrdersApplication'
}
```

DSL properties may vary by plugin/version; check the API of your project's version.

If you need multiple independent run modes (for example, a server and a migration tool), consider creating a separate `JavaExec` task or a separate module rather than relying on ambiguous main class inference.

## 11. What is Maven spring-boot:run?

For a Maven project with the Spring Boot Maven plugin properly configured, the goal:

```bash
mvn spring-boot:run
```

allows running the application without manually packaging an executable JAR first.

If the project has the Maven wrapper:

```bash
./mvnw spring-boot:run
```

On Windows PowerShell:

```powershell
.\mvnw.cmd spring-boot:run
```

Maven executes the required steps according to its lifecycle/plugin configuration so that compiled classes, resources, and appropriate dependencies are available when running. `spring-boot:run` is a **Maven plugin goal**, not a standalone Java launcher command.

Run it in the module containing the Maven plugin and application main class, or select the right module with Maven reactor options.

## 12. Example pom.xml for the Spring Boot Maven plugin

An illustrative `pom.xml` configuration:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">

    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>orders-service</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-web</artifactId>
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

This is only a structural example for the Boot 3.x line and does not claim this version is the latest. Some projects inherit from a custom parent or use a separate BOM/`pluginManagement`; plugin declaration and version configuration will differ.

In environments with a Maven wrapper, `mvnw` is usually preferred so the project's specified Maven version is used, similar to Gradle's `gradlew`.

### How does Maven differ from Gradle?

- Gradle uses **tasks** such as `bootRun`.
- Maven uses **plugin goals** such as `spring-boot:run`.
- Both can run an application directly from compiled output/classpath.
- Both still direct execution to the `main` entry point or the main class chosen by the build configuration.
- Both can select profiles, properties, and JVM arguments through their own mechanisms.

Do not try to run `./gradlew bootRun` in a Maven-only project or `mvn spring-boot:run` in a Gradle-only project.

## 13. Passing arguments to Maven spring-boot:run

The Maven Spring Boot plugin supports a plugin property for application arguments in compatible versions:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--spring.profiles.active=dev --server.port=8081"
```

In Windows PowerShell, you may need to adjust quoting so that a `-D...` is parsed properly by Maven:

```powershell
.\mvnw.cmd spring-boot:run '-Dspring-boot.run.arguments=--spring.profiles.active=dev --server.port=8081'
```

In both examples, the intent is to pass two **application arguments** to Spring Boot:

```text
--spring.profiles.active=dev
--server.port=8081
```

How the shell handles quotes is very important because `-Dspring-boot.run.arguments` is a single Maven argument containing multiple parts. If the application does not receive them properly, check how the Maven plugin reports arguments or try a single simple option first.

### 13.1. Maven parameter for Spring profiles

The plugin also has a dedicated property for Spring profiles, for example:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
```

Depending on version and configuration, you can also use `spring-boot.run.arguments` as shown above.

**Do not confuse a Maven profile with a Spring profile.**

```bash
./mvnw -Pdevelopment spring-boot:run
```

`-Pdevelopment` activates a **Maven build profile** named `development`. It does not automatically mean Spring Boot will activate the `dev` profile, unless the project configures an explicit mapping or variable forwarding.

| What you want to change | Mechanism |
|---|---|
| Spring Boot runtime profile | `--spring.profiles.active=dev` or plugin property `spring-boot.run.profiles` |
| Maven build profile | `mvn -PprofileName ...` |
| Gradle build configuration | Gradle script/project properties/task configuration |
| JVM system property | `-Dname=value` for the app JVM via the appropriate plugin/task |

## 14. JVM arguments with the Maven plugin

For example, when you need to set the heap size for the application JVM:

```bash
./mvnw spring-boot:run -Dspring-boot.run.jvmArguments="-Xmx512m -Duser.timezone=UTC"
```

The `spring-boot.run.jvmArguments` property targets the JVM arguments of the application launched by the Maven Spring Boot plugin in supported versions.

Distinguish between:

```bash
mvn -Duser.timezone=UTC spring-boot:run
```

and:

```bash
mvn spring-boot:run -Dspring-boot.run.jvmArguments="-Duser.timezone=UTC"
```

The first command uses Maven `-D` to set a user property in the build context; it is not necessarily equivalent to a JVM system property on the application process. The second command intends to pass that option into the application's JVM.

In Windows shells, quoting syntax may need adjustment.

If you need an environment variable for the application process, you can set it in the shell before calling the Maven wrapper or use the plugin's environment variables configuration feature when supported by your version.

## 15. Maven multi-module: selecting the right module

Example:

```text
shop-parent/
├── pom.xml
├── shop-common/
│   └── pom.xml
├── orders-api/
│   └── pom.xml
└── billing-api/
    └── pom.xml
```

If `orders-api` is a Spring Boot application module, you can select the module using the Maven reactor:

```bash
./mvnw -pl orders-api -am spring-boot:run
```

In practice, this command may require adjustment depending on how the plugin goal executes across the reactor and dependent modules. `-pl` selects the project and `-am` includes related modules, but if the `spring-boot:run` goal runs on library modules without a main class, it can cause errors.

Another approach is to install/build dependency modules first according to the project workflow, then run the plugin goal inside the application module itself:

```bash
cd orders-api
../mvnw spring-boot:run
```

Module selection must match the build structure. Do not assume a plugin goal should run on every module, especially when the parent is only a `pom` aggregator or common modules are libraries.

### 15.1. Multiple main classes with Maven

When the Maven plugin cannot infer the appropriate main class, you can declare it explicitly:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <mainClass>com.example.orders.OrdersApplication</mainClass>
    </configuration>
</plugin>
```

If the project inherits plugin configuration from a parent, configure it in the specific module so sibling modules are not affected.

## 16. Comparison table of the main ways to run

| Run method | Who prepares the classpath? | Commonly used when | Requires packaging JAR first? |
|---|---|---|---|
| Call `main` via IDE | IDE/project model | Writing code, quick debugging | No |
| IDE delegated run | Gradle/Maven invoked by IDE | Wanting build-tool behavior | Not required |
| Gradle `bootRun` | Gradle + Spring Boot plugin | Dev running from terminal/CI testing | No |
| Maven `spring-boot:run` | Maven + Spring Boot plugin | Dev running from terminal/Maven workflow | No |
| `java -jar` | Java launcher reading built executable JAR | Running packaged artifact | Yes |

In the first four dev approaches, code/classes/resources usually come from output directories and a tool-managed dependency classpath. The fifth approach uses a packaged artifact.

**Do not describe `bootRun` or `spring-boot:run` as "no build needed".** The build tool may still compile classes and process resources according to the dependency graph; what is not required is creating an executable archive before running.

## 17. Differences between bootRun and java -jar

The two commands:

```bash
./gradlew bootRun
```

and:

```bash
java -jar build/libs/orders-service-0.0.1-SNAPSHOT.jar
```

are not identical in how they run.

### bootRun

- Typically uses classes/resources from build outputs.
- Uses the runtime classpath constructed by Gradle.
- Convenient when editing code frequently.
- Can be combined with an IDE or DevTools to speed up the development loop.
- Does not verify every issue that only happens when packaging an executable JAR.

### java -jar

- Runs the built archive.
- Depends on how the JAR is packaged, the manifest, and the Spring Boot loader.
- Reflects the behavior of the deployed artifact more closely.
- Does not automatically pick up the latest Java code unless the JAR is rebuilt.
- May expose resource path, packaging, or missing dependency issues not encountered in a dev run.

If the application only works with `bootRun` and fails under `java -jar`, investigate packaging, resources, and classpath instead of concluding that Spring Boot startup logic is completely different.

## 18. Creating and running an executable JAR

With the Gradle Spring Boot plugin, the task to package an executable archive is typically:

```bash
./gradlew bootJar
```

Then run the actual generated JAR:

```bash
java -jar build/libs/orders-service-0.0.1-SNAPSHOT.jar
```

With the Maven Spring Boot plugin, the typical workflow is:

```bash
./mvnw package
```

Then:

```bash
java -jar target/orders-service-0.0.1-SNAPSHOT.jar
```

The example filename depends on `artifactId`, `version`, and build configuration. Do not copy the name verbatim if your project produces a different artifact.

A JAR might only be a **plain library JAR** without the appropriate Spring Boot executable layout/launcher. `java -jar` requires an archive with a valid manifest/main entry. Do not assume every generated `jar` is a Spring Boot executable JAR.

If `java -jar` reports no main manifest attribute or cannot find the main class, check which task/plugin produced the artifact.

## 19. "Running from source" does not mean skipping dependencies

Running the `main` method directly requires a complete classpath:

- Classes compiled from `src/main/java`.
- Resources from `src/main/resources`.
- Spring Boot libraries.
- Starter/service/client dependencies in runtime scope.
- The logging implementation in use.
- Project modules that the app depends on.

Simply running:

```bash
java com.example.orders.OrdersApplication
```

without configuring the classpath is usually insufficient for a real Spring Boot application.

IDEs and build tools are convenient because they **assemble the classpath** for you.

Table of common sources:

| Source | When running from IDE/bootRun/Maven | When running executable JAR |
|---|---|---|
| `src/main/java` | Compiled to `.class` in output dir | Classes inside the archive |
| `src/main/resources` | Resources on runtime classpath | Resources packaged into archive |
| Runtime dependencies | JARs on the process classpath | Bundled or managed by loader per packaging |
| `src/test/java` | Usually not part of main app runtime | Not normally packaged into executable app |
| `src/test/resources` | Usually not part of main app runtime | Not normally packaged into executable app |

If dependencies have inappropriate scopes (test-only, provided, optional), runtime behavior can differ between the build, IDE, and JAR. Check dependency scopes and packaging instead of manually copying JARs.

## 20. The role of the working directory

A common mistake: running from the IDE can read a file, while running from the terminal cannot; or vice versa.

Suppose the code is:

```java
Path path = Path.of("data/input.csv");
List<String> lines = Files.readAllLines(path);
```

The relative path `data/input.csv` is resolved based on the **current working directory of the Java process**.

Different environments may choose different working directories:

- IDEs usually default to the project/module root, though it can be configured.
- Gradle tasks have their own working directory configuration.
- Maven plugins run in the project/module context.
- `java -jar` runs from the directory the operator is in when invoking the command, unless changed by a process manager.
- Containers have their own `WORKDIR` or current directory.

Therefore, do not write business code assuming the working directory is always the source project root.

### 20.1. Classpath resources vs. files on disk

When you need to read a resource packaged in `src/main/resources`, use the classpath resource API.

Example:

```java
try (InputStream input = getClass()
        .getResourceAsStream("/templates/email.html")) {

    if (input == null) {
        throw new IllegalStateException("Missing email template");
    }

    // Read the input stream content.
}
```

This can work both from output directories and inside an executable JAR, as long as the resource is packaged properly.

Conversely:

```java
new File("src/main/resources/templates/email.html")
```

depends on the source tree still existing at runtime. When deploying a JAR, the path `src/main/resources` may not exist at all on the host machine.

Clearly distinguish **resources bundled in the artifact** from **external files provided outside the application**.

## 21. Profiles and properties in each run environment

Setting `spring.profiles.active` can take different paths.

### IDE

In **Program arguments**:

```text
--spring.profiles.active=dev
```

Or in **Environment variables**:

```text
SPRING_PROFILES_ACTIVE=dev
```

### Gradle

```bash
./gradlew bootRun --args="--spring.profiles.active=dev"
```

### Maven

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
```

### Executable JAR

```bash
java -jar app.jar --spring.profiles.active=dev
```

All of these aim for Spring Boot to receive the corresponding active profile. However, the **delivery path** from launcher to application differs.

If a profile is configured simultaneously via environment, `application.yml`, command line, or plugin args, property source precedence determines the final value. When the profile differs from expectations, inspect both the launch configuration source and startup logs.

## 22. Application arguments, JVM options, and environment variables

These are three concepts that are frequently mixed up:

| Type | Example | Who handles it first? | How Spring Boot accesses it |
|---|---|---|---|
| Application arguments | `--server.port=8081` | `main(String[] args)`/`SpringApplication` | Command-line property source, runners |
| JVM system property | `-Duser.timezone=UTC` | Java launcher/JVM | `System.getProperty`, Environment |
| JVM memory flag | `-Xmx512m` | JVM | Runtime JVM configuration |
| Environment variable | `SPRING_PROFILES_ACTIVE=dev` | OS process environment | `System.getenv`, Environment |

Example running an executable JAR:

```bash
java -Xmx512m -Duser.timezone=UTC -jar app.jar --server.port=8081
```

Positional syntax matters:

- `-Xmx512m` and `-Duser.timezone=UTC` before `-jar` are JVM options.
- `--server.port=8081` after the archive name is an application argument.

When using Gradle/Maven, do not dump every option into one field expecting the tool to figure it out. `bootRun` and `spring-boot:run` provide separate ways to pass each group.

## 23. Running a non-web application

Not every Spring Boot application opens an HTTP port. If you use Spring Boot to run a batch/CLI/worker job, you can choose a non-web application:

```java
@SpringBootApplication
public class ImportApplication {

    public static void main(String[] args) {
        SpringApplication app =
                new SpringApplication(ImportApplication.class);

        app.setWebApplicationType(WebApplicationType.NONE);
        app.run(args);
    }
}
```

A runner can perform the work:

```java
@Component
public class ImportRunner implements CommandLineRunner {

    @Override
    public void run(String... args) {
        System.out.println("Import job arguments: " + args.length);
    }
}
```

With the `NONE` setting, the application does not create Boot's embedded web server. You still get the Spring container, dependency injection, and runners.

Whether launched by IDE, `bootRun`, or `spring-boot:run`, the web application type is determined by the application/classpath/configuration, not necessarily imposed solely by the build tool.

If an app only has the base Spring Boot starter without a web stack, Boot typically infers non-web mode; do not expect an endpoint on port 8080 if the project has no matching server runtime.

## 24. Spring Boot DevTools during development

`spring-boot-devtools` can assist the development loop with features like restarting when the classpath changes and convenient development settings.

Gradle example:

```groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

Maven example with an optional dependency in appropriate projects:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
```

DevTools is helpful when:

- Running from an IDE.
- Running from compiled classes via Gradle/Maven.
- You frequently edit code and recompile.
- The application needs quick restarts on classpath changes.

**Do not assume DevTools automatically hot-swaps every source change.** Source changes must be compiled by the IDE or build process into updated classes/resources on the classpath for the restart mechanism to detect them.

In addition, restart behavior depends on how the app is run and classloader configuration. DevTools is not a replacement for building/redeploying production executable artifacts.

## 25. Starting and stopping the application

When running a Spring Boot web service from the terminal:

```bash
./gradlew bootRun
```

the terminal usually keeps the process running until the server stops.

You can send a stop signal depending on the environment, such as **Ctrl+C** in the terminal. IDEs have a Stop or Terminate button. Stopping from an IDE, shell, systemd, and containers may differ in signals and timeouts.

If stopped **gracefully**, Spring has a chance to run its shutdown lifecycle: closing the application context, stopping the web server, releasing resources, and invoking destroy callbacks as configured.

If force-killed or if the JVM crashes, full cleanup logic cannot be guaranteed to run.

### 25.1. Avoid accidentally starting two instances on the same port

If one instance is holding port 8080 and you start a second instance with the same configuration, you may encounter the error:

```text
Port 8080 was already in use
```

Ways to handle this:

1. Stop the old instance running in the IDE/terminal.
2. Pick a different port when you need to run instances side by side.
3. Check which OS process is occupying the port.
4. Ensure both IDE Run and `bootRun` are not running the same app without you realizing it.

Changing the port:

```bash
./gradlew bootRun --args="--server.port=8081"
```

or in Maven/JAR via the corresponding arguments mechanism.

## 26. Distinguishing the app process from the build tool process

When using an IDE, Gradle, or Maven, multiple Java processes may exist:

- IDE process.
- Gradle daemon.
- Maven launcher/plugin process.
- JVM running the Spring Boot application.
- Test worker processes if the build also runs tests.

Not every Java command-line option affects all of these processes.

For example, in Gradle, an option passed to the Gradle daemon can differ from `jvmArgs` for `bootRun`. With the Maven plugin, the `spring-boot.run.jvmArguments` property targets the application's JVM.

This matters when:

- Checking heap with `-Xmx`.
- Attaching a debugger.
- Calculating timeouts or memory usage.
- Reading environment variables.
- Stopping the right process.
- Separating Gradle/Maven logs from Spring Boot logs.

If behavior differs between the IDE and terminal, identify **which Java process actually runs the main class**.

## 27. Running with a remote debugger

IDE Debug usually configures the debugger automatically. Sometimes, however, you want to debug a JVM launched via a build tool or an executable JAR.

Common JDWP JVM option example for **local development**:

```text
-agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005
```

On Java versions supporting this syntax, the option lets a debugger connect to port 5005 on loopback.

With an executable JAR:

```bash
java -agentlib:jdwp=transport=dt_socket,server=y,suspend=n,address=127.0.0.1:5005 -jar app.jar
```

With Gradle/Maven, pass the JDWP option through the application process's JVM arguments mechanism, not through application arguments.

Security notes:

- Do not expose a remote debugger publicly on a production network interface.
- Only bind to localhost or use managed tunnels/controls.
- A debugger can inspect and alter execution, so treat it as a sensitive operational interface.
- Check that port 5005 is not already in use.

For routine debugging during development, the IDE's **Debug** button remains the lowest-configuration option.

## 28. Running from IDE but the application fails to start

Typical causes:

| Symptom | Possible cause | What to check |
|---|---|---|
| No Run button on main | IDE hasn't imported project/JDK properly or non-standard method signature | Sync project, verify `public static void main(String[] args)` |
| ClassNotFound error | Wrong main class, module/classpath, or failed compilation | Check Run Configuration and build output |
| NoClassDefFoundError | Runtime classpath missing dependency | Reimport Gradle/Maven, check dependency scope |
| Beans not scanned | Main application in wrong package or missing scan config | Check package hierarchy and `@SpringBootApplication` |
| No web server logs | Missing web starter or application type is NONE | Check classpath and `spring.main.web-application-type` |
| Exits right after startup | Non-web app with no worker/thread keeping process alive | Check runners and lifecycle |
| Breakpoint not hit | Launched with Run instead of Debug or debugger attached to wrong process | Select Debug on the right main class |
| Config differs from terminal | Different program args/profile/working dir/env variables | Compare Run Configuration |
| Port already in use | Another instance is running | Stop old process or change port |

### 28.1. Not seeing "Started ..." is not always an error

Some applications lack full logging, fail early during startup, or filter log messages by level. Look at the exit code/exception and process status rather than inferring from a single missing log line.

If the application is a batch job, it may finish and exit normally without opening a web server.

## 29. bootRun failures: common causes

| Error or symptom | Troubleshooting suggestion |
|---|---|
| `Task 'bootRun' not found` | Check Spring Boot Gradle plugin and project/subproject path |
| `Could not find or load main class` | Check `mainClass`, package, and classpath |
| `Unable to find a single main class` | Specify main class explicitly |
| Dependency resolution error | Check repositories/network/dependency constraints and versions |
| Incompatible Java version | Check Gradle toolchain, `java -version`, and Boot Java compatibility |
| `--args` has no effect | Check quoting and the task being run |
| Different Spring profile than expected | Check args/env/IDE overrides and property source precedence |
| Build tool cannot see module | Check `settings.gradle` and project path |
| App runs but exits immediately | Distinguish non-web vs. web app and job lifecycle |
| Build succeeded but app reports startup failed | Distinguish compilation error from Spring context creation error |

### 29.1. Gradle wrapper and JDK

`gradlew` ensures the project uses the Gradle distribution specified in the wrapper. However, the wrapper does not automatically pick the right JDK for every situation.

Distinguish between:

- The JDK running the Gradle daemon.
- The JDK used as the Java toolchain for compilation.
- The JVM actually used to run `bootRun`.
- The Java version required by the project's Spring Boot version.

If the Java version is incompatible, inspect the project build configuration and logs rather than just installing another JDK without selecting it in the IDE/build tool.

## 30. spring-boot:run failures: common causes

| Error or symptom | Troubleshooting suggestion |
|---|---|
| `No plugin found for prefix 'spring-boot'` | Check that the Maven Spring Boot plugin is properly declared/resolved |
| `Unable to find a suitable main class` | Check module and plugin `mainClass` |
| `ClassNotFoundException` | Compiled output or runtime dependencies missing |
| Plugin runs on parent/library module | Select the right application module in the Maven reactor |
| `-Pdev` does not change Spring profile | Maven profile and Spring profile are two different mechanisms |
| `spring-boot.run.arguments` split incorrectly | Check quoting in the shell |
| JVM options have no effect | Use the plugin's JVM arguments property, not just a Maven user property |
| Dependencies not found | Check Maven repositories, settings, and network |
| Port already in use | Stop old process or pass a different `--server.port` |
| Main works in IDE but Maven fails | Compare compiler settings, resources, dependency scopes, and plugin config |

You can inspect the effective Maven configuration using appropriate Maven tools when diagnosing, rather than hastily changing the whole POM just because IDE Run succeeds.

## 31. Confusing differences between IDE, Gradle, Maven, and JAR

### 31.1. "IDE Run succeeds so the JAR will definitely run"

Not guaranteed. The IDE classpath may include resources or dependencies that packaging has not put into the executable archive, and the working directory also differs.

### 31.2. "bootRun is just an alias for java -jar"

Incorrect. `bootRun` typically runs compiled classes/resources on Gradle's runtime classpath, whereas `java -jar` runs the packaged archive.

### 31.3. "mvn spring-boot:run also builds the production artifact"

Incorrect. It runs the application from the Maven project context; to produce a distribution artifact, use the appropriate package/repackage workflow.

### 31.4. "Setting -Dserver.port=8081 anywhere works the same"

Not necessarily. You must know whether `-D` is handled by the app JVM, the Gradle/Maven launcher, or the plugin. `--server.port=8081` is an application argument when passed properly to Spring Boot.

### 31.5. "spring.profiles.active=dev in YAML behaves the same in every Run Configuration"

The effective value depends on property source precedence. IDE program args or environment variables can override YAML. Use one clear source of truth for the run environment.

### 31.6. "Using Maven -Pdev definitely activates the dev Spring profile"

Not automatically. `-P` is a Maven build profile, unless the project explicitly wires the Maven profile to the Spring runtime profile.

### 31.7. "Running from the IDE means every breakpoint in the code will hit"

You must run the right Debug configuration, hit the right code path, and attach to the right JVM/process. With async code, a breakpoint may be hit on a different thread or after the request returns.

### 31.8. "Files in src/main/resources can always be read using a File path"

Not after packaging a JAR. Use the classpath resource abstraction for bundled resources; use an external filesystem path for files actually located outside the artifact.

## 32. A practical developer workflow

Suppose you just cloned a Spring Boot service and want to run, debug, and then build an artifact.

**Phase 1 — Understand the project**

1. Identify whether the project uses Gradle or Maven.
2. Locate the application main class.
3. Check the required JDK/Java version.
4. See whether the project is single-module or multi-module.
5. Identify the web starter and external services needing configuration.
6. Inspect `application.yml` and profile-specific files.

**Phase 2 — Run for development**

If using an IDE, import the project and run the main class with the `dev` profile.

If using Gradle:

```bash
./gradlew bootRun --args="--spring.profiles.active=dev"
```

If using Maven:

```bash
./mvnw spring-boot:run -Dspring-boot.run.profiles=dev
```

Make sure two instances do not accidentally share the same port.

**Phase 3 — Observe and debug**

Check the startup log, active profile, port, context creation, and health endpoint if provided by the app. Set breakpoints in controllers/services to verify the processing flow.

**Phase 4 — Verify packaging**

With Gradle:

```bash
./gradlew bootJar
```

With Maven:

```bash
./mvnw package
```

Then verify the exact artifact using `java -jar` in an intentional working directory, independent of the source tree.

**Phase 5 — Compare runtime behavior**

If there are differences, compare:

- Main class.
- Profiles/properties.
- Java runtime.
- Runtime dependencies.
- Packaged resources.
- Working directory.
- Environment variables.
- External service endpoints.

This is a systematic way to find root causes instead of randomly changing multiple settings at once.

## 33. Practice exercises

### Exercise A — Running from main

Create a Spring Boot application with `OrdersApplication` and `GreetingController`. Run the `main` method from the IDE. Call `GET /hello` and verify the response body.

### Exercise B — Program arguments

In the IDE Run Configuration, set:

```text
--spring.profiles.active=dev --server.port=8081
```

Run again and access `http://localhost:8081/hello`. Check the logs to confirm the active profile.

### Exercise C — VM options

Set the VM option:

```text
-Duser.timezone=UTC
```

Write a `CommandLineRunner` that prints `System.getProperty("user.timezone")` and compare it with passing the same key as a program argument.

### Exercise D — Gradle bootRun

If the project uses Gradle, run:

```bash
./gradlew bootRun
```

Then run:

```bash
./gradlew bootRun --args="--server.port=8082"
```

Observe the app startup and port. Explain why creating a JAR beforehand is not required to run the task.

### Exercise E — Maven spring-boot:run

If the project uses Maven, run:

```bash
./mvnw spring-boot:run
```

Then try:

```bash
./mvnw spring-boot:run -Dspring-boot.run.arguments="--server.port=8083"
```

Compare with Gradle on how arguments are passed.

### Exercise F — Multi-module

Create a root project with a `common` library module and a `web-app` application module. Run the right module using a Gradle project task path or Maven reactor/module directory. Explain why the root project does not necessarily have a runnable main class.

### Exercise G — Working directory and resources

Place `sample.txt` in `src/main/resources` and `input.csv` outside the application. Read the first via the classpath resource API and the second via a filesystem path. Run from the IDE and from the JAR to observe the difference.

### Exercise H — DevTools

Add DevTools according to the project's development configuration. Enable compile/build on code changes in the IDE and observe the restart mechanism if supported. Explain why editing source without compiling may not trigger a restart.

### Exercise I — Two instances on the same port

Run the application from the IDE and then start `bootRun` or `spring-boot:run` with the default port. Observe the error if the port is occupied; then pass a different port to the second instance.

### Exercise J — Running an executable JAR

Package the application using the build tool and run:

```bash
java -jar <actual-artifact-name>.jar --spring.profiles.active=dev
```

Note that this is a template command: replace the actual artifact name and do not type the angle brackets literally. Compare working directory, resource loading, and configuration with the `bootRun` run.

## 34. Quick selection table for running methods

| Goal | Usually most convenient approach |
|---|---|
| Quick run after editing Java code | IDE Run |
| Set breakpoints and inspect variables | IDE Debug |
| Run Gradle project per build configuration | `./gradlew bootRun` |
| Run Maven project per build configuration | `./mvnw spring-boot:run` |
| Run a Gradle subproject | `./gradlew :module:bootRun` |
| Run application in Maven multi-module | Select the right module and call `spring-boot:run` |
| Pass Spring profile with Gradle | `bootRun --args="--spring.profiles.active=dev"` |
| Pass Spring profile with Maven | `-Dspring-boot.run.profiles=dev` |
| Set JVM heap for the application | VM options or task/plugin JVM args configuration |
| Run artifact matching deployment format | Build executable JAR then `java -jar` |
| Read resource packaged in JAR | Classpath resource API |
| Run a batch/worker without an HTTP server | Spring Boot main with appropriate `WebApplicationType` |

## 35. Key takeaways

1. **`main(String[] args)` is the Java entry point**, while `SpringApplication.run(...)` initializes the Spring Boot application context.
2. IDE Run/Debug, Gradle `bootRun`, and Maven `spring-boot:run` typically run the same main application but differ in how they prepare the classpath and configure the process.
3. **IDE Run** is convenient for development and debugging; you must select the right module, main class, JDK, arguments, and working directory.
4. **Gradle `bootRun`** runs the application directly from output classes/resources and runtime dependencies without requiring an executable JAR to be packaged first.
5. **Maven `spring-boot:run`** is a goal of the Spring Boot Maven plugin, also commonly used to run during development.
6. Gradle's `--args` and Maven's `spring-boot.run.arguments` pass **application arguments** to Spring Boot.
7. `spring-boot.run.profiles` is for the Spring runtime profile, whereas Maven `-P` is a Maven build profile.
8. **VM/JVM options differ from program arguments**: `-Xmx` and `-D...` must target the application JVM, while `--server.port=...` is an application argument.
9. Multi-module projects require selecting the right module with the main class and Spring Boot plugin; not every library module has a runnable task/goal.
10. **`bootRun` and `spring-boot:run` are not identical to `java -jar`**: the packaged JAR has its own resource layout and runtime packaging.
11. Relative file paths depend on the working directory; classpath resources must be read through an appropriate resource mechanism.
12. DevTools helps the development loop but does not automatically hot-reload every source change before compilation.
13. A web service can fail if the port is already occupied by another process; a batch/non-web app can finish and exit on its own.
14. When Debug does not work, check the right JVM/main class/code path, not just the breakpoint.
15. When startup behavior differs between IDE, Gradle, Maven, and JAR, compare Java version, dependencies, profiles, property sources, resources, and working directory.

**Core mindset:** **Run main**, **IDE Run**, **`bootRun`**, and **`spring-boot:run`** are different paths to prepare and launch **the same Spring Boot application**. Understanding which tool prepares the classpath, which tool passes arguments, and which JVM executes `main` helps you run, debug, and package your application proactively and consistently.
