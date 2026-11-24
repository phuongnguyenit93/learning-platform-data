# Integrating Formatting Checks, Static Analysis, and Coverage into Maven verify or Gradle check

## 1. Goal: Making Code Quality a Condition for Build Success

In a Spring Boot project, passing tests alone does not prove that code is consistently formatted, free of latent bugs, or sufficiently tested. Three verification groups are commonly added to a build's **quality gate**:

1. **Format check**: verifies code follows a uniform formatter—for example, Spotless paired with Google Java Format. The goal is checking, not silently rewriting code in CI.
2. **Static analysis**: inspects source or bytecode without executing the code paths under review. For instance, PMD detects bug-prone Java patterns, Checkstyle enforces style rules, and SpotBugs inspects bytecode patterns. Each tool covers a different scope.
3. **Test coverage**: measures the bytecode executed by tests. For instance, JaCoCo computes line/branch/instruction coverage and enforces minimum thresholds.

The end goal is: **a single command shared locally and in CI exits non-zero whenever any mandatory check fails**.

- With **Maven**, the standard command is `./mvnw verify` (Windows: `mvnw.cmd verify`). Plugin goals must be **bound to the lifecycle**, typically in the `verify` phase.
- With **Gradle**, the standard command is `./gradlew check` (Windows: `gradlew.bat check`). Verification tasks must belong to the **`check` task dependency graph**.

Running `spotless:check`, `pmd:check`, or `jacocoTestCoverageVerification` once manually without wiring them into the lifecycle/task graph **does not mean** `verify` or `check` will execute them.

## 2. Maven and Gradle Comparison Table

| Capability | Maven | Gradle | What fails the build? |
|---|---|---|---|
| Unit tests | Maven Surefire Plugin in `test` phase | `test` task as a dependency of `check` via Java plugin | Test failures or errors during test execution |
| Formatting | Spotless Maven Plugin goal `spotless:check` | Spotless Gradle task `spotlessCheck` | Sources differ from expected formatter output |
| Applying formatting locally | `spotless:apply` | `spotlessApply` | This command **modifies files**; never use it as a CI verification gate |
| Java source static analysis | Maven PMD Plugin goal `pmd:check` | PMD plugin: `pmdMain`, `pmdTest` | Rule violations exceeding configured threshold |
| Alternate/additional Java style rules | Maven Checkstyle Plugin goal `checkstyle:check` | Checkstyle plugin: `checkstyleMain`, `checkstyleTest` | Rule set violations |
| Bytecode analysis | SpotBugs Maven plugin goal `spotbugs:check` | SpotBugs Gradle plugin and related tasks | Violations configured to fail |
| Collecting coverage data | JaCoCo `prepare-agent` + tests | JaCoCo agent attached to `Test` tasks | Data collection alone is not a gate |
| Generating coverage reports | JaCoCo `report` | `jacocoTestReport` | Tool/report error, **does not fail by default on low %** |
| Enforcing coverage thresholds | JaCoCo `check` | `jacocoTestCoverageVerification` | Coverage ratio falls below rules |
| Single entry point | `mvn verify` | `gradle check` | Any wired check returns a failing exit code |

**Core difference:** Maven uses a **phase lifecycle** with plugin goals bound to phases; Gradle uses a **task graph** with `dependsOn` edges. Distinguish "tool declared" from "tool guaranteed to run when invoking the primary command."

## 3. What Does Maven `verify` Actually Run?

The Maven default lifecycle typically traverses phases in this order:

```text
validate -> compile -> test -> package
           -> integration-test -> verify -> install -> deploy
```

When running `./mvnw verify`, Maven executes phases up through `verify`, including all plugin goals bound to them. **Not every phase** necessarily has goals or integration tests. A Spring Boot project using `spring-boot-starter-parent` inherits many default plugin settings, yet it does not automatically gain Spotless, PMD, or JaCoCo coverage gates simply by invoking `verify`.

Example intentional binding:

```text
initialize       -> JaCoCo prepare-agent
test             -> Surefire runs JUnit, writes target/jacoco.exec
package          -> Packages JAR (appropriate Spring Boot config)
verify           -> Spotless check
                 -> PMD check
                 -> JaCoCo report
                 -> JaCoCo check (evaluates thresholds)
```

JaCoCo `prepare-agent` must configure the JVM agent **before tests execute**. JaCoCo `report` reads execution data produced by tests. JaCoCo `check` requires explicit rules: without configured thresholds, generating a report does not enforce your organization's coverage targets.

**Among goals bound to the same phase, order can matter.** In the POM example below, JaCoCo `report` is placed before `check` so the report is generated before thresholds are evaluated. However, builds normally halt on the first failing gate, so you cannot assume every later report is generated in the same failing run. CI should archive whatever report artifacts were produced even when the job exits non-zero.

## 4. What Does Gradle `check` Actually Run?

With the Gradle Java plugin, `check` is the lifecycle verification task. By default it depends on `test`; additional plugins register analysis tasks:

