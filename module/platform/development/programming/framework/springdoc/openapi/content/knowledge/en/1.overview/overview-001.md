# What Is Springdoc OpenAPI and How Does It Solve the API Documentation Problem?

## 1. The Problem: An API Can Work Correctly While Its Documentation Is Wrong

In a Spring Boot application, controllers, DTOs, and security configurations form the contract that clients must follow. This contract answers specific questions:

- What endpoints exist, which HTTP methods do they use, and what parameters do they accept?
- What is the structure of the request body? Which fields are required, and which have constraints?
- What do successful responses and error responses look like?
- What authentication or permissions does an endpoint require?
- Which functional group or version does an API belong to?

If a development team writes documentation manually in a wiki or a separate file, the documentation easily drifts out of sync with the source code. An endpoint gets renamed without updating the docs, a new DTO field appears while request examples remain outdated, or an error response changes without notifying clients. Integrators end up reading the source code, asking the backend team, or testing individual requests to figure out how the API works.

Therefore, API documentation needs to be generated and maintained close to where the API is defined. With Spring Boot, **springdoc-openapi** helps accomplish this by collecting information from the application, generating an OpenAPI specification, and providing a Swagger UI interface for people to explore and try calling endpoints.

## 2. What Is Springdoc OpenAPI?

**Springdoc OpenAPI** is a library that integrates with the Spring ecosystem to automatically generate documentation following the **OpenAPI** standard from APIs declared in a Spring Boot application. The library reads Spring MVC or Spring WebFlux mapping metadata, parameter and return types, and additional descriptive annotations to build the API specification.

You can view the solution through three components:

1. **The Spring Boot application** is the source of truth for endpoints, parameters, DTOs, validation, and security configuration.
2. **The OpenAPI document** is a structured API description, usually exported as JSON or YAML. Machines can read this document to generate clients, validate contracts, or integrate into development workflows.
3. **Swagger UI** is a web interface that renders the OpenAPI document. Users can inspect endpoints, schemas, and parameters, and send test requests directly in the browser if the environment allows.

OpenAPI is a language- and framework-agnostic specification. Swagger is the name of an ecosystem of tools that work with that specification; Swagger UI is a popular interface for displaying the documentation. Springdoc acts as the bridge between a Spring application and the OpenAPI specification.

Springdoc does not replace controllers, DTOs, or business logic. It describes what the application exposes. If the source code lacks descriptions of business semantics, authorization rules, or error cases, the auto-generated documentation may also be insufficiently clear. In those cases, developers need to add descriptive annotations or configuration.

## 3. How Does Springdoc Solve the Problem?

### 3.1. Auto-Discovering Endpoints from Spring

Spring MVC and Spring WebFlux already carry metadata about routes declared with annotations such as:

- **@RestController** and **@Controller**;
- **@RequestMapping**, **@GetMapping**, **@PostMapping**, **@PutMapping**, **@DeleteMapping**;
- **@PathVariable**, **@RequestParam**, **@RequestHeader**, and **@RequestBody**.

Springdoc uses the application's metadata to determine paths, HTTP methods, parameters, and input/output data types. As a result, when an endpoint is added or changed in a controller, the documentation can reflect that change once the application is restarted or updated.

For example, from the declaration:

~~~java
@GetMapping("/{id}")
public ProductResponse findById(@PathVariable Long id) {
    // Find the product and return the result
    return null; // Replace with the result from the service in a real application
}
~~~

Springdoc can identify a GET endpoint with a path containing the **id** variable, while inferring the parameter type and response type from the method signature.

### 3.2. Inferring Schemas from Data Types

Request and response classes are typically converted into schemas under the **components.schemas** section of the OpenAPI document. Springdoc relies on Java types, property structures, and relevant annotations to describe schemas.

For example:

~~~java
public record CreateProductRequest(
    @NotBlank
    @Schema(description = "Product name", example = "Mechanical keyboard")
    String name,

    @Positive
    @Schema(description = "Product price", example = "1290000")
    BigDecimal price
) {}
~~~

From the data types and annotations, the documentation can express field names, data types, examples, and certain validation constraints. This helps clients understand the request payload to send without having to open the DTO source code.

However, inferred schemas do not fully explain business meaning on their own. For instance, a **String** type does not indicate whether a value must be a country code, an order status, or an arbitrary string. Use appropriate descriptions, examples, and constraints to clarify those cases.

### 3.3. Adding Intentional Descriptions with Annotations

Annotations in the **io.swagger.v3.oas.annotations** package let you describe information that Spring cannot infer from a method signature:

| Annotation | Purpose |
|---|---|
| **@Tag** | Group controllers or endpoints by topic |
| **@Operation** | Describe the meaning, summary, and behavior of an operation |
| **@Parameter** | Describe a query, path, header, or cookie parameter |
| **@ApiResponse** | Declare a response code and returned content |
| **@Schema** | Describe a model, property, example, and constraints |
| **@SecurityRequirement** | Attach a security requirement to an operation or group of operations |
| **@Hidden** | Hide an element from the generated documentation |

Example of a clearly documented endpoint:

~~~java
@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "Product management API")
public class ProductController {

    @GetMapping("/{id}")
    @Operation(
        summary = "Get product by ID",
        description = "Returns detailed information for a single product."
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Product found",
            content = @Content(
                schema = @Schema(implementation = ProductResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Product not found",
            content = @Content
        )
    })
    public ProductResponse findById(
        @Parameter(description = "Product ID", example = "42")
        @PathVariable Long id
    ) {
        // Business logic omitted
        return null;
    }
}

@Schema(description = "Product information")
public record ProductResponse(
    @Schema(description = "Product ID", example = "42")
    Long id,

    @Schema(description = "Product name", example = "Mechanical keyboard")
    String name,

    @Schema(description = "Product price", example = "1290000")
    BigDecimal price
) {}
~~~

The snippet focuses on how to write documentation metadata; the data query implementation is omitted. In a real application, the **404** response needs to match how the application actually handles exceptions and formats errors.

## 4. Integrating Springdoc into a Spring Boot Application

### 4.1. Choosing the Right Starter

For a Spring MVC application using Swagger UI, the commonly used Maven dependency is:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>${springdoc.version}</version>
</dependency>
~~~

Here, **springdoc.version** is the version managed in the project's build configuration. If using Gradle:

~~~kotlin
implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:$springdocVersion")
~~~

Choose a Springdoc version compatible with your project's Spring Boot and Java versions according to Springdoc's compatibility matrix. Do not mix major versions arbitrarily or include multiple UI starters at the same time for the same application.

Some common choices:

- **springdoc-openapi-starter-webmvc-ui**: Spring MVC applications that need both the OpenAPI document and Swagger UI.
- **springdoc-openapi-starter-webmvc-api**: Spring MVC applications that only need the endpoint serving the OpenAPI document.
- **springdoc-openapi-starter-webflux-ui**: Spring WebFlux applications that need both the OpenAPI document and Swagger UI.
- **springdoc-openapi-starter-webflux-api**: Spring WebFlux applications that only need the OpenAPI document.

Artifact names and integration approaches can differ across Springdoc generations. When upgrading an older project, check the migration guide for the version being used instead of just changing the dependency version number.

### 4.2. Running the Application and Checking Documentation Endpoints

After adding the starter and starting the application, the common default paths are:

| Path | Content |
|---|---|
| **/v3/api-docs** | OpenAPI document in JSON format |
| **/v3/api-docs.yaml** | OpenAPI document in YAML format |
| **/swagger-ui.html** | Swagger UI entry point, usually redirects to the UI |

If the application has a context path, runs behind a reverse proxy, or overrides default settings, the actual paths may differ. Check the deployment configuration and startup logs when the URLs above are unreachable.

You can quickly inspect the JSON using a browser or an HTTP command:

~~~bash
curl http://localhost:8080/v3/api-docs
~~~

If you receive JSON containing sections such as **openapi**, **info**, **paths**, and **components**, the application is serving the OpenAPI documentation. If Swagger UI is included, open **/swagger-ui.html** to view endpoints grouped by tags and try calling the API.

### 4.3. Configuring Paths and the UI

Several settings can be customized via **application.yml**:

~~~yaml
springdoc:
  api-docs:
    path: /api-docs
  swagger-ui:
    path: /docs
    operationsSorter: method
    tagsSorter: alpha
    displayRequestDuration: true
~~~

With this configuration, the OpenAPI JSON resides at **/api-docs**, and Swagger UI is accessed via **/docs**. Configuration property names must match the Springdoc version the application is using.

Do not blindly enable documentation or Swagger UI in every environment. In production, the development team needs to decide whether documentation should be public or protected by authentication, an internal network, or a gateway.

## 5. Customizing General Document Information

Information such as the API title, contract version, and general description can be declared with an **OpenAPI** bean:

~~~java
@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI shopOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Shop API")
                .version("v1")
                .description("API for managing products and orders."));
    }
}
~~~

This information appears in the **info** section of the OpenAPI document and is displayed by Swagger UI. The **version** value here is the version of the published API contract; it does not necessarily match the application's release version.

You can add contact details, license info, server URLs, or external documentation when needed. Across multiple environments, ensure the server URL reflects the actual address reachable by clients. Avoid hardcoding localhost addresses into released documentation.

## 6. Describing Security So Clients Know How to Call the API

If the API uses JWT Bearer tokens, you can declare a security scheme with an annotation:

~~~java
@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class OpenApiSecurityConfiguration {
}
~~~

Then attach the security requirement to a controller or operation:

~~~java
@RestController
@RequestMapping("/api/orders")
@SecurityRequirement(name = "bearerAuth")
@Tag(name = "Orders", description = "Order management API")
public class OrderController {
    // Order endpoints
}
~~~

When the scheme is properly declared and linked, the OpenAPI document reflects the Bearer authentication mechanism; Swagger UI can provide an Authorize button for users to enter a token when testing API calls.

Declaring a security scheme only describes the contract. It does not automatically enable authentication in Spring Security, generate JWTs, or replace authorization configuration. The application must still enforce security at the appropriate layer.

You must also distinguish between the security of the API itself and the security of the documentation pages. If Spring Security blocks **/v3/api-docs/** or **/swagger-ui/**, Swagger UI may fail to load the documentation. The development team needs to configure access rules for these paths according to the environment's policy: allow public access, require login, or restrict to an internal network.

## 7. Splitting Documentation into Multiple API Groups

A large application may contain APIs for administration, customers, products, and internal integrations. Putting all endpoints into a single document makes it difficult for readers to find the parts they need.

Springdoc supports creating groups using **GroupedOpenApi**. For example:

~~~java
@Configuration
public class OpenApiGroupsConfiguration {

    @Bean
    public GroupedOpenApi catalogApi() {
        return GroupedOpenApi.builder()
            .group("catalog")
            .pathsToMatch("/api/products/**", "/api/categories/**")
            .build();
    }

    @Bean
    public GroupedOpenApi orderApi() {
        return GroupedOpenApi.builder()
            .group("orders")
            .pathsToMatch("/api/orders/**")
            .build();
    }
}
~~~

Each group can be accessed through its corresponding documentation endpoint, such as **/v3/api-docs/catalog** and **/v3/api-docs/orders** with default paths. Swagger UI can display a dropdown list of groups so users can select which document to view.

API groups are useful when:

- One application serves multiple client audiences with different access scopes.
- Public documentation needs to be separated from internal endpoints.
- The development team wants to publish documentation by bounded context or API version.
- The release process needs to inspect each contract separately.

Grouping documentation does not automatically create a security boundary. If internal endpoints remain deployed and reachable, access control must still be enforced at the application or infrastructure layer.

## 8. Documentation Details That Need Care

Auto-generating OpenAPI reduces repetitive work, yet documentation quality still depends on how the API is designed and described.

**Requests and parameters:** Clarify whether a parameter belongs in path, query, header, or body; document data types, formats, example values, and whether it is required. For DTOs, use Bean Validation to express verifiable constraints and use **@Schema** to add semantic meaning.

**Responses:** Describe success responses, empty responses if any, and errors meaningful to clients such as 400, 401, 403, 404, or 409. Do not assume Springdoc always infers every error response completely from **@ControllerAdvice**; explicitly declare important responses and shared error schemas.

**Enums and sample values:** Provide descriptions or examples for statuses, payment method types, and fields with a restricted set of values. Clients need to know the meaning of each value, not just that the field is a string type.

**Pagination and sorting:** Explain conventions for page, size, sort, default ordering, and result metadata structure. Parameters inferred by the framework may still need business descriptions.

**Operations and tags:** Choose clear summary names, group endpoints by function, and avoid forcing readers to guess from Java method names.

**Unpublished endpoints:** Use **@Hidden** or appropriate filtering configuration when an endpoint falls outside the documentation scope. Hiding an endpoint from OpenAPI does not replace access control.

## 9. From the OpenAPI Document to Contract Testing

The OpenAPI document does not only serve human readers. Because it is structured data, it can participate in the development pipeline:

1. **Client SDK generation:** OpenAPI-compatible tools can generate client code for Java, TypeScript, or other languages.
2. **Contract testing:** Pipelines can validate that the document is valid, endpoints have required response schemas, and sample requests conform to the contract.
3. **Breaking-change detection:** Compare the current branch's OpenAPI document against a released version to detect deleted endpoints, changed field types, or altered responses.
4. **Documentation distribution:** Store JSON/YAML as a build artifact, publish to a developer portal, or distribute to integration teams.
5. **Version management:** Use the version in **info**, URL versioning, or documentation groups to clarify which contracts are supported.

A practical workflow can fetch **/v3/api-docs** from the started application in a test environment, validate the document using an OpenAPI tool, and compare it against the documentation from the latest release. You must clearly choose a canonical source of truth: documentation generated from the exact configuration and exact application version the team intends to release.

Springdoc does not automatically guarantee that the API complies with its documentation. An endpoint might be documented to return 200 while the actual logic returns 500; a schema might have the right types while having the wrong business semantics. Therefore, auto-generated documentation must be combined with integration tests, contract tests, and API change reviews.

## 10. Common Integration Issues

| Symptom | Causes to Check |
|---|---|
| Endpoints missing from Swagger UI | Controller outside component scan scope; endpoint filtered out by path/package configuration; endpoint hidden; application failed to load mappings |
| **/v3/api-docs** returns 404 | Wrong starter; API docs disabled or path changed; context path or reverse proxy configuration incorrect |
| Swagger UI fails to load JSON | UI and API docs paths do not match; Spring Security blocks the request; proxy does not forward the prefix properly |
| Schema missing fields or wrong types | DTO uses custom types, generics, or special serializers; check how Jackson and Springdoc interpret the model and add **@Schema** when needed |
| Documentation shows wrong server URL | Application runs behind a proxy or across multiple environments without properly configured forwarded headers/server info |
| Missing error responses | **@ApiResponse** not explicitly declared; actual exception handlers not described in OpenAPI |
| Incompatibility after upgrading | Spring Boot, Java, and Springdoc versions mismatch; consult the compatibility matrix and migration guide |

When troubleshooting, check dependencies and versions, startup logs, the OpenAPI JSON endpoint, filter configurations, Spring Security, and reverse proxy settings in order. JSON is a useful diagnostic source: if an endpoint already appears in the JSON but does not render as expected in the UI, the issue likely lies in the UI or display configuration.

## 11. Adoption Workflow in a Project

Adoption can start with a small scope:

1. Choose a starter compatible with the Spring Boot version and web model in use.
2. Start the application and inspect the OpenAPI JSON and Swagger UI.
3. Add **@Tag**, **@Operation**, **@Schema**, and responses for key endpoints.
4. Declare general info, security schemes, and documentation groups if the project needs them.
5. Verify documentation under settings close to the deployment environment, including context path, proxy, and Spring Security.
6. Add OpenAPI document validation to CI; treat documentation changes as part of API contract reviews.
7. Distribute the matching documentation version alongside releases and communicate changes that affect clients.

There is no need to annotate every line of code. Prioritize information that helps API consumers construct valid requests, understand responses, and handle errors. The goal is documentation clear enough that another team can integrate without reading deep into the implementation.

## 12. Conclusion

Springdoc OpenAPI helps Spring Boot applications publish API contracts following the OpenAPI standard and display those contracts via Swagger UI. The library leverages mappings, data types, and annotations in the application to reduce drift between source code and documentation. When enriched with descriptions of requests, responses, security, API groups, and versioning, the documentation can serve developers, integrating clients, and testing pipelines alike.

The value of Springdoc does not lie in merely producing a Swagger UI page. The greater value is bringing API documentation into the software development lifecycle: endpoint changes drive contract changes, contracts are verified before release, and integration teams have a consistent source of truth to work from.

