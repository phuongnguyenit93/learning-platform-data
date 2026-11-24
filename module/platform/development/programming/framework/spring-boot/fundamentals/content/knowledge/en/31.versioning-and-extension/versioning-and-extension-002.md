# Reading Documentation for Your Running Version and Verifying New APIs

One common cause of errors in Spring Boot development is following an example from the Internet that belongs to a different framework version than the current project. A method may appear in newer documentation yet be absent from the library your application uses; a property may have been renamed; a starter may have been split or replaced; and a code snippet may require a newer Java baseline than your build environment.

Before adopting a new API, answer two questions:

1. **What version is the application actually running?**
2. **Is the desired API or feature supported in that exact dependency set?**

In the **Versioning and Extension** chapter of *Spring Boot Fundamentals*, this lesson guides you through reading version-matched documentation, identifying Spring Boot/Spring Framework and runtime dependency versions, consulting API references, release notes, and migration guides, and verifying new APIs through actual builds and tests.

The goal is a repeatable workflow: **identify runtime → choose matching documentation → find version/API requirements → verify dependencies → test compilation and execution → check compatibility before integrating into the application**.

## 1. Why read documentation for the running version?

Framework documentation is updated continuously. The default documentation page often displays the latest release, while your project may still be on an older release.

Example:

```text
Running project:
  Spring Boot 3.1.x
  Spring Framework 6.0.x
  Java 17

Example found on the Internet:
  Newer Spring Boot release
  Newer Spring Framework release
  Java baseline may differ

Result:
  Sample code may call an API that does not exist on the current classpath.
```

This is an illustrative diagram, not an official compatibility matrix for a specific project. Actual versions must be taken from the application's dependency management and runtime artifacts.

### 1.1. A very common scenario

You find the snippet:

```java
var client = RestClient.create();
```

Your IDE reports that `RestClient` cannot be found, or the build fails. The snippet may belong to a newer Spring Framework release than the one managed by your project's Spring Boot BOM.

At this point, there are three distinct possibilities:

- The project uses a Spring Framework version too old to include that class/API.
- The dependency containing the API is not on the compile classpath.
- The project has multiple versions or classpath skew, causing compiler and runtime to see different versions.

Looking only at the code snippet cannot distinguish these three cases. You must inspect versions and the dependency graph.

### 1.2. New documentation does not automatically apply to older applications

An API appearing in newer documentation may:

- Not exist in older releases.
- Exist only in a separate module/starter.
- Have been added in a minor release.
- Be marked experimental or incubating.
- Be deprecated or replaced in a newer release.
- Have different signatures or semantics across releases.

Therefore, consult **documentation matching your project's version** first, then read release notes for newer versions if you are considering an upgrade.

## 2. Distinguishing versions within a Spring Boot application

Saying "the project uses Spring Boot 3" is not enough to know every available API. An application has multiple version layers:

| Component | Example | Why it matters |
| --- | --- | --- |
| Spring Boot | 3.x.y | Release train, auto-configuration, starters, Boot APIs |
| Spring Framework | 6.x.y | Core container, MVC, WebFlux, transactions, validation integration |
| Java/JDK | 17, 21 | Language features, bytecode level, JVM APIs, and toolchain |
| Spring Security | Managed by BOM/constraints | Security DSL, filters, and integration |
| Spring Data | Corresponding release | Repository APIs and persistence integration |
| Hibernate | Managed or overridden version | JPA provider behavior and APIs |
| Jackson | Managed or overridden version | JSON serialization/deserialization APIs |
| Micrometer | Managed version | Metrics/observations/tracing integration |
| Servlet container | Tomcat/Jetty/Undertow version | Servlet API and web runtime behavior |
| Third-party SDK | Vendor-specific version | SDK APIs and compatibility matrix |

### 2.1. Spring Boot version is not the Spring Framework version

Spring Boot builds on Spring Framework and manages a compatible version via dependency management. For example, an application may use Spring Boot 3.x while the specific Spring Framework version is selected by Boot's BOM.

If an API belongs to package `org.springframework.web.client`, check the version of the Spring Framework artifact containing that API, not just the web starter version.

### 2.2. A starter is not the library containing every API

`spring-boot-starter-web` is a starter that pulls in the components needed for a web application. The API you are looking for might belong to:

- A Spring Framework module such as `spring-web` or `spring-webmvc`.
- A third-party library brought in by the starter.
- A separate starter such as validation, security, or data access.
- A dependency the project has not yet declared.

Thus, the right question is not just "Which Boot version?" but **which artifact contains the class/method and which version of that artifact is on the classpath?**

### 2.3. Java version is an independent axis

An API may exist in a library, yet the library's bytecode may require a newer Java runtime. The error may then be `UnsupportedClassVersionError`, or the build tool may refuse to compile due to toolchain settings.

Conversely, running a project on a newer Java version does not make new Spring APIs appear if the dependencies are still old.

Separate:

- **Java language/API level:** the compiler and JDK APIs source code is permitted to use.
- **Library API level:** which dependency version provides the class/method.
- **Runtime JDK:** the actual JVM running the application.

## 3. Identifying the project's Spring Boot version

Start with the build configuration, then verify at runtime if needed.

### 3.1. Maven: inspect parent or property

A project using the Spring Boot parent may declare:

```xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.x.y</version>
    <relativePath/>
</parent>
```

In this example, `3.x.y` is just a placeholder. Read the real version in `pom.xml` or the referenced property.

A project not using the Boot parent may import the BOM:

```xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-dependencies</artifactId>
            <version>3.x.y</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>
```

Do not just grab the first `<version>` tag in a POM and draw conclusions. A project may have another parent, multiple modules, properties, or a BOM imported at another level.

### 3.2. Maven: inspect the effective POM

Run:

```bash
./mvnw help:effective-pom
```

On Windows:

```powershell
.\mvnw.cmd help:effective-pom
```

The effective POM displays the configuration after Maven applies inheritance, properties, and dependency management. It is useful when versions are defined in a parent or BOM that the current POM does not show directly.

