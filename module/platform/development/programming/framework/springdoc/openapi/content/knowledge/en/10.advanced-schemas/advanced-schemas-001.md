# Nested DTOs and Shared Schema References

An API request or response often contains multiple layers of data. An order has a shipping address and a list of items; a customer profile has a contact address; each item in turn references product information. Describing all fields in one large object or repeating the same structure across multiple endpoints makes OpenAPI documentation hard to maintain and prone to drift.

With springdoc-openapi, Java DTOs help describe data structures in a way that stays close to application code. The library analyzes property types, collections, and relationships between DTOs to generate Schema Objects in OpenAPI. Reused types can be placed in `components.schemas` and linked via `$ref`. This lesson guides you through designing nested DTOs, reusing schemas, and inspecting the generated documentation.

## 1. From Java DTOs to Schema Objects

A DTO (Data Transfer Object) is a data type used to exchange information over an API. A DTO can appear in a request body or a response body. Each property of a DTO becomes a property in the corresponding schema.

Example of a simple response:

~~~java
public class ProductResponse {
    private String id;
    private String name;
    private BigDecimal price;

    // Constructor, getters, and setters.
}
~~~

With a controller returning `ProductResponse`:

~~~java
@GetMapping("/api/products/{id}")
public ProductResponse getProduct(@PathVariable String id) {
    return productService.findById(id);
}
~~~

springdoc analyzes the return type and can generate a schema in `components.schemas`, then reference that schema from the operation's response content.

Abbreviated OpenAPI model:

~~~yaml
paths:
  /api/products/{id}:
    get:
      responses:
        '200':
          description: Product information
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductResponse'

components:
  schemas:
    ProductResponse:
      type: object
      properties:
        id:
          type: string
        name:
          type: string
        price:
          type: number
~~~

The actual generated schema name depends on the Java type, generic type, and annotation metadata. You can use `@Schema(name = "...")` to give a component a clearer, more stable name when needed.

## 2. Representing Nested Objects

A property whose type is another DTO becomes a nested object in the schema. For example, an order containing a shipping address:

~~~java
public class ShippingAddress {
    private String recipient;
    private String street;
    private String city;
    private String postalCode;

    // Constructor, getters, and setters.
}

public class OrderResponse {
    private String id;
    private String status;
    private ShippingAddress shippingAddress;

    // Constructor, getters, and setters.
}
~~~

The corresponding OpenAPI definition can be represented using a schema reference:

~~~yaml
components:
  schemas:
    OrderResponse:
      type: object
      properties:
        id:
          type: string
        status:
          type: string
        shippingAddress:
          $ref: '#/components/schemas/ShippingAddress'

    ShippingAddress:
      type: object
      properties:
        recipient:
          type: string
        street:
          type: string
        city:
          type: string
        postalCode:
          type: string
~~~

Here, `shippingAddress` remains a property of `OrderResponse`, while its structure definition is placed in the `ShippingAddress` schema. Clients follow `$ref` to retrieve the referenced structure.

Extracting child DTOs helps:

- Easily reuse the same structure across multiple requests or responses.
- Centralize field descriptions and constraints in one place.
- Avoid repeating long schemas across multiple operations.
- Keep documentation readable when objects have multiple levels.
- Support client generation and validators based on a consistent structure.

Extracting a class does not necessarily mean it must become a shared component. For small objects used in only one place, an inline schema can also be clear enough. The goal is to keep the structure easy to understand and maintain.

## 3. Collections Containing DTOs

DTOs often contain lists of child objects. For example, an order with multiple line items:

~~~java
public class OrderItemResponse {
    private String productId;
    private String productName;
    private Integer quantity;
    private BigDecimal unitPrice;

    // Constructor, getters, and setters.
}

public class OrderResponse {
    private String id;
    private List<OrderItemResponse> items;

    // Constructor, getters, and setters.
}
~~~

In OpenAPI, the `items` property is described with `type: array` and an `items` schema:

