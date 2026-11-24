# Controlling the Exclusion of DevTools and Development Helpers from Release Artifacts

## 1. Goals and Principles

When developing Spring Boot applications, we often want **automatic restarts on code edits**, **auto-started Docker Compose services**, **test runners**, **annotation-based code generation**, **debugging**, or **local data viewers**. These helpers speed up development, yet they should not automatically end up inside a JAR, WAR, or container image shipped to production.

After this lesson, you will be able to:

1. Distinguish **development-time runtime dependencies**, **build/test tooling dependencies**, **required runtime dependencies**, and **development-only resources/configurations**.
2. Configure `spring-boot-devtools` with Maven and Gradle for a great developer experience while keeping it **out of release executable artifacts**.
3. Understand Maven's `spring-boot-maven-plugin`, `repackage`, `excludeDevtools`, and `excludeDockerCompose`, and use `<excludes>` carefully for other dev-only libraries.
4. Understand Gradle's `developmentOnly` and the difference between `runtimeClasspath` used during development and the packaging classpath of `bootJar`/`bootWar`.
5. **Verify by opening the actual JAR/WAR**, rather than relying solely on profiles, startup logs, or paper configuration.
6. Add CI checks to prevent accidentally shipping DevTools, test suites, local config files, or unnecessary helper libraries.

**Example context:** the `pom.xml` and `build.gradle` files illustrate a **Spring Boot 3.3.13, Java 17** application for consistent syntax throughout the guide. When your project uses Spring Boot 3.5, 4.x, or different Gradle/Maven plugins, consult the official documentation **for that exact version**. Never upgrade or downgrade a project's versions merely to copy an example.

**Core principle:** "DevTools is inactive in production" **does not mean** "DevTools is absent from the artifact." Only inspecting the bytes/contents of the release archive confirms packaging exclusion.

## 2. Selecting the Right Items to Exclude: Four Distinct Groups

| Group | Examples | Normally in Production Artifact? | Measure |
| --- | --- | --- | --- |
| Required runtime | Spring MVC, JSON serializers, real DB drivers, security, required logging runtime | **Yes**, per architecture | Gradle `implementation`/`runtimeOnly`; Maven appropriate `compile`/`runtime` |
| Dev runtime for local coding only | `spring-boot-devtools`, `spring-boot-docker-compose`, local dev helper libraries | **No**, unless a specific controlled exception exists | Gradle `developmentOnly`; Maven plugin exclusions and proper declarations |
| Test/compile tooling | JUnit, Mockito, `spring-boot-starter-test`; annotation processors like Lombok/MapStruct processors | Normally **no** | Maven `test`, processor paths; Gradle `testImplementation`, `annotationProcessor`/`compileOnly` |
| Local config/data | `application-local.yml`, `.env`, debug scripts, test fixtures, private certs | Usually **no**, depending on needs | Keep secrets out of `src/main/resources`; exclude resources intentionally; use external config/secret stores |

Do not equate "**support tools**" with "**harmful code**." For example, `spring-boot-starter-actuator` provides observability endpoints that may be **genuinely required in production** with proper access control and exposure; blindly stripping Actuator just because it aids operations is wrong. Conversely, an HTTP inspector, local database, or remote-devtool with no production runtime role should not be carried along merely out of convenience.

For a JAR/WAR, an unwanted tool can enter an artifact via two paths:

- **Dependency libraries:** e.g., `spring-boot-devtools-<version>.jar` inside `BOOT-INF/lib` of an executable JAR.
- **Application code/resources:** e.g., a debug controller, `application-local.yml`, mock data, or a `.env` file copied into `BOOT-INF/classes`.

Dependency exclusions only address the first path; cleaning the second requires reviewing **source sets, resource processing, profiles/configuration, and archive contents themselves**.

## 3. What Is DevTools and Why Separate It from Releases?

`spring-boot-devtools` enhances the development workflow with classpath-change restarts, LiveReload, and developer-friendly defaults (such as disabling template caches). A project may want it when running in an IDE or via `bootRun`/`spring-boot:run`, whereas the production distribution has no reason to carry it.

### 3.1 Three States to Distinguish

| State | Question It Answers | Evidence Required |
| --- | --- | --- |
| **Present in dependency declaration** | Does the POM/build file declare DevTools? | `pom.xml` / `build.gradle[.kts]` |
| **Present on development classpath** | Can the app use DevTools when running during development? | Maven/Gradle dependency resolution and direct run behavior |
| **Present in release archive** | Does the shipped JAR/WAR contain DevTools bytes? | `jar tf` on the **exact artifact file** |

Spring Boot documentation states that DevTools **disables itself automatically** when running as a fully packaged application (for instance launched via `java -jar`). That is a **runtime behavioral safeguard**, not proof that `spring-boot-devtools-*.jar` was excluded from the ZIP/JAR/WAR. Misconfigured plugins can still pack the library into the archive even if it remains dormant during normal startup.

You can disable restarts via the system property `-Dspring.devtools.restart.enabled=false`, yet **that is not removing the dependency from the archive either**. Attempting to force-enable it in production with `-Dspring.devtools.restart.enabled=true` is risky and should never be done. Remote DevTools in particular should never be shipped in a production system just to debug remotely.

### 3.2 Not Every Helper Library Has Built-in Default Exclusions

The Spring Boot plugins specifically recognize **`spring-boot-devtools`** and, on supported Spring Boot versions, **`spring-boot-docker-compose`**. Other third-party or internal libraries like a custom "local debug helper" **are not automatically excluded** just because their name contains "dev" or "debug," or because they are gated by `@Profile("local")`.

