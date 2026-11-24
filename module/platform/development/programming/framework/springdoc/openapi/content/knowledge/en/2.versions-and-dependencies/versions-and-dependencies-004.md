# Choosing a Starter for Spring MVC or WebFlux

For springdoc-openapi to generate documentation accurately for an application, choose the starter matching the web stack that Spring Boot actually boots: Spring MVC or Spring WebFlux. Then choose the variant with Swagger UI if you need an interface to test APIs, or the API-only variant if you only need OpenAPI JSON/YAML endpoints for CI, an API portal, or other tools.

These two decisions are independent:

1. **Web stack:** MVC or WebFlux.
2. **Documentation distribution:** API-only or with Swagger UI.

Do not choose a starter solely based on whether the project uses Reactor, WebClient, or a reactive dependency. An MVC application can still use WebClient; that does not turn the server into WebFlux.

## 1. The Four Common Starters

For springdoc-openapi version 2 and above, the primary selection table is:

| Application Web Stack | OpenAPI JSON/YAML only | With Swagger UI |
|---|---|---|
| Spring MVC / Servlet | springdoc-openapi-starter-webmvc-api | springdoc-openapi-starter-webmvc-ui |
| Spring WebFlux / Reactive | springdoc-openapi-starter-webflux-api | springdoc-openapi-starter-webflux-ui |

The artifact name reflects two pieces of information:

- webmvc or webflux indicates integration matching the web stack.
- api or ui indicates the scope of documentation provided.

API-only starters provide OpenAPI endpoints without packaging the Swagger UI interface. UI starters integrate Swagger UI alongside OpenAPI generation for the corresponding web stack. For typical needs, choose exactly one starter for the application.

Do not add both the api and ui starters of the same type just to have both JSON and Swagger UI. The UI starter already includes everything needed to serve the OpenAPI document and interface. Declaring two starters with overlapping functionality usually only complicates the dependency graph.

## 2. Determining Whether the Application Runs Spring MVC or WebFlux

Inspect the server-booting dependency and ApplicationContext type, not just the return type of a single controller.

| Indicator | Spring MVC | Spring WebFlux |
|---|---|---|
| Primary web starter | spring-boot-starter-web | spring-boot-starter-webflux |
| Server model | Servlet stack | Reactive stack |
| Core abstraction | DispatcherServlet, Servlet filters | HttpHandler, WebFilter |
| Common controller | @RestController, @RequestMapping | @RestController, @RequestMapping |
| Typical return types | DTO, ResponseEntity, List | Mono, Flux, ResponseEntity<Mono<T>> |
| Functional endpoints | Servlet MVC functional routing | RouterFunction, HandlerFunction, ServerRequest |
| Codec/converter | HttpMessageConverter | HttpMessageReader, HttpMessageWriter |

Annotation-based controllers in MVC and WebFlux look nearly identical. Looking only at @RestController or @GetMapping is not enough to determine the web stack.

MVC example:

~~~java
@RestController
@RequestMapping("/api/products")
class ProductController {

    @GetMapping
    List<ProductResponse> findAll() {
        return productService.findAll();
    }
}
~~~

WebFlux example:

~~~java
@RestController
@RequestMapping("/api/products")
class ReactiveProductController {

    @GetMapping
    Flux<ProductResponse> findAll() {
        return productService.findAll();
    }
}
~~~

The two examples share the same annotation style, but the application needs the springdoc starter matching the web stack configured by Spring Boot.

## 3. Checking the Application's Base Dependencies

With Maven, open pom.xml and identify the web starter:

~~~xml
<!-- Spring MVC / Servlet -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>
~~~

Or:

~~~xml
<!-- Spring WebFlux / Reactive -->
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

With Gradle:

~~~kotlin
// Spring MVC / Servlet
implementation("org.springframework.boot:spring-boot-starter-web")

// Or Spring WebFlux / Reactive
implementation("org.springframework.boot:spring-boot-starter-webflux")
~~~

Do not add both web starters just to test which springdoc starter runs. First identify the server stack the application is designed to use.

