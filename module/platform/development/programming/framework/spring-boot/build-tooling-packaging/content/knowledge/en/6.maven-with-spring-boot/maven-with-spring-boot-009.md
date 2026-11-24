# Using Maven Profiles for Spring Boot Build Variants

## 1. Goal and Context

The same Spring Boot project sometimes needs multiple **build variants**: running quickly on a developer machine, running extra integration tests in CI, or tagging metadata when producing release artifacts. Apache Maven supports **build profiles** to alter part of the build configuration contextually while keeping a single `pom.xml`.

After this lesson, you will be able to:

1. Explain what a Maven profile is, which parts of a build can vary, and which parts should stay stable.
2. Define profiles in `pom.xml`, activate them explicitly via `-P`, and understand activation by property, JDK, OS, environment, or file.
3. Design `local`, `ci`, and `release` examples with observable results; enable integration tests in one variant.
4. Verify that a **profile is truly active** using the Maven Help Plugin, effective POM, and build outputs rather than trusting profile names alone.
5. Distinguish **Maven build profiles** from **Spring runtime profiles** (`spring.profiles.active`) and avoid baking runtime secrets or environment configs into artifacts.
6. Troubleshoot common issues where the same build command behaves differently between a local laptop and CI.

**Context:** Examples assume you already have a Maven-based Spring Boot project with `pom.xml`, Maven Wrapper (`mvnw`, `mvnw.cmd`), and a Java version compatible with Spring Boot. XML snippets will be explicitly labeled as *snippets to merge into an existing POM* or *standalone files*. You do not need to switch to Gradle or create a new project to learn how profiles work.

## 2. What Is a Maven Profile Really?

A **Maven profile** is a conditional set of Maven configuration. When active, Maven merges its effects into the build model to adjust properties, dependencies, plugins, resources, repositories, or other supported settings. A profile **is not an independent Maven lifecycle**: `package`, `verify`, and `install` remain the exact same phases as before.

Examples:

- `local`: uses base build configuration by default, running only tests normally bound to the lifecycle.
- `ci`: when selected, enables Failsafe to run extra integration tests in `integration-test` and evaluate results in `verify`.
- `release`: tags build metadata, or configures release-gate steps if project workflow requires them. **Merely naming a profile `release` does not deploy an application or sign artifacts.**

A Maven profile can define `<properties>`, `<dependencies>`, `<dependencyManagement>`, `<build>` (with plugins/resources), and other supported Maven elements. Not every POM element is valid inside `<profile>`, so follow the POM schema instead of moving the entire project into a profile.

### Maven Profile vs. Spring Profile: Same Word "Profile", Different Responsibilities

| Criterion | Maven Build Profile | Spring Boot Runtime Profile |
| --- | --- | --- |
| Selected via | `-Pci`, `-Prelease`, `<activation>`, `settings.xml` | `spring.profiles.active`, `SPRING_PROFILES_ACTIVE` env var, `@ActiveProfiles` in tests |
| Timing | When Maven computes the build model and runs plugins/lifecycle | When the Spring `ApplicationContext` initializes |
| Scope of effect | Plugins, dependencies, resources, properties, artifacts, and build steps | Beans, `application-{profile}.yml`, configuration, runtime conditions |
| Example command | `./mvnw -Pci clean verify` | `java -jar target/app.jar --spring.profiles.active=dev` (use actual JAR name) |
| Linked automatically? | **No** | **No** |

`-Pprod` **does not automatically** make Spring Boot load `application-prod.yml`. Conversely, setting `SPRING_PROFILES_ACTIVE=prod` for the application JVM does not activate a Maven profile named `prod`. You can wire an intentional bridge, but handle it carefully because build time and runtime are two distinct lifecycles.

For applications deployed to multiple environments, a solid practice is **building one identical artifact** and supplying runtime differences via environment variables, a secret manager, or deployment config. Only produce different artifacts via Maven profiles when there is a genuine packaging requirement.

