# Minimal `pom.xml` Structure for a Spring Boot Application

## 1. Goal and Starting Point

A Spring Boot application using Maven needs a `pom.xml` file so Maven knows **what the project is**, **where to fetch libraries**, **which Java version to use**, and **which plugins to compile and package with**. With `spring-boot-starter-parent`, the POM file can be short because Spring Boot already provides sensible defaults and manages compatible library versions.

After this lesson, you will be able to:

- Create and read a valid `pom.xml` for a single-module Spring Boot application using Maven.
- Explain accurately the roles of `modelVersion`, `parent`, `groupId`, `artifactId`, `version`, `properties`, `dependencies`, and `build/plugins`.
- Distinguish between the **minimum for Maven to recognize a project** and the **minimum to run a Spring Boot application and produce an executable JAR**.
- Understand why starters do not need `<version>` declared when versions are managed by the parent.
- Compile, run, test, and package a sample application; find the effective Maven configuration after inheritance.
- Recognize common XML, parent, JDK, dependency, and plugin errors.

**Scope:** a single Spring Boot application using Maven, without extending into multi-module projects, enterprise profiles, or CI/CD pipelines. The example below pins **Spring Boot 3.3.13 and Java 17** to provide a clear configuration that can be cross-checked against the official documentation of that same version. This is an **illustrative version**, not a claim that it is the latest Spring Boot release. In real projects, use the version chosen by your team/CI and check the compatibility policy of that version.

## 2. Distinguishing Three Levels of "Minimal"

There are three different requirements:

| Purpose | Required Components |
| --- | --- |
| Maven recognizes a project | Valid POM XML with `project`, `modelVersion`, and project coordinates (`groupId`, `artifactId`, `version` or appropriately inherited values) |
| Spring Boot application can compile and run | Valid POM, Spring Boot version configuration, appropriate dependencies, JDK, and source code with an entrypoint |
| `mvn package` produces an executable Spring Boot JAR | All conditions above **plus Spring Boot Maven Plugin and the `repackage` execution**, for example as already configured by `spring-boot-starter-parent` |

A POM with only `parent` and project coordinates can allow Maven to run `package` successfully, or even produce an empty JAR; that **does not prove** the Spring Boot application is ready to run. Conversely, adding a starter so code compiles does not mean Maven already has the plugin to package an executable JAR.

This lesson uses the **practical minimum for a runnable web application**: parent, coordinates, Java version, a web starter, a test starter, and the Spring Boot Maven Plugin. The test starter can be omitted if you only want a skeleton without tests, but it should be kept in learning and production projects.

## 3. Complete `pom.xml` Ready to Use Directly

Create a folder named `demo`, and inside it create a `pom.xml` file with the following content:

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
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <name>demo</name>
    <description>Minimal Maven Spring Boot example</description>

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

This is a **complete POM file**, not a fragment that needs extra pieces pasted in. All XML tags are properly closed, elements are at the right nesting level, and standard element names understood by Maven are used. Maven downloads the parent, dependencies, and plugins from the repositories configured in your environment. If your machine is blocked from the network/repository, the project may fail to build even though the POM syntax is valid.

With this configuration, Maven typically creates an artifact named `target/demo-0.0.1-SNAPSHOT.jar`; if the source code has a valid entrypoint, the plugin packages an executable JAR during the `package` phase.

### 3.1. Why Is `<packaging>jar</packaging>` Not Needed?

If `<packaging>` is omitted, Maven defaults to `jar`. Therefore, the POM above can omit:

~~~xml
<packaging>jar</packaging>
~~~

If you want readers to clearly see the packaging intent, you can add that line **once** after the project's `<version>`. Declaring `jar` explicitly is valid but not required. For WAR, change `packaging` and related sections according to deployment requirements; merely changing the single word `jar` to `war` does not automatically configure a complete WAR application for an external servlet container.

### 3.2. Why Can `name` and `description` Be Omitted?

`<name>` and `<description>` are helpful metadata for human readers, tools, and reports. They do not determine dependency resolution, main class, or executable packaging. You can remove both and the sample application will still have the same build behavior. Real-world POMs usually keep them so documentation and artifacts are self-explanatory.

