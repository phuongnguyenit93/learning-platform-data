# Conditions for Springdoc to Recognize Controllers and Handlers

Springdoc generates documentation from endpoints registered by Spring in the application. Therefore, for an operation to appear in OpenAPI, the controller must be created as a bean in the `ApplicationContext`, the handler method must be recognized as a handler by Spring MVC or Spring WebFlux, and the endpoint must fall within the scope of the documentation being generated.

Simply naming a class `Controller` or naming a method `getUsers()` is not enough for Springdoc to recognize it. What decides is whether Spring's startup process registers that class and maps HTTP requests to the method. Afterwards, springdoc filters and hidden annotations decide whether the operation is included in a specific document.

## 1. Recognition Flow from Application Startup

In a Spring Boot application using Spring MVC or WebFlux, the process can be pictured through these steps:

1. **Spring Boot creates the ApplicationContext**: application configuration, component scan, profiles, and auto-configuration conditions determine which beans are registered.
2. **Controllers become beans**: classes discovered via component scan, imports, or bean definitions are instantiated according to the Spring lifecycle.
3. **The web framework registers handlers**: Spring MVC or WebFlux reads mappings on controllers and registers them into the handler mapping system.
4. **Springdoc reads handler metadata**: springdoc collects mappings, parameters, data types, and related annotations to build OpenAPI operations.
5. **Documentation is filtered and exported**: package/path configuration, groups, and hidden annotations decide which operations belong to the document being viewed.

Therefore, distinguish three questions when an endpoint does not appear:

- Is the controller actually a bean in the running application?
- Did Spring register a mapping for that method?
- Was the registered mapping excluded from the documentation by a filter or annotation?

Swagger UI only renders the generated OpenAPI document. If a controller has not been registered by Spring or no mapping exists, opening Swagger UI cannot make the endpoint appear on its own.

## 2. Conditions for a Controller to Become a Bean

### 2.1. Using the Appropriate Stereotype Annotation

Springdoc works with Spring-managed controllers. For REST APIs, the most common approach is `@RestController`:

```java
package com.example.shop.web;

import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/products")
public class ProductController {

    @GetMapping
    public List<ProductResponse> findAll() {
        return productService.findAll();
    }
}
```

`@RestController` is a combined annotation of `@Controller` and `@ResponseBody`. It marks the class as a Spring controller and indicates that method return values are written to the response body, typically via a JSON converter.

`@Controller` can also be recognized as a controller by Spring. However, if methods return API data instead of view names, `@ResponseBody` is required at the method or class level:

```java
@Controller
@ResponseBody
@RequestMapping("/api/v1/products")
class ProductController {

    @GetMapping
    List<ProductResponse> findAll() {
        return productService.findAll();
    }
}
```

Springdoc can read handlers registered from `@Controller` or `@RestController`. Choosing `@RestController` primarily makes the intent of building an API and returning response bodies explicit.

### 2.2. Controller Must Be Within Component Scan Scope

By default, `@SpringBootApplication` enables component scanning from the package containing the application class and its subpackages. For example:

```text
com.example.shop
├── ShopApplication.java
├── web
│   └── ProductController.java
├── service
│   └── ProductService.java
└── repository
    └── ProductRepository.java
```

If `ShopApplication` resides in `com.example.shop`, `ProductController` in `com.example.shop.web` is discovered under default configuration.

If a controller resides outside the root package, such as `com.example.catalog.web`, default component scanning may not reach that package. Configure the scan scope explicitly:

```java
@SpringBootApplication(scanBasePackages = {
        "com.example.shop",
        "com.example.catalog"
})
public class ShopApplication {
    public static void main(String[] args) {
        SpringApplication.run(ShopApplication.class, args);
    }
}
```

Another option is importing required configurations or beans with `@Import` when modular architecture calls for it. Only expand the scan scope to packages belonging to the application; scanning too broadly can cause Spring to register unintended beans or create bean name conflicts.

In multi-module applications, ensure the module containing the controller is declared as a runtime dependency and its package is component-scanned or imported. Having source code in the repository alone does not mean that class is included in the running application.

### 2.3. Conditions and Profiles Can Prevent Controller Creation

A controller can be controlled by configurations such as:

- `@Profile`: the bean exists only when the corresponding profile is active.
- `@ConditionalOnProperty`: the bean is created only when the property satisfies the condition.
- `@ConditionalOnClass` or `@ConditionalOnMissingBean`: the bean depends on the classpath or the presence/absence of another bean.
- `@ComponentScan` configuration with include/exclude filters.

Example:

```java
@RestController
@RequestMapping("/api/internal/reports")
@Profile("internal")
class InternalReportController {

    @GetMapping
    List<ReportResponse> findAll() {
        return reportService.findAll();
    }
}
```

The controller above is created only when the `internal` profile is active. If the application runs with the `dev` profile without enabling `internal`, the mapping is not registered and springdoc has no operation to document.

When documentation differs across local, staging, and production environments, compare the active profiles, properties, and bean creation conditions of each environment.

## 3. Conditions for a Method to Become a Handler

### 3.1. Method Must Have a Spring-Supported Request Mapping

In Spring MVC and WebFlux, annotations such as `@RequestMapping`, `@GetMapping`, `@PostMapping`, `@PutMapping`, `@PatchMapping`, and `@DeleteMapping` register handler methods.

Example:

```java
@RestController
@RequestMapping("/api/v1/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse findById(@PathVariable UUID id) {
        return orderService.findById(id);
    }

    @PostMapping
    OrderResponse create(@RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }

    @PutMapping("/{id}")
    OrderResponse replace(
            @PathVariable UUID id,
            @RequestBody UpdateOrderRequest request) {
        return orderService.replace(id, request);
    }
}
```

Spring combines the class-level mapping `/api/v1/orders` with the method-level mappings. Thus, the handlers have the final paths:

| Java Method | HTTP Method | Path |
|---|---|---|
| `findById` | `GET` | `/api/v1/orders/{id}` |
| `create` | `POST` | `/api/v1/orders` |
| `replace` | `PUT` | `/api/v1/orders/{id}` |

A plain Java method without a mapping will not become an HTTP endpoint just because it sits inside a `@RestController`:

```java
@RestController
class OrderController {

    // This is an internal helper method, not an HTTP handler.
    OrderResponse mapToResponse(Order order) {
        return new OrderResponse(order.getId(), order.getCode());
    }
}
```

### 3.2. Mapping Must Be Successfully Registered by Spring

Spring MVC uses `RequestMappingHandlerMapping` to find and register handler methods. WebFlux has a corresponding handler mapping mechanism. If the application fails to start because two handlers have conflicting mappings, the documentation cannot reflect a valid application state either.

Mapping conditions can include:

- HTTP method: `GET`, `POST`, `PUT`, `PATCH`, `DELETE`.
- Path and path variables.
- `params` and `headers`.
- `consumes` and `produces`.
- Custom mapping conditions added by the application.

Example:

```java
@GetMapping(
        path = "/search",
        params = "status",
        produces = MediaType.APPLICATION_JSON_VALUE
)
List<OrderResponse> search(@RequestParam String status) {
    return orderService.search(status);
}
```

Springdoc reads the mapping metadata registered by Spring. Inspect `params`, `headers`, media type, and path conditions when an operation appears missing or looks different from the endpoint you expect.

OpenAPI defines only one operation per path and HTTP method pair. If an application has multiple handlers sharing the same path and method differentiated only by `params` or `headers`, design the documentation to express a unified contract, such as modeling optional parameters or multiple media type values within the same operation. Do not expect Swagger UI to always display each mapping variant as an independent operation.

### 3.3. Return Type Does Not Decide Handler Registration

A handler can return a DTO, `ResponseEntity<T>`, `List<T>`, reactive types, or other response bodies depending on the stack. Return types affect the schema inferred by springdoc, but the prerequisite for the method to be recognized remains a valid controller bean and request mapping.

If the method is registered but its schema is incomplete, check return types, generics, Jackson annotations, and OpenAPI metadata. That is a response description issue, distinct from whether Spring recognizes the handler.

## 4. Spring MVC, WebFlux, and Functional Endpoints

### 4.1. Choosing the Right Starter for the Web Stack

Springdoc needs a starter matching the application:

| Web stack | With Swagger UI | OpenAPI Endpoint Only |
|---|---|---|
| Spring MVC | `springdoc-openapi-starter-webmvc-ui` | `springdoc-openapi-starter-webmvc-api` |
| Spring WebFlux | `springdoc-openapi-starter-webflux-ui` | `springdoc-openapi-starter-webflux-api` |

With Spring MVC, handlers are typically declared using controllers and `@RequestMapping`. With WebFlux, annotated controllers are also supported; ensure the application actually runs WebFlux and uses the corresponding WebFlux starter.

Choosing the wrong starter can prevent springdoc from reading the application's handler mapping system properly or leave out required UI/API components. Verify runtime dependencies before investigating controller annotations.

### 4.2. Functional Endpoints Using RouterFunction

Spring WebFlux and Spring MVC support declaring functional routes via `RouterFunction`. These routes are not controller methods annotated with `@GetMapping`, so they need to be documented using springdoc's router operation mechanism.

