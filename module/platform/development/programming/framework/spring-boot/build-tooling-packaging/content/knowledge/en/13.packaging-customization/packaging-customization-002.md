# Adding or Excluding Libraries in repackage and bootJar Configurations

## 1. Goal and context

A Spring Boot application built with Maven or Gradle can be packaged into an **executable JAR** containing application code and the libraries needed to run via `java -jar`. When adding a JDBC driver, JSON module, or development-only library, you must decide **which artifacts actually belong in the release JAR**, rather than merely making source code compile.

Two central mechanisms:

- **Maven**: the `spring-boot:repackage` goal of `spring-boot-maven-plugin` takes the JAR/WAR produced by the lifecycle and repackages it with the launcher and appropriate dependencies.
- **Gradle**: the `bootJar` task of the `org.springframework.boot` Gradle plugin builds the executable JAR; the packaged library set depends on the **task's classpath**.

After this lesson, you will be able to:

1. Distinguish **declared** dependencies, dependencies **resolved on a classpath**, and dependencies **actually present in the executable JAR**.
2. Add libraries with the proper scope in Maven/Gradle, avoiding confusing `test` or `compileOnly` with runtime libraries.
3. Exclude an artifact from Maven `repackage` using `<excludes>`, and understand `<excludeGroupIds>` and how it differs from dependency-level exclusions.
4. Adjust the packaged library set of Gradle `bootJar`, knowing when to use `runtimeOnly`, `developmentOnly`, dependency exclusions, or task-specific classpaths.
5. Inspect `BOOT-INF/lib/` inside the artifact, run smoke tests, read the dependency tree, and recognize runtime failures after library removal.
6. Keep local and CI builds consistent, avoiding releasing artifacts missing dependencies or shipping development libraries/secrets to production.

**Running example:** Spring Boot `3.3.5`, Java `17`, an application using only `spring-boot-starter` and `com.h2database:h2` to **illustrate the presence or absence of a runtime JAR**. Here H2 is *not used as a real database*, opens no connections, and needs no JDBC starter. The Spring Boot version is purely illustrative; use your real project version and its Maven/Gradle/JDK support matrix.

## 2. Executable JAR structure and three decision layers

A typical Spring Boot executable JAR looks like:

~~~text
packaging-demo-0.0.1-SNAPSHOT.jar
├── META-INF/MANIFEST.MF
├── org/springframework/boot/loader/...  (Spring Boot launcher)
└── BOOT-INF/
    ├── classes/                          (application classes and resources)
    │   └── com/example/packaging/PackagingDemoApplication.class
    └── lib/                              (packaged dependency JARs)
        ├── spring-boot-*.jar
        ├── spring-core-*.jar
        ├── ...
        └── h2-*.jar                      (only when included)
~~~

In a standard JAR layout, `Main-Class` in the manifest points to the **Spring Boot launcher**, while `Start-Class` points to the application main class. The launcher loads nested JARs under `BOOT-INF/lib`; manually copying a library into `BOOT-INF/classes` or altering `Main-Class` is generally not the right way to manage the classpath.

**Three completely distinct steps:**

| Layer | Maven | Gradle | Question to answer |
| --- | --- | --- | --- |
| **Declaration** | `<dependencies>`, `<scope>` | `dependencies { implementation / runtimeOnly / ... }` | Which artifacts does the project request? |
| **Resolution** | Maven dependency mediation, scopes, BOM/dependencyManagement | Configurations, constraints, BOM, dependency resolution | Which versions actually end up on which classpath? |
| **Packaging** | Spring Boot `repackage` with `includes/excludes` | `bootJar` with task `classpath` and `developmentOnly` rules | Which JAR files actually land in the executable archive? |

Do not infer "the dependency tree has module X" means "the release JAR definitely has X." Packaging configuration can exclude that module. Conversely, not seeing a module referenced directly in source code **does not mean** it is unused: runtime may rely on SPI, reflection, logging providers, drivers, or auto-configuration.

### Distinguishing executable JAR, plain JAR, and WAR

- **Maven**: `package` builds the source JAR; `repackage` creates the executable archive, and the original JAR is typically preserved as `.original`. Do not inspect `.original` to check `BOOT-INF/lib`.
- **Gradle**: `bootJar` builds the executable archive; the `jar` task may produce `-plain.jar`. A plain JAR normally does not contain the Spring Boot loader or full nested dependencies.
- **WAR**: an executable WAR uses `WEB-INF/classes`, `WEB-INF/lib`, and possibly `WEB-INF/lib-provided`. Rules for external servlet containers differ from executable JARs; this lesson focuses on **JAR**.

Additionally, `layers.idx` and `classpath.idx` (if present) provide metadata supporting layering and launching, and **do not replace** actual library selection.

## 3. Choose the scope/configuration before thinking about `exclude`

### Maven

