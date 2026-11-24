# Cutting Unnecessary Tasks While Preserving Required Quality Gates

A fast Spring Boot build is **not** a build that skips the most tests. The right goal is **never re-running work that already has a valid result, skipping unrelated modules, and avoiding heavy steps on every minor edit**, while ensuring every change merged into main or released still passes all **quality gates** the project has committed to.

For example:

- A developer editing a single Java method can run just the relevant unit test for fast feedback.
- Pull-request CI must still run the **required** test suite for the change scope per policy, including integration tests if required for merge.
- Build tools can **reuse task outputs** from a previous run when inputs are unchanged; this is fundamentally different from passing **skip** flags that erase verification steps.
- An executable Spring Boot JAR must be **packaged and verified** before deployment; passing unit tests on an IDE classpath does not prove the packaged JAR works.

This lesson belongs to **Build Optimization** in Spring Boot Build Tooling Packaging. Examples are pinned to **Java 17, Spring Boot 3.3.13**, Maven 3.9.x, and Gradle compatible with Spring Boot 3.3. This is a learning baseline, not a statement about the latest versions. The focus is on durable strategies rather than version-specific plugin tricks.

## 1. Separating Redundant Work from Quality Barriers

Consider a typical pipeline:

```text
Commit / Pull Request
        |
        v
Resolve dependencies + compile
        |
        v
Unit tests
        |
        v
Integration tests
        |
        v
Static / architecture / dependency checks (if required)
        |
        v
Package Spring Boot executable JAR
        |
        v
Archive inspection + artifact smoke test
        |
        v
Publish / deploy
```

Sound optimization asks:

1. **Which steps are required?** Which conditions must pass before merge, release, or deploy?
2. **Which steps repeat needlessly?** For example, running identical unit tests twice in a row with unchanged inputs.
3. **Which steps can be scoped?** For example, when one module changes, avoiding building unrelated modules.
4. **Which steps can be cached?** Deterministic tasks with fully declared inputs and outputs.
5. **Which steps must never be replaced by guesses?** For example, real-database integration tests, mandatory security scans, and release artifact checks.

### Strategy comparison table

| Technique | Reduces work? | Preserves quality? | Condition |
| --- | --- | --- | --- |
| Maven `-pl :app -am` | Yes, skips unrelated modules | Potentially | Complete reactor dependency graph; unselected modules governed by policy |
| Gradle `:app:build` | Yes, selects only the task graph needed for `app` | Potentially | Task dependencies and app quality gates wired properly |
| Gradle `UP-TO-DATE` | Yes | Potentially | Inputs/outputs accurately declared, cache unpolluted by external state |
| Gradle `FROM-CACHE` | Yes | Potentially | Reuses valid outputs from a trusted cache with matching effective inputs |
| Maven `mvn test` instead of `mvn verify` while editing a method | Yes | **Local dev loop only** | Merge/release still enforces the `verify` gate |
| Maven `-DskipTests` in a release job | Yes | **No** | Skips unit tests; must never count as QA pass |
| Maven `-Dmaven.test.skip=true` | Yes | **No** | Can skip even test compilation, hiding test compile errors |
| Gradle `build -x test` in a release job | Yes | **No** | Removes test tasks from the task graph |
| Allowing test failures while ignoring exit code | Appears fast | **No** | Pipeline can release broken code |
| Running `bootJar` without `check` and shipping immediately | Yes | **Insufficient** | `bootJar` packages; it does not replace test suites |

**Core principle:** *fewer tasks* does not mean *fewer required checks*. Optimization requires a **clear mapping from quality requirements to actual executed tasks/goals**.

## 2. Define Quality Gates Before Optimizing

A project should define explicit verification tiers. They can differ across local development, Pull Requests, and releases, yet must never silently drop a policy-mandated check.

| Tier | Purpose | Example commands | Permitted conclusion |
| --- | --- | --- | --- |
| Local fast feedback | Quickly verify the fix being written | Maven single unit test; Gradle `test --tests` | **Selected tests** passed; whole project not yet verified |
| Module verification | Validate a module and its relevant dependencies | Maven `-pl/-am verify`; Gradle `:module:build` | Gates **configured** in the selected module/task graph passed |
| Required PR gate | Pre-merge verification per policy | Maven `verify`; Gradle `build` + custom checks | Required unit/integration/static checks for PR scope ran and passed |
| Release validation | Validate the shippable artifact | Full required gate + `java -jar` smoke test + artifact scan | Specific artifact meets release policy |
| Production monitoring | Detect live environment issues | Health/metrics/logs/canary | Does not replace build-time tests; post-deploy observability |

Checks such as SAST, dependency vulnerability scans, license checks, Checkstyle, SpotBugs, JaCoCo coverage thresholds, OpenAPI compatibility, or database migration validation **are only truly enforced** when written into policy and wired into required jobs/tasks. `mvn verify` or `./gradlew build` **does not magically run every check in the world** simply because the lifecycle name sounds comprehensive.

### A rule to protect quality

If a team declares "a PR may only merge when unit tests, integration tests, and static checks pass," the pipeline must ensure:

- Every check category has an explicit task/goal or CI job.
- When a check fails, the job exits with **non-zero status**—never mask failures with `|| true` or `ignoreFailures = true`.
- If a test suite unexpectedly turns up empty due to misconfiguration, the build should **fail** instead of silently passing with zero tests; enable `failIfNoTests`/`failOnNoMatchingTests` per plugin.
- Cache reuse has evidence that outputs match inputs and were not tampered with.
- Only after all gates pass is **that exact verified artifact** published/deployed.

## 3. Maven Lifecycle: `test`, `package`, and `verify` Are Not the Same

