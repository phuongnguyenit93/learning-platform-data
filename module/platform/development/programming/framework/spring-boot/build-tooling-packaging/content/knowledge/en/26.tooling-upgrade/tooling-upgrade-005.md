# Upgrading the Wrapper and Verifying Existing Convention Plugins or Parent POMs

## 1. Objectives and Principles

The Maven Wrapper and Gradle Wrapper pin the build tool version a project uses. They ensure developers, CI, and other build machines run the exact same Maven/Gradle version without relying on a globally installed version on the machine. When upgrading a Wrapper, you must also inspect the project's shared configuration layer: convention plugins in Gradle or the parent POM in Maven. These are usually where plugin versions, compiler/toolchain settings, test configuration, dependency management, and multi-module build conventions live.

Objectives of the process:

- Upgrade the Wrapper version in a controlled way, keep wrapper files synchronized, and verify the downloaded distribution.
- Identify whether the build uses Gradle convention plugins or a Maven parent POM, then verify the existing mechanism.
- Detect configurations that are duplicated, overridden, no longer compatible, or only work because of a personal machine's environment.
- Run tests across the entire reactor/multi-project build and in CI using the newly upgraded Wrapper itself.
- Separate Wrapper changes from convention/parent changes when possible to isolate causes if the build breaks.

**Do not upgrade a version just because a new release exists.** First identify the Java runtime, Spring Boot version, plugins, repositories, CI runners, and modules in use. Pick a target version that supports those components, then upgrade in verifiable steps.

## 2. What Does the Wrapper Actually Pin?

The Wrapper is a launcher script for the build tool bundled with the project. When running:

~~~bash
./gradlew clean build
~~~

or:

~~~bash
./mvnw clean verify
~~~

the wrapper script reads the distribution configuration, downloads the exact Maven/Gradle distribution if not yet cached, and starts the build using that distribution.

| Project | Key Files | Role |
| --- | --- | --- |
| Gradle | `gradlew`, `gradlew.bat` | Scripts for Unix-like OSes and Windows |
| Gradle | `gradle/wrapper/gradle-wrapper.jar` | Wrapper bootstrap code |
| Gradle | `gradle/wrapper/gradle-wrapper.properties` | Distribution URL, checksum, and download options |
| Maven | `mvnw`, `mvnw.cmd` | Scripts for Unix-like OSes and Windows |
| Maven | `.mvn/wrapper/maven-wrapper.properties` | Distribution URL and Wrapper configuration |
| Maven | `.mvn/wrapper/maven-wrapper.jar` (if the Wrapper type uses this file) | Wrapper bootstrap |

The Wrapper **does not by itself lock down the entire build environment**. Results can still differ if the JDK, environment variables, OS, native libraries, repository contents, plugin versions, dependency versions, or CI configuration differ. Therefore, you must verify both the Wrapper and the shared configuration layer.

Distinguish two important Java concepts:

- **JDK running the build tool:** the JVM used to run the Gradle/Maven daemon or process.
- **Java toolchain/compiler target:** the JDK/compiler used to compile and run project tests.

Upgrading Gradle/Maven can change the minimum JDK required to run the build tool. That does not mean the application must change its Java target at the same time. Check both requirements separately.

## 3. Pre-Upgrade Survey

Before editing files, record the current state and establish a comparable baseline.

### 3.1. Identify the Build Type and Module Scope

Check the indicators in the repository:

| Indicator | Common Conclusion |
| --- | --- |
| `settings.gradle` or `settings.gradle.kts` | Gradle build, possibly multi-project |
| `build.gradle` or `build.gradle.kts` | Gradle project/module |
| `build-logic/` or `buildSrc/` | May contain convention plugins or build logic |
| Root `pom.xml` with `pom` packaging | May be a Maven aggregator/parent |
| Module POM has `parent` pointing to root | Modules inherit the internal parent POM |
| Parent POM declared via `groupId`/`artifactId`/`version` | May be fetched from a Maven repository |
| `.mvn/wrapper` or `gradle/wrapper` | Project already has the corresponding Wrapper |

Read the exact build files and directly referenced files. For Gradle, check plugins applied by ID, `pluginManagement`, `includeBuild`, `buildSrc`, and version catalogs. For Maven, trace the parent chain, `dependencyManagement`, `pluginManagement`, `build/plugins`, and modules in the reactor.

