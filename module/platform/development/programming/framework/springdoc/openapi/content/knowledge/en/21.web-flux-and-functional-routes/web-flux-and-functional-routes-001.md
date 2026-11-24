# Choosing the Right WebFlux Starter for Reactive Applications

When a Spring Boot application runs on Spring WebFlux, springdoc-openapi needs the WebFlux-specific starter to correctly read the reactive web model and generate OpenAPI documentation. The key choice is whether the application only needs JSON/YAML endpoints, needs Swagger UI, or wants the Scalar interface. Use `springdoc-openapi-starter-webflux-api` if you only publish machine-readable documentation; use `springdoc-openapi-starter-webflux-ui` for Swagger UI or `springdoc-openapi-starter-webflux-scalar` for Scalar. For Spring Boot 2.x, the artifact names in the springdoc 1.x line differ from the starters for Boot 3.x and 4.x.

Choosing WebFlux should be based on the request processing architecture of the entire application. WebFlux is suitable when the HTTP, service, and data access layers can run in a non-blocking model. Merely changing return types to `Mono` or `Flux` does not automatically turn an application using blocking libraries into a reactive one.

## 1. When Should You Choose Spring WebFlux?

Spring MVC and Spring WebFlux can both build REST APIs, but they use two different runtime models:

| Criterion | Spring MVC | Spring WebFlux |
|---|---|---|
| Processing model | Traditional Servlet and request thread model | Reactive Streams, event loop, and non-blocking processing |
| Common return types | DTO, `List<T>`, `ResponseEntity<T>` | `Mono<T>`, `Flux<T>`, `Mono<ResponseEntity<T>>` |
| Suitable data access | JDBC, JPA, and blocking libraries | R2DBC, reactive MongoDB, reactive HTTP clients, and non-blocking drivers |
| Common default server | Tomcat | Reactor Netty |
| springdoc documentation integration | `webmvc-api`, `webmvc-ui`, or `webmvc-scalar` starter | `webflux-api`, `webflux-ui`, or `webflux-scalar` starter |

Choose WebFlux when the application needs to handle high concurrent I/O, streaming, or end-to-end reactive communication. For example, an API that aggregates data from multiple services using `WebClient`, queries reactive data stores, and returns results as a stream can benefit from WebFlux.

If most processing relies on JPA/JDBC, blocking SDKs, or typical CPU-bound work, Spring MVC is usually simpler. WebFlux can still call blocking libraries on a dedicated scheduler, but you must manage scheduler switching and resource limits; that approach does not make blocking operations non-blocking.

### Do Not Choose WebFlux Just Because a Controller Returns Mono or Flux

Spring MVC also supports some reactive return types such as `Mono` and `Flux`. Therefore, a method returning `Mono<Product>` is not enough to conclude that the application must run WebFlux. Consider the web runtime, server dependencies, data access, and how the entire request is processed.

### WebClient Does Not Determine the Web Server

A Spring MVC application can still call external services using `WebClient`. WebClient is an HTTP client; using a reactive client does not require the server itself to switch to WebFlux.

With Spring Boot 4, if you only need the HTTP client, you can use `spring-boot-starter-webclient` without adding a reactive web server. With Spring Boot 3, WebClient lives in the `spring-webflux` ecosystem, so some projects add `spring-boot-starter-webflux` to get the client. If the application also has `spring-boot-starter-web`, Spring Boot defaults to choosing Spring MVC as the web application type. In that case, documentation must use the springdoc WebMVC starter.

Only choose `spring-boot-starter-webflux` as the server starter when the application truly needs WebFlux to handle HTTP requests. If the system primarily uses JPA/JDBC and blocking SDKs, Spring MVC is usually simpler; do not switch servers just to use WebClient.

## 2. Distinguishing springdoc WebFlux Starters

Springdoc provides modules based on how documentation is published:

| Artifact | Purpose | Common Endpoints |
|---|---|---|
| `springdoc-openapi-starter-webflux-api` | Generates OpenAPI document from a WebFlux application | `/v3/api-docs`, `/v3/api-docs.yaml` |
| `springdoc-openapi-starter-webflux-ui` | Generates OpenAPI document and integrates Swagger UI | `/v3/api-docs`, `/v3/api-docs.yaml`, `/swagger-ui.html` |
| `springdoc-openapi-starter-webflux-scalar` | Generates OpenAPI document and integrates the Scalar UI | `/v3/api-docs`, `/scalar` |

