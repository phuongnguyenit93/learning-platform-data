# Identifying Inputs, Outputs, and Success Status of Each Spring Boot Build Stage

## 1. Purpose and scope

A command like `mvn clean verify` or `./gradlew clean build` often shows only an overall result `BUILD SUCCESS` or `BUILD SUCCESSFUL`. To control quality, you need to know **what each stage receives, what it produces, and what evidence qualifies it as successful**.

After this lesson, you can:

1. Trace the path of Spring Boot source code from checkout, dependency resolution, compilation, testing, and packaging through release.
2. Identify **inputs**, **outputs**, **PASS conditions**, **FAIL/SKIP signs**, and **verification evidence** for each stage.
3. Map the same activity to **Maven phases/plugin goals** and **Gradle tasks**, while accurately distinguishing the Maven lifecycle from the Gradle build lifecycle.
4. Design CI quality gates to avoid treating a "green build" as synonymous with "ran enough tests", "JAR is runnable", or "service is ready".
5. Investigate incidents from the first failing stage instead of reading only the last error line.

**Primary scope:** Java/Spring Boot applications packaged as executable JARs with Maven or Gradle. Examples use Java 17+ and Spring Boot 4.1.2. For other Spring Boot versions, check the corresponding Java requirements, build tool versions, starters, plugins, and task names.

## 2. Mental model: every stage has five attributes

Use the following template for any stage:

| Attribute | Question to answer |
| --- | --- |
| **Input** | Which files, tool versions, configurations, artifacts, services, or permissions does this stage require? |
| **Processing** | What work do the Maven goal, Gradle task, compiler, test runner, or external system perform? |
| **Output** | Which verifiable artifacts—classes, resources, test reports, JARs, images, checksums, publications, or deployment records—are produced? |
| **PASS** | What specific condition allows advancing to the next stage? Must anything beyond exit code 0 be verified? |
| **FAIL / SKIP** | What causes the stage to fail, be skipped, or have no work? Under what circumstances is that status permitted? |

A stage can end **validly in success without producing new files**; for example, Maven `validate` checks validity, and Gradle task `processResources NO-SOURCE` occurs when a project has no resources. Conversely, a stage might already have output files on disk from a previous build while **the current run did not succeed**. Therefore, combine the current run's logs, task execution conditions, and output state.

**Definition of Done used in this lesson:**

> A stage PASSES when essential inputs are valid, required steps executed or were legitimately reused, results meet defined criteria, and traceable evidence exists. A skipped stage counts as PASS only if project policy permits that skip.

Do not turn every `SKIPPED` line into PASS; if policy requires unit tests and they were skipped, the quality gate must report **failed** even if the build tool exited with code 0.

## 3. Roadmap of an artifact

~~~text
Source code + pom.xml/build.gradle + wrapper + config + JDK
                           |
                           v
             [0] Checkout / build initialization
                           |
                           v
             [1] Validate / configure tasks
                           |
                           v
             [2] Resolve dependencies + plugins
                           |
                           v
             [3] Generate sources + process resources
                           |
                           v
             [4] Compile production code
                           |
                           v
             [5] Compile tests -> run tests -> reports
                           |
                           v
             [6] Build JAR/WAR -> Spring Boot executable JAR
                           |
                           v
             [7] Verify / integration / smoke checks
                           |
                           v
             [8] Publish artifact / image (if requested)
                           |
                           v
             [9] Deploy -> verify runtime readiness
~~~

This is a **logical pipeline** for observing inputs/outputs; it is not an identical official phase list for both tools:

- **Maven** has `clean`, `default`, and `site` lifecycles. The `default` lifecycle contains **ordered phases** such as `validate`, `process-resources`, `compile`, `test`, `package`, `verify`, `install`, and `deploy`. Plugin goals are bound to phases. Calling `mvn verify` runs the necessary phases before `verify`; `mvn clean verify` also runs the `clean` lifecycle.
- **Gradle** has three **internal phases**: initialization, configuration, execution. During execution, Gradle runs a **task graph** based on dependencies and requested tasks, such as `compileJava`, `test`, `bootJar`, `check`, and `build`. There is no mandatory fixed sequence of tasks identical to Maven phases by default.
- **Spring Boot plugins** add operations for packaging executable JARs, running the application, and building container images; enabling additional release/testing activities depends on specific configuration.

## 4. Matrix of inputs, outputs, and PASS conditions by stage

