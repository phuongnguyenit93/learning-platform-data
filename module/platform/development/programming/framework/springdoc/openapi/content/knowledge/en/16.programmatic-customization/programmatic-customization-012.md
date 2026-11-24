# Registering Components Synchronously with Every Added $ref

When customizing OpenAPI in Java, you may need to add shared schemas, error responses, parameters, request bodies, or security schemes so multiple operations can reference them together. In OpenAPI, reusable definitions reside in **components**; locations that use them point there using **$ref** or the corresponding scheme name.

A reference is meaningful only when its target exists and has the right type. For example, a $ref pointing to `#/components/responses/NotFound` must resolve to a Response Object; you cannot register that name under `components.schemas` and expect operations to understand it. This lesson explains how to register components using OpenAPI models and springdoc customizers, build accurate references, avoid overwriting existing components, and verify the entire document after customization.

## 1. What Problem Do Components and $ref Solve?

If many operations share the same error structure, repeating schemas and descriptions in every operation makes the document verbose and inconsistent. OpenAPI provides the `components` section to define reusable building blocks.

Example:

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
        message:
          type: string

paths:
  /api/orders/{id}:
    get:
      responses:
        '404':
          description: Order not found
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ApiError'
~~~

The ApiError schema is defined once inside components.schemas. Operations reference that schema via a JSON Pointer.

Benefits of this organization:

- Keeps shared descriptions in one place.
- Avoids duplicating schemas across multiple operations.
- Enables client generators to reuse models.
- Makes updating shared structures and assessing impact easier.
- Makes large documents easier to read and maintain.

Components are a definitions section, not HTTP endpoints. Adding a schema to components does not create a new API or alter controller behavior.

## 2. Which Component Groups Can Be Registered?

OpenAPI supports several component categories. Each category has its own location and reference style:

| Group | Location | Used to Reuse |
|---|---|---|
| Schemas | `components.schemas` | Objects, enums, primitive schemas, request/response structures |
| Responses | `components.responses` | Response descriptions, headers, content, and schemas |
| Parameters | `components.parameters` | Path, query, header, or cookie parameters |
| Request Bodies | `components.requestBodies` | Request bodies along with media types and schemas |
| Headers | `components.headers` | Response header definitions |
| Examples | `components.examples` | Request or response examples |
| Links | `components.links` | Links from responses to other operations |
| Callbacks | `components.callbacks` | Callbacks invoked by the API toward clients |
| Security Schemes | `components.securitySchemes` | Authentication mechanisms such as bearer, API key, or OAuth2 |

Not all components are referenced with the same annotation syntax. Schemas, responses, parameters, and request bodies can usually use $ref at their respective locations. Security schemes are usually attached to operations via the scheme name in a security requirement or `@SecurityRequirement` annotation.

## 3. Reading $ref Paths Properly

For internal components within the same document, references typically follow the form:

~~~text
#/components/<group>/<component-name>
~~~

Examples:

~~~yaml
$ref: '#/components/schemas/ApiError'
$ref: '#/components/responses/NotFound'
$ref: '#/components/parameters/TraceId'
$ref: '#/components/requestBodies/CreateOrderBody'
$ref: '#/components/headers/RateLimitRemaining'
$ref: '#/components/securitySchemes/bearerAuth'
~~~

How to read `#/components/schemas/ApiError`:

1. `#` indicates the current OpenAPI document.
2. `components` navigates to the components section.
3. `schemas` selects the schemas group.
4. `ApiError` selects the component with that exact name.

Component names are case-sensitive. `ApiError`, `apiError`, and `APIError` are three distinct keys. Names containing special characters in JSON Pointer must be escaped according to JSON Pointer rules; to avoid confusion, use simple component names consisting of letters, digits, and underscores when needed.

Never construct a $ref by guessing a Java class name. Component names can be altered by `@Schema(name = "...")`, generic types, model converters, or swagger-core configuration. Inspect the actual key in the generated JSON.

## 4. Registering Schemas Using the OpenAPI Model

Components can be built directly with classes from swagger-models. Example registering the ApiError schema:

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.media.ObjectSchema;
import io.swagger.v3.oas.models.media.StringSchema;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI openAPI() {
        Components components = new Components()
            .addSchemas(
                "ApiError",
                new ObjectSchema()
                    .addProperties("code",
                        new StringSchema().example("ORDER_NOT_FOUND"))
                    .addProperties("message",
                        new StringSchema().example("Order not found"))
            );

        return new OpenAPI()
            .components(components);
    }
}
~~~

