# Operation Missing Due to @Hidden, Inheritance, or Unrecognized Mapping

An operation may fail to appear in OpenAPI even though the application starts and other APIs still work. The cause usually lies in one of three layers: an annotation requesting that the operation be hidden, mapping metadata placed on an interface or superclass that Spring does not resolve as expected, or a controller/method not registered by Spring MVC or Spring WebFlux as a handler that Springdoc can read.

When troubleshooting this issue, distinguish two questions: is the endpoint actually registered by Spring to receive HTTP requests, and is the registered endpoint included in the current OpenAPI document? If the route still handles requests but is missing from `/v3/api-docs`, check hiding annotations, package/path filters, document groups, and customizers. If the route also returns 404 or is not recognized by handler mappings, check the controller bean, component scan, proxy, and mapping annotations.

This lesson moves from the meaning of `@Hidden` to how Spring handles annotations on interfaces, inheritance, and request mappings. The final part builds a diagnostic procedure using handler mappings, OpenAPI JSON, group endpoints, and HTTP tests to pinpoint the exact layer causing the missing operation.

## 1. Classifying the Symptom Before Fixing

Not every case of Swagger missing an operation has the same cause:

| Symptom | Layer to check first |
|---|---|
| HTTP endpoint still works but OpenAPI lacks the path | @Hidden, @Operation(hidden), filter, group, customizer |
| Both HTTP endpoint and OpenAPI are missing | Controller bean, component scan, mapping registration |
| Path exists but is missing one HTTP method | Method-level @Hidden, mapping condition, operation customizer |
| Method appears in default document but disappears in group | GroupedOpenApi package/path filters |
| Parameter disappears while operation remains | @Parameter(hidden = true), parameter resolution |
| Schema or property disappears while operation remains | @Schema(hidden = true), Jackson view, or schema customization |
| Endpoint exists on local JVM but not in another profile | @Profile, @Conditional, component scan, or environment config |
| Mapping is on interface but route is not registered | Placement of @RequestMapping, proxy strategy, and Spring Framework version |

Before editing annotations, confirm the URL, HTTP method, profile, context path, and OpenAPI endpoint being inspected. The application may be running a different profile or document group than the developer assumes.

## 2. @Hidden at the Controller Level

Springdoc supports the `io.swagger.v3.oas.annotations.Hidden` annotation on controllers. When placed at the type level, the annotation excludes the controller from documentation:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Hidden
@RestController
@RequestMapping("/internal/reports")
public class InternalReportController {

    @GetMapping
    public List<ReportResponse> listReports() {
        return reportService.findAll();
    }
}
~~~

In this case, the `GET /internal/reports` operation is omitted from the OpenAPI document. However, `@Hidden` only controls documentation generation. It does not disable the bean, remove the `RequestMappingHandlerMethod`, or block HTTP requests.

If the endpoint needs protection, use Spring Security, service-layer authorization, or an appropriate access control mechanism. Hiding a path in Swagger UI is not a security measure.

## 3. @Hidden at the Method Level

You can hide an individual method while still publishing the remaining methods of the controller:

~~~java
@RestController
@RequestMapping("/orders")
public class OrderController {

    @GetMapping("/{id}")
    public OrderResponse getOrder(@PathVariable UUID id) {
        return orderService.getById(id);
    }

    @Hidden
    @DeleteMapping("/{id}/purge")
    public void purgeOrder(@PathVariable UUID id) {
        orderService.purge(id);
    }
}
~~~

The `GET /orders/{id}` operation still appears, whereas `DELETE /orders/{id}/purge` is hidden from OpenAPI.

This is appropriate when a controller contains both public APIs and operations meant only for internal tasks. However, if another documentation group also needs that operation, `@Hidden` can still exclude the operation from documentation globally; consider using `GroupedOpenApi` or a group-specific customizer instead of hiding globally.

## 4. Using @Operation(hidden = true)

Another way to hide an operation is setting the `hidden` attribute in the `Operation` annotation:

~~~java
@GetMapping("/diagnostics")
@Operation(
    operationId = "getDiagnostics",
    summary = "Get diagnostic information",
    hidden = true
)
public DiagnosticsResponse diagnostics() {
    return diagnosticsService.snapshot();
}
~~~

`@Operation(hidden = true)` is clearly scoped to the operation. It can be used when the method already carries other OpenAPI metadata but the entire operation needs to be hidden.

Do not confuse `hidden` with `deprecated`. `deprecated` signals that an operation should not be used for new integrations while still appearing in documentation. `hidden` removes the operation from documentation.

## 5. Distinguishing @Hidden, @Parameter(hidden), and @Schema(hidden)

These three annotations apply at different levels:

| Annotation | Target hidden | Does the operation remain? |
|---|---|---|
| @Hidden on controller | Entire controller from documentation | No |
| @Hidden on method | Method/operation from documentation | No |
| @Operation(hidden = true) | Operation | No |
| @Parameter(hidden = true) | One parameter | Yes |
| @Schema(hidden = true) | Schema, field, or property where applied | Usually yes |

Example hiding an internal parameter:

~~~java
@GetMapping("/{id}")
public OrderResponse getOrder(
        @PathVariable UUID id,
        @Parameter(hidden = true) @AuthenticationPrincipal UserPrincipal principal) {
    return orderService.getForUser(id, principal);
}
~~~

The operation remains in OpenAPI; only the `principal` parameter is not documented as client-supplied input.

Example hiding a schema property:

~~~java
public class OrderResponse {

    private UUID id;

    @Schema(hidden = true)
    private String internalRiskScore;
}
~~~

If a developer mistakenly applies `@Parameter(hidden = true)` or `@Schema(hidden = true)` intending to hide the entire endpoint, the operation can still appear. Verify the exact annotation target before changing code.

## 6. @Hidden on RestControllerAdvice

Springdoc also supports `@Hidden` on `RestControllerAdvice`. This is useful when an advice only handles internal errors and should not appear as part of the API documentation.

~~~java
@Hidden
@RestControllerAdvice
public class InternalExceptionAdvice {

    @ExceptionHandler(InternalWorkflowException.class)
    ResponseEntity<InternalError> handle(InternalWorkflowException ex) {
        return ResponseEntity.internalServerError()
            .body(new InternalError("INTERNAL_WORKFLOW_ERROR"));
    }
}
~~~

Springdoc also inspects `@Hidden` on exception handler methods when building generic error responses from `ControllerAdvice`. Thus, an operation may remain while generic error responses change if an advice or exception handler is hidden.

Do not place `@Hidden` on a shared advice if its error responses need to be documented in public documentation. Split advice classes by scope or configure responses appropriately.

## 7. Checking for the Right Annotation Import

A codebase may contain multiple annotations with the same name or custom organizational annotations. Swagger's hidden annotation is:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
~~~

The `Operation` annotation is:

~~~java
import io.swagger.v3.oas.annotations.Operation;
~~~

If an internal annotation is also named `Hidden`, check the actual import on the class or method. An accidentally imported wrong annotation can prevent Springdoc from processing it as expected.

When debugging, inspect the compiled source or bytecode of the running class, especially when the application has multiple modules and dependencies containing identical class names.

## 8. Does @Hidden Stop the Endpoint from Working?

No. `@Hidden` is metadata for annotation scanning and documentation generation. Spring MVC or WebFlux can still register the mapping and invoke the method.

You can verify this with two requests:

~~~bash
curl -i http://localhost:8080/internal/reports
curl -s http://localhost:8080/v3/api-docs
~~~

If the first request returns a response while the second JSON omits `/internal/reports`, the route still exists and has only been hidden from documentation.

This is intentional in many applications. However, do not use the absence of a path in OpenAPI as proof that an endpoint is unreachable.

## 9. Annotations on Interfaces Are Supported by Springdoc

The Springdoc FAQ confirms that the library supports reading annotations from interfaces. Thus, an API contract can declare mappings and OpenAPI metadata on an interface while the implementation class provides the logic:

~~~java
@RequestMapping("/orders")
public interface OrderApi {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Look up order"
    )
    OrderResponse getOrder(@PathVariable UUID id);
}
~~~