| Logical stage | Main inputs | Expected outputs | Provable PASS criteria | Common Maven / Gradle equivalents |
| --- | --- | --- | --- | --- |
| **0. Checkout & environment** | Commit, source tree, wrapper, JDK, env, repo credentials if needed | Workspace at exact commit; JDK/build tool available | Right commit, wrapper runs, Java meets requirements, no missing required vars | `./mvnw -version` / `./gradlew --version` and CI checkout |
| **1. Validate & configure** | POM or settings/build scripts, profiles, plugin declarations | Configured effective model or task graph | Valid config; plugins loaded; no parse/config errors | `validate` / initialization + configuration |
| **2. Dependency resolution** | Coordinates, BOM, repositories, credentials, cache | Resolved dependency graph and artifacts | All required modules/plugins resolved at expected versions, no severe conflicts | Maven resolve / Gradle resolve when tasks require |
| **3. Generate & resources** | Generator inputs, `src/main/resources`, filtering values | Generated sources, resources in build output | Generators complete; needed resources copied/filtered; no missing critical assets | `generate-sources`, `process-resources` / generate task, `processResources` |
| **4. Compile production** | `src/main/java`, generated sources, compile classpath, JDK | `.class` + compilation metadata | Zero compile errors, compatible release target, classes created when sources exist | `compile` / `compileJava` |
| **5. Compile & run tests** | Test sources, test classpath, runtime, fixtures | Test classes, JUnit XML, logs | Required tests discovered and executed; 0 failures/errors per policy | `test-compile`, `test` / `compileTestJava`, `test` |
| **6. Package** | Compiled classes, resources, runtime dependencies, manifest, Boot plugin | JAR/WAR and executable archive | Archive newly created/validly reused, readable, valid Boot layout, `java -jar` can launch | `package` + `repackage` / `bootJar` |
| **7. Verify** | Packaged artifact, integration checks, quality rules | Integration/verification reports, gate verdict | All **configured and mandatory** checks pass; no policy-violating skips | `verify` + bound plugins / `check` and custom tasks |
| **8. Publish** | Approved artifact, version, credentials, repository/image registry | Maven coordinates/metadata or image digest at destination | Upload succeeds, coordinates/checksum/digest retrievable | `install`, `deploy` / `publishToMavenLocal`, `publish` |
| **9. Deploy & readiness** | Approved artifact/image, environment config, secrets, infrastructure | Running release, logs, and health status | Deployment completes, actual readiness/smoke probes pass | CI/CD or deployment tools outside the build tool |

**Important:** Not all of these stages are triggered in a single command. For instance, `mvn clean package` stops before `verify`; `./gradlew bootJar` does not automatically imply unit tests ran; `./gradlew build` does not publish by default; `java -jar` succeeding at startup does not by itself prove readiness in production.

## 5. Stage 0 — identifying build inputs

### Input

- Repository at a **specific commit**, along with tracked submodules/files needed for the build.
- `pom.xml` or `build.gradle`/`build.gradle.kts`, `settings.gradle`, `gradle.properties`; Maven/Gradle Wrapper if present.
- Java/JDK supported by the build tool version and Spring Boot plugin; toolchain JDK for compile/test if different.
- Dependency repository configurations, proxies, private artifact credentials, environment variables only when genuinely required.
- Version info, build profiles, build feature flags, codegen inputs, and resource files.

### Output and PASS

The output is not a JAR yet, but a **reproducible workspace**: checked out at the exact commit, executable wrapper, and verified prerequisites. In CI, record the commit SHA, Java runtime, Maven/Gradle version, and list of build profiles/properties (never write secrets to logs).

~~~bash
# Run in the project root directory with the corresponding wrapper
git rev-parse HEAD
java -version
./mvnw -version
# or
./gradlew --version
~~~

**PASS:** repository matches the intended revision, wrapper starts cleanly, Java and environment meet requirements. **FAIL:** wrong commit checked out, wrapper lacks execute permission, Java too old, private registry unreachable. **Note:** the Java running Maven/Gradle and the Java Toolchain used to compile can differ; do not infer the compiler solely from `java -version`.

## 6. Stage 1 — validate, initialize, configure

### Maven

`mvn validate` runs goals bound to the `validate` phase and any preceding phases of the appropriate lifecycle. It checks the model and whatever bound plugins are configured to check. **Do not treat `validate` as a comprehensive check of code, tests, or production readiness**.

Inputs are the POM, parent, profiles, and plugin settings; output is a valid build model/configuration to proceed to subsequent stages. You can inspect the effective POM:

~~~bash
mvn help:effective-pom
mvn validate
~~~

**PASS:** no POM parsing errors, parent/module resolution issues, missing required plugins, or failed configured validate rules. Note that a parseable POM does not prove sources compile.

### Gradle

Gradle's three internal phases:

1. **Initialization:** determines the build, settings, and projects.
2. **Configuration:** evaluates build scripts, applies plugins, registers and configures required tasks (supporting lazy configuration and configuration cache).
3. **Execution:** determines the task graph to run, resolves required inputs, and runs tasks by dependency.