## 4. When Both MVC and WebFlux Are on the Classpath

Spring Boot has an easily overlooked rule: if both spring-boot-starter-web and spring-boot-starter-webflux are on the classpath, Spring MVC takes precedence by default. Spring Boot chooses this behavior because many MVC applications add WebFlux mainly to use WebClient, not to switch the server to the reactive stack.

Example of an MVC application using WebClient:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-webflux</artifactId>
</dependency>
~~~

If the application still boots Servlet/MVC, use springdoc-openapi-starter-webmvc-api or springdoc-openapi-starter-webmvc-ui depending on documentation needs. Using WebClient is not a reason to choose the WebFlux starter.

If you genuinely want to run WebFlux even though MVC is on the classpath, Spring Boot lets you set the application type explicitly:

~~~yaml
spring:
  main:
    web-application-type: reactive
~~~

Only do this when the entire application is designed and tested as a reactive server. Forcing the application type does not automatically convert controllers, filters, security configurations, or Servlet libraries to WebFlux.

When in doubt about the application context type, check startup logs, DispatcherServlet/HttpHandler beans, web application type configuration, and the dependency tree. Do not infer it from a Reactor class being present in the project.

## 5. Choosing API-Only vs. Swagger UI

### Choose API-Only When

- The OpenAPI document is consumed by another API portal or developer portal.
- CI needs to download JSON/YAML to lint, diff, generate SDKs, or run contract tests.
- The organization does not want Swagger UI embedded in the service.
- Documentation is published through a separate host or system.
- You want to reduce static UI resources packaged in the application.

API-only starter:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

If the server is WebFlux, replace the artifact with springdoc-openapi-starter-webflux-api.

### Choose Swagger UI When

- Developers need to inspect operations, parameters, schemas, and responses directly inside the application.
- The team wants to use Try it out to test endpoints.
- The application provides interactive documentation in local, test, or internal environments.

UI starter for MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

UI starter for WebFlux:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

The examples use version 3.2.0 for Spring Boot 4. If the application uses Spring Boot 3, you must use the springdoc 2.x line; do not copy version 3.2.0 as-is into a Boot 3 project.

## 6. Spring Boot and springdoc Compatibility Matrix

Choosing the right web stack is not enough; the springdoc major version must also be compatible with the Spring Boot major version.

| Spring Boot | springdoc Line | Corresponding Documentation | Notes |
|---|---|---|---|
| 4.x | 3.x | springdoc.org | Current line for Boot 4 |
| 3.x | 2.x | springdoc.org/v2 | Line for Boot 3 |
| 2.x and 1.x | 1.8.0 | springdoc.org/v1 | Legacy branch, open-source support ended |

At the time of writing, official documentation displays springdoc 3.2.0 for Spring Boot 4 and springdoc 2.10.0 for Spring Boot 3. These versions are examples from current documentation; when creating a new project, check the compatibility matrix and release notes to pick a suitable patch release.

Do not use springdoc 3.x with Spring Boot 3 just because the version number is newer. Do not use springdoc 2.x with Boot 4. Do not mix v1 artifacts with v2/v3 starters in the same dependency graph.

### Artifacts in springdoc v1 Differ from Current Starter Names

If maintaining a legacy Spring Boot 1.x/2.x application, v1 docs use artifacts without the starter prefix:

| Need | MVC in v1 | WebFlux in v1 |
|---|---|---|
| API document | springdoc-openapi-webmvc-core | springdoc-openapi-webflux-core |
| Swagger UI | springdoc-openapi-ui | springdoc-openapi-webflux-ui |

These are artifact names from the v1 branch. From v2 onward, modules moved to starters such as springdoc-openapi-starter-webmvc-api and springdoc-openapi-starter-webflux-ui. When upgrading v1 to v2, follow the migration guide rather than only changing the version.

## 7. Maven Configuration for Spring MVC

Example of a Spring Boot 4 project using MVC and needing Swagger UI:

~~~xml
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