Choose `webflux-api` when the documentation is fetched by a pipeline, API portal, or client generator tool and you do not need Swagger UI embedded in the application. Choose `webflux-ui` when developers need to browse endpoints, inspect schemas, and try out API calls directly in the browser.

Choose `webflux-scalar` if your team wants to use Scalar instead of Swagger UI. Do not add the API, UI, and Scalar starters simultaneously just to get the same OpenAPI document. The UI/Scalar starters already include the necessary document generation module; only use multiple UIs when there is an explicit deployment requirement.

### When You Only Need JSON/YAML Documentation

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-api</artifactId>
    <version>${springdoc.version}</version>
</dependency>
```

The application still publishes OpenAPI, but without Swagger UI integrated. Clients or API portals can fetch JSON/YAML from the documentation endpoint.

### When You Need Swagger UI

```xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
```

Swagger UI reads the OpenAPI document generated by springdoc and displays endpoints, requests, responses, schemas, and declared security schemes.

## 3. Choosing Artifacts by Spring Boot Version

Springdoc artifact names change across major versions. Do not use the newer Boot 3/4 starters in a Boot 2 project, or the older v1 dependencies in a Boot 3/4 project.

| Spring Boot | springdoc Line | WebFlux Artifact with Swagger UI | WebFlux API-Only Artifact |
|---|---|---|---|
| 2.x | 1.x | `springdoc-openapi-webflux-ui` | `springdoc-openapi-webflux-core` |
| 3.x | 2.x | `springdoc-openapi-starter-webflux-ui` | `springdoc-openapi-starter-webflux-api` |
| 4.x | 3.x | `springdoc-openapi-starter-webflux-ui` | `springdoc-openapi-starter-webflux-api` |

With springdoc 2.x and 3.x, `springdoc-openapi-starter-webflux-scalar` is also available if you want Scalar. The v1 line does not use starter naming, and the v1 WebFlux documentation lists `springdoc-openapi-webflux-ui`; the corresponding API-only module is `springdoc-openapi-webflux-core`.

This is guidance by major version. Springdoc 1.8.0 is the final legacy line for Spring Boot 1.x/2.x and has reached end of open-source support; new projects should use a springdoc line compatible with Spring Boot 3.x or 4.x. Check the compatibility matrix and release notes to pick the minor/patch version matching your Spring Boot and Spring Framework versions.

For example, the springdoc v2 documentation for Spring Boot 3.x currently uses the `springdoc-openapi-starter-webflux-ui` or `springdoc-openapi-starter-webflux-api` starter. The springdoc v1 line for Spring Boot 2.x uses the older artifact names without the `starter` suffix. Current springdoc documentation includes WebFlux examples for Spring Boot 4 and the springdoc 3.x line.

## 4. Maven Configuration for WebFlux and springdoc

A WebFlux application with Swagger UI needs the Spring Boot WebFlux starter and the springdoc WebFlux UI starter:

```xml
<properties>
    <java.version>21</java.version>
    <springdoc.version>3.2.0</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

This example uses Spring Boot 4.x and springdoc 3.x. `spring-boot-starter-webflux` should have its version managed by the Spring Boot parent or your project's dependency management. Do not copy the example version number into a Boot 3.x project if the compatibility matrix requires a different springdoc line.

If you only need OpenAPI JSON/YAML, replace the `springdoc-openapi-starter-webflux-ui` artifact with `springdoc-openapi-starter-webflux-api`.

### Maven with Spring Boot 3.x

Keep the same Spring Boot WebFlux dependency, but choose springdoc 2.x:

```xml
<properties>
    <springdoc.version>2.10.0</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
```

The version in this example illustrates a release in the springdoc 2.x line. Choose a release compatible with the Spring Boot minor version you are using rather than treating this as a mandatory version.

## 5. Gradle Configuration

With Gradle Kotlin DSL:

```kotlin
val springdocVersion = "3.2.0" // Spring Boot 4; for Spring Boot 3, use a compatible 2.x release
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springdoc:springdoc-openapi-starter-webflux-ui:$springdocVersion")
}
```

