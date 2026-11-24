# Where repackage, bootJar, and bootWar Sit in a Spring Boot Build

## 1. What problem does this lesson solve?

In a Spring Boot project, the application packaging operation has different names depending on the build tool:

- **Maven:** the `spring-boot:repackage` goal of the Spring Boot Maven Plugin repackages the JAR/WAR already created in the lifecycle.
- **Gradle:** the `bootJar` task creates an executable JAR, and the `bootWar` task creates an executable WAR.
- **Maven `package`, Gradle `assemble`, and Gradle `build`:** are entry points of the build process, not directly synonymous with the three Spring Boot operations above.

This lesson helps answer: at which step does the operation run; which configuration/plugins are needed; where is the archive created from; does `package`/`build` run tests; when are plain archives and executable archives produced at the same time; and how to verify results without guessing from filenames.

After this lesson, you can read Maven/Gradle logs, pinpoint where `repackage` or `bootJar`/`bootWar` actually runs, select the right artifact to deploy, and avoid applying executable packaging to library modules.

## 2. How do the three operations differ?

| Aspect | Maven `repackage` | Gradle `bootJar` | Gradle `bootWar` |
| --- | --- | --- | --- |
| Owner | Spring Boot Maven Plugin | Spring Boot Gradle Plugin | Spring Boot Gradle Plugin |
| Operation type | Maven goal | Gradle task of type `BootJar` | Gradle task of type `BootWar` |
| Input | Base JAR/WAR already created in `package` | Application classes/resources + runtime dependencies | Classes/resources + dependencies and WAR configuration |
| Output | Executable JAR or WAR | Executable JAR | Executable WAR |
| Default lifecycle milestone | Goal bound to Maven `package` phase when a valid execution exists | Wired into Gradle `assemble` when the Java plugin is present | Wired into Gradle `assemble` when the War plugin is present |
| Typical invocation | `./mvnw package` | `./gradlew bootJar` or `./gradlew build` | `./gradlew bootWar` or `./gradlew build` |

**Key point:** there is no default sequence `repackage → bootJar → bootWar`. They solve corresponding scenarios in **two separate build systems**. A project using Maven does not need to run a Gradle task to complete `repackage`, and a project using Gradle does not need a Maven goal to complete `bootJar`.

An executable Boot JAR/WAR typically has runtime libraries bundled inside the archive and the metadata required for the Spring Boot loader to launch the application:

~~~bash
java -jar path/to/app.jar
# or
java -jar path/to/app.war
~~~

However, a `.jar`/`.war` file extension **does not by itself prove** the file can run with `java -jar`.

## 3. Maven lifecycle: `repackage` sits at the `package` phase

### 3.1. Position in the Maven lifecycle

Maven defines a default lifecycle with ordered phases. Abbreviated sequence:

~~~text
validate
   ↓
compile
   ↓
test
   ↓
package             ← creates JAR/WAR and may run repackage
   ↓
verify
   ↓
install
   ↓
deploy
~~~

This is only an illustration: Maven also has `process-resources`, `test-compile`, `integration-test`, and other intermediate phases. When invoking `./mvnw package`, Maven executes the required phases up to and including `package`. When invoking `./mvnw verify` or `./mvnw install`, Maven passes through `package` on the way to the requested phase.

Depending on the project's packaging, the `package` phase has standard goals:

- `<packaging>jar</packaging>`: typically runs `maven-jar-plugin:jar`, producing a regular JAR.
- `<packaging>war</packaging>`: typically runs `maven-war-plugin:war`, producing a regular WAR.
- `<packaging>pom</packaging>`: typically applies to root aggregators/parents; does not by default have an application archive to repackage.

The `spring-boot:repackage` goal runs **after a base archive exists** to convert it into an executable Boot archive. Model:

~~~text
Java source + dependencies
    ↓ compile, test...
maven-jar-plugin:jar or maven-war-plugin:war
    ↓ creates base JAR/WAR in the package phase
spring-boot-maven-plugin:repackage
    ↓ converts into executable Boot JAR/WAR
verify / install / deploy if requested
~~~

If `repackage` and the archive-creating plugin are both bound to `package`, the goal order must ensure **the JAR/WAR is created first and then repackaged**. When configuring manually, check the execution order in the effective POM and actual logs.

