# Packaging Internal Dependencies and Required Transitive Libraries in Multi-Module Spring Boot Projects

## 1. The Problem: A Runnable Application Must Carry Its Entire Runtime Dependency Chain

A Spring Boot repository often contains multiple modules: an `app` module responsible for starting an HTTP server or batch job, and one or more `core`, `domain`, `persistence`, or `adapter` modules containing business logic or shared code. Each module may in turn depend on external libraries. **When shipping an executable JAR**, the application needs not only `app`'s own code, but also **internal modules and the transitive libraries required at runtime**.

Consider the minimal graph:

~~~text
multi-module-demo
├── core                  (internal Java library)
│   └── commons-lang3     (external library, called directly by core)
└── app                   (Spring Boot application)
    ├── core              (app calls core's public API)
    │   └── commons-lang3 (transitive dependency needed when core executes)
    └── spring-boot-starter-web
        └── Spring MVC / embedded server / logging / ...
~~~

If `app` packages only `app` classes and **omits `core.jar`**, the JVM cannot find `com.example.core.GreetingComposer`. If it includes `core.jar` yet **omits `commons-lang3.jar`**, the application may load `GreetingComposer` and then crash when invoking the method that actually uses `org.apache.commons.lang3.StringUtils`. Both are **runtime classpath** failures that may not surface during compilation or in tests that skip that code path.

**Goal of this lesson:** given multi-module project sources, accurately identify **direct internal dependencies** (`app → core`) and **transitive dependencies** (`core → commons-lang3`), package them into the app module's executable JAR, and prove that both **archive structure and actual behavior** are correct.

Examples use **Java 17, Spring Boot 3.3.13, and Maven or Gradle** with deliberate configurations for learning purposes; this is not a claim of the latest versions. Commands and files should be executed in an environment with a compatible JDK/Wrapper, repository access, and required preconditions. Do not treat expected outputs as pre-measured logs.

### Learning Outcomes

After completing this lesson, you will be able to:

1. Distinguish **multi-module build graph**, **dependency graph**, and **runtime archive classpath**.
2. Have library modules produce **plain JARs**, and only the app module produce a **Spring Boot executable JAR**.
3. Configure Maven reactor `<modules>`, dependencies on `core`, and Spring Boot `repackage` without accidentally repackaging libraries.
4. Configure Gradle `include('core', 'app')`, `implementation project(':core')`, `java-library`, and `bootJar`.
5. Explain Maven transitive dependencies/scopes and Gradle `api` versus `implementation` for library consumers.
6. Use `dependency:tree`, `dependencies`, `dependencyInsight`, and `jar tf` to verify the resolved graph against files in `BOOT-INF/lib`.
7. Test `java -jar` and an endpoint that exercises `core`'s code, not just an endpoint that bypasses dependencies.
8. Diagnose missing internal artifacts, missing transitive libraries, version mismatches, `compileOnly`/`test`/`optional`, and plain-vs-executable JAR mix-ups.

## 2. Three Related Yet Distinct Graphs

### 2.1. The Build's Module Graph

**Maven** knows which modules belong to the reactor via `<modules>` in the aggregator POM. **Gradle** knows subprojects via `include(...)` in `settings.gradle`. This structure lets the build tool select and order module builds, yet **does not automatically define a dependency from `app` to `core`**.

For example, a Maven root having:

~~~xml
<modules>
    <module>core</module>
    <module>app</module>
</modules>
~~~

or Gradle settings:

~~~groovy
include('core', 'app')
~~~

On their own, those two snippets **do not let `app` use `core`**. The app module must still **declare the dependency** with accurate Maven coordinates or a Gradle project dependency.

### 2.2. The Dependency Graph

Once `app → core` and `core → commons-lang3` are declared, the build tool resolves **the entire path** according to metadata, scopes/configurations, constraints, BOMs, exclusions, version conflicts, and project variants.

~~~mermaid
flowchart LR
    A["app (Spring Boot)"] --> C["core (internal library)"]
    C --> L["commons-lang3 (external library)"]
    A --> W["spring-boot-starter-web"]
    W --> S["Spring MVC + embedded Tomcat + other runtime deps"]
~~~

- **Direct dependencies of app:** `core` and `spring-boot-starter-web`.
- **Transitive dependency via core:** `commons-lang3`.
- **Resolved version:** the final version selected by the build tool, which may differ from a requested version due to BOMs, constraints, or conflict resolution.
- **Whether it gets packaged into the executable JAR:** also depends on scope, runtime configuration, and the Spring Boot plugin's packaging rules.

An entry in Maven `dependencyManagement` or a Gradle version catalog only manages declarations/versions and **does not automatically add a new dependency to the graph**.

### 2.3. The Product's Runtime Classpath Graph

An executable Spring Boot JAR typically has the layout:

~~~text
app-1.0.0-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...    (Boot Loader)
└── BOOT-INF/
    ├── classes/
    │   └── com/example/app/MultiModuleApplication.class
    └── lib/
        ├── core-1.0.0-SNAPSHOT.jar
        ├── commons-lang3-<resolved-version>.jar
        ├── spring-boot-<resolved-version>.jar
        ├── spring-webmvc-<resolved-version>.jar
        └── ... (other runtime libraries)
~~~

**Two important facts:**

- `app` code sits under `BOOT-INF/classes`; internal module `core` typically sits as a **nested `core.jar` inside `BOOT-INF/lib`**, rather than being unpacked directly into `BOOT-INF/classes`.
- `commons-lang3` sits in `BOOT-INF/lib` **even though `app` does not declare it directly**, as long as that transitive dependency stays in `app`'s resolved runtime graph and is not excluded by packaging rules.

Java does not automatically treat `BOOT-INF/lib/*.jar` inside an outer ZIP as a classpath. The Spring Boot Loader launches via the manifest (`Main-Class`) and constructs a classpath from app classes plus nested libraries before invoking `Start-Class`. This differs from a plain JAR.

**Do not confuse "present in the build cache" with "present in the archive".** The Maven local repository/Gradle cache only holds files for building; ultimately you must verify the **exact app JAR** being delivered.

## 3. Module Design: Only the Application Has a Boot Entry Point

The demo has two modules:

| Module | Build Type | Provides | What Artifact Should It Produce? |
| --- | --- | --- | --- |
| `core` | Maven `jar` or Gradle `java-library` | `GreetingComposer` and string-processing dependency | **Plain library JAR** for `app` and other projects to consume. |
| `app` | Spring Boot application | `@SpringBootApplication`, REST `/ping`, dependency on `core` | **Spring Boot executable JAR** with `BOOT-INF/classes` and `BOOT-INF/lib`. |
| Root | Maven aggregator `pom` / Gradle settings + root build | Manages modules/plugins/versions/repositories | Not an application; does not need an executable JAR. |

**Anti-pattern:** applying `spring-boot-maven-plugin` with `repackage` or Gradle `org.springframework.boot` to **every library module**, then consuming the boot-repackaged `core.jar` as a dependency of `app`. A Boot executable JAR puts classes under `BOOT-INF/classes` instead of root package paths like a standard library JAR; Java/Maven/Gradle consumers do not treat that layout as a standard library classpath. The result can be `package com.example.core does not exist` even though you see `GreetingComposer.class` inside the file.

Practical rule: **`core` builds a plain JAR; `app` builds a Boot JAR**. If a module must both publish a library and offer a standalone executable variant, clearly separate **classifier/variant/artifact** so consumers pull the plain library artifact; never turn the default library artifact into a Boot JAR without verifying consumer metadata.

### 3.1. When Should You Create a Separate Module?

A library is worth extracting when it has a stable responsibility, a clear public API, independent testability, and reasonable reuse. There is no need to make every class its own module. Too many modules complicate dependency graphs, build configuration, and release governance.

### 3.2. Do Not Treat the Root Aggregator as a Dependency of Every Module

Maven `<parent>` provides inheritance of settings/plugin/dependency management; `<modules>` controls aggregation; `<dependencies>` adds libraries. Gradle `include(...)` defines project membership; `implementation(project(':core'))` adds dependencies. **Parent and aggregator do not replace dependency declarations.**

## 4. Java 17 Example Sharing the Same Sources for Maven and Gradle

Directory tree:

~~~text
multi-module-demo/
├── pom.xml                          # Maven root aggregator, if using Maven
├── settings.gradle                  # Gradle root, if using Gradle
├── build.gradle                     # Gradle root, if using Gradle
├── core/
│   ├── pom.xml                      # Maven, if using Maven
│   ├── build.gradle                 # Gradle, if using Gradle
│   └── src/main/java/com/example/core/GreetingComposer.java
└── app/
    ├── pom.xml                      # Maven, if using Maven
    ├── build.gradle                 # Gradle, if using Gradle
    ├── src/main/java/com/example/app/MultiModuleApplication.java
    └── src/test/java/com/example/app/MultiModuleApplicationTest.java
~~~

**Choose one build tool for your hands-on run:** Maven needs Maven Wrapper (`mvnw`, `mvnw.cmd`, `.mvn/wrapper`); Gradle needs Gradle Wrapper (`gradlew`, `gradlew.bat`, `gradle/wrapper`). This lesson presents both setups side by side for comparison, without suggesting real projects maintain two build pipelines.

### 4.1. `core` Module Calling an External Library

`core/src/main/java/com/example/core/GreetingComposer.java`:

~~~java
package com.example.core;

import org.apache.commons.lang3.StringUtils;

public final class GreetingComposer {

    private GreetingComposer() {
    }

    public static String message() {
        return StringUtils.capitalize("from core");
    }
}
~~~

Explanation:

- `core`'s public API is `String message()`, returning a **standard Java String**.
- Using **Apache Commons Lang 3**'s `StringUtils.capitalize` is an **implementation detail inside the method body** and does not appear in the public method signature.
- When the method executes, the JVM needs `org.apache.commons.lang3.StringUtils`. Thus `commons-lang3` must be present in `app`'s runtime dependency graph.
- Given the exact input `"from core"`, `StringUtils.capitalize` returns `"From core"`. This class has no `main()` entry point and does not run via `java GreetingComposer`; it is a library called by applications.

### 4.2. `app` Module Calling `core`

`app/src/main/java/com/example/app/MultiModuleApplication.java`:

~~~java
package com.example.app;

import com.example.core.GreetingComposer;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class MultiModuleApplication {

    public static void main(String[] args) {
        SpringApplication.run(MultiModuleApplication.class, args);
    }

    @GetMapping("/ping")
    public String ping() {
        return "hello " + GreetingComposer.message();
    }
}
~~~

When `GET /ping` hits `app`, the execution flow is:

~~~text
HTTP GET /ping
  -> MultiModuleApplication.ping()   (app module)
  -> GreetingComposer.message()      (core module)
  -> StringUtils.capitalize(...)     (commons-lang3 transitive dependency)
  -> HTTP 200 / "hello From core"
~~~

This is a **better check** than a `/ping` returning a literal inside `app` without calling `core`: if runtime lacks `core` or `commons-lang3`, the request fails with an appropriate error. Testing only startup without touching dependencies can miss missing classes.

### 4.3. App Test Using JUnit + MockMvc

`app/src/test/java/com/example/app/MultiModuleApplicationTest.java`:

~~~java
package com.example.app;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.web.servlet.MockMvc;

import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest
@AutoConfigureMockMvc
class MultiModuleApplicationTest {

    @Autowired
    private MockMvc mvc;

    @Test
    void applicationUsesCoreAndTransitiveLibrary() throws Exception {
        mvc.perform(get("/ping"))
           .andExpect(status().isOk())
           .andExpect(content().string("hello From core"));
    }
}
~~~

The test uses the **Spring test context and MockMvc** without opening a real HTTP port. It proves `app` and `core` work together on the **test runtime classpath**. It **does not replace** a `java -jar` check because the test classpath can be broader than the packaged archive's classpath. A solid pipeline verifies both test reports and the **executable JAR**.

## 5. Maven: Three POMs, One Reactor, Right Dependency Scopes

### 5.1. Root `pom.xml`: Aggregator and Parent of Both Modules

Create `multi-module-demo/pom.xml`:

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
    <artifactId>multi-module-demo</artifactId>
    <version>1.0.0-SNAPSHOT</version>
    <packaging>pom</packaging>

    <modules>
        <module>core</module>
        <module>app</module>
    </modules>

    <properties>
        <java.version>17</java.version>
    </properties>
</project>
~~~

**Key points:**

- `<packaging>pom</packaging>` is mandatory for an aggregator POM like this.
- `<modules>` lists the two modules so the Maven reactor determines build order from dependencies, without automatically attaching `core` to `app`.
- Parent `spring-boot-starter-parent` lets the root and children inherit dependency/plugin management aligned with Spring Boot 3.3.13.
- The root **does not** declare `spring-boot-maven-plugin` in `<build><plugins>`. As a result, `repackage` is not automatically applied to the root or `core`.
- This is an illustrative setup using the Boot starter parent. Organizations using a corporate parent and importing the BOM must configure compiler/JDK, plugin versions, and `repackage` separately; the BOM alone does not supply all build defaults.

### 5.2. `core/pom.xml`: Produces Only a Library JAR

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>multi-module-demo</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>core</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</project>
~~~

- `core` does not apply the Spring Boot Maven plugin, so `mvn package` builds the **plain `core-1.0.0-SNAPSHOT.jar`** with classes under `com/example/core/...` directly at the JAR root.
- `commons-lang3` has Maven's default `compile` scope, making it a **transitively visible dependency** in the Maven dependency graph rather than `test`/`provided`/`system`.
- Version `3.14.0` is the **requested version** of this specific declaration. When the app has dependency management/BOM or another dependency path, the **selected version** in the final graph may differ. Do not write an assertion requiring exact `commons-lang3-3.14.0.jar` without checking the dependency tree.
- Because `GreetingComposer` directly uses `StringUtils` at compile time, do not switch Commons Lang to Maven's `runtime` scope: `core` would fail to compile.

### 5.3. `app/pom.xml`: Boot JAR and Direct Internal Dependency

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>com.example</groupId>
        <artifactId>multi-module-demo</artifactId>
        <version>1.0.0-SNAPSHOT</version>
        <relativePath>../pom.xml</relativePath>
    </parent>

    <artifactId>app</artifactId>
    <packaging>jar</packaging>

    <dependencies>
        <!-- Internal dependency: app directly calls classes belonging to core -->
        <dependency>
            <groupId>com.example</groupId>
            <artifactId>core</artifactId>
            <version>${project.version}</version>
        </dependency>

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
            <!-- Only the application module gets Spring Boot repackage -->
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
~~~

**Packaging mechanism:**

1. The Maven reactor builds `core` before `app` because `app` declares a dependency on `core` in the same build.
2. `core` outputs a plain library JAR without Boot repackaging.
3. `app` compiles against `core` and Spring MVC from the starter.
4. `app`'s runtime dependency graph includes `core`; `core` brings in `commons-lang3` via Maven transitivity/scope unless altered by exclusions, `optional`, or dependency management.
5. When `mvn package` builds the app JAR, the Spring Boot plugin `repackage` bundles it into an executable archive with `BOOT-INF/classes` and runtime libraries in `BOOT-INF/lib`.
6. `spring-boot-starter-test` is in `test` scope, so it is **not** included in the standard Boot runtime archive.

`${project.version}` in the app dependency is a Maven expression resolving to the inherited `1.0.0-SNAPSHOT`. It keeps `core`'s version aligned with the reactor in this example; larger teams can manage module versions via `dependencyManagement`, an internal BOM, or CI versioning, while ensuring `app`'s coordinates point to the right `core` artifact.

### 5.4. Building Maven from the Root Reactor

From the root directory with the committed Maven Wrapper:

~~~bash
# Check Maven/JDK
./mvnw -version

# Select only app and all reactor modules app needs
./mvnw -pl app -am clean verify

# Or build the entire reactor
./mvnw clean verify
~~~

Meaning:

- `-pl app`: selects the `app` module.
- `-am`: adds **reactor projects needed to build `app`**, such as `core` (and the aggregator).
- Maven orders the relevant projects by dependency graph. `-am` only works on modules **in the same reactor**; it does not locate source code for external libraries outside the repo.
- `clean verify` runs the proper lifecycle, including compile, test, package, and repackage on **app**, while **not** Boot-repackaging `core` since `core` does not declare the Boot plugin.

**Common error:** running `./mvnw -f app/pom.xml clean package` when `core` has not been installed into the local Maven repository. The child POM may find its parent via `relativePath`, yet the binary dependency `com.example:core` still needs resolution. Run from root with `-pl app -am`, or `install` the library/parent properly beforehand if running a single module.

### 5.5. Running Maven Goals on the Right Module

To test the app via `spring-boot:run` in a multi-module setup:

~~~bash
# Prepare reactor artifacts in the local Maven repository if needed
./mvnw -pl app -am install

# Then invoke the run goal only on the app module
./mvnw -pl app spring-boot:run -Dspring-boot.run.arguments="--server.port=18085"
~~~

Do not mechanically run `./mvnw -pl app -am spring-boot:run`: many plugin goals execute on **every selected project**, causing Maven to attempt running the Boot app goal on `core`, which lacks a main class. With `mvn clean verify`, plugin goals are bound to the right modules/lifecycles, so this issue does not arise.

For local development runs once `core` is already in the local repository, the app can be invoked directly. When `core` SNAPSHOT changes, ensure the local repo reflects the latest build or use a reactor flow so you do not run against stale code.

## 6. Maven Transitivity: When Is Commons Lang Pulled In?

Suppose `app` has:

~~~text
app --compile--> core --compile--> commons-lang3
~~~

In Maven's dependency mechanism, transitive dependencies can flow through multiple levels of the dependency graph. However, scopes and metadata govern whether they appear on `app`'s compile, runtime, or test classpath.

| Case in Module `core` | Impact on `app`? | Consequence to Know |
| --- | --- | --- |
| `commons-lang3` default `compile`, not optional/excluded | Usually present on `app`'s compile/runtime transitive classpath. | `core` can use `StringUtils` when `app` runs. |
| `commons-lang3` `runtime` | Can reach `app` runtime, yet **`core` uses it to compile**, so this `core` config is unsuitable. | `core` compilation can fail unless another path provides the class. |
| `commons-lang3` `test` | Only for `core`'s tests, not a runtime transitive dependency of `app`. | `core` production source using the class will fail to compile. |
| `commons-lang3` `provided` | Maven `core` compile/test sees it, yet it is not propagated as an `app` compile/runtime transitive under standard Maven rules. | `app` Boot runtime may lack the library when the `core` method runs. |
| `commons-lang3` `optional=true` in `core` | Consumers like `app` **do not automatically pull** optional dependencies via `core`. | If `app` actually needs it when calling `core`, `app` must declare the dependency or fix `core`'s metadata. |
| `app` applies `<exclusions>` for `commons-lang3` on the `core` dependency | Removes the transitive dependency along the path from `core`. | JAR still contains `core`, yet may lack Commons at runtime. |

**Distinguish Maven `provided` from Spring Boot packaging rules:** The Boot Maven Plugin has special rules for including direct `provided` dependencies in executable archives; however, you must not assume **any deep `provided` dependency inside `core`** will always appear transitively in `app`. Maven dependency resolution runs first; if `app`'s graph lacks Commons, `repackage` cannot infer it is needed by scanning bytecode.

### 6.1. `optional` Is Not the Same as `exclude`

`optional=true` on a dependency declared in **`core`** tells consuming projects that this dependency may not be needed in all cases. It is normally **not pulled in transitively**. If a `core` feature is mandatory whenever `app` runs, marking it optional violates the contract.

`<exclusions>` in `app` explicitly drops a transitive dependency along a specific dependency edge; if the same artifact arrives through another path, it can still appear. Removing a dependency from the graph differs from **merely excluding a dependency from the archive during Spring Boot repackaging**.

### 6.2. Do Not Use `dependencyManagement` to "Add Commons"

Suppose `app`'s versions are managed in the root POM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.apache.commons</groupId>
            <artifactId>commons-lang3</artifactId>
            <version>3.14.0</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

This is an **illustrative snippet**, absent from the minimal root POM in section 5. `dependencyManagement` chooses versions for dependencies that the graph actually contains; it **does not create a dependency** if no declaration or transitive path exists. If `app` stripped Commons via exclusions/optional and lacks the runtime library, adding version management alone fixes nothing.

### 6.3. Multiple Versions of the Same Library

If `app` directly or through a starter receives a different version of Commons Lang than what `core` declared, Maven applies **dependency mediation** and dependency management precedence. Inspect `dependency:tree -Dverbose` or `dependency:tree` depending on your Maven Dependency Plugin version, and check the selected version. With `StringUtils.capitalize`, its long-standing API keeps the demo simple, yet there is **no rule that every version change is binary-compatible**.

## 7. Gradle: Project Dependencies and `java-library` Variants

In Gradle, root settings defines which subprojects participate in the build; `java-library` separates the **API consumers need to compile** from **internal implementation details consumers only need at runtime**.

### 7.1. Root `settings.gradle`

~~~groovy
pluginManagement {
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = 'multi-module-demo'
include('core', 'app')
~~~

- `include('core', 'app')` registers modules; it does not create `app → core`.
- `dependencyResolutionManagement.repositories` gives subprojects access to Maven Central.
- `pluginManagement.repositories` handles plugin resolution.
- If your organization uses an internal mirror/repository, update repositories per policy; never disable verification or add unapproved mirrors.

### 7.2. Root `build.gradle`: Managing Plugin Versions Without Applying to All Modules

~~~groovy
plugins {
    id 'org.springframework.boot' version '3.3.13' apply false
    id 'io.spring.dependency-management' version '1.1.7' apply false
}
~~~

`apply false` lets the root resolve those plugin IDs/versions for subprojects without **enabling `bootJar` at the root**. `app` applies them explicitly; `core` does not. For multi-module builds, this is usually better than `subprojects { apply plugin: 'org.springframework.boot' }` applying Boot to every library.

**Note:** `java`/`java-library` are Gradle core plugins and need no version. The Spring Boot plugin version is declared at the root for this lesson, while the `app` module declares plugin IDs without versions.

### 7.3. `core/build.gradle`: Internal Library

~~~groovy
plugins {
    id 'java-library'
}

group = 'com.example'
version = '1.0.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

Because `GreetingComposer.message()` returns only `String`, Commons Lang classes **do not appear in the public API**. `implementation` is the right choice:

- When compiling `core`, Gradle supplies Commons Lang.
- When compiling `app` against `core`, Gradle does not expose Commons Lang onto `app`'s compile classpath just because `core` uses it internally.
- When running `app`, `core` **still needs** Commons Lang; `core`'s `runtimeElements` variant carries `implementation` dependencies into the consumer's runtime graph.
- When packaging `:app:bootJar`, `core.jar` and Commons Lang are resolved as runtime libraries (assuming the graph was not altered/excluded).

**Do not turn `core` into a Spring Boot application module** just to use the dependency management plugin. Commons Lang in this `core` example has a direct version, while Boot starter versions in `app` are managed by the declared Boot plugin/dependency-management. If your organization centralizes all versions, use a version catalog, platform/BOM, dependency constraints, or convention plugin while preserving proper scopes/configurations.

### 7.4. `app/build.gradle`: App Dependency on `:core`

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot'
    id 'io.spring.dependency-management'
}

group = 'com.example'
version = '1.0.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    // Direct dependency on the core project in the same Gradle build
    implementation project(':core')

    implementation 'org.springframework.boot:spring-boot-starter-web'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

This is the complete build script matching the sources in section 4:

- `implementation project(':core')` is a **project dependency**; Gradle identifies needed producer tasks/artifacts and wires the task graph accordingly.
- `spring-boot-starter-web` provides Servlet Spring MVC and embedded Tomcat in this example.
- `io.spring.dependency-management` works with the Spring Boot plugin to manage versions for starters and test libraries.
- JUnit/MockMvc stay in test scope and do not belong in the standard runtime artifact.
- `bootJar` applies only in `app`; `core` keeps its Java library `jar`, not an executable Boot JAR.

When `core` and `app` share a Gradle toolchain or plugin conventions, make sure versions align across **both modules**. The example declares Java 17 explicitly in each module to keep snippets self-contained; larger projects can move toolchain rules into a shared convention plugin.

### 7.5. Gradle Task Graph Does Not Need Installing `core` to Maven Local

~~~bash
# From the Gradle repository root with Wrapper
./gradlew :app:build

# Build only the app executable archive
./gradlew :app:bootJar

# Preview the task graph before actually running
./gradlew :app:bootJar --dry-run
~~~

Gradle knows `:core` is a **project dependency in the same build** and fetches `core`'s artifact/outputs via the appropriate variant. You **do not need** to run `publishToMavenLocal` for `app` to consume `core` in the same build. If a company splits `core` into a separate repository/published dependency, then published coordinates/metadata/repositories and versions are required, unlike a project dependency.

**Do not infer from `:core:jar` that `core` classes sit directly inside `app`'s `BOOT-INF/classes`**. `bootJar` normally packages the `core` artifact as a nested `BOOT-INF/lib/core-...jar`. The Spring Boot classloader still locates internal classes at runtime.

## 8. Gradle `api` vs `implementation`: Different Visibility at Compile and Runtime

The `java-library` plugin supports *API/implementation separation*. Consider two scenarios:

**Scenario A — matches the current demo:**

~~~java
// Public API only uses java.lang.String:
public static String message() {
    return org.apache.commons.lang3.StringUtils.capitalize("from core");
}
~~~

Commons Lang is an **implementation detail**, so in `core/build.gradle`:

~~~groovy
dependencies {
    implementation 'org.apache.commons:commons-lang3:3.14.0'
}
~~~

When `app` calls `GreetingComposer.message()`, `app`'s compiler does not need to know about `StringUtils`. Yet when `app` runs, `core` still loads `StringUtils`, so Commons Lang is needed on **`app`'s `runtimeClasspath`** and inside the Boot JAR.

**Scenario B — if the public API returns a type from an external library:**

~~~java
// Illustrative signature only showing a type exposed in the API.
// Suppose ExternalType is a public class from a third-party library:
public ExternalType compute();
~~~

If an external library's type genuinely appears in `core`'s public methods, fields, generic types, or base classes, consumers need that type to **compile**; Gradle should use `api` instead of `implementation` when the library is also needed at runtime:

~~~groovy
dependencies {
    api 'com.example:public-contract-library:1.0.0'
}
~~~

This is an **illustrative snippet**, not an actual dependency in the demo. Choosing `api` depends on the real Java ABI; if a library is used only inside private method bodies, stick with `implementation` to minimize compile classpaths and avoid unnecessary rebuilds.

| `core` Configuration | On `app` Compile Classpath? | On `app` Runtime Classpath? | When to Use? |
| --- | --- | --- | --- |
| `api` | Yes, transitively exposed. | Yes. | Dependency types appear in `core`'s public API/ABI. |
| `implementation` | Not directly leaked onto `app`'s compile classpath. | Yes. | Internal implementation details, like Commons Lang in the demo. |
| `runtimeOnly` | No. | Yes. | Libraries needed only at runtime (drivers, runtime plugins...), not needed to compile `core` sources. |
| `compileOnly` | Does not make runtime dependency transitively available. | **No**. | Compile-time APIs/annotations not needed at runtime; dangerous if code calls classes at runtime. |
| `testImplementation` | No. | Not in main runtime. | `core` tests, not distributed to `app`. |

**Real-world failure:** changing `core`'s Commons Lang from `implementation` to `compileOnly` can let `core` compile, and `app` compile/test if an extra classpath masks it, yet the executable Boot JAR **lacks Commons Lang** if no other runtime path provides it. The result can be `NoClassDefFoundError: org/apache/commons/lang3/StringUtils` when calling `/ping`. Never fix this by disabling tests or manually stuffing JARs into the archive; fix the **dependency configuration**.

## 9. Comparing Compile/Test/Runtime Across Maven and Gradle

### 9.1. Classification by Dependency Source

| Source / Component | When Compiling `app` | When Testing `app` | When Running Packaged Boot JAR |
| --- | --- | --- | --- |
| `app` production code | Present. | Present. | Present, typically in `BOOT-INF/classes`. |
| Internal `core` library code | Present if `app` declares `core` dependency properly. | Present. | Present, typically in `BOOT-INF/lib/core-...jar`. |
| Commons Lang, dependency `core` uses in method body | Maven `compile` transitively; Gradle `implementation` in `core` may stay **hidden** from `app` compile classpath. | Present in `app`'s appropriate runtime test graph. | Must be present in `app`'s runtime transitive dependency graph. |
| Spring MVC, Jackson, embedded web server | Per starters and scopes. | Present so test context starts. | Present as corresponding runtime JARs. |
| `src/test/java` + JUnit + MockMvc test-only libs | Not part of main output. | Present. | **Absent** under normal packaging. |
| Build plugins: Maven/Gradle plugin implementation | Runs at configure/build time. | Runs per build lifecycle. | Not automatically Spring application runtime dependencies. |

**Subtle difference:** in Maven, transitive `compile` scope exposes implementation dependencies to consumers at compile time. In Gradle `java-library`, `implementation` **hides them from the consumer compile classpath** while **still propagating them to runtime**. Both achieve the **same goal of a complete runtime**, despite different compile surfaces. Do not port Maven builds to Gradle by mechanically turning every `compile` into `api`.

### 9.2. Maven `provided` and Boot Repackage

When a module directly uses `provided`, Maven transitivity and packaging selection vary across layers. The Spring Boot Maven Plugin has special rules to include direct `provided` dependencies in executable archives; however, `app` **cannot** package a library missing from the graph due to non-transitive `optional`/exclusions. Safe workflow:

1. Inspect `mvn dependency:tree` of **`app`**.
2. Verify each dependency's scope and path into the graph.
3. Run `jar tf app.jar` to confirm archive contents.
4. Exercise the code path needing the library after launching `java -jar`.

### 9.3. Proper Scope for Version-Management Dependencies

The Spring Boot BOM manages versions for many Spring and third-party libraries; it **does not automatically add `core` to `app`**. Nor does Maven root `dependencyManagement` add a project dependency. Gradle plugins, dependency management, or version catalogs do not create `implementation project(':core')` automatically either. The decisive lines remain:

~~~xml
<dependency>
    <groupId>com.example</groupId>
    <artifactId>core</artifactId>
    <version>${project.version}</version>
</dependency>
~~~

and:

~~~groovy
dependencies {
    implementation project(':core')
}
~~~

If Maven parent and `app` both inherit dependency management yet `app` forgets to declare `core`, the compiler will report missing packages (unless another dependency accidentally pulls `core` in). That is a **dependency declaration** error, not a `repackage` bug.

## 10. Maven Verification: Module Order, Dependency Tree, Archive, and Runtime

### 10.1. Step 1 — Check Reactor and Build

~~~bash
./mvnw -version
./mvnw -pl app -am clean verify
~~~

**Expectations:**

- Reactor includes the root aggregator, `core`, and `app`.
- Builds `core` before `app` per dependency, producing `core/target/core-1.0.0-SNAPSHOT.jar` as a plain library JAR.
- `app` compiles cleanly when importing `com.example.core.GreetingComposer`.
- `app`'s JUnit/MockMvc test `applicationUsesCoreAndTransitiveLibrary` is discovered and passes.
- `app`'s Boot plugin builds the executable `app/target/app-1.0.0-SNAPSHOT.jar`.
- `app` test reports usually appear under `app/target/surefire-reports/`. Do not look only at `BUILD SUCCESS`; verify how many tests actually ran.

**Do not run `mvn -pl app -am spring-boot:repackage` directly across the reactor** if libraries are not configured for it. The `repackage` goal expects an already-built JAR/WAR from `package`; root `pom`/core library do not share that purpose. Running `clean verify` with the plugin declared only in `app` is cleaner.

### 10.2. Step 2 — Inspect `app`'s Dependency Graph

~~~bash
./mvnw -pl app -am dependency:tree
~~~

Look for these entries in the real output (exact formatting/order depends on Maven Dependency Plugin):

~~~text
com.example:app:jar:1.0.0-SNAPSHOT
+- com.example:core:jar:1.0.0-SNAPSHOT:compile
|  \- org.apache.commons:commons-lang3:jar:<resolved-version>:compile
\- org.springframework.boot:spring-boot-starter-web:jar:<resolved-version>:compile
   \- ... other dependencies ...
~~~

The snippet above is an **illustrative pattern**, not a guaranteed literal output. Dependency mediation can alter versions, and Maven may list transitive dependencies in a different order. Check for both direct `core` and descendant `commons-lang3`; if `core` appears without Commons, investigate `optional`, scope, exclusions, or dependency metadata.

To filter by group/artifact when supported by the plugin version:

~~~bash
./mvnw -pl app -am dependency:tree -Dincludes=com.example:core,org.apache.commons:commons-lang3
~~~

When passing `-Dincludes` through a shell, match the formatting expected by your project's Maven Dependency Plugin; if a filter errors or yields an empty tree, run `dependency:tree` unfiltered first to inspect the graph.

### 10.3. Step 3 — Inspect the Plain `core` JAR First

~~~bash
jar tf core/target/core-1.0.0-SNAPSHOT.jar
~~~

**Expect `com/example/core/GreetingComposer.class`** right at the root package path. Do not expect `BOOT-INF/classes` or the Boot Loader in `core`; if present, Boot repackaging was misapplied to the library module.

### 10.4. Step 4 — Inspect the Executable `app` JAR

~~~bash
jar tf app/target/app-1.0.0-SNAPSHOT.jar
~~~

Expect entries like:

~~~text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/com/example/app/MultiModuleApplication.class
BOOT-INF/lib/core-1.0.0-SNAPSHOT.jar
BOOT-INF/lib/commons-lang3-<resolved-version>.jar
BOOT-INF/lib/spring-boot-<resolved-version>.jar
BOOT-INF/lib/spring-webmvc-<resolved-version>.jar
...
~~~

Exact version numbers and starter/dependency sets must be read from the **real JAR**, without treating angle-bracket placeholders as literal filenames. On other Boot versions, loader packages/classnames may differ; check the archive's manifest.

**Note:** `jar tf app.jar` lists the nested `core.jar` as a single entry; it **does not** automatically list `GreetingComposer.class` inside nested `core.jar`. To inspect its contents, list `core/target/core-...jar` separately or extract the nested JAR and run `jar tf` on it.

### 10.5. Step 5 — Run the Exact Executable JAR

~~~bash
java -jar app/target/app-1.0.0-SNAPSHOT.jar --server.port=18085
~~~

In another terminal, once the app is ready:

~~~bash
curl -i http://localhost:18085/ping
~~~

**Expectation:** HTTP status **200**, exact body **`hello From core`**. The execution path ran app → core → Commons Lang on the **classpath assembled by the Boot Loader from the artifact**.

Stop the instance with Ctrl+C and verify the process exits. If another app is already running on 8080 from an earlier command, do not mistake it for 18085. For Batch/CLI apps without an HTTP server, check exit codes/job results/side effects instead of `curl`.

## 11. Gradle Verification: Project Variants, `runtimeClasspath`, and `BootJar`

### 11.1. Inspect Modules and Tasks

~~~bash
./gradlew --version
./gradlew projects
./gradlew :core:tasks --all
./gradlew :app:tasks --all
~~~

**Expectations:** subprojects `:core` and `:app` exist; `core` has `jar`, while `app` has `bootJar`/`bootRun`. If `:core:bootJar` exists too, check why the Boot plugin was applied to `core`; this simple library needs no executable archive.

### 11.2. Run Build and Tests

~~~bash
./gradlew :core:clean :app:clean :app:build
~~~

Gradle runs the producer tasks required by `app` via project dependency `:core`. You do not need to call `:core:jar` manually beforehand if the task graph is complete. Expect reports under `app/build/reports/tests/test/` (or `app/build/test-results/test/`) showing `applicationUsesCoreAndTransitiveLibrary` passed.

Do not mistake `UP-TO-DATE` or `FROM-CACHE` for "tests never ran": inspect reports and task inputs/cache provenance per CI workflow; for targeted debugging, run `--rerun-tasks` deliberately rather than enabling it on every build.

### 11.3. Inspect the Runtime Graph

~~~bash
./gradlew :app:dependencies --configuration runtimeClasspath

# To inspect Commons Lang specifically and why its version was chosen:
./gradlew :app:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3

# Distinguish app's compileClasspath if needed:
./gradlew :app:dependencies --configuration compileClasspath
~~~

In `runtimeClasspath`, look for project dependency `project :core` and descendant Commons Lang. In `app`'s `compileClasspath`, `commons-lang3` may **not** be exposed via `core` because `core` uses `implementation` rather than `api`. That is **correct** Java Library plugin behavior and does not mean Commons Lang is missing at runtime.

**When reading `dependencyInsight`:** check the requested version, selected version, and reason from constraints/conflict resolution. Do not assume the archive must contain `3.14.0` simply because `core/build.gradle` requested that version.

### 11.4. Check Nested JARs in the App Artifact

~~~bash
./gradlew :app:bootJar
jar tf app/build/libs/app-1.0.0-SNAPSHOT.jar
jar tf core/build/libs/core-1.0.0-SNAPSHOT.jar
~~~

Expectations:

- Plain core JAR: class at `com/example/core/GreetingComposer.class`.
- Boot app JAR: app classes in `BOOT-INF/classes/...`, `core-1.0.0-SNAPSHOT.jar` and Commons Lang JAR in `BOOT-INF/lib/...`.
- JUnit test classes and `starter-test` are excluded from the app runtime archive under standard config.
- If Gradle also creates `app-1.0.0-SNAPSHOT-plain.jar`, **do not deploy the plain archive by mistake**.

With the Java + Boot Gradle Plugin, `app/build/libs/app-1.0.0-SNAPSHOT.jar` is the typical executable JAR filename; if a project customizes `archiveFileName`/`classifier`, substitute the **actual file produced by `bootJar`**.

### 11.5. Run the Exact Gradle Binary

~~~bash
java -jar app/build/libs/app-1.0.0-SNAPSHOT.jar --server.port=18085
~~~

In another terminal:

~~~bash
curl -i http://localhost:18085/ping
~~~

Expect HTTP **200** and body **`hello From core`**. If MockMvc tests pass while `java -jar` hits classloading errors, compare `testRuntimeClasspath` with `bootJar`/`runtimeClasspath` and list `BOOT-INF/lib`; that exposes missing dependencies masked by test configurations.

## 12. Write Automated Archive Assertions Instead of Eyeballing

A reusable check verifies that **both key runtime JARs actually exist inside the app archive**, with no leaked test classes or plain-archive mix-up. The Bash snippet below takes the executable JAR path as an argument, using JDK `jar`, Bash, and `grep`.

~~~bash
#!/usr/bin/env bash
set -euo pipefail

ARCHIVE="${1:?Usage: check-boot-jar.sh <executable-app.jar>}"
ENTRIES="$(jar tf "$ARCHIVE")"

# App main class exists in BOOT-INF/classes
grep -q '^BOOT-INF/classes/com/example/app/MultiModuleApplication.class$' <<< "$ENTRIES"

# Internal core JAR exists as a nested library
grep -q '^BOOT-INF/lib/core-1\.0\.0-SNAPSHOT\.jar$' <<< "$ENTRIES"

# Commons Lang transitive JAR exists; version is not hardcoded
grep -Eq '^BOOT-INF/lib/commons-lang3-[^/]+\.jar$' <<< "$ENTRIES"

# Test classes must not belong in the executable artifact
if grep -q 'MultiModuleApplicationTest.class' <<< "$ENTRIES"; then
    echo "FAIL: test class leaked into runtime archive" >&2
    exit 1
fi

echo "PASS: application, internal module and transitive dependency packaged"
~~~

**Technical note:** before running in real Bash, ensure `${1:?...}`/`$(...)`/`$ARCHIVE`/`$ENTRIES` use standard shell `$` syntax — this final Markdown file already uses the proper `$` characters. This snippet only checks a few entries; it does not replace vulnerability scanning, runtime tests, license verification, or SBOMs.

**How to invoke:**

~~~bash
# Maven artifact
bash check-boot-jar.sh app/target/app-1.0.0-SNAPSHOT.jar

# Gradle artifact
bash check-boot-jar.sh app/build/libs/app-1.0.0-SNAPSHOT.jar
~~~

**Expected stdout when the script passes:**

~~~text
PASS: application, internal module and transitive dependency packaged
~~~

If an entry is missing, one of the `grep` checks fails and Bash exits non-zero before printing PASS. For other archive paths or core versions, update the assertions to match your actual artifacts. This is a demo verification script, not a universal scanner for every project.

**Why use a here-string `<<< "$ENTRIES"` instead of `jar tf ... | grep -q`?** Under `set -o pipefail`, a consumer closing early can trigger SIGPIPE on the producer for large archives. Here, the archive listing is captured first and then checked in the shell. For huge artifacts or strict CI policies, replace it with a unit test using Java's ZIP API for clear failure messages without buffering the full listing in memory.

### 12.1. Extracting a Nested `core` JAR for Inspection When Needed

To confirm `core`'s class sits inside the nested library of **the app JAR itself**, use `unzip -p` in a dedicated inspection directory:

~~~bash
# Example run from the Maven project root, only if unzip is available
mkdir -p jar-inspect
unzip -p app/target/app-1.0.0-SNAPSHOT.jar \
  BOOT-INF/lib/core-1.0.0-SNAPSHOT.jar > jar-inspect/core-from-app.jar

jar tf jar-inspect/core-from-app.jar
~~~

Expect `com/example/core/GreetingComposer.class`, with no `BOOT-INF/classes` inside the nested core library JAR. That `jar tf outer.jar` does not list nested classes is normal; open the inner JAR whenever inspection is needed.

### 12.2. Deliberate Negative-Path Experiment

On a **dedicated learning branch**, try changing `core`'s Commons Lang dependency to `compileOnly` in Gradle `core` (or Maven `optional`/exclusion on `app → core`), build, and observe:

1. Does `app`'s dependency graph still include Commons Lang?
2. Does `BOOT-INF/lib` still contain that JAR?
3. Does the app test / `java -jar` fail at compile time, startup, or when hitting `GET /ping`?
4. Why does class loading fail only when the actual code path invokes `StringUtils`?

Then restore the proper `implementation`/`compile` scope, clean build, and re-verify. **Never deploy an artifact intentionally missing dependencies.** Only run negative experiments in authorized environments.

## 13. Common Pitfalls in Multi-Module Projects

| Symptom | Typical Root Cause | Verification & Fix |
| --- | --- | --- |
| Maven app fails to resolve `com.example:core`. | Built child standalone before `core` installed in local repo; groupId/version mismatch with reactor. | Run from root with `-pl app -am`, check GAV and parent/module paths. |
| Maven reactor does not build `core` before `app`. | `app` lacks `core` dependency declaration, having `core` only in `<modules>`. | Add explicit `<dependency>` and check reactor build order. |
| Maven `-am spring-boot:run` tries to run on `core`. | Invoked goal directly on all selected modules instead of only `app`. | Build/install dependencies via reactor, then run `-pl app spring-boot:run`. |
| `java -jar` throws `ClassNotFoundException: com.example.core.GreetingComposer`. | Executable app JAR lacks `core` JAR or `core` was packaged wrongly. | Inspect `BOOT-INF/lib/core-...jar` and extract nested JAR. |
| `NoClassDefFoundError: org/apache/commons/lang3/StringUtils`. | Commons Lang excluded/optional/provided/compileOnly or packaging omitted runtime deps. | Compare app runtime graph and `BOOT-INF/lib`; restore proper scope. |
| `core` has `BOOT-INF/classes` instead of classes at root package path. | Library was Boot-repackaged. | Apply Boot plugin only in `app`; keep `core` plain JAR; rebuild from source. |
| Gradle `app` compile cannot import Commons Lang directly. | `core` uses `implementation` and hides Commons from `app`'s `compileClasspath`. | If `app` genuinely calls Commons directly, add a direct dependency in `app`; or use `api` in `core` **only if the type is in the public API**. |
| Gradle `core` uses `compileOnly` and `app` lacks Commons at runtime. | Compile-only does not propagate to app runtime. | Use `implementation` if `core` invokes the dependency at runtime. |
| App tests pass yet executable JAR fails. | Test classpath is broader than packaged runtime classpath. | Compare `testRuntimeClasspath`/`runtimeClasspath` and archive listing; run real binary smoke test. |
| App uses Boot plugin yet archive lacks starter dependencies. | Runtime configuration/exclusions/BOM or `bootJar` classpath customized wrongly. | Check `dependencyInsight`/`dependency:tree` and `bootJar`/`repackage` config. |
| Maven `core` dependency version is stale compared to edited source. | Stale SNAPSHOT in local repo when building child outside reactor. | Use root reactor build; check GAV and artifact timestamps/hashes if needed. |
| Gradle `Project with path ':core' could not be found`. | `settings.gradle` missing `include('core')` or mismatched project path. | Fix `include`/path; run `./gradlew projects`. |
| Gradle `:core:bootJar` asks for `mainClass`. | Boot plugin applied to library. | Remove Boot from `core`; keep `java-library`/`jar`. |
| App contains two versions of a dependency. | Graph BOM/constraints/dependency conflict/exclusions. | Use `dependencyInsight` or Maven tree to align versions; never delete nested JARs manually. |
| Deployed `app-...-plain.jar` by mistake. | Gradle produces plain and Boot JARs with different classifiers. | Confirm `bootJar` task, manifest, `BOOT-INF`, and run the right artifact. |
| Setting `mainClass` did not solve missing `core`. | `mainClass` selects only the entry point and adds no dependencies. | Declare `app → core` and inspect the runtime graph. |
| Have BOM/version catalog yet `core` JAR is missing. | BOM/catalog manages metadata/version notation only. | Add an actual dependency, not just version management. |
| App fails only under a specific profile/batch job. | Dependency loaded lazily along that code path, missed by smoke test. | Test profiles/jobs using that module; audit optional/conditional dependencies. |
| Archive contains `junit-jupiter` or test classes. | Test dependencies/source sets leaked into production. | Fix scope/configuration and package inputs; add negative entry assertions. |
| Maven plugin applied to all modules, breaking `core` consumption. | Parent `<build><plugins>` enforces `repackage` and overwrites library artifact. | Use `pluginManagement` or declare Boot plugin only in `app`; separate classifiers if an executable variant is truly needed. |

### 13.1. Four-Layer Diagnostic Workflow

**Layer 1 — Module membership:** Do `core` and `app` genuinely belong to the same reactor or Gradle multi-project build? Is the `app → core` relation declared?

**Layer 2 — Dependency resolution:** Does `app`'s runtime graph include `core` and Commons Lang? Did exclusions, `optional`, `provided`, `compileOnly`, version mediation, or constraints alter expectations?

**Layer 3 — Packaging:** Does the plain `core` JAR have classes properly? Does the Boot app JAR have `BOOT-INF/lib/core-*.jar` and Commons Lang JAR? Did `*-plain.jar` or a repackaged library slip in?

**Layer 4 — Runtime behavior:** Does `java -jar` start up and does `GET /ping` genuinely flow app → core → Commons Lang and return `hello From core`? If the app has no HTTP server, is there an equivalent job-flow check?

Never blindly add every library directly to `app` as a "quick fix" without understanding metadata/scopes; that masks flawed API contracts in `core` and duplicates dependencies across consumers.

## 14. Versioning, Snapshots, and Reproducibility

### 14.1. Why Can the Packaged App Pick a Different Version Than `core` Compiled Against?

Suppose `core` requests Commons Lang `3.14.0`, yet `app` has a Spring Boot BOM or another dependency constraint/path. In Maven, dependency management/mediation may select a different version for the consumer; Gradle applies conflict resolution/constraints. Hence:

- **`core/build.gradle`/`core/pom.xml`** reflects the producer's request.
- **App dependency reports** show the version selected for the consumer.
- **`BOOT-INF/lib`** shows the library artifact **actually** distributed.

Do not conclude a JAR is missing or mis-selected merely because its filename differs from a hardcoded version in docs. What matters is **matching group:artifact, compatible version, proper scope/variant, and passing behavioral tests**.

### 14.2. SNAPSHOTs and Maven Local Cache

`core` `1.0.0-SNAPSHOT` may sit in the local cache from an older source revision. Running `app` as a single module without rebuilding `core` risks pulling a **stale binary**. For reproducibility:

1. Prefer building/testing `app` and `core` in **one reactor**: `./mvnw -pl app -am clean verify`.
2. Only `install`/`publish` when workflows require standalone module runs or external repos need the artifact.
3. Record commit, version, Maven settings/repositories, and artifact hashes when releasing.
4. Use clean CI workspaces or strict cache isolation policies to avoid pulling SNAPSHOTs from the wrong commit.

### 14.3. Gradle Project Dependencies vs Published Artifacts

`implementation project(':core')` uses **project outputs/variants in the same build**, so Gradle knows which producer to build. Replacing it with:

~~~groovy
dependencies {
    implementation 'com.example:core:1.0.0-SNAPSHOT'
}
~~~

creates an **external module dependency by coordinates**, requiring a repository with published artifacts and metadata. When migrating from a project dependency to a published dependency, verify that `core`'s Gradle module metadata/POM scopes preserve `api`/`implementation` and transitive dependencies.

### 14.4. Layered JARs and Internal Modules

Spring Boot executable JARs can include `BOOT-INF/layers.idx` for layer extraction/container image builds. The Maven Boot Plugin can recognize **local module dependencies of the current build** and place them into the application layer, whereas a module resolved solely from the local Maven cache as an external binary may be categorized differently. This is a **container layer cache optimization**, not what determines whether `core`/Commons exist at runtime.

Therefore, do not tweak layer indices to fix `NoClassDefFoundError`. Ensure the dependency graph and archive contents are right first; layer tuning comes afterward.

### 14.5. Do Not Equate Dependency Completeness with Supply-Chain Safety

An executable JAR needs its runtime libraries to run, yet you also need:

- Version management and vulnerability advisory tracking per policy.
- Dependency verification/checksums/lockfiles where reproducibility is required.
- License notices/SBOMs and provenance for internal artifacts.
- Scanning to ensure no secrets, test-only tooling, or devtools leak into production JARs.
- Testing across profiles/code paths that use optional or reflection-based dependencies.

This lesson focuses on **deliberately bundling complete runtime dependencies**, not dumping "every JAR on the machine" into deliverables.

## 15. Hands-On Labs and Acceptance Criteria

### Lab A — Maven Reactor

1. Create root `pom.xml`, `core/pom.xml`, `app/pom.xml`, and the three Java files exactly as shown in sections 4–5.
2. Using the project's Maven Wrapper, run `./mvnw -version`.
3. Run `./mvnw -pl app -am clean verify`.
4. Read `app/target/surefire-reports` and confirm `applicationUsesCoreAndTransitiveLibrary` ran.
5. Inspect `core/target/core-1.0.0-SNAPSHOT.jar`: `core` classes must sit at the root package path.
6. Inspect `app/target/app-1.0.0-SNAPSHOT.jar`: `app` classes sit in `BOOT-INF/classes`, while `core` and Commons JARs sit in `BOOT-INF/lib`.
7. Run `./mvnw -pl app -am dependency:tree` and trace the path `app → core → commons-lang3`.
8. Run `java -jar app/target/app-1.0.0-SNAPSHOT.jar --server.port=18085` and `curl -i http://localhost:18085/ping`.
9. Pass when HTTP status is **200**, body is **hello From core**, test reports pass, and archive layout is valid.

### Lab B — Gradle Multi-Project

1. Use root `settings.gradle`, root `build.gradle`, `core/build.gradle`, and `app/build.gradle` from section 7.
2. Run `./gradlew projects` to confirm both subprojects.
3. Run `./gradlew :core:clean :app:clean :app:build` and inspect `app`'s JUnit report.
4. Run `./gradlew :app:dependencies --configuration runtimeClasspath` and `:app:dependencyInsight --configuration runtimeClasspath --dependency commons-lang3`.
5. Compare `compileClasspath` with `runtimeClasspath` to explain why `core`'s `implementation` **still reaches runtime** without leaking onto `app`'s compile API.
6. Run `./gradlew :app:bootJar`, `jar tf app/build/libs/app-1.0.0-SNAPSHOT.jar`, and assert `core`/Commons inside `BOOT-INF/lib`.
7. Run `java -jar`/`curl` as in Lab A, verifying body **hello From core**.

### Lab C — Observing a Transitive Dependency When Removed

On a learning branch, make one deliberate change:

- Maven: set `optional=true` on `core`'s Commons Lang dependency or exclude Commons on `app → core`, then inspect the tree and app artifact. If `app` needs Commons Lang at runtime, fix the metadata/scope or declare an explicit dependency appropriately.
- Gradle: change `core`'s Commons Lang from `implementation` to `compileOnly`, then compare `app`'s `runtimeClasspath` and archive.
- Build and test runtime behavior, recording the **actual error** if one appears without assuming every error shares the exact same message across Gradle/Maven/JDK versions.
- Revert, rebuild cleanly, and verify complete artifacts again.

Never ship builds deliberately missing dependencies into production pipelines.

### Evaluation Checklist

- [ ] Distinguish root aggregator/parent, module dependency graph, and resolved runtime classpath.
- [ ] Know `<modules>`/`include(...)` do not automatically create `app → core`.
- [ ] Maven `app` declares `com.example:core` with a version matching the reactor.
- [ ] Gradle `app` uses `implementation project(':core')`.
- [ ] `core` builds a plain `jar`; `app` builds an executable `repackage`/`bootJar`.
- [ ] Explain app classes in `BOOT-INF/classes`, and internal/external libraries in `BOOT-INF/lib`.
- [ ] Know Commons Lang is pulled in via `core` even though `app` does not declare it directly.
- [ ] Distinguish Maven `compile`, `provided`, `test`, `optional`, and transitive exclusions.
- [ ] Distinguish Gradle `api`/`implementation`/`runtimeOnly`/`compileOnly`/`testImplementation`.
- [ ] Know Maven reactor `-pl app -am` differs from running `app` alone when local SNAPSHOTs do not exist.
- [ ] Know Gradle project dependencies wire build tasks automatically without requiring `publishToMavenLocal`.
- [ ] Use dependency reports to identify selected versions and actual dependency paths.
- [ ] Use `jar tf` to inspect both the `core` JAR and the executable `app` JAR; never deploy the plain JAR by mistake.
- [ ] App tests exercise `core` and Commons Lang, not startup alone.
- [ ] Have test reports and a real `java -jar` HTTP smoke test.
- [ ] Can diagnose missing `core`, missing Commons Lang, or stale SNAPSHOTs.
- [ ] Never patch archives by manually inserting/deleting JARs instead of fixing dependency configuration.
- [ ] Maintain version/lock/security/SBOM policies matching release requirements.

**Completion criterion:** demonstrate a real **multi-module build** showing `app → core → commons-lang3` in the resolved graph, `core.jar` as a plain library, the executable app JAR containing **both `core` and Commons Lang nested JARs**, and `/ping` returning `hello From core` when running the app archive itself. If any test or external package step was not executed, state clearly what remains unverified rather than treating `BUILD SUCCESS` as a guarantee for every runtime path.

## Official References

- [Spring Boot 3.3 Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot — Executable JAR Format / Nested JARs](https://docs.spring.io/spring-boot/specification/executable-jar/nested-jars.html)
- [Apache Maven — Guide to Working with Multiple Modules](https://maven.apache.org/guides/mini/guide-multiple-modules.html)
- [Apache Maven — Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Gradle — Multi-Project Builds](https://docs.gradle.org/current/userguide/multi_project_builds.html)
- [Gradle — Java Library Plugin, API vs Implementation](https://docs.gradle.org/current/userguide/java_library_plugin.html)
- [Gradle — Dependency Management for JVM Projects](https://docs.gradle.org/current/userguide/dependency_management_for_java_projects.html)

**Remember:** an internal module can pull in one or more external libraries that `app` never declares directly. For reliable runtime execution, let **dependency metadata + scopes/configurations + reactor/project variants + Spring Boot packaging** assemble the runtime classpath, and then **verify against the actual executable archive**, instead of manually collecting JARs or trusting test classpaths alone.