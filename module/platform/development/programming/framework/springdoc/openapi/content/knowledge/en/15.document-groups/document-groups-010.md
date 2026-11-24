# Group Overlap, Missing Operations, and Scope Verification

When a Spring Boot application publishes multiple OpenAPI documents with springdoc-openapi, an endpoint may appear in multiple groups or in none at all. This usually results from scope filters such as **pathsToMatch**, **pathsToExclude**, **packagesToScan**, and **packagesToExclude**. Understanding how these filters combine helps avoid two common mistakes: thinking an endpoint disappeared from the application when it was only filtered out of one document, or accidentally exposing internal endpoints in documentation meant for external clients.

Each **GroupedOpenApi** produces a separate OpenAPI document. Groups can intentionally overlap: the same operation can be published in both an overview document and a domain-specific document. Appearing in multiple documents does not create duplicate routes and does not alter runtime access permissions.

This article explains how inclusion and exclusion filters work, how to design intentional group overlap, how to trace missing operations, and how to inspect each JSON/YAML document.

## 1. One Operation Can Belong to Multiple Groups

Suppose an application has these endpoints:

| Operation | Controller | Purpose |
|---|---|---|
| GET /api/books | BookController | List books |
| GET /api/books/{bookId} | BookController | View a book |
| POST /api/books | BookController | Create a book |
| GET /api/orders | OrderController | List orders |
| POST /api/orders | OrderController | Create an order |
| GET /api/internal/health | InternalController | Internal check |

You might want two documents:

- **public-api**: all public endpoints under /api, excluding internal routes.
- **orders**: only order management endpoints.

In this design, GET /api/orders and POST /api/orders appear in both documents. That is intentional overlap, not a duplicate route error.

~~~mermaid
flowchart TD
    A["Spring MVC handlers"] --> B["public-api group filters"]
    A --> C["orders group filters"]
    B --> D["Document /v3/api-docs/public-api"]
    C --> E["Document /v3/api-docs/orders"]
    F["GET/POST /api/orders"] --> B
    F --> C
    G["GET /api/internal/health"] --> H["Excluded from public-api"]
    G --> I["Does not match orders group"]
~~~

A group is a **scoped API contract snapshot**. A group is not a separate Spring module, does not re-register controllers, and does not create new HTTP business endpoints.

## 2. GroupedOpenApi Filters

Common filters:

| Filter | Effect |
|---|---|
| **pathsToMatch** | Keep only operations whose path matches at least one declared pattern |
| **pathsToExclude** | Exclude operations whose path matches an exclusion pattern |
| **packagesToScan** | Keep only handlers in selected packages |
| **packagesToExclude** | Exclude handlers in excluded packages |

Configuration example:

~~~java
@Configuration
public class OpenApiGroups {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public-api")
            .pathsToMatch("/api/**")
            .pathsToExclude("/api/internal/**")
            .build();
    }

    @Bean
    GroupedOpenApi ordersApi() {
        return GroupedOpenApi.builder()
            .group("orders")
            .packagesToScan("com.example.app.orders")
            .pathsToMatch("/api/**")
            .build();
    }
}
~~~

In this example:

- public-api selects paths under /api/** and excludes /api/internal/**.
- orders selects handlers in the orders package with paths under /api/**.
- If a handler in the orders package has path /api/orders, it can belong to both groups.

### How Filters Combine

When a configuration specifies both paths and packages, evaluate conditions in two layers:

1. Within a single pattern list, an operation only needs to match **one** pattern to satisfy that filter.
2. When a group declares both path and package filters, an operation must satisfy the respective inclusion conditions; exclusion criteria remove the operation if it matches an excluded criterion.

For example, a group declaring:

~~~java
GroupedOpenApi.builder()
    .group("catalog")
    .pathsToMatch("/api/**")
    .packagesToScan("com.example.app.catalog")
    .pathsToExclude("/api/catalog/internal/**")
    .build();
~~~

A handler must reside in the selected package and have a path matching /api/**. Then, if the path matches /api/catalog/internal/**, the handler is excluded from the group.

Do not treat pathsToMatch and packagesToScan as interchangeable alternatives. When both are declared, they jointly narrow the scope. If the result is unexpectedly empty, test path filters and package filters separately to see which condition is excluding the operation.

Simple decision table:

| Path Matches Include | Package Matches Include | Matches Exclusion | Outcome |
|---|---|---|---|
| Yes | Yes | No | Included in group |
| No | Yes | No | Excluded |
| Yes | No | No | Excluded |
| Yes | Yes | Yes | Excluded |

> Exact matching rules and extra filters can vary across springdoc/Spring versions. Verify against the live documentation endpoint of your project's version, especially with complex patterns or nested packages.

## 3. Overlapping Groups Using Path Patterns

A straightforward way to build overlapping groups is using inclusive path patterns:

~~~java
@Bean
GroupedOpenApi allPublicEndpoints() {
    return GroupedOpenApi.builder()
        .group("public-api")
        .pathsToMatch("/api/**")
        .pathsToExclude("/api/internal/**")
        .build();
}

@Bean
GroupedOpenApi bookEndpoints() {
    return GroupedOpenApi.builder()
        .group("books")
        .pathsToMatch("/api/books/**")
        .build();
}

@Bean
GroupedOpenApi orderEndpoints() {
    return GroupedOpenApi.builder()
        .group("orders")
        .pathsToMatch("/api/orders/**")
        .build();
}
~~~

Book endpoints belong to public-api and books. Order endpoints belong to public-api and orders. This works well when an overview document serves general integrators while specialized documents serve specific domain teams or clients.

### Stable Group Naming

Group names appear in document URLs, for example:

- /v3/api-docs/public-api
- /v3/api-docs/books
- /v3/api-docs/orders

Use short, unique, and stable names. Renaming a group changes URLs referenced by Swagger UI, API portals, test pipelines, and client tooling.

Group names are not tag names. **Groups** decide which operations belong in a document; **tags** categorize operations within that document. An orders group can still contain Orders, Payments, and Customers tags if those operations fall within the document's scope.

## 4. Overlapping Groups Using Package Filters

Package filters work well when source code structure mirrors business domain boundaries:

~~~text
com.example.app
  books
    BookController
  orders
    OrderController
  payments
    PaymentController
  internal
    InternalController
~~~

You can generate documents by package:

~~~java
@Bean
GroupedOpenApi bookApi() {
    return GroupedOpenApi.builder()
        .group("books")
        .packagesToScan("com.example.app.books")
        .build();
}

@Bean
GroupedOpenApi commerceApi() {
    return GroupedOpenApi.builder()
        .group("commerce")
        .packagesToScan(
            "com.example.app.orders",
            "com.example.app.payments"
        )
        .build();
}
~~~

If a package is included in multiple groups, its handlers can appear in multiple documents. For example, both commerce and orders groups can scan the orders package.

### Package Scan Is Not Component Scan

GroupedOpenApi's **packagesToScan** filters handlers during documentation generation. It does not register Spring controllers and does not alter application component scanning.

If a controller is not instantiated as a Spring bean, adding its package to packagesToScan will not make endpoints appear. First confirm the controller is actually registered and has request mappings.

### Checking the Controller's Actual Package

A common mistake is specifying a parent or child package that does not match the class's declared package. When in doubt:

1. Open the package declaration inside the controller file.
2. Compare against packagesToScan and packagesToExclude.
3. Check whether the group also sets pathsToMatch.
4. Fetch the group document and search for the specific path.

Do not infer packages from disk folder names; Java packages are determined by the package declaration in source and compiled class structure.

Package filters are typically applied against handler package names and may include subpackages. Avoid ambiguous package prefixes—for instance, **orders** and **ordersArchive** can behave unexpectedly if the library version matches by string prefix. When package boundaries matter, pick unambiguous namespaces and verify actual operations in each group.

## 5. Exclusions Are Always Checked Alongside Inclusions

Exclusions are useful when a broad group needs to omit specific routes or packages:

~~~java
@Bean
GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner-api")
        .pathsToMatch("/api/**")
        .pathsToExclude(
            "/api/internal/**",
            "/api/admin/**"
        )
        .packagesToExclude(
            "com.example.app.internal",
            "com.example.app.admin"
        )
        .build();
}
~~~

In this example, partner-api accepts handlers under `/api/**`, then removes the specified paths and packages. Treat exclusions as document guardrails: if a handler matches an exclusion criterion, it does not belong in this group.

### Watch Out for Overly Broad Paths

The pattern **/** can cover nearly every route visible to springdoc. If you use it as an include condition, add explicit exclusions for paths that do not belong in that document.

