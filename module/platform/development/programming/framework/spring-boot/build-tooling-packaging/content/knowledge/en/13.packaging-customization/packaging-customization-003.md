# Checking the Impact of `provided`, `compileOnly`, and `developmentOnly` Dependencies

## Learning Objectives

When customizing Spring Boot packaging, a dependency may **appear at compile time**, **be present when running tests or running on a developer machine**, yet **be absent from the released JAR/WAR**. The opposite also happens: a dependency declared as `provided`—assumed to be excluded from runtime—is **intentionally packaged by Spring Boot into the executable JAR/WAR**. If you guess solely from the scope or configuration name, it is easy to break a WAR, starve tests of a Servlet runtime, ship DevTools to production, or produce an artifact that works locally but fails in deployment.

This lesson answers a specific question: **which classpaths and archive types do `provided`, `compileOnly`, and `developmentOnly` affect, and how do you prove it using build tools?**

After this lesson, you will be able to:

1. Distinguish Maven `<scope>provided</scope>` from Gradle `compileOnly`, `developmentOnly`, and the War plugin's `providedCompile`/`providedRuntime`.
2. Build a matrix **compile → test → development runtime → production runtime → executable JAR/WAR** for each dependency.
3. Explain why Maven Spring Boot `repackage` **still includes `provided` in an executable JAR**, or places them in `WEB-INF/lib-provided` of an executable WAR.
4. Configure the Spring Boot Gradle plugin to use `developmentOnly` for DevTools, `compileOnly` + `annotationProcessor` for Lombok, and `providedRuntime` for Tomcat when packaging a WAR.
5. Investigate properly with Maven `dependency:tree`/`help:effective-pom`, Gradle `dependencies`/`dependencyInsight`, and `jar tf` on the **final artifact**.
6. Implement CI regression checks, avoiding mixing up plain and executable archives and avoiding treating configuration names as sufficient proof.

**Example versions:** Spring Boot **3.3.13**, Java **17**, compatible Gradle 8.x or Maven 3.6.3+. Commands and dependencies are presented in this context. On Spring Boot 4.x, starters/plugin capabilities may differ: read the documentation for your exact version. You do not need to upgrade a project just to follow the examples.

## 1. Before talking about `provided`, separate five distinct layers

A dependency does not merely have a "present" or "absent" state. It can participate in **multiple classpaths and artifacts**:

| Layer | Question to answer | Example places to observe |
| --- | --- | --- |
| **Dependency declaration** | What does the project declare, and under what scope/configuration? | `pom.xml`, `build.gradle`, `build.gradle.kts` |
| **Compile classpath** | Which classes/APIs does the Java compiler see? | Maven compile scope resolution; Gradle `compileClasspath` |
| **Test classpath** | Which libraries are present when compiling and running tests? | Maven test classpath; Gradle `testCompileClasspath`/`testRuntimeClasspath` |
| **Development runtime** | When running from an IDE or `bootRun`/`spring-boot:run`, which dependencies are present? | Development run task and its runtime classpath |
| **Packaged runtime** | What libraries does `java -jar` carry inside the JAR/WAR? | `BOOT-INF/lib`, `WEB-INF/lib`, `WEB-INF/lib-provided` |
| **External container** | Which extra libraries does the servlet container/JDK/infrastructure provide? | Tomcat/Jetty runtime, image, and server config |

The table has six rows because **"packaged"** and **"provided by the environment"** are often lumped together under the word runtime.

A simple mental model:

```text
                    dependency declaration
                           |
           +---------------+----------------+
           |               |                |
      compile Java     run tests       run in dev
           |               |                |
           +---------------+----------------+
                           |
                      build plugin
                           |
           +---------------+-------------------+
           |                                   |
       plain JAR/WAR                      Boot JAR/WAR
   classes + selective                classes + selective
         content                          dependencies
                                               |
                                      java -jar / container
```

**Do not infer backward without evidence:** a Maven dependency appearing in `dependency:tree` does not mean it is in `BOOT-INF/lib`; Gradle `runtimeClasspath` showing DevTools does not mean `bootJar` includes it; a JAR inside `WEB-INF/lib-provided` does not mean an external Tomcat loads it alongside `WEB-INF/lib`.

### 1.1 Three minimum questions to record in a report

For any dependency under inspection, record its **coordinates** (`groupId:artifactId` or `group:module`), **application module**, **artifact type**, and **verification check**:

1. "During compile/test, where does this class come from?"
2. "When running locally and when packaged for release, where is this class located?"
3. "If the library is excluded from the normal archive, will the container supply it or will it genuinely be missing?"

Without specifying **plain JAR, Boot executable JAR, plain WAR, or Boot executable WAR**, a statement like "`provided` is not packaged" can be true in one context and false in another.

## 2. Maven `provided`: scope semantics and Spring Boot's important exception

### 2.1 Maven dependency scope `provided`

Maven has common scopes: `compile` (default), `runtime`, `test`, `provided`. Under the Maven dependency mechanism:

- `compile`: present on compile, runtime, and test classpaths, and normally propagated to consumers.
- `runtime`: not needed when compiling main sources, but needed at runtime and test time.
- `test`: used only during test compilation and execution.
- **`provided`**: the project needs classes at **compile and test time** but **expects the JDK or container to provide them at runtime**. This scope is **not on Maven's standard runtime classpath** and is not transitively propagated to consumers like `compile` dependencies.

Maven snippet example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-tomcat</artifactId>
    <scope>provided</scope>
</dependency>
```

For a **Spring Boot MVC application deployed to an external Tomcat**, Tomcat is supplied by the external container; marking the embedded server `provided` is intentional. That does not mean you should mark **every** application dependency as `provided`.

Another case: compiling code referencing `jakarta.servlet.http.HttpServletRequest` for a Servlet WAR, where the Servlet API is provided by the external container. This is the classic `provided` concept. In Spring Boot 3.x, the API package is **`jakarta.servlet.*`**, not `javax.servlet.*` from older Java EE generations.

### 2.2 Core Maven matrix (before Spring Boot `repackage`)

| Maven scope | Main compile | Test compile/run | Maven main runtime classpath | External container expected to provide? |
| --- | --- | --- | --- | --- |
| `compile` | Yes | Yes | Yes | No per scope expectation |
| `runtime` | Not needed at main compile | Yes | Yes | No per scope expectation |
| `test` | No | Yes | No | No; test-only |
| **`provided`** | **Yes** | **Yes** | **No** | **Yes, per project declaration** |

This matrix reflects **core Maven classpath rules**; it does not fully describe Spring Boot Plugin behavior or certain custom compiler/test plugin cases.

**Pitfall:** if you run a non-Spring-Boot app using `java -cp ...` with Maven's plain runtime classpath, `provided` libraries may be absent, causing `ClassNotFoundException`. That matches `provided` semantics: you declared the external environment would supply them.

### 2.3 Spring Boot Maven `repackage` can still **include `provided`**

This is the most important point in this lesson. When `spring-boot-maven-plugin` runs `repackage`, the Spring Boot documentation states it **includes the project's `provided` dependencies**, unless excluded by appropriate exclusion rules.

For an **executable JAR**:

```text
pom.xml:
  spring-boot-starter-tomcat  (provided)
               |
               v