| Scope | During the build | For Spring Boot JAR `repackage` |
| --- | --- | --- |
| `compile` (default) | Needed at compile and runtime | Normally included unless filtered out |
| `runtime` | Not needed at compile time; needed at runtime | Normally included |
| `test` | Serves test compilation/execution | Not part of normal runtime archive |
| `provided` | Present at compile time; expected from external runtime environment | **Spring Boot `repackage` can still include `provided`**, unlike naive deductions from standard Maven scopes; consult your exact version's docs |
| `system` | Depends on a user-specified local file | `includeSystemScope=false` by default in Spring Boot Maven plugin; avoid for reproducible builds |
| `optional` | Controls dependency propagation to consumers | Should not be treated as a "remove from Boot JAR" switch; packaging behavior depends on plugin/version—inspect the artifact |

**Be careful with `provided`:** in the 3.3 branch, Spring Boot Maven plugin `repackage` and `run` include certain `provided` dependencies by rule. Do not write down "`provided` = guaranteed absent from executable JAR." Rules for **WARs and external containers** differ and must be designed around the actual deployment model.

### Gradle

| Configuration | Role | Normally in `bootJar`? |
| --- | --- | --- |
| `implementation` | Used at compile and runtime | Yes, via runtime classpath |
| `runtimeOnly` | Used at runtime, not compile time | Yes, suited for JDBC drivers loaded via reflection/SPI |
| `compileOnly` | Needed only at compile time | Not part of normal runtime classpath |
| `testImplementation` / `testRuntimeOnly` | Tests only | Not part of application runtime JAR |
| `developmentOnly` (Spring Boot plugin) | Development-only tools, e.g. Devtools | **Excluded from executable JAR/WAR by default** |

This table describes default behavior in the Spring Boot Gradle plugin for Java/JVM projects. Customizing `bootJar.classpath`, `runtimeClasspath`, or source sets can alter the outcome.

**Principles for choosing a solution:**

- Library needed for the app to run: add with `runtime` (Maven) or `runtimeOnly` (Gradle), or `compile`/`implementation` if Java code calls its API directly.
- Library used only in tests: `test` / `testImplementation`, rather than trying to exclude it at packaging time.
- Library used only during development: consider `spring-boot-devtools` with appropriate development config and Gradle `developmentOnly`.
- Library needed only in a special deploy configuration: use a dedicated tested artifact/build variant rather than creating hidden differences between local and production.

## 4. A Java example that can verify packaged libraries

We use **one complete Spring Boot class** to check for the presence of `org.h2.Driver` via reflection. Because the code does not import H2 classes directly, it compiles when H2 is declared in runtime scope and also runs when H2 is excluded from the archive. This is a **classpath observation test**, not a JDBC test.

Create **`src/main/java/com/example/packaging/PackagingDemoApplication.java`**:

~~~java
package com.example.packaging;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class PackagingDemoApplication {

    public static void main(String[] args) {
        System.out.println("PACKAGED_H2=" + h2Present());
        SpringApplication.run(PackagingDemoApplication.class, args);
    }

    private static boolean h2Present() {
        try {
            Class.forName("org.h2.Driver");
            return true;
        }
        catch (ClassNotFoundException ex) {
            return false;
        }
    }
}
~~~

**Explanation:**

1. `@SpringBootApplication` provides Boot configuration, and `main` is a valid Java entrypoint.
2. `Class.forName("org.h2.Driver")` looks up the class by name at **runtime**, so the H2 JAR is not needed at compile time.
3. If the class is present and loadable, the program prints `PACKAGED_H2=true`; when absent from the runtime classpath, it prints `PACKAGED_H2=false`.
4. Both cases then invoke `SpringApplication.run`; because there is no JDBC starter, the example creates no H2 connection.
5. In real environments, `ClassNotFoundException` can also stem from classloader issues; inspecting both the archive and runtime as in section 10 provides complete evidence.

**Expected marker line when H2 is in the executable archive:**

~~~text
PACKAGED_H2=true
~~~

**Expected marker line after excluding H2 and running the rebuilt JAR:**

~~~text
PACKAGED_H2=false
~~~

Spring Boot may print an additional banner and logs with changing timestamps/PIDs. Only the two specified marker lines are deterministic outputs of the probe code.

## 5. Maven: baseline with a runtime dependency included in the JAR

### 5.1. Complete POM for the exercise

**`pom.xml`** for a standalone Maven project with an appropriate Maven Wrapper set up in the repository:

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.5</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>packaging-demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter</artifactId>
        </dependency>

        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
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

Spring Boot Starter Parent manages dependency versions, including an H2 version compatible with the selected Boot BOM. **You do not need to pin the H2 version** in the example POM. If a real project only imports the Spring Boot BOM without inheriting the Parent, you must configure compiler/plugin executions appropriately: a BOM import does not bring in the Parent's plugin management and `repackage` execution automatically.

When inheriting `spring-boot-starter-parent`, you only need to declare the Spring Boot Maven plugin under `<plugins>` because the Parent already configures the `repackage` execution. Avoid accidentally declaring a second `repackage` execution that causes the goal to run twice.

### 5.2. Build and verify baseline

