# Determining Spring Boot, Spring Framework, and JDK Baselines for a Library

## 1. Goal: publishing a verifiable compatibility contract

When developing a library in the Spring ecosystem, the question “which Spring Boot versions does the library support?” cannot be answered simply by looking at the dependency version in `pom.xml`. There are at least three independent axes to lock down:

1. **Minimum JDK:** the lowest Java bytecode and API level that the library requires.
2. **Minimum Spring Framework:** the Spring API line that the library source code uses.
3. **Minimum Spring Boot and supported lines:** the Boot versions that provide the dependency management, auto-configuration API, and integration environment against which the library is tested.

A library can compile with JDK 21 while still targeting Java 17 bytecode; it can use the Spring Framework 6.2 API; and it can be tested against multiple different Boot lines. Those three numbers do not have to be identical.

This lesson guides you on choosing a baseline, accurately reading the relationship between Boot/Framework/JDK, designing modules to support multiple lines, configuring Maven/Gradle, building a CI matrix, and publishing compatibility scopes. Examples use **Java 17+** and the current Spring Boot lines in the official documentation at the time of writing.

## 2. Three version axes and the meaning of each axis

### 2.1. JDK baseline

The JDK baseline answers: what is the minimum Java version on which consuming applications can run the library?

Three values must be distinguished:

- **JDK used to build:** the JDK installed on the developer machine or CI.
- **Java release/bytecode target:** the class file version and set of Java APIs that the compiler is allowed to use.
- **Minimum runtime JDK:** the lowest JVM capable of loading and running the artifact.

For example, building with JDK 21 while configuring `--release 17` restricts bytecode and Java APIs to Java 17. If you only declare source/target without using an appropriate release flag, the compiler may still allow referencing APIs introduced only in a newer JDK; applications may subsequently fail when running on the minimum JDK.

For new libraries targeting Spring Boot 3.x and 4.x, the practical Java baseline is typically **Java 17** because these Boot lines require Java 17 or later. If the library needs Java 21 APIs, the library baseline must be raised to Java 21 even though Boot still supports Java 17.

### 2.2. Spring Framework baseline

The Spring Framework baseline answers: what is the minimum Spring API the library needs to compile and run?

For example:

- A module that only uses `org.springframework.core` or `spring-context` may have a narrower dependency scope than an auto-configuration module.
- A module that uses APIs from `spring-webmvc`, `spring-security`, or `spring-data` must also consider the versions of those corresponding projects.
- A module that uses `@AutoConfiguration`, `@ConditionalOnClass`, `@ConditionalOnMissingBean`, or `AutoConfiguration.imports` also depends on Spring Boot, not just Spring Framework.

A library that compiles successfully with Spring Framework 7.0 does not automatically prove that it runs on Spring Framework 6.2. If the source code references a new method or class that only appeared in 7.0, a 6.2 runtime may encounter `NoSuchMethodError` or `NoClassDefFoundError`.

### 2.3. Spring Boot baseline

The Spring Boot baseline answers: which Boot lines does the library support and which BOM is it tested against?

For a library that only provides a Java API, depending on Spring Boot may not be necessary. For a Spring integration library, Boot may only be a testing environment. However, for an auto-configuration or starter module, Boot is a direct dependency because that module uses the Boot API.

Distinguish between:

- **Compile baseline:** the lowest version against which the source code is compiled.
- **Runtime compatibility:** the version lines on which the artifact actually runs.
- **Tested support:** the version lines that have run through the test suite in CI.
- **Recommended version:** the line that documentation advises users to choose for new projects.

Only declare a Boot line as supported when you have appropriate test evidence. Do not infer support just because Maven can resolve the dependencies.

## 3. Relationship between Spring Boot, Spring Framework, and JDK lines

Spring Boot manages a set of dependencies that have been tested together. Each Boot line is tied to a specific Spring Framework line and a specific Java baseline. The table below uses stable patch releases in the official documentation as examples; the minimum patch version of Framework may vary by Boot patch release.

