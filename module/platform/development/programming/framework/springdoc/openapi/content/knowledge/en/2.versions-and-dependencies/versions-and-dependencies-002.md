# Reading the Compatibility Matrix Before Choosing the Library

Choosing a springdoc-openapi version solely by looking at the latest version number easily leads to startup failures, missing auto-configuration, or dependency conflicts. springdoc runs inside a Spring Boot application, so its version must match the Spring Boot line, Spring Framework, Java, and web stack that the application uses.

Before adding dependencies, answer four questions:

1. Which Spring Boot line is the application using and which Spring Framework version is managed by Boot?
2. Which Java version does the application run on and is it using the `javax.*` or `jakarta.*` namespace?
3. Is the web stack Spring MVC (Servlet) or Spring WebFlux (Reactive)?
4. Do you only need OpenAPI JSON/YAML or also the Swagger UI interface?

Only then consult the springdoc-openapi matrix and select the right starter. The matrix is a starting point to rule out incompatible combinations; the dependency graph and application tests confirm that the choice works in the actual project.

## 1. Why Read the Compatibility Matrix?

springdoc-openapi reads controllers, Spring mappings, DTOs, validation, and application configuration to generate an OpenAPI document. The library depends on Spring Boot/Spring Framework APIs and auto-configuration. When Spring changes packages, extension points, or bean initialization mechanisms, an older springdoc line may stop working.

For example:

- Spring Boot 2 is based on Spring Framework 5 and the Java EE ecosystem using `javax.*`.
- Spring Boot 3 moves to Spring Framework 6 and the Jakarta `jakarta.*` namespace.
- Spring Boot 4 uses the Spring Framework 7 generation and continues using the Jakarta namespace.

A library compiled for Spring Boot 2 cannot inherently run with Spring Boot 4 just because both run on the JVM. The difference lies in the APIs the library links against, not only in Java bytecode.

Choosing the wrong version can cause:

- `NoSuchMethodError`, `NoClassDefFoundError`, or `ClassNotFoundException` at startup.
- Failure to load springdoc auto-configuration.
- Missing `/v3/api-docs` endpoint or Swagger UI.
- Errors caused by mixing `javax.servlet` with `jakarta.servlet`.
- Version conflicts among `swagger-core`, Jackson, or Spring Framework.
- Application starting up but failing when requesting documentation or serializing schemas.

## 2. Reading the springdoc-openapi and Spring Boot Matrix

The official springdoc matrix records the Spring Boot lines against which each springdoc line was built. As of the check on **20/11/2026**, the published combinations are:

| Spring Boot | Published compatible springdoc-openapi line |
|---|---|
| `4.1.x` | `3.1.x` – `3.2.x` |
| `4.0.x` | `3.0.x` |
| `3.5.x` | `2.8.x` – `2.10.x` |
| `3.4.x` | `2.7.x` – `2.8.x` |
| `3.3.x` | `2.6.x` |
| `3.2.x` | `2.3.x` – `2.5.x` |
| `3.1.x` | `2.2.x` |
| `3.0.x` | `2.0.x` – `2.1.x` |
| `2.7.x` | `1.x` line; v1 docs list minimum `1.6.11` |
| `2.6.x` | `1.x` line; v1 docs list minimum `1.6.0` |
| `2.5.x` | `1.x` line; v1 docs list minimum `1.5.9` |
| `2.4.x` | `1.x` line; v1 docs list minimum `1.5.0` |
| `2.3.x` | `1.x` line; v1 docs list minimum `1.4.0` |
| `2.2.x` | `1.x` line; v1 docs list minimum `1.2.1` |
| `2.0.x` | `1.x` line; v1 docs list minimum `1.0.0` |

These are combinations documented by the project as built, not a guarantee that every patch version or every custom dependency is compatible. Read the page corresponding to the major line in use:

- Spring Boot 4: [current springdoc-openapi](https://springdoc.org/).
- Spring Boot 3: [springdoc-openapi v2 documentation](https://springdoc.org/v2/).
- Spring Boot 2 and 1: [springdoc-openapi v1 documentation](https://springdoc.org/v1/).

### Major Version Selection Rule

| Spring Boot Line | springdoc Major to Choose | Notes |
|---|---|---|
| Spring Boot 4.x | springdoc 3.x | Current line for Spring Boot 4 |
| Spring Boot 3.x | springdoc 2.x | Line for Spring Boot 3 |
| Spring Boot 2.x or 1.x | springdoc 1.x | Legacy line; latest open-source version published is `1.8.0` |

Do not use springdoc 3.x with Spring Boot 3 just because `3` is greater than `2`. The two numbers belong to two different projects. The major version of springdoc is chosen by the Spring Boot line, not by the habit of "picking the largest version."

### Choosing a Stable Release in the Compatible Range

If the application uses Spring Boot `3.5.x`, the matrix allows springdoc `2.8.x` through `2.10.x`. When starting a new integration, prefer the latest stable patch in the compatible range, then run tests against the actual dependency graph.

If the project is locked by another dependency or needs a step-by-step upgrade, you may choose a lower version within the range. Document the reason and update plan to avoid keeping an old version indefinitely.

Do not default to `SNAPSHOT`, milestone, or release candidate versions for production. If you must test a preview release, clearly mark it in the build, run regression tests, and do not treat it as a stable combination confirmed by the matrix.

## 3. The Matrix Is Not Just About Spring Boot

Spring Boot manages a dependency set including Spring Framework, Spring Security, Jackson, and many other libraries. Therefore, you must also check Java, Spring Framework, and the namespace.

| Component | Spring Boot 2.x | Spring Boot 3.x | Spring Boot 4.x |
|---|---|---|---|
| Spring Framework generation | 5.x | 6.x | 7.x |
| Common web namespace | `javax.*` | `jakarta.*` | `jakarta.*` |
| springdoc line | 1.x | 2.x | 3.x |
| Java requirement | Depends on specific Boot version; may be lower than Java 17 | Java 17 or higher | Java 17 or higher |

Spring Boot 4.1.2 currently requires at least Java 17 and Spring Framework 7.0.10 or higher. Spring Framework 7.x uses the Jakarta EE namespace. Spring Boot 3 also moved to the Jakarta namespace; when upgrading from Boot 2 to Boot 3, imports such as `javax.servlet.*`, `javax.validation.*`, or `javax.persistence.*` typically have to be changed to their corresponding `jakarta.*` packages.

Check the system requirements of the exact Spring Boot patch instead of relying only on a general table. [Spring Boot System Requirements](https://docs.spring.io/spring-boot/system-requirements.html) and [Spring Framework Versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions) are two essential references to cross-check.

### Namespace Error Example

An older filter might import:

~~~java
import javax.servlet.Filter;
~~~

In a Spring Boot 3/4 application, the Servlet API uses Jakarta:

~~~java
import jakarta.servlet.Filter;
~~~

Adding a springdoc starter with the right major version does not automatically migrate source code from `javax.*` to `jakarta.*`. Upgrading the framework, source code, and libraries must be treated as one synchronized migration plan.

## 4. Determining the Actual Spring Boot Version of a Project

Do not just look at a single dependency line in `pom.xml` or `build.gradle`. The project may use a parent, BOM, version catalog, or version management plugin.

With Maven, inspect:

~~~bash
./mvnw help:effective-pom
./mvnw dependency:tree -Dincludes=org.springframework.boot,org.springframework
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-boot --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-core --configuration runtimeClasspath
~~~

These commands show resolved dependencies, not just initially declared versions. If multiple modules use Spring Boot, inspect the exact subproject containing the Springdoc application.

At a minimum, record:

- Versions of `spring-boot` and `spring-boot-autoconfigure`.
- Versions of `spring-core`, `spring-context`, and `spring-webmvc` or `spring-webflux`.
- Java version used to compile and run the application.
- Actual web starter brought onto the runtime classpath.
- Spring Security major version, if present.
- Any `swagger-core`, Jackson, and related dependencies overridden by the project.

If `spring-boot-starter-parent` or `spring-boot-dependencies` manages Spring Framework, let Boot's BOM decide the versions of Spring modules. Avoid manually setting `spring-core` to a different line than Boot.

## 5. Choosing WebMVC vs. WebFlux Correctly

springdoc provides separate starters for the two web stacks. Choose according to the application's actual runtime:

| Application Web Stack | OpenAPI JSON/YAML only | Both Swagger UI needed |
|---|---|---|
| Spring MVC / Servlet (`spring-boot-starter-web`) | `springdoc-openapi-starter-webmvc-api` | `springdoc-openapi-starter-webmvc-ui` |
| Spring WebFlux / Reactive (`spring-boot-starter-webflux`) | `springdoc-openapi-starter-webflux-api` | `springdoc-openapi-starter-webflux-ui` |

Do not choose `webflux` merely because controllers return `Mono` or `Flux` in a project with a Servlet runtime; check the actual web application type and dependencies. Conversely, do not use the WebMVC starter for an application running pure Netty/WebFlux.

If you only publish an OpenAPI file to an API portal or code generation pipeline, the `*-api` starter is usually enough. If users need an interactive interface to browse operations and test requests, choose the `*-ui` starter.

## 6. Choosing the Exact Artifact by Purpose

Example with Spring Boot 4.1.x and springdoc 3.2.0:

| Artifact | Use when |
|---|---|
| `springdoc-openapi-starter-webmvc-api` | Servlet application needs OpenAPI endpoints without Swagger UI |
| `springdoc-openapi-starter-webmvc-ui` | Servlet application needs OpenAPI and Swagger UI |
| `springdoc-openapi-starter-webflux-api` | Reactive application needs OpenAPI endpoints without Swagger UI |
| `springdoc-openapi-starter-webflux-ui` | Reactive application needs OpenAPI and Swagger UI |

Default endpoint examples:

- OpenAPI JSON: `/v3/api-docs`.
- OpenAPI YAML: `/v3/api-docs.yaml`.
- Swagger UI: `/swagger-ui.html`.

Paths can be changed via properties and may include a context path. Choosing a starter only determines the integration module; it does not replace verifying URLs after the application starts.

## 7. Maven Example for Spring Boot 4

The following example uses Spring Boot `4.1.2`, Java 17 or higher, and springdoc `3.2.0`. The application uses Spring MVC and needs Swagger UI:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>4.1.2</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>3.2.0</version>
    </dependency>
</dependencies>
~~~

The Spring Boot parent manages Spring Boot/Spring Framework dependencies. The springdoc version is chosen from the compatibility matrix. There is no need to declare a version for `spring-boot-starter-web` when using the Boot parent.

If the project only needs OpenAPI JSON/YAML, replace the UI artifact with:

~~~xml
<artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
~~~

If using WebFlux, choose `springdoc-openapi-starter-webflux-api` or `springdoc-openapi-starter-webflux-ui` accordingly.

## 8. Managing springdoc Modules with the BOM

Since springdoc `2.8.7`, the project provides a BOM to manage springdoc module versions consistently. If the project uses multiple modules such as API, UI, or other integration support, you can import the BOM:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-bom</artifactId>
            <version>3.2.0</version>
            <type>pom</type>
            <scope>import</scope>
        </dependency>
    </dependencies>
</dependencyManagement>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    </dependency>
</dependencies>
~~~

The Spring Boot BOM manages libraries in the Boot ecosystem; the springdoc BOM manages springdoc modules. The two BOMs have different scopes and can be used together.

Do not import a springdoc BOM of a different major than the Boot line in use. The BOM only aligns artifacts within the same project; it does not make springdoc 3.x compatible with Boot 3.

## 9. Maven Example for Spring Boot 3

If the application uses Spring Boot `3.5.x`, select springdoc `2.8.x` through `2.10.x` per the matrix. Example using `2.10.0`:

~~~xml
<parent>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-parent</artifactId>
    <version>3.5.16</version>
    <relativePath/>
</parent>

<properties>
    <java.version>17</java.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-web</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>2.10.0</version>
    </dependency>
</dependencies>
~~~

Do not copy Boot 4 dependencies into a Boot 3 project and only change the parent version. Check artifacts, springdoc major, and namespaces of all dependencies before building.

## 10. Gradle Kotlin DSL Example

With Gradle, you can import the springdoc BOM to avoid repeating versions across modules:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")

    implementation(platform("org.springdoc:springdoc-openapi-bom:3.2.0"))
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui")
}
~~~

The example assumes the Spring Boot Gradle plugin or the project's dependency management already manages the Spring Boot version. If that dependency management mechanism is not used, also import the Spring Boot dependencies BOM according to the project's Gradle setup.

With Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'

    implementation platform('org.springdoc:springdoc-openapi-bom:3.2.0')
    implementation 'org.springdoc:springdoc-openapi-starter-webmvc-ui'
}
~~~

Change `3.2.0` and the starter according to the Boot line, web stack, and documentation goals of the application. Do not mix WebMVC and WebFlux starters in the same runtime just to try both modules.

## 11. Understanding Module Differences Between springdoc v1 and v2/v3

When upgrading from springdoc v1 to v2 or v3, artifact names and some Java packages changed. For example:

| springdoc v1 | springdoc v2/v3 | Meaning |
|---|---|---|
| `springdoc-openapi-webmvc-core` | `springdoc-openapi-starter-webmvc-api` | OpenAPI for Spring MVC |
| `springdoc-openapi-webflux-core` | `springdoc-openapi-starter-webflux-api` | OpenAPI for WebFlux |
| `springdoc-openapi-ui` | `springdoc-openapi-starter-webmvc-ui` | Swagger UI for Spring MVC |
| `springdoc-openapi-webflux-ui` | `springdoc-openapi-starter-webflux-ui` | Swagger UI for WebFlux |
| `org.springdoc.core.GroupedOpenApi` | `org.springdoc.core.models.GroupedOpenApi` | API group package |
| `org.springdoc.core.customizers.OpenApiCustomiser` | `org.springdoc.core.customizers.OpenApiCustomizer` | Customizer name |
| `org.springdoc.api.annotations.ParameterObject` | `org.springdoc.core.annotations.ParameterObject` | ParameterObject package |

Do not just change the version in the POM while keeping all imports untouched. When upgrading major versions, read the migration guide of the target line and update packages/imports accordingly. v2 and v3 use the new starter structure; v3 targets Spring Boot 4, and v2 targets Spring Boot 3.

## 12. Avoiding Transitive Dependency Conflicts

springdoc pulls in components related to OpenAPI and Swagger UI. Do not individually override the following dependencies without solid evidence of need:

- `io.swagger.core.v3:swagger-core` or `swagger-annotations`.
- Swagger UI artifacts.
- Jackson databind and Jackson modules.
- Spring Framework modules such as `spring-web`, `spring-core`, `spring-context`.
- Servlet API or Reactive Streams API.

For instance, forcing `swagger-core` to a newer version can cause springdoc to call an API that no longer exists in the forced version or cause schemas to serialize differently than expected. Similarly, forcing `spring-web` onto a different line from Spring Boot can create runtime linkage errors.

Safety rules:

1. Let the Spring Boot BOM manage the Spring and Jackson dependencies supported by Boot.
2. Let the springdoc BOM manage springdoc modules when using multiple artifacts.
3. Only override a transitive dependency after identifying the root cause, verifying compatibility, and adding regression tests.
4. Document the reason for the override and who is responsible for updating it.

## 13. Inspecting the Dependency Graph After Adding springdoc

With Maven:

~~~bash
./mvnw dependency:tree -Dincludes=org.springdoc,org.springframework,io.swagger.core.v3,com.fasterxml.jackson.core
~~~

With Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-webmvc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

When reading the output, pay attention to:

- Whether multiple versions of the same artifact exist.
- Whether the selected version comes from a BOM, constraint, resolution rule, or direct dependency.
- Whether old springdoc v1 modules remain in the graph.
- Whether both WebMVC and WebFlux starters are present simultaneously.
- Whether `swagger-core` or Jackson is forced to a version different from what springdoc expects.

Seeing a dependency in the tree is not necessarily an error. What matters is whether the resolved version belongs to a compatible combination and whether it conflicts with other modules.

## 14. Verifying the Selection with an Application Run

After dependencies resolve and the build succeeds, verify that integration works at runtime:

1. Start the application with a profile close to the deployment environment.
2. Check logs to confirm there are no `NoSuchMethodError`, `ClassNotFoundException`, or auto-configuration errors.
3. Call `GET /v3/api-docs` and confirm OpenAPI JSON is returned.
4. Call `GET /v3/api-docs.yaml` if the application exposes YAML.
5. Open `/swagger-ui.html` if the UI starter was chosen.
6. Verify an actual path, operation, parameter, and schema in the document.
7. Call a business endpoint to ensure adding springdoc did not alter mappings or security.

Example:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
~~~

If the application uses a context path, a different port, or a custom docs path, adjust the URL according to configuration. Do not conclude the library is broken when the request is calling the wrong base path.

## 15. Quick Decision Matrix

| Situation | Initial Choice |
|---|---|
| Boot 4.1.x + Spring MVC + Swagger UI needed | springdoc 3.1.x–3.2.x, `webmvc-ui` |
| Boot 4.0.x + WebFlux + JSON/YAML only | springdoc 3.0.x, `webflux-api` |
| Boot 3.5.x + Spring MVC + Swagger UI needed | springdoc 2.8.x–2.10.x, `webmvc-ui` |
| Boot 3.3.x + WebFlux + JSON/YAML only | springdoc 2.6.x, `webflux-api` |
| Boot 3.0.x + Spring MVC + Swagger UI needed | springdoc 2.0.x–2.1.x, `webmvc-ui` |
| Boot 2.7.x + Spring MVC | springdoc v1; check legacy limits and open-source release `1.8.0` |
| Any Boot line needing only OpenAPI artifact builds | Choose `*-api` starter matching web stack and major |
| Swagger UI needed in the application | Choose `*-ui` starter matching web stack and major |

This table is for choosing an initial direction. Before merging, still confirm Java, Spring Framework, the dependency graph, and runtime smoke tests.

## 16. Common Version Selection Errors

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Boot 3 but springdoc 3.x added | Confusing springdoc major with Spring Boot major | Use the springdoc 2.x line for Boot 3 |
| Boot 4 but springdoc 2.x used | Copying dependencies from an old Boot 3 project | Use the springdoc 3.x line per Boot 4 matrix |
| `/v3/api-docs` returns 404 | Starter does not match web stack or auto-configuration not loaded | Check MVC/WebFlux starter and dependency graph |
| `NoSuchMethodError` after adding library | Spring/Swagger/Jackson version conflict | Inspect dependency tree and remove unnecessary overrides |
| `ClassNotFoundException` for Servlet | Mixing `javax.*` and `jakarta.*` | Align Boot major and namespace |
| Swagger UI missing while JSON docs work | Currently using `*-api` starter | Switch to `*-ui` starter if UI is needed |
| Swagger UI fails when using WebFlux | WebMVC starter was chosen | Choose `springdoc-openapi-starter-webflux-ui` |
| Using springdoc v1 on Boot 3/4 | Keeping legacy artifact after Boot upgrade | Switch to v2 for Boot 3 or v3 for Boot 4 |
| Build passes but runtime fails | Runtime dependencies or auto-configuration not verified | Run app, call `/v3/api-docs`, inspect logs |
| Version differs between local machine and CI | Version not pinned or different BOMs | Pin BOM/version and inspect effective dependency graph |
| Docs wrong after forcing Jackson | Jackson version out of sync with Boot/springdoc | Remove override or verify compatibility with tests |
| Group does not appear | Group bean not component-scanned or starter/config wrong | Check group configuration and package scan |

## 17. Library Selection Workflow Before Committing

Proceed step by step:

1. Read the Spring Boot version from the project's parent, BOM, or plugin.
2. Confirm the actual Spring Framework version on the runtime classpath.
3. Check the Java target and Java runtime.
4. Identify the `javax.*` vs. `jakarta.*` namespace.
5. Identify the web stack: Spring MVC or WebFlux.
6. Consult the correct springdoc v1, v2, or v3 matrix page.
7. Pick the latest stable patch within the published compatible range.
8. Select `webmvc`/`webflux` and `api`/`ui` starter per requirements.
9. Use the appropriate BOM to manage modules.
10. Inspect the dependency graph, build, and runtime endpoints.
11. Save the chosen version in the build file and document any overrides.
12. Run smoke tests in CI to catch regressions when dependencies change.

## 18. Pre-Merge Checklist

- [ ] Exact Spring Boot version identified.
- [ ] Spring Framework and Java runtime versions cross-checked.
- [ ] Correct springdoc major selected per official matrix.
- [ ] `javax.*`/`jakarta.*` namespace checked.
- [ ] Correct WebMVC or WebFlux starter selected.
- [ ] `*-api` or `*-ui` chosen according to needs.
- [ ] springdoc v1, v2, and v3 modules not mixed in the same runtime.
- [ ] Spring Boot BOM manages Spring dependencies.
- [ ] springdoc BOM used when multiple springdoc modules need alignment.
- [ ] No arbitrary overrides of swagger-core, Jackson, or Spring Framework.
- [ ] Dependency tree has no unexplained conflicts.
- [ ] Application starts successfully.
- [ ] `/v3/api-docs` returns a valid document.
- [ ] Swagger UI works if the UI starter was chosen.
- [ ] Smoke test for documentation endpoints exists in CI.

## 19. Official References

- [springdoc-openapi v3 — Compatibility matrix and getting started](https://springdoc.org/) — Spring Boot 4 matrix, dependency starters, WebMVC/WebFlux modules, and BOM.
- [springdoc-openapi v2 — Compatibility matrix](https://springdoc.org/v2/) — springdoc 2.x ranges compatible with Spring Boot 3.x.
- [springdoc-openapi v1 — Compatibility matrix](https://springdoc.org/v1/) — legacy releases supporting Spring Boot 2.x and 1.x.
- [Spring Boot — System Requirements](https://docs.spring.io/spring-boot/system-requirements.html) — Java, Spring Framework, and build tool requirements by Boot version.
- [Spring Framework — Supported Versions](https://github.com/spring-projects/spring-framework/wiki/Spring-Framework-Versions) — framework lifecycle, JDK range, and Java/Jakarta EE namespace.
- [springdoc-openapi — GitHub repository](https://github.com/springdoc/springdoc-openapi) — source code, releases, and project guides.

Reading the compatibility matrix before choosing the library helps eliminate mismatched major combinations early. Afterward, cross-check Java, Spring Framework, namespace, and web stack, select the right starter, inspect the dependency graph, and verify documentation endpoints at runtime. A selection is only complete when the build, application, and OpenAPI document all work in the real configuration.
