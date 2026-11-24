# Execution Order and Overwrite Risks Between Customizers

springdoc-openapi allows customizing the specification after scanning controllers and building the OpenAPI model. An application may register multiple customizers to supplement metadata, standardize responses, add security requirements, modify schemas, or change server URLs. When multiple customizers modify the same part of the document, execution order determines the final outcome.

For example, the first customizer sets the API title, the second replaces the entire `Info` object, and the third adds the version. If the second customizer runs last, the title set by the first customizer disappears. Another case is two customizers both adding a `429` response; the later customizer can overwrite the response added earlier if both write to the same status code.

This lesson explains the document generation lifecycle, commonly used customizer types, how Spring orders beans, the difference between replacement and additive operations, and how to design a deterministic customization chain.

## Objectives

After this lesson, you will be able to:

- Identify the stages where springdoc builds and customizes OpenAPI.
- Distinguish customizers at the operation, full-document, and document-group levels.
- Use `@Order` or `Ordered` to declare execution order.
- Understand why `@DependsOn`, `@Primary`, and bean instantiation order do not substitute for customizer ordering.
- Recognize operations that can replace previous data such as `setInfo`, `setServers`, and `setResponses`.
- Design additive operations with duplicate checks that preserve existing configuration.
- Avoid conflicts between customizers when modifying paths, operations, responses, tags, security, or components.
- Test ordering, idempotency, and the final OpenAPI document.

## 1. Why Does Customizer Order Matter?

OpenAPI is a multi-level data structure:

- The root document contains `info`, `servers`, `tags`, `paths`, `components`, and `security`.
- Each path contains operations such as GET, POST, PUT, and DELETE.
- Each operation has parameters, request body, responses, tags, security, and extensions.
- Components contain schemas, responses, parameters, security schemes, and reusable elements.

Multiple customizers can modify the same node in this structure. Example:

| Customizer | Change |
|---|---|
| MetadataCustomizer | Sets title, description, and version in `info` |
| ServerCustomizer | Adds server URL for the deployment environment |
| SecurityCustomizer | Adds security schemes and security requirements |
| ErrorResponseCustomizer | Adds shared error responses to operations |
| TagCustomizer | Standardizes tags and tag ordering |

If customizers operate on independent parts, order may not matter. However, when two customizers write to the same property or replace the same collection, the result depends on order. This creates subtle bugs: titles vanish, servers disappear, error responses get overwritten, tags duplicate, or security requirements no longer behave as expected.

Treat customizers as a sequential transformation pipeline over the same OpenAPI model. For each transformation, know what data it reads, where it writes, whether it replaces existing data, or whether it only appends data.

## 2. OpenAPI Document Generation Lifecycle

Conceptually, document generation can be viewed in stages:

1. Spring Boot initializes the application context and registers springdoc-related beans.
2. springdoc discovers controllers, request mappings, functional routes, and metadata annotations.
3. springdoc builds paths, operations, parameters, request bodies, responses, and schemas.
4. Operation customizers are invoked as operations are created or finalized.
5. OpenAPI customizers receive the assembled document and modify the overall model.
6. The document is serialized to JSON or YAML to be served via the docs endpoint.

This is a high-level diagram. The exact placement of each hook may vary across springdoc versions, MVC vs. WebFlux applications, and grouped APIs. Never deduce the order of every extension point solely from bean initialization order.

For example, the default endpoint is typically:

~~~text
GET /v3/api-docs
~~~

If the application defines groups, each group can have its own documentation endpoint, typically in the form:

~~~text
GET /v3/api-docs/{group}
~~~

Customizers can apply at different scopes. Therefore, when verifying results, call the exact documentation endpoint that clients or API gateways actually consume.

### At Which Level Do OperationCustomizer and OpenApiCustomizer Run?

`OperationCustomizer` acts on an individual operation alongside its corresponding `HandlerMethod`. It is suited for adding metadata based on controller methods, such as extensions containing feature names, default responses, or descriptions driven by internal annotations.

`OpenApiCustomizer` receives the entire `OpenAPI` object. It is suited for document-level changes such as `info`, `servers`, root tags, security schemes, or scanning across multiple paths and operations.

An operation-level customizer generally runs while operations are being built; a document-level customizer sees the overall structure once operations have been assembled. However, do not rely on assumptions about this ordering as a substitute for the API docs of your springdoc version. Test specific hooks whenever logic depends on timing.