## 3. Where Can Maven Profiles Be Declared?

| Location | Used For | Characteristics |
| --- | --- | --- |
| Project's `pom.xml` | Build variants the whole team and CI need to know | Version-controlled with code; can adjust dependencies, plugins, and resource processing |
| User's `~/.m2/settings.xml` | Machine- or organization-specific mirrors/repositories/properties | Settings profiles have narrower configuration scope; cannot define `<build><plugins>` like POM profiles |
| Maven global settings | Maven configuration at the installation level | Environment-dependent, harder to port to CI; use thoughtfully |
| Parent POM / module POMs | Shared policies or module-specific overrides | Profile definitions in a POM are not "inherited verbatim"; **effects of an active profile in the parent** can be inherited |

**Recommendation:** put shared build variants in `pom.xml`; keep local machine details, proxies, internal repositories, and credentials in settings or proper secret management. Never commit passwords, tokens, private keys, or absolute JDK paths into project profiles.

### Maven Wrapper

Run builds with the Wrapper committed to the repository to keep Maven versions uniform:

~~~bash
# Linux/macOS, in the directory containing pom.xml and mvnw
./mvnw --version
./mvnw clean verify
~~~

~~~powershell
# Windows PowerShell
.\mvnw.cmd --version
.\mvnw.cmd clean verify
~~~

If the Wrapper is missing, use a Maven version approved by the project. Running from the wrong directory can cause Maven to complain about a missing `pom.xml`; all examples below run from the **root directory of the chosen module/project containing the POM**.

## 4. Activating Profiles with `-P` and Inspecting Actual State

Maven lets you select profiles by ID, keeping profile IDs distinct from Maven phases/goals:

~~~bash
# Neither "ci" nor "release" profile enabled via CLI
./mvnw clean verify

# Activate one profile defined in the POM
./mvnw -Pci clean verify

# Activate release profile and build only up to package
./mvnw -Prelease clean package

# Intentionally activate multiple profiles
./mvnw -Pci,release clean verify
~~~

On Windows PowerShell, replace `./mvnw` with `.\mvnw.cmd`. `-Pci` can also appear after the goal, though keeping a consistent position in scripts improves readability.

**Note:** `-Pci,release` does not necessarily mean "CI first, then release" according to CLI argument order. When multiple profiles modify the same property, Maven merges the model using precedence rules, including definition order inside the POM. Best practice is avoiding activating two **conflicting** profiles together. In Maven 4, specifying a nonexistent profile ID can fail the build; never treat missing-profile warnings as harmless.

To see which profiles are actually active:

~~~bash
./mvnw help:active-profiles
./mvnw help:all-profiles
./mvnw -Pci help:active-profiles
~~~

`help:active-profiles` lists profiles active in the current project context; `help:all-profiles` shows available profiles. In multi-module projects, output may be reported per module. **An existing ID does not mean it is active.**

To view the final configuration after merging parent, profiles, and plugins:

~~~bash
./mvnw -Pci help:effective-pom -Doutput=target/effective-ci.xml
./mvnw -Prelease help:effective-pom -Doutput=target/effective-release.xml
~~~

You can open those effective POM files to compare plugins, properties, and resources. They are **generated inspection files**, not configuration sources to edit manually. If Maven fails creating the file because the output folder does not exist yet in your setup, pick a valid writable path and create the folder beforehand.

## 5. End-to-End Example: Three Build Variants with Verifiable Outputs

In an existing Spring Boot Maven project with `pom.xml` and the `spring-boot-starter-test` dependency, we design:

| Variant | How to Select | Intended Effect | Command to Use |
| --- | --- | --- | --- |
| Default (`local`) | No `-P` needed | Resource metadata records `local`; regular unit tests still run | `./mvnw clean verify` |
| `ci` | `-Pci` | Metadata records `ci`, binds Failsafe `integration-test` and `verify` goals | `./mvnw -Pci clean verify` |
| `release` | `-Prelease` | Metadata records `release` so the artifact variant can be identified | `./mvnw -Prelease clean package` |