In the example, `addSchemas("ApiError", ...)` registers a schema under the key ApiError. Operations can then reference it:

~~~yaml
schema:
  $ref: '#/components/schemas/ApiError'
~~~

The OpenAPI model is the specification's object model, not a runtime controller DTO. When creating schemas manually, declare all types, properties, required fields, formats, enums, and constraints that clients need to know. Creating a schema in Java does not generate a DTO class or runtime validation in the application.

If the application already uses an ApiError DTO and springdoc generates its schema automatically, consider letting the library analyze the DTO instead of creating a duplicate manual schema with the same name. Choose one clear source of truth for each component.

## 5. Adding Components with OpenApiCustomizer

When you want to add components to a document generated by springdoc from controllers, you can use `OpenApiCustomizer`. The customizer receives the generated OpenAPI model to add or adjust metadata.

~~~java
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.media.ObjectSchema;
import io.swagger.v3.oas.models.media.Schema;
import io.swagger.v3.oas.models.media.StringSchema;
import io.swagger.v3.oas.models.responses.ApiResponse;
import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
class SharedOpenApiComponentsConfiguration {

    @Bean
    OpenApiCustomizer sharedComponentsCustomizer() {
        return openApi -> {
            Components components = openApi.getComponents();

            if (components == null) {
                components = new Components();
                openApi.setComponents(components);
            }

            components.addSchemas("ApiError", apiErrorSchema());
            components.addResponses("BadRequest", badRequestResponse());
        };
    }

    private Schema<?> apiErrorSchema() {
        return new ObjectSchema()
            .addProperties("code", new StringSchema()
                .example("VALIDATION_FAILED"))
            .addProperties("message", new StringSchema()
                .example("Invalid request data"));
    }

    private ApiResponse badRequestResponse() {
        return new ApiResponse()
            .description("Invalid request")
            .content(new Content().addMediaType(
                "application/json",
                new MediaType().schema(
                    new Schema<>().$ref("#/components/schemas/ApiError")
                )
            ));
    }
}
~~~

The customizer above adds two components:

- `components.schemas.ApiError`: schema of the error body.
- `components.responses.BadRequest`: response using the ApiError schema.

Inside the Response Object, the schema is referenced via `#/components/schemas/ApiError`. Registering the response and registering the schema are two separate steps; ensure both exist.

The example uses swagger-core model APIs. Imports and extension points must match the springdoc/swagger-models version your project uses. If upgrading major versions, verify the corresponding packages and API signatures.

## 6. Do Not Replace All Components When Only Appending

A common mistake is creating a new Components object and reassigning it on OpenAPI after springdoc has already generated other schemas:

~~~java
// Avoid this if the goal is only to add a single component.
openApi.setComponents(
    new Components().addSchemas("ApiError", apiErrorSchema())
);
~~~

This can wipe out schemas, responses, or security schemes already generated from controllers and annotations. Retrieve the existing Components; instantiate a new one only if null; then add the specific elements needed.

Safer pattern:

~~~java
Components components = openApi.getComponents();

if (components == null) {
    components = new Components();
    openApi.setComponents(components);
}

components.addSchemas("ApiError", apiErrorSchema());
~~~

If you need to modify an existing component, establish clearly who owns that component and why it needs to change. Never replace the entire map just to update one key.

## 7. Controlling Name Collisions and Overwrite Policies

Components are stored by key. When registering a component with the same name as an existing key, the add call may overwrite the prior definition depending on how the model API manages its map. Accidental overwrites can alter schemas currently referenced by many operations.

You can check for collisions before adding:

~~~java
Map<String, Schema> schemas = components.getSchemas();

if (schemas != null && schemas.containsKey("ApiError")) {
    throw new IllegalStateException(
        "Component ApiError already exists; identify the authoritative source before replacing"
    );
}

components.addSchemas("ApiError", apiErrorSchema());
~~~

This illustrates a fail-fast policy. Depending on the project, you can choose one of these approaches:

- Use the existing component if it already matches the contract.
- Rename the new component if its semantics differ.
- Perform an intentional merge and verify compatibility.
- Replace the old component only after assessing impact on all `$ref`s.