### 3.2. "`repackage` has a default phase" does not mean it always runs

Do not conclude `mvn package` will automatically create a Boot archive just because `pom.xml` declares the `spring-boot-starter-web` dependency. Dependencies are libraries; executable packaging depends on **plugins and executions**.

**Approach A: inherit `spring-boot-starter-parent`.** The Spring Boot parent provides a preconfigured `repackage` execution. The application module declares `spring-boot-maven-plugin` in `build/plugins` to use that configuration; when invoking `package`, the repackage goal is brought into the lifecycle.

**Approach B: use another parent or only import the `spring-boot-dependencies` BOM.** A BOM manages dependency versions, and **does not automatically supply all Maven plugin configurations of the starter parent**. If you want `repackage` to run during `package`, you must declare the Maven plugin version and appropriate execution in the POM or current parent.

Illustrative snippet for Approach B, inserted into a complete POM:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-maven-plugin</artifactId>
            <!-- Version must be specified here or via pluginManagement. -->
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

This is an **XML fragment** to integrate into a project's POM, not a standalone `pom.xml`.

### 3.3. Maven JAR: complete example to try

With Spring Boot 3.3.13 and Java 17, a minimal `pom.xml` for a web application:

~~~xml
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

File `src/main/java/com/example/demo/DemoApplication.java`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}

@RestController
class PingController {
    @GetMapping("/ping")
    public String ping() {
        return "pong";
    }
}
~~~

The Java code above runs with the given dependency configuration, compatible JDK, and Maven. If the project has a Maven wrapper:

~~~bash
./mvnw clean package
java -jar target/demo-0.0.1-SNAPSHOT.jar
~~~

If there is no wrapper, use `mvn clean package` with a valid Maven installation. In Windows PowerShell, use `.\mvnw.cmd clean package` when a wrapper is available. After the app starts on the default port, a `GET http://localhost:8080/ping` request returns the exact response body:

~~~text
pong
~~~

Execution conditions: the default port is not already in use and no application config overrides the port/route. Build results depend on the JDK, repositories, and environment setup.

In the `./mvnw package` log, you will see the plugin creating the base JAR and the `spring-boot:repackage` goal per the parent execution. Spring Boot documentation describes the repackage goal as transforming the base archive into an executable JAR/WAR.

### 3.4. Why not just invoke `spring-boot:repackage`?

Compare:

~~~bash
./mvnw package
# Runs the Maven lifecycle up to package; creates the archive and automatically repackages
# if the execution is configured.

./mvnw spring-boot:repackage
# Requests only the repackage goal; the base archive must already exist beforehand.
~~~

`repackage` **does not replace the compile/test/package sequence**. When you need to run the goal manually alongside archive creation, Spring Boot documentation shows `mvn package spring-boot:repackage`. However, when `repackage` is already bound to `package`, invoking the goal directly as well can trigger the operation repeatedly; with a standard starter parent setup, `./mvnw package` alone is sufficient.

To prove the execution is active:

~~~bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw package
~~~

In the effective POM, look for the `spring-boot-maven-plugin` plugin and the execution containing the `repackage` goal. In the build log, look for the `spring-boot:repackage` goal line for the **correct module**. If it is missing, inspect the plugin/execution configuration before editing application code.

### 3.5. Maven output: original archive and executable archive

By default, `repackage` can replace the main artifact with the executable archive and keep the original archive with a `.original` suffix. For example, with `demo`:

~~~text
target/
├── demo-0.0.1-SNAPSHOT.jar            # Spring Boot executable JAR
└── demo-0.0.1-SNAPSHOT.jar.original   # JAR before repackage
~~~

Filenames depend on `finalName`, packaging, classifier, and plugin configuration. When configuring a custom classifier such as `exec`, the build system can preserve the original artifact and also produce `demo-0.0.1-SNAPSHOT-exec.jar`; at publish time you must specify which artifact is meant for runtime.

Note: `.jar.original` is Maven's way of keeping the original under default settings, not the same naming convention as Gradle's `-plain.jar`.

## 4. Gradle: `bootJar` and `bootWar` live in the task graph

### 4.1. Gradle lifecycle tasks differ from Maven phases