The configuration output is an **executable build model/task graph**; there need not be new JARs/classes yet. Ways to inspect tasks:

~~~bash
./gradlew tasks
./gradlew help
./gradlew build --dry-run
~~~

`--dry-run` previews scheduled work **without executing real tasks**; therefore it is **not proof that compile/test/package PASS**. When using configuration cache, Gradle can restore saved configuration instead of reconfiguring from scratch; valid reuse does not equate to a failed stage.

## 7. Stage 2 — resolving dependencies and plugins

**Input:** starter/dependency coordinates, Maven BOM or Gradle platform, plugin versions, dependency constraints, repositories, scopes/configurations, and credentials if needed. The build tool builds the resolved dependency graph and downloads artifacts not yet cached.

- **Maven:** check `mvn dependency:tree`; Maven `dependencyManagement` determines default versions for managed dependencies.
- **Gradle:** check `./gradlew dependencies --configuration runtimeClasspath` or `./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath`.

~~~bash
mvn dependency:tree
# Or in a Gradle project:
./gradlew dependencies --configuration runtimeClasspath
~~~

**Output:** validly resolved artifacts/metadata in cache/repository and the actual dependency graph. **PASS:** all dependencies required by tasks resolved, no missing artifacts, SSL/auth errors, or dependency conflicts exceeding policy thresholds.

**Difference to remember:** dependency resolution can occur at different times depending on plugins/tasks and caching; it is not always a standalone visible "resolve phase". A command showing one dependency graph only proves that corresponding configuration, not that every task's classpath is identical.

**Failure examples:** starter declared properly but BOM/parent does not manage its version; private registry denies access; two libraries pull incompatible APIs. Do not debug this by inspecting the JAR: it failed **before** packaging.

## 8. Stage 3 — generating sources and processing resources

### Input

- `src/main/resources/**`, sample app configurations, OpenAPI/protobuf schemas, generator files, build properties used for filtering.
- Codegen plugins/tasks if the project uses them; not every Spring Boot project requires source generation.

### Maven and Gradle

| Task | Maven | Gradle |
| --- | --- | --- |
| Generate code before compile | Goal configured at `generate-sources`/appropriate phase | Custom/plugin generate task wired as dependency of `compileJava` |
| Copy resources to output | `resources:resources` typically at `process-resources` | `processResources` |
| Processed resources | Typically `target/classes/...` | Typically `build/resources/main/...` |
| Generated sources | Plugin-configured path, e.g. under `target/generated-sources` | Task/plugin-configured path, usually under `build/generated/...` |

**PASS:** required generators complete, outputs match schemas/contracts, needed resources are copied/filtered properly. **FAIL:** invalid schema, missing template, missing filtering variable, resources substituted for the wrong environment.

If a project genuinely has no resources, Gradle may report `processResources NO-SOURCE`. This can be a **normal** status. However, if CI expects `application.yml` and the task suddenly reports `NO-SOURCE`, treat it as **evidence of missing inputs**.

Do not put production secrets into resources packaged inside the JAR. Build artifacts should be configured per environment at deployment time whenever feasible.

## 9. Stage 4 — compiling production code

**Input:** Java sources, generated sources, compile classpath, compiler JDK, Java release target, and annotation processors. **Output:** class files, processor-generated metadata, and compilation results.

- Maven: usually in `target/classes/` via `maven-compiler-plugin` at `compile`.
- Gradle: usually in `build/classes/java/main/` via `compileJava`. Resources may reside in `build/resources/main/`.
- Java compatibility configuration: Maven `maven.compiler.release`; Gradle `options.release`/Java Toolchains.

**PASS:** compiler exits without error; all required classes are present, match the release/bytecode target, and generated annotations/metadata are intact. If the task returns code 0 yet needed sources were excluded by misconfiguration, check output directories and source set structure rather than status alone.

~~~bash
mvn compile
# Or:
./gradlew compileJava

# Once actual class files exist, inspect bytecode level:
javap -verbose target/classes/dev/example/Hello.class
# Gradle equivalent: build/classes/java/main/dev/example/Hello.class
~~~

`javap` displays the class `major version`. For example, Java 17 is major **61**, Java 21 is major **65**. Do not take the major version as proof of the JDK **running the build tool**; it only indicates the class-file target.

## 10. Stage 5 — compiling and running tests

### Input

Test sources `src/test/java`, test classpath, fixture data, test environment, mocks/test services, test JDK. Outputs include compiled test classes and test reports.