### 3.3. Gradle: inspect plugins and version catalogs

A project may declare the Spring Boot Gradle plugin:

```groovy
plugins {
    id 'org.springframework.boot' version '3.x.y'
}
```

Or read the version from a Gradle version catalog:

```toml
[versions]
spring-boot = "3.x.y"

[plugins]
spring-boot = {
    id = "org.springframework.boot",
    version.ref = "spring-boot"
}
```

If the version is declared in `settings.gradle`, a convention plugin, or a catalog, inspect that source. Do not infer the Boot version from an individual starter dependency when the project uses plugin/BOM management.

### 3.4. Checking versions at runtime

You can print the Spring Boot version from code:

```java
import org.springframework.boot.SpringBootVersion;

public class VersionReport {

    public static void printBootVersion() {
        System.out.println(
                "Spring Boot: " + SpringBootVersion.getVersion()
        );
    }
}
```

And the Spring Framework version:

```java
import org.springframework.core.SpringVersion;

public class FrameworkVersionReport {

    public static void printFrameworkVersion() {
        System.out.println(
                "Spring Framework: " + SpringVersion.getVersion()
        );
    }
}
```

These methods allow you to observe the framework versions present at runtime. Results may depend on packaging and artifact metadata; if they return `null` or look unclear, inspect package metadata, the dependency graph, and the artifact.

### 3.5. Recording build version in the application

In real applications, include build information in the artifact deliberately. With the Maven Spring Boot plugin, build information can be generated; with Gradle, the plugin provides a corresponding mechanism depending on the version.

When build metadata is generated and the appropriate contributor is enabled, Actuator `info` can expose part of the release/build information. For example:

```properties
management.endpoints.web.exposure.include=health,info
```

Do not expose all build metadata to the public Internet. Include only non-sensitive information and apply appropriate access controls.

### 3.6. Build file version may not be the running artifact

A deployment might be running:

- An older image because the pipeline has not updated the tag.
- An older JAR copied into the container.
- An artifact from another module.
- Another process holding the port.
- A different profile/configuration than local.

When investigating production, verify **the running artifact/image digest or build ID**, not just `pom.xml` in the latest repository commit.

## 4. Choosing the right Spring Boot documentation set

The official Spring Boot documentation site has distinct sections:

- Reference Documentation: guides for configuring and using the framework.
- API Documentation/Javadoc: detailed classes, interfaces, methods, annotations, and contracts.
- Release Notes: changes between releases.
- Migration Guide: notes for upgrading between version lines.
- Dependency Versions: library versions managed by Spring Boot.

Starting points:

- <Link url="https://docs.spring.io/spring-boot/" title="Spring Boot documentation"/>.
- <Link url="https://docs.spring.io/spring-framework/reference/" title="Spring Framework reference"/>.
- <Link url="https://docs.spring.io/spring-boot/api/java/" title="Spring Boot API documentation"/>.

Official sites may change navigation across releases. Use the version selector or version-specific URLs on the documentation site instead of assuming the current URL always points to your project's release.

### 4.1. Using the version selector

When opening Reference Documentation:

1. Check which version is currently displayed on the page.
2. Select the exact version used by your application.
3. Read the corresponding content in the Reference Guide.
4. Open the API Javadoc for the same release if you need class/method details.
5. Check release notes/migration guides when an API is missing or has changed.

If the default page shows "current" or "latest," that does not mean your project uses that release.

### 4.2. Do not mix Reference Guide and Javadoc from two versions

The Reference Guide may describe configuration conceptually. Newer Javadoc may list a method that does not exist in an older version.

When a guide says "call method X," check method X in the Javadoc **for the exact same version as the resolved dependency**. If the Javadoc shows the method only in a newer release, you must either upgrade or choose a compatible approach.

### 4.3. Spring Boot docs vs. Spring Framework docs

Not every API in a Spring Boot application belongs to Spring Boot.

Examples:

- `@SpringBootApplication`: Spring Boot.
- `SpringApplication`: Spring Boot.
- `ApplicationContext`: Spring Framework.
- `@Transactional`: Spring Framework abstraction.
- `RestClient`: Spring Framework web client API.
- `@PreAuthorize`: Spring Security.
- `JpaRepository`: Spring Data.

Consulting the right project's documentation avoids looking up the wrong API version. If an API belongs to Spring Security, read Spring Security documentation for the version managed by Boot.

## 5. Finding API details in Javadoc

When adopting a new class or method, API documentation is the most accurate place to verify it.

### 5.1. Locate class and package

First identify:

- Full class/interface name.
- Package.
- Containing artifact/module.
- Whether the API is public or only an internal implementation.

Example:

```java
import org.springframework.web.client.RestClient;
```

The package indicates the API belongs to the Spring Framework Web module. From there, check the version of the artifact containing the class rather than only checking the top-level starter.

### 5.2. Check the method signature

Javadoc provides:

- Method name and visibility.
- Parameter types.
- Return type.
- Generic bounds.
- Declared checked exceptions.
- Overloads.
- Documented contracts and side effects.

Two methods with the same name can have different signatures. Do not match only the method name and assume the API exists.

### 5.3. Check @since

Javadoc often includes `Since` or `@since` showing which release introduced the API.

Illustrative example:

```java
/**
 * Creates a client with default settings.
 *
 * @since 6.1
 */
public static RestClient create() {
    // ...
}
```

This only illustrates how Javadoc expresses versions, not a verbatim quote of a specific API's documentation.

If an API is marked since Spring Framework 6.1, confirm whether your application actually has a compatible Spring Framework version. Do not assume all Spring Boot 3.x releases include that API; different Boot minor releases manage different Framework versions.

### 5.4. Check deprecated and forRemoval

Javadoc/annotations may indicate that an API is deprecated:

```java
@Deprecated(since = "x.y", forRemoval = true)
public void oldOperation() {
    // ...
}
```

The `since` and `forRemoval` attributes help assess the migration path:

- `since`: which version deprecated the API.
- `forRemoval`: whether it is scheduled for removal in a future release per the API contract.
- `@deprecated` Javadoc: usually recommends the replacement API.

Avoid starting a new implementation on a deprecated API when a recommended alternative exists.

### 5.5. Check whether an API is public or internal

Not every importable class is a long-term supported API. Some packages contain implementation details, internal helpers, or classes supporting auto-configuration.

Before depending on one directly:

1. Check the package and module.
2. Read the Javadoc/class description.
3. Check whether official guides use that API.
4. Check annotations or versioning policies if published by the library.
5. Prefer public abstractions designed for application code.

An internal class may change or be removed without the same compatibility promise as public APIs.

## 6. What questions do release notes and migration guides answer?

Javadoc describes a specific API. Release notes describe **what changed between versions**.

When adopting a new API, look for:

- Which release added the API?
- Is a new module/dependency required?
- Does the API replace an older one or add new functionality?
- Are there behavior changes or breaking changes?
- Is there a new minimum JDK requirement?
- Did default configurations change?
- Are there mandatory migration actions?

### 6.1. Release notes

Release notes are useful when:

- Upgrading minor/patch versions.
- Adding a new feature.
- Finding where an API was introduced.
- Investigating behavior differences between two versions.
- Looking up bug fixes or known issues.

Read release notes for **the right library line**. A Spring Framework change can be versioned independently from Spring Boot.

### 6.2. Migration guide

Migration guides typically summarize changes required when moving between release lines:

- Java baseline.
- Package namespaces.
- Removed/deprecated APIs.
- Renamed configuration properties.
- Default behavior changes.
- Auto-configuration changes.
- Dependency/module changes.

When upgrading a Spring Boot major version, do not read only the release notes of one patch release. Read the migration guidance covering every step across the major lines your project crosses.

### 6.3. Dependency versions appendix

Spring Boot documentation includes a section listing managed dependency versions. This is a useful place to see which versions of Spring Framework, Jackson, Hibernate, Micrometer, and other libraries a Boot release manages.

However, a project may override the BOM. Therefore, Boot's version table is only the **default managed baseline**, while the dependency tree/runtime artifact shows what the project actually uses.

### 6.4. Compatibility matrices of related ecosystems

If the project uses Spring Cloud, Spring Security, Spring Data, or third-party SDKs, check the compatibility information for those components themselves.

For example:

- Which Spring Cloud release train is compatible with which Spring Boot line?
- Which Spring Security DSL is present in the version in use?
- Which Spring Framework/JDK does the Spring Data module require?
- Which Boot/Jakarta/JDK versions does a vendor SDK support?

Do not rely solely on the Boot BOM and assume all external ecosystem libraries are verified compatible.

## 7. Distinguishing stable, snapshot, milestone, and release candidate

Documentation sites may link to several release types:

| Type | General meaning | Usage |
| --- | --- | --- |
| Stable release | Stable release | Suitable for regular applications per project policy |
| Snapshot | Development build changing over time | Controlled experimentation; not treated as stable API |
| Milestone (M) | Experimental build at a development milestone | Early feature evaluation; subject to change |
| Release Candidate (RC) | Candidate build prior to official release | Pre-release testing and feedback |
| GA | General Availability, official release | Usable under compatibility/support policies |

Version suffixes may include `-SNAPSHOT`, `-M1`, `-RC1`. Do not confuse these with stable releases simply because the main version numbers match.

### 7.1. Why following snapshot docs is risky

A snapshot may:

- Contain methods not yet included in GA.
- Change signatures before release.
- Have temporary properties/configurations.
- Lack final migration guidance.

If your project uses a stable release, do not rely on snapshot Javadoc to decide whether an API is available.

### 7.2. New APIs may not carry the same stability guarantees

Some features are marked incubating/experimental or carry limited contracts. Read the API status and compatibility policy before adopting them in long-lived libraries.

## 8. Verifying a new API with a repeatable workflow

When you find a new API, follow these steps in order:

### Step 1 — State the exact API to use

Do not write vaguely "want to use the new feature." Specify:

```text
Class / annotation / method / property / endpoint:
Fully qualified name:
Expected module/artifact:
Documentation version:
First available version (if documented):
Replacement/deprecation status:
```

### Step 2 — Identify the current runtime versions

Read build files, BOM, dependency graph, and confirm running artifacts. If needed, print `SpringBootVersion.getVersion()` and `SpringVersion.getVersion()` in a reproducible environment.

### Step 3 — Identify which artifact owns the API

Find the package/class in API docs and dependency metadata. If the API lives in `spring-web`, having `spring-boot-starter-web` does not prove your resolved `spring-web` version has that method.

### Step 4 — Check @since and release notes

Confirm the first version introducing the API and read release notes/migration guides for related changes.

### Step 5 — Inspect the actual dependency graph

Use Maven dependency tree or Gradle dependency insight to verify the selected version on compile/runtime classpaths.

### Step 6 — Verify signature with Javadoc or javap

If Javadoc is unclear, inspect the actual JAR. Confirm the exact class/method/signature in the resolved artifact.

### Step 7 — Write a small compile probe

Create a minimal class/test using only the API under evaluation. Build with the project's exact dependencies. If compilation fails, check modules/versions before editing application code.

### Step 8 — Run tests on the runtime artifact

Passing compilation is not enough. Run unit/integration tests and, if needed, run the executable JAR or container image matching deployment.

### Step 9 — Evaluate migration and compatibility

If dependencies must be upgraded, check related libraries, Java baseline, release trains, and behavior changes.

### Step 10 — Record the version decision

Keep dependency management centralized, update lockfiles/CI if used by the project, and document reasons for any overrides.

## 9. Verifying APIs with the Maven dependency graph

Maven dependency tree helps identify which artifact and version the project resolves.

### 9.1. View overall dependencies

```bash
./mvnw dependency:tree
```

### 9.2. Filter the module containing the API

For example, if the API belongs to Spring Web:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework:spring-web
```

If the API belongs to Spring Core:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework:spring-core
```