Implementation class:

~~~java
@RestController
public class OrderController implements OrderApi {

    @Override
    public OrderResponse getOrder(UUID id) {
        return orderService.getById(id);
    }
}
~~~

Springdoc can read API annotations from interfaces. However, distinguish Springdoc reading metadata from Spring MVC actually registering the handler. An annotation may be visible during OpenAPI generation while runtime mapping still depends on Spring Framework's controller detection rules and how proxies are created.

## 10. Interface Method and Interface Type-Level Mappings

There are two common positions for mappings on interfaces:

- Method-level mappings such as `@GetMapping("/{id}")`.
- Type-level mappings such as `@RequestMapping("/orders")`.

In some configurations, method-level mappings are resolved while type-level mappings are not applied as expected. This deserves special attention when the controller is wrapped in a JDK interface proxy.

Spring Framework 6.0 changed controller detection: for interface proxies, Spring MVC no longer detects a controller solely based on a type-level `@RequestMapping` on the interface. Spring Framework documentation recommends using class-based proxies or placing `@Controller` on the interface in that case.

To reduce ambiguity, you can place `@RestController` and the base path on the implementation class, while the interface holds the method contract and metadata:

~~~java
public interface OrderApi {

    @GetMapping("/{id}")
    @Operation(
        operationId = "getOrderById",
        summary = "Look up order"
    )
    OrderResponse getOrder(@PathVariable UUID id);
}

@RestController
@RequestMapping("/orders")
public class OrderController implements OrderApi {

    @Override
    public OrderResponse getOrder(UUID id) {
        return orderService.getById(id);
    }
}
~~~

After making changes, check both handler mappings and OpenAPI. Do not look only at the document to conclude that Spring MVC registered the right route.

## 11. Annotations on Superclasses and Inherited Methods

A controller may inherit methods from a parent class:

~~~java
public abstract class BaseReadController<T> {

    @GetMapping("/{id}")
    public abstract T getById(@PathVariable UUID id);
}

@RestController
@RequestMapping("/customers")
public class CustomerController extends BaseReadController<CustomerResponse> {

    @Override
    public CustomerResponse getById(UUID id) {
        return customerService.getById(id);
    }
}
~~~

Spring and Springdoc must resolve the concrete method, generic types, and annotations along the hierarchy. When an operation disappears or a schema unexpectedly becomes `Object`, check whether the overridden method preserves the required mappings and metadata.

Java does not automatically inherit all annotations. `@Inherited` only applies to class-level annotations read through a superclass; it does not make annotations on interfaces or methods automatically inherited. Swagger's `@Hidden` targets `TYPE`, `METHOD`, `FIELD`, and `ANNOTATION_TYPE`, and does not carry the `@Inherited` meta-annotation.

Therefore, do not assume `@Hidden` placed on a superclass automatically applies to every subclass, or that `@Hidden` on an interface method is always carried over to the implementation method in every configuration. If you want to hide a specific endpoint, placing the annotation directly on the implementation controller's method is the clearest approach. Then inspect the output on the exact Springdoc version.

## 12. Annotations on Interfaces and Implementations Can Differ

Example interface describing an operation:

~~~java
public interface AdminApi {

    @GetMapping("/audit")
    @Operation(operationId = "getAudit")
    List<AuditEntry> getAudit();
}
~~~

The implementation may add an annotation:

~~~java
@RestController
@RequestMapping("/admin")
public class AdminController implements AdminApi {

    @Override
    @Hidden
    public List<AuditEntry> getAudit() {
        return auditService.findRecent();
    }
}
~~~

If the operation still appears, check how your Springdoc version merges annotations between interfaces and implementations. You may need to place the hiding metadata where Springdoc actually reads it in the current controller structure, or use `OperationCustomizer` to explicitly exclude operations by path/method.

A useful rule is to keep contract metadata in one consistent place and avoid scattering `@Operation`, `@Hidden`, and mappings across multiple layers unintentionally.

## 13. Is the Controller Managed by Spring?

