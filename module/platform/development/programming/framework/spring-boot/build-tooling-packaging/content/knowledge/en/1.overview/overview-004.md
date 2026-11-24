# Artifact, Dependency, Repository, Classpath, and Lifecycle in Spring Boot

When building a Spring Boot application, tools like Maven and Gradle must answer five questions: **what deliverable needs to be produced (artifact), what libraries are needed (dependency), where do we fetch them from (repository), where do the JVM and compiler find classes (classpath), and in what order do build tasks run (lifecycle)**. These five concepts are interconnected, yet each has a distinct role.

## 1. The Big Picture

```text
Source code + build configuration
       |
       | declare dependencies and repositories
       v
Resolve versions, download dependent artifacts
       |
       v
Build appropriate compile/test/runtime classpaths
       |
       v
Lifecycle or task graph: compile -> test -> package
       |
       v
Output artifact: JAR/WAR (can be a Spring Boot executable JAR)
```

For example, an application declares `spring-boot-starter`. The build tool looks up required artifacts in repositories, resolves transitive dependencies, places the appropriate libraries onto the classpath for compiling/running, and produces a JAR through the build steps. **Declaring a dependency**, **putting classes on the classpath**, and **packaging libraries into a JAR** are three related actions, not synonyms.

## 2. Artifact — What Is Produced or Reused

An **artifact** is an identifiable—and usually versioned—deliverable that a build tool can produce, store, download, or distribute: `.jar`, `.war`, `.pom`, and other formats. A third-party library is an input artifact; your project's application JAR is an output artifact.

In Maven, the three fundamental identifying coordinates are **GAV**:

| Component | Meaning | Example |
|---|---|---|
| `groupId` | Owning group/organization | `com.example` |
| `artifactId` | Module/product name | `build-terms-demo` |
| `version` | Version | `0.0.1-SNAPSHOT` |

The coordinates `com.example:build-terms-demo:0.0.1-SNAPSHOT` identify **which artifact**; packaging type (`jar`, `war`, `pom`) and sometimes a `classifier` (such as a sources or tests artifact) identify the **file variant**. `SNAPSHOT` denotes an in-development version that may change between publications; fixed release versions are better suited for reproducible builds. Do not infer from a filename alone that every JAR is self-executable.

Common outputs:
- Maven: `target/build-terms-demo-0.0.1-SNAPSHOT.jar`.
- Gradle: `build/libs/build-terms-demo-0.0.1-SNAPSHOT.jar` (when `rootProject.name` and `version` are set as in the example below).
- Spring Boot: the `bootJar` task / `repackage` goal produces an **executable JAR** containing application code plus required runtime dependencies. Regular library JARs typically do not bundle these dependencies.

## 3. Dependency — An Artifact Needed by Another Component

A **dependency** is a reliance relationship: module A needs module B to compile, test, or run. A declared dependency can pull in **transitive dependencies**. For example, a Spring Boot starter can bring in Spring core libraries, logging, and autoconfiguration; not all of them are listed directly in the application's build configuration.

A dependency should be evaluated across at least three dimensions:
1. **Identity and version**: which library and which version wins after conflict resolution.
2. **Usage scope**: whether it is needed at compile time, runtime, or test time.
3. **Transitive relationships**: which additional dependencies get pulled in, and whether any must be excluded.

### Maven Scopes and Gradle Configurations

| Intent | Maven | Common Gradle | Practical Meaning |
|---|---|---|---|
| Needed at compile and runtime | `compile` (default) | `implementation` | Present when compiling and running the application |
| Needed only at compile time | `provided` | `compileOnly` | Usually assumes the runtime environment provides the library; semantics are not strictly identical |
| Needed only at runtime | `runtime` | `runtimeOnly` | Not needed to compile main source code |
| Used only for tests | `test` | `testImplementation` | Not packaged as a regular runtime dependency |
| Expose library API to consumers | No direct equivalent scope | `api` with `java-library` plugin | Dependency is part of the library's public API |

