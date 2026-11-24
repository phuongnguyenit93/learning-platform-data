# JAR Discovery Testing to Catch Missing or Misconfigured Imports Files

## 1. Goal: testing the artifact that applications actually use

An auto-configuration can work perfectly in unit tests yet fail to run when a user adds the starter to an application. The root cause often lies in packaging or discovery:

- The `AutoConfiguration.imports` file is missing from the JAR.
- The file is placed in the wrong directory or has the wrong casing.
- A line in the file contains an incorrect fully qualified class name (FQCN).
- The class was moved/renamed, yet the imports resource was not updated.
- Resource filtering, shading, or packaging overwrote or dropped the content.
- Tests only import the class directly and therefore never exercise Spring Boot's discovery mechanism.

This article focuses on verifying at the **artifact boundary**: building the library, installing/publishing the JAR, and running an independent consumer project that depends solely on that artifact. The consumer test both checks that the resource is inside the right JAR and boots Spring Boot to prove the auto-configuration is discovered via the imports file.

Example scope: Spring Boot 3.3.x, Java 17+, Maven, and JUnit 5. Examples use a fictional `acme-audit` library that can be swapped for a real artifact.

## 2. Spring Boot 3.x discovery mechanism

In Spring Boot 3.x, auto-configurations are declared in the resource:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Spring Boot searches for this resource on the classpath, including inside published dependency JARs. Each line contains **one fully qualified auto-configuration class name**:

```text
com.acme.audit.autoconfigure.AuditAutoConfiguration
com.acme.audit.autoconfigure.AuditWebAutoConfiguration
```

Comments starting with `#` and blank lines are allowed. Class names must have the exact package, exact casing, and exact class name.

Example resource in the `acme-audit-spring-boot-autoconfigure` module:

```text
src/main/resources/
└── META-INF/
    └── spring/
        └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

File content:

```text
com.acme.audit.autoconfigure.AuditAutoConfiguration
```

### 2.1. Why are direct-import tests not enough?

A unit test typically writes:

```java
new ApplicationContextRunner()
        .withConfiguration(
                AutoConfigurations.of(AuditAutoConfiguration.class))
        .run(context -> {
            // Assert beans here.
        });
```

This test is useful for verifying conditions, properties, bean creation, and back-off. However, it **passes the class directly into the context via test code**. As a result, the test can still pass even if the JAR contains no imports file, the file is at the wrong path, or the class name line has a typo.

These are two different questions:

| Test type | What does it verify? | Does it verify the imports resource? |
| --- | --- | :---: |
| `ApplicationContextRunner` + `AutoConfigurations.of(...)` | Internal logic of the auto-configuration | No |
| Reading the resource directly from the JAR | Packaged path and class names | Yes |
| Consumer using `@EnableAutoConfiguration` / `@SpringBootTest` | Whether Boot actually discovers and applies the auto-configuration from the classpath | Yes, via runtime flow |
| Using only `@Import(AuditAutoConfiguration.class)` | Importing the class as requested by test/app | Does not prove discovery |

A starter test suite should keep both condition unit tests and consumer integration tests. Unit tests are fast and isolate bugs; consumer tests verify the finished artifact.

### 2.2. Do not rely on component scanning to load auto-configurations

Auto-configurations must be loaded via the imports resource. Placing the class in a package scanned by `@SpringBootApplication` can let tests find the class even when the imports file is missing.

To make discovery tests meaningful:

- Place auto-configuration classes in the library's own dedicated package.
- Do not declare a broad `@ComponentScan` covering that package.
- In the consumer smoke test, use `@SpringBootConfiguration` and `@EnableAutoConfiguration` without adding `@ComponentScan`.
- Do not directly `@Import` the auto-configuration class in discovery tests.

Spring Boot recommends keeping auto-configurations in a dedicated package that is not targeted by component scanning and does not itself enable component scanning to find more components. Use explicit `@Import` for supporting configurations.

### 2.3. Nested auto-configuration classes

If an imports file needs to reference a nested auto-configuration (not top-level), the class name uses `$`:

```text
com.acme.OuterAutoConfiguration$NestedAutoConfiguration
```

Do not use a dot instead of `$`. Whenever possible, prefer declaring top-level auto-configurations so the resource is easier to read and safer to refactor.

## 3. Building the sample library

We create two artifacts following the standard starter layout:

```text
acme-audit/
├── acme-audit-spring-boot-autoconfigure/
│   └── src/main/
│       ├── java/com/acme/audit/
│       │   ├── AuditMarker.java
│       │   └── autoconfigure/AuditAutoConfiguration.java
│       └── resources/META-INF/spring/
│           └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
└── acme-audit-spring-boot-starter/
    └── pom.xml
