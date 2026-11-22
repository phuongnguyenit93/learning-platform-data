# Eliminating Configuration Differences Between IDE, Command Line, and CI

A Java project can compile cleanly in an IDE yet fail when running `./gradlew build` or `./mvnw verify`. There are also cases where commands succeed on a developer's machine, while CI reports `UnsupportedClassVersionError`, missing dependencies, timezone-skewed test failures, or annotation processors generating different sources. When upgrading the JDK and libraries during **Java Advance Compatibility Migration**, these discrepancies are easily mistaken for compatibility bugs in Java itself.

The cause usually lies in the fact that **the three environments are not actually using the same build model**: the IDE may choose its own compiler and classpath, the terminal uses the JDK from `JAVA_HOME` or `PATH`, while CI uses a different container/JDK alongside its own environment variables, repositories, profiles, or credentials. Merely changing "Project SDK" in an IDE does not guarantee that the Gradle daemon, Maven, compile tasks, test workers, and application all use the right JDK.

The goal of this lesson is to establish a **predictable, reproducible build system**: given the same source revision, the same dependencies, and the same declared conditions, verification outcomes will match across IDE, command line, and CI; when environments intentionally differ, those differences must be explicitly declared, measured, and tested.

## 1. Getting It Right: Not Every Process Has to Use the Same JDK

A Java project can involve multiple JVMs serving different roles:

| Component | Role | Example |
|---|---|---|
| IDE runtime | JVM running the IDE itself | JVM bundled with or configured for the IDE |
| Project SDK | JDK the IDE uses to understand sources, index, and provide code completion | JDK 21 |
| Gradle daemon | JVM executing Gradle builds and plugins | JDK 21 |
| Maven runtime | JVM running Maven core and plugins | JDK 21 |
| Java compiler/toolchain | `javac` selected to compile sources | JDK 21, with `--release 17` |
| Test worker | JVM executing unit/integration tests | JDK 17 |
| Application runtime | JVM running the actual artifact | JDK 17 or 21 per support matrix |
| Annotation processor/plugin | Code running at build time with its own classpath | Depends on JDK/compiler/plugins |
| CI agent/container | Operating system and image running builds | Linux x64, specific JDK |

**Consistent configuration** does not mean "forcing everything onto the same Java version". For example, a library may intentionally use a JDK 21 compiler to produce Java 17 bytecode, then run tests on JDK 17 to confirm its minimum baseline. That is an **intentional, managed difference**, not configuration drift.

What must be eliminated is **unknown or uncontrolled differences**: an IDE running tests on JDK 21 while CI runs on JDK 17 without being stated in the build, or a machine running a newer Gradle installation simply because it did not invoke the wrapper.

## 2. A Practical "Single Source of Truth" Model

No single configuration file can hold every factor: build tools, JDKs, credentials, and test infrastructure have separate responsibilities. Instead, define the **authoritative source of declaration for each decision**.

| Decision | Where to Declare/Control It | What to Avoid |
|---|---|---|
| Gradle/Maven version | Wrapper committed into the repository | Using random global Gradle/Maven |
| JDK/compiler target | Build files, toolchains, and `--release` | Setting only the IDE Project SDK |
| Plugin versions | `settings.gradle(.kts)`, build logic, or Maven POM | Plugins picking versions based on the machine |
| Dependency versions | Build files, catalog/BOM/constraints, and locks if applied | Uncontrolled dynamic versions |
| Repositories | Standard build config and managed mirrors | Succeeding only via local Maven/Gradle caches |
| Secrets | Secret stores, CI credentials, user-local settings | Committing tokens/passwords into source |
| Profiles/variants | Named configurations and explicit selection criteria | Auto-switching behavior by user hostname |
| Test environment | Build tasks, fixtures/containers, or declared pipelines | Tests "randomly" depending on local timezone, locale, or local services |
| Deploy/runtime | Containers/IaC and managed parameters | Assuming the test JVM is identical to production |

A repository should specify the standard build commands. The IDE is recommended to **run or delegate to the standard build commands**, rather than inventing a separate compilation process with different rules.

## 3. Start by Observing What Versions Are Actually Used

When facing an "IDE passes but CI fails" error, do not edit code right away. First measure what each environment is actually executing.

In a terminal:

~~~bash
java -version
javac -version
echo "$JAVA_HOME"
~~~

In PowerShell:

~~~powershell
java -version
javac -version
$env:JAVA_HOME
Get-Command java
Get-Command javac
~~~

Check the project's build tool via the wrapper:

~~~bash
./gradlew --version
./mvnw --version
~~~

On Windows you can use `gradlew.bat` and `mvnw.cmd` depending on your terminal and project.

Do not look only at `java -version` and conclude that the compiler, Gradle daemon, and tests use that JVM. For example:

- `JAVA_HOME` points to JDK 17, while the IDE configures Gradle JVM as JDK 21.
- `PATH` prioritizes the Java 21 executable, while Maven uses `JAVA_HOME` set to JDK 17.
- Gradle toolchain selects JDK 21 for compiling, while tests use a different launcher.
- CI runs in an image with JDK 17 and does not provision toolchain 21.
- The IDE test runner executes under the Project SDK instead of going through Gradle/Maven.

Record at least: **JDK feature/update/vendor**, Gradle/Maven version, compiler target, test launcher, and the environment of the failing process.

### 3.1. A Proper Finding Must State Roles Explicitly

Instead of writing "the project uses Java 17", write:

~~~text
Build tool runtime: JDK 21 (recorded vendor/build)
JavaCompile compiler: JDK 21
javac --release: 17
Unit test launcher: JDK 17
Application minimum runtime: Java 17
CI baseline OS: Linux x64
~~~