maven-jar-plugin:jar             (plain JAR before repackage)
               |
               v
spring-boot:repackage
               |
               v
target/demo-0.0.1-SNAPSHOT.jar
  BOOT-INF/lib/tomcat-embed-core-...jar       <- may be present
  BOOT-INF/lib/tomcat-embed-websocket-...jar  <- depends on graph
```

**Do not use `provided` as a guarantee that "this library will never enter the Boot JAR."** For a Spring Boot executable JAR, Boot aims to create a self-contained artifact for `java -jar`. If you want to omit a specific artifact from output, use Spring Boot Maven Plugin `<excludes>` or revise your design/scope, then inspect the artifact. Caution: dropping a runtime-required dependency can prevent the JAR from running.

For an **executable WAR**:

```text
target/demo-0.0.1-SNAPSHOT.war
  WEB-INF/classes/...                    <- application
  WEB-INF/lib/...                        <- application dependencies
  WEB-INF/lib-provided/tomcat-embed-...  <- provided dependencies
  org/springframework/boot/loader/...    <- supports java -jar
```

Boot places `provided` dependencies in **`WEB-INF/lib-provided`**, avoiding conflicts with classes already supplied by an external container. At the same time, when running the executable WAR with `java -jar`, the Boot launcher can still use them for the embedded environment.

Comparison:

- Maven **plain WAR** packaged by `maven-war-plugin` per scope: `provided` dependencies normally **do not enter `WEB-INF/lib`**.
- Maven **Boot executable WAR** packaged by `repackage`: `provided` is kept in `WEB-INF/lib-provided`—**it does not vanish**.
- Maven **Boot executable JAR**: `provided` can reside in `BOOT-INF/lib` because no external servlet container supplies it when running standalone.

### 2.4 `optional` is not synonymous with `provided`

`<optional>true</optional>` mainly affects **transitive dependency propagation to consuming projects**. It does not mean "the dependency is gone from this project's classpath." A library module may mark a dependency optional for consumers to opt in. With the Spring Boot 3.3 Maven plugin, do not rely on `optional` as a general mechanism to omit dependencies from executable archives; built-in exceptions like `spring-boot-devtools` have their own exclusion handling.

Example:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-devtools</artifactId>
    <optional>true</optional>
</dependency>
```

The Spring Boot Maven Plugin enables `excludeDevtools` by default; this is **distinct** from Maven `optional` semantics. For WARs, classifying DevTools and Docker Compose as optional or provided also interacts with plugin exclusion conditions. Conclusions must rest on **effective POM + plugin configuration + repackaged file**.

### 2.5 When is using `provided` wrong?

- A real JDBC driver that the application must carry and the container does not supply is switched to `provided` merely to shrink size.
- A JSON library, HTTP client, or runtime framework is marked `provided` even though no third party provides it.
- DevTools is placed in `provided` assuming it will never enter an executable JAR.
- A library module marks an API dependency `provided` even though practical consumers do not have that dependency, causing runtime errors in consuming modules.

**Rule:** `provided` is not an "exclude" button. It is a **contract with the runtime environment**; Spring Boot `repackage` intentionally interacts with that contract based on archive type.

## 3. Gradle `compileOnly`: present only at compile time

### 3.1 Gradle Java plugin configurations

When using Gradle `java` or `java-library`:

- `implementation`: dependencies required for **main compile + runtime**.
- `runtimeOnly`: dependencies needed only at runtime, not compile time.
- **`compileOnly`**: needed only on the **main compile classpath**, **absent from runtime classpath**, **not automatically on test classpaths**, and **not packaged into the JAR/WAR by standard mechanisms**.
- `annotationProcessor`: annotation processing tool run during `compileJava`; distinct from `compileOnly`.
- `testCompileOnly`, `testImplementation`, `testRuntimeOnly`, and `testAnnotationProcessor`: configurations dedicated to tests.

Groovy DSL example:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    // Coordinate illustration only; supply an appropriate version or BOM.
    compileOnly 'org.projectlombok:lombok:1.18.36'
    annotationProcessor 'org.projectlombok:lombok:1.18.36'

    testCompileOnly 'org.projectlombok:lombok:1.18.36'
    testAnnotationProcessor 'org.projectlombok:lombok:1.18.36'
}
```

This is a **build snippet demonstrating dependency classification**, not a complete Spring Boot build. `compileOnly` lets the compiler see Lombok annotations and APIs in source code, while `annotationProcessor` runs Lombok to generate getters/constructors at compile time. Declaring only `compileOnly` without providing the processor can cause code using Lombok-generated methods to **fail to compile**.

Once annotation processing emits bytecode, most Lombok-assisted code is compiled straight into the application's own classes. Thus keeping `lombok-...jar` out of runtime is usually **intended**. Still, do not overgeneralize that **every** annotation library is compile-only: an annotation or framework may be read via reflection at runtime and still need a runtime dependency.

### 3.2 Why can't `compileOnly` replace `providedRuntime`?

Suppose a Spring MVC app needs Tomcat classes to run **web integration tests**. If you place Tomcat in `compileOnly`:

- Source code may compile because the compiler sees the classes.
- However, **`testRuntimeClasspath` does not carry it automatically**, because main's `compileOnly` is not part of main's or test's runtime.
- Spring tests may fail to start the embedded web server; the failure surfaces at `test` rather than `compileJava`.
- A Boot executable WAR meant to run via `java -jar` also will not receive Tomcat from `compileOnly`, since standard runtime/War packaging rules do not package it.

For an external container, using a configuration present in **dev test/runtime** yet **separated by WAR packaging** is cleaner: the Gradle War plugin's `providedRuntime`.

### 3.3 Test compilation does not inherit main `compileOnly` automatically

A common mistake: `src/main/java` using Lombok compiles, while `src/test/java` using Lombok annotations fails. You added Lombok to main's `compileOnly`/`annotationProcessor` without declaring `testCompileOnly` and `testAnnotationProcessor` for tests.

Sometimes tests compile yet fail at runtime due to a missing library because an app class references at runtime a dependency marked `compileOnly`. The fix is not blindly dumping all `compileOnly` into `testRuntime`; analyze **whether it is genuinely a compile-time API or actually used at runtime**.

### 3.4 Reports to inspect

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testCompileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

On Windows PowerShell use `.\gradlew.bat` instead of `./gradlew`.

**Expected observations** if a dependency is declared only as `compileOnly` and not pulled into runtime by another dependency:

- Present in `compileClasspath`.
- Absent from `runtimeClasspath`.
- Not automatically present in `testCompileClasspath`/`testRuntimeClasspath`.
- Absent from `BOOT-INF/lib` of `bootJar`.

If you still see that module at runtime, check whether another starter/`implementation`/`runtimeOnly` pulls it back in. **"Only in `compileOnly`"** is what allows predicting absence from configuration; the final artifact must still be verified.

## 4. Gradle `developmentOnly`: used in development, excluded from the Boot archive

### 4.1 Configuration added by the Spring Boot Gradle plugin

When the Spring Boot Gradle plugin is applied with the Java plugin, `developmentOnly` is used for dependencies needed when **running during development** that should not appear in the release executable archive. Typical examples are:

- `org.springframework.boot:spring-boot-devtools`: restarts, LiveReload, and developer utilities.
- `org.springframework.boot:spring-boot-docker-compose`: Docker Compose service integration during local runs in supported Spring Boot versions.

Example:

```groovy
dependencies {
    developmentOnly 'org.springframework.boot:spring-boot-devtools'
    developmentOnly 'org.springframework.boot:spring-boot-docker-compose'
}
```

In this example, versions of these modules are managed by the `spring-boot-dependencies` BOM via Spring Boot dependency management. If your project does not apply that BOM mechanism, declare versions or use Gradle's native `platform` appropriately.

Unlike `compileOnly`, `developmentOnly` can participate in **development-mode `runtimeClasspath`** so `bootRun`/IDE launches include those helper tools. The Spring Boot Gradle plugin also provides `productionRuntimeClasspath` to distinguish production runtime dependencies from development-only ones.

This is **not** a Spring `dev`/`prod` profile flag. Simply setting `spring.profiles.active=prod` **does not remove the DevTools JAR from the artifact**; `developmentOnly` acts on the **build classpath and packaging**, whereas profiles act on **Spring runtime configuration**.

### 4.2 Do not treat `runtimeClasspath` as an exact mirror of the Boot JAR

With `developmentOnly`, the development `runtimeClasspath` may **display DevTools**. However, per Spring Boot Gradle plugin documentation, `developmentOnly` dependencies are **excluded from the executable JAR/WAR by default**.

```text
Gradle:
    implementation starter-web
    developmentOnly devtools
             |
             +--> bootRun / dev runtimeClasspath ----> may show DevTools
             |
             \--> bootJar / bootWar output ----------> DevTools excluded by default