## 4. Explaining Each Component of the POM

### 4.1. `project`, XML Namespace, and `modelVersion`

The outermost part:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <!-- Remaining POM elements -->
</project>
~~~

- `<project>` is the root element of a Maven POM. There is only **one root `project`** in a `pom.xml` file.
- `xmlns` specifies the Maven POM 4.0.0 model namespace; `xsi:schemaLocation` provides the XML Schema hint so IDEs and tools can validate structure.
- `<modelVersion>4.0.0</modelVersion>` describes the **POM data model version**, not the Maven CLI version, Spring Boot version, or application version.

Do not change `modelVersion` to `3.3.13` because that is the Spring Boot version: Maven will fail with an error due to an invalid model version.

### 4.2. `parent`: Inheriting Spring Boot Configuration

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.3.13</version>
    <relativePath/>
</parent>
~~~

This is the Maven parent POM from which the project inherits. `spring-boot-starter-parent` provides suitable defaults for Spring Boot applications, including:

- `dependencyManagement` inherited from `spring-boot-dependencies` to manage versions of commonly used libraries.
- Compatible Maven plugin configurations and plugin versions in `pluginManagement`.
- Default Java 17 compiler level for the Spring Boot 3.3 line, along with UTF-8 encoding and `-parameters` configuration.
- A pre-configured `spring-boot:repackage` execution; when the Spring Boot Maven Plugin is declared in the project, this goal can run during the `package` lifecycle.
- Sensible defaults for resource filtering and common plugins.

An empty `<relativePath/>` instructs Maven **not to look for the parent at the default relative path in the parent directory**, and instead resolve the parent from repositories. It is especially useful for single-module projects where there is no local Spring Boot parent file. This is a common configuration, not a network URL for downloading Spring Boot.

**Understanding inheritance properly:** a project can declare **only one parent** in Maven. If a company already uses an internal parent POM, you cannot add `spring-boot-starter-parent` as a second parent. In that case, you typically import the Spring Boot BOM and configure the plugin manually; see Section 9.

### 4.3. GAV: Artifact Identification

~~~xml
<groupId>com.example</groupId>
<artifactId>demo</artifactId>
<version>0.0.1-SNAPSHOT</version>
~~~

These three elements are called **GAV (groupId, artifactId, version)**, which uniquely identify a Maven artifact:

- `groupId`: the organization/team namespace, typically in reversed-domain form such as `com.example`.
- `artifactId`: the module/artifact name, `demo` in the example.
- `version`: the main version of the artifact produced by the project, `0.0.1-SNAPSHOT` in the example.

The coordinates can be written as `com.example:demo:0.0.1-SNAPSHOT`. With the default JAR packaging, Maven typically outputs `target/demo-0.0.1-SNAPSHOT.jar`, unless `finalName`, classifier, or outputDirectory configuration changes it.

**The project's `version` is separate from Spring Boot's version:** a `0.0.1-SNAPSHOT` project can still use Spring Boot `3.3.13`. `SNAPSHOT` indicates that the project's artifact may continue to be updated during the development cycle; it does not automatically turn all dependencies into snapshots.

In multi-module Maven builds, the parent can provide `groupId`/`version` via inheritance; the single-module example declares them explicitly for easy observation.

### 4.4. `properties` and Java Version

~~~xml
<properties>
    <java.version>17</java.version>
</properties>
~~~

When using the corresponding Spring Boot starter parent, `java.version` is the property used by the parent to configure the Java compiler. For Spring Boot 3.3, Java 17 is the baseline supported level; setting it explicitly lets readers see the module's compilation target.

Distinguish clearly between:

- **Java used to run Maven:** checked via `mvn -version` or `./mvnw -version`.
- **Java used by the Maven compiler to generate bytecode:** depends on plugin configuration and JDK/toolchain. With the parent, `java.version` aligns the compiler release, but it does not automatically change the JDK running Maven.
- **Java runtime used to run the executable JAR:** must be compatible with the compiled class files and packaged dependencies.

