# Role of Swagger Annotations, Swagger Core, and WebJars

When integrating `springdoc-openapi` into Spring Boot, several components participate in generating and displaying API documentation. Swagger/OpenAPI annotations add meaning to controllers and DTOs; Swagger Core provides the data types, models, and utilities for working with the OpenAPI specification; WebJars package web UI resources such as JavaScript, CSS, and images. Springdoc connects these components with Spring's request mapping mechanism and provides documentation endpoints along with Swagger UI.

Understanding the role of each layer helps you select just the right dependencies, place them in the proper modules, and resolve version conflict errors. In particular, annotations, OpenAPI models, and the Swagger UI interface are three distinct types of components, even though they all come together in a single documentation page.

## 1. Big Picture of the Components

A typical documentation generation and rendering flow proceeds as follows:

1. Spring Boot initializes controllers, DTOs, Spring MVC or WebFlux configuration, and related beans.
2. Springdoc detects Spring endpoints, reads information from mappings, data types, and annotations, and builds the OpenAPI document.
3. Annotation types and OpenAPI models from the Swagger ecosystem supply metadata and standard structures to represent operations, schemas, responses, servers, and security.
4. Springdoc serves the document through JSON or YAML endpoints, typically `/v3/api-docs` and `/v3/api-docs.yaml`.
5. If a UI starter is used, Swagger UI assets are packaged inside a WebJar dependency. The browser downloads HTML, JavaScript, and CSS, then calls the document endpoint to render the interface.

| Component | Primary Responsibility | Examples |
|---|---|---|
| Springdoc OpenAPI | Integrates with Spring, detects endpoints, combines metadata, and exposes documentation/UI endpoints | `springdoc-openapi-starter-webmvc-ui` |
| Swagger annotations | Adds descriptions to operations, parameters, schemas, responses, and security | `@Operation`, `@Parameter`, `@Schema`, `@ApiResponse` |
| Swagger Core and related modules | Provides OpenAPI models and utilities for processing the specification | `OpenAPI`, `Info`, `Paths`, `Schema` |
| WebJars | Packages frontend assets inside JARs so Java apps can serve them from the classpath | `swagger-ui` WebJar |
| Swagger UI | Browser-based UI for reading documentation and testing requests | `/swagger-ui.html` page |

Springdoc is the bridge for the Spring ecosystem. Swagger Core is the foundational library of the Swagger/OpenAPI ecosystem. Swagger UI is the frontend application, and WebJars are the distribution mechanism for serving those frontend files in a Java application.

## 2. Swagger Annotations: Describing API Semantics

Springdoc can infer a lot of information from controllers and DTOs. For instance, `@GetMapping` indicates the HTTP method and path, `@PathVariable` indicates a path parameter, and the return type helps determine the response schema. However, Java signatures do not express full business semantics, such as possible error codes, field units, request examples, or authentication requirements.

Swagger annotations let you add this information directly on controllers, methods, parameters, or DTOs. Common annotations include:

| Annotation | Typical Location | Meaning |
|---|---|---|
| `@Tag` | Controller or operation group | Names and describes an API group |
| `@Operation` | Endpoint handler method | Describes the operation, summary, description, and responses |
| `@Parameter` | Method parameter | Describes query, path, header, or cookie parameters |
| `@Parameters` | Method or parameter | Groups multiple parameter annotations when needed |
| `@ApiResponse` and `@ApiResponses` | Method or operation | Describes response status codes, content, and schemas |
| Swagger's `@RequestBody` | Method or parameter | Describes the request body in the OpenAPI contract |
| `@Schema` | DTO, field, property, or data type | Adds schema name, description, example, constraints, and structure |
| `@Content` | Request body or response | Declares content media type and schema |
| `@ExampleObject` | Request/response content | Provides payload examples |
| `@SecurityScheme` | OpenAPI configuration | Declares an authentication mechanism such as HTTP Bearer or OAuth2 |
| `@SecurityRequirement` | Controller or operation | Attaches the requirement to use a declared security scheme |
| `@Hidden` | Supported controller, method, or element | Hides the element from the generated documentation |

These annotations live in the `io.swagger.v3.oas.annotations...` packages. They describe the API contract; they do not implement routing, validate requests, or perform authentication themselves. Those duties still belong to Spring MVC, Bean Validation, Spring Security, and business code.

### Endpoint Documentation Example

```java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.tags.Tag;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "Look up product information")
class ProductController {

    @GetMapping("/{id}")
    @Operation(
        summary = "Get product by ID",
        description = "Returns detailed information for a managed product."
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Product found",
            content = @Content(
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(responseCode = "404", description = "Product not found")
    })
    ProductResponse getById(
        @Parameter(description = "Product identifier", example = "42")
        @PathVariable Long id
    ) {
        return productService.getById(id);
    }
}
```

