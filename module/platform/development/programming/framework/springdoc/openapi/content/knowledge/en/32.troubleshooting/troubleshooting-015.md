# Narrowing Down Bugs Using the JSON Spec, Mappings, and Relevant Logs

When Swagger UI is missing an endpoint, OpenAPI JSON has an inaccurate schema, or an operation behaves differently from what documentation describes, locate the exact layer causing the discrepancy before changing code. springdoc-openapi gathers information from the Spring application context, handler mappings, annotations, request/response types, and serialization settings. Thus, bugs can stem from routes not registered by Spring, springdoc filters, controller metadata, Jackson, validation, customizers, or incompatible dependencies.

An effective procedure starts by recording the symptom and actual request, then comparing three sources of evidence: the generated OpenAPI JSON, the handler mappings Spring is running, and logs at reproduction time. Whenever these three disagree, each difference narrows the search area. Avoid guessing with extra annotations or widening component scanning before knowing at which step the operation disappeared.

This lesson walks through layered diagnosis: confirming the docs endpoint, reading OpenAPI JSON, inspecting Spring mappings, checking package/path filters, analyzing parameters and schemas, cross-checking Jackson/validation, reading logs, checking dependencies, and reproducing with tests. Examples assume Spring Boot with springdoc-openapi; property names and APIs can differ across major versions, so verify against documentation for your exact version.

## 1. Identifying the Exact Symptom Before Fixing

A vague report such as "Swagger is broken" is not enough to find the cause. Classify the observed symptom:

| Symptom | First question |
|---|---|
| Cannot open Swagger UI | What status does the UI page return? Are JavaScript or document requests failing? |
| `/v3/api-docs` returns 404 | Did the docs endpoint change path, context path, or get blocked by security? |
| `/v3/api-docs` returns 500 | What is the first exception in server logs? |
| Missing an operation | Did Spring register that handler? Did filters or annotations exclude it? |
| Operation exists yet lacks parameter | Were the method mapping and parameter annotations read properly? |
| Schema lacks a field | Does Jackson serialize that field? Do schema annotations or mixins affect it? |
| Wrong required/format | Do Bean Validation annotations match the OpenAPI version? |
| Docs are right yet API runs wrongly | Does runtime request/response differ from contract? |
| Only one group fails | Do that group's customizers or filters differ from the default document? |

Collect at minimum:
- Exact HTTP method and full URL called.
- Status code, response headers, and error body with sensitive data scrubbed.
- Document name: default or specific group.
- Active Spring profile, port, context path, and environment.
- Reproduction timestamp and correlation/request ID if available.
- Java, Spring Boot, and springdoc versions in use.
- One concrete example operation, including path, method, and related DTOs.

Record a repeatable reproduction. If the bug only appears in production or behind a proxy, keep both the public URL and corresponding backend URL to inspect context paths, forwarded headers, and routing.

## 2. Understanding the OpenAPI Generation Flow to Isolate Layers

springdoc does not auto-discover every class in source code. It works with handlers already registered by Spring, then analyzes metadata and related models to build the document.

Overall flow:

~~~mermaid
flowchart TD
    A[Spring Boot starts] --> B[Component scanning and bean creation]
    B --> C[Spring MVC or WebFlux handler mappings]
    C --> D[springdoc selects eligible handlers]
    D --> E[Operation and parameter analysis]
    E --> F[Request and response schema resolution]
    F --> G[OpenAPI customizers and extensions]
    G --> H[OpenAPI JSON or YAML]
    H --> I[Swagger UI loads the document]
~~~

Causes can be grouped into layers:

1. **Application context:** was the controller instantiated as a bean?
2. **Handler mapping:** did Spring register the route and HTTP method?
3. **springdoc selection:** did package/path filters or annotations exclude the operation?
4. **Metadata:** are operation, parameters, responses, and security fully described?
5. **Schema resolution:** how do Jackson, validation, and data types construct schemas?
6. **Customization:** did a customizer alter or break the document?
7. **Delivery:** are JSON/YAML endpoints and Swagger UI served at the right URLs?