```

Therefore, these two statements do not contradict each other:

> "`./gradlew dependencies --configuration runtimeClasspath` shows DevTools."

> "`jar tf build/libs/demo.jar` does not contain `spring-boot-devtools-...jar`."

The two commands answer **two different questions**. Conversely, if you put DevTools in `implementation` or `runtimeOnly`, or customize `bootJar.classpath` to include `developmentOnly`, the default exclusion guarantee no longer holds.

### 4.3 Gradle verification commands

```bash
# Run only where the Java plugin and appropriate Boot plugin are applied.
./gradlew dependencies --configuration runtimeClasspath

# Production classpath provided by the Spring Boot Gradle plugin.
./gradlew dependencies --configuration productionRuntimeClasspath

# What pulls in DevTools—is it from developmentOnly?
./gradlew dependencyInsight --dependency spring-boot-devtools \
  --configuration runtimeClasspath

# Package the Boot JAR and inspect the final file:
./gradlew clean bootJar
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
```

**Do not assume every Gradle project has `developmentOnly`/`productionRuntimeClasspath`:** these configurations come from the Spring Boot Gradle plugin in a compatible Java setup. If the command reports they do not exist, check the exact module, whether the plugin has `apply false`, the Gradle Wrapper/Boot version, and Java configuration first.

**Overlap note:** if a module enters via both `developmentOnly` and another valid runtime dependency, verify the actual resolution and packaging outcome. Do not infer from a single declaration line that zero bytes of that `group:artifact` exist in the output.

### 4.4 `testAndDevelopmentOnly` (where supported by plugin version)

In Spring Boot 3.3, the Gradle plugin also provides `testAndDevelopmentOnly` for dependencies needed **during development and testing** but not in the production archive. This classification is helpful for certain local/test support tools. It is a **supplemental** configuration, not a universal replacement for `developmentOnly` or `testImplementation`; use it when test requirements and your plugin version align.

When investigating why a dependency appears in test runtime or dev runtime yet is absent from the packaged archive, check any custom development/test configurations declared by the project.

## 5. Gradle War plugin: `providedCompile` and `providedRuntime` are not `compileOnly`

### 5.1 Two configurations that appear only when `war` is applied

The Gradle War plugin automatically applies the Java plugin and adds these configurations:

- **`providedCompile`**: dependencies needed at compile time and supplied by an external servlet container at deployment. Per the Gradle War plugin, they are present on **main/test compile and runtime classpaths**, yet excluded from the **plain WAR**.
- **`providedRuntime`**: dependencies needed at runtime and supplied by an external servlet container. They are present on **main/test runtime classpaths**, yet excluded from the **plain WAR**.

| Configuration with Gradle War plugin | Main compile | Main/test runtime | Plain `war`, `WEB-INF/lib` | Purpose |
| --- | --- | --- | --- | --- |
| `implementation` | Yes | Yes | Usually yes | Self-contained app libraries |
| `compileOnly` | Yes | **No** from this config alone | No | Compile-only APIs/annotations |
| `providedCompile` | Yes | **Yes** | **Excluded** | Container-provided APIs, also used in tests |
| `providedRuntime` | Not added just for compile | **Yes** | **Excluded** | Runtime supplied by external container |
| `testImplementation` | Test only | Test only | No | Test libraries |
| `developmentOnly` (Boot plugin) | Not a compile requirement | Dev runtime | Excluded from Boot archive by default | DevTools and local tools |

Cells describe **direct configuration effects**, not immutable guarantees if a module is pulled in via another path or custom task classpath.

### 5.2 Why does `providedRuntime` fit Spring Boot WARs?

Using Spring Boot 3.3 with MVC Servlet and Tomcat:

```groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
```

This is a **Groovy DSL snippet**: a complete build also needs `group`, `version`, `repositories`, Java toolchain, and application code. `war` applies `java` automatically. Using `providedRuntime`:

1. **Compile/test:** compile-time APIs come from appropriate app dependencies; Tomcat runtime is still on the test classpath, giving Spring web integration tests the server environment they need.
2. **Plain WAR:** Tomcat is treated as container-provided and **stays out of `WEB-INF/lib`** in the plain WAR per Gradle War plugin rules.
3. **Boot executable WAR:** the Spring Boot plugin **places `providedRuntime` into `WEB-INF/lib-provided`**, allowing the WAR to run via `java -jar` while still deploying cleanly to an external Tomcat without mixing embedded Tomcat into `WEB-INF/lib`.
4. **If `compileOnly` were used instead:** Tomcat would not automatically appear in test runtime and would not be placed into `WEB-INF/lib-provided` via `providedRuntime`; web integration tests or `java -jar` could fail.

Spring Boot documentation **prefers `providedRuntime` over `compileOnly`** for the embedded Servlet container in a WAR. This is not a blanket claim that "all `compileOnly` is wrong," but guidance for container-provided dependencies that **are still needed to run tests and executable WARs**.

### 5.3 These configurations are transitive

The Gradle War plugin's `providedCompile`/`providedRuntime` affect **transitive dependencies**. When a library is marked provided, dependencies it pulls in can also be excluded from `WEB-INF/lib` of a plain WAR, **even if the same coordinates are also declared through an `implementation` branch**.

Hypothetical graph example:

```text
implementation --> app-component --------> shared-util:1.0
providedRuntime --> container-helper ----> shared-util:1.0
```

You cannot conclude `shared-util` is guaranteed to appear in `WEB-INF/lib` solely because of the `implementation` edge. The Gradle War plugin warns about propagation of provided configurations; inspect the resolved graph and actual WAR file. When fine-tuning is required, unwanted transitivity can be avoided with an artifact-only dependency like `group:module:version@jar` in appropriate cases, though you must evaluate carefully since dropping transitives can leave the runtime missing classes.

### 5.4 Are `providedCompile` and `providedRuntime` interchangeable?

Not completely:

- If Java code **directly imports** a container-only API, `providedCompile` fits better in the Gradle WAR model.
- If Java code does not need that API to compile yet needs the server/runtime in tests or an executable WAR, `providedRuntime` is the typical choice.
- Both can be used together when artifacts genuinely serve distinct roles.
- Do not put all of `spring-boot-starter-web` into `provided` just because Tomcat is `provided`; `starter-web` pulls in Spring MVC/JSON components that an **external Tomcat does not provide**.
- Inspect resolved libraries **artifact by artifact**, avoiding treating the whole Spring stack as "the container will have it."

## 6. Three classic cases: Lombok, DevTools, Tomcat

| What needs to happen? | Appropriate Maven | Appropriate Gradle | Verification point |
| --- | --- | --- | --- |
| Generate getters/constructors with Lombok at compile time | Maven Compiler Plugin annotation processor, appropriately classified Lombok dependency; configure plugin if runtime exclusion needed | `compileOnly` + `annotationProcessor`, plus test variants if Lombok is used in tests | Compiled classes have methods; `lombok-...jar` is absent from Boot runtime archive |
| Have DevTools in development, not released | `spring-boot-devtools` typically declared optional; Boot Maven `excludeDevtools=true` (default) | `developmentOnly` | Present during dev run; no `spring-boot-devtools-...jar` in Boot JAR/WAR |
| Deploy Boot MVC WAR to external Tomcat | `spring-boot-starter-tomcat` with `<scope>provided</scope>` | `providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'` | Boot WAR has `WEB-INF/lib-provided`; plain WAR omits container JARs from `WEB-INF/lib` |
| Run standalone Boot MVC JAR | Tomcat can be compile/runtime or even `provided` since Boot `repackage` includes `provided`, though don't abuse it | Tomcat needed at Boot JAR runtime, do not put in `compileOnly` | `BOOT-INF/lib/tomcat-embed-...jar` is present when embedded Tomcat is used |
| Use JUnit/Mockito for testing | `<scope>test</scope>` | `testImplementation`/`testRuntimeOnly` | `test` runs; no JUnit in packaged Boot runtime |

