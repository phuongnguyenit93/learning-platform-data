# Differences in how starters and modules are split across Spring Boot releases

When adding a feature to a Spring Boot project, developers typically start with a dependency like `spring-boot-starter-web` or `spring-boot-starter-data-jpa`. However, **starter names, the libraries they pull in, and where auto-configuration code lives are not immutable across Spring Boot generations**. In particular, Spring Boot 4 reorganizes many components into smaller technology-focused modules and provides matching test starters.

This lesson explains how to read dependency structures from Spring Boot 1.x, 2.x, 3.x through 4.x, focusing on **starters**, **Spring Boot modules**, **Spring Framework modules**, **dependency management**, and the implications for creating new applications or upgrading existing ones.

> **Version scope:** Artifact name examples are aligned with conventions of each major line, especially the **Spring Boot 3 → 4.0** migration guide. When working on a specific minor/patch version, check the documentation for that exact version. A renamed starter may temporarily remain under its old name for compatibility, which does not mean it is the name to use for new projects.

## 1. Do not confuse starters, modules, and the framework

Three commonly seen layers appear in Gradle/Maven, yet each holds a different responsibility.

| Artifact type | Examples | Responsibility |
|---|---|---|
| **Starter** | `spring-boot-starter-web` (Boot 3), `spring-boot-starter-webmvc` (Boot 4) | Bundles dependencies commonly needed for an application type; users declare it to choose desired capabilities. |
| **Spring Boot implementation/support module** | `spring-boot-autoconfigure` (common in Boot 2/3), `spring-boot-webmvc` (Boot 4) | Contains code provided by Spring Boot, such as auto-configuration, framework integrations, and support APIs. |
| **Spring Framework module** | `org.springframework:spring-webmvc`, `spring-context`, `spring-core` | Contains foundational Spring Framework capabilities: DI container, MVC, web abstractions, transactions, etc. |
| **Third-party library** | Hibernate, Jackson, Tomcat, Flyway | Implements specific technologies; it is not a Spring Boot module merely because Boot manages its version. |
| **BOM / dependency management** | `spring-boot-dependencies` | Manages compatible version sets; the BOM itself does not activate a web server or create beans. |

**A starter is not synonymous with a source-code module.** Many starters are primarily dependency declarations, while runtime behavior lives in Spring Boot modules, Spring Framework modules, or other libraries. For instance, adding a web starter places related components onto the classpath; the `DispatcherServlet` class belongs to Spring MVC, while Spring Boot auto-configures the application when conditions are met.

Nor is a starter **a Gradle/Maven module you created yourself**. If a repository has `:api`, `:service`, and `:data` subprojects, that is your application's multi-module layout; it is independent of how Spring Boot splits its internal JARs.

## 2. Why does Spring Boot provide starters?

Without starters, a traditional web application had to declare many libraries manually and pick compatible versions:

- Spring Framework for DI, HTTP, and MVC.
- A suitable Servlet container or web server.
- A JSON processing library when sending/receiving JSON.
- Logging libraries and related components.
- Versions capable of working together.

A starter acts as an **intent-based bundle**. Developers declare a meaningful name, and the build tool resolves the corresponding dependency graph.

A conceptual chain:

```text
Declare starter by need
        │
        ▼
Gradle/Maven resolves dependencies
        │
        ├── Spring Boot support modules
        ├── Spring Framework modules
        ├── third-party libraries
        └── other transitive dependencies
        │
        ▼
Runtime classpath
        │
        ▼
Spring Boot evaluates auto-configuration conditions
        │
        ▼
Actual beans/features configured
```

This diagram is a **responsibility model**, not the complete dependency tree of a specific artifact. Exact transitive edges and module sets can vary by Boot release line, other dependencies, and exclusions.

Two ideas must be kept distinct:

1. **Having a dependency** means the library is present on the classpath per build configuration.
2. **A feature working** also depends on annotations, beans, configuration, application type, and auto-configuration conditions.

For example, adding the JPA starter does not automatically create entities or a running database. You need a datasource, driver, entity metadata, and corresponding configuration.

## 3. Evolution overview from Spring Boot 1.x to 4.x

