# Scanning Scope and Impact on Processed Handlers and Schemas

springdoc-openapi reads the handlers registered by Spring MVC or WebFlux, then builds OpenAPI operations from mappings, annotations, parameters, request bodies, responses, and related data types. When an application has many controllers, internal endpoints, API versions, or shared DTOs, a broad scanning scope can make the documentation larger and increase OpenAPI generation time.

Controlling the scanning scope ensures that the documentation only includes the APIs that need to be published, reducing the number of operations and the schema graph that springdoc must process for each document. This is especially useful when there are multiple document groups or when running the application under GraalVM Native Image. However, documentation filtering must be distinguished from Spring component scanning: springdoc filtering does not automatically prevent Spring from creating beans or initializing dependencies.

This lesson explains how to select packages and paths, hide operations, organize document groups, understand the impact of the schema graph, and measure document generation time. The examples use modern springdoc configuration; verify property names and builder APIs against the major version in use.

## 1. What Does Springdoc Have to Process?

To generate an OpenAPI document, springdoc needs to find the request mappings registered by Spring and transform them into operations. For each operation, the library must also analyze metadata and related data types.

High-level processing flow:

~~~mermaid
flowchart TD
    A[Spring MVC / WebFlux handler mappings] --> B[Select handlers by package and path]
    B --> C[Create operations and parameters]
    C --> D[Analyze request bodies and responses]
    D --> E[Discover DTOs, enums, and referenced schemas]
    E --> F[Apply annotations and customizers]
    F --> G[Serialize OpenAPI JSON/YAML]
~~~

Main data groups:

- **Handler mapping:** controller method, HTTP method, path, consumes, produces, and mapping conditions.
- **Operation metadata:** summary, description, operationId, tag, security requirement, and response.
- **Parameter:** path, query, header, and cookie parameters.
- **Request/response model:** DTO, record, generic wrapper, collection, map, and return type.
- **Schema graph:** models referenced directly and indirectly through nested properties.
- **OpenAPI components:** shared schemas, security schemes, reusable responses/parameters, and metadata added by customizers.

Therefore, the cost does not depend solely on the number of controllers. A controller with few endpoints that uses deeply nested DTOs, complex generics, or many polymorphic branches can still produce a large schema graph.

## 2. Distinguishing Spring Component Scanning from Springdoc Operation Scanning

The two types of scanning serve different purposes:

| Mechanism | Purpose | Primary Impact |
|---|---|---|
| Spring component scanning | Find and register beans such as controllers, services, repositories, and configurations | Application context, dependency injection, and startup process |
| Spring MVC/WebFlux handler mapping | Register routes/handlers capable of receiving requests | The actual set of endpoints in the application |
| Springdoc package/path filtering | Select which handlers are included in the OpenAPI document | Number of operations and schemas to process for that document |

`springdoc.packages-to-scan` and `springdoc.paths-to-match` filter which operations are documented. They do not replace `@ComponentScan`, do not automatically disable controller beans, and do not guarantee that a controller's dependencies are excluded from the application context.

For example, if an admin controller still has a bean created by Spring but is excluded from OpenAPI via a path filter, that endpoint can still operate over HTTP. Documentation filtering is not a security or endpoint-disabling mechanism.

Do not narrow `@ComponentScan` just to reduce the number of operations in Swagger UI. Doing so can cause services, repositories, security configurations, or required beans to disappear, preventing the application from starting or altering runtime behavior.

## 3. Filtering by Package with springdoc.packages-to-scan

When controllers are organized by package, you can restrict the packages that springdoc includes in the default document:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.catalog.api
    - com.example.catalog.partner
~~~

In the example, springdoc only includes handlers belonging to the two selected packages in the document where this configuration applies. DTOs located in other packages can still appear in `components.schemas` if they are referenced by the request or response of a selected operation.

This point is very important: `packages-to-scan` filters handler packages, not an independent list of DTO packages. There is no need to move all models into the same package as the controllers for them to be included in schemas.

Choose packages that are specific enough:
- `com.example.catalog.api` if the entire package contains APIs to be published.
- `com.example.catalog.publicapi` if public APIs are clearly separated.
- Avoid choosing a root package that is too broad, such as `com.example`, if beneath it there are admin, internal, actuator, or adapter packages that do not belong to the public contract.

