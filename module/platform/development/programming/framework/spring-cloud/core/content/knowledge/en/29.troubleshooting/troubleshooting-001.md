# Application Fails to Start Due to Boot and Cloud Incompatibility

## 1. Recognizing Compatibility Errors Right at Startup

Spring Boot and Spring Cloud are released on two different versioning cadences. Spring Boot uses versions in the form `4.1.2`, while Spring Cloud uses release trains in the form `2025.1.4`. These two versions do not need to match; they must belong to a pair published by Spring as compatible.

When the wrong release train is chosen, the application may stop immediately at startup with a message similar to:

```text
APPLICATION FAILED TO START

Your project setup is incompatible with our requirements
due to the following reasons:

- Spring Boot [4.x.y] is not compatible with this Spring Cloud release train

Action:
- Change Spring Boot version to one of the compatible versions
  listed by the Spring Cloud release train.
```

This message typically comes from the **Spring Cloud Compatibility Verifier**. The verifier checks the Spring Boot version present on the classpath against the versions accepted by the release train. It helps detect unsupported version pairs before the application proceeds deep into initialization.

However, not every startup failure is a release train error. `NoSuchMethodError`, `NoClassDefFoundError`, `ClassNotFoundException`, `UnsupportedClassVersionError`, or bean creation failures can stem from overridden dependencies, an outdated JDK, missing starters, or misconfiguration. This lesson guides you on how to distinguish these error groups before changing versions.

## 2. Understanding the Two Independent Versioning Systems

Spring Boot and Spring Cloud are responsible for managing different parts:

- Spring Boot provides the application foundation, auto-configuration, embedded server, dependency management, and build plugins.
- Spring Cloud adds abstractions and integrations for distributed systems such as Config, Discovery, LoadBalancer, Gateway, Circuit Breaker, Bus, and OpenFeign.
- The Spring Boot BOM manages Spring Framework, logging, JSON, server, and many third-party dependencies as a tested set.
- The Spring Cloud release train BOM manages the versions of Spring Cloud modules so they work consistently with a specific Spring Boot generation.

An application can use Spring Boot `4.1.2` together with Spring Cloud `2025.1.4`. This is a valid version pair according to the current compatibility matrix. You do not need—and should not try—to find a Spring Cloud version numbered `4.1.2`.

## 3. Checking the Compatibility Matrix Before Changing Dependencies

At the time of writing (18-11-2026), the Spring Cloud page announces Spring Cloud `2025.1.4` as the latest GA release train. The official compatibility table lists:

| Spring Cloud release train | Compatible Spring Boot | Notes |
| --- | --- | --- |
| `2025.1.x` Oakwood | `4.0.x`; `4.1.x` starting with `2025.1.2` | Current GA release train |
| `2025.0.x` Northfields | `3.5.x` | Compatible per matrix; project page marks EOL with `*` |
| `2024.0.x` Moorgate | `3.4.x` | End of OSS support |
| `2023.0.x` Leyton | `3.2.x`, `3.3.x` starting with `2023.0.2` | End of OSS support |
| `2022.0.x` Kilburn | `3.0.x`, `3.1.x` starting with `2022.0.3` | End of OSS support |
| `2021.0.x` Jubilee | `2.6.x`, `2.7.x` starting with `2021.0.3` | End of OSS support |

Older release trains also have their own mapping tables, but are no longer covered by the OSS support policy. If you are maintaining a legacy system, check the support status and upgrade plan before continuing to use them.

Spring Cloud `2026.0.0-RC2` is currently a preview release and announces support for Spring Boot `4.2.0-RC2`. This is not a GA release. Do not use this RC pair for production just to resolve a verifier error on an application using Boot GA.

Rules for reading the table:

1. Select the row according to your application's Spring Boot version.
2. Choose the corresponding Spring Cloud release train.
3. If the table states a condition such as “Starting with 2025.1.2”, you must use a service release from that milestone onward.
4. Within the same release train, prefer the latest still-supported GA service release.
5. Check the support lifecycle of each Cloud module if your application uses modules with separate support schedules.

Do not choose a release train solely based on its codename or a higher version number. A newer release train may require a newer generation of Spring Boot.

## 4. How Does the Spring Cloud Compatibility Verifier Work?