| Spring Boot line | Minimum Java | Corresponding Spring Framework line | Notes |
|---|---:|---|---|
| 2.7.x | 8 | 5.3.x | Legacy Java EE line, uses `javax` namespace for related Jakarta/Servlet APIs |
| 3.0.x–3.1.x | 17 | 6.0.x | Switched to Jakarta EE, `jakarta.*` packages |
| 3.2.x–3.3.x | 17 | 6.1.x | Framework 6.1 line |
| 3.4.x–3.5.x | 17 | 6.2.x | Framework 6.2 line |
| 4.0.x–4.1.x | 17 | 7.0.x | Framework 7.0 line, requires dedicated compatibility testing |

Some patch milestones in the official system requirements documentation:

| Documented Boot release | Minimum Java | Minimum Spring Framework |
|---|---:|---|
| Boot 2.7.18 | 8 | 5.3.31 |
| Boot 3.0.13 | 17 | 6.0.14 |
| Boot 3.1.12 | 17 | 6.0.21 |
| Boot 3.2.12 | 17 | 6.1.x |
| Boot 3.3.13 | 17 | 6.1.21 |
| Boot 3.4.13 | 17 | 6.2.15 |
| Boot 3.5.16 | 17 | 6.2.19 |
| Boot 4.0.9 | 17 | 7.0.10 |
| Boot 4.1.2 | 17 | 7.0.10 |

These are the requirements of each cited Boot release, not a guarantee that every older patch of a line supports every new JDK. Open the System Requirements page for the exact patch before finalizing a CI matrix or declaring runtime support.

At the time of writing, the official documentation lists the stable lines 3.3, 3.4, 3.5, 4.0, and 4.1. That does not mean a library must support all of them. Library maintainers need to choose the scope based on target users, maintenance time, and testing cost.

## 4. Steps to choose a baseline for a library

### Step 1: identify the artifact type

First, determine which case the library falls into:

| Module type | Primary dependencies | Baseline to publish |
|---|---|---|
| Core Java library | JDK and standalone Java libraries | Minimum JDK; Boot not needed if Boot is unused |
| Spring integration | Spring Framework | JDK + Spring Framework |
| Boot auto-configuration | Spring Boot auto-config API and Spring Framework | JDK + Boot/Framework line |
| Starter aggregator | Integration modules and dependencies pulled in by the starter | Boot line against which the starter is tested |
| Adapter for external project | APIs of Spring Security, Data, Kafka, etc. | Boot/Framework and integrated project version |

If a repository contains both a core API and auto-configuration, you do not have to force every module to share the same dependency graph. You can separate the core to keep its API stable and separate Boot modules to integrate with each Boot line.

### Step 2: gather requirements from users

Collect data from real consuming applications:

- Are they running Boot 3.3, 3.5, or 4.1?
- Are there still applications forced to use Boot 2.7?
- Is the lowest runtime JDK 17, 21, or higher?
- Do they use the Servlet stack, WebFlux, or no web stack?
- Do they need native image, AOT processing, or GraalVM?
- Are there Spring Cloud/Spring Data/Security projects whose versions need to be coordinated?

Do not support an older line just because it compiles. Every declared supported line increases the number of combinations to test, documentation overhead, and issue triage time.

### Step 3: choose the minimum JDK based on actually used Java APIs

If the targets are Boot 3.5 and Boot 4.1, Java 17 is the lowest common baseline required by these two Boot lines. Using `release 17` makes the compiler prevent accidental use of newer Java APIs.

If the core library needs to support Java 8 to be used with Boot 2.7, modules can be split:

- `acme-core`: Java 8 or the lowest baseline that core can maintain.
- `acme-spring-boot3-autoconfigure`: Java 17.
- `acme-spring-boot4-autoconfigure`: Java 17, if a separate adapter is needed.

Do not set Java 8 as the baseline for the entire library just because a core module can run on Java 8; Boot 3/4 integration modules must still satisfy Java 17.

### Step 4: choose the lowest Boot/Framework line you commit to supporting

If broad Boot 3.x support is needed, a baseline could be Boot 3.3.x / Framework 6.1.x with additional testing on 3.5.x / Framework 6.2.x. If targeting only the latest 3.x line, Boot 3.5.x / Framework 6.2.x can be used as the baseline.