- The PMD plugin automatically wires `pmdMain` and `pmdTest` into `check`.
- The Checkstyle plugin automatically wires `checkstyleMain` and `checkstyleTest` into `check`.
- The Spotless Gradle plugin usually adds `spotlessCheck` to `check`, though wiring it explicitly makes project policy auditable.
- The JaCoCo plugin creates `jacocoTestReport` and `jacocoTestCoverageVerification`, yet **verification is NOT automatically a dependency of `check`**. You must wire it if you want `check` to enforce coverage.

Target graph for the Gradle example below:

```text
./gradlew check
       |
       +-- test --------------------------------+
       |                                        |
       +-- pmdMain / pmdTest (via PMD plugin)   |
       |                                        v
       +-- spotlessCheck               jacocoTestReport
                                                |
                                                v
                                    jacocoTestCoverageVerification
```

The diagram shows logical dependencies, not guaranteed log ordering or strictly vertical execution. `check` succeeds only when every required dependency task succeeds.

**Distinguishing `check` and `build`:** in projects using the Java plugin, `build` normally depends on `assemble` and `check`. Thus, wiring gates into `check` means running `build` triggers them too. If you invoke only `bootJar` or `assemble`, **never assume** all quality gates ran; CI policy should explicitly invoke `check` or `build`.

## 5. Preparing a Java 17 Spring Boot Project for Practice

This lesson uses a shared example for Maven and Gradle. Initialize a Spring Boot Java project with:

- Java 17+ compatible with the Spring Boot version.
- Spring Boot 3.5.x (configuration below uses `3.5.16`).
- `spring-boot-starter-test` dependency for JUnit Jupiter.
- Either Maven **or** Gradle, with its corresponding wrapper.

Source structure:

```text
quality-demo/
├── pom.xml or build.gradle
├── mvnw, mvnw.cmd  [if Maven chosen]
├── gradlew, gradlew.bat [if Gradle chosen]
├── src/
│   ├── main/java/com/example/quality/
│   │   ├── QualityApplication.java
│   │   └── DiscountCalculator.java
│   └── test/java/com/example/quality/
│       └── DiscountCalculatorTest.java
└── target/ or build/   [generated after build]
```

**Do not create both build files to mix workflows.** The Java files below are shared across **two** alternative configs in the Maven and Gradle sections.

### 5.1. Spring Boot Application

File `src/main/java/com/example/quality/QualityApplication.java`:

```java
package com.example.quality;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class QualityApplication {
    public static void main(String[] args) {
        SpringApplication.run(QualityApplication.class, args);
    }
}
```

This class provides the entry point for the executable JAR. The tests below **do not need to start the Spring context** because the business logic is plain Java; this helps keep unit tests fast.

### 5.2. Branched Java Logic to Measure Coverage

File `src/main/java/com/example/quality/DiscountCalculator.java`:

```java
package com.example.quality;

public final class DiscountCalculator {
    public int total(int price, boolean member) {
        if (price < 0) {
            throw new IllegalArgumentException("price must be >= 0");
        }
        return member ? price * 9 / 10 : price;
    }
}
```

- The `price < 0` branch checks invalid input.
- The `member` branch computes a 10% discount.
- The remaining branch keeps the full price.

The calculation uses `int` and **integer division**; the example is solely for testing/coverage and is **not** standard monetary arithmetic for financial systems. In production code, use `BigDecimal` or smallest currency units with explicit rounding rules.

### 5.3. JUnit Jupiter Test

File `src/test/java/com/example/quality/DiscountCalculatorTest.java`:

```java
package com.example.quality;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

import org.junit.jupiter.api.Test;

class DiscountCalculatorTest {
    private final DiscountCalculator calculator = new DiscountCalculator();

    @Test
    void memberGetsDiscount() {
        assertEquals(90, calculator.total(100, true));
    }

    @Test
    void nonMemberPaysFullPrice() {
        assertEquals(100, calculator.total(100, false));
    }

    @Test
    void negativePriceIsRejected() {
        assertThrows(IllegalArgumentException.class,
                () -> calculator.total(-1, true));
    }
}
```

Tests verify both pricing paths and the exception path; expected results are `90`, `100`, and `IllegalArgumentException`. This test file runs in a project with **JUnit Jupiter on the test classpath**; it will not compile with bare `javac` without JUnit dependencies. There is no fixed stdout for the tests: Maven/Gradle print reports per plugin, while assertions fail if actual values differ.

**Watch out for formatting:** the Java code above is readable, though not guaranteed to match *every space/newline* of the chosen Google Java Format version. Run `spotlessApply`/`spotless:apply` once locally before expecting `spotlessCheck`/`spotless:check` to PASS.

## 6. Maven: Adding Three Quality Gates to the `verify` Phase

### 6.1. Runnable Application POM

