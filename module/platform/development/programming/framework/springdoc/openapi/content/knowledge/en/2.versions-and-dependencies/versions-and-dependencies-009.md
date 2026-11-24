# Avoiding Mixing Springfox, Springdoc, and Incompatible Swagger Libraries

A Spring Boot application should have only one toolset responsible for generating API documentation. If Springfox, Springdoc, multiple versions of Swagger Core, or multiple Swagger UI packages are placed on the classpath simultaneously, the application can encounter startup errors, library linkage failures, duplicate documentation endpoints, or annotations not being recognized as expected. These errors often appear after upgrading Spring Boot or adding a documentation dependency without checking existing dependencies.

To avoid conflicts, identify the exact Spring Boot generation, choose one appropriate Springdoc or Springfox line, use the right starter for Spring MVC or WebFlux, and keep Swagger libraries on compatible versions. When migrating from Springfox to Springdoc, migrate dependencies, annotations, and Java configuration together.

## 1. Distinguishing OpenAPI, Swagger, Springfox, and Springdoc

These names are related but do not refer to the same component:

- **OpenAPI** is the specification describing an HTTP API contract in JSON or YAML. An OpenAPI document describes paths, operations, parameters, request bodies, responses, schemas, and security schemes.
- **Swagger** is the name of the tool ecosystem built around OpenAPI, including Swagger UI and Swagger Core libraries. In practice, many developers also use the word "Swagger" loosely to refer to API documentation or annotations.
- **Springfox** is an API documentation integration project for Spring. It has its own dependencies, configuration, and annotation processing. Springfox 3 added OpenAPI 3 support alongside earlier Swagger capabilities, but remains an independent implementation separate from Springdoc.
- **Springdoc OpenAPI** is the library integrating Spring Boot with OpenAPI. It reads Spring controllers, data types, annotations, and configuration to generate the specification, and can also integrate Swagger UI.

Therefore, "using OpenAPI" does not inherently mean using Springfox or Springdoc. OpenAPI is the contract format; Springfox and Springdoc are implementation choices to generate or serve documentation in a Spring application.

### Two Common Annotation Generations

A common source of confusion is the following two annotation namespaces:

| Annotation Group | Package | Examples |
| --- | --- | --- |
| Swagger Core v1 / Swagger 2 annotations | `io.swagger.annotations` | `@Api`, `@ApiOperation`, `@ApiModel`, `@ApiParam` |
| Swagger Core v2 / OpenAPI 3 annotations | `io.swagger.v3.oas.annotations` | `@Tag`, `@Operation`, `@Schema`, `@Parameter` |

Annotation names between the two generations can look similar, yet their packages, purposes, and interpretations differ. Springdoc uses the OpenAPI 3 annotation system in `io.swagger.v3.oas.annotations`. When migrating from an old Springfox setup, only renaming annotations in source code while keeping old imports will prevent Springdoc from reading metadata as expected.

For example, `@ApiOperation` from the old namespace is not a drop-in replacement for `@Operation`. Update imports and adjust attributes to the new API:

```java
// OpenAPI 3 annotations used with Springdoc
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.tags.Tag;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.Parameter;

@Tag(name = "Books", description = "Book management API")
class BookControllerDocumentation {

    @Operation(summary = "Find book by ID")
    void findBook(
            @Parameter(description = "Book ID") long id) {
        // Illustrative example showing metadata declaration.
    }
}

@Schema(description = "Book information")
record BookResponse(long id, String title) {}
```

This is a metadata example; an actual controller still needs Spring mapping annotations such as `@RestController`, `@GetMapping`, and business logic.

## 2. Choosing the Springdoc Version by Spring Boot Generation

Spring Boot 3 moved to Spring Framework 6 and Jakarta EE, where many legacy Java EE packages changed from `javax.*` to `jakarta.*`. This is an important boundary when choosing an API documentation library.

| Application Platform | Typical Springdoc Line | Notes |
| --- | --- | --- |
| Spring Boot 1.x/2.x | Springdoc 1.x | Choose a 1.x release compatible with the project's Spring Boot minor and Java version |
| Spring Boot 3.x and above | Springdoc 2.x and above | Use modern starters built on Spring Framework 6 and Jakarta |

Do not just pick the latest Springdoc version and add it to an old Boot application. Conversely, do not keep Springdoc 1.x when upgrading an application to Boot 3. Even if package names in source code still compile in some cases, underlying `javax`/`jakarta` classes, Spring Framework, and transitive dependencies may be incompatible at runtime.