Never assume a library is excluded because of its `artifactId` name or `@Profile("dev")`. Inspect **scope/configuration** and **how the packaging task assembles its classpath**.

## 4. Maven: `optional`, `repackage`, and DevTools Exclusion Options

### 4.1 Complete Maven POM Example for a JAR Application

The `pom.xml` below applies the Spring Boot parent and Maven plugin. `spring-boot-devtools` is marked `optional`, while `repackage` sets both exclusion flags to `true` (already the defaults for this plugin version, shown explicitly for clarity in reviews).

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
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <packaging>jar</packaging>

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
            <artifactId>spring-boot-devtools</artifactId>
            <optional>true</optional>
        </dependency>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-docker-compose</artifactId>
            <optional>true</optional>
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
                <configuration>
                    <excludeDevtools>true</excludeDevtools>
                    <excludeDockerCompose>true</excludeDockerCompose>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

This is a complete POM for the build/dependency layer; to package a runnable executable JAR, the project still needs a `main` class with `@SpringBootApplication` (shown in Section 7). `spring-boot-starter-parent` preconfigures the `repackage` execution, so declaring `spring-boot-maven-plugin` inside `<plugins>` suffices. If your project **does not** inherit the parent, you must configure the `repackage` execution explicitly; never assume every POM listing the plugin runs `repackage` during `package`.

#### Meaning of Each Attribute

- `<optional>true</optional>` on a **Maven dependency** mainly tells modules *consuming your artifact* not to pull this dependency **transitively**. It **does not** mean "Maven cannot use this dependency inside this project itself"; DevTools remains available for local development runs.
- `<excludeDevtools>true</excludeDevtools>` is a **Spring Boot Maven Plugin `repackage`** option that strips `spring-boot-devtools` from the executable archive; default is `true`.
- `<excludeDockerCompose>true</excludeDockerCompose>` strips `spring-boot-docker-compose` from the archive; default is `true` on supported plugin versions.
- `<scope>test</scope>` keeps the Spring Boot test starter scoped to testing; it is not treated as a standard release runtime dependency.
- `<packaging>jar</packaging>` builds a JAR artifact; Spring Boot `repackage` places dependencies under `BOOT-INF/lib`.

**Note on version differences:** newer generations of the Spring Boot Maven Plugin introduce general optional-dependency flags (such as `includeOptional`); capabilities and defaults may differ from 3.3.13. Therefore, in real projects, **do not deduce packaging solely from `optional`**: consult your exact plugin version's docs and inspect the final artifact.

### 4.2 How `spring-boot:repackage` Differs from `jar` and `scope`

Typical Maven flow:

```text
src/main/java + src/main/resources
          |
          v
       compile
          |
          v
        package ----> Plain JAR/WAR before repackage
          |
          v
spring-boot:repackage ---> executable Boot JAR/WAR
          |
          +-- excludes spring-boot-devtools
          +-- excludes spring-boot-docker-compose
          +-- applies configured <excludes>
```

Ordering and produced artifacts depend on actual configuration. With the Boot parent, `repackage` binds to the lifecycle; `./mvnw package` executes prior phases and produces the final artifact. In a project that neither uses the parent nor configures `repackage`, `target/*.jar` may be only a **plain JAR**, lacking the executable Boot JAR layout.

**Important caveat:** Maven's `provided` scope is not a "guarantee of exclusion from an executable Spring Boot archive." The Spring Boot Maven Plugin can package **provided dependencies** inside executable JAR/WAR archives so they run standalone; in a WAR, they may sit in `WEB-INF/lib-provided`. Therefore, to exclude a local-only helper, do not simply change its scope to `provided` and assume it is gone. For DevTools and Docker Compose, use the dedicated exclusion options and inspect the archive.

For WAR files deployed to an external servlet container, Spring Boot documentation also notes marking `spring-boot-devtools` and `spring-boot-docker-compose` as `optional` or `provided` so WAR packaging exclusion works properly. **Prefer `optional` as shown above** and verify both `WEB-INF/lib` and `WEB-INF/lib-provided`.

### 4.3 Excluding *Other* Helper Libraries via `<excludes>`

If a third-party dependency is strictly for local use yet enters the archive, the Spring Boot Maven Plugin provides `<excludes>` matching `groupId` and `artifactId`. **Configuration snippet example**—replace the illustrative coordinates with the real dependency:

```xml
<plugin>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-maven-plugin</artifactId>
    <configuration>
        <excludeDevtools>true</excludeDevtools>
        <excludeDockerCompose>true</excludeDockerCompose>
        <excludes>
            <exclude>
                <groupId>com.example.tools</groupId>
                <artifactId>local-debug-helper</artifactId>
            </exclude>
        </excludes>
    </configuration>
</plugin>
```

`com.example.tools:local-debug-helper` is purely an **illustrative coordinate**, not a claim that such a library exists. This snippet goes inside `<build><plugins>` of an existing POM. **Exact** exclusions are safer than broad `<excludeGroupIds>`, which might accidentally strip valid runtime libraries sharing the same group.

Before excluding at packaging time, investigate **why it appears** (`dependency:tree`); ideally **put the dependency in the right scope or remove the unnecessary declaration**. Packaging `<excludes>` acts as a helpful guardrail, yet it can mask a dependency actually called by application code. If the app invokes APIs from a stripped library, `java -jar` risks `ClassNotFoundException` or `NoClassDefFoundError`.

### 4.4 How Maven WAR Packaging Differs from JAR