If you want to support Boot 4.x, add a separate test lane with Boot 4.1.x / Framework 7.0.x. Do not claim Boot 4 compatibility solely based on sharing the Java 17 requirement; a major release can change APIs, dependency graphs, modules, and integrations.

### Step 5: compile against the lowest baseline, test across every declared line

If a library declares support for Boot 3.3, 3.5, and 4.1:

- Compile the source against the lowest API you want to support.
- Use the corresponding BOM to resolve dependencies when running tests for each line.
- Run integration tests on each line.
- If a line requires its own source set or adapter, split modules rather than adding hard-to-maintain version conditionals.

Compiling with Framework 7.0 and only testing on Boot 4.1 does not prove Boot 3.5 support. Conversely, compiling with Framework 6.2 does not automatically prove that all Boot 4.1 APIs and extension points remain compatible.

## 5. Choosing a single baseline or multiple supported lines?

### 5.1. A single baseline

Suitable when the library is new, target users have already moved to a clear Boot line, the team is small, and maintenance cost must stay low.

Example contract:

~~~text
Library version: 2.x
Java: 17+
Spring Boot: 3.5.x
Spring Framework: 6.2.x (per Boot's BOM)
Tested with: Boot 3.5.16
~~~

The advantage is ease of understanding, testing, and support. The downside is that applications on Boot 3.3 or Boot 4.1 may not be able to use it if the library does not declare/test those lines.

### 5.2. One artifact supporting multiple Boot lines

Suitable when the library primarily uses stable APIs, target Boot lines share the same Java baseline, source code does not depend on new APIs present only in higher lines, and CI can run the full matrix.

Example contract:

~~~text
Library version: 2.x
Java: 17+
Spring Boot: 3.3.x, 3.5.x, 4.1.x
Spring Framework: per each Boot line's BOM
Tested patch versions: specified in release notes
~~~

When using one artifact, the compile dependency versions in the POM and the consuming application's dependency management must be coordinated. Inspect the runtime dependency tree to be certain consumers are running the Spring version selected by their BOM.

### 5.3. Splitting modules or artifacts by major line

Split when there are genuine differences in APIs, namespaces, dependency graphs, or code that must be compiled separately.

~~~text
acme-library/
├── acme-core/
├── acme-spring/
├── acme-boot3-autoconfigure/
├── acme-boot3-starter/
├── acme-boot4-autoconfigure/
└── acme-boot4-starter/
~~~

`acme-core` contains independent logic. The Boot 3 module depends on Spring Boot 3 and Spring Framework 6; the Boot 4 module depends on Spring Boot 4 and Spring Framework 7. Both adapters can call into the shared core API.

Do not split modules merely to mirror every patch version. Splitting is usually only needed when there is a major compatibility boundary or when the source code genuinely differs.

### 5.4. When supporting both Boot 2.7 and Boot 3+ is required

Boot 2.7 uses Java 8 and Spring Framework 5.3; Boot 3+ requires Java 17 and moves Jakarta APIs to the `jakarta.*` namespace. Integrations using Servlet, Validation, Persistence, or Jakarta APIs usually need separate source/modules.

If both must be supported:

- Keep the core module at the lowest possible Java baseline.
- Separate the legacy Boot 2/Jakarta module and the Boot 3+ module.
- Do not let `javax.*` types leak into the public API of the Boot 3 module.
- Check the dependency tree to exclude legacy Java EE dependencies from the Boot 3 module.
- Use the proper auto-configuration metadata for the target lines.

Spring Boot 2.7 supports both the `AutoConfiguration.imports` file and the `spring.factories` mechanism for auto-configuration. Spring Boot 3 removed auto-configuration registration via the `EnableAutoConfiguration` key in `spring.factories`; if an artifact needs to be compatible with both 2.7 and 3.x, design metadata and tests according to the official migration guide.

## 6. Spring Boot BOM: letting Boot manage Spring Framework

Spring Boot publishes the `spring-boot-dependencies` BOM containing dependency versions selected and tested together. When upgrading Boot, the BOM updates Spring Framework and many related libraries in sync.

Key principles for libraries:

- Do not set your own versions for `spring-core`, `spring-context`, `spring-beans`, `spring-web`, or other Spring modules when a BOM manages them.
- Do not upgrade Spring Framework individually to a newer line just to grab an API while still claiming support for an older Boot line.
- If an override is genuinely needed, document the reason, verify compatibility, and test thoroughly.
- Consuming applications should use the BOM of the Boot line the application is running on.

For example: Boot 3.5 manages Spring Framework 6.2; Boot 4.1 manages Spring Framework 7.0. A library POM should not force all consumers onto Framework 7.0 if it still wants to support Boot 3.5.

### 6.1. Maven example for an auto-configuration module

The example below uses Boot 3.5.16 as the build/test baseline. This is a sample configuration for a module using the Boot auto-configuration API, not a claim that every consumer must run this exact patch.

File `pom.xml`:

~~~xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <groupId>com.acme</groupId>
    <artifactId>acme-boot-autoconfigure</artifactId>
    <version>2.0.0</version>

    <properties>
        <java.version>17</java.version>
        <maven.compiler.release>17</maven.compiler.release>
        <spring-boot.version>${spring-boot.version}</spring-boot.version>
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

    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-autoconfigure</artifactId>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-configuration-processor</artifactId>
            <optional>true</optional>
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
                <artifactId>maven-compiler-plugin</artifactId>
                <version>3.13.0</version>
                <configuration>
                    <release>17</release>
                </configuration>
            </plugin>
        </plugins>
    </build>
</project>
~~~

Replace `${spring-boot.version}` with the chosen version property or manage it via CI profiles. Using the Maven parent `spring-boot-starter-parent` provides dependency management and compiler defaults out of the box; for multi-module libraries, importing the BOM directly often helps preserve control over the organization's parent POM.

Note: the library's dependency management helps build the module consistently. Consuming applications should still manage their dependency graph with the BOM of the Boot line they run on. Inspect the published POM and actual dependency tree instead of assuming a library's BOM automatically replaces the application's platform.

### 6.2. Gradle example

With Gradle and the Java Library plugin:

~~~groovy
plugins {
    id 'java-library'
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation(platform(
        "org.springframework.boot:spring-boot-dependencies:3.5.16"
    ))

    implementation(
        "org.springframework.boot:spring-boot-autoconfigure"
    )

    testImplementation(
        "org.springframework.boot:spring-boot-starter-test"
    )
}

tasks.withType(JavaCompile).configureEach {
    options.release = 17
}
~~~

`toolchain` selects the JDK used to compile. `options.release` restricts the bytecode and Java APIs used. If the library declares Java 17+, keep both settings at 17, even when CI runs on JDK 21 or 25.

To test across multiple Boot lines, manage the BOM version via a Gradle property or version catalog and run each CI job with a specific value. Do not use dynamic versions like `latest.release` in release builds because results can change without any source changes.

## 7. Dependency scope and public API

Choose scopes based on how consumers need to use the library:

| Dependency | When to use | Notes |
|---|---|---|
| `api` (Gradle) | Dependency types appear in the library's public method/signature and consumers must compile against those types | Makes the dependency part of the consumer's compile API |
| `implementation` | Dependency is an internal detail but still needed at runtime | Usually suitable for implementations and runtime auto-configuration |
| `compileOnly` | Container or consuming application definitely provides the dependency; the artifact should not pull in a runtime dependency | Use only when the library contract requires the consumer to provide it |
| Maven `optional` | You want the dependency not to propagate transitively to consumers | Consumers must declare the dependency if they want the corresponding feature |
| `test` / `testImplementation` | Used only when running tests | Does not appear in the consumer's runtime |

Do not use `optional` out of habit. If an auto-configuration class needs a Boot type to be loaded, or a starter needs an integration library to create a bean, design runtime dependencies explicitly. For optional integrations, split modules or use safe conditions/classloaders so applications without that dependency can still start.

Public API also affects the baseline. If a public method returns a type present only in Spring Framework 7, consumers using that module are bound to Framework 7 even if most of the library logic is compatible with Framework 6.

## 8. Designing modules to reduce version coupling

A maintainable library typically separates business logic from integration code:

~~~text
acme/
├── acme-core/
│   └── Pure Java API and logic
├── acme-spring-support/
│   └── Spring Framework integration
├── acme-boot3-autoconfigure/
│   └── Boot 3 conditions and bean definitions
├── acme-boot3-starter/
│   └── Dependency aggregator for Boot 3
├── acme-boot4-autoconfigure/
│   └── Boot 4 adapter if needed
└── acme-boot4-starter/
    └── Dependency aggregator for Boot 4
~~~

Benefits:

- Core has minimal dependence on Spring Boot, making it easier to keep the API stable.
- Business logic can be tested without starting an ApplicationContext.
- Each adapter compiles against its corresponding BOM.
- When a Boot major version changes, only the adapter module needs updates if the core API is unaffected.
- The starter can declare the exact dependencies for the target Boot line.

Do not create empty modules just to increase the artifact count. Only split when there is a real dependency or compatibility boundary.

## 9. Auto-configuration and metadata per Boot line

An auto-configuration module must be tested with the exact registration mechanism and API of the declared Boot line.

Example configuration class:

~~~java
package com.acme.autoconfigure;

import com.acme.core.AcmeClient;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
public class AcmeAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    AcmeClient acmeClient() {
        return new AcmeClient();
    }
}
~~~