**Lombok pitfall:** `compileOnly` is a Gradle configuration, not a standard **Maven scope**. Do not write `<scope>compileOnly</scope>` in `pom.xml`. Maven uses dependency scopes, compiler plugin config, and annotation processor paths accordingly.

**DevTools pitfall:** Spring Boot DevTools also auto-disables itself when running a packaged application. However, **"auto-disabled at runtime"** does **not mean** **"absent from the archive"**; only `jar tf` proves whether the final artifact contains that JAR.

## 7. Complete Maven example: `provided` Tomcat and unreleased DevTools

Create a Spring Boot MVC project using Maven Wrapper and Java 17. Illustrative `pom.xml`:

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
    <packaging>war</packaging>

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
            <artifactId>spring-boot-starter-tomcat</artifactId>
            <scope>provided</scope>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-devtools</artifactId>
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
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
```

Explanation:

- `<packaging>war</packaging>` triggers Maven WAR packaging before Boot `repackage`.
- `spring-boot-starter-tomcat` with scope `provided` declares that an **external servlet container** provides this part when deploying the WAR.
- `spring-boot-starter-web` remains an application dependency: external containers do not automatically supply Spring MVC/Jackson.
- Optional `spring-boot-devtools` supports development, while `excludeDevtools` configures Boot packaging not to release it.
- `spring-boot-starter-test` is in `test` scope; not needed in the runtime archive.
- `spring-boot-starter-parent` already configures the `repackage` execution for the Spring Boot Maven plugin; in a project **importing only the BOM without inheriting the parent**, bind the execution explicitly to produce an executable archive.
- Actual JAR/WAR contents and dependency versions may differ with profiles, different parents, exclusions, or overrides. Verify via commands.

### 7.1 A Java 17+ class runnable in both embedded and external WAR modes

Create `src/main/java/com/example/demo/DemoApplication.java`:

```java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder app) {
        return app.sources(DemoApplication.class);
    }

    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