This `pom.xml` uses Spring Boot starter parent, Java 17, Spotless, PMD, and JaCoCo. Plugin versions below are **specific released versions for reproducibility**, not a requirement to always pick the newest release of every plugin. Verify JDK/Maven/plugin compatibility in your actual repository before upgrading.

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
             https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.5.16</version>
        <relativePath/>
    </parent>

    <groupId>com.example</groupId>
    <artifactId>quality-demo</artifactId>
    <version>0.1.0-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    </properties>

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>

    <build>
        <plugins>
            <!-- Spring Boot executable JAR -->
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>

            <!-- 1) Formatting: check (never rewrite files in CI) -->
            <plugin>
                <groupId>com.diffplug.spotless</groupId>
                <artifactId>spotless-maven-plugin</artifactId>
                <version>3.10.4</version>
                <configuration>
                    <java>
                        <googleJavaFormat>
                            <version>1.30.0</version>
                        </googleJavaFormat>
                    </java>
                </configuration>
                <executions>
                    <execution>
                        <id>check-formatting</id>
                        <phase>verify</phase>
                        <goals><goal>check</goal></goals>
                    </execution>
                </executions>
            </plugin>

            <!-- 2) Static analysis: PMD -->
            <plugin>
                <groupId>org.apache.maven.plugins</groupId>
                <artifactId>maven-pmd-plugin</artifactId>
                <version>3.28.0</version>
                <configuration>
                    <failOnViolation>true</failOnViolation>
                    <printFailingErrors>true</printFailingErrors>
                    <rulesets>
                        <ruleset>/category/java/errorprone.xml</ruleset>
                    </rulesets>
                </configuration>
                <executions>
                    <execution>
                        <id>check-static-analysis</id>
                        <phase>verify</phase>
                        <goals><goal>check</goal></goals>
                    </execution>
                </executions>
            </plugin>

            <!-- 3) Coverage: agent before tests, report + threshold -->
            <plugin>
                <groupId>org.jacoco</groupId>
                <artifactId>jacoco-maven-plugin</artifactId>
                <version>0.8.16</version>
                <executions>
                    <execution>
                        <id>attach-coverage-agent</id>
                        <goals><goal>prepare-agent</goal></goals>
                    </execution>
                    <execution>
                        <id>coverage-report</id>
                        <phase>verify</phase>
                        <goals><goal>report</goal></goals>
                    </execution>
                    <execution>
                        <id>coverage-threshold</id>
                        <phase>verify</phase>
                        <goals><goal>check</goal></goals>
                        <configuration>
                            <rules>
                                <rule>
                                    <element>BUNDLE</element>
                                    <limits>
                                        <limit>
                                            <counter>LINE</counter>
                                            <value>COVEREDRATIO</value>
                                            <minimum>0.50</minimum>
                                        </limit>
                                    </limits>
                                </rule>
                            </rules>
                        </configuration>
                    </execution>
                </executions>
            </plugin>
        </plugins>
    </build>
</project>
```

**QA points before applying:**

- `pom.xml` places **plugins in `<build><plugins>`** and declares `<executions>`, rather than putting them only in `<pluginManagement>`; `pluginManagement` *defines defaults* without activating goals.
- Spotless `check` is bound to `verify`. PMD `check` is also bound to `verify`; per Maven PMD docs, this goal triggers the `pmd` analysis before checking violations.
- JaCoCo `prepare-agent` uses its default pre-test phase so the agent participates during test execution. `report` and `check` run in `verify`; the rule checks **LINE/COVEREDRATIO** across the **BUNDLE**.
- The **0.50 = 50%** threshold is just a starting value for an example containing an untested Spring Boot bootstrap class. In real projects, choose a higher target aligned with baselines, justified exclusions, and module categorization; **never treat 50% as a universal quality standard**.
- Using `spring-boot-starter-parent` inherits suitable compiler/test defaults. When using a corporate parent instead, configure compiler, JUnit Surefire, and Spring Boot repackage explicitly.
- If customizing `maven-surefire-plugin`'s `argLine`, never accidentally overwrite the JaCoCo agent argument; use **late property evaluation** when combining JDWP, module flags, or custom JVM options.
- Plugins must be downloaded from repositories; builds can fail without internet, proxy/credentials, or compatible Maven/JDK versions. The source code in section 5 and this POM form a structurally valid project, yet still require the real environment's wrapper and JDK.

### 6.2. Maven Commands for Individual Checks

```bash
# Fix SOURCE formatting locally, then review Git diff
./mvnw spotless:apply

# Check for formatting violations only
./mvnw spotless:check

# Run static analysis check
./mvnw pmd:check

