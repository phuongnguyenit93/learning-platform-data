# Declaring Dependencies with Maven or Gradle

## 1. Why Must Springdoc Dependencies Be Declared Correctly?

Springdoc OpenAPI reads metadata from a Spring Boot application to generate an OpenAPI document and, when using a UI module, serve Swagger UI. For this process to work, the application must declare the right library matching its web stack, Spring Boot version, and deployment needs.

Declaring the wrong artifact or wrong major version can prevent the application from starting, skip registering the `/v3/api-docs` endpoint, omit Swagger UI, cause runtime class errors, or pull in two incompatible library sets.

The SPRINGDOC_OPENAPI module focuses on using springdoc-openapi to generate and customize OpenAPI specifications and Swagger UI from Spring Boot controllers. Therefore, dependency choices must support these needs: describing requests/responses, schemas, security, document groups, exporting JSON/YAML, contract testing, and distributing API documentation.

Maven and Gradle both manage the dependency graph, though syntax and version centralization differ. You must understand which artifact to select before adding it to a build file.

## 2. Choosing a Starter by Web Stack

Springdoc provides different artifacts for Spring MVC and Spring WebFlux. Choose based on the application's actual stack:

| Web Stack | Starter with Swagger UI | Starter for API docs only |
|---|---|---|
| Spring MVC | springdoc-openapi-starter-webmvc-ui | springdoc-openapi-starter-webmvc-api |
| Spring WebFlux | springdoc-openapi-starter-webflux-ui | springdoc-openapi-starter-webflux-api |

Starters with the ui suffix typically integrate OpenAPI endpoints and Swagger UI. Starters with the api suffix provide OpenAPI document generation without packaging the Swagger UI interface.

A Spring MVC application using spring-boot-starter-web usually chooses the webmvc starter. A reactive application using spring-boot-starter-webflux usually chooses the webflux starter.

Do not add both webmvc-ui and webflux-ui to the same application just to experiment. The two web stacks handle requests differently and can pull in unintended auto-configuration.

If the application has a special architecture or uses both stacks, clearly verify the actual runtime and Springdoc's guide for the corresponding version before choosing dependencies.

## 3. Distinguishing UI Starters and API Starters

Choose the starter based on where documentation will be used:

**Use the UI starter when:**

- Developers need to open Swagger UI in a browser.
- The team needs to test requests directly with Try it out.
- The application serves documentation to integrators.
- You want an out-of-the-box interface without building a custom docs page.

**Use the API starter when:**

- Only OpenAPI JSON/YAML endpoints are needed.
- CI downloads the document to validate, lint, or diff contracts.
- Another developer portal renders the OpenAPI document.
- You want to reduce UI resources in the production runtime.

Disabling Swagger UI via a property is not the same as excluding the UI dependency from the artifact. If the project does not need a UI in any environment, the API starter states that intent more clearly.

Regardless of which starter is used, the OpenAPI document can still be served via the Springdoc endpoint if api-docs is enabled.

## 4. Checking Compatibility Between Spring Boot and Springdoc

Springdoc has different artifact lines for each Spring Boot major version. Do not choose a dependency just because artifact names look similar.

General rule:

| Platform | Typical Corresponding Springdoc Line | Notes |
|---|---|---|
| Spring Boot 2.x | Springdoc 1.x, legacy artifacts | Use artifacts like springdoc-openapi-ui or springdoc-openapi-webflux-ui by stack |
| Spring Boot 3.x | Springdoc 2.x, new starters | Use starters with webmvc or webflux suffix |
| Newer Spring Boot majors | Check Springdoc compatibility matrix | Do not infer Springdoc major solely from Spring Boot major number |

Spring Boot 3 moved to Jakarta EE APIs, so dependencies must be compatible with the jakarta namespace. The Springdoc 2.x starter line is designed for the Spring Boot 3 platform. Do not arbitrarily combine legacy libraries using javax with a Jakarta application.

The table above is a selection guideline and does not replace the official compatibility matrix. Before pinning a version, check the exact Spring Boot patch line, Java version, Spring Framework, and supported Springdoc release.

Do not use dynamic versions like latest.release in release builds. Pin a specific version so local, CI, and production resolve the same dependency graph.

## 5. Declaring Dependencies with Maven

In a Maven project with an appropriate Spring Boot parent or dependency management, add the starter under dependencies.

Example for Spring MVC with Swagger UI:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>2.x.y</version>
    </dependency>
