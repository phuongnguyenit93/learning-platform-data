# Running Tests Consistently Across IDE and Build Tools

A Spring test may pass in the IDE yet fail when executed with Gradle or Maven on another machine. A test may also pass on a developer's machine and fail in CI. These differences usually stem from how the test is launched: different JDKs, different runners, mismatched profiles or environment variables, different working directories, different test filters, or different parallelism and JVM fork configurations.

The goal of consistent test execution is to ensure the same test receives the same dependencies, configuration, resources, and execution conditions whether launched from an IDE, a terminal, or CI. The build tool should serve as the reproducible source of configuration; the IDE needs to sync the project with the build tool and use the same JDK, classpath, profiles, system properties, and test filters.

Not every discrepancy between an IDE and a build tool is a Spring bug. The IDE may use its own JUnit runner, whereas Gradle or Maven runs JUnit Platform inside a JVM managed by the build tool. Accurate diagnosis requires knowing which runner executed the test and what configuration was passed to the test process.

## 1. Why Can the Same Test Produce Different Results?

A Spring test depends on many factors outside the body of the test method:

| Factor | Possible discrepancy |
|---|---|
| JDK | IDE uses JDK 21 while the Gradle daemon or Maven uses JDK 17 |
| Test runner | IDE runs directly via a JUnit runner; the build tool runs via JUnit Platform |
| Dependencies | IDE has not synced the latest versions from Maven/Gradle |
| Profile | IDE sets spring.profiles.active=test; terminal does not pass the profile |
| Environment variables | Run configuration has a test API URL that the shell lacks |
| System properties | IDE passes user.timezone or spring.*; the build tool does not |
| Working directory | IDE runs from a submodule; the build tool runs from the root project |
| Test discovery | IDE finds the method; Surefire/Failsafe or a Gradle filter does not select that class |
| Parallel/fork | IDE runs sequentially in one JVM; CI runs multiple workers or forks |
| External resources | Docker is available locally but missing in CI; ports or services differ |
| Test order | Test depends on state created by an earlier test |

When results differ, do not immediately change assertions or add sleeps. Compare the environment and actual launch command first. A stable test must set up the conditions it needs itself and must not rely on accidental IDE state.

## 2. Make the Build Tool the Primary Source of Configuration

The IDE is where you write, run individual tests, and debug. Gradle or Maven describes dependencies, source sets, test engines, JVMs, system properties, tasks, and lifecycle. CI should execute using the project's own wrapper to ensure the exact build tool version.

With Gradle:

~~~bash
./gradlew test
~~~

On Windows:

~~~powershell
.\gradlew.bat test
~~~

With Maven:

~~~bash
./mvnw test
~~~

On Windows:

~~~powershell
.\mvnw.cmd test
~~~

Wrappers ensure developers and CI use the Gradle or Maven version declared by the project. Avoid requiring every machine to install a separate global version and expecting identical results.

In the IDE, import the project from build.gradle or pom.xml, sync dependencies, and configure the runner based on the build tool. When the IDE lets you choose between its internal runner and the Gradle/Maven runner, use the build tool runner when you need to reproduce CI behavior accurately. The internal runner remains useful for quick debugging, but keep in mind it may use different discovery rules or a different JVM.

## 3. Sync the JDK Across IDE, Build Tool, and Test JVM

A project may have multiple JDK choices:

- The IDE or Project SDK JDK.
- The JDK running the Gradle daemon or Maven process.
- The Java toolchain used to compile sources.
- The JVM running test workers or forks.
- The CI runner's JDK.

These values are not automatically identical. For example, the IDE may have Project SDK 21 while the Gradle JVM is still 17; the build may compile with toolchain 21 while the test task is configured to fork with a different executable.

### 3.1. Declare a Java Toolchain in Gradle

With Gradle, use a toolchain to describe the Java version the project requires:

~~~kotlin
java {
    toolchain {
        languageVersion.set(JavaLanguageVersion.of(21))
    }
}
~~~

Test tasks can use a launcher from the toolchain:

~~~kotlin
tasks.withType<Test>().configureEach {
    useJUnitPlatform()
    javaLauncher.set(
        javaToolchains.launcherFor {
            languageVersion.set(JavaLanguageVersion.of(21))
        }
    )
}
~~~

Toolchains let Gradle pick the appropriate JDK for compilation and testing. The build machine still needs an appropriate JDK installed or must be configured so Gradle can download the toolchain according to project policy.