Linux/macOS (at project root):

~~~bash
./mvnw --version
./mvnw clean package
./mvnw dependency:tree -Dincludes=com.h2database:h2
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar | grep 'BOOT-INF/lib/h2-'
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Windows PowerShell:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd clean package
.\mvnw.cmd dependency:tree -Dincludes=com.h2database:h2
jar tf .\target\packaging-demo-0.0.1-SNAPSHOT.jar |
    Select-String 'BOOT-INF/lib/h2-'
java -jar .\target\packaging-demo-0.0.1-SNAPSHOT.jar
~~~

After `package`, Maven creates the executable JAR `target/packaging-demo-0.0.1-SNAPSHOT.jar`; the `.original` file (if present) is **not** the file to run. `jar tf` must show an entry of the form `BOOT-INF/lib/h2-<version>.jar`; the exact version is managed by the BOM and is not hardcoded in the expected output.

In the `java -jar` output, the expected marker is `PACKAGED_H2=true`. `dependency:tree` proves H2 was resolved for the Maven project, while `jar tf` proves H2 was **actually packaged**. These are two distinct measurements, and both should be kept when evaluating customizations.

## 6. Maven: exclude a single library from `repackage`

To exclude **only the H2 JAR** from the executable archive, keep the `com.h2database:h2` dependency in `<dependencies>` and replace the plugin declaration in `pom.xml` with:

~~~xml
<!-- Snippet inside <build><plugins> of the existing pom.xml -->
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <excludes>
            <exclude>
                <groupId>com.h2database</groupId>
                <artifactId>h2</artifactId>
            </exclude>
        </excludes>
    </configuration>
</plugin>
~~~

**This is a fragment replacing the previous plugin block, not a new POM.** In `spring-boot-maven-plugin`, `<excludes>` contains `<exclude>` elements identifying **modules by groupId + artifactId**, with an optional classifier if needed. This lets H2 remain in the dependency graph while omitting it from the Boot archive's JAR set.

Re-run `clean package`:

~~~bash
./mvnw clean package
./mvnw dependency:tree -Dincludes=com.h2database:h2
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar | grep 'BOOT-INF/lib/h2-' || echo 'H2 NOT PACKAGED'
java -jar target/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

In PowerShell:

~~~powershell
.\mvnw.cmd clean package
.\mvnw.cmd dependency:tree -Dincludes=com.h2database:h2
jar tf .\target\packaging-demo-0.0.1-SNAPSHOT.jar |
    Select-String 'BOOT-INF/lib/h2-'
java -jar .\target\packaging-demo-0.0.1-SNAPSHOT.jar
~~~

The expected result is that `dependency:tree` **still shows H2**, while `jar tf` **has no H2 entry** and `java -jar` prints `PACKAGED_H2=false`. In PowerShell, `Select-String` prints nothing when no match is found; do not treat that silence as proof if the preceding `jar` command failed. Always check exit codes or re-run `jar tf` separately when needed.

**Key takeaway:** `repackage.excludes` does not remove the H2 declaration from the POM, does not stop the compiler from seeing eligible dependencies, and does not alter the overall Maven resolution graph; it adjusts packaging and related Boot goals. In the Spring Boot Maven Plugin, exclude settings can also affect the `spring-boot:run` goal per plugin docs; do not assume `spring-boot:run` and `java -jar` always behave identically if build settings differ.

### `excludeGroupIds`: exclude an entire artifact group

The Spring Boot Maven plugin also supports:

~~~xml
<configuration>
    <excludeGroupIds>com.example.legacy,com.example.diagnostics</excludeGroupIds>
</configuration>
~~~

This is a **list of groupIds**, not artifactIds; it excludes every artifact matching those groupIds within the scope of `repackage`. **Use only after auditing the entire group.** A groupId like `org.springframework` or `com.fasterxml.jackson.core` includes core libraries; excluding an entire group carelessly will easily prevent the application from starting.

When you only need to exclude a single artifact, `<excludes>` is safer and easier to review than `<excludeGroupIds>`. If both are configured, inspect the effective plugin configuration to know the exact excluded set.

### `<includes>` does not automatically fetch a new library

The plugin provides `<includes>` to restrict/allowlist dependencies during packaging. **It is a filter over dependencies already resolved by the project**, not a replacement for `<dependency>` in the POM, and it cannot introduce coordinates absent from the dependency graph.

Syntax snippet example:

~~~xml
<configuration>
    <includes>
        <include>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
        </include>
    </includes>
</configuration>
~~~

**Do not apply this snippet to a normal sample app**: an allowlist containing only H2 can exclude other Boot starter dependencies needed to run. Use `includes` only when you explicitly want to control every eligible dependency, have listed all required ones, and run smoke tests on the final JAR. If your goal is to **add** a library, the standard way is adding `<dependency>` with the right scope.

## 7. Maven: do not confuse dependency exclusions with `repackage` exclusions

Two exclusions exist with different effects:

**Dependency level — prevent pulling in a transitive module:**

