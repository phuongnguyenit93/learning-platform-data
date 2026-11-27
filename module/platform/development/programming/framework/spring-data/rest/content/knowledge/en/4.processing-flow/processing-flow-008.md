# Relationship Between Standard Spring MVC Configuration and Spring Data REST Infrastructure

## Objective

Spring Data REST publishes Spring Data repositories as REST resources. It runs on top of Spring MVC and uses the application's shared HTTP processing lifecycle, while registering dedicated components to discover repositories, route requests, invoke repositories, build linked representations, and handle REST-specific rules.

When configuring an application, distinguish two scopes:

- **Standard Spring MVC** governs controllers written by the application, such as `@Controller`, `@RestController`, `@RequestMapping` routes, interceptors, resource handlers, and general web configuration.
- **Spring Data REST** governs how repositories are published as REST resources, base paths, resource names, pagination, sorting, media types, links, validation, and data-write lifecycle hooks.

Both scopes cooperate within the same web application. Standard MVC configuration remains important, but do not assume every setting meant for MVC controllers automatically replaces Spring Data REST's dedicated configuration.

## 1. Architecture model: same Spring MVC, plus a repository-processing branch

Spring Data REST does not start an independent HTTP server or a separate `DispatcherServlet`. Requests still pass through the servlet container and Spring MVC's `DispatcherServlet`. The difference lies in the `HandlerMapping` instances, handlers, adapters, argument resolvers, message converters, and repository-publishing components that Spring Data REST registers in the `ApplicationContext`.

The overall flow can be pictured as follows:

~~~mermaid
flowchart TD
    A[HTTP request] --> B[Servlet container]
    B --> C[DispatcherServlet]
    C --> D{HandlerMappings}
    D -->|Standard @RequestMapping route| E[Controller / RestController]
    D -->|Exported repository path| F[Spring Data REST HandlerMapping]
    F --> G[Repository REST controller and HandlerAdapter]
    G --> H[RepositoryInvoker]
    H --> I[Spring Data Repository]
    I --> J[Store module: JPA, MongoDB, JDBC, ...]
    E --> K[Spring MVC response handling]
    J --> L[REST representation and links]
    K --> M[HTTP response]
    L --> M
~~~

Key components:

| Component | Role |
|---|---|
| `DispatcherServlet` | Receives requests and dispatches them to the appropriate handler. This is Spring MVC's shared entry point. |
| `HandlerMapping` | Finds a handler for the URL and HTTP request. Spring MVC has mappings for controller annotations; Spring Data REST adds mappings for repository resources. |
| `HandlerAdapter` | Invokes the selected handler. Spring Data REST configures adapters capable of handling the exporter's specialized controllers and argument resolvers. |
| `RepositoryResourceMappings` | Determines which repositories are exported and their corresponding resource paths. |
| `RepositoryInvoker` | Invokes operations on a repository according to resource metadata. |
| `RepositoryRestConfiguration` | Stores configuration specific to the REST exporter, such as base path, repository detection strategy, and representation options. |
| `HttpMessageConverter` | Reads request bodies and writes response bodies. Spring Data REST configures converters suited for JSON, HAL, and formats supported by the exporter. |
| `RepositoryRestConfigurer` | Extension point for applications to customize Spring Data REST configuration. |

Some internal implementation class names may differ across versions. Integration documentation describes the specialized mapping as `RepositoryRestHandlerMapping`; newer APIs may wrap routing via `DelegatingHandlerMapping`. The key point is that the exporter has its own `HandlerMapping` branch to recognize repository paths.

## 2. How are requests routed?

Suppose the application has:

- A standard controller handling `GET /health`.
- An exported repository with resource path `people`.
- Spring Data REST configured with base path `/api`.

Requests are handled according to their purpose:

| Request | Expected handler | Reason |
|---|---|---|
| `GET /health` | Standard MVC controller | This is a route declared by the application with `@GetMapping` or `@RequestMapping`. |
| `GET /api/people` | Spring Data REST | This is the collection resource of the exported repository. |
| `GET /api/people/42` | Spring Data REST | This is an item resource of that repository. |
| `GET /reports/daily` | Standard MVC controller | The path does not belong to an exported repository's resource path. |