| Spring Boot line | Notable organization | How to read `dependencies` |
|---|---|---|
| **1.x** | Pioneered feature-based starters, bootstrapping, and auto-configuration; focused on servlet web, data, security, actuator. | Look for broad starters by need, then inspect underlying modules/framework. |
| **2.x** | Maintained the starter system; expanded modern options like **WebFlux** and technology-specific starters. | Clearly separate servlet web and reactive web; do not treat every web app as the same stack. |
| **3.x** | Built on Spring Framework 6 and Jakarta EE; kept many familiar 2.x starter names while changing the baseline and many underlying dependencies. | Starter names may look like 2.x, yet code uses `jakarta.*` instead of `javax.*` and library versions differ markedly. |
| **4.x** | Splits much support code into **technology-focused modules**; standardizes main starters, test starters, and package names; renames several starters. | Identify the right new starters, specialized modules, test starters, and corresponding auto-configuration imports. |

The table demonstrates **you cannot judge compatibility merely by looking at a starter's name**. Two projects both listing `spring-boot-starter-data-jpa` on Boot 2 vs. Boot 3 still differ in JPA API, Spring Data, Hibernate, and Java baseline.

### Spring Boot 1.x: starters as simple entry points

The first generation established thinking by application capability: want web, use the web starter; want JDBC/JPA, use the data starter; want security, use the security starter. Developers rarely had to assemble JARs by hand.

Java libraries and Spring Framework modules remained underneath. Spring Boot did not replace Spring Framework; it provided a smoother configuration and packaging experience.

### Spring Boot 2.x: expanding by programming model

The 2.x line added reactive choices such as `spring-boot-starter-webflux` (from Boot 2.0), while `spring-boot-starter-web` remained the familiar choice for Spring MVC on the servlet stack.

One important shift within 2.x itself: starting in **2.3**, Bean Validation was no longer pulled in the same way by the web starter. For projects needing validation, explicitly declaring `spring-boot-starter-validation` became necessary. This shows that **even a minor version upgrade can change which transitive dependencies are included**.

### Spring Boot 3.x: many familiar names, transformed ecosystem underneath

Boot 3 moved to Spring Framework 6, Java 17+, and Jakarta APIs. In code using Servlet, Validation, JPA, etc., many old Java EE `javax.*` imports had to migrate to `jakarta.*` per the underlying libraries.

For example:

```java
// Old Java EE import style, common in Boot 2 projects:
import javax.persistence.Entity;

// Import style matching Jakarta Persistence in Boot 3:
import jakarta.persistence.Entity;
```

The name `spring-boot-starter-data-jpa` stayed the same, yet that did not mean code compiled on Boot 2 was automatically compatible with Boot 3. Upgrading requires checking **both APIs and the dependency graph**, not just looking for renamed artifacts.

### Spring Boot 4.x: splitting modules and aligning starters with technologies

Boot 4.0 reorganizes core modules by specialized capability. Instead of assuming most auto-configuration lives inside one large JAR, you encounter names such as:

- `spring-boot-webmvc` for Boot's support of Spring MVC.
- `spring-boot-webflux` for Boot's support of WebFlux.
- `spring-boot-data-jpa` for Boot's support of Spring Data JPA.
- `spring-boot-jackson` for Jackson support.
- `spring-boot-flyway` for Flyway support.
- `spring-boot-webmvc-test`, `spring-boot-data-jpa-test` for dedicated test infrastructure.

The naming convention described in the Boot 4.0 documentation is:

```text
spring-boot-<technology>                   # Main support module
org.springframework.boot.<technology>       # Corresponding root package
spring-boot-starter-<technology>           # Main starter
spring-boot-<technology>-test              # Test support module, when present
spring-boot-starter-<technology>-test      # Test starter, when present
```

Not every technology has every artifact variant. For example, some web server starters do not have a separate dedicated test starter. Check the official catalog for the version you are using instead of constructing names by pattern and assuming an artifact exists.

## 4. Starter name comparison table between Boot 3 and Boot 4

The table below highlights names that commonly cause confusion when upgrading from 3.x to 4.x.

