# Learning Path from Your First API to Contract Verification and Release

A Spring Boot API can work properly yet remain difficult to integrate if users do not know which endpoints exist, what data structure to send, what status codes they will receive, and how to authenticate. **API contracts** solve that problem through a structured, machine-readable description shared across development, testing, operations, and integration teams.

In the Spring ecosystem, **springdoc-openapi** analyzes Spring MVC or Spring WebFlux endpoints along with annotated metadata to generate an OpenAPI specification. The tool can serve JSON/YAML specifications and a Swagger UI interface for humans to explore and try calling the API. The roadmap below progresses from a simple controller to contract verification, version management, and distribution in a release pipeline.

## Learning Outcomes

After completing this roadmap, you will be able to:

- Integrate springdoc-openapi matching your Spring Boot version and web application model.
- Read and customize OpenAPI documents generated from controllers, DTOs, and annotations.
- Clearly describe requests, responses, errors, schemas, examples, and security mechanisms.
- Split documentation into API groups, customize metadata, and export documentation in JSON or YAML.
- Verify that documentation is valid and accurately reflects API behavior.
- Manage contract versions and incorporate verified documentation into release workflows.

## Roadmap Overview

~~~mermaid
flowchart TD
    A["First Spring Boot API"] --> B["Integrate springdoc-openapi"]
    B --> C["Generate OpenAPI and open Swagger UI"]
    C --> D["Describe requests, responses, and schemas"]
    D --> E["Add errors and security"]
    E --> F["Group and customize documentation"]
    F --> G["Export JSON/YAML"]
    G --> H["Verify validity and conformance"]
    H --> I["Manage versions and releases"]
~~~

Each stage should produce a verifiable artifact. Do not start by adding dozens of annotations: first understand where documentation is generated from, then add descriptions where source code cannot fully express contract semantics.

## 1. Start with a Spring Boot API

Choose a small REST application with at least one endpoint that reads data and one endpoint that accepts data. For example, a product management API might provide:

| Method | Path | Purpose |
|---|---|---|
| GET | /api/products/{id} | Retrieve a single product |
| GET | /api/products | Search or list products |
| POST | /api/products | Create a product |

Before integrating springdoc-openapi, understand the basic Spring components:

- Controllers declare HTTP entry points with annotations such as @RestController, @RequestMapping, @GetMapping, and @PostMapping.
- DTOs define input and output data structures. DTOs keep the API contract more stable than exposing database entities directly.
- Bean Validation expresses data constraints such as required, length, email format, or minimum value.
- Security configuration decides which endpoints require authentication and which permissions are allowed access.

Run and test the API using an HTTP client or integration tests first. Knowing actual behavior gives you a baseline to verify generated documentation against.

## 2. Integrate springdoc-openapi

Choose the starter matching your application model:

| Application | Common Starter |
|---|---|
| Spring MVC | springdoc-openapi-starter-webmvc-ui |
| Spring WebFlux | springdoc-openapi-starter-webflux-ui |

With Spring Boot 3 and Maven, the MVC dependency can be declared as follows. Replace the version property value with a springdoc version compatible with your project's Spring Boot version per springdoc-openapi's compatibility matrix.

~~~xml
<properties>
    <springdoc.version>YOUR_COMPATIBLE_VERSION</springdoc.version>
</properties>

<dependencies>
    <dependency>
        <groupId>org.springdoc</groupId>
        <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
        <version>${springdoc.version}</version>
    </dependency>
</dependencies>
~~~

WebFlux applications use the corresponding WebFlux starter. Do not add both starters simultaneously just for testing; use the starter matching your application's web stack. For Spring Boot 2 projects or projects using older springdoc lines, artifact names and configuration may differ. Always consult the migration guide and compatibility matrix for the exact major version before upgrading.

Start the application and check the default addresses:

| Resource | Default Address |
|---|---|
| OpenAPI specification in JSON | /v3/api-docs |
| OpenAPI specification in YAML | /v3/api-docs.yaml |
| Swagger UI | /swagger-ui.html |

Paths can be changed via configuration. For example:

~~~yaml
springdoc:
  api-docs:
    path: /internal/openapi
  swagger-ui:
    path: /docs
~~~

When changing paths, verify both the JSON/YAML endpoints and the Swagger UI page. Do not assume the UI and specification endpoint always share the same URL.

At this stage, documentation is already auto-generated from controllers. This is a good starting point, yet not necessarily a sufficiently clear contract: parameter names, business meaning, examples, and error cases usually need additional descriptions.

## 3. Understand OpenAPI and Swagger UI

OpenAPI is a specification format describing an HTTP API. The document typically contains these information groups:

- **info**: API name, description, and version.
- **servers**: server addresses clients can call.
- **paths**: paths and HTTP operations.
- **parameters**: parameters in path, query, header, or cookie.
- **requestBody**: structure of submitted data.
- **responses**: possible responses returned.
- **components**: schemas, security schemes, and reusable components.

springdoc-openapi handles generating the specification from a Spring application. Swagger UI reads that specification and renders an interactive interface. The two concepts are related yet not synonymous: you can publish an OpenAPI file for other tools to consume without publishing Swagger UI.

A good OpenAPI document lets integrators quickly answer key questions: which URL to call, which method to use, which fields are required, what format data has, what success and failure return, and what authentication credentials to send.

## 4. Describe Operations, Requests, and Responses

Springdoc can infer much information from controller signatures and Java data types. Use OpenAPI annotations to add semantics that source code does not express.

DTO example:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

@Schema(description = "Required information to create a product")
public record CreateProductRequest(
    @NotBlank
    @Size(max = 120)
    @Schema(description = "Product name", example = "Mechanical keyboard")
    String name,

    @Positive
    @Schema(description = "Selling price, in the store's currency",
            example = "1250000")
    long price
) {}
~~~

Controller example:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.tags.Tag;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/products")
@Tag(name = "Products", description = "Product management")
public class ProductController {

    @GetMapping("/{id}")
    @Operation(
        summary = "Get product by ID",
        description = "Returns product information if the ID exists."
    )
    @ApiResponse(responseCode = "200", description = "Product found")
    @ApiResponse(responseCode = "404", description = "Product not found")
    public ProductResponse getById(
        @Parameter(description = "Product ID", example = "42")
        @PathVariable long id
    ) {
        // Call the service and return the DTO.
        return productService.getById(id);
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    @Operation(summary = "Create a new product")
    @ApiResponse(responseCode = "201", description = "Created successfully")
    @ApiResponse(
        responseCode = "400",
        description = "Invalid input data",
        content = @Content(
            schema = @Schema(implementation = ApiError.class)
        )
    )
    public ProductResponse create(@Valid @RequestBody CreateProductRequest request) {
        return productService.create(request);
    }
}
~~~

The snippet illustrates how to add descriptions; replace ProductResponse, ApiError, and productService with your application's actual data types and service.

When writing descriptions, pay attention to:

1. **Path parameters** identify a specific resource, usually as part of the URL. For example: id in /api/products/{id}.
2. **Query parameters** are typically used for filtering, pagination, or sorting. State default values, value ranges, and how filters combine.
3. **Header parameters** carry control info or request context. Do not document secret tokens as ordinary parameters; declare a security scheme instead.
4. **Request bodies** must specify schema, required fields, bounds, and valid examples.
5. **Responses** must document HTTP codes, returned schemas, and trigger conditions.

Common annotations:

| Annotation | Role |
|---|---|
| @Tag | Groups related operations in documentation |
| @Operation | Describes an API operation |
| @Parameter | Supplements information for a parameter |
| @ApiResponse and @ApiResponses | Describes responses |
| @Schema | Describes a schema or property |
| @ExampleObject | Provides request/response examples |
| @io.swagger.v3.oas.annotations.parameters.RequestBody | Describes request content in OpenAPI; differs from Spring's @RequestBody used for HTTP data binding |

Spring annotations control how the application receives and handles requests. OpenAPI annotations add descriptions for the contract. Do not confuse these two roles, nor repeat annotations when springdoc already infers accurate information from source code.

## 5. Describe Schemas and Data Rules

Schemas form the foundation for clients to know data structures. A clear schema should answer:

- What data type does the property have: string, integer, number, boolean, array, or object?
- Is the property required?
- What length limits, numeric bounds, or formats apply to values?
- Which valid values does an enum have?
- What is the property's business meaning and typical example?

Prefer separate DTOs for requests and responses. For example, a create-product request need not contain a server-generated id; the response can include id, creation timestamp, and status. Sharing a single entity for all data directions easily exposes internal fields or unintentionally alters the contract when storage structures change.

Bean Validation such as @NotNull, @NotBlank, @Size, @Min, @Max, and @Email can feed additional details into schemas. However, inspect the generated specification to ensure constraints appear as expected. Complex business rules in services usually cannot be inferred from Java types or validation annotations; document them through text and examples.

For special data types, check OpenAPI formats, date-time timezones, decimal precision, and how null values are represented. For example, timestamp fields should consistently use ISO 8601 and explicitly specify whether they carry an offset or UTC indicator.

## 6. Standardize Errors and Document Security

A contract that only documents success responses makes it hard for clients to handle real-world conditions. List possible errors per operation, for instance:

| HTTP Code | Common Meaning | Information to Document |
|---|---|---|
| 400 | Malformed request or validation violation | Invalid fields and messages |
| 401 | Unauthenticated or invalid credentials | How to provide credentials |
| 403 | Authenticated yet insufficient permissions | Access permission conditions |
| 404 | Resource not found | Relevant resource or identifier |
| 409 | State or data conflict | Conflict condition |
| 500 | Unexpected server error | Support reference ID without leaking internal details |

If the application uses a shared error structure, document that schema and reuse it across responses. You can use @ApiResponse on each operation or OpenAPI customization mechanisms to add shared responses. Having @ControllerAdvice does not automatically guarantee all error responses are fully documented in the contract; inspect documentation after configuring error handling.

For APIs using bearer tokens, declare a security scheme in OpenAPI so Swagger UI and clients understand how to authenticate:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import org.springframework.context.annotation.Configuration;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
@SecurityRequirement(name = "bearerAuth")
public class OpenApiSecurityConfig {
}
~~~

@SecurityRequirement can be placed at the class or operation level depending on the scope requiring protection in documentation. For OAuth2 or OpenID Connect, declare flows and corresponding scopes rather than vaguely stating "uses token".

A security scheme only describes how clients authenticate. It **does not enable endpoint security**, replace Spring Security, or grant access permissions. Enforcement rules must still be configured and tested in the application.

## 7. Customize Metadata and Split Documentation into Groups

Metadata helps users identify the right contract. It can be declared with @OpenAPIDefinition or an OpenAPI bean:

~~~java
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.info.Contact;
import io.swagger.v3.oas.models.info.Info;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    OpenAPI productApi() {
        return new OpenAPI().info(new Info()
            .title("Product API")
            .description("API for managing categories and products")
            .version("1.0.0")
            .contact(new Contact()
                .name("API Support")
                .email("api-support@example.com")));
    }
}
~~~

Replace illustrative contact details with your organization's real support address before release. The version in info.version is the API contract version managed by the project team; it differs from the OpenAPI specification version found in the openapi field of the generated document.

When an application has multiple endpoint groups, split documentation using GroupedOpenApi. The following example illustrates configuring a public group:

~~~java
import org.springdoc.core.models.GroupedOpenApi;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class ApiGroupsConfig {

    @Bean
    GroupedOpenApi publicApi() {
        return GroupedOpenApi.builder()
            .group("public")
            .pathsToMatch("/api/**")
            .build();
    }
}
~~~

The package for GroupedOpenApi may differ across springdoc major versions; use imports matching your project's version. You can create separate groups for public, internal, or admin, combining pathsToMatch, packagesToScan, and appropriate filters. A group's specification typically follows the form /v3/api-docs/{group}, such as /v3/api-docs/public.

Grouping helps readers find the right API scope and enables audience-based documentation distribution. However, hiding a group from Swagger UI is not a security measure. If internal documentation must not be publicly accessible, control documentation endpoints with security configuration or disable them in required environments.

## 8. Export and Distribute JSON/YAML

OpenAPI JSON suits automated processing tools; YAML is often convenient for reading and pull request reviews. You can fetch them directly from the endpoints:

~~~bash
curl -H "Accept: application/json" \
  http://localhost:8080/v3/api-docs \
  -o openapi.json

curl -H "Accept: application/yaml" \
  http://localhost:8080/v3/api-docs.yaml \
  -o openapi.yaml
~~~

If the project has documentation groups, export the exact endpoint for each group. In CI, save the specification file as a build artifact tagged with the commit hash or release version. This lets you trace the exact contract that was verified and delivered to partners.

A distribution workflow typically includes: starting the application or documentation generation environment, downloading OpenAPI, validating format, archiving the artifact, and publishing to a documentation portal or approved storage. Never put tokens, passwords, customer data, or internal server addresses in public examples.

In production environments, clearly decide who may view the specification and Swagger UI. If serving documentation directly from the application is unnecessary, disable the endpoints via configuration:

~~~yaml
springdoc:
  api-docs:
    enabled: false
  swagger-ui:
    enabled: false
~~~

Another option is enabling documentation only in development or staging environments, or placing documentation endpoints behind authentication. The specific choice depends on your system's release policy.

## 9. Verify the Contract Before Release

Having /v3/api-docs return HTTP 200 only proves documentation can be generated and reached. It does not prove the document is valid, complete, or matches real API behavior.

Verify across multiple layers:

1. **Verify document generation:** call JSON/YAML endpoints in a test environment and confirm non-empty content.
2. **Verify structure:** use an OpenAPI validator or linter to catch malformed structure, missing schema references, and unmet documentation conventions.
3. **Verify content:** confirm key paths, HTTP methods, request bodies, responses, error codes, security requirements, and examples are present.
4. **Verify behavior:** send real requests for success, invalid data, missing authentication, insufficient permissions, and resource-not-found cases; check returned status codes and schemas against the contract.
5. **Verify changes:** compare the new specification against the released version to identify changes that could break clients.

For example, if OpenAPI declares POST /api/products returns 201 with ProductResponse yet the application actually returns 200 or a different structure, the contract and implementation have drifted. Similarly, if documentation marks a field optional while the server rejects requests omitting it, clients will be misled.

Minimum test scenarios for the product creation endpoint:

| Case | Outcome to Verify |
|---|---|
| Valid request | Status 201 and ProductResponse schema |
| Missing product name | Validation error code and ApiError schema |
| Invalid price value | Error code and message per convention |
| Missing token | Status 401 if endpoint requires authentication |
| Token with insufficient permissions | Status 403 if policy applies |

Put these checks into CI so contract defects are caught before release. For systems with many clients or partners, add contract tests between providers and consumers to verify critical integration assumptions.

## 10. Manage Versions and Compatible Changes

API version and OpenAPI specification version are two separate concepts:

- The specification version, such as OpenAPI 3.x, indicates which format version the document follows.
- The API version, typically set in info.version, indicates which version of the product's contract is being published.

Define a consistent versioning strategy, such as /api/v1 and /api/v2 paths, or another versioning mechanism agreed upon in the system. Create matching documentation groups so users can consult the right contract. Do not bump versions for internal changes that do not affect clients; conversely, potentially breaking changes must be evaluated and communicated upfront.

Changes requiring careful review include deleting or renaming fields, changing data types, making an optional field required, removing response codes, changing enum meanings, altering authentication mechanisms, or changing error formats. Adding a response field may be compatible for many clients yet still affect strict deserializers; evaluate against your actual client ecosystem's conventions.

Archive released OpenAPI snapshots alongside corresponding source code or build artifacts. When investigating incidents, teams can identify which contract clients integrated against instead of relying on shifting documentation in a live environment.

## 11. Common Errors and How to Handle Them

| Symptom | Possible Cause | Investigation Step |
|---|---|---|
| Missing /v3/api-docs | Missing starter, wrong starter type, or disabled via config | Check dependencies, startup logs, and springdoc configuration |
| Swagger UI fails to load | Wrong path, context path, or proxy rewrite | Open the OpenAPI endpoint directly, then check the UI URL |
| Endpoints missing from docs | Group filters, package scan, or bean conditions | Check pathsToMatch, packagesToScan, and actual mappings |
| Schema missing constraints | DTO lacks metadata or validation not recognized as expected | Inspect generated JSON and add @Schema if needed |
| Error responses missing | Responses not declared or shared descriptions not configured | Add @ApiResponse or OpenApiCustomizer |
| Authorize button misbehaves | Security scheme misdeclared or requirement scope wrong | Check components.securitySchemes and operation security |
| Docs work locally yet fail after deploy | Context path, reverse proxy, HTTPS, or environment config differs | Check public URLs, forwarded headers, and per-environment config |

When troubleshooting, treat the JSON document as the primary diagnostic source. Swagger UI is merely a presentation layer; if JSON content is already wrong, tweaking UI settings will not fix the contract.

## 12. Comprehensive Practice Exercise

Starting from a Spring Boot application with ProductController, complete the following tasks:

1. Add the springdoc starter matching Spring MVC or WebFlux.
2. Open JSON, YAML, and Swagger UI; save an initial OpenAPI snapshot.
3. Add descriptions for product retrieval, search, and creation operations.
4. Separate request/response DTOs, and declare validation, examples, and schemas.
5. Document success and error responses; standardize the error schema.
6. Declare bearer authentication if the API actually uses JWTs.
7. Create at least one documentation group and verify the group endpoint works.
8. Export JSON/YAML, run a validator, and write tests for primary request cases.
9. Compare the specification against actual behavior and fix discrepancies.
10. Save version-tagged artifacts and add validation steps into CI.

### Completion Criteria

- [ ] Every endpoint in documentation scope appears with accurate path and HTTP method.
- [ ] Requests and responses use named schemas with clear data types and examples.
- [ ] Required fields, validation constraints, and enum values are accurately documented.
- [ ] Key error codes have response schemas and trigger conditions.
- [ ] Security schemes and security requirements reflect actual authentication policies.
- [ ] JSON/YAML passes the chosen OpenAPI validator.
- [ ] Actual tests confirm the contract matches API status codes and payloads.
- [ ] Release artifacts are version-tagged and traceable.
- [ ] Production documentation access matches system policy.

## Continue Learning

After this overview, dive into each skill area: annotations and schemas for requests/responses; error handling and security schemes; GroupedOpenApi and customizers; documentation export and CI integration; compatibility testing and contract change management. As you study each topic, always cross-check three things: controller/DTO code, generated OpenAPI documentation, and real HTTP responses. Consistency across all three is the strongest sign that an API contract can be trusted and used for integration.