Springdoc generates documentation from Spring-managed endpoints. If a class is merely a plain Java object and not registered as a controller bean, Springdoc has no standard handler mapping to describe.

Example of a detected controller:

~~~java
@RestController
@RequestMapping("/products")
public class ProductController {

    @GetMapping
    public List<ProductResponse> list() {
        return productService.findAll();
    }
}
~~~

Check:

- Does the class have `@RestController` or an appropriate `@Controller`?
- Is the package within component scan scope?
- Is the bean excluded by `@Profile` or `@Conditional` in the current profile?
- Is the module containing the controller on the runtime classpath?
- Are there `excludeFilters` configured in component scanning?
- Did the bean initialize successfully?

If the bean is not created, adding `@Operation` or `@Hidden` will not resolve the root cause.

## 14. @Controller Without @ResponseBody

The Springdoc FAQ clearly states that a `@Controller` without `@ResponseBody` is normally not treated as a REST endpoint to include in documentation. This is the default behavior because methods may return view names rather than a response body.

Example MVC view controller:

~~~java
@Controller
@RequestMapping("/reports")
public class ReportPageController {

    @GetMapping
    public String index(Model model) {
        return "reports/index";
    }
}
~~~

If the method actually returns JSON, use `@RestController` or combine `@Controller` and `@ResponseBody`:

~~~java
@Controller
@RequestMapping("/api/reports")
public class ReportApiController {

    @ResponseBody
    @GetMapping
    public List<ReportResponse> list() {
        return reportService.findAll();
    }
}
~~~

For legacy applications where annotations cannot be changed, `SpringDocUtils` can register additional classes as REST controllers:

~~~java
static {
    SpringDocUtils.getConfig()
        .addRestControllers(LegacyReportController.class);
}
~~~

Only use this approach for classes that actually serve REST responses. Do not force view-returning `@Controller` classes into OpenAPI.

## 15. Incorrect Component Scan Package

A common mistake is placing the application class in a package that is not a parent of the controller package.

Example layout:

~~~text
com.acme.application.Application
com.acme.web.order.OrderController
~~~

If component scanning only covers `com.acme.application`, the controller in `com.acme.web.order` may not be discovered.

You can set the scan base package intentionally:

~~~java
@SpringBootApplication(scanBasePackages = "com.acme")
public class Application {
}
~~~

Do not widen component scanning to a broad root package if doing so instantiates unintended beans. Pick a narrow package and verify the actual beans in `ApplicationContext`.

## 16. Checking the Web Stack and Framework in Use

Springdoc focuses on REST endpoints managed by Spring. If the application uses Jersey/JAX-RS with `@Path` and `@GET`, Springdoc does not automatically describe those resources as Spring MVC controllers.

Distinguish:

| Web API style | Common annotations/mappings |
|---|---|
| Spring MVC | @RestController, @RequestMapping, @GetMapping |
| Spring WebFlux annotated controller | @RestController, @RequestMapping, @GetMapping |
| JAX-RS/Jersey | @Path, @GET, @POST |
| Spring functional route | RouterFunction, route DSL |

For functional routes, appropriate configuration and supporting modules are required; do not assume a `RouterFunction` will be processed like a `@GetMapping` method. If the application combines multiple web frameworks, determine which handler mapping serves the missing URL.

## 17. @RequestMapping on Class and Method

Spring MVC combines type-level and method-level mappings:

~~~java
@RestController
@RequestMapping("/api/orders")
public class OrderController {

    @GetMapping("/{id}")
    public OrderResponse get(@PathVariable UUID id) {
        return orderService.getById(id);
    }

    @PostMapping
    public OrderResponse create(@RequestBody CreateOrderRequest request) {
        return orderService.create(request);
    }
}
~~~

The final mapping is built from the class path and method path. In the example:

| Method mapping | Final path |
|---|---|
| GET /{id} | GET /api/orders/{id} |
| POST | POST /api/orders |

When searching for an operation, check both class-level and method-level mappings. A path prefix moved to another class or changed via a placeholder can make the actual URL differ from the path the developer is looking for in JSON.

## 18. Do Not Place Multiple Mapping Annotations on the Same Element