This is an illustrative configuration, not verified parameters of any specific repository.

## 4. Using Gradle Wrapper and Maven Wrapper

A wrapper lets a repository specify how to fetch and run the build tool version rather than relying on each developer's global installation.

A Gradle project typically has:

~~~text
gradlew
gradlew.bat
gradle/wrapper/gradle-wrapper.properties
gradle/wrapper/gradle-wrapper.jar
~~~

A Maven Wrapper project typically has:

~~~text
mvnw
mvnw.cmd
.mvn/wrapper/maven-wrapper.properties
~~~

Actual files depend on the configured Maven Wrapper version/type. Do not treat missing files as an error if a project's wrapper mechanism differs from the illustrative layout; inspect the repository.

Consistent commands:

~~~bash
./gradlew clean test
./mvnw clean verify
~~~

**There is no need to run both**: pick the build tool the project actually uses.

Benefits of wrappers:

- Reduces build tool version differences between personal machines and CI.
- Ensures the repository's exact CLI is used when reproducing failures.
- Controls Gradle/Maven upgrades through reviewable commits.
- Avoids "IDE uses Gradle A while terminal uses Gradle B".
- Helps document the build entrypoint in CI.

However, a wrapper **does not automatically select the right JDK**, resolve dependency conflicts, or guarantee every plugin is compatible. Combine it with toolchains, dependency management, and testing.

### 4.1. Managing Wrapper Integrity

The wrapper is executable during builds. Review changes to wrapper scripts, wrapper binaries/configs, distribution download sources, and checksums/verification as supported by each wrapper. Use only approved distribution sources. Do not arbitrarily download wrapper binaries from unknown sources or point URLs to uncontrolled mirrors.

## 5. Gradle: Distinguishing Gradle JVM, Java Toolchain, and `--release`

In Gradle, there are at least three independent decisions:

1. **Gradle JVM:** the JDK running the Gradle daemon and plugins.
2. **Java toolchain:** the JDK selected for tasks needing a compiler/launcher.
3. **Compiler release:** language rules, class-file target, and Java SE APIs that sources are allowed to use.

Example `build.gradle.kts`:

~~~kotlin
plugins {
    java
}

java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}

tasks.withType<JavaCompile>().configureEach {
    options.release.set(17)
    options.encoding = "UTF-8"
}
~~~

In this example:

- Toolchain requests a Java 21 compiler.
- `options.release = 17` compiles sources against Java 17 and Java SE 17 APIs.
- Java artifacts compile to Java 17 class-file level, provided all relevant compile tasks are configured as intended.
- `options.encoding` reduces source reading differences across machines.
- There is no guarantee tests run on JDK 17 unless a test launcher is configured.

Do not rely solely on `sourceCompatibility = JavaVersion.VERSION_17` and `targetCompatibility = JavaVersion.VERSION_17` when the goal is preventing sources from calling Java SE 21 APIs. When supported by the compiler, `--release 17` restricts platform APIs to the target release; standalone source/target flags do not have the equivalent effect.

### 5.1. Setting the JVM for Tests

You can require tests to execute on the minimum JDK the artifact is declared to support:

~~~kotlin
tasks.withType<Test>().configureEach {
    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    )
}
~~~

A `Test` task configured like this uses the launcher selected by the Gradle toolchain. If integration test tasks use another task class or plugin, confirm whether equivalent configuration is applied.

**Do not rely on the default Gradle JVM for tests** if the team needs to verify a Java 17 runtime or run a multi-JDK test matrix.

### 5.2. Tasks Running the Application Differ from Test Tasks

`JavaExec`, `Test`, and custom plugins can pick JVMs via different mechanisms. For example, if there is a task running a Java program:

~~~kotlin
tasks.withType<JavaExec>().configureEach {
    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(17))
        }
    )
}
~~~

Apply this configuration when every `JavaExec` task genuinely must run on Java 17. If code generators or build tools require Java 21, do not apply it globally; configure the relevant tasks individually.

### 5.3. Do Not Force Everything Through `org.gradle.java.home`

`org.gradle.java.home` can select the JVM running Gradle under appropriate conditions; it **does not replace Java toolchains** and `options.release`. Committing an absolute path like `C:\Program Files\...\jdk-21` into the repository's `gradle.properties` will break on Linux/CI or other machines.

When configuring a local JDK, prefer toolchains and managed provisioning, or documented user-local settings. In CI, provision JDKs explicitly and ensure Gradle can discover/select the right JDK.

## 6. Maven: Distinguishing Maven JVM, Compiler, and Tests

Maven has similar layers:

- The wrapper sets the Maven version according to configured mechanisms.
- `JAVA_HOME` and launcher environments affect the JDK running Maven.
- Maven Compiler Plugin can use the compiler from Maven's JDK or a declared toolchain.
- Maven Surefire/Failsafe and test forks have their own Java execution selection mechanisms depending on configuration/plugins.
- Plugins generating sources, packaging, or analyzing bytecode have their own JDK requirements.

Example Maven Compiler Plugin configuration for Java 17:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <release>17</release>
                <encoding>UTF-8</encoding>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

The plugin version here illustrates a configuration; projects must choose a version from the compatibility matrix with the actual Maven/JDK in use. `release` tells the compiler to restrict language rules, class-file target, and Java SE APIs to the target release when supported.

Properties can be centralized:

~~~xml
<properties>
    <maven.compiler.release>17</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
    <project.reporting.outputEncoding>UTF-8</project.reporting.outputEncoding>
</properties>
~~~