Maven organizes builds into lifecycle phases; those relevant to this lesson include:

```text
validate
   |
compile
   |
test-compile
   |
test          -> Surefire (if configured and matching tests exist)
   |
package       -> JAR/WAR Plugin; Spring Boot repackage (if configured)
   |
integration-test  -> Failsafe integration-test (if bound)
   |
verify        -> Failsafe verify and other checkers (if bound)
```

Calling `mvn verify` executes all preceding phases in order. Calling `mvn test` stops at `test` and never reaches `package`, `integration-test`, or `verify`.

| Maven command | Typically executes | Never assume |
| --- | --- | --- |
| `mvn compile` | Compiles main sources | Unit tests ran |
| `mvn test` | Compiles main/test sources and runs Surefire unit tests | Integration tests, archive checks, or release gate passed |
| `mvn package` | Runs through `package`; creates executable JAR if Boot plugin is bound | Integration tests bound after `package` ran |
| `mvn verify` | Full lifecycle through `verify`, including configured plugin goals | Arbitrary security/static scans automatically exist |
| `mvn clean verify` | Deletes old build outputs and re-runs lifecycle | Always faster; `clean` can negate incremental work |
| `mvn -pl :app -am verify` | Builds `app` and required upstream reactor modules | Unselected modules were verified too |

**Failsafe warning:** when using the Maven Failsafe Plugin, bind **both `integration-test` and `verify` goals**. Never substitute `mvn integration-test` for `mvn verify` in a release pipeline: Failsafe is designed to report test failures during `verify`, after lifecycle teardown steps have had a chance to run.

## 4. Gradle Task Graph: `build`, `check`, `test`, and `bootJar`

With the Java/Java Library plugin, lifecycle tasks relate as follows:

```text
build
├── assemble
│   └── jar / bootJar per plugins and config
└── check
    ├── test
    ├── integrationTest   (only if you configure dependsOn)
    └── staticChecks      (only if wired by a plugin or task)
```

Gradle builds a **task graph** from your requested target tasks and their task dependencies. Tasks outside the graph generally do not execute. Gradle can mark tasks `UP-TO-DATE` or `FROM-CACHE` when outputs qualify for reuse.

- `./gradlew test`: focuses on the `test` task; does not build the executable JAR by default.
- `./gradlew check`: runs verification tasks wired into `check`.
- `./gradlew bootJar`: builds the executable Spring Boot JAR, **without guaranteeing required tests ran**.
- `./gradlew build`: runs `assemble` + `check` for the project model; includes integration tests only if you wire them into `check` or an equivalent verification step.
- `./gradlew :catalog-app:build`: targets a specific subproject; required dependency tasks in upstream modules may still run.

### Why `-x test` is risky

Gradle allows:

```bash
./gradlew build -x test
```

yet official documentation cautions against abusing `-x`: it excludes that task and can also exclude upstream tasks depended on solely by the excluded task. As a result, a build **can report SUCCESS without running unit tests**.

If you need a local **package-only** path, invoke the appropriate lifecycle task like `assemble` or `bootJar` and **state clearly it is not a merge/release gate**. Never pass `-x test` in a job named "Full QA" and present the result as tested.

## 5. Spring Boot Java 17 Example with Separate Unit and Integration Tests

We use a small app where `GET /ping` returns `pong`. Two test suites verify different things:

- Unit test `GreetingServiceTest` calls the Java service directly without starting a Spring `ApplicationContext`.
- Integration test `PingEndpointIT` boots Spring Boot on a **random HTTP port**, sends a real HTTP request, and asserts status/body.

They are intentionally named after Maven Surefire (`*Test`) and Failsafe (`*IT`) conventions. Gradle configures explicit test filters and two tasks. **Without configuring `integrationTest` in Gradle or Failsafe in Maven, `build`/`verify` can report success without running ITs—precisely the pitfall this lesson prevents.**

### 5.1. Source layout

```text
build-gates-demo/
├── pom.xml                         (if choosing Maven)
├── settings.gradle                 (if choosing Gradle)
├── build.gradle                    (if choosing Gradle)
└── src/
    ├── main/java/dev/example/gates/
    │   ├── BuildGatesDemoApplication.java
    │   ├── GreetingService.java
    │   └── PingController.java
    └── test/java/dev/example/gates/
        ├── GreetingServiceTest.java
        └── PingEndpointIT.java
```

**Choose one build definition per trial:** use `pom.xml` for Maven, or `settings.gradle` + `build.gradle` for Gradle. You do not need both build tools in the same project simultaneously.

### 5.2. Main class

`src/main/java/dev/example/gates/BuildGatesDemoApplication.java`:

```java
package dev.example.gates;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BuildGatesDemoApplication {

    public static void main(String[] args) {
        SpringApplication.run(BuildGatesDemoApplication.class, args);
    }
}
```

### 5.3. Simple service

`src/main/java/dev/example/gates/GreetingService.java`:

```java
package dev.example.gates;

import org.springframework.stereotype.Service;

@Service
public class GreetingService {

    public String message() {
        return "pong";
    }
}
```

### 5.4. Controller

`src/main/java/dev/example/gates/PingController.java`:

```java
package dev.example.gates;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class PingController {

    private final GreetingService service;

    public PingController(GreetingService service) {
        this.service = service;
    }

    @GetMapping("/ping")
    public String ping() {
        return service.message();
    }
}
```

### 5.5. Unit test: no Spring startup

`src/test/java/dev/example/gates/GreetingServiceTest.java`:

```java
package dev.example.gates;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class GreetingServiceTest {

    @Test
    void messageIsPong() {
        GreetingService service = new GreetingService();
        assertEquals("pong", service.message());
    }
}
```