If controllers are located in subpackages, check the package matching rules of the springdoc version in use and confirm via the OpenAPI output. Do not assume a parent package always includes all subpackages in the exact same way across versions.

## 4. Filtering by Path with springdoc.paths-to-match

Matching packages do not always reflect API boundaries. A single package may contain both public and internal endpoints. In that case, you can filter by URL path:

~~~yaml
springdoc:
  paths-to-match:
    - /api/**
    - /partner/**
~~~

The example above selects only paths under the two prefixes. You can combine packages and paths to narrow the scope further:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.catalog
  paths-to-match:
    - /api/**
~~~

An operation must satisfy the corresponding filter conditions to be included in the document. Check the actual path after applying the context path, WebFlux base path, or proxy configuration; the path seen by springdoc is the application's mapping, not necessarily identical to the full public URL outside the proxy.

Commonly used patterns:

| Pattern | Illustrative Meaning |
|---|---|
| `/api/**` | Paths under the `/api` prefix |
| `/api/v1/**` | Only v1 APIs |
| `/partner/**` | Partner endpoint group |
| `/api/orders/*` | One segment after `/api/orders` according to path matcher rules |

The exact syntax and matching semantics depend on the Spring Framework/springdoc version. If a pattern does not match, the document may be empty even though the controller still works. Open `/v3/api-docs` and check `paths` after each filter change.

## 5. Excluding Packages and Paths

When most APIs need to be published but certain areas need to be excluded, you can use `packages-to-exclude` or `paths-to-exclude`:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.catalog
  packages-to-exclude:
    - com.example.catalog.internal
  paths-to-exclude:
    - /api/internal/**
    - /api/debug/**
~~~

Use package exclusion when internal controllers are organized separately. Use path exclusion when you want to exclude a route prefix regardless of the package containing the handler.

You can combine include and exclude filters to make the documentation clearer. After configuring, always check boundary endpoints:
- Are public endpoints in the parent package accidentally excluded?
- Are admin endpoints in the same package but with a different path included?
- Does a route with multiple path mappings still retain the desired operation?
- Is there another document group that needs to keep an endpoint excluded from the default document?

Do not treat `paths-to-exclude` as an authorization rule. Clients can still call the endpoint if the runtime route and security policy allow it, even when the endpoint does not appear in the OpenAPI document.

## 6. Hiding a Specific Controller or Operation

If you only need to hide a few individual endpoints, you can use annotations instead of adding global filters.

Hiding an entire controller:

~~~java
import io.swagger.v3.oas.annotations.Hidden;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@Hidden
@RestController
@RequestMapping("/internal/diagnostics")
class DiagnosticsController {
    // Endpoints not published in OpenAPI
}
~~~

Hiding a single method:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @Operation(hidden = true)
    @GetMapping("/api/orders/reindex")
    void reindex() {
        // Internal task
    }
}
~~~

Use `@Hidden` when you want to exclude a resource or handler from documentation. Use `@Operation(hidden = true)` when an operation has already been declared and you want to hide that operation.

Hiding an operation only affects documentation. The endpoint can still exist and must be protected by Spring Security, a gateway, or permission checks in the application. Do not use hiding annotations as a security measure.

## 7. GroupedOpenApi for Scoped Documents

An application can publish multiple documentation groups, such as public API, partner API, and internal API. Each group can have its own package/path filters.

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiGroupsConfiguration {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .packagesToScan("com.example.catalog.publicapi")
            .pathsToMatch("/api/public/**")
            .build();
    }

    @Bean
    GroupedOpenApi partnerApi() {
        return GroupedOpenApi.builder()
            .group("partner")
            .packagesToScan("com.example.catalog.partner")
            .pathsToMatch("/partner/**")
            .build();
    }
}
~~~

With the default springdoc group configuration, documents are typically accessed in the following format:

~~~text
/v3/api-docs/public
/v3/api-docs/partner
~~~

The group name becomes part of the documentation endpoint. Check the actual path if `springdoc.api-docs.path` has been customized.

Groups help distribute documentation by consumer audience and limit the number of operations in each document. However, each group is a document that must be generated and maintained. Too many groups or heavily overlapping groups can increase total processing time, cache memory usage, and document size.

Create groups along meaningful boundaries:
- Different consumer audiences, such as public and partner.
- Independent business domains.
- API versions with different lifecycles.
- Different documentation publishing and security policies.

Do not create a separate group for each controller or each operation if there is no actual distribution need.

## 8. Avoiding Unintended Group Overlap

Two groups can both include the same operation if their package/path filters intersect. This is not necessarily wrong, but it should be intentional.

For example:
- Group `public` selects `/api/**`.
- Group `orders` selects `/api/orders/**`.

Order operations may appear in both documents. If each document is loaded and validated separately, schema generation/maintenance costs may be duplicated.

Draw up a group boundary table before creating the configuration:

| Group | Package | Path | Audience |
|---|---|---|---|
| public | `com.example.api.publicapi` | `/api/public/**` | External applications |
| partner | `com.example.api.partner` | `/partner/**` | Integration partners |
| internal | `com.example.api.internal` | `/internal/**` | Operations team |

If an internal group is not meant to be published externally, protect that group's document endpoint with a separate security policy. Naming it `internal` or hiding the group from the Swagger UI dropdown does not automatically protect the JSON document.

## 9. How Does Handler Count Affect Operation Count?

Each handler mapping included in a document can generate one or more operations depending on the mapping. For instance, a single method can support multiple HTTP methods or multiple path mappings.

Do not use the number of controller classes as a proxy for document size. Metrics to distinguish:

- **Controller count:** number of controller classes.
- **Handler count:** number of methods/handlers registered by Spring.
- **Path count:** number of paths in `paths`.
- **Operation count:** total number of HTTP method operations under the paths.
- **Schema count:** number of component schemas generated.
- **Document count:** number of OpenAPI documents/groups to generate.

One controller with 30 mapping methods can produce more operations than 10 small controllers. Conversely, many controllers might only provide a very small number of endpoints selected by a filter.

Example of one path with two operations:

~~~yaml
paths:
  /api/orders:
    get:
      operationId: listOrders
      responses:
        "200":
          description: OK
    post:
      operationId: createOrder
      responses:
        "201":
          description: Created
~~~

Here the path count is 1, but the operation count is 2. When measuring document scale, count operations separately from paths.

## 10. Schema Count Depends on the Data Type Graph

Schemas are discovered from request/response types and the types referenced within them. The graph can expand through property relationships:

~~~text
CreateOrderRequest
  ├── CustomerReference
  ├── List<OrderLine>
  │     └── ProductReference
  └── ShippingAddress

OrderResponse
  ├── OrderStatus
  ├── List<OrderLineResponse>
  └── Money
~~~

A single operation can pull in many schema components. A DTO shared by multiple operations is usually referenced repeatedly rather than creating an independent component for each use, though inline schemas, generic specializations, or differing annotations can make the output more complex.

Factors that make the schema graph large or expensive to process:
- Deeply nested DTOs across many levels.
- Many generic wrappers or nested collections.
- Polymorphism with `oneOf`, `allOf`, discriminators, and many subtypes.
- Large enums or models with many properties.
- Jackson mixins, naming strategies, and custom serializers.
- `@Schema` annotations or customizers that create additional schemas.
- Recursive models with circular references.

Therefore, reducing the number of operations usually reduces the schemas discovered, though not at a fixed ratio. An endpoint returning a large model graph can take more work to process than many endpoints returning simple scalars.

## 11. Referenced Schemas Are Still Needed Even If the DTO Package Is Outside the Scan Scope

Suppose the controller is in `com.example.catalog.api`, while the DTOs are in `com.example.catalog.contract`:

~~~java
package com.example.catalog.api;

import com.example.catalog.contract.OrderResponse;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

@RestController
class OrderController {

    @GetMapping("/api/orders/{id}")
    OrderResponse getOrder(@PathVariable String id) {
        // ...
        return null;
    }
}
~~~

~~~java
package com.example.catalog.contract;

public record OrderResponse(
    String id,
    String status,
    CustomerSummary customer
) {
}

record CustomerSummary(String customerId, String displayName) {
}
~~~

If the handler is selected, springdoc still needs to describe `OrderResponse` and the types referenced within it. There is no need to add the DTO package to `packages-to-scan` just to make the schemas appear. Doing so could cause springdoc to treat the model package as a handler scan area even though that package contains no API mappings.

If a schema is missing, check the method/request body types, Jackson visibility, annotations, and customizers before expanding the package filter.

## 12. Impact of Group Count and Document Caching

Each group can have a different set of operations and schemas. When there are many groups:
- Initial document generation time can increase.
- Shared schemas may be analyzed or serialized across multiple documents.
- Total JSON/YAML payload size increases.
- Each document's cache may hold additional data in memory.
- Swagger UI may need to fetch the corresponding document when the user switches groups.

Springdoc includes an OpenAPI document caching mechanism in standard configurations. The `springdoc.cache.disabled` property can disable caching in supported versions; only disable it when you genuinely need the documentation to vary per request or have a specific testing reason. Disabling the cache can make repeated document generation more CPU-intensive.

Caching reduces the cost of repeated reads, but it does not eliminate the initial document generation cost. If you need to optimize the first access, reduce the handler/schema scope, inspect customizers, and measure cold generation time.

If a customizer generates content that depends on the user, tenant, or request headers, do not assume the default OpenAPI cache automatically distinguishes every variant. OpenAPI documentation should generally be stable per application/group; caller-dependent content needs separate design and inspection for cross-request data leakage risks.

## 13. Measuring OpenAPI Generation Time Before and After Filtering

Measure three stages separately:
1. Spring Boot startup time.
2. Time for the first OpenAPI request after the application starts.
3. Time for repeated requests once the document is cached.

Use the same machine, profile, JVM, configuration data, and dependency versions when comparing. Run multiple times and record the median or p95 rather than drawing conclusions from a single measurement.

Example of measuring the first request after a restart:

~~~bash
curl -sS -o /dev/null \
  -w 'first OpenAPI request: %{time_total}s\n' \
  http://localhost:8080/v3/api-docs
~~~

Call repeatedly to measure warm requests:

~~~bash
for i in 1 2 3 4 5; do
  curl -sS -o /dev/null \
    -w 'warm OpenAPI request: %{time_total}s\n' \
    http://localhost:8080/v3/api-docs
done
~~~

When caching is enabled, warm requests are typically faster than cold requests. If not, confirm the springdoc version and cache configuration before comparing.

Do not measure through a proxy in one run and call the backend directly in another. Network latency, TLS handshake, authentication, and gateways can skew the results. If you need to measure server processing time accurately, combine application-side logs/metrics with HTTP client timing.

## 14. Counting Paths, Operations, and Schemas in OpenAPI JSON

After downloading the document:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

You can use `jq` to obtain basic metrics:

~~~bash
jq '{
  openapi: .openapi,
  pathCount: (.paths | length),
  operationCount: ([
    .paths[] | to_entries[]
    | select(
        .key == "get" or .key == "put" or .key == "post" or
        .key == "delete" or .key == "options" or .key == "head" or
        .key == "patch" or .key == "trace"
      )
  ] | length),
  schemaCount: (.components.schemas // {} | length)
}' openapi.json
~~~

These metrics help compare before and after changing filters:
- Path count decreases, though operation count may decrease at a different ratio.
- Schema count decreases when some models are no longer referenced.
- Schema count does not decrease much if many operations share common DTOs.
- Document groups can have separate metrics.

These are scale metrics, not a complete benchmark. One complex schema can take more work to process than many simple schemas; file size and serialization time must also be considered.

## 15. Configuring Filters for the Default Document and Separate Groups

If only one document is needed, using properties may be sufficient:

~~~yaml
springdoc:
  packages-to-scan:
    - com.example.catalog.api
  paths-to-match:
    - /api/**
  packages-to-exclude:
    - com.example.catalog.api.internal
  paths-to-exclude:
    - /api/internal/**
~~~

If there are multiple groups with distinct scopes, declare `GroupedOpenApi` beans so each group has explicit filters:

~~~java
@Bean
GroupedOpenApi orderApi() {
    return GroupedOpenApi.builder()
        .group("orders")
        .packagesToScan("com.example.catalog.orders")
        .pathsToMatch("/api/orders/**")
        .pathsToExclude("/api/orders/internal/**")
        .build();
}
~~~

Do not configure overly narrow global includes/excludes and then expect a separate group to automatically restore all excluded endpoints. Check how the springdoc version in use combines global configuration with group-specific filters. Open each group's document endpoint and verify the actual paths.

If using a custom `OpenAPI` bean, `OpenApiCustomizer`, or `GlobalOpenApiCustomizer`, verify that they do not add operations/schemas beyond the intended scope. Scan filters do not necessarily remove components that customizers proactively add.

## 16. Scanning Scope and GraalVM Native Image

Native Image compiles the application into a native executable using AOT analysis and packages the required components. Operations relying on reflection, resource lookup, or classpath discovery must be supported by appropriate metadata/hints.

Narrowing operation scanning can:
- Reduce the number of operations and schemas that springdoc generates for the document.
- Reduce the size of the generated and distributed OpenAPI JSON.
- Avoid processing models belonging only to API groups that do not need to be published in that document.
- Clarify the set of DTOs that need reflection/serialization verification in the native executable.

However, springdoc filters do not automatically exclude controller beans from Spring AOT, do not automatically generate all reflection hints, and do not guarantee a smaller native image by a fixed ratio. If a controller is still component-scanned, its classes and dependencies can still be included in the application context/native image.

For DTOs used in requests/responses, Spring provides annotations such as `@RegisterReflectionForBinding` to register reflection hints for binding when needed:

~~~java
import org.springframework.aot.hint.annotation.RegisterReflectionForBinding;
import org.springframework.context.annotation.Configuration;

@Configuration
@RegisterReflectionForBinding({
    CreateOrderRequest.class,
    OrderResponse.class
})
class ApiReflectionConfiguration {
}
~~~

This is an example for models requiring binding/reflection in the native runtime. Do not treat this annotation as a universal solution for all reflection that springdoc, Jackson, or other libraries might use. Only add hints after inspecting native build output and specific runtime errors; test using the actual native executable.

If the documentation only needs to be distributed to clients, another option is exporting OpenAPI JSON/YAML in CI using a test JVM profile and then publishing a static artifact. In that case, the native runtime application does not necessarily need to serve Swagger UI or generate documentation dynamically in production. However, if product requirements call for `/v3/api-docs` on the native executable, that endpoint must be tested in native tests.

## 17. Scanning Scope Optimization Checklist

- [ ] Distinguish Spring component scanning from springdoc operation filtering.
- [ ] Identify the packages containing controllers/handlers to publish.
- [ ] Use `springdoc.packages-to-scan` when package boundaries are clear.
- [ ] Use `springdoc.paths-to-match` when API boundaries are expressed via paths.
- [ ] Use `packages-to-exclude` or `paths-to-exclude` for unpublished areas.
- [ ] Use `@Hidden` or `@Operation(hidden = true)` for individual cases.
- [ ] Do not treat hiding operations as endpoint protection.
- [ ] Keep referenced DTOs even if they reside outside the handler scan package.
- [ ] Create `GroupedOpenApi` by consumer audience or business domain.
- [ ] Avoid overlapping groups and overly granular groups when unnecessary.
- [ ] Check that customizers do not add unintended operations/schemas.
- [ ] Count paths, operations, and schemas before and after filtering.
- [ ] Measure cold generation separately from warm cached requests.
- [ ] Measure under the same environment and configuration for meaningful comparisons.
- [ ] For native image, check AOT/reflection hints and run the real executable.
- [ ] Confirm `/v3/api-docs` or group endpoints contain the exact set of operations to publish.

## References

- [springdoc-openapi – Properties](https://springdoc.org/properties.html): package/path filtering, cache, and OpenAPI configuration properties.
- [springdoc-openapi – GroupedOpenApi](https://springdoc.org/#springdoc-openapi-core): configuring multiple document groups.
- [Spring Framework – Classpath Scanning](https://docs.spring.io/spring-framework/reference/core/beans/classpath-scanning.html): bean discovery and component scanning mechanisms.
- [Spring Boot – AOT Processing](https://docs.spring.io/spring-boot/reference/packaging/aot.html): AOT processing for Spring Boot applications.
- [Spring Boot – GraalVM Native Images](https://docs.spring.io/spring-boot/reference/packaging/native-image/index.html): building and testing native executables.
- [Spring Framework – Runtime Hints](https://docs.spring.io/spring-framework/reference/core/aot.html): reflection, resource, and proxy hints for AOT/native image.
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html): OpenAPI paths, operations, and components structure.