```

This is a **complete Java class inside a Spring Boot project with dependencies**, not runnable via standalone `javac DemoApplication.java` without the Spring classpath. `SpringBootServletInitializer` enables deployment to an external Servlet container; `main` serves `java -jar`/`spring-boot:run`. On the default port 8080 without changing the context path, calling `GET /ping` on the embedded server returns the response body:

```text
pong
```

That is the **HTTP response body** of the Java `ping()` method, not the full stdout/Spring Boot logs. When deploying the WAR to an external Tomcat, the URL may be `/demo/ping` or another context path chosen by the container.

### 7.2 Spring MVC context startup test

`src/test/java/com/example/demo/DemoApplicationTests.java`:

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

This test verifies the **Spring context loads**. It does not verify the HTTP endpoint, prove external Tomcat deployment succeeds, or confirm the archive excluded DevTools. For an HTTP integration test, use `@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)` with an appropriate test client and Servlet runtime on the test classpath.

### 7.3 Build and conditional expectations

```bash
./mvnw test
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
./mvnw help:effective-pom -Doutput=effective-pom.xml
./mvnw clean package
jar tf target/demo-0.0.1-SNAPSHOT.war
```

With a compatible POM, app, and environment, in the **Spring Boot executable WAR** expect files similar to:

```text
WEB-INF/classes/com/example/demo/DemoApplication.class
WEB-INF/lib/spring-webmvc-...jar
WEB-INF/lib-provided/tomcat-embed-core-...jar
```

The `...` placeholders denote real versions chosen by the BOM/graph, not literal filenames. Do **not** expect `spring-boot-devtools` or JUnit libraries inside the WAR's runtime directories. Still inspect the actual built file: do not mistake an expectation table for an execution log.

Run the executable WAR:

```bash
java -jar target/demo-0.0.1-SNAPSHOT.war
```

In another terminal once the server is up:

```bash
curl http://localhost:8080/ping
```

If an external Tomcat is used, only a WAR compatible with its Servlet/Jakarta API and initialization model will deploy successfully. `provided` and `lib-provided` handle dependency classification, and **do not guarantee server compatibility by themselves**.

### 7.4 Switching Maven `war` to `jar`

Change `<packaging>war</packaging>` to `<packaging>jar</packaging>` on an experimental copy/branch and re-run `./mvnw clean package`. Under Boot Maven `repackage`, a `provided` dependency like Tomcat **can still appear** in `BOOT-INF/lib` of the executable JAR. This creates a clear contrast:

| Tomcat dependency with `provided` scope | Maven Boot WAR | Maven Boot JAR |
| --- | --- | --- |
| Where is it placed? | `WEB-INF/lib-provided` | `BOOT-INF/lib` |
| Can it run with `java -jar`? | Yes with a valid executable WAR | Yes with a valid executable JAR |
| For external servlet container deploy? | WAR is built for that | Not the traditional Servlet WAR deploy model |
| Does it prove `provided` is never packaged? | **No** | **No** |

This is not a recommendation to mark all JAR app dependencies `provided`; it simply demonstrates **Spring Boot `repackage` behavior** that differs from core Maven scope expectations and must be verified.

## 8. Gradle JAR example: `compileOnly` Lombok and `developmentOnly` DevTools

### 8.1 Complete Groovy DSL `build.gradle`

`settings.gradle`:

```groovy
rootProject.name = 'demo'
```

`build.gradle`:

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

    compileOnly 'org.projectlombok:lombok'
    annotationProcessor 'org.projectlombok:lombok'
    testCompileOnly 'org.projectlombok:lombok'
    testAnnotationProcessor 'org.projectlombok:lombok'

    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}
```

In this example, the dependency-management plugin imports the matching Boot BOM and supplies versions for BOM-managed artifacts. If a project uses native Gradle platforms instead, declare the BOM/constraints properly rather than just deleting the dependency-management plugin.

You can reuse the **same `DemoApplication.java`** from section 7, even though that class does not need Lombok; Lombok here demonstrates compile-time tool classification. To verify annotation processing works, add the small classes below.

### 8.2 Class using Lombok for compile-time verification

Create `src/main/java/com/example/demo/Greeting.java`:

```java
package com.example.demo;

import lombok.Getter;

@Getter
public final class Greeting {
    private final String value;

    public Greeting(String value) {
        this.value = value;
    }
}
```

`@Getter` makes Lombok generate `getValue()` in the compiled class. Create `src/main/java/com/example/demo/GreetingProbe.java`:

```java
package com.example.demo;

public final class GreetingProbe {

    public static void main(String[] args) {
        Greeting greeting = new Greeting("hello");
        System.out.println(greeting.getValue());
    }
}
```

With Gradle `compileOnly + annotationProcessor`, after `./gradlew classes` you can invoke this small program **without the Lombok JAR at runtime**:

```bash
./gradlew classes
java -cp build/classes/java/main com.example.demo.GreetingProbe
```

Exact stdout **from `GreetingProbe` itself**, once both classes compile cleanly:

```text
hello
```

The command above targets macOS/Linux or compatible environments; on Windows use `java -cp build\classes\java\main com.example.demo.GreetingProbe`. `GreetingProbe` is a Java 17+ program not using Spring Boot runtime; it uses only compiled bytecode. **Do not run `javac Greeting.java` directly** without supplying the Lombok annotation processor. You do not need `lombok-...jar` in `BOOT-INF/lib` for `getValue()` to exist.

### 8.3 Inspect the corresponding classpaths

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencies --configuration productionRuntimeClasspath
./gradlew dependencyInsight --dependency lombok --configuration compileClasspath
./gradlew dependencyInsight --dependency spring-boot-devtools --configuration runtimeClasspath
./gradlew clean bootJar
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
```

Expected observations **assuming no other configuration pulls the modules in**:

- Lombok: appears in `compileClasspath`, **not** in `runtimeClasspath`/`BOOT-INF/lib` solely from `compileOnly`.
- DevTools: may appear in development `runtimeClasspath`, **not** in `productionRuntimeClasspath`/`BOOT-INF/lib` thanks to `developmentOnly`.
- Embedded Tomcat: still packaged in `BOOT-INF/lib` via `spring-boot-starter-web` since the standalone web app needs a server.
- JUnit: present in test graphs, absent from packaged runtime archive.

Not seeing Lombok in `runtimeClasspath` does not by itself prove annotation processing generated the method; that is verified by `./gradlew classes` and running `GreetingProbe`.

### 8.4 Kotlin DSL equivalent

`build.gradle.kts` snippet, applied to a project with matching plugins and BOM:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    compileOnly("org.projectlombok:lombok")
    annotationProcessor("org.projectlombok:lombok")
    testCompileOnly("org.projectlombok:lombok")
    testAnnotationProcessor("org.projectlombok:lombok")
    developmentOnly("org.springframework.boot:spring-boot-devtools")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

This is a **snippet**: to compile and run from scratch you also need `group`, `version`, `java.toolchain`, `repositories`, and `tasks.test.useJUnitPlatform()` as in Groovy DSL. Do not mix Groovy `compileOnly '...'` syntax into `.gradle.kts`.

## 9. Gradle WAR example: `providedRuntime` and executable WAR

On a copy of the Gradle JAR project from section 8, change the `java` plugin to `war`; `war` already applies Java. Keep Spring Boot/dependency management, and update Tomcat as follows:

```groovy
plugins {
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    // External container will provide Tomcat.
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'

    // Development-only dependency.
    developmentOnly 'org.springframework.boot:spring-boot-devtools'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}