| Testing | Maven | Gradle |
| --- | --- | --- |
| Compile tests | `test-compile`, typically `compiler:testCompile` | `compileTestJava` |
| Run unit tests | `test`, typically `surefire:test` | `test` |
| Unit test reports | `target/surefire-reports/` | `build/test-results/test/` and `build/reports/tests/test/` |
| Integration tests | Failsafe at `integration-test` / `verify` **if configured** | Custom `integrationTest` or task defined by plugin/build script |
| General gate | `mvn verify` runs up to verify phase | `./gradlew check`/`build` runs tasks wired into the graph |

**Minimum PASS:** required tests **are discovered**, executed per policy, have zero failures/errors, and test reports contain results. If integration tests are required, corresponding tasks/goals, environments, and reports must exist.

Common faulty inferences:

- `BUILD SUCCESS` when the project **has no tests** or tests were skipped **does not** prove "all tests pass".
- Maven `-DskipTests` usually skips running Surefire unit tests while still compiling tests; `-Dmaven.test.skip=true` skips compiling tests too. With newer Failsafe versions, unit/integration skip properties differ: verify the exact plugin version and choose `-DskipITs` when needed.
- `./gradlew build -x test` can pass green because the `test` task was excluded from the graph; if tests are mandatory, CI must **forbid** that option.
- Gradle `NO-SOURCE` for test compile/test may be acceptable in a module without tests, but modules requiring tests must mark it a **policy fail**.
- Integration tests do not exist automatically just because a command is named `verify` (Maven) or `check` (Gradle). Plugins/tasks must be wired into the lifecycle.

Therefore, test PASS criteria include **count**, **fail/error/skipped**, **correct suite**, **correct environment**, and **actually executed or validly reused** per policy.

## 11. Stage 6 — packaging into an executable Spring Boot JAR

### Input

Compiled class files, processed resources, runtime dependencies, main application class, and Boot packaging plugin configuration.

**Maven:** `jar:jar` creates the base JAR in the `package` lifecycle; `spring-boot:repackage` converts an existing JAR/WAR into an executable archive if an execution is configured. With `spring-boot-starter-parent` and the Spring Boot plugin declared, the repackage goal is usually pre-bound. If importing only the BOM without the Boot parent, configure the plugin/execution yourself.

**Gradle:** the `bootJar` task creates the executable archive when applying the Spring Boot Gradle plugin alongside the Java plugin. Plain `jar` and `bootJar` serve different roles. `build`/`assemble` are appropriately wired by the plugin to create the artifact; still inspect the project's exact task graph.

| Output type | Maven (typical) | Gradle (typical) |
| --- | --- | --- |
| Compiled classes | `target/classes/` | `build/classes/java/main/` |
| Executable archive | `target/<artifactId>-<version>.jar` | `build/libs/<project>-<version>.jar` |
| Nested runtime dependencies | `BOOT-INF/lib/` | `BOOT-INF/lib/` |
| Application classes | `BOOT-INF/classes/` | `BOOT-INF/classes/` |
| Launch manifest | `META-INF/MANIFEST.MF` | `META-INF/MANIFEST.MF` |

**Packaging stage PASS:** the JAR file exists in the right location for the current build, has reasonable size, is readable via `jar tf`, contains the Boot loader/classes/runtime dependencies, manifest defines the entry point, and can start with a compliant Java runtime.

~~~bash
# Maven
mvn clean package
jar tf target/demo-0.0.1-SNAPSHOT.jar

# Gradle
./gradlew clean bootJar
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
~~~

**Do not confuse:** a `mvn package` exiting 0 can produce only a plain JAR if the Spring Boot Maven Plugin is not bound. A properly named JAR can still lack dependencies or have the wrong main class. Better evidence is inspecting the archive **and** testing `java -jar`/smoke test.

## 12. Stage 7 — verifying the artifact, integration tests, and quality gates

This stage answers "does the artifact **meet release criteria**?" Inputs are the packaged artifact, quality rules, unit test reports, integration tests, and verification environment.

**Maven:** `mvn verify` walks earlier phases through `verify`; only if Maven Failsafe or a quality plugin is configured at appropriate phases do those checks execute. Without binding integration tests, `verify` does not automatically create and run an integration suite.

**Gradle:** `check` is a lifecycle task commonly connecting verification tasks; `build` usually depends on `assemble` and `check` in the Java plugin. Quality plugins (Checkstyle, SpotBugs, JaCoCo, separate integration test source sets...) must be configured and wired into the graph. The mere existence of a `check` task does not mean all verification types are configured.

**Sample PASS criteria for a Spring Boot service:**

1. Required tests executed and reports confirm zero errors.
2. Static analysis or code coverage meets thresholds **if mandated by policy**.
3. Executable archive has expected name/version and no missing runtime dependencies.
4. Smoke test starts the app with test profile/environment, and required endpoints return expected values.
5. If an integration suite exists, reports and required environments are valid.

