# Arrays, Collections, and @ArraySchema

## 1. Why Describe Arrays and Collections?

Many APIs exchange data as lists: product lists, order line items, user roles, attached images, or sets of status codes to filter by. In Java, such data is typically represented by an array, `List`, `Set`, or another `Collection` type.

JSON uses the **array** type to represent an ordered sequence of values. OpenAPI describes this data type with a schema having `type: array` and a nested `items` schema specifying the type of each element. When Springdoc OpenAPI reads controller signatures and DTOs, the library can infer array structures from Java types. The **`@ArraySchema`** annotation allows describing both the array and its inner elements more clearly.

Properly describing array schemas helps clients know:

- What data type a list in the response returns.
- Whether the request must send an array of strings, numbers, enums, or objects.
- Whether the array may be empty and its minimum/maximum element count.
- Whether elements must be unique.
- What schema, format, example, and constraints apply to each element.

If you merely write "list of data" without describing element types, clients must guess the JSON structure. If the schema allows an empty array while the backend requires at least one element, documentation and runtime will be inconsistent.

## 2. Arrays in JSON and Array Schemas in OpenAPI

In JSON, arrays are written using square brackets. Elements can be strings, numbers, booleans, objects, nested arrays, or null values if permitted by the schema.

Example:

~~~json
{
  "productIds": [101, 102, 103],
  "tags": ["new", "featured"],
  "items": [
    {
      "productId": 101,
      "quantity": 2
    },
    {
      "productId": 102,
      "quantity": 1
    }
  ]
}
~~~

OpenAPI describes an array using `type: array`. The `items` field is the schema of each element:

~~~yaml
type: array
items:
  type: integer
  format: int64
~~~

The schema above describes an array of 64-bit integers. A valid JSON example is `[101, 102, 103]`.

For an array of objects, `items` references the object's schema:

~~~yaml
type: array
items:
  $ref: '#/components/schemas/OrderItem'
~~~

Each element in the array must conform to the `OrderItem` schema. This structure commonly appears when an endpoint returns a list of DTOs or accepts a list of objects in a request body.

## 3. How Are Java Arrays and Collections Inferred by Springdoc?

Java has several ways to represent a sequence of data. Common types:

| Java Type | Meaning | Common JSON Shape |
|---|---|---|
| `ProductResponse[]` | Java array with fixed size after creation | Array |
| `List<ProductResponse>` | Ordered list allowing duplicate elements | Array |
| `Set<ProductResponse>` | Set disallowing duplicate elements; order depends on implementation | Array |
| `Collection<String>` | General collection interface | Array |
| `List<String>` | List of strings | Array |
| `List<List<Long>>` | Nested array | Array containing arrays |

Example of a controller returning a list:

~~~java
@GetMapping("/api/products")
public List<ProductResponse> findAll() {
    return productService.findAll();
}
~~~

Springdoc typically infers the response schema as an array with `items` schema `ProductResponse`. In the OpenAPI document, elements can reference `components.schemas.ProductResponse`.

A declaration using a Java array also produces a JSON array shape:

~~~java
@GetMapping("/api/product-codes")
public String[] getProductCodes() {
    return productService.getProductCodes();
}
~~~

To a client, a JSON array does not directly indicate whether the backend uses `List`, `Set`, or a Java array. The difference mainly lies in Java semantics and behavior. The OpenAPI contract should describe the JSON structure and the rules clients must follow.

## 4. The items Structure: Describing Each Element's Type

In an Array Schema, `items` defines the type and constraints of each element. This is the most important part for clients to understand what data a list holds.

### 4.1. Array of strings

~~~yaml
type: array
items:
  type: string
  example: featured
~~~

Corresponding JSON:

~~~json
["new", "featured", "sale"]
~~~

### 4.2. Array of numbers

~~~yaml
type: array
items:
  type: number
  format: double
~~~

Corresponding JSON:

~~~json
[12.5, 18.75, 20.0]
~~~

### 4.3. Array of enums

~~~yaml
type: array
items:
  type: string
  enum:
    - DRAFT
    - ACTIVE
    - ARCHIVED
~~~

Each element may only take one of the published enum values.

### 4.4. Array of objects

~~~yaml
type: array
items:
  $ref: '#/components/schemas/OrderItem'
~~~

Each element must follow the `OrderItem` schema structure. Do not describe an array of objects simply with `type: object` if clients need to know the child properties.