For example, declaring Java 17 while Maven starts with JDK 11 can fail; fix `JAVA_HOME`/IDE Maven runner/toolchain to match, not just `Project SDK` in the IDE. Always verify the JDK before looking for bugs in the POM.

### 4.5. `dependencies`: Libraries the Application Needs

~~~xml
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
~~~

In the example:

- `spring-boot-starter-web` adds the set of libraries needed to build a typical Servlet/MVC web application, including Spring MVC and the starter's default embedded server.
- `spring-boot-starter-test` adds utilities for testing Spring Boot applications and testing libraries curated by the starter.
- `<scope>test</scope>` makes test dependencies available when compiling/running tests, rather than placing them on the application's runtime dependency graph.

There is no `<version>` on these two dependencies because the parent manages versions through the Spring Boot BOM. This does not mean Maven picks the "latest version": Maven resolves managed versions and constraints/conflicts according to the build model. To inspect actual resolved versions, check the dependency tree and effective POM.

**Note:** the parent POM **does not automatically add `spring-boot-starter-web`** to dependencies. The parent manages versions, while whether you use web, data, actuator, or test depends on the dependencies you declare. Without the web starter, the web annotations and classes used by the controller example will not be on the classpath.

### 4.6. `build/plugins`: Telling Maven How to Package Spring Boot

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
        </plugin>
    </plugins>
</build>
~~~

`spring-boot-maven-plugin` provides goals related to Spring Boot applications, including:

- `spring-boot:run`: runs the application via the plugin in a development environment.
- `spring-boot:repackage`: turns the standard JAR/WAR into an executable archive with the Boot loader and nested dependencies.

With `spring-boot-starter-parent`, the plugin version and `repackage` execution are already managed/configured; therefore, the plugin configuration in the example POM **does not need a repeated version or `executions` declaration**.

When running `mvn package`, Maven executes the required lifecycle phases and plugin goals; the standard JAR plugin creates the initial archive first, and then the `repackage` execution builds the executable JAR for the application. **Declaring Spring Boot dependencies while forgetting this plugin** can allow code to compile normally while producing a JAR that is not in the expected executable Spring Boot format.

Do not confuse `build/plugins` with `build/pluginManagement`. `pluginManagement` provides default configuration/versions when a plugin is used; it does not have the same effect as declaring a plugin directly in the application's `plugins` section.

## 5. Minimal Directory Structure Accompanying the POM

Maven follows a standard directory layout:

~~~text
demo/
├── pom.xml
├── src/
│   ├── main/
│   │   ├── java/
│   │   │   └── com/example/demo/
│   │   │       ├── DemoApplication.java
│   │   │       └── PingController.java
│   │   └── resources/
│   │       └── application.properties    # optional
│   └── test/
│       └── java/
│           └── com/example/demo/
│               └── DemoApplicationTests.java
└── target/                               # generated by Maven during build
~~~

You **do not need to create `target/` manually** because Maven generates it during the build. The `src/main/resources` directory and `application.properties` can be left empty or omitted in this example because Spring Boot has sensible defaults, including the default HTTP port 8080 with the web starter.

You can use Maven Wrapper (`mvnw`, `mvnw.cmd`, and the `.mvn/wrapper` folder) to pin the Maven distribution in the project. The wrapper **does not appear automatically just from writing `pom.xml`**: it must be generated from Spring Initializr or set up following your team's workflow.

## 6. Two Java Files for a Truly Runnable Application

### 6.1. Entry Point

Create `src/main/java/com/example/demo/DemoApplication.java`:

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

`@SpringBootApplication` enables Spring Boot application configuration, auto-configuration, and component scanning starting from the package containing this class. `SpringApplication.run` creates and runs the application context. In this example, `com.example.demo` is the root package of the controller, so component scanning will discover the controller.

### 6.2. Verification Endpoint

Create `src/main/java/com/example/demo/PingController.java`:

~~~java
package com.example.demo;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

`@RestController` marks this as a Spring MVC controller with a response body; `@GetMapping("/ping")` maps GET `/ping`. With the default port 8080, calling this endpoint returns the body `pong`. The code uses APIs from `spring-boot-starter-web`, demonstrating the concrete effect of the dependency declared in the POM.

