# Replacing Inferred Schemas with implementation or Reusable Components

springdoc-openapi typically infers schemas from the Java types of controller parameters, DTOs, and return values. This is convenient when Java signatures accurately reflect the JSON data an API publishes. However, in some cases, Java types do not express the full contract: a controller returns `ResponseEntity<?>`, returns a generic wrapper, an internal type serializes to a different structure, or the same Java class needs two different descriptions depending on where it is used.

In these situations, you can use `@Schema(implementation = ...)` to specify a representative class for the schema, or use a named component and reference it via `$ref`. For more complex cases, springdoc allows adding or modifying `components.schemas` via an `OpenAPI` bean or `OpenApiCustomizer`. These techniques help documentation describe the contract clients actually see while avoiding duplicating a schema across multiple endpoints.

## 1. When Do You Need to Replace an Inferred Schema?

Suppose a controller returns `ResponseEntity<OrderResponse>`. springdoc can infer `OrderResponse` from the generic argument and generate the right schema. Yet if the return signature is `ResponseEntity<?>`, `Object`, a generic wrapper, or an internal Java type, type information may be insufficient to produce the desired contract.

Common situations include:

| Situation | Potential issue with inferred schema | Resolution |
| --- | --- | --- |
| Controller returns `ResponseEntity<?>` | Concrete JSON type cannot be determined | Specify `implementation` on the response content |
| Endpoint returns a wrapper or generic type | Type parameter may be lost or not represented as intended | Use a concrete DTO or a specialized `implementation` class |
| Internal Java type differs from public JSON structure | Schema reflects internal class rather than external contract | Use an API DTO or override the schema |
| Same class used in multiple contexts | Each place needs a different description, e.g., home vs. work address | Create separate component schemas and reference by context |
| Endpoint not declared in a controller | No Java signature for springdoc to infer automatically | Use `OpenApiCustomizer` and register schemas into `components` |

Before overriding, determine the actual JSON the application sends or receives. `implementation` and `$ref` only change OpenAPI documentation; they do not change Java return types, Jackson serialization, or request-handling logic.

## 2. Using @Schema(implementation = ...) to Specify a Representative Type

`implementation` tells swagger-core which Java class to use to build the schema for the documented element. It can replace the type inferred from that element. Other descriptive attributes of `@Schema`, such as `description`, `example`, or `requiredMode`, can still supplement the generated schema.

For example, a controller returns `ResponseEntity<?>` while the API actually always returns an `OrderResponse`:

~~~java
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RestController;

import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;

@RestController
public class OrderController {

    @GetMapping("/api/orders/{id}")
    @Operation(summary = "Get order by ID")
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
            description = "Order not found",
            content = @Content
        )
    })
    public ResponseEntity<?> getById(@PathVariable long id) {
        Object body = orderService.findResponse(id);
        return ResponseEntity.ok(body);
    }
}
~~~

In the example, `ResponseEntity<?>` is a detail of the Java signature, whereas the response content is documented using `OrderResponse`. The OpenAPI spec will use `OrderResponse`'s schema for the 200 response. This is only accurate if `orderService.findResponse(id)` genuinely returns JSON matching that class's structure.

You can use `implementation` for request bodies when a handler parameter's type does not directly express the public payload. For example, if a controller accepts a generic or intermediate type, use `io.swagger.v3.oas.annotations.parameters.RequestBody` with `@Content(schema = @Schema(implementation = CreateOrderRequest.class))` to clarify the request schema. When an explicit DTO is already in the Spring signature, prefer letting springdoc infer from the DTO.

## 3. Overriding Collection Schemas with @ArraySchema

When data is an array or list, use `@ArraySchema` to describe the element schema. The `@ArraySchema` annotation is specifically for arrays; do not place both `@ArraySchema` and `@Schema` on the same element simultaneously.

Example where the response is a list of orders while the return type is declared generically:

~~~java
@GetMapping("/api/orders")
@Operation(summary = "List orders")
@ApiResponse(
    responseCode = "200",
    description = "List of orders",
    content = @Content(
        mediaType = "application/json",
        array = @ArraySchema(
            schema = @Schema(implementation = OrderResponse.class)
        )
    )
)
public ResponseEntity<?> listOrders() {
    return ResponseEntity.ok(orderService.findAll());
}
~~~

The published schema is an array whose elements have the `OrderResponse` structure. Ensure the actual response is a JSON array. If the application returns a pagination object with fields such as `content`, `totalElements`, and `page`, do not describe it as a plain array; use the page type's schema or a concrete pagination DTO.