Do not create a new convention plugin or a new parent POM if the project already has a configuration-sharing mechanism. The goal of this guide is to upgrade and verify the existing mechanism.

### 3.2. Record the Baseline Versions

Gradle:

~~~bash
./gradlew --version
~~~

Maven:

~~~bash
./mvnw --version
~~~

Record:

- Wrapper version and actual build tool version.
- JVM used to run the build tool.
- Java toolchain/release required by the project.
- Spring Boot version and key build plugins.
- Custom or internal plugins.
- Which modules use which convention plugin/parent POM.
- CI commands currently run and enabled profiles/environments.

Run a pre-upgrade baseline:

~~~bash
./gradlew clean check
~~~

or:

~~~bash
./mvnw -B -ntp clean verify
~~~

If the baseline is already failing, record the existing error before changing anything. Without a baseline, it is very hard to tell whether a failure came from the Wrapper or from an already broken build configuration.

### 3.3. Check the Compatibility Matrix

Cross-check at least these relationships:

1. Gradle/Maven version vs. JDK used to run the build tool.
2. Spring Boot version vs. supported Java version and Gradle/Maven plugin versions.
3. Convention plugin or parent POM vs. the plugin versions it manages.
4. Third-party plugins vs. new Gradle/Maven APIs.
5. CI runner image vs. JDK, shell, Docker daemon, and required tools.
6. Internal repository vs. TLS, authentication, mirrors, and metadata format.

In particular, Gradle has two distinct compatibility boundaries: the JVM running Gradle and the application's Java toolchain. A newer Gradle release may require a newer JDK to run, even if the project still compiles with an older toolchain when that combination is supported.

With Maven, check the Maven runtime JDK, Maven Compiler Plugin, Surefire/Failsafe, and packaging plugins. Do not assume that because Maven runs on a given JDK, every compiler/plugin in the project is compatible with that JDK.

## 4. Upgrading the Gradle Wrapper

### 4.1. Choose a Version and Update via the Wrapper Task

Pick a Gradle version whose compatibility has been verified. If the current Wrapper works, use the Wrapper itself to upgrade:

~~~bash
./gradlew wrapper --gradle-version 8.14.3 --distribution-type bin
~~~

The version in the example illustrates syntax only; replace it with the project-approved target version. You can choose distribution type `bin` for a smaller download; choose `all` if the team needs bundled source/documentation for IDE debugging.

After the task finishes, inspect changes in:

- `gradle/wrapper/gradle-wrapper.properties`
- `gradle/wrapper/gradle-wrapper.jar`
- `gradlew`
- `gradlew.bat`

Depending on the Wrapper version and current file state, you may need to run the Wrapper task once more using the new Wrapper to synchronize scripts/JAR. Do not apply mechanically: inspect the diff and follow the target Gradle version's instructions, then confirm all necessary files were updated.

### 4.2. Inspect gradle-wrapper.properties

Example configuration:

~~~properties
distributionBase=GRADLE_USER_HOME
distributionPath=wrapper/dists
distributionUrl=https://services.gradle.org/distributions/gradle-8.14.3-bin.zip
networkTimeout=10000
zipStoreBase=GRADLE_USER_HOME
zipStorePath=wrapper/dists
~~~

In a real file, if policy requires a checksum, set `distributionSha256Sum` to the official SHA-256 matching that exact chosen distribution file. Do not copy the checksum from the `all` distribution to `bin`, or from another version.

Items to verify:

- Distribution URL uses HTTPS and points to the exact version.
- Checksum is taken from Gradle's official checksums page and reviewed alongside the URL.
- Does not point to an arbitrary ZIP on a developer machine or an uncontrolled URL.
- Do not remove the checksum just to get a build passing quickly if project policy requires distribution verification.
- Cache path is under Gradle User Home, not the application's build output directory.

`distributionSha256Sum` verifies the downloaded distribution ZIP. It does not replace checking the integrity of the Wrapper JAR or reviewing wrapper scripts.

### 4.3. Inspect the Wrapper JAR and Scripts

The Wrapper JAR is an executable file committed into the repository. If the JAR is tampered with, the wrapper could execute unexpected behavior before the build even starts. Therefore:

- Keep the Wrapper JAR generated from official Wrapper sources.
- Review diffs to the JAR and scripts; do not take files from untrusted commits/URLs.
- Use the Gradle Wrapper Validation Action in GitHub Actions or your organization's equivalent verification process.
- Pin CI actions by reviewed commit SHA if supply-chain policy requires it.
- Do not manually edit scripts just to mask a compatibility error.

After upgrading, run:

~~~bash
./gradlew --version
./gradlew help
./gradlew tasks
~~~

The first command confirms the distribution/JVM. The next two force Gradle to configure the build and list tasks, exposing plugin or build-logic errors early before running long tests.

### 4.4. Test from a Clean Environment

The Wrapper may work on a machine with a cached distribution, whereas CI or a new developer may not have it cached yet. Test on a clean runner/container or clear only the Wrapper cache in a separate test environment and re-run.

Do not wipe the entire shared Gradle User Home on a shared machine just to test. You can use a temporary Gradle User Home:

~~~bash
GRADLE_USER_HOME="$(mktemp -d)"
export GRADLE_USER_HOME
./gradlew --version
./gradlew help
~~~

On PowerShell, use a separate temporary directory and set the corresponding environment variable for the process. Afterward, clean up the temporary directory you created.

The goal is to confirm the distribution downloads from the committed URL, the checksum is valid, the Wrapper starts up, and the build does not rely on unmanaged local files.

## 5. Upgrading the Maven Wrapper

### 5.1. Choose the Target Maven Distribution

Check the current Maven version:

~~~bash
./mvnw --version
~~~

Upgrade the Wrapper using the Maven Wrapper Plugin with the plugin version and syntax supported by the official documentation of the plugin in use. One common command form is:

~~~bash
mvn wrapper:wrapper -Dmaven=3.9.9
~~~

Replace the illustrative version with the Maven version chosen after checking JDK and plugin compatibility. If the current Wrapper still works, you can use it to run the plugin; if there is no Wrapper yet, use a locally installed Maven to bootstrap it once, then commit all generated wrapper files.

### 5.2. Inspect maven-wrapper.properties

Example distribution URL:

~~~properties
distributionUrl=https://repo.maven.apache.org/maven2/org/apache/maven/apache-maven/3.9.9/apache-maven-3.9.9-bin.zip
~~~

Some Maven Wrapper versions/types support additional checksum or wrapper artifact settings. Only add properties actually supported by the implementation in use; verify property names and semantics in the matching Maven Wrapper documentation. Do not guess property names from Gradle Wrapper because the two implementations are not identical.

Verify:

- HTTPS URL points to the exact Maven distribution and version.
- Distribution is fetched from Apache Maven or a trusted internal mirror.
- If the Wrapper supports distribution/JAR checksums, pin the corresponding official checksum and review the change.
- Commit `mvnw`, `mvnw.cmd`, `.mvn/wrapper/maven-wrapper.properties`, and the bootstrap JAR if that Wrapper type uses it.
- Do not commit downloaded cache files or the local Maven repository.

### 5.3. Test the Maven Wrapper on Windows and Unix

Run:

~~~bash
./mvnw --version
./mvnw -B -ntp help:effective-pom
~~~

On Windows:

~~~powershell
.\mvnw.cmd --version
.\mvnw.cmd -B -ntp help:effective-pom
~~~

Confirm both scripts exist in the repository and can run in their corresponding CI environments. For the Unix script, preserve the executable bit if the repository/CI invokes `./mvnw` directly. Check line endings and executable permissions when diffing wrapper files.

## 6. Verifying Existing Gradle Convention Plugins

A convention plugin centralizes shared build rules so modules can apply them via a plugin ID. It may set the Java toolchain, test framework, compiler flags, Spring Boot conventions, dependency constraints, lint/check tasks, and packaging conventions.

### 6.1. Locate Where the Plugin Is Declared

Common locations:

- `buildSrc/src/main/kotlin` or `buildSrc/src/main/groovy`.
- An included build such as `build-logic`.
- Precompiled script plugins in `build-logic/src/main/kotlin`.
- Binary plugins published from an internal repository.
- Plugins declared via `pluginManagement` in `settings.gradle.kts`.

Find the plugin ID in modules and trace it back to its implementation. Identify the plugin's version and the dependencies of the build logic itself. Do not confuse applying a plugin in a module with the dependency/plugin versions declared inside build logic.

### 6.2. Example Included Build Containing a Precompiled Convention Plugin