```

The autoconfigure module holds the classes and the imports resource. The starter simply aggregates dependencies on the autoconfigure module and the dependencies required for the default experience.

### 3.1. Marker bean for testing

File `AuditMarker.java`:

```java
package com.acme.audit;

public record AuditMarker(String origin) {
}
```

This is a simple bean with no network, database, or external system connections. Tests can confirm the auto-configuration was applied by checking this bean.

### 3.2. Auto-configuration

File `AuditAutoConfiguration.java`:

```java
package com.acme.audit.autoconfigure;

import com.acme.audit.AuditMarker;

import org.springframework.boot.autoconfigure.AutoConfiguration;
import org.springframework.boot.autoconfigure.condition.ConditionalOnMissingBean;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.context.annotation.Bean;

@AutoConfiguration
@ConditionalOnProperty(
        prefix = "acme.audit",
        name = "enabled",
        havingValue = "true")
public class AuditAutoConfiguration {

    @Bean
    @ConditionalOnMissingBean
    public AuditMarker auditMarker() {
        return new AuditMarker("auto-configuration");
    }
}
```

The `acme.audit.enabled=true` condition lets the test clearly control when the bean should appear. `@ConditionalOnMissingBean` lets applications supply their own bean to replace the default.

This class belongs in the autoconfigure module, with compile dependencies on `spring-boot-autoconfigure` and `AuditMarker`.

### 3.3. Imports resource

Create the exact file:

```text
acme-audit-spring-boot-autoconfigure/
└── src/main/resources/META-INF/spring/
    └── org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Content:

```text
com.acme.audit.autoconfigure.AuditAutoConfiguration
```

Do not add quotes, commas, or annotations to the class name line. Do not place the file at `META-INF/spring.factories` to register auto-configurations using the legacy Boot 2.x mechanism. For Spring Boot 3.x, use this dedicated imports resource.

### 3.4. Minimal POM for autoconfigure

Required dependency example:

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-autoconfigure</artifactId>
    </dependency>
</dependencies>
```

The Spring Boot version should be managed by a parent or the `spring-boot-dependencies` BOM in the project. Do not hard-code mismatched versions for `spring-boot-autoconfigure` and `spring-boot-test`.

### 3.5. Minimal POM for starter

```xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter</artifactId>
    </dependency>

    <dependency>
        <groupId>com.acme</groupId>
        <artifactId>acme-audit-spring-boot-autoconfigure</artifactId>
        <version>1.0.0-SNAPSHOT</version>
    </dependency>
</dependencies>
```

The starter does not need to contain the auto-configuration classes itself. It pulls in the autoconfigure module as a regular dependency so the resource is distributed inside that artifact.

## 4. Creating an independent consumer integration test

This is the most important step. The consumer must resolve the **installed/published JAR**, not the class output of the autoconfigure module in the same Maven reactor.

Project structure:

```text
consumer-it/
├── pom.xml
└── src/test/java/example/consumer/
    ├── ConsumerApplication.java
    └── StarterJarDiscoveryTest.java
```

This project sits outside the library's build reactor or is run via a separate Maven invocation after the library has been installed into the local repository.

### 4.1. Consumer POM

`pom.xml`:

```xml
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0
         https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>

    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.3.13</version>
        <relativePath/>
    </parent>

    <groupId>example.consumer</groupId>
    <artifactId>acme-audit-consumer-it</artifactId>
    <version>1.0.0</version>

    <properties>
        <java.version>17</java.version>
    </properties>

    <dependencies>
        <dependency>
            <groupId>com.acme</groupId>
            <artifactId>acme-audit-spring-boot-starter</artifactId>
            <version>1.0.0-SNAPSHOT</version>
        </dependency>

        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-test</artifactId>
            <scope>test</scope>
        </dependency>
    </dependencies>