If a JDK 21 compiler is needed while Maven's own JVM differs, use Maven Toolchains according to plugin versions and build support. Supplying `toolchains.xml` must have deployment conventions across developers and CI. **Never assume that configuring a toolchain for Compiler Plugin makes every Maven plugin and test fork use that same JDK.**

### 6.1. Maven Toolchains: Decoupling Requirements from Local Paths

Maven Toolchains allow supported plugins to pick tools such as a requested JDK rather than relying entirely on Maven's JVM. Actual toolchain configuration can reside in a user-local file specifying installed JDK locations.

For the repository:

- Document the minimum JDK/version and vendor criteria if required.
- Choose plugin versions that support toolchains and the target JDK.
- Provision JDKs in CI or document installation steps.
- Do not commit machine-specific files containing personal JDK paths or credentials.
- Check which toolchain compiler and test plugins actually use.

If a plugin does not support toolchains, it may still run inside Maven's JVM. Verify this in the pipeline rather than merely reading config files.

## 7. The IDE Must Use the Standard Build Model

IDEs offer useful features: indexing, code completion, auto-compilation, test runners, debugging, and dependency import. These are helpful, yet they can use a different classpath/JDK than Gradle or Maven.

For example, in IntelliJ IDEA, check these setting groups:

| Group | What to Verify |
|---|---|
| Project SDK and language level | Match module source and target API configurations |
| Gradle JVM | JDK running Gradle from inside the IDE |
| Gradle import/sync | Modules and dependencies come from the build definition |
| Build/run delegation | With Gradle, the IDE can delegate builds/tests to Gradle |
| Test runner | Is it using Gradle, a Maven goal, or the IDE built-in test runner? |
| Run configuration | Main class, working directory, env vars, VM args, and JDK |
| Annotation processing | Does the IDE enable processing or delegate builds properly? |
| Generated sources | Does the IDE index the exact directory generated by the build tool? |

With Maven, IDEs can import a project from POMs and run goals from the Maven tool window, yet **do not assume every "Run" button executes `mvn verify`**. When outcomes differ, compare the actual Maven command against the IDE run configuration.

Principle:

> The IDE is a development interface; the committed build definition must be the authoritative source for dependencies, compiler, code generation, and test contracts.

If the IDE's built-in compiler follows a different path than the build tool, it can help with fast feedback, but must never serve as final evidence for release artifacts.

### 7.1. Importing the Repository Properly from the Gradle/Maven Project

When opening a project, import from `settings.gradle.kts`/`build.gradle.kts` or `pom.xml` appropriately, avoiding manually creating standalone IDE modules with manually added JARs. A JAR added to the IDE classpath but missing from Gradle/Maven can make IDE compilation pass while CI fails.

If a module is not recognized cleanly by the IDE, inspect project import/sync and build definitions before adding dependencies directly in the IDE.

### 7.2. Generated Code and Annotation Processors

Lombok, MapStruct, QueryDSL, Dagger, JPA metamodels, OpenAPI generators, or other annotation processors can generate sources during builds.

Common discrepancies:

- The IDE enables a separate processor plugin while the build tool lacks the processor dependency.
- The build tool has `annotationProcessor`, while the IDE has not synced generated sources.
- The IDE generates code with a different JDK than the CLI compile task.
- A CI clean build lacks generated files that existed on a dev machine.
- Processor version is incompatible with the new compiler JDK.
- A code generator task relies on undeclared files/resources.

Configure processors and generators **in the build**, not relying on manually generated files or plugins installed only on developer machines. Required generated sources must regenerate from a clean checkout and clean CI build.

## 8. Avoiding Reliance on Local Caches and Uncommitted Files

IDEs and terminals typically run on machines with long-lived caches. CI runs in a clean checkout and thus exposes hidden dependencies:

- A JAR previously installed manually into the Maven local repository.
- An artifact cached by Gradle that is no longer in configured repositories.
- Generated sources left over from an earlier build.
- Environment config files present only on a developer machine.
- A JAR in an IDE `libs` folder not declared by the build tool.
- Test fixtures/data residing outside the repository.
- A SNAPSHOT version resolving to different artifacts in two places.
- CI needing network access while the developer is working offline.

Do not solve this by copying an entire `~/.m2/repository` or Gradle cache from a personal machine to CI as a permanent dependency source. That hides repository and provenance problems.

Use managed repositories, locked versions, and artifact verification metadata where appropriate; if private artifacts exist, ensure CI and developers authenticate under the same model.

### 8.1. Testing on a Clean Checkout

One way to verify configuration does not rely on IDE/cached files is running a build from a fresh checkout in an environment with provisioned JDK and build tools, resolving dependencies from standard repositories. This is an example of **a check to execute in real projects**, not mandatory while authoring documentation.

It is unnecessary to wipe a developer's entire Maven/Gradle cache. When suspecting cache issues, inspect the specific artifact or compare in a clean environment; wiping caches wholesale wastes time without finding the root cause.

## 9. Unifying Dependency Versions and Plugin Versions

A unified dependency graph is necessary so IDE, CLI, and CI use the same API/runtime libraries.

With Gradle, manage via:

- Version catalogs.
- Platforms/BOMs for artifact groups needing version alignment.
- Appropriate dependency constraints.
- Dependency locking when resolved versions must be reproducible.
- Dependency verification metadata or managed provenance mechanisms.

Kotlin DSL example with an explicit version:

~~~kotlin
dependencies {
    implementation("com.example:client-api:2.4.1")
}
~~~

The coordinates above are placeholders. For real dependencies, choose artifacts/versions per compatibility/support policies.

A version catalog:

~~~toml
# gradle/libs.versions.toml
[versions]
client = "2.4.1"