Registered in file:

`src/main/resources/META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`

Contents:

~~~text
com.acme.autoconfigure.AcmeAutoConfiguration
~~~

If the same module must support Boot 2.7 and Boot 3.x, evaluate the metadata registration of both lines. Boot 2.7 supports the imports file and `spring.factories`; Boot 3 removed the `EnableAutoConfiguration` key in `spring.factories`. Do not confuse other SPIs that still use `spring.factories` with the auto-configuration registration mechanism.

When supporting Boot 4, build and test the module with the Boot 4 BOM; do not merely change the version in the POM and assume every API, starter dependency, and extension point remains unchanged.

## 10. Building a compatibility test matrix

A library must only declare support for combinations that have been tested. The matrix does not need to cover every JDK and every patch version, but it must cover key boundaries.

### 10.1. Recommended matrix for a new library

If the library plans to support both the newer Boot 3 line and Boot 4:

| Test lane | Spring Boot | Spring Framework via BOM | Test JDKs |
|---|---|---|---|
| Boot 3 baseline | 3.5.16 | 6.2.x | 17, 21, 25 |
| Boot 4 baseline | 4.1.2 | 7.0.x | 17, 21, 27 |

This is an example matrix based on the documented JDK limits for the patch releases above. If your project's CI does not have the newest JDK, pick a representative subset and document the actual scope. If the library claims support for Boot 3.3, you must add a Boot 3.3 test lane; do not infer it from Boot 3.5 tests.