## 4. Creating Stable Component Names for DTOs

OpenAPI places reusable schemas in `components.schemas`. For complex objects, springdoc usually creates a component and references it from operations or other properties via `$ref`. You can set the component name using `@Schema(name = "...")` on the DTO class:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(
    name = "OrderSummary",
    description = "Summary information of an order"
)
public class OrderSummary {

    private Long id;
    private String orderNumber;
    private String status;

    // Getters and setters omitted.
}
~~~

When the DTO is used in requests or responses, springdoc can place the schema into `components.schemas` named `OrderSummary` and reference it wherever used. Stable component names make documentation easier to read, easier to diff across versions, and convenient when multiple endpoints share one structure.

Choose names reflecting the public contract, such as `CreateOrderRequest`, `OrderResponse`, or `OrderSummary`. Avoid internal class names if they carry no meaning for clients. When renaming a component already referenced by clients or used by code generators, treat it as a change that impacts documentation consumers.

## 5. Referencing Components with $ref

A schema already in `components.schemas` can be reused in multiple places. In OpenAPI, `$ref` points to a schema defined once:

~~~yaml
components:
  schemas:
    Address:
      type: object
      properties:
        street:
          type: string
        city:
          type: string
        postalCode:
          type: string

    CustomerResponse:
      type: object
      properties:
        id:
          type: string
        address:
          $ref: '#/components/schemas/Address'

    SupplierResponse:
      type: object
      properties:
        id:
          type: string
        address:
          $ref: '#/components/schemas/Address'
~~~

Both responses reference the single `Address` definition. If the address structure changes per contract, update the component once and check all references. This is the main benefit of reusable schemas: reducing duplication and keeping structures consistent.

In annotations, you can specify a schema reference for a property via `@Schema(ref = "...")`. The springdoc FAQ illustrates referencing registered components by names such as `WorkAddressSchema` or `HomeAddressSchema`. Inspect the generated OpenAPI JSON to ensure the final value is a valid `$ref`, typically formatted as `#/components/schemas/WorkAddressSchema`.

Do not create references to nonexistent components. A misspelled name or wrong `$ref` path can prevent validators, Swagger UI, or client generators from resolving the schema.

## 6. Using Two Different Schemas for the Same Java Class

Sometimes one Java class is used in multiple positions with different descriptive meanings. For example, `Address` has the same Java fields, yet as a work address it needs one description while as a home address it needs another. You can register two separate component schemas and reference them from each property:

~~~java
public class PersonResponse {

    private String fullName;

    @Schema(ref = "WorkAddressSchema")
    private Address workAddress;

    @Schema(ref = "HomeAddressSchema")
    private Address homeAddress;

    // Getters and setters omitted.
}
~~~

A straightforward way is declaring both components in an `OpenAPI` bean:

~~~java
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

import io.swagger.v3.oas.models.OpenAPI;
import io.swagger.v3.oas.models.Components;
import io.swagger.v3.oas.models.media.ObjectSchema;
import io.swagger.v3.oas.models.media.StringSchema;

@Configuration
public class OpenApiConfiguration {

    @Bean
    public OpenAPI customOpenAPI() {
        return new OpenAPI().components(new Components()
            .addSchemas(
                "WorkAddressSchema",
                addressSchema("Work address")
            )
            .addSchemas(
                "HomeAddressSchema",
                addressSchema("Home address")
            )
        );
    }

    private ObjectSchema addressSchema(String description) {
        return new ObjectSchema()
            .description(description)
            .addProperties(
                "addressName",
                new StringSchema().description("Address name or description")
            );
    }
}
~~~

In the example, the two components share the same property structure while having different descriptions. If two schemas must differ in fields, data types, bounds, or `required`, declare the corresponding properties inside each component. There is no need to create two Java classes just to produce two different OpenAPI descriptions.

This is documentation metadata. Two components do not change the `Address` object at runtime, nor do they cause Jackson to distinguish home addresses from work addresses automatically. If two contexts require genuinely different business data, consider creating separate DTOs rather than merely changing descriptions.

## 7. Registering Schemas via OpenAPI Beans and Customizers

An `OpenAPI` bean fits when declaring shared components or metadata for the generated document. Definitions added to the bean can appear in the default specification and in groups depending on springdoc configuration.

To modify documentation per group, attach an `OpenApiCustomizer` to `GroupedOpenApi`. If a customizer needs to apply to both the default document and groups, springdoc provides `GlobalOpenApiCustomizer`. Choose an explicit scope so required components are not missing in one of the groups.