**Default `local` is a property in the base POM**, avoiding an `activeByDefault` `local` profile. This provides a clear fallback even when another profile is enabled.

### 5.1. Configuration to Merge into Existing `pom.xml`

In your Spring Boot Maven project POM, keep the existing `parent`/BOM, dependencies, and plugins intact. **Merge** the following into `<project>`: if the POM already has `<properties>`, `<build>`, or `<profiles>`, place the contents inside the matching sections without creating duplicate sibling tags.

~~~xml
<!-- Snippet inside <project> of an existing pom.xml -->
<properties>
    <build.flavor>local</build.flavor>
</properties>

<build>
    <resources>
        <!-- Keep application config, YAML, and regular resources untouched. -->
        <resource>
            <directory>src/main/resources</directory>
            <filtering>false</filtering>
        </resource>

        <!-- Filter only metadata files specifically meant for filtering. -->
        <resource>
            <directory>src/main/build-resources</directory>
            <filtering>true</filtering>
            <includes>
                <include>build-variant.properties</include>
            </includes>
        </resource>
    </resources>
</build>

<profiles>
    <profile>
        <id>ci</id>
        <properties>
            <build.flavor>ci</build.flavor>
        </properties>
        <build>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-failsafe-plugin</artifactId>
                    <version>3.3.1</version>
                    <executions>
                        <execution>
                            <goals>
                                <goal>integration-test</goal>
                                <goal>verify</goal>
                            </goals>
                        </execution>
                    </executions>
                </plugin>
            </plugins>
        </build>
    </profile>

    <profile>
        <id>release</id>
        <properties>
            <build.flavor>release</build.flavor>
        </properties>
    </profile>
</profiles>
~~~

**This is a configuration snippet, not a standalone POM.** Failsafe plugin `3.3.1` is an illustrative version; projects should use the version supported by their parent/`pluginManagement` and approved by the team. If `pom.xml` already configures `maven-failsafe-plugin`, merge the logic instead of defining two conflicting executions. If the project lacks JUnit/test dependencies, add an appropriate test suite before running tests.

How it works:

1. `build.flavor` evaluates to `local` when building with no profile.
2. `-Pci` changes the property to `ci` and adds Failsafe to the build; `-Prelease` sets it to `release`.
3. Resource filtering replaces the `@build.flavor@` placeholder with the build property value in the output file. That data is **packaged into the JAR** when a packaging step runs.
4. With `ci`, Maven Failsafe runs integration tests matching the class naming convention during `integration-test` and `verify`, provided matching tests exist.

### 5.2. Creating the Metadata File for Observable Output

Create the standalone text file `src/main/build-resources/build-variant.properties` with this exact content:

~~~properties
build.variant=@build.flavor@
~~~

Do not put this file inside `src/main/resources` if you kept `filtering=false` there, because Maven will copy the placeholder untouched. When Maven runs `process-resources`, it reads the property from the build model and writes `target/classes/build-variant.properties`.

**Safety note:** filter only text files you explicitly select. Never enable filtering broadly across all of `src/main/resources`, especially `application.yml` files with Spring placeholders, certificates, images, binaries, or content that must remain verbatim. Maven resource filtering can alter data or corrupt binary files if misconfigured.

### 5.3. Build and Inspect Results on Linux/macOS

~~~bash
./mvnw clean package
cat target/classes/build-variant.properties

./mvnw -Pci clean verify
cat target/classes/build-variant.properties

./mvnw -Prelease clean package
cat target/classes/build-variant.properties
~~~

Expected output of `cat`, **after each successive successful build**, is:

~~~text
build.variant=local
build.variant=ci
build.variant=release
~~~

These three lines represent **three separate file reads**, not three lines inside one file. `BUILD SUCCESS` and Maven plugin logs appear separately and vary across projects.