Knowing which layer drops an operation shrinks the investigation area significantly. For example, if handler mappings lack the route, editing `@Operation` will never make the route appear.

## 3. Confirming the Right Docs Endpoint and Environment

By default springdoc serves OpenAPI JSON at `/v3/api-docs` and YAML at `/v3/api-docs.yaml`. Swagger UI is typically accessible via `/swagger-ui.html` or the UI path matching your configuration/version.

Call the JSON endpoint directly before investigating the UI:

~~~bash
curl -i http://localhost:8080/v3/api-docs
~~~

Save the response for analysis:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

If the application has a context path, such as `/catalog`, the URL may be:

~~~text
http://localhost:8080/catalog/v3/api-docs
~~~

If `springdoc.api-docs.path` was changed, use that actual path. Do not conclude springdoc is broken just because calling the default endpoint fails when the project customized the path.

Check these points:
- Calling the right host, port, and application instance.
- Current profile enables docs-generating dependencies/configurations.
- Context path or servlet path is included in the URL.
- Reverse proxy rewrites prefixes or not.
- Security filters require authentication for docs endpoints or not.
- Multiple services are running and you might be hitting the wrong instance.

If the JSON endpoint works yet UI fails to load, move to checking Swagger UI configuration and proxies. If both JSON and YAML fail, prioritize checking server logs and document generation.

## 4. Reading OpenAPI JSON with `jq`

OpenAPI JSON is direct evidence of what springdoc generated. First confirm the document has the basic structure:

~~~bash
jq '{openapi, info, serverCount: (.servers // [] | length), pathCount: (.paths // {} | length)}' openapi.json
~~~

List paths:

~~~bash
jq -r '.paths | keys[]' openapi.json
~~~

List paths and HTTP methods:

~~~bash
jq -r '
  .paths
  | to_entries[]
  | .key as $path
  | .value
  | to_entries[]
  | select(
      .key == "get" or .key == "post" or .key == "put" or
      .key == "patch" or .key == "delete" or .key == "options" or
      .key == "head" or .key == "trace"
    )
  | "\(.key | ascii_upcase) \($path)"
' openapi.json
~~~

Inspect a specific operation:

~~~bash
jq '.paths["/api/orders/{id}"].get' openapi.json
~~~

Inspect a schema component:

~~~bash
jq '.components.schemas.OrderResponse' openapi.json
~~~

Inspect security schemes:

~~~bash
jq '.components.securitySchemes' openapi.json
~~~

If `jq` reports a parse error, the fetched response may be an HTML error page, login page, or non-JSON content. Check status/headers and the first few lines of the file before concluding the document is corrupt.

Do not rely solely on path count to confirm a complete document. One path can hold multiple operations, and one operation can reference multiple schemas. Inspect the path, method, parameters, `requestBody`, `responses`, and `components` of the endpoint under investigation.

## 5. Comparing OpenAPI JSON Against Spring Handler Mappings

This step separates Spring issues from springdoc issues.

If Spring Boot Actuator is present and the `mappings` endpoint is exposed in a diagnostic environment, inspect:

~~~bash
curl -fsS http://localhost:8080/actuator/mappings -o mappings.json
~~~

Search for the path or controller name in the output:

~~~bash
jq '.. | objects | select(tostring | contains("/api/orders"))' mappings.json
~~~

Actuator's output structure may vary by Spring Boot version. If the `jq` filter misses, open the JSON file and search for the path string or handler name directly.

Interpret results using this table:

| Actuator mappings | OpenAPI JSON | Investigation direction |
|---|---|---|
| Route absent | Operation absent | Spring did not register the handler; check bean, profile, conditions, and mapping |
| Route present | Operation absent | Check springdoc filters, `@Hidden`, groups, and customizers |
| Route present | Operation present with wrong metadata | Check annotations, parameter resolution, and schema resolution |
| Route and operation present | Runtime returns error | Check security, validation, services, and business logic |
| No Actuator available | No mapping evidence | Use startup logs, integration tests, or a debugger to confirm the handler |

Actuator mappings are useful runtime evidence, yet this endpoint can reveal internal application structure. Only expose it in local/test environments or protect it under strict security policies. Do not broaden public Actuator access just for convenience.