## 3. Customizer Types and Scopes of Application

springdoc provides multiple extension points. Choose the type with the smallest scope sufficient for the need:

| Extension Point | Scope | Example Use |
|---|---|---|
| `OperationCustomizer` | One operation bound to a handler method | Adding extensions or responses from method annotations |
| `GlobalOperationCustomizer` | Operations across documents, including groups as supported by version | Applying shared policies to operations |
| `OpenApiCustomizer` | Entire default OpenAPI document | Modifying `info`, `servers`, root tags, or components |
| `GlobalOpenApiCustomizer` | Entire documents, including grouped OpenAPIs as supported by version | Shared policy across all groups |
| `RouterOperationCustomizer` | Operations discovered from functional routes | Adding metadata for routes without controller annotations |

Interface names, packages, and group scopes may change across major versions. In springdoc 2.x, customizers typically reside in `org.springdoc.core.customizers`; `ParameterObject` resides in `org.springdoc.core.annotations`. Use the APIs provided by your project's actual dependencies.

### Choosing the Right Scope

If you only need to modify an operation based on a method annotation, use OperationCustomizer. There is no need to scan all of `openApi.getPaths()` to locate that method again.

If you need to add a server URL or `Info` for the entire default document, OpenApiCustomizer is more appropriate.

If an application has multiple `GroupedOpenApi` instances and a policy must apply to every group, consider GlobalOpenApiCustomizer or GlobalOperationCustomizer. A regular OpenApiCustomizer may apply only to the default document depending on version and registration. Never assume all groups automatically receive the same customizers.

### OperationCustomizer Example

~~~java
import io.swagger.v3.oas.models.Operation;
import org.springdoc.core.customizers.OperationCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration
class OperationCustomizationConfiguration {

    @Bean
    @Order(100)
    OperationCustomizer addOperationSourceExtension() {
        return (operation, handlerMethod) -> {
            operation.addExtension(
                "x-source-method",
                handlerMethod.getMethod().getName()
            );
            return operation;
        };
    }
}
~~~

The example adds an extension to each operation based on the method name. The extension is added using `addExtension` without replacing the entire existing extensions map.

### OpenApiCustomizer Example

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Info;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.annotation.Order;

@Configuration
class DocumentCustomizationConfiguration {

    @Bean
    @Order(100)
    OpenApiCustomizer addDefaultInfo() {
        return openApi -> {
            if (openApi.getInfo() == null) {
                openApi.setInfo(new Info());
            }

            Info info = openApi.getInfo();
            if (info.getTitle() == null) {
                info.setTitle("Product API");
            }
            if (info.getVersion() == null) {
                info.setVersion("1.0");
            }
        };
    }
}
~~~

The customizer only fills in missing fields. This approach preserves `title` or `version` values already declared from another source. If the goal is to enforce a specific value, you can overwrite it explicitly, while clearly documenting that customizer's ownership.

## 4. Execution Order with @Order and Ordered

Spring supports sorting beans when they are collected into a list or processed by a mechanism using an order comparator. You can declare ordering with `@Order` on a bean or by implementing the `Ordered` interface.

Value rules:

- Lower numbers have higher priority and run earlier.
- `Ordered.HIGHEST_PRECEDENCE` represents the highest priority.
- `Ordered.LOWEST_PRECEDENCE` represents the lowest priority.
- If multiple beans share the same order value, do not rely on accidental registration order or implementation details to dictate outcomes.

Example:

~~~java
@Bean
@Order(10)
OpenApiCustomizer addBaseMetadata() {
    return openApi -> {
        // Step 1: set up baseline metadata.
    };
}

@Bean
@Order(20)
OpenApiCustomizer addEnvironmentServer() {
    return openApi -> {
        // Step 2: add environment-specific server.
    };
}

@Bean
@Order(30)
OpenApiCustomizer addSharedResponses() {
    return openApi -> {
        // Step 3: add shared responses.
    };
}
~~~

When springdoc collects beans of the same type in Spring order, the customizer with order 10 runs before order 20, followed by order 30. Verify behavior against your springdoc version if logic depends on this order.

### Implementing Ordered

If you need to write a customizer as a standalone class:

~~~java
public class MetadataOpenApiCustomizer
        implements OpenApiCustomizer, Ordered {

    @Override
    public int getOrder() {
        return 10;
    }

    @Override
    public void customise(OpenAPI openApi) {
        // Add baseline metadata.
    }
}
~~~