The table above only provides guidance by major generation. When picking a specific version, cross-check Springdoc's compatibility matrix against the project's actual Spring Boot, Java, and Spring Framework versions. Do not independently upgrade Swagger Core or Swagger annotations to fix a compatibility error before identifying which dependency manages that version.

### Dependency Example for Spring Boot 3 and Spring MVC

For a Spring MVC application running on Spring Boot 3, use the corresponding Springdoc 2.x UI starter:

```xml
<properties>
    <springdoc.version>2.x.y</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

`2.x.y` is a placeholder; replace it with a specific version confirmed compatible with the project's Spring Boot version. The `webmvc-ui` starter integrates OpenAPI generation for Spring MVC and the Swagger UI interface.

### Dependency Example for Spring Boot 2 and Spring MVC

For applications in the Spring Boot 2 generation, use the Springdoc 1.x line and its corresponding artifact:

```xml
<properties>
    <springdoc.version>1.x.y</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

Artifact names in Springdoc 1.x differ from the `springdoc-openapi-starter-*` starters of the 2.x line. Do not copy Boot 3 dependencies verbatim into a Boot 2 project or vice versa. Verify that the chosen 1.x release supports the exact Boot minor version in use.

### Choosing a Starter for Spring MVC vs. WebFlux

Springdoc provides separate artifacts for the two main web models:

| Application Model | Springdoc 2.x with Swagger UI |
| --- | --- |
| Spring MVC | `springdoc-openapi-starter-webmvc-ui` |
| Spring WebFlux | `springdoc-openapi-starter-webflux-ui` |

Choose the starter matching the application's actual web stack. Do not add both starters "just in case"; Spring Boot has context-selection rules when multiple web stacks appear, and mixing them increases the chance of ambiguous configuration. If only OpenAPI endpoints without a UI are needed, consider the corresponding `*-api` starter in the Springdoc 2.x line instead of `*-ui`.

## 3. Error-Prone Ways of Mixing Dependencies

### Keeping Springfox and Adding Springdoc at the Same Time

Example of a `pom.xml` containing both dependency sets:

```xml
<dependencies>
    <dependency>
        <groupId>io.springfox</groupId>
        <artifactId>springfox-boot-starter</artifactId>
        <version>3.0.0</version>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

This configuration should be avoided in an application migrating to Springdoc. Both libraries can register controller scanning components, documentation configurations, or UIs simultaneously. The result can be multiple documentation endpoints, multiple Swagger UI configs, unwanted beans, or configuration-order-dependent behavior. Having both libraries on the classpath does not mean they are designed to coexist.

When choosing Springdoc, remove the Springfox starter and related Springfox modules from the application. If an internal library pulls Springfox in transitively, determine whether that library can be upgraded or have the dependency excluded.

### Adding Standalone Swagger Core or Annotations with Mismatched Versions

Springdoc already declares required Swagger dependencies through its own dependencies. Directly adding a different version of `swagger-core`, `swagger-annotations`, or `swagger-models` can cause Maven/Gradle to pick a version inconsistent with what Springdoc was tested against.

Specifically, the two annotation artifacts have different namespaces:

```xml
<!-- Swagger Core v1: legacy annotations -->
<dependency>
    <groupId>io.swagger</groupId>
    <artifactId>swagger-annotations</artifactId>
    <version>1.x</version>
</dependency>

<!-- Swagger Core v2: OpenAPI 3 annotations -->
<dependency>
    <groupId>io.swagger.core.v3</groupId>
    <artifactId>swagger-annotations</artifactId>
    <version>2.x</version>