Changing `"pong"` to `"pang"` makes this unit test fail almost instantly without starting Tomcat. This is ideal **fast feedback** when iterating on service logic.

### 5.6. Integration test: real HTTP on a random port

`src/test/java/dev/example/gates/PingEndpointIT.java`:

```java
package dev.example.gates;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

import static org.junit.jupiter.api.Assertions.assertEquals;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class PingEndpointIT {

    @Autowired
    private TestRestTemplate restTemplate;

    @Test
    void pingIsServedOverHttp() {
        ResponseEntity<String> response =
                restTemplate.getForEntity("/ping", String.class);

        assertEquals(HttpStatus.OK, response.getStatusCode());
        assertEquals("pong", response.getBody());
    }
}
```

Random port avoids conflicts with other apps bound to 8080. This test verifies the Spring context, controller mapping, embedded server, and HTTP serialization. It is **still not a smoke test of the packaged JAR**, because the test runner uses the test/runtime classpath rather than launching the executable archive with `java -jar`.

## 6. Maven: POM with Real Bound Quality Gates

Complete `pom.xml`:

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

    <groupId>dev.example</groupId>
    <artifactId>build-gates-demo</artifactId>
    <version>1.0.0</version>
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
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-enforcer-plugin</artifactId>
                <version>3.4.1</version>
                <executions>
                    <execution>
                        <id>enforce-build-java</id>
                        <goals>
                            <goal>enforce</goal>
                        </goals>
                        <configuration>
                            <rules>
                                <requireJavaVersion>
                                    <version>[17,)</version>
                                </requireJavaVersion>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-surefire-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
            </plugin>

            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-failsafe-plugin</artifactId>
                <version>3.3.1</version>
                <configuration>
                    <failIfNoTests>true</failIfNoTests>
                </configuration>
                <executions>
                    <execution>
                        <goals>
                            <goal>integration-test</goal>
                            <goal>verify</goal>
                        </goals>
                    </execution>
                </executions>
            </plugin>

            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

Inspecting the POM from a quality standpoint:

- **Enforcer:** runs in the default `validate` phase of the bound `enforce` goal, failing if the Java version running the build is below 17. It does not replace Maven version or Dependency Convergence rules; configure those separately if policy requires.
- **Surefire 3.3.1:** runs unit tests matching `*Test` in phase `test`; `failIfNoTests=true` prevents the sample project from accidentally passing with zero unit tests.
- **Failsafe 3.3.1:** runs `*IT` in `integration-test` and checks results in `verify`; `failIfNoTests=true` catches an empty integration suite.
- **Spring Boot Maven Plugin:** starter parent binds `repackage` during `package` when declared, creating the executable JAR. It is **packaging**, not a substitute for tests.
- **Starter test:** supplies JUnit 5, `TestRestTemplate`, and Spring test support in `test` scope, keeping them out of the runtime executable JAR.

In real projects where a module legitimately **has no unit or IT tests**, do not blindly enable `failIfNoTests=true` globally and force dummy tests. Apply gate rules by module type and actual policy. Since this example **includes both tests**, this strict setup works cleanly.

### 6.1. Distinguishing the two Maven test plugins

| Plugin | Relevant default convention in example | Phase |
| --- | --- | --- |
| Maven Surefire | `GreetingServiceTest.java` (`*Test` names) | `test` |
| Maven Failsafe | `PingEndpointIT.java` (`*IT` names) | `integration-test` and `verify` |

You do not need both suites during `mvn test`: fast feedback runs Surefire in `test`, while `verify`/full gates include ITs. If a team wants ITs on every PR, **the required CI job must invoke `verify`** and inspect Failsafe reports—not just `mvn test`.

### 6.2. Fast locally without bypassing the full CI gate

While editing a method in `GreetingService`:

```bash
mvn -B -ntp -Dtest=GreetingServiceTest test
```

This runs only the selected unit test (along with earlier phases up to `test`), stopping before `package`/IT/`verify`. It **fits local iteration**, not release sign-off.

To run all unit tests without packaging:

```bash
mvn -B -ntp test
```

Before merge or release, run the gate:

```bash
mvn -B -ntp clean verify
```

With the sample POM, `verify` runs Enforcer, compilation, Surefire, `repackage`, Failsafe `integration-test`, and Failsafe `verify`. `clean` establishes a clean-output baseline; locally you can omit `clean` to keep valid build optimizations intact.

### 6.3. Verify real test reports instead of trusting `BUILD SUCCESS`

After `mvn verify`, inspect:

```text
target/surefire-reports/...
target/failsafe-reports/...
target/build-gates-demo-1.0.0.jar
```

In the sample project, confirm **at least one unit test and one integration test** were discovered and passed. Check test counts, failures, and skips in logs/reports—not just file existence. Without Failsafe bound, `mvn verify` **will not guess that `*IT` tests exist**.

## 7. Maven Skip Flags and Their Risk to Quality Gates

**Do not use the flags below as default optimizations in required PR/release jobs.** They exist for controlled cases such as temporary local packaging.

| Flag/command | Primary effect | Risk if misused |
| --- | --- | --- |
| `mvn -DskipTests package` | Skips Surefire test execution while still compiling test sources | Packages an artifact without unit tests; impact on Failsafe **depends on plugin version and config** |
| `mvn -Dmaven.test.skip=true package` | Skips compiling and running tests across supporting plugins | Can hide broken test compilation |
| `mvn -DskipITs verify` | Failsafe skips integration tests when supported by plugin/version | Removes the integration gate |
| `mvn -Dtest=GreetingServiceTest test` | Runs only the selected Surefire test | Not the full test suite |
| `mvn package` | Stops before `integration-test`/`verify` | Release artifact never passed the Failsafe gate |
| `mvn -DfailIfNoTests=false verify` | Allows passing even with zero tests in a required suite | Hides misconfiguration or missing tests |