Depending on the interface version, the callback method name may be `customise` or `customize`. The example above illustrates the `customise` API style; use the exact signature provided by your project's springdoc dependency. The `@Order` annotation is usually more concise when only bean ordering is needed.

### Order Only Applies Within the Same Pipeline

`@Order` does not establish a single unified chain across every extension point. An OperationCustomizer and an OpenApiCustomizer belong to different phases; do not expect placing `@Order(10)` on an OpenApiCustomizer to make it run before an OperationCustomizer with `@Order(20)`.

Similarly, ordering between `OpenApiCustomizer` and `GlobalOpenApiCustomizer`, or between default customizers and group customizers, depends on how springdoc organizes each pipeline. Set explicit orders within the same collection type and test each scope separately.

### @Order Is Not Bean Initialization Order

`@Order` typically controls ordering within a collection or order-aware mechanism. It is not a guarantee that beans are instantiated in strict numeric order. Spring can instantiate beans according to dependencies and application context lifecycle.

Three easily confused annotations/mechanisms:

| Mechanism | Role | Sorts Customizer Callbacks? |
|---|---|---|
| `@Order` / `Ordered` | Sorts beans in order-aware collections | Yes, if springdoc uses a comparator for that collection |
| `@DependsOn` | Forces dependent beans to initialize before the current bean | Does not sort customizer invocation order |
| `@Primary` | Selects the preferred bean when resolving a single dependency | Does not sort all customizers |

If one customizer must run after another, use ordering in the right pipeline or merge dependent logic into a single customizer. Do not use `@DependsOn` to try to control OpenAPI transformation order.

## 5. Distinguishing Replacement from Additive Operations

Swagger Core models have many setters and helper methods. They do not share the same semantics:

- Setters such as `setInfo`, `setServers`, and `setResponses` usually replace the current reference or collection with a new value.
- `add...` methods typically append items, though for keyed maps like responses or schemas, adding the same key can overwrite the old value.
- Modifying a child object through a getter usually changes only the selected property while preserving other properties of that object.

Do not call an operation a “merge” if it simply replaces an entire object or map. Read the exact semantics of each model method and check existing values before writing.

| Component | Operation Risking Replacement | Less Destructive Update Approach |
|---|---|---|
| Info | `openApi.setInfo(new Info())` | Get `getInfo()` and update title/description/version individually |
| Servers | `openApi.setServers(newServers)` | Iterate existing list, add or update server by URL |
| Root tags | `openApi.setTags(tags)` | Add tag if no matching name exists yet |
| Responses | `operation.setResponses(newResponses)` | Get current map, add only missing status codes |
| Security | `operation.setSecurity(requirements)` | Check current requirements and append needed schemes |
| Extensions | `operation.setExtensions(map)` | Use `addExtension` per key |
| Paths | `openApi.setPaths(paths)` | Add or update a specific path, checking if path exists |
| Schemas | `components.setSchemas(schemas)` | Add schema by unique name, explicitly handling existing keys |

### setInfo Can Wipe Out Previous Metadata

The following snippet replaces the entire existing Info:

~~~java
openApi.setInfo(new Info()
    .title("Internal API")
    .version("2.0"));
~~~

If an earlier customizer set description, terms of service, contact, or license, those values may be lost because the new Info lacks them.

If only the title needs updating, modify that property directly:

~~~java
if (openApi.getInfo() == null) {
    openApi.setInfo(new Info());
}

openApi.getInfo().setTitle("Internal API");
~~~

The second approach preserves other Info properties. If you intentionally want to replace the entire Info, do so deliberately and let a single customizer own all metadata.

### setServers and addServersItem

`setServers` replaces the current server list. If one customizer sets a server URL from deployment configuration, another customizer calling `setServers` with a list containing only a local URL can erase the deployment server.

`addServersItem` appends a server to the list. However, repeated calls can create duplicate servers. Check the URL before adding:

~~~java
String serverUrl = "https://api.example.com";

if (openApi.getServers() == null) {
    openApi.setServers(new ArrayList<>());
}

boolean exists = openApi.getServers().stream()
    .anyMatch(server -> serverUrl.equals(server.getUrl()));

if (!exists) {
    openApi.addServersItem(
        new Server().url(serverUrl).description("Production")
    );
}
~~~

The example uses the URL as the identifying key. If two entries share the same URL with different descriptions, decide clearly whether to keep the existing description or update it.