Maven can use `<packaging>war</packaging>` with Spring Boot `repackage` to produce an executable WAR. There, application libraries generally live under `WEB-INF/lib`, while container-provided dependencies may live under `WEB-INF/lib-provided`. Do not grep only `BOOT-INF/lib` when auditing a WAR.

When deploying to an external servlet container, you must still satisfy `SpringBootServletInitializer`, compatible Servlet APIs, and proper container-dependency scoping. **That is a separate concern from excluding DevTools**, though missing deployment setup can be mistaken for a DevTools problem.

Never set `<excludeDevtools>false</excludeDevtools>` in production just for "easy debugging"; if an exception is ever needed for remote development, keep it in a separate artifact never fed into the production release pipeline.

## 5. Gradle: `developmentOnly` and `bootJar`/`bootWar`

### 5.1 Complete Groovy DSL Example

With `settings.gradle`:

```groovy
rootProject.name = 'demo'
```

File `build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
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

    // Present when running in development, excluded from bootJar/bootWar by default.
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
    developmentOnly 'org.springframework.boot:spring-boot-docker-compose'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

This is a **Spring Boot 3.3.x setup using the Gradle Java plugin**. The project also needs a Java `main` class. `io.spring.dependency-management` handles BOM resolution for this example and is not what excludes DevTools; projects using Gradle's native BOM can manage versions differently while keeping `developmentOnly` classification.

**`developmentOnly`** is a configuration created by the Spring Boot Gradle plugin when applied appropriately. Dependencies placed there serve **development workflows** and **are excluded by default from executable JAR/WAR files** built by `bootJar`/`bootWar`. When launching from the IDE or `bootRun`, the development runtime classpath can include them—which is the intended behavior.

Conversely, the snippet below is **not recommended** if you want DevTools restricted to development:

```groovy
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-devtools'
}
```

`runtimeOnly` declares the library as a **normal runtime dependency**. Once DevTools enters the production runtime tier rather than `developmentOnly`, never rely on its "auto-disable" behavior to guarantee a clean JAR. Use `developmentOnly` and verify the `bootJar` output.

### 5.2 Equivalent Kotlin DSL

In `build.gradle.kts`, the key sections are:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    developmentOnly("org.springframework.boot:spring-boot-devtools")
    developmentOnly("org.springframework.boot:spring-boot-docker-compose")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

**This is an excerpt**: for a complete build file, include `group`, `version`, `java` toolchain, `repositories`, and `tasks.test` accordingly. Do not paste Groovy syntax like `developmentOnly '...'` into Kotlin DSL.

### 5.3 Three Distinct Classpaths

| Gradle Component | Role | Might DevTools Appear? |
| --- | --- | --- |
| `runtimeClasspath` / `bootRun` for development | Runs app directly from classes/resources during development | **Yes**, when properly added to `developmentOnly` |
| `productionRuntimeClasspath` (provided by Boot plugin on applicable versions) | Represents runtime with development-only dependencies stripped | By design, **excludes** dependencies appearing solely via `developmentOnly` |
| `bootJar`/`bootWar` classpath | Input to assemble the release executable archive | By default, **excludes** `developmentOnly` dependencies |

This distinction is **intentional**: seeing DevTools in the `runtimeClasspath` report **does not prove** your `bootJar` contains DevTools. Compare the right classpath and inspect the real archive contents.

Diagnostic commands:

```bash
# Development runtime; may contain DevTools.
./gradlew dependencies --configuration runtimeClasspath

# Production runtime per the Spring Boot Gradle plugin model.
./gradlew dependencies --configuration productionRuntimeClasspath

# Trace where a dependency enters the runtime classpath.
./gradlew dependencyInsight --dependency spring-boot-devtools --configuration runtimeClasspath

# Run for development.
./gradlew bootRun

# Build release artifact.
./gradlew clean bootJar
```

`developmentOnly` and `productionRuntimeClasspath` are **plugin/version-dependent** configurations; run `./gradlew dependencies` or `./gradlew help --task bootJar` if a name is absent. In multi-module builds, qualify the subproject path such as `:app:dependencies` and inspect the **releasing application module**, not only the root project.

### 5.4 Do Not Accidentally Re-Add `developmentOnly` to the Archive

The Spring Boot Gradle plugin docs show how to **intentionally include** development-only dependencies in an archive by altering `bootJar` or `bootWar` classpath. The snippet below is an **anti-pattern to avoid in release configurations**, shown solely as a review red flag:

```groovy
// DO NOT put in a release pipeline if the goal is to exclude DevTools.
tasks.named('bootJar') {
    classpath configurations.developmentOnly
}
```

This tells the Boot task to add `developmentOnly` dependencies into the archive, **defeating the default exclusion guarantee**. Do not mistake `classpath configurations.developmentOnly` for "excluding a classpath"—it **adds** it.

Likewise, with the `war` plugin, use `bootWar` for executable WARs and inspect its task classpath; a `classpath` override or custom Copy task can re-introduce dev dependencies that were properly scoped.

`jar`/`war` differ from `bootJar`/`bootWar`, so testing only the plain task or inspecting `-plain.jar` **does not prove** the released executable archive is clean.

## 6. Other Tools: Applying Policies by Function

### 6.1 `spring-boot-docker-compose`

Since Spring Boot 3.1, `spring-boot-docker-compose` helps manage services via Docker Compose during development. That is distinct from a production app **running inside Docker**; a production Dockerfile/image does not need this module.

- **Maven:** add as an optional dependency, keep `excludeDockerCompose=true` in `spring-boot-maven-plugin`, inspect the JAR/WAR.
- **Gradle:** declare in `developmentOnly`. Never place it in `implementation` merely because Compose runs on laptops.
- **Do not confuse** "containerized Docker image execution" with "application requiring the Spring Boot Docker Compose library at runtime." They are two separate stages.

A project might not use `spring-boot-docker-compose` at all. In that case, **do not add a dependency just to exclude it**; a minimal build file is always better.

### 6.2 Testing Libraries

`spring-boot-starter-test`, JUnit, Mockito, and unit/integration test fixtures belong in the **test** scope/configuration, never runtime.

Maven:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-test</artifactId>
    <scope>test</scope>
</dependency>
```