~~~xml
<!-- Example snippet: exclude a transitive artifact from this dependency branch -->
<dependency>
    <groupId>com.example</groupId>
    <artifactId>customer-client</artifactId>
    <version>1.2.0</version>
    <exclusions>
        <exclusion>
            <groupId>com.example</groupId>
            <artifactId>legacy-transport</artifactId>
        </exclusion>
    </exclusions>
</dependency>
~~~

The coordinates `com.example:customer-client:1.2.0` and `legacy-transport` are **syntax illustrations only**, not public libraries guaranteed to exist. Dependency-level `<exclusions>` adjust the **dependency graph of that branch**. If another dependency still pulls in the same module, it can appear via that other path.

**Spring Boot plugin level — filter packaged files:**

~~~xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <excludes>
            <exclude>
                <groupId>com.h2database</groupId>
                <artifactId>h2</artifactId>
            </exclude>
        </excludes>
    </configuration>
</plugin>
~~~

The plugin mechanism only controls which resolved artifacts `repackage` places in the executable JAR, without altering the project's dependency declarations. If you **no longer use a library in any configuration**, the cleanest fix is deleting the dependency declaration or excluding the transitive dependency on the proper branch, rather than keeping it in the dependency tree and silently hiding it from the archive.

### Maven options worth knowing

- `excludeDevtools`: Spring Boot Maven plugin excludes `spring-boot-devtools` from the executable archive by default.
- `excludeDockerCompose`: in supported versions, excludes `spring-boot-docker-compose` by default.
- `includeSystemScope`: defaults to `false`; avoid enabling it just to bundle a JAR sitting on a personal machine, as it hurts build reproducibility.
- `requiresUnpack`: used for libraries that must be unpacked to temporary files at runtime; **not** a way to add or remove dependencies.
- `includeTools`: controls jar tools used for layer operations in supported versions; **not** a switch to exclude arbitrary application libraries.
- `classifier`/ `attach`: controls the generated artifact and whether it is attached for install/deploy; **does not decide** which modules are excluded from the classpath.

Avoid enabling `includeSystemScope` to "fix" a `ClassNotFoundException` in production. A system JAR outside official repositories needs proper provenance, versioning, checksums, or internal publishing per policy.

## 8. Gradle: add a library via `runtimeOnly` and verify `bootJar`

**`settings.gradle`** (Groovy DSL):

~~~groovy
rootProject.name = 'packaging-demo'
~~~

Complete **`build.gradle`**, using the same Java class from section 4:

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.5'
    id 'io.spring.dependency-management' version '1.1.6'
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
    implementation 'org.springframework.boot:spring-boot-starter'
    runtimeOnly 'com.h2database:h2'
}

springBoot {
    mainClass = 'com.example.packaging.PackagingDemoApplication'
}
~~~

`runtimeOnly 'com.h2database:h2'` puts H2 on **`runtimeClasspath`**, not on the main `compileClasspath`. Because the code uses reflection, the project still compiles. `bootJar` packages main output and eligible runtime libraries by default, so H2 should appear in `BOOT-INF/lib/`.

**If the project uses `dependencyResolutionManagement` with `RepositoriesMode.FAIL_ON_PROJECT_REPOS` in settings, remove the `repositories` block from `build.gradle` and configure Maven Central/mirrors in settings.** Repository configuration is outside the library configuration scope of this lesson.

### Running Gradle on Linux/macOS

~~~bash
./gradlew --version
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency h2 --configuration runtimeClasspath
./gradlew clean bootJar
jar tf build/libs/packaging-demo-0.0.1-SNAPSHOT.jar | grep 'BOOT-INF/lib/h2-'
java -jar build/libs/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

### Running Gradle on Windows PowerShell

~~~powershell
.\gradlew.bat --version
.\gradlew.bat dependencies --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency h2 --configuration runtimeClasspath
.\gradlew.bat clean bootJar
jar tf .\build\libs\packaging-demo-0.0.1-SNAPSHOT.jar |
    Select-String 'BOOT-INF/lib/h2-'
java -jar .\build\libs\packaging-demo-0.0.1-SNAPSHOT.jar
~~~

**Expected result:** `runtimeClasspath` contains H2, `jar tf` finds `BOOT-INF/lib/h2-...`, and `java -jar` prints `PACKAGED_H2=true`.

If H2 is missing from the dependency graph, check whether `runtimeOnly` is in the right module or affected by excludes/constraints. If it is in the graph but absent from the archive, check `bootJar.classpath`, `developmentOnly`, or applied packaging filters. A module can exist in **`testRuntimeClasspath`** without existing in main's **`runtimeClasspath`**.

## 9. Gradle: exclude a single JAR from the `bootJar` task

Unlike Maven `repackage.excludes`, the Spring Boot Gradle plugin primarily relies on the **`bootJar` task's classpath**. If you want to omit H2 **only from the executable archive** while keeping `runtimeOnly` to test/verify the difference between build classpath and packaged classpath, you can filter files in `BootJar`'s classpath.