### 5.4. Build and Inspect Results on Windows PowerShell

~~~powershell
.\mvnw.cmd clean package
Get-Content .\target\classes\build-variant.properties

.\mvnw.cmd -Pci clean verify
Get-Content .\target\classes\build-variant.properties

.\mvnw.cmd -Prelease clean package
Get-Content .\target\classes\build-variant.properties
~~~

If the file does not exist, check the POM location, resource folder, and `maven-resources-plugin` logs; **do not assume the JAR build failed just because you are in the wrong module directory**. In multi-module projects, each packaged module has its own `target`.

## 6. Verifying That Integration Tests Actually Run Under `ci`

The Maven Surefire Plugin normally runs unit tests in the `test` phase; **Failsafe** runs integration tests in `integration-test` and `verify`. By standard naming conventions, `*IT.java` tests are discovered by Failsafe, whereas Surefire defaults skip them.

If the project already has `spring-boot-starter-test` or JUnit Jupiter configured, create this illustrative Java 17+ file:

**File:** `src/test/java/com/example/demo/BuildVariantIT.java`

~~~java
package com.example.demo;

import java.io.InputStream;
import java.util.Properties;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;

class BuildVariantIT {

    @Test
    void ciProfileFiltersBuildMetadata() throws Exception {
        InputStream stream = getClass().getClassLoader()
                .getResourceAsStream("build-variant.properties");
        assertNotNull(stream, "Filtered resource must exist");

        try (stream) {
            Properties values = new Properties();
            values.load(stream);
            assertEquals("ci", values.getProperty("build.variant"));
        }
    }
}
~~~

**This is a project test class with no `main` method;** run it through Maven/JUnit rather than `java BuildVariantIT`. If your project uses a different base package, adjust the path and package accordingly. The `*IT` suffix is one of Failsafe's standard default discovery patterns.

Run:

~~~bash
./mvnw -Pci clean verify
~~~

Expected verification outcome: Failsafe discovers `BuildVariantIT`; the assertion reads the metadata file and confirms `build.variant=ci`; `verify` fails the build if the test fails. Reports are normally written under `target/failsafe-reports/`. If no integration tests exist or none match the pattern, a green `verify` **is not enough** to conclude integration tests ran: always check the actual discovered test count.

**Why use `verify` instead of `package`?** The Maven lifecycle runs `test → package → pre-integration-test → integration-test → post-integration-test → verify`. `package` finishes **before** integration tests. Failsafe checks results at `verify` so `post-integration-test` still gets a chance to perform cleanup. Running `./mvnw -Pci clean package` only packages and never reaches `integration-test`/`verify` in this example.

With `./mvnw clean verify` **without `-Pci`**, the `ci` profile does not add Failsafe, so `BuildVariantIT` does not run by default through Failsafe; regular unit tests still run. In a project that configures Failsafe elsewhere (parent POM or another plugin execution), behavior may differ; verify via effective POM and logs.

## 7. Automatic Activation via Environment, Property, JDK, OS, or File

Beyond `-P`, Maven supports conditions inside `<activation>`. The snippets below are **alternative declarations to merge into the right profile**, not commands to combine all at once.

### 7.1. Activating by CLI Property

Inside the `ci` profile:

~~~xml
<activation>
    <property>
        <name>build.mode</name>
        <value>ci</value>
    </property>
</activation>
~~~

The following command activates this profile:

~~~bash
./mvnw -Dbuild.mode=ci clean verify
~~~

`-Dbuild.mode=ci` is a **Maven user property** acting as a trigger; it does not set `build.flavor=ci` unless the profile defines that property. `-Pci` remains clearer when you simply want to pick a named variant. Avoid property names that look like Spring runtime config keys.

### 7.2. Activating by CI Environment Variable

Instead of a CLI property, you can use:

~~~xml
<activation>
    <property>
        <name>env.CI</name>
    </property>
</activation>
~~~