`DispatcherServlet` queries `HandlerMapping` instances to find a handler. Spring Data REST's mapping checks whether the URL corresponds to an exported repository resource. If it does not match, that mapping lets other `HandlerMapping` instances continue processing. If it matches, the request is dispatched to Spring Data REST's controller.

Therefore, **a repository's path can occupy a URL space that a standard MVC controller also wants to use**. If a repository is exported as `people`, another controller declaring a conflicting route under `/api/people/**` might not receive requests as expected. The best solution is to design non-overlapping URLs and clearly define which routes belong to the repository exporter and which belong to business controllers.

Do not adjust `HandlerMapping` ordering by guesswork to resolve conflicts. First inspect the actual resource paths, base path, repository detection strategy, and mappings registered by the version in use.

## 3. Two configuration systems with distinct responsibilities

### Standard Spring MVC configuration

These settings serve the application's web layer, especially controllers written by the development team. The familiar extension point is `WebMvcConfigurer`.

Examples of responsibilities typically belonging to MVC:

- Registering interceptors for MVC controllers.
- Configuring resource handlers to serve static resources.
- Registering formatters and converters for controller input data.
- Configuring CORS for standard MVC routes.
- Adjusting content negotiation or shared MVC components.
- Registering controllers with `@Controller`, `@RestController`, `@RequestMapping`, `@GetMapping`.

Example:

~~~java
@Configuration
class WebConfiguration implements WebMvcConfigurer {

    @Override
    public void addInterceptors(InterceptorRegistry registry) {
        registry.addInterceptor(new RequestLoggingInterceptor())
                .addPathPatterns("/health", "/reports/**");
    }

    @Override
    public void addCorsMappings(CorsRegistry registry) {
        registry.addMapping("/reports/**")
                .allowedMethods("GET");
    }
}
~~~

This example illustrates the scope of the application's MVC configuration. If you want a rule to apply to Spring Data REST endpoints, check the corresponding exporter extension point rather than assuming every MVC callback applies identically.

### Spring Data REST configuration

Spring Data REST has its own configuration via:

- `RepositoryRestConfiguration`: exporter options.
- `RepositoryRestConfigurer`: callbacks to modify exporter configuration and supporting components.
- Spring Boot properties under the `spring.data.rest.*` namespace.

Common settings include:

- Base path, for example `/api`.
- Repository detection strategy: which repositories are allowed to be published as REST resources.
- Collection resource names and paths.
- Default page size, page size limits, and query parameter names for `page` and `sort`.
- Default media types and response body behavior on create/update.
- CORS for REST resources.
- The exporter's `ConversionService`, `HttpMessageConverter`, and Jackson mapper.
- Validation listeners and exception resolvers related to Spring Data REST.

For example, changing the base path in Spring Boot:

~~~properties
spring.data.rest.base-path=/api
spring.data.rest.default-page-size=20
spring.data.rest.max-page-size=100
~~~

These properties belong to the Spring Data REST namespace. They are distinct from standard Spring Data Web configuration such as `spring.data.web.*`.

## 4. Spring Boot vs. non-Boot Spring MVC applications

### When using Spring Boot

The standard approach is to add the starter:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-rest</artifactId>
</dependency>
~~~

Or with Gradle:

~~~groovy
implementation("org.springframework.boot:spring-boot-starter-data-rest")
~~~

When the application is enabled with `@SpringBootApplication` or `@EnableAutoConfiguration`, Spring Boot auto-configures Spring Data REST. There is no need to manually import `RepositoryRestMvcConfiguration` again.

To customize the exporter, register a `RepositoryRestConfigurer` bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.rest.webmvc.config.RepositoryRestConfigurer;

@Configuration
class DataRestConfiguration {

    @Bean
    RepositoryRestConfigurer repositoryRestConfigurer() {
        return RepositoryRestConfigurer.withConfig(config ->
                config.setBasePath("/api"));
    }
}
~~~

The example above uses the `RepositoryRestConfigurer.withConfig` convenience API. If your project's Spring Data REST version does not provide this convenience method, implement the interface and override the corresponding configuration method for that version.

### When integrating into a non-Boot Spring MVC application