These artifact names are examples; identify the actual module containing the class you are looking up.

### 9.3. View the effective POM

```bash
./mvnw help:effective-pom
```

Check:

- Boot parent/BOM version.
- Dependency management overrides.
- Explicit dependency versions.
- Exclusions.
- Scope.
- Profiles altering dependencies.

### 9.4. Verify compile/runtime scope

If an API compiles but fails at runtime, generate or inspect the runtime classpath:

```bash
./mvnw dependency:build-classpath -Dmdep.outputFile=runtime-classpath.txt
```

If an API belongs to a dependency in `test` or `provided` scope only, it may be absent from the runtime artifact. Check scope and packaging before concluding the API is unsupported.

### 9.5. Do not override a version just to make the compiler error disappear

If an API is not yet present in the Boot-managed Framework version, you can upgrade to an appropriate Spring Boot release or choose an implementation compatible with the current version.

Pinning `spring-web` alone to a newer version can misalign `spring-core`, `spring-context`, and other modules. Override a single module only with compatibility evidence and thorough testing.

## 10. Verifying APIs with Gradle dependency insight

Gradle can show why a specific version was selected.

### 10.1. View the runtime graph

```bash
./gradlew dependencies --configuration runtimeClasspath
```

### 10.2. Inspect why a module version was chosen

```bash
./gradlew dependencyInsight \
  --dependency spring-web \
  --configuration runtimeClasspath
```

The output shows:

- Selected version.
- Versions requested by other dependencies.
- Participating constraints/platforms.
- Selection reason.

### 10.3. Compare compile and runtime

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration runtimeClasspath
```

If an API is on the compile classpath but missing from runtime, check configuration and dependency declarations.

### 10.4. Check test runtime

```bash
./gradlew dependencies --configuration testRuntimeClasspath
```

A test might pass because a dependency exists only in test runtime. That does not prove application runtime can use the API.

### 10.5. Dependency locking

If the project enables dependency locking, lockfiles record resolved versions. When adding a new API, update lock state per project workflow and review the diff.

Locking makes builds reproducible, but it does not prove API compatibility. Still cross-check docs and run tests.

## 11. Using javap to verify classes and methods

Javadoc is a great API reference, but when you need to know **which methods a JAR on hand actually contains**, `javap` is very useful.

### 11.1. Identify the JAR containing the class

First locate the artifact in the dependency tree. Then use the JAR path in the Maven/Gradle cache or extracted artifact.

Example:

```bash
jar tf spring-web.jar | grep 'RestClient.class'
```

In PowerShell:

```powershell
jar tf spring-web.jar |
    Select-String 'RestClient.class'
```

### 11.2. Inspect public methods

```bash
javap -classpath spring-web.jar org.springframework.web.client.RestClient
```

To see additional members and descriptors:

```bash
javap -classpath spring-web.jar -p -s org.springframework.web.client.RestClient
```

`javap` verifies bytecode/APIs inside a specific JAR. It does not replace Javadoc for semantics, lifecycle, or recommended usage.

### 11.3. Compare two versions

To find which release added a method, download/resolve two versions in a test environment and run `javap` on each JAR.

```bash
javap -classpath spring-web-old.jar -p org.springframework.web.client.RestClient
javap -classpath spring-web-new.jar -p org.springframework.web.client.RestClient
```

Do not look only at the method name; compare parameter types, return types, visibility, and inheritance.

### 11.4. The JAR inspected must be the JAR used at runtime

If your machine has multiple versions in the local repository, inspecting the wrong JAR leads to false conclusions. Confirm the version from the dependency report and actual class origin before running `javap`.

## 12. Writing a compile probe to test a new API

A compile probe is a minimal example focused solely on the API you want to use. It isolates version/API questions from complex business code.

Example probe class:

```java
package com.example.apiprobe;

import org.springframework.web.client.RestClient;

public class RestClientProbe {

    public RestClient createClient() {
        return RestClient.create();
    }
}
```

If the current project lacks this class/method, the compiler immediately reports the missing symbol.

### 12.1. Compile probe with Maven

Place the class in the source of a test module using the application's exact parent/BOM and dependencies, then run:

```bash
./mvnw -pl catalog-service -am test
```

Or build the module containing the probe per the project structure. Do not create a throwaway project with the latest version and use its result to conclude the main application supports the API.

### 12.2. Compile probe with Gradle

```bash
./gradlew :catalog-service:compileJava
```

Use the right subproject and dependency configuration. If the API is only in test sources, run the corresponding test compile task.

### 12.3. The probe needs the exact dependency set

If a compile probe directly adds a newer version of `spring-web`, it may compile yet fail to reflect what the application runs with its current BOM.

A probe is meaningful only when it uses **the application module's exact dependency management**.

### 12.4. Passing compilation is not enough

If compiled against a newer version while the runtime artifact loads an older version, `NoSuchMethodError` or `NoClassDefFoundError` may occur.

After the compile probe, verify the runtime graph and run corresponding tests/runtime artifacts.

## 13. Verifying configuration-property APIs

Not every new API is a Java method. Spring Boot has many configuration properties bound from YAML/properties files.

Example:

```yaml
spring:
  application:
    name: catalog-service
```

When wanting to use a new property, determine:

- Does the property belong to Boot, Framework, or another library?
- Which version introduced it?
- Is there a deprecated alias or old name?
- Is the property conditional on classpath/features?
- What are its type and default value?
- Must another endpoint/feature be enabled for the property to take effect?

### 13.1. Configuration metadata

Spring Boot configuration metadata is often packaged in the resource:

```text
META-INF/spring-configuration-metadata.json
```

Metadata can describe:

- Property name.
- Type.
- Description.
- Default value.
- Deprecation information.
- Hints for IDEs.

IDE autocomplete backed by metadata helps discover properties, but **autocomplete does not replace documentation for your exact version**. A property may exist in IDE caches yet be absent from the current runtime dependency.

### 13.2. Verifying property binding

For application-defined properties:

```java
@ConfigurationProperties(prefix = "app.catalog")
public record CatalogProperties(
        int pageSize,
        Duration timeout
) {
}
```

Binding can be tested using Spring Boot configuration properties test support or a small context with property values:

```java
new ApplicationContextRunner()
        .withUserConfiguration(CatalogPropertiesConfiguration.class)
        .withPropertyValues(
                "app.catalog.page-size=50",
                "app.catalog.timeout=2s"
        )
        .run(context -> {
            assertThat(context).hasNotFailed();
            CatalogProperties properties =
                    context.getBean(CatalogProperties.class);
            assertThat(properties.pageSize()).isEqualTo(50);
        });