If still supporting Boot 2.7, add a separate lane with appropriate JDK 8/11/17. When that module uses `javax.*`, do not merge it with a `jakarta.*` adapter just to reduce job count.

### 10.2. What to test in each lane?

On each Boot line, run at least:

1. Compile all modules.
2. Unit tests for core logic.
3. Auto-configuration tests with `ApplicationContextRunner`.
4. Integration tests using an actual consumer application that depends on the starter.
5. Tests with optional dependencies present and absent on the classpath.
6. Tests where a user bean causes default auto-configuration to back off.
7. Property condition and binding tests.
8. JAR packaging tests to verify the imports resource is present.
9. Runtime tests on the declared minimum JDK.
10. Dependency tree inspection to catch overridden Spring Framework versions.

### 10.3. Auto-configuration test example

~~~java
package com.acme.autoconfigure;

import com.acme.core.AcmeClient;

import org.junit.jupiter.api.Test;
import org.springframework.boot.autoconfigure.AutoConfigurations;
import org.springframework.boot.test.context.runner.ApplicationContextRunner;

import static org.assertj.core.api.Assertions.assertThat;

class AcmeAutoConfigurationTests {

    private final ApplicationContextRunner runner =
            new ApplicationContextRunner()
                    .withConfiguration(
                            AutoConfigurations.of(
                                    AcmeAutoConfiguration.class
                            )
                    );