For example, registering a reusable schema in the document:

~~~java
@Bean
public OpenAPI customOpenAPI() {
    return new OpenAPI()
        .components(new Components()
            .addSchemas(
                "ApiError",
                new ObjectSchema()
                    .description("Standard API error information")
                    .addProperties("code", new StringSchema())
                    .addProperties("message", new StringSchema())
            )
        );
}
~~~

Error responses can then reference this component:

~~~java
@ApiResponse(
    responseCode = "400",
    description = "Invalid request",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(ref = "#/components/schemas/ApiError")
    )
)
~~~

When using an `OpenAPI` bean, ensure other application `components` configurations are preserved. If the project already has a bean declaring API info or security schemes, extend the existing bean or merge components instead of creating competing configuration sources.

## 8. Generating Schemas from Java Classes in Custom Endpoints

Sometimes an endpoint is exposed by a filter, gateway, or mechanism without a controller method for springdoc to infer from. In that case, you can use `OpenApiCustomizer` to add the operation and generate schemas from Java classes.

For current springdoc versions, the FAQ recommends `SpringDocAnnotationsUtils.extractSchema`. This method takes `Components`, a Java type, and the OpenAPI spec version; it registers referenced schemas, including nested types, and returns the schema or `$ref` to attach to the operation.

Example illustrating a login endpoint added to the document:

~~~java
import static org.springframework.http.MediaType.APPLICATION_JSON_VALUE;

import org.springdoc.core.customizers.OpenApiCustomizer;
import org.springdoc.core.utils.SpringDocAnnotationsUtils;
import org.springframework.context.annotation.Bean;

import io.swagger.v3.oas.models.Operation;
import io.swagger.v3.oas.models.PathItem;
import io.swagger.v3.oas.models.media.Content;
import io.swagger.v3.oas.models.media.MediaType;
import io.swagger.v3.oas.models.parameters.RequestBody;
import io.swagger.v3.oas.models.responses.ApiResponse;
import io.swagger.v3.oas.models.responses.ApiResponses;
import io.swagger.v3.oas.models.media.Schema;

@Bean
public OpenApiCustomizer loginEndpointCustomizer() {
    return openApi -> {
        Schema<?> requestSchema = SpringDocAnnotationsUtils.extractSchema(
            openApi.getComponents(),
            LoginRequest.class,
            null,
            null,
            openApi.getSpecVersion()
        );

        Operation operation = new Operation()
            .operationId("login")
            .requestBody(new RequestBody()
                .required(true)
                .content(new Content().addMediaType(
                    APPLICATION_JSON_VALUE,
                    new MediaType().schema(requestSchema)
                ))
            )
            .responses(new ApiResponses().addApiResponse(
                "200",
                new ApiResponse().description("Login successful")
            ));

        openApi.path("/login", new PathItem().post(operation));
    };
}
~~~

If `LoginRequest` contains a nested type such as `Address`, `extractSchema` registers both the root schema and child schemas in `components.schemas`, then returns the appropriate `$ref`. Converters registered with springdoc are also applied during this process. This is cleaner than calling `ModelConverters` manually and copying referenced schemas into `Components` yourself.

The example above adds an operation that does not originate from a controller. If an endpoint is already scanned by springdoc from a controller, do not add it again via a customizer as that can create duplicate paths or operations.

## 9. Reusable Enums and Composed Schemas

Enums used across multiple DTOs can be extracted into a separate component using `@Schema(enumAsRef = true)`:

~~~java
@Schema(enumAsRef = true, description = "Order status")
public enum OrderStatus {
    NEW,
    CONFIRMED,
    SHIPPED,
    CANCELLED
}
~~~

When an enum is reused, extracting a component avoids repeating value lists across multiple schemas. The springdoc FAQ also describes the global option `ModelResolver.enumsAsRef = true`, though a global setting affects every enum. Enable it only when your project's documentation convention wants all enums as reusable components.

When you need to represent multiple valid data shapes, consider composition keywords such as `oneOf`, `anyOf`, or `allOf`. They serve different purposes:

- `oneOf`: the value must match exactly one schema in the list.
- `anyOf`: the value can match one or more schemas in the list.
- `allOf`: the schema combines constraints from all component schemas.