Gradle coordinates **tasks and dependencies between tasks**. With the Java plugin, the common lifecycle structure looks like:

~~~text
build
├── assemble       # gathers packaged outputs
└── check          # verifications; usually includes test
~~~

The Spring Boot Gradle Plugin reacts to foundational plugins:

- Java plugin present → creates `bootJar` task of type `BootJar` and wires it into `assemble` by default.
- War plugin present → creates `bootWar` task of type `BootWar` and wires it into `assemble` by default.
- Standard `jar` and `war` tasks may still exist and create plain archives.

Typical configuration of a JAR application:

~~~text
./gradlew build
    ├── assemble
    │    ├── jar       → plain JAR, if enabled
    │    └── bootJar   → executable Spring Boot JAR
    └── check
         └── test      → test suite, per Java plugin
~~~

This is a diagram of **typical relationships**, not a guarantee that every build always has the exact same tasks. Build logic, other plugins, disabled tasks, project dependencies, and CLI flags can change the graph.

Therefore:

- `./gradlew bootJar` runs the tasks needed to create the Boot JAR; **does not by default prove unit tests ran**.
- `./gradlew assemble` builds artifacts wired into assemble, including Boot JAR/WAR per configuration.
- `./gradlew build` normally runs `assemble` and `check`; thus it usually both packages and tests.
- `./gradlew bootWar` is similar to `bootJar` but outputs a Boot WAR when the task exists.

### 4.2. Gradle JAR: a runnable `build.gradle`

File `settings.gradle`:

~~~groovy
rootProject.name = 'demo'
~~~

File `build.gradle` (Groovy DSL, Spring Boot 3.3.13 example):

~~~groovy
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
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Create the Java file `src/main/java/com/example/demo/DemoApplication.java` using the code from the Maven example. This is a **separate Gradle project**; do not combine the POM and Gradle build from the two examples as if they automatically share a lifecycle.

When a compatible Gradle wrapper is present:

~~~bash
./gradlew tasks --all
./gradlew bootJar
./gradlew assemble
./gradlew build
~~~

- `tasks --all`: view declared and plugin-generated tasks.
- `bootJar`: creates the executable Boot JAR.
- `assemble`: creates outputs registered in the assemble lifecycle.
- `build`: adds check/test according to the project's task graph and build logic.

For a project without a wrapper yet, use an appropriately installed `gradle` command. In Windows PowerShell, use `.\gradlew.bat` if a wrapper exists.

### 4.3. Plain JAR and executable Boot JAR are not the same

In Spring Boot Gradle Plugin 3.3, when `bootJar` is present, the `jar` task typically uses the `plain` classifier by convention. After building, you may see:

~~~text
build/libs/
├── demo-0.0.1-SNAPSHOT.jar        # bootJar, executable
└── demo-0.0.1-SNAPSHOT-plain.jar  # jar, plain
~~~

Both files are valid JARs, yet they usually serve different purposes:

- Executable Boot JAR contains application classes, nested runtime JAR dependencies, the Boot loader, and a manifest suitable for running `java -jar`.
- Plain JAR contains classes/resources as a standard Java archive; it can be used as a library and does not by default contain all dependencies/Boot launcher.

In a Gradle Groovy DSL build, if project policy wants to disable the plain JAR task:

~~~groovy
tasks.named('jar') {
    enabled = false
}
~~~

This is a fragment added to a `build.gradle` that has the Java plugin. **Do not blindly disable the `jar` task** if library publishing, other tasks, or native-image workflows need the plain archive. Besides disabling, you can adjust classifiers so the two artifact types have clearer names.

### 4.4. Gradle WAR: when is `bootWar` present?

`bootWar` is created when applying the Spring Boot Gradle Plugin alongside the War plugin. Example of the sections to adjust for a Servlet application:

~~~groovy
plugins {
    id 'java'
    id 'war'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    providedRuntime 'org.springframework.boot:spring-boot-starter-tomcat'
}
~~~

This is a **fragment** for `build.gradle`, to be combined into a complete `build.gradle` with `group`, `version`, `repositories`, and Java configuration as seen in the JAR example. When switching from JAR to WAR, edit the existing `plugins` and `dependencies` blocks rather than inserting duplicate `plugins` blocks.

