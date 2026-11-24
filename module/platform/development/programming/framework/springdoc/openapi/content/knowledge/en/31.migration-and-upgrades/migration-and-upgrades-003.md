# Replacing @Api, @ApiOperation, and @ApiParam with Corresponding OpenAPI Annotations

Common Swagger 2 annotations in legacy Spring Boot projects include @Api, @ApiOperation, @ApiParam, @ApiModel, and @ApiModelProperty. When migrating to springdoc-openapi, replace them with OpenAPI 3 Swagger Core 3 annotations in the io.swagger.v3.oas.annotations package.

Core mappings:

- @Api becomes @Tag.
- @ApiOperation becomes @Operation.
- @ApiParam becomes @Parameter.
- @ApiModel and @ApiModelProperty become @Schema.
- Swagger 2 @ApiResponse becomes OpenAPI 3 @ApiResponse, with code/message changing to responseCode/description.

Renaming annotations alone is not enough to ensure accurate documentation. Some details previously declared inside annotations should now come from Spring MVC mappings, Java types, or the OpenAPI model. This guide covers replacing package imports, mapping attributes, handling responses/security/schemas, and verifying the document after migration.

## 1. Identify the two annotation systems

Swagger 2 annotations typically use the package:

~~~java
io.swagger.annotations.Api
io.swagger.annotations.ApiOperation
io.swagger.annotations.ApiParam
io.swagger.annotations.ApiModel
io.swagger.annotations.ApiModelProperty
~~~

OpenAPI 3 annotations use the package:

~~~java
io.swagger.v3.oas.annotations.tags.Tag
io.swagger.v3.oas.annotations.Operation
io.swagger.v3.oas.annotations.Parameter
io.swagger.v3.oas.annotations.media.Schema
io.swagger.v3.oas.annotations.responses.ApiResponse
~~~

Some annotation names are retained, such as ApiResponse and ApiResponses, but their packages and attributes changed. Therefore, when the IDE auto-imports, verify the full package rather than looking only at the short name.

Do not keep swagger-annotations 1.x and swagger-annotations 2.x side by side in code for an uncontrolled partial migration. The two systems share simple class names, making wrong imports likely and leading to inconsistent documentation.

## 2. Common annotation mapping table

| Swagger 2 | OpenAPI 3 | Purpose |
|---|---|---|
| @Api | @Tag | Group controllers or operations |
| @ApiOperation | @Operation | Describe an operation |
| @ApiParam | @Parameter | Describe path/query/header/cookie parameters |
| @ApiImplicitParam | @Parameter | Declare parameters without a matching Java argument |
| @ApiImplicitParams | @Parameters | Group multiple parameters |
| @ApiModel | @Schema | Describe a model/schema |
| @ApiModelProperty | @Schema | Describe a property within a schema |
| @ApiResponse | @ApiResponse | Describe a single response |
| @ApiResponses | @ApiResponses | Group multiple responses |
| @ApiIgnore | @Hidden, @Operation(hidden=true), or @Parameter(hidden=true) | Hide APIs or parameters |
| @Authorization | @SecurityRequirement combined with @SecurityScheme | Describe security |
| @AuthorizationScope | OAuth flow scopes inside @SecurityScheme | Declare OAuth scopes |

This is a starting map, not a one-to-one textual replacement. Review each attribute and where the annotation is placed.

## 3. Replace @Api with @Tag

In Swagger 2, @Api is commonly placed at the controller level to group operations:

~~~java
import io.swagger.annotations.Api;

@Api(
    value = "Orders",
    description = "Order management operations"
)
@RestController
@RequestMapping("/api/orders")
class OrderController {
}
~~~

In OpenAPI 3, use @Tag:

~~~java
import io.swagger.v3.oas.annotations.tags.Tag;

@Tag(
    name = "Orders",
    description = "Order management operations"
)
@RestController
@RequestMapping("/api/orders")
class OrderController {
}
~~~

name is the tag name used to group operations. description explains that group in the documentation.

If a controller contains multiple operation groups or one method belongs to a different tag from the controller, you can specify tags directly on @Operation:

~~~java
@Operation(
    summary = "Search orders",
    tags = {"Orders", "Search"}
)
~~~

Do not use @Tag to describe the HTTP method or URL. Spring MVC mappings such as @GetMapping and @PostMapping still define the route.

## 4. Replace @ApiOperation with @Operation

Swagger 2 example:

~~~java
import io.swagger.annotations.ApiOperation;

@ApiOperation(
    value = "Find order by ID",
    notes = "Returns only orders the user is authorized to access",
    nickname = "findOrderById"
)
@GetMapping("/{id}")
OrderResponse findById(@PathVariable String id) {
    // ...
}
~~~

OpenAPI 3:

~~~java
import io.swagger.v3.oas.annotations.Operation;

@Operation(
    summary = "Find order by ID",
    description = "Returns only orders the user is authorized to access",
    operationId = "findOrderById"
)
@GetMapping("/{id}")
OrderResponse findById(@PathVariable String id) {
    // ...
}
~~~

Commonly mapped attributes:

| Old @ApiOperation | New @Operation |
|---|---|
| value | summary |
| notes | description |
| nickname | operationId |
| hidden | hidden |
| authorizations | security |
| tags | tags |
| deprecated | deprecated |
| extensions | extensions |
| response/code | Usually moved to @ApiResponse or inferred by springdoc from the method return type |

summary should be concise and describe the action. description can explain conditions, constraints, or business behavior.

operationId must be unique within the document if client generators rely on it to name methods. Avoid creating duplicate operationIds after renaming controllers or methods.

## 5. @ApiOperation attributes that should not be replaced mechanically

Some old Swagger 2 attributes have no direct equivalent on @Operation:

| Old attribute | How to handle |
|---|---|
| httpMethod | Already defined by @GetMapping, @PostMapping, or equivalent mapping |
| consumes | Declare consumes on the Spring mapping |
| produces | Declare produces on the Spring mapping |
| response | Let springdoc infer from the return type; specify schema in @ApiResponse when overriding |
| responseContainer | Use the actual generic type such as List<T> or @ArraySchema when needed |
| code | Declare responseCode in @ApiResponse |
| authorizations | Use @SecurityRequirement and @SecurityScheme |
| protocols | Configure server URL/scheme per OpenAPI and deployment |
| position | No direct mapping; consider tag ordering or UI display configuration |

For example, consumes/produces belong to Spring's HTTP contract:

~~~java
@PostMapping(
    value = "/api/orders",
    consumes = MediaType.APPLICATION_JSON_VALUE,
    produces = MediaType.APPLICATION_JSON_VALUE
)
~~~

Do not turn them into arbitrary fields on @Operation. springdoc reads Spring's mappings to generate the appropriate requestBody and response content.

## 6. Replace @ApiParam with @Parameter

Swagger 2:

~~~java
import io.swagger.annotations.ApiParam;

@GetMapping("/{id}")
OrderResponse findById(
    @ApiParam(
        name = "id",
        value = "Order ID",
        required = true,
        example = "ORD-1001"
    )
    @PathVariable String id
) {
    // ...
}
~~~

OpenAPI 3:

~~~java
import io.swagger.v3.oas.annotations.Parameter;

@GetMapping("/{id}")
OrderResponse findById(
    @Parameter(
        description = "Order ID",
        example = "ORD-1001",
        required = true
    )
    @PathVariable String id
) {
    // ...
}
~~~

Parameter can describe path, query, header, and cookie parameters.

With Spring MVC, springdoc usually infers name, location, and type from @PathVariable, @RequestParam, @RequestHeader, or @CookieValue. Add @Parameter only for descriptions or adjustments that cannot be inferred from code.

If parameter names matter to clients, declare name explicitly to avoid relying on the compiler preserving parameter names.

## 7. Describe query parameters and default values

Example:

~~~java
@GetMapping
List<OrderResponse> search(
    @Parameter(
        description = "Order status",
        example = "PAID"
    )
    @RequestParam(required = false)
    OrderStatus status,

    @Parameter(
        description = "Maximum number of records",
        schema = @Schema(defaultValue = "20", minimum = "1", maximum = "100")
    )
    @RequestParam(defaultValue = "20")
    int limit
) {
    // ...
}
~~~

Spring binding's required and defaultValue must align with metadata in @Parameter. With @RequestParam(defaultValue = "20"), the parameter is normally optional from the request's perspective; documentation should reflect the right default.

Do not mark required=true just to make Swagger UI display an asterisk if the server actually accepts a missing parameter.

When declaring allowable values, you can use a schema enum:

~~~java
@Parameter(
    description = "Order status",
    schema = @Schema(
        allowableValues = {"PENDING", "PAID", "CANCELLED"}
    )
)
@RequestParam(required = false)
String status
~~~

If the Java type is already an enum, springdoc usually infers the value list. Only override when the documentation intentionally requires a different value set and runtime actually supports it.

## 8. Replace @ApiImplicitParam with @Parameter

@ApiImplicitParam is often used when a parameter does not appear as an explicit method argument, such as a header managed by a filter or gateway.

Swagger 2:

~~~java
@ApiImplicitParam(
    name = "X-Request-Id",
    value = "Request correlation ID",
    required = false,
    dataType = "string",
    paramType = "header"
)
@GetMapping("/api/orders")
List<OrderResponse> list() {
    // ...
}
~~~

OpenAPI 3:

~~~java
@Operation(
    summary = "List orders",
    parameters = {
        @Parameter(
            name = "X-Request-Id",
            description = "Request correlation ID",
            in = ParameterIn.HEADER,
            schema = @Schema(type = "string")
        )
    }
)
@GetMapping("/api/orders")
List<OrderResponse> list() {
    // ...
}
~~~

ParameterIn specifies the location: PATH, QUERY, HEADER, or COOKIE.

For authentication headers like Authorization, do not declare an ordinary header parameter manually if its real purpose is a security scheme. Use @SecurityScheme and @SecurityRequirement so Swagger UI understands the authentication mechanism properly.

## 9. Replace @ApiImplicitParams with @Parameters

Swagger 2:

~~~java
@ApiImplicitParams({
    @ApiImplicitParam(
        name = "X-Tenant-Id",
        value = "Tenant ID",
        paramType = "header",
        dataType = "string"
    ),
    @ApiImplicitParam(
        name = "X-Request-Id",
        value = "Correlation ID",
        paramType = "header",
        dataType = "string"
    )
})
~~~

OpenAPI 3:

~~~java
@Parameters({
    @Parameter(
        name = "X-Tenant-Id",
        description = "Tenant ID",
        in = ParameterIn.HEADER,
        schema = @Schema(type = "string")
    ),
    @Parameter(
        name = "X-Request-Id",
        description = "Correlation ID",
        in = ParameterIn.HEADER,
        schema = @Schema(type = "string")
    )
})
~~~

If the corresponding parameter is already in the method signature, prefer placing @Parameter directly on the argument. That keeps documentation tied closely to request binding and reduces duplicate declarations.

## 10. Use @ParameterObject for objects grouping query parameters

Some controllers use an object to group multiple query parameters:

~~~java
@GetMapping("/api/orders")
Page<OrderResponse> search(OrderSearchCriteria criteria) {
    // ...
}
~~~

If you want springdoc to expand the fields into query parameters, use @ParameterObject:

~~~java
import org.springdoc.core.annotations.ParameterObject;

@GetMapping("/api/orders")
Page<OrderResponse> search(
    @ParameterObject OrderSearchCriteria criteria
) {
    // ...
}
~~~

This is a springdoc helper annotation, not a Swagger 3 annotation directly replacing @ApiParam. It documents a query object property by property.

If the object is a JSON request body, do not use @ParameterObject; use @RequestBody and the DTO schema.

## 11. Replace @ApiModel with @Schema

Swagger 2:

~~~java
import io.swagger.annotations.ApiModel;

@ApiModel(
    value = "Order",
    description = "Order details"
)
public class OrderResponse {
}
~~~

OpenAPI 3:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "Order",
    description = "Order details"
)
public class OrderResponse {
}
~~~

@Schema can describe name, title, description, type, format, requiredMode, allowableValues, example, constraints, implementation, oneOf/anyOf/allOf, discriminator, accessMode, deprecated, and hidden.

Normally springdoc infers schemas from Java types and Jackson annotations. Only use @Schema when you need to supplement or adjust documentation.

## 12. Replace @ApiModelProperty with @Schema

Swagger 2:

~~~java
@ApiModelProperty(
    value = "Order ID",
    required = true,
    example = "ORD-1001",
    position = 1
)
private String id;
~~~

OpenAPI 3:

~~~java
@Schema(
    description = "Order ID",
    requiredMode = Schema.RequiredMode.REQUIRED,
    example = "ORD-1001"
)
private String id;
~~~

Common mappings:

| @ApiModelProperty | @Schema |
|---|---|
| value | description |
| name | name |
| dataType | type or implementation when genuinely needed |
| example | example |
| allowableValues | allowableValues |
| required | requiredMode |
| readOnly | accessMode = READ_ONLY |
| hidden | hidden |
| notes | description |
| deprecated | deprecated |
| accessMode | accessMode |

requiredMode clarifies how requiredness is specified. Depending on the swagger-annotations version, the old required attribute may be deprecated; use the API of the version managed by springdoc.

position has no direct equivalent in @Schema. If property display order is a requirement, consider Jackson's @JsonPropertyOrder or UI configuration, then inspect toolchain output.

## 13. Required, nullable, and allowEmptyValue

The springdoc migration guide maps @ApiModelProperty(allowEmptyValue = true) to @Schema(nullable = true). However, during migration you should understand the actual data semantics.

These concepts differ:

- Required: whether the property must be present.
- Nullable: whether the property is allowed to hold a null value.
- Empty string: whether the property can hold an empty string value.

In JSON, null and an empty string are two distinct values:

~~~json
{
  "nickname": null,
  "comment": ""
}
~~~

Do not equate nullable with allowing an empty string. If the API needs to accept empty strings, check Bean Validation such as @NotBlank, @NotEmpty, @Size and document the schema accordingly.