Coverage thresholds, security policies, and license requirements **must be defined by the project**, not assumed as default behavior of Maven/Gradle/Spring Boot.

**PASS for `verify` or `check` is only as meaningful as the goals/tasks bound to it**, so audit configurations and logs to know exactly which criteria were applied.

## 13. Stage 8 — install, publish, release, image

This step is **optional and has external side effects**; run it only when the pipeline genuinely needs to publish.

### Maven

- `mvn install`: after earlier phases, installs the artifact into the **local Maven repository** (`~/.m2/repository` by default). This is local output and **does not** prove the artifact was published to a company server.
- `mvn deploy`: runs earlier phases and uploads to a **remote repository** per `distributionManagement`/repository settings and proper credentials. Output is the artifact/metadata in the remote repository.
- To enforce a pre-release quality gate, run `verify` with mandatory checks first, and allow `deploy` only when it passes.

### Gradle

- `publishToMavenLocal`/`publish` are tasks of `maven-publish` when the plugin is applied and publications/repositories are configured.
- `build` is not synonymous with `publish`. Publish tasks require permissions and valid versions/repositories; successful runs should be verified against artifacts/metadata at the destination.

### Spring Boot container images

- Maven's Spring Boot plugin has the `build-image` goal; Gradle's Spring Boot plugin has the `bootBuildImage` task. They build OCI images using Buildpacks in supported configurations; usually requiring a container runtime/daemon or compatible builder service.
- **Output is an image with a tag/digest**, not necessarily pushed to a registry yet. Distinguish **build image**, **push image**, and **deploy image**.

**Release PASS:** artifact or image is present at the target system, version/tag/digest coordinates match, accessible with permissions, and checksums or digests are consistent; signing, scanning, and provenance policies are met if required. Seeing "publish task completed" while the remote registry cannot serve the artifact is insufficient evidence of distribution.

Never put production secrets/environment configs into artifact logs or commits; supply credentials via CI/CD secret mechanisms.

## 14. Stage 9 — running and verifying the service

Packaging produces a runnable file, yet **build success is not production success**. The deploy stage takes the approved artifact/image, applies profile configs, database and external service connections, and infrastructure/secrets. Output is a **running instance** and observable telemetry.

Different levels of verification:

- **Artifact-level:** `jar tf` opens cleanly, manifest and libraries are valid.
- **Process-level:** `java -jar` launches, process stays up, does not exit due to bad config.
- **Application-level:** endpoints start, routes return expected results, required profiles and configs are valid.
- **Readiness-level:** health/readiness probes checked by the deployment platform pass; databases, message brokers, or critical dependencies are in states compliant with policy.
- **Release-level:** rollout and smoke/regression checks in the live environment pass; logs/metrics/alerts monitored post-deploy.

Spring Boot Actuator can provide health/readiness endpoints when the dependency and appropriate config are added. **Do not assume `/actuator/health` exists automatically** in every project. Even an HTTP 200 on one route does not automatically prove every production dependency is healthy.

## 15. End-to-end example: one Spring Boot app using both Maven and Gradle

The example below has **one controller and one unit test**. We use the same Java code for two build options; in a real project, use **one primary build system** or define clear processes if maintaining both.

### 15.1. Java files

Structure:

~~~text
demo/
├── src/main/java/dev/example/DemoApplication.java
├── src/main/java/dev/example/Greeting.java
└── src/test/java/dev/example/GreetingTest.java
~~~

**`src/main/java/dev/example/DemoApplication.java`**

~~~java
package dev.example;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@SpringBootApplication
@RestController
public class DemoApplication {
    public static void main(String[] args) {
        SpringApplication.run(DemoApplication.class, args);
    }

    @GetMapping("/hello")
    public String hello() {
        return Greeting.message();
    }
}
~~~

**`src/main/java/dev/example/Greeting.java`**

~~~java
package dev.example;

public final class Greeting {
    private Greeting() {
    }

    public static String message() {
        return "Hello pipeline";
    }
}
~~~

**`src/test/java/dev/example/GreetingTest.java`**

~~~java
package dev.example;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingTest {
    @Test
    void returnsExpectedMessage() {
        assertEquals("Hello pipeline", Greeting.message());
    }
}
~~~

This test is a unit test for `Greeting.message()`, **not** an HTTP integration test yet. To confirm `/hello` actually serves HTTP, you must run the app and send a request, or write an appropriate integration test.

### 15.2. Option A: Maven with Spring Boot parent

**`pom.xml`**

~~~xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>4.1.2</version>
        <relativePath/>
    </parent>

    <groupId>dev.example</groupId>
    <artifactId>demo</artifactId>
    <version>0.0.1-SNAPSHOT</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-webmvc</artifactId>
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