In Maven, `provided` is still present on compile and test classpaths, but not on the regular runtime classpath; in Gradle, `compileOnly` does not automatically become a runtime dependency. Do not use these configurations in place of `implementation` just to shrink a JAR: runtime can fail with `NoClassDefFoundError`.

**Version management differs from adding a dependency.** Maven's `dependencyManagement` or a BOM (Bill of Materials) only manages versions and version alignment rules; only when a module explicitly declares a dependency is that library added to the dependency graph. Spring Boot uses a BOM to keep library versions compatible. Maven `spring-boot-starter-parent` provides build defaults and dependency management; Gradle can use `platform('org.springframework.boot:spring-boot-dependencies:...')`.

When multiple branches pull in different versions of the same module, the build tool performs **dependency resolution** using its own rules. Maven generally uses the nearest-definition rule in the dependency tree; Gradle evaluates requirements/constraints and selects versions using Gradle's conflict resolution mechanism. Therefore, always inspect the **actually resolved version** rather than looking only at directly declared dependencies.

Diagnostic commands:

```bash
# Maven: view the resolved dependency tree
mvn dependency:tree

# Gradle: view dependencies of the runtime classpath
./gradlew dependencies --configuration runtimeClasspath

# Windows, when the project has the Gradle Wrapper
gradlew.bat dependencies --configuration runtimeClasspath
```

`./gradlew`/`gradlew.bat` requires the Gradle Wrapper files in the project. Maven similarly provides `./mvnw`/`mvnw.cmd` if the project generated the Maven Wrapper.

## 4. Repository — Where Artifacts Are Stored and Fetched

A **repository** in a build context is a store of published artifacts with metadata, not automatically a Git source code repository.

- **Remote repository:** a server hosting artifacts for download, such as Maven Central or an organization's internal repository.
- **Local Maven repository:** typically `~/.m2/repository`; caches downloaded/installed artifacts. `mvn install` also places the built artifact into this local repository.
- **Gradle dependency cache:** Gradle stores resolved artifacts and metadata under Gradle's cache directory (typically `~/.gradle/caches`); this cache does not share the exact layout of a Maven repository.
- **Plugin repository:** where build plugins are resolved; in Gradle, plugin repositories and dependency repositories can be configured independently.

General workflow: read dependency coordinates → query repository/cached metadata → determine versions and transitive dependencies → download or reuse cached copy → place appropriate artifacts onto the classpath. When offline, a build can still succeed if all required artifacts are cached; otherwise it may fail with `Could not resolve dependency` even if source code hasn't changed.

Maven configuration typically relies on Maven Central by default plus internal repositories from `settings.xml`/POM when needed. With Gradle, declare dependency repositories in `build.gradle`:

```groovy
repositories {
    mavenCentral()
}
```

Do not add untrusted repositories or hardcode passwords in build files. A repository missing an artifact, failing authentication, or having conflicting metadata is a **resolution** issue, not necessarily a Java error.

## 5. Classpath — Where Java Finds Classes and Resources

The **classpath** is the set of locations (directories containing `.class` files, JARs) searched by the compiler or JVM to locate classes and resources. This concept is distinct from source code paths and from repository storage. Modern applications may also use JPMS **module paths**, though most standard Spring Boot projects still rely primarily on the classpath.

Common classpaths:
- **Compile classpath:** libraries needed to compile code in `src/main/java`.
- **Test classpath:** compiled application code plus testing libraries.
- **Runtime classpath:** application code plus dependencies needed at execution time, which may differ from the compile classpath.

The pure Java 17 example below shows a directory of bytecode added to the classpath. Create `src/demo/ClasspathDemo.java`:

```java
package demo;

public class ClasspathDemo {
    public static void main(String[] args) {
        System.out.println(ClasspathDemo.class.getName());
        System.out.println(
            ClasspathDemo.class.getResource("ClasspathDemo.class") != null
        );
    }
}
```

From the example root directory, run:

```bash
javac -d out src/demo/ClasspathDemo.java
java -cp out demo.ClasspathDemo
```

Exact stdout:

```text
demo.ClasspathDemo
true
```

`-d out` places `.class` files into `out/demo/`; `-cp out` tells the JVM the root of package `demo`. If you forget `-cp out` and the class isn't on the default classpath, the command fails to find the main class. Multiple classpath entries are separated by `;` on Windows and `:` on Linux/macOS; when pointing to a single directory as above, no separator is needed.

Distinguish two error types:
- `ClassNotFoundException`: code attempts to load a class by name, but it cannot be found on the classpath/module path at load time.
- `NoClassDefFoundError`: the JVM needs a class definition at runtime, but cannot load it (often due to a missing dependency, or because class initialization failed).

In a Spring Boot executable JAR, the structure typically contains `BOOT-INF/classes` (application code/resources) and `BOOT-INF/lib` (dependency JARs). The **Spring Boot launcher** handles loading nested JARs; do not assume a plain `java -cp app.jar ...` command will automatically read nested JARs. Run packaged applications with `java -jar app.jar`. When `-jar` is used, the Java launcher ignores `-cp` as an additional application classpath.

## 6. Lifecycle — In What Order Do Build Tasks Run?

### Maven: Lifecycles, Phases, and Plugin Goals

Maven has standard lifecycles such as **default**, **clean**, and **site**. The `default` lifecycle consists of ordered phases; invoking a phase executes all required preceding phases within that lifecycle. For example:

| Command / Phase | Primary Work |
|---|---|
| `mvn validate` | Validate project information |
| `mvn compile` | Compile main source code (after preceding phases) |
| `mvn test` | Compile and run unit tests per configuration |
| `mvn package` | Package the artifact, e.g., JAR |
| `mvn verify` | Run checks to verify the artifact meets quality criteria |
| `mvn install` | Install the artifact into the local Maven repository |
| `mvn deploy` | Publish the artifact to the configured remote repository |

`mvn clean package` executes the `clean` phase from the `clean` lifecycle first, then runs up through `package` in the `default` lifecycle. `clean` is not a phase of the `default` lifecycle. `deploy` in Maven means **publishing the artifact to a repository**, not automatically deploying the application to production.

A **plugin goal** is a specific action performed by a plugin (e.g., `compiler:compile` or `spring-boot:repackage`); Maven binds goals to phases based on packaging type and plugin configuration. You can invoke a goal directly, such as `mvn dependency:tree`, without running the whole `package` phase.

### Gradle: Task Graph Instead of Maven Phases

Gradle models builds using **tasks** and dependencies between tasks. The `java` plugin provides tasks such as `compileJava`, `test`, `jar`, and `build`. The Spring Boot Gradle plugin adds `bootJar` and `bootRun` for matching projects. When running `gradle build`, Gradle executes the required tasks along the dependency graph; there is no fixed `validate -> compile -> ... -> deploy` phase chain like Maven.

```bash
# Run a task and all tasks it depends on
./gradlew build

# Create the Spring Boot executable JAR
./gradlew bootJar

# Run the application directly from the project
./gradlew bootRun

# Preview the planned task graph without executing it
./gradlew build --dry-run
```

Tasks can be skipped when inputs/outputs haven't changed or satisfied from cache when valid. Thus, `UP-TO-DATE`/`FROM-CACHE` log entries do not mean the task was ignored.

## 7. Example Connecting All Five Concepts in a Spring Boot Project

This example uses **Java 17** and Spring Boot **3.5.0** so the configuration snippets have concrete, compatible versions. These are illustrative versions; real projects should select actively supported versions with current patches. Choose **Maven or Gradle**—do not place both configurations below into one build expecting them to stay synchronized automatically.

### Maven Option