~~~yaml
OrderResponse:
  type: object
  properties:
    id:
      type: string
    items:
      type: array
      items:
        $ref: '#/components/schemas/OrderItemResponse'
~~~

Each element of the array conforms to the `OrderItemResponse` schema. You can add constraints to collections using Bean Validation and OpenAPI metadata:

~~~java
public class CreateOrderRequest {

    @NotEmpty
    @Size(max = 50)
    @Valid
    private List<OrderItemRequest> items;

    // Getters and setters.
}
~~~

~~~java
@Schema(name = "OrderItemRequest")
public class OrderItemRequest {

    @NotBlank
    @Schema(description = "Product ID", example = "SKU-1001")
    private String productId;

    @Min(1)
    @Schema(description = "Order quantity", example = "2", minimum = "1")
    private Integer quantity;

    // Getters and setters.
}
~~~

In the example, `@NotEmpty` requires the list to have at least one element when validation runs; `@Size(max = 50)` limits the number of elements. `@Valid` requires validating the child objects. The schema may reflect `minItems` and `maxItems` if the integration version maps the corresponding constraints. Inspect the actual JSON rather than assuming all constraints are converted.

## 4. Multiple Levels of Nested DTOs

Multiple levels of nesting can be used if the business structure requires it. For example:

~~~java
public class CreateOrderRequest {
    private CustomerSummary customer;
    private ShippingAddress shippingAddress;
    private List<OrderItemRequest> items;

    // Getters and setters.
}

public class CustomerSummary {
    private String customerId;
    private String displayName;

    // Getters and setters.
}

public class ShippingAddress {
    private String recipient;
    private String street;
    private String city;
    private String postalCode;

    // Getters and setters.
}

public class OrderItemRequest {
    private String productId;
    private Integer quantity;

    // Getters and setters.
}
~~~

Relationship diagram:

~~~mermaid
classDiagram
    class CreateOrderRequest {
      CustomerSummary customer
      ShippingAddress shippingAddress
      List~OrderItemRequest~ items
    }
    class CustomerSummary {
      String customerId
      String displayName
    }
    class ShippingAddress {
      String recipient
      String street
      String city
      String postalCode
    }
    class OrderItemRequest {
      String productId
      Integer quantity
    }
    CreateOrderRequest --> CustomerSummary
    CreateOrderRequest --> ShippingAddress
    CreateOrderRequest --> OrderItemRequest
~~~

In OpenAPI, each type can become a separate schema component and be referenced from `CreateOrderRequest`. When reading the documentation, start from the operation's `requestBody`, follow `$ref` to the root schema, and continue expanding the `$ref` entries of child properties and array items.

Multi-level nesting is valid, but excessive depth should be avoided. An overly deep structure makes it hard for clients to build payloads and understand data relationships. If multiple layers merely forward a single field, consider flattening them when doing so does not lose domain meaning.

## 5. Reusing the Same DTO Across Multiple Operations

One benefit of component schemas is being able to use the same data type across multiple operations. For example, `AddressDto` is used in both customer profiles and orders:

~~~java
@Schema(
    name = "Address",
    description = "Contact or shipping address"
)
public class AddressDto {

    @Schema(example = "12 Nguyen Hue")
    private String street;

    @Schema(example = "Ben Nghe")
    private String ward;

    @Schema(example = "Ho Chi Minh City")
    private String city;

    @Schema(example = "700000")
    private String postalCode;

    // Getters and setters.
}
~~~

Two different DTOs can use `AddressDto`:

~~~java
public class CustomerResponse {
    private String id;
    private String fullName;
    private AddressDto address;

    // Getters and setters.
}

public class DeliveryRequest {
    private String orderId;
    private AddressDto destination;

    // Getters and setters.
}
~~~

OpenAPI can contain a single `Address` component referenced in both places:

~~~yaml
components:
  schemas:
    CustomerResponse:
      type: object
      properties:
        id:
          type: string
        fullName:
          type: string
        address:
          $ref: '#/components/schemas/Address'

    DeliveryRequest:
      type: object
      properties:
        orderId:
          type: string
        destination:
          $ref: '#/components/schemas/Address'

    Address:
      type: object
      properties:
        street:
          type: string
        ward:
          type: string
        city:
          type: string
        postalCode:
          type: string
~~~

The same component is used in multiple locations. When the `Address` structure changes, all references point to the newly generated definition. This reduces duplication, but also means changing a shared DTO can affect multiple endpoints simultaneously.

Only reuse a DTO when the data semantics are the same. Two objects with the same fields but different meanings or privacy rules may require separate DTOs.

## 6. Naming Components with @Schema

Component names generated from class names may not be clear enough, especially when multiple classes share the same name across different packages or when there are multiple DTO versions. You can set the schema name using `@Schema`:

~~~java
@Schema(
    name = "PublicCustomer",
    description = "Customer information permitted for public exposure to clients"
)
public class CustomerPublicResponse {
    private String id;
    private String displayName;

    // Getters and setters.
}
~~~

Another example:

~~~java
@Schema(
    name = "AdminCustomer",
    description = "Customer information for administrative functions"
)
public class CustomerAdminResponse {
    private String id;
    private String displayName;
    private String email;
    private String internalNote;

    // Getters and setters.
}
~~~

Even though the two DTOs share some fields, they have different semantics and exposure scopes. Clear schema names help readers distinguish them and reduce the risk of misunderstanding which data is returned to public clients.

When naming components, you should:

- Use names that describe role and data direction, such as `CreateOrderRequest` or `OrderResponse`.
- Avoid overly generic names like `Data`, `Object`, or `Model`.
- Keep names stable across releases if schemas are referenced by clients.
- Avoid having two unrelated DTOs declare the same schema name.
- Avoid arbitrarily renaming components if the document serves as a contract for code generation or contract testing.

Component names are part of the OpenAPI document. Renaming them can affect generated clients, saved spec files, and tools referencing JSON Pointers.

## 7. Understanding $ref Paths

`$ref` is a Reference Object or schema reference used to point to another definition. For a component schema within the same document, the common form is a JSON Pointer:

~~~yaml
$ref: '#/components/schemas/Address'
~~~

Reading the path:

- `#` indicates the current document.
- `/components` navigates to the `components` object.
- `/schemas` navigates to the schemas collection.
- `/Address` selects the schema named `Address`.

Example:

~~~yaml
components:
  schemas:
    OrderResponse:
      type: object
      properties:
        shippingAddress:
          $ref: '#/components/schemas/Address'
    Address:
      type: object
      properties:
        city:
          type: string
~~~

When a client reads `OrderResponse`, it must follow `$ref` to know what structure `shippingAddress` has.

External references are possible, such as a URL to another OpenAPI file. However, for documents dynamically generated by springdoc from an application, internal references under `components.schemas` are usually easier to deploy and distribute. External references require ensuring the resource is stably hosted and accessible to client tools.

Do not construct `$ref` paths by guessing from class names. Inspect the actual JSON because component names can be adjusted by annotations, generic types, converters, or library configuration.

## 8. Describing Child Fields with @Schema

You can add `description`, `example`, `format`, `allowableValues`, and constraints to each property:

~~~java
public class ShippingAddress {

    @Schema(
        description = "Recipient name",
        example = "Nguyen Van An",
        minLength = 1,
        maxLength = 100
    )
    private String recipient;

    @Schema(
        description = "Street address and house number",
        example = "12 Nguyen Hue",
        maxLength = 255
    )
    private String street;

    @Schema(
        description = "Postal code",
        example = "700000",
        pattern = "^[0-9]{5,10}$"
    )
    private String postalCode;

    // Getters and setters.
}
~~~

Field-level metadata gives a shared schema complete descriptions wherever it is referenced. If a field has runtime validation, you can combine it with Bean Validation:

~~~java
@NotBlank
@Size(max = 100)
@Schema(
    description = "Recipient name",
    example = "Nguyen Van An",
    minLength = 1,
    maxLength = 100
)
private String recipient;
~~~

Keep constraints consistent between `@Schema` and Bean Validation. If the documentation allows strings up to 100 characters but the backend only allows 80, clients may send data they believe is valid only to be rejected. If the backend allows more than the schema, clients generated from the spec may block valid data themselves.

## 9. Reusing Schemas with Generic Wrappers

Many APIs use a common wrapper to package data and pagination metadata:

~~~java
public class ApiResponse<T> {
    private String code;
    private String message;
    private T data;

    // Getters and setters.
}
~~~

A controller can return `ApiResponse<ProductResponse>`:

~~~java
@GetMapping("/api/products/{id}")
public ApiResponse<ProductResponse> getProduct(@PathVariable String id) {
    return productService.getProduct(id);
}
~~~

Or `ApiResponse<OrderResponse>`:

~~~java
@GetMapping("/api/orders/{id}")
public ApiResponse<OrderResponse> getOrder(@PathVariable String id) {
    return orderService.getOrder(id);
}
~~~

Generic types enable wrapper reuse in Java. springdoc/swagger-core can resolve parameterized types to describe the type of `data` in the schema. The specific component name may be generated from the generic signature or library configuration; do not assume there is always a single shared `ApiResponse` component.

If you need to adjust the schema for a generic wrapper, you can use `@Schema(implementation = ...)` on the response or customize the OpenAPI model. However, ensure the final schema still reflects the concrete `data` type of each operation. If every endpoint ends up describing `data` as a generic object, the generic type information has been lost and clients cannot generate accurate code.

For paginated responses, consider using `Page` or a dedicated pagination DTO. When a public contract needs stability, a dedicated DTO usually gives better control over field names, metadata structure, and the format clients see than relying directly on internal framework types.

## 10. Using allOf to Represent Schema Composition

OpenAPI supports composition to combine multiple schemas. `allOf` requires an instance to satisfy all component schemas. This mechanism is commonly used when describing data types with a shared base and extensions.

Example:

~~~yaml
components:
  schemas:
    AuditFields:
      type: object
      properties:
        createdAt:
          type: string
          format: date-time
        updatedAt:
          type: string
          format: date-time

    ProductResponse:
      allOf:
        - $ref: '#/components/schemas/AuditFields'
        - type: object
          properties:
            id:
              type: string
            name:
              type: string
~~~

`ProductResponse` combines audit fields with product-specific fields. `allOf` is an OpenAPI schema composition mechanism; it is not automatic Java inheritance in all cases.

If using Java inheritance, springdoc can describe inheritance relationships based on metadata and how swagger-core processes models. For stable results, inspect the generated JSON and verify that client tools interpret `allOf` properly. Do not use `allOf` just to save a few lines of repetition if the resulting structure makes the client harder to use.

You should also distinguish:

- **`$ref`:** references an already defined schema.
- **`allOf`:** combines multiple schemas; all component conditions must be satisfied.
- **`oneOf`:** the instance must match exactly one of the listed schemas according to `oneOf` semantics.
- **`anyOf`:** the instance matches at least one schema in the list.

These compositions are useful for polymorphic models or multi-form data. Use them only when there is a clear requirement and verify with compatible validators or client generators.

## 11. Separate DTOs for Requests and Responses

Do not use a single DTO for every data direction just because the fields look similar. Requests and responses usually differ:

- Requests may accept passwords, secrets, or write-only data.
- Responses may return `id`, `createdAt`, processing status, or computed fields.
- A field may be read-only, write-only, or hidden based on permissions.
- Required rules on creation may differ from those on update.
- Internal data should not appear in public responses.

Example:

~~~java
public class CreateCustomerRequest {
    @NotBlank
    private String fullName;

    @NotBlank
    @Email
    private String email;

    @NotBlank
    private String password;

    // Getters and setters.
}

@Schema(name = "CustomerResponse")
public class CustomerResponse {
    private String id;
    private String fullName;
    private String email;
    private Instant createdAt;

    // Getters and setters.
}
~~~

`CreateCustomerRequest` and `CustomerResponse` can share child types like `AddressDto` if the semantics and data scope are the same, but `password` should not be placed in the response schema.

Separating DTOs ensures schemas accurately reflect each operation's contract and prevents leaking fields not meant for clients. Do not rely solely on `@Schema(accessMode = READ_ONLY or WRITE_ONLY)` as a substitute for safe DTO design when requests and responses differ significantly.

## 12. Avoiding Circular References in DTOs

Some domain models have bidirectional relationships: `Department` holds a list of `Employee`s, while `Employee` holds a `Department`. Exposing bidirectional entities or DTOs directly in the API can cause documentation to generate recursive schema chains; JSON serializers may also hit infinite loops depending on configuration.

Example of a relationship prone to cycles:

~~~java
public class DepartmentDto {
    private String id;
    private List<EmployeeDto> employees;
}

public class EmployeeDto {
    private String id;
    private DepartmentDto department;
}
~~~

In terms of schema, recursive references can be valid in some models, but you must ensure runtime JSON does not create infinite loops. For list-reading APIs, it is usually better to limit the reference direction:

~~~java
public class DepartmentResponse {
    private String id;
    private List<EmployeeSummaryResponse> employees;
}

public class EmployeeSummaryResponse {
    private String id;
    private String displayName;
}
~~~

If department details are needed from an employee, provide a separate endpoint or DTO for that information. This design helps control response size, avoid duplicate data, and keep schemas readable.

## 13. Customizing Components via OpenAPI Model or Customizers

Annotations suit metadata attached directly to DTOs. When you need to adjust schemas at the document level, you can use an `OpenAPI` bean or customizers provided by springdoc. For example, adding descriptions or modifying metadata of a component after the model is built.

Basic `OpenAPI` bean configuration:

~~~java
@Configuration
class OpenApiConfiguration {

    @Bean
    OpenAPI shopOpenAPI() {
        return new OpenAPI()
            .info(new Info()
                .title("Shop API")
                .version("v1")
                .description("Sales system API"));
    }
}
~~~

For specialized schema changes, springdoc provides extension points such as `OpenApiCustomizer` or `OperationCustomizer` depending on scope. Use a customizer when metadata depends on the whole document, a group, or global rules; use `@Schema` when descriptions belong to a specific DTO.

Avoid customizing the same field via multiple mechanisms without a clear precedence rule. Annotations, model beans, customizers, and global configuration can all affect the document together. After adding a customizer, inspect the JSON output and confirm every required OpenAPI group receives the expected changes.

## 14. Inspecting Components and $ref in OpenAPI JSON

After the application is running, save the document:

~~~bash
curl -fsS http://localhost:8080/v3/api-docs -o openapi.json
~~~

Inspect the root schema of `OrderResponse`:

~~~bash
jq '.components.schemas.OrderResponse' openapi.json
~~~

Inspect an operation's response schema:

~~~bash
jq '.paths["/api/orders/{id}"].get.responses["200"].content["application/json"].schema' openapi.json
~~~

List component schemas:

~~~bash
jq -r '.components.schemas | keys[]' openapi.json
~~~

Find schema references:

~~~bash
jq -r '
  .. | objects
  | select(has("$ref"))
  | ."$ref"
' openapi.json
~~~

Check the following points:

- Do nested DTOs appear properly under `properties`?
- Do collections have `type=array` and `items` with the right schema?
- Does `$ref` point to an existing component?
- Are shared components generated in duplicate copies with colliding names?
- Are schema names meaningful and stable?
- Do generic wrappers preserve the concrete `data` type?
- Do request and response schemas separate fields properly?
- Are there unexpected circular references?