Both files must reside under the paths matching `package com.example.demo;`. The public class name must match the `.java` file name: `DemoApplication.java` and `PingController.java`. Trying to put both public classes in one file or using mismatched file names will cause a Java compiler error.

### 6.3. Simple Context Test (Recommended)

Create `src/test/java/com/example/demo/DemoApplicationTests.java`:

~~~java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DemoApplicationTests {

    @Test
    void contextLoads() {
        // Verifies that the Spring application context starts successfully.
    }
}
~~~

When running the test lifecycle, `spring-boot-starter-test` provides JUnit Jupiter and Spring Test. This test confirms the application context can load; **it does not send an HTTP request and does not prove the endpoint returns `pong`**. To verify the endpoint, call it while the application is running or write a dedicated HTTP test.

In this minimal lesson, the test file is not strictly required to compile an app without tests, but adding it gives `mvn test` a useful check.

## 7. Running from Terminal: Which Command Verifies What?

Open a terminal in the `demo` folder containing `pom.xml`.

### 7.1. Verify JDK and Maven First

~~~bash
java -version
mvn -version
~~~

If the project has a Maven Wrapper, use:

~~~bash
./mvnw -version
~~~

On Windows PowerShell with the wrapper, use `.\mvnw.cmd -version`. For the example POM, you need Maven/JDK compatible with Spring Boot 3.3 and Java 17+, plus access to Maven repositories to download dependencies. `mvn -version` shows both the Maven version and the Java version that Maven actually runs on.

**Subsequent commands use `mvn` because we only created `pom.xml` manually without generating a wrapper.** If your project already has a wrapper, replace `mvn` with `./mvnw` on Linux/macOS or `.\mvnw.cmd` on Windows to use the project-pinned Maven distribution.

### 7.2. Compile, Test, Package

~~~bash
mvn validate
mvn compile
mvn test
mvn package
~~~

Each command has a distinct meaning:

- `validate`: checks that the project has the required information to start building; it is not a full compile.
- `compile`: runs the lifecycle up to `compile` to compile sources in `src/main/java`.
- `test`: runs up to `test`, including compiling tests and executing tests when Surefire/test configuration permits.
- `package`: runs up to `package`, creating the JAR and executing `repackage` when the plugin/execution is configured as in the example POM.

Maven phases are cumulative: invoking `mvn package` normally runs through all preceding phases. You do not have to run all four commands in sequence every time; splitting them in this lesson helps observe their differences.

To clean old outputs and rebuild:

~~~bash
mvn clean package
~~~

`clean` belongs to the clean lifecycle and deletes the build directory (usually `target`) before running the default lifecycle up to `package`. This prevents confusing artifacts from an old build with current outputs.

### 7.3. Running the Application with the Maven Plugin

~~~bash
mvn spring-boot:run
~~~

This command invokes the `spring-boot:run` goal to start the application directly. It is convenient during development; it **differs** from `mvn package`, which focuses on producing an artifact. Once the application has started successfully, open another terminal:

~~~bash
curl -s http://localhost:8080/ping
~~~

Expected response body:

~~~text
pong
~~~

`curl -s` does not append a newline to the body; this snippet simply represents the exact body. If the application uses a different server port or port 8080 is already occupied by another process, adjust/pass an available port. Stop the Maven-launched app with Ctrl+C.

### 7.4. Running the Executable JAR

~~~bash
mvn clean package
java -jar target/demo-0.0.1-SNAPSHOT.jar
~~~

From another terminal, call `/ping` again as above. Receiving `pong` indicates the archive contains the example's HTTP code/routes and is executable in the current environment.

Inside `target`, you will typically see:

~~~text
target/
├── classes/
├── test-classes/
├── demo-0.0.1-SNAPSHOT.jar
└── demo-0.0.1-SNAPSHOT.jar.original
~~~