    @Test
    void createsDefaultClientWhenUserHasNoClient() {
        this.runner.run(context -> {
            assertThat(context).hasNotFailed();
            assertThat(context).hasSingleBean(AcmeClient.class);
        });
    }
}
~~~

This test verifies the conditions and bean registration of the auto-configuration in a test context. For a real discovery test, add a consumer application that only declares the starter dependency, without `@Import`ing the auto-configuration class and without component-scanning the library's package. A consumer test verifies that JAR metadata is read through the application startup path.

### 10.4. Illustrative CI matrix

You can use a single Maven property for the BOM version and run multiple jobs:

~~~bash
./mvnw -Dspring-boot.version=3.5.16 clean verify
./mvnw -Dspring-boot.version=4.1.2 clean verify
~~~

If the BOM version is hardcoded in the POM, turn it into a property/profile or use two separate build fixtures. Do not edit the POM file manually between jobs as this can make CI results non-reproducible.

Each job should record:

- Actual JDK (`java -version`).
- Maven/Gradle version.
- Boot BOM version.
- Resolved Spring Framework version.
- Test results and artifact commit.
- Whether any test lane was skipped.

## 11. Inspecting the actual dependency graph

A successful build is not enough. Another dependency can pull in a Spring Framework version outside the BOM, or an SDK can pull legacy `javax.*` APIs into a Boot 3 module.

Maven:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree -Dincludes=org.springframework,org.springframework.boot
~~~

Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

Read the output to answer:

- Are `spring-core`, `spring-context`, and `spring-beans` on the same line?
- Are `spring-boot` and `spring-boot-autoconfigure` on the same Boot line?
- Does any old dependency pull `javax.servlet` or `javax.validation` into a Jakarta module?
- Are there any version overrides outside the BOM?
- Did an optional integration accidentally become a required runtime dependency?

When releasing a library, inspect both the module's effective POM and the dependency tree inside a consumer application. The library module's own dependency tree does not always accurately reflect the final graph of a consuming application.

## 12. Version upgrade rules

### 12.1. Patch upgrades within the same line

Patch releases typically focus on bug fixes and compatible dependency updates within the same release line. Even so, run CI on the latest Boot patch the project chooses to support and check the changelogs of Spring Boot, Framework, and integrated libraries.

Do not pin consumers to an old patch without a reason. In a consuming application, Boot's BOM is usually where the patch dependency graph is chosen.

### 12.2. Boot minor/feature release upgrades

When moving from Boot 3.3 to 3.5, Spring Framework also moves from the 6.1 line to 6.2. Check deprecations, behavior changes, dependency upgrades, and condition processing. If the library declares both lines, test both instead of building only against the newest version.

### 12.3. Major release upgrades

Boot 2 → 3 is a significant boundary: Java 17 becomes the baseline, Spring Framework 6 is used, and the Jakarta namespace replaces the Java EE namespace in related APIs.

Boot 3 → 4 also requires a dedicated compatibility lane because Boot switches to Spring Framework 7 and may update many dependencies, modules, and integrations. Read the migration guide for each jump; if spanning multiple releases, read the release notes of intermediate lines.

### 12.4. Do not use version ranges in place of a compatibility policy

A wide Maven version range declaration does not prove the library is compatible with every version in the range. Resolvers may pick a version different from the tested one, or a new version may have API/behavior changes.

Publish a clear support table and test each line. If you want to use a version range, have a concrete reason, understand resolver rules, and still maintain a CI matrix to confirm.

## 13. Publishing the baseline in documentation and artifacts

The README or release page should include a short Compatibility section, following a template like:

~~~markdown
## Compatibility

| Library line | Java | Spring Boot | Spring Framework |
|---|---|---|---|
| 2.x | 17+ | 3.5.x | Managed by Boot BOM |
| 2.x | 17+ | 4.1.x | Managed by Boot BOM |