## 6. Conflicts in Responses, Security, Tags, and Components

### Responses Are Keyed by Status Code

`ApiResponses` is a map keyed by response codes such as `200`, `400`, `429`, or `default`. When two customizers both write a `429` response, the later customizer can overwrite the response for that key.

Example prone to overwriting:

~~~java
operation.getResponses().addApiResponse(
    "429",
    new ApiResponse().description("Rate limit exceeded")
);
~~~

If another customizer also adds `429` with different content, the later value overwrites the earlier one. Choose a policy:

- If a `429` response already exists, keep it intact.
- If absent, add the default response.
- If normalizing existing responses, intentionally update description/content rather than replacing the entire ApiResponse.

Example adding only when absent:

~~~java
ApiResponses responses = operation.getResponses();
if (responses == null) {
    responses = new ApiResponses();
    operation.setResponses(responses);
}

if (!responses.containsKey("429")) {
    responses.addApiResponse(
        "429",
        new ApiResponse().description("Rate limit exceeded")
    );
}
~~~

If shared error responses must be standardized across every operation, place the logic in one customizer with clear ownership and avoid having multiple beans define the same status code.

### Security Requirements Can Be Replaced

Root security (`openApi.security`) and operation security (`operation.security`) are two separate levels. `setSecurity(...)` at one level replaces the current list at that level. If an operation already has its own security, adding security at the root does not necessarily mean the operation adds that requirement as you might expect; OpenAPI semantics allow operation-level security to override root-level security.

Before modifying security, check:

- Whether the security scheme already exists in `components.securitySchemes`.
- Which requirements root security currently applies.
- Whether the operation declares its own security.
- Whether `security: []` is used to mark an operation as not requiring authentication.

In OpenAPI, each Security Requirement Object in the `security` list is an alternative option (OR). Within a single object, multiple schemes must be satisfied simultaneously (AND). Thus, adding a new object to the list creates an alternative authentication method; adding multiple schemes to the same object requires the client to supply all of them.

Example of two alternative authentication options:

~~~yaml
security:
  - bearerAuth: []
  - apiKeyAuth: []
~~~

Clients can use either a bearer token or an API key. If both schemes are placed in the same Security Requirement Object, clients must provide both:

~~~yaml
security:
  - bearerAuth: []
    apiKeyAuth: []
~~~

Do not delete existing security requirements just to add a new scheme. Combine requirements following OpenAPI OR/AND semantics and verify the generated document.

### Tags and Extensions

Root tags and operation tags are separate. Adding a tag to an operation does not automatically create a tag description at the root. If a customizer adds root tags multiple times, the document can end up with duplicate names. Check `tag.getName()` before adding.

For extensions, prefer `addExtension("x-key", value)` over `setExtensions(...)` when only adding a single key. If a key already exists, specify which customizer owns updating its value.

### Components and Schema Names

`components.schemas` is a map keyed by component name. Two customizers adding a schema named `ErrorResponse` do not create two independent schemas; writing the same key overwrites the existing value. This is especially hazardous when two groups use the same name for different structures.

Use clearly scoped component names such as `PublicErrorResponse` and `AdminErrorResponse`, or use a single shared schema owned by one central configuration. Before adding a schema, check whether the name already exists and confirm `$ref` references from operations still point to the right schema.

## 7. Designing a Customizer Chain with Clear Ownership

Ordering only solves part of the problem. If multiple customizers have permission to modify the same property, sorting them merely decides who writes last; the configuration remains fragile whenever new beans are added or order changes.

A maintainable design clearly defines:

1. Which customizer owns each part of the document.
2. Which customizers may only supplement data when absent.
3. Which customizers are allowed to replace existing values.
4. Whether customizers depend on each other's output.
5. Whether scope is the default document, all groups, or one specific group.

Example conventions:

| Data | Suggested Owner | Rule |
|---|---|---|
| `info.title`, `info.version` | Metadata customizer | One place decides final values |
| `info.description`, contact, license | Metadata customizer | Updates specific properties, preserves unowned fields |
| `servers` | Server customizer | Upserts by URL, avoids deleting other servers |
| Security schemes | Security customizer | Unique scheme names, avoids replacing map unnecessarily |
| `429` response | Rate-limit customizer | Adds only if absent or updates per agreed policy |
| Error schema | Error-contract customizer | Convention-based component names, never collides with differing structures |
| Operation extensions | Operation customizer | Uses distinct keys namespaced under `x-...` |

