# Schema, Parameter, Response, RequestBody, and SecurityScheme in Components

OpenAPI allows declaring reusable elements inside the `components` object. Elements such as schemas, parameters, responses, request bodies, and security schemes let multiple operations share one definition, keep contracts consistent, and reduce duplication in the document. Springdoc-openapi can infer many components from Spring Boot controllers and DTOs; when an explicit contract is needed, annotations or configuration can be added to describe and reference them.

## 1. Components as a Shared Definition Store

In OpenAPI, `components` is where definitions are placed so they can be referenced from multiple places in the document. Common groups include:

| Group | Key in `components` | Purpose |
|---|---|---|
| Schema | `schemas` | Describe data structures, DTOs, enums, and nested types |
| Parameter | `parameters` | Reuse path, query, header, or cookie parameters |
| Response | `responses` | Reuse response descriptions by status code |
| Request body | `requestBodies` | Reuse request payloads with media types and schemas |
| Security scheme | `securitySchemes` | Declare authentication methods such as API key, Basic, Bearer, OAuth2, or OpenID Connect |
| Other groups | `examples`, `headers`, `links`, `callbacks` | Reuse examples, response headers, operation links, and callbacks |

A definition placed in `components` does not create an endpoint or automatically apply to operations. It takes effect only when referenced via `$ref` or applied in the corresponding configuration. For example, declaring `Product` in `components.schemas` does not automatically give `GET /products/{id}` that response schema; the operation must point to `#/components/schemas/Product`.

Structure example:

```yaml
openapi: 3.1.0
info:
  title: Store API
  version: 1.0.0
paths: {}
components:
  schemas: {}
  parameters: {}
  responses: {}
  requestBodies: {}
  securitySchemes: {}
```

Component names are keys chosen by the document author and are case-sensitive. Use names that express their role consistently, such as `Product`, `CreateProductRequest`, `ProductNotFound`, or `BearerAuth`.

## 2. $ref Connects Operations to Components

`$ref` is a reference to an object defined elsewhere. For components in the same document, the standard syntax is a JSON Pointer starting with `#/components/`:

```yaml
schema:
  $ref: '#/components/schemas/Product'
```

Common reference paths:

| Referenced Object | Path |
|---|---|
| Schema `Product` | `#/components/schemas/Product` |
| Parameter `PageSize` | `#/components/parameters/PageSize` |
| Response `NotFound` | `#/components/responses/NotFound` |
| Request body `CreateProduct` | `#/components/requestBodies/CreateProduct` |
| Security scheme `BearerAuth` | `#/components/securitySchemes/BearerAuth` |

Example of the same schema used in two responses:

```yaml
paths:
  /products/{id}:
    get:
      responses:
        '200':
          description: Product found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
  /products:
    post:
      responses:
        '201':
          description: Product created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
```

When a component changes, every operation referencing it receives the updated definition. This avoids duplicating schemas, yet it also means editing a widely shared component can impact many endpoints. Evaluate the impact of changes before modifying broadly shared components.

## 3. Schemas Describe Data Structures

An OpenAPI Schema describes data types, properties, constraints, and relationships between values. In Spring Boot APIs, schemas typically correspond to request DTOs, response DTOs, enums, or nested data types.

Product component schema example:

```yaml
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
          type: string
          format: uuid
          description: Product identifier
        name:
          type: string
          minLength: 1
          maxLength: 120
          example: Ballpoint pen
        price:
          type: number
          minimum: 0
          example: 12000
        active:
          type: boolean
          default: true
```

Key fields:

- `type` specifies the type such as `object`, `string`, `integer`, `number`, `boolean`, or `array`.
- `properties` lists the fields of an object.
- `required` lists fields that must be present on the object. Properties absent from this list are generally optional.
- `format` refines the format such as `uuid`, `date`, `date-time`, `int32`, or `int64`.
- `enum` restricts the allowed values.
- `minimum`, `maximum`, `minLength`, `maxLength`, `minItems`, and `maxItems` describe value limits.
- `description`, `example`, and `default` help readers understand how to use the field.