Example:

~~~java
@Schema(
    description = "Nickname, may be null",
    nullable = true
)
private String nickname;
~~~

OpenAPI 3.0 and 3.1 represent null differently. Check the generated OpenAPI version as well as the validators and client generators in use.

## 14. Replace Swagger 2 @ApiResponse with OpenAPI 3 @ApiResponse

The two annotations share the same name but have different packages and attributes.

Swagger 2:

~~~java
import io.swagger.annotations.ApiResponse;

@ApiResponse(
    code = 404,
    message = "Order not found",
    response = ApiError.class
)
~~~

OpenAPI 3:

~~~java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;

@ApiResponse(
    responseCode = "404",
    description = "Order not found",
    content = @Content(
        schema = @Schema(implementation = ApiError.class)
    )
)
~~~

Main attributes:

| Swagger 2 | OpenAPI 3 |
|---|---|
| code | responseCode as String |
| message | description |
| response | content.schema.implementation |
| responseContainer | @ArraySchema or matching schema |
| responseHeaders | headers |
| examples | @ExampleObject inside @Content |

If the response type is already inferred accurately from the method return type, do not re-declare the schema merely to repeat information. Use @ApiResponse to add status codes, descriptions, headers, or to override the response when necessary.

## 15. Declare multiple responses with @ApiResponses

Example:

~~~java
@Operation(summary = "Find order by ID")
@ApiResponses({
    @ApiResponse(
        responseCode = "200",
        description = "Order found",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = OrderResponse.class)
        )
    ),
    @ApiResponse(
        responseCode = "404",
        description = "Not found",
        content = @Content(
            mediaType = "application/json",
            schema = @Schema(implementation = ApiError.class)
        )
    )
})
@GetMapping("/{id}")
OrderResponse findById(@PathVariable String id) {
    // ...
}
~~~

@ApiResponses remains the container annotation in OpenAPI 3, but must be imported from io.swagger.v3.oas.annotations.responses.

Do not declare a 200 response with a schema that does not match the method return type. If a controller returns ResponseEntity<OrderResponse>, the documentation must accurately describe the actual body and possible status codes.

## 16. Describe collection responses

In Swagger 2, responseContainer was often used to indicate the return type was List or Set. In Spring, prefer declaring the actual generic type:

~~~java
@GetMapping
List<OrderResponse> list() {
    // ...
}
~~~

springdoc can infer an array schema from List<OrderResponse>.

If explicit response declaration is needed:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "List of orders",
    content = @Content(
        array = @ArraySchema(
            schema = @Schema(implementation = OrderResponse.class)
        )
    )
)
~~~

Do not use @Schema(implementation=OrderResponse.class) alone if the actual body is an array. When schemas have nested structures or complex generics, check the output OpenAPI JSON to make sure items are described accurately.

## 17. Describe the request body instead of using @ApiParam

@ApiParam is meant for parameters, not the modern way to describe a request body.

Spring MVC:

~~~java
@PostMapping("/api/orders")
OrderResponse create(
    @RequestBody CreateOrderRequest request
) {
    // ...
}
~~~

springdoc infers requestBody and its schema from CreateOrderRequest.

If additional description is needed:

~~~java
@PostMapping("/api/orders")
OrderResponse create(
    @io.swagger.v3.oas.annotations.parameters.RequestBody(
        description = "Information required to create an order",
        required = true
    )
    @RequestBody
    CreateOrderRequest request
) {
    // ...
}
~~~

Here there are two annotations with the same simple name RequestBody: one from Spring and one from OpenAPI. You can use the fully qualified name or import the OpenAPI annotation unambiguously to avoid confusion.

If you only need to describe the DTO, @Schema on the request class or fields is usually easier to maintain.

## 18. Replace @ApiIgnore with @Hidden or the hidden flag

Swagger 2:

~~~java
@ApiIgnore
@GetMapping("/internal/diagnostics")
Map<String, Object> diagnostics() {
    // ...
}
~~~

OpenAPI 3 can use:

~~~java
@Hidden
@GetMapping("/internal/diagnostics")
Map<String, Object> diagnostics() {
    // ...
}
~~~

Other options:

~~~java
@Operation(hidden = true)
@GetMapping("/internal/diagnostics")
Map<String, Object> diagnostics() {
    // ...
}
~~~

Hide a parameter:

~~~java
@GetMapping("/api/orders")
List<OrderResponse> list(
    @Parameter(hidden = true)
    @RequestHeader("X-Internal-Trace") String trace
) {
    // ...
}
~~~

Choose the right scope:

- @Hidden on a controller or method to hide it from OpenAPI.
- @Operation(hidden = true) to hide a single operation.
- @Parameter(hidden = true) to hide a single parameter.

