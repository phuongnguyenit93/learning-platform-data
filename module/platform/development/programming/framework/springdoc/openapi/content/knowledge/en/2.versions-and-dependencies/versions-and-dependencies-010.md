# Locking Versions and Inspecting the Dependency Tree

A Spring Boot application may run fine on a developer's machine yet fail after a library update or when built in another environment. The cause often lies in dependency versions resolving differently, a transitive library pulling in an incompatible version, or multiple modules in the same ecosystem being mixed.

With `springdoc-openapi`, version management must start from the Spring Boot version and the application's web stack. Only then choose the right springdoc line, lock the version directly, and inspect transitive libraries such as Swagger Core, Swagger UI, Spring Framework, and Jackson. The dependency tree shows which versions actually enter the classpath; the build file only shows what the project requested.

## 1. Why Lock Versions?

When declaring a dependency, a project can request a specific version or a version range. The build tool continues resolving the transitive dependencies needed by that library. The end result is a set of libraries placed on the classpath to compile, test, and run the application.

Without version control, different builds can produce different results due to:

- Dynamic version declarations such as `2.+`, `latest.release`, or version ranges.
- Transitive dependencies updated in a Maven repository.
- Multiple libraries requesting different versions of the same module.
- A BOM or dependency management changing after upgrading Spring Boot.
- Build plugins, repositories, or CI configs using different versions than the development machine.

Locking versions makes a build reproducible with the same set of libraries. It also makes upgrade reviews easier: version changes appear clearly in config files or lockfiles instead of silently changing at build time.

Locking versions does not prove two libraries are compatible with each other. The project still needs to choose the right version line, inspect the dependency tree, and run tests on the actual application.

## 2. Choosing a springdoc Line Compatible with Spring Boot

`springdoc-openapi` integrates deeply with Spring Boot, Spring Framework, Spring Web MVC/WebFlux, and serialization libraries. Therefore, do not choose a springdoc version independently of the Spring Boot version.

According to the compatibility table in springdoc documentation at the time of writing, the main lines relate as follows:

| Spring Boot | Published compatible springdoc line |
|---|---|
| 4.1.x | 3.1.x to 3.2.x |
| 4.0.x | 3.0.x |
| 3.5.x | 2.8.x to 2.10.x |
| 3.4.x | 2.7.x to 2.8.x |
| 3.3.x | 2.6.x |
| 3.2.x | 2.3.x to 2.5.x |
| 3.1.x | 2.2.x |
| 3.0.x | 2.0.x to 2.1.x |

Older Spring Boot lines may require springdoc 1.x and legacy artifact declarations. The 1.8.0 line is noted in current documentation as the end-of-open-source-support release for Spring Boot 1.x/2.x. For projects under maintenance, check the exact documentation for that version branch rather than copying examples from newer line guides.