A schema does not enforce validation inside a controller by itself. For instance, `minimum: 0` documents the minimum value in the contract; the application still needs validation or business logic to reject negative inputs.

### Arrays and Nested Objects

A property can reference another schema or describe an array directly:

```yaml
components:
  schemas:
    ProductLine:
      type: object
      required: [product, quantity]
      properties:
        product:
          $ref: '#/components/schemas/Product'
        quantity:
          type: integer
          minimum: 1
    ProductOrder:
      type: object
      properties:
        orderId:
          type: string
        lines:
          type: array
          items:
            $ref: '#/components/schemas/ProductLine'
```

### Enums and Composite Types

Enums express a finite set of values:

```yaml
components:
  schemas:
    ProductStatus:
      type: string
      enum:
        - DRAFT
        - ACTIVE
        - ARCHIVED
```

When a schema accepts multiple valid forms, OpenAPI supports composition keywords such as `oneOf`, `anyOf`, and `allOf`:

```yaml
components:
  schemas:
    PaymentMethod:
      oneOf:
        - $ref: '#/components/schemas/CardPayment'
        - $ref: '#/components/schemas/BankTransfer'
    AuditedEntity:
      type: object
      properties:
        createdAt:
          type: string
          format: date-time
    AuditedProduct:
      allOf:
        - $ref: '#/components/schemas/Product'
        - $ref: '#/components/schemas/AuditedEntity'
```

`oneOf` requires data to match exactly one schema in the list; `anyOf` permits matching one or more schemas; `allOf` combines schemas into a single model. When using polymorphic types, consider adding a `discriminator` so client generators can recognize subtypes. Verify tool support among OpenAPI consumers, because not all generators handle every composition construct identically.

## 4. Parameters Describe Data in URLs, Headers, and Cookies

An OpenAPI Parameter Object describes a value passed with a request outside the request body. Parameters have four standard locations:

| `in` | Location | Example |
|---|---|---|
| `path` | Segment in the URL path | `/products/{id}` |
| `query` | Query string | `?page=0&size=20` |
| `header` | HTTP header | `X-Request-Id: abc-123` |
| `cookie` | Cookie | `sessionId=...` |

Reusable query parameter example:

```yaml
components:
  parameters:
    PageNumber:
      name: page
      in: query
      required: false
      description: Zero-based page index
      schema:
        type: integer
        minimum: 0
        default: 0
    PageSize:
      name: size
      in: query
      required: false
      description: Number of items per page
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
```

Operation using parameters via `$ref`:

```yaml
paths:
  /products:
    get:
      parameters:
        - $ref: '#/components/parameters/PageNumber'
        - $ref: '#/components/parameters/PageSize'
      responses:
        '200':
          description: Product list
```

Rules to keep in mind:

- A `path` parameter must always have `required: true`, since it is part of the declared URL.
- The `name` and `in` pair uniquely identifies a parameter. The same name in a different location is a separate parameter.
- A parameter can use `schema` for simple types or `content` for complex media-type representations; typically query/path/header parameters use `schema`.
- `style` and `explode` control how arrays or objects are serialized in URLs/headers. Declare them only when specific formatting is required.
- Never use a Parameter Object to describe a JSON body. Bodies belong in `requestBody`.
- The `Accept`, `Content-Type`, and `Authorization` headers are reserved by OpenAPI for content negotiation or security; declaring them as regular header parameters is ignored per the specification. Use `requestBody.content`/response `content` for media types and `securitySchemes` for authentication.

In Spring MVC, `@PathVariable`, `@RequestParam`, `@RequestHeader`, and `@CookieValue` allow springdoc to infer parameters. You can add `@Parameter` to document meaning, examples, schemas, or requiredness. For parameters reused across operations, `components.parameters` maintains a single shared definition.

## 5. RequestBody Describes Payloads Sent by Clients

A Request Body Object describes the request payload, commonly used with POST, PUT, or PATCH. Its key properties are:

- `description`: explains what content must be sent.
- `required`: indicates whether the body is mandatory.
- `content`: maps media types to corresponding schemas and metadata.

JSON request body example:

```yaml
components:
  requestBodies:
    CreateProduct:
      description: Product details to create
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateProductRequest'
```

Operation referencing that request body:

```yaml
paths:
  /products:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateProduct'
      responses:
        '201':
          description: Product created
```

A request body can support multiple media types:

```yaml
requestBody:
  required: true
  content:
    application/json:
      schema:
        $ref: '#/components/schemas/CreateProductRequest'
    application/xml:
      schema:
        $ref: '#/components/schemas/ProductXml'
```

Each media type can reference its own schema. Declaring multiple formats in OpenAPI must match the actual capabilities of the controller, `consumes`, and `HttpMessageConverter`.

### Multipart and Form Bodies

For file uploads, request bodies typically use `multipart/form-data`:

```yaml
requestBody:
  required: true
  content:
    multipart/form-data:
      schema:
        type: object
        required: [file, metadata]
        properties:
          file:
            type: string
            format: binary
          metadata:
            $ref: '#/components/schemas/UploadMetadata'
```

For URL-encoded forms, the media type is `application/x-www-form-urlencoded`; the schema is usually an object whose properties correspond to form fields. For multipart, `encoding` can be used to describe the media type or headers of individual parts when needed.

By HTTP convention, request bodies are typically used with POST, PUT, and PATCH. OpenAPI can represent a request body on other operations, though body semantics on GET, HEAD, and DELETE are not uniformly defined in HTTP and some clients/proxies do not support them. Design such bodies only when participating systems have an explicit agreement.

## 6. Responses Describe Possible Server Results

The Responses Object maps HTTP status codes to Response Objects. Every response requires `description`; if a body is returned, declare `content` by media type and schema.

Reusable response example:

```yaml
components:
  responses:
    NotFound:
      description: Resource not found
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
    ValidationError:
      description: Invalid request data
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
```

Operation referencing responses:

```yaml
paths:
  /products/{id}:
    get:
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Product found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
        '404':
          $ref: '#/components/responses/NotFound'
        default:
          description: Unspecified error
```

Common status codes:

| Status | Common Meaning | Body |
|---|---|---|
| `200` | Request succeeded | May include a representation |
| `201` | Resource created | Typically returns representation or `Location` header |
| `202` | Accepted for asynchronous processing | May describe task tracking info |
| `204` | Succeeded with no content | Do not declare `content` |
| `400` | Invalid request | Typically includes error description |
| `401` | Unauthenticated or invalid credentials | May include error details |
| `403` | Forbidden from performing action | May include error details |
| `404` | Resource not found | May include error details |
| `409` | State or data conflict | May include conflict details |
| `415` | Unsupported request media type | May include error description |
| `500` | Unexpected server error | Typically uses shared error schema |

`default` can describe responses for status codes not explicitly listed. Avoid documenting only success responses when the API actually returns important business errors. When a response has no body, such as `204 No Content`, provide only `description` and any headers, without declaring a fake body schema.

Responses can include `headers` to document returned headers such as `Location`, `ETag`, or `X-RateLimit-Remaining`. `links` can describe how to invoke follow-up operations from data in the response.

## 7. SecurityScheme Declares Authentication Mechanisms

`securitySchemes` describes how clients supply authentication credentials. Declaring a security scheme only defines the mechanism in the contract; it does not enable Spring Security, issue tokens, or protect endpoints at runtime.

Common types:

| Type | Key Fields | Usage Example |
|---|---|---|
| API key | `type: apiKey`, `in`, `name` | API key in `X-API-Key` header, query, or cookie |
| HTTP Basic | `type: http`, `scheme: basic` | Username and password via HTTP Basic |
| HTTP Bearer | `type: http`, `scheme: bearer`, optional `bearerFormat` | JWT bearer token in Authorization header |
| OAuth2 | `type: oauth2`, `flows` | Authorization Code, Client Credentials, Password, or Implicit per supported setup |
| OpenID Connect | `type: openIdConnect`, `openIdConnectUrl` | Discover OpenID Connect configuration from discovery URL |

### API Key

```yaml
components:
  securitySchemes:
    ApiKeyAuth:
      type: apiKey
      in: header
      name: X-API-Key
```

Clients send the `X-API-Key` header as required by the API. If the API key resides in a query parameter or cookie, update `in` and `name` to match the actual design.

### HTTP Bearer and Basic

```yaml
components:
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
    BasicAuth:
      type: http
      scheme: basic
```

With Bearer, clients typically send `Authorization: Bearer <token>`. `bearerFormat: JWT` is only a hint to readers; OpenAPI does not validate JWT structure or signatures.

### OAuth2

OAuth2 declares one or more flows. Client Credentials example:

```yaml
components:
  securitySchemes:
    OAuth2:
      type: oauth2
      flows:
        clientCredentials:
          tokenUrl: https://identity.example.test/oauth2/token
          scopes:
            products:read: Read products
            products:write: Create and update products
```

`tokenUrl` and scopes must reflect the real authorization server. Other flows have their own properties, such as `authorizationUrl` for Authorization Code or Implicit. Publish only flows that the system actually supports.

### OpenID Connect

```yaml
components:
  securitySchemes:
    OpenID:
      type: openIdConnect
      openIdConnectUrl: https://identity.example.test/.well-known/openid-configuration
```

The discovery URL must point to a valid OpenID Connect configuration document from the identity provider.

## 8. Applying Security Requirements to the API

Declaring a scheme in `components.securitySchemes` does not force operations to require that scheme. To require authentication, attach a Security Requirement at the document level or operation level.

Require Bearer across the whole API:

```yaml
security:
  - BearerAuth: []
```

Require a specific OAuth2 scope:

```yaml
security:
  - OAuth2:
      - products:read
```

Apply to a single operation:

```yaml
paths:
  /products:
    get:
      security:
        - BearerAuth: []
      responses:
        '200':
          description: Product list
```

If the document sets global security, an operation can write `security: []` to clear the inherited requirement:

```yaml
paths:
  /health:
    get:
      security: []
      responses:
        '200':
          description: Service is running
```

In a Security Requirement Object, placing multiple schemes inside one object means the client must satisfy all schemes in that object. Multiple objects in the list represent alternatives (OR). Example:

```yaml
security:
  - BearerAuth: []
  - ApiKeyAuth: []
```

The example above accepts either Bearer or API key. If both are required simultaneously:

```yaml
security:
  - BearerAuth: []
    ApiKeyAuth: []
```

For OAuth2, the scope list specifies the permissions needed for the operation. For API key and HTTP authentication, the scope array is normally empty.

## 9. Connecting Components with springdoc-openapi

Springdoc automatically generates many schemas from DTOs and mappings. When richer descriptions are needed, use Swagger Core annotations. Common annotations:

| Annotation | Placement | Purpose |
|---|---|---|
| `@Schema` | DTO, field, record component, data type | Describe schema, property, example, enum, and constraints |
| `@Parameter` | Handler parameter | Supplement parameter descriptions |
| `@ApiResponse` / `@ApiResponses` | Controller method | Describe responses by status code |
| `@Content` | Request body or response | Describe media type and schema |
| `@io.swagger.v3.oas.annotations.parameters.RequestBody` | Method or parameter as appropriate | Customize request body in OpenAPI |
| `@SecurityScheme` | Configuration class or supported annotation target | Register a security scheme |
| `@SecurityRequirement` | Class or method | Require a scheme for an API or operation |
| `@OpenAPIDefinition` | Configuration class | Document metadata and default security |

### Describing Schemas with @Schema

```java
public record ProductResponse(
    @Schema(description = "Product ID", format = "uuid")
    UUID id,

    @Schema(description = "Product name", example = "Ballpoint pen", maxLength = 120)
    String name,

    @Schema(description = "Status", allowableValues = {"ACTIVE", "ARCHIVED"})
    String status
) {}
```

### Defining and Applying a Bearer Scheme with Annotations

```java
@Configuration
@SecurityScheme(
    name = "BearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiSecurityConfiguration {
}
```

Apply to an entire controller:

```java
@RestController
@RequestMapping("/api/products")
@SecurityRequirement(name = "BearerAuth")
class ProductController {
    // Endpoints requiring a Bearer token
}
```

Or apply only to a single operation by placing `@SecurityRequirement` on the method. For public endpoints, omit the requirement or explicitly configure `security = {}` depending on how the documentation is structured.

### Describing Responses and Request Bodies

```java
public record ApiError(String code, String message) {}

@Operation(summary = "Get product by ID")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Product found",
        content = @Content(
            mediaType = MediaType.APPLICATION_JSON_VALUE,
            schema = @Schema(implementation = ProductResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Product not found",
        content = @Content(
            mediaType = MediaType.APPLICATION_PROBLEM_JSON_VALUE,
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
@GetMapping("/{id}")
ProductResponse find(@PathVariable UUID id) {
    return productService.findById(id);
}
```

When describing a request body more explicitly, use the `RequestBody` annotation from the Swagger package with its fully qualified name to avoid confusion with Spring's `org.springframework.web.bind.annotation.RequestBody`. OpenAPI annotations control documentation only; reading the body, validating tokens, and authorization remain handled by Spring MVC, converters, and Spring Security.

## 10. Complete Components Example Shared Across Operations

The following example combines schemas, parameters, request bodies, responses, and a security scheme in one document:

```yaml
openapi: 3.1.0
info:
  title: Store API
  version: 1.0.0
paths:
  /products:
    get:
      summary: List products
      security:
        - BearerAuth: []
      parameters:
        - $ref: '#/components/parameters/PageNumber'
        - $ref: '#/components/parameters/PageSize'
      responses:
        '200':
          description: Product list
          content:
            application/json:
              schema:
                type: array
                items:
                  $ref: '#/components/schemas/Product'
    post:
      summary: Create product
      security:
        - BearerAuth: []
      requestBody:
        $ref: '#/components/requestBodies/CreateProduct'
      responses:
        '201':
          description: Product created
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
        '400':
          $ref: '#/components/responses/ValidationError'
  /products/{id}:
    get:
      summary: Get product details
      security:
        - BearerAuth: []
      parameters:
        - name: id
          in: path
          required: true
          schema:
            type: string
            format: uuid
      responses:
        '200':
          description: Product found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/Product'
        '404':
          $ref: '#/components/responses/NotFound'
  /health:
    get:
      summary: Check service health
      security: []
      responses:
        '200':
          description: Service is running
components:
  schemas:
    Product:
      type: object
      required: [id, name, price]
      properties:
        id:
          type: string
          format: uuid
        name:
          type: string
          minLength: 1
        price:
          type: number
          minimum: 0
    CreateProductRequest:
      type: object
      required: [name, price]
      properties:
        name:
          type: string
        price:
          type: number
          minimum: 0
    ProblemDetail:
      type: object
      properties:
        type:
          type: string
          format: uri-reference
        title:
          type: string
        status:
          type: integer
        detail:
          type: string
  parameters:
    PageNumber:
      name: page
      in: query
      schema:
        type: integer
        minimum: 0
        default: 0
    PageSize:
      name: size
      in: query
      schema:
        type: integer
        minimum: 1
        maximum: 100
        default: 20
  requestBodies:
    CreateProduct:
      required: true
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateProductRequest'
  responses:
    NotFound:
      description: Resource not found
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
    ValidationError:
      description: Invalid data
      content:
        application/problem+json:
          schema:
            $ref: '#/components/schemas/ProblemDetail'
  securitySchemes:
    BearerAuth:
      type: http
      scheme: bearer
      bearerFormat: JWT
```

The key point in the example is that each component has a clear responsibility and is wired via `$ref`. Schema `Product` serves responses; `CreateProductRequest` serves requests; `PageNumber` and `PageSize` are shared for paginated queries; error responses are defined once; and `BearerAuth` is attached to operations needing authentication. The `/health` endpoint is public via `security: []`.

## 11. Verifying Components in the Generated Document

After starting the Spring Boot application, fetch the JSON document at `/v3/api-docs` or YAML at `/v3/api-docs.yaml`. Inside `components`, verify:

1. **schemas:** do schema names, properties, types, `required`, enums, formats, and constraints match the DTOs?
2. **parameters:** do names, locations, types, defaults, and required flags match controller parameters?
3. **requestBodies:** do media types and schemas match the payloads endpoints actually read?
4. **responses:** do status codes, descriptions, media types, and schemas reflect actual results?
5. **securitySchemes:** do authentication types, header names, token URLs, or scopes match the identity provider config?
6. **references:** does every `$ref` point to an existing component without typos or casing mismatches?

Swagger UI is convenient for browsing and trying operations, yet JSON/YAML is the contract artifact to verify. If Swagger UI does not render a schema as expected, first determine whether the data in `/v3/api-docs` itself is already accurate.

## 12. Common Mistakes When Organizing Components

| Issue | Cause | How to Fix |
|---|---|---|
| `$ref` fails to resolve | Wrong component name, wrong JSON Pointer path, or casing mismatch | Cross-check exact keys inside `components` |
| Component declared but absent from operations | Not referenced from paths, request bodies, responses, or security | Add the appropriate `$ref` or Security Requirement |
| Success response has a schema but errors lack bodies | Missing `content` for error status codes | Create an error schema and shared responses if the API returns error payloads |
| Body parameter documented as query | Wrong annotation used or data placed in wrong location | Use `@RequestBody` for bodies; `@RequestParam` for queries |
| Swagger UI requires auth for a public endpoint | Global Security Requirement inherited | Set `security: []` on the public operation or narrow requirement scope |
| Document shows Bearer scheme yet API accepts tokenless calls | Only documented without configuring runtime security | Configure Spring Security and test actual access controls |
| Shared schema change impacts many endpoints | Multiple operations reference the same component | Assess contract impact and consider separate schemas when models truly diverge |
| Collision between similarly named schemas | Multiple DTOs or generics share a simple class name | Use explicit component names and review springdoc schema naming rules |

Do not copy-paste a component merely to avoid an intentional change. Reuse when operations genuinely share the same contract; if two DTOs have different business meanings or lifecycles, separate schemas allow independent evolution and prevent accidentally widening contracts.

## 13. Workflow for Designing and Maintaining Components

When building an API contract, you can follow this sequence:

1. Identify DTOs and schemas reused across multiple operations.
2. Define shared parameters such as pagination, filtering, request ID, or tenant ID.
3. Create request body components for reused payloads and declare accurate media types.
4. Standardize success and error responses, especially common errors like validation, not found, and conflict.
5. Declare security schemes matching the actual authentication mechanisms.
6. Attach components to operations using `$ref` and Security Requirements.
7. Validate the JSON/YAML document, confirm all references resolve, and diff contracts across releases.

Components are the foundation of structured, readable, and consistent OpenAPI documentation. Combining inference from Spring Boot DTOs/controllers with shared components reduces duplication, while every definition must still faithfully reflect the application's HTTP behavior and security policy.

## 14. References

- [OpenAPI Specification – Components Object](https://spec.openapis.org/oas/latest.html#components-object): list of reusable components and referencing rules.
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object): data types, properties, composition, and schema constraints.
- [OpenAPI Specification – Parameter Object](https://spec.openapis.org/oas/latest.html#parameter-object): parameter locations, serialization, and schemas.
- [OpenAPI Specification – Request Body Object](https://spec.openapis.org/oas/latest.html#request-body-object): request body descriptions and media types.
- [OpenAPI Specification – Responses Object](https://spec.openapis.org/oas/latest.html#responses-object): HTTP results by status code.
- [OpenAPI Specification – Security Scheme Object](https://spec.openapis.org/oas/latest.html#security-scheme-object): API key, HTTP authentication, OAuth2, and OpenID Connect.
- [Springdoc OpenAPI](https://springdoc.org/): Spring Boot integration, annotations, and OpenAPI document configuration.
- [Swagger Core Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations): annotations to enrich schemas, responses, and security metadata.