</dependencies>
~~~

Replace 2.x.y with a Springdoc version verified compatible with the project's Spring Boot version. Do not leave placeholders in pom.xml.

For WebFlux applications, replace the artifact with:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

If you only need OpenAPI endpoints without Swagger UI, use the corresponding API artifact:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Do not add both UI and API starters for the same web stack if the UI starter already provides the needed API features. Pick the single artifact matching your needs.

## 6. Managing the Springdoc Version in Maven

In multi-module projects, avoid repeating a version literal across multiple pom.xml files. You can declare a property in the parent POM:

~~~xml
<properties>
    <springdoc.version>2.x.y</springdoc.version>
</properties>
~~~

Then use that property as the Springdoc dependency version in the modules that need it. In illustrative examples, the 2.x.y version literal must be replaced with the corresponding Maven property reference in a real POM.

If multiple modules use Springdoc, you can place the dependency in the parent's dependencyManagement to centralize the version, while each module declares the artifacts it actually needs.

dependencyManagement example:

~~~xml
<dependencyManagement>
    <dependencies>
        <dependency>
            <groupId>org.springdoc</groupId>
            <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
            <version>2.x.y</version>
        </dependency>
    </dependencies>
</dependencyManagement>
~~~

Child modules can declare the dependency without repeating the version if dependencyManagement manages the exact artifact coordinates.

Do not place every Springdoc dependency into parent dependencies if some modules are not web applications. The parent should manage versions; child modules decide whether they need the library.

## 7. Declaring Dependencies with Gradle Groovy DSL

For build.gradle using Groovy DSL:

~~~groovy
dependencies {
    implementation 'org.springdoc:springdoc-openapi-starter-webmvc-ui:2.x.y'
}
~~~

With WebFlux:

~~~groovy
dependencies {
    implementation 'org.springdoc:springdoc-openapi-starter-webflux-ui:2.x.y'
}
~~~

OpenAPI API only:

~~~groovy
dependencies {
    implementation 'org.springdoc:springdoc-openapi-starter-webmvc-api:2.x.y'
}
~~~

Replace the version placeholder with a pinned compatible release. Gradle uses implementation so the dependency is on the module's compile classpath and the application's runtime classpath.

Do not use testImplementation for dependencies the application needs at actual runtime. If Springdoc is only in test scope, tests might see the classes while the executable application lacks docs endpoints.

## 8. Declaring Dependencies with Gradle Kotlin DSL

For build.gradle.kts:

~~~kotlin
dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:2.x.y")
}
~~~

WebFlux:

~~~kotlin
dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webflux-ui:2.x.y")
}
~~~

API-only:

~~~kotlin
dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-api:2.x.y")
}
~~~

Kotlin DSL uses function calls and parentheses. Coordinates follow the same group:artifact:version format as Groovy DSL.

If using convention plugins or shared build logic, you can place dependency declarations in a shared location. Still, a module should only receive the starter matching its own web stack.

## 9. Managing Versions with Gradle Version Catalog

In multi-module Gradle projects, a Version Catalog helps centralize versions and aliases.

Example gradle/libs.versions.toml:

~~~toml
[versions]
springdoc = "2.x.y"

[libraries]
springdoc-webmvc-ui = { module = "org.springdoc:springdoc-openapi-starter-webmvc-ui", version.ref = "springdoc" }
springdoc-webflux-ui = { module = "org.springdoc:springdoc-openapi-starter-webflux-ui", version.ref = "springdoc" }
springdoc-webmvc-api = { module = "org.springdoc:springdoc-openapi-starter-webmvc-api", version.ref = "springdoc" }
~~~

Then in build.gradle.kts:

~~~kotlin
dependencies {
    implementation(libs.springdoc.webmvc.ui)
}
~~~

Or a WebFlux module:

~~~kotlin
dependencies {
    implementation(libs.springdoc.webflux.ui)
}
~~~

Gradle generates accessors from aliases in the catalog. The alias springdoc-webmvc-ui is typically accessed as libs.springdoc.webmvc.ui in Kotlin DSL.

A Version Catalog centralizes versions and dependency names; it does not guarantee the version is compatible. The team still needs to check the compatibility matrix before upgrading.

## 10. Using Properties or Convention Plugins in Gradle

If not yet using a Version Catalog, you can manage versions with a Gradle property or extra property in shared build logic.

Example declaring directly in a build script:

~~~kotlin
val springdocVersion = "2.x.y"

dependencies {
    implementation(
        "org.springdoc:springdoc-openapi-starter-webmvc-ui:$springdocVersion"
    )
}
~~~

In large projects, avoid declaring the same version separately across multiple subprojects. Use a Version Catalog or convention plugin so all modules follow one policy.

Do not create new version variables per module if they must always stay synchronized. A single version management location makes upgrade reviews easier and reduces the risk of one service running a different Springdoc major than the others.

## 11. Maven vs. Gradle: Which Management Approach to Choose?

| Criterion | Maven | Gradle |
|---|---|---|
| Declaring dependencies | dependencies/dependency in pom.xml | implementation in build.gradle or build.gradle.kts |
| Centralized versions | Parent properties and dependencyManagement | Version Catalog, convention plugin, or shared property |
| Inspecting dependencies | dependency:tree | dependencies, dependencyInsight |
| Runtime/compile scope | Maven scope | Gradle configuration |
| Multi-module | Parent POM and modules | Root build, subprojects, and convention plugins |
| Locking | Dependency management and supporting plugins | Built-in dependency locking |

Neither option automatically makes Springdoc more compatible. What matters is that versions are pinned, artifacts match the web stack, and the dependency graph contains no conflicting versions.

Use the build tool the project has already chosen. Do not add Gradle just to declare one dependency for a Maven application or vice versa.

## 12. Understanding Dependency Scope and Configuration

In Maven, dependencies without an explicit scope default to compile scope. The Springdoc starter must be present when the application runs, so do not put it in test scope.

Common scopes:

- compile: present on compile and runtime classpaths.
- runtime: not needed for compile, present at runtime.
- provided: expected to be supplied by the deployment environment.
- test: present only on the test classpath.

In Gradle, implementation is usually the right choice for starters needed at both compile time and runtime. testImplementation is only for libraries used exclusively in tests.

Do not use compileOnly for a Springdoc starter if auto-configuration and endpoints are needed at runtime. The application may compile but fail at runtime with missing classes or unregistered beans.

If the project uses special packaging, inspect the executable JAR or container image contents to verify the dependency is actually packaged.

## 13. Do Not Declare Multiple Unnecessary Starters Simultaneously

Some common misconfigurations:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.x.y</version>
</dependency>
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Since the UI starter already includes API documentation support, also declaring the API starter for the same stack is usually unnecessary. It can complicate the dependency graph and increase the risk of version conflicts if the two dependencies are managed differently.

Another mistake is adding both WebMVC and WebFlux starters even though the app uses only one stack. Add only the dependencies the application truly needs.

If you need specialized Springdoc features such as Data REST, Security, or Kotlin support, check the corresponding module in the documentation for the right version. Do not manually add internal artifacts just because you saw their names in the dependency tree.

## 14. Avoiding Mixing Springdoc 1.x and 2.x

The Springdoc 1.x line uses legacy artifacts such as:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-ui</artifactId>
    <version>1.8.x</version>
</dependency>
~~~

The Springdoc 2.x line uses the new starters, for example:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.x.y</version>
</dependency>
~~~

Do not add both lines to the same application. They have different module structures, dependencies, and compatibility platforms.

When upgrading from 1.x to 2.x, update artifact coordinates according to the migration guide, and verify Jakarta namespace, Swagger Core, and Spring Boot compatibility. Do not merely change the version number on an old dependency and expect the new starter behavior to work.

## 15. Do Not Arbitrarily Override Swagger Core

Springdoc depends on Swagger Core libraries to process annotations and OpenAPI models. Starters usually declare the necessary compatible dependencies.

If the project manually adds swagger-core, swagger-models, or swagger-annotations with a different version, it can create binary incompatibilities:

- NoSuchMethodError when runtime calls a method missing in the loaded version.
- NoClassDefFoundError when a class is missing.
- Annotations not read as expected.
- Schemas or documents serialized incorrectly.
- Multiple versions of the same library on the classpath.

Do not add Swagger Core just to use @Schema or @Operation; the Springdoc starter usually already supplies the required annotation dependency via transitive dependencies.

Only override a version when there is a technical reason, compatibility has been verified, and tests confirm it. Document the reason in dependency management so future upgraders understand the constraint.

## 16. Inspecting the Dependency Tree with Maven

Use dependency:tree to see which Springdoc and Swagger Core versions are actually resolved:

~~~bash
./mvnw dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3
~~~