**Version-sensitive detail to remember:** Maven Surefire binds `-DskipTests` to skipping unit-test execution while keeping test compilation; `-Dmaven.test.skip=true` is also honored by the Compiler Plugin to skip test compilation. Maven Failsafe **changed `skipTests` property binding in newer releases** (for instance, starting in Failsafe 3.6.0, `-DskipTests` no longer behaves identically for Failsafe as in earlier releases). Therefore, use the dedicated `-DskipITs` flag if temporarily skipping ITs locally, and **check Failsafe logs for your project's exact version**. Never treat it as an invariant rule that `-DskipTests` skips every test suite in every version.

**Never hardcode `skipTests=true` in a parent POM just to make local builds feel faster** if required CI inherits it. Instead, maintain two clearly named commands or CI jobs: *local-fast* and *required-verification*. Release gates must never pass skip flags.

### Using the Maven reactor to build only affected modules

In a monorepo, narrow scope with:

```bash
mvn -B -ntp -pl :catalog-app -am verify
```

This is a **snippet applicable only to a monorepo containing `catalog-app`**, not directly runnable on the single-module `build-gates-demo` above. `-pl` selects the app; `-am` builds required upstream modules while skipping unrelated ones.

However, **unselected modules** have no tests run in that job. If policy requires verifying all modules before merge/release, a separate required job must test the remainder or run full-reactor verification at the right stage. Never use `-pl` to "dodge" a broken module's tests.

## 8. Gradle: Separating Unit and Integration Tests While Keeping `build` as the Full Gate

Use the **same Java files** from Section 5. Replace the POM with these two Gradle files.

`settings.gradle`:

```groovy
rootProject.name = 'build-gates-demo'
```

`build.gradle` (Groovy DSL):

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'dev.example'
version = '1.0.0'

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

tasks.named('test', Test) {
    useJUnitPlatform()
    filter {
        includeTestsMatching '*Test'
        failOnNoMatchingTests = true
    }
}

tasks.register('integrationTest', Test) {
    description = 'Run HTTP integration tests before verification is complete'
    group = 'verification'

    testClassesDirs = sourceSets.test.output.classesDirs
    classpath = sourceSets.test.runtimeClasspath
    useJUnitPlatform()

    filter {
        includeTestsMatching '*IT'
        failOnNoMatchingTests = true
    }

    shouldRunAfter tasks.named('test')
}

tasks.named('check') {
    dependsOn tasks.named('integrationTest')
}
```

**Why does this configuration preserve the gate?**

1. `test` filters classes ending in `Test`—`GreetingServiceTest` here—for fast feedback when invoked alone.
2. `integrationTest` reuses the compiled test source set, filters `*IT`—`PingEndpointIT` here—and uses JUnit Platform. This is a **new** task; it does not appear automatically just from naming a file `*IT.java`.
3. `check.dependsOn(integrationTest)` ensures `./gradlew check` and `./gradlew build` in the Java lifecycle **must run** `integrationTest`.
4. `failOnNoMatchingTests=true` fails filtering when no tests match instead of silently passing with "0 tests."
5. `shouldRunAfter test` expresses ordering preference when both are in the graph, without making `test` a hard dependency of `integrationTest`. Both run during `build` because `check` depends on `test` (Java plugin) and `integrationTest` (our configuration).
6. `bootJar` packages the executable JAR, and does not substitute for `check`.

In production projects, if ITs need separate runtime/data, use a **dedicated `integrationTest` source set / JVM Test Suite**, Docker/Testcontainers, or separate test resources. This example intentionally splits by **class-name filter** to keep the source tree intact and make the quality-gate logic easy to verify. When scaling up, manage classpaths, test dependencies, CI services, and IT cacheability explicitly.

### Gradle commands: fast locally, complete in CI

Assuming a compatible Gradle Wrapper, on Linux/macOS:

```bash
# Single unit test while editing code:
./gradlew test --tests 'dev.example.gates.GreetingServiceTest'

# All unit tests:
./gradlew test

# Run IT suite alone:
./gradlew integrationTest

# Full verification gate: unit + integration:
./gradlew check