[libraries]
client-api = { module = "com.example:client-api", version.ref = "client" }
~~~

Putting versions in a catalog reduces duplication, yet **does not guarantee `runtimeClasspath` resolves that exact version** if constraints or transitive dependencies intervene. Inspect the actual resolved graph.

With Maven, `dependencyManagement`, BOM imports, and `pluginManagement` can manage versions. Remember:

- Dependency management does not automatically introduce a dependency if it is not declared or pulled in elsewhere.
- `pluginManagement` defines configuration/versions for plugins used via Maven mechanisms, without forcing goals to run.
- A parent POM can apply configuration through inheritance.
- Active profiles and settings can influence resolution.

Regardless of the build tool, **do not use uncontrolled "latest" versions** letting CI silently swap binaries between builds. Use version ranges/dynamic versions only with documented rationale, locking, and supporting evidence.

## 10. Maven Effective POM and Gradle Resolved Graph

When seeing the IDE and CI receive different dependencies, compare the **effective configuration**, not just a few source lines.

With Maven, helpful investigative goals:

~~~bash
./mvnw help:active-profiles
./mvnw help:effective-pom
./mvnw dependency:tree
~~~

Those commands resolve Maven Help/Dependency Plugins per the actual configuration. `effective-pom` output includes configuration from parents and profiles; take care not to leak secrets or sensitive info in reports.

With Gradle:

~~~bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight \
  --configuration runtimeClasspath \
  --dependency client-api
~~~

These commands are for **investigating inside a project**, and the configuration name must target the right module. In multi-project Gradle builds, use project paths such as `:app:dependencies`.

Good reports capture **resolved** versions, not only declared ones. A conflict or substitution rule can yield a result different from what the developer expected.

## 11. Profiles and Environment Variables: Explicit Selection Over Guessing

Maven profiles and Gradle properties help configure environments, yet they are also a source of drift.

Maven can activate profiles by:

- Explicit specification with `-P`.
- Conditions in the POM such as properties, JDK, or OS.
- User or system settings per Maven mechanisms.
- Activation rules in declared configurations.

Gradle can read project/system properties from the command line, environment, and supported `gradle.properties` locations. Configuration layers have specific precedence rules; never assume two machines share the same effective properties merely from sharing source.

Maven example specifying a profile:

~~~bash
./mvnw -P integration verify
~~~

Gradle example specifying a project-defined property:

~~~bash
./gradlew test -PtargetEnvironment=integration
~~~

`targetEnvironment` is an illustrative property; Gradle does not automatically understand or create an environment from it. Build logic must declare its meaning clearly.

### 11.1. Which Settings Should Be Defaults?

Use defaults only for settings that are **truly invariant** across environments: source encoding, compiler baselines, conventions, or test behavior independent of secrets.

Intentional differences such as test endpoints, database fixtures, integration environments, or private repositories should be declared as named profiles/properties and explicitly selected in CI.

Avoid:

~~~text
If the hostname is "dev-laptop", use mode A;
otherwise automatically pick mode B.
~~~

This creates unpredictable, hard-to-reproduce builds.

## 12. Secrets and Repository Credentials

A project may resolve dependencies on a developer machine while CI fails due to different credentials/mirrors. Do not "fix" this by committing passwords or tokens into the repository.

Principles:

- Build files declare the repository URL or a managed alias.
- Secrets come from user-local mechanisms or CI secret stores.
- CI supplies credentials with least privilege.
- Developers have documented account-setup instructions.
- Never print passwords/tokens in build logs or reports.
- Never place secrets in committed `gradle.properties` or public POMs.
- When debugging, check repository permissions, mirrors, TLS, and artifact existence while redacting credentials.

Gradle examples reading credentials from environment variables in a build script must be designed carefully around organizational models. An illustrative pattern:

~~~kotlin
repositories {
    maven {
        url = uri("https://repo.example.org/maven")
        credentials {
            username = providers.environmentVariable("REPO_USER").orNull
            password = providers.environmentVariable("REPO_PASSWORD").orNull
        }
    }
}
~~~

The URL and variable names are placeholders; use only when provided by the real environment and allowed by mechanisms. Verify plugin/Gradle versions and appropriate authorization models. Crucially, **never embed secret values directly in source**.

With Maven, credentials/mirrors are usually managed via `settings.xml` at the appropriate user/CI scope. If the server id in the POM and settings do not match, 401/403 errors can occur even when dependencies are declared correctly.

## 13. Standardizing Encoding, Locale, and Timezone

Small environment differences can cause test flakiness, especially when upgrading Java.

### 13.1. Source Encoding

With Gradle JavaCompile:

~~~kotlin
tasks.withType<JavaCompile>().configureEach {
    options.encoding = "UTF-8"
}
~~~

With Maven:

~~~xml
<properties>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

This sets the encoding for **sources** or resources/reports per the respective plugin, not a single global flag governing every I/O stream in the application.

### 13.2. Runtime Charset

On modern JDKs, UTF-8 defaults are standardized in many contexts, yet legacy code may still assume platform encoding or call file-reading APIs without specifying a charset. The durable approach is specifying the encoding explicitly at read/write sites:

~~~java
String content = java.nio.file.Files.readString(
        path,
        java.nio.charset.StandardCharsets.UTF_8);
~~~

If the application must read historical data encoded differently, declare and test the conversion rather than defaulting all legacy data to UTF-8.

### 13.3. Locale and Timezone

Example date-formatting test:

~~~java
String output = java.time.LocalDate.of(2026, 11, 12)
        .format(java.time.format.DateTimeFormatter
                .ofPattern("dd MMM yyyy", java.util.Locale.ENGLISH));