The Compatibility Verifier belongs to Spring Cloud Commons. It detects the Spring Boot version on the classpath and compares it against the list of versions accepted by the release train. When incompatible, the verifier generates a report explaining the current version and the accepted versions.

Key properties:

| Property | Effect |
| --- | --- |
| `spring.cloud.compatibility-verifier.enabled` | Enables or disables the compatibility verification step |
| `spring.cloud.compatibility-verifier.compatible-boot-versions` | Overrides the list of Boot versions accepted by the verifier |

To proactively enable the check in your project:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
```

Default behavior and property metadata may differ across Spring Cloud versions. When you need the verifier to run reliably in CI or development environments, explicitly declare `true` rather than relying on assumptions from an older article.

If using a standard release train, let the compatibility list be provided by the release train. Do not manually add Boot versions to `compatible-boot-versions` just to silence the error message. Doing so only changes the condition accepted by the verifier; it does not prove that APIs, auto-configurations, or dependencies are actually compatible.

An example of overriding the list is only appropriate when an organization maintains a Spring Cloud fork or a tested combination with dedicated support responsibility:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: true
      compatible-boot-versions: "4.0.x,4.1.x"
```

Do not use the configuration above as a quick fix for a regular application. If an override is required, there must be documentation explaining why the combination is valid, integration tests covering the relevant modules, and an owner responsible for maintenance.

## 5. Determining the Actual Running Versions

Do not just read the versions declared in `pom.xml` or `build.gradle`. Dependencies can be overridden by a parent POM, another BOM, Gradle constraints, version catalogs, or transitive dependencies.

Identify at least four version groups:

- Spring Boot plugin/parent version.
- Actual Spring Boot runtime artifacts, such as `spring-boot` and `spring-boot-autoconfigure`.
- Spring Cloud release train BOM.
- Actual Spring Cloud modules, such as `spring-cloud-commons`, `spring-cloud-config`, and `spring-cloud-netflix`.

If the log shows `SpringBootVersion` in the manifest, cross-check it with the version in the dependency graph. The version in the build file and the runtime version must match.

A project might declare Boot `4.1.2`, yet dependency management or another module pulls in a different version of `spring-boot-autoconfigure`. In that case, merely looking at the version property at the top of the file will not reveal the problem.

## 6. Fixing Versions with Maven

Maven should use the Spring Boot parent or import the Spring Boot BOM, then import exactly one Spring Cloud release train BOM. The following example uses Boot `4.1.2` with Cloud `2025.1.4`:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
    <spring-cloud.version>2025.1.4</spring-cloud.version>
</properties>

<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.cloud</groupId>
            <artifactId>spring-cloud-dependencies</artifactId>
            <version>${spring-cloud.version}</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-config</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.cloud</groupId>
        <artifactId>spring-cloud-starter-netflix-eureka-client</artifactId>
    </dependency>
</dependencies>
```

This is an example of dependency management structure. Check the Java baseline according to your exact Spring Boot version and project toolchain before choosing `java.version`.

Points to note:

- `spring-cloud-dependencies` is a BOM that manages versions; it does not automatically put all Spring Cloud modules onto the classpath.
- Every starter that the application actually uses must still be declared under `<dependencies>`.
- Do not specify individual versions for each Spring Cloud starter if the BOM already manages them.
- Do not import multiple different Cloud release trains simultaneously.
- Do not use the parent POM of an older Cloud release train alongside the BOM of a newer release train without a specific reason and thorough testing.

If the project does not use the Spring Boot parent, you can import both the `spring-boot-dependencies` BOM and `spring-cloud-dependencies` BOM inside `dependencyManagement`. Make sure the ordering and any overrides are explicitly reviewed.

## 7. Fixing Versions with Gradle

With Gradle Kotlin DSL, you can use native BOM support to manage both Boot and Cloud:

```kotlin
plugins {
    id("org.springframework.boot") version "4.1.2"
    java
}