If you only need API docs:

```kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-webflux")
    implementation("org.springdoc:springdoc-openapi-starter-webflux-api:$springdocVersion")
}
```

If using Scalar, replace the UI artifact with `springdoc-openapi-starter-webflux-scalar`. For Spring Boot 3.x, set `springdocVersion` to a compatible 2.x release; for Boot 4.x, use springdoc 3.x. For Spring Boot 2.x, use the older v1 artifacts and check the migration guide before upgrading major versions.

Declare the springdoc version in a single property or version catalog so the UI starter and other springdoc modules in the same project share the exact same version. Do not let the dependency graph pull in multiple versions of `springdoc-openapi` or `swagger-core` simultaneously.

## 6. Do Not Mix WebFlux and Web MVC Starters

A common mistake is adding both dependencies:

```xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
```

When both Spring MVC and WebFlux are on the classpath, Spring Boot usually selects Spring MVC as the web application type. This can cause the application to start on the servlet stack even when developers think they are using WebFlux.

If the application genuinely needs WebFlux, remove `spring-boot-starter-web` and any dependencies that transitively pull in Spring MVC if not needed. Also choose the matching springdoc starter:

```text
spring-boot-starter-webflux
springdoc-openapi-starter-webflux-ui
```

Avoid configurations like:

```text
spring-boot-starter-web
springdoc-openapi-starter-webflux-ui
```

or:

```text
spring-boot-starter-webflux
springdoc-openapi-starter-webmvc-ui
```

### Can You Force the Application Type to Reactive?

Spring Boot has a property:

```yaml
spring:
  main:
    web-application-type: reactive
```

This property can force the web application type when handling special classpath situations. However, it does not remove MVC dependencies and does not resolve configuration conflicts caused by both stacks being present. A cleaner approach is to keep only the dependencies matching the web runtime the application actually uses.

## 7. springdoc Automatically Detects WebFlux Controllers

For annotation-based controllers, once the right starter is added, springdoc automatically reads mappings such as `@RestController`, `@RequestMapping`, `@GetMapping`, `@PostMapping`, and metadata from Swagger annotations.

Example reactive controller:

```java
@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "Product lookup")
class ProductController {

    private final ProductService productService;

    ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/{id}")
    Mono<ProductResponse> getById(@PathVariable UUID id) {
        return productService.findById(id);
    }

    @GetMapping
    Flux<ProductResponse> findAll() {
        return productService.findAll();
    }
}
```

springdoc inspects the path, HTTP method, parameters, and element type of reactive return types to generate operations. You can use `@Operation`, `@ApiResponse`, `@Parameter`, and `@Schema` just like with MVC controllers.

Example service:

```java
interface ProductService {
    Mono<ProductResponse> findById(UUID id);
    Flux<ProductResponse> findAll();
}
```

`Mono<T>` represents at most one element or no element; `Flux<T>` represents a sequence of zero to many elements. When returning `Flux<T>` with the standard JSON media type, the API is usually consumed as a collection; when using `text/event-stream` or another streaming format, clearly document the content type and streaming behavior in OpenAPI.

## 8. WebFlux Functional Endpoints Also Use the WebFlux Starter

Applications can declare routes using `RouterFunction` and handlers instead of controller annotations. Still use the `webflux-api`, `webflux-ui`, or `webflux-scalar` starter according to your documentation needs.

Example functional routes:

```java
@Configuration
class ProductRoutes {

    @Bean
    RouterFunction<ServerResponse> productRouter(ProductHandler handler) {
        return RouterFunctions.route(
                RequestPredicates.GET("/api/products"),
                handler::findAll
            )
            .andRoute(
                RequestPredicates.GET("/api/products/{id}"),
                handler::findById
            );
    }
}
```

With functional routes, springdoc needs metadata to know the operationId, summary, parameters, and responses. You can use `@RouterOperation` for a single route or `@RouterOperations` for multiple routes in the same bean. `operationId` is important metadata and should be declared uniquely.

Example declaring multiple routes:

```java
@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "findAll",
        operation = @Operation(
            operationId = "products_findAll",
            summary = "List products",
            tags = {"Products"},
            responses = @ApiResponse(
                responseCode = "200",
                description = "List of products",
                content = @Content(
                    schema = @Schema(
                        type = "array",
                        implementation = ProductResponse.class
                    )
                )
            )
        )
    ),
    @RouterOperation(
        path = "/api/products/{id}",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "findById",
        operation = @Operation(
            operationId = "products_findById",
            summary = "Get product by ID",
            tags = {"Products"}
        )
    )
})
RouterFunction<ServerResponse> productRouter(ProductHandler handler) {
    return RouterFunctions.route(
            RequestPredicates.GET("/api/products"), handler::findAll
        )
        .andRoute(
            RequestPredicates.GET("/api/products/{id}"), handler::findById
        );
}
```

This is a directional example; import `RouterOperation`/`RouterOperations` from the springdoc package for your major version and complete the response metadata for each operation. For a bean containing multiple routes, declare the `path` and HTTP method for each route so springdoc matches the metadata to the exact endpoint.

springdoc also supports a functional DSL to attach operation metadata directly while declaring routes. This approach is helpful if the development team wants routes and OpenAPI descriptions side by side instead of separating them into annotations.

## 9. Choosing WebFlux API vs. WebFlux UI by Distribution Method

Not every application needs Swagger UI embedded in the production runtime.

| Scenario | Recommended Option | Reason |
|---|---|---|
| Internal API where developers need to try requests directly | `webflux-ui` | Provides Swagger UI alongside OpenAPI |
| CI fetches OpenAPI for linting or contract comparison | `webflux-api` | Only JSON/YAML is needed, no UI required |
| Documentation is published to a separate API portal | `webflux-api` | The portal can pull the document from the endpoint or build artifact |
| Production microservice that should not serve a UI | `webflux-api` or expose docs only per policy | Reduces unnecessary runtime UI surface |
| Developer portal wants Scalar UI integrated in the app | `webflux-scalar` | Includes both Scalar UI and the OpenAPI document |
| Developer portal needs multiple API groups | `webflux-ui` or `webflux-api` depending on where it renders | Grouped OpenAPI is still generated; UI is only needed for direct viewing |

You can disable Swagger UI per profile if you use the UI starter but do not want to serve the interface in certain environments:

```yaml
springdoc:
  swagger-ui:
    enabled: false
```

OpenAPI JSON/YAML can still be enabled independently via `springdoc.api-docs.enabled`. If you want to hide machine-readable docs in production as well, configure `springdoc.api-docs.enabled: false` or protect the endpoints with Spring Security per deployment policy.

## 10. Documentation Endpoints and Basic Configuration

With default configuration, springdoc publishes:

| Endpoint | Content |
|---|---|
| `/v3/api-docs` | OpenAPI JSON |
| `/v3/api-docs.yaml` | OpenAPI YAML |
| `/swagger-ui.html` | Swagger UI page or redirect to UI resources |
| `/scalar` | Scalar UI when using the Scalar starter |

You can customize the documentation paths:

```yaml
springdoc:
  api-docs:
    path: /api/openapi
  swagger-ui:
    path: /docs
```

When using the API-only starter, `swagger-ui.path` has no effect because Swagger UI is not installed. Changing `api-docs.path` does not alter the application's controller mappings.

If there are multiple groups, springdoc can publish documents by group, such as `/v3/api-docs/public` and `/v3/api-docs/admin`. Groups still need to be configured separately using `GroupedOpenApi` or the corresponding mechanism.

## 11. WebFlux Does Not Automatically Make Everything Non-Blocking

An application can run on WebFlux and still call a blocking database or SDK. This easily stalls the event loop if blocking operations run directly on request-handling threads.

Example of what not to do in a WebFlux handler:

```java
Mono<ProductResponse> findById(UUID id) {
    ProductEntity entity = jpaRepository.findById(id).orElseThrow();
    return Mono.just(mapper.toResponse(entity));
}
```

`jpaRepository.findById(...)` is blocking. It executes before the `Mono` is returned and can hold the request-handling thread for the entire duration of the query.

A better solution is to use reactive drivers/repositories if the architecture requires end-to-end non-blocking execution. If you must call a blocking library, isolate that operation on an appropriate scheduler and limit concurrency:

```java
Mono<ProductResponse> findById(UUID id) {
    return Mono.fromCallable(() -> jpaRepository.findById(id)
            .orElseThrow(() -> new ProductNotFoundException(id)))
        .subscribeOn(Schedulers.boundedElastic())
        .map(mapper::toResponse);
}
```

This is a way to isolate blocking calls, not a way to make JPA reactive. You must load-test, set timeouts, and limit resources; if most requests depend on JPA, Spring MVC may be a better fit.

In controllers/handlers, avoid calling `.block()` or `.subscribe()` manually to retrieve data before returning a response. Return the publisher so the framework manages subscription and lifecycle.

## 12. Avoiding Dependency and Classpath Conflicts

When an application starts on the wrong web stack or springdoc fails to generate docs, inspect the dependency tree:

```bash
mvn dependency:tree
```

Or with Gradle:

```bash
./gradlew dependencies --configuration runtimeClasspath
```

Check for the following dependencies:

- `spring-boot-starter-webflux` is present when the application chooses WebFlux.
- `spring-boot-starter-web` is not present unintentionally.
- `springdoc-openapi-starter-webflux-api` or `springdoc-openapi-starter-webflux-ui` matches the right major version.
- No `springdoc-openapi-starter-webmvc-*` artifacts exist in a WebFlux application.
- No conflicting multiple versions of `springdoc-openapi`, `swagger-core`, or Swagger annotations are present.

Another library might pull in `spring-boot-starter-web` transitively. If that dependency does not need the servlet stack, exclude the MVC dependency on the specific module that brings it in. Do not add `spring.main.web-application-type=reactive` just to mask a conflict without understanding the dependency source.

## 13. Verifying the Application Is Running on WebFlux

After startup, verify that the application uses a reactive web application context. You can check startup logs, the dependency tree, and the server runtime. If using Actuator, some info endpoints can help verify this, though they should be secured.

Then verify the documentation:

1. Call `/v3/api-docs` and confirm HTTP 200 with valid JSON.
2. Call `/v3/api-docs.yaml` if YAML publishing is needed.
3. If using the UI starter, open `/swagger-ui.html` and confirm Swagger UI loads the document properly.
4. Check that annotation-based controllers appear under `paths`.
5. Check that functional routes with `@RouterOperation`/DSL metadata appear under `paths`.
6. Check that reactive return types are documented with the proper response schema, without exposing `Mono` or `Flux` as a business object.
7. Check media types for streaming endpoints such as SSE/NDJSON.

Example using curl:

```bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
curl -i http://localhost:8080/swagger-ui.html
```

The last command only applies if you use the UI starter and have not changed the Swagger UI path.

## 14. Testing WebFlux with WebTestClient

WebFlux supports `WebTestClient` for testing reactive endpoints. You can use this client to verify the OpenAPI document without depending on a browser UI:

```java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@AutoConfigureWebTestClient
class OpenApiWebFluxTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void exposesOpenApiJson() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
            .expectBody()
            .jsonPath("$.openapi").exists()
            .jsonPath("$.paths['/api/products']").exists();
    }

    @Test
    void exposesSwaggerUiWhenUiStarterIsInstalled() {
        webTestClient.get()
            .uri("/swagger-ui.html")
            .exchange()
            .expectStatus().is3xxRedirection();
    }
}
```

The Swagger UI test depends on how the starter serves resources and any custom path; it may return a redirect or HTML depending on configuration. If using the API-only starter, omit the UI test because that endpoint does not exist.

For functional routes, add assertions to check the operationId and response schema in the document. If a route runs at runtime but does not appear in OpenAPI, check the router annotation/DSL metadata and declared path/method.