In Gradle, `providedRuntime` is used for servlet container dependencies provided by an external servlet container at runtime. With a Spring Boot executable WAR, dependencies in this scope are stored in `WEB-INF/lib-provided`, allowing the WAR to run standalone without causing container library conflicts during traditional deployment.

So that the WAR can be deployed to an external servlet container, a Servlet MVC application class can extend `SpringBootServletInitializer`:

~~~java
package com.example.demo;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.builder.SpringApplicationBuilder;
import org.springframework.boot.web.servlet.support.SpringBootServletInitializer;

@SpringBootApplication
public class DemoApplication extends SpringBootServletInitializer {

    @Override
    protected SpringApplicationBuilder configure(SpringApplicationBuilder application) {
        return application.sources(DemoApplication.class);
    }

    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }
}
~~~

If using this class, replace the `DemoApplication` class from the JAR example; do not declare two public classes of the same name in the same package. You can keep `PingController` in a separate file to test requests. The external WAR example suits Servlet applications; do not apply this exact pattern by default to pure WebFlux projects.

Commands:

~~~bash
./gradlew tasks --all
./gradlew bootWar
./gradlew assemble
./gradlew build
~~~

A WAR build normally yields an executable `.war` and a plain `-plain.war` if both `bootWar` and `war` are enabled. Because the War plugin builds on the Java plugin, **a single project can have both `bootJar` and `bootWar`**. Inspect the exact graph and artifact to deploy, and only disable unwanted tasks after determining packaging policy.

## 5. Maven WAR and Gradle WAR: same destination, different paths

### 5.1. Maven WAR

Declare `<packaging>war</packaging>`, have the WAR plugin create the base archive in the `package` phase, and have the Spring Boot Maven Plugin execute `repackage` if an execution is configured. Diagram:

~~~text
Maven: package
  ├─ maven-war-plugin:war      → regular WAR
  └─ spring-boot:repackage    → executable Boot WAR
~~~

In the Maven POM example from section 3, change packaging and dependencies for a Servlet WAR:

~~~xml
<packaging>war</packaging>

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
</dependencies>
~~~

This is a fragment to **replace** packaging/dependencies in a complete POM, not a standalone POM. You still need `spring-boot-maven-plugin` configured. If deploying the WAR into an external servlet container, add `SpringBootServletInitializer` as in the Gradle WAR example and verify servlet container compatibility with the Spring Boot version in use.

### 5.2. Gradle WAR

Gradle runs the `bootWar` task directly; it does not call `maven-war-plugin:war` and has no Maven `package` phase. The `assemble` task is wired to produce the executable WAR; the `build` task normally includes `assemble` and `check`.

Key differences:

| Need | Maven | Gradle |
| --- | --- | --- |
| Package executable JAR | `./mvnw package` with `repackage` goal properly bound | `./gradlew bootJar` or `./gradlew assemble/build` |
| Package executable WAR | `packaging=war`, WAR plugin then `repackage` | War plugin, `bootWar` task |
| Inspect execution point | Effective POM, lifecycle log, execution ID | `tasks --all`, `--dry-run`, task graph and logs |
| Testing in full build | Lifecycle up to `package` usually includes tests, per plugins/skip flags | `build` usually includes `check/test`; `bootJar`/`bootWar` directly does not guarantee tests |
| Typical artifacts | `target/*.jar` or `target/*.war` | `build/libs/*.jar` or `build/libs/*.war` |

Do not treat a standalone "BUILD SUCCESSFUL" or "BUILD SUCCESS" message as proof that all tests ran or the right kind of executable was produced: inspect goals/tasks and outputs.

## 6. Inside the archive: telling plain and executable apart

An executable Spring Boot JAR typically contains:

~~~text
META-INF/MANIFEST.MF
BOOT-INF/classes/               # application classes/resources
BOOT-INF/lib/                   # nested runtime JAR dependencies
org/springframework/boot/loader/...
~~~

An executable Spring Boot WAR typically contains:

~~~text
META-INF/MANIFEST.MF
WEB-INF/classes/                # application classes/resources
WEB-INF/lib/                    # runtime libraries
WEB-INF/lib-provided/           # provided libraries, if any
org/springframework/boot/loader/...
~~~