| Need | Common name in Spring Boot 3.x | Appropriate name in Boot 4.x | Notes |
|---|---|---|---|
| Spring MVC + HTTP server | `spring-boot-starter-web` | `spring-boot-starter-webmvc` | The name `starter-web` is kept but **deprecated** in Boot 4.0. |
| WebFlux | `spring-boot-starter-webflux` | `spring-boot-starter-webflux` | Main name unchanged; underlying Boot components reorganized. |
| Spring Data JPA | `spring-boot-starter-data-jpa` | `spring-boot-starter-data-jpa` | Main name unchanged, though integration/test modules differ. |
| JDBC | `spring-boot-starter-jdbc` | `spring-boot-starter-jdbc` | Technology starter remains present across lines. |
| Bean Validation | `spring-boot-starter-validation` | `spring-boot-starter-validation` | Declare explicitly when using validation; do not assume every web starter includes it. |
| Core Spring Security | `spring-boot-starter-security` | `spring-boot-starter-security` | Security testing has its own dedicated starter in Boot 4. |
| OAuth2 Client | `spring-boot-starter-oauth2-client` | `spring-boot-starter-security-oauth2-client` | Old name marked deprecated in Boot 4. |
| OAuth2 Resource Server | `spring-boot-starter-oauth2-resource-server` | `spring-boot-starter-security-oauth2-resource-server` | New name emphasizes the Security grouping. |
| Spring Web Services | `spring-boot-starter-web-services` | `spring-boot-starter-webservices` | Old name deprecated in Boot 4. |
| Spring GraphQL | `spring-boot-starter-graphql` | `spring-boot-starter-graphql` | Has clear technology Boot module and companion test starter. |
| Flyway migration | Often declared `org.flywaydb:flyway-core` directly | `spring-boot-starter-flyway` | Boot 4 requires using the dedicated starter for proper Boot integration. |
| Liquibase migration | Often declared `org.liquibase:liquibase-core` directly | `spring-boot-starter-liquibase` | Review starters per Boot release line. |

**Deprecated does not mean immediately removed.** Boot 4.0 documentation notes that several older starter names remain available to support gradual migration, yet you should use the replacement names when updating a Boot 4 project's build. Do not assume every old starter is preserved as an alias.

### Example: looking just at the Web starter name shows the difference

In a Spring MVC Boot 3 application, a common Gradle declaration is:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
}
```

For a Boot 4 project using Spring MVC:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
}
```

What changed is **the selection name and the corresponding dependency organization**. Controllers using `@RestController` and `@GetMapping` still belong to the Spring MVC model; switching starters does not mean rewriting every controller.

However, a major version upgrade **may require** updating other APIs, packages, properties, or libraries. Do not treat swapping one dependency line as a guarantee that the entire application is compatible after upgrading.

## 5. From broad support modules to technology-focused modules

In Boot 2 and Boot 3, two frequently encountered artifacts were:

- `org.springframework.boot:spring-boot`: Boot's core classes and primary APIs.
- `org.springframework.boot:spring-boot-autoconfigure`: broad collection of auto-configurations.

In Boot 4, much technology support moves into clearly named modules. This perspective is especially helpful when reading a stack trace or locating a moved class:

| What you are looking for | Example specialized module in Boot 4 | Role |
|---|---|---|
| Spring MVC integration | `spring-boot-webmvc` | Boot support and configuration for Spring MVC. |
| WebFlux | `spring-boot-webflux` | Boot support for the reactive web stack. |
| Spring Data JPA | `spring-boot-data-jpa` | Boot integration with Spring Data JPA. |
| Non-reactive HTTP client | `spring-boot-restclient` | Boot integration for `RestClient`/`RestTemplate`. |
| Reactive WebClient | `spring-boot-webclient` | Boot integration for `WebClient`. |
| Caching | `spring-boot-cache` | Auto-configuration support for caching. |
| Security | `spring-boot-security` | Boot support for Spring Security. |
| Jackson | `spring-boot-jackson` | Jackson integration for Boot 4. |

For instance, `spring-boot-webmvc` is **not** a replacement name for the underlying Spring MVC library `org.springframework:spring-webmvc`. The two artifacts belong to **two projects and two responsibilities**: Spring Framework supplies MVC capabilities; Spring Boot supplies integration and convention-based auto-configuration.

In documentation and build errors, always check the **group ID** as well:

```text
org.springframework.boot:spring-boot-webmvc      # Spring Boot 4 module
org.springframework:spring-webmvc                # Spring Framework module
org.springframework.boot:spring-boot-starter-webmvc  # Spring Boot 4 starter
```

Two artifacts with `webmvc` in their names are not directly interchangeable.

## 6. Separating Web MVC, WebFlux, and HTTP clients

One easy mistake is thinking everything related to HTTP must share one web starter. In reality there are at least three distinct needs:

1. **Spring MVC Server**: serves requests on the Spring MVC servlet stack.
2. **WebFlux Server**: reactive application using Spring WebFlux.
3. **HTTP Client**: an application calling external APIs without necessarily opening its own web server.

In Boot 3, applications needing `WebClient` often added `spring-boot-starter-webflux` even when they only wanted the client. Boot 4 provides dedicated starters for HTTP clients to express intent cleanly:

| Need | Boot 4 Starter |
|---|---|
| Spring MVC Server | `spring-boot-starter-webmvc` |
| WebFlux Server | `spring-boot-starter-webflux` |
| Imperative HTTP client (e.g. `RestClient`) | `spring-boot-starter-restclient` |
| Reactive HTTP client (`WebClient`) | `spring-boot-starter-webclient` |

This avoids assuming **using an HTTP client requires building a web server**. A scheduled job, message consumer, or CLI application can call HTTP APIs without opening a port to serve incoming requests.

When code uses `RestTemplate`, `RestClient`, or `WebClient`, choose the starter matching both **the API and the Boot line**, rather than looking for any dependency containing “web.”

## 7. Test starters are also split differently

In Boot 2/3, `spring-boot-starter-test` was the standard dependency for JUnit, AssertJ, Spring Test, and MockMvc-related testing utilities depending on version and dependency graph. Certain specialized technologies still needed separate test dependencies, such as `spring-security-test`.

Boot 4 retains the core test starter while adding **technology-specific test starters**, such as:

| Technology under test | Boot 4 Test Starter |
|---|---|
| Spring MVC | `spring-boot-starter-webmvc-test` |
| Spring WebFlux | `spring-boot-starter-webflux-test` |
| Spring Data JPA | `spring-boot-starter-data-jpa-test` |
| Spring Security | `spring-boot-starter-security-test` |
| Spring GraphQL | `spring-boot-starter-graphql-test` |
| Spring JDBC | `spring-boot-starter-jdbc-test` |

Boot 4's specialized test starters typically pull in `spring-boot-starter-test` transitively. Therefore, once you choose the right technology test starters, you do not necessarily need to declare `spring-boot-starter-test` directly as well.

This is a **notable design change**, not just a rename. In Boot 4, adding a raw test library like `spring-security-test` without the matching integration starter may omit the test auto-configuration/infrastructure you expect.

### Example test dependencies across generations

A **Boot 3** project using Spring MVC, JPA, and Security commonly declares:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testImplementation 'org.springframework.security:spring-security-test'
}
```

An equivalent **Boot 4** project can declare:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-security'

    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-data-jpa-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-security-test'
}
```

These snippets illustrate **dependency composition** only, assuming the project already configures the Spring Boot plugin and dependency management/BOM matching the corresponding version. Database drivers, datasource configuration, test suites, and other libraries must be added for real applications.

In both versions, `@SpringBootTest` does not turn itself into a complete test suite. Choose appropriate test styles such as unit tests, `@WebMvcTest`, or `@DataJpaTest` where supported by tooling and infrastructure.

## 8. For database migrations, third-party dependencies alone may fall short

Flyway and Liquibase are key examples when moving from Boot 3 to Boot 4.

With **Boot 3**, applications often declared the third-party library directly:

```groovy
dependencies {
    implementation 'org.flywaydb:flyway-core'
    // Or:
    // implementation 'org.liquibase:liquibase-core'
}
```

Spring Boot 3 could auto-configure support based on the dependency and configuration present. Moving to **Boot 4**, modularization means migration guidance calls attention to **Spring Boot's dedicated starters**:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-flyway'
    // Or:
    // implementation 'org.springframework.boot:spring-boot-starter-liquibase'
}
```

Do not simply copy `flyway-core` over from an old build and assume all Boot 4 auto-configuration will work as before. Beyond the starter, Flyway may also require database-specific modules for your DBMS; verify per version and database.

Likewise, Boot managing a library's version **does not mean adding that library alone brings in all Boot integration**. BOMs and starters serve different purposes.

## 9. Changes in JSON: note Jackson 2 vs. Jackson 3

In Boot 3, Jackson 2 was the standard JSON choice in the web ecosystem; common packages used the `com.fasterxml.jackson` prefix. Boot 4 favors **Jackson 3**, with many modules and packages moving to `tools.jackson`.

Conceptual example of import names:

```java
// Jackson 2, common in Boot 3 applications:
import com.fasterxml.jackson.databind.ObjectMapper;