In this example, Spring annotations determine how the endpoint can be invoked; Swagger annotations explain what the endpoint means in the documentation. Springdoc merges both sources of information to produce the OpenAPI operation.

### Describing a DTO Schema

```java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(description = "Product information returned by the API")
public record ProductResponse(
    @Schema(description = "Product ID", example = "42")
    Long id,

    @Schema(description = "Display name of the product", example = "Mechanical Keyboard")
    String name,

    @Schema(description = "Selling price in the system currency", example = "1290000")
    Long price
) {
}
```

`@Schema` helps readers understand the meaning of each property and gives client generators richer metadata. Examples should match actual data types and rules. If a field has length limits, value ranges, or special formats, describe those constraints with appropriate schema attributes and make sure they reflect enforced validation.

### Distinguishing Two Annotations Named `RequestBody`

In Spring Boot you can encounter two annotations named `RequestBody`:

```java
import org.springframework.web.bind.annotation.RequestBody;
```

Spring's annotation binds HTTP request data to a method parameter for Spring MVC to process. Meanwhile:

```java
import io.swagger.v3.oas.annotations.parameters.RequestBody;
```

Swagger's annotation describes the request body in the OpenAPI document. In most cases Springdoc infers the request body from Spring's annotation and parameter type, so you do not need to add the Swagger annotation to every endpoint. Use the Swagger annotation only when you need to describe or override details such as description, required, content, or examples. When both are needed in the same method, use a fully qualified name or adjust imports to avoid confusion.

### Declaring Application-Level API Information

Annotations are not the only option for adding metadata. You can create an `OpenAPI` bean using Swagger's model classes to declare title, version, description, and shared metadata:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI productApi() {
        return new OpenAPI()
            .info(new Info()
                .title("Product API")
                .version("v1")
                .description("API for managing and looking up products"));
    }
}
```

This bean uses model classes from `io.swagger.v3.oas.models`, a different package from the `io.swagger.v3.oas.annotations` annotations. Springdoc uses the OpenAPI bean to supply document-level metadata. You can combine this bean with annotations on controllers and DTOs; pick one place to manage shared information to avoid duplicate or conflicting declarations.

## 3. Swagger Core: OpenAPI Specification Models and Utilities

Swagger Core is a Java library in the Swagger ecosystem that provides foundational components for representing and processing the OpenAPI specification. Related modules typically include:

- **Swagger annotations:** defines annotations like `@Operation`, `@Schema`, and `@ApiResponse` to attach metadata in source code.
- **Swagger models:** provides object models such as `OpenAPI`, `Info`, `Paths`, `PathItem`, `Operation`, `Components`, `Schema`, and `SecurityScheme`.
- **Swagger Core:** a collection of utilities for processing models, reading or converting specifications, and integrations supported by the Swagger ecosystem.

Exact artifact names can differ across version lines and Jakarta variants. Therefore, inspect the dependency tree of the springdoc version in use rather than assuming all Swagger classes live in a single JAR.

Springdoc uses components from the Swagger ecosystem to represent the OpenAPI contract while handling Spring-specific endpoint discovery and metadata itself. This is very important: a Spring MVC application does not need to configure a JAX-RS scanner just for springdoc to read Spring controllers. Use the Springdoc starter matching MVC or WebFlux to integrate with the right web platform.

### When to Work Directly with the OpenAPI Model?

Most applications only need annotations and Springdoc configuration. The OpenAPI model is useful when you need to build or customize document-level information in Java, such as adding shared servers, contact, license, tags, or security schemes.

The following example adds contact info and a server:

```java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import io.swagger.v3.oas.models.servers.Server;
import java.util.List;