In an executable archive, the manifest normally has `Main-Class` pointing to Spring Boot's launcher and `Start-Class` pointing to the application entrypoint. Therefore, a regular JAR containing only classes/resources does not behave like an executable JAR, even with the same file extension.

Use the JDK `jar` tool to list contents:

~~~bash
# Maven JAR example:
jar tf target/demo-0.0.1-SNAPSHOT.jar

# Gradle JAR example:
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar

# Gradle WAR example:
jar tf build/libs/demo-0.0.1-SNAPSHOT.war
~~~

Only use the command matching the actual artifact type you have; output filenames can change via `finalName`/classifier/`archiveFileName` and module paths. Look for `BOOT-INF/lib` or `WEB-INF/lib` and the loader; finally verify by running `java -jar` with the executable build in the runtime environment.

## 7. Multi-module projects: apply Boot packaging only to applications

Example:

~~~text
root/
├── common/          # shared library
├── persistence/     # data library
└── api-service/     # Spring Boot application with main class
~~~

Do not apply executable packaging indiscriminately:

- Maven root aggregator uses `packaging=pom`, library modules can build plain JARs, and only the `api-service` module uses `repackage` to produce a Boot executable. If an internal parent applies the plugin to all modules, check whether modules without an entrypoint are unintentionally invoking `repackage`.
- Gradle modules `common` and `persistence` can use `java-library`, while `api-service` applies the Spring Boot plugin to get `bootJar` or `bootWar`. Applying the Boot plugin across the board can cause missing main class errors and produce wrong artifacts for libraries.

Illustrative commands for a project that **actually** has a module named `api-service`:

~~~bash
# Maven multi-module:
./mvnw -pl api-service -am package

# Gradle multi-project:
./gradlew :api-service:bootJar
./gradlew :api-service:build
~~~

Maven's `-am` also selects modules needed to build the chosen module; Gradle uses subproject task paths. Do not infer module names or publish policies merely from seeing a JAR file appear.

## 8. Verifying the lifecycle with evidence instead of guessing

### 8.1. Maven

Run in the right Maven root:

~~~bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
./mvnw package
# If the process requires verify:
./mvnw verify
~~~

Cross-check 5 factors:

1. Is the module's POM packaging `jar`, `war`, or `pom`?
2. Does the effective POM have `spring-boot-maven-plugin` and an execution binding `repackage`?
3. Does the `package` log show the jar/war goal before the `repackage` goal?
4. Does `target` contain the executable archive and original `.original`/classifier file?
5. Do `install`/`deploy` targets, if used, publish the exact archive that runtime expects?

When deep diagnostics are needed, you can use Maven debug logs, but avoid exposing sensitive credentials/settings in shared environments. Inspect the actual error before changing plugins.

### 8.2. Gradle

Run in the Gradle root, selecting the right module if multi-module:

~~~bash
./gradlew tasks --all
./gradlew bootJar --dry-run
./gradlew build --dry-run
./gradlew build
~~~

If the project only builds a WAR, replace `bootJar` with `bootWar`. Running `bootWar` in a project without the War plugin may report task not found; that is not a packaging bug of a JAR project.

`--dry-run` shows scheduled tasks in the graph without executing task actions; **it does not create new archives and does not prove tests pass**. Run an actual `build`/`bootJar`/`bootWar` to confirm outputs.

Distinguish Gradle statuses:

- Task listed in the graph.
- Task action actually runs.
- Task marked `UP-TO-DATE` or `FROM-CACHE`.
- Artifact is present and runnable.

A task appearing in the graph does not guarantee its action just executed; an existing artifact in the build directory might be leftover output from a previous run. When investigating, check timestamps/logs and run a clean build per appropriate workflow.

## 9. Common errors and how to find root causes