`.jar` is the executable Boot archive after the plugin succeeds at `repackage`; `.jar.original` is typically the archive before repackaging under the default configuration. Exact files may vary depending on plugin config, Java tests, classifier, `finalName`, or plugin version. Avoid hardcoding artifact names in CI if the project defines a different output name.

If `mvn package` succeeds but `java -jar` fails with missing main manifest or missing libraries, inspect the Maven plugin execution, whether the archive is correct, the main class, and the build output. A regular JAR cannot run as a Spring Boot executable JAR by itself.

## 8. How Dependencies and Plugin Versions Are Resolved

### 8.1. Parent Manages, Dependencies Decide What Is Used

A very common misconception: `spring-boot-starter-parent` **does not automatically download every Spring Boot starter into your application**. It provides dependency management and plugin defaults. You still have to declare the dependencies you need in `dependencies`.

In the example POM:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

There is no version, yet Maven can resolve the version via the parent/BOM's `dependencyManagement`. The relationship is:

~~~text
spring-boot-starter-parent:3.3.13
    ↓ manages versions for selected dependencies
spring-boot-dependencies:3.3.13
    ↓ dependencyManagement
spring-boot-starter-web (declared in the application)
    ↓ pulls in required transitive dependencies
Spring MVC, embedded server, JSON, and supporting libraries
~~~

This diagram illustrates the principle; the actual dependency graph must be inspected via `mvn dependency:tree`. If you manually add a `<version>` to a dependency managed by Spring Boot, you can override the BOM's compatible selection; only do so with a clear technical reason and after checking compatibility.

### 8.2. `dependencies` vs. `dependencyManagement`

- `dependencies`: declares **which libraries the project needs**; Maven places these dependencies on the appropriate classpaths according to their scope.
- `dependencyManagement`: defines **default versions/scopes/attributes** for dependencies when those dependencies are used; it does not automatically add dependencies to the module's classpath.
- `pluginManagement`: sets defaults for Maven plugins; it is not the same as using a plugin in `build/plugins`.

This distinction is precisely what keeps a minimal Spring Boot POM both concise and version-controlled.

### 8.3. Scopes to Keep Runtime Lean

Scope affects which classpaths include a dependency during compile/test/run:

| Scope | Brief Meaning | Usage Example |
| --- | --- | --- |
| `compile` | Default if scope is omitted; usually on compile/runtime/test classpaths | `spring-boot-starter-web` |
| `test` | Needed only for compiling/running tests | `spring-boot-starter-test` |
| `provided` | Needed for compile/test, expected to be provided by runtime/container | Servlet API/Tomcat in a WAR deployed to an external container |
| `runtime` | Not needed to compile main source, but required at runtime | JDBC driver in many setups |

Do not set `spring-boot-starter-web` to `test` if main source code uses Spring MVC annotations: code will fail to compile because the needed classes are missing from the main compile classpath.

## 9. What If You Cannot Use `spring-boot-starter-parent`?

With an enterprise Maven parent or a team-specific parent, a POM **cannot declare a second parent**. Instead, you can import the Spring Boot BOM inside `dependencyManagement`:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.3.13</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

This is only a **fragment** for a POM that already has a valid parent or project coordinates. Importing the BOM preserves dependency version management, but **does not import all plugin management, compiler configuration, or the `repackage` execution** that inheriting the starter parent provides.

Without inheriting the starter parent, an application that needs an executable JAR must specify an appropriate plugin version and execution configuration, for example:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <version>3.3.13</version>
            <executions>
                <execution>
                    <goals>
                        <goal>repackage</goal>
                    </goals>
                </execution>
            </executions>
        </plugin>
    </plugins>
</build>
~~~

In addition, you must configure the Java compiler release/encoding and standard plugins according to the policy of your current parent. Do not copy fragments and treat them as a complete POM. This lesson prioritizes the starter parent because it keeps configuration short, easy to learn, and requires minimal manual version management.

## 10. Reading the Effective Maven Configuration

The POM you write by hand is only part of the build model. Maven also combines the Super POM, parent POM, `dependencyManagement`, `pluginManagement`, profiles, settings, and command-line arguments.

Practical commands:

~~~bash
mvn help:effective-pom -Doutput=target/effective-pom.xml
mvn help:active-profiles
mvn dependency:tree
mvn help:effective-settings
~~~

- **`help:effective-pom`**: outputs the POM model after inheritance and activation; use it to confirm the Spring Boot plugin version, Java compiler configuration, and `repackage` execution.
- **`help:active-profiles`**: shows which Maven profiles are actually active; the minimal example defines no custom profiles.
- **`dependency:tree`**: displays the resolved dependency graph, including transitive dependencies; use it to investigate versions or unexpectedly pulled dependencies.
- **`help:effective-settings`**: views merged settings to investigate repositories/mirrors. Never share credentials, private repository tokens, or sensitive settings.

When changing the Spring Boot version in the parent, do not just look at the version written in `pom.xml`: inspect the effective POM and dependency tree to see the plugin and library versions Maven actually selected.

If you encounter `No plugin found for prefix 'spring-boot'`, the plugin may be missing from the build or cannot be resolved from repositories. If the error occurs while Maven is downloading the parent, check repository reachability and the parent version first.

## 11. Common Mistakes When Writing a Minimal POM

| Symptom | Common Cause | How to Check/Fix |
| --- | --- | --- |
| `Non-parseable POM` | Unclosed XML tag, invalid nesting, unescaped `&` character | Check XML syntax and single root `project`; use `&amp;` for literal `&` in XML |
| `Unrecognised tag` | Placing `dependency` outside `dependencies` or `plugin` in the wrong place | Review POM structure; a `dependency` belongs in `dependencies` or `dependencyManagement/dependencies` |
| Parent POM cannot be resolved | Wrong version, offline/network issue, mirror/proxy, or wrong `relativePath` | Verify parent version and repo settings; use empty `<relativePath/>` when fetching starter parent from repository |
| `Cannot find symbol RestController/GetMapping` | Missing web starter or unresolved dependency | Inspect `dependencies`, run Maven sync and `mvn dependency:tree` |
| Dependency version is missing | No parent/BOM managing versions, or dependency is not in the managed list | Inspect effective POM and declare version in the right place |
| `invalid target release: 17` | JDK used by Maven/compiler is older than the selected release | Run `mvn -version`, check JDK/toolchain and `JAVA_HOME` |
| `No plugin found for prefix spring-boot` | Plugin not declared or cannot be resolved | Check `build/plugins` and reachable repositories |
| `mvn package` produces a JAR but `java -jar` fails | Missing repackage execution, picked plain archive by mistake, or missing main class | Inspect effective POM, `spring-boot:repackage` log, and manifest/archive |
| `Unable to find a single main class` | Multiple entrypoints or no main class discoverable by the plugin | Keep one clear entrypoint, configure `mainClass` when truly needed |
| Test compile/fail | Missing test starter, broken test code, or context startup failure | Inspect Surefire output, test package, annotations, and environment |
| `mvn` succeeds but IDE still shows red errors | IDE hasn't imported POM, wrong JDK, different Maven settings | Reload Maven project, compare JDK and Maven distribution/settings |
| Build works on machine A but fails on machine B | Different Maven/JDK, mirror, profile, environment, or cache | Use Maven Wrapper/standard JDK, record versions and reproducible commands |

Do not try to fix issues by randomly deleting the parent, manually adding `<version>` to every starter, or wiping the entire cache. Identify whether the error is in **POM syntax**, **resolution**, **compiler**, **test**, or **packaging**, then fix the exact part.

## 12. Misconceptions to Avoid

**"Parent POM is a dependency."** False. The parent is declared in `<parent>` so Maven inherits configuration. Dependencies live in `<dependencies>` to place libraries on the classpath.

**"Having `spring-boot-starter-parent` automatically gives you a web server."** False. The parent manages configuration; to build a simple MVC web app like the example, you must declare `spring-boot-starter-web`.

**"`<java.version>17</java.version>` automatically installs JDK 17."** False. This is a property configuring the Java target; a suitable JDK must be installed and used by Maven/compiler.

**"Omitting a starter's version makes Maven fetch the latest version."** False. Versions are managed via the BOM/parent; without appropriate management, Maven will report a missing version.