</project>
```

The starter dependency pulls the autoconfigure module onto the runtime classpath. The test does not need to declare the auto-configuration class directly as an import.

### 4.2. Consumer application without component-scanning the library

File `ConsumerApplication.java`:

```java
package example.consumer;

import org.springframework.boot.SpringBootConfiguration;
import org.springframework.boot.autoconfigure.EnableAutoConfiguration;

@SpringBootConfiguration
@EnableAutoConfiguration
public class ConsumerApplication {
}
```

Do not add `@ComponentScan` or `@Import(AuditAutoConfiguration.class)`. That way, when `AuditMarker` appears, the test can trace it directly to Boot's auto-configuration discovery flow.

If using `@SpringBootApplication`, that annotation includes component scanning. In that case, make sure the scanned package does not accidentally scan the library's auto-configuration package, otherwise the test could pass via a different loading path.

## 5. Test: verifying the resource and discovery from the JAR

This test locates the JAR containing `AuditAutoConfiguration`, opens the JAR, and verifies:

1. The artifact is actually a JAR file, not a `target/classes` directory.
2. The resource sits at the exact path `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
3. The resource content contains the exact FQCN of `AuditAutoConfiguration`.
4. Spring Boot creates the bean when the consumer enables the property.

File `StarterJarDiscoveryTest.java`:

```java
package example.consumer;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.List;
import java.util.jar.JarEntry;
import java.util.jar.JarFile;

import com.acme.audit.AuditMarker;
import com.acme.audit.autoconfigure.AuditAutoConfiguration;

import org.junit.jupiter.api.Test;

import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.context.ApplicationContext;

import static org.assertj.core.api.Assertions.assertThat;

@SpringBootTest(
        classes = ConsumerApplication.class,
        properties = "acme.audit.enabled=true")
class StarterJarDiscoveryTest {

    private static final String IMPORTS_PATH =
            "META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports";

    @Autowired
    private ApplicationContext context;

    @Test
    void autoConfigurationImportsFileIsPackagedInItsJar()
            throws Exception {

        var codeSource =
                AuditAutoConfiguration.class
                        .getProtectionDomain()
                        .getCodeSource();

        assertThat(codeSource)
                .as("Auto-configuration class must come from a dependency artifact")
                .isNotNull();

        URL location = codeSource.getLocation();
        Path jarPath = Path.of(location.toURI());

        assertThat(Files.isRegularFile(jarPath))
                .as("Expected a packaged JAR, not target/classes: " + jarPath)
                .isTrue();

        assertThat(jarPath.getFileName().toString())
                .endsWith(".jar");

        try (JarFile jar = new JarFile(jarPath.toFile())) {
            JarEntry imports = jar.getJarEntry(IMPORTS_PATH);

            assertThat(imports)
                    .as("Imports resource must be inside the autoconfigure JAR")
                    .isNotNull();

            List<String> classNames;

            try (BufferedReader reader = new BufferedReader(
                    new InputStreamReader(
                            jar.getInputStream(imports),
                            StandardCharsets.UTF_8))) {

                classNames = reader.lines()
                        .map(String::trim)
                        .filter(line -> !line.isEmpty())
                        .filter(line -> !line.startsWith("#"))
                        .toList();
            }

            assertThat(classNames)
                    .contains(AuditAutoConfiguration.class.getName());
        }
    }

    @Test
    void bootDiscoversAutoConfigurationFromTheConsumerClasspath() {
        assertThat(context.getBeansOfType(AuditMarker.class))
                .hasSize(1);

        assertThat(context.getBean(AuditMarker.class).origin())
                .isEqualTo("auto-configuration");
    }
}
```

This test runs inside the consumer project. It does not call `AutoConfigurations.of(...)`. `@SpringBootTest` builds the context using `SpringApplication`, and `@EnableAutoConfiguration` triggers searching for imports resources on the classpath.

