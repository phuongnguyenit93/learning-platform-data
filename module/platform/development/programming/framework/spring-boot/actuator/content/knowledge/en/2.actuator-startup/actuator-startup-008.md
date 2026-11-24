# Verifying the Spring Boot, Micrometer, and Exporter Library Version Set

An application can compile cleanly yet fail at startup with a missing class or missing method error in metrics. In other cases, the application still runs, yet the exporter library uses a different line than the sample code. To handle this properly, inspect the entire dependency set rather than looking at a single version line.

This lesson walks through identifying the **managed version set**, the **version set selected by the build tool**, and **the libraries actually loaded at runtime**. Examples use Spring Boot 3.3.5 for reproducibility; the numbers in the examples are not recommendations to upgrade or downgrade every project to that version.

## 1. Which components must be distinguished?

In an application using Actuator and Prometheus, the simplified metrics path is:

```text
Spring Boot + Actuator
       │ integrates and configures
       ▼
Micrometer Core / Observation
       │ records metrics
       ▼
Micrometer registry for target system
       │ uses corresponding client library / format
       ▼
Output or export path
       │
       ▼
External monitoring system
```

| Component | Role when verifying versions |
| --- | --- |
| Spring Boot | Provides the integration foundation and managed dependency set |
| Micrometer Core | API and mechanism for recording metrics |
| Micrometer Observation | Mechanism for describing observed operations, when used by the application |
| Micrometer registry | Integrates metrics with a target system |
| Client library beneath the registry | Component the registry uses to format or export data |
| External monitoring server | System receiving/scraping data, with its own version lifecycle |