# Run full test/package/quality gates lifecycle
./mvnw clean verify
```

**Tip:** `./mvnw pmd:check` may require compiled/resolved project state; for clean-checkout diagnostics, run `./mvnw verify` across the full lifecycle. Never use `spotless:apply` in CI because it modifies working tree files without forcing developer review and commit.

### 6.3. Distinguishing Maven Outcomes

- **Unformatted source:** `spotless:check` fails at `verify`, logging the file and instructing you to run apply.
- **PMD finds a disallowed pattern:** `pmd:check` fails when violations exceed configuration. `maven-pmd-plugin` can write reports under `target/`; exact paths depend on plugin config.
- **Failing tests:** Maven normally stops at the `test` phase before entering `verify`. Thus a failing `verify` run does not guarantee later quality gates ran.
- **Coverage below 50%:** JaCoCo `check` fails in `verify` when execution data exists and rules evaluate. Default HTML reports from `report` normally live at `target/site/jacoco/index.html`; XML at `target/site/jacoco/jacoco.xml` when XML output is enabled.
- **Missing coverage data:** JaCoCo may log "Skipping JaCoCo execution due to missing execution data file"; **this does NOT automatically count as 0% and fail the threshold**. For a trustworthy gate, CI must actually run tests, collect execution data, and verify outputs are present.
- **Running `mvn package` instead of `mvn verify`:** does not run goals bound to `verify`. CI must invoke **verify**.

## 7. Gradle: Wiring Spotless, PMD, and JaCoCo into `check`

### 7.1. A Runnable Groovy DSL `build.gradle`

Assume a Spring Boot Gradle project generated by Spring Initializr with `settings.gradle` and a Gradle Wrapper. Minimal `settings.gradle`:

```groovy
rootProject.name = 'quality-demo'
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.5.16'
    id 'io.spring.dependency-management' version '1.1.7'

    // Formatting
    id 'com.diffplug.spotless' version '8.11.0'

    // Static analysis and coverage are Gradle core plugins
    id 'pmd'
    id 'jacoco'
}

group = 'com.example'
version = '0.1.0-SNAPSHOT'

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

repositories {
    mavenCentral()
}

dependencies {
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'org.junit.platform:junit-platform-launcher'
}

tasks.named('test') {
    useJUnitPlatform()
}

// 1) Consistent Java formatting across main and test sources
spotless {
    java {
        googleJavaFormat('1.30.0')
    }
}

// 2) PMD: sample Java ruleset, fail on violations
pmd {
    toolVersion = '7.16.0'
    ruleSets = ['category/java/errorprone.xml']
    ignoreFailures = false
    consoleOutput = true
}

// 3) JaCoCo collects coverage when tests run
jacoco {
    toolVersion = '0.8.16'
}

tasks.named('jacocoTestReport') {
    dependsOn tasks.named('test')
    reports {
        xml.required = true
        html.required = true
    }
}

tasks.named('jacocoTestCoverageVerification') {
    // Wire dependencies so report and tests run before threshold check.
    dependsOn tasks.named('jacocoTestReport')
    violationRules {
        rule {
            element = 'BUNDLE'
            limit {
                counter = 'LINE'
                value = 'COVEREDRATIO'
                minimum = 0.50
            }
        }
    }
}

tasks.named('check') {
    // PMD plugin wires pmdMain/pmdTest into check automatically.
    // Wire Spotless and coverage explicitly for easy auditing.
    dependsOn tasks.named('spotlessCheck'),
              tasks.named('jacocoTestCoverageVerification')
}
```

**Read the task wiring carefully:**

1. `id 'java'` creates `test`, `check`, and the `src/main/java`/`src/test/java` conventions.
2. The Spring Boot plugin assists with packaging the application and does not replace static analysis or coverage gates.
3. `id 'com.diffplug.spotless'` provides `spotlessCheck` and `spotlessApply`. In many versions Spotless wires itself into `check`; explicit `dependsOn` above makes the project requirement obvious.
4. `id 'pmd'` provides `pmdMain`/`pmdTest` and wires them into `check`; you do not need to invoke PMD manually when running `check`.
5. `id 'jacoco'` instruments the Java `Test` task and supplies reporting/verification tasks.
6. `jacocoTestReport.dependsOn test` ensures tests run before generating the report. `jacocoTestCoverageVerification.dependsOn jacocoTestReport` ensures reports and data exist before enforcing thresholds.
7. `check.dependsOn spotlessCheck, jacocoTestCoverageVerification` is an **intentional mandatory step** in the example. Merely adding `jacoco { ... }` does not tell `check` to enforce percentages.
8. `ignoreFailures = false` for PMD sets the policy to fail on violations; flipping it to `true` still generates reports while allowing `check` to pass despite PMD violations.
9. `toolVersion` specifies the PMD/JaCoCo engine version, independent of the Gradle plugin/Wrapper version. Choose engine versions compatible with your JDK and build tool.

The plugin/engine versions above are examples **requiring a compatible wrapper and JVM**; especially when upgrading Spotless/Gradle/Boot in an existing codebase, verify compatibility and test `./gradlew help` first. For projects using Gradle Kotlin DSL, **syntax differs**—do not paste Groovy code directly into `build.gradle.kts`.

### 7.2. Gradle Commands for Practice

```bash
# Apply formatting locally, then review git diff
./gradlew spotlessApply

# Check formatting without modifying sources
./gradlew spotlessCheck

# Run static analysis standalone
./gradlew pmdMain pmdTest

# Run unit tests and generate coverage report
./gradlew test jacocoTestReport

# Check coverage threshold only (dependsOn report/test configured)
./gradlew jacocoTestCoverageVerification

# Run all quality gates
./gradlew clean check