### Groovy DSL

**Add** the following block to `build.gradle` from section 8, without deleting `runtimeOnly 'com.h2database:h2'`:

~~~groovy
tasks.named('bootJar', org.springframework.boot.gradle.tasks.bundling.BootJar) {
    classpath = classpath.filter { file ->
        !(file.name ==~ /h2-[0-9].*\.jar/)
    }
}
~~~

This is a **JAR filename filter** example specifically for this exercise. Gradle `FileCollection.filter` produces a filtered file collection, while `BootJar.classpath` determines which nested libraries enter the archive. When reassigning `classpath`, keep other files/class directories intact; the snippet only drops files matching `h2-<version>.jar`.

**Important note on robustness:** filtering by filename is a task-level technique, not the most durable way to manage dependencies by group/module. If the H2 file is renamed or has a custom classifier, the regex may stop matching. In real projects, prefer deleting unused dependencies, using coordinate-based Gradle dependency exclusions when you truly want them out of the **runtime resolution graph**, or using a clearly tested packaging model. If archive-only filtering is unavoidable, add a `BOOT-INF/lib` check in CI.

### Kotlin DSL equivalent

**Add** to `build.gradle.kts` in a Kotlin DSL project (and remember to import `BootJar` at the top of the file):

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    classpath = classpath.filter { file ->
        !Regex("""h2-[0-9].*\.jar""").matches(file.name)
    }
}
~~~

In Kotlin DSL, the `import` belongs at the top of the file. `classpath.filter` preserves main output directories and other JARs. **Choose Groovy or Kotlin; do not mix both in the same file**.

**Do not use** `tasks.named("bootJar") { exclude("BOOT-INF/lib/h2-*.jar") }` as a default substitute: `exclude` on the archive copy specification has different semantics from removing a module from the dependency graph/classpath. It can produce unexpected outcomes because Spring Boot tasks add nested libraries through dedicated handling; control `BootJar.classpath` and inspect the archive instead.

### Verify after filtering

~~~bash
./gradlew clean bootJar
./gradlew dependencyInsight --dependency h2 --configuration runtimeClasspath
jar tf build/libs/packaging-demo-0.0.1-SNAPSHOT.jar | grep 'BOOT-INF/lib/h2-' || echo 'H2 NOT PACKAGED'
java -jar build/libs/packaging-demo-0.0.1-SNAPSHOT.jar
~~~

Result: `dependencyInsight` may **still see H2 in `runtimeClasspath`**, yet `BOOT-INF/lib` no longer has H2 and the app prints:

~~~text
PACKAGED_H2=false
~~~

This is an **intentionally divergent state** for demonstration. In production, if the application genuinely invokes the H2 driver, excluding H2 from `bootJar` causes database access to fail even if `bootRun` still works. **Do not equate a green test build with a functionally sound executable JAR.**

### Gradle: exclude at the dependency graph layer when more appropriate

If the application no longer needs H2 in any runtime, the cleanest approach is **removing** the `runtimeOnly 'com.h2database:h2'` declaration. If you only want to exclude a *transitive dependency* of another library, Gradle supports exclusions on the dependency declaration:

~~~groovy
dependencies {
    implementation('com.example:client-sdk:1.2.0') {
        exclude group: 'com.example', module: 'legacy-transport'
    }
}
~~~

This is **illustrative syntax**, not public artifact coordinates guaranteed to exist. An exclusion affects only that dependency edge; if another path still requires the artifact, it can still be selected. Check with `dependencyInsight` instead of assuming `exclude` always removes the module from the entire graph.

**Key difference to remember:** a Gradle dependency exclusion alters the resolution graph of the relevant classpath, potentially affecting `bootRun`/tests/other runtimes. A `bootJar.classpath` filter affects only the packaging task unless custom wiring exists. The two mechanisms **do not replace each other**.

## 10. Gradle: `developmentOnly` and options to add libraries at packaging time

The Spring Boot Gradle plugin creates `developmentOnly` for development dependencies, typically Devtools:

~~~groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
~~~

By default, dependencies declared in `developmentOnly` **are not placed inside the executable JAR/WAR**. This is the proper way to omit development tools **without writing manual filters** in `bootJar`.

If you intentionally want to include `developmentOnly` in a **special-purpose archive**, the plugin lets you add that classpath configuration to the task. Groovy DSL example:

~~~groovy
tasks.named('bootJar', org.springframework.boot.gradle.tasks.bundling.BootJar) {
    classpath configurations.developmentOnly
}
~~~

Kotlin DSL:

~~~kotlin
import org.springframework.boot.gradle.tasks.bundling.BootJar

tasks.named<BootJar>("bootJar") {
    classpath(configurations["developmentOnly"])
}
~~~

**Do not use this configuration for production just because "devtools is missing"**: Devtools is a development tool and normally should not be packaged. Here `classpath(...)` **appends** files to the task classpath; it differs from assigning `classpath = ...`, which **replaces** the classpath collection. If the project already customizes `bootJar.classpath`, preserve core libraries.