Spring Boot Actuator integrates Micrometer and its registries. Having the registry on the runtime classpath is one part of configuration, while pushing/scraping data still requires proper setup for the target system. See [Spring Boot 3.3 — Metrics](https://docs.spring.io/spring-boot/3.3/reference/actuator/metrics.html).

### 1.1. Version numbers do not have to be equal

For example, `micrometer-registry-prometheus` belongs to the Micrometer artifact group, whereas `prometheus-metrics-core` belongs to Prometheus Java Client. Two libraries can participate in the same metric export path while using different versioning schemes.

Similarly, Micrometer Tracing is its own component group. Do not take `micrometer-core`'s version number and assign it verbatim to every artifact whose name starts with `micrometer`.

A consistent version set means components align with the chosen dependency management mechanism and integration requirements. It does not mean all version strings must be identical.

### 1.2. The Prometheus server is not Prometheus Java Client

The application-side JAR helps produce data for Prometheus to scrape. The Prometheus server outside the application has its own role. Do not infer that the server version must match the Java Client JAR version.

When reading errors, always state the full component name. Saying "Prometheus is on 1.2.1" leaves unclear whether you mean the Java library, the registry, or the server.

## 2. Three levels of evidence to cross-check

| Level | Question | Source of evidence |
| --- | --- | --- |
| Managed | Which version set does this Spring Boot platform prescribe? | BOM, version-matched dependency table |
| Resolved | Which versions did the application build ultimately select? | Dependency graph, version selection reasons |
| Loaded at runtime | Which JARs is the current process actually using? | Class loading location, deployed artifact, and runtime classpath |

A **BOM (Bill of Materials)** is a dependency version management catalog. It lets declarations omit explicit versions, yet importing a BOM does not automatically add every library in the catalog to the application.

**Direct dependencies** are declared by the project; **transitive dependencies** are brought in through other libraries. The build tool resolves version requirements to construct the final classpath.

### 2.1. Verified illustrative version set

With Spring Boot 3.3.5 and no related version-management overrides, the set below is cross-checked from the release's BOM/POM:

| Artifact or group | Illustrative version |
| --- | --- |
| `org.springframework.boot:spring-boot` | `3.3.5` |
| `io.micrometer:micrometer-core` | `1.13.6` |
| `io.micrometer:micrometer-observation` | `1.13.6` |
| `io.micrometer:micrometer-registry-prometheus` | `1.13.6` |
| `io.prometheus:prometheus-metrics-core` | `1.2.1` |
| Micrometer Tracing, if used | `1.3.5` |

The Micrometer, Micrometer Tracing, and Prometheus Client milestones are declared in [the Spring Boot v3.3.5 BOM source](https://raw.githubusercontent.com/spring-projects/spring-boot/v3.3.5/spring-boot-project/spring-boot-dependencies/build.gradle). The program in section 6 also directly inspects the JARs of the Prometheus metrics branch.

Do not apply this table blindly to all Spring Boot 3.3.x releases. When reading [Managed Dependency Coordinates](https://docs.spring.io/spring-boot/3.3/appendix/dependency-versions/coordinates.html), check the page's version label: documentation URLs tracking the `3.3` line may display a different patch release than your application uses.

### 2.2. A difference does not automatically prove an error

A project may intentionally change a version for a specific requirement. In that case, know where it was changed, why it was changed, and what scope was verified.

Conversely, seeing versions match the BOM is not enough to conclude the export pipeline works. Target configuration, authentication, endpoint exposure, or network paths can still be wrong.

## 3. Identifying who manages versions in Gradle

Spring Boot supports either the `io.spring.dependency-management` plugin or Gradle's native BOM mechanism. The two approaches have different customization rules. See [Spring Boot 3.3 — Managing Dependencies](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html).

### 3.1. Using Gradle's platform support

In a project with the Java plugin applied, a concise configuration can be:

```groovy
dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')

    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    runtimeOnly 'io.micrometer:micrometer-registry-prometheus'
}
```

The BOM manages the versions. The registry is declared `runtimeOnly` because this example assumes application code does not directly import registry-specific types.

If Java code imports `PrometheusMeterRegistry`, it needs that library on the compile classpath, such as declared with `implementation` in the section 6 experiment.

In Gradle, `platform` provides version constraints and can be influenced by other requests/constraints. It does not guarantee every final dependency always equals the value in the BOM. `enforcedPlatform` enforces more strongly; do not switch to it just to make reports show no differences without understanding the impact. See [Gradle — Platforms](https://docs.gradle.org/current/userguide/platforms.html).

### 3.2. Using the dependency-management plugin

If a project uses the Spring Boot Gradle Plugin together with `io.spring.dependency-management`, the Boot plugin imports the corresponding BOM through its integration. Managed dependencies then usually do not need separate versions.

However, verify the actual plugins and configuration of the application project. Seeing a plugin version in a root project or a version catalog is not enough to know all subprojects are managed identically.

The [Dependency Management Plugin](https://docs.spring.io/dependency-management-plugin/docs/current/reference/html/) documentation describes how BOMs are imported and their scope. With this mechanism, version management properties can be customized as supported by the plugin.

Do not assume setting a property like `micrometer.version` has the same effect when switching to native `platform`. Use the right mechanism and re-read the dependency resolution output.

### 3.3. Places that can alter the version set

When results differ from expectations, check the relevant locations:

- Versions declared directly on dependencies.
- Other BOMs or platforms participating together.
- Version constraints and dependency resolution rules.
- Version-forcing directives such as `resolutionStrategy.force`.
- Convention plugins or shared configurations.
- Version catalogs providing referenced declarations.
- Active dependency locking.
- Differences between compile, runtime, and test classpaths.

This is a list of places to look for evidence, not a suggestion to delete configurations wholesale. In particular, lock files keep resolution results stable; update them intentionally when changing dependencies. See [Gradle — Locking Versions](https://docs.gradle.org/current/userguide/dependency_locking.html).

## 4. Reading the resolved versions

For a Gradle project, start from the runtime classpath of the actual application:

```powershell
.\gradlew.bat dependencies --configuration runtimeClasspath
```

Then use the detailed report for the main components:

```powershell
.\gradlew.bat dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency micrometer-registry-prometheus --configuration runtimeClasspath
.\gradlew.bat dependencyInsight --dependency prometheus-metrics-core --configuration runtimeClasspath
```

If using another registry, replace the filter with the real artifact name. In multi-project builds, prepend the registered project path, for example:

```powershell
.\gradlew.bat :service:dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
```

`:service` is an illustrative project name; use the application's actual project path. On Linux/macOS, use the `./gradlew` wrapper accordingly.

### 4.1. Do not look for just a single version string

Read all of:

1. Which path requested the dependency.
2. Which final version was selected.
3. The reason that version was selected.
4. Which constraints or rules participated.
5. Whether the inspected configuration matches the process to be run.

Example of a hypothetical tree line:

```text
io.micrometer:micrometer-core:1.13.5 -> 1.13.6
```

This line shows that a request for 1.13.5 was resolved to 1.13.6 in that graph. It does not mean both JARs are packaged together.

The `(c)` marker denotes a constraint, while `(*)` indicates the transitive tree was already shown elsewhere. Reasons such as `By constraint`, `Selected by rule`, or `Forced` help trace version management effects. See [Gradle — Viewing Dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html).

Do not call a dependency resolving to a different version than originally requested a "breaking conflict" before reading the reason and evaluating the final version set.

### 4.2. Comparing compile and runtime when skew is suspected

If the program compiles yet fails at runtime, you can also read:

```powershell
.\gradlew.bat dependencyInsight --dependency micrometer-core --configuration compileClasspath
.\gradlew.bat dependencyInsight --dependency micrometer-core --configuration runtimeClasspath
```

The two reports help identify differences across configurations. They still need to be cross-checked against how the application is actually packaged and launched.

Do not take results from a library project or test classpath and treat them as evidence for the runtime of a different application project.

## 5. Distinguishing registry branches and exporter libraries

### 5.1. Two Prometheus branches with similar names

In the Micrometer 1.13 line, the two choices below use different generations of the Prometheus Java Client:

| Registry artifact | Underlying client branch | Typical registry package |
| --- | --- | --- |
| `micrometer-registry-prometheus` | Prometheus Java Client 1.x | `io.micrometer.prometheusmetrics` |
| `micrometer-registry-prometheus-simpleclient` | Simpleclient 0.x | `io.micrometer.prometheus` |

The split is described in [Micrometer 1.13 — Prometheus](https://docs.micrometer.io/micrometer/reference/1.13/implementations/prometheus.html).

These are not two spellings of the same artifact name. Code importing the old branch's package may fail to compile against the new branch's dependency.

Before editing imports or adding dependencies, determine which integration branch the application intends to use and the requirements of collaborating frameworks/libraries. Do not add both registries just to make every import resolve.

### 5.2. Do not assign the registry version number to the client

In the verified example:

```text
micrometer-registry-prometheus 1.13.6
              ↓ uses
prometheus-metrics-core 1.2.1
```

The number 1.13.6 belongs to Micrometer. There is no basis to manually change `prometheus-metrics-core` to 1.13.6 to "synchronize" them.

Likewise, when you only want to enable Prometheus metrics through Actuator, usually declare the appropriate registry and let the transitive dependency be managed. Declare the client explicitly only when code or integration design truly requires it, then re-inspect the graph.

### 5.3. OTLP metrics and trace export are two paths to distinguish

`micrometer-registry-otlp` serves metrics over OTLP. The corresponding configuration in Spring Boot uses the `management.otlp.metrics.export` property group. See [Micrometer 1.13 — OTLP](https://docs.micrometer.io/micrometer/reference/1.13/implementations/otlp.html).

For traces, Spring Boot uses Micrometer Tracing and matching bridges/exporters. For example, OpenTelemetry integration requires components dedicated to tracing, not just a metrics registry. See [Spring Boot 3.3 — Tracing](https://docs.spring.io/spring-boot/3.3/reference/actuator/tracing.html).

Therefore, seeing the word "exporter" in an error is not enough to pick a replacement dependency. Specify what kind of telemetry is being exported, which artifact is used, and which protocol/destination is targeted.

## 6. Java experiment: inspecting loaded JARs and exporting a sample metric

The experiment uses a standalone Java program without opening an HTTP port or connecting to a Prometheus server. It inspects where classes are loaded from and uses the registry to produce a metric sample.

### 6.1. Prepare a small project

Use JDK 17 or higher with compatible Gradle. Create a fresh directory to prevent old JARs or other configurations from interfering.

Create `settings.gradle`:

```groovy
rootProject.name = 'version-set-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'java'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation platform(
        'org.springframework.boot:spring-boot-dependencies:3.3.5')

    implementation 'org.springframework.boot:spring-boot-starter-actuator'
    implementation 'io.micrometer:micrometer-registry-prometheus'
}

tasks.register('copyDemoLibraries', Copy) {
    from configurations.runtimeClasspath
    into layout.projectDirectory.dir('lib')
}
```

Here the registry uses `implementation` because the program directly imports its specific API and that of the transitive client. Importing the BOM alone is not enough; used dependencies still must be declared.

### 6.2. Complete Java code

Save to `src/main/java/lab/versions/VersionSetDemo.java`:

```java
package lab.versions;

import java.nio.file.Path;

import io.micrometer.core.instrument.Counter;
import io.micrometer.core.instrument.MeterRegistry;
import io.micrometer.prometheusmetrics.PrometheusConfig;
import io.micrometer.prometheusmetrics.PrometheusMeterRegistry;
import org.springframework.boot.SpringBootVersion;

public class VersionSetDemo {
    public static void main(String[] args) throws Exception {
        System.out.println("spring-boot=" + SpringBootVersion.getVersion());
        System.out.println("micrometer-core=" + jarName(MeterRegistry.class));
        System.out.println("registry=" + jarName(PrometheusMeterRegistry.class));
        System.out.println("prometheus-client="
                + jarName(io.prometheus.metrics.core.metrics.Counter.class));

        PrometheusMeterRegistry registry =
                new PrometheusMeterRegistry(PrometheusConfig.DEFAULT);
        try {
            Counter checks = registry.counter("version.checks");
            checks.increment();
            System.out.println("counter=" + checks.count());
            String sample = registry.scrape().lines()
                    .filter(line -> line.startsWith("version_checks_total "))
                    .findFirst().orElseThrow();
            System.out.println("sample=" + sample);
        } finally {
            registry.close();
        }
    }

    private static String jarName(Class<?> type) throws Exception {
        return Path.of(type.getProtectionDomain()
                .getCodeSource().getLocation().toURI())
                .getFileName().toString();
    }
}
```

The `jarName` method reads the location the JVM used to load the class. In an experiment running with regular JARs on the classpath, the filename reveals the artifact and version of the inspected class.

Do not treat this technique as a universal verifier for every packaging style. When libraries are shaded, renamed, loaded by custom classloaders, or compiled into a native image, code-source location info may differ or be unavailable in that form.

### 6.3. Compile and run commands

In the experiment root directory, using PowerShell:

```powershell
gradle copyDemoLibraries
javac -encoding UTF-8 -cp "lib/*" -d out src/main/java/lab/versions/VersionSetDemo.java
java -cp "out;lib/*" lab.versions.VersionSetDemo
```

If the test project has a wrapper, use that wrapper instead of `gradle`. On Linux/macOS, the run command uses `:`:

```bash
java -cp "out:lib/*" lab.versions.VersionSetDemo
```

Gradle needs repository access if dependencies are not cached yet. The copy task is not meant to delete old JARs, so use a fresh directory to avoid mixing libraries from other attempts.

Verified stdout with the example's version set:

```text
spring-boot=3.3.5
micrometer-core=micrometer-core-1.13.6.jar
registry=micrometer-registry-prometheus-1.13.6.jar
prometheus-client=prometheus-metrics-core-1.2.1.jar
counter=1.0
sample=version_checks_total 1.0
```

Gradle download or execution output is not part of the Java program's stdout.

### 6.4. What do the results prove?

| Observation | Conclusion that can be drawn in the experiment |
| --- | --- |
| Spring Boot line | Version of the loaded Boot class |
| Three JAR name lines | Representative classes were loaded from those specific artifacts |
| `counter=1.0` | The counter recorded one increment |
| `sample=...` | The registry produced a Prometheus metric sample for that counter |

The test export is more useful than only printing version names: it exercises a real operational path from the Micrometer API to output data.

However, this is a small check. It does not validate all meter types, histogram configurations, tracing, Actuator HTTP, or successful scraping by an external server. When evaluating a version upgrade, add checks for the capabilities the real application uses.

### 6.5. Cross-checking against the deployed application

If the IDE and deployment package behave differently, inspect the actual packaging and runtime. For example, with an illustrative Spring Boot executable JAR named `order-service-1.0.0.jar`:

```powershell
jar --list --file "build/libs/order-service-1.0.0.jar" | Select-String "BOOT-INF/lib/.*(spring-boot|micrometer|prometheus)"
```

Replace the filename with the real artifact. The command only lists contents without modifying the JAR. It applies to executable JARs using Boot's packaging layout, not the class output of the console experiment.

The JAR list inside the package verifies packaging. When multiple class loading sources or custom classloaders exist, process-level evidence is still needed to know which class was chosen.

## 7. If the project uses Maven

The verification principles remain the same: identify the version management source, read the final graph, and cross-check runtime.

A Maven project may inherit `spring-boot-starter-parent` or import `spring-boot-dependencies` in `dependencyManagement`. Declaring only the Spring Boot Maven plugin version is not equivalent to importing the dependency management BOM. See [Spring Boot 3.3 — Using the Maven Plugin](https://docs.spring.io/spring-boot/3.3/maven-plugin/using.html).

Useful inspection commands in the exact application module:

```powershell
mvn dependency:tree "-Dincludes=org.springframework.boot:*,io.micrometer:*,io.prometheus:*"
mvn help:effective-pom
```

If a Maven Wrapper exists, use the project's wrapper. In `effective-pom`, check dependency management and direct declarations; in the dependency tree, check the selected version and the path that introduced it.

The `dependency:tree` filter supports group/artifact wildcards. If using an exporter from another group, add that group to the filter instead of assuming absence from the report means no dependency exists. See [Maven Dependency Plugin — tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html).

Do not transfer Gradle's conflict resolution rules directly onto Maven. Use the reports and management mechanisms of the build tool actually building the application.

## 8. Reading errors to pick the right investigation direction

| Symptom | First direction to check | What cannot be concluded immediately |
| --- | --- | --- |
| Registry package import does not exist | Artifact, client branch, and compile classpath | Need to add both registry branches |
| `NoSuchMethodError` | Caller class, loaded class, and binary compatibility | Every error is caused by the newest library |
| `NoClassDefFoundError` | Missing class, runtime classpath, and cause chain | Just need to add an arbitrary JAR |
| `UnsupportedClassVersionError` | Running JDK and class bytecode version | Actuator endpoint config is wrong |
| `/actuator/prometheus` unreachable | Dependencies, conditions, exposure, security, path | Version set is definitely incompatible |
| Registry has data yet external system sees nothing | Scrape/push path, destination, and permissions | Must upgrade Micrometer |
| Metrics exported yet dashboards are empty | Names, tags, queries, and retention | Application lacks a registry |

### 8.1. NoSuchMethodError: mismatch in method definition

The JVM throws this error when code attempts to invoke a method, yet the class definition used at runtime lacks the corresponding method. See [Java 17 — NoSuchMethodError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoSuchMethodError.html).

Example investigation steps:

1. Record the method and class names from the error.
2. Identify the libraries containing the caller class and callee class.
3. Read versions in the compile/runtime graph.
4. Inspect the JARs actually packaged or loaded.
5. Find the rule or declaration that produced a different library set than expected.

Clean compilation does not rule out this error if runtime uses a different set of classes. Do not fix it by trying versions one after another without keeping evidence.

### 8.2. NoClassDefFoundError: check the class and root cause

One possibility is that the needed class is no longer on the runtime classpath. See [Java 17 — NoClassDefFoundError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/NoClassDefFoundError.html).

Also read the full cause chain: a message about failing to initialize a class may trace back to an earlier initialization error. Do not grab only the class name on the last line and add a duplicate-function dependency.

Switching from the old Prometheus Client branch to the new one also requires checking which code or libraries still reference the old package.

### 8.3. UnsupportedClassVersionError: check the JDK actually running

This error relates to the JVM not supporting the class file version being read. See [Java 17 — UnsupportedClassVersionError](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/UnsupportedClassVersionError.html).

A simple check:

```powershell
java -version
javac -version
.\gradlew.bat --version
```

These commands identify tools in the invoking environment. The IDE, Gradle toolchain, or deployment machine may use a different JDK; inspect the exact process under diagnosis.

This is a separate issue from whether Micrometer JARs share the same version. Record the two checks separately.

## 9. When and how to change versions?

Start from the version set managed by the Spring Boot platform. If a change is needed, state the concrete goal: API requirement, bug fix, or verified compatibility requirement.

A verifiable change should document:

1. Current version set and current management mechanism.
2. Target version set and matching documentation.
3. Which declarations/constraints will change.
4. Which metrics or trace exports must be re-tested.
5. Runtime evidence and test results.
6. How to roll back to the verified set if needed.

### 9.1. Avoid updating one piece without checking the rest

If you bump `micrometer-core` alone while keeping the registry on an old branch, you have created a new combination that must be evaluated. A higher version number does not automatically guarantee that combination fits the Spring Boot version in use.

Conversely, upgrading Spring Boot while keeping an old `force` or lock can cause the application to continue using part of the older library set. Re-read the graph after changes; do not check only the plugin line.

### 9.2. Verify according to actually used capabilities

For Prometheus, check representative meters, output generation, and the HTTP path if the application uses Actuator web. If the application has histograms, custom tags, or trace-linked exemplars, test those as well.

For push paths, check export configuration, destination responses, and real data in the target system. The console program in section 6 does not represent those paths.

If the application uses tracing, separately verify context creation and propagation, the exporter, and the trace backend. Do not infer that tracing works merely from one successfully exported Prometheus metric.

### 9.3. Do not use clean operations as a substitute for diagnosis

`clean` generally deletes build outputs; it does not alter dependency selection rules. Refreshing caches also will not fix a wrong version-forcing declaration still sitting in configuration.

Fix the identified root cause, rebuild the artifact when needed, and re-read the graph and runtime. Keep changes small enough to explain before and after.

## 10. Writing a comparable version verification record

A sample record filled from the experiment:

```text
Management source: spring-boot-dependencies 3.3.5.
Mechanism: Gradle native platform.
Micrometer Core: 1.13.6.
Registry: micrometer-registry-prometheus 1.13.6.
Underlying client: prometheus-metrics-core 1.2.1.
Package branch: io.micrometer.prometheusmetrics.
Verified runtime: console program on standalone JAR classpath.
Evidence: loaded JAR names, counter=1.0, and generated Prometheus sample.
Not yet verified: Actuator HTTP, Prometheus server, and tracing.
```

For a real application, add the build module name, inspected configuration, deployed artifact, JDK, and verification timestamp. If graph and runtime differ, record the difference explicitly rather than simply marking "matches BOM".

### Scenario self-check

**Scenario A:** Core and registry are 1.13.6, client is 1.2.1. Should the client be changed to match the same number?

No. These are artifact groups with separate versioning schemes. Cross-check the managed set and actual graph rather than comparing version strings for equality.

**Scenario B:** The build file specifies no registry version, yet runtime still uses a version different from what the BOM prescribes.

Check whether version management applies to the right configuration, other constraints/rules, lock files, and the deployed artifact. Omitting a version on one line does not eliminate other sources of influence.

**Scenario C:** Code imports `io.micrometer.prometheus`, while dependencies use the 1.x client branch.

Verify which branch the code and dependencies belong to. Choose the appropriate integration approach and adjust in a verified manner; do not add the old branch alongside it just to silence import errors.

**Scenario D:** The registry exports a sample, yet Prometheus does not scrape it.

The test confirmed part of the application side. Continue checking the delivery path and scraper; there is no evidence yet that library versions must change.

### Applied exercise

Choose one export pipeline in your application and build a table containing: artifact, managed version, selected version, class loading location or deployment package, and reason for version selection.

Then record a representative test and the limits of that test. You have completed version-set verification when you can explain **why the build chose those libraries, what the process uses, and how far the data pipeline has been verified**.