</dependency>
```

Do not add both just because source code uses annotations from both packages. Migrate source code to OpenAPI 3 annotations if Springdoc is chosen, then remove the unneeded Swagger v1 dependency. If another library genuinely requires Swagger v1, check whether that library can be excluded or upgraded before keeping both generations alive together.

### Adding a Separate Swagger UI WebJar When the Starter Already Provides UI

Springdoc starters with the `-ui` suffix already integrate what is needed to serve Swagger UI. If you also add another Swagger UI WebJar or another documentation UI package, the application can contain duplicate UI assets or load the wrong OpenAPI configuration. Only add a standalone UI when there is a specific reason and you have verified how it is served; do not add one out of habit.

### Using Both Top-Level Starters and Old Submodules

A project might already have the umbrella starter and then add separate core, UI, or webmvc modules from an old guide. This can pull in multiple versions or duplicate configurations. Prefer a single starter matching the version and web stack; declare individual modules only when that version's documentation explicitly requires it.

## 4. Why Does Springfox Often Break When Upgrading Spring Boot?

Springfox was built during a period when the Spring and Spring Boot ecosystems had different underlying APIs than today. Two major changes to note:

- **Spring Boot 2.6 and path matching:** changes in how Spring MVC handles paths can cause Springfox 3.0.0 to fail during documentation initialization, often manifesting as errors related to `PatternsRequestCondition` or `PathPattern`. Some older Boot 2 projects used compatibility settings such as `spring.mvc.pathmatch.matching-strategy=ant_path_matcher`, but this is only a version-dependent workaround and should not be treated as a long-term solution for every project.
- **Spring Boot 3 and Jakarta:** Boot 3 is built on Spring Framework 6 and moved many APIs from `javax.*` to `jakarta.*`. Springfox 3.0.0 is not a compatible choice for this platform generation. Adding Springfox to a Boot 3 project can lead to missing class or method errors during compilation or startup.

If upgrading Boot 2 to Boot 3, this is the right time to migrate to Springdoc 2.x and complete annotation migration. If the application still runs Boot 2, you can continue using one toolset compatible with that platform while planning the upgrade; avoid adding Springdoc just to test alongside the existing runtime.

## 5. Process for Migrating from Springfox to Springdoc

The migration must be carried out synchronously across dependencies, annotations, configuration, and documentation verification.

### Step 1: Identify the Current Platform

Record the following before editing dependencies:

- Spring Boot and Spring Framework versions.
- Java version used to compile and run.
- Whether the app uses Spring MVC or WebFlux.
- Springfox, Springdoc, and Swagger Core declared directly or pulled transitively.
- Documentation and UI endpoints currently used in development, testing, and production environments.

Do not decide the Springdoc version solely from a dependency snippet found in another guide. The version must match the application's actual platform.

### Step 2: Remove the Springfox Dependency Set

Delete unused dependencies such as `springfox-boot-starter`, `springfox-swagger2`, `springfox-swagger-ui`, or other declared Springfox modules. Check transitive dependencies from internal libraries too. Do not let an old Springfox starter quietly linger after adding Springdoc.

### Step 3: Add the Right Springdoc Starter

Select Springdoc 1.x or 2.x according to the Spring Boot generation; select `webmvc` or `webflux` according to the application; select the `-ui` suffix if Swagger UI is needed. Avoid adding old and new Springdoc artifacts together.

### Step 4: Migrate Annotations

Common mappings when migrating from Swagger v1 annotations to OpenAPI 3:

| Old Annotation | Common OpenAPI 3 Annotation |
| --- | --- |
| `@Api` | `@Tag` |
| `@ApiOperation` | `@Operation` |
| `@ApiParam` | `@Parameter` |
| `@ApiModel` | `@Schema` |
| `@ApiModelProperty` | `@Schema` on field or property |
| `@ApiImplicitParam` | `@Parameter` or request declaration matching parameter location |

This is an intent-based mapping, not a mechanical attribute-by-attribute replacement. For example, request body descriptions should generally be represented via DTO types and `@RequestBody`; responses should describe schemas and status codes with `@ApiResponse`, `@Content`, and `@Schema` when needed. Check imports to ensure annotations belong to `io.swagger.v3.oas.annotations`.

Response description example:

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@Operation(summary = "Find book by ID")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Book found",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = BookResponse.class)
        )
    ),
    @ApiResponse(responseCode = "404", description = "Book not found")
})
```

### Step 5: Replace Springfox Configuration

Springfox typically uses `Docket` beans and configuration types in `springfox.documentation.*`. Springdoc can use `OpenAPI` beans, `GroupedOpenApi`, and OpenAPI 3 annotations. Do not keep `Docket` expecting Springdoc to convert it automatically.

Example creating a group with Springdoc 2.x:

```java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfig {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/public/**")
            .build();
    }
}
```

If `Docket` previously filtered packages, paths, headers, or configured responses, port each rule to the corresponding Springdoc configuration API and verify the resulting document. Not every Springfox-specific option has the same name or behavior in Springdoc.

### Step 6: Verify Documentation After Migration

Start the application and verify outputs matching configuration:

| Common Output | What to Verify |
| --- | --- |
| `/v3/api-docs` | Valid JSON containing the expected paths, schemas, and responses |
| `/v3/api-docs.yaml` | YAML matching the published contract |
| `/swagger-ui/index.html` | Swagger UI loads the desired OpenAPI document |
| `/v3/api-docs/{group}` | Each group contains the right endpoint scope |