Maven exposes environment variables as `env.NAME`. This condition matches whenever the `CI` variable exists; many CI platforms set it, though **not every system sets it identically**. A developer with `CI` exported in their local shell could also trigger the profile unintentionally. For critical pipelines, passing `-Pci` explicitly and logging the command is easier to audit.

### 7.3. Activating by JDK and Operating System

~~~xml
<!-- Each snippet below belongs inside its own <profile> as needed -->
<activation>
    <jdk>[17,)</jdk>
</activation>
~~~

~~~xml
<activation>
    <os>
        <family>Windows</family>
    </os>
</activation>
~~~

JDK activation evaluates the **JDK running Maven**, not necessarily the toolchain JDK selected by the Maven Compiler Plugin. OS activation evaluates the host OS running Maven. These triggers help handle tooling or native command differences; do not use them to branch application logic when the same artifact should run across OSes.

Maven also supports file-exists/file-missing activation, such as checking for a local config file. However, differing files between local machines and CI easily cause "same source, different build output"; use file activation only when genuinely needed and with clear relative paths.

### 7.4. `activeByDefault`: Understanding the Catch

~~~xml
<activation>
    <activeByDefault>true</activeByDefault>
</activation>
~~~

An `activeByDefault` profile in a POM is automatically **deactivated** whenever any other profile **in the same POM** is activated. This frequently surprises teams expecting the default profile to stay stacked on top. Shared baseline values belong in the root POM, such as `build.flavor=local`; put only **conditional overrides** inside profiles. When you need multiple independent features, design separate focused profiles instead of overusing `activeByDefault` to create unpredictable layers.

## 8. Effects of Multiple Profiles, Parents, and `settings.xml`

Maven can define profiles with the same ID in a parent POM, module POMs, or `settings.xml`. Never see the name `ci` and assume every module gets the identical effect.

- **Parent POM:** profiles are evaluated in the POM where they are declared; the *effects* of an active profile can be inherited by children when the build model is assembled. A profile definition itself is not an abstract template children arbitrarily toggle like a plugin.
- **Child POM:** can define its own profile IDs, configurations, and activations. A profile auto-activated in one module is not guaranteed to auto-activate in another just because they share an ID.
- **User/global settings:** primarily configure repositories, pluginRepositories, properties, or machine-level `<activeProfiles>`. They can silently alter dependency sources and properties without testers noticing.
- **Multiple active profiles:** when multiple active profiles in the same POM define the same scalar element, the profile defined **later** typically wins; collections/plugins follow specific merge rules. Do not rely on `-Pci,release` CLI ordering to encode business precedence.

Inspect the actual combined profile config with:

~~~bash
./mvnw -Pci help:active-profiles
./mvnw -Pci help:effective-pom
./mvnw -Pci dependency:tree
~~~

Especially in multi-module builds: compare affected modules, child plugin executions, newly added dependencies, and each module's effective POM. When building a single application module with `-pl`, select the right Maven selector and avoid skipping parent/reactor projects the module depends on.

## 9. Designing Safe Build Variants for Spring Boot

### When Does It Make Sense for a Profile to Change Dependencies?

A profile can add a dependency needed only in one build flavor, such as a build-check tool or a module-specific library. However, changing runtime dependencies via profiles creates **two artifacts with identical coordinates yet different classpaths**, complicating debugging, vulnerability scanning, and testing.

If dependencies must differ:

1. Document exactly which dependencies and scopes change when the profile is active.
2. Run `dependency:tree` under **each profile** and archive the output.
3. Inspect `compile`, `test`, and `runtime` scopes; do not just read the POM.
4. Keep versions managed by the Spring Boot BOM wherever possible, avoiding unverified overrides.
5. Use appropriate artifact classifiers/versions/publishing policies if variants are published side by side; never silently publish different contents under the same version.

### When Does It Make Sense for a Profile to Change Plugins?