When you genuinely need to add an **archive-only library**, the task can also include JAR files from a custom configuration. However, that will not automatically update compile/test classpaths or dependency provenance; if new code calls the library, ensure compile and runtime designs stay consistent. **Prefer declaring `implementation` or `runtimeOnly` in the project** so IDE, tests, dependency graph, and CI can all observe the dependency.

### `requiresUnpack` solves a different problem

Some libraries cannot run while remaining nested inside a JAR. Spring Boot Gradle supports:

~~~groovy
tasks.named('bootJar', org.springframework.boot.gradle.tasks.bundling.BootJar) {
    requiresUnpack '**/jruby-complete-*.jar'
}
~~~

This configuration only marks a library to be **unpacked to a temporary file at application startup**; it is **not** a command to add a new module or exclude a dependency. If the library is not already on the task classpath, `requiresUnpack` will not make it appear.

## 11. Maven and Gradle: "add/exclude" comparison table by goal

| Goal | Maven | Gradle | Consequences to verify |
| --- | --- | --- | --- |
| Add a library needed at runtime | `<dependency><scope>runtime</scope></dependency>` | `runtimeOnly("group:module")` | Runtime classpath and nested JAR |
| Add a library needed at compile + runtime | `compile` or default scope | `implementation("group:module")` | Compile, runtime, and tests |
| Test library excluded from executable JAR | `test` | `testImplementation` | Present on testClasspath, absent from archive |
| Development-only library | Spring Boot plugin excludes Devtools; consider appropriate Maven scopes/optional | `developmentOnly` | Does not leak into release artifact |
| Exclude 1 module **at packaging only** | `spring-boot-maven-plugin` `<excludes>` | Adjust `BootJar.classpath` with verification | Dependency graph may still show the module |
| Exclude 1 transitive module from graph | `<exclusions>` on dependency | `exclude(group, module)` on dependency or controlled policy | Affects resolved classpath |
| Exclude an entire group during repackage | `<excludeGroupIds>` | No direct one-to-one option in `bootJar`; design via Gradle configurations/classpath | Risk of dropping an entire group of needed libraries |
| Include dev-only in a special archive | Requires explicit plugin config and security review | `bootJar { classpath(configurations.developmentOnly) }` | Normally unsuitable for production |
| Nested library requiring unpack | `<requiresUnpack>` | `requiresUnpack(...)` | Artifact is still packaged but unpacked at runtime |

Do not translate Maven `<excludes>` syntax directly into `bootJar { excludes ... }` without checking the Gradle API: each plugin has a **different configuration model**.

## 12. Reading the dependency graph to distinguish missing dependencies from missing JAR entries

### Maven: identify coordinates and dependency branches

~~~bash
./mvnw dependency:tree
./mvnw dependency:tree -Dincludes=com.h2database:h2
./mvnw help:effective-pom -Doutput=effective-pom.xml
~~~

`dependency:tree` reflects dependencies resolved and selected by Maven mediation rules. `effective-pom` shows the POM after merging parents, profiles, and plugin management; it is very useful when suspecting a profile or parent is unintentionally applying `repackage.excludes`.

**Do not edit `effective-pom.xml`** to change configuration: edit the source `pom.xml`. In a multi-module project, run commands in the actual packaging module; a library module has a different dependency graph from an app module.

### Gradle: inspect the right runtime configuration

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency h2 --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
~~~

`runtimeClasspath` is the main source set's classpath, whereas `testRuntimeClasspath` is for tests. `dependencyInsight` explains why a version or branch pulled the dependency in. If H2 remains in `runtimeClasspath` yet is filtered out of `BootJar.classpath`, these commands **cannot prove by themselves that H2 is inside the JAR**. You must combine them with archive inspection.

**On Gradle dependency locking:** a lockfile pins resolved versions for reproducibility, but **does not guarantee the file set in `bootJar`** if you have task-specific filters or a custom classpath. Version catalogs/BOMs likewise describe versions/constraints only and do not replace output inspection.

## 13. Inspecting the executable JAR with JDK tools, without relying on an IDE

### 13.1. List nested JARs

Maven:

~~~bash
jar tf target/packaging-demo-0.0.1-SNAPSHOT.jar | grep '^BOOT-INF/lib/'
~~~

Gradle:

~~~bash
jar tf build/libs/packaging-demo-0.0.1-SNAPSHOT.jar | grep '^BOOT-INF/lib/'
~~~

In PowerShell:

~~~powershell
jar tf .\target\packaging-demo-0.0.1-SNAPSHOT.jar |
    Select-String '^BOOT-INF/lib/'
~~~

For Gradle, replace the path with `.\build\libs\...`. If a specific version is required, listing JAR names alone does not prove BOM compliance: verify the actual resolved names and versions.

### 13.2. Inspect the manifest

A typical Spring Boot 3.3 executable JAR contains entries such as:

~~~text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: com.example.packaging.PackagingDemoApplication
~~~