If you have an OpenAPI validator in your pipeline, run it after downloading the spec to detect invalid `$ref` targets or malformed schema compositions. Then try generating a client or opening Swagger UI to verify that documentation consumers can read the components.

## 15. Common Pitfalls

| Symptom | Cause to check |
|---|---|
| Child DTO does not appear in schema | Property type not introspected, missing getter/setter, or hidden field |
| Nested object appears inline instead of `$ref` | How the model resolver handles the type, configuration, or library version; inspect JSON before concluding it is a bug |
| Same DTO produces multiple near-identical components | Schema names differ due to generics, packages, or annotations |
| Two different DTOs have colliding component names | `@Schema(name = ...)` uses the same name; rename according to semantics |
| Collection lacks clear `items` schema | Generic type lost due to raw `List` or overly generic declared type |
| Generic response has `data` as an unspecified object | Parameterized type not preserved in method signature or schema customized too broadly |
| `$ref` points to a nonexistent schema | Component name changed or document edited manually out of sync |
| Client generator mishandles `allOf` | Check the generator's composition support and the OpenAPI structure |
| Document has excessively deep recursive schemas | Bidirectional DTOs or entity graph exposed directly in the API |
| Internal fields appear in response | Shared request/response DTO or missing separate public DTO |

## 16. Conventions for Designing DTOs and Shared Schemas

Several conventions help keep OpenAPI documentation stable:

- Name DTOs by purpose: `CreateRequest`, `UpdateRequest`, `DetailResponse`, and `SummaryResponse`.
- Extract child objects when they have independent business meaning or are reused.
- Use clear component names via `@Schema(name = ...)` when contract stability is needed.
- Use collections with concrete generic types such as `List<OrderItemResponse>`; avoid raw `List`.
- Do not expose persistence entities directly in the API contract.
- Keep descriptions, examples, and constraints on shared schemas consistent.
- Avoid bidirectional circular references if clients do not need that structure.
- Check the impact on every operation using a component before changing a shared DTO.
- Use `allOf`/`oneOf`/`anyOf` when genuine composition is needed, not just to shorten YAML.
- Verify OpenAPI JSON and client generators after structural changes.

## 17. Checklist for Nested DTOs and $ref

- [ ] Root DTO has clear schema and properties.
- [ ] Child objects are represented with the right types.
- [ ] Collections have `items` schemas and concrete generic types.
- [ ] Reused DTOs have appropriate component schemas.
- [ ] All `$ref` entries point to existing schemas.
- [ ] Component names are meaningful and non-colliding.
- [ ] Request DTOs and response DTOs do not accidentally leak fields.
- [ ] Generic wrappers preserve the concrete data type per operation.
- [ ] `allOf`/`oneOf`/`anyOf` are used with proper semantics.
- [ ] No unexpected circular references exist.
- [ ] Checked `/v3/api-docs` with `jq` or a validator.
- [ ] Swagger UI or client generators can read the generated structure.

## 18. References

- [springdoc-openapi – Official Documentation](https://springdoc.org/)
- [Swagger – Using $ref](https://swagger.io/docs/specification/v3_0/using-ref/)
- [OpenAPI Specification – Reference Object](https://spec.openapis.org/oas/latest.html#reference-object)
- [OpenAPI Specification – Schema Object](https://spec.openapis.org/oas/latest.html#schema-object)
- [OpenAPI Specification – Composition and Inheritance](https://spec.openapis.org/oas/latest.html#composition-and-inheritance)
- [Swagger Core – Annotations](https://github.com/swagger-api/swagger-core/wiki/Swagger-2.X---Annotations)

springdoc-openapi translates Java types and annotation metadata into schemas in the OpenAPI document. Nested DTOs describe hierarchical structures; component schemas and `$ref` enable reusing definitions across multiple places. After every DTO change, inspect the generated JSON and the operations using the component to ensure the contract remains clear and consistent.