## 15. Common Errors When Choosing a Starter

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `/v3/api-docs` returns 404 | Missing springdoc starter or wrong web-stack starter | Use the matching `webflux-api`/`webflux-ui` starter |
| Swagger UI returns 404 while OpenAPI JSON works | Only `webflux-api` is installed | Switch to `webflux-ui` if a UI is needed |
| WebFlux controller runs, yet the app actually runs MVC | Both `spring-boot-starter-web` and `webflux` are present | Check dependency tree and exclude the unneeded starter |
| `org.springdoc...` classes do not exist at compile time | Using imports/APIs from a different major version | Cross-check springdoc 1.x, 2.x, or 3.x |
| Spring Boot reports Spring Framework compatibility errors | Chosen springdoc major/minor does not match Boot | Check the compatibility matrix and dependency management |
| Functional routes do not appear in documentation | Missing `@RouterOperation`, `@RouterOperations`, or DSL metadata | Add operationId, path, method, and response metadata |
| Schema shows `Mono`/`Flux` incorrectly as a model | Unrecognized custom wrapper or converter | Check return types and schema annotations in the document |
| WebFlux application is slow or stalled | Blocking calls running on the event loop | Use reactive drivers or isolate bounded blocking work |
| Swagger UI works, but Try it out calls the wrong URL | Incorrect server URL, context path, or proxy config | Check OpenAPI `servers`, forwarded headers, and proxy |
| API docs work locally, but return 401/403 in deployed envs | Spring Security protects the documentation endpoints | Configure access rules for `/v3/api-docs/**` and Swagger UI per policy |

## 16. Workflow for Selecting and Adding a Starter

When integrating springdoc into a reactive application, follow this order:

1. Confirm whether the application uses Spring MVC or Spring WebFlux.
2. Inspect server dependencies and data access libraries; determine whether end-to-end non-blocking is needed.
3. Identify the Spring Boot major version to select the corresponding springdoc 1.x, 2.x, or 3.x line.
4. Choose `webflux-api` if only OpenAPI JSON/YAML is needed; choose `webflux-ui` if Swagger UI is needed.
5. Remove unnecessary MVC dependencies and inspect the dependency tree.
6. Add metadata for controllers or functional routes.
7. Start the application and verify `/v3/api-docs`, YAML, and UI if enabled.
8. Test reactive endpoints, streaming media types, security, and proxy paths.
9. Compare the OpenAPI document against the intended contract before release.

Choosing the right WebFlux starter helps springdoc inspect the right web stack and generate documentation suited to a reactive architecture. The WebFlux decision should be based on the application's I/O model, while the `api` vs. `ui` decision depends on how your team and consumers use the documentation.

## 17. References

- [Springdoc OpenAPI – Spring WebFlux support](https://springdoc.org/modules.html): WebFlux API and Swagger UI starters.
- [Springdoc OpenAPI – Scalar support](https://springdoc.org/modules.html): WebFlux Scalar starter for the current springdoc line.
- [Springdoc OpenAPI v2 – Spring WebFlux support](https://springdoc.org/v2/modules.html): `springdoc-openapi-starter-webflux-api` and `springdoc-openapi-starter-webflux-ui` artifacts for Spring Boot 3.
- [Springdoc OpenAPI v1 – Spring WebFlux support](https://springdoc.org/v1/modules.html): WebFlux artifacts for the springdoc 1.x line.
- [Springdoc OpenAPI – Migrating from v1 to v2](https://springdoc.org/v2/migrating-from-springdoc-v1.html): mapping `springdoc-openapi-webflux-core` to `springdoc-openapi-starter-webflux-api`.
- [Springdoc OpenAPI – Compatibility Matrix](https://springdoc.org/#what-is-the-compatibility-matrix-of-spring-boot-with-springdoc-openapi-): compatibility between Spring Boot and springdoc.
- [Springdoc OpenAPI – Functional Endpoints](https://springdoc.org/features.html#spring-webfluxwebmvc-fn-with-functional-endpoints): `@RouterOperation`, `@RouterOperations`, and functional DSL.
- [Spring Framework – WebFlux](https://docs.spring.io/spring-framework/reference/web/webflux.html): reactive web framework architecture.
- [Spring Boot – Web Reactive](https://docs.spring.io/spring-boot/reference/web/reactive.html): reactive web application configuration and server selection.
- [Spring Boot – Build Systems](https://docs.spring.io/spring-boot/reference/using/build-systems.html): standalone WebClient starter in Spring Boot 4 and web starters.
- [Reactor – Reactive Programming](https://projectreactor.io/docs/core/release/reference/): `Mono`, `Flux`, schedulers, and principles for not blocking the event loop.