# Compile/package + all checks in the Java lifecycle
./gradlew build
```

`./gradlew clean check` clears outputs under `build/` first. You do not need `clean` on every local iteration: use `./gradlew check` to leverage incremental compilation and up-to-date checks, then run `clean` when clearing stale outputs.

### 7.3. Gradle Kotlin DSL: Key Syntax Equivalents

If the project uses `build.gradle.kts`, equivalent `plugins` block:

```kotlin
plugins {
    java
    id("org.springframework.boot") version "3.5.16"
    id("io.spring.dependency-management") version "1.1.7"
    id("com.diffplug.spotless") version "8.11.0"
    pmd
    jacoco
}
```

And the main quality gate settings (added to a `build.gradle.kts` that already declares `repositories`, `dependencies`, and the Java toolchain):

```kotlin
spotless {
    java {
        googleJavaFormat("1.30.0")
    }
}

pmd {
    toolVersion = "7.16.0"
    ruleSets = listOf("category/java/errorprone.xml")
    isIgnoreFailures = false
}

jacoco {
    toolVersion = "0.8.16"
}

tasks.test {
    useJUnitPlatform()
}

tasks.jacocoTestReport {
    dependsOn(tasks.test)
    reports {
        xml.required.set(true)
        html.required.set(true)
    }
}

tasks.jacocoTestCoverageVerification {
    dependsOn(tasks.jacocoTestReport)
    violationRules {
        rule {
            element = "BUNDLE"
            limit {
                counter = "LINE"
                value = "COVEREDRATIO"
                minimum = "0.50".toBigDecimal()
            }
        }
    }
}

tasks.check {
    dependsOn("spotlessCheck", "jacocoTestCoverageVerification")
}
```

The Kotlin DSL snippets illustrate **syntax differences** only; for a complete build, combine them with `group`, `version`, `java.toolchain`, repositories, and dependencies like the Groovy example. Never mix both DSL languages in a single project.

## 8. Configuring Rules and Thresholds: Do Not Just Install Plugins

### 8.1. Formatting Rules

Formatters should be **version-locked** and run with identical rules across IDE, CLI, and CI. If your team adopts Google Java Format, verify both the plugin version and the declared Google Java Format version. When upgrading formatter versions, many files may change; make a dedicated formatting commit so logic diffs are not obscured.

- `check`: detects formatting violations only, failing the build as configured.
- `apply`: modifies files on disk; run locally, review `git diff`, and commit.
- Never turn CI into a bot that silently reformats code and marks the build successful; otherwise Git history diverges from verified sources.

### 8.2. How PMD, Checkstyle, and SpotBugs Differ

**PMD** analyzes source code against rule sets; it catches potential logic bugs, maintainability issues, and poor coding practices. The `java/errorprone` category is only a starting point; specific rules vary by PMD version. Effective static analysis selects rules fitting your Java release and team architecture, avoiding enabling hundreds of noisy rules that flood developers with false positives.

**Checkstyle** excels at enforcing Java style, imports, naming, and method size rules. It does not replace PMD's semantic checks. You can use Checkstyle **instead of or alongside** PMD when strict style rules are required.

**SpotBugs** analyzes compiled bytecode to find post-compile bug patterns (such as API misuse or nullness bugs); it operates differently from PMD. You can add it to advanced builds while verifying plugin versions, task/goal bindings, and severity policies.

**Example replacing PMD with Checkstyle in Gradle:**

```groovy
plugins {
    id 'java'
    id 'checkstyle'
}

checkstyle {
    toolVersion = '10.23.0'
    configFile = file('config/checkstyle/checkstyle.xml')
    ignoreFailures = false
}
```

This is a **replacement snippet, not an entire build**. You must supply a valid `config/checkstyle/checkstyle.xml`; if missing, the plugin fails due to missing config rather than code violations. The Gradle Java + Checkstyle plugins automatically wire `checkstyleMain`/`checkstyleTest` into `check`.

Minimal valid Checkstyle configuration example (file `config/checkstyle/checkstyle.xml`):

```xml
<?xml version="1.0"?>
<!DOCTYPE module PUBLIC
    "-//Checkstyle//DTD Checkstyle Configuration 1.3//EN"
    "https://checkstyle.org/dtds/configuration_1_3.dtd">
<module name="Checker">
    <property name="charset" value="UTF-8"/>
    <module name="TreeWalker">
        <module name="AvoidStarImport"/>
    </module>
</module>
```

This example checks only wildcard imports (not a full corporate rule set), illustrating the configuration mechanism. When running PMD and Spotless together, avoid overlapping rules with conflicting standards.

**Maven Checkstyle** offers `checkstyle:check` to fail on violations; `checkstyle:checkstyle` primarily generates Maven site reports and should not be mistaken for a quality gate. An alternate bound configuration looks like:

```xml
<!-- Snippet inside <build><plugins> of pom.xml, replacing/supplementing PMD per policy -->
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-checkstyle-plugin</artifactId>
    <version>3.6.0</version>
    <configuration>
        <configLocation>config/checkstyle/checkstyle.xml</configLocation>
        <failOnViolation>true</failOnViolation>
    </configuration>
    <executions>
        <execution>
            <phase>verify</phase>
            <goals><goal>check</goal></goals>
        </execution>
    </executions>