# Build: verification + executable archive:
./gradlew build
```

Windows uses `gradlew.bat`. If no Wrapper exists yet, use a compatible Gradle version managed in your build setup; do not assume `gradlew` already exists.

`./gradlew bootJar` is suited for quickly checking **packaging**, yet **must not replace `./gradlew build`** in required CI. In the example above, `./gradlew build` pulls in both `test` and `integrationTest` via `check`.

### Inspecting the task graph

```bash
./gradlew build --dry-run
./gradlew tasks --all
```

`--dry-run` shows planned tasks **without creating outputs or running tests**. It is a graph-analysis tool, not QA proof. In a real build, look for:

```text
:test
:integrationTest
:check
:bootJar
:build
```

Displayed order/names may vary across Gradle versions or customizations, but required steps must appear in the graph or have validly reused outcomes per policy. If `integrationTest` is missing during `build`, inspect `check.dependsOn(...)` and applied plugins.

## 9. Gradle `UP-TO-DATE` and Build Cache: Skip Re-Runs, Not Gates

Gradle offers multiple optimization layers:

1. **Task avoidance:** tasks outside the selected graph are not scheduled.
2. **Up-to-date checks:** when task inputs/outputs are declared and local outputs remain valid, Gradle can mark them `UP-TO-DATE`.
3. **Build cache:** when a cacheable task sees identical effective inputs, Gradle can restore outputs from local/remote cache as `FROM-CACHE`.
4. **Incremental compilation:** certain tasks/compilers do less work when only part of the inputs change.
5. **Configuration cache:** saves the configuration phase result when scripts/plugins comply; distinct from task output caching.

Example log:

```text
> Task :compileJava UP-TO-DATE
> Task :test FROM-CACHE
> Task :integrationTest
> Task :check
> Task :bootJar
BUILD SUCCESSFUL
```

This is an **illustrative log**, not guaranteed output on every machine: tasks may be `EXECUTED`, `NO-SOURCE`, `UP-TO-DATE`, `FROM-CACHE`, or skipped depending on actual state.

### 9.1. Enabling the build cache

Single run:

```bash
./gradlew build --build-cache
```

Or configure `gradle.properties`:

```properties
org.gradle.caching=true
```

**Do not assume every task is cacheable.** Gradle only caches tasks with complete input/output metadata and safe conditions; custom tasks reading undeclared env vars, time, network, or secrets can return stale/incorrect outputs.

### 9.2. Is caching tests safe?

Pure Java tests depending strictly on sources, dependencies, and declared properties can fit output caching well. However, **integration tests** frequently involve databases, Docker services, network APIs, timezones, wall-clock time, OS environment, or credentials. Caching those can miss regressions outside the code.

Rules:

- Cache tests only when behavior is truly **hermetic/deterministic** or all external inputs are modeled.
- Never cache scan/IT results that depend on external services using only the commit hash as the key.
- Verify tasks cache via accurate inputs rather than a custom task forgetting to declare an input.
- If policy demands **fresh integration execution** on release, configure tasks/CI to run fresh; never use a cache hit as proof that production dependencies are healthy.
- Remote caches require a trust model: control who can write, guard against cache poisoning, and keep sensitive data out of cached outputs.

In our example, `PingEndpointIT` only binds a local random port with no external services, making it suitable for studying input-based caching; do not generalize that to every integration test being safely cacheable.

### 9.3. When should you force re-execution?

Use for **diagnosis**, not as a default in optimization loops:

```bash
./gradlew check --rerun-tasks --no-build-cache
```

This forces tasks in the graph to execute instead of reusing up-to-date or build-cache outputs. Useful when suspecting stale caching or misdeclared inputs, at the cost of slower runs; clean CI may also enforce its own container/cache policies.

**Do not run `clean` on every file save**: `clean` deletes outputs and destroys local incremental history. For release baselines or when suspecting stale outputs, `clean build` verifies from a clean state.

## 10. Maven and Gradle: Optimizing the Same Goals via Different Mechanisms

| Scenario | Maven | Gradle |
| --- | --- | --- |
| Run one local unit test | `mvn -Dtest=GreetingServiceTest test` | `./gradlew test --tests '*GreetingServiceTest'` |
| Run unit tests only | `mvn test` | `./gradlew test` |
| Require both unit + IT in example | `mvn verify` with Failsafe goals bound | `./gradlew check` with `integrationTest` wired to `check` |
| Require executable JAR and tests | `mvn verify` + artifact inspection | `./gradlew build` + artifact inspection |
| Select app/module in monorepo | `mvn -pl :app -am verify` | `./gradlew :app:build` |
| Inspect work graph | `mvn help:effective-pom`, Reactor Summary/logs | `./gradlew build --dry-run` |
| Reuse unchanged outputs | Maven/plugin-specific, repository caching; no default Gradle-style task cache | `UP-TO-DATE` and `--build-cache` |
| When CI needs a clean build | `mvn clean verify` | `./gradlew clean build` |
| Dangerous shortcuts to avoid | Never use `-DskipTests`/`-Dmaven.test.skip` in required gates | Never use `-x test`/`enabled=false` in required gates |

**Do not describe Maven 3 as having a built-in Gradle-style build cache.** Maven has incremental/plugin optimizations, dependency caching, and its own extension ecosystem; skipping/reuse behaves differently from Gradle. If a team adopts the Maven Build Cache Extension, verify its correctness explicitly; never assume `mvn verify` caches task outputs out of the box like Gradle.

## 11. Cutting Time Through Triage Instead of Disabling Tasks

Prioritize approaches in order from lowest risk upward:

### 11.1. Measure before editing

Before optimizing, record at least:

- Total cold/warm build durations.
- Compile, unit test, integration test, packaging, and static check times.
- Test counts (ran/passed/failed/skipped) and modules/tasks processed.
- Cache hits/misses, remote repository downloads, and container startup times.
- JDK, Maven/Gradle/Boot plugin versions, CPU/RAM, and CI environment.

Helpful commands:

```bash
# Maven:
mvn -B -ntp verify