Requires Maven and a compliant JDK installed; the Spring Boot parent manages dependencies and configures related plugins. The example omits the wrapper because we did not create wrapper files; in projects with a wrapper, replace `mvn` with `./mvnw`.

**Run through each gate:**

~~~bash
mvn validate
mvn dependency:tree
mvn compile
mvn test
mvn clean verify

# Inspect the executable artifact created by the Spring Boot plugin
jar tf target/demo-0.0.1-SNAPSHOT.jar
java -jar target/demo-0.0.1-SNAPSHOT.jar
~~~

In another terminal:

~~~bash
curl -s http://localhost:8080/hello
~~~

**Exact HTTP response body:**

~~~text
Hello pipeline
~~~

The response string contains no newline character; terminal tools may add a prompt or display formatting. Raw Maven command output varies by plugin version, cache, and environment, so **a fixed log transcript cannot be treated as mandatory stdout**.

**Observing inputs/outputs:**

1. `validate`: valid POM; does not require class files yet.
2. `compile`: generates classes in `target/classes/dev/example/`.
3. `test`: compiles/runs unit tests, reports in `target/surefire-reports/`; verify test count and failures.
4. `package` occurs on the way to `verify`: Boot plugin creates `target/demo-0.0.1-SNAPSHOT.jar` with `BOOT-INF/classes` and `BOOT-INF/lib`.
5. `verify`: **configured** verification goals must succeed; this example has not configured standalone integration tests yet.
6. `java -jar` + `curl`: smoke test confirms runtime and endpoint actually work under the active profile/port.

### 15.3. Option B: Gradle Groovy DSL

Keep the three Java files and remove `pom.xml` when using Gradle exclusively. Add:

**`settings.gradle`**

~~~groovy
rootProject.name = 'demo'
~~~

**`build.gradle`**

~~~groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '4.1.2'
}

group = 'dev.example'
version = '0.0.1-SNAPSHOT'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)
    testImplementation platform(org.springframework.boot.gradle.plugin.SpringBootPlugin.BOM_COORDINATES)

    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}
~~~

Requires a Gradle version supported by Spring Boot 4.1.2, JDK 17 discoverable by toolchain, and a compatible runtime running Gradle. If the project has a wrapper:

~~~bash
./gradlew tasks
./gradlew dependencies --configuration runtimeClasspath
./gradlew compileJava
./gradlew test
./gradlew clean build

jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
java -jar build/libs/demo-0.0.1-SNAPSHOT.jar
~~~

In another terminal:

~~~bash
curl -s http://localhost:8080/hello
~~~

The expected response body is also exactly `Hello pipeline`. On Windows, use `gradlew.bat`. With Gradle, the `build` task aggregates assemble/verification tasks when configured as in the example; inspect the actual task graph in logs to confirm `bootJar` and `test` were invoked.

## 16. Turning the matrix into automated checks in CI

Minimum policy for a Spring Boot project with mandatory unit tests:

~~~text
GATE A — Build inputs
    Exact commit, wrapper, JDK, repo locks validly configured
    -> FAIL if any mandatory condition is missing

GATE B — Resolve + compile
    Dependency graph resolved, compilation succeeds, classes match release
    -> FAIL if required classes are missing or compiler fails

GATE C — Unit tests
    Test task must run; test count > 0; failed count = 0
    -> FAIL if tests are skipped against policy, or test runner discovers no tests

GATE D — Artifact
    Executable JAR exists, is readable, has main class/runtime libs
    -> FAIL if only plain JAR exists or JAR has wrong version

GATE E — Smoke / integration
    Start app in test environment and call required endpoints
    -> FAIL if process exits, times out, or HTTP body/status violates contract

GATE F — Publication / deployment (if applicable)
    Runs only after Gate A..E pass and proper approval/credentials exist
    -> FAIL if registry/deployment health cannot verify output
~~~

In CI, preserve **evidence**: commit SHA, JDK/build tool versions, resolved dependency reports when needed, JUnit XML, artifact files, SHA-256 checksums, image digests if applicable, smoke-test status, build links, and deployed environment. Avoid printing passwords/tokens; do not log every environment variable.

### Illustrative shell pipelines (not a replacement for full CI configs)

~~~bash
# Maven
mvn clean verify

# Only when the command above succeeds, inspect the artifact:
jar tf target/demo-0.0.1-SNAPSHOT.jar
# Then run a smoke-test with explicit timeout and process cleanup in CI.
~~~

~~~bash
# Gradle
./gradlew clean build

# Only when the command above succeeds, inspect the artifact:
jar tf build/libs/demo-0.0.1-SNAPSHOT.jar
# Then run a smoke-test with explicit timeout and process cleanup in CI.
~~~