### 3.2. Declare the Java Release in Maven

With the Maven Compiler Plugin, you can declare release:

~~~xml
<properties>
    <maven.compiler.release>21</maven.compiler.release>
    <project.build.sourceEncoding>UTF-8</project.build.sourceEncoding>
</properties>
~~~

The maven.compiler.release property controls the target Java language level and APIs during compilation. It does not by itself guarantee that every Maven process or test fork runs with the same JDK. If the project uses the Maven Toolchains Plugin, configure toolchains to select the specific JDK for the compiler and related plugins.

### 3.3. Verify the Actual JDK

When suspecting environment differences, record:

~~~bash
java -version
./gradlew -version
./mvnw -version
~~~

In tests, you can inspect the runtime version with System.getProperty("java.version"). Only assert on the version if it is a project requirement; ordinarily, logging the runtime in the build aids diagnosis without coupling tests too tightly to patch versions.

The IDE should point Project SDK and the Gradle JVM/Maven runner JRE to configurations compatible with the toolchain. If different JDKs are used intentionally, ensure those versions are within the project's support matrix.

## 4. Use the Same JUnit Platform and Test Engine

Spring Framework testing commonly uses JUnit Jupiter. JUnit Platform is the discovery and execution foundation for engines; Jupiter is an engine running on that platform.

In Gradle, enable JUnit Platform for test tasks:

~~~kotlin
dependencies {
    testImplementation("org.junit.jupiter:junit-jupiter")
}

tasks.test {
    useJUnitPlatform()
}
~~~

With Spring Boot, dependency management can supply compatible JUnit versions via the test starter. Avoid declaring incompatible versions of JUnit Platform, Jupiter API, and engines without a specific reason.

In Maven, configure a Surefire version compatible with JUnit Platform and the corresponding engine dependencies. Example plugin configuration:

~~~xml
<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-surefire-plugin</artifactId>
            <version>3.5.2</version>
        </plugin>
    </plugins>
</build>
~~~

The version number above is an illustrative example; projects should use the version managed by the Spring Boot BOM or internal plugin policy. What matters is that Surefire supports JUnit Platform and the classpath contains the Jupiter engine. If using JUnit 4, include the appropriate engine or provider; do not mix JUnit 4 and Jupiter configurations inadvertently.

If the IDE runs tests but Maven/Gradle reports no tests found, check the engine, dependency scopes, test source directories, and class names. The IDE can run a class directly even when Surefire/Failsafe does not select that class based on its include patterns.

## 5. Sync Test Discovery

A test only runs when the runner discovers the class and method. File naming conventions, source directories, and filters can vary between build tools.

### 5.1. Gradle

Gradle by default runs compiled tests in the test source set and uses JUnit Platform when useJUnitPlatform() is configured. You can run an individual class or method:

~~~bash
./gradlew test --tests "com.example.order.OrderServiceTest"
./gradlew test --tests "com.example.order.OrderServiceTest.createsOrder"
~~~

With a separate integration test task, you must invoke that specific task, for example:

~~~bash
./gradlew integrationTest
~~~

If a project creates a separate integrationTest source set and task, that task may not be part of the default test task. Inspect the task graph and check configuration to see whether integration tests run in CI.

### 5.2. Maven Surefire and Failsafe

Maven Surefire usually runs unit tests during the test phase. Default include conventions typically match names such as Test*, *Test, *Tests, and *TestCase. A class named OrderServiceSpec may run in the IDE but go undiscovered by Surefire unless suitable includes are configured.

Running a single class:

~~~bash
./mvnw -Dtest=OrderServiceTest test
~~~

Maven Failsafe is typically meant for integration tests named IT*, *IT, or *ITCase. Run through the lifecycle so Failsafe executes both integration-test and verify:

~~~bash
./mvnw verify
~~~

Invoking only integration-test while skipping verify can bypass result aggregation or failure checks that the plugin performs at the end of the lifecycle. Use verify as the standard entry point for Maven integration tests.

### 5.3. Class Names and Source Sets Must Be Clear

Follow consistent naming conventions:

- OrderServiceTest for unit or slice tests.
- OrderRepositoryIT or OrderWorkflowIT for integration tests if the build tool is configured accordingly.

Names are only a convention; plugin/task configuration actually determines which tests run. Do not rely on the IDE showing a green play icon to conclude that CI will pick up that class as well.

## 6. Sync Spring Profiles and Test Configuration