The application needs the `spring-data-rest-webmvc` dependency compatible with the Spring Data version in use. Then import Spring Data REST's MVC configuration into the application configuration:

~~~java
import org.springframework.context.annotation.Configuration;
import org.springframework.context.annotation.Import;
import org.springframework.data.rest.webmvc.config.RepositoryRestMvcConfiguration;

@Configuration
@Import(RepositoryRestMvcConfiguration.class)
class WebConfiguration {
}
~~~

`RepositoryRestMvcConfiguration` bootstraps the MVC components needed to export repositories in the `ApplicationContext`. The application must also configure Spring Data repositories and the corresponding store module, such as Spring Data JPA or Spring Data MongoDB.

Do not both rely on Spring Boot auto-configuration and manually re-import the exporter configuration without a clear reason. Duplicate configuration can make bean initialization and MVC behavior unpredictable.

## 5. Example: repository resources running alongside MVC controllers

A repository can be exported as follows:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;

@RepositoryRestResource(path = "people")
public interface PersonRepository extends JpaRepository<Person, Long> {
}
~~~

With base path `/api`, Spring Data REST generates resource endpoints from repository metadata, such as:

- `GET /api/people`: retrieve collection.
- `GET /api/people/42`: retrieve a single item.
- `POST /api/people`: create an item if the operation is exported and permitted.
- `PUT` or `PATCH /api/people/42`: update an item if exported and permitted.
- `DELETE /api/people/42`: delete an item if exported and permitted.

Actual supported operations also depend on the repository, export configuration, hidden methods, and access permissions. Do not treat the list above as a guarantee that all write endpoints are always open.

A standard MVC controller can still coexist alongside the repository:

~~~java
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import java.util.Map;

@RestController
class HealthController {

    @GetMapping("/health")
    Map<String, String> health() {
        return Map.of("status", "UP");
    }
}
~~~

Here:

- `/health` is handled by standard Spring MVC.
- `/api/people` is handled by Spring Data REST.
- Both run in the same web application and go through `DispatcherServlet`.

Spring Data REST invokes the repository directly through the Spring Data abstraction. It does not automatically invoke the application's business services simply because service beans exist. If an operation requires a multi-step business workflow, business-level authorization checks, coordinating multiple aggregates, or specialized side effects, consider creating a controller endpoint and calling the corresponding service instead of directly exposing the repository operation.

## 6. Choosing annotations for custom controllers

Three cases are commonly confused:

| Annotation | When to use | Primary behavior |
|---|---|---|
| `@RestController` / `@Controller` | Endpoints belonging to the application's standard web layer. | Handled by standard Spring MVC configuration; does not automatically fall under Spring Data REST's dedicated configuration and handling. |
| `@RepositoryRestController` | Custom endpoints tied to the URI space and resources of the repository exporter. | Served under Spring Data REST's base path and can use the exporter's configuration, message converters, exception handling, and certain specialized behaviors. |
| `@BasePathAwareController` | Custom endpoints that should live under Spring Data REST's base path but are not specific operations on an entity resource. | Suitable for custom operations or resources inside Spring Data REST's API namespace. |

Example of a custom endpoint inside the repository REST space:

~~~java
import org.springframework.data.rest.webmvc.RepositoryRestController;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.http.ResponseEntity;

@RepositoryRestController
class ScannerController {

    @GetMapping("/scanners/search/producers")
    ResponseEntity<?> getProducers() {
        // Call service or repository and build the appropriate representation.
        return ResponseEntity.ok().build();
    }
}
~~~

With base path `/api`, the full path of this example is `/api/scanners/search/producers`.

Use `@RepositoryRestController` when a custom endpoint needs to integrate into repository REST mechanics. Spring Data REST documentation describes additional behaviors such as applying repository-specific CORS and interceptors supporting lazy property access when using JPA.

If you only need a standalone application endpoint, `@RestController` is usually the better choice. Choosing a specialized annotation should be driven by the need to integrate with the exporter, not merely because the endpoint returns JSON.

## 7. Shared concerns vs. separately configured concerns