~~~

Specifying a locale keeps output independent of the machine's default language.

For real timestamps, choose `ZoneId` or `ZoneOffset` explicitly in the domain layer. Do not rely on the default timezone when business contracts require a specific zone.

In Gradle tests, a system property can be set:

~~~kotlin
tasks.withType<Test>().configureEach {
    systemProperty("user.timezone", "UTC")
}
~~~

Setting `user.timezone` reduces drift in some code paths, but does not replace proper temporal API design. If the application must support multiple timezones, run a test matrix across representative zones instead of forcing every test to UTC.

### 13.4. Clocks and Randomness

Tests calling `Instant.now()` or using unfixed random seeds can fail based on timing or execution order. For reproducibility, inject a `Clock`:

~~~java
Clock fixed = Clock.fixed(
        Instant.parse("2026-11-12T00:00:00Z"),
        ZoneOffset.UTC);
~~~

`Clock`, `Instant`, and `ZoneOffset` belong to `java.time`. Tests must ensure the class under test actually uses the injected clock rather than calling the system clock directly.

## 14. Working Directory, Paths, and Operating System

An IDE might launch the application with the working directory in a submodule, a terminal from the repository root, and CI from another workspace. Code using relative paths such as:

~~~java
Path file = Path.of("config/application.properties");
~~~

may read a different file or fail to find the file.

For application configs/resources, prefer explicit packaging:

~~~java
try (InputStream stream =
         MyApp.class.getResourceAsStream("/application.properties")) {
    if (stream == null) {
        throw new IllegalStateException("Resource not found");
    }
    // Read the resource.
}
~~~

Not every config file belongs inside a JAR: external config, certificates, or secrets require paths supplied by the environment. What matters is that **paths and ownership are defined**, not dependent by chance on an IDE working directory.

OS differences to watch for:

- Classpath separators: `:` on Unix and `;` on Windows.
- Shell quoting and how environment variables are passed.
- Case-sensitive paths on certain filesystems.
- Line endings, file permissions, and wrapper executable bits.
- Default locale/timezone.
- Native libraries and OS architecture.
- Path length limits and special characters in directory names.

CI may run Linux while developers use Windows. For projects supporting both, run a matrix or at least test relevant file-handling and native code on each OS.

## 15. Distinguishing Compile/Test/Package Between IDE and Build Tools

An IDE "Build Project" button may not equate to:

~~~bash
./gradlew clean build
~~~

nor does it necessarily equate to:

~~~bash
./mvnw clean verify
~~~

In Gradle, `build` depends on configured tasks and plugins; in Maven, `verify` executes lifecycle phases along with bound plugins. Custom tests may not be wired into the standard lifecycle unless the team declares them.

Therefore, to ensure CI runs all needed tests:

- Define the standard release build task/goal.
- Ensure necessary integration test or verification tasks are wired into the pipeline.
- Document commands used by developers and CI.
- Have the IDE run the same Gradle/Maven tasks/goals when confirming results.
- Clarify which tasks an IDE may run separately for debugging without substituting for full verification.

For example, an `integrationTest` task in Gradle **does not exist by default** in every project. Only document that command if the build defines that task.

## 16. Test Framework Configuration and Engine Discovery

An IDE may run JUnit tests using its own runner while CLI finds none due to a missing test engine, plugin, or task configuration.

In the Gradle Java plugin, configuring the appropriate JUnit platform may be required:

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
}
~~~

At the same time, JUnit API and engine dependencies must be managed according to the versions chosen by the project. Writing `useJUnitPlatform()` alone does not automatically add every required library.

With Maven, test discovery/execution can depend on Maven Surefire/Failsafe versions/configs, test naming, and the corresponding JUnit/Jupiter engine. When tests pass in the IDE yet `./mvnw test` reports "0 tests", investigate test discovery before concluding tests passed.

Test reports should state the actual count of executed tests. **Zero executed tests is not evidence of a functionally passing test suite.**

## 17. Mirroring CI Locally Without Assuming Exact Parity with Production

A good CI environment has these traits:

- Clean checkout at an exact commit.
- Pinned wrapper/build tool.
- JDKs provisioned per a declared matrix.
- Repository access and secrets supplied explicitly.
- Managed test environment units.
- No dependence on IDEs or user-local files.
- Logs and artifact reports.
- Separation between test jobs, packaging jobs, and deploy jobs.

Locally, developers can run **CI-like commands** to reproduce many failures:

~~~bash
./gradlew clean test
~~~

or:

~~~bash
./mvnw clean verify
~~~

However, local and CI do not need every service identical to production. Elements such as database servers, external APIs, queues, or TLS endpoints require test containers, dedicated integration environments, or mocks with clear contracts.

Do not require every developer to maintain full production infrastructure locally. Instead, define **which test sets run locally**, **which test sets need CI infrastructure**, and what each set proves.

## 18. Sample Verification-Driven CI Pipeline

A vendor-independent pipeline can include:

~~~text
Checkout commit
    |
Provision JDK/build-tool prerequisites
    |
Use committed Gradle/Maven wrapper
    |
Resolve and verify dependencies
    |
Compile and run unit tests
    |
Run contract/integration tests
    |
Test minimum supported Java runtime
    |
Package and inspect artifact
    |
Archive logs, reports, dependency and JDK metadata
    |
Promote only when gates pass
~~~

Not every step must reside in a single job. If there are multiple JDKs or operating systems, use an appropriate matrix:

| Job | Compiler/Build JDK | Runtime Test JDK | Purpose |
|---|---|---|---|
| Compile | 21 | — | Compile with `--release 17` |
| Baseline runtime | 21 or per build | 17 | Confirm artifact runs on minimum Java |
| Current runtime | 21 or per build | 21 | Verify behavior on the other target JDK |
| Integration | Selected JDK | 17/21 per support | JDBC, HTTP, framework, and serializers |
| Platform-specific | Per build | Per environment | Verify file/native/network behavior |

This is an example matrix, not a directive to use JDK 17/21 for every project. If an application supports only Java 21, Java 17 tests are not required. If a product supports multiple JDKs, define a representative set and coverage boundaries.

### 18.1. Never Treat CI Cache as a Source of Truth

CI caching can speed up builds, yet should not cause pipeline artifacts to vary based on cache history. Dependency versions must be determined by the declared build and repositories, with caching serving strictly as a controlled acceleration layer.

Periodically run clean resolution/build checks and use proper invalidation mechanisms. If CI succeeds only with cache while clean CI fails, that is a reproducibility bug to fix.

## 19. Managing Integration Test Environments

Many discrepancies between IDE/CLI/CI come from databases, message brokers, or external services.

Examples:

- IDE connects to a local database with schema S1.
- CLI uses an environment variable pointing to schema S2.
- CI spins up a database in a container yet misses migrations.
- Test data on a personal machine has special records absent in CI.
- Server timezone or collation differs.
- Local credentials have higher privileges than the CI account.

Remediation steps:

1. Record database/service versions and actual effective configuration.
2. Create schemas via version-controlled migration scripts.
3. Use independent, resettable fixtures free of developer-local data.
4. Manage container images/digests or test environments under a reproducibility policy.
5. Isolate endpoints/credentials via environment variables or secret stores.
6. Test negative cases, timeouts, authorization errors, and network failures.
7. Ensure integration tests fail clearly when a service is unavailable rather than silently skipping.

If a test uses a real service, ensure it cannot affect production data. Use dedicated test environments and least-privilege accounts.

## 20. JPMS, `--add-opens`, and VM Arguments

During Java migrations, older frameworks can hit `InaccessibleObjectException` when using deep reflection into internal packages or DTOs in named modules.

One cause of "IDE passes, CI fails" is an IDE run configuration adding:

~~~text
--add-opens=java.base/java.lang=ALL-UNNAMED
~~~

while CLI/CI lack it. However, copying that flag everywhere is not automatically the right fix.

To handle it:

- Read source module/package and target module from the exception.
- Identify which library is calling `setAccessible`.
- Prefer upgrading the framework or moving to supported public APIs.
- If the module belongs to the project, intentionally use `opens package to framework.module`.
- Use `--add-opens` only as a narrow workaround with an owner and removal plan.
- Specify which JVM needs the flag: Gradle daemon, test worker, or application runtime.

If tests temporarily need the flag in Gradle, configure the right task:

~~~kotlin
tasks.withType<Test>().configureEach {
    jvmArgs("--add-opens=java.base/java.lang=ALL-UNNAMED")
}
~~~

This configuration does not propagate automatically to `JavaExec` or production containers. When CI/tests fail, pinpoint which JVM failed. Avoid setting a global `JAVA_TOOL_OPTIONS` variable opening access across all processes when only one library needs fixing.

## 21. TLS and Truststore Differences

An application using HTTPS/database TLS may fail only in CI:

~~~text
javax.net.ssl.SSLHandshakeException:
PKIX path building failed
~~~

This may happen because:

- CI uses a different JDK distribution/truststore than local.
- The container lacks internal CAs already installed on developer machines.
- Endpoints traverse different proxies or DNS.
- The URL hostname does not match the certificate SAN.
- The certificate lacks an intermediate chain or has expired.
- A JDK update/build has different security algorithm constraints.

Do not fix this with a TrustManager that accepts all certificates or by disabling hostname verification. The right fix is verifying the chain, CA, DNS, endpoint, and environment truststore per organizational policy.

In test records, log the **truststore/CA type** and managed path, never passwords, private keys, or tokens. If CI needs internal certificates, provision them through proper security mechanisms rather than relying on manual steps on personal machines.

## 22. Maven/Gradle Plugins and Build Logic Varying Across Environments

Besides runtime dependencies, build plugins can cause drift:

- Gradle plugins or Maven plugins resolve to different versions.
- A profile activates only on a specific JDK/OS.
- A plugin accesses JDK internals and fails on a newer JDK.
- Build scripts invoke files or commands present only on developer machines.
- Code generation plugins do not run in the CI lifecycle.
- A task relies on an undeclared environment variable.
- Scripts depend on current wall-clock time or filesystem ordering.
- Build cache masks missing input/output declarations.

Approach:

1. Pin build tool and plugin versions.
2. Define task dependencies and inputs/outputs clearly.
3. Ensure generated sources can build from a clean checkout.
4. Verify the runtime JDK of each plugin.
5. Review profile activations and system properties.
6. When debugging, run builds with appropriate logging while redacting secrets.
7. If failures happen only on incremental builds, compare with a clean build to isolate caching.

Do not work around faulty task input/output declarations by enabling `clean` on every task forever; the build logic itself may need fixing.

## 23. Common Failure Symptoms and How to Isolate Them