@Bean
OpenAPI serviceApi() {
    return new OpenAPI()
        .info(new Info()
            .title("Inventory API")
            .version("v1")
            .contact(new Contact().name("API Team")))
        .servers(List.of(
            new Server().url("https://api.example.com").description("Production")
        ));
}
```

The server address in the example is an illustrative value only. In a real application, manage URLs by environment or reverse proxy configuration so documentation does not mistakenly point to the production server when running in local or staging.

Do not rebuild the entire document by manually writing object models if Springdoc already infers it accurately from controllers. Only customize what is needed, because manually declaring metadata that duplicates inferred data can make documentation hard to maintain or drift out of sync with real endpoints.

## 4. WebJars: Distributing UI Assets Inside a JAR

Swagger UI is a frontend application. It needs HTML, JavaScript, CSS, fonts, and images to run in a browser. WebJars package these web assets into Maven/Gradle artifacts so Java applications can serve them from the classpath, instead of requiring the development team to manually download and copy files into the static folder.

A WebJar typically places resources under a structure similar to:

```text
META-INF/resources/webjars/<webjar-name>/<webjar-version>/...
```

In the Swagger UI starter's dependencies, the `swagger-ui` WebJar supplies the frontend files. Springdoc configures serving these resources and provides entry points to the UI, typically `/swagger-ui.html` or `/swagger-ui/index.html` depending on path settings and version. The browser loads the UI, then fetches the OpenAPI document from the configured endpoint.

WebJars do not generate schemas from controllers and do not handle business requests. They only distribute web assets. If `/v3/api-docs` returns the right document while the browser reports missing JavaScript or CSS, inspect UI resource serving, the WebJar dependency, and asset paths.

### When Do You Need to Add a WebJar Directly?

For applications using `springdoc-openapi-starter-webmvc-ui` or the corresponding WebFlux UI starter, the required Swagger UI dependency is already pulled in transitively. There is no need to declare a separate Swagger UI WebJar if you only use the interface integrated by springdoc.

Only consider adding or managing a WebJar directly when the application has a custom frontend distribution need, intentionally overrides UI asset versions, or uses another static resource mechanism. When managing the WebJar version manually, verify compatibility between Swagger UI assets and the configuration expected by springdoc.

## 5. Choosing Starters and Placing Dependencies in the Right Module

For Spring MVC, two common choices in springdoc's modern starter line are:

| Need | Artifact |
|---|---|
| Provide OpenAPI endpoint without integrated Swagger UI | `springdoc-openapi-starter-webmvc-api` |
| Provide OpenAPI endpoint with Swagger UI | `springdoc-openapi-starter-webmvc-ui` |

For Spring WebFlux, use the corresponding starters named `springdoc-openapi-starter-webflux-api` or `springdoc-openapi-starter-webflux-ui`. Choose the exact web stack running in the application; do not add both MVC and WebFlux starters unless the architecture requires both.

Maven dependency example for a Spring MVC app needing both documentation and UI:

```xml
<properties>
    <springdoc.version>YOUR_COMPATIBLE_VERSION</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

Gradle example:

```kotlin
dependencies {
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:$springdocVersion")
}
```

Replace `YOUR_COMPATIBLE_VERSION` or `springdocVersion` with a version compatible with the project's Spring Boot line. Do not use placeholder strings as real release versions.

### Where to Place Dependencies in a Multi-Module Project?

Suppose a project has the structure:

```text
application
  └── Spring Boot configuration and Swagger UI
product-api
  └── controllers, DTOs, and Swagger annotations
product-domain
  └── domain models
```

If `product-api` contains source code importing `@Operation` or `@Schema`, this module must have those annotations on its compile classpath. If the Springdoc starter is only declared in `application`, that dependency will not necessarily appear on `product-api`'s compile classpath, depending on how inter-module dependencies are configured. Declare the dependency in the module directly using the annotation types, or design shared dependencies to fit the architecture.

The application module that boots and serves API Docs/UI usually declares the Springdoc integration starter. If a library module only needs annotations to describe controllers/DTOs without running Springdoc, you can declare the compatible annotation artifact in that module. When doing so, ensure the annotation version matches the version pulled in by the Springdoc starter.

Do not put the Swagger UI WebJar into the domain module just because that module holds DTOs. UI assets belong to the web application layer responsible for serving documentation.

## 6. Version Compatibility and Jakarta Variants

Springdoc, Swagger Core, Swagger annotations, and WebJars artifacts depend on one another. Beyond matching library versions, the project must also match the Spring Boot line and Servlet namespace used by the platform.

One key detail is the transition from `javax.*` to `jakarta.*` in the Spring ecosystem. Newer Spring Boot lines use the Jakarta namespace; older Spring Boot lines use the Java EE ecosystem with `javax`. Corresponding Swagger Core versions may offer standard and Jakarta-variant artifacts, such as names ending with `-jakarta`.

Selection rules:

1. Identify the application's Spring Boot line and web stack before choosing Springdoc.
2. Select the Springdoc line published as compatible with that Spring Boot version.
3. Let the Springdoc starter manage the versions of Swagger Core, Swagger models, annotations, and UI it requires, unless there is a clear technical reason to override.
4. If declaring Swagger annotations directly in another module, pick the Jakarta or non-Jakarta variant matching the project's library line.
5. Inspect the dependency tree to ensure the runtime does not contain multiple incompatible versions of the same artifact.