The two scripts above only illustrate **build → inspect archive order**, and are **incomplete** because they lack JAR content assertions, app launch, HTTP checks, CI environment setup, credentials, and cleanup. For a real gate, scripts/CI must halt on non-zero exit codes, assert output contents, run smoke tests with timeouts, and terminate the process after testing. If publishing is needed, add a separate publish step after all mandatory gates pass.

## 17. Reading Maven and Gradle statuses accurately

### 17.1. Maven

- `[INFO] BUILD SUCCESS`: the goals Maven executed in that invocation finished successfully according to their logic.
- `[ERROR] BUILD FAILURE`: at least one goal/setup error stopped the build; locate the **first failing goal and phase**.
- `No tests to run` or Surefire skip notices: **does not prove tests PASS**; verify test counts, policy, and runner.
- `Nothing to compile`: valid if sources did not change and outputs remain consistent, or the module has no sources; suspicious if the project is supposed to have classes and source paths are wrong.
- `mvn package`: does not run phases after `package` such as `verify` and `deploy`. `mvn verify` also does not automatically upload remote artifacts.

### 17.2. Gradle

| Task label | Meaning | Evaluation when task is mandatory |
| --- | --- | --- |
| Unlabeled / `EXECUTED` | Actions were executed | PASS when actions and assertions succeed |
| `UP-TO-DATE` | Gradle determined inputs/outputs need no rerun | Can PASS when outputs are valid and policy permits incrementality |
| `FROM-CACHE` | Outputs were restored from build cache | Can PASS when cache is trusted and outputs/metadata match |
| `NO-SOURCE` | Task had no sources to process | PASS if no sources are expected; FAIL if sources are mandatory |
| `SKIPPED` | Task did not run due to condition/exclusion | Check policy; do not automatically mark PASS |
| `FAILED` | Task failed | FAIL; investigate error and dependent tasks |

A Gradle task can be skipped via cache while **the overall build is validly green**. However, for sensitive steps like security checks, policy may require fresh execution, forbid `-x test`, or disable certain caches in release CI.

`./gradlew --dry-run build` only prints tasks intended to run; it **does not** create actual output files and does not prove PASS.

### 17.3. Distinguishing "technical status" from "quality status"

~~~text
Task status: SKIPPED
  |
  +--> Validly skipped because module has no tests? --> Conditional policy PASS
  |
  +--> Tests mandatory but bypassed with -x test? --> Policy FAIL

Task status: UP-TO-DATE
  |
  +--> Inputs unchanged, artifact valid? --> Policy PASS
  |
  +--> CI requires fresh scanner run? --> Insufficient evidence; force rerun

Tool status: BUILD SUCCESS
  |
  +--> JAR exists, executable, tests pass? --> Build gate passes
  |
  +--> Missing tests or wrong artifact? --> Separate build gate must FAIL
~~~

**In short:** exit code 0 is technical data; "release-ready" is a conclusion drawn from verification criteria defined by the project team.

## 18. Troubleshooting from the first failing stage

| Symptom | Priority stage to inspect | Evidence / troubleshooting direction |
| --- | --- | --- |
| Invalid POM or Gradle fails to configure | 1 | POM/build script syntax, plugin loader, JDK running the build |
| `Could not resolve dependency` / `Artifact not found` | 2 | Repository URL, BOM, versions, credentials, network |
| Generated class/resource not found | 3 | Whether codegen task/goal ran before compile, source-set configuration |
| `cannot find symbol` / `invalid target release` | 4 | Compiler classpath, source/imports, JDK Toolchain, release target |
| `Tests run: 0` despite mandatory tests | 5 | Test runner, patterns, JUnit engine, skip flags, test discovery |
| Test report shows failures/errors | 5 | Assertions, fixtures, DB/test isolation; prioritize root failure |
| `no main manifest attribute` or `java -jar` fails | 6 | Missing Boot repackage/bootJar, wrong JAR or manifest |
| `verify` is green yet no integration-test report | 7 | Failsafe not bound or integration task not wired into `check` |
| `401 Unauthorized` during publish | 8 | Credentials, repository server, permissions, profiles/secrets |
| Container image build green yet missing on registry | 8 | Image not pushed; distinguish local image from remote image |
| HTTP endpoint fails post-deploy despite green build | 9 | Runtime config, Java, service dependencies, readiness/smoke |

**Investigation strategy:** note the first stage that failed, check that stage's inputs, inspect actual outputs, fix one verifiable cause, and rerun the relevant gate and dependent stages. No need to wipe all caches every time; wipe only when there is evidence of corrupted cache/outputs or when testing clean reproducibility.

## 19. Multi-module: PASS must be evaluated per module and target artifact

In a monorepo/multi-module setup, modules serve different roles:

- `common` or `domain` is a library: package PASS can be a **plain** JAR, without a Boot loader or `java -jar`.
- `service` has `main`: requires an executable Spring Boot archive and smoke test.
- `integration-tests` may only run suites; `NO-SOURCE` on `compileJava` is not automatically an error if the module's purpose is testing another artifact.

**Maven reactor:** a root command can build many modules; check which modules were `FAIL`/`SKIPPED` in the reactor summary. **Gradle multi-project:** tasks have paths, e.g., `:service:bootJar` or `:common:jar`; a `BUILD SUCCESSFUL` log at root must be verified against the requested tasks.

A release must specify the **exact target artifact** (`group`/`artifact`/`version` or path/digest), rather than concluding from "the whole repo built green" while overlooking the service module to deploy.

## 20. Self-check exercises

1. **Ran `mvn package` and got `BUILD SUCCESS`. Are `verify` and integration tests guaranteed to have run?** No. `package` stops before `verify`; integration tests run only if plugins/goals are configured.
2. **`./gradlew bootJar` is green. Is `test` guaranteed to have run?** No. `bootJar` builds the archive and its dependent tasks; `test` only runs if the graph includes `test`.
3. **Is `processResources NO-SOURCE` a FAIL?** Not automatically. If there are no resources to process, it is normal; if the project requires resources, policy must FAIL it.
4. **Does `UP-TO-DATE` mean the task just executed its actions?** No; Gradle determined inputs/outputs do not require redoing work.
5. **Why does unit test `GreetingTest` passing not prove the `/hello` endpoint passes?** Because the test calls the method directly, without starting the server or sending an HTTP request.
6. **Does `java -jar` running prove production readiness?** No; configuration, external services, health/readiness probes, and rollout remain.
7. **How do Maven `install` and `deploy` differ?** Install puts the artifact into the local repository; deploy publishes to a remote repository.
8. **There are two JARs `demo-...-plain.jar` and `demo-....jar`. Which file should you inspect to run Spring Boot?** Inspect the executable archive created by `bootJar`, verify its layout, and run `java -jar`.
9. **Build reports `Tests run: 0` with exit code 0. What should a mandatory test gate do?** Mark FAIL, investigate test discovery/configuration.
10. **Build uploaded image tag `latest`. How do you prove the right image is deployed?** Record and match the digest/immutable tag against the release record, inspect the registry and runtime deployment.

## 21. Checklist to apply immediately to your project

- [ ] Identify commit, wrapper, build JVM, and compiler/toolchain.
- [ ] Document key inputs and outputs of each phase/task.
- [ ] Distinguish Maven phases, Gradle tasks, and Gradle's three internal phases.
- [ ] Verify resolved dependency graphs and selected versions.
- [ ] Ensure generated sources/resources are included in compile/package inputs.
- [ ] Verify class outputs and Java release targets.
- [ ] Ensure test reports and appropriate test counts exist; do not skip mandatory tests.
- [ ] Distinguish plain JARs from Spring Boot executable JARs; verify Boot layout.
- [ ] Use artifact smoke tests to verify process startup and HTTP contracts.
- [ ] Establish explicit quality gates for integration, static analysis, and coverage if needed.
- [ ] Publish/deploy only after the artifact and mandatory gates PASS.
- [ ] Record versions/digests/checksums, archive reports, and build links for traceability.
- [ ] Apply FAIL/SKIP/UP-TO-DATE/FROM-CACHE criteria consistently per policy.

**Core takeaway:** for every stage, always connect **Input → Processing → Output → PASS/FAIL Evidence**. Maven/Gradle tell you what ran as configured, whereas your project's release criteria determine whether it is **qualified to move forward**.

## 22. Official documentation

- [Apache Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Maven Surefire Plugin — Running Tests and Reports](https://maven.apache.org/surefire/maven-surefire-plugin/)
- [Maven Surefire Plugin — Skipping Tests](https://maven.apache.org/surefire/maven-surefire-plugin/examples/skipping-tests.html)
- [Gradle — Build Lifecycle](https://docs.gradle.org/current/userguide/build_lifecycle.html)
- [Gradle — Understanding Tasks and Task Outcomes](https://docs.gradle.org/current/userguide/more_about_tasks.html)
- [Gradle — Incremental Builds and Build Cache](https://docs.gradle.org/current/userguide/gradle_optimizations.html)
- [Spring Boot Maven Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/maven-plugin/packaging.html)
- [Spring Boot Gradle Plugin — Packaging Executable Archives](https://docs.spring.io/spring-boot/gradle-plugin/packaging.html)
- [Spring Boot — Build Systems and Starters](https://docs.spring.io/spring-boot/reference/using/build-systems.html)