## 6. If the Route Is Missing from Spring Mappings

When a route does not appear in `/actuator/mappings`, investigate from the application context.

### 6.1. Was the Controller Created as a Bean?

Check:
- Does the class have `@RestController` or an appropriate `@Controller`?
- Is the controller's package inside component scan scope?
- Was the class excluded by profile, conditional property, or test configuration?
- Did a dependency initialization error prevent the bean from being created?
- Is the controller restricted by `@Profile` or `@ConditionalOnProperty`?

Example controller existing only in the `dev` profile:

~~~java
@Profile("dev")
@RestController
@RequestMapping("/api/orders")
class OrderController {
    // ...
}
~~~

When running the `production` profile, the controller will not be registered. That is an application configuration difference, not an OpenAPI generation bug.

### 6.2. Checking Request Mappings

For example:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse getById(@PathVariable String id) {
        return service.findById(id);
    }
}
~~~

The final path is `/api/orders/{id}`. When checking mappings, account for:
- Class-level `@RequestMapping`.
- Method-level `@GetMapping`, `@PostMapping`, or `@RequestMapping`.
- HTTP method.
- `consumes` and `produces`.
- Servlet context path or WebFlux base path.
- Additional mapping conditions such as `params`/`headers`.

A controller may be registered while the method mapping does not match the request you are calling. Do not merely search for the class name in logs.

### 6.3. Checking Functional Routes

For WebFlux functional endpoints or router functions, routes are not declared via standard controller annotations. Verify your springdoc version and functional-route support mechanism for your stack, and verify that the router function is actually created in the application context.

## 7. If Spring Has the Route Yet OpenAPI Lacks the Operation

When the route exists in Spring mappings yet JSON omits the operation, focus on filters and exclusion metadata.

### 7.1. Package and Path Filters

Check these properties:
- `springdoc.packages-to-scan`
- `springdoc.packages-to-exclude`
- `springdoc.paths-to-match`
- `springdoc.paths-to-exclude`