Hiding from documentation does not protect the endpoint. Authorization, network policies, and Spring Security must still enforce access control.

## 19. Replace authorization annotations with security schemes

Swagger 2 often uses @Authorization or the authorizations attribute on @Api/@ApiOperation. OpenAPI 3 separates two concepts:

1. @SecurityScheme defines the authentication method.
2. @SecurityRequirement requires an operation to use that scheme.

Bearer JWT example:

~~~java
import org.springframework.context.annotation.Configuration;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;

@Configuration
@SecurityScheme(
    name = "bearerAuth",
    type = SecuritySchemeType.HTTP,
    scheme = "bearer",
    bearerFormat = "JWT"
)
class OpenApiSecurityConfiguration {
}
~~~

Apply on an operation:

~~~java
@Operation(
    summary = "Get account info",
    security = @SecurityRequirement(name = "bearerAuth")
)
@GetMapping("/api/me")
AccountResponse me() {
    // ...
}
~~~

Do not declare Authorization as an ordinary query or header parameter if it is an authentication mechanism. Security schemes allow Swagger UI to show the Authorize button and document credentials properly per OpenAPI.

## 20. Migrate OAuth scopes

Swagger 2 has @AuthorizationScope to describe scopes. In OpenAPI 3, scopes are declared inside the OAuth flow of @SecurityScheme.

Example:

~~~java
import org.springframework.context.annotation.Configuration;
import io.swagger.v3.oas.annotations.enums.SecuritySchemeType;
import io.swagger.v3.oas.annotations.security.SecurityScheme;
import io.swagger.v3.oas.annotations.security.OAuthFlow;
import io.swagger.v3.oas.annotations.security.OAuthFlows;
import io.swagger.v3.oas.annotations.security.OAuthScope;

@Configuration
@SecurityScheme(
    name = "oauth2",
    type = SecuritySchemeType.OAUTH2,
    flows = @OAuthFlows(
        authorizationCode = @OAuthFlow(
            authorizationUrl = "https://auth.example.com/oauth/authorize",
            tokenUrl = "https://auth.example.com/oauth/token",
            scopes = {
                @OAuthScope(
                    name = "orders.read",
                    description = "Read orders"
                ),
                @OAuthScope(
                    name = "orders.write",
                    description = "Create and update orders"
                )
            }
        )
    )
)
class OpenApiOAuthConfiguration {
}
~~~

Require a scope on an operation:

~~~java
@Operation(
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"orders.read"}
    )
)
~~~

Scopes are part of security schemes and requirements. Do not convert @AuthorizationScope into @Parameter because scopes are not HTTP parameters.

## 21. Convert @ApiOperation.authorizations to @SecurityRequirement

Old example:

~~~java
@ApiOperation(
    value = "Update order",
    authorizations = {
        @Authorization(value = "oauth2",
            scopes = {
                @AuthorizationScope(
                    scope = "orders.write",
                    description = "Update order"
                )
            }
        )
    }
)
~~~

New:

~~~java
@Operation(
    summary = "Update order",
    security = @SecurityRequirement(
        name = "oauth2",
        scopes = {"orders.write"}
    )
)
~~~

The name in SecurityRequirement must match the name of @SecurityScheme. If they do not match, the document can end up with a requirement referencing a nonexistent scheme.

After migration, check both components.securitySchemes and security at the root/operation level in the OpenAPI JSON.

## 22. Replace response header annotations

If Swagger 2 declared response headers, OpenAPI 3 uses @Header inside @ApiResponse:

~~~java
@ApiResponse(
    responseCode = "200",
    description = "Success",
    headers = {
        @Header(
            name = "ETag",
            description = "Resource version tag",
            schema = @Schema(type = "string")
        )
    }
)
~~~

A response header is different from a request header parameter. One lives in the Response Object, and the other lives in the Parameter Object.

For shared headers sent by the client such as X-Request-Id, use @Parameter(in = ParameterIn.HEADER). For headers returned by the server, use @Header inside @ApiResponse.

## 23. Replace examples and allowable values

Swagger 2 may declare examples inside @ApiParam or @ApiModelProperty. OpenAPI 3 can use:

- @Parameter(example = "...") for parameters.
- @Schema(example = "...") for properties or schemas.
- @ExampleObject inside @Content for request/response examples.

Request body example:

~~~java
@io.swagger.v3.oas.annotations.parameters.RequestBody(
    description = "Order creation details",
    content = @Content(
        examples = @ExampleObject(
            name = "Standard order",
            value = """
                {
                  "customerId": "CUS-1001",
                  "items": [
                    {
                      "productId": "SKU-01",
                      "quantity": 2
                    }
                  ]
                }
                """
        )
    )
)
~~~