</plugin>
```

When using Checkstyle/PMD in multi-module builds, decide how config/rulesets are shared from parent/root so modules reference stable rule files. A module with no Java sources may need to skip the relevant task; never disable the entire quality gate just to work around a minor exception.

### 8.3. How Should Coverage Ratios Be Interpreted?

JaCoCo provides several **counters** and **values**. Common counters:

| Counter | Interpretation |
|---|---|
| `INSTRUCTION` | Bytecode instructions executed |
| `LINE` | Whether lines containing bytecode executed |
| `BRANCH` | Control-flow branches such as `if`/`switch` conditions (not equal to test case count) |
| `METHOD` | Methods invoked |
| `CLASS` | Classes with executed code |

Values like `COVEREDRATIO`, `MISSEDRATIO`, `COVEREDCOUNT`, and `MISSEDCOUNT` have distinct semantics. For example:

\`LINE COVEREDRATIO = 0.80\` means **80%** line coverage as JaCoCo counts bytecode-bearing lines within the rule scope. It does not mean 80% of business flows were thoroughly verified. A test that merely executes code without meaningful assertions still raises coverage without guaranteeing quality.

Thresholds are **policy**, not an automatic property of measurement. For example, `minimum = 0.50` must be chosen intentionally per module type; you can ratchet up 60% → 75% → 85% as test suites mature, while avoiding arbitrary targets that push teams to write meaningless tests just to hit a number.

**Arithmetic example:** if JaCoCo counts 80 bytecode-bearing lines and tests execute 64 lines, the ratio is `64 / 80 = 0.80`. If the gate requires `0.85`, the build fails; if the gate is `0.75`, the build passes. This is an arithmetic illustration, not measured output from the `DiscountCalculator` files above.

### 8.4. Responsible Exclusions

Sometimes generated classes, DTOs, bootstrap classes, or framework-generated code should be excluded from coverage. Never exclude classes just to "boost scores." Every exclusion should be documented, reviewed, and kept consistent between reporting and threshold verification.

**Warning:** configuring exclusions for **reporting** without matching exclusions in **verification** (or vice versa) causes displayed percentages and enforced percentages to disagree. In multi-module projects, JaCoCo defaults to per-module/source-set metrics; if you want a repository-wide threshold, aggregate execution data and define aggregation explicitly.

## 9. Experiment: Proving All Three Gates Actually Block the Build

After creating the Java/test files and selecting one build tool:

### 9.1. Formatting Normalization Step

Maven:

```bash
./mvnw spotless:apply
./mvnw clean verify
```

Gradle:

```bash
./gradlew spotlessApply
./gradlew clean check
```

**Expected:** once code is formatted, static analysis rules pass, and coverage meets the threshold, `verify`/`check` completes successfully. Exact stdout is not fixed because Maven/Gradle/plugin versions produce varying logs.

### 9.2. Triggering a Safe Formatting Error

Alter indentation/spacing in `DiscountCalculator.java` so the formatter would modify it while keeping it valid Java source. Then **do not** run apply; invoke `./mvnw verify` or `./gradlew check`. With format checking properly wired, the build must fail. Afterward, run apply and inspect the diff.

If you break Java syntax so the parser fails, compiler tasks fail before formatting checks run; to test **only the formatting gate**, run `spotless:check` or `spotlessCheck`.

### 9.3. Triggering a Static Analysis Error

Introduce a violation of an enabled rule (such as a wildcard import when using the Checkstyle `AvoidStarImport` rule above) and run the static analysis goal/task directly. Confirm the report pinpoints file, line, and rule. Then fix the code and re-run.

**Do not assume** PMD catches every "bad" code pattern: only enabled rules in the active version determine violations. To test PMD reliably, pick a specific rule in `category/java/errorprone.xml` and craft an input violating that exact rule.

### 9.4. Proving the Coverage Threshold

Temporarily raise `minimum` above measured coverage (e.g., from 0.50 to 0.99 for a build with an untested bootstrap class) and run `verify`/`check`.

- Maven: JaCoCo `check` fails for missing the threshold.
- Gradle: `jacocoTestCoverageVerification` fails, failing `check` due to `dependsOn`.

This is an **intentional experiment**; afterward restore your policy threshold rather than committing `0.99` just to prove the gate. If no error appears, inspect execution data files, rule scope, skip flags, and whether the task actually executed.

## 10. Reports, Exit Codes, and CI Integration

### 10.1. Where Are Reports Generated?

| Tool | Common locations | Contents |
|---|---|---|
| Maven Surefire | `target/surefire-reports/` | Unit test XML/text reports |
| Gradle Test | `build/test-results/test/`, `build/reports/tests/test/` | Test result XML/HTML |
| Maven JaCoCo | `target/site/jacoco/index.html`, `jacoco.xml` | Coverage HTML/XML |
| Gradle JaCoCo | `build/reports/jacoco/test/html/index.html`, `build/reports/jacoco/test/jacocoTestReport.xml` | Coverage HTML/XML |
| Maven PMD | `target/pmd.xml` / reports in `target/site/` (varies by goal/config) | PMD violations |
| Gradle PMD | `build/reports/pmd/` | Reports per source set |
| Gradle Checkstyle | `build/reports/checkstyle/` | Checkstyle reports |
| Spotless | Plugin-provided logs/diffs | Files violating formatter rules |

Paths may differ when plugins or multi-module layouts customize output directories. Coverage XML feeds CI/aggregators; HTML helps developers inspect which lines tests exercised. **XML reports do not replace build-failing rules.**

### 10.2. What Must a CI Job Do?

A sound pipeline should:

1. Check out the exact source commit.
2. Provision the appropriate JDK and Maven/Gradle Wrapper.
3. Use controlled dependency caching to speed up builds without replacing test/quality gates.
4. Run **`./mvnw -B verify`** or **`./gradlew --no-daemon check`** (plus build/package if the pipeline needs artifacts).
5. Respect the command **exit code**. If non-zero, fail the job and block the PR via branch protection.
6. Archive test/PMD/Checkstyle/JaCoCo reports as artifacts—even on job failure if supported by your CI platform.
7. Never auto-apply formatting in CI and pass; formatting fixes must be committed and reviewed.

Maven shell example:

```bash
./mvnw -B clean verify
```

Gradle shell example:

```bash
./gradlew --no-daemon clean check
```

`--no-daemon` suits ephemeral CI runners, though it is not a strict technical requirement for every Gradle runner. For Spring Boot packaging in Gradle CI, `./gradlew build` normally includes `check` via the Java lifecycle; still verify your project's actual task graph and branch protection checks.

**Important note about reports on failure:** If the formatting check fails before tests run, JaCoCo cannot produce a new report. If tests fail, coverage data/reports may exist while the lifecycle stops before JaCoCo `check`. To collect every diagnostic in a single pass, teams can run independent checks in separate CI jobs or use Gradle finalizers where appropriate rather than assuming one command emits all reports regardless of early failure.

## 11. Multi-Module Builds: Where Do Gates Live and How Is Coverage Computed?

### 11.1. Maven Reactor

In multi-module Maven:

- A parent POM can centralize plugin versions/configs inside `<pluginManagement>` for consistency across modules.
- However, `pluginManagement` **does not automatically run goals in every module**; plugins must be applied in `<build><plugins>` on the appropriate parent/modules, paying attention to `<inherited>` and packaging.
- `pom`-packaged modules without Java code may need to skip lint/coverage or run only relevant gates.
- Single-module JaCoCo `report` does not automatically enforce **a single reactor-wide threshold**. Consolidated reporting requires `report-aggregate` and dedicated dependency/aggregation setup.

When running `./mvnw -pl :orders-api verify`, upstream modules may need `-am` and compatible reactor setup:

```bash
./mvnw -pl :orders-api -am verify
```

Do not apply identical thresholds to application modules, generated-code modules, and test fixture modules without considering each module's purpose. Define minimum gates and justified module exceptions explicitly.

### 11.2. Gradle Multi-Project

In Gradle, `check` is a **per-project** task:

```bash
./gradlew :orders-api:check
./gradlew :shared-domain:check
```

In a multi-project build, calling `./gradlew check` invokes tasks named `check` across the structure, though you should not assume every custom verification task in every module is wired in. Use `./gradlew tasks --all` and `./gradlew :module:check --dry-run` to inspect which tasks actually execute.

- Apply `pmd`, `jacoco`, and `spotless` to the right modules/source sets.
- Package shared conventions in **convention plugins** so no module forgets `dependsOn`.
- Each module normally produces its own JaCoCo report. To measure aggregate application coverage across cross-module tests, configure JaCoCo report aggregation with appropriate execution data setup; simply averaging module percentages is mathematically wrong when line counts differ.
- Do not enable the Spring Boot executable plugin on library modules solely to attach quality gates. Quality plugins pair cleanly with `java-library` on non-Boot modules.

## 12. Common Pitfalls and Diagnostic Steps

| Symptom | Common cause | Resolution |
|---|---|---|
| `./mvnw verify` passes despite unformatted files | Spotless declared without binding `check`, or skip flag active | Check `<executions>`, `<phase>verify</phase>`, and goal logs |
| `./gradlew check` passes despite 0% coverage | `jacocoTestCoverageVerification` not wired as a `check` dependency | Add `check.dependsOn` verification and inspect `--dry-run` |
| HTML coverage exists, yet gate does not fail | Only `report` ran without configuring `check`/`violationRules` | Add rules and wire into `verify`/`check` |
| JaCoCo reports missing execution data | Agent not attached to test JVM, tests skipped, test task skipped, or custom output path | Check `prepare-agent`/`Test` instrumentation, report paths, and skip flags |
| Wrong JaCoCo coverage across multiple modules/test suites | Measuring only `test` in a single module instead of all suites | Configure report aggregation and proper rule scope |
| PMD/Checkstyle only emits warnings | `ignoreFailures`/`failOnViolation`/policy allows errors | Set strict failure policy and test with a sample violation |
| CI auto-fixes formatting and passes | Using `spotlessApply`/`spotless:apply` instead of check | CI runs check only; developers run apply + review locally |
| Maven JaCoCo agent disappears after adding VM options | Surefire `argLine` overwritten | Combine agent property with custom VM options per plugin docs |
| Build fails due to missing Checkstyle config | `checkstyle.xml` not committed or wrong path | Commit rule file and reference the right path |
| Spotless formatting differs between IDE and CI | Unpinned formatter/plugin version or line endings | Pin versions, configure Git attributes, and align IDE |
| `./gradlew bootJar` succeeds without running static checks | `bootJar` does not depend on `check` | Invoke `check`/`build` in CI |
| PMD false positives on generated code | Ruleset scans generated sources or excludes are misconfigured | Scope inputs properly and review exclusions |
| Tests pass, yet logic quality remains weak | Coverage measures execution only, not assertion strength | Review test cases, add branch/behavior tests, consider mutation testing |

Run diagnostic commands **only for the build tool your project uses**:

```bash
# Maven: inspect effective configuration and executed goals
./mvnw help:effective-pom
./mvnw -X verify