Spring Framework warns against placing multiple `@RequestMapping` or composed mapping annotations on the same class or method. If multiple mapping annotations exist on the same element, Spring logs a warning and uses only the first detected annotation.

Example to avoid:

~~~java
@GetMapping("/orders")
@PostMapping("/orders")
public Object orders() {
    return null;
}
~~~

Split into separate methods:

~~~java
@GetMapping("/orders")
public List<OrderResponse> list() {
    return orderService.findAll();
}

@PostMapping("/orders")
public OrderResponse create(@RequestBody CreateOrderRequest request) {
    return orderService.create(request);
}
~~~

If a custom composed annotation is needed, create a single annotation meta-annotated with `@RequestMapping` specifying a clear HTTP method/path. Do not combine `@GetMapping` and `@PostMapping` on the same method expecting Spring to create two operations.

## 19. Conditional Mappings

A handler may only be registered or match requests when conditions are satisfied:

- `method`: GET, POST, PUT, DELETE...
- `params`: a query parameter must be present or equal a specific value.
- `headers`: a header must be present or equal a defined value.
- `consumes`: request Content-Type.
- `produces`: Accept or response media type.
- `version`: API version if supported by framework/configuration.

For example:

~~~java
@GetMapping(
    value = "/reports",
    params = "format=summary",
    produces = MediaType.APPLICATION_JSON_VALUE
)
public ReportSummary summary() {
    return reportService.summary();
}
~~~

If you are looking for operation `GET /reports` while the method only maps when `params` has `format=summary`, check that condition. The operation may be represented in OpenAPI with the corresponding parameter; if metadata is missing or custom mappings are overly complex, the document might not fully reflect runtime conditions.

## 20. Duplicate or Ambiguous Mappings

Two methods with overlapping mappings can prevent Spring from registering handlers as expected or trigger an ambiguous mapping error at startup. Read startup logs, especially messages related to `RequestMappingHandlerMapping`.

For example:

~~~java
@GetMapping("/{id}")
public OrderResponse find(@PathVariable String id) { ... }

@GetMapping("/{code}")
public OrderResponse findByCode(@PathVariable String code) { ... }
~~~

Two patterns with the same structure and HTTP conditions can conflict. Change one path clearly, such as `/by-code/{code}`, or use meaningful mapping conditions.

If the application fails to start due to ambiguous mappings, OpenAPI generation cannot fix this error. Resolve the handler conflict first.

## 21. Placeholders and URL Prefixes

Example of class-level mapping setting a base path directly:

~~~java
@RequestMapping("/api/orders")
public class OrderController {
}
~~~

The actual value can still be affected by property sources, profiles, and servlet configuration. If OpenAPI contains path `/v2/orders` while you are looking for `/api/orders`, inspect the resolved configuration.

Additionally, the following factors can make the access URL differ from the path in OpenAPI:

- `server.servlet.context-path`.
- `spring.mvc.servlet.path`.
- Reverse proxy prefix.
- Forwarded headers.
- API versioning strategy.

Do not mechanically add the context path into every annotation. Distinguish the path segment belonging to the controller mapping from the part supplied by the servlet or proxy.

## 22. Springdoc Package and Path Filters

Even when the controller is properly registered, Springdoc can exclude it from the document via include/exclude settings.

For example:

~~~yaml
springdoc:
  packages-to-scan:
    - com.acme.api.public
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
~~~

If the controller lives in `com.acme.api.admin` or the path starts with `/internal`, it may not appear under this configuration.

The Springdoc FAQ also describes package and path selection settings to filter endpoints. Check the exact property binding for the version in use; property names in documentation and older configs may differ in spelling.

If global filtering is unnecessary, remove unneeded filters and re-test. Do not open up all packages just to make one operation appear if that accidentally publishes internal endpoints.

## 23. GroupedOpenApi Can Exclude an Operation from One Document

An application can generate multiple OpenAPI documents:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .packagesToScan("com.acme.api.public")
        .pathsToMatch("/api/**")
        .build();
}
~~~

The group document has a default URL:

~~~text
/v3/api-docs/public
~~~