The resource test inspects the exact artifact containing the auto-configuration class. If the consumer project accidentally resolves module source/classes instead of a JAR, `Files.isRegularFile` fails and pinpoints the test setup issue.

### 5.1. Why are both assertions needed?

| Check | Fault detected |
| --- | --- |
| Reading the JAR and checking the imports resource | Missing file, wrong path, wrong FQCN, or class coming from a build directory rather than a JAR |
| Booting context and checking `AuditMarker` | Boot failing to discover/apply auto-configuration, or broken condition/bean behavior |

Checking the resource answers "is the file inside the artifact with the right line?". Checking the context answers "did Boot actually use that artifact?". Both passing together is stronger evidence than only reading the resource or only asserting the bean.

## 6. Building in the right order so tests do not accidentally use target/classes

With multi-module Maven, if the consumer integration test lives in the same reactor, Maven may resolve the module dependency to the build output directory of the module being built. In that case, code source can point to compiled class directories instead of the packaged JAR.

A simple, controllable approach:

1. Build and install the library into the local Maven repository.
2. Run the consumer project via a separate Maven invocation.
3. Consumer dependencies reference the exact installed GAV/version.
4. The test verifies the code source is a JAR file.

Example:

```bash
mvn -f acme-audit/pom.xml clean install
```

After that command finishes:

```bash
mvn -f consumer-it/pom.xml clean verify
```

If the library parent has multiple modules, `clean install` must build both autoconfigure and starter in reactor order. Do not skip the install step if the consumer uses a snapshot version that just changed.

In CI, you can use two jobs or two stages:

- Stage 1: build/test/install or publish artifacts.
- Stage 2: create a clean consumer workspace, resolve the artifact from the repository, and run integration tests.

If using a remote repository, the consumer must resolve the exact version just published; a unique build version can prevent stale snapshot caching.

### 6.1. Useful Maven commands

Verify dependencies resolve from the expected coordinates:

```bash
mvn -f consumer-it/pom.xml dependency:tree -Dincludes=com.acme
```

Inspect a specific dependency:

```bash
mvn -f consumer-it/pom.xml dependency:tree -Dincludes=com.acme:acme-audit-spring-boot-autoconfigure
```

If output shows the dependency coming from an old version or another profile, fix consumer dependencies/repositories before blaming the imports file.

## 7. Inspecting the JAR manually when tests fail

Automated tests are the primary guardrail. When a test fails, inspect the artifact with JDK tools to diagnose packaging issues.

### 7.1. Check whether the JAR has the resource

```bash
jar tf acme-audit-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar
```

Filter specifically for the imports file on Linux/macOS:

```bash
jar tf acme-audit-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar | grep AutoConfiguration.imports
```

PowerShell:

```powershell
jar tf acme-audit-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar |
    Select-String "AutoConfiguration.imports"
```

The output must contain literally:

```text
META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Looking only at `target/classes` or the source tree is not enough. A resource can exist in the project yet be excluded from the JAR by resource rules or packaging plugins.

### 7.2. Read the resource content inside the JAR

If `unzip` is available:

```bash
unzip -p acme-audit-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Or extract just that resource into a temporary directory:

```bash
jar xf acme-audit-spring-boot-autoconfigure-1.0.0-SNAPSHOT.jar META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

Then read the extracted file. `jar xf` writes the resource into the current working directory; run it in a temporary directory to avoid overwriting project files of the same name.

Verify the content has the line:

```text
com.acme.audit.autoconfigure.AuditAutoConfiguration
```

Do not add trailing semicolons, quotes, or a `class` prefix. The imports file is a plain text list of class names, one per line.

### 7.3. Distinguishing source resources from packaged resources

| Location | What does it prove? |
| --- | --- |
| `src/main/resources/META-INF/spring/...` | The developer created the file in the source tree |
| `target/classes/META-INF/spring/...` | Maven copied the resource into the output directory |
| Inside the JAR | The released artifact actually contains the resource |
| Consumer classpath + SpringApplication | Boot can discover the resource from the dependency |

Only the last two steps verify the contract received by starter users.

## 8. Deliberate fault testing to prove tests catch regressions

A good regression test must fail when the imports file is broken. You can run negative controls in a separate working branch or artifact fixture.

### 8.1. Case A: deleting the imports resource entirely

Temporarily remove the file from the autoconfigure module, rebuild the JAR, and install the new test version.

Expected:

- The JAR-reading test fails because `jar.getJarEntry(IMPORTS_PATH)` returns null.
- The consumer context does not receive `AuditAutoConfiguration` via auto-configuration discovery.
- When `acme.audit.enabled=true`, `AuditMarker` does not appear; the bean discovery test fails.

Do not hard-code expectations around a specific startup exception for a missing file. Usually the auto-configuration is simply not loaded, so the context may still start while the expected bean is absent.

### 8.2. Case B: wrong resource path

For example, placing it mistakenly at:

```text
META-INF/org.springframework.boot.autoconfigure.AutoConfiguration.imports
```

or:

```text
META-INF/spring/AutoConfiguration.imports
```

The JAR test fails because it does not find the entry at the standard path. Boot likewise does not treat resources at other locations as the auto-configuration list.

### 8.3. Case C: wrong FQCN

For example, the resource states:

```text
com.acme.audit.autoconfigure.AuditAutoConfig
```

while the actual class is `AuditAutoConfiguration`.

The resource test fails because the list does not contain `AuditAutoConfiguration.class.getName()`. When Boot processes the invalid entry, the context may fail while loading the configuration class or fail to register the expected bean, depending on the naming mistake. Do not rely on a fixed exception message; checking exact FQCN matching catches the bug earlier.

### 8.4. Case D: class moved to another package, resource still old

Refactor:

```text
com.acme.audit.autoconfigure.AuditAutoConfiguration
```

to:

```text
com.acme.audit.boot.AuditAutoConfiguration
```

If you forget to update the imports resource, the test comparing against `AuditAutoConfiguration.class.getName()` fails. This is the benefit of using the class literal in the assertion to obtain the expected FQCN instead of copying an independent test string.

### 8.5. Case E: resource lists the right class, yet auto-configuration is skipped by a condition

Here the JAR test still passes because the resource is right. The consumer test may not see the bean because:

- `@ConditionalOnProperty` does not match.
- `@ConditionalOnClass` cannot find a required dependency.
- `@ConditionalOnBean` or `@ConditionalOnMissingBean` is not satisfied.
- The application already supplied an override bean.
- The auto-configuration was excluded via `spring.autoconfigure.exclude` or `@EnableAutoConfiguration(exclude=...)`.

This is why resource tests must be kept distinct from context tests. If the resource is right yet the bean does not appear, inspect the condition report and consumer inputs before modifying the imports file.

## 9. Common packaging mistakes

### 9.1. Placing the file in the wrong source directory

Maven/Gradle by default copy resources from `src/main/resources`. If placed under `src/test/resources`, the file exists only on the test classpath, not in the released JAR.

This is a dangerous mistake because tests inside the autoconfigure module itself can see the test resource and pass. Consumer projects lack that resource so the auto-configuration disappears.

### 9.2. Wrong casing

Resource paths are case-sensitive entry names inside a JAR. On a Windows filesystem, casing mismatches can go unnoticed during development. Linux CI builds will expose the bug.

Keep the exact name:

```text
AutoConfiguration.imports
```

Do not use `Autoconfiguration.imports`, `AutoConfigurations.imports`, or other variants.

### 9.3. Resource filtering altering the file

Imports files usually contain only FQCNs, yet if the build enables filtering for all resources, special characters or placeholder-like strings may be modified.

Configure resource filtering intentionally. In Maven, exclude the imports resource from filtering if the project enables global filtering. In Gradle, avoid custom tasks treating the file as a template. After building, always inspect the contents inside the JAR.

### 9.4. Shading/uber-JAR overwriting identically named resources

If multiple dependencies are packaged into an uber-JAR via shading, several JARs may contain `AutoConfiguration.imports`. If the plugin keeps only the last resource, lists from other dependencies can be lost.

When using Maven Shade Plugin or an equivalent tool:

- Configure an appropriate resource transformer/appender to **merge the contents** of imports resources.
- Do not let identically named resources overwrite each other depending on dependency order.
- After shading, inspect the final list to ensure classes from all required artifacts are present.
- Run the consumer smoke test against the produced uber-JAR itself.

If the application uses Spring Boot's standard executable JAR, dependencies typically live in nested JARs; there is no need to flatten all dependencies just to load auto-configurations. Avoid shading unless there is a specific deployment requirement.

### 9.5. Mistakenly using Boot 2's spring.factories

In Boot 2, auto-configurations were commonly registered under the `EnableAutoConfiguration` key in `META-INF/spring.factories`. In Boot 3, register candidates via `META-INF/spring/org.springframework.boot.autoconfigure.AutoConfiguration.imports`.

When upgrading a library from Boot 2 to Boot 3:

- Move the auto-configuration list to the imports resource.
- Check FQCNs if packages moved.
- Update consumer tests to use Boot 3.
- Do not delete other `spring.factories` entries still needed for separate compatible extension points; remove only the old auto-configuration registration once Boot 2 is no longer targeted.

### 9.6. Resource exists only in starter, not in autoconfigure

Boot searches imports resources across the entire classpath, so a resource in the starter could still list classes from another dependency. However, the maintainable structure is to keep the file in the module that owns the auto-configurations.

When testing the artifact, inspect the exact JAR containing the auto-configuration class. This catches cases where the resource was mistakenly moved into a starter aggregator or another module, keeping the packaging contract clean.

## 10. Reading the condition report when the resource is right yet the bean is missing

If the JAR test passes yet the consumer context lacks the bean, enable debug mode by setting `debug=true` in the consumer test/application or running the app with `--debug`. Read the Condition Evaluation Report to distinguish:

- Whether the auto-configuration was imported and which conditions matched/did not match.
- Whether a property or classpath condition excluded the configuration.
- Whether a bean condition backed off because a user bean already existed.
- Whether the auto-configuration was excluded or not selected.

If Actuator is present and an appropriate endpoint is exposed, `/actuator/conditions` can also provide the report. Do not expose diagnostic endpoints publicly just to debug a packaging error.

If the auto-configuration source does not appear in the report at all, revisit imports candidates, classpath, and exclusions. If the source appears with a condition non-match, imports discovery already succeeded; fix the condition inputs or user configuration instead.

## 11. Scaling to multiple auto-configurations

An imports file can list multiple classes:

```text
com.acme.audit.autoconfigure.AuditAutoConfiguration
com.acme.audit.autoconfigure.AuditWebAutoConfiguration
com.acme.audit.autoconfigure.AuditMetricsAutoConfiguration
# Reactive integration is loaded from a separate optional artifact
```

Each class can have its own conditions. Consumer tests should verify the capabilities the starter promises to provide:

| Auto-configuration | Example condition | Consumer assertion |
| --- | --- | --- |
| `AuditAutoConfiguration` | Core SDK present, feature enabled | `AuditMarker` present |
| `AuditWebAutoConfiguration` | Servlet web application | Web adapter present |
| `AuditMetricsAutoConfiguration` | Actuator present | Metrics contributor present |
| `AuditReactiveAutoConfiguration` | Reactive context and reactive SDK present | Reactive adapter present |

A single test does not need to verify every integration. Split consumer fixtures by optional dependency to avoid pulling every SDK onto one test classpath and accidentally masking missing-dependency bugs.

When multiple imports resources come from multiple artifacts, Boot reads candidates from resources across the classloader. Therefore, never assume there is only one imports file on the entire application classpath. Direct JAR tests verify your artifact; consumer tests verify the combined set of resources the application actually sees.

## 12. Recommended CI pipeline

A concise, high-value pipeline:

```text
Compile & unit tests
        |
        v