Create `pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.0</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>build-terms-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

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
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

No separate `version` is specified for the two starters because the parent manages their versions; the `<dependency>` entries themselves are what bring them into use.

Create `src/main/java/com/example/buildterms/BuildTermsApplication.java`:

```java
package com.example.buildterms;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BuildTermsApplication {
    public static void main(String[] args) {
        SpringApplication.run(BuildTermsApplication.class, args);
    }
}
```

Prerequisites: JDK 17+ and Maven available, with network access or a populated cache for dependencies. Run in the directory containing `pom.xml`:

```bash
mvn clean package
java -jar target/build-terms-demo-0.0.1-SNAPSHOT.jar
```

The first command resolves dependencies from repositories, compiles, tests, and produces the artifact. The Spring Boot Maven plugin's `repackage` creates the executable JAR at the path shown above. The second command runs the application via the Boot launcher; startup logs depend on configuration/environment, so do not assume a fixed stdout line. Because the project uses `spring-boot-starter` (not the web starter), no HTTP endpoint is automatically opened on port 8080.

### Equivalent Gradle Option

You can reuse the exact same Java file above in a Gradle project. Create `settings.gradle`:

```groovy
rootProject.name = 'build-terms-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.0'
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
    implementation platform('org.springframework.boot:spring-boot-dependencies:3.5.0')
    implementation 'org.springframework.boot:spring-boot-starter'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Here `platform` imports version constraints from the Spring Boot BOM; `implementation` and `testImplementation` actually add the starters to the dependency graph. With Gradle installed or a Gradle Wrapper generated for the project:

```bash
./gradlew clean bootJar
java -jar build/libs/build-terms-demo-0.0.1-SNAPSHOT.jar
```

On Windows, replace `./gradlew` with `gradlew.bat`. The `bootJar` task packages the runnable application, while the Java plugin's `jar` task creates a regular JAR; they are not interchangeable for every use case.

### Tracing a Build from Start to Finish

1. **Target artifact:** `com.example:build-terms-demo:0.0.1-SNAPSHOT` becomes the application JAR.
2. **Dependencies:** `spring-boot-starter` and `spring-boot-starter-test` are declared; starters bring transitive dependencies.
3. **Repositories:** Maven/Gradle queries Maven Central and configured caches to fetch missing artifacts.
4. **Classpaths:** the compiler uses the compile classpath; tests add testing libraries; running the app uses runtime dependencies.
5. **Lifecycle/tasks:** Maven progresses to the `package` phase, Gradle runs `bootJar` along with its dependent tasks; Spring Boot packages the executable JAR.
6. **Runtime:** `java -jar` invokes the Boot launcher to access classes and dependencies inside the JAR.

## 8. Common Errors and How to Pinpoint the Right Layer

| Symptom | Concept to Check | Recommended Action |
|---|---|---|
| `Could not resolve ...` / `artifact not found` | Repository + dependency | Verify coordinates/version, repositories, network, authentication, and cache |
| Compiler error `package ... does not exist` | Compile classpath | Check that the dependency is declared with the right scope/configuration and resolved |
| Tests pass but `java -jar` fails with missing class | Runtime classpath + packaging | Check `test`/`provided`/`compileOnly`, transitive exclusions, and runtime dependencies |
| JAR fails on `java -jar` with missing main manifest | Artifact + packaging | Check whether the JAR was produced by `bootJar`/`repackage` or is just a plain JAR |
| `mvn package` and `mvn install` behave differently | Maven lifecycle | `install` also puts the artifact into the local repository; `package` stops short of that |
| `gradle build` appears not to re-run a step | Task graph / cache | Check `--dry-run`, `--info`, and `UP-TO-DATE`/`FROM-CACHE` status |
| Running JAR exposes no HTTP endpoint | Dependency + application | Plain `spring-boot-starter` does not include a web server; you need a web starter and endpoint |

**Rule of thumb:** artifact is **what** is produced/consumed; dependency is **what is needed**; repository is **where it comes from**; classpath is **where classes are searched**; lifecycle/task graph is **what runs and in what order**. Understanding these boundaries helps pinpoint build issues at the right layer instead of randomly changing versions or commands.