```

This is a test example for an application property. When checking a new framework property, ensure the right configuration class/auto-configuration reads it.

### 13.3. Misnamed properties may be silently ignored

An unbound property does not always fail startup. If a property has no consumer, the application may start while the feature does not behave as expected.

Check metadata/Javadoc, binding objects, condition evaluation, and actual behavior. Do not rely on "no error messages" to conclude a property is supported.

## 14. Verifying new annotations or features

An annotation may exist in a package yet only take effect when a corresponding processor, registrar, or auto-configuration is active.

Example annotation:

```java
@SomeNewFeature
public class FeatureConfiguration {
}
```

Passing compilation alone does not prove the feature is enabled. Check:

1. Which artifact owns the annotation.
2. Which framework/processor handles the annotation.
3. Which configuration or starter must be imported.
4. Whether the feature is conditional on properties/classpath/profiles.
5. Whether a context test proves the expected bean/behavior appears.

### 14.1. Annotation APIs can be markers or carry semantics

Some annotations merely mark metadata; others are read by component scanners, AOP, bean factories, validation engines, or compiler processors.

Read Javadoc and the reference section to understand **what processes the annotation**. Never assume placing an annotation on a class automatically activates behavior.

### 14.2. Checking auto-configuration

If a feature relies on Boot auto-configuration, inspect:

- `@ConditionalOnClass` conditions.
- `@ConditionalOnProperty` conditions.
- `@ConditionalOnBean`/`@ConditionalOnMissingBean` conditions.
- Required dependencies.
- The condition evaluation report at application startup.

An API may be present, yet if auto-configuration does not match, the feature still will not run.

## 15. Verifying new endpoints or Actuator features

An endpoint may require multiple conditions:

- Actuator dependency.
- Endpoint implementation present in the version.
- Endpoint enabled.
- Endpoint exposed over HTTP/JMX.
- Security permitting access.

For example, a 404 response might mean the endpoint is unexposed or uses a different base path—not necessarily that it does not exist in your version.

### 15.1. Separate three questions

| Question | How to verify |
| --- | --- |
| Does the endpoint exist in this version? | Reference docs/Javadoc/release notes |
| Is the endpoint enabled/exposed? | `management.*` configuration and mappings |
| Does the caller have permission? | Security configuration and HTTP response |

### 15.2. Check configuration by version

A management property may change across releases. Use the property appendix or configuration metadata for the same version. Do not copy configurations verbatim from old blogs without knowing which release they target.

## 16. Concrete example: evaluating the RestClient API

Suppose the team wants to use `RestClient` instead of an older HTTP client abstraction.

### 16.1. Identify the API owner

`RestClient` is a Spring Framework API belonging to the corresponding web/client module. Therefore, check the version of the Spring Framework artifact containing the class.

### 16.2. Cross-reference the release

Spring Framework documentation/Javadoc indicates this API was introduced in the 6.1 line. Check whether your project's Boot BOM manages Spring Framework 6.1; do not infer it from the generic "Spring Boot 3" label.

### 16.3. Check dependencies

Maven:

```bash
./mvnw dependency:tree -Dincludes=org.springframework:spring-web
```

Gradle:

```bash
./gradlew dependencyInsight --dependency spring-web --configuration compileClasspath
```

Confirm the selected version contains the API.

### 16.4. Compile probe

```java
import org.springframework.web.client.RestClient;

class RestClientProbe {
    RestClient client() {
        return RestClient.create();
    }
}
```

Compile the probe with the project's actual build. If compilation succeeds, proceed to verify the runtime classpath and tests.

### 16.5. Decision

If the current version lacks the API:

- Upgrade Spring Boot to a release managing a suitable Spring Framework version, after reviewing migration/compatibility.
- Or continue using the current client API until an upgrade is planned.
- Avoid pinning `spring-web` individually without evaluating the remaining Spring Framework modules.

The key takeaway is not memorizing a specific version number, but verifying the API owner, release requirement, and actual dependency.

## 17. Example: finding a new API in Spring Security

Suppose a tutorial uses a newer DSL in `HttpSecurity`.

Do not:

1. Copy the code.
2. See red underlines in the IDE.
3. Add the latest Spring Security version directly.
4. Treat passing compilation as complete.

Instead:

1. Identify the class/method in Spring Security.
2. Open Spring Security reference/API docs for the matching version.
3. Check method `@since`, deprecations, and migration notes.
4. Check which Spring Security version is managed by the Boot BOM.
5. Inspect the dependency tree for any overrides.
6. Write security configuration tests with MockMvc or an appropriate context.
7. Verify requests are authorized/denied with the expected behavior.

### 17.1. DSL APIs can change semantics

Two snippets may compile yet not be equivalent in authorization behavior. When changing security APIs, test:

- Anonymous requests.
- Authenticated users.
- Valid roles/authorities.
- Missing roles/authorities.
- CSRF where applicable.
- Filter ordering and exception handling.

A compile probe verifies only that the API exists, not that the security policy is correct.

## 18. Reading documentation when an API is deprecated

A deprecated API may still compile and run, but warnings should not be ignored.

Workflow:

1. Open the API's Javadoc.
2. Read `@Deprecated` and the `@deprecated` description.
3. Identify which version deprecated it.
4. Find the replacement API.
5. Read the migration guide/release notes.
6. Check whether the replacement exists in your current version or requires an upgrade.
7. Update the code and write tests verifying equivalent behavior.

### 18.1. Deprecated does not mean removed

Deprecated APIs often remain present for one or more releases. However, new code should prefer the recommended replacement.

### 18.2. Pay attention to forRemoval

If an API is marked `forRemoval = true`, plan to remove it from your codebase before upgrading to a release that may delete the API.

### 18.3. Replacements can have different semantics

Replacing an old method with a similarly named new method does not always preserve identical behavior. Read Javadoc and test real cases, especially regarding:

- Null handling.
- Default values.
- Exception behavior.
- Ordering.
- Thread-safety.
- Resource lifecycle.
- Transaction boundaries.
- Security semantics.

## 19. Reading property documentation by version

Configuration properties are a common source of compatibility issues because properties can be added, renamed, or have their defaults changed.

### 19.1. Look up properties in the reference guide

Consult the exact feature section, such as web, data, logging, Actuator, or security integration. Verify property names and configuration examples for the same version.

### 19.2. Search configuration metadata

Inside dependency JARs, metadata may reside in:

```text
META-INF/spring-configuration-metadata.json
```

You can list JAR contents and read the metadata file. If a property is absent from metadata, it does not guarantee non-existence (some properties are constructed differently), but it is a signal to investigate further.

### 19.3. Check default values

Default behavior can change between releases. An application that leaves a property unset may behave differently after an upgrade even with zero source changes.

Read migration guides/release notes for default changes, then decide whether to declare the property explicitly.

### 19.4. Do not copy blog configurations while ignoring prefixes

A property may have moved from an old prefix to a new prefix or been replaced by a different configuration. Check property deprecation metadata and migration notes.

## 20. Reading versioned documentation in a multi-module environment

A system may be structured as:

```text
root/
  catalog-service
  order-service
  notification-service
  shared-library