# Gradle: inspect task graph and task execution/skip reasons
./gradlew check --dry-run
./gradlew check --info
```

Debug logs may expose environment variables or system details; share them only after scrubbing sensitive data.

## 13. Practical Quality Gate Policy Suggestions

**Formatting** should be binary: either formatted properly or not. Provide an obvious apply command so developers can fix violations in seconds. If your team chooses Spotless, standardize the formatter/version and never mix competing Java formatters on the same files.

**Static analysis** should prioritize error severity, use a reviewed ruleset, and provide a reasoned suppression mechanism instead of enabling `ignoreFailures` wholesale. Fast rules can block PRs while heavier bytecode checks run on schedules—just document mandatory merge requirements clearly.

**Coverage** needs at least one realistic threshold and archived reports. Start from your existing baseline, ratchet targets gradually, and emphasize high-risk code, branch coverage, and behavioral tests. Bootstrap classes, DTOs, and generated code should only be excluded under an explicit policy; never equate "90% coverage" with "zero bugs."

**Performance:** leverage Gradle incremental/up-to-date checks, Maven plugin caching, and per-module/CI job splitting. Never sacrifice gate accuracy to save a few seconds; build caches may reuse valid results, never cause checks to be bypassed unconditionally.

**Maintenance:** update plugins/JDK/rulesets periodically in a controlled way, audit reported false positives, verify CI branch protection, and periodically run fault-injection tests to confirm gates still block violations.

## 14. Pre-CI Deployment Checklist

1. **Formatting**: `spotlessCheck` or `spotless:check` runs automatically in `check`/`verify`; `apply` runs manually only.
2. **Static analysis**: selected PMD/Checkstyle/SpotBugs tools have pinned versions, rulesets, source scopes, and fail modes.
3. **Coverage agent**: tests are instrumented properly; execution data is generated during the CI build.
4. **Coverage reports**: HTML/XML are generated and archived when data exists; report paths match module layout.
5. **Coverage gate**: JaCoCo `check`/`jacocoTestCoverageVerification` enforces real thresholds rather than just generating reports.
6. **Lifecycle/task graph**: Maven goals bind to `verify`; Gradle `check` depends on the required tasks; verified via logs or dry-run.
7. **JUnit**: Maven Surefire/Gradle `test` discovers and runs the right test framework; no skip flags enabled in mandatory jobs.
8. **Packaging**: if releasing a JAR, run `package`/`build` appropriately **after or alongside** gates; do not mistake `bootJar` for full verification.
9. **Multi-module**: each module enforces gates suited to its role; coverage aggregation is configured explicitly if needed.
10. **CI security**: tokens and repository credentials live in secrets, never committed to build files or printed to logs.
11. **Failure testing**: deliberately introduce one format violation, one static analysis violation, and one failing coverage threshold, confirming the main command exits non-zero.
12. **Reporting**: CI archives reports so developers can locate file/line/rule; restore thresholds and sources after experiments.

### Official Documentation

- [Maven — Introduction to the Build Lifecycle](https://maven.apache.org/guides/introduction/introduction-to-the-lifecycle.html)
- [Spotless Maven Plugin — check and lifecycle binding](https://github.com/diffplug/spotless/blob/main/plugin-maven/README.md)
- [Spotless Gradle Plugin — spotlessCheck/spotlessApply tasks](https://github.com/diffplug/spotless/blob/main/plugin-gradle/README.md)
- [Maven PMD Plugin — verifying in verify](https://pmd.github.io/pmd/pmd_userdocs_tools_maven.html)
- [Gradle PMD Plugin](https://docs.gradle.org/current/userguide/pmd_plugin.html)
- [Gradle Checkstyle Plugin](https://docs.gradle.org/current/userguide/checkstyle_plugin.html)
- [Gradle JaCoCo Plugin — verification does not depend on check automatically](https://docs.gradle.org/current/userguide/jacoco_plugin.html)
- [JaCoCo Maven — check goal](https://www.jacoco.org/jacoco/trunk/doc/check-mojo.html)
- [JaCoCo Maven — report goal](https://www.jacoco.org/jacoco/trunk/doc/report-mojo.html)

**Remember:** Quality becomes a true **quality gate** only when formatting checks, static analysis, and coverage verification are wired into **`mvn verify` or `gradle check`**, backed by clear rules, and actually fail the build on violations. Pretty reports that never break the build are **not** a quality gate.