### 4.5. Array whose elements are arrays

~~~yaml
type: array
items:
  type: array
  items:
    type: integer
~~~

Corresponding JSON:

~~~json
[
  [1, 2, 3],
  [4, 5, 6]
]
~~~

For nested arrays, each array level needs its own `items` schema. Clearly describe the number of dimensions and the meaning of each level so clients do not confuse a matrix array with a list of objects.

## 5. What Is @ArraySchema Used For?

The **`@ArraySchema`** annotation belongs to the `io.swagger.v3.oas.annotations.media` package. It is used to describe the schema of an array in OpenAPI, including:

- The element schema via the `schema` attribute.
- Metadata of the array itself via `arraySchema`.
- Element count constraints such as `minItems` and `maxItems`.
- Element uniqueness rules via `uniqueItems`.

The two key attributes can be understood as:

| Attribute | Description |
|---|---|
| `schema` | Schema of each element in the array |
| `arraySchema` | Schema of the array itself, such as description or overall metadata |

Example describing a list of product IDs:

~~~java
@ArraySchema(
    arraySchema = @Schema(
        description = "List of product IDs"
    ),
    schema = @Schema(
        type = "integer",
        format = "int64",
        example = "101"
    ),
    minItems = 1,
    maxItems = 100,
    uniqueItems = true
)
private List<Long> productIds;
~~~

Here, `arraySchema` describes the overall list; `schema` describes a single product ID. `minItems` requires at least one element, `maxItems` limits to at most 100 elements, and `uniqueItems` declares that elements must be unique.

Supported annotation attributes depend on the `swagger-annotations` version your project uses. When upgrading libraries, check the annotation API and the generated OpenAPI documentation.

## 6. Describing Arrays in Request DTOs

A request body often contains a list of objects. For example, when creating an order, the client sends line items in the `items` property.

DTO:

~~~java
public record CreateOrderRequest(
    @NotEmpty
    @Size(min = 1, max = 50)
    @ArraySchema(
        arraySchema = @Schema(
            description = "Order line items"
        ),
        schema = @Schema(
            implementation = OrderItemRequest.class
        ),
        minItems = 1,
        maxItems = 50
    )
    List<@Valid OrderItemRequest> items
) {}

public record OrderItemRequest(
    @NotNull
    @Positive
    @Schema(description = "Product ID", example = "101")
    Long productId,

    @NotNull
    @Min(1)
    @Schema(description = "Order quantity", example = "2")
    Integer quantity
) {}
~~~

Controller receiving the request:

~~~java
@PostMapping("/api/orders")
public OrderResponse createOrder(
    @Valid @RequestBody CreateOrderRequest request
) {
    return orderService.create(request);
}
~~~

Springdoc can generate an array schema for `items` and reference the `OrderItemRequest` schema for each element. When clients read the docs, they know each element must contain productId and quantity.

In the example, the annotations have distinct roles:

- `@ArraySchema` describes the array structure in OpenAPI.
- `@Schema` describes elements or array metadata.
- `@NotEmpty` requires the collection to be non-null and non-empty when validation runs.
- `@Size` limits the element count on the backend.
- `@Valid` on the collection element triggers nested validation for each `OrderItemRequest`.

Documentation constraints and validation should stay consistent. If `minItems = 1` is only declared in OpenAPI without backend validation, clients can send an empty array and get behavior different from what documentation promises.

## 7. Distinguishing required, minItems, and nullable

Three concepts are often confused when describing an array property on an object.

| Rule | Meaning |
|---|---|
| Object `required` | Whether the array property must appear in the JSON object |
| `minItems` | Minimum number of elements in the array |
| `nullable` or type containing null | Whether the array property's value may be null |

Example:

~~~yaml
type: object
required:
  - tags
properties:
  tags:
    type: array
    minItems: 1
    items:
      type: string
~~~

This schema requires the `tags` property to be present and contain at least one string.

If `tags` is removed from the `required` list, the property may be omitted. If kept in `required` without declaring minItems, an empty array may still be valid.

In OpenAPI 3.0, `nullable: true` can be used to allow the array property to be null. In OpenAPI 3.1, null is represented per JSON Schema, such as `type: [array, "null"]`. Whether the property must appear is still determined separately by the object's `required` list.

Therefore, when designing DTOs, distinguish:

- `List<String> tags` can be non-null or null depending on constructor, binding, and validation.
- `@NotNull` requires the collection to be non-null.
- `@NotEmpty` requires the collection to be non-null and have at least one element.
- `@Size(min = 1, max = 10)` limits element count; if null must be forbidden, add a separate constraint.

## 8. minItems, maxItems, and uniqueItems

OpenAPI provides keywords specifically for array schemas:

| Keyword | Meaning |
|---|---|
| `minItems` | Minimum number of elements |
| `maxItems` | Maximum number of elements |
| `uniqueItems` | Requires elements to be non-duplicate |

Example:

~~~yaml
type: array
minItems: 1
maxItems: 20
uniqueItems: true
items:
  type: string
~~~

The array must have 1 to 20 strings and no two duplicate elements under JSON Schema comparison rules.

Several constraints can be mapped from Bean Validation:

| Bean Validation | Corresponding Array Constraint |
|---|---|
| `@NotNull` | Collection must not be null; not equivalent to minItems |
| `@NotEmpty` | Non-null and has at least one element |
| `@Size(min = 1)` | Minimum of one element |
| `@Size(max = 20)` | Maximum of 20 elements |
| `@UniqueElements` if using Hibernate Validator | Non-duplicate elements per validator |

Springdoc may infer some limits from Bean Validation depending on version and configuration. `@UniqueElements` is not part of standard Bean Validation; it is a Hibernate Validator constraint. If used, ensure the validator dependency is present and check whether Springdoc converts that constraint into `uniqueItems` in the documentation. You can declare `uniqueItems` directly in `@ArraySchema` to state the contract clearly.

## 9. Describing Set Collections and Uniqueness Semantics

Java `Set` typically represents a collection without duplicate elements according to the element's `equals/hashCode` rules. JSON has no separate Set type; when serialized, a Set is typically represented as an array.

Example:

~~~java
public record ProductFilter(
    Set<String> categories
) {}
~~~

JSON:

~~~json
{
  "categories": ["keyboard", "mouse", "monitor"]
}
~~~

However, Java using a Set does not automatically mean clients are guaranteed a stable order. Some implementations such as `HashSet` do not guarantee iteration order. If order matters in the contract, use `List` and document the ordering in description.

If uniqueness is an important rule for clients, express it explicitly with `uniqueItems: true` or `@ArraySchema(uniqueItems = true)`. Do not rely solely on the `Set` type because OpenAPI documentation needs to publish this rule for all clients, including clients written in other languages.

Also note that JSON Schema uniqueness compares JSON values. For objects, two objects with equivalent content are considered duplicates under JSON Schema rules, whereas a Java `Set` may use custom `equals` logic. Verify alignment when elements are objects.

## 10. Describing Arrays in Responses

An endpoint can return a list directly:

~~~java
@GetMapping("/api/products")
public List<ProductResponse> findAll() {
    return productService.findAll();
}
~~~

Springdoc typically infers the response as an array with item schema `ProductResponse`. If you want to add a description or constraints to the response array, you can use `@ArraySchema` on the method:

~~~java
@GetMapping("/api/products")
@Operation(summary = "Get list of products")
@ArraySchema(
    arraySchema = @Schema(
        description = "List of currently available products"
    ),
    schema = @Schema(
        implementation = ProductResponse.class
    )
)
public List<ProductResponse> findAll() {
    return productService.findAll();
}
~~~

For responses shaped as an object wrapping a list, such as:

~~~json
{
  "content": [
    {
      "id": 101,
      "name": "Mechanical keyboard"
    }
  ],
  "totalElements": 1
}
~~~

`content` is an array property inside the object, rather than the entire response being an array. Use `@ArraySchema` on the `content` property inside the wrapper DTO and use `@Schema` for the outer object.

Distinguish `List<ProductResponse>` from `Page<ProductResponse>`. The `Page` type is typically represented as an object with pagination metadata; do not describe the entire `Page` response as a plain array.

## 11. Nested Arrays and Composite Collections

An array can contain arrays or an object can have array properties. Example of route coordinate data across multiple paths:

~~~yaml
type: array
items:
  type: array
  items:
    type: number
    format: double
~~~

Or an object containing multiple lists:

~~~yaml
type: object
properties:
  images:
    type: array
    items:
      type: string
      format: uri
  variants:
    type: array
    items:
      $ref: '#/components/schemas/ProductVariant'
~~~

In Java:

~~~java
public record ProductResponse(
    Long id,
    List<String> images,
    List<ProductVariant> variants
) {}
~~~

Springdoc typically infers each array property from its generic type. If nested structures are complex or require separate descriptions at the array and item levels, use `@ArraySchema` and `@Schema` in appropriate places, then check the generated JSON/YAML.

Do not overuse multidimensional arrays when an object with meaningful field names helps clients understand the data better. For example, instead of returning `[[1,2],[3,4]]`, you can return a list of objects with `latitude` and `longitude` if they represent geographic coordinates.

## 12. Examples and Descriptions for Array Elements

Arrays often need examples so clients understand the data shape. You can use an example at the array level or examples for individual items.

OpenAPI example:

~~~yaml
type: array
description: List of status codes to filter by
minItems: 1
items:
  type: string
  enum:
    - ACTIVE
    - INACTIVE
    - ARCHIVED
example:
  - ACTIVE
  - ARCHIVED
~~~

In Java, you can use `@ArraySchema` for structure and `@ExampleObject` on the request/response media type to provide a complete example. Examples must conform to the schema, including element type, enum, count limits, and uniqueness.

Do not confuse an array example with an item example. If the schema is an array, the example must be an array like `["ACTIVE", "ARCHIVED"]`, not a single string like `"ACTIVE"`.

## 13. Common Mistakes When Describing Arrays

| Symptom | Cause to Check |
|---|---|
| Swagger UI displays item as an empty object | Springdoc could not infer generic type or `implementation` needs to be declared |
| Array is described as an object | Annotation placed in the wrong location or incorrect schema override |
| Missing element count bounds | `minItems`/`maxItems` not declared or constraints not inferred |
| Set does not indicate uniqueness | `uniqueItems` not declared or tool does not infer from Java type |
| Array response wrapped as object | Actual return type is a wrapper like `Page` or DTO |
| Nested array has wrong dimensions | `items` schemas at each level were not declared accurately |
| Invalid example | Example is a single item instead of an array or mismatches item schema |
| Backend accepts empty array while docs forbid it | `minItems`/validation are out of sync |
| Backend deduplicates elements while docs do not mention it | `uniqueItems` or deduplication rules were not published |

When encountering issues, inspect the OpenAPI JSON/YAML first, then compare with Java types, annotations, and actual validation. Do not rely solely on how Swagger UI renders it, because the UI may hide some schema details.

## 14. Inspecting Array Schemas in the OpenAPI Document

After starting the application, fetch the document:

~~~http
GET /v3/api-docs
~~~

For each array property or operation returning an array, check:

1. The schema has `type: array`.
2. `items` describes the element type.
3. The item schema references the proper component if it is a DTO.
4. `minItems`, `maxItems`, and `uniqueItems` match backend rules.
5. Object `required` reflects whether the array property must be present.
6. Nullability is described according to the OpenAPI version in use.
7. Examples are valid arrays and items match the schema.
8. Nested arrays have the right number of `items` levels.

You can combine an OpenAPI validator and integration tests:

- Send an empty array.
- Send element counts at and beyond the bounds.
- Send elements of the wrong type.
- Send duplicate elements if uniqueness is required.
- Send null elements if the schema allows or forbids them.
- Verify the response array and element order if order is part of the contract.

## 15. Principles for Using @ArraySchema in Projects

When describing arrays and Collections with Springdoc, keep these principles in mind:

1. Let Springdoc infer from Java arrays or generic Collections when the element type is already clear.
2. Use `@ArraySchema` when you need to describe the array container, item schema, or specific constraints.
3. Use `schema` to describe elements and `arraySchema` to describe the entire array.
4. Distinguish a required array property from minItems and nullability.
5. Only declare uniqueItems when the backend actually guarantees or checks uniqueness.
6. Use Bean Validation to enforce min/max size and nested validation at runtime.
7. Clearly describe nested arrays and composite generic Collections.
8. Use examples with an array shape matching the schema.
9. Inspect OpenAPI JSON/YAML and runtime behavior after changing annotations.

Java arrays, Lists, and Sets can all be represented as JSON arrays, but semantics regarding order, duplicate elements, and validation can differ. When Springdoc combines Java type inference with `@ArraySchema` and appropriate constraints, the OpenAPI documentation accurately describes both the array structure and the rules clients must obey.