Tested with:
- Spring Boot 3.5.16 on JDK 17, 21, and 25
- Spring Boot 4.1.2 on JDK 17, 21, and 27

The Spring Framework version is selected by the Spring Boot BOM.
Do not override Spring Framework modules independently unless required.
~~~

Do not write “Spring Boot 3+” if you only tested one patch of Boot 3.5 and have not tested 3.0/3.1/3.2/3.3. Likewise, do not write “Java 17+” if bytecode was built with release 21.

Clearly state:

- The lowest supported Boot line.
- The tested Boot lines.
- The minimum JDK and tested JDKs.
- Which BOM manages Framework.
- Separate modules/artifacts for different Boot major versions.
- Unsupported lines and the last maintained version.

## 14. Common mistakes when choosing a baseline

- **Choosing only the latest version:** ignoring users on older Boot lines and failing to evaluate maintenance cost.
- **Treating the build JDK as the minimum runtime JDK:** building with JDK 21 does not mean the artifact runs on Java 17 unless `--release` is used.
- **Compiling against a newer Framework and declaring support for an older Framework:** can cause linkage errors when running on the older API.
- **Specifying a standalone Framework version in a starter:** can break Boot BOM dependency alignment.
- **Confusing the Boot baseline with the Framework baseline:** the auto-configuration API belongs to Boot; `ApplicationContext` and many extension APIs belong to Framework.
- **Using one artifact for both `javax` and `jakarta` without a boundary:** type signatures, dependencies, and runtime APIs may be incompatible.
- **Using version ranges to claim support:** a resolver picking a version does not mean tests proved compatibility.
- **Compiling only without running integration tests:** fails to catch bean condition, metadata, classpath, or runtime linkage failures.
- **Testing only the latest Boot:** does not prove the lowest baseline still works.
- **Not testing the minimum JDK:** bytecode may load, yet newer Java APIs still cause runtime errors.
- **Making an optional SDK a required dependency:** consumers that do not use the integration may hit classpath errors.
- **Combining Boot 2.7 and Boot 3+ in one adapter without considering namespaces:** `javax` and `jakarta` are two different APIs.
- **Not checking the consumer dependency tree:** the module builds cleanly, yet the final application may resolve a different Framework version.
- **Not stating the tested patch versions:** users do not know the evidence level behind the compatibility claim.
- **Keeping an old line without a maintenance owner:** matrix size grows without capacity to fix bugs and apply security updates.

## 15. Quick decision workflow

1. List consuming applications and the actual Boot lines in use.
2. Identify which modules are pure Java, Spring integration, and Boot auto-configuration.
3. Choose the minimum JDK based on required Java APIs and users' runtime JDKs.
4. Choose the lowest Spring Framework line that the source code actually needs.
5. Choose the corresponding Boot BOM; do not upgrade Spring Framework independently.
6. Decide whether to support one Boot line, multiple lines, or split adapters by major version.
7. If supporting Boot 2.7 alongside Boot 3+, split modules when `javax`/`jakarta` differ.
8. Configure the compiler using `release`, not just source/target.
9. Create a CI matrix for the Boot baseline, the latest supported Boot, and the minimum JDK.
10. Run integration tests in a consumer app and check the runtime dependency tree.
11. Publish the tested matrix, patch versions, and unsupported lines.
12. When upgrading Boot/Framework majors, update the compatibility policy and migration notes before release.

### Sample recommendation for a new library

If a new library needs to serve both Boot 3 and Boot 4 applications in today's environment, a practical policy is:

- Use **Java 17** as the common bytecode baseline.
- Maintain a **Boot 3.5.x / Framework 6.2.x** test lane.
- Maintain a separate **Boot 4.1.x / Framework 7.0.x** test lane.
- Use a single artifact only if the same source and dependency graph pass both lanes; otherwise, split adapters by major version.
- Add Boot 2.7 only when there is a concrete user need and the ability to maintain a separate Java 8/Framework 5.3 module.

If the library targets only Boot 4, Boot 4.1.x / Framework 7.0.x / Java 17+ can serve as the primary baseline. If the library targets only Boot 3, choose the latest Boot 3.x patch within the support scope and let the BOM manage the corresponding Framework 6.x line.