If you only need the OpenAPI document, replace webmvc-ui with webmvc-api:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-api</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Do not declare both dependencies simultaneously without a specific modularization reason. Choose the single one that fits your needs.

## 8. Maven Configuration for WebFlux

Example of a Spring Boot 4 project using WebFlux and needing Swagger UI:

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>

    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webflux-ui</artifactId>
        <version>3.2.0</version>
    </dependency>
</dependencies>
~~~

If you only need the OpenAPI document, replace webflux-ui with webflux-api:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webflux-api</artifactId>
    <version>3.2.0</version>
</dependency>
~~~

Do not add webmvc-ui to a WebFlux app or webflux-ui to an MVC app just to try Swagger UI. Choose the module matching the server stack.

## 9. Gradle Configuration for MVC and WebFlux

With Gradle Groovy DSL, MVC + Swagger UI:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springdoc:springdoc-openapi-starter-webmvc-ui:3.2.0'
}
~~~

WebFlux + Swagger UI:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-webflux'
    implementation 'org.springdoc:springdoc-openapi-starter-webflux-ui:3.2.0'
}
~~~

API-only for MVC:

~~~groovy
implementation 'org.springdoc:springdoc-openapi-starter-webmvc-api:3.2.0'
~~~

API-only for WebFlux:

~~~groovy
implementation 'org.springdoc:springdoc-openapi-starter-webflux-api:3.2.0'
~~~

With Kotlin DSL, the corresponding dependency syntax is:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:3.2.0")
}
~~~

Swap the two artifacts per the matrix when using WebFlux or API-only. In real projects, declare the springdoc version in one place and pin a version verified for compatibility.

## 10. Using Dependency Management and Avoiding Version Drift

The Spring Boot parent/BOM manages versions of Spring Boot dependencies. That does not mean every third-party library, including springdoc-openapi, is managed under the same version.

With Maven:

- Use spring-boot-starter-parent or import the Spring Boot dependency BOM per project structure.
- Declare one springdoc.version property.
- Use the same version across springdoc artifacts if extension modules are added.
- Do not override swagger-core or swagger-annotations separately without reason and compatibility testing.

With Gradle:

- Use the Spring Boot plugin and dependency management per project setup.
- Pin the springdoc version in a version catalog or centralized variable.
- Run dependencyInsight when multiple versions are pulled in.

Version catalog example:

~~~toml
[versions]
springdoc = "3.2.0"

[libraries]
springdoc-webmvc-ui = {
  module = "org.springdoc:springdoc-openapi-starter-webmvc-ui",
  version.ref = "springdoc"
}
~~~

Do not use dynamic versions like latest.release in production builds. Dynamic versions can change the dependency graph between two builds even when source code has not changed.

## 11. Dependencies That Should Not Be Duplicated

The springdoc starter pulls in the modules needed for the functionality it provides. Therefore:

- Do not manually add swagger-core just for springdoc to generate OpenAPI.
- Do not add swagger-annotations separately if you only need annotations already provided by the starter.
- Do not add a separate swagger-ui artifact when already using the springdoc UI starter.
- Do not add both API-only and UI starters for the same web stack without a clear module architecture.
- Do not add both MVC and WebFlux springdoc starters in an application with only one server stack.

If you need a special extension, read the module guide and dependency tree before adding it. Directly declaring a transitive dependency can force a version incompatible with springdoc or Spring Boot.

## 12. Inspecting the Dependency Tree

With Maven:

~~~bash
mvn dependency:tree -Dincludes=org.springdoc,io.swagger.core.v3
~~~

With Gradle:

~~~bash
./gradlew dependencies --configuration runtimeClasspath
~~~

Or inspect a specific dependency:

~~~bash
./gradlew dependencyInsight \
  --dependency springdoc-openapi \
  --configuration runtimeClasspath
~~~

Check for these signs:

- Only one intentional web stack branch is present.
- The springdoc starter has the webmvc or webflux suffix matching the application.
- No v1 artifacts mixed with v2/v3 starters.
- No two competing versions of swagger-core/swagger-annotations.
- Swagger UI is present only if the UI starter was chosen.