This is an OpenAPI RequestBody annotation example; when used alongside Spring @RequestBody, distinguish the two packages or use the fully qualified name.

Examples must be valid payloads per the schema and must not contain sensitive real data. If an example mismatches required fields or enums, Swagger UI may construct failing requests.

## 24. Replace polymorphism and discriminator descriptions

Swagger 2 @ApiModel may use subTypes and discriminator. OpenAPI 3 expresses this more explicitly via oneOf/allOf and discriminator in @Schema.

Example:

~~~java
@Schema(
    name = "Payment",
    oneOf = {
        CardPayment.class,
        BankTransferPayment.class
    },
    discriminatorProperty = "paymentType"
)
public interface Payment {
}
~~~

Subtypes:

~~~java
@Schema(name = "CardPayment")
public class CardPayment implements Payment {
    private String cardToken;
}
~~~

~~~java
@Schema(name = "BankTransferPayment")
public class BankTransferPayment implements Payment {
    private String bankAccount;
}
~~~

Verify the discriminator mapping in the OpenAPI output. Declaring Java inheritance alone does not guarantee every client generator infers the union type properly.

If a subtype uses a discriminator value different from the class name, configure explicit mapping according to the capabilities of the swagger-annotations version in use.

## 25. No need to replace annotations when Spring already provides metadata

Some Swagger 2 annotations may repeat information already expressed in Spring MVC:

- @ApiOperation.httpMethod duplicates @GetMapping/@PostMapping.
- @ApiParam.name duplicates @PathVariable("id") or @RequestParam("status").
- consumes/produces duplicate attributes on the mapping.
- response type duplicates the method return type.
- required duplicates @RequestParam(required=true) or Bean Validation.

When migrating, prefer the runtime source of truth. If Spring already knows the method, path, parameter type, or media type, let springdoc infer it.

Only add OpenAPI annotations when describing information the framework cannot infer or when intentionally overriding it.

This prevents documentation from drifting out of sync with controllers during future refactors.

## 26. Complete controller migration example

Swagger 2:

~~~java
import io.swagger.annotations.Api;
import io.swagger.annotations.ApiOperation;
import io.swagger.annotations.ApiParam;
import io.swagger.annotations.ApiResponse;
import io.swagger.annotations.ApiResponses;

@Api(
    value = "Orders",
    description = "Order management operations"
)
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @ApiOperation(
        value = "Find order",
        notes = "Find by order ID",
        nickname = "findOrderById"
    )
    @ApiResponses({
        @ApiResponse(
            code = 200,
            message = "Order found",
            response = OrderResponse.class
        ),
        @ApiResponse(
            code = 404,
            message = "Not found"
        )
    })
    @GetMapping("/{id}")
    OrderResponse findById(
        @ApiParam(
            value = "Order ID",
            required = true,
            example = "ORD-1001"
        )
        @PathVariable String id
    ) {
        // ...
    }
}
~~~

OpenAPI 3:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.tags.Tag;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;

@Tag(
    name = "Orders",
    description = "Order management operations"
)
@RestController
@RequestMapping("/api/orders")
class OrderController {

    @Operation(
        summary = "Find order",
        description = "Find by order ID",
        operationId = "findOrderById"
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "Order found",
            content = @Content(
                schema = @Schema(
                    implementation = OrderResponse.class
                )
            )
        ),
        @ApiResponse(
            responseCode = "404",
            description = "Not found"
        )
    })
    @GetMapping("/{id}")
    OrderResponse findById(
        @Parameter(
            description = "Order ID",
            required = true,
            example = "ORD-1001"
        )
        @PathVariable String id
    ) {
        // ...
    }
}
~~~

In this example, the Spring mapping still defines GET /api/orders/{id}. @Operation only describes the operation. The return type OrderResponse already tells springdoc the response schema; the explicit schema inside @ApiResponse is shown here to illustrate how to override or pin a schema.

If you do not need to override the response, you can omit content so springdoc uses return type inference, then verify the output.

## 27. Dependencies and imports to update

When migrating from Springfox to springdoc, remove unnecessary Swagger 2/Springfox dependencies and add the springdoc starter matching Spring MVC or WebFlux.

Maven example for Spring MVC:

~~~xml
<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>3.x.y</version>
</dependency>
~~~

For WebFlux, use the corresponding webflux UI starter. Choose the version according to the Spring Boot major version and the springdoc compatibility table.

Do not retain the following dependencies solely to preserve old annotations:

- springfox-swagger2.
- springfox-swagger-ui.
- springfox-boot-starter.
- swagger-annotations 1.x if the code has moved to OpenAPI 3.

The springdoc starter already brings in a compatible OpenAPI 3 swagger-annotations version. Avoid manually adding a different swagger-annotations version without a clear compatibility reason.