`Main-Class` is the Spring Boot launcher, not the project's main class. `Start-Class` indicates the application main class. An archive with all libraries present can still fail to run if `Start-Class` is wrong; thus **checking the launcher and checking dependencies** are two separate steps.

### 13.3. Before/after comparison without mixing stale artifacts

1. Run **`clean package`** or **`clean bootJar`** in the right module.
2. Record the name and size of the JAR under inspection; if the directory contains multiple JARs, identify the executable file precisely instead of picking `-plain.jar` or `.original`.
3. List `BOOT-INF/lib/` and save before/after lists; when excluding only H2, **essential Spring Boot libraries must not disappear**.
4. Run `java -jar` on the newly built JAR. In the H2 example, verify the `PACKAGED_H2=true/false` marker.
5. Run smoke/integration tests exercising features that depend on the remaining libraries. A JAR may boot yet fail when hitting a branch that uses an excluded library.
6. Cross-check results in CI and supported runtime environments. Never treat "local `bootRun` still works" as proof that the release JAR contains the right libraries.

When verifying checksums to ensure the artifact matches the deployed/executed file, use `sha256sum` on Linux or `Get-FileHash` on Windows. Different checksums can have many causes (build timestamps, metadata, dependency sets); to prove **which library was excluded**, the nested JAR listing and dependency graph remain more direct evidence.

## 14. Risks and criteria for deciding whether to exclude a library

### 14.1. Unit test classpaths can be broader than the runtime artifact

A test may pass because a dependency is present in `testRuntimeClasspath`, Maven's test classpath, or when running `bootRun` locally. Yet the packaged executable JAR may lack a nested library, leading to:

- `ClassNotFoundException` / `NoClassDefFoundError` during class loading.
- `ServiceConfigurationError` when an SPI/provider is missing.
- `NoSuchMethodError` or linkage errors if an incompatible set of versions is accidentally packaged.
- JDBC connection failures or parser/driver errors in a rarely used feature, even though the app starts cleanly.
- Auto-configuration failures because a library vanished or a new dependency caused a condition to evaluate differently.

**Smoke tests must run against `java -jar` on the final artifact**, not only inside a test JVM with a full IDE/Gradle/Maven classpath.

### 14.2. Pick the exclusion method matching the root cause

If a dependency is **no longer used**: delete it from `dependencies`/POM first. If a dependency is pulled **transitively** and unneeded: apply an exclusion on the confirmed branch, then check for alternate dependency paths. If a dependency is merely unsuitable for the **artifact** while needed by other tools/test runtimes: use packaging-specific plugin/task configuration accompanied by tests.

Do not exclude `spring-boot-loader`, SLF4J providers, Spring Framework core, Jackson modules, JDBC drivers, or security libraries just to shrink the JAR if the application still needs them. Saving a few MB does not justify lost functionality and hard-to-diagnose production failures.

### 14.3. Security and provenance

Excluding a JAR from the executable archive can alter the SBOM and CVE exposure **of that artifact**, but it does not eliminate the vulnerability from the source tree, dependency graph, test tools, container base image, or other artifacts. If the dependency is still downloaded during the build, your organization may still need to govern it under policy.

Read advisories, assess packages actually present at runtime, and upgrade versions via the Spring Boot BOM/compatible range when patches exist. Do not use `exclude` to silence scanner alerts without analyzing application call paths and functional impact.

## 15. CI: turn packaging conditions into an automated check

If you **intentionally exclude H2** from the example archive, CI can verify that H2 is **absent from the executable JAR** and required Spring Boot libraries **remain present**.

Example **Linux/bash** script running after Maven `package`:

~~~bash
set -eu
jar_path="target/packaging-demo-0.0.1-SNAPSHOT.jar"

jar tf "$jar_path" > jar-entries.txt

if grep -q '^BOOT-INF/lib/h2-' jar-entries.txt; then
    echo "Unexpected H2 JAR in executable archive" >&2
    exit 1
fi

grep -q '^BOOT-INF/lib/spring-boot-' jar-entries.txt
grep -q '^BOOT-INF/classes/com/example/packaging/PackagingDemoApplication.class$' jar-entries.txt

echo "Packaging contents verified"
~~~

For Gradle, change the path to `build/libs/packaging-demo-0.0.1-SNAPSHOT.jar`. The script assumes the right working directory and JDK `jar` installed. `grep -q` exits non-zero if expected content is missing, causing the job to fail via `set -e`. **Exact line printed by the script when passing**:

~~~text
Packaging contents verified
~~~

If the goal is to **require H2 to be included**, invert the check:

~~~bash
jar tf "$jar_path" | grep -q '^BOOT-INF/lib/h2-'
~~~

**Pipeline note:** with `set -o pipefail`, `jar tf | grep -q` can occasionally trigger unexpected status if `jar` hits a broken pipe after `grep` matches early; saving `jar-entries.txt` first and grepping it is simpler and more reliable. You can substitute a Python/Java script that reads the archive if your organization has more complex requirements.