CI or release profiles can add integration tests, coverage, static analysis, license checks, or quality verification. These **build-time** effects are much cleaner than injecting debug dependencies into production apps. If a release profile signs artifacts using credentials/secrets, have CI inject those secrets and never store secrets in the POM.

With Spring Boot Maven Plugin, `spring-boot:repackage` builds an executable archive when bound to the lifecycle. Profiles can tweak plugin settings, which alters JAR/WAR structure: inspect main class, layered JAR, classifier, and `java -jar` startup on the resulting artifact. **Never assume** `-Prelease` automatically "optimizes" a Boot JAR solely because of its profile name.

### Draw a Clear Boundary Between Build Time and Runtime

Maven profiles **must not hardcode** production database URLs, passwords, tokens, or API keys into `application.yml` via filtering. If using Maven filtering for text files, include only harmless metadata such as build flavor, revision, or tooling flags. Sensitive runtime values must come from deployment-time configuration and secret management.

## 10. CI Example Invoking a Profile Explicitly

This YAML snippet is an **illustrative workflow** placed at `.github/workflows/maven-verify.yml` in a repository using GitHub Actions. Adjust Java and action versions to your project policy:

~~~yaml
name: Verify Maven build

on:
  push:
  pull_request:

jobs:
  verify:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-java@v4
        with:
          distribution: temurin
          java-version: '21'
          cache: maven

      - name: Confirm Maven and profiles
        run: |
          java -version
          ./mvnw --version
          ./mvnw -Pci help:active-profiles

      - name: Unit and integration tests
        run: ./mvnw --batch-mode --no-transfer-progress -Pci clean verify

      - name: Inspect filtered metadata
        run: cat target/classes/build-variant.properties
~~~

The workflow assumes `mvnw` at the repository root has the **executable bit** set and the project builds on Java 21. In multi-module projects, adjust `working-directory` or the Wrapper and artifact paths. Explicit `-Pci` makes the CI profile transparent in logs, preventing runner environment variables from unexpectedly activating different profiles.

**Do not use Maven profiles to skip testing:** CI should run `verify` and capture evidence of actual unit/integration tests executed. If a `fast` profile exists for local developer iteration, clearly document which tests it skips and never equate its fast run with full CI verification.

Releases should be a separately controlled job triggered only after required checks and approvals. In this lesson's example, `-Prelease` only updates metadata; **it performs no deploy/publish** and touches no external artifact repository.

## 11. Step-by-Step Troubleshooting When a Profile Appears Inactive

| Symptom | Common Cause | How to Investigate |
| --- | --- | --- |
| Maven says profile ID does not exist | Typo in name, wrong POM/module directory, profile in another file, or Maven 4 strict checks | `help:all-profiles`, `help:active-profiles`, check POM and `-P` |
| `-Pci` runs yet `build.variant` stays `local` | Property overridden in child POM, settings/user property, or resource not filtered | Inspect effective POM, `target/classes` file, resources plugin execution |
| `build-variant.properties` still shows `@build.flavor@` | Folder/file not inside a filtered resource block | Check `<resources>` and `maven-resources-plugin` log; run `clean` and retry |
| `application.yml` contents unexpectedly modified | Filtering enabled across all of `src/main/resources` | Separate filtered resource directories and target exact text files; restore source |
| `-Pci clean package` runs no integration tests | `package` ends before `integration-test` and `verify` | Run `-Pci clean verify`, inspect `target/failsafe-reports` and test count |
| `verify` prints `BUILD SUCCESS` with zero ITs run | No `*IT` classes, missing Failsafe execution, or plugin missed tests | Inspect effective POM, naming patterns, test dependencies, and Failsafe reports |
| `activeByDefault` stops working when another profile is enabled | Maven disables same-POM default profile when another profile activates | Move baseline settings to root POM; clarify activation rules |
| Profile auto-activates in CI but not locally | Different `env.CI`, JDK, OS, file, or settings | Run `help:active-profiles` and `--version` in both places; prefer explicit `-P` |
| Maven profile active yet Spring still uses `default` | Maven profiles and Spring runtime profiles are separate mechanisms | Check runtime config, `SPRING_PROFILES_ACTIVE`, and Spring `ApplicationContext` logs |
| Build passes yet JAR fails to run | Profile altered dependencies/plugins, artifacts, or resources | Compare dependency tree, executable JAR, Java runtime, and integration tests |
| One module gets the plugin while another does not | Parent/module profile or differing configuration inheritance | Inspect effective POM **per module** in the reactor |
| Artifact changes despite unchanged code | Differing profiles, resource filtering, plugins, user settings, or dependency resolution | Record Maven/JDK, active profiles, properties, effective POM, and CI env |