Package autoconfigure + starter JAR
        |
        v
Inspect JAR entries and imports content
        |
        v
Install/publish artifacts
        |
        v
Build isolated consumer project
        |
        v
SpringApplication discovery smoke test
        |
        v
Dependency and condition diagnostics
```

Steps to ensure:

1. Condition unit tests run inside the autoconfigure module.
2. The build produces real JARs.
3. Packaging assertions inspect the JAR entry and FQCNs.
4. Artifacts are installed/published with a deterministic version.
5. A separate consumer project depends solely on the published starter.
6. `@SpringBootTest` confirms default beans appear when properties are enabled.
7. At least one negative control exists for a missing resource or wrong class name in the dev/CI fixture workflow.
8. Dependency tree and condition report are saved when the smoke test fails for quick diagnosis.

You can keep a consumer fixture inside the repository while running it as a separate build after installing the artifacts. What matters is that dependencies are resolved like an external user, without the reactor substituting an output directory.

## 13. Symptom-based diagnostic checklist

| Symptom | First check | Common cause |
| --- | --- | --- |
| Unit tests pass, consumer lacks bean | Does consumer use `@EnableAutoConfiguration` and was the JAR published? | Unit tests imported directly, bypassing discovery |
| JAR lacks imports resource | `jar tf` and build resource config | File placed in wrong source path or excluded during packaging |
| Resource exists in JAR with wrong content | Read entry via `unzip -p` or `JarFile` | FQCN typo, stale class after refactor, filtering |
| Resource is right yet context lacks bean | Condition Evaluation Report | Property/class/bean condition did not match |
| Context fails because class cannot load | Imports FQCN and whether class exists in JAR/dependency | Entry points to non-existent class or missing dependency |
| Tests pass on Windows yet fail on Linux | Check path casing | Local filesystem masked wrong resource name |
| Some other auto-configurations vanish after shading | Compare imports before and after shading | Identically named resources overwritten instead of appended |
| Consumer test passes accidentally when resource is missing | Check component scan and `@Import` | Auto-configuration loaded via another path |
| Code source is `target/classes` | Check reactor/build invocation | Consumer is using project output, not testing the JAR |
| JAR test finds no entry yet Boot still discovers it | Check if resource lives in another dependency JAR | Resource placed in wrong artifact yet still on classpath |

## 14. Pre-release review checklist

- [ ] Auto-configuration classes have `@AutoConfiguration`.
- [ ] Imports resource sits in `src/main/resources/META-INF/spring/`.
- [ ] File name is literally `org.springframework.boot.autoconfigure.AutoConfiguration.imports`.
- [ ] Each line is a valid FQCN with no quotes or commas.
- [ ] Nested classes use `$` if needed.
- [ ] Auto-configuration does not rely on component scanning to be loaded.
- [ ] Packaged JAR contains the resource at the exact path.
- [ ] A test reads the JAR containing the class to verify the resource and FQCN.
- [ ] An independent consumer project uses the installed/published starter.
- [ ] The consumer uses `@EnableAutoConfiguration` without importing the class directly.
- [ ] Consumer tests verify beans appear according to defined properties/conditions.
- [ ] Negative controls exist for missing files, wrong paths, or wrong FQCNs.
- [ ] If shading is used, imports resources are appended/merged properly.
- [ ] If upgrading from Boot 2, auto-configuration registration has been migrated to the Boot 3 imports file.
- [ ] CI tests the published artifact, not only the source tree or `target/classes`.

**Takeaway:** `ApplicationContextRunner` with `AutoConfigurations.of(...)` tests auto-configuration logic yet bypasses imports discovery. To catch missing or broken resources, inspect the packaged JAR directly and run an independent consumer project via `@EnableAutoConfiguration`/`SpringApplication`. The first test verifies the file and FQCN; the second verifies that Spring Boot actually discovers and applies the configuration from the artifact. That is the evidence starter users experience.

## Official Documentation

- Spring Boot 3.3.13 — Creating Your Own Auto-configuration, locating candidates and imports resource: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13 — Testing Auto-configuration with `ApplicationContextRunner`: https://docs.spring.io/spring-boot/3.3/reference/features/developing-auto-configuration.html
- Spring Boot 3.3.13 — Testing Spring Boot Applications and `@SpringBootTest`: https://docs.spring.io/spring-boot/3.3/reference/testing/spring-boot-applications.html
- Spring Boot 3.3.13 API — `@AutoConfiguration`: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfiguration.html
- Spring Boot 3.3.13 API — `AutoConfigurations` test utility: https://docs.spring.io/spring-boot/3.3/api/java/org/springframework/boot/autoconfigure/AutoConfigurations.html