# Gradle: local task timing report:
./gradlew build --profile
```

Gradle `--profile` generates a local task/configuration profile report, **not an automatic release gate**. Maven prints per-plugin/phase logs and supports profiling extensions or CI step timestamps; never claim a percentage speedup without measuring identical inputs and environments.

### 11.2. Narrow scope along the dependency graph

Maven monorepo:

```bash
mvn -B -ntp -pl :catalog-app -am verify
```

Gradle monorepo:

```bash
./gradlew :catalog-app:build
```

Both commands are **illustrative for a repo containing `catalog-app`**. They target the app while still building upstream dependencies. Savings come from **skipping unrelated modules**, not dropping real dependencies.

**QA condition:** if required PR policy also mandates verifying indirectly affected downstream consumers, add jobs/selection to cover them. An API change in a core module can break downstream services, so testing only `core` is insufficient.

### 11.3. Do not repackage when only testing logic

In local dev:

- Maven `mvn test` stops before `package`.
- Gradle `./gradlew test` runs only the task graph needed for unit tests.
- Gradle `./gradlew classes` verifies main source compilation but does **not** run tests.

Afterward, the **full CI gate** must still package, run integration tests, and check the release artifact per policy.

### 11.4. Optimize dependencies and annotation processing

- Eliminate duplicate or unused dependencies, without stripping runtime libraries the app actually needs just to shrink the JAR.
- Put annotation processors on the dedicated processor path; avoid letting processors run inadvertently from the regular classpath.
- For heavy code generation, declare task inputs/outputs and generated sources cleanly so Gradle incremental/build cache works safely.
- Do not hand-commit generated sources just to "avoid building" when generation is part of quality/reproducibility; external contract artifacts may have separate policies.
- If Spring Boot `bootJar`/Maven `repackage` rebuilds the archive when dependencies change, that is **necessary work**—do not disable release packaging just to chase faster timings.

### 11.5. Enable parallelism only when tests and plugins are safe

Maven offers reactor-level parallel builds:

```bash
mvn -B -ntp -T 1C verify
```

`-T 1C` scales concurrency with CPU cores. It **is not guaranteed faster** on single-module repos and can overload CPU/RAM, raise lock contention, or expose non-thread-safe plugins. Tests sharing ports, databases, or filesystems can fail intermittently. Enable only after checking parallel safety, resource limits, and Maven thread-safety warnings.

Gradle supports multi-project parallel execution:

```properties
org.gradle.parallel=true
```

Still ensure tasks declare dependencies/outputs clearly, tests avoid shared mutable state, and CI runners have sufficient resources. **Do not equate parallelism with skipping verification**: outcomes must remain deterministic and all required tasks must remain in the graph.

## 12. Separate Local, PR, and Release Into Three Clear Lanes

Instead of one skip flag everywhere, define explicit workflows:

### Local: optimize for short feedback loops

```bash
# Pick one build tool.

# Maven: one focused test
mvn -B -ntp -Dtest=GreetingServiceTest test

# Gradle: one focused test
./gradlew test --tests 'dev.example.gates.GreetingServiceTest'
```

Developers must **never** present this as a "full QA pass." It confirms only the targeted subset ran.

### Pull Request: full required quality gates

```bash
# Maven, sample POM with Failsafe bound:
mvn -B -ntp verify

# Gradle, sample build.gradle with integrationTest -> check:
./gradlew build --build-cache
```

These are **two alternatives**—do not run both Maven and Gradle for one project unless the team intentionally maintains dual build definitions.

If static analysis, license/security checks, or quality thresholds exist, wire them into required CI jobs with mandatory status checks. Never bury them behind an "optional" profile disabled in the PR pipeline.

### Release: tested artifact, smoke-tested, published only on pass

Example:

```bash
# Maven:
mvn -B -ntp clean verify

# Or Gradle:
./gradlew clean build --build-cache
```

After the build, inspect the exact output file:

```text
target/build-gates-demo-1.0.0.jar            (Maven)
build/libs/build-gates-demo-1.0.0.jar       (Gradle)
```

**Requiring `clean` on every PR is unnecessary** on clean runners or when inputs are well-managed, whereas release validation may deliberately choose a clean baseline to minimize stale-output risk. Base that on environment and policy rather than a superstition that "clean is always better."

## 13. Artifact Inspection: Passing Tests Do Not Mean the JAR Runs

A Spring Boot executable JAR typically contains:

```text
META-INF/MANIFEST.MF
org/springframework/boot/loader/launch/JarLauncher.class
BOOT-INF/classes/dev/example/gates/BuildGatesDemoApplication.class
BOOT-INF/classes/dev/example/gates/GreetingService.class
BOOT-INF/classes/dev/example/gates/PingController.class
BOOT-INF/lib/spring-boot-3.3.13.jar
BOOT-INF/lib/...
```

`BOOT-INF/lib` holds runtime dependencies, while `BOOT-INF/classes` holds app classes and resources. The Spring Boot Loader uses manifest entries `Main-Class` and `Start-Class` to launch the app via `java -jar`.

Inspect the Maven artifact:

```bash
jar tf target/build-gates-demo-1.0.0.jar
unzip -p target/build-gates-demo-1.0.0.jar META-INF/MANIFEST.MF
```

For Gradle:

```bash
jar tf build/libs/build-gates-demo-1.0.0.jar
unzip -p build/libs/build-gates-demo-1.0.0.jar META-INF/MANIFEST.MF
```

Typical manifest entries in Spring Boot 3.3:

```text
Main-Class: org.springframework.boot.loader.launch.JarLauncher
Start-Class: dev.example.gates.BuildGatesDemoApplication
```

These are the key lines to check, not the entire manifest. Running `jar tf` and inspecting the manifest catches accidentally deploying `-plain.jar` or an un-repackaged JAR.

**Safe optimization:** you do not need a full JAR smoke test on every Java file save. For releases, however, launching the exact executable JAR with an HTTP probe is high-value because it tests packaging, loader, dependencies, and runtime startup in ways classpath-based unit/IT tests do not.

## 14. Standalone Smoke Test for the Executable JAR

Once all unit/integration tests and archive checks pass, run the real artifact. Locally, for example on port 18080:

```bash
java -jar target/build-gates-demo-1.0.0.jar --server.port=18080
```

If using Gradle, replace the path with `build/libs/build-gates-demo-1.0.0.jar`. In a **second terminal** once Spring Boot has started:

```bash
curl -fsS http://localhost:18080/ping
```

Exact response body:

```text
pong
```

This is a smoke test on the packaged archive. It **does not** replace full integration suites or production monitoring, yet it catches missing dependencies, wrong main classes, startup config bugs, or deploying the wrong archive.

### Shell gate example with cleanup for Linux CI

This applies **after Maven has built**; for Gradle update the `APP` variable. Runner needs `bash`, JDK, and `curl`:

```bash
#!/usr/bin/env bash
set -euo pipefail