```

The snippet above shows only the changes, not a complete `build.gradle`. Keep `repositories`, Java toolchain, group/version, and test configuration from section 8 if testing on a copy. `DemoApplication` from section 7 already extends `SpringBootServletInitializer`, making it suitable for external Servlet container testing.

Kotlin DSL equivalent (snippet):

```kotlin
plugins {
    war
    id("org.springframework.boot") version "3.3.13"
    id("io.spring.dependency-management") version "1.1.7"
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    providedRuntime("org.springframework.boot:spring-boot-starter-tomcat")
    developmentOnly("org.springframework.boot:spring-boot-devtools")
    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
```

### 9.1 `war` and `bootWar` tasks do not share the same contents

```bash
./gradlew clean war bootWar
jar tf build/libs/demo-0.0.1-SNAPSHOT-plain.war
jar tf build/libs/demo-0.0.1-SNAPSHOT.war
```

With the modern Spring Boot Gradle plugin, `war` typically gets the `plain` classifier to avoid colliding with `bootWar`. Filenames may vary if the project customizes `archiveClassifier`/`archiveBaseName`.

| Archive location | Plain WAR from `war` | Executable WAR from `bootWar` |
| --- | --- | --- |
| `WEB-INF/classes` | Present | Present |
| `WEB-INF/lib` (app dependencies) | Present | Present |
| `WEB-INF/lib-provided` (provided servlet runtime) | Not how plain WAR normally packages | Present with `providedRuntime` |
| Spring Boot launcher | Absent by default | Present |
| Run with `java -jar` | Not the default target | Supported for valid Boot WAR |
| Deploy to external Servlet container | Possible, for valid Servlet app | Possible, with right layout and initializer |

**Do not judge by filename alone.** Open the actual archive and confirm Tomcat is not wrongly placed in `WEB-INF/lib` while `WEB-INF/lib-provided` exists in the Boot WAR.

### 9.2 Why do tests still have Tomcat?

The Gradle War plugin keeps `providedRuntime` on **main/test runtime classpaths**, even while excluding the dependency from the plain WAR. Hence integration tests have the embedded servlet runtime to boot the application. This is the crucial difference from `compileOnly`—a compile-only dependency will not automatically appear in test runtime.

### 9.3 WAR for an external container is more than a classifier

To deploy to an external Tomcat, beyond dependency placement you also need:

- A Spring Boot app using **Spring MVC/Servlet**, rather than packaging a pure reactive Netty app as a traditional Servlet WAR.
- The main class extending `SpringBootServletInitializer` when container-triggered startup is needed.
- External container Servlet/Jakarta API **compatible** with your Spring Boot version.
- Correct context path, JDK version, security, and deployment configuration.
- Verification via **actual deployment** to the external container, not `java -jar` alone.

A passing `bootWar` build only proves build/packaging, not that external deployment succeeds.

## 10. Evidence-based measurement: graph + classpath + archive contents

### 10.1 Unified workflow

To answer "is dependency X included in or excluded from the artifact?", follow these steps in order:

**Step 1 – Define the target.** Record build system, module, Spring Boot plugin version, archive type, dependency coordinates, and runtime expectation.

**Step 2 – Inspect declarations.** Look for Maven `<scope>provided</scope>`/`<optional>`/plugin `<excludes>`; Gradle `compileOnly`/`developmentOnly`/`providedRuntime` and task classpaths.

**Step 3 – Confirm the resolved dependency graph.** Never treat one declaration line as the final outcome; a dependency can be pulled in via another edge or have its version changed by constraints/BOM.

**Step 4 – Confirm the intended classpath.** Maven scopes vs. Gradle compile/test/runtime/`productionRuntimeClasspath`; ensure you target the right module.

**Step 5 – Build the right artifact.** Maven `package` with Boot repackage, or Gradle `bootJar`/`bootWar`. Do not inspect plain files, Maven `.jar.original`, or stale artifacts.

**Step 6 – Run `jar tf` on the artifact and check target paths.** For WARs inspect both `WEB-INF/lib` and `WEB-INF/lib-provided`; for JARs inspect `BOOT-INF/lib`.

**Step 7 – Smoke test.** Run `java -jar` or deploy the WAR to the target external container; investigate runtime failures if a class declared `provided` is not actually supplied by the environment.

### 10.2 Maven: inspect the graph and effective POM

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-starter-tomcat
./mvnw dependency:tree -Dincludes=org.springframework.boot:spring-boot-devtools

# POM model after parents, profiles, and plugin configuration:
./mvnw help:effective-pom -Doutput=effective-pom.xml

# Build the final artifact, if clean is allowed in your workspace:
./mvnw clean package
```

`dependency:tree` is evidence of the project's resolved graph; `effective-pom.xml` clarifies scopes and plugin settings. Do **not** treat Tomcat's absence from Maven's plain runtime classpath as proof it is absent from the Spring Boot repackaged JAR/WAR.

### 10.3 Gradle: use the right configuration

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencies --configuration testCompileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
./gradlew dependencies --configuration productionRuntimeClasspath

./gradlew dependencyInsight \
  --dependency spring-boot-devtools \
  --configuration runtimeClasspath

./gradlew dependencyInsight \
  --dependency lombok \
  --configuration compileClasspath

./gradlew dependencyInsight \
  --dependency spring-boot-starter-tomcat \
  --configuration runtimeClasspath
```

`productionRuntimeClasspath` is a configuration name from the Spring Boot Gradle plugin, not Gradle core. Invoke it only in a project/module where the plugin is applied such that the configuration exists. In multi-module projects, use `./gradlew :app:dependencies --configuration runtimeClasspath` if `:app` is the real app module. `dependencyInsight` explains versions and inclusion paths; it **does not by itself tell you which files were packaged in the archive**.

**Do not try to resolve `compileOnly` as a resolvable configuration on modern Gradle:** it is a declarable bucket. To inspect compilation dependencies, query `compileClasspath`.

### 10.4 Inspecting executable JAR/WAR on macOS/Linux

After building, run the command matching your real artifact:

```bash
# Maven executable JAR:
jar tf target/demo-0.0.1-SNAPSHOT.jar

# Maven executable WAR:
jar tf target/demo-0.0.1-SNAPSHOT.war

# Gradle executable JAR:
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar

# Gradle executable WAR:
jar tf build/libs/demo-0.0.1-SNAPSHOT.war
```

Do not run all four against one project if that project does not produce all four artifacts. In a Boot JAR look for `BOOT-INF/lib/`; in a Boot WAR look for `WEB-INF/lib/` and `WEB-INF/lib-provided/`. Structural files `META-INF/MANIFEST.MF` and the Boot loader distinguish executable archives from plain ones.

To search for specific artifacts:

```bash
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar | grep -E '^BOOT-INF/lib/.*(lombok|spring-boot-devtools|tomcat-embed).*\.jar$'

jar tf build/libs/demo-0.0.1-SNAPSHOT.war | grep -E '^WEB-INF/(lib|lib-provided)/.*(spring-boot-devtools|tomcat-embed).*\.jar$'
```

These are **suggested queries for the example artifacts**, not commands guaranteed to print matches. If `grep` finds nothing, verify the artifact path, version, folder layout, and whether a dependency was renamed/shaded. In a WAR, a module may appear in `lib-provided` instead of `lib`.

### 10.5 Windows PowerShell

```powershell
.\gradlew.bat clean bootJar
$archive = "build\libs\demo-0.0.1-SNAPSHOT.jar"
$entries = & jar tf $archive

if ($LASTEXITCODE -ne 0) {
    throw "Cannot inspect archive: $archive"
}

$entries | Select-String -Pattern "BOOT-INF/lib/(lombok|spring-boot-devtools|tomcat-embed)"
```

For Maven Wrapper use `.\mvnw.cmd`, with the JAR under `target\...`; WARs contain `WEB-INF`. This command **prints matching lines**, not a guarantee that those dependencies must appear. When verifying exclusions, having no matching lines is expected for Lombok/DevTools, whereas embedded Tomcat in a Boot JAR may be **required**.

## 11. Automated checks: what must be absent and what must be present?

A useful CI gate must express **policy for a specific artifact**. For example, in the section 8 Spring Boot JAR: DevTools and Lombok must not sit in `BOOT-INF/lib`, while embedded Tomcat may be required by the web app.

### 11.1 Bash check for an executable JAR

```bash
#!/usr/bin/env bash
set -euo pipefail

artifact="build/libs/demo-0.0.1-SNAPSHOT.jar"

if [[ ! -f "$artifact" ]]; then
    echo "FAIL: release artifact missing"
    exit 1
fi

entries="$(jar tf "$artifact")"

if ! grep -Fq 'BOOT-INF/classes/' <<< "$entries"; then
    echo "FAIL: not an expected Boot JAR layout"
    exit 1
fi

# These are the two modules the JAR example intentionally does not package.
deny='^BOOT-INF/lib/(lombok|spring-boot-devtools)-[^/]+[.]jar$'
if grep -E "$deny" <<< "$entries"; then
    echo "FAIL: compile-only or development-only artifact packaged"
    exit 1
fi

# The example app uses embedded Tomcat to run the web server.
if ! grep -Eq '^BOOT-INF/lib/tomcat-embed-core-[^/]+[.]jar$' <<< "$entries"; then
    echo "FAIL: expected embedded Tomcat missing"
    exit 1
fi

echo "PASS: Boot JAR dependency policy satisfied"
```

When the artifact **has the right layout**, **lacks the two forbidden modules**, and **includes embedded Tomcat** as required, stdout printed by **the script** is:

```text
PASS: Boot JAR dependency policy satisfied
```

This is a **conditional expected result**, not output from a live execution. If a forbidden module is present, the script prints the offending file and exits 1. If Tomcat is missing or a plain JAR was picked by mistake, the gate also fails. Customize the denylist/allowlist to fit real needs instead of applying it verbatim to non-Servlet apps.

### 11.2 Bash check for an executable WAR

For the Gradle WAR in section 9:

```bash
#!/usr/bin/env bash
set -euo pipefail

artifact="build/libs/demo-0.0.1-SNAPSHOT.war"
entries="$(jar tf "$artifact")"

if ! grep -Fq 'WEB-INF/classes/' <<< "$entries"; then
    echo "FAIL: unexpected WAR layout"
    exit 1
fi

if ! grep -Eq '^WEB-INF/lib-provided/tomcat-embed-core-[^/]+[.]jar$' <<< "$entries"; then
    echo "FAIL: Tomcat missing from lib-provided"
    exit 1
fi

if grep -Eq '^WEB-INF/lib/tomcat-embed-core-[^/]+[.]jar$' <<< "$entries"; then
    echo "FAIL: embedded Tomcat wrongly placed in WEB-INF/lib"
    exit 1
fi

if grep -Eq '^WEB-INF/(lib|lib-provided)/spring-boot-devtools-[^/]+[.]jar$' <<< "$entries"; then
    echo "FAIL: DevTools packaged"
    exit 1
fi

echo "PASS: Boot WAR dependency policy satisfied"
```

With a properly packaged sample WAR, the script prints:

```text
PASS: Boot WAR dependency policy satisfied
```

If `jar tf` fails, `set -e` stops the shell immediately. This snippet only applies when **policy expects Tomcat in `lib-provided`**. If the project uses Jetty/Undertow or a custom Boot layout, adjust the conditions accordingly. The gate must run on the **exact file used by the deploy stage**, not an arbitrary file in `build/libs`.

### 11.3 Do not over-rely on "absent from ZIP" to guarantee system safety

Even when `spring-boot-devtools-*.jar` is absent from the archive:

- A developer might have copied debug classes into `BOOT-INF/classes`.
- A debug agent might be attached at runtime via `-javaagent`.
- Dockerfile/image layers might introduce extra files outside the JAR.
- A custom startup script's runtime classpath might differ from the Boot launcher's classpath.
- A library might be **shaded/relocated** under a new name.

Thus dependency CI gates are necessary controls, but do not replace security reviews, secret scanning, smoke tests, or final image inspection.

## 12. Common errors when changing scopes/configurations

| Symptom | Possible cause | Check and resolution |
| --- | --- | --- |
| Java compiles yet `java -jar` fails with `ClassNotFoundException` | Runtime dependency placed in `compileOnly` or excluded from artifact | Check `runtimeClasspath`, `BOOT-INF/lib`, and import/runtime call stack |
| Maven `provided` still seen in Boot JAR | Boot Maven `repackage` **intentionally includes `provided`** | Documented behavior, not automatically a bug |
| Maven Boot WAR puts Tomcat in `lib-provided` | Boot uses WAR layout supporting both `java -jar` and external containers | Verify `WEB-INF/lib-provided` and server startup |
| Plain WAR lacks Tomcat in `WEB-INF/lib` | `providedRuntime`/`providedCompile` assumes external container supplies it | Intended design when deploying to compatible container |
| Gradle `compileOnly` class works in main, tests fail with missing class | Main `compileOnly` is not on test classpaths | Add appropriate dependency for tests if needed; do not dump into production runtime |
| Lombok annotation recognized yet `getValue()` not generated | Has `compileOnly` but lacks `annotationProcessor` | Configure both; run `compileJava` to verify |
| DevTools appears in `runtimeClasspath` yet missing from Boot JAR | `developmentOnly` is working as intended | Compare `productionRuntimeClasspath` and `jar tf`; do not call it a build bug |
| DevTools appears in `BOOT-INF/lib` | Put in `implementation`/`runtimeOnly` or custom Boot task classpath | Move to `developmentOnly`/check overrides; rebuild |
| `providedRuntime` reports Unknown configuration | Gradle `war` plugin not applied to that project | Check `plugins`, `:module:tasks`, declare in the right module |
| Servlet API compiles yet external WAR fails to run | External container has wrong Jakarta Servlet version or initializer/config issue | Check `SpringBootServletInitializer`, server logs, compatibility |
| Web integration test breaks after replacing `providedRuntime` with `compileOnly` | Tomcat missing from test runtime | Restore `providedRuntime` if following WAR model |
| Gradle `war` has fewer dependencies than expected despite `implementation` edge | `provided` configurations propagate transitively | Check `dependencyInsight` and WAR contents; evaluate transitivity |
| Maven `dependency:tree` shows dependency yet JAR lacks it | Scope/exclusion, `repackage` config, different artifact or version | Compare effective POM, plugin config, and final JAR |
| Gradle `dependencies --configuration compileOnly` fails to resolve | `compileOnly` is declarable, not resolvable like `compileClasspath` | Use `compileClasspath` |
| Build outputs both `-plain.jar` and executable JAR | Gradle `jar` and `bootJar` emit two archive types | Select the right task output; avoid wildcards |
| Maven outputs `.jar.original` | `repackage` backs up the pre-Boot JAR | Inspect the main repackaged file, never deploy `.original` |
| Changed scope to shrink size and app crashes | No actual runtime provider exists | Revert scope, identify runtime-required dependencies before optimizing |
| CI gate passes yet deployed image fails | Deploy stage used a different artifact/image than scanned | Pin hashes/digests and ensure the verified artifact is deployed |

### 12.1 Special case: `developmentOnly` does not automatically make test runtime match dev runtime

When designing tests, distinguish:

- `developmentOnly` serves **development-only** dependencies.
- `testImplementation` and `testRuntimeOnly` serve **tests**.
- `testAndDevelopmentOnly` (when available) serves combined **test + dev** needs.

Do not place an essential test library into `developmentOnly` assuming every test classpath will inherit it. If tests need it, declare it intentionally in test configurations and check `testRuntimeClasspath`. Conversely, do not promote all of `testImplementation` to production runtime just because `@SpringBootTest` uses them.

### 12.2 Special case: the same module appearing via multiple paths

A module can enter via multiple configurations or dependency paths. For example, `lombok` added to `compileOnly` might also be added to `runtimeOnly` by another plugin; or Tomcat put in `providedRuntime` is also pulled transitively by `starter-web`.

Hence an answer like "artifact X is in Y because of line Z" is only accurate after checking **resolved graph + final classpath + final archive**. Maven/Gradle outcomes can shift due to BOMs, dependency constraints, exclusions, plugin versions, resolution rules, and module-specific settings.

## 13. Before–after measurement labs

### Lab A – Maven `provided` in executable JAR/WAR

1. Use `pom.xml` and `DemoApplication` from section 7; keep versions pinned.
2. Run `dependency:tree` to verify `spring-boot-starter-tomcat` has scope `provided`.
3. Build the executable WAR and inspect `target/demo-0.0.1-SNAPSHOT.war` with `jar tf`. Confirm `tomcat-embed-...jar` files sit in `WEB-INF/lib-provided`.
4. Run `java -jar ...war` and call `/ping`. Record the response body.
5. On a **branch/copy**, switch packaging to `jar`, rebuild, and inspect `BOOT-INF/lib`. Explain why Maven `provided` did not make Tomcat disappear from the executable JAR.
6. Inspect `effective-pom` and identify which plugin/execution performs `repackage`.
7. Answer: how does core Maven `provided` differ from Spring Boot's packaging decision?

### Lab B – Gradle `compileOnly` with Lombok

1. Use `build.gradle` from section 8 and add `Greeting.java` and `GreetingProbe.java`.
2. Run `./gradlew classes` and `java -cp build/classes/java/main com.example.demo.GreetingProbe`, confirming output `hello`.
3. Verify `compileClasspath` includes Lombok while `runtimeClasspath` does not from `compileOnly` alone.
4. Build `bootJar`; search for `lombok-...jar` in `BOOT-INF/lib` and record the result.
5. On a copy, remove `annotationProcessor` while keeping `compileOnly`; observe the compiler error because `getValue()` is not generated; restore configuration afterward.
6. Answer: why are `testCompileOnly` and `testAnnotationProcessor` separate configurations?

### Lab C – Gradle `developmentOnly` with DevTools

1. Run `./gradlew dependencies --configuration runtimeClasspath` and locate DevTools.
2. Run `./gradlew dependencies --configuration productionRuntimeClasspath` and compare the DevTools dependency path.
3. Run `./gradlew clean bootJar` and confirm `BOOT-INF/lib` has no `spring-boot-devtools-...jar` by default.
4. On an isolated branch, test moving DevTools to `runtimeOnly` and compare the graph/package; **never** send that test artifact into a release pipeline.
5. Explain the difference between DevTools "auto-disabling when packaged" and "having zero DevTools bytes in the artifact."

### Lab D – Gradle `providedRuntime` and WAR

1. Convert the Gradle MVC app to the War plugin and add Tomcat under `providedRuntime`.
2. Run tests appropriately; if using web integration tests, confirm the Servlet runtime is present.
3. Run `./gradlew clean war bootWar` and inspect both the plain WAR and Boot WAR.
4. Confirm the plain WAR keeps Tomcat out of `WEB-INF/lib`, while the Boot WAR places it in `WEB-INF/lib-provided`.
5. Run `java -jar` on the Boot WAR and test deploying to a **compatible** external container if available.
6. On an experimental branch, replace `providedRuntime` with `compileOnly`, re-run tests/`bootWar`, and explain the difference using evidence; revert afterward.
7. Find a transitive dependency marked provided; check whether it is excluded from the plain WAR as Gradle documentation warns.

### Lab E – Write a verifiable report

For each dependency in the lesson, fill out a report using this template:

```text
Module:
Build system and version:
Artifact type: plain JAR / Boot JAR / plain WAR / Boot WAR
Dependency (group:artifact:version):
Scope/configuration in build file:
Present in compileClasspath? Evidence:
Present in testRuntimeClasspath? Evidence:
Present in development runtime? Evidence:
Present in release artifact? ZIP path:
What does the external container provide?
Conclusion (why use provided/compileOnly/developmentOnly):
```

This is a **learner report template**. Conclusions must rely on actual project commands, not "yes/no" guesses filled from intuition. If a report only writes "**`dependency:tree` has X**" or "**Gradle build succeeded**" without opening the archive, it has not met the packaging verification objective.

## 14. Official documentation

- Apache Maven – Introduction to the Dependency Mechanism: `compile`, `provided`, `runtime`, `test`, `optional`: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Spring Boot 3.3 Maven Plugin – Packaging Executable Archives, `repackage`, provided dependencies, WAR layout, and exclusions: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 Gradle Plugin – Packaging Executable Archives, `bootJar`/`bootWar`, `developmentOnly`, `providedRuntime`: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
- Spring Boot 3.3 – Traditional Deployment, Maven `provided` and Gradle `providedRuntime` for external Servlet containers: https://docs.spring.io/spring-boot/3.3/how-to/deployment/traditional-deployment.html
- Gradle – Java Plugin: `compileOnly`, `annotationProcessor`, test classpaths, and `runtimeClasspath`: https://docs.gradle.org/current/userguide/java_plugin.html
- Gradle – War Plugin: `providedCompile`, `providedRuntime`, differences from `compileOnly`, and transitivity: https://docs.gradle.org/current/userguide/war_plugin.html
- Spring Boot 3.3 Gradle Plugin API – configuration names `developmentOnly`, `testAndDevelopmentOnly`, and `productionRuntimeClasspath`: https://docs.spring.io/spring-boot/3.3/gradle-plugin/api/java/org/springframework/boot/gradle/plugin/SpringBootPlugin.html

**Remember:** `provided`, `compileOnly`, and `developmentOnly` are not three equivalent ways of saying "do not package." They are **different classpath contracts**. Spring Boot packaging adds its own processing steps on top. To reach sound conclusions, connect **declaration → compile/test/dev runtime → Boot packaging → ZIP layout → actual startup**.