Spring Boot can load configuration by profile. A test running in the IDE with the test profile but run from the terminal without a profile may connect to the wrong database or use unintended configuration.

You can specify the profile on the test:

~~~java
@SpringBootTest
@ActiveProfiles("test")
class OrderServiceIntegrationTest {
}
~~~

For tests needing dedicated configuration, place an application-test.yml file in src/test/resources:

~~~yaml
spring:
  datasource:
    url: jdbc:h2:mem:orders-test;DB_CLOSE_DELAY=-1
  jpa:
    hibernate:
      ddl-auto: create-drop
~~~

This is only an example of a test database configuration; if you need to test the production dialect, use the corresponding database rather than H2.

ActiveProfiles("test") makes the profile explicit in the test class and less dependent on IDE Run Configurations. Profiles can also be passed via system properties or environment variables when running the same suite under multiple configurations:

~~~bash
./gradlew test -Dspring.profiles.active=test
./mvnw -Dspring.profiles.active=test test
~~~

However, do not let critical tests work only when a developer remembers to enter a profile manually. Put mandatory configuration in test annotations or version-controlled build configuration.

### 6.1. Property Source Precedence

Spring Boot has multiple property sources and a precedence order. Test properties, @DynamicPropertySource, system properties, environment variables, and configuration files can override one another according to Spring Boot's rules. When IDE and CI results diverge, inspect the actual resolved properties rather than reading only one YAML file.

For dynamic dependencies such as Testcontainers, @DynamicPropertySource is suitable for registering the URL, username, and password from a running container:

~~~java
@DynamicPropertySource
static void databaseProperties(DynamicPropertyRegistry registry) {
    registry.add("spring.datasource.url", postgres::getJdbcUrl);
    registry.add("spring.datasource.username", postgres::getUsername);
    registry.add("spring.datasource.password", postgres::getPassword);
}
~~~

This avoids hardcoding random ports or assuming the container always runs at the same address.

## 7. Sync Environment Variables and System Properties

The IDE can store environment variables in a Run Configuration. The terminal and CI need equivalent variables set. For example:

~~~text
SPRING_PROFILES_ACTIVE=test
PAYMENT_API_URL=http://localhost:9090
FEATURE_NEW_CHECKOUT=false
~~~

Variables required by tests can be declared in build configuration or test configuration files. Never put real secrets into the repository. Use dummy values, fake services, or the CI secret store as appropriate.

Gradle can pass system properties to the test JVM:

~~~kotlin
tasks.withType<Test>().configureEach {
    systemProperty("user.timezone", "UTC")
    systemProperty("user.language", "en")
}
~~~

Maven Surefire can pass system properties:

~~~xml
<plugin>
    <groupId>org.apache.maven.plugins</groupId>
    <artifactId>maven-surefire-plugin</artifactId>
    <configuration>
        <systemPropertyVariables>
            <user.timezone>UTC</user.timezone>
            <user.language>en</user.language>
        </systemPropertyVariables>
    </configuration>
</plugin>
~~~

Only fix locale or timezone when tests require deterministic behavior under one standard. If the product must support multiple locales/timezones, write parameterized tests for those cases instead of assuming the whole system always runs in UTC.

Do not read secrets from a developer machine and make tests depend on them. Automated tests must use non-sensitive configuration and be able to run in a clean CI environment.

## 8. Working Directory and Test Resources

The IDE may set the working directory to a module or project directory; Gradle/Maven typically runs tasks with the project/module working directory. If a test reads a file via a relative path like new File("src/test/resources/data.json"), results can differ between runners.

Prefer reading resources from the classpath:

~~~java
ClassPathResource resource =
        new ClassPathResource("fixtures/orders/valid-order.json");

try (InputStream input = resource.getInputStream()) {
    String json = new String(
            input.readAllBytes(),
            StandardCharsets.UTF_8);
}
~~~

Place fixtures in src/test/resources or a build-declared test resource directory. Classpath resources work more reliably than paths dependent on the working directory.

For files created during tests, use JUnit @TempDir:

~~~java
@Test
void writesExport(@TempDir Path tempDir) throws IOException {
    Path output = tempDir.resolve("export.json");
    // Write and read files in the test's temporary directory.
}
~~~

Do not write fixtures or test outputs into shared source directories. Parallel tests can overwrite each other's files if they use the same filenames or fixed directories.

## 9. Sync Dependencies and Plugins

The IDE may hold an outdated project model if Maven/Gradle has not been reloaded. When dependencies change, the internal runner might use a different classpath than the build tool.