APP="target/build-gates-demo-1.0.0.jar"

java -jar "$APP" --server.port=18080 > boot-smoke.log 2>&1 &
pid=$!

trap 'kill "$pid" 2>/dev/null || true; wait "$pid" 2>/dev/null || true' EXIT

ready=0
response=""
for i in {1..30}; do
    if response=$(curl -fsS http://localhost:18080/ping 2>/dev/null); then
        ready=1
        break
    fi
    sleep 1
done

test "$ready" -eq 1
test "$response" = "pong"
echo "PASS: packaged Spring Boot JAR serves /ping"
```

When successful, the script prints:

```text
PASS: packaged Spring Boot JAR serves /ping
```

Limitations: this sample uses fixed port `18080`; on shared CI runners allocate ports/isolate properly so another process cannot answer on the same port. A production release job should also verify PID liveness, artifact checksums, logs, timeouts, and port allocation. The `trap` cleanup ensures no background process lingers after the script exits.

**Never smoke-test only from source via `spring-boot:run`/`bootRun`** when the goal is validating the release artifact: those commands use build-output classpaths rather than opening the shipped executable JAR.

## 15. Measuring: Real Optimization vs. Dropped Checks?

To compare before/after, record evidence against the same baseline:

| Metric | What to record | Why |
| --- | --- | --- |
| Build duration | Total time, cold/warm, same runner class | Fair comparison |
| Compile time | Main/test compilation | Spots heavy processors/generators |
| Unit test count | Discovered/executed/passed/failed/skipped | Ensures "speedup" didn't come from running 0 tests |
| Integration test count | Discovered/executed/passed/failed/skipped | Catches ITs silently dropping out of lifecycle |
| Static/security jobs | Status and rule/scan versions | Confirms required gates remain intact |
| Gradle task outcomes | `EXECUTED`, `UP-TO-DATE`, `FROM-CACHE` | Distinguishes valid reuse from skips |
| Maven reactor scope | Modules built vs. unaffected modules | Verifies scoping |
| Artifact check | Manifest/`BOOT-INF`/checksum | Ensures deployable output |
| Smoke test | Startup status and HTTP contract | Validates the built artifact |

Illustrative comparison table (not real measurements):

| Before optimization | After valid optimization |
| --- | --- |
| Full reactor runs even when only `app` changed | Targeted reactor/build following dependency graph |
| Rebuilds all classes and resources every run | Gradle reuses outputs when inputs are unchanged |
| Unit suite has 12 passing tests | Still has 12 passing tests when required gate runs |
| IT suite has 3 passing tests | Still has 3 passing tests or policy-verified cache |
| Artifact smoke test passes | Artifact smoke test still passes |
| All steps recorded | All steps recorded; only redundant work reduced |

**If test count drops from 12 to 0 without a policy change, that is a regression in gate coverage, not a valid optimization.** If a task changes from `EXECUTED` to `FROM-CACHE`, verify cache trust and inputs before counting it as valid savings.

## 16. Avoiding Accidental Gate Bypasses in CI

### 16.1. Never mask exit codes

Never write:

```bash
mvn verify || true
./gradlew build || true
```

in required validation. Those commands let a shell job succeed even when Maven/Gradle failed. If CI must always archive logs/reports after failure, use CI `finally`/`post` blocks or store the exit code and return the non-zero status accurately.

### 16.2. Never ignore test failures

In Maven, never enable `maven.test.failure.ignore` to "improve the pass rate" of a release job; in Gradle, never set `ignoreFailures = true` on required `Test` tasks. Those flags make reports look green without verifying the software works.

### 16.3. Prevent unintentionally empty suites

Scenarios:

- Failsafe is configured, yet a test is named `PingEndpointIntegration.java` and misses the default `*IT` pattern.
- An `integrationTest` task exists, yet `check.dependsOn(integrationTest)` was forgotten.
- Tests sit in another source set that is never compiled.
- A Gradle filter uses the wrong name and runs zero tests.

Countermeasures: inspect reports and test counts; enable `failIfNoTests`/`failOnNoMatchingTests` per module policy; add CI assertions checking which gates ran. **If a project legitimately has no ITs, do not write fake tests; document why that gate does not apply**.

### 16.4. Never consume outputs from untrusted branches

Remote caches and shared artifacts can contain code, test reports, and dependencies. If a fork or untrusted user job can **write** to the same trusted cache used by releases, cache poisoning becomes a risk. CI should separate read/write cache permissions and keep secrets out of untrusted PR jobs. Reusing build outputs must preserve integrity, not just maximize cache hit rates.

### 16.5. Never ship a different artifact than the one tested

If PR/release validation tested file A while the deploy script rebuilds file B with a different Java version, profile, or dependencies, the validation evidence no longer applies. Attach and publish **the exact file that passed the gate**, along with its checksum/digest and provenance. For container images, verify the image copies that exact Boot JAR.

## 17. Maven/Gradle Scenarios Requiring Different Decisions

**Scenario A: A developer edits only `GreetingService.message()`.**

*Recommendation:* Run a single unit test for fast feedback. Before merge, the required gate still runs full Surefire + Failsafe / Gradle `check` per policy.

**Scenario B: A PR edits only the README or code-unrelated docs.**

*Recommendation:* Change detection/path filters may skip certain heavy jobs **if** policy confirms the edits cannot affect the build and required status checks still resolve properly. Build scripts, generated docs, API specs, Dockerfiles, and release configs sometimes live under "docs" yet affect the product, so never skip using overly broad patterns.

**Scenario C: A core module changes its API while an app module has no source edits.**

*Recommendation:* Test downstream consumers along the dependency graph. Maven `-amd` or appropriate Gradle task/project selection helps scope affected consumers; never test only `core`, as the app's compile contract may be broken.

**Scenario D: Gradle reports `:test FROM-CACHE`.**

*Recommendation:* If the task is cacheable and inputs are accurate, this can be valid reuse. Check cache policy and test reports; for integration tests touching external systems, consider requiring fresh execution.

**Scenario E: Maven `mvn package` builds the Boot JAR cleanly.**

*Recommendation:* Do not assume integration tests passed. When Failsafe binds to `integration-test`/`verify`, required gates must call `mvn verify`. Run artifact smoke tests per release policy.

**Scenario F: Gradle `bootJar` is faster than `build`.**

*Recommendation:* Expected, because `bootJar` does not run `check`. It is a packaging task, not full verification. Fine locally, never a replacement for the release gate.

**Scenario G: Maven uses `-Dmaven.test.skip=true` to build a JAR quickly.**

*Recommendation:* Recognize this skips test compilation as well across supporting plugins. Never use in releases; switch to a scoped local test command when fast feedback is needed.

**Scenario H: Failsafe 3.6+ still runs ITs despite `-DskipTests`.**

*Explanation:* Flag binding behavior changed. Check plugin version and logs; if temporarily skipping ITs locally, use `-DskipITs`. On required gates, use no skip flags.

**Scenario I: CI enables `--parallel`/`-T` and tests turn flaky.**

*Recommendation:* Audit test isolation, ports, DB state, file locks, RAM, and plugin thread safety. Keep parallelism only when results are deterministic; never swallow flaky failures.

**Scenario J: IT fails because an external database briefly went down.**

*Recommendation:* This may be an infrastructure or dependency contract failure, not something to turn green with permanent skips. Stabilize test environments, apply policy-bounded retries if appropriate, and record root cause. Required gates must still accurately signal readiness.

## 18. Checklist Before Accepting a Build Optimization

### Work scope

- Measured cold/warm baselines rather than claiming "faster" without data.
- Scoped modules/tasks via the dependency graph without dropping affected consumers.
- Avoided redundant local phases/tasks; caching and incremental builds configured cleanly.
- Avoided abusing `clean` when fast feedback is needed.
- Enabled parallelism only after proving tests and plugins are thread-safe.

### Quality gates

- Mandatory unit tests report counts and fail the build on test failures.
- Mandatory integration tests are wired into Maven `verify`, Gradle `check`, or required CI jobs.
- Policy-mandated static/architecture/security/license checks have explicit required status checks.
- Flags like `skipTests`, `maven.test.skip`, `skipITs`, and `-x test` never appear in required gate commands.
- `ignoreFailures`, `maven.test.failure.ignore`, and `|| true` are never used to hide red builds.
- Caching enforces trust/input policies; critical external-state checks are not silently bypassed.
- Unexpectedly empty test suites fail the build unless an approved exception exists.

### Final artifact

- The build outputs the proper **Spring Boot executable JAR**, never deploying a plain JAR by mistake.
- Archive includes the main class, Boot loader, runtime dependencies, and valid manifest.
- `java -jar` with an HTTP smoke test runs on the exact release artifact at the release gate.
- Only verified artifacts are published/deployed, with version/digest and traceable logs.
- Never equate "build success" with "application ready for production."

**Conclusion:** Cut unnecessary tasks through **targeted scoping, accurate task dependencies, incremental/up-to-date/build caching, fast local test selection, and eliminating duplicate work**. Preserve quality via **explicit required verification paths**: Maven `verify` with bound Surefire/Failsafe or Gradle `build` with `check` wiring all test tasks, plus policy-required static/security checks and an executable-artifact smoke test. **Optimization means avoiding redundant work—not faking a green build by skipping checks.**

### Official References

- Apache Maven — Build Lifecycle: https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html
- Apache Maven — Working with Multiple Modules: https://maven.apache.org/guides/mini/guide-multiple-modules.html
- Maven Surefire 3.3.1 — Skipping Tests: https://maven.apache.org/components/surefire-archives/surefire-3.3.1/maven-surefire-plugin/examples/skipping-tests.html
- Maven Failsafe 3.3.1 — Usage: https://maven.apache.org/components/surefire-archives/surefire-3.3.1/maven-failsafe-plugin/usage.html
- Maven Failsafe — Integration Test Goal: https://maven.apache.org/surefire/maven-failsafe-plugin/integration-test-mojo.html
- Gradle — Controlling Task Execution: https://docs.gradle.org/current/userguide/controlling_task_execution.html
- Gradle — Testing in Java & JVM Projects: https://docs.gradle.org/current/userguide/java_testing.html
- Gradle — Build Cache: https://docs.gradle.org/current/userguide/build_cache.html
- Gradle — Multi-Project Builds: https://docs.gradle.org/current/userguide/multi_project_builds.html
- Spring Boot 3.3 — Maven Plugin Packaging: https://docs.spring.io/spring-boot/3.3/maven-plugin/packaging.html
- Spring Boot 3.3 — Gradle Plugin Packaging: https://docs.spring.io/spring-boot/3.3/gradle-plugin/packaging.html