Gradle:

```groovy
dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Place test helpers in `src/test/java` and `src/test/resources` rather than `src/main` when they are purely for tests. To share test fixtures across modules, use dedicated test-fixtures plugins/configurations rather than pulling test libraries into the main app's `implementation`.

**Remember:** `-DskipTests` or `./gradlew -x test` only **skips test execution**; it does not keep test dependencies out of an artifact. Scopes/configurations and packaging rules determine what lands in the archive.

### 6.3 Lombok and Annotation Processors

Annotation processors generate code at **compile time** and do not automatically belong in runtime. Gradle example:

```groovy
dependencies {
    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'

    testCompileOnly 'org.projectlombok:lombok'
    testAnnotationProcessor 'org.projectlombok:lombok'
}
```

Coordinates and versions can be managed by dependency management or another configuration; this snippet illustrates **classification**, not a full `build.gradle`. In Maven, use annotation processor paths or the Maven Compiler Plugin's processor settings matching your version, keeping processors out of runtime dependencies.

Do not exclude genuinely required runtime libraries like MapStruct's **runtime API**, database drivers, or libraries invoked by generated code at runtime simply because their ecosystem mentions "processor." Classify **specific artifacts** rather than filtering vaguely by keyword.

### 6.4 Local Diagnostics / Debug Agents / Helper UIs

Debugging utilities may be attached via:

- A startup Java agent using `-javaagent:/path/to/agent.jar`.
- Java system properties or IDE run configurations.
- `bootRun`, Maven `spring-boot:run`, or custom launch scripts.
- A misdeclared dependency in `runtimeOnly`/`implementation`.

A Java agent passed on the command line **does not reside inside the executable JAR**; conversely, a debug JAR inside `BOOT-INF/lib` does not vanish simply because production omits `-javaagent`. Inspect **the archive**, Dockerfiles/entrypoints, and startup scripts if the goal is keeping tooling out of release environments.

Remote DevTools and remote debugging expose a large attack surface. Never enable remote dev configs in production as a verification shortcut; rely on production-designed observability with proper authorization and no bundled dev tooling.

### 6.5 Do Not Label Everything Containing "tools" as DevTools

Some Spring Boot executable archives include `spring-boot-jarmode-tools` to support layered archives and extraction for container builds. That is **not** `spring-boot-devtools`. Spring Boot Maven/Gradle plugins offer an `includeTools` option to control packaging-related tooling in supported versions.

If policy restricts tools, verify the meaning and impact of `includeTools=false` before changing it; disabling it can break image build pipelines relying on layer extraction. **The goal of this lesson is not deleting every file containing "tools"**, but removing unneeded runtime artifacts without breaking designed packaging behavior.

## 7. Java 17+ Example for Verifying Runtime After Packaging

For both Maven and Gradle examples, create `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {

    @GetMapping("/ready")
    public String ready() {
        return "ready";
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

This is **a complete Java class for a Spring Boot project that already has its starters**. It does not run standalone with `javac DemoApplication.java` because Spring Boot libraries are needed on the classpath. With `spring-boot-starter-web`, `GET /ready` returns the text:

```text
ready
```

That is the **controller's HTTP response body**, not Maven/Gradle logs. When running standalone on the default port 8080 with no custom context path, call `curl http://localhost:8080/ready`. If port, profile, or context path changed, use the actual URL.

Create a minimal test `src/test/java/com/example/demo/DemoApplicationTests.java`:

```java
package com.example.demo;

import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;

@SpringBootTest
class DemoApplicationTests {

    @Test
    void contextLoads() {
    }
}
```

Running `./mvnw test` or `./gradlew test` with the Maven/Gradle configurations above verifies that the context loads. It **does not prove DevTools was excluded from the JAR**; that proof comes from inspecting the archive below.

### Running in Development vs. Running the Packaged Artifact

Maven:

```bash
# From the directory containing pom.xml and mvnw
./mvnw spring-boot:run

# In another terminal, call the endpoint:
curl http://localhost:8080/ready

# Stop the application, then package:
./mvnw clean package
java -jar target/demo-0.0.1-SNAPSHOT.jar
```

Gradle:

```bash
# From the directory containing build.gradle and gradlew
./gradlew bootRun

# Another terminal:
curl http://localhost:8080/ready

# Stop the application, then package:
./gradlew clean bootJar
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
```

Note that `spring-boot:run`/`bootRun` usually **holds the terminal** while running; stop the app or use another terminal before running the next build so port 8080 does not conflict. With Docker Compose dev support, local container startup/connection depends on your Compose file and Docker environment; to test the endpoint exercise without Spring Boot starting Compose automatically, either **omit `spring-boot-docker-compose`** or disable it in your practice environment.

Expected observations table:

| Check | Development Run | Packaged Production-Style Run |
| --- | --- | --- |
| DevTools dependency | May be on the development classpath | Excluded from the executable archive if configured properly |
| Restart/live reload | Can operate when classpath changes | Not a desired feature in release deliverables |
| `/ready` | Returns `ready` when app starts | Still returns `ready` when archive is valid |
| Test starter | Used during `test` | Absent from archive's runtime library path |
| Proves clean artifact | **No**, as it is only a local run | Requires `jar tf` / inspecting the released image |

## 8. Inspecting the Real JAR/WAR Directly: A Mandatory Step

### 8.1 Verify the Right Archive Name First

After Maven `./mvnw clean package`, the Spring Boot executable JAR for this example may be `target/demo-0.0.1-SNAPSHOT.jar`. Another `.original` file may hold the pre-repackage archive: **never pick it instead of the deployable artifact**.

After Gradle `./gradlew clean bootJar`, the executable JAR may be `build/libs/demo-0.0.1-SNAPSHOT.jar`; if the `jar` task also ran, `demo-0.0.1-SNAPSHOT-plain.jar` may exist too. Never accidentally inspect the plain file when CI deploys the boot file (or vice versa).

Exact filenames depend on `artifactId`, `rootProject.name`, `version`, and archive customizations. In real projects, **locate the exact file used by the deploy stage** and inspect that exact file.

### 8.2 Inspecting the JAR with the JDK Tool

`jar tf` lists ZIP/JAR/WAR entries without running the application:

```bash
# Maven (per example)
jar tf target/demo-0.0.1-SNAPSHOT.jar

# Gradle (per example)
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
```

A Spring Boot executable JAR typically follows this layout:

```text
BOOT-INF/
    classes/
        com/example/demo/DemoApplication.class
    lib/
        spring-boot-...jar
        spring-webmvc-...jar
        ... runtime dependencies ...
META-INF/
org/springframework/boot/loader/...
```

This is an **illustrative** tree. Exact library names, versions, and loader classes depend on the Boot version and app. With proper example configuration, the following **must not** appear:

```text
BOOT-INF/lib/spring-boot-devtools-<version>.jar
BOOT-INF/lib/spring-boot-docker-compose-<version>.jar
BOOT-INF/lib/spring-boot-starter-test-<version>.jar
BOOT-INF/lib/junit-jupiter-<version>.jar
```

Those lines describe **entries that must be absent**, not literal filenames in the artifact. `<version>` is merely an explanatory placeholder, not literal text.

For an executable WAR, inspect **both** `WEB-INF/lib/` **and** `WEB-INF/lib-provided/`. A dependency absent from `WEB-INF/lib` may still be packaged inside `lib-provided`. Checking only `BOOT-INF/lib` does not work for WARs.

### 8.3 Quick CI Check Script (Bash)

This script checks for **JAR filenames of both Spring Boot development modules** inside an executable JAR/WAR using `jar tf` and `grep` without manual inspection:

```bash
#!/usr/bin/env bash
set -euo pipefail

# Replace with the exact deploy artifact. Maven example:
artifact="target/demo-0.0.1-SNAPSHOT.jar"

# jar tf fails -> script fails (missing or corrupt archive).
entries="$(jar tf "$artifact")"

# Match ZIP paths for executable JAR or WAR.
dev_regex='^(BOOT-INF/lib|WEB-INF/lib|WEB-INF/lib-provided)/(spring-boot-devtools|spring-boot-docker-compose)-[^/]+[.]jar$'

if printf '%s\n' "$entries" | grep -E "$dev_regex"; then
    echo "FAIL: development-only module exists in release archive"
    exit 1
fi

echo "PASS: no Spring Boot DevTools/Docker Compose JAR in archive"
```

**Exact meaning:** if `jar tf` succeeds and `grep` finds neither module in the standard directories, the script prints:

```text
PASS: no Spring Boot DevTools/Docker Compose JAR in archive
```

This stdout holds **only under those conditions** (without claiming execution on a real project). If a module is found, the script prints the offending path and exits with 1; if the archive cannot be read, the script halts due to `set -e`.

This template does not replace checking **all** internal dev tools; expand the `artifactId` list per your organization's approved catalog. Never add an essential runtime library to a denylist blindly without analyzing the dependency graph.

### 8.4 PowerShell (Windows)

```powershell
$artifact = "target/demo-0.0.1-SNAPSHOT.jar"
$entries = & jar tf $artifact
if ($LASTEXITCODE -ne 0) {
    throw "Cannot inspect release archive"
}

$pattern = '^(BOOT-INF/lib|WEB-INF/lib|WEB-INF/lib-provided)/(spring-boot-devtools|spring-boot-docker-compose)-[^/]+[.]jar$'
$hits = @($entries | Select-String -Pattern $pattern)
if ($hits.Count -gt 0) {
    $hits
    throw "Development dependency found in release archive"
}
Write-Output "PASS: no Spring Boot DevTools/Docker Compose JAR in archive"
```

This requires the JDK's `jar` on `PATH` and running from the right working directory. For Gradle, replace `$artifact` with the real `build/libs/...jar` path. This checks the **built archive** and does not prove a Docker image holds that exact build if the image build uses another artifact.

### 8.5 Checking for Mistakenly Bundled Test Dependencies and Dev Configs

You can also run a manual search:

```bash
jar tf target/demo-0.0.1-SNAPSHOT.jar | grep -E \
  '(BOOT-INF/lib|WEB-INF/lib|WEB-INF/lib-provided)/|application-(local|dev)[.]|(^|/)[.]env$'
```

This report is for **review**, not an automated PASS/FAIL check: a file named `application-dev.yml` might be intentional if it holds no secrets, though you should carefully evaluate whether it belongs in production builds. Meanwhile, a `.env` or password file inside `src/main/resources` will not disappear thanks to `excludeDevtools`.

For security assurance, also incorporate **SBOM/dependency inventories**, source/secret scanning, and post-build Docker image inspection. A clean archive in one module does not guarantee the entire repository and all images are clean.

## 9. Why Might DevTools Still Land in the Artifact Even When "Disabled in Production"?

This can happen when:

1. **Gradle:** DevTools was declared in `implementation` or `runtimeOnly` instead of `developmentOnly`.
2. **Gradle:** a custom `bootJar`/`bootWar` classpath appended `configurations.developmentOnly`.
3. **Maven:** the project did not actually run `spring-boot:repackage`, or ran a different plugin version/config than expected; the inspected artifact is the pre-repackage JAR.
4. **Maven:** `excludeDevtools` was set to `false` or configured in the wrong block, or a WAR build violated the plugin's `optional`/scope rules.
5. **General build:** DevTools entered transitively through another library module on the runtime graph, or the pipeline used a custom packaging mechanism instead of Boot's executable archive.
6. **CI:** mistakenly picked `-plain.jar`, `.original`, a stale cached JAR, or built the image from a different build folder.
7. **Non-dependency files:** debug code, local configs, or shaded/repackaged libraries under another name; scanning for `spring-boot-devtools-*.jar` will miss copied classes.

When suspicious, never slap on a "disable" flag and call it done. Fix it at the **right layer**: dependency graph → task/scope → output archive → image/runtime.

### Maven: Tracing the Dependency Source

```bash
# See which path pulls devtools into the build:
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-devtools

# Inspect the resolved Maven model after parent/profiles:
./mvnw help:effective-pom -Doutput=effective-pom.xml

# Clean build using the Wrapper:
./mvnw clean package
```

A `dependency:tree` entry for DevTools is **evidence that the dependency exists in the project's graph**, not proof it enters the executable JAR. Check plugin configuration and `jar tf` separately. `clean` deletes `target`; run it only in workspaces you are allowed to build.

If pulled in by an internal starter or library module, consider marking it **optional** in the declaring module, splitting it into a dev-only module, or declaring targeted exclusions in the application. Never resolve conflicts in a way that strips runtime libraries the app actually needs.

### Gradle: Explaining the Dependency Path

```bash
./gradlew dependencyInsight \
  --dependency spring-boot-devtools \
  --configuration runtimeClasspath

./gradlew dependencies --configuration productionRuntimeClasspath

./gradlew clean bootJar
```

If `runtimeClasspath` contains DevTools while `productionRuntimeClasspath` does not, that is usually the **intended behavior** of `developmentOnly`. If DevTools still shows up under `BOOT-INF/lib` inside `bootJar`, inspect `bootJar.classpath` customizations, custom plugins, and verify you opened the right file.

When analyzing submodules, specify the target project, e.g., `./gradlew :app:dependencies --configuration productionRuntimeClasspath` if `:app` is the releasing module. Never substitute another module's report as evidence for the application module.

### "DevTools Not Found" Yet App Still Exhibits Dev Behavior

Development defaults or custom behavior can also come from:

- Settings in `application.yml` or system properties (e.g., template caching, stacktrace details).
- IDE, Gradle tasks, or custom run scripts attaching agents.
- Custom code gated by `@Profile("local")` or feature flags.
- Dev resources or scripts inside the JAR even without the main DevTools dependency.

Thus **removing DevTools is one step**, not an automatic "production hardening" guarantee. Audit production profiles, logging, endpoint exposure, secrets, and operations independently.

## 10. Preventing Dev-Only Files from Leaking via `src/main/resources`

Files inside `src/main/resources` are normally copied onto the application classpath and packaged into the executable archive, even if the active profile at runtime is `prod`. **`@Profile` or `spring.profiles.active` does not remove resources from the JAR.**

Example:

```text
src/main/resources/
├── application.yml
├── application-local.yml
├── application-prod.yml
├── static/
│   └── ...
└── private-dev-data.json
```

By default, `application-local.yml` and `private-dev-data.json` can still be packaged inside the JAR. Spring may not load `application-local.yml` when running `prod`, yet its bytes still exist inside the artifact. **Never treat "inactive profile" as a secret-protection mechanism**.

Preferred practices:

- Keep credentials and secrets out of the repository and archive; supply them via environment variables, secret stores, or external config per operational policy.
- Place fixtures and test data in `src/test/resources`, not `src/main/resources`, if used solely for tests.
- For local files that belong in the repo for convenience yet must not ship, store them in a development directory not copied by the build, or use verified includes/excludes.
- Never filter passwords during build time into `application-prod.yml` or a Dockerfile assuming it is safe just because logs don't print the file.

### Gradle: Excluding Dev-Only Resources via `processResources`

**Groovy DSL snippet example:**

```groovy
tasks.named('processResources') {
    exclude('private-dev-data.json')
    exclude('application-local.yml')
}
```

This tells the Gradle Java plugin **not to copy** those relative paths into `build/resources/main`. If the app actually relies on `application-local.yml` when running directly on the local classpath, **do not apply this blindly**: supply local external config instead. `bootRun` typically reads from the source set output as well, so excluding a file here alters local behavior too—which is why separating local resources from production sources from the outset is cleaner.

### Maven: Excluding Resources via `<excludes>`

**Snippet example** inside `<build>`:

```xml
<resources>
    <resource>
        <directory>src/main/resources</directory>
        <excludes>
            <exclude>private-dev-data.json</exclude>
            <exclude>application-local.yml</exclude>
        </excludes>
    </resource>
</resources>
```

**Warning:** redefining `<build><resources>` can override `spring-boot-starter-parent`'s resource filtering rules, such as filtering `@...@` placeholders in `application.properties`. In existing Maven projects, inspect `help:effective-pom` and preserve required resource blocks/filters when adding excludes; never paste this snippet blindly and break filtering elsewhere.

## 11. Enforcing Release Artifact Hygiene in CI/CD

To prevent regressions, place an **artifact verification gate** between build and deploy rather than reviewing `pom.xml`/`build.gradle` only once.

### 11.1 Minimal Evidence-Backed Pipeline

1. **Check out reviewed code** and run trusted Maven/Gradle Wrappers.
2. **Run tests** in a dedicated stage; never treat skipping tests as a way to exclude test libraries.
3. **Build the release artifact** using the exact task: Maven `package` with Spring Boot `repackage`, or Gradle `bootJar` / `bootWar`.
4. **Pick the exact artifact**: never use overly broad wildcards when a directory holds both executable and plain archives or stale build outputs.
5. **Inspect the archive** with `jar tf`, checking against a denylist of dev dependencies and prohibited resources.
6. **Fail the pipeline if a prohibited entry is present**, printing the offending path so it can be fixed.
7. **Pass that exact verified artifact into the deploy/image stage**, rather than rebuilding with another command and bypassing the check.
8. **Inspect the final image** whenever a Dockerfile or buildpack can pull extra files, agents, or layers from the build context outside the JAR.

Attaching a SHA-256 hash to the verified artifact helps prove "the deployed file is the verified file"; a hash **does not prove cleanliness** unless content inspection ran first.

### 11.2 When Building Container Images

A Dockerfile or image builder can pull in more than the executable JAR. Instructions like "copy the entire workspace directory" into the image can leak `.env`, test directories, and build caches. Prefer **copying the exact verified artifact** from the build stage, using `.dockerignore`, and keeping build-time secrets out of image layers.

Example **Dockerfile snippet consuming a pre-built artifact** (not a universal Dockerfile for every CI setup):

```dockerfile
FROM eclipse-temurin:17-jre
WORKDIR /app
COPY target/demo-0.0.1-SNAPSHOT.jar app.jar
ENTRYPOINT ["java", "-jar", "/app/app.jar"]
```

This applies to the Maven JAR example once the file is built, present in the Docker build context, and scanned. For Gradle, change `target/...` to the exact `build/libs/...`; for external-container WAR deployments, base image and entrypoint differ completely. Even when copying a single JAR, **the JAR contents still need inspection**; a Dockerfile cannot "strip" DevTools that was already packaged inside.

### 11.3 Versioned Denylist

Spring Boot's built-in exclusions cover known modules. Organizations may have internal dev tools too; maintain a curated list such as:

```text
# Illustrative coordinates; replace with your project's actual catalog.
org.springframework.boot:spring-boot-devtools
org.springframework.boot:spring-boot-docker-compose
com.example.tools:local-debug-helper
```

Never mistake illustrative coordinates for "detected dependencies." Release governance should update denylists when libraries change and **match exact coordinates**, rather than grepping blindly for `debug` and accidentally blocking legitimate production observability/diagnostics libraries.

## 12. Real-World Scenarios: How a One-Line Edit Causes a Leak

### Scenario A – Gradle: Confusing `developmentOnly` with `runtimeOnly`

Initially:

```groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
}
```

A pull request changes it to:

```groovy
dependencies {
    runtimeOnly 'org.springframework.boot:spring-boot-devtools'
}
```

**Why is this dangerous?** Even though `bootRun` still gets restarts, the dependency is now classified as runtime. Custom archives or `bootJar` can ship it to production. The proper review fix is restoring `developmentOnly` and running a **release build + archive inspection**, rather than only testing that the app boots in `local` mode.

### Scenario B – Maven: `optional` Does Not Mean "Removed from the App"

A project has:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
```

Saying "`optional=true` is present, so the artifact is guaranteed clean" **skips verification**. Maven `optional` primarily governs propagation to other projects; application packaging still depends on Spring Boot Maven Plugin `repackage` and exclusions. What actually proves safety is confirming plugin `excludeDevtools` takes effect, `package` runs `repackage`, and `jar tf` omits the module.

### Scenario C – Switching to WAR While Checking Only `BOOT-INF/lib`

An app migrates from a Boot JAR to a WAR. The legacy scan script checks only `BOOT-INF/lib/spring-boot-devtools`, so it always reports "PASS" even though the WAR carries it inside `WEB-INF/lib` or `WEB-INF/lib-provided`.

**Fix:** detect layout by artifact type and inspect **all three** paths. Enforce the appropriate JAR/WAR checks in CI rather than only documenting them in a wiki.

### Scenario D – Excluding DevTools from the JAR While Still Copying `.env`

The app uses Maven `excludeDevtools=true` or Gradle `developmentOnly`. However, a developer leaves a `.env` file or private key inside `src/main/resources`. It still gets copied into `BOOT-INF/classes` during the build despite DevTools being absent.

**Fix:** keep sensitive data out of the repository and artifacts using proper configuration/secret management; inspect resource outputs and images. **DevTools exclusion is not a secret scanner.**

### Scenario E – Confusing the Docker Compose Module with the Runtime Driver

Local dev uses Docker Compose to launch a database, and the app uses a real database driver. In production, you generally **do not need** `spring-boot-docker-compose` in the executable archive, yet you **still need** the JDBC driver to connect to the production database.

Removing the driver too just because "Compose started the database in dev" will prevent the app from connecting in real deployments. Distinguish the **local service launcher** from the **runtime database connector** before trimming dependencies.

## 13. Decision Checklist: When Should a Tool Be Allowed in a Release?

When reviewing a dependency or helper tool, ask:

1. Is it invoked by **runtime application code**, or used solely by the IDE, build, or tests?
2. Could it enter transitively from another module?
3. Is it in Gradle `developmentOnly` / `testImplementation`, or did it slip into `implementation` / `runtimeOnly`?
4. In Maven, are `scope`/`optional` right, and does Boot `repackage` actually exclude it?
5. Do any `bootJar.classpath`, `bootWar.classpath`, `includeOptional`, or `excludeDevtools=false` overrides alter defaults?
6. If needed in dev, does **excluding it from releases** still preserve full `bootRun`/`spring-boot:run` ergonomics?
7. Does the file sit in `BOOT-INF/lib`, `WEB-INF/lib`, `WEB-INF/lib-provided`, or was it shaded/copied into `classes`?
8. Is there any debug code, `application-local.yml`, test fixture, sample dataset, or secret inside `BOOT-INF/classes`?
9. Is CI scanning the **exact artifact** being deployed and checking the final image rather than scanning a different build?
10. After excluding it, do tests and production-style startup still succeed?

A valid production runtime dependency needs a **clear runtime justification**, not merely developer convenience. Yet "shrinking JAR size" is not the sole goal; never break genuinely needed operational features like health, metrics, or security.

## 14. Verifiable Hands-on Exercises

### Exercise 1 – Maven: From Declaration to Artifact

Using the Maven POM and `DemoApplication` from Sections 4 and 7:

1. Run `./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-devtools`, noting that Maven includes the dependency in the project.
2. Run `./mvnw spring-boot:run` in a properly configured development environment; verify DevTools if active. Stop the application.
3. Run `./mvnw clean package` and locate `target/demo-0.0.1-SNAPSHOT.jar`.
4. Use `jar tf` to inspect `BOOT-INF/lib`. Look for `spring-boot-devtools` and `spring-boot-docker-compose`; explain why they must be **absent**.
5. Run `java -jar target/demo-0.0.1-SNAPSHOT.jar`; verify `/ready` still works.
6. Explain the distinct roles of `<optional>true</optional>`, `<scope>test</scope>`, and `<excludeDevtools>true</excludeDevtools>`.
7. **Without altering production configuration**, on a practice copy only, observe what changes if you temporarily tweak plugin flags. Never ship an intentionally DevTools-bundled artifact into release channels.

### Exercise 2 – Gradle: Comparing Development and Production Classpaths

With `build.gradle` and `DemoApplication` above:

1. Run `./gradlew dependencies --configuration runtimeClasspath`, locate `spring-boot-devtools`, and record its path.
2. Run `./gradlew dependencies --configuration productionRuntimeClasspath`; explain why a `developmentOnly` dependency is absent from production runtime.
3. Run `./gradlew dependencyInsight --dependency spring-boot-devtools --configuration runtimeClasspath` when tracing what pulls it in.
4. Run `./gradlew clean bootJar` and open `build/libs/demo-0.0.1-SNAPSHOT.jar` with `jar tf`.
5. Verify the Bash or PowerShell script from Section 8 outputs **PASS** under the example setup.
6. Run `java -jar` and `GET /ready` to confirm the app does not depend on DevTools to start.
7. On an experimental branch, compare `developmentOnly` vs. `runtimeOnly` without pushing a configuration that ships DevTools to release pipelines.

### Exercise 3 – Controlling WARs, Dev Files, and CI

1. On a valid Spring MVC WAR app, build `bootWar` or Maven repackaged WAR and inspect both `WEB-INF/lib` and `WEB-INF/lib-provided`.
2. Add a non-sensitive placeholder like `private-dev-data.json` in `src/main/resources` to simulate a dev resource. Add appropriate include/exclude rules and verify the file is **absent from the archive**; never use real secrets for testing.
3. Create a CI stage running the script from Section 8 against the **exact artifact path used by the deploy stage**. Test on a copy containing a violating dependency to ensure the stage fails without modifying real release artifacts.
4. If the project builds Docker images, verify the final image holds only approved components and does not copy the whole workspace.

**Completion criteria:** provide evidence from a source build, dependency graph, **the exact executable archive**, repeatable PASS/FAIL check output, and a startup smoke test. Stating only "DevTools auto-disabled" or "the `prod` profile doesn't use it" is insufficient.

## Official Documentation

- Spring Boot Developer Tools (Maven optional / Gradle developmentOnly declarations and packaged behavior): https://docs.spring.io/spring-boot/reference/using/devtools.html
- Spring Boot Maven Plugin – Packaging Executable Archives, `excludeDevtools`/`excludeDockerCompose`/`excludes`: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot Gradle Plugin – Packaging Executable Archives and `developmentOnly`: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot Gradle Plugin – Running Your Application: https://docs.spring.io/spring-boot/3.3/gradle-plugin/running.html
- Spring Boot Gradle Plugin – Reacting to Other Plugins: https://docs.spring.io/spring-boot/3.3/gradle-plugin/reacting.html
- Maven – Introduction to the Dependency Mechanism (`scope`, `optional`): https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle – Dependency Configurations: https://docs.gradle.org/current/userguide/declaring_configurations.html

**Takeaway:** dependency control has at least three layers: **proper declaration and scoping → proper build/repackage exclusion → proving the actual release archive and image contain no prohibited contents**. Skipping the final layer leaves you assuming your configuration works rather than confirming the outcome.