| Symptom or false assumption | How to verify and handle |
| --- | --- |
| `mvn package` outputs a JAR but `java -jar` reports missing launcher | Check whether the `repackage` goal is bound/ran, distinguish original file vs executable |
| Having a Spring Boot starter guarantees `repackage` runs | False: a starter is a dependency; Maven plugin/execution is required |
| Calling `mvn spring-boot:repackage` before creating an archive | The goal needs a base JAR/WAR; run the `package` lifecycle with proper execution |
| Repackage reports source artifact not found | Check whether the jar/war creation goal ran first and the module's packaging is right |
| `./gradlew bootJar` succeeds but tests have not run | `bootJar` does not replace `build`/`check`; inspect the graph or run tests separately |
| `./gradlew build` does not produce a Boot archive | Check if the plugin is applied, task enabled, what `assemble` depends on, and which subproject |
| Seeing `-plain.jar` and assuming it is the Boot executable | `-plain.jar` is usually the plain archive; check `BOOT-INF`/manifest and choose `bootJar` output |
| `bootWar` exists but you only want a WAR output | Check `bootJar` from War/Java plugin too and configure disabling unwanted tasks, then inspect final artifacts |
| Deploying WAR to external servlet container fails | Check Servlet WAR, `SpringBootServletInitializer`, provided servlet runtime, container compatibility |
| Library module has no main class so `bootJar` fails | Review applying the Spring Boot plugin; a library may only need plain `jar` |
| CI publishes the wrong JAR/WAR | Explicitly specify module, task/goal, classifier, and output path; do not grab the first file matching `*.jar` |
| Both Maven and Gradle exist in the repo | Verify which build source is maintained in CI and the repo; do not treat two build systems as sequential steps |

Do not troubleshoot by wiping cache directories en masse or adding plugins blindly. First pinpoint the exact **module**, **goal/task**, **execution order**, and **artifact**.

## 10. Practice verifying each operation's location

Choose a Spring Boot application with a valid entrypoint and wrapper. Run only the workflow of the build tool used by that project.

### Maven exercise

1. Read the POM; identify `packaging`, parent, and Spring Boot Maven Plugin.
2. Use the effective POM to show whether the `repackage` execution is bound to the lifecycle.
3. Run `./mvnw clean package`; in the log, confirm the base archive precedes the `repackage` goal.
4. Inspect the `target` directory, explaining the executable file and original archive if present.
5. Use `jar tf` to inspect structure and `java -jar` to start the application.
6. Answer: if you change the command to `./mvnw verify`, does `repackage` still run, and why?

### Gradle exercise

1. Read the plugins in `build.gradle(.kts)`; identify whether the project uses Java, War, or both.
2. Run `./gradlew tasks --all` to prove `bootJar`/`bootWar` tasks exist.
3. Run `./gradlew build --dry-run` to trace the path from `build` to `assemble` and the executable packaging task.
4. Run `./gradlew clean build`, cross-check logs against the graph, and inspect files under `build/libs`.
5. Distinguish plain output from executable output and verify with `jar tf`.
6. Compare with `./gradlew bootJar --dry-run` or `bootWar --dry-run`. Explain why calling the packaging task alone is not proof that the test suite ran.

### Self-check questions

**1.** Why might Maven using the Spring Boot BOM without the starter parent fail to run `repackage` in the `package` phase?

**Answer:** The BOM manages dependency versions, whereas goal bindings come from plugin executions. You must configure the execution in the appropriate module/parent.

**2.** Why does Gradle have both `jar` and `bootJar`?

**Answer:** The Java plugin provides the plain JAR task, while the Spring Boot plugin adds the executable JAR task; the classifier convention prevents overwriting files.

**3.** Does `./gradlew bootWar` succeeding mean `./gradlew test` ran?

**Answer:** No. Check the task dependency graph; run `build`/`test` according to the project's testing policy.

**4.** Do you need to call `repackage` and then `bootJar` to get an executable archive?

**Answer:** No. Maven and Gradle are two separate mechanisms. Choose the workflow matching the build tool used by the project.

**Completion criteria:** you accurately trace from source code to regular archive/executable archive for Maven, and from Gradle task graph to executable JAR/WAR for Gradle; and present actual logs, tasks/goals, and artifacts as proof.

## 11. Official documentation references

- Spring Boot 3.3 — Maven Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Maven Using the Plugin: https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html
- Spring Boot 3.3 — Gradle Packaging Executable Archives: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html

Examples here use Spring Boot 3.3 and Java 17 for illustration. In real projects, always consult documentation for the **actual Spring Boot, Maven/Gradle plugin, and JDK versions**, as default behaviors can change across versions.