For example:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.catalog.api
  paths-to-match:
    - /api/**
  paths-to-exclude:
    - /api/internal/**
~~~

If the controller sits outside included packages or its path fails to match patterns, springdoc can skip the operation even while the endpoint keeps running.

Compare the controller's actual declared package against package filters. Compare the combined class-level and method-level path against patterns. After each change, reload OpenAPI JSON and check for the specific operation.

### 7.2. Hiding Annotations

Check:
- `@Hidden` on controller or method.
- `@Operation(hidden = true)` on operation.
- Shared project annotations/meta-annotations.
- Customizers deleting operations or paths from the document.

Hiding an operation affects only documentation. The endpoint remains active and must be protected via Spring Security or runtime policies.

### 7.3. `GroupedOpenApi`

An operation may appear in the default document while missing from the group being viewed, or vice versa, depending on each group's filters.

For example:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .packagesToScan("com.example.catalog.partner")
        .pathsToMatch("/partner/**")
        .build();
}
~~~

Fetch the exact group endpoint, typically `/v3/api-docs/partner`, or the customized path. Do not compare the default document against the `partner` group and conclude the endpoint disappeared.

### 7.4. Customizers

Search for beans such as:
- `OpenApiCustomizer`.
- `GlobalOpenApiCustomizer`.
- Custom `OpenAPI` beans.
- Logic removing paths, operations, tags, or schemas.

Temporarily isolate customizers in a branch/test profile to see whether customization causes the discrepancy. Never delete production customizers just to "test" without understanding their purpose.

## 8. If the Operation Exists Yet Parameters Are Missing or Misplaced

Cross-check the controller signature against the OpenAPI operation:

| Spring annotation | Typical HTTP location |
|---|---|
| `@PathVariable` | `path` |
| `@RequestParam` | `query` |
| `@RequestHeader` | `header` |
| `@CookieValue` | `cookie` |
| `@RequestBody` | `requestBody` |
| `@ModelAttribute` | Fields bound from request parameters per Spring MVC processing |

For example:

~~~java
@GetMapping("/api/orders")
List<OrderResponse> search(
    @RequestParam(required = false) String status,
    @RequestHeader(name = "X-Tenant-Id") String tenantId
) {
    return service.search(status, tenantId);
}
~~~

OpenAPI should document `status` as a query parameter and `X-Tenant-Id` as a header parameter. If location or `required` is wrong, check:
- Is the annotation placed on the right parameter?
- Is there a parameter annotation from another library causing confusion?
- Are parameter names compiled with appropriate metadata?
- Does `@Parameter` or `@Parameters` override metadata?
- Does the method have overloads or complex mappings?

You can declare explicitly:

~~~java
@Parameter(
    name = "status",
    in = ParameterIn.QUERY,
    required = false,
    description = "Filter by status"
)
@RequestParam(required = false) String status
~~~

After editing, inspect `parameters` in JSON. Do not use annotations to mask a broken runtime signature; parameters must reflect requests Spring actually binds.

## 9. If `requestBody` or Response Schema Is Wrong

When the operation exists yet the model is wrong, examine the data types in the method signature first:

~~~java
@PostMapping("/api/orders")
ResponseEntity<OrderResponse> create(
    @Valid @RequestBody CreateOrderRequest request
) {
    // ...
}
~~~

Check these factors:
- Request body parameter type.
- Actual return type.
- Generic wrappers such as `ResponseEntity<T>`, `Page<T>`, or custom envelopes.
- DTOs, records, inheritance, and generic types.
- Jackson annotations and mixins.
- Schema annotations.
- Serialization modules registered in the application context.

Jackson example:

~~~java
public record OrderResponse(
    String id,
    @JsonProperty("order_status") String status,
    @JsonIgnore String internalNote
) {
}
~~~

OpenAPI schemas usually reflect JSON property names and serialization rules recognized by springdoc/Jackson. Thus, `status` may appear as `order_status`, while `internalNote` is omitted from serialization schemas.

If a field is missing:
1. Confirm the field actually appears in runtime JSON responses.
2. Check `@JsonIgnore`, `@JsonProperty`, visibility, and naming strategy.
3. Check getters/record components and Jackson mixins.
4. Check `@Schema(hidden = true)` or schema customizers.
5. Inspect the schema component in JSON and see where `$ref` is used.

If the field is in runtime JSON yet absent from the schema, the issue likely lies in introspection/annotations. If the field is also missing from runtime JSON, check the DTO and serializer before tweaking springdoc.

## 10. Analyzing `required`, `nullable`, and Validation

Bean Validation annotations can supply schema constraints, yet results depend on version, annotation placement, and data types.

For example:

~~~java
public record CreateOrderRequest(
    @NotBlank
    String customerId,

    @NotEmpty
    List<@Valid OrderLineRequest> items
) {
}
~~~

Check:
- Is the validation dependency present?
- Do annotation imports use `jakarta.validation` or `javax.validation` matching the Spring Boot line?
- Is the annotation placed on field, getter, record component, or type-use?
- Does the controller have `@Valid` or `@Validated` where needed?
- Are constraints enforced by the runtime validator?
- Do generated schemas contain appropriate `required`, `minLength`, `minItems`, or `format`?

Spring Boot 3 uses the Jakarta namespace for many APIs. When upgrading from Boot 2 to Boot 3, if source code still uses `javax.validation` annotations, dependencies may fail to behave as expected or clash with the new stack. Verify actual imports and dependencies.

Distinguish:
- `required` in OpenAPI describes fields that must be present in the payload.
- `nullable` describes whether a field can take `null` per the dialect.
- `@NotNull`/`@NotBlank`/`@NotEmpty` are runtime validation constraints.
- A `default` value in a schema does not automatically make the server assign that value.

If schema and runtime validation disagree, fix both contract and validation implementation, then add tests to prevent regressions.

## 11. Checking Response Codes and Error Schemas

An operation may have a default response inferred by springdoc from the return type, while actual status codes come from exception handlers or conditional response logic.

Check:
- `@ApiResponse` and `@ApiResponses`.
- `@ControllerAdvice` and `@ExceptionHandler`.
- `ResponseEntity` with dynamic statuses.
- Actual error responses.
- Media types and response headers.
- Default response codes and specific response codes.

Example documenting responses:

~~~java
@Operation(summary = "Get order details")
@ApiResponses({
    @ApiResponse(responseCode = "200", description = "Order found"),
    @ApiResponse(responseCode = "404", description = "Not found"),
    @ApiResponse(responseCode = "500", description = "System error")
})
@GetMapping("/api/orders/{id}")
OrderResponse getById(@PathVariable String id) {
    return service.findById(id);
}
~~~

Annotations only describe documentation. They do not automatically make the endpoint return 404 or 500 with that content. Use integration tests to confirm runtime status and body match OpenAPI.

If every operation receives the exact same error response, check global response configuration or customizers before editing individual controllers.

## 12. Reading Logs with a Clear Target

Logs need to answer specific questions. Enabling `DEBUG` across the entire application produces noise and buries critical exceptions.

Start with startup logs and the first exception:
- Which controller beans were created?
- Are there classpath errors or `NoClassDefFoundError`?
- Are there mapping conflicts or ambiguous mappings?
- Are there exceptions during schema resolution or OpenAPI serialization?
- Which customizers ran right before the error?
- Did requests to `/v3/api-docs` pass through security filters?

You can enable logging for the springdoc package in a diagnostic profile:

~~~yaml
logging:
  level:
    org.springdoc: DEBUG
~~~

If you need to inspect Spring MVC mappings, temporarily enable logging for the relevant package:

~~~yaml
logging:
  level:
    org.springframework.web.servlet.mvc.method.annotation.RequestMappingHandlerMapping: DEBUG
~~~

With WebFlux, logger packages and mapping details differ from MVC; use the logger matching your actual stack.

After collecting logs, turn off `DEBUG` when no longer needed. Never leave verbose logging enabled indefinitely in production if it creates high volume or writes sensitive metadata.

## 13. Using Actuator to Inspect Conditions and Loggers

If the application already includes Spring Boot Actuator, these endpoints can assist investigation:
- `/actuator/mappings`: handler mappings.
- `/actuator/conditions`: auto-configuration and bean conditions.
- `/actuator/beans`: bean list.
- `/actuator/loggers`: logger status and authorized level adjustments.

Example inspecting conditions:

~~~bash
curl -fsS http://localhost:8080/actuator/conditions -o conditions.json
~~~

Search for springdoc or web auto-configuration entries in the output. The condition report can be large; filter by keywords and inspect both positive and negative matches.

If Actuator endpoints are not exposed, do not open them in production solely for diagnostics. Use local/test profiles, startup logs, or test contexts to collect evidence.

Never expose `env`, `configprops`, `beans`, `mappings`, or `loggers` publicly without access control. These endpoints can disclose configurations, internal beans, routes, or allow changing logger levels.

## 14. Checking Dependencies and Compatibility Errors

OpenAPI generation failures sometimes originate in the dependency tree rather than controllers. Check especially when:
- Spring Boot or springdoc was just upgraded.
- Multiple `swagger-core`/`swagger-annotations` versions exist.
- Jackson was manually overridden.
- The project retains both modern starters and old springdoc artifacts.
- Both MVC and WebFlux starters were pulled in unintentionally.
- `NoSuchMethodError`, `ClassNotFoundException`, or `NoClassDefFoundError` occurs.

With Maven:

~~~bash
mvn dependency:tree -Dverbose -Dincludes=org.springdoc,io.swagger.core.v3,com.fasterxml.jackson.core
~~~

With Gradle:

~~~bash
./gradlew dependencyInsight --dependency springdoc --configuration runtimeClasspath
./gradlew dependencyInsight --dependency swagger-core --configuration runtimeClasspath
./gradlew dependencyInsight --dependency jackson-databind --configuration runtimeClasspath
~~~

Check:
- Which version the Spring Boot BOM manages.
- Whether the springdoc starter matches MVC or WebFlux.
- No duplicate legacy artifacts with overlapping functionality exist.
- Transitive dependencies are not excluded or overridden improperly.
- Compile classpath and runtime classpath show no unexpected divergence.

Do not add an arbitrary `swagger-core`/Jackson version to silence a compile error. Identify the springdoc and Spring Boot version compatibility first, then adjust dependency management intentionally in one place.

## 15. Checking Swagger UI When JSON Is Already Right

If `/v3/api-docs` returns valid JSON containing the expected operations yet the UI is blank or shows errors, investigate the delivery layer:

- Is the Swagger UI URL right after the context path?
- Can the UI load JavaScript/CSS?
- What status do network requests fetching the OpenAPI document return?
- Does the UI point to an old document URL in `springdoc.swagger-ui.url` or config URL?
- Does a proxy rewrite paths or schemes?
- Is there HTTPS termination while server URLs are generated as HTTP?
- Does CSP or security policy block UI assets?
- Does CORS interfere when UI and API docs sit on different origins?

Open Browser Developer Tools and inspect Network:
1. Request for the Swagger UI page.
2. JS/CSS assets.
3. Request to OpenAPI JSON.
4. Response status and content type.
5. First Console error.

If the UI uses a separately configured document URL, verify it points to the right group and context path. Do not edit controllers when OpenAPI JSON is already correct.

## 16. Checking Proxy, Forwarded Headers, and Server URLs

When running behind a reverse proxy or ingress, server URLs in the document may differ from public URLs. Compare:
- Public request URL visited by browsers/clients.
- Backend URL forwarded by the proxy.
- `Host`, `X-Forwarded-Host`, `X-Forwarded-Proto`, and forwarded prefixes.
- Application context path.
- springdoc properties related to server URLs or proxies.

If server URLs are wrong, check Spring Boot and proxy forwarded-header settings. Trust forwarded headers only from trusted proxies; never allow arbitrary client headers to alter generated host URLs.

To determine whether an issue lies in the proxy or application, fetch OpenAPI JSON directly from the backend in a safe environment and compare against the document via public ingress. If backend is right and ingress is wrong, investigate rewrites/forwarded headers at the proxy layer.

## 17. When the Document Returns 500: Read the Root Exception

A 500 error at `/v3/api-docs` usually indicates document generation threw an exception. Locate the stack trace by timestamp/request ID and start from the first exception, not just the last line.

Common clues:

| Clue in logs | Area to inspect |
|---|---|
| `NoSuchMethodError` | Incompatible dependency versions |
| `ClassNotFoundException` | Missing artifact or wrong classpath |
| `NullPointerException` inside customizer | Custom code assumes object/path always exists |
| Jackson mapping/serialization exception | Serializers, mixins, modules, or data types |
| Schema resolution exception | Generics, recursive models, or annotations |
| `Ambiguous mapping` | Spring registered indistinguishable handlers |
| Security 401/403 | Docs endpoint blocked by security policy |
| 404 | Wrong path, context path, or docs endpoint unregistered |

If the error occurs immediately when calling the document and the stack trace points to a customizer, isolate the customizer in an integration test. Add intentional null guards, check whether paths/methods exist, and verify extensions attach to the right operations.

If the exception involves a schema, identify the exact DTO being analyzed. Temporarily swap the response type with a simple DTO in a test to see if the error vanishes; then reintroduce fields/generics step by step to pinpoint the offending model. Do not alter production DTOs just to dodge exceptions without understanding the root cause.

## 18. Checking Caching and First-Call vs Subsequent-Call Differences

If OpenAPI JSON only changes after a restart, or a customizer alters data yet responses stay stale, check caching and document initialization.

springdoc caches the OpenAPI document in standard setups. `springdoc.cache.disabled` can disable caching in supported versions. Use this only as a diagnostic step or when documents genuinely must vary per request; disabling caching increases repeated document generation cost.

Compare:
1. Document right after application startup.
2. Document after customizers/configuration run.
3. Document on repeated requests.
4. Document for each group.

If OpenAPI content depends on user, tenant, or request headers, design explicit caching and security. Do not assume default caching distinguishes all variants. An API document should normally be deterministic per build and group; never embed private user data into OpenAPI metadata.

## 19. Ordered Error-Narrowing Procedure

Follow this sequence to avoid overlooking critical evidence:

~~~mermaid
flowchart TD
    A[Record exact symptom and request] --> B[Fetch OpenAPI JSON]
    B --> C{JSON endpoint works?}
    C -- No --> D[Check status, security, path and server exception]
    C -- Yes --> E{Operation exists in JSON?}
    E -- Yes --> F[Inspect parameters, schemas, responses and security]
    E -- No --> G[Check Spring handler mappings]
    G --> H{Handler registered?}
    H -- No --> I[Check bean, profile, condition and mapping]
    H -- Yes --> J[Check springdoc filters, Hidden and groups]
    F --> K[Compare runtime request/response]
    I --> K
    J --> K
    D --> L[Inspect dependencies and customizers]
    K --> M[Create focused regression test]
    L --> M
~~~

Interpretation:
- JSON endpoint fails: check URL, security, server logs, and dependencies.
- JSON works yet misses operation: compare with Spring handler mappings.
- Handler missing: investigate application context and routing.
- Handler exists yet operation missing: check filters, hidden annotations, groups, and customizers.
- Operation exists yet schema is wrong: check signatures, Jackson, validation, and annotations.
- JSON is right yet UI fails: check UI assets, document URL, and proxy.
- Docs are right yet API fails: check runtime behavior and contract tests.

Change only one factor per reproduction attempt whenever possible. Simultaneously modifying package scanning, DTOs, Jackson, and customizers makes it hard to know which change actually fixed the bug.

## 20. Real-World Example: Endpoint Works in App Yet Missing from OpenAPI

Suppose controller:

~~~java
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @GetMapping("/{id}")
    OrderResponse getById(@PathVariable String id) {
        return service.findById(id);
    }
}
~~~

Symptom: calling `GET /api/orders/1001` succeeds, yet `/v3/api-docs` lacks path `/api/orders/{id}`.

Follow this sequence:

1. Fetch `/actuator/mappings` in a diagnostic environment and search for `/api/orders/{id}`.
2. If mapping is absent, check controller bean, profile, component scan, and startup logs.
3. If mapping is present, check whether the controller's package falls under `springdoc.packages-to-scan`.
4. Check `springdoc.paths-to-match` and `springdoc.paths-to-exclude`.
5. Search for `@Hidden` or `@Operation(hidden = true)`.
6. Confirm you are fetching the right default document or group.
7. Check whether customizers delete paths/operations.
8. Reload JSON and confirm the path and method now appear.

Do not add `@Operation` to the method before confirming Spring registered the handler. Annotations describe existing operations; they do not register routes by themselves.

## 21. Real-World Example: Schema Missing a Field After Editing a DTO

Suppose DTO:

~~~java
public record OrderResponse(
    String id,
    @JsonProperty("order_status") String status,
    @JsonIgnore String internalNote
) {
}
~~~

OpenAPI has schema:

~~~yaml
OrderResponse:
  type: object
  properties:
    id:
      type: string
    order_status:
      type: string
~~~

Consumers report `status` is missing and assume springdoc dropped the field. However, actual JSON serialization uses `order_status`, while `internalNote` is ignored by Jackson.

How to verify:
1. Call the real endpoint and save the JSON response.
2. Compare the JSON response with `components.schemas.OrderResponse`.
3. Confirm property naming per `@JsonProperty`.
4. Confirm hidden field per `@JsonIgnore`.
5. If schema mismatches runtime, inspect Jackson modules/mixins and customizers.
6. Update clients or contracts to match the agreed JSON property names.

Do not treat Java field names as authoritative when wire JSON is configured differently. The contract must describe the actual representation consumers receive.

## 22. Writing Regression Tests After Finding Root Cause

Once the bug is identified, add tests at the right layer:

- `@WebMvcTest` or `MockMvc` for controller mappings and HTTP behavior.
- `@SpringBootTest` when verifying springdoc documents generated from the real application context.
- Direct OpenAPI JSON tests asserting paths, `operationId`, parameters, schemas, and responses.
- Adapter/customizer tests if extensions or groups caused the bug.
- Contract tests verifying real requests/responses align with documentation.

Example testing OpenAPI JSON via MockMvc:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiDocumentTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void exposesOrderLookupOperation() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.paths['/api/orders/{id}'].get").exists())
            .andExpect(jsonPath(
                "$.paths['/api/orders/{id}'].get.operationId"
            ).value("getOrderById"));
    }
}
~~~

This example requires the appropriate test dependencies and static imports for `get`, `status`, and `jsonPath`. If the API docs endpoint is protected, configure test authentication accordingly. If the application changed the docs path, update the URL in tests to match published configuration.

Do not assert only that a path exists. For schema issues, assert critical fields/required/types. For security issues, assert schemes and operation requirements. For group issues, call the exact group document endpoint.

## 23. Common Diagnostic Pitfalls and How to Avoid Them

| Unfounded action | Why it hurts | Better approach |
|---|---|---|
| Adding `@Operation` to make a route appear | Annotations do not register Spring handlers | Check handler mappings first |
| Expanding component scan across modules | Can unintentionally alter application context | Inspect controller package and springdoc filters separately |
| Removing `@Hidden` without checking source | Can expose internal operations | Verify publishing policy before changing |
| Deleting all customizers | Can wipe out security/schema metadata | Isolate each customizer in tests |
| Overriding Jackson/`swagger-core` arbitrarily | Introduces new dependency conflicts | Read dependency tree and compatibility matrix |
| Looking only at Swagger UI | Cannot tell if JSON document is broken | Call OpenAPI endpoint directly |
| Leaving `DEBUG` enabled app-wide indefinitely | Too noisy and can leak data | Enable targeted package loggers briefly |
| Exposing all of Actuator | Discloses internal structure and config | Use local/test or strict security policy |
| Disabling cache immediately upon stale data | Can mask the real root cause | Compare cold/warm documents and check versions |
| Testing only the document | Does not verify runtime API | Combine document tests with endpoint contract tests |

## 24. Springdoc Bug Investigation Checklist

- [ ] Recorded HTTP method, URL, status, response, and reproduction time.
- [ ] Confirmed right host, port, profile, context path, and document group.
- [ ] Called OpenAPI JSON directly before investigating Swagger UI.
- [ ] Verified JSON is valid and inspected for the expected path/operation.
- [ ] If operation is missing, checked Spring handler mappings.
- [ ] If handler is absent, checked beans, profiles, conditions, and mappings.
- [ ] If handler is present, checked package/path filters and hiding annotations.
- [ ] Checked `GroupedOpenApi` and customizers.
- [ ] Compared controller signature with parameters/`requestBody`/responses.
- [ ] Compared schema against actual Jackson serialization.
- [ ] Checked Jakarta/Javax validation namespaces and constraints.
- [ ] Checked response codes, exception handlers, and error schemas.
- [ ] Read root exception in server logs and correlation IDs.
- [ ] Checked dependency tree if classpath or version errors occur.
- [ ] If JSON is right yet UI fails, checked Network, proxy, CSP, and document URL.
- [ ] Protected Actuator and logs from unauthorized access.
- [ ] Created regression tests at the exact failing layer.
- [ ] Reloaded document and called real endpoint to confirm fix.

## References

- [springdoc-openapi](https://springdoc.org/): configuring OpenAPI endpoints, filters, groups, Swagger UI, and customizers.
- [Spring Boot Actuator – Endpoints](https://docs.spring.io/spring-boot/reference/actuator/endpoints.html): mappings, conditions, beans, loggers, and exposing endpoints.
- [Spring MVC – Handler Methods](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods.html): controllers, request mappings, and method arguments.
- [Spring WebFlux – Annotated Controllers](https://docs.spring.io/spring-framework/reference/web/webflux/controller/ann.html): mappings and binding in WebFlux.
- [Jackson Annotations](https://github.com/FasterXML/jackson-annotations): property names, ignore, and serialization metadata.
- [Jakarta Bean Validation](https://beanvalidation.org/): constraints and validation metadata.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): paths, operations, parameters, request bodies, responses, and schemas.