| Symptom | Likely Cause | Verification Direction |
|---|---|---|
| IDE compiles, Gradle CLI fails | IDE uses different JDK/classpath; not synced | Compare Project SDK, Gradle JVM, toolchain, and resolved graph |
| Local CLI passes, CI `invalid source release` | CI compiler older than configured release | Record `javac -version` and compiler toolchain |
| CI `UnsupportedClassVersionError` | Runtime older than bytecode or dependency | Check class-file version and test worker JDK |
| Local Maven passes, CI misses artifacts | Manual JAR in local repo; different mirror/credentials | Check repos, settings, dependency tree, and clean resolution |
| IDE tests pass, Maven reports 0 tests | Different test runner/engine/plugin discovery | Check Surefire/Failsafe, JUnit engine, and reports |
| Gradle tests fail due to timezone | JVM `user.timezone` or tests relying on defaults | Define temporal contracts and test zones explicitly |
| CI codegen misses classes | Generated sources not produced by build | Check annotation processors and task dependencies |
| CI tests throw `InaccessibleObjectException` | Different JDK/framework and module openness | Stack trace, dependency version, exact test JVM |
| CI TLS handshake fails | Different truststore/CA/hostname/proxy | Certificate chain and JDK security config |
| JDBC `getObject` results differ | Different driver/server/session settings | Check mapping, driver version, timezone, fixtures |
| Local defaults differ from CI | Different profiles/environment activation or precedence | Print effective config with secrets redacted |
| Artifact checksums differ | Non-reproducible inputs, timestamp metadata, dependency drift | Compare build inputs and reproducible packaging |

This table is an investigation guide; a single failure may have multiple causes. Gather evidence before modifying build setup or code.

## 24. Investigation Workflow When IDE, CLI, and CI Produce Different Results

### Step 1: Record Three Runs on the Same Commit

Confirm IDE, terminal, and CI use the same source revision. If one environment has not synced the branch or holds uncommitted files, they cannot be compared as the same build.

### Step 2: Record Command Lines and JVM Roles

State the exact task/goal invoked, the JDK running the build tool, compiler/toolchain, test launcher, VM args, working directory, OS, and environment. Do not merely write "Java 21".

### Step 3: Compare Effective Configurations

Inspect the Gradle resolved graph or Maven effective POM/active profiles; compare dependency versions, repositories, and plugin versions. Do not guess from isolated POM/`build.gradle` snippets.

### Step 4: Separate Build Errors from Runtime Errors

If compilation fails, check source, target, release, and compiler classpath. If class loading fails, check runtime JDK, dependencies, and class-file versions. If test behavior diverges, check data, timezone, locale, network, and framework settings.

### Step 5: Reproduce with the Wrapper

Run the repository's standard command from a terminal or a CI-like environment. If the IDE runner differs, try delegating tasks/goals to the build tool to pinpoint where the discrepancy sits.

### Step 6: Narrow the Change

Do not swap JDK, plugins, and dependencies wholesale just to "try things". Isolate the smallest change that reproduces the bug: one module, one test, one dependency, or one JVM flag.

### Step 7: Fix at the Authoritative Declaration Source

Examples:

- Wrong JDK/compiler → fix toolchain or CI provisioning.
- Wrong dependency → fix build dependency/constraints.
- Wrong test runner → fix build test plugin/task.
- Wrong timezone → fix temporal contract and test configuration.
- Wrong certificate → fix environment truststore/endpoint.
- Disallowed reflection → upgrade framework or open package in a controlled way.

Do not patch only IDE-local settings if the flaw belongs to the build definition and every developer/CI requires that rule.

### Step 8: Re-Run Equivalence Checks

Execute the defined build/test commands across all three relevant environments, recording results and limitations. If CI runs deeper tests than local, still distinguish "unit-level equivalence" from "full-pipeline equivalence".

### Step 9: Update Documentation and Guardrails

After fixing, commit repository configuration; update setup guides, version requirements, profile selection, and the CI matrix. Add tests or simple checks so configuration drift does not recur.

## 25. Environment Evidence Record Template

A record can help compare multiple runs:

~~~yaml
buildEvidence:
  commit: "example-commit-id"
  tool:
    name: "Gradle"
    wrapperVersion: "record actual version"
  compile:
    compilerJdk: "21"
    javaRelease: "17"
    sourceEncoding: "UTF-8"
  tests:
    runtimeJdk: "17"
    timezone: "UTC"
    locale: "record required locale"
  dependencyGraph:
    reference: "archived report path"
  environment:
    os: "linux-x64"
    ciImageDigest: "record exact image digest"
  results:
    compilation: "PASS"
    unitTests: "PASS"
    integrationTests: "NOT_RUN"
  limitations:
    - "windows-runtime-not-tested"
    - "external-plugin-consumers-not-covered"
~~~

This is illustrative data, not actual test results that took place. When applying it, save timestamps, JDK vendor/build, resolved dependency checksums, test reports, artifact digests, and genuinely meaningful environment fields.

To prevent information leaks, do not dump raw environment variables or Maven settings containing secrets into reports. Record only required variable/config names and non-sensitive values.

## 26. Designing Guardrails So Configuration Does Not Drift Again

Once environments are aligned, turn critical assumptions into automated checks:

| Constraint | Suggested Guardrail |
|---|---|
| Build tool version | Mandatory wrapper in docs/pipelines |
| Compiler release | Centralized `--release` config and compile tests |
| Minimum test JDK | CI job running on the exact JDK baseline |
| Dependency consistency | Locking/verification and resolved graph reports when needed |
| Test discovery | Check executed test count and loaded test engine |
| Generated sources | Clean checkout builds and declared task dependencies |
| Encoding/timezone | Explicit config in builds and test fixtures |
| Profiles | Pipelines select profiles by name, not hostname |
| Private repositories | Clear secret stores and permissions; check 401/403 |
| Artifact identity | Record digest, commit, and dependency metadata |
| Module/JVM flags | Restrict VM args and review workarounds |
| Compatibility contracts | Unit, integration, and consumer tests based on risk |