**Short debugging routine:** record the exact Wrapper command → inspect active profiles → inspect effective POM → compare build output/resources → inspect test reports → retry with `clean` on the exact module. Never change multiple profiles at once before isolating the root cause.

## 12. Hands-On Exercise with Acceptance Criteria

Use a working Maven Spring Boot project on an experimental branch:

1. Add the baseline `build.flavor=local` property and the three resource/profile snippets from Section 5; create `src/main/build-resources/build-variant.properties`.
2. Run **default**: `./mvnw clean verify`; confirm the generated file has `build.variant=local`.
3. Run **CI**: `./mvnw -Pci clean verify`; confirm `help:active-profiles` lists `ci`, metadata reads `ci`, and Failsafe discovers at least one `*IT` test if you added Section 6's test.
4. Run **release**: `./mvnw -Prelease clean package`; confirm metadata reads `release`. Verify that `-Prelease` does not trigger deployment or a Spring runtime profile.
5. Export/read the effective POMs for `ci` and `release`, pointing out differences in `maven-failsafe-plugin`, resource properties, and build outputs.
6. Intentionally run `-Pci,release` and observe the final `build.flavor` value per merge rules; then **remove conflicting combinations** from CI scripts and document the agreed command.
7. Explain aloud: when to use Maven profiles vs. Spring runtime profiles; why production secrets must not go into resource filtering; and why `package` is insufficient to prove integration tests ran.

You pass when you can **reproduce intentional differences** across build variants, prove active profiles with Maven tooling, and verify that tests and artifacts accurately reflect the selected profile.

## 13. Principles for Real-World Projects

- Keep the base POM buildable with standard commands; reserve profiles for **justified build changes** instead of creating a profile for every minor option.
- Maintain a clear, version-controlled CI profile tested through the Wrapper; log active profiles and Maven/JDK versions.
- Never turn a build profile into storage for production runtime config. Keep Spring active profile selection separate at application startup.
- Avoid opaque profile side effects: changing package versions, skipping tests, dependency overrides, or plugin executions that only run on the author's laptop.
- For every release variant, verify the actual artifact, dependency graph, filtered resources, and startup behavior. Preserve traceability of build profile, version, and revision.
- When migrating Maven or Spring Boot versions, retest all active profiles; effective POMs and lifecycle/plugin executions can shift across parent or plugin updates.

## Official Documentation

- [Apache Maven – Introduction to Build Profiles](https://maven.apache.org/guides/introduction/introduction-to-profiles.html)
- [Apache Maven – Maven POM Reference](https://maven.apache.org/pom.html)
- [Apache Maven Help Plugin – active-profiles](https://maven.apache.org/plugins/maven-help-plugin/active-profiles-mojo.html)
- [Apache Maven Help Plugin – effective-pom](https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html)
- [Apache Maven Resources Plugin – Filtering](https://maven.apache.org/plugins/maven-resources-plugin/examples/filter.html)
- [Apache Maven Failsafe Plugin](https://maven.apache.org/surefire/maven-failsafe-plugin/)
- [Spring Boot Maven Plugin – Using the Plugin](https://docs.spring.io/spring-boot/maven-plugin/using.html)
- [Spring Boot – Profiles](https://docs.spring.io/spring-boot/reference/features/profiles.html)