For example:

~~~java
GroupedOpenApi.builder()
    .group("external")
    .pathsToMatch("/**")
    .pathsToExclude(
        "/internal/**",
        "/actuator/**",
        "/admin/**"
    )
    .build();
~~~

For public documentation, prefer explicit prefix allowlists like /api/public/** or selected API packages. Exclusion lists are easily forgotten when a new internal endpoint is added.

## 6. Configuring Groups in application.yml

Besides Java beans, springdoc supports declaring groups via Spring Boot configuration. Example:

~~~yaml
springdoc:
  group-configs:
    - group: public-api
      paths-to-match:
        - /api/**
      paths-to-exclude:
        - /api/internal/**
        - /api/admin/**
    - group: orders
      packages-to-scan:
        - com.example.app.orders
      paths-to-match:
        - /api/**
    - group: books
      paths-to-match:
        - /api/books/**
~~~

Each entry in group-configs creates a document group with its own name. You can use package filters, path filters, or a combination to define scope.

When using properties configuration:

- Use unique group names.
- Verify YAML indentation and property names for your springdoc version.
- Avoid defining the same group in both Java beans and properties unless intentional.
- If global settings such as springdoc.paths-to-match or springdoc.packages-to-scan exist, verify their combined effect with group configuration.

Do not assume global settings and per-group settings cancel each other out. When multiple filter layers exist, inspecting the JSON endpoint is the most reliable verification.

## 7. Missing Operations: Locating Where They Were Filtered Out

When an operation does not appear in a document, trace it in the following order.

### Step 1: Confirm the Endpoint Exists in Spring MVC

Check:

- Is the controller instantiated as a bean by component scan?
- Does the method have @GetMapping, @PostMapping, @RequestMapping, or an equivalent mapping?
- Could a profile, conditional bean, or deployment setting prevent the controller from being created?
- Is the endpoint conflicting with another mapping or unregistered?

If the application includes Spring Boot Actuator and exposes the mappings endpoint, **/actuator/mappings** can help inspect runtime mappings. Only use this endpoint in permitted environments and configurations; it is not an OpenAPI endpoint.

### Step 2: Check the Right Group's Filters

Compare the controller package against packagesToScan and packagesToExclude. Then compare the path against pathsToMatch and pathsToExclude.

If the group uses both package and path filters, check each condition separately. A handler in the right package whose path fails to match will still be excluded; likewise, a matching path outside the selected package is excluded.

### Step 3: Check Hiding Annotations

These annotations remove operations from documentation:

~~~java
@Hidden
@RestController
public class InternalController {
    // Controller operations can be hidden from OpenAPI
}
~~~

Or hiding a single method:

~~~java
@Operation(hidden = true)
@GetMapping("/api/internal/diagnostics")
public DiagnosticsResponse diagnostics() {
    // ...
    return null;
}
~~~

Check both class-level and method-level annotations. If the controller uses functional endpoints, inspect router configuration and corresponding springdoc metadata.

### Step 4: Check Global Filters and Customizers

Beyond group filters, the application may have:

- Global properties springdoc.paths-to-match, springdoc.paths-to-exclude, springdoc.packages-to-scan, or springdoc.packages-to-exclude.
- Customizers modifying the path/operation list after filtering. Distinguish **OpenApiCustomizer** for the default document, **GlobalOpenApiCustomizer** for the default document and groups, and customizers attached directly to **GroupedOpenApi** for that group.
- Settings hiding operations or controllers.
- Group configuration active only under a specific profile or application context.

A customizer can strip paths after initial filters select the operation. Thus, if a path passes filters yet is missing from the final JSON, inspect customizers and OpenAPI configuration.

### Step 5: Query the Right Document URL

Do not open /v3/api-docs alone and conclude a group has no operations. Query the exact group:

~~~bash
curl -i http://localhost:8080/v3/api-docs/orders
curl -i http://localhost:8080/v3/api-docs/books
curl -i http://localhost:8080/v3/api-docs/public-api
~~~

If YAML is enabled:

~~~bash
curl -i http://localhost:8080/v3/api-docs/orders.yaml
~~~

If documentation endpoints were changed via springdoc.api-docs.path or groups are configured differently, use your application's actual URLs.

## 8. Distinguishing Operations Missing from Docs vs. Non-Existent Endpoints

These are two distinct conclusions:

| Observation | Conclusion |
|---|---|
| Endpoint returns 200 when called directly but is absent from group A | Runtime route exists; group A does not publish that operation |
| Endpoint is in group B but absent from group A | Group B includes the operation; group A excludes or does not select it |
| Endpoint is absent from every document and direct call returns 404 | Mapping may be unregistered, though check profiles, context, and base path |
| /v3/api-docs/orders returns 401/403 | Documentation may be protected; cannot conclude operation was filtered out |
| /v3/api-docs/orders returns 404 | Group name/URL may be wrong or group is not registered |
| Document has the path but is missing one HTTP method | Method may be hidden, filtered/customized out, or mapped differently |

In particular, if a request to /v3/api-docs/{group} gets 401 or 403, that is a document access issue. It differs from the server returning a 200 document whose JSON omits the expected operation.

## 9. Document Filters Are Not Runtime Security

Excluding an endpoint from OpenAPI does not prevent clients from calling it. For example:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public-api")
        .pathsToMatch("/api/**")
        .pathsToExclude("/api/admin/**")
        .build();
}
~~~