You can use `@Schema(oneOf = {...})`, `@Schema(anyOf = {...})`, or `@Schema(allOf = {...})` when annotations and Java types match. If the schema is an array, use `@ArraySchema` for elements and place composition on the element schema. Do not use `implementation` to pretend a data type has multiple shapes if the actual contract is a union; describe it accurately with composition or discriminating DTOs.

## 10. Inspecting Schemas and References After Generation

After the application starts, open `/v3/api-docs` or the corresponding group documentation endpoint. Check the following items:

1. Operations have response or request content with the right media type and expected schema.
2. `implementation` generated a schema from the representative class rather than leaving an unexpected `Object` or `string`.
3. Complex schemas are placed in `components.schemas` with stable names.
4. `$ref` entries point to existing components with valid paths.
5. Nested components, enums, and reused schemas are all registered completely.
6. Two schemas for the same class in different contexts have their own descriptions and properties.
7. No duplicate component names or broken references exist.
8. Actual endpoint JSON matches the published schema.

You can download the document for quick inspection:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Then run an OpenAPI validator matching the spec version your project emits. Open Swagger UI to inspect how components render and test sample requests/responses. If a component does not appear, check whether it is referenced and whether configuration strips unreferenced definitions.

## 11. Common Pitfalls and How to Fix Them

| Symptom | Possible cause | Resolution |
| --- | --- | --- |
| Response still shows `Object` or `string` | Override placed in the wrong spot or missing `@Content(schema = ...)` | Place `implementation` on the response content's schema and inspect generated JSON |
| Array schema has wrong element type | Used `@Schema` for array instead of `@ArraySchema` | Use `@ArraySchema(schema = @Schema(implementation = ...))` |
| `$ref` fails to resolve | Component not registered or wrong name | Compare component names in `components.schemas` with `$ref` paths |
| Two contexts sharing one schema cannot have separate descriptions | Both properties reference the same component | Create separate components per context and point `ref` accordingly |
| Duplicate component names | Multiple DTOs or configs register the same name | Pick meaningful component names and centralize management |
| Generic wrapper generates schema missing concrete `data` fields | Generic info lost during inference | Create a concrete DTO or use an `implementation` representing the actual payload |
| Custom endpoint has `$ref` but lacks nested schemas | Added only `$ref` without adding child schemas to `components` | Use `SpringDocAnnotationsUtils.extractSchema` for recursive registration |
| Documentation is right but actual response structure differs | Annotations only change OpenAPI, not Jackson or runtime code | Align DTOs/serializers with the contract or update schema to match actual JSON |
| Component appears in default doc but missing in a group | Customizer only applied to default OpenAPI | Register customizer on the group or use `GlobalOpenApiCustomizer` for the desired scope |

## 12. Selection Principles

Prefer letting springdoc infer schemas when Java types already reflect the contract accurately. Use `@Schema(implementation = ...)` when you need to specify the representative type for part of a request or response. Use `@Schema(name = ...)` to stabilize component names; use `$ref` when multiple locations need to reference one definition. If a class has context-dependent representations, create separate components for each representation and clearly specify where each is used.

For endpoints not originating from controllers or requiring programmatic schema construction, use `OpenApiCustomizer` and springdoc utilities to register all referenced schemas completely. Finally, verify both the generated spec and runtime JSON. A schema override is only helpful when it accurately describes the data clients actually send and receive.

## 13. Official References

- [springdoc-openapi FAQ](https://springdoc.org/faq.html) — overriding response schemas, generating components from Java classes, creating multiple schemas for the same class, `OpenApiCustomizer`, and reusable enums.
- [springdoc-openapi v2 FAQ](https://springdoc.org/v2/faq.html) — `OpenAPI` bean configuration, per-group customizers, and `SpringDocAnnotationsUtils.extractSchema`.
- [Swagger Core — Schema Annotation](https://docs.swagger.io/swagger-core/v2.2.41/apidocs/io/swagger/v3/oas/annotations/media/Schema.html) — `implementation`, `ref`, schema composition, and how annotations override inferred types.
- [OpenAPI Specification 3.1.2 — Components Object](https://spec.openapis.org/oas/v3.1.2.html#components-object) — location and role of reusable schemas.
- [OpenAPI Specification 3.1.2 — Reference Object](https://spec.openapis.org/oas/v3.1.2.html#reference-object) — rules for referencing reusable components.

When replacing inferred schemas or creating reusable components, the goal is keeping a consistent, clearly named OpenAPI contract that accurately reflects data on the wire. springdoc provides annotations and customization APIs to achieve this without forcing teams to write the entire specification by hand.