dependencies {
    implementation(
        platform("org.springframework.boot:spring-boot-dependencies:4.1.2")
    )
    implementation(
        platform("org.springframework.cloud:spring-cloud-dependencies:2025.1.4")
    )

    implementation("org.springframework.cloud:spring-cloud-starter-config")
    implementation("org.springframework.cloud:spring-cloud-starter-netflix-eureka-client")
}
```

Gradle can also use the `io.spring.dependency-management` plugin. If you choose that approach, configure the Spring Boot plugin and Cloud BOM according to the Spring Boot Gradle Plugin documentation. Do not mix the two dependency management approaches without understanding precedence rules and applied constraints.

### 7.1. Checking Version Catalogs and Dependency Constraints

If the project uses `gradle/libs.versions.toml`, check whether Spring Boot and Spring Cloud aliases declare separate versions. A version catalog may retain an old version even when a new BOM has been updated elsewhere.

Also search for declarations such as:

- `version`
- `strictly`
- `prefer`
- `force`
- `resolutionStrategy`
- `enforcedPlatform`
- `constraints`

A constraint or `force` in the root project can override the version intended to be managed by the BOM. Do not blindly delete all constraints; identify which dependency needs an override and why.

## 8. Common Mistakes When Mixing BOMs

| Misconfiguration | Possible Consequence | Resolution |
| --- | --- | --- |
| Boot 4.1.x with Cloud 2025.1.0 | Release train does not support Boot 4.1.x yet | Use Cloud 2025.1.2 or higher |
| Boot 3.5.x with Cloud 2025.1.x | Different Boot generation than supported by the release train | Use Cloud 2025.0.x |
| Importing Cloud 2025.0 and 2025.1 together | Cloud modules may resolve to mismatched versions | Import only one release train |
| Declaring an explicit version for `spring-cloud-commons` | Commons may drift from Config, Consul, Netflix, or Gateway | Remove the explicit version and let the Cloud BOM manage it |
| Overriding `spring-core` or `spring-context` with an arbitrary version | Spring Framework APIs may no longer align with Boot | Revert to the version managed by the Boot BOM |
| Using an old starter via a transitive dependency | Classpath may contain unwanted legacy modules | Use the dependency tree to trace how it is pulled in and update/exclude intentionally |
| Upgrading only the Boot plugin without upgrading the runtime BOM | Build plugin and runtime dependencies are from different generations | Update Boot parent/BOM and Cloud BOM in sync |

The Spring Boot BOM and Spring Cloud BOM have different management scopes. The Boot BOM manages Spring Framework modules and many foundational libraries; the Cloud BOM manages Spring Cloud modules. You should not force all dependencies to the same version number.

## 9. Reading Stack Traces to Find the True Cause

The first message often only tells you that the application failed to start. The specific cause usually lies deeper in the `Caused by` chain.

| Symptom | Common Meaning | What to Check |
| --- | --- | --- |
| `Spring Boot [...] is not compatible with this Spring Cloud release train` | Compatibility Verifier rejected the Boot/Cloud pair | Release train matrix and BOMs |
| `NoSuchMethodError` | Code was compiled against an API different from the runtime version loaded | Mixed Spring Framework, Boot, and Cloud artifacts |
| `NoSuchFieldError` | Runtime class lacks a field expected by the caller | Dependency version overrides |
| `NoClassDefFoundError` | Class existed at compile time but is missing at runtime, or static initialization failed | Runtime classpath, optional dependencies, and initialization cause |
| `ClassNotFoundException` | Class loader cannot find the class by name | Missing dependency, wrong class name, or classloader boundary |
| `AbstractMethodError` | Runtime implementation does not satisfy the method contract expected by the caller | API module and implementation version mismatch |
| `UnsupportedClassVersionError` | Runtime JDK is too old to read the bytecode | Java runtime, toolchain, and target bytecode |
| `NoSuchBeanDefinitionException` | Bean was not created or is absent from the context | Starters, auto-configuration conditions, profiles, and component scan |
| `BeanDefinitionOverrideException` | Duplicate bean name or changed override behavior | Application configuration and auto-configuration changes |
| Gradle `No matching variant` | Variant does not match attributes such as JVM version, usage, or platform | JDK, Gradle metadata, and dependency attributes |
| Maven `Could not resolve artifact` | Artifact could not be downloaded or version/repository does not exist | Coordinates, repositories, proxy, and dependency versions |

Do not jump to the conclusion that `NoSuchBeanDefinitionException` is always caused by Boot/Cloud incompatibility. It can also occur because the application is missing a starter, configuration is not activated, the active profile is wrong, or a condition is not met.

## 10. Distinguishing Boot/Cloud Errors from JDK and Build Tool Errors

The Spring Boot/Spring Cloud matrix does not replace Java runtime and build tool requirements.

For example:

- `UnsupportedClassVersionError` indicates that the bytecode requires a newer Java version than the current runtime.
- An outdated Gradle wrapper may fail to run new plugins or a newer JDK.
- The Maven Compiler Plugin may set `release` lower or higher than the actual JDK.
- Native libraries or third-party libraries may have specific OS/architecture requirements.
- A Spring Cloud module may be compatible with the release train while the application's third-party dependencies are already out of support.

When an error occurs, record the output of:

```bash
java -version
./mvnw -version
./gradlew --version
```

Run the commands matching your project's build tool. If CI and local machines use different JDKs, compare `JAVA_HOME`, toolchains, and Gradle/Maven wrapper versions as well.

## 11. Inspecting the Dependency Tree with Maven

The following command shows the resolved dependency graph:

```bash
./mvnw dependency:tree
```

Narrow the output to the relevant groups:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot:*,org.springframework:*,org.springframework.cloud:*
```