Do not upgrade `swagger-annotations` alone to the latest release while keeping an old Springdoc starter. A new annotation might not exist in the version used by the processing library; conversely, a newer Swagger Core version might change APIs that older springdoc is incompatible with.

## 7. Inspecting the Dependency Tree and Resolving Conflicts

When annotations are ignored, documentation endpoints fail, or Swagger UI lacks resources, inspect the actual resolved dependencies rather than just reading `pom.xml` or `build.gradle`. Directly declared dependencies may pull in another version from another module or platform library.

With Maven, inspect related artifacts:

```bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3,org.webjars
```

With Gradle, inspect runtime dependencies:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Or check why a dependency was selected:

```bash
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-annotations --configuration compileClasspath
./gradlew dependencyInsight --dependency swagger-ui --configuration runtimeClasspath
```

Configuration names may differ in Android projects, plugins, or specialized Gradle modules; pick the configuration that exists in the module under inspection.

Some indicators and troubleshooting paths:

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| IDE reports `io.swagger.v3.oas.annotations...` not found | Module containing controllers/DTOs lacks annotations on compile classpath | Check direct dependencies and inter-module relationships |
| `NoClassDefFoundError` or `ClassNotFoundException` at startup | Missing required JAR or mismatched artifact variant | Inspect runtime dependency tree and exclusions |
| `NoSuchMethodError` or `NoSuchFieldError` | Incompatible Swagger Core/models/annotations versions | Find duplicate pulled versions and dependency overrides |
| JSON/YAML has data but Swagger UI fails to load | Wrong document URL, access permissions, or CORS | Inspect the document request in the browser's Network tab |
| UI returns 404 for JavaScript/CSS | WebJar or resource handler not packaged/served properly | Check UI starter, WebJar, and paths behind reverse proxy |
| Annotations exist but descriptions do not appear as expected | Wrong package imported, annotation misplaced, or metadata overridden by config | Check imports, annotation placement, and generated document |

When excluding transitive dependencies, first identify the conflicting artifact from the dependency tree. Only add an `exclusion` when you know which replacement component will supply the excluded classes and that the replacement version is compatible. Excluding all of Swagger Core or Swagger models can prevent springdoc from starting.

## 8. Common Misconceptions

**Adding Swagger annotations means Swagger UI is already available.** Incorrect. Annotations only supply metadata. To get documentation endpoints you need the appropriate Springdoc API starter; to get an integrated UI you need the UI starter or a separate frontend.

**Having the WebJar automatically generates OpenAPI.** Incorrect. The WebJar holds web assets. Springdoc and OpenAPI processing components generate the document from the application.

**Swagger Core automatically understands every Spring controller.** Do not assume this. Spring integration is implemented by Springdoc; choose the matching MVC or WebFlux starter.

**Having `@SecurityRequirement` means the API is already protected.** Incorrect. The annotation only documents security in the spec. Spring Security or an actual authentication mechanism enforces access policies.

**If the application module has the dependency, every submodule can compile annotations.** Not necessarily. Each module must declare the dependency on its compile classpath if its own source code uses those types.

**Swagger Core can be upgraded independently without checking Springdoc.** High risk. Artifacts are managed as a compatible dependency set; check compatibility and the dependency tree before overriding.

## 9. Checklist for Selecting and Verifying Components

- [ ] Identified whether the application uses Spring MVC or Spring WebFlux.
- [ ] Springdoc starter matches the web stack and Spring Boot line.
- [ ] API starter used if only documentation is needed, or UI starter if integrated Swagger UI is needed.
- [ ] Modules containing controllers/DTOs declare annotations on their compile classpath.
- [ ] Annotations imported from the right `io.swagger.v3.oas.annotations...` packages.
- [ ] Custom models use the right `io.swagger.v3.oas.models...` packages.
- [ ] No duplicate Swagger UI WebJar added when the UI starter already provides required resources.
- [ ] Swagger Core, annotations, models, and WebJars artifacts are not forced to incompatible versions.
- [ ] Dependency tree has no conflicts causing compile or runtime errors.
- [ ] OpenAPI endpoints and Swagger UI resources both load in the deployment environment.

When roles are cleanly separated, controllers and DTOs provide the source data, Swagger annotations add semantics, Swagger Core provides OpenAPI structures, Springdoc integrates with Spring, and WebJars distribute the Swagger UI interface. Managing dependencies in the right modules and within the same compatible version line keeps documentation generation stable, maintainable, and faithful to the API contract.