| Concern | Standard Spring MVC | Spring Data REST |
|---|---|---|
| HTTP entry point | Uses the application's `DispatcherServlet`. | Also uses that same `DispatcherServlet`. |
| Routing | Mappings for controller annotations and other MVC handlers. | Adds mappings recognizing exported repository resources. |
| Controllers | `@Controller`, `@RestController`. | Built-in exporter controllers and custom controllers carrying appropriate annotations. |
| JSON and response bodies | MVC's message converter configuration. | Has converters and representations for JSON, HAL, URI lists; customize via `RepositoryRestConfigurer` when needed. |
| Base path | Usually comes from context path, servlet path, or application mappings. | Uses `RepositoryRestConfiguration` or `spring.data.rest.base-path`. |
| CORS | MVC configuration such as `WebMvcConfigurer#addCorsMappings`. | CORS configuration within REST exporter scope, e.g., `RepositoryRestConfigurer` callback. |
| Validation | Request/controller validation and Bean Validation per MVC configuration. | Has repository event validation listeners and pre/post repository operation hooks. |
| Exceptions | MVC resolvers and advice. | Has exporter exception handling; `RepositoryRestConfigurer` provides callbacks to customize related resolvers. |
| Security | Servlet filter chain, such as Spring Security. | That same filter chain protects repository endpoints; permissions still must be configured for routes and write operations. |
| Pagination and sorting | Can use Spring Data Web support such as `Pageable` and `Sort` in controllers. | Has the REST exporter's own query parameter conventions and page sizes, configurable via `spring.data.rest.*`. |

Some infrastructure sits outside `DispatcherServlet`, notably servlet filters and the Spring Security filter chain; they apply before requests enter MVC and therefore protect both groups of endpoints. Conversely, interceptors, converters, or exception resolvers attached to a specific `HandlerMapping` or configuration should not be assumed to apply uniformly to all handlers.

## 8. Distinguishing Spring Data Web from Spring Data REST

The two concepts are related but do not replace each other:

- **Spring Data Web support** enables MVC controllers to receive types like `Pageable` and `Sort`, or convert identifiers into domain objects via web support components.
- **Spring Data REST** exports repositories as REST resources and provides a REST API with resource mappings, representations, links, metadata, and repository behaviors.

Therefore, enabling `@EnableSpringDataWebSupport` does not mean repositories are exported as REST endpoints. Similarly, changing `spring.data.web.*` does not replace configuring `spring.data.rest.*`.

## 9. CORS, exceptions, converters, and security

### CORS

If MVC endpoints work but repository endpoints fail preflight or are blocked by browsers, check Spring Data REST's CORS configuration. You can configure it via `RepositoryRestConfigurer` and the `CorsRegistry` parameter of the exporter configuration callback. If CORS is needed for standard controllers, standard MVC configuration still plays its own role.

### Message converters and representations

Spring Data REST supports representations such as HAL and JSON, while generating links between collections, items, and associations. When clients send `Accept` or `Content-Type`, media types and converters determine how requests are read and responses are written.

If you need to add converters or customize Jackson for repository REST, use `RepositoryRestConfigurer` callbacks such as:

- `configureHttpMessageConverters(...)`
- `configureJacksonObjectMapper(...)`
- `configureConversionService(...)`

When adding converters, preserve the default converters required by the exporter. Replacing the entire list without checking can break HAL reading/writing or specialized media types.

### Exception handling

Errors from the repository exporter can pass through exception resolvers configured for Spring Data REST. If an exception is handled differently between MVC controllers and repository endpoints, check the handlers, resolvers, and controller annotations in use. `RepositoryRestConfigurer` provides `configureExceptionHandlerExceptionResolver(...)` to extend the exporter's resolver.

### Security

Exporting repositories can expose read and write operations supported by the repository. Spring Data REST does not replace application authorization. You must:

- Use Spring Security to protect appropriate URLs and HTTP methods.
- Only export repositories that truly need to be public.
- Use repository detection strategies and the `exported` attribute to control which resources or methods are published.
- Enforce permissions on each operation, especially create, update, and delete.
- Never rely on hiding a link in HAL as a security mechanism.

If business rules require authorization decisions based on aggregate state or relationships across multiple objects, place checks in the appropriate service/security layer and test them with real HTTP requests to the endpoints.

## 10. Common misconceptions