Use verbose mode to also see dependencies omitted due to conflicts:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework.boot:*,org.springframework:*,org.springframework.cloud:*
```

Export the effective POM to inspect the parent, BOMs, and managed versions:

```bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
```

When reading the results, look for:

- Multiple versions of `spring-boot`, `spring-boot-autoconfigure`.
- Multiple Spring Framework versions such as `spring-core`, `spring-context`, `spring-beans`.
- Cloud modules belonging to a different release train.
- Versions brought in by transitive dependencies.
- Dependencies marked `omitted for conflict` or versions managed by an unintended BOM.

Do not fix issues by adding exclusions until you know which dependency pulls in the wrong version. An exclusion can remove classes that another module needs.

## 12. Inspecting the Dependency Graph with Gradle

List runtime dependencies:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Inspect a specific dependency to see the selected version and the reason:

```bash
./gradlew dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot-autoconfigure --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
```

If the error only occurs in tests, check `testRuntimeClasspath`. If it only occurs during compilation, check `compileClasspath`. A dependency can resolve differently across configurations.

For multi-module projects, run the command in the appropriate module or specify the project path, for example:

```bash
./gradlew :inventory-service:dependencyInsight --dependency spring-cloud-commons --configuration runtimeClasspath
```

Do not inspect only the root project: each module can import its own BOM or apply its own constraints.

## 13. Safe Order of Troubleshooting Steps

Follow this order to avoid changing too many versions at once:

1. **Save the full startup error**: preserve the `APPLICATION FAILED TO START` message, leading lines, and the `Caused by` chain.
2. **Identify the actual Boot version**: check the parent/plugin and the version in the dependency graph.
3. **Identify the Cloud release train**: find the imported BOM and the resolved Cloud module versions.
4. **Check the official matrix**: determine the supported Boot/Cloud pair and support status.
5. **Select one release train**: use the appropriate BOM for that train, preferring the latest GA service release.
6. **Remove unnecessary version pins**: remove explicit versions on Spring Cloud modules if managed by the BOM.
7. **Inspect transitive dependencies**: use dependency tree/insight to find legacy artifacts or forced versions.
8. **Verify JDK and wrapper**: ensure the toolchain matches Spring Boot requirements.
9. **Rebuild from scratch**: run a clean build after updating dependency configuration.
10. **Run tests and startup smoke tests**: verify auto-configuration, web context, and active Cloud integrations.
11. **Check verifier logs**: keep compatibility verification enabled in CI to catch regressions early.

Change only one group of versions at a time. If you upgrade Boot, Cloud, JDK, Gradle, Netty, and HTTP clients simultaneously, it becomes hard to tell which change fixed or introduced an error.

## 14. Examples of Choosing a Release Train by Spring Boot Version

### 14.1. Applications Using Spring Boot 4.1.x

Choose Spring Cloud `2025.1.2` or higher. Current GA configuration example:

```xml
<properties>
    <spring-boot.version>4.1.2</spring-boot.version>
    <spring-cloud.version>2025.1.4</spring-cloud.version>