Illustrative structure:

~~~text
project/
├── settings.gradle.kts
├── build.gradle.kts
├── build-logic/
│   ├── build.gradle.kts
│   └── src/main/kotlin/
│       └── acme.java-conventions.gradle.kts
├── service-a/
│   └── build.gradle.kts
└── service-b/
    └── build.gradle.kts
~~~

In `settings.gradle.kts`:

~~~kotlin
pluginManagement {
    includeBuild("build-logic")
}

rootProject.name = "sample-platform"
include("service-a", "service-b")
~~~

In `build-logic/build.gradle.kts`:

~~~kotlin
plugins {
    `kotlin-dsl`
}

repositories {
    gradlePluginPortal()
    mavenCentral()
}
~~~

In `build-logic/src/main/kotlin/acme.java-conventions.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(17))
    }
}

tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

Module applying the convention:

~~~kotlin
plugins {
    id("acme.java-conventions")
}
~~~

The precompiled script plugin filename determines the plugin ID per Gradle rules. The example above creates the ID `acme.java-conventions`. In a real project, do not rename the ID arbitrarily because other modules, plugin aliases, or build scripts may depend on it.

This example illustrates only a small Java convention. If existing conventions also configure Spring Boot, publishing, dependency management, or quality checks, preserve those behaviors and verify them after upgrading the Wrapper.

### 6.3. Check Plugin Dependency Versions

A convention plugin may depend on Gradle APIs, the Kotlin DSL plugin, the Spring Boot Gradle Plugin, or third-party plugins. When upgrading Gradle:

- Check whether the plugins support the target Gradle version.
- Pin plugin dependency versions inside build logic.
- Avoid declaring the same plugin version in multiple places when it can be managed centrally.
- Verify plugin markers/artifacts can be downloaded from the repositories configured in build logic.
- Check that plugins do not use deprecated or removed Gradle APIs.
- Check whether plugins support Configuration Cache if the project enables it.

If the convention plugin uses the Spring Boot Gradle Plugin, upgrade and verify the Spring Boot version per a separate compatibility matrix. Do not assume upgrading the Wrapper automatically upgrades the Spring Boot plugin.

### 6.4. Verify Conventions Are Actually Applied

A plugin existing in build logic does not mean every module uses it. Check:

- Which modules declare the plugin ID.
- Which modules have local configuration overriding the convention.
- Whether a plugin is applied twice via a root plugin and a module plugin.
- Whether the root project accidentally applies a plugin meant only for application modules.
- Whether tasks created by the convention exist and are configured properly.

Run:

~~~bash
./gradlew projects
./gradlew tasks --all
./gradlew help
~~~

Then run tasks for each module type, for example:

~~~bash
./gradlew :service-a:tasks --all
./gradlew :service-a:clean :service-a:check :service-a:bootJar
~~~

Do not rely on the root build succeeding if application or library modules have not been configured/tested.

### 6.5. Testing Convention Plugins with Gradle TestKit

For convention plugins with substantial logic, use Gradle TestKit to create a temporary sample project, apply the plugin, and inspect results. TestKit runs a real build via `GradleRunner`.

Conceptual test example:

~~~kotlin
class JavaConventionsPluginTest {
    @TempDir
    lateinit var projectDir: File

    @Test
    fun `applies java plugin and configures toolchain`() {
        projectDir.resolve("settings.gradle.kts")
            .writeText("rootProject.name = \"sample\"")

        projectDir.resolve("build.gradle.kts").writeText(
            """
            plugins {
                id("acme.java-conventions")
            }
            """.trimIndent()
        )

        val result = GradleRunner.create()
            .withProjectDir(projectDir)
            .withPluginClasspath()
            .withArguments("tasks", "--stacktrace")
            .build()

        assertTrue(result.output.contains("build"))
    }
}
~~~

This is a structural test example; the test project must declare Gradle TestKit, JUnit, and plugin classpath appropriately for how build logic is organized. Real assertions should verify critical behaviors: Java plugin applied, toolchain/release set properly, test task uses JUnit Platform, convention tasks exist, and overrides work properly.

If a convention plugin is only a few lines of simple configuration, a fixture integration build running representative modules may suffice. No need to build complex TestKit suites for every single line of config.

### 6.6. Checking Conventions with Configuration Cache

If the project enables Configuration Cache, run the build twice:

~~~bash
./gradlew check --configuration-cache
./gradlew check --configuration-cache
~~~

The second run should reuse the cache if the build and plugins are compatible. Read warnings about incompatible tasks/plugins; do not disable Configuration Cache globally just to make errors disappear without identifying the root cause.

Verify custom plugins do not eagerly read the environment/filesystem or hold unsafe state during the configuration phase. Fix the convention plugin or task implementation where the error originates, then re-run the representative build.

## 7. Verifying Existing Maven Parent POMs

A parent POM typically manages dependency versions, plugins, compiler settings, test plugins, profiles, repository policies, and shared properties. In multi-module Maven builds, the root POM can act as both aggregator and parent, though those two roles are distinct:

- **Aggregator:** declares `<modules>` so the Maven reactor builds them together.
- **Parent:** supplies configuration inherited by modules via `<parent>`.

A POM with `<modules>` does not automatically become the parent of every module. Modules must declare the exact parent coordinates to inherit from it.

### 7.1. Distinguishing dependencyManagement and pluginManagement

| Section | What It Manages | Activates Automatically? |
| --- | --- | --- |
| `dependencyManagement` | Dependency versions, default scopes/types/exclusions | Does not automatically add dependencies to a module |
| `dependencies` | Dependencies actually placed on the project's classpath | Yes |
| `pluginManagement` | Plugin versions and default configuration | Does not automatically run a plugin just because it is managed |
| `build/plugins` | Plugins declared for the build; can be inherited | Yes, per configured lifecycle/execution/goal |

A well-structured parent POM keeps modules from repeating identical versions and settings. However, placing a plugin only in `pluginManagement` still requires declaring the plugin in `build/plugins` when you want to apply it (except for plugins invoked by lifecycle mappings or other mechanisms).

### 7.2. Example Parent POM Managing Compiler and Spring Boot BOM

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme.build</groupId>
    <artifactId>acme-parent</artifactId>
    <version>1.0.0</version>
    <packaging>pom</packaging>

    <properties>
        <maven.compiler.release>17</maven.compiler.release>
        <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
        <spring-boot.version>3.5.0</spring-boot.version>
    </properties>

    <dependencyManagement>
        <dependencies>
            <dependency>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-dependencies</artifactId>
                <version>${spring-boot.version}</version>
                <type>pom</type>
                <scope>import</scope>
            </dependency>
        </dependencies>
    </dependencyManagement>

    <build>
        <pluginManagement>
            <plugins>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-compiler-plugin</artifactId>
                    <version>3.14.0</version>
                    <configuration>
                        <release>${maven.compiler.release}</release>
                    </configuration>
                </plugin>
                <plugin>
                    <groupId>org.apache.maven.plugins</groupId>
                    <artifactId>maven-surefire-plugin</artifactId>
                    <version>3.5.3</version>
                </plugin>
            </plugins>
        </pluginManagement>
    </build>
</project>
~~~

This is an illustrative parent POM. In a real project, pick versions according to a verified compatibility matrix and centralize them in one place. Do not copy example versions into production without verification.

Child module declaring parent:

~~~xml
<parent>
    <groupId>com.acme.build</groupId>
    <artifactId>acme-parent</artifactId>
    <version>1.0.0</version>
    <relativePath>../pom.xml</relativePath>
</parent>
~~~

If the parent is published separately and no POM file exists at the default relative path, configure `relativePath` accordingly; an empty `<relativePath/>` can be used to tell Maven to resolve the parent from repositories rather than looking for a local POM by default.

### 7.3. Spring Boot Parent or Spring Boot BOM?

Maven only allows one direct parent in `<parent>`. If a project already has an internal parent POM, you cannot simultaneously declare `spring-boot-starter-parent` as a second parent on the module.

Two common patterns exist:

1. The internal parent inherits from the Spring Boot parent, and modules inherit from the internal parent.
2. The internal parent stands alone and imports the `spring-boot-dependencies` BOM in `dependencyManagement`, while explicitly managing needed plugin versions and configurations itself.

Importing the BOM manages dependency versions; it does not automatically bring all plugin management, build defaults, or executions from the Spring Boot parent. When using BOM import, inspect the Spring Boot Maven Plugin and `repackage` execution separately if the application needs to build an executable archive.

Do not assume importing the BOM means the Spring Boot Maven Plugin is already enabled.

### 7.4. Inspecting the Effective POM

The POM Maven actually uses is the result of parent inheritance, profiles, properties, dependency management, plugin management, and other settings. Use the Help Plugin to inspect the effective POM:

~~~bash
./mvnw -pl :service-a help:effective-pom -Dverbose
~~~

You can write it to a file in the build directory for comparison:

~~~bash
./mvnw -pl :service-a help:effective-pom -Dverbose -Doutput=target/effective-pom.xml
~~~

Check:

- Actual parent coordinates and version.
- Maven Compiler Plugin version and release.
- Surefire/Failsafe version, includes/excludes, and system properties.
- Spring Boot Maven Plugin version, executions, and `repackage` goal.
- Dependency versions managed by BOM/parent.
- Which profiles are active and which properties override the parent.
- Which plugin configurations are overridden by child modules.
- Plugins have explicit versions rather than relying on uncontrolled default versions.

Verbose output helps trace configuration origins on supported Help Plugin versions. The effective POM is a diagnostic tool, not a file to commit in place of the original POM.

### 7.5. Verifying the Reactor and Individual Modules

Run from the root:

~~~bash
./mvnw -N -B -ntp validate
./mvnw -B -ntp clean verify
~~~

To check only one module along with the reactor modules it depends on:

~~~bash
./mvnw -pl :service-a -am -B -ntp clean verify
~~~

`-pl` selects the project; `-am` includes upstream modules required in the reactor. Also run modules with different packaging types (library, application, integration test) if the parent POM applies different configurations.

For a separately published parent POM, test both cases: modules building within the reactor and a module resolving the parent from a repository. A passing reactor build alone does not prove the parent artifact was published and resolves properly in a clean environment.

## 8. Verifying Inherited and Overridden Configurations

Upgrading a Wrapper can expose discrepancies between centralized configuration and local module configuration. Check systematically:

| Question | Gradle Convention Plugin | Maven Parent POM |
| --- | --- | --- |
| Where does config live? | `build-logic`/`buildSrc`/plugin artifact | Parent POM |
| How do modules apply it? | Plugin ID | Parent coordinates |
| Where are plugin versions managed? | `pluginManagement`/build logic/version catalog | `pluginManagement`/plugin declarations |
| Where are dependency versions? | Version catalog/platform/constraints | `dependencyManagement`/BOM |
| How to inspect effective config? | `tasks`, `dependencies`, task reports, test fixtures | `help:effective-pom`, `dependency:tree` |
| Checking inheritance/overrides? | Compare plugin application and module-specific config | Compare effective POMs and profiles |
| Testing custom logic? | Gradle TestKit/integration build | Reactor fixture/sample module/integration test |

### 8.1. Avoiding Duplicate Configurations

Gradle example: the root `plugins` block pins a Spring Boot version, build logic declares a different version, and a module applies the plugin with its own version. This causes behavioral drift across modules.

Maven example: the parent manages Surefire 3.x, a child module specifies an old version in `build/plugins`, and the child overrides parent configuration. The effective POM reveals the final version and configuration.

When duplication is found, identify where ownership of the version/configuration belongs. Move shared values into the existing central mechanism, and remove old declarations only after verifying no module still needs them.

### 8.2. Checking Profiles and Environments

Maven profiles can be activated by JDK, OS, properties, settings, or CLI flags. Gradle can alter configuration based on project properties, environment variables, settings plugins, or init scripts. CI may also supply init scripts/settings that differ from local machines.

Therefore, record the exact commands and properties used for verification. Compare:

- Local build vs. CI build.
- Default build vs. profile/release profile.
- Root build vs. direct module build.
- Cached build vs. clean build.
- Reactor build vs. resolving parent/plugins from a repository.

Do not include credentials or secrets in diagnostic output. When inspecting properties, print only names and whether they are set; never print secret values.

## 9. Recommended Upgrade Workflow

Follow these steps to isolate any breaking change easily.

### Step 1 — Capture a Baseline

Save the Wrapper version, JVM, test/verify results, module list, and effective configuration. Record any pre-existing failures before changing anything.

### Step 2 — Upgrade Only the Wrapper

Update only the Gradle Wrapper or Maven Wrapper and its wrapper files. Do not simultaneously upgrade Spring Boot, plugins, dependencies, or build structure.

### Step 3 — Verify the Wrapper

Check the URL, checksum, Wrapper JAR/scripts, executable bits, and run version/help in a clean environment. If the Wrapper cannot run yet, do not proceed to modifying conventions/parent POMs.

### Step 4 — Inspect the Existing Sharing Mechanism

- For Gradle: check convention plugins, included builds/`buildSrc`, `pluginManagement`, and the version catalog.
- For Maven: check the parent chain, `dependencyManagement`, `pluginManagement`, profiles, and the effective POM.

Identify the minimal compatibility changes needed; do not switch from convention plugins to a parent POM or vice versa during the same Wrapper upgrade.

### Step 5 — Update Central Configuration

Upgrade plugin dependencies or fix deprecated/removed APIs in the centralized management location. Keep module-specific overrides if intentional and backed by tests.

### Step 6 — Test Representative Modules, Then the Full Build

Pick at least one application module, one library module, and any module with special configuration (integration tests, publishing, or custom packaging). Then run the full multi-project/reactor build.

### Step 7 — Verify in CI

CI must invoke the committed Wrapper, not a globally installed Maven/Gradle binary as a substitute. Run wrapper validation, verify the JDK, and execute the same verification commands as locally. Test building from a clean checkout and empty cache.

### Step 8 — Review the Diff and Record Results

Review all Wrapper files, build logic/parent POMs, version changes, and effective configuration. Record the upgrade rationale, target version, verified compatibility, test commands, and any behavior changes.

## 10. Reference Verification Command Suite

### 10.1. Gradle

~~~bash
./gradlew --version
./gradlew help
./gradlew projects
./gradlew tasks --all
./gradlew clean check
./gradlew build
./gradlew check --configuration-cache
./gradlew check --configuration-cache
~~~

For a specific module:

~~~bash
./gradlew :service-a:clean :service-a:check :service-a:bootJar
~~~

If the project has no `bootJar` task (such as a library module), substitute the task appropriate for that module type. Do not add dummy tasks just to make sample commands run.

### 10.2. Maven

~~~bash
./mvnw --version
./mvnw -N -B -ntp validate
./mvnw -pl :service-a help:effective-pom -Dverbose
./mvnw -pl :service-a -am -B -ntp clean verify
./mvnw -B -ntp clean verify
~~~

If a module uses Failsafe integration tests, verify integration-test/verify executions and required environments. If the parent POM has a release profile, test that profile separately in a protected CI job.

### 10.3. What to Save

A useful upgrade report contains:

- Old and new Wrapper versions.
- Verified distribution URL/checksum.
- JDK running the build tool and Java toolchain.
- Affected plugin/convention/parent versions.
- Effective POM or Gradle task/configuration evidence for representative modules.
- Test commands and exit statuses.
- CI run from a clean checkout.
- Known limitations or modules not yet verified.

Do not put secret contents, settings credentials, or tokens into the report.

## 11. Common Failures and Troubleshooting

| Symptom | Common Cause | How to Fix |
| --- | --- | --- |
| Wrapper downloads the wrong version | `distributionUrl` was not updated or old cache masks the issue | Check properties, run in a temporary Gradle User Home/Maven cache |
| Gradle Wrapper reports checksum mismatch | Checksum does not match the ZIP or version/type | Obtain the official checksum for that exact distribution; do not skip validation |
| Wrapper runs locally but fails in CI | Missing script/JAR, executable bit, shell, or different JDK | Commit all wrapper files, check Unix/Windows scripts and JDK |
| Gradle fails to start on current JDK | Target Gradle requires a newer JVM | Upgrade the JDK running Gradle in CI/developer machines, separate from target toolchain |
| Gradle reports incompatible plugin | Plugin uses removed APIs or version lacks support for new Gradle | Check compatibility, upgrade plugin, or update convention plugin |
| Convention plugin not found | Wrong `includeBuild`/plugin ID/source layout | Check settings, plugin filenames, and plugin classpath |
| Plugin applied twice | Both root and module apply it or overlapping conventions | Designate a single owner for applying the plugin |
| Gradle task missing on a module | Convention plugin not applied to that module or different module type | Check plugin ID and tasks appropriate for that module |
| Configuration Cache not reused | Plugin/task incompatible or configuration reads state unsafely | Read the problem report, fix plugin/task, and run twice |
| Maven parent fails to resolve | Wrong coordinates/version/`relativePath` or artifact not published | Check parent declaration and repository resolution |
| Maven module does not inherit plugin | Only in `pluginManagement`, not declared in `build/plugins` | Activate plugin in module/parent as intended |
| Effective POM has old version | Module/profile overrides parent | Locate override source and unify version management |
| Spring Boot `repackage` does not run | Using BOM without plugin execution | Explicitly configure Spring Boot Maven Plugin and `repackage` |
| Reactor build passes but standalone module build fails | Internal parent exists only in reactor/local repo | Verify parent artifact publishes/resolves from a clean repository |
| CI and local give different effective configs | Different profiles, init scripts, env, or settings | Compare commands, active profiles, and build configs |
| Cached build passes but clean build fails | Cache masks missing dependency or task input | Run `clean` in a clean environment and fix dependency/input declarations |
| Wrapper upgrade produces a noisy diff | Updated Wrapper, plugin, dependencies, and formatting together | Split changes into focused, purpose-built commits |

## 12. Pre-Merge Checklist

- [ ] Recorded baseline Wrapper version, JVM, and pre-upgrade build results.
- [ ] Identified existing Gradle convention plugins or Maven parent POM.
- [ ] Verified compatibility of build tool, JDK, Spring Boot, and plugins.
- [ ] Gradle distribution URL or Maven distribution URL points to a trusted source.
- [ ] Gradle distribution checksum verified if required by policy.
- [ ] Wrapper JAR and scripts reviewed/validated; no files taken from unknown sources.
- [ ] Committed all required wrapper scripts, properties, and bootstrap JARs.
- [ ] Unix and Windows wrapper scripts tested for supported CI environments.
- [ ] Gradle convention plugin IDs, plugin classpath, and module applications are consistent.
- [ ] Maven parent chain, `relativePath`, and artifact resolution work properly.
- [ ] Distinguished `dependencyManagement` from `dependencies`, and `pluginManagement` from `build/plugins`.
- [ ] Effective POM or Gradle task/configuration evidence inspected on representative modules.
- [ ] Module-specific overrides reviewed.
- [ ] Build/tests pass from a clean checkout and empty cache.
- [ ] Full multi-project/reactor build verified.
- [ ] CI uses the repository Wrapper, exact JDK, and does not rely on globally installed tools.
- [ ] No credentials, tokens, caches, or temporary files committed/uploaded.
- [ ] Diff contains only intentional changes that are reviewable and reversible.

## 13. Official Documentation

- Gradle — The Gradle Wrapper: https://docs.gradle.org/current/userguide/gradle_wrapper.html
- Gradle — Compatibility Matrix: https://docs.gradle.org/current/userguide/compatibility.html
- Gradle — Pre-compiled Script Plugins: https://docs.gradle.org/current/userguide/implementing_gradle_plugins_precompiled.html
- Gradle — Sharing Build Logic Between Subprojects: https://docs.gradle.org/current/userguide/sharing_build_logic_between_subprojects.html
- Gradle — Testing Gradle Plugins: https://docs.gradle.org/current/userguide/testing_gradle_plugins.html
- Gradle — Configuration Cache Requirements: https://docs.gradle.org/current/userguide/configuration_cache_requirements.html
- Apache Maven — Maven Wrapper: https://maven.apache.org/tools/wrapper/
- Apache Maven — POM Reference: https://maven.apache.org/pom.html
- Apache Maven — Introduction to the POM: https://maven.apache.org/guides/introduction/introduction-to-the-pom.html
- Apache Maven Help Plugin — effective-pom: https://maven.apache.org/plugins/maven-help-plugin/effective-pom-mojo.html
- Apache Maven — Maven Enforcer Plugin: https://maven.apache.org/enforcer/maven-enforcer-plugin/
- Spring Boot — Build Tool Plugins: https://docs.spring.io/spring-boot/gradle-plugin/
- Spring Boot — Maven Plugin: https://docs.spring.io/spring-boot/maven-plugin/

**Conclusion:** Upgrading the Wrapper changes the build tool version; verifying convention plugins or parent POMs confirms that every module still receives the expected build conventions afterward. Capture a baseline, upgrade the Wrapper, verify the distribution and scripts, inspect shared configuration in the right place, check effective configuration, run representative modules, and then verify the full build and CI from a clean checkout.