In Windows PowerShell CI, use `jar tf` to capture entries and `Select-String` to match, checking results/exit codes; do not copy bash `set -eu` scripts verbatim into PowerShell.

CI also needs **real application tests** and a smoke test running the actual artifact. A passing `BOOT-INF/lib` check only confirms the file list; it does not guarantee the application context and features work end-to-end.

## 16. Common misconceptions and errors

| Symptom | Possible cause | How to verify and resolve |
| --- | --- | --- |
| Added H2 in POM but `java -jar` reports missing driver | Wrong scope, `repackage.excludes`, running the `.original` file, or wrong version/module | Check `dependency:tree`, `BOOT-INF/lib/`, effective POM, and JAR path |
| Added `runtimeOnly` in Gradle but `bootJar` lacks the file | Runtime graph excluded it, task classpath filter, `developmentOnly`, or wrong module built | `dependencies --configuration runtimeClasspath`, `dependencyInsight`, `jar tf` |
| Maven `dependency:tree` still shows excluded module | `repackage.excludes` filters packaging, not the resolution graph | Expected behavior; inspect nested JARs directly |
| Gradle `bootRun` works while `java -jar` fails | `bootJar` has a classpath filter while `bootRun` still uses full `runtimeClasspath` | Compare `bootJar.classpath`, `runtimeClasspath`, and JAR contents |
| Excluded broad group and Boot JAR fails to start | `excludeGroupIds` dropped essential modules | Revert to narrow groupId/artifactId excludes; re-verify all nested JARs |
| Enabled `<includes>` for one module and app fails | Allowlist accidentally dropped core libraries | Remove allowlist or populate it completely with testing |
| `testImplementation` has H2 but JAR lacks it | Dependency is used only in test configuration | Move to `runtimeOnly` if app runtime actually needs it |
| `spring-boot-devtools` packaged in production | Devtools unintentionally added to packaging classpath | Use `developmentOnly` (Gradle), keep default exclude/check `repackage` (Maven) |
| `NoClassDefFoundError` only on a rarely used API | Required dependency was excluded, and smoke test missed that branch | Add business integration tests; inspect runtime graph |
| Smaller JAR yet scanner still alerts | Dependency remains in another image, test/build graph, or scanner inspects a different source | Identify the exact scanned artifact and CVE scope |
| Ran `-plain.jar` or `.original` by mistake | Archive is not the final executable archive | Locate Boot JAR with proper classifier; check manifest/BOOT-INF |
| Standalone `spring-boot:repackage` failed | Goal expects source JAR from `package` phase first | Use `clean package` when bound to lifecycle or `package spring-boot:repackage` if needed |
| Local build green, CI fails to resolve library | Different repositories, mirrors, credentials, proxies, or Gradle/Maven caches | Pin Wrapper/JDK/BOM; inspect dependency graph on clean CI |

## 17. Decision workflow and post-change checklist

1. **State the goal:** are you adding a library needed at runtime, or excluding a library from the artifact because production does not need it?
2. **Record baseline:** Spring Boot version, JDK, Maven/Gradle Wrapper, dependency tree/`runtimeClasspath`, nested JAR list, and smoke test results.
3. **Pick the smallest layer to change:** dependency declaration/scope to add; graph exclusion if truly unneeded; packaging-specific plugin/task config when altering only the archive.
4. **Defer versions to the BOM** whenever possible to avoid incompatibilities across a library family; document reasons if overriding.
5. **Clean build:** Maven `clean package` or Gradle `clean bootJar` via the Wrapper in the right module.
6. **Read artifact:** open the manifest, list `BOOT-INF/lib`, verify exact artifact/classifier.
7. **Run artifact:** `java -jar`, observe markers/health/business branches using the library.
8. **Run tests:** unit tests, integration tests, runtime smoke tests on the committed JDK/environment.
9. **Automate assertions:** CI checks required/forbidden modules and fails on mismatch.
10. **Review security:** SBOM, dependency graph, download sources, CVEs, licenses, and removal risk.
11. **Document and rollback:** note changes in the PR so you can revert to prior dependencies/packaging if features or compatibility break.

You have completed this lesson when you can explain **why `mvn dependency:tree` or `gradle dependencies` alone cannot prove a library is in the executable JAR**, add or exclude H2 yourself in the example, and prove the outcome via **`BOOT-INF/lib` and `java -jar`**.

## Official documentation

- [Spring Boot 3.3 – Maven Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html)
- [Spring Boot 3.3 – Gradle Plugin: Packaging Executable Archives](https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html)
- [Spring Boot – Executable JAR Format](https://docs.spring.io/spring-boot/specification/executable-jar/index.html)
- [Apache Maven – Introduction to the Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html)
- [Apache Maven – Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Gradle – Dependency Configurations](https://docs.gradle.org/current/userguide/dependency_configurations.html)
- [Gradle – Viewing and Debugging Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Gradle – Excluding Transitive Dependencies](https://docs.gradle.org/current/userguide/how_to_exclude_transitive_dependencies.html)