## 28. Find remaining Swagger 2 annotations

You can use ripgrep to scan the source:

~~~bash
rg -n "io\.swagger\.annotations|@Api\b|@ApiOperation\b|@ApiParam\b|@ApiModel\b|@ApiModelProperty\b|@ApiIgnore\b|@ApiImplicitParam\b" src
~~~

Check old dependencies in Maven:

~~~bash
mvn dependency:tree | findstr /i "springfox swagger-annotations"
~~~

Or Gradle:

~~~bash
./gradlew dependencies
~~~

Do not search only for annotation names. Some imports may be aliased, use fully qualified names, or live in other modules. Inspect the dependency tree of all relevant modules.

After migration, the code should have no io.swagger.annotations.* imports, and legacy Swagger 2 dependencies should no longer resolve unless another library has an evaluated requirement for them.

## 29. Avoid conflicting annotations with identical names

Several names are used in both Swagger 2 and OpenAPI 3:

- ApiResponse.
- ApiResponses.
- Api.
- ApiOperation may still exist in old dependencies.

The IDE may auto-import the old package when the project has dependencies for both systems.

When encountering compile errors or documentation that does not update after migration:

1. Open the imports at the top of the file.
2. Confirm the package is io.swagger.v3.oas.annotations.
3. Inspect the dependency tree.
4. Remove unused legacy imports.
5. Clean and rebuild the project.
6. Reload /v3/api-docs and inspect the output.

Do not resolve import conflicts by keeping both annotations on the same method. springdoc reads OpenAPI 3 annotations; old annotations may be ignored.

## 30. Update tests and documentation endpoints

Springfox typically exposes Swagger 2 documents at /v2/api-docs. springdoc exposes OpenAPI documents at /v3/api-docs by default.

After migration, update:

- Integration tests fetching the spec.
- API gateways or API portals reading the spec.
- OpenAPI Generator input URLs.
- JSON/YAML export scripts.
- Internal documentation links.
- CI contract validation.
- Swagger UI configuration if using an external spec.

Example:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o target/openapi.json
~~~

If the application configures springdoc.api-docs.path differently from the default, use the configured path instead of hard-coding /v3/api-docs.

Do not keep tests that only check the endpoint returns 200. Verify the openapi field, tags, operation summaries, parameters, requestBody, responses, and schemas.

## 31. Verify migrated annotations via JSON

Useful jq commands:

~~~bash
jq '.tags' target/openapi.json
~~~

~~~bash
jq '.paths["/api/orders/{id}"].get' target/openapi.json
~~~

~~~bash
jq '.components.schemas.OrderResponse' target/openapi.json
~~~

~~~bash
jq '.components.securitySchemes' target/openapi.json
~~~

Cross-check:

- Do tags have the right names and descriptions?
- Do operations have summary, description, and operationId?
- Do path parameters have required=true?
- Do query/header parameters have the right in value and schema?
- Are response codes exact strings like "200" and "404"?
- Do response schemas have the right type or array structure?
- Do security requirements reference existing schemes?
- Are hidden operations/parameters actually hidden?

Inspecting the output document is more important than merely confirming the code compiles.

## 32. Test with WebTestClient

You can test the OpenAPI endpoint in an integration test:

~~~java
@SpringBootTest(
    webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT
)
@AutoConfigureWebTestClient
class OpenApiAnnotationMigrationTest {

    @Autowired
    WebTestClient webTestClient;

    @Test
    void publishesMigratedOperationMetadata() {
        webTestClient.get()
            .uri("/v3/api-docs")
            .exchange()
            .expectStatus().isOk()
            .expectBody()
            .jsonPath("$.openapi").exists()
            .jsonPath("$.paths['/api/orders/{id}'].get.summary")
                .isEqualTo("Find order")
            .jsonPath("$.paths['/api/orders/{id}'].get.operationId")
                .isEqualTo("findOrderById")
            .jsonPath("$.paths['/api/orders/{id}'].get.parameters[0].name")
                .isEqualTo("id");
    }
}
~~~

Parameter ordering can change depending on how the framework collects metadata. If a test only needs to verify a parameter exists, use a JSONPath filter or parse the document and search by name instead of relying on a fixed index.

Also test critical response codes, schemas, and security requirements to catch ignored annotations.

## 33. Cases requiring manual review

A renaming script can handle most simple imports, but the following cases require human review:

- @ApiOperation.responseContainer.
- @ApiOperation.response and generic return types.
- @ApiParam placed on a request body.
- @ApiImplicitParam for authentication headers.
- @Authorization and OAuth scopes.
- @ApiModel.subTypes and discriminator.
- @ApiModelProperty.position.
- allowEmptyValue, nullable, and empty string.
- Response headers and examples.
- Annotations placed on interfaces or base controllers.
- Annotations combined with custom composed annotations.