Never overwrite silently. If an existing component is used by many operations, changing a required field, type, or enum can affect every client.

## 8. Registering Shared Responses and Referencing Them from Operations

After registering `components.responses.BadRequest`, operations can reference this response:

~~~java
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@PostMapping("/api/orders")
@ApiResponses({
    @ApiResponse(
        responseCode = "201",
        description = "Order created"
    ),
    @ApiResponse(
        responseCode = "400",
        ref = "#/components/responses/BadRequest"
    )
})
public OrderResponse createOrder(
    @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

In the generated OpenAPI output, the 400 response references the BadRequest response component. That response component in turn contains a content schema pointing to ApiError.

The reference chain must remain consistent:

~~~text
operation.responses["400"]
    -> #/components/responses/BadRequest
        -> content.application/json.schema
            -> #/components/schemas/ApiError
~~~

Every link must exist and have the right type. If the response component exists yet the ApiError schema is absent, the document still has a broken reference.

Note: @ApiResponse only describes documentation. The controller or exception handler must still return status 400 and a body matching the ApiError structure if that is the published contract.

## 9. Registering Shared Parameters

A header such as X-Request-Id may be used across many operations. You can register a Parameter Object:

~~~java
import io.swagger.v3.oas.models.parameters.Parameter;
import io.swagger.v3.oas.models.media.StringSchema;

components.addParameters(
    "TraceId",
    new Parameter()
        .name("X-Request-Id")
        .in("header")
        .required(false)
        .description("Correlation ID sent by the client if provided")
        .schema(new StringSchema())
);
~~~

Referencing from annotations:

~~~java
@GetMapping("/api/orders")
public List<OrderResponse> listOrders(
    @io.swagger.v3.oas.annotations.Parameter(
        ref = "#/components/parameters/TraceId"
    )
    @RequestHeader(name = "X-Request-Id", required = false)
    String traceId
) {
    return orderService.findAll();
}
~~~

In the example, the OpenAPI `@Parameter` annotation is fully qualified to distinguish it from the `io.swagger.v3.oas.models.parameters.Parameter` model class. Spring's `@RequestHeader` annotation still governs header binding at runtime.

The header name in the component must match the header used by the controller and clients. If the component describes X-Request-Id while the controller reads X-Correlation-Id, documentation and runtime are out of sync.

## 10. Registering Shared Request Bodies

When multiple operations accept the same request body structure, you can register a Request Body Object in components.requestBodies:

~~~yaml
components:
  requestBodies:
    CreateOrderBody:
      required: true
      description: Order creation payload
      content:
        application/json:
          schema:
            $ref: '#/components/schemas/CreateOrderRequest'
~~~

Referencing on an operation:

~~~yaml
paths:
  /api/orders:
    post:
      requestBody:
        $ref: '#/components/requestBodies/CreateOrderBody'
      responses:
        '201':
          description: Order created
~~~

In a controller, the OpenAPI request body annotation can reference the component while the Spring annotation still performs binding:

~~~java
public OrderResponse createOrder(
    @org.springframework.web.bind.annotation.RequestBody
    @io.swagger.v3.oas.annotations.parameters.RequestBody(
        ref = "#/components/requestBodies/CreateOrderBody"
    )
    CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

Use a shared request body only when operations truly share the same structure, media type, required flag, and data semantics. If two requests are only partially similar with different required rules, create separate schemas or request bodies to avoid misleading descriptions.

## 11. Registering Security Schemes and Synchronizing Requirement Names

Security schemes are declared in `components.securitySchemes`. Example for bearer JWT:

~~~java
import io.swagger.v3.oas.models.security.SecurityScheme;

components.addSecuritySchemes(
    "bearerAuth",
    new SecurityScheme()
        .type(SecurityScheme.Type.HTTP)
        .scheme("bearer")
        .bearerFormat("JWT")
);
~~~

An operation can require the scheme by name:

~~~java
@Operation(
    summary = "Get current profile",
    security = @SecurityRequirement(name = "bearerAuth")
)
@GetMapping("/api/me")
public ProfileResponse getProfile() {
    return profileService.current();
}
~~~

The name `bearerAuth` in @SecurityRequirement must match the exact key registered in components.securitySchemes. This is a link by scheme name, not a regular $ref.

If the scheme is declared under `jwtAuth` yet the operation requires `bearerAuth`, documentation may fail to attach the right authentication mechanism. Inspect both the component and the security requirement in JSON.

Declaring a security scheme only describes how clients send credentials. It does not configure Spring Security, issue tokens, or protect endpoints. Runtime configuration must be implemented separately.

## 12. Organizing Components with a Clear Source of Truth

In large projects, components may come from several sources:

- Automatic inference by springdoc from DTOs and return types.
- Swagger annotations such as @Schema, @ApiResponse, and @SecurityScheme.
- An OpenAPI bean.
- OpenApiCustomizer or group customizers.
- External OpenAPI files loaded or merged.

If multiple sources create components, establish ownership conventions. Example:

| Component | Recommended Source of Definition |
|---|---|
| Request/response DTOs | Java DTOs and @Schema |
| Shared error responses | Error DTO or shared customizer |
| Shared header parameters | Customizer or OpenAPI bean |
| Security schemes | OpenAPI bean or @SecurityScheme |
| Group-specific components | Customizer attached to that group |

There is no need to manually define a schema when springdoc already generates it accurately from DTOs and annotations. Duplicate definitions increase the risk of divergence in required flags, nullability, formats, and properties.

If using an OpenAPI bean and customizers together, define which creates baseline metadata and which supplements it. Avoid multiple customizers writing to the same component key with differing contents.

## 13. Distinguishing Global and Group Customizers

An application can publish multiple documents through GroupedOpenApi. Each group can have its own set of paths, operations, and components.

When adding components via customizers, determine the scope:

- Components needed across every document should be configured at a globally applied extension point suitable for your springdoc version.
- Components serving only one API group should be added via a customizer attached to that group.
- Components referenced inside a group must exist in that group's document, not solely in the default document.

Extension points like OpenApiCustomizer and GlobalOpenApiCustomizer differ in scope between default configuration and grouped APIs. Check the documentation for your springdoc version and inspect each documentation endpoint, such as `/v3/api-docs` along with `/v3/api-docs/{group}`.

An internal $ref always resolves within the document containing it. Never assume a component in the default document is automatically present in group documents.

## 14. Avoiding Orphan Components and Missing References

Two common situations:

- **Orphan component:** a component is registered yet referenced by no operations. This does not necessarily make the document invalid, though it can create clutter and cause client generators to emit unnecessary models depending on the tool.
- **Missing reference:** an operation has a $ref whose target component does not exist. This is a structural error that must be fixed before release.

Incorrect example:

~~~yaml
responses:
  '404':
    $ref: '#/components/responses/NotFound'

components:
  responses:
    NotFoundOrder:
      description: Order not found
~~~

The operation points to NotFound, yet the registered component is NotFoundOrder. The mismatched keys leave the reference unresolved.

Fix:

~~~yaml
responses:
  '404':
    $ref: '#/components/responses/NotFoundOrder'
~~~

Check the component category as well. If a response mistakenly points to `#/components/schemas/NotFoundOrder`, having the same trailing name does not make the reference type valid.

## 15. Inspecting $refs in OpenAPI JSON

After the application runs, download the document:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

List all references in the document:

~~~bash
jq -r '
  .. | objects
  | .["$ref"]? // empty
' openapi.json
~~~

Inspect registered schema components:

~~~bash
jq '.components.schemas | keys' openapi.json
~~~

Inspect a shared response:

~~~bash
jq '.components.responses.BadRequest' openapi.json
~~~

Inspect an operation's response:

~~~bash
jq '.paths["/api/orders"].post.responses["400"]' openapi.json
~~~

Inspect security schemes and requirements:

~~~bash
jq '.components.securitySchemes, .paths["/api/me"].get.security' openapi.json
~~~

Cross-check each reference:

- Is it in the right component group?
- Does the key name match exactly?
- Does the component actually exist in the same document?
- Does the component type fit the usage site?
- Does the component have all necessary schemas, descriptions, media types, or headers?
- Do grouped APIs register their required group-specific components?

You can use an OpenAPI validator to automatically catch invalid references:

~~~bash
openapi-generator-cli validate -i openapi.json
~~~

Validators do not replace semantic review. A $ref can be structurally valid yet point to a schema that misrepresents the runtime payload.

## 16. Verifying with Tests

You can write tests calling the OpenAPI endpoint and verifying components along with references:

~~~java
@Test
void documentsSharedBadRequestResponse() throws Exception {
    mockMvc.perform(get("/v3/api-docs"))
        .andExpect(status().isOk())
        .andExpect(jsonPath(
            "$.components.schemas.ApiError"
        ).exists())
        .andExpect(jsonPath(
            "$.components.responses.BadRequest"
        ).exists())
        .andExpect(jsonPath(
            "$.paths['/api/orders'].post.responses['400'].$ref"
        ).value("#/components/responses/BadRequest"));
}
~~~

The test above verifies key published components. You can add an assertion confirming the response component references the ApiError schema:

~~~java
.andExpect(jsonPath(
    "$.components.responses.BadRequest.content['application/json'].schema.$ref"
).value("#/components/schemas/ApiError"));
~~~

If using grouped APIs, call each group's endpoint and verify required components exist in every document. Testing only the default document does not guarantee groups are accurate.

Alongside JSON tests, run a validator in CI and test runtime requests/responses. A properly referenced response component can still misdescribe the body returned by an exception handler.

## 17. Common Pitfalls

| Symptom | Cause to Check |
|---|---|
| $ref points to nonexistent component | Wrong key name, unregistered component, or customizer did not run on that document |
| Registered ApiError yet operations still inline schemas | Operations do not reference the component or annotation uses implementation instead of ref |
| Auto-generated components vanish after customizer | Customizer replaces entire Components instead of adding to existing object |
| Schema changes unexpectedly | Two sources write to the same component key |
| Response $ref points to schemas by mistake | Used wrong component group in JSON Pointer |
| Security requirement does not recognize scheme | Name in @SecurityRequirement differs from securitySchemes key |
| Default document works yet group fails | Customizer does not apply to grouped OpenAPI or group lacks needed component |
| Validator reports error after adding response ref | Response component lacks description or inner schema reference is invalid |
| Many orphan components appear | Unnecessary manual registrations or lack of cleanup conventions |
| External ref unreachable | Wrong external document URL or consumers lack resource access |

When troubleshooting, trace the chain from usage site to component and any nested references inside. Never just check for a component name and assume all links are valid.

## 18. Safe Component Registration Workflow

When adding a new component, follow this sequence:

1. Determine the component category: schema, response, parameter, request body, header, or security scheme.
2. Choose a stable component name that does not collide with existing keys.
3. Register the component in the right Components group.
4. Add the $ref or security requirement at usage sites.
5. Check nested references inside the component.
6. Verify the customizer applies to the default document and required groups.
7. Download the OpenAPI JSON and check components along with every $ref.
8. Run validators and automated tests.
9. Compare schemas against runtime requests/responses.
10. Review the impact of shared component changes on existing operations and clients.

Keep registration and references close in code organization, or centralized in shared configuration. This helps maintainers see where components are defined and where they are used.

## 19. Checklist for Registering Components and $refs

- [ ] Identified the exact reusable component category.
- [ ] Component name is meaningful, stable, and unique.
- [ ] Component is added to the right group inside Components.
- [ ] Customizer preserves components already generated by springdoc.
- [ ] Every $ref points to the right group and exact component name.
- [ ] Nested $refs inside components are also valid.
- [ ] Security requirements use exact security scheme names.
- [ ] No unintended component overwrites occur.
- [ ] Components are registered only in documents/groups where needed.
- [ ] No unnecessary orphan components exist.
- [ ] OpenAPI validator succeeds.
- [ ] Tests verify components and references in JSON.
- [ ] Schemas and response components match runtime data.

## 20. References

- [OpenAPI Specification – Components Object](https://spec.openapis.org/oas/latest.html#components-object)
- [OpenAPI Specification – Reference Object](https://spec.openapis.org/oas/latest.html#reference-object)
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [Swagger – Using $ref](https://swagger.io/docs/specification/v3_0/using-ref/)
- [springdoc-openapi – official documentation](https://springdoc.org/)
- [Swagger Core – Models and annotations](https://github.com/swagger-api/swagger-core)

Components store shared definitions; $refs and security requirements connect operations to those definitions. When customizing with springdoc, add to existing Components, avoid key collisions, and verify every reference in every published OpenAPI document. A specification should only feed client generators once its components, references, and runtime behavior have been verified.