```

Do not assume every module shares the same dependency graph:

- Each executable service may have its own Boot plugin/BOM.
- Shared libraries might not use Spring Boot.
- Test modules may have different test dependencies.
- One service may upgrade versions before another.

### 20.1. Identify the exact module being executed

When reading documentation for `catalog-service`, inspect that module's POM/Gradle configuration. Do not inspect only the root build file if modules override dependencies.

### 20.2. Shared libraries need clear compatibility ranges

If `shared-library` uses a newer Spring Framework API, consuming services must run compatible versions. A library compiling cleanly in its own repository does not guarantee every consumer can run it.

Identify:

- Java baseline.
- Spring Framework/Spring Boot baseline if the library depends on them directly.
- Public APIs exposed by the library.
- Dependency scopes and optional dependencies.
- Consumer compatibility tests.

### 20.3. Avoid letting a library force uncontrolled framework versions

A shared library should generally avoid forcing Spring Framework/Spring Boot versions onto consuming applications without good reason. Use appropriate dependency management, declare proper dependency scopes, and let the application platform manage the release train.

The exact design depends on the library type (Spring Boot starter, auto-configuration module, or plain Java library).

## 21. API compatibility and versioning

When using an API, understand the stability level and types of changes committed by the library authors.

### 21.1. Source compatibility

Source compatibility means old source code still compiles against the new version (within the stated contract).

### 21.2. Binary compatibility

Binary compatibility means previously compiled bytecode can still link and run against the new version per contract.

An API change can keep source looking nearly identical while still breaking binary descriptors, or vice versa.

### 21.3. Behavioral compatibility

An API may still compile and link while behavior changes:

- Default timeouts.
- Null handling.
- Exception types.
- Ordering.
- Retry behavior.
- Serialization output.
- Security defaults.

Therefore, API verification does not stop at confirming a class/method exists.

### 21.4. Semantic compatibility

A method may accept the same parameters while its meaning changes. For example, a property that previously meant per-request timeout might later be interpreted as total operation timeout. Current Javadoc/release notes and integration tests catch these differences.

## 22. Verifying new APIs in CI

If a project updates its framework frequently, incorporate version/API checks into the workflow:

1. Build with reviewed dependency management.
2. Compile main/test sources.
3. Run unit tests.
4. Run context startup tests.
5. Run integration tests for new APIs.
6. Package the executable JAR.
7. Run smoke tests on the packaged artifact.
8. Check the dependency graph and vulnerability/compatibility policies.

### 22.1. Why are context tests important?

An API may compile yet auto-configuration may not activate due to missing conditions/dependencies. Context tests confirm actual beans/configurations are created.

### 22.2. Why are artifact tests important?

Tests run on the test classpath. The executable JAR runs on the packaged runtime classpath. Artifact smoke tests reveal missing dependencies or version mismatches.

### 22.3. New APIs should have regression tests

If the team upgrades to use a new method/property, add tests asserting the needed behavior. That protects the application during future framework or dependency upgrades.

## 23. Lookup and verification tools

| Tool | Question it answers |
| --- | --- |
| Spring Boot Reference Guide | How are features/configurations used in a specific release? |
| Spring Framework Reference Guide | How do Framework APIs/behaviors work? |
| Javadoc | What signatures and contracts do classes/methods/annotations have? |
| Release notes | What did a release add, change, or fix? |
| Migration guide | What needs to change when upgrading? |
| Dependency versions appendix | Which versions does the Boot BOM manage? |
| Maven `dependency:tree` | Which dependency brings in an artifact/version? |
| Maven `help:effective-pom` | What final configuration do parent/BOM/properties produce? |
| Gradle `dependencyInsight` | Why did Gradle select this version? |
| `javap` | Which class/method descriptors exist in a specific JAR? |
| IDE autocomplete | Suggests APIs/properties based on the IDE's current classpath |
| Compile probe | Does source compile against the current dependency set? |
| Context/integration test | Does the API/feature work in a Spring context/runtime? |

No single tool completely replaces the others. They provide evidence at different layers.

## 24. Documentation sources to prioritize

When verifying an API or behavior, prioritize in order:

1. **Official documentation matching the exact version** of the library in use.
2. **Javadoc for the same version** for signatures and API contracts.
3. **Official release notes/migration guides** for change history.
4. **Dependency metadata and source JARs** for resolved artifacts.
5. Official examples and sample repositories for the same release.
6. Blogs, Q&A, or videos as supplementary explanations.

Community sources can be very helpful, but verify the snippet's version. An answer valid for Spring Boot 2 may no longer apply to Boot 3 or newer releases.

### 24.1. When reading blogs or Stack Overflow

Note:

- Publication and last-updated dates.
- Spring Boot version used by the author.
- Spring Framework version.
- Java version.
- Dependency versions.
- Whether the referenced API is now deprecated/removed.

If this information is missing, treat the code snippet as a hint requiring verification.

### 24.2. When reading GitHub source

If you need to inspect implementation:

- Select the exact tag/release, not just the `main` branch.
- Read the source of the artifact version you are using.
- Distinguish public APIs from implementation details.
- Check related commits/release notes.

The development branch may already contain unreleased code.

## 25. Common errors from reading wrong-version documentation

| Symptom | Possible cause | How to check |
| --- | --- | --- |
| IDE cannot find class | API does not exist yet or module is missing | Javadoc, dependency graph, JAR contents |
| IDE has class but CI build fails | IDE cache/classpath differs from build | Run Maven/Gradle compile in a CI-like environment |
| Compiles cleanly but runtime `NoSuchMethodError` | Runtime loads an older/different version | Runtime graph, class origin, `javap` |
| Property has no effect | Property does not exist yet, wrong prefix, or condition unmatched | Reference docs, metadata, binding/conditions |
| Endpoint returns 404 | Endpoint missing, disabled, unexposed, or wrong base path | Docs, `management.*`, mappings |
| Bean is not auto-configured | Missing dependency/property or condition unmatched | Conditions report and dependency graph |
| Deprecated API warning | Code uses an older API | Javadoc and migration guide |
| `UnsupportedClassVersionError` | Runtime JDK does not support bytecode | Java toolchain and runtime version |
| Behavior differs after upgrade | Default/semantic change | Release notes, migration guide, integration tests |
| Fails only in executable JAR | Runtime packaging differs from IDE/test | Inspect nested JARs and run the actual artifact |

## 26. Common misconceptions

| Misconception | Accurate understanding |
| --- | --- |
| "The default docs page is my project's version." | The site may display the latest release; select the exact version |
| "Spring Boot version equals Spring Framework version." | Boot manages a compatible Framework version; the two numbers differ |
| "Having starter-web means every new web API is available." | APIs depend on the specific module and version |
| "Java 21 lets me use every new Spring API." | Java level and library API level are two independent axes |
| "The latest Javadoc describes my current runtime." | You need Javadoc for the resolved artifact version |
| "Seeing `@since` guarantees the classpath has the API." | `@since` only shows the introducing release; the project must still resolve that module/version |
| "IDE autocomplete means the runtime has the API." | The IDE may use a different classpath/cache than the artifact |
| "A passing compile probe means the app runs." | You must check runtime linkage, auto-configuration, and behavior |
| "A resolved dependency tree means APIs are compatible." | Resolution does not prove binary/behavioral compatibility |
| "The Boot BOM manages all third-party dependencies." | The BOM manages only artifacts within its scope |
| "Deprecated means the API has been deleted." | Deprecated APIs usually still exist but need a migration plan |
| "Release notes are only for framework authors." | Release notes help apps learn about API/default/compatibility changes |
| "An old blog post is still valid because the Java compiles." | Code may rely on APIs/configurations from another version |

## 27. Practical exercises

### Exercise 1 — Identify real versions

Open a Spring Boot project:

1. Find the Boot version in the Maven parent/BOM or Gradle plugin/catalog.
2. Print `SpringBootVersion.getVersion()` at runtime.
3. Print `SpringVersion.getVersion()`.
4. Check Java build and runtime versions.
5. Record the versions in a table.

Explain why the Boot version and Framework version do not need to match.

### Exercise 2 — Read the matching Reference Guide

Pick a feature used in the project, such as validation, Actuator, or Spring MVC.

1. Open the official docs.
2. Select the version matching the project.
3. Open the same section in a newer version.
4. Record the differences.

Do not change dependencies in the project for this exercise.

### Exercise 3 — Look up a new API

Pick a new class/method in Spring Framework or Spring Boot.

1. Find its fully qualified name.
2. Identify the artifact/module.
3. Read `@since`.
4. Verify your project's dependency version.
5. Write a compile probe.

Explain why knowing only "Spring Boot 3" is insufficient.

### Exercise 4 — Maven dependency tree

Run:

```bash
./mvnw dependency:tree -Dverbose -Dincludes=org.springframework:spring-web
```

Identify the selected `spring-web` version, dependency path, and version management source.

### Exercise 5 — Gradle dependencyInsight

Run:

```bash
./gradlew dependencyInsight --dependency spring-web --configuration runtimeClasspath
```

Record the requested version, selected version, and selection reason. Compare with `compileClasspath`.

### Exercise 6 — Inspect methods with javap

Locate a class in a resolved JAR. Run:

```bash
javap -classpath path/to/library.jar -p -s fully.qualified.ClassName
```

Find the target method and verify its parameter/return descriptors.

### Exercise 7 — Read deprecations

Find a deprecated API in the project. Record:

- Deprecated since.
- Whether `forRemoval` is set.
- Recommended replacement.
- Whether the replacement exists in the current version.

Write a test proving behavior after replacement.

### Exercise 8 — New configuration property

Pick a property from newer Boot documentation. Check whether it exists in your current dependency metadata, check `@since`/release notes if available, and test it in a context test.

Explain why a misnamed property may not cause startup to fail.

### Exercise 9 — Inspect an endpoint

Pick an Actuator endpoint. Determine:

- Does the endpoint exist in this version?
- Which dependencies are needed?
- Does it need to be enabled?
- Does it need to be exposed?
- What is the security policy?

Test different responses in a protected local environment.

### Exercise 10 — Compare docs against the artifact

Read Javadoc of a newer version and compare it against the JAR currently in your Maven/Gradle cache using `javap`.

Find an API present only in the newer version. Explain why source code cannot call it while the project uses the older version.

### Exercise 11 — Inspect the executable JAR

Build the project and inspect `BOOT-INF/lib`. Confirm the artifact contains the library version matching the dependency report. Run `java -jar` and exercise a code path using the newly added API.

### Exercise 12 — Plan an upgrade

Suppose the team wants to use a new API unsupported by the current version. Write a plan covering:

1. Target Boot version.
2. Java baseline.
3. Framework/dependency version changes.
4. Migration guides to read.
5. Dependency overrides to remove or update.
6. Tests to run.
7. Artifacts to verify.

## 28. Template notes when evaluating a new API

Before bringing an API into production code, write a short evaluation record:

```text
Feature/API:
Fully qualified name:
Owning project/module:
Artifact:
Current Spring Boot version:
Current Spring Framework version:
Current Java runtime:
API first available version:
Javadoc/reference version checked:
Release note / migration note:
Deprecated/experimental status:
Compile classpath version:
Runtime classpath version:
Required additional dependency:
Compatibility concerns:
Compile probe result:
Context/integration test result:
Executable artifact result:
Decision:
```

This template is especially useful when reviewing a pull request that bumps dependencies or introduces an API not yet used in the codebase.

## 29. Upgrade workflow when an API is missing in the current version

If you have confirmed an API is absent from current dependencies, there are three main options:

### 29.1. Keep the current version and use an alternative API

Suitable when:

- The new functionality is not strictly required yet.
- Upgrading brings many breaking changes.
- Related libraries are not yet compatible.
- The project is in a release stabilization phase.

Advantage: keeps the current dependency graph stable. Trade-off: cannot yet use the new API.

### 29.2. Upgrade Spring Boot along the release train

Suitable when:

- The new API exists in a released Boot version.
- The Java baseline is satisfied.
- Major dependencies are compatible.
- The team has capacity for migration/integration testing.

Workflow:

1. Select target Boot version.
2. Read release notes and migration guide.
3. Verify Java/JDK baseline.
4. Verify Spring Cloud and vendor compatibility.
5. Update Boot parent/plugin/BOM.
6. Remove overrides that are no longer needed.
7. Run dependency reports.
8. Build/test/package.
9. Run the executable artifact.

### 29.3. Override an individual dependency

This is a higher-risk option, appropriate only when:

- You know the exact module containing the API.
- Compatibility guidance exists for that version combination.
- Related modules remain compatible.
- Integration tests cover the code paths.
- There is a clear reason the full Boot release train cannot be upgraded yet.

Never override a single Spring Framework module just because the IDE reports a missing method and hope the remaining modules stay compatible.

## 30. How to read documentation during a major upgrade

Upgrading a major version requires broader evaluation than looking up a single new method.

### 30.1. Check baselines

Identify minimum Java, build tool versions, container/servlet APIs, framework lines, and dependency release trains.

### 30.2. Find breaking changes

Read migration guides and release notes across each upgrade step. Note removed APIs, renamed packages, behavior changes, and default changes.

### 30.3. Check source compatibility

Compile sources after updating dependencies. Address deprecations/removals and API signature changes.

### 30.4. Check runtime compatibility

Run tests, inspect the dependency graph, and run the executable artifact. Linkage errors may only surface when a specific code path is executed.

### 30.5. Check behavior

Test configuration defaults, serialization, security, transactions, database access, scheduling, and web request behavior.

### 30.6. Do not overlook third-party libraries

An application may upgrade Spring Boot cleanly while an older SDK still lacks Jakarta or new Java baseline support. Verify the compatibility matrix of each critical integration.

## 31. Limitations of API lookup

### 31.1. Docs may not list every runtime detail

Some behavior depends on classpath, auto-configuration conditions, profiles, environment, and infrastructure. Javadoc for a class does not describe full runtime composition.

### 31.2. API presence does not mean the feature is enabled

A class may compile while the feature still requires another starter, property, bean, or auto-configuration.

### 31.3. Version reports may be incomplete in custom packaging

Package implementation versions may be null or fail to reflect every module. Dependency graphs and artifact inspection remain necessary.

### 31.4. "Current" docs are not a compatibility guarantee

The `current` page documents the active release, not a promise that the API exists in earlier releases.

### 31.5. Compile success does not guarantee binary compatibility

A compile probe confirms source compiles against the compile classpath. Runtime may still load another version or lack a dependency.

## 32. Summary

**Reading documentation for your running version is a mandatory step before introducing a new API into a Spring Boot application.** An API may have been introduced in Spring Framework, Spring Security, Spring Data, or another library; it is not automatically present simply because the project uses a Spring Boot version with the same major number.

Keep in mind:

1. Identify the **Spring Boot, Spring Framework, Java, and key dependency versions** actually running.
2. Distinguish the version in the build file from the resolved version and the version inside the deployed artifact.
3. Select the Reference Guide and Javadoc matching your release; avoid accidentally using `current` docs for an older project.
4. Read `@since`, deprecations, release notes, migration guides, and compatibility matrices.
5. Identify the **API owner and artifact/module** containing the class or method.
6. Use Maven dependency tree or Gradle dependency insight to check the selected version.
7. Use `javap` when needed to verify class/method descriptors in the actual JAR.
8. Write a compile probe using the application's exact dependency management.
9. Verify runtime, auto-configuration, and behavior using integration tests/artifact smoke tests.
10. When a new API is needed, prefer upgrading Boot along a compatible release train; override individual modules only with evidence and thorough testing.

A useful working rule is: **never adopt a snippet just because it appears in the latest documentation; verify that it belongs to the right library, the right version, and the actual runtime classpath of your application.** That habit prevents compile, linkage, and configuration errors as well as subtle behavior changes during Spring Boot upgrades.