// With Jackson 3, corresponding APIs are reorganized
// under the tools.jackson namespace; follow the new APIs accurately
// rather than performing blind find-and-replace across package strings.
```

Boot 4 provides `spring-boot-jackson` and `spring-boot-starter-jackson` for Jackson support. Yet having the JSON starter **does not mean** custom code written for Jackson 2 is binary- or source-compatible with Jackson 3.

When a project uses Jackson directly (custom serializers, deserializers, modules, `ObjectMapper`, configuration), read the Jackson 3 upgrade guide. An app whose controllers only accept/return JSON DTOs encounters fewer of these details than one deeply customizing Jackson, yet should still run serialization/deserialization tests.

## 10. Boot 4 includes “classic starters” for step-by-step migration

After modularization, large applications calling low-level Boot classes may encounter imports no longer on the classpath as before. Boot 4.0 provides an intermediate bridge:

- `spring-boot-starter-classic`
- `spring-boot-starter-test-classic`

Classic starters place onto the classpath a module set closer to the prior generation's layout, helping fix the application and verify execution. **They are recommended as migration bridges**, not the ideal final setup for every Boot 4 project.

A controlled migration workflow:

1. Identify the project's Java and Spring Boot versions; establish a baseline of passing builds and tests.
2. Read the migration guide and update build plugins, dependency management, and legacy starter names.
3. If needed, temporarily use classic starters to address moved classes/imports and get the application running again.
4. Transition incrementally to technology-specific starters while inspecting the dependency graph.
5. Remove classic starters once all required dependencies are verified and explicitly declared.
6. Verify tests, HTTP endpoints, security, database migrations, and runtime behavior.

Avoid abusing classic starters to hide missing dependencies: it may keep the app running temporarily while making it harder for maintainers to tell which technologies are genuinely required.

## 11. Dependency management: the same artifact can carry different versions

Spring Boot publishes the `org.springframework.boot:spring-boot-dependencies` BOM managing many compatible library versions. Starters express **needed technologies**; the BOM decides **managed versions** for dependencies within its scope.

For example, a Gradle project with the BOM imported and appropriate plugin applied can declare:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
}
```

Here the starter version is omitted because dependency management provides it. A native Gradle BOM approach looks like:

```groovy
dependencies {
    implementation platform('org.springframework.boot:spring-boot-dependencies:4.0.0')
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
}
```

This snippet illustrates **dependency management**, not a complete build file. A project using the Spring Boot plugin also needs plugin, Java, and task configurations. Do not import two BOMs from two different Boot lines at the same time, nor force core libraries back to incompatible generations.

When using Maven, versions are typically managed via `spring-boot-starter-parent` or importing the BOM inside `dependencyManagement`. Gradle can use `io.spring.dependency-management` or `platform(...)` per build setup. These choices do not change the distinction between **starters and modules**.

### Why inspect the dependency graph instead of only the build file?

The build file shows only **directly declared** dependencies; runtime also contains **transitive** dependencies.

```text
You declare:
spring-boot-starter-webmvc
         │
         ▼
A set of web, Spring, Boot integration,
server, and serialization libraries resolves by version
         │
         ▼
Actual classpath depends on:
BOM + dependency conflict resolution + exclusions
+ profile/configuration + Boot version
```

Therefore, two builds with the exact same starter line can still behave differently when BOMs, exclusions, or additional dependencies differ.

## 12. How to inspect the actual dependencies of a project

### With Gradle

In the directory containing the project's wrapper:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

To find **why** a specific module appears (for example in Boot 4):

```bash
./gradlew dependencyInsight \
  --dependency spring-boot-webmvc \
  --configuration runtimeClasspath
```

In Windows PowerShell, you can write it on one line:

```powershell
.\gradlew.bat dependencyInsight --dependency spring-boot-webmvc --configuration runtimeClasspath
```

Commands inspect the dependency graph for the **specified project/configuration**. In a multi-module repository, specify the subproject, such as `:app:dependencies`. The artifact name `spring-boot-webmvc` is illustrative for a Boot 4 project using webmvc; do not run that query expecting to draw conclusions in a Boot 2/3 project.

To inspect compile or test dependencies:

```bash
./gradlew dependencies --configuration compileClasspath
./gradlew dependencies --configuration testRuntimeClasspath
```

A library being present in `testRuntimeClasspath` does not guarantee it exists on the packaged application's runtime classpath.