Structural example:

```java
@Bean
@RouterOperations({
    @RouterOperation(
        path = "/api/v1/products",
        method = RequestMethod.GET,
        beanClass = ProductHandler.class,
        beanMethod = "findAll",
        operation = @Operation(
            operationId = "findAllProducts",
            summary = "Get product list"
        )
    )
})
RouterFunction<ServerResponse> productRoutes(ProductHandler handler) {
    return RouterFunctions.route(
            RequestPredicates.GET("/api/v1/products"),
            handler::findAll
    );
}
```

`@RouterOperation` or `@RouterOperations` provides OpenAPI metadata for functional routes. Cross-check declarations and handler types with the springdoc version in use, as some attributes may differ across major versions and between MVC and WebFlux.

If using functional routes without corresponding descriptive metadata, do not assume every route is fully documented just because the application serves requests successfully.

### 4.3. Endpoints That Are Not Controller Handlers

Not every URL served by an application is a `@RequestMapping` handler. For instance, static resources, custom servlets, filters, WebSockets, gateway routes, or endpoints registered by another framework may go through separate mechanisms.

Springdoc focuses on the handlers and integrations it supports. For endpoints belonging to other mechanisms, consult the corresponding integration documentation or describe the OpenAPI contract via appropriate configuration/annotations. Do not add a dummy controller just to make a path appear in the documentation if it does not represent actual runtime behavior.

## 5. Filters That Decide Which Handlers Appear in Documentation

After Spring registers handlers, springdoc can narrow documentation scope by package, path, or group. Therefore, an endpoint may work normally yet not appear in a particular OpenAPI document.

### 5.1. Filtering by Package and Path

Global configuration in `application.yml` can restrict which controllers and paths are included in the documentation:

```yaml
springdoc:
  packages-to-scan:
    - com.example.shop.web
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
```

- `packages-to-scan` limits which controller packages are scanned.
- `paths-to-match` keeps only paths matching the pattern.
- `paths-to-exclude` removes paths matching the pattern from documentation.

These filters affect the documentation generated by springdoc. They do not alter Spring's component scan and do not remove mappings from the application.

### 5.2. Creating Separate Documents with GroupedOpenApi

An application may have public and internal documentation. Each group can apply its own package/path scope:

```java
@Configuration
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
                .group("public")
                .packagesToScan("com.example.shop.web.publicapi")
                .pathsToMatch("/api/**")
                .build();
    }

    @Bean
    GroupedOpenApi internalApi() {
        return GroupedOpenApi.builder()
                .group("internal")
                .packagesToScan("com.example.shop.web.internal")
                .pathsToMatch("/internal/**")
                .build();
    }
}
```

When investigating a missing endpoint, verify whether you are looking at the default document or a specific group. An endpoint might not belong to the `public` group while still appearing in the `internal` group.

### 5.3. Hidden Annotations Excluding Operations from OpenAPI

Springdoc supports OpenAPI's hidden annotations:

```java
@Hidden
@RestController
@RequestMapping("/api/internal/maintenance")
class MaintenanceController {
    // Handlers in this controller are hidden from documentation.
}
```

Or hiding a single method:

```java
@Operation(hidden = true)
@DeleteMapping("/{id}/purge")
void purge(@PathVariable UUID id) {
    maintenanceService.purge(id);
}
```

`@Hidden` can be applied at the controller or handler level; `@Operation(hidden = true)` hides a specific operation. These annotations affect only OpenAPI documentation; they do not disable routes or replace authorization mechanisms.

Additionally, `@Parameter(hidden = true)` and `@Schema(hidden = true)` hide parameters or schema properties respectively. They do not hide the entire controller.

## 6. Distinguishing Endpoint Recognition from Authentication and Authorization

Spring Security may block a request if the caller is unauthenticated or lacks permissions. That does not mean the handler was not registered by Spring.

For example, a method with `@PreAuthorize("hasAuthority('ORDER_READ')")` can still appear in OpenAPI if the controller and mapping are valid. In that case, the documentation should describe the security scheme and appropriate security requirements so integrators know how to call the endpoint.

Similarly, CORS, CSRF, servlet filters, or interceptors can affect runtime requests without typically determining whether Springdoc recognizes the handler mapping. When an operation appears in docs but testing it yields `401`, `403`, or a CORS error, investigate the security layer and HTTP configuration separately.

## 7. Diagnostic Workflow for Missing Endpoints

Follow these steps in order to pinpoint the exact layer causing the issue:

1. **Check the application started with the right profile**: verify active profiles, properties, and controller bean creation conditions.
2. **Check the controller exists in ApplicationContext**: verify package scan, runtime modules, `@Import`, and conditions like `@Profile`/`@ConditionalOnProperty`.
3. **Check mappings registered by Spring**: if Spring Boot Actuator is present and the mappings endpoint is exposed, inspect `/actuator/mappings` to find the desired path, HTTP method, and handler method.
4. **Check the springdoc starter**: confirm MVC vs. WebFlux and the matching `*-api` or `*-ui` dependency.
5. **Inspect OpenAPI directly**: call `/v3/api-docs` or the path configured via `springdoc.api-docs.path`; search for the path and method in JSON.
6. **Check filters/groups**: cross-check `packages-to-scan`, `paths-to-match`, `paths-to-exclude`, and `GroupedOpenApi` configuration.
7. **Check hidden annotations**: look for `@Hidden` or `@Operation(hidden = true)` on the controller or method.
8. **Check the endpoint type**: if the route is a `RouterFunction` or custom handler mapping, verify springdoc supports it and appropriate metadata has been provided.

The table below helps direct your investigation:

| Inspection Result | Where to Investigate |
|---|---|
| Controller bean not found | Component scan, `@Import`, profiles, conditional beans, module dependencies |
| Bean exists but no mapping in Actuator | `@RequestMapping`, web stack configuration, mapping conflicts, or handler type |
| Mapping exists in Actuator but missing in OpenAPI | Starter, package/path filters, groups, hidden annotations, unsupported mapping type |
| Operation exists in `/v3/api-docs` but not shown in Swagger UI | UI path, selected group, browser cache, or document loaded by UI |
| Operation exists but calling the API is rejected | Authentication, authorization, CSRF, CORS, or runtime filters |

If not using Actuator, inspect startup logs or write integration tests to verify mappings. Only expose Actuator endpoints when needed in testing environments; do not widen production access just for diagnostics.

## 8. Testing Recognition Conditions with Integration Tests

An integration test can verify that the controller is registered and OpenAPI contains the expected operation. Example with Spring Boot Test and MockMvc:

```java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiControllerRegistrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void productEndpointIsPublishedInOpenApi() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
                .andExpect(status().isOk())
                .andExpect(jsonPath(
                        "$.paths['/api/v1/products'].get"
                ).exists());
    }
}
```

The example assumes the application uses the WebMVC starter, the default documentation endpoint, and `ProductController` is registered in the test context. With WebFlux, use `WebTestClient` and the corresponding test setup.

This test verifies the OpenAPI output actually produced by the application. Add assertions for key methods, schemas, or responses if the API contract needs protection across refactorings.

## 9. Common Misconceptions

- **Naming the class `ProductController` is enough**: Spring must create the bean and register the handler mapping. A class name does not replace annotations or bean configuration.
- **Having `@RestController` turns every method into an endpoint**: methods need a Spring-supported HTTP mapping.
- **If an endpoint runs, it must appear in every OpenAPI group**: package/path filters and groups can exclude endpoints from the document being viewed.
- **Getting `401/403` means Springdoc did not recognize the handler**: security governs request authorization; it does not mean the mapping is absent.
- **`@Hidden` disables the endpoint**: the annotation only hides the operation from documentation; it does not remove the runtime route.
- **Every URL is a controller handler**: static resources, servlets, WebSockets, gateway routes, and functional endpoints have their own registration mechanisms.
- **Swagger UI not showing it means the controller does not exist**: inspect `/v3/api-docs` first to separate documentation generation issues from UI or group issues.

## 10. Checklist When Adding a New Controller

- [ ] Controller uses `@RestController` or `@Controller` appropriately and is managed by Spring.
- [ ] Controller package is within component scan scope or explicitly imported.
- [ ] Module containing the controller is on the runtime classpath.
- [ ] Profiles and bean creation conditions match the running environment.
- [ ] Each endpoint has `@RequestMapping` or a corresponding mapping annotation.
- [ ] Mappings do not conflict and have the right path, HTTP method, params, headers, consumes, and produces.
- [ ] Springdoc starter matches Spring MVC or WebFlux.
- [ ] Package/path filters and groups include the desired endpoints.
- [ ] No unintended `@Hidden` or `@Operation(hidden = true)` annotations exist.
- [ ] Functional endpoints have appropriate `@RouterOperation`/`@RouterOperations` metadata.
- [ ] Endpoint appears in `/v3/api-docs` and is tested if it is part of a critical contract.

Springdoc can only accurately document handlers that the application has registered and that fall within the documentation scope. Once you grasp the sequence from component scan, bean registration, and handler mapping to OpenAPI filters, finding why an endpoint is missing becomes clear and verifiable at every layer.