If a dependency is brought in by an internal module, inspect the dependency path instead of randomly deleting an artifact from the cache.

## 13. Endpoints to Verify After Choosing a Starter

With either the API-only or UI starter, default OpenAPI documents typically include:

| URL | Expected Result |
|---|---|
| /v3/api-docs | OpenAPI document in JSON format |
| /v3/api-docs.yaml | OpenAPI document in YAML format |

With the UI starter, Swagger UI is typically accessible at:

| URL | Purpose |
|---|---|
| /swagger-ui.html | Swagger UI entry URL, usually redirects |
| /swagger-ui/index.html | Static UI page |
| /v3/api-docs/swagger-config | Configuration loaded by Swagger UI |

Actual URLs also depend on context path, springdoc.api-docs.path, springdoc.swagger-ui.path, reverse proxy, and security configuration.

After running the application, test:

~~~bash
curl -i http://localhost:8080/v3/api-docs
curl -i http://localhost:8080/v3/api-docs.yaml
curl -i http://localhost:8080/swagger-ui.html
~~~

If using API-only, /swagger-ui.html returning 404 is normal. Do not conclude the starter is broken when the application is designed not to serve a UI.

## 14. Choosing a Starter for WebFlux Functional Endpoints

Spring WebFlux supports both annotation-based controllers and functional endpoints:

- Annotation-based: @RestController, @GetMapping, @PostMapping.
- Functional: RouterFunction<ServerResponse> combined with HandlerFunction.

springdoc supports functional endpoints. For routes needing explicit operation descriptions, you can use @RouterOperation or @RouterOperations to attach OpenAPI metadata to the route.

Route example:

~~~java
@Configuration
class ProductRoutes {

    @Bean
    RouterFunction<ServerResponse> productRouter(ProductHandler handler) {
        return RouterFunctions.route()
            .GET("/api/products", handler::findAll)
            .POST("/api/products", handler::create)
            .build();
    }
}
~~~

When documenting a functional route, add operation metadata according to the corresponding springdoc guide:

~~~java
@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/products",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "findAll",
        operation = @Operation(
            operationId = "findProducts",
            summary = "List products"
        )
    )
})
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route()
        .GET("/api/products", handler::findAll)
        .build();
}
~~~

This is a condensed example to illustrate route metadata; imports and bean structure must match the springdoc version in use. Functional endpoints are not a reason to choose the MVC starter; if the server is WebFlux, still choose webflux-api or webflux-ui.

## 15. Spring Security Does Not Decide MVC vs. WebFlux

Spring Security has separate integrations for Servlet and Reactive stacks. Choose the springdoc starter by the web stack, then configure access permissions for OpenAPI/Swagger UI according to the active security model.

For example:

- MVC app using spring-boot-starter-security with a Servlet filter chain: choose webmvc-api or webmvc-ui.
- WebFlux app using reactive security: choose webflux-api or webflux-ui.

If you only need the OpenAPI document and not an interface, API-only is usually cleaner. However, API-only does not automatically make the document public or secure; the /v3/api-docs endpoint is still subject to the application's security rules.

If using the UI starter, check permissions for Swagger UI resources, swagger-config, and the OpenAPI document. Do not open all business APIs just so the UI can load.

## 16. When to Choose API-Only for CI or an API Portal?

A production service may not need Swagger UI embedded in the application. CI can start or hit the app, download the document, validate it, and save it as an artifact:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o target/openapi.json
~~~

The pipeline can then:

1. Validate the OpenAPI document.
2. Run lint checks against organization rules.
3. Compare against the previous release document.
4. Generate SDKs or portal documentation.
5. Store the document as a build artifact.

In this model, API-only reduces the UI components to deploy. If the API portal fetches the document over HTTP, configure authentication, network access, and CORS matching how the portal accesses it; API-only does not configure those policies automatically.

## 17. Signs of Choosing the Wrong Starter