1. **Changing `spring.mvc.*` does not change the repository base path.** The exporter's base path belongs to `spring.data.rest.base-path` or `RepositoryRestConfiguration.setBasePath(...)`.
2. **Enabling `@EnableSpringDataWebSupport` does not expose repository endpoints.** That annotation provides web support for Spring Data; it does not export repositories.
3. **Custom controllers do not receive requests.** Check whether the path overlaps an exported repository's resource path.
4. **Using `@RestController` while expecting the exporter's base path, HAL converters, or exception handling.** Use `@RepositoryRestController` or `@BasePathAwareController` if the endpoint genuinely needs to integrate with Spring Data REST.
5. **Adding converters breaks HAL.** Check how converters are added and preserve required default converters.
6. **Repository endpoints work, but writes are unprotected.** Exporting resources does not guarantee authorization; configure Spring Security and control exports.
7. **Manually importing exporter configuration in Spring Boot unnecessarily.** The starter and auto-configuration already handle registration; add manual configuration only when the application architecture genuinely requires it.
8. **Assuming the service layer automatically runs when repositories are exported.** Spring Data REST works against the repository abstraction; service business workflows are not invoked automatically.

## 11. Diagnostic checklist when an endpoint does not work

When `GET /api/people` returns 404 or hits the wrong controller, check in order:

1. Is `spring-boot-starter-data-rest` or `spring-data-rest-webmvc` present and compatible with the Spring Boot/Spring Data release train?
2. Does the application have Spring Boot auto-configuration enabled? If not using Boot, is `RepositoryRestMvcConfiguration` imported into the right `ApplicationContext`?
3. Is the repository scanned and registered as a bean in the `ApplicationContext`?
4. Is the repository exported under the current detection strategy? Is any annotation or `exported=false` attribute hiding it?
5. What is the actual base path? What resource path is generated from the repository?
6. Does any MVC controller declare a URL overlapping the repository's resource space?
7. Does the request pass through Spring Security? Was it rejected before reaching `DispatcherServlet`?
8. What `Accept` and `Content-Type` headers is the client sending? Do the exporter's converters support those media types?
9. If only preflight requests fail, is CORS configured for the right endpoint scope?

When debugging, inspect the mappings registered at application startup and check the actual URLs. Do not alter `HandlerMapping` ordering or add broad MVC configuration before determining which mapping is currently handling the request.

## 12. Guidelines for choosing an implementation approach

- Use Spring Data REST when a resource can be naturally represented from a repository and standard CRUD operations meet the requirements.
- Use standard MVC controllers calling services when an endpoint represents a business use case or workflow.
- Use `@RepositoryRestController` when a custom endpoint needs to blend into Spring Data REST's base path, representations, CORS, or exception handling.
- Keep repository resource URLs and business controller URLs separate.
- Place configuration in the right scope: `WebMvcConfigurer` for application MVC, `RepositoryRestConfigurer` for the exporter.
- Manage Spring Boot, Spring Data Commons, and Spring Data REST versions according to a compatible release train; do not upgrade a single Spring Data module independently without checking the compatibility matrix.

## Summary

Spring Data REST is an extension of Spring MVC. `DispatcherServlet` and the web application remain the shared foundation; Spring Data REST adds a specialized routing and processing branch to turn repositories into REST resources. Therefore, standard MVC configuration and Spring Data REST configuration can coexist while maintaining separate scopes of responsibility.

When a setting does not affect repository endpoints as expected, identify which `HandlerMapping` owns the request and adjust the right extension point: `WebMvcConfigurer` for MVC controllers, and `RepositoryRestConfigurer` and `RepositoryRestConfiguration` for the repository exporter.

## References

- [Spring Data REST — Getting Started](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html)
- [Adding Spring Data REST to an Existing Spring MVC Application](https://docs.spring.io/spring-data/rest/reference/customizing/adding-sdr-to-spring-mvc-app.html)
- [Overriding Spring Data REST Response Handlers](https://docs.spring.io/spring-data/rest/reference/customizing/overriding-sdr-response-handlers.html)
- [RepositoryRestConfigurer API](https://docs.spring.io/spring-data/rest/reference/api/java/org/springframework/data/rest/webmvc/config/RepositoryRestConfigurer.html)
- [Spring Framework — Special Bean Types](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-servlet/special-bean-types.html)