# Components and Reusable Elements

When an API has many endpoints, multiple operations often share a data structure, a parameter, an error response, or an authentication mechanism. Describing every element inline everywhere makes the OpenAPI document long, prone to drift, and hard to maintain. **Components** provide a central place to define reusable elements; **$ref** lets endpoints reference those definitions.

In Spring Boot, springdoc-openapi can generate schemas from DTOs, return types, and controller annotations. You can also declare shared elements using OpenAPI annotations or the Java models from the `swagger-core` library. Understanding how Components are organized lets you build consistent contracts, reduce duplication, and help Swagger UI and client generators interpret the API structure accurately.

## Objectives

After this lesson, you will be able to:

- Understand the role of the Components Object in an OpenAPI document.
- Distinguish the groups of reusable elements and know when to use each group.
- Use `$ref` to link endpoints to schemas, responses, parameters, request bodies, headers, and security schemes.
- Organize shared schemas, nested schemas, and polymorphic schemas.
- Create Components via YAML, annotations, and Java configuration in Spring Boot.
- Validate references, avoid duplicate definitions, and maintain extensible documentation.

## 1. What Are Components?

In OpenAPI, the Components Object is a collection of named definitions. Each definition can be referenced from another location in the document using the `$ref` key. Components do not create endpoints on their own and do not automatically apply definitions across the entire API; a component takes effect only where it is referenced.

For example, many operations may return the same error structure. Instead of repeating the error schema everywhere, we define it once in `components.schemas`:

~~~yaml
components:
  schemas:
    ApiError:
      type: object
      required:
        - code
        - message
      properties:
        code:
          type: string
          example: PRODUCT_NOT_FOUND
        message:
          type: string
          example: Product not found
~~~

A response can reuse that schema:

~~~yaml
paths:
  /api/products/{id}:
    get:
      responses:
        '404':
          description: Product not found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
~~~

The `$ref` path above is an internal reference pointing to a location within the same OpenAPI document. If the schema changes, every location referencing `ApiError` receives the updated definition. That is the primary benefit of standardizing shared components.

## 2. Component Groups in Components

OpenAPI 3.0 defines the following main groups inside Components:

| Group | Used to Reuse | Examples |
|---|---|---|
| schemas | Data structures | Product, PageResponse, ApiError |
| responses | HTTP responses | NotFound, ValidationError |
| parameters | Path, query, header, or cookie parameters | ProductId, PageSize |
| examples | Example values | NewProduct, InvalidProduct |
| requestBodies | Request payloads | CreateProductBody |
| headers | Response headers | RetryAfter, RateLimitRemaining |
| securitySchemes | Authentication mechanisms | bearerAuth, oauth2 |
| links | Links from a response to another operation | GetCreatedProduct |
| callbacks | Out-of-band callback requests initiated by the API | OrderStatusCallback |

OpenAPI 3.1 adds the `pathItems` group for reusing Path Item Objects. If the project generates an OpenAPI 3.0 specification, do not put `pathItems` under Components because that version does not define it. Check the `openapi` field at the top of the document to see which specification version the project uses.

The most common components in Spring Boot APIs are `schemas`, `responses`, `parameters`, `requestBodies`, `headers`, `examples`, and `securitySchemes`. `links`, `callbacks`, and `pathItems` are more useful in APIs with multi-step workflows, webhooks, or path structures that need to be shared.

## 3. How $ref Works

An internal reference typically has the form:

~~~yaml
$ref: '#/components/schemas/Product'
~~~

The part after `#` is a JSON Pointer identifying a location in the document:

- `#` points to the root of the document.
- `/components` enters the Components Object.
- `/schemas` enters the schemas group.
- `/Product` selects the component named `Product`.

A reference to a response uses a similar form:

~~~yaml
$ref: '#/components/responses/NotFound'
~~~

Component names are case-sensitive. To avoid reference errors, use clear names without spaces and prefer alphanumeric characters, dots, hyphens, or underscores. If a key contains special JSON Pointer characters, escape them per JSON Pointer rules: tilde as `~0` and slash as `~1`. In practice, simple names are easier to read and less error-prone.

### Internal and External References

Internal references such as `#/components/schemas/Product` reside within the same document, which is convenient when exporting a standalone JSON/YAML file. OpenAPI also permits referencing external documents by URI, for example:

~~~yaml
$ref: './common-schemas.yaml#/components/schemas/Address'
~~~

External references are helpful when multiple APIs genuinely share a contract repository. However, they introduce dependencies on the location, access permissions, and versioning of external files. If exporting a specification to send to partners or generate clients in an environment without internal network access, ensure external references are distributed alongside it or bundled into a self-contained document.

### Rules When Using $ref

- The reference target must exist and match the object type expected at that location.
- Avoid unnecessary circular references, especially with client generators that have recursion limits.
- Do not place sibling properties next to a `$ref` expecting them to override the original definition. For broad compatibility, keep referenced objects simple; when combining schemas, use `allOf`, `oneOf`, or `anyOf` as intended.
- Verify the document after bundling or conversion, as tools may alter how references are represented.

## 4. Reusing Schemas in components.schemas

Schemas describe the data structures of requests or responses. For example, a product API might use these schemas:

~~~yaml
components:
  schemas:
    Product:
      type: object
      required:
        - id
        - name
        - price
      properties:
        id:
          type: integer
          format: int64
          example: 42
        name:
          type: string
          maxLength: 120
          example: Mechanical keyboard
        price:
          type: number
          format: double
          minimum: 0
          example: 1250000
    CreateProductRequest:
      type: object
      required:
        - name
        - price
      properties:
        name:
          type: string
          maxLength: 120
        price:
          type: number
          minimum: 0
    ApiError:
      type: object
      required: [code, message]
      properties:
        code:
          type: string
        message:
          type: string
~~~

Endpoints can use `Product` for read responses, `CreateProductRequest` for creation bodies, and `ApiError` for errors. Separating input and output DTOs helps the contract accurately reflect each operation's responsibility. For instance, clients do not send a server-generated `id` when creating a product.

### Nested Schemas and Collections

A schema can reference another schema in `properties` or `items`:

~~~yaml
components:
  schemas:
    Category:
      type: object
      properties:
        id:
          type: integer
        name:
          type: string
    Product:
      type: object
      properties:
        id:
          type: integer
        category:
          $ref: '#/components/schemas/Category'
        tags:
          type: array
          items:
            type: string
    ProductPage:
      type: object
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/Product'
        page:
          type: integer
        totalElements:
          type: integer
          format: int64
~~~

When the same structure appears in multiple places, referencing a schema establishes a single source of truth. For structures that appear once and are very small, inline schemas can remain easier to read. Do not extract every object into a component; reuse when it clarifies the contract or eliminates meaningful duplication.

### allOf, oneOf, and anyOf

OpenAPI supports schema composition:

- `allOf`: a value must satisfy all member schemas. Commonly used to merge property groups or model extended structures.
- `oneOf`: a value must match exactly one of the listed schemas.
- `anyOf`: a value must match at least one of the listed schemas.

Example of a response with common fields and specialized payloads:

~~~yaml
components:
  schemas:
    BaseEvent:
      type: object
      required: [eventId, occurredAt, eventType]
      properties:
        eventId:
          type: string
        occurredAt:
          type: string
          format: date-time
        eventType:
          type: string
          enum: [PRODUCT_CREATED, PRODUCT_DELETED]
    ProductCreatedEvent:
      allOf:
        - $ref: '#/components/schemas/BaseEvent'
        - type: object
          required: [productId]
          properties:
            productId:
              type: integer
    ProductDeletedEvent:
      allOf:
        - $ref: '#/components/schemas/BaseEvent'
        - type: object
          required: [productId, reason]
          properties:
            productId:
              type: integer
            reason:
              type: string
~~~

`allOf` is an intersection of schema constraints, not automatically Java class inheritance with every language rule. When using `oneOf` for multiple event or result types, consider declaring a `discriminator` so clients can identify the data type:

~~~yaml
components:
  schemas:
    ProductEvent:
      oneOf:
        - $ref: '#/components/schemas/ProductCreatedEvent'
        - $ref: '#/components/schemas/ProductDeletedEvent'
      discriminator:
        propertyName: eventType
        mapping:
          PRODUCT_CREATED: '#/components/schemas/ProductCreatedEvent'
          PRODUCT_DELETED: '#/components/schemas/ProductDeletedEvent'
~~~

In concrete schemas, `eventType` must hold values matching the mapping. Otherwise, clients may fail to distinguish variants. Verify how your client generator handles `allOf`, `oneOf`, `anyOf`, and `discriminator`, since support varies across tools.

## 5. Reusing Responses in components.responses

Shared responses are typically common errors such as resource not found, validation failure, or rate limit exceeded:

~~~yaml
components:
  responses:
    NotFound:
      description: Resource not found
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
          examples:
            productMissing:
              summary: Product does not exist
              value:
                code: PRODUCT_NOT_FOUND
                message: Product not found
    ValidationError:
      description: Invalid request data
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
    TooManyRequests:
      description: Request rate limit exceeded
      headers:
        Retry-After:
          $ref: '#/components/headers/RetryAfter'
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/ApiError'
~~~

Endpoint referencing the responses:

~~~yaml
paths:
  /api/products/{id}:
    get:
      responses:
        '200':
          description: Product found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
        '404':
          $ref: '#/components/responses/NotFound'
        '429':
          $ref: '#/components/responses/TooManyRequests'
~~~

Every referenced response must preserve accurate semantics for the operation. A `NotFound` response can be shared across endpoints if the content is genuinely equivalent. If messages, schemas, or headers differ significantly, create a separate component or use a shared schema with tailored examples.

Reusable responses let you update descriptions in one place. However, they do not make Spring automatically return that status code. Controllers, `ResponseEntity`, or exception handlers must still produce the status, headers, and body declared in the contract.

## 6. Reusing Parameters in components.parameters

A Parameter Object describes a path, query, header, or cookie parameter. For example, a product ID parameter appearing across multiple endpoints:

~~~yaml
components:
  parameters:
    ProductId:
      name: id
      in: path
      required: true
      description: Product identifier
      schema:
        type: integer
        format: int64
      example: 42
    PageSize:
      name: size
      in: query
      required: false
      description: Maximum number of items per page
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
~~~

Using the defined parameter:

~~~yaml
paths:
  /api/products/{id}:
    get:
      parameters:
        - $ref: '#/components/parameters/ProductId'
      responses:
        '200':
          description: Success
~~~

For a parameter in `path`, `required` must be `true`. A parameter is uniquely identified by the pair `name` and `in` within an operation or path scope. If a query parameter shares the same name as a path parameter, they remain two distinct parameters.

Do not declare an authentication token as a regular header parameter. For an `Authorization` bearer token, use a security scheme so tools understand authentication semantics and enable the Authorize button in Swagger UI.

## 7. Reusing Request Bodies in components.requestBodies

When multiple endpoints accept the same request body structure, define a Request Body Object:

~~~yaml
components:
  requestBodies:
    CreateProductBody:
      description: Product creation payload
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateProductRequest'
          examples:
            default:
              summary: New product
              value:
                name: Mechanical keyboard
                price: 1250000
~~~

Referencing in an operation:

~~~yaml
paths:
  /api/products:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateProductBody'
      responses:
        '201':
          description: Product created
~~~

A request body can declare multiple media types, such as `application/json` and `multipart/form-data`. When reusing, ensure all endpoints accept the same formats, field meanings, and required rules. If one endpoint allows an optional body or has different constraints, use a separate request body.

## 8. Reusing Examples in components.examples

Examples can be placed inline inside a schema or `content`. When the same example is used in multiple places, define it under `components.examples`:

~~~yaml
components:
  examples:
    ProductCreated:
      summary: Product created successfully
      description: Example response after creating a new product
      value:
        id: 42
        name: Mechanical keyboard
        price: 1250000
    ProductValidationError:
      summary: Product name is blank
      value:
        code: VALIDATION_FAILED
        message: Product name must not be blank
~~~

Referencing an example from a media type:

~~~yaml
content:
  application/json:
    schema:
      $ref: '#/components/schemas/Product'
    examples:
      created:
        $ref: '#/components/examples/ProductCreated'
~~~

A schema can have multiple examples illustrating normal, boundary, and error cases. Examples must conform to the schema and contain no real customer data, tokens, or internal information. Swagger UI uses examples to help readers try requests and understand responses.

## 9. Reusing Headers in components.headers

A header can be defined separately when multiple responses return the same header metadata. Example:

~~~yaml
components:
  headers:
    RetryAfter:
      description: Number of seconds or HTTP-date the client should wait before retrying
      schema:
        type: string
      example: '30'
    RateLimitRemaining:
      description: Number of remaining requests in the current rate-limit window
      schema:
        type: integer
      example: 12
~~~

Using header components in a response:

~~~yaml
components:
  responses:
    TooManyRequests:
      description: Rate limit exceeded
      headers:
        Retry-After:
          $ref: '#/components/headers/RetryAfter'
        X-RateLimit-Remaining:
          $ref: '#/components/headers/RateLimitRemaining'
~~~

Header names are case-insensitive in HTTP. Even so, keep casing consistent in the documentation. For standard headers, describe the data type and semantics accurately; for instance, `Retry-After` can represent seconds or an HTTP-date, so examples and descriptions should reflect what the server actually sends.

## 10. Reusing securitySchemes

A Security Scheme Object describes an authentication mechanism supported by the API. Common types:

- HTTP authentication: Basic or Bearer.
- API key in header, query, or cookie.
- OAuth2 with flows and scopes.
- OpenID Connect.

Bearer JWT example:

~~~yaml
components:
  securitySchemes:
    bearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
~~~

Declaring a security requirement at the API level:

~~~yaml
security:
  - bearerAuth: []
~~~

Or applying only to protected operations:

~~~yaml
paths:
  /api/products:
    post:
      security:
        - bearerAuth: []
      responses:
        '201':
          description: Product created
~~~

With HTTP bearer, the scope list is normally empty. OAuth2 uses specific scope names per the declared flow. An operation can declare multiple security requirements; separate objects in the list represent alternatives, whereas multiple schemes placed together in a single object mean all of those mechanisms are required simultaneously.

To allow a public operation to override API-wide security, OpenAPI can use:

~~~yaml
security: []
~~~

A security scheme only describes the authentication contract. It does not configure Spring Security, validate JWTs, or authorize users. Inspect the actual security configuration and verify that the list of public/private operations matches the documentation.

## 11. Links and Callbacks

### Links: Pointing to the Next Operation

A Link Object describes the relationship from one response to another operation. For example, after creating a product, the response can provide an `id` for the client to invoke the detail lookup operation:

~~~yaml
components:
  links:
    GetCreatedProduct:
      operationId: getProductById
      parameters:
        id: '$response.body#/id'
      description: Fetch the newly created product
~~~

Response referencing the link:

~~~yaml
paths:
  /api/products:
    post:
      responses:
        '201':
          description: Product created
          links:
            getCreatedProduct:
              $ref: '#/components/links/GetCreatedProduct'
~~~

The referenced `operationId` must exist and be unique in the document. A link only describes the relationship and suggests the next call; it does not execute requests or guarantee the resource still exists.

### Callbacks: Describing Requests Sent by the API to Clients

Callbacks are useful when an API receives a callback URL from a client and proactively sends notifications to that URL when an event occurs. For example, a client registers `callbackUrl` when creating an order:

~~~yaml
paths:
  /api/orders:
    post:
      requestBody:
        required: true
        content:
          application/json:
            schema:
              type: object
              properties:
                callbackUrl:
                  type: string
                  format: uri
      callbacks:
        orderStatus:
          '{$request.body#/callbackUrl}':
            post:
              requestBody:
                required: true
                content:
                  application/json:
                    schema:
                      $ref: '#/components/schemas/OrderStatusEvent'
              responses:
                '200':
                  description: Client acknowledged notification
~~~

Callbacks represent outbound communication initiated by the API. When accepting client-supplied callback URLs, the system must validate target URLs and mitigate forged-request or internal-network-access risks. The contract should document webhook signatures, retry behavior, timeouts, and acknowledgment rules if supported.

Callbacks can be placed in `components.callbacks` and referenced if the same callback structure appears across multiple operations. Check actual support in your OpenAPI version and documentation generator.

## 12. PathItems in OpenAPI 3.1

OpenAPI 3.1 allows reusing Path Item Objects via `components.pathItems`. This can be useful when multiple documents or API groups share a path structure. Example:

~~~yaml
components:
  pathItems:
    HealthCheck:
      get:
        operationId: healthCheck
        summary: Check service health
        responses:
          '200':
            description: Service is running
~~~

Then reference it in `paths`:

~~~yaml
paths:
  /health:
    $ref: '#/components/pathItems/HealthCheck'
~~~

Use this component only when the document declares OpenAPI 3.1 or higher and pipeline tools support it. With OpenAPI 3.0, you may need to repeat the Path Item or structure the documentation differently.

## 13. Generating and Reusing Components from Spring Boot

springdoc-openapi reads controllers, Java types, and annotations to build the specification. When a DTO is used in requests or responses across multiple endpoints, its schema is typically placed in `components.schemas` and operations reference that schema.

DTO example:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Positive;

@Schema(name = "ProductResponse", description = "Product details returned to clients")
public record ProductResponse(
    @Schema(description = "Product ID", example = "42")
    Long id,

    @NotBlank
    @Schema(description = "Product name", example = "Mechanical keyboard")
    String name,

    @Positive
    @Schema(description = "Product price", example = "1250000")
    long price
) {}
~~~

When multiple controllers return `ProductResponse`, springdoc can share the `ProductResponse` schema. Component names can be customized with `@Schema(name = "...")` to make documentation clearer and more stable. If multiple Java classes share the same simple name, assign explicit schema names to avoid collisions or confusing auto-generated names.

### Declaring Reusable Responses with Annotations

You can register response components via Java OpenAPI configuration, then reference them from annotations:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.Schema;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class OpenApiConfig {

    @Bean
    OpenAPI applicationOpenApi() {
        Components components = new Components()
            .addResponses("NotFound",
                new io.swagger.v3.oas.models.responses.ApiResponse()
                    .description("Resource not found")
                    .content(new Content().addMediaType(
                        "application/json",
                        new MediaType().schema(
                            new Schema<>().$ref("#/components/schemas/ApiError")
                        )
                    ))
            );

        return new OpenAPI().components(components);
    }
}
~~~

The `ApiError` schema definition must be generated by springdoc from a DTO used in the API or explicitly added to Components. Do not reference a nonexistent schema. When using a different library version, check the corresponding imports and model APIs.

In the controller:

~~~java
@GetMapping("/{id}")
@ApiResponse(
    responseCode = "404",
    ref = "#/components/responses/NotFound"
)
public ProductResponse getById(@PathVariable long id) {
    return productService.getById(id);
}
~~~

The annotation reference lets the operation use the registered response definition. Verify that the generated specification has the expected response code and `$ref`. In particular, a response-documentation annotation does not replace runtime exception handlers.

### Reusing Parameters with Annotations

For repeated parameters, you can declare a Parameter Object in Components and reference it:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.media.Schema;

Components components = new Components()
    .addParameters("ProductId",
        new Parameter()
            .name("id")
            .in("path")
            .required(true)
            .description("Product ID")
            .schema(new Schema<>().type("integer").format("int64"))
    );
~~~

In an operation, the OpenAPI annotation has a `ref` attribute to point to the component parameter:

~~~java
@GetMapping("/{id}")
public ProductResponse getById(
    @Parameter(ref = "#/components/parameters/ProductId")
    @PathVariable long id
) {
    return productService.getById(id);
}
~~~

This illustrates combining model configuration with annotations; inspect the OpenAPI JSON to ensure Springdoc does not emit a duplicate parameter alongside it.

### Reusing Security Schemes with Annotations

For HTTP bearer, you can declare the scheme with an annotation:

~~~java
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityRequirement;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
public class ApiSecurityDocumentation {
}
~~~

Apply the requirement to protected controllers or operations:

~~~java
@RestController
@RequestMapping("/api/admin")
@SecurityRequirement(name = "bearerAuth")
public class AdminController {
    // Operations requiring a bearer token.
}
~~~

Declaring the scheme creates the entry in `components.securitySchemes`; the requirement specifies which operations require that scheme. Declaring only a scheme without attaching a requirement tells Swagger UI the mechanism exists without indicating which operations need it.

### When Do You Need an OpenAPI Bean or Customizer?

Use annotations when metadata attaches directly to a controller, DTO, or operation and is clear right at the declaration site. Use an `OpenAPI` bean or customizer when registering many shared components, applying environment-based rules, standardizing metadata, or adjusting the document after springdoc generates it.

If the application has multiple `GroupedOpenApi` beans, confirm the customizer applies to the right groups. Configuration affecting only the default document may not appear in another group's specification. Use global customizers or per-group configuration according to the springdoc version in use.

## 14. Organizing Components for Maintainability

A good structure balances reuse with endpoint specificity:

1. Name components by business role, e.g., `ProductResponse`, `CreateProductRequest`, `ApiError`, `NotFound`, and `PageSize`.
2. Separate request and response models when they differ in lifecycle or fields.
3. Share schemas when structures and meanings genuinely match, not just because two objects happen to share field names.
4. Share responses when status, media type, schema, headers, and semantics are equivalent.
5. Keep examples close to realistic data, include boundary values, and avoid secrets.
6. Avoid overly generic schemas that obscure which fields appear in each scenario.
7. Check references and component names when renaming DTOs or packages.
8. Version and archive OpenAPI artifacts so you know exactly which components were released.

### Avoiding Schema Name Collisions

If two Java modules both have a `Product` class with different meanings, do not let them compete for the same component name. Give explicit names such as `CatalogProduct` and `OrderProduct` via `@Schema(name = "...")`, or use separate DTOs whose names reflect their context. This helps client generators create stable class names and avoids accidental schema overrides.

### Avoiding Over-Reuse

A single DTO shared across every request and response can leak internal fields or cause a change on one endpoint to impact another. Likewise, a `GeneralError` response with a vague description can blur the difference between validation, authentication, and conflict errors. Reuse should reflect a genuinely shared contract, not merely fewer lines of YAML.

### Controlling Recursive Schemas

A schema can reference itself, such as `Category` having a `children` list of `Category`. This is valid for tree structures, though some client generators or renderers struggle with circular references. Keep nesting depth reasonable, test integration tools, and consider depth-bounded DTOs if clients handle recursion poorly.

## 15. Verifying Components and References

After the application starts, open the specification endpoint, usually `/v3/api-docs`, and verify:

- Required components sit under the right `components` group.
- Component names are unique and clear.
- Every `$ref` points to an existing component of the proper type.
- Operations reference the right responses, parameters, request bodies, and schemas.
- Security schemes are declared and requirements are attached at the right scope.
- Examples match schemas and contain no sensitive data.
- No `204` response declares a content body.
- Every document group contains all components referenced by that group's operations.

### Checking with a Validator

You can download the JSON specification:

~~~bash
curl http://localhost:8080/v3/api-docs -o openapi.json
~~~

Then run an OpenAPI validator or linter compatible with the specification version. Automated tools catch dangling references, malformed responses, invalid schemas, and inconsistent naming rules. Validators do not replace business review: a syntactically valid document can still misrepresent actual API behavior.

### Checking in Swagger UI

Swagger UI lets you inspect rendered API groups, schemas, and responses. Expand the Schemas section, examine each operation's responses, and test request examples. If a component is missing or a reference renders unexpectedly, inspect the raw JSON directly to determine whether the issue lies in document generation or UI rendering.

### Compatibility Checks When Changing Components

Changing a component can impact many endpoints simultaneously. Changes requiring careful evaluation:

- Deleting or renaming a referenced schema, response, parameter, or security scheme.
- Changing data type, format, enum values, or property names.
- Adding a required field or tightening data constraints.
- Changing response codes, media types, or headers.
- Modifying a discriminator or `oneOf`/`allOf` structure.

Before releasing, diff the new OpenAPI against the published version to identify potentially breaking changes. For incompatible changes, prepare a versioning plan, transition window, and integrator notice.

## 16. Comprehensive Practice Exercise

Build a product management API with read, create, and delete operations. Complete the following:

1. Create schemas `Product`, `CreateProductRequest`, `ProductPage`, and `ApiError`.
2. Use `$ref` to reuse schemas in requests and responses.
3. Create response components `NotFound`, `ValidationError`, and `TooManyRequests`.
4. Create parameter components `ProductId` and `PageSize`.
5. Create requestBody component `CreateProductBody`.
6. Define examples `ProductCreated` and `ProductValidationError`.
7. Define header component `RetryAfter` and use it in the `429` response.
8. Declare security scheme `bearerAuth` and attach the requirement to protected endpoints.
9. Add a link from the product creation response to the get-product-by-id operation.
10. Generate the specification with springdoc-openapi, open Swagger UI, and run a validator.
11. Rename a schema used in multiple places, update references, and compare before/after specs.

### Completion Criteria

- [ ] Component groups are clearly named and placed correctly inside `components`.
- [ ] Shared schemas, responses, parameters, and request bodies are referenced via `$ref`.
- [ ] No internal reference is missing or points to the wrong object type.
- [ ] Request and response schemas accurately reflect DTOs and validation.
- [ ] Security schemes and security requirements accurately express authentication scope.
- [ ] Headers and examples match actual HTTP responses.
- [ ] Swagger UI renders the shared schemas and responses.
- [ ] OpenAPI validator confirms the document is valid.
- [ ] Component changes are impact-reviewed and archived with the contract version.

## Next Steps

After this lesson, combine Components with Paths, Operations, Parameters, and Responses; explore schema composition, security, callbacks, and `springdoc-openapi` customizers in greater depth. Whenever you modify a DTO or annotation, review `components` and the generated `$ref` pointers, then verify both the document and HTTP behavior to keep the contract consistent.