| Symptom | Possible Cause | Where to Check |
|---|---|---|
| MVC app does not generate OpenAPI document | Using webflux starter | Switch to webmvc starter |
| WebFlux app lacks OpenAPI integration | Using webmvc starter | Switch to webflux starter |
| /v3/api-docs works but Swagger UI 404s | Using API-only starter | Add UI starter matching web stack if UI is needed |
| Swagger UI loads but document 404s | Security/path/context path or endpoint config | Check swagger-config and docs URL |
| Project has both MVC and WebFlux but runs MVC | Spring Boot prefers MVC when both starters are present | Check application type and choose webmvc starter if intended |
| Project uses WebClient but server is MVC | Confusing WebClient with WebFlux server | Keep webmvc starter |
| Class/method not found errors after adding springdoc | Mixed major versions or overridden dependencies | Check compatibility matrix and dependency tree |
| Duplicate Swagger UI resources or version mismatch | Manually added swagger-ui alongside UI starter | Remove duplicate dependency after verifying |
| Only API group fails | Wrong group URL or security matcher | Check /v3/api-docs/{group} and access permissions |
| Functional route missing from document | Missing route metadata or annotation config | Use @RouterOperation/@RouterOperations per docs |

## 18. Selection Workflow in a New Project

1. Identify the Spring Boot major version.
2. Check the dependency that boots the web server: MVC or WebFlux.
3. If both are present, determine the actual application type; remember MVC takes precedence by default.
4. Choose the springdoc line compatible with Spring Boot.
5. Decide between API-only and Swagger UI.
6. Add the single corresponding starter.
7. Do not re-declare transitive dependencies already pulled in by the starter without a specific need.
8. Run dependency tree to detect duplicate modules or versions.
9. Start the application and verify /v3/api-docs.
10. If using the UI starter, verify /swagger-ui.html and /v3/api-docs/swagger-config.
11. If Spring Security is present, verify access rules for documentation and APIs per policy.
12. If WebFlux functional routes exist, declare operation metadata and verify generated routes.

## 19. References

- [springdoc-openapi – Getting Started](https://springdoc.org/getting-started.html): current starters, example versions, and Swagger UI/OpenAPI URLs.
- [springdoc-openapi – Modules](https://springdoc.org/modules.html): distinguishing Web MVC, WebFlux, API-only, and UI starters.
- [springdoc-openapi v2 – Getting Started](https://springdoc.org/v2/getting-started.html): starters and versions for Spring Boot 3.
- [springdoc-openapi v2 – Modules](https://springdoc.org/v2/modules.html): MVC/WebFlux API and UI artifacts in the v2 line.
- [springdoc-openapi – Compatibility Matrix](https://springdoc.org/#what-is-the-compatibility-matrix-of-spring-boot-with-springdoc-openapi-): Spring Boot and springdoc major version relationship.
- [springdoc-openapi v1 – Getting Started](https://springdoc.org/v1/getting-started.html): legacy branch artifacts for Spring Boot 1.x/2.x.
- [springdoc-openapi – Migrating from v1](https://springdoc.org/v2/migrating-from-springdoc-v1.html): mapping v1 artifacts to v2 starters.
- [Spring Boot – Reactive Web Applications](https://docs.spring.io/spring-boot/reference/web/reactive.html): WebFlux, functional endpoints, and behavior when both MVC/WebFlux are on the classpath.
- [Spring Boot – Servlet Web Applications](https://docs.spring.io/spring-boot/reference/web/servlet.html): Spring MVC and Servlet stack.

## 20. Practical Summary

Choose the webmvc starter if the server actually runs Spring MVC; choose the webflux starter if the server runs Spring WebFlux. Then choose the api suffix when you only need OpenAPI JSON/YAML or the ui suffix when you need Swagger UI. Also check the Spring Boot major version to use the matching springdoc line: 3.x for Boot 4, 2.x for Boot 3, and 1.8.0 for legacy Boot 1/2 apps.

The right dependency integrates springdoc into the right web stack, but it does not replace checking security, URLs behind reverse proxies, and the generated contract. After adding the starter, verify /v3/api-docs; if UI was selected, also verify Swagger UI and swagger-config before integrating documentation into the development workflow.