The compatibility table can change as Spring Boot or springdoc releases new versions. Before upgrading, check the official table at [springdoc-openapi compatibility](https://springdoc.org/#what-is-the-compatibility-matrix-of-springdoc-openapi-with-spring-boot-) or the corresponding 2.x branch documentation at [springdoc.org/v2](https://springdoc.org/v2/).

### 2.1. Choosing the Right Starter

In modern springdoc lines, starter artifacts indicate the web stack and UI needs:

| Application | Common Artifact |
|---|---|
| Spring MVC, with Swagger UI | `springdoc-openapi-starter-webmvc-ui` |
| Spring MVC, OpenAPI endpoint only | `springdoc-openapi-starter-webmvc-api` |
| Spring WebFlux, with Swagger UI | `springdoc-openapi-starter-webflux-ui` |
| Spring WebFlux, OpenAPI endpoint only | `springdoc-openapi-starter-webflux-api` |

Choose MVC or WebFlux based on the stack the application runs. Do not add both starters just to test; that can pull unnecessary configuration or libraries onto the classpath. If Swagger UI is needed, pick the `*-ui` starter; if only distributing JSON/YAML to other tools, the `*-api` starter may fit better.

Within springdoc 2.x/3.x, starters share the same springdoc version. Avoid mixing starters across major lines or declaring legacy 1.x artifacts alongside new starters. Artifact names, module structure, and configuration options can differ across majors.

## 3. Locking Versions in Maven

### 3.1. Using the Spring Boot BOM and a Property for springdoc

If the project inherits `spring-boot-starter-parent`, Spring Boot already provides dependency management for many libraries in the Spring ecosystem. If not using the parent, you can import the `spring-boot-dependencies` BOM in `dependencyManagement`.

The Spring Boot BOM manages dependencies in the ecosystem it supports. Declare the springdoc version explicitly via a separate property unless documentation for the version in use specifies a different management mechanism.

The example below is for a Spring Boot 3.5.x and springdoc 2.10.0 project:

```xml
<properties>
    <springdoc.version>2.10.0</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

This example assumes the application uses Spring MVC. If it uses WebFlux, replace the artifact with the corresponding WebFlux starter. For Spring Boot 4.1.x, choose a springdoc 3.1.x or 3.2.x version per the compatibility table; for example, current documentation uses 3.2.0 for Boot 4.1.x.

When the project does not use the Spring Boot parent, the BOM can be imported as follows:

```xml
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
```

Do not manually pin individual versions for `spring-core`, `spring-web`, `spring-context`, or Jackson modules without a specific compatibility reason. Overriding versions managed by the Spring Boot BOM can create combinations untested by Spring Boot.

### 3.2. Managing Transitive Dependencies

Maven selects dependency versions using its resolution rules, where distance from the root dependency and `dependencyManagement` affect the outcome. When multiple branches request the same artifact at different versions, the dependency tree can show one selected version and others omitted.

If there is a valid reason to adjust a transitive dependency, manage its version in `dependencyManagement` at the appropriate level and document why. Do not add a direct dependency just to force a version without verifying compatibility with springdoc and Spring Boot.

Maven does not provide built-in dependency lockfiles the way Gradle does. For reproducible builds:

- Declare direct versions and build plugin versions explicitly.
- Use the chosen BOM and keep the BOM version stable.
- Avoid dynamic versions and `SNAPSHOT` dependencies in release builds.
- Use Maven Enforcer to detect conflicts or transitive versions lower than required.
- Use Maven Wrapper to pin the Maven version used by the project.
- Keep repository configuration consistent between developer machines and CI.

You can add Maven Enforcer's `dependencyConvergence` and `requireUpperBoundDeps` rules to catch certain version skew cases:

```xml
<rules>
    <dependencyConvergence/>
    <requireUpperBoundDeps/>
</rules>
```

The snippet above is the `rules` section inside the `maven-enforcer-plugin` goal configuration. Declare the plugin and plugin version in the project's `build/plugins` or `pluginManagement`. These two rules can surface conflicts needing resolution; if a version difference is intentional, explain and manage the exception explicitly.

## 4. Locking Versions in Gradle

### 4.1. Declaring Versions and the BOM

Gradle can use the Spring Boot BOM via a dependency platform. The example below illustrates Spring Boot 4.1.2 with springdoc 3.2.0:

```kotlin
val springBootVersion = "4.1.2"
val springdocVersion = "3.2.0"

dependencies {
    implementation(platform(
        "org.springframework.boot:spring-boot-dependencies:$springBootVersion"
    ))

    implementation(
        "org.springdoc:springdoc-openapi-starter-webmvc-ui:$springdocVersion"
    )
}
```

If the project already uses the Spring Boot Gradle plugin with the dependency management plugin, follow the project's existing BOM import style to avoid declaring two overlapping version management mechanisms. The Spring Boot BOM manages dependencies covered by the BOM; the springdoc version must still be selected per the compatibility table.

You can centralize versions in `gradle/libs.versions.toml` so modules share the same values:

```toml
[versions]
spring-boot = "4.1.2"
springdoc = "3.2.0"

[libraries]
spring-boot-bom = { module = "org.springframework.boot:spring-boot-dependencies", version.ref = "spring-boot" }
springdoc-webmvc-ui = { module = "org.springdoc:springdoc-openapi-starter-webmvc-ui", version.ref = "springdoc" }
```

Then reference the aliases in `build.gradle.kts`:

```kotlin
dependencies {
    implementation(platform(libs.spring.boot.bom))
    implementation(libs.springdoc.webmvc.ui)
}
```

A version catalog unifies declared versions. It does not yet lock all transitive versions resolved by Gradle; dependency locking solves that part.

### 4.2. Enabling Dependency Locking

In `build.gradle.kts`, enable locking for the required configurations:

```kotlin
dependencyLocking {
    lockAllConfigurations()
}
```

In `build.gradle` using Groovy DSL:

```groovy
dependencyLocking {
    lockAllConfigurations()
}
```

After enabling locking, run a task that resolves the dependencies to lock, for example:

```bash
./gradlew build --write-locks
```

Gradle writes resolved versions to a lockfile, typically `gradle.lockfile` at the project level. In multi-project builds, lock state can be generated per project. Commit the lockfile alongside source code so subsequent builds use the same locked versions.

When intentionally upgrading dependencies, update the version catalog or constraints first, then rerun the appropriate task with `--write-locks`, review lockfile changes, and run tests. Do not update lockfiles mechanically without inspecting which modules changed versions.

Dependency locking does not replace Gradle plugin version management. Plugins in `plugins {}` or `pluginManagement` must have stable versions declared separately.

### 4.3. Verifying Artifact Integrity

Lockfiles record resolved versions. Gradle dependency verification adds checksum or signature verification for downloaded artifacts. SHA-256 checksum metadata can be generated with:

```bash
./gradlew --write-verification-metadata sha256 build
```

This command creates or updates `gradle/verification-metadata.xml`. Review and commit this file after confirming artifacts come from trusted repositories. When a later build downloads an artifact with a mismatched checksum, Gradle fails instead of silently accepting different contents.

Do not use mutable dependencies like `SNAPSHOT` and expect a lockfile to guarantee an absolutely reproducible build. Locking versions cannot guarantee immutable artifact contents if a repository allows overwriting artifacts at the same coordinates.

## 5. Reading and Analyzing the Dependency Tree

The dependency tree shows relationships between direct and transitive dependencies. When investigating springdoc issues, focus on both the compile classpath and runtime classpath, since an application can compile cleanly yet fail at startup.

### 5.1. Maven: `dependency:tree`

View the full dependency tree:

```bash
./mvnw dependency:tree
```

Filter groups related to springdoc, Swagger, and Spring:

```bash
./mvnw dependency:tree -Dverbose \
  -Dincludes=org.springdoc:*,io.swagger.core.v3:*,org.springframework.boot:*,org.springframework:*
```

On Windows PowerShell, use `mvnw.cmd` instead of `./mvnw`:

```powershell
.\mvnw.cmd dependency:tree -Dverbose -Dincludes=org.springdoc:*,io.swagger.core.v3:*,org.springframework.boot:*,org.springframework:*
```

`-Dverbose` lets you also see nodes omitted during conflict resolution. When you need to know where Maven's final managed version comes from, export the effective POM:

```bash
./mvnw help:effective-pom -Doutput=target/effective-pom.xml
```

The effective POM shows the configuration after parent inheritance and applying profiles, properties, and dependency management. Cross-reference the effective POM with `dependency:tree` to understand declared versions versus actually selected versions.

### 5.2. Gradle: `dependencies` and `dependencyInsight`

Inspect the runtime dependency tree:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Find why a springdoc version was selected:

```bash
./gradlew dependencyInsight --dependency springdoc-openapi-starter-webmvc-ui --configuration runtimeClasspath
```

`dependencyInsight` shows which dependency requests the module, which version was chosen, and why—such as conflict resolution, constraints, or dependency locking. If the app uses WebFlux, replace the module name in the command with the WebFlux starter.

You can also inspect the compile classpath:

```bash
./gradlew dependencies --configuration compileClasspath
```

If a module appears on the compile classpath but not the runtime classpath, check the declared scope/configuration. If multiple versions appear in the report, read the selection reason to see how Gradle resolved the conflict.

## 6. Reading a Dependency Tree in a Real Scenario

Suppose an application declares:

```text
org.springdoc:springdoc-openapi-starter-webmvc-ui:3.2.0
```

This starter pulls in the modules needed for OpenAPI and Swagger UI. Transitive dependencies may include `org.springdoc` modules, `io.swagger.core.v3`, Spring libraries, and JSON libraries. Final versions of each module depend on starter metadata, BOMs, constraints, and other dependencies in the application.

When reading the output, answer in sequence:

1. Is there exactly one springdoc starter matching the MVC or WebFlux stack?
2. Are `org.springdoc` modules on the same version line?
3. Are Swagger Core and related modules pulled to a different version by another direct dependency?
4. Are Spring Framework, Spring Boot, and Jackson libraries within the ranges managed by the Spring Boot BOM?
5. Was any node omitted due to version conflicts? Is the selected version the one the project intends to use?
6. Does the runtime classpath include the modules needed to generate `/v3/api-docs` and serve Swagger UI?

Not every dependency requested at multiple versions is an error. Maven and Gradle have version selection rules; what needs verification is whether the final selected version is compatible with the entire stack. If an `exclusion` is needed, identify which dependency introduces the module into the tree and verify the replacement module provides the exact API required by the library.

## 7. Signs of a Problematic Dependency Tree

| Symptom | Possible Cause | How to Check |
|---|---|---|
| `NoSuchMethodError` or `NoClassDefFoundError` at startup | Compile-time and runtime libraries have different APIs/versions | Inspect runtime tree; look for overridden Spring or Swagger modules. |
| Bean creation or auto-configuration error | Springdoc incompatible with Spring Boot/Spring Framework line | Cross-check compatibility matrix and effective dependency tree. |
| `/v3/api-docs` errors or is missing | Wrong stack starter, missing API module, or auto-configuration not loaded | Check direct artifacts and startup logs. |
| Swagger UI fails to load document | Missing UI starter, wrong path config, or UI assets absent from runtime classpath | Check `*-ui` artifact, path config, and browser network requests. |
| Same library requested at multiple versions | Multiple direct/transitive dependencies or inconsistent BOMs | Run `dependency:tree -Dverbose` or `dependencyInsight`. |
| Runs locally but fails in CI | Differing JDK, Maven/Gradle, repositories, profiles, or lock state | Compare wrapper, toolchain, effective POM, and dependency lockfiles. |

Do not try to fix every error by upgrading all dependencies to the latest version. Find the conflicting module, identify what manages its version, and update the BOM, constraint, or direct dependency in the right place.

## 8. Safe springdoc Upgrade Procedure

When upgrading Spring Boot or springdoc, follow this sequence:

1. **Record the baseline**: save current Java, Spring Boot, springdoc, Maven/Gradle, and lockfile versions.
2. **Verify compatibility**: consult the official compatibility table for the exact Spring Boot minor; identify MVC/WebFlux and API/UI artifacts.
3. **Make controlled changes**: update springdoc or Spring Boot versions step by step; let the BOM manage Spring Framework and ecosystem libraries.
4. **Re-resolve dependencies**: run `dependency:tree` or `dependencies`/`dependencyInsight`; inspect selected versions and omitted nodes.
5. **Update locks**: in Gradle, intentionally regenerate lock state; in Maven, update BOM/properties and Enforcer rules if needed.
6. **Verify the application**: run unit tests, integration tests, start the app, and hit `/v3/api-docs`, `/v3/api-docs.yaml` if YAML is enabled, and the Swagger UI page.
7. **Compare contracts**: check whether OpenAPI changes altered schemas, operations, security, or responses that existing clients rely on.
8. **Review build changes**: commit config files, lockfiles, and relevant verification metadata; note upgrade reasons and notable changes.

Upgrading Spring Boot and springdoc at the same time makes root cause analysis harder if errors occur. In large projects, split changes into separately testable steps, especially across major versions.

## 9. Pre-Merge Checklist

- [ ] springdoc version belongs to a line compatible with the Spring Boot version in use.
- [ ] Starter matches Spring MVC or WebFlux and UI/API needs.
- [ ] springdoc modules are declared at the same version.
- [ ] Spring Framework, Spring Boot, and Jackson are managed consistently via BOM or dependency management.
- [ ] No dynamic versions or `SNAPSHOT` dependencies in release builds.
- [ ] Runtime tree inspected; conflicts and omitted dependencies explained.
- [ ] Maven Enforcer or Gradle dependency locking configured appropriately for the build system.
- [ ] Gradle lockfile and verification metadata updated, reviewed, and committed if used by the project.
- [ ] Application starts cleanly; OpenAPI JSON/YAML and Swagger UI work.
- [ ] API contract changes evaluated and tested.

## 10. References

- [springdoc-openapi: guide and compatibility table](https://springdoc.org/)
- [springdoc-openapi v2: documentation for Spring Boot 3](https://springdoc.org/v2/)
- [Gradle User Manual: Dependency Locking](https://docs.gradle.org/current/userguide/dependency_locking.html)
- [Gradle User Manual: Viewing and debugging dependencies](https://docs.gradle.org/current/userguide/viewing_debugging_dependencies.html)
- [Maven Dependency Plugin: dependency:tree](https://maven.apache.org/plugins/maven-dependency-plugin/tree-mojo.html)
- [Maven Enforcer Plugin](https://maven.apache.org/enforcer/maven-enforcer-plugin/)

Locking versions makes builds reproducible; the dependency tree explains accurately what enters the application. Combining both with the springdoc compatibility table and real endpoint checks significantly reduces version-mismatch errors during API development, integration, and release.