### Example Separating Responsibilities by Order

~~~java
@Configuration
class OpenApiConfiguration {

    @Bean
    @Order(10)
    OpenApiCustomizer ensureDocumentInfo() {
        return openApi -> {
            if (openApi.getInfo() == null) {
                openApi.setInfo(new Info());
            }

            Info info = openApi.getInfo();
            if (info.getTitle() == null) {
                info.setTitle("Catalog API");
            }
            if (info.getVersion() == null) {
                info.setVersion("1.0");
            }
        };
    }

    @Bean
    @Order(20)
    OpenApiCustomizer ensureProductionServer() {
        return openApi -> {
            String url = "https://api.example.com";
            if (openApi.getServers() == null) {
                openApi.setServers(new ArrayList<>());
            }

            boolean exists = openApi.getServers().stream()
                .anyMatch(server -> url.equals(server.getUrl()));

            if (!exists) {
                openApi.addServersItem(
                    new Server().url(url).description("Production")
                );
            }
        };
    }

    @Bean
    @Order(30)
    OpenApiCustomizer ensureRateLimitResponse() {
        return openApi -> {
            if (openApi.getPaths() == null) {
                return;
            }

            openApi.getPaths().values().forEach(pathItem ->
                pathItem.readOperations().forEach(operation -> {
                    ApiResponses responses = operation.getResponses();
                    if (responses == null) {
                        responses = new ApiResponses();
                        operation.setResponses(responses);
                    }
                    if (!responses.containsKey("429")) {
                        responses.addApiResponse(
                            "429",
                            new ApiResponse().description("Rate limit exceeded")
                        );
                    }
                })
            );
        };
    }
}
~~~

The three customizers have distinct orders and each bean handles one responsibility. `ensureDocumentInfo` only fills missing fields; `ensureProductionServer` adds a server by URL if absent; `ensureRateLimitResponse` only adds missing status codes. Consequently, if the document already has a description, server, or `429` response, the customizers do not erase them accidentally.

The example requires the corresponding imports from swagger-models and Spring. Load the server URL from application configuration instead of hardcoding production in code if the application runs across multiple environments.

In the example, `ensureRateLimitResponse` adds `429` to every traversed operation. Real applications should filter operations by annotation, policy, or endpoint group that actually has rate limiting; do not publish responses the server cannot return.

Types used in the example include `OpenAPI`, `Info`, `Server`, `ApiResponses`, `ApiResponse`, `OpenApiCustomizer`, `@Bean`, `@Configuration`, and `@Order`. Import them from `io.swagger.v3.oas.models`, `org.springdoc.core.customizers`, and the corresponding Spring packages.

### When to Consolidate Multiple Customizers into One?

If two changes must always occur together or a later step relies on data just created by an earlier step, a single customizer is often clearer:

~~~java
@Bean
OpenApiCustomizer applySharedApiPolicy() {
    return openApi -> {
        ensureDocumentInfo(openApi);
        ensureServers(openApi);
        ensureCommonResponses(openApi);
    };
}
~~~

Consolidating logic reduces reliance on bean sorting mechanisms and clarifies one place responsible for the shared policy. Do not build an oversized monolithic customizer for unrelated changes; group steps that share the same lifecycle and ownership.

The `ensureDocumentInfo`, `ensureServers`, and `ensureCommonResponses` methods in the example are application-defined helpers; their bodies are omitted to focus on organizing the chain.

## 8. Idempotency and Avoiding Shared Mutable State

An idempotent customizer is one that can run multiple times without changing the document unintentionally after the first run. Given the same input, running once or multiple times yields the exact same result.

Non-idempotent example:

~~~java
openApi.addServersItem(
    new Server().url("https://api.example.com")
);
~~~

If the customizer is called repeatedly, the server list can accumulate duplicate URLs. Similarly, repeatedly adding tags, parameters, or responses to collections can create duplicates or overwrite values under the same key.

Pre-checked version:

~~~java
boolean hasServer = openApi.getServers() != null
    && openApi.getServers().stream()
        .anyMatch(server ->
            "https://api.example.com".equals(server.getUrl())
        );

if (!hasServer) {
    openApi.addServersItem(
        new Server().url("https://api.example.com")
    );
}
~~~

Operations that commonly need upserts or duplicate checks:

- Server: identified by URL.
- Tag: identified by name.
- Parameter: identified by `name` and `in`.
- Response: identified by status code.
- Schema: identified by component name.
- Security scheme: identified by scheme name.
- Extension: identified by key.

### Do Not Store Mutable OpenAPI Models in Shared Fields

Customizers are typically singleton beans. Do not store `OpenAPI`, `Operation`, `ApiResponses`, or mutable collections across runs in static or instance fields for reuse. Documents for other groups or subsequent builds can be corrupted by stale state.

Avoid:

~~~java
@Component
class UnsafeCustomizer implements OpenApiCustomizer {
    private final List<String> seenPaths = new ArrayList<>();

    @Override
    public void customise(OpenAPI openApi) {
        // seenPaths retains state across multiple documentation builds.
    }
}
~~~

Create temporary collections per invocation and operate directly on the passed-in OpenAPI instance:

~~~java
@Component
class SafeCustomizer implements OpenApiCustomizer {

    @Override
    public void customise(OpenAPI openApi) {
        Set<String> currentPaths =
            new LinkedHashSet<>(openApi.getPaths().keySet());

        // Process currentPaths within the scope of this invocation.
    }
}
~~~

Additionally:

- Do not generate random values or fresh timestamps each time a customizer runs unless they belong to the contract.
- Do not call network services or databases from a customizer to build documentation when configuration can be placed in application properties.
- Do not depend on iteration order of unordered collections if deterministic output is required.
- Do not mutate annotations or controller metadata directly from a customizer.

### Idempotency Does Not Mean Overwriting Is Forbidden

A customizer can intentionally set `info.version` to a configured value and still remain idempotent because running it multiple times yields the same result. What matters is that overwriting behavior is deliberate, has clear ownership, and does not depend on transient state from previous runs.

## 9. Customizers with GroupedOpenApi

An application can generate multiple documents, such as public, admin, and partner. Each group has its own paths, operations, and metadata:

~~~java
@Bean
GroupedOpenApi publicApi() {
    return GroupedOpenApi.builder()
        .group("public")
        .pathsToMatch("/api/public/**")
        .addOpenApiCustomizer(openApi ->
            openApi.getInfo().setTitle("Public API")
        )
        .build();
}
~~~

Attaching a customizer directly to the group builder is appropriate when changes apply only to that group. For example, the public group has its own title, while the admin group has its own servers or tags. `GroupedOpenApi` belongs to `org.springdoc.core.models` in springdoc 2.x.

For policies shared across all groups, consider `GlobalOpenApiCustomizer` or `GlobalOperationCustomizer` depending on your springdoc version. Distinguish clearly:

- `OpenApiCustomizer`: default document-level customizer; group scope must be verified by version.
- `GlobalOpenApiCustomizer`: for document-level changes applying across groups as supported by springdoc.
- `GroupedOpenApi.builder().addOpenApiCustomizer(...)`: attaches a customizer specifically to one group.

Do not register the same change in both a global customizer and a group customizer without idempotency checks. If both add a server or response, results can be duplicated or overwritten.

### Prevent Group Customizers from Erasing Global Results

Suppose a global customizer adds two servers, while the public group's customizer calls `setServers(List.of(publicServer))`. The group's output may end up with only one server. If the intent is only to add the public server, upsert by URL; if the intent is to replace the entire list, document that as the group's server ownership policy.

Ordering between global customizers and group-attached customizers depends on the springdoc version's pipeline. If a group's output requires a specific order, verify the `/v3/api-docs/{group}` endpoint with integration tests instead of relying on assumptions.

## 10. Testing Ordering and Final Output

Test at two levels:

1. Unit tests for transformation logic on a small OpenAPI object.
2. Integration tests calling the `/v3/api-docs` endpoint to verify springdoc applies customizers properly in a real application context.

### Unit Testing Customizers

~~~java
class DocumentCustomizerTest {

    @Test
    void fillsMissingInfoWithoutReplacingExistingDescription() {
        OpenAPI openApi = new OpenAPI()
            .info(new Info().description("Existing description"));

        OpenApiCustomizer customizer = openApiDocument -> {
            if (openApiDocument.getInfo() == null) {
                openApiDocument.setInfo(new Info());
            }
            Info info = openApiDocument.getInfo();
            if (info.getTitle() == null) {
                info.setTitle("Catalog API");
            }
            if (info.getVersion() == null) {
                info.setVersion("1.0");
            }
        };

        customizer.customise(openApi);
        customizer.customise(openApi);

        assertEquals("Catalog API", openApi.getInfo().getTitle());
        assertEquals("1.0", openApi.getInfo().getVersion());
        assertEquals("Existing description", openApi.getInfo().getDescription());
    }
}
~~~