### With Maven

```bash
./mvnw dependency:tree
```

Or filter to the Spring Boot group:

```bash
./mvnw dependency:tree -Dincludes=org.springframework.boot
```

The output helps check which dependencies are direct, which are transitive, and which versions were chosen. When migrating Boot 3 → 4, compare at least the **runtime** and **test** dependency graphs before and after.

### Reading artifacts by full coordinates

Do not compare `spring-webmvc` with `spring-boot-webmvc` using just a few shared letters; always look at the full coordinates:

```text
groupId:artifactId:version

org.springframework:spring-webmvc:<spring-framework-version>
org.springframework.boot:spring-boot-webmvc:<spring-boot-version>
org.springframework.boot:spring-boot-starter-webmvc:<spring-boot-version>
```

The `<...>` placeholders represent actual versions, not literal text to paste into build commands.

## 13. Auto-configuration depends on classpath, yet is not equivalent to a starter

Spring Boot activates many auto-configurations based on **conditions**: whether classes are present, whether beans exist, whether the application is an appropriate web type, whether properties enable/disable features, and so on.

For example, an auto-configuration may apply only when JDBC libraries and a suitable datasource exist. If required classes are missing, conditions fail; if the application supplies its own bean, auto-configuration can back off.

A starter brings **required classes** into the environment, yet cannot substitute for all runtime configuration. When an expected bean does not appear, check:

- Are main and transitive dependencies on the right versions?
- Are Boot support classes/modules on the runtime classpath?
- Which auto-configurations were applied, excluded, or missed conditions?
- Did a user-defined bean prevent Boot from creating the default bean?
- Do properties, profiles, application type, or environment conditions interfere?

You can start the application in development with `--debug` to view the **conditions evaluation report**. This report helps explain auto-configuration, though it does not prove the entire application configuration is valid on its own.

When upgrading to Boot 4, a class that used to reside in the broad auto-configuration package in Boot 3 may have moved to a technology-specific module package. If the application imports internal Boot classes directly, consult API docs and migration guides instead of assuming a missing starter is the only issue.

## 14. Common errors when upgrading Spring Boot lines

| Symptom | What to investigate | Appropriate fix |
|---|---|---|
| Code from Boot 3 fails to find a Boot class after upgrading to Boot 4 | Module/package changed, or dependency not declared explicitly | Check migration guide, locate new module and package, add matching technology starter if needed. |
| Boot 4 project still declares `spring-boot-starter-web` | Deprecated old starter in use | Switch to `spring-boot-starter-webmvc` when using Spring MVC. |
| After upgrading, Security tests using `@WithMockUser` fail | Security test infrastructure not fully integrated | Check `spring-boot-starter-security-test` in Boot 4. |
| After upgrading to Boot 4, Flyway does not run as expected | Kept old Flyway dependency; missing Boot integration module | Check `spring-boot-starter-flyway` and corresponding DB driver/module. |
| Project has both MVC and WebFlux starters, web model unclear | Two different technologies on the classpath together | Choose the intended server stack; check application type and config. |
| Upgrading 2.x to 3.x causes `javax.persistence` or `javax.servlet` errors | Transition to Jakarta EE | Update APIs/imports and compatible dependencies, upgrade related libraries. |
| `NoClassDefFoundError` at runtime | Missing classpath entry or incompatible version | Inspect dependency tree, exclusions, and runtime configuration. |
| Dependency version changed unexpectedly | BOM conflict, manual override, or build tool resolution | Check dependency insight/tree and version management rules. |
| Using Boot module directly yet auto-config is incomplete | Bypassed starter and missed related integration dependencies | Check official starter or declare all needed modules deliberately. |

### A small migration example with multiple layers

Suppose a Boot 3 service has MVC endpoints, OAuth2 login, and Flyway:

```groovy
// Dependencies in a Boot 3 application
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-oauth2-client'
    implementation 'org.flywaydb:flyway-core'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

When migrating to Boot 4, the selections following the new naming become:

```groovy
// Illustrative dependencies for an application migrated to Boot 4
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webmvc'
    implementation 'org.springframework.boot:spring-boot-starter-security-oauth2-client'
    implementation 'org.springframework.boot:spring-boot-starter-flyway'

    testImplementation 'org.springframework.boot:spring-boot-starter-webmvc-test'
    testImplementation 'org.springframework.boot:spring-boot-starter-security-oauth2-client-test'
}
```

This is a **map of dependencies to review**, not a complete upgrade recipe. You still have to review Java target, Spring Framework version, security configuration, database connections, drivers, migration scripts, and other libraries.

## 15. Practice exercises on reading real starters and modules

### Exercise 1: Distinguish starters from modules

In `build.gradle` or `pom.xml`, pick a declared starter. Using the dependency tree, list three layers:

1. The directly declared starter.
2. A Spring Boot integration module present transitively.
3. A Spring Framework module or third-party library used by the starter.

Explain why these three layers cannot be treated as the same artifact.

### Exercise 2: Compare Spring MVC on Boot 3 and Boot 4

Create two separate experimental projects using the corresponding Spring Boot versions: one Boot 3 project using `spring-boot-starter-web` and one Boot 4 project using `spring-boot-starter-webmvc`. Each project has a `@RestController` returning a string for `GET /hello`.

Compare:

- The starter name declared in the build file.
- The list of `org.springframework.boot` modules in the runtime dependency tree.
- Spring Framework's `spring-webmvc` library.
- How the endpoint behaves once started with the matching Java/runtime for each version.

The goal is to see that **MVC responsibilities keep the same concepts** while Boot's artifact organization evolves.

### Exercise 3: Observe Boot 4 test starters

In a Boot 4 project with Spring MVC, add `spring-boot-starter-webmvc-test` and inspect `testRuntimeClasspath`. Check whether `spring-boot-starter-test` is pulled in transitively. Then try writing an HTTP test for your controller.

### Exercise 4: Inspect auto-configuration

Create an application with appropriate JDBC/JPA dependencies. Run with `--debug` and inspect the conditions evaluation report. Identify what conditions datasource auto-configurations check. If the application lacks a database or driver, note the resulting error/message and distinguish **connection configuration errors** from **missing starter/module errors**.

### Exercise 5: Build an upgrade mapping table

Pick a Boot 3 project with at least three starters. Before changing versions, create a table:

| Current dependency | Feature group | Boot 4 name | Change test starter? | Additional checks |
|---|---|---|---|---|
| `spring-boot-starter-web` | MVC | `spring-boot-starter-webmvc` | `webmvc-test` | Controllers, serialization, server |
| `spring-boot-starter-data-jpa` | Persistence | Keep main name | `data-jpa-test` | Jakarta, JPA, Hibernate, driver |
| `spring-boot-starter-security` | Security | Keep main name | `security-test` | Authentication, filter chain |

Use the dependency tree and the target version's migration guide to fill in unclear rows. Do not rename every artifact by a string pattern without verifying the actual artifact exists.

## 16. Key principles to remember

1. **Starters express feature selections**, while modules contain implementation/integration code. The BOM is the version management source; these three solve three distinct problems.
2. **Boot 1/2 established the starter model**; Boot 2 expanded options like WebFlux; Boot 3 updated the Spring Framework/Jakarta baseline even where many starter names stayed unchanged.
3. **Boot 4.0 splits Spring Boot into technology-focused modules**, standardizes starter names, and adds dedicated test starters; some Boot 3 names remain as deprecated aliases.
4. **Never deduce dependencies solely from names**: look at `group:artifact:version` coordinates, runtime/test classpaths, and resolved transitive dependencies.
5. **Upgrading across major versions touches the entire dependency graph and APIs**, including Java, Spring Framework, Jakarta/Jackson, auto-configuration, tests, and other libraries.
6. **Choosing starters matching the right Boot line** before writing code avoids classpath errors, auto-configuration surprises, and ambiguous configurations later.

### Official reference documentation

- [Spring Boot 4.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-4.0-Migration-Guide) — module lists, starters, test starters, deprecated names, and guidance for moving from Boot 3.
- [Spring Boot 3.0 Migration Guide](https://github.com/spring-projects/spring-boot/wiki/Spring-Boot-3.0-Migration-Guide) — major changes from Boot 2 to Boot 3, including Jakarta EE.
- [Spring Boot Reference — Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html) — official starter list published for the version being viewed.
- [Spring Initializr](https://start.spring.io/) — select Boot lines and dependencies to generate a real reference project.

When reading or upgrading a project, start with the question **“Which technologies does the application need, on which Spring Boot line?”**, choose starters for that line, and verify the actual modules and libraries using the dependency graph. This approach works far better than memorizing a rigid list of starter names across every release.