You can inspect the full dependency tree when needed:

~~~bash
./mvnw dependency:tree
~~~

Focus on checking:

- Exactly one Springdoc major line is used.
- The webmvc or webflux artifact matches the application.
- No Swagger Core version is unexpectedly overridden.
- No legacy dependency is pulled from another module.
- Runtime scope includes the necessary starter.

If Maven picks a version different from the one declared directly, check dependencyManagement, the parent POM, and mediation rules. Maven may select the nearest dependency in the graph when version management is not explicit.

Do not exclude transitive dependencies mechanically. Before excluding, identify which dependency pulls the library in and whether the starter genuinely needs it.

## 17. Inspecting the Dependency Graph with Gradle

Gradle can display the dependency graph:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

To find the source of a dependency:

~~~bash
./gradlew dependencyInsight \
  --dependency springdoc-openapi \
  --configuration runtimeClasspath
~~~

You can run dependencyInsight for Swagger Core when suspecting a version conflict:

~~~bash
./gradlew dependencyInsight \
  --dependency swagger-core \
  --configuration runtimeClasspath
~~~

Inspect the runtimeClasspath configuration because that is where dependencies must be present when the app runs. CompileClasspath might look right while runtimeClasspath is missing something or resolves a different version.

If using dependency locking, update the lockfile following the project workflow after verifying versions. Do not delete the lockfile just to let Gradle pick a new dependency graph.

## 18. Distinguishing Compile-Time and Runtime Errors

A dependency can let the build compile successfully while causing the application to fail at runtime.

| Symptom | Where to Check |
|---|---|
| Annotation package not found at compile time | Compile classpath and annotation artifact |
| App starts but /v3/api-docs returns 404 | Starter, auto-configuration, and profile |
| Swagger UI lacks static resources | Whether UI starter or API-only starter is used |
| NoClassDefFoundError | Runtime dependency graph |
| NoSuchMethodError | Version conflict between Springdoc and Swagger Core |
| Bean creation exception | Compatibility, auto-configuration, and classpath |
| MVC handlers not detected | Wrong web stack chosen or MVC configuration |
| WebFlux endpoints do not appear | MVC starter chosen by mistake or reactive mapping |
| Annotations ignored | Swagger annotations version/namespace and scan config |

When errors occur, record the first stack trace and the dependency tree. Do not randomly add another artifact to fix an error before knowing which class is missing or which version is mismatched.

## 19. Verifying Endpoints After Adding Dependencies

After building and running the application, check the documentation endpoint:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs
~~~

If using the Swagger UI starter, open:

~~~text
http://localhost:8080/swagger-ui/index.html
~~~

If using the API-only starter, do not expect Swagger UI to be packaged. OpenAPI JSON/YAML can still function.

Verify the document contains:

- The openapi field.
- info.title and info.version.
- Expected operations under paths.
- Needed schemas under components.
- Response and security metadata.
- Server URL matching the environment.

HTTP 200 alone is not enough to verify documentation. The response could be an HTML login page or an empty document. In CI, parse and validate the document using an OpenAPI-aware tool.

## 20. Checking Dependencies in Tests

You can use a Spring Boot test with MockMvc to verify the docs endpoint:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiEndpointTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void shouldExposeOpenApiDocument() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.openapi").exists())
            .andExpect(jsonPath("$.info.title").exists());
    }
}
~~~

The test requires appropriate imports and static imports in the project. If API docs are protected, the test must authenticate with an appropriate user/role or configure test security intentionally.

With WebFlux, use WebTestClient instead of MockMvc for reactive endpoints.

A simple test helps catch an unloaded starter, disabled api-docs, or changed paths. It does not replace contract validation and full schema verification.

## 21. Multi-Module and Shared Dependency Management

In multi-module Maven projects, the parent POM can manage the Springdoc version centrally via properties or dependencyManagement. Specific web modules declare the starter matching their stack.

In multi-project Gradle builds, a Version Catalog or convention plugin can manage aliases/versions. API modules select the appropriate alias, such as webmvc-ui or webflux-api.

Do not force every module to depend on Springdoc if that module does not expose an HTTP API. A domain or persistence library module usually does not need a web documentation starter.

If multiple services need Springdoc, align versions under a shared policy while still allowing controlled upgrades when a service has different compatibility needs. Do not apply one global dependency block to all subprojects.

## 22. Springdoc Version Upgrade Process