</properties>
```

If using the Spring Boot parent, the Boot version is declared in `<parent>`; the property above merely illustrates the relationship between the two versions.

### 14.2. Applications Using Spring Boot 3.5.x

Spring Cloud `2025.0.x` is the release train paired with Boot `3.5.x`, though the project page currently marks this train EOL with `*`. If you must maintain a legacy application, use the latest published patch and confirm your organization's support policy; plan an upgrade of Boot/Cloud to a still-supported GA pair. Do not pair Cloud 2025.1 with Boot 3.5 simply because it is a newer release train.

### 14.3. Applications Using Spring Boot 3.4.x or Older

Spring Cloud `2024.0.x` was previously paired with Boot `3.4.x`, but this release train has reached end of OSS support according to the current table. Trains 2023.0.x and older also have published EOL status.

If you need to continue maintaining legacy systems, check commercial support options or plan a tested upgrade path for Boot and Cloud. Do not upgrade Boot alone to a new major release while keeping an old Cloud train.

## 15. When Can the Compatibility Verifier Be Disabled?

In regular projects, you should not disable the verifier to hide compatibility errors.

Disabling the verifier with:

```yaml
spring:
  cloud:
    compatibility-verifier:
      enabled: false
```

should only be considered temporarily when:

- Verifying a custom combination with private patches.
- Integration tests already prove that the required modules work.
- It is clearly confirmed that the verifier is rejecting only because the default list does not yet include a tested Boot version.
- There is a plan to remove the override or responsibly maintain the fork.

Disabling the verifier does not fix `NoSuchMethodError`, does not add missing classes, and does not make APIs compatible again. Without solid evidence, keep the verifier enabled and fix the version pair first.

## 16. Causes Outside the Release Train

Even when the Boot/Cloud BOMs are correct, an application can still fail because:

- A third-party library pulls in a different Spring Framework or Reactor version.
- A starter was replaced with an incompatible module.
- The production profile activates different auto-configurations than the local profile.
- Conditional bean configurations are no longer satisfied after a version upgrade.
- The Java runtime, Gradle wrapper, or Maven plugin does not meet Boot's requirements.
- The classpath contains two implementations of the same API.
- The application uses deprecated APIs that were removed in a major release.

Therefore, after confirming the release train is correct, inspect the root cause and dependency graph instead of continuing to change versions at random.

## 17. Testing After Aligning Versions

A successful build only proves compilation/packaging completed. Run the following additional checks:

| Check | What to Confirm |
| --- | --- |
| Unit tests | Business logic and configuration are unaffected |
| Application context test | ApplicationContext initializes with the expected bean graph |
| Auto-configuration test | Starters and conditional configurations activate properly |
| Config Client integration | Application reads configuration by profile/application |
| Discovery integration | Service registration and lookup work |
| LoadBalancer/Feign/Gateway | Requests to services resolve correctly |
| Actuator health | Health contributors are not missing or reporting wrong statuses |
| Runtime smoke test | Application starts on a JDK and environment close to production |
| CI dependency report | No unexpected Spring Boot/Framework/Cloud versions appear |

If using multiple profiles or multiple Cloud modules, test at least one context for each critical configuration. An application with only Config Client might start up even if another Eureka/Gateway module is still mismatched in version.

## 18. Recording Versions to Prevent Regression

After fixing the issue, record:

- Spring Boot version.
- Spring Cloud release train and service release.
- JDK vendor/version.
- Maven/Gradle wrapper version.
- Spring Cloud modules in use.
- Any dependency overrides with clear justification.
- Dependency tree or Gradle dependency insight output.

Use dependency locking or dependency verification if your build process requires reproducibility. In CI, you can store the dependency report as a build artifact for comparison during version upgrades.

When upgrading, read the release notes for both Spring Boot and Spring Cloud. A version pair being in the same matrix does not mean nothing in the application's behavior will change; major releases can still remove old APIs or change auto-configuration.

## 19. Quick Diagnostic Table

| Symptom | First Check | Fix Direction |
| --- | --- | --- |
| Verifier reports incompatible Boot | Boot version and Cloud release train | Choose the right Cloud BOM from the matrix |
| Boot 4.1.x with Cloud 2025.1.0 | 4.1.x support milestone | Upgrade Cloud to 2025.1.2+ |
| Boot 3.5.x with Cloud 2025.1.x | Release train in use | Use Cloud 2025.0.x |
| `NoSuchMethodError` in `org.springframework.*` | Actual Framework version | Remove overrides and use Boot BOM |
| `NoSuchMethodError` in `org.springframework.cloud.*` | Resolved Cloud modules | Align under a single Cloud BOM |
| `NoClassDefFoundError` only at runtime | `runtimeClasspath`/Maven runtime tree | Add dependency in proper scope or remove bad exclusion |
| `UnsupportedClassVersionError` | `java -version` and class file version | Upgrade runtime JDK or set matching build target |
| Gradle `No matching variant` | Gradle attributes and Java toolchain | Align Gradle wrapper, JDK, and plugins |
| Maven fails to resolve BOM | Effective POM, repository, version | Fix coordinates/repository or use a published release |
| Verifier reports no error but app still fails | Root cause and dependency graph | Diagnose specific API/classpath/auto-configuration issue |

## 20. Checklist Before Concluding the Fix Is Complete

- [ ] Read the entire `Caused by` chain, not just the `APPLICATION FAILED TO START` line.
- [ ] Identified the actual Spring Boot version on the runtime classpath.
- [ ] Identified a single Spring Cloud release train BOM.
- [ ] Cross-checked the version pair against the official compatibility table.
- [ ] Checked the service release and support status.
- [ ] Removed unnecessary Spring Cloud module version pins.
- [ ] Checked for overridden Spring Framework/Boot dependencies.
- [ ] Verified JDK and Maven/Gradle wrapper versions.
- [ ] Ran dependency tree or dependency insight.
- [ ] Ran context tests and smoke tests in a production-like environment.
- [ ] Did not disable the verifier just to hide the error.
- [ ] Documented the version matrix in the project's upgrade documentation.

## 21. Self-Check Questions

1. Why does Spring Boot `4.1.2` not need Spring Cloud `4.1.2`?
2. Which modules does the Spring Cloud release train BOM manage?
3. Starting from which service release does Spring Cloud `2025.1.x` support Boot `4.1.x`?
4. Which release train should Boot `3.5.x` be paired with?
5. What does the Compatibility Verifier check and what are its limitations?
6. Why does disabling the verifier not fix `NoSuchMethodError`?
7. How can you detect a Spring Cloud module being pulled back to an older version?
8. What role do `dependencyManagement` and BOM imports play in Maven?
9. How does Gradle `dependencyInsight` help find why a version was chosen?
10. How does `UnsupportedClassVersionError` differ from a release train error?
11. Why should you not import multiple Spring Cloud release trains in the same application?
12. What should be tested after aligning Boot/Cloud versions?

## 22. Official References

- [Spring Cloud — Release Train Compatibility](https://spring.io/projects/spring-cloud/) — Spring Boot and Spring Cloud mapping table, service releases, and BOM import instructions.
- [Spring Cloud — Supported Versions](https://github.com/spring-cloud/spring-cloud-release/wiki/Supported-Versions) — support policy, supported release trains, and EOL history.
- [Spring Cloud Commons — Common Abstractions](https://docs.spring.io/spring-cloud-commons/reference/spring-cloud-commons/common-abstractions.html) — Spring Cloud Compatibility Verification and error reporting when Boot is incompatible.
- [Spring Cloud Commons — Configuration Properties](https://docs.spring.io/spring-cloud-commons/reference/configprops.html) — `spring.cloud.compatibility-verifier.enabled` and `compatible-boot-versions`.
- [Spring Boot — Managing Dependencies](https://docs.spring.io/spring-boot/gradle-plugin/managing-dependencies.html) — dependency management with Boot BOM and Gradle.
- [Spring Boot — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html) — dependency management and `spring-boot-dependencies`.
- [Gradle — Importing a Platform (BOM)](https://docs.gradle.org/current/userguide/platforms.html) — native BOM support, `platform`, and dependency constraints.
- [Apache Maven — Dependency Mechanism](https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html) — BOM imports and `dependencyManagement`.
- [Apache Maven Dependency Plugin — dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/usage.html) — inspecting the resolved dependency graph.

*This document helps locate and fix startup failures caused by incompatible Spring Boot/Spring Cloud version pairs. Align with a supported release train, verify actual dependencies, and re-confirm with tests on the application's target JDK/runtime.*