**"Having the Boot plugin in `pluginManagement` means Maven always runs repackage."** False. The plugin/execution must be applied to the module; the standard Spring Boot parent provides the execution when the plugin is properly declared.

**"Once `mvn test` passes, you have an executable JAR."** False. `test` runs before `package`; `package` is required to produce the JAR. Conversely, `spring-boot:run` can run the app without generating an executable JAR under `target`.

**"Only `pom.xml` is needed, no Java code."** Maven can recognize a project and package a basic artifact when source code is absent; to have an actually runnable application, you need an entrypoint and appropriate code.

## 13. Hands-On Exercise and Completion Criteria

Practice in a fresh `demo` directory with JDK 17+ and compatible Maven.

1. Create the complete POM from Section 3, the two Java files from Sections 6.1–6.2, and optionally the test from Section 6.3.
2. Run `mvn -version` and note the Java runtime running Maven.
3. Run `mvn clean test`. Verify Java classes compile and the JUnit context test passes if created.
4. Run `mvn spring-boot:run`, send a GET request to `http://localhost:8080/ping`, verify the body `pong`; stop the app with Ctrl+C.
5. Run `mvn clean package`; inspect files under `target`, confirm the Maven log shows `spring-boot:repackage`, and run `java -jar target/demo-0.0.1-SNAPSHOT.jar`.
6. Run `mvn help:effective-pom -Doutput=target/effective-pom.xml`; locate `java.version`/compiler config, the Spring Boot plugin, the `repackage` execution, and `dependencyManagement`.
7. Try **removing only** `spring-boot-starter-web` from a copy of the POM: controller source will no longer have MVC APIs on the compile classpath. Restore the dependency and verify the build again.
8. Try removing `spring-boot-maven-plugin` from a copy of the POM: observe that `package` still produces a basic JAR but lacks the `repackage` execution for an executable Boot archive. Restore the plugin and verify the result.
9. Try changing `artifactId` in a copy and explain why the output filename changes while the `/ping` URL does not depend on `artifactId`.

### Self-Check Questions

**Question 1.** In the example POM, why does `spring-boot-starter-web` not need a `<version>`?

**Answer:** `spring-boot-starter-parent` inherits `dependencyManagement` from `spring-boot-dependencies` to provide managed versions.

**Question 2.** Is it mandatory to declare `<packaging>jar</packaging>`?

**Answer:** No. Maven defaults to `jar` packaging if omitted.

**Question 3.** What is the difference between `<version>0.0.1-SNAPSHOT</version>` on the project and `<version>3.3.13</version>` on the parent?

**Answer:** The first is the version of the application's own artifact; the second selects the version of the Spring Boot starter parent and its corresponding managed defaults.

**Question 4.** Why are `mvn spring-boot:run` and `java -jar target/...jar` not the same operation?

**Answer:** The `run` goal launches the application through the plugin during development; `java -jar` executes the built and repackaged executable archive.

**Question 5.** If you cannot use `spring-boot-starter-parent` due to an internal parent, is importing the BOM alone enough to replace all configuration?

**Answer:** Not yet. The BOM solves dependency management, whereas Java compiler settings, plugin management, and the `repackage` execution must be configured via the current parent or module POM.

**Completion criteria:** you have a valid POM, the Java 17+ project compiles, `mvn test`/`mvn package` succeed as configured, `/ping` returns `pong`, the executable JAR runs, and you can explain each POM block without confusing parent, dependency, and plugin.

## 14. Official References

- Spring Boot 3.3 — Tutorial: Developing Your First Spring Boot Application: https://docs.spring.io/spring-boot/3.3/tutorial/first-application/
- Spring Boot 3.3 — Maven Plugin, Using the Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Boot 3.3 — Maven Plugin, Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Maven POM Reference: https://maven.apache.org/pom.html
- Maven Introduction to the Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html

When creating real-world projects with Spring Initializr or a team-approved template, prefer keeping the template's structure and corresponding versions. The POM is an important build input, but **the result after inheritance and dependency resolution** shows exactly how Maven will execute.