A guardrail must verify real conditions. For example, `./gradlew test` returning exit code 0 while **zero tests ran** fails the goal of "the test suite ran properly".

## 27. Maven and Gradle: Similarities and Differences When Syncing All Three Environments

| Concern | Gradle | Maven |
|---|---|---|
| Standard entrypoint | `gradlew` / `gradlew.bat` | `mvnw` / `mvnw.cmd` |
| Compiler target | `JavaCompile.options.release` | Maven Compiler Plugin `release` |
| JDK selection | Java toolchains, daemon JVM, and task launchers | Maven runtime, Maven Toolchains, and plugin support |
| Dependency versions | Catalogs, constraints, platform/BOM, locking | Dependency management, BOMs, POM hierarchy |
| Plugin versions | Plugin management/build logic | Plugins, pluginManagement, and parent POM |
| Variant config | Properties, tasks, source sets, build logic | Profiles, properties, lifecycle/plugin bindings |
| Test execution | Gradle Test task/JUnit platform, custom tasks | Surefire/Failsafe and test engines |
| Dependency investigation | `dependencies`, `dependencyInsight` | `dependency:tree`, `help:effective-pom` |
| IDE drift points | IDE JDK, Gradle JVM, delegated vs IDE runner | Maven runtime, active profiles, IDE runner, and import |

It is not necessary to switch between Maven and Gradle to eliminate drift. Builds can be reproducible with either tool when properly designed and managed. Only change build tools with independent justification, as that is itself a major change requiring testing.

## 28. Common Misconceptions

**"The IDE Project SDK is Java 21, so CI must also be Java 21."** No. CI uses its own JDK; Gradle/Maven have separate JVMs, toolchains, and test launchers.

**"The wrapper eliminates every difference."** The wrapper pins the build tool, not every JDK, dependency, secret, OS, and test environment.

**"Setting `sourceCompatibility = 17` suffices to prevent using new APIs."** Not completely. When supported by the compiler, `--release 17` is required to restrict Java SE APIs.

**"Gradle toolchain Java 21 means tests run on Java 21."** The test launcher can be configured separately; never guess.

**"Maven `<release>17</release>` means production runs Java 17."** That is compiler configuration; it does not pick the deployment runtime.

**"The IDE has the Lombok plugin, so annotation processors surely run on CI."** IDE plugins do not replace build-time annotation processor dependencies/configuration.

**"A test passing in the IDE proves `mvn verify` or `gradle build` passes."** Runners, JDKs, classpaths, and lifecycles can all differ.

**"If the local dependency cache has the artifact, repository config is fine."** Clean CI environments may still fail to resolve that artifact.

**"Setting `user.timezone=UTC` fixes all time bugs."** No. Temporal data needs correct semantics; test other timezones if contracts require them.

**"We can copy developers' entire `gradle.properties` and `settings.xml` to CI."** That can leak secrets or embed local paths; separate public config from credentials.

**"`--add-opens` is in the IDE, so put it in production too."** Identify the root cause, the exact JVM, flag scope, and a long-term fix.

**"A green CI build means the artifact works on every supported JVM."** Runtime tests are needed on the minimum JDK and declared environments.

**"OS/JDK must be 100% identical for tests to be valid."** Not always possible; document intentional differences and run a matrix sufficient to back conclusions.

## 29. Implementation Checklist for the Project

- [ ] Identified primary build tool and committed wrapper with trusted download sources.
- [ ] Confirmed IDE, CLI, and CI use the same commit and build definition.
- [ ] Recorded runtime JDKs for IDE, Gradle/Maven, compiler, tests, and application.
- [ ] Configured compiler release/source target per supported Java baseline.
- [ ] Provisioned Java toolchains or Maven compiler/toolchains at exact versions.
- [ ] Configured test runners and test JVMs, and confirmed tests actually execute.
- [ ] Brought annotation processors, generated sources, and code generators into the build.
- [ ] Managed dependency versions, plugin versions, and repositories via shared configuration.
- [ ] Inspected resolved graphs, profiles, and effective configuration.
- [ ] Eliminated dependencies existing only in IDE or local caches.
- [ ] Defined working directory, external configs, and resource paths explicitly.
- [ ] Controlled UTF-8, timezone, locale, clocks, and test fixtures.
- [ ] Separated secrets from the repository, using proper credential stores for developers and CI.
- [ ] Checked TLS/truststores and module/JVM flags without arbitrarily weakening security.
- [ ] Defined which tests run locally vs which tests require CI infrastructure.
- [ ] Ran clean builds in a reproducible environment and saved reports.
- [ ] Established a CI JDK/OS matrix per support policy and resource constraints.
- [ ] Saved commit, artifact digests, test results, and untested scopes.
- [ ] Added guardrails to prevent configuration drift from recurring after migration.

## Conclusion

**Eliminating configuration differences between IDE, command line, and CI** does not mean forcing every process onto one JVM or one interface. It means turning key decisions into authoritative, version-controlled, verifiable configuration: wrappers for build tools, compiler `--release` and toolchains for Java, dependency management for artifacts, tasks/goals for testing, and CI provisioning for environments.

During Java Advance Compatibility Migration, treat the IDE as one way to invoke the standard build, not as an independent configuration source. Verify every JVM role, resolved graph, profile, generated source, encoding, timezone, repository, and security setting; then prove equivalence via builds/tests on the same commit with traceable logs and artifacts. Intentional differences between compiler, test JDK, and production runtime remain valid when documented and explicitly verified. The ultimate goal is: **a Java or dependency change yields explainable, reproducible, safely deployable results — regardless of whether execution started from an IDE, terminal, or CI pipeline.**