This is a suggested policy and does not replace checking the runtime requirements of SDKs, database drivers, Servlet containers, or integration libraries the product actually uses.

## 16. Self-check questions

1. What are the three version axes that must be published? **Minimum JDK, Spring Framework baseline, and supported/tested Spring Boot lines.**
2. Does building with JDK 21 prove a library runs on Java 17? **No.** You must compile with `--release 17` and run runtime tests on JDK 17.
3. Which Framework line accompanies Boot 3.5.x? **Framework 6.2.x per Boot 3.5's BOM.**
4. Which Framework line accompanies Boot 4.1.x? **Framework 7.0.x per Boot 4.1's BOM.**
5. Should you pin the `spring-context` version yourself in a starter? **Usually no.** Let Boot's BOM manage Spring modules.
6. If you need to support Boot 2.7 and Boot 3+, what major boundaries must be considered? **Java 8 versus Java 17 and the `javax.*` versus `jakarta.*` namespaces.**
7. Does a pure Java core module need a Boot dependency? **No**, if it does not use Boot APIs.
8. When should you split Boot 3 and Boot 4 adapters? **When APIs, dependency graphs, or integration sources are incompatible in a shared artifact.**
9. Does testing with Boot 3.5 prove Boot 3.3 support? **No.** You must run tests on Boot 3.3 if declaring support for that line.
10. What is the `spring-boot-dependencies` BOM used for? **Selecting a Boot-managed set of compatible dependency versions.**
11. Why should you not use a version range instead of a test matrix? **Resolvers can pick untested versions; a range is not compatibility evidence.**
12. What is the minimum evidence to declare support for a Boot line? **Compilation, unit/integration tests, consumer tests, JDK runtime tests, and the dependency tree for that line.**

## 17. Official references

- [Spring Boot 3.5 — System Requirements](https://docs.spring.io/spring-boot/3.5/system-requirements.html): JDK and Spring Framework requirements for Boot 3.5.
- [Spring Boot 4.1 — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html): JDK and Spring Framework requirements for Boot 4.1.
- [Spring Boot 4.0 — System Requirements](https://docs.spring.io/spring-boot/4.0/system-requirements.html): JDK and Spring Framework requirements for Boot 4.0.
- [Spring Boot 3.4 — System Requirements](https://docs.spring.io/spring-boot/3.4/system-requirements.html): requirements for the Boot 3.4 line.
- [Spring Boot 3.3 — System Requirements](https://docs.spring.io/spring-boot/3.3/system-requirements.html): requirements for the Boot 3.3 line.
- [Spring Boot 3.2 — Getting Started and System Requirements](https://docs.spring.io/spring-boot/docs/3.2.x/reference/html/getting-started.html): requirements for the Boot 3.2 line.
- [Spring Boot 3.1 — Getting Started and System Requirements](https://docs.spring.io/spring-boot/docs/3.1.x/reference/htmlsingle/): requirements for the Boot 3.1 line.
- [Spring Boot 3.0 — Getting Started and System Requirements](https://docs.spring.io/spring-boot/docs/3.0.13/reference/html/getting-started.html): requirements for the Boot 3.0 line.
- [Spring Boot 2.7 — Getting Started and System Requirements](https://docs.spring.io/spring-boot/docs/2.7.18/reference/htmlsingle/): requirements for the Boot 2.7 line.
- [Spring Boot — Build Systems and Dependency Management](https://docs.spring.io/spring-boot/reference/using/build-systems.html): BOMs, dependency management, and the recommendation not to specify Spring Framework versions manually.
- [Spring Boot 3.3 — Managing Dependencies with Gradle](https://docs.spring.io/spring-boot/3.3/gradle-plugin/managing-dependencies.html): importing the BOM in Gradle and managing dependency versions.
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide): Java 17, Spring Framework 6, Jakarta namespace, and auto-configuration metadata migration.
- [Spring Boot — Upgrading](https://docs.spring.io/spring-boot/upgrading.html): approach to migration and release notes when upgrading Boot lines.