Steps when encountering ClassNotFoundException, NoSuchMethodError, or differing JUnit behavior:

1. Reload the Gradle or Maven project in the IDE.
2. Inspect the build tool's dependency tree.
3. Verify the test runtime has the expected JUnit engine and Spring Test versions.
4. Check whether the BOM or dependency constraints manage versions consistently.
5. Run tests via the wrapper to determine if the failure reproduces outside the IDE.

With Gradle, you can inspect a specific dependency:

~~~bash
./gradlew dependencyInsight --dependency junit-jupiter-engine --configuration testRuntimeClasspath
~~~

With Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.junit.jupiter,org.junit.platform
~~~

Do not add a standalone JUnit version just to silence an IDE warning if the Spring Boot BOM manages a compatible set of versions. Dependency changes must be based on the dependency graph and the actual Spring/Boot versions.

## 10. Sync Test Filters, Tags, and Test Groups

JUnit Jupiter supports @Tag for categorization:

~~~java
@Tag("integration")
@SpringBootTest
class OrderWorkflowIT {
}
~~~

Gradle can filter tags via JUnit Platform configuration:

~~~kotlin
tasks.test {
    useJUnitPlatform {
        excludeTags("integration")
    }
}

tasks.register<Test>("integrationTest") {
    useJUnitPlatform {
        includeTags("integration")
    }
    testClassesDirs = sourceSets["test"].output.classesDirs
    classpath = sourceSets["test"].runtimeClasspath
}
~~~

This is an illustrative configuration skeleton; a project may use a separate source set for integration tests and require corresponding task relationships, dependencies, or output directories.

With Maven Surefire/Failsafe, groups/tags can be configured according to the JUnit Platform provider the plugin uses. For example:

~~~xml
<configuration>
    <groups>integration</groups>
</configuration>
~~~

Check the project's actual plugin and engine configuration before copying. The same tag can be handled differently if the IDE, Surefire, and Gradle have different filter configurations.

In the IDE, running a specific method or class often bypasses some build task filters. When you need to reproduce CI, run the corresponding task/tag filter via the wrapper.

## 11. Parallel Execution, JVM Forking, and Test Isolation

IDEs often run a test class in a single process or IDE-managed runner. Build tools can run multiple test workers, multiple JVM forks, or multiple tasks concurrently.

With Gradle:

~~~kotlin
tasks.withType<Test>().configureEach {
    maxParallelForks = 1
}
~~~

A value of 1 keeps the task's fork count at one. Once tests are independent and thread-safe, you can increase maxParallelForks to shorten run times. Distinguish between Gradle's JVM forks and JUnit Jupiter's parallel execution within a single JVM; these are two separate configuration layers.

JUnit Jupiter can enable parallel execution via junit-platform.properties in test resources:

~~~properties
junit.jupiter.execution.parallel.enabled=true
junit.jupiter.execution.parallel.mode.default=concurrent
junit.jupiter.execution.parallel.mode.classes.default=same_thread
~~~

Only enable parallelism when tests share no mutable state or already have proper locking mechanisms. Tests sharing database records, system properties, fixed files, mutable singleton beans, or shared executors can cause race conditions.

Maven Surefire has fork settings such as forkCount and reuseForks. If tests depend on static state or in-JVM caches, changing fork settings can alter outcomes. Do not disable forking or parallelism globally to mask a non-independent test; first identify which state is shared and isolate it.

### 11.1. Sources of Failure Under Parallel Execution

- Multiple tests use the same username or business key in the database.
- Tests write to the same fixed file under target or build.
- Tests modify system properties or the default timezone without restoring them.
- One test shuts down an executor or clears a singleton bean used by another test.
- Tests depend on execution order or data created by an earlier test.
- Tests use a fixed port and two processes try to bind simultaneously.
- A Testcontainers container or mock server is shared, and one test stops it too early.

Prefer per-test data, random ports, @TempDir, independent fixtures, and managed lifecycles. If a resource must be shared, use locks or intentionally run that test group sequentially.

## 12. Testcontainers and Docker Across IDE, Local, and CI

Tests using Testcontainers require a Docker-compatible runtime. The IDE may run on a developer's machine with Docker Desktop, whereas a CI runner may lack a Docker socket or sufficient permissions.

For consistency:

- Pin image tags or digests according to project policy.
- Do not hardcode host ports; obtain the mapped port from the container.
- Manage container initialization via Testcontainers/JUnit lifecycle.
- Wait for health checks or readiness rather than using sleep.
- Supply Spring configuration via @DynamicPropertySource or the service connection mechanism suited to your Spring Boot version.
- Ensure CI runners have a Docker-compatible runtime and the required permissions.

If CI does not support Docker, make an explicit decision: run integration tests on a Docker-capable runner, use a provisioned database service, or separate the test group. Never silently skip critical tests simply because an environment lacks a dependency.

## 13. Spring ApplicationContext Cache and Differences Between Single Runs and Full Suites

Spring TestContext caches application contexts to avoid reinitializing them for test classes with the same configuration. This speeds up the suite but can expose tests that depend on state:

- A test mutates a singleton bean or static state and does not restore it.
- A test alters a system property after the context has already been created.
- A test uses @DirtiesContext, closing a context that other tests depend on.
- A bean holds an in-memory cache or data across multiple test classes.

A test run alone may pass because it gets a fresh context, yet fail in the full suite because a context is reused or test ordering differs. The fix is to keep tests independent, clean up state after each test, avoid mutating shared singleton beans, and use @DirtiesContext only when the context is genuinely altered beyond recovery.

When tests depend on profile or property configuration, place them directly on the test context using appropriate annotations/configuration. Do not rely on a system property set by another test class.

## 14. Timeouts and Time-Sensitive Environments

Tests can behave differently if they depend on timezone, locale, clocks, or wall-clock time:

- Start/end dates may differ when JVM timezones differ.
- Locale-based number or date parsing may differ between developers and CI.
- Tests using Instant.now() may cross date boundaries or timeout thresholds.
- Async tests relying on Thread.sleep() easily fail when CI runners are under heavy load.

For time-dependent business logic, prefer injecting Clock:

~~~java
@Bean
Clock applicationClock() {
    return Clock.systemUTC();
}
~~~

Tests can supply a fixed clock:

~~~java
Clock fixedClock = Clock.fixed(
        Instant.parse("2026-11-13T00:00:00Z"),
        ZoneOffset.UTC);
~~~

This makes time-based tests repeatable without depending on the system clock. For tests waiting on async work, use futures, latches, Awaitility, or StepVerifier with finite timeouts rather than sleep.

## 15. Running the Same Test from IDE, Terminal, and CI

A practical workflow may include:

1. Run a single method in the IDE for quick debugging.
2. Run the full class using the Gradle/Maven runner in the IDE or terminal.
3. Run the same task via the wrapper from the root project.
4. Run the required test group with the same profile, tags, and environment.
5. Run the corresponding CI command or local pipeline before opening a pull request.

Gradle examples:

~~~bash
./gradlew test
./gradlew test --tests "com.example.order.OrderServiceTest"
./gradlew integrationTest
./gradlew check
~~~

Maven examples:

~~~bash
./mvnw test
./mvnw -Dtest=OrderServiceTest test
./mvnw verify
~~~

check in Gradle may depend on configured verification tasks; verify in Maven runs preceding phases together with plugins bound to the lifecycle. Do not assume they execute integration tests unless the project has wired the corresponding tasks/plugins.

In the IDE, choose the Gradle or Maven runner when you need the same lifecycle as CI. If you use the internal JUnit runner for debugging, re-run via the wrapper afterward to confirm the build tool discovers and executes the test as well.

## 16. Reading Build Tool Reports to Diagnose Discrepancies

When IDE and build tool results differ, build tool reports reveal which tests actually ran:

- Gradle typically generates HTML reports in build/reports/tests/test/ and XML reports in build/test-results/test/.
- Maven Surefire typically generates reports in target/surefire-reports/.
- Maven Failsafe typically generates reports in target/failsafe-reports/.

Paths may vary if the project customizes output directories or task names. Reports help identify the number of discovered tests, skipped tests, exceptions, and stack traces. Compare reports with the list of tests the IDE ran to spot filtered tests or discovery differences.

Enable enough test logging to see test names and failures:

~~~kotlin
tasks.test {
    testLogging {
        events("passed", "skipped", "failed")
        exceptionFormat = org.gradle.api.tasks.testing.logging.TestExceptionFormat.FULL
    }
}
~~~

Do not turn on overly verbose logging for the entire suite if it obscures root errors or bloats CI output. You can increase logging specifically for the task or test group under investigation.

## 17. Checklist for IDE Run Configurations

When a test behaves differently from the terminal, check in order:

| Component | What to verify |
|---|---|
| Project SDK | Matches the Java version supported by the project |
| Gradle JVM/Maven runner JRE | Aligns with the wrapper and toolchain |
| Test runner | IDE runner vs. Gradle/Maven runner |
| Module/classpath | Correct module containing the tests and test dependencies |
| Working directory | Matches the project/module root assumed by the build |
| Active profile | Matches the test configuration declared in the repository |
| Environment variables | Contains all required variables, without personal secrets |
| VM options/system properties | Matches build tool configuration |
| Test filters/tags | Does not accidentally exclude or include test groups |
| Parallel execution | Compatible with isolation and shared resources |
| Before launch tasks | Required dependency/resource generation has run |

Store shared configuration in project/build configuration whenever possible. Avoid letting a test pass only because of an unshared personal Run Configuration or undocumented environment variables on a developer machine.

## 18. Common Issues and How to Handle Them

| Symptom | Possible cause | Resolution |
|---|---|---|
| Runs in IDE but Maven/Gradle cannot find the test | Class name does not match include patterns, source set, or task filters | Check naming conventions, test source directories, and plugin/task setup |
| Passes in IDE but build tool fails with class/method errors | Dependency model out of sync or runner uses a different classpath | Reload project, inspect dependency tree, and run via wrapper |
| Test uses different profiles | Run Configuration has a profile that the build lacks | Use ActiveProfiles or configure the profile in the build |
| Fixture-reading test only works in IDE | Uses paths dependent on working directory | Load from classpath or TempDir |
| Test only fails in CI | Different JDK, locale, timezone, environment, Docker, or parallelism | Compare runtimes and properties; remove local machine assumptions |
| Passes alone but fails in the full suite | Shared state, context cache, ordering, or race condition | Make tests independent, clean state, and use resource locks where needed |
| Integration tests do not run in test | Task/source set or Failsafe lifecycle not wired | Invoke the right task or configure check/verify |
| IDE uses a different JDK than Gradle daemon | Project SDK and Gradle JVM differ | Align IDE settings and toolchain |
| Testcontainers runs locally but fails in CI | CI lacks Docker-compatible runtime or permissions | Use a Docker-capable runner and verify readiness |
| Time-based test is flaky | Uses system clock, sleep, or overly tight timeouts | Inject Clock and synchronize with bounded-timeout signals |

## 19. Standardization Workflow for a Spring Project

So that new developers can run tests without manual per-machine setup, the project should standardize:

1. Commit the Gradle Wrapper or Maven Wrapper and use the wrapper in documentation and CI.
2. Declare the Java version/toolchain explicitly.
3. Use JUnit Platform and compatible engine dependencies.
4. Define test naming, source sets, and tasks for unit/integration tests.
5. Declare test profiles and properties in the repository.
6. Load fixtures from the classpath and temporary files from TempDir.
7. Set timeouts, locale, and timezone according to business requirements.
8. Configure parallelism/forking only after tests are independent.
9. Document external dependencies such as Testcontainers and CI environment requirements.
10. Provide standard wrapper commands for running single tests, the unit suite, and integration tests.
11. Retain reports and logs sufficient to diagnose skipped or failed tests.
12. Configure the IDE to sync the project model and prefer the build tool runner when reproducing CI.

## 20. Example of a Unified Test Execution Convention

A project's internal README can publish concise commands:

~~~text
Run unit and slice tests:
  ./gradlew test
  ./mvnw test

Run a single class:
  ./gradlew test --tests "com.example.OrderServiceTest"
  ./mvnw -Dtest=OrderServiceTest test

Run integration tests:
  ./gradlew integrationTest
  ./mvnw verify

Run full verification:
  ./gradlew check
  ./mvnw verify
~~~

Publish only the commands matching the build tool actually used by the project; there is no need to maintain both Gradle and Maven instructions if the repository uses only one build system. The integrationTest task, check task, or Failsafe plugin must be configured before being documented.

When the IDE, terminal, and CI use the same wrapper, JDK, test engine, profiles, test filters, and dependencies, results become far more reproducible. If discrepancies still occur, compare the actual JVM, classpath, properties, working directory, number of discovered tests, and build tool reports to pinpoint the exact cause.

Consistent execution does not mean every test must be run the same manual way. It means the project clearly defines the environment and standard commands, the IDE can reproduce that configuration, and CI executes the exact version-controlled configuration. As a result, test outcomes reflect the application's code and contracts rather than the private state of a single development machine.