The test invokes the customizer twice to verify idempotency while ensuring the existing description is preserved. The example assumes JUnit, `assertEquals`, `OpenAPI`, `Info`, and `OpenApiCustomizer` imports. If your project uses an interface version with a different callback name, adjust the call to match your dependency API.

### Integration Testing the Final OpenAPI Output

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class OpenApiCustomizationIntegrationTest {

    @Autowired
    MockMvc mockMvc;

    @Test
    void appliesDocumentCustomizersInExpectedOrder() throws Exception {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.info.title").value("Catalog API"))
            .andExpect(jsonPath("$.info.version").value("1.0"))
            .andExpect(jsonPath("$.servers[0].url")
                .value("https://api.example.com"));
    }
}
~~~

Assertion values must match the application's test configuration. The example assumes `SpringBootTest`, `AutoConfigureMockMvc`, `Autowired`, `MockMvc`, `Test`, request/result matchers, and `get` imports. If the server URL comes from a profile or property, set explicit test values so outcomes do not depend on the execution environment.

### Checking That Responses Are Not Overwritten

If a customizer adds a `429` response, verify:

- The original `200` response remains intact.
- Any `400` response declared by the controller remains intact.
- The `429` response has the expected description/content.
- If a `429` response was already explicitly declared, the preserve-or-replace policy behaves properly.

Do not merely check that the `429` key exists; also check schema, media type, headers, and description if those fields belong to the contract.

### Checking Every Group

If the application has groups, test each group endpoint separately:

~~~java
mockMvc.perform(get("/v3/api-docs/public"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.info.title").value("Public API"));

mockMvc.perform(get("/v3/api-docs/admin"))
    .andExpect(status().isOk())
    .andExpect(jsonPath("$.info.title").value("Admin API"));
~~~

Ensure shared customizers apply properly to both groups and group-specific customizers do not wipe out shared metadata.

## 11. Diagnosing Incorrect Order or Output

When OpenAPI JSON is not as expected, trace the data from source to output:

1. Check whether controller annotations and return types produce the expected initial operation/response.
2. Confirm customizer beans are registered in the application context and profile/property conditions are met.
3. Identify which pipeline each customizer belongs to: operation, default document, global, or specific group.
4. Locate every call to setters or writes to the same map/list key where data is being lost.
5. Check whether `@Order` is applied within the right collection and uses distinct values.
6. Request the exact default documentation endpoint or group endpoint.
7. Check results after restarting or clearing documentation caches.

### Symptoms and Causes

| Symptom | Common Cause | How to Check |
|---|---|---|
| Title or version vanishes | Another customizer calls `setInfo(new Info())` afterward | Search all `setInfo` calls and check ordering |
| Server URL disappears | A later customizer calls `setServers` | Find places replacing the entire server list |
| Error response is lost | Customizer replaces `ApiResponses` or writes the same status code | Inspect responses map before and after each step |
| Duplicate tags/servers/parameters | Customizer appends without checking first | Check idempotency and identifying keys |
| Security scheme present yet operations do not require it | Scheme was added only to components without matching security requirements | Inspect root and operation security |
| Customizer runs on default document but not groups | Using a customizer without group scope | Use global or attach customizer to GroupedOpenApi |
| `@Order` does not produce expected order | Beans belong to different pipelines or share identical orders | Check customizer types and assign distinct orders |
| Code changed yet JSON stays stale | Document is cached or hitting wrong group/instance | Restart, check cache settings, and verify endpoint |
| Wrong schema or `$ref` | Two customizers use the same component name | Inspect `components.schemas` and all `$ref`s |

### Checking Document Cache

springdoc can cache generated documents to avoid re-analyzing controllers repeatedly. When diagnosing customizer changes, restart the application and re-fetch the documentation endpoint. You can temporarily disable caching via configuration:

~~~yaml
springdoc:
  cache:
    disabled: true
~~~

Use this setting only for diagnostics or when there is a clear operational reason. Disabling cache can increase document generation cost; do not ship debug settings to production without evaluating impact.

### Finding All Writes to the Same Property

When a property is overwritten, search the entire codebase for related setters, such as:

~~~text
setInfo(
setServers(
setResponses(
setSecurity(
setTags(
setSchemas(
setExtensions(
~~~

Then tabulate the order and write sources. For conditional customizers, check profiles, properties, and groups to see which branches actually execute. Do not rely solely on `@Bean` method declaration order; verify callback ordering in the pipeline.

## 12. Safety Rules When Modifying the OpenAPI Model

Before mutating the model, apply these rules:

- Check for null before accessing child objects like `info`, `servers`, `paths`, `responses`, or `components`.
- For lists, check for duplicates by business key rather than object identity alone.
- For maps, remember that writing the same key overwrites the previous value.
- When updating a single property, mutate that property instead of recreating the entire parent object.
- When replacing an entire collection, establish clearly which customizer owns the collection and which entries may be dropped.
- Do not share the same mutable model across groups.
- Do not modify existing responses or schemas without checking controller annotations and other customizers.
- Prefix extension names with `x-` and use distinct namespaces to avoid key collisions.

### Preserving Existing Data

Example helper to add a tag if missing:

~~~java
private void addTagIfMissing(OpenAPI openApi, String name, String description) {
    if (openApi.getTags() == null) {
        openApi.setTags(new ArrayList<>());
    }

    boolean exists = openApi.getTags().stream()
        .anyMatch(tag -> name.equals(tag.getName()));

    if (!exists) {
        openApi.addTagsItem(
            new Tag().name(name).description(description)
        );
    }
}
~~~

This helper uses the tag name as the key. If a tag already exists yet its description needs updating, write a dedicated policy instead of appending a second tag with the same name.

Example adding a parameter if missing:

~~~java
private void addHeaderIfMissing(Operation operation, Parameter header) {
    if (operation.getParameters() == null) {
        operation.setParameters(new ArrayList<>());
    }

    boolean exists = operation.getParameters().stream()
        .anyMatch(existing ->
            Objects.equals(header.getName(), existing.getName())
                && Objects.equals(header.getIn(), existing.getIn())
        );

    if (!exists) {
        operation.addParametersItem(header);
    }
}
~~~

Parameters are identified by the `(name, in)` pair, since the same name can appear in query, header, path, or cookie. The example uses `Objects.equals` for safe comparison when a value is unset; import `java.util.Objects`. If a parameter already exists at the path level, consider path-level parameters before adding an operation-level parameter.

## 13. Comprehensive Practice Exercise

Build a Spring Boot application with a default document and two groups: `public` and `admin`. Create these customizers:

1. A metadata customizer that fills in title and version if missing.
2. A server customizer that adds a URL from environment configuration without creating duplicates.
3. A security customizer that adds a shared security scheme while preserving existing schemes.
4. A response customizer that adds a `429` response if the operation lacks one.
5. An operation customizer that adds an `x-owner` extension from handler method metadata.
6. Group customizers setting distinct titles for public and admin.
7. Assign distinct orders to customizers in the same pipeline and document the reason for the ordering.
8. Create an experimental customizer calling `setInfo(new Info())` to observe lost metadata, then fix it by updating individual properties.
9. Call `/v3/api-docs`, `/v3/api-docs/public`, and `/v3/api-docs/admin` to compare scopes.
10. Invoke customizers multiple times in unit tests to verify no duplicate servers, tags, or responses are generated.
11. Write integration tests confirming final title, servers, security, responses, and extensions.
12. Temporarily disable caching if needed for diagnostics and re-verify output after re-enabling caching.

### Completion Criteria

- [ ] Can distinguish operation customizers from document customizers.
- [ ] Knows which customizers apply to the default document, globally, and per group.
- [ ] Uses `@Order`/`Ordered` within the right pipeline without confusing it with bean initialization order.
- [ ] Can demonstrate how setters replace existing data and `add` helpers can cause duplicates or overwrite keys.
- [ ] Preserves metadata by updating specific properties.
- [ ] Responses, security, tags, servers, and schemas are not unintentionally overwritten.
- [ ] Customizers are idempotent and hold no mutable state across invocations.
- [ ] OpenAPI JSON of every group has the expected content.
- [ ] Integration tests catch ordering changes or customizer conflicts.

## Continuing Study

After this lesson, combine customizers with schema converters, operation filters, grouped documentation, and contract testing. Whenever adding a new customizer, document its extension point, group scope, order, owned data, and policy when keys already exist. That keeps OpenAPI documentation predictable as the application evolves.