In particular, responseContainer List/Set must be converted properly to an array schema. If the return type is already List<OrderResponse>, there is no need to retain old annotations just to declare List again.

## 34. Step-by-step migration workflow

A workflow you can follow:

1. Inventory all Swagger 2 annotations and related dependencies.
2. Identify target Spring Boot, Spring MVC/WebFlux, and springdoc versions.
3. Remove Springfox and Swagger 2 dependencies once confirmed unused by any module.
4. Add the appropriate springdoc starter.
5. Switch imports to io.swagger.v3.oas.annotations.
6. Convert @Api to @Tag.
7. Convert @ApiOperation to @Operation.
8. Convert @ApiParam and implicit params to @Parameter/@Parameters.
9. Convert model annotations to @Schema.
10. Convert response code/message/schema to @ApiResponse.
11. Convert authorization to security schemes and requirements.
12. Review attributes without direct mappings.
13. Build and resolve import conflicts.
14. Fetch /v3/api-docs and inspect JSON.
15. Run integration/contract tests.
16. Compare before and after specs to spot unintended changes.

Working controller group by controller group or module by module makes diff reviews easier, especially when the codebase has deeply nested annotations.

## 35. Common pitfalls

| Symptom | Cause to check |
|---|---|
| Old @Api does not create a tag | springdoc reads @Tag in the OpenAPI 3 package |
| Summary missing | Used value instead of summary |
| Description missing | Used notes instead of description |
| operationId changed | Did not migrate nickname to operationId |
| Parameter not shown | Imported wrong @Parameter package or parameter is hidden |
| Auth header shows as regular query/header | Used Parameter instead of SecurityScheme |
| Wrong response schema | Migrated response directly without declaring appropriate content/schema |
| List response becomes an object | Array schema not described or return type unclear |
| 404 missing | Did not convert code/message to responseCode/description |
| Wrong nullability | Confused null with empty string or allowEmptyValue |
| Model property order changed | position has no direct mapping |
| Swagger UI does not show scheme | SecurityRequirement references nonexistent name |
| New annotation compiles but output unchanged | Controller still has old Swagger 2 imports |
| Tests still call /v2/api-docs | Endpoint not updated to /v3/api-docs |
| IDE keeps adding old imports | Swagger 2 dependency still on classpath |

## 36. Migration completion checklist

- [ ] Selected the right springdoc starter for Spring MVC or WebFlux.
- [ ] Removed unused Springfox dependencies.
- [ ] Removed swagger-annotations 1.x from migrated code.
- [ ] New imports use io.swagger.v3.oas.annotations.
- [ ] @Api converted to @Tag.
- [ ] @ApiOperation converted to @Operation.
- [ ] @ApiParam converted to @Parameter.
- [ ] @ApiImplicitParam and @ApiImplicitParams converted properly.
- [ ] @ApiModel and @ApiModelProperty converted to @Schema.
- [ ] @ApiResponse code/message converted to responseCode/description.
- [ ] Response schemas and array schemas match return types.
- [ ] Security schemes and requirements defined separately.
- [ ] Hidden controllers/operations/parameters use the right scope.
- [ ] Required, nullable, and empty string distinguished.
- [ ] Attributes without direct mappings reviewed.
- [ ] /v2/api-docs endpoints updated to /v3/api-docs in tests and CI.
- [ ] Actual OpenAPI JSON verified.
- [ ] Integration tests and contract validation executed.
- [ ] Pre/post-migration diff reviewed.

## 37. References

- [springdoc-openapi – Migrating from SpringFox](https://springdoc.org/migrating-from-springfox.html)
- [springdoc-openapi v2 – Migrating from SpringFox](https://springdoc.org/v2/#migrating-from-springfox)
- [Swagger Core – Swagger 2.X Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)
- [Swagger Core – OpenAPI 3 Annotations](https://github.com/swagger-api/swagger-core/wiki/Annotations)
- [Swagger Core – Operation annotation API](https://docs.swagger.io/swagger-core/v2.2.34/apidocs/io/swagger/v3/oas/annotations/Operation.html)
- [Swagger Core – ApiResponse annotation API](https://github.com/swagger-api/swagger-core/blob/master/modules/swagger-annotations/src/main/java/io/swagger/v3/oas/annotations/responses/ApiResponse.java)
- [OpenAPI Specification](https://spec.openapis.org/oas/latest.html)

Proper migration means transferring the intent of annotations, not merely renaming classes. @Tag organizes controllers, @Operation describes operations, @Parameter describes parameters, and @Schema describes data; responses and security must be declared according to the OpenAPI 3 model. Leverage metadata that Spring MVC can infer automatically, review attributes without direct mappings, and verify the final JSON document before wrapping up the migration.