This configuration only removes /api/admin/** from the public-api document. If Spring MVC still registers the endpoint and Spring Security permits the caller, clients can invoke that route.

To protect endpoints, configure Spring Security, service/controller-level authorization, or an appropriate protection layer. To protect OpenAPI docs, configure access rules for /v3/api-docs and Swagger UI. Never use pathsToExclude as an authorization control.

Conversely, an operation appearing in public-api does not mean every user is authorized to call it. Documentation and access control are two separate contracts.

## 10. Inspecting Each Group's Scope with jq

Once the application is running, list paths in each document:

~~~bash
curl -s http://localhost:8080/v3/api-docs/public-api \
  | jq -r '.paths | keys[]'

curl -s http://localhost:8080/v3/api-docs/orders \
  | jq -r '.paths | keys[]'
~~~

To view methods and paths:

~~~bash
curl -s http://localhost:8080/v3/api-docs/orders \
  | jq -r '
      .paths
      | to_entries[]
      | .key as $path
      | .value
      | to_entries[]
      | select(
          .key == "get" or
          .key == "post" or
          .key == "put" or
          .key == "patch" or
          .key == "delete" or
          .key == "head" or
          .key == "options" or
          .key == "trace"
        )
      | "\(.key | ascii_upcase) \($path)"
    '
~~~

To verify a specific operation:

~~~bash
curl -s http://localhost:8080/v3/api-docs/orders \
  | jq '.paths["/api/orders"].get'
~~~

If the output is null, the operation is not in the orders document at that URL. Check public-api or other groups to determine whether the operation is published elsewhere.

### Comparing Two Groups

You can save two documents to temporary files and compare their path/method lists with jq or a test script. When comparing, check methods as well as paths: a path might expose GET in group A but only POST in group B.

For large APIs, maintain an expected operation list per group. This list helps catch:

- New operations accidentally leaking into external docs.
- Public operations disappearing after a package or path refactor.
- Specialized groups absorbing too many endpoints.
- Two groups drifting from their designed overlap.

## 11. Testing Groups with MockMvc

You can verify documentation endpoints in integration tests:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiGroupTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void ordersDocumentContainsOrderOperations() throws Exception {
        mockMvc.perform(get("/v3/api-docs/orders"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$['paths']['/api/orders']['get']"
            ).exists())
            .andExpect(jsonPath(
                "$['paths']['/api/orders']['post']"
            ).exists());
    }

    @Test
    void publicDocumentDoesNotExposeInternalPath() throws Exception {
        mockMvc.perform(get("/v3/api-docs/public-api"))
            .andExpect(status().isOk())
            .andExpect(jsonPath(
                "$['paths']['/api/internal/health']"
            ).doesNotExist());
    }
}
~~~

This example tests the generated documentation. Pair it with tests calling runtime endpoints to verify routes and access controls behave as required. The two test suites have distinct goals:

- Documentation tests verify which operations are published in each group.
- Runtime tests verify real requests are handled and authorization is enforced.

If the project secures /v3/api-docs with Spring Security, tests must provide a principal or test security config to access docs. Do not misinterpret a 401/403 as a group filter failure.

## 12. Building a Group Scope Matrix Before Configuring

Before creating many GroupedOpenApi beans, drafting an operation matrix clarifies overlaps and exclusions:

| Operation | public-api | books | orders | internal |
|---|---:|---:|---:|---:|
| GET /api/books | Yes | Yes | No | No |
| POST /api/books | Yes | Yes | No | No |
| GET /api/orders | Yes | No | Yes | No |
| POST /api/orders | Yes | No | Yes | No |
| GET /api/internal/health | No | No | No | Yes |

This matrix serves as test criteria. After changing paths, packages, or groups, compare actual documents against the matrix to spot missing operations or misgrouped endpoints.

Useful guidelines:

- Every group should have a clear purpose and target audience.
- Overlap should occur only when an operation genuinely belongs in multiple documents.
- Use explicit path/package allowlists for partner or customer documentation.
- Keep group names stable because document URLs may be referenced by external systems.
- Avoid configuring redundant groups with identical filters; they multiply documents without adding organization value.
- When an operation is missing, verify runtime mappings first before inspecting each filter layer.

## 13. Checklist for Investigating Missing or Misgrouped Operations

**When an operation is missing:**

- [ ] Confirmed the controller is a Spring bean.
- [ ] Confirmed the method has a valid request mapping.
- [ ] Queried the right group's documentation URL.
- [ ] Path matches at least one pathsToMatch pattern if configured.
- [ ] Package matches packagesToScan if configured.
- [ ] Path does not match pathsToExclude.
- [ ] Package does not match packagesToExclude.
- [ ] Controller/method is not marked @Hidden or @Operation(hidden = true).
- [ ] Checked global filters, customizers, and active profiles.
- [ ] Distinguished 401/403 document access errors from operations absent in JSON.

**When an operation appears in an unwanted group:**

- [ ] Checked path patterns covering the route.
- [ ] Checked package scan covering the controller's package.
- [ ] Checked whether the group uses global filters.
- [ ] Added appropriate path/package exclusions.
- [ ] Verified whether the operation is intentionally shared between overview and specialized docs.
- [ ] Verified JSON after changes to confirm the operation was not dropped from groups that should keep it.

## Conclusion

An operation can appear in multiple GroupedOpenApi documents if it satisfies each group's filters. **pathsToMatch** and **packagesToScan** define the inclusion scope; **pathsToExclude** and **packagesToExclude** remove non-matching handlers. Missing operations should be traced across Spring MVC mappings, package/path filters, hiding annotations, global settings, customizers, and the right group's documentation URL. Use JSON at **/v3/api-docs/{group}**, jq, a scope matrix, and MockMvc tests to verify every group. Documentation filters only determine OpenAPI content; endpoint security and documentation security still require separate configuration.