If an operation only belongs to an internal group, it will not be in the public document. This is not a system-wide missing-operation bug.

Check:

1. Default `/v3/api-docs`.
2. `/v3/api-docs/{groupName}` for each group.
3. `packagesToScan`.
4. `pathsToMatch` and `pathsToExclude`.
5. `OpenApiCustomizer` attached specifically to the group.

Do not inspect only the group selected in Swagger UI and conclude Springdoc failed to generate the operation.

## 24. Customizers Can Remove Paths or Operations After Scanning

Springdoc allows customizing the OpenAPI document after controller scanning. If an `OpenApiCustomizer` or `OperationCustomizer` deletes a path, method, or operation, the handler mapping may still exist while the final result no longer contains the operation.

Example customizer removing an internal path:

~~~java
@Bean
OpenApiCustomizer removeInternalPaths() {
    return openApi -> {
        if (openApi.getPaths() != null) {
            openApi.getPaths().remove("/api/internal/diagnostics");
        }
    };
}
~~~

When debugging, search for all beans of type:

- `OpenApiCustomizer`.
- `GlobalOpenApiCustomizer`.
- `OperationCustomizer`.
- `GroupedOpenApi.addOpenApiCustomizer`.
- `GroupedOpenApi.addOperationCustomizer`.

Check execution order and conditions of each customizer. A customizer applied to a group may remove the operation only from that group, while the default document keeps it.

If a customizer deletes operations based on path strings, check the path after placeholders and mapping prefixes are resolved. A trailing slash mismatch or version prefix difference can cause the filter rule to match unintentionally.

## 25. Disabled API Docs Is Not the Same as Disabled Swagger UI

Two different control properties exist:

~~~yaml
springdoc:
  api-docs:
    enabled: true
  swagger-ui:
    enabled: true
~~~

`springdoc.api-docs.enabled=false` disables the OpenAPI endpoint. `springdoc.swagger-ui.enabled=false` only disables the Swagger UI; OpenAPI JSON/YAML can still be served if `api-docs` remains enabled.

If the entire document endpoint is unreachable, check `api-docs` properties. If only the Swagger UI page fails to open, check UI dependencies and `swagger-ui` properties.

Do not use `swagger-ui.enabled=false` to troubleshoot a specific operation missing from JSON. It is not an operation filter.

## 26. Checking Handler Mappings with Actuator

Spring Boot Actuator has a `mappings` endpoint to view registered handlers. In a development or test environment, you can expose the endpoint:

~~~yaml
management:
  endpoints:
    web:
      exposure:
        include: health,mappings
~~~

Then inspect:

~~~bash
curl -s http://localhost:8080/actuator/mappings
~~~

Look for the path and controller method under investigation. The `mappings` endpoint shows which handlers Spring registered; the OpenAPI document shows which operations Springdoc included in the documentation.

Diagnose by result:

| In /actuator/mappings | In OpenAPI | Investigation direction |
|---|---|---|
| Yes | Yes | Operation was recognized |
| Yes | No | @Hidden, group/filter, customizer, or metadata |
| No | No | Controller bean, mapping, proxy, profile, or web stack |
| No | Yes | Check whether document comes from a different runtime/instance or a customizer manually adds the path |

Do not expose `/actuator/mappings` publicly unless necessary. Mappings can disclose controller names, internal paths, and application structure. Protect the endpoint with Spring Security or enable it only in test profiles.

## 27. Inspecting OpenAPI JSON Directly

Do not rely solely on Swagger UI. Call the documentation endpoint:

~~~bash
curl --fail --silent --show-error \
  http://localhost:8080/v3/api-docs \
  -o target/openapi.json
~~~

List paths:

~~~bash
jq -r '.paths | keys[]' target/openapi.json
~~~

Inspect a specific operation:

~~~bash
jq '.paths["/api/orders/{id}"]' target/openapi.json
~~~

If the path exists but a method is missing, inspect the path object and methods `get`, `post`, `put`, `patch`, `delete`. If the path is absent, check filters or `@Hidden`.

If using groups, call the exact group URL and save a separate file:

~~~bash
curl --fail --silent \
  http://localhost:8080/v3/api-docs/public \
  -o target/openapi-public.json
~~~

The document must come from the exact instance, profile, and version under investigation. Avoid comparing a previously exported file against a running application without checking timestamps or commit hashes.

## 28. Checking Annotations at Runtime

If source code has `@Hidden` yet the operation still appears, check the class actually loaded:

- Verify the bean's package and class name in `ApplicationContext`.
- Check the import of `@Hidden`.
- Check whether the annotation is on the concrete controller or on an interface/superclass.
- Check whether the implementation method overrides the method declaring the mapping.
- Check multiple modules for classes with the same name.
- Check whether build output is updated or the application is running an old artifact.

You can use reflection in a test to verify the annotation:

~~~java
Method method = OrderController.class
    .getDeclaredMethod("purgeOrder", UUID.class);

assertThat(method.isAnnotationPresent(Hidden.class)).isTrue();
~~~

This test only confirms the annotation sits directly on the method. It does not prove Springdoc applied the annotation during document generation. You still must inspect the OpenAPI output.

If the annotation comes from an interface or meta-annotation, inspect the hierarchy and merged annotations using Spring `AnnotationUtils` or `MergedAnnotations` appropriate for your Spring version. Do not rely on `getDeclaredAnnotation` on the implementation to conclude the annotation is absent from the interface.

## 29. Writing Regression Integration Tests

When fixing the issue, include a test verifying that the operation intentionally appears or disappears.

Example OpenAPI JSON test:

~~~java
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class OpenApiVisibilityTest {

    @Autowired
    TestRestTemplate restTemplate;

    @Test
    void publicOperationIsDocumented() {
        ResponseEntity<String> response =
            restTemplate.getForEntity("/v3/api-docs", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        assertThat(response.getBody())
            .contains("/api/orders/{id}")
            .contains("get");
    }

    @Test
    void hiddenOperationIsNotDocumented() {
        ResponseEntity<String> response =
            restTemplate.getForEntity("/v3/api-docs", String.class);

        assertThat(response.getBody())
            .doesNotContain("/api/internal/diagnostics");
    }
}
~~~

The example above illustrates the approach; parse JSON with Jackson and check `paths`/method structure rather than relying on substrings in large suites. If the application has multiple groups, test each group individually.

For operations that are hidden yet whose routes must keep working, write an additional HTTP test:

~~~java
@Test
void hiddenEndpointStillHasItsRuntimePolicy() {
    ResponseEntity<String> response =
        restTemplate.getForEntity("/api/internal/diagnostics", String.class);

    assertThat(response.getStatusCode())
        .isIn(HttpStatus.OK, HttpStatus.UNAUTHORIZED, HttpStatus.FORBIDDEN);
}
~~~

Replace the expected statuses with your application's actual policy. The goal is to prove that hiding documentation did not inadvertently change runtime behavior.

## 30. Ordered Diagnostic Procedure

When an operation goes missing, follow this sequence:

1. Record the URL, HTTP method, profile, and instance under investigation.
2. Call the REST endpoint directly to see whether the route still works.
3. Check `/actuator/mappings` in a protected environment.
4. Call `/v3/api-docs` instead of looking only at Swagger UI.
5. If using groups, call `/v3/api-docs/{groupName}` directly.
6. Search for `@Hidden` on controllers, superclasses, interfaces, methods, and advice.
7. Search for `@Operation(hidden = true)` on methods.
8. Distinguish `@Parameter(hidden = true)` and `@Schema(hidden = true)`.
9. Check whether `@Controller` has `@ResponseBody` or switch to `@RestController`.
10. Check component scanning, `@Profile`, and `@Conditional`.
11. Check interface mappings, proxy types, and Spring Framework version.
12. Check class-level and method-level `@RequestMapping`.
13. Look for multiple mapping annotations on the same element and ambiguous mappings.
14. Check `packages-to-scan`, `paths-to-match`, and `paths-to-exclude`.
15. Check whether customizers remove paths or operations.
16. Check API version, context path, and property placeholders.
17. Restart or refresh the exact instance after configuration changes.
18. Add integration tests for expected behavior.

Do not change multiple layers at once. Change only one evidenced cause at a time, then inspect handler mappings and OpenAPI output to confirm.

## 31. Causes and Fixes Table

| Cause | Symptom | How to fix |
|---|---|---|
| @Hidden on controller | All controller methods disappear | Remove annotation if controller should be published |
| @Hidden on method | Only one operation disappears | Remove or move annotation to the method actually needing hiding |
| @Operation(hidden = true) | Operation absent even though mapping works | Change hidden=false or remove hiding metadata |
| Confused with @Parameter(hidden) | Parameter disappears while operation remains | Check the exact hiding target |
| Confused with @Schema(hidden) | Property/schema disappears | Place annotation on the proper schema or remove hidden |
| Annotation on interface | Result differs between interface and implementation | Check merged annotations; place metadata clearly on concrete method |
| Type-level mapping on interface with JDK proxy | Controller not detected by Spring MVC | Place mapping on implementation or use class-based proxy as needed |
| @Controller missing @ResponseBody | Method returns view and stays out of REST docs | Use @RestController or @ResponseBody |
| Controller outside component scan | No bean and no mapping | Fix scan base package |
| Profile/conditional excludes bean | Missing in only one environment | Check active profile and bean conditions |
| Multiple mapping annotations on same method | Spring warning and only first mapping used | Split methods or create a proper composed annotation |
| Duplicate mapping | Startup error or ambiguous handler | Make mappings unique |
| Package/path filter | Only certain paths excluded | Fix packages-to-scan or paths-to-match/exclude |
| Wrong document group | Present in another group but absent in current group | Check GroupedOpenApi |
| Customizer deletes operation | Handler exists but OpenAPI omits it | Fix OpenApiCustomizer/OperationCustomizer rules |
| Inspecting stale artifact | JSON unchanged despite edited source | Verify process, profile, build, and timestamp |

## 32. Key Takeaways

- `@Hidden` on a controller hides the entire controller from documentation; on a method it hides that operation.
- `@Operation(hidden = true)` is the direct choice for hiding one operation.
- `@Parameter(hidden = true)` only hides a parameter; `@Schema(hidden = true)` affects schemas/properties.
- `@Hidden` does not disable routes and does not replace Spring Security.
- Springdoc supports annotations from interfaces, yet Spring MVC handler registration still follows Spring Framework mapping and proxy rules.
- Since Spring Framework 6.0, JDK interface proxies are no longer detected solely from type-level `@RequestMapping` on an interface.
- Java does not automatically inherit annotations from interfaces or methods; place annotations directly when deterministic behavior is needed.
- Controllers must be Spring-managed beans; `@Controller` without `@ResponseBody` is typically not treated as a REST endpoint.
- Do not place multiple `@RequestMapping`/composed mappings on the same element.
- `GroupedOpenApi`, package/path filters, and customizers can exclude operations from a document.
- Compare `/actuator/mappings` with `/v3/api-docs` to separate mapping errors from documentation errors.
- Check each document group and the exact runtime instance.
- Add integration tests verifying both OpenAPI visibility and runtime behavior.

When an operation disappears, verify the route in handler mappings first, then inspect the OpenAPI document and specific group. `@Hidden` or customizers may only hide documentation while the endpoint keeps running; conversely, incorrect interface mappings, component scanning, or mapping annotations can prevent Spring from registering the handler altogether. Distinguishing these two cases lets you fix the true cause while preserving the intended API behavior.

## References

- Springdoc OpenAPI FAQ – Hide an operation or controller: https://springdoc.org/faq.html
- Springdoc OpenAPI FAQ – Interface annotations and controller detection: https://springdoc.org/faq.html
- Swagger Core – Hidden annotation API: https://docs.swagger.io/swagger-core/v2.2.40/apidocs/io/swagger/v3/oas/annotations/Hidden.html
- Spring Framework – Mapping Requests: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-requestmapping.html
- Spring Framework – Controller Declaration and AOP Proxies: https://docs.spring.io/spring/reference/web/webmvc/mvc-controller/ann.html