If the application uses a context path, reverse proxy, or customized `server.servlet.context-path`, actual URLs may include a prefix. Verify both the browser-visited path and the document URL fetched by Swagger UI.

## 6. Inspecting the Dependency Tree for Conflicts

When an unexplained error appears after adding a documentation library, inspect the dependency tree before adding another dependency to "patch" a missing class.

### Maven

List libraries related to Springdoc, Springfox, and Swagger:

```bash
mvn dependency:tree -Dincludes=org.springdoc,io.springfox,io.swagger,io.swagger.core.v3,org.webjars
```

Look for these signs:

- Both `io.springfox` and `org.springdoc` present at runtime without an explicit reason.
- Multiple versions of `io.swagger.core.v3` or multiple versions of `swagger-annotations`.
- An internal library pulling an older Swagger Core version than Springdoc requires.
- Multiple Swagger UI packages or WebJars supplying the same resources.

Maven selects dependency versions using mediation rules, generally preferring the nearest dependency in the tree. Therefore, seeing a dependency in `pom.xml` does not guarantee that version wins at runtime. Read the dependency tree and dependency paths to know which component is winning.

### Gradle

With Gradle, inspect the runtime configuration:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

To find why a version was selected, run `dependencyInsight` on the module under inspection, for example:

```bash
./gradlew dependencyInsight \
  --dependency swagger-annotations \
  --configuration runtimeClasspath
```

Gradle selects versions using resolution rules and constraints. If you need to exclude a transitive dependency, place the exclusion on the exact dependency pulling it in and verify that the library still works after excluding it.

Do not force all Swagger dependencies to an arbitrary version via blanket overrides. Components such as `swagger-core`, `swagger-models`, and `swagger-annotations` belong to one compatible version set. Prefer versions managed by Springdoc; override only when there is a clear, tested technical reason.

## 7. Recognizing Common Errors

| Symptom | Possible Cause | Where to Check |
| --- | --- | --- |
| `ClassNotFoundException` or `NoClassDefFoundError` related to `javax.*`/`jakarta.*` | Library not from the same generation as Spring Boot or legacy dependencies remain | Check Boot 2/3, Springdoc 1.x/2.x, and dependency tree |
| `NoSuchMethodError` in `io.swagger.*` or `org.springdoc.*` | Modules loaded at incompatible versions | Use dependency tree or `dependencyInsight` to find actual versions |
| Springdoc ignores descriptions from annotations | Source still imports Swagger v1 annotations or wrong same-named class imported | Verify `io.swagger.v3.oas.annotations` package |
| Multiple UIs or documentation endpoints exist | Both Springfox and Springdoc active, or duplicate UI/WebJars | Check starters and UI assets on runtime classpath |
| App fails generating docs after Boot 2.6 upgrade | Interaction between Springfox and path matching mechanism | Inspect stack trace; consider migrating to matching Springdoc |
| Swagger UI opens but fails to load spec | Wrong doc URL, context path, proxy, or protected endpoint | Inspect `/v3/api-docs` request in Network tab and URL config |
| `/v3/api-docs` returns 404 | Missing right starter/API module, path changed, or docs disabled | Check dependencies, `springdoc.api-docs.path`, and environment config |

An error name is only a clue for narrowing scope, not a final conclusion. Use the full stack trace and your application's own dependency tree to identify the root cause.

## 8. Principles for Keeping the Classpath Stable

- Choose only one API documentation generator per application: Springfox or Springdoc.
- Choose Springdoc 1.x or 2.x according to the Spring Boot generation and exact compatibility table.
- Choose the WebMVC or WebFlux starter matching the application's web stack.
- Prefer the `-ui` starter when Swagger UI is needed; do not add a redundant WebJar.
- When using Springdoc, prefer OpenAPI 3 annotations in `io.swagger.v3.oas.annotations`.
- Remove Swagger v1 dependencies and Springfox configuration once migration is complete, unless a controlled compatibility requirement exists.
- Avoid overriding Swagger Core and submodule versions without knowing which dependency manages them.
- Inspect the dependency tree after adding, upgrading, or removing libraries.
- Verify JSON/YAML documents, Swagger UI, groups, and critical schemas after every change.

Keeping a single consistent documentation library set reduces classpath errors and clarifies the source of truth for the API contract. When upgrading Spring Boot or migrating from Springfox to Springdoc, treat dependencies, annotations, and configuration as one coordinated change, then verify the document generated from the running application.