When upgrading Springdoc:

1. Identify current Spring Boot and Java versions.
2. Check the Springdoc compatibility matrix.
3. Verify the artifact matches the web stack.
4. Update the version in the centralized management location.
5. Read release notes and migration notes.
6. Check transitive Swagger Core dependencies.
7. Clean build and run tests.
8. Start the application and download JSON/YAML.
9. Check Swagger UI if using the UI starter.
10. Validate the document and compare the contract diff.
11. Check behavior of annotations, customizers, and document groups.
12. Commit lockfile or dependency changes per project workflow.

Do not upgrade Spring Boot, Springdoc, Swagger Core, and build plugins all at once unless necessary. Changing one group in a controlled manner makes it easier to identify root causes if regressions occur.

## 23. Common Mistakes When Declaring Maven or Gradle Dependencies

| Symptom | Common Cause | Resolution |
|---|---|---|
| Maven cannot resolve artifact | Wrong groupId/artifactId or repository | Check artifact coordinates and repository |
| Gradle cannot find module | Wrong coordinates or non-existent version | Check catalog and dependency declaration |
| /v3/api-docs returns 404 | Wrong starter, docs disabled, or wrong profile | Check web stack and api-docs.enabled |
| Swagger UI missing | Using API-only starter | Switch to UI starter if interface is needed |
| NoClassDefFoundError | Missing dependency on runtime classpath | Inspect runtime dependency tree |
| NoSuchMethodError | Swagger Core/Springdoc version conflict | Check dependency mediation and overrides |
| javax/jakarta class mismatch | Mixing dependencies from different Spring Boot majors | Use compatible Springdoc line |
| Both MVC and WebFlux loaded | Added multiple unnecessary starters | Choose exactly one stack |
| Annotations have no effect | Missing or mismatched Swagger annotations | Check resolved dependency |
| CI and local give different results | Dynamic versions or differing lockfiles/configs | Pin versions and reproduce dependency graph |

Do not solve problems by adding all starters or forcing every dependency to the same version number. That can mask the initial error and create new conflicts.

## 24. Checklist Before Committing Dependencies

Before committing Maven or Gradle changes:

- Spring Boot major/minor and Java version identified.
- Whether the app uses Spring MVC or WebFlux identified.
- UI starter or API-only starter selected per needs.
- Springdoc version chosen per compatibility matrix.
- Specific version pinned.
- Legacy Springdoc 1.x not mixed with 2.x starters.
- UI and API starters for the same stack not both declared needlessly.
- WebMVC and WebFlux starters not both added arbitrarily.
- Swagger Core not overridden without reason.
- Dependency tree/runtimeClasspath inspected.
- Built and tests passed.
- Verified /v3/api-docs returns a valid document.
- Verified Swagger UI if the project needs an interface.
- Updated lockfile or parent dependency management per workflow.

## 25. Principles for Selecting and Managing Dependencies

When declaring Springdoc with Maven or Gradle:

1. Choose the artifact based on Spring MVC or Spring WebFlux.
2. Choose the UI starter if Swagger UI is needed; choose the API starter if only document endpoints are needed.
3. Match the Spring Boot major to the compatible Springdoc line.
4. Use explicitly pinned versions and manage them centrally.
5. Keep dependencies in appropriate compile/runtime scopes.
6. Avoid mixing Springdoc 1.x and 2.x or mixing javax/jakarta namespaces.
7. Do not duplicate starters or arbitrarily override Swagger Core.
8. Inspect the dependency tree with Maven or Gradle.
9. Verify JSON/YAML endpoints and Swagger UI after startup.
10. Run contract validation and tests before upgrading versions.

A proper dependency declaration reflects the application's actual web stack, platform version, and runtime needs. When versions are managed centrally, the dependency graph is inspected, and documentation endpoints are verified after builds, Springdoc becomes a stable part of the API development and release pipeline.

## 26. References

- Springdoc OpenAPI documentation: https://springdoc.org/
- Springdoc compatibility and migration documentation: https://springdoc.org/#getting-started
- Spring Boot dependency management: https://docs.spring.io/spring-boot/reference/using/build-systems.html
- Maven dependency mechanism: https://maven.apache.org/guides/introduction/introduction-to-dependency-mechanism.html
- Gradle dependency management: https://docs.gradle.org/current/userguide/dependency_management.html
- Gradle Version Catalogs: https://docs.gradle.org/current/userguide/version_catalogs.html

