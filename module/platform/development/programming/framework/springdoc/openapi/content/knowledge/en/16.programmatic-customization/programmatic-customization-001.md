# The OpenAPI Bean and Swagger Core Object Model

## 1. When Is Programmatic OpenAPI Customization in Java Needed?

Springdoc OpenAPI can inspect Spring Boot controllers, data types, and annotations to generate an OpenAPI document. For simple applications, development teams often only need to declare basic metadata and let the library infer paths, operations, parameters, request bodies, responses, and schemas.

Some scenarios require programmatic intervention:

- Centrally declaring API info, servers, tags, or security schemes.
- Supplementing metadata loaded from application configuration.
- Adding vendor extensions such as x-api-owner or x-internal.
- Adjusting individual operation descriptions based on business annotations.
- Customizing documentation specifically for a document group.
- Adding shared schemas or responses that cannot be conveniently expressed via controller annotations.
- Standardizing the document before exporting JSON/YAML or distributing it through a developer portal.

Springdoc integrates with **Swagger Core** through the OpenAPI object model. An application can create an OpenAPI bean, after which Springdoc adds operations inferred from controllers. Customizers allow modifying the model before the document is returned.

Three components should be distinguished:

1. **OpenAPI model**: Java classes representing the document structure.
2. **Springdoc customizer**: extension points for modifying the document or operations.
3. **OpenAPI annotations**: metadata placed on controllers, methods, and DTOs for Springdoc to read.

## 2. What Is the Swagger Core Object Model?

Swagger Core provides Java classes corresponding to objects in the OpenAPI Specification. These classes reside primarily in the io.swagger.v3.oas.models package.

| Java Class | Corresponding OpenAPI Object | Purpose |
|---|---|---|
| OpenAPI | OpenAPI Object | Root document |
| Info | Info Object | Title, description, version, contact, license |
| Server | Server Object | Server URL and server variables |
| Paths | Paths Object | Collection of paths |
| PathItem | Path Item Object | Methods at a single path |
| Operation | Operation Object | Description of an HTTP operation |
| Parameter | Parameter Object | Path, query, header, or cookie parameter |
| RequestBody | Request Body Object | Body sent by the client |
| ApiResponses | Responses Object | Responses keyed by status code |
| ApiResponse | Response Object | Description of an HTTP result |
| Content | Content Object | Media types and schemas |
| Schema | Schema Object | Data types and constraints |
| Components | Components Object | Reusable definitions |
| SecurityScheme | Security Scheme Object | Authentication mechanism |
| Tag | Tag Object | Group of operations |

These models are Java objects that can be instantiated via constructors and modified through setters or fluent methods. Springdoc uses them to generate JSON/YAML documents.

Example:

~~~java
OpenAPI openAPI = new OpenAPI()
    .info(new Info()
        .title("Shop API")
        .description("API for managing products and orders")
        .version("1.0.0"));
~~~

The model above represents the corresponding metadata section:

~~~yaml
openapi: 3.1.0
info:
  title: Shop API
  description: API for managing products and orders
  version: "1.0.0"
~~~

The openapi value at the document level indicates the specification version. Info.version describes the published API version; these two values serve different purposes.

## 3. Distinguishing Model Classes from Annotation Classes

Swagger Core has two package groups that are easily confused:

| Group | Representative Package | Usage |
|---|---|---|
| Annotation | io.swagger.v3.oas.annotations | Place metadata on classes, methods, fields, or parameters |
| Model | io.swagger.v3.oas.models | Create and modify OpenAPI objects in Java |

Annotation example:

~~~java
@Operation(
    summary = "Get product information",
    description = "Look up a product by identifier"
)
@GetMapping("/api/products/{id}")
public ProductResponse findById(@PathVariable Long id) {
    return productService.findById(id);
}
~~~

Annotations are placed on methods for Springdoc to read when scanning controllers.

Model example:

~~~java
Operation operation = new Operation()
    .summary("Get product information")
    .description("Look up a product by identifier");
~~~

Models are created and modified in code. They do not attach to controllers automatically; they must be incorporated into the OpenAPI document through a customizer or appropriate configuration.

Do not confuse io.swagger.v3.oas.annotations.Operation with io.swagger.v3.oas.models.Operation. The class names are identical, but one is an annotation and the other is a model.

## 4. Declaring an OpenAPI Bean in Spring Boot

A common way to provide global metadata is to declare an OpenAPI bean:

~~~java
@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI shopOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Shop API")
                .description("API for managing products, categories, and orders.")
                .version("1.0.0"))
            .servers(List.of(
                new Server()
                    .url("https://api.example.com")
                    .description("Production server")
            ));
    }
}
~~~

The model imports in the example belong to the io.swagger.v3.oas.models package; @Configuration and @Bean belong to Spring Framework.

Springdoc uses this bean as the foundation for the OpenAPI document and continues discovering operations from controllers. You do not need to manually build all Paths if the application already has controllers scanned by Springdoc.

Keep the bean focused on metadata or shared components such as servers, components, and security. Details tied to individual methods are usually a better fit for annotations or OperationCustomizer.

If the application already declares metadata with @OpenAPIDefinition, avoid declaring another source with conflicting values. You can use annotations for static metadata or an OpenAPI bean for configuration built programmatically; choose one primary source and verify the final output.

## 5. Declaring Info, Server, and Tag Using Models

An OpenAPI bean can contain a variety of metadata:

~~~java
@Bean
public OpenAPI shopOpenAPI() {
    return new OpenAPI()
        .info(new Info()
            .title("Shop API")
            .description("API for sales applications and integration systems.")
            .version("1.4.0")
            .contact(new Contact()
                .name("API Support")
                .email("api-support@example.com")
                .url("https://example.com/support"))
            .license(new License()
                .name("Apache 2.0")
                .url("https://www.apache.org/licenses/LICENSE-2.0.html")))
        .servers(List.of(
            new Server()
                .url("https://api.example.com")
                .description("Production"),
            new Server()
                .url("https://staging-api.example.com")
                .description("Staging")
        ))
        .tags(List.of(
            new Tag()
                .name("Products")
                .description("Manage products"),
            new Tag()
                .name("Orders")
                .description("Manage orders")
        ));
}
~~~

The Server Object describes the URL that clients can call. Avoid hardcoding a fixed production URL if the documentation needs to vary by environment. Values can be loaded from application properties or profiles, while ensuring the document does not accidentally expose internal hostnames.

Document-level tags define group names and descriptions. Operations still need to reference a tag by its corresponding name so Swagger UI groups endpoints properly. Creating a Tag Object without attaching the tag to any operation may leave the tag with no visible operations.

Info.summary should only be used when the OpenAPI model version and exported document support this field, namely OpenAPI 3.1.0 or higher. If the project exports OpenAPI 3.0 or swagger-models lacks the corresponding property, place the brief introduction in description.

## 6. Reusing Schemas Through Components

Components is where reusable definitions are stored, such as schemas, responses, parameters, request bodies, and security schemes.

Example of adding a schema using a model:

~~~java
@Bean
public OpenAPI shopOpenAPI() {
    Schema<?> productSchema = new Schema<>()
        .type("object")
        .addProperty("id", new Schema<>().type("integer").format("int64"))
        .addProperty("name", new Schema<>().type("string"))
        .addProperty("price", new Schema<>().type("number"));

    Components components = new Components()
        .addSchemas("ProductSummary", productSchema);

    return new OpenAPI()
        .info(new Info()
            .title("Shop API")
            .version("1.0.0"))
        .components(components);
}
~~~

The ProductSummary schema can be referenced from a response:

~~~java
Schema<?> productReference = new Schema<>()
    .$ref("#/components/schemas/ProductSummary");
~~~

In many cases, Springdoc automatically generates component schemas from DTOs used in controllers. Only add a schema using models when you need a special shared definition or need to supplement a structure that automatic inference does not accurately represent.

Do not create a component with the same name as a schema already generated by Springdoc. Component names must be unique within the document, and $ref references must point to the exact location.

## 7. Declaring a Security Scheme Using the OpenAPI Model

A Bearer JWT mechanism can be described in Components:

~~~java
@Bean
public OpenAPI shopOpenAPI() {
    SecurityScheme bearerScheme = new SecurityScheme()
        .type(SecurityScheme.Type.HTTP)
        .scheme("bearer")
        .bearerFormat("JWT")
        .description("Enter a JWT access token");

    Components components = new Components()
        .addSecuritySchemes("bearerAuth", bearerScheme);

    return new OpenAPI()
        .info(new Info()
            .title("Shop API")
            .version("1.0.0"))
        .components(components)
        .addSecurityItem(new SecurityRequirement()
            .addList("bearerAuth"));
}
~~~

The Security Scheme defines an authentication mechanism named bearerAuth. A document-level Security Requirement applies that requirement to operations according to OpenAPI rules. If some endpoints are public, you can override security on the corresponding operation with an empty security requirement or appropriate configuration.

Declaring a scheme only describes the contract for OpenAPI tools. It does not enable Spring Security, validate JWTs, or issue tokens. The application must still configure the filter chain, token decoder, and authorization rules at runtime.

Do not put real tokens or secrets into the OpenAPI model. The documentation only describes how clients send authentication credentials.

## 8. OpenApiCustomizer Modifies the Entire Document

OpenApiCustomizer is a Springdoc extension point that lets you modify the OpenAPI model after the document is generated. It is suitable for document-level changes such as adding extensions, tags, servers, or general metadata.

Example of adding an extension and a tag:

~~~java
@Configuration
public class OpenApiCustomizationConfiguration {

    @Bean
    public OpenApiCustomizer documentMetadataCustomizer() {
        return openApi -> {
            openApi.addExtension("x-api-owner", "platform-team");

            openApi.addTagsItem(new Tag()
                .name("Internal")
                .description("Operations for internal integration"));
        };
    }
}
~~~

In Springdoc 2.x, OpenApiCustomizer typically resides in the org.springdoc.core.customizers package. Use the package and API appropriate for your project's Springdoc version; the package may differ in older major versions.

The customizer receives the constructed OpenAPI model and can modify existing properties. If you need to preserve metadata from beans or annotations, update conditionally instead of replacing the entire object:

~~~java
if (openApi.getInfo() != null) {
    openApi.getInfo().setDescription(
        "API documentation generated from Spring Boot controllers."
    );
}
~~~

Calling openApi.info(new Info()) inside a customizer can replace the entire previous Info. Only do so when replacement is intentional and the required fields are preserved.

## 9. OperationCustomizer Modifies Individual Operations

OperationCustomizer operates at the level of a single operation and additionally receives the corresponding HandlerMethod. It is suitable when metadata needs to be added based on the method or controller.

Example of adding an extension containing the method name:

~~~java
@Configuration
public class OperationCustomizationConfiguration {

    @Bean
    public OperationCustomizer operationMetadataCustomizer() {
        return (operation, handlerMethod) -> {
            operation.addExtension(
                "x-handler-method",
                handlerMethod.getMethod().getName()
            );

            return operation;
        };
    }
}
~~~

This customizer is invoked for each operation generated by Springdoc from a handler method. You can use HandlerMethod to read custom application annotations, controller packages, or method details.

For example, if the project has an @ApiOwner("catalog-team") annotation, OperationCustomizer can read the annotation on the method and add the corresponding x-api-owner extension. This approach avoids repeating metadata across multiple OpenAPI annotations.

OperationCustomizer does not replace Spring MVC mappings and does not change how requests are handled. It only modifies the documentation model. If you add extensions or change the summary, ensure those values accurately reflect actual behavior.

## 10. Comparing OpenApiCustomizer and OperationCustomizer

The two customizers have different scopes:

| Criterion | OpenApiCustomizer | OperationCustomizer |
|---|---|---|
| Received object | OpenAPI document | Operation and HandlerMethod |
| Scope | Entire document | Individual endpoint operation |
| Knows specific controller method? | Not directly via basic callback | Yes |
| Examples | Adding servers, tags, document-wide extensions | Attaching owner, business code, or per-method description |
| When to use | Shared metadata or document-level structure | Metadata dependent on controller/method |

Avoid using OperationCustomizer to add document-wide metadata when OpenApiCustomizer can be used. Conversely, avoid manually iterating over all Paths just to locate a HandlerMethod when OperationCustomizer already provides the method context.

If a customizer needs to apply to all document groups, Springdoc provides a global customizer mechanism in supported versions. If you only want to modify one group, attach the customizer to the corresponding GroupedOpenApi configuration. Verify the exact customizer type and scope in your project's dependency version.

## 11. Attaching a Customizer to a Document Group

An application can have multiple document groups. Each group may require its own metadata or extensions.

Example:

~~~java
@Bean
public GroupedOpenApi partnerApi() {
    return GroupedOpenApi.builder()
        .group("partner")
        .pathsToMatch("/api/partner/**")
        .addOpenApiCustomizer(openApi -> {
            openApi.info(new Info()
                .title("Partner API")
                .description("API for partners")
                .version("1.0.0"));

            openApi.addExtension("x-audience", "partners");
        })
        .build();
}
~~~

The customizer is attached on the group builder to adjust that group's document. This approach is useful when public, admin, and partner documents have different titles, servers, or metadata.

Check whether metadata configured in the global OpenAPI bean is overridden by the group customizer. If you only want to change a single field, update that field and preserve the remaining values.

In versions providing GlobalOpenApiCustomizer, it can be used when changes must appear in both the default document and all groups. Do not use a group-specific customizer for a rule that must apply system-wide without checking the default document.

## 12. Adding Operation and PathItem Using Swagger Core Models

Springdoc normally generates PathItem and Operation from controllers automatically. However, Swagger Core models also allow creating operations programmatically when you need to describe an endpoint not generated directly from a controller, or add a special path.

Example of creating a health operation:

~~~java
@Bean
public OpenApiCustomizer healthOperationCustomizer() {
    return openApi -> {
        Operation healthOperation = new Operation()
            .operationId("healthCheck")
            .summary("Check service status")
            .description("Returns the operational status of the API")
            .responses(new ApiResponses()
                .addApiResponse("200", new ApiResponse()
                    .description("Service is operational")));

        openApi.path(
            "/internal/health-doc",
            new PathItem().get(healthOperation)
        );
    };
}
~~~

This example creates a PathItem and Operation directly in the model. It only supplements the OpenAPI documentation; the corresponding HTTP endpoint must actually exist at runtime if clients are expected to call it.

Do not create an operation that duplicates a path/method already generated by Springdoc from a controller. If the same path and HTTP method are added twice, one configuration may overwrite the other or make the document unpredictable.

For endpoints actually implemented by controllers, prefer declaring controllers and annotations so the documentation stays linked to runtime code. Reserve manual models for cases with a clear reason.

## 13. Adding Responses and Schemas Using Models

Swagger Core models can describe responses with status codes, descriptions, media types, and schemas:

~~~java
ApiResponse successResponse = new ApiResponse()
    .description("Returns the product")
    .content(new Content()
        .addMediaType(
            "application/json",
            new MediaType().schema(
                new Schema<>().$ref("#/components/schemas/ProductSummary")
            )
        ));

Operation operation = new Operation()
    .responses(new ApiResponses()
        .addApiResponse("200", successResponse));
~~~

Shared component schemas can be added:

~~~java
Schema<?> productSchema = new Schema<>()
    .type("object")
    .addProperty("id", new Schema<>().type("integer").format("int64"))
    .addProperty("name", new Schema<>().type("string"));

openApi.getComponents()
    .addSchemas("ProductSummary", productSchema);
~~~

When referencing a schema, the component name must match the exact key in components.schemas. Even if a component is added after a response references it, the final output must still contain both the definition and the reference.

In Springdoc applications, controllers and DTOs are usually the primary source for generating responses and schemas. Only intervene with models when you need to adjust structure or add a shared definition that automatic inference does not satisfy.

## 14. Order and Scope of Customization

An OpenAPI document can be built from multiple sources:

- Metadata in @OpenAPIDefinition.
- An OpenAPI bean.
- Annotations on controllers and DTOs.
- Models inferred by Springdoc from Java types.
- OpenApiCustomizer.
- OperationCustomizer.
- Group-specific customizers.

When multiple sources modify the same field, the result depends on the document generation pipeline and how customizers are applied in that Springdoc version. Do not rely on implicit ordering if the application has multiple customizers overriding the same property.

To keep configuration clear:

1. Choose one primary source for global metadata.
2. Use annotations for information tied directly to controllers or DTOs.
3. Use OperationCustomizer for metadata dependent on HandlerMethod.
4. Use OpenApiCustomizer for document-level changes.
5. Use group customizers for group-specific metadata.
6. Avoid having multiple customizers replace the entire Info, Paths, or Components.
7. Inspect the final document after all customizers have run.

Do not replace the entire Paths with a new object inside a customizer if you want to keep operations discovered by Springdoc. If you need to add a path, add that specific path instead of replacing the existing collection.

## 15. Loading Configuration Values from Application Properties

Some metadata changes per environment, such as server URLs or contact details. You can inject Spring configuration into the bean:

~~~yaml
app:
  api:
    title: Shop API
    version: 1.4.0
    server-url: https://api.example.com
~~~

~~~java
@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI shopOpenAPI(
        @Value("${app.api.title}") String title,
        @Value("${app.api.version}") String version,
        @Value("${app.api.server-url}") String serverUrl
    ) {
        return new OpenAPI()
            .info(new Info()
                .title(title)
                .version(version))
            .servers(List.of(
                new Server().url(serverUrl)
            ));
    }
}
~~~

This approach allows environment-specific metadata to be managed via Spring Boot configuration. For multiple related values, you can use a @ConfigurationProperties class instead of multiple @Value parameters.

Distinguish between the server URL used in OpenAPI and the actual address exposed by a gateway or reverse proxy. If the application runs behind a proxy, forwarded headers configuration and the server URL must be consistent so Swagger UI sends requests to the right host and path.

Do not place secrets, passwords, access tokens, or internal connection details in the OpenAPI bean.

## 16. Verifying the Model After Customization

After the application starts, fetch the OpenAPI document:

~~~http
GET /v3/api-docs
~~~

If groups are used, also check each group's document endpoint, for example:

~~~http
GET /v3/api-docs/partner
~~~

Verify the following:

- Info has the correct title, description, and version.
- Server URLs match the environment and base path.
- Tags have consistent names and descriptions.
- Components contain all referenced schemas, responses, and security schemes.
- Security requirements apply to the intended operations.
- OperationCustomizer only affects the expected operations.
- OpenApiCustomizer does not drop Paths or Components generated by Springdoc.
- Extensions start with x- and have the right value types.
- Document groups have their own properly scoped metadata.
- JSON/YAML remains valid after model modifications.

You can use an OpenAPI validator in CI to verify the structure. A validator does not verify that runtime endpoints actually exist or that security rules are enforced; separate integration tests are needed for those.

## 17. Common Pitfalls When Customizing with Models

| Symptom | Cause to Check |
|---|---|
| Wrong Operation import | Using the annotation class instead of the model class or vice versa |
| Bean metadata does not appear | Bean is not scanned by Spring, configuration is overridden by another source, or wrong document group |
| Controller paths disappear | Customizer replaces all Paths instead of adding the needed path |
| Schema reference fails to resolve | Component is not declared or $ref name is wrong |
| Security scheme exists but UI does not require token | Missing Security Requirement or requirement not applied to the operation |
| Every operation gets the same extension | OperationCustomizer logic does not filter by controller/method |
| Group lacks customized metadata | Wrong customizer scope used or customizer only applies to default document |
| Summary does not appear | Specification uses OpenAPI 3.0 or model version does not yet support Info.summary |
| Swagger UI calls wrong server | Server URL, context path, or reverse proxy mismatch |
| Duplicate or overwritten operation | Manually creating a path/method that collides with an operation scanned from a controller |

When troubleshooting, inspect the OpenAPI JSON first to see what the final model actually contains. Then check which beans, annotations, and customizers created or modified that field.

## 18. Design Principles for OpenAPI Customization

When using the OpenAPI bean and Swagger Core models in Springdoc, apply these principles:

1. Use an OpenAPI bean for shared metadata and components.
2. Use Swagger Core model classes when you need to create or modify the document in Java.
3. Distinguish the model package from the annotation package.
4. Use OpenApiCustomizer for document-level changes.
5. Use OperationCustomizer for changes dependent on HandlerMethod.
6. Use a group-specific customizer when metadata belongs only to one group document.
7. Do not replace all Paths or Components if you only need to add a single item.
8. Do not manually declare operations that collide with controllers scanned by Springdoc.
9. Keep servers, schemas, security, and extensions consistent with runtime.
10. Inspect the OpenAPI JSON/YAML and run contract/integration tests after changes.

The OpenAPI bean provides a controlled starting point for the document; Swagger Core models represent the OpenAPI structure in Java; customizers allow modifying the document or operations at the right scope. When each source is used in its proper role and the final output is verified, the application can extend its documentation while keeping the contract consistent with Spring Boot controllers.

