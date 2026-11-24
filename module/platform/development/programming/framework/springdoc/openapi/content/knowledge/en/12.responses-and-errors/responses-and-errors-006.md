# Array Responses, Data Envelopes, and Pagination Structures

A data-reading endpoint can return a single object, an array of objects, or a page of results containing both data and pagination metadata. These three response shapes have different meanings for clients. An array simply represents a collection of elements; a data envelope can add status or common messages; and a paginated response must convey the current position, page size, and total results.

In Spring Boot, controllers commonly return `List<T>`, wrapper DTOs, or Spring Data results. springdoc-openapi analyzes return types to generate OpenAPI schemas, helping Swagger UI and client generators understand response structures. This lesson guides you through designing these response shapes so they are clear, stable, and easy to test.

## Objectives

After this lesson, you will be able to:

- Distinguish object, array, wrapper, and page responses.
- Describe arrays in OpenAPI using `type: array` and `items`.
- Use `List<T>` or dedicated DTOs in Spring MVC controllers.
- Design generic data wrappers and know when to use an envelope.
- Design stable pagination DTOs instead of depending directly on library internal structures.
- Document `page`, `size`, and `sort` query parameters alongside pagination metadata schemas.
- Use springdoc-openapi to verify that array, wrapper, and page responses are generated accurately.
- Test empty results, multiple pages, the last page, and large datasets.

## 1. Distinguishing Object, Array, Wrapper, and Page

Suppose a product management API can return the following shapes:

**Single product:**

~~~json
{
  "id": 42,
  "name": "Mechanical keyboard",
  "price": 1250000
}
~~~

**Product list:**

~~~json
[
  {
    "id": 42,
    "name": "Mechanical keyboard",
    "price": 1250000
  },
  {
    "id": 43,
    "name": "Wireless mouse",
    "price": 650000
  }
]
~~~

**Data envelope:**

~~~json
{
  "data": [
    {
      "id": 42,
      "name": "Mechanical keyboard",
      "price": 1250000
    }
  ],
  "message": "Data retrieved successfully"
}
~~~

**Paginated result:**

~~~json
{
  "items": [
    {
      "id": 42,
      "name": "Mechanical keyboard",
      "price": 1250000
    }
  ],
  "page": {
    "number": 0,
    "size": 20,
    "totalElements": 57,
    "totalPages": 3,
    "numberOfElements": 1,
    "first": true,
    "last": false
  }
}
~~~

| Response shape | Root structure | Suitable for |
|---|---|---|
| Object | A JSON object | Fetching details of a single resource |
| Array | A JSON array | Small lists without page metadata |
| Wrapper | Object containing data and shared metadata | APIs using a uniform envelope |
| Page | Object containing a slice of data and pagination metadata | Large datasets fetched page by page |

Do not wrap every response in an envelope merely to enforce an identical outer shape. Choose the structure that helps clients understand the data and navigate results. If an endpoint returns an empty list, it should normally return `200 OK` with `[]`; `204 No Content` means the response has no body and represents a different contract.

## 2. Arrays in JSON and OpenAPI

In JSON, arrays are enclosed in square brackets. Elements within an array normally follow the same schema:

~~~json
[
  "spring",
  "java",
  "openapi"
]
~~~

OpenAPI describes an array with `type: array`; `items` defines the type of each element:

~~~yaml
type: array
items:
  type: string
~~~

An array of objects referencing a shared schema:

~~~yaml
type: array
items:
  $ref: '#/components/schemas/ProductResponse'
~~~

Schema declaration example:

~~~yaml
components:
  schemas:
    ProductResponse:
      type: object
      required:
        - id
        - name
      properties:
        id:
          type: integer
          format: int64
          example: 42
        name:
          type: string
          example: Mechanical keyboard
        price:
          type: number
          example: 1250000
    ProductList:
      type: array
      items:
        $ref: '#/components/schemas/ProductResponse'
~~~

When the item schema changes, every reference to ProductResponse uses the updated definition. Do not describe an array with only `type: array` and omit `items`; otherwise clients cannot tell whether elements are strings, numbers, or which object type.

### Array Constraints

OpenAPI can describe item-count limits and uniqueness:

~~~yaml
type: array
minItems: 1
maxItems: 100
uniqueItems: true
items:
  type: integer
  format: int64
~~~

- `minItems`: minimum number of items.
- `maxItems`: maximum number of items.
- `uniqueItems: true`: elements must not repeat according to schema equality rules.
- `items`: schema of each element.

Declare constraints only if the server actually validates or guarantees them. If OpenAPI says at most 100 items while the endpoint accepts 500 items, the contract fails to reflect runtime behavior.

## 3. Returning `List<T>` from Spring Boot

Spring MVC can serialize a `List<ProductResponse>` into a JSON array:

~~~java
public record ProductResponse(
    Long id,
    String name,
    BigDecimal price
) {}

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping
    public List<ProductResponse> list() {
        return productService.findAll();
    }
}
~~~

If the service returns an empty list, the typical response is:

~~~http
HTTP/1.1 200 OK
Content-Type: application/json

[]
~~~

springdoc normally infers the item type from the generic return type and generates an array schema with `items` referencing ProductResponse. You do not need to manually declare `type: array` on every controller when the Java type is clear and the generated output is accurate.

### When to Describe Arrays Explicitly

If the return type is complex or inference falls short, you can use `@ApiResponse`, `@Content`, and `@ArraySchema`:

~~~java
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;

@GetMapping
@ApiResponse(
    responseCode = "200",
    description = "Product list",
    content = @Content(
        mediaType = "application/json",
        array = @ArraySchema(
            schema = @Schema(implementation = ProductResponse.class)
        )
    )
)
public List<ProductResponse> list() {
    return productService.findAll();
}
~~~

`@ArraySchema` describes the array schema itself; `@Schema(implementation = ProductResponse.class)` describes each item. Do not use `@Schema(implementation = ProductResponse.class)` alone when the actual response is an array, as that can cause the docs to describe an object instead of an array.

### `ResponseEntity<List<T>>`

When you need to control status or headers, wrap the list in ResponseEntity:

~~~java
@GetMapping
public ResponseEntity<List<ProductResponse>> list() {
    List<ProductResponse> products = productService.findAll();
    return ResponseEntity.ok(products);
}
~~~

`ResponseEntity` does not alter the body structure: the JSON remains an array. springdoc inspects the inner body type inside ResponseEntity to generate the response schema.

## 4. Nested Arrays and Other Element Types

Arrays can contain nested objects:

~~~java
public record ProductGroupResponse(
    String category,
    List<ProductResponse> products
) {}
~~~

Corresponding OpenAPI:

~~~yaml
ProductGroupResponse:
  type: object
  properties:
    category:
      type: string
    products:
      type: array
      items:
        $ref: '#/components/schemas/ProductResponse'
~~~

Arrays can also contain enums:

~~~java
public enum ProductStatus {
    DRAFT,
    ACTIVE,
    ARCHIVED
}

public record ProductStatusResponse(
    List<ProductStatus> statuses
) {}
~~~

The enum element schema can be represented as a string with allowed values. For arrays of numbers, dates/times, or value objects, inspect `type`, `format`, and referenced schemas in the generated docs.

### Empty Arrays, Null, and Missing Fields

These three states are not the same:

- `[]`: the array exists with zero elements.
- `null`: the array value is null.
- Missing property: the field does not appear on the parent object.

Clients may handle these three cases differently. For result lists, prefer returning `[]` when there are no items. If a property can be null or absent, describe that clearly in the schema and ensure serialization and validation follow the convention.

## 5. Data Envelopes (Response Envelopes)

An envelope is an object wrapping the primary payload alongside shared metadata. Example:

~~~java
public record ApiResponse<T>(
    T data,
    String message
) {}
~~~

A controller can return:

~~~java
@GetMapping("/{id}")
public ApiResponse<ProductResponse> getById(@PathVariable Long id) {
    ProductResponse product = productService.getById(id);
    return new ApiResponse<>(product, "Product retrieved successfully");
}
~~~

With a list:

~~~java
@GetMapping
public ApiResponse<List<ProductResponse>> list() {
    return new ApiResponse<>(
        productService.findAll(),
        "Product list retrieved successfully"
    );
}
~~~

In the second case, the body is an object with a `data` property, and `data` is an array. This is not a direct array response. Clients must access `response.data` before iterating over items.

### When Should You Use an Envelope?

An envelope is useful when the API needs a consistent convention for metadata such as request IDs, display messages, or the main payload. However, weigh the trade-offs:

- If the metadata adds no value, an envelope makes responses longer and adds an extra property lookup for clients.
- If errors use a different structure, document error responses separately instead of forcing every case into the same envelope.
- When using HTTP status codes to convey success or failure, do not return `200` everywhere and replace HTTP semantics with a `success` boolean.
- If an API was already released returning raw arrays directly, switching to an envelope is a breaking contract change.

There is no rule requiring every endpoint to use an envelope. Choose an API-wide convention and apply it consistently.

## 6. Generic Schemas for Envelopes

OpenAPI can represent a wrapper schema containing a `data` property. When `data` is ProductResponse:

~~~yaml
ApiResponseProduct:
  type: object
  properties:
    data:
      $ref: '#/components/schemas/ProductResponse'
    message:
      type: string
~~~

When `data` is an array:

~~~yaml
ApiResponseProductList:
  type: object
  properties:
    data:
      type: array
      items:
        $ref: '#/components/schemas/ProductResponse'
    message:
      type: string
~~~

A generic Java class `ApiResponse<T>` reduces code duplication, though the exact component names generated by springdoc/swagger-core can vary across versions and configurations. Inspect `/v3/api-docs` to see how schemas are named and whether the generic `T` was substituted with the concrete type.

### Generic Types in Controllers

Declaring complete return types enables tool inference:

~~~java
@GetMapping("/{id}")
public ApiResponse<ProductResponse> getById(@PathVariable Long id) {
    return new ApiResponse<>(productService.getById(id), "OK");
}
~~~

Avoid raw return types such as `ApiResponse` or `ResponseEntity` without type arguments. When type information is lost, springdoc struggles to determine the `data` schema, and client generators may produce an untyped object.

If tooling does not generate generic schemas as desired, define concrete DTOs for key responses:

~~~java
public record ProductResponseEnvelope(
    ProductResponse data,
    String message
) {}

public record ProductListEnvelope(
    List<ProductResponse> data,
    String message
) {}
~~~

Concrete DTOs yield predictable component names and tighter control, at the cost of a few extra Java classes.

## 7. Why Should You Avoid Returning `PageImpl` Directly?

Spring Data provides `Page<T>` to represent a data slice alongside pagination metadata. A controller can return it directly:

~~~java
@GetMapping
public Page<ProductResponse> search(Pageable pageable) {
    return productService.search(pageable);
}
~~~

This is convenient for internal apps, but JSON serialization of implementation types such as PageImpl can expose internal library structure. When Spring Data versions change, the JSON shape can change as well. That couples clients to implementation details instead of an intentionally designed API contract.

Spring Data also warns that serializing Page implementations directly is not a stable format for public APIs. In modern Spring Data versions, you can use the web support's DTO serialization mode for a more stable representation; however, a dedicated response DTO still gives exact control over field names, metadata content, and contract compatibility.

Treat `Page<T>` as a utility result type in the service/repository layer. At the API boundary, map that result to a public DTO whose structure is owned by your project.

## 8. Designing Pagination DTOs

A page response structure can include a list of items and metadata:

~~~java
public record PageMetadata(
    int number,
    int size,
    long totalElements,
    int totalPages,
    int numberOfElements,
    boolean first,
    boolean last,
    boolean empty
) {}

public record PageResponse<T>(
    List<T> items,
    PageMetadata page
) {}
~~~

Meaning:

| Field | Meaning |
|---|---|
| `items` | Elements in the current page |
| `number` | Current page index, e.g., 0-based if following Spring Data conventions |
| `size` | Requested page size or effective page size per contract |
| `totalElements` | Total elements matching the query |
| `totalPages` | Total number of pages |
| `numberOfElements` | Actual number of elements in the current page |
| `first` | Whether this is the first page |
| `last` | Whether this is the last page |
| `empty` | Current page has no elements |

Example response:

~~~json
{
  "items": [
    {
      "id": 42,
      "name": "Mechanical keyboard",
      "price": 1250000
    },
    {
      "id": 43,
      "name": "Wireless mouse",
      "price": 650000
    }
  ],
  "page": {
    "number": 0,
    "size": 20,
    "totalElements": 57,
    "totalPages": 3,
    "numberOfElements": 2,
    "first": true,
    "last": false,
    "empty": false
  }
}
~~~

Metadata definitions must remain consistent. For example, if a client requests `size=1000` while the server caps page size at 100, the response should return `size=100` to show the effective size. `totalElements` must be the total matching results after filters are applied, not the count of items on the current page.

### Converting `Page<T>` to `PageResponse<T>`

The service can return `Page<ProductResponse>`, and the controller converts it to the DTO:

~~~java
private PageResponse<ProductResponse> toPageResponse(
        Page<ProductResponse> result) {

    PageMetadata metadata = new PageMetadata(
        result.getNumber(),
        result.getSize(),
        result.getTotalElements(),
        result.getTotalPages(),
        result.getNumberOfElements(),
        result.isFirst(),
        result.isLast(),
        result.isEmpty()
    );

    return new PageResponse<>(result.getContent(), metadata);
}
~~~

Controller:

~~~java
@GetMapping
public PageResponse<ProductResponse> search(
        @ParameterObject Pageable pageable) {
    Page<ProductResponse> result = productService.search(pageable);
    return toPageResponse(result);
}
~~~

springdoc's `@ParameterObject` expands Pageable properties into query parameters in the documentation. Import `org.springdoc.core.annotations.ParameterObject` in modern springdoc versions. If your project version lacks this annotation or infers differently, declare `page`, `size`, and `sort` explicitly with `@Parameter`.

In real controllers, enforce a maximum `size` limit and an allowlist of `sort` fields. Never allow clients to sort arbitrarily by internal column names or unchecked expressions.

## 9. Describing Pagination Schemas in OpenAPI

A page schema has two layers: the item array and metadata. Example:

~~~yaml
components:
  schemas:
    PageMetadata:
      type: object
      required:
        - number
        - size
        - totalElements
        - totalPages
      properties:
        number:
          type: integer
          minimum: 0
          description: Zero-based page index
          example: 0
        size:
          type: integer
          minimum: 1
          example: 20
        totalElements:
          type: integer
          format: int64
          example: 57
        totalPages:
          type: integer
          example: 3
        numberOfElements:
          type: integer
          example: 20
        first:
          type: boolean
          example: true
        last:
          type: boolean
          example: false
        empty:
          type: boolean
          example: false
    ProductPageResponse:
      type: object
      required:
        - items
        - page
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/ProductResponse'
        page:
          $ref: '#/components/schemas/PageMetadata'
~~~

An operation using this schema:

~~~yaml
paths:
  /api/products:
    get:
      summary: Search products with pagination
      responses:
        '200':
          description: Page of products
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductPageResponse'
~~~

If the endpoint wraps the page in an outer envelope, the schema adds one more layer:

~~~yaml
ProductSearchEnvelope:
  type: object
  properties:
    data:
      $ref: '#/components/schemas/ProductPageResponse'
    message:
      type: string
~~~

Keep the schema faithful to the actual structure. If the controller returns ProductPageResponse directly, do not add a `data` property. If the controller returns ApiResponse<ProductPageResponse>, the schema must show `data` containing the page.

## 10. Query Parameters for Pagination and Sorting

A paginated API typically accepts:

| Parameter | Meaning | Example |
|---|---|---|
| `page` | Page index | `page=0` |
| `size` | Maximum items per page | `size=20` |
| `sort` | Sort field and direction | `sort=createdAt,desc` |

Spring Data Pageable uses zero-based page indexing by default. For example, `page=0&size=20` requests the first page of up to 20 items. If an API exposes 1-based page numbers to users, convert consistently between the public contract and `PageRequest`; never leave clients guessing.

A sort parameter can repeat to sort by multiple fields:

~~~text
GET /api/products?page=0&size=20&sort=createdAt,desc&sort=name,asc
~~~

In OpenAPI, these parameters can be described as follows:

~~~yaml
parameters:
  - name: page
    in: query
    required: false
    description: Zero-based page index
    schema:
      type: integer
      minimum: 0
      default: 0
  - name: size
    in: query
    required: false
    description: Maximum number of items per page
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
  - name: sort
    in: query
    required: false
    description: Sort field and direction; repeat parameter for multiple criteria
    style: form
    explode: true
    schema:
      type: array
      items:
        type: string
    example:
      - createdAt,desc
      - name,asc
~~~

With `style: form` and `explode: true`, multiple values are serialized by repeating the key in the query string. This matches how Spring Data binds multiple sort parameters. If the API uses a different syntax, document the actual syntax.

### Using `@ParameterObject` with Pageable

Springdoc can expand Pageable into query parameters:

~~~java
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.data.domain.Sort;

@GetMapping
public ProductPageResponse search(
        @ParameterObject
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        )
        Pageable pageable) {

    Page<ProductResponse> result = productService.search(pageable);
    return toPageResponse(result);
}
~~~

`@PageableDefault` sets default values for Pageable; `@ParameterObject` tells springdoc to expand the object's properties into documented parameters. Inspect `/v3/api-docs` to confirm that page, size, and sort have accurate descriptions, defaults, and bounds. If the annotation is not recognized in your version, declare individual `@Parameter` annotations instead of leaving query parameters undocumented.

### Explicit Parameter Declaration

When you want the contract independent of the Pageable type, declare parameters directly:

~~~java
@Operation(summary = "Search products with pagination")
@Parameters({
    @Parameter(
        name = "page",
        in = ParameterIn.QUERY,
        description = "Zero-based page index",
        schema = @Schema(type = "integer", defaultValue = "0", minimum = "0")
    ),
    @Parameter(
        name = "size",
        in = ParameterIn.QUERY,
        description = "Maximum number of items per page",
        schema = @Schema(type = "integer", defaultValue = "20", minimum = "1", maximum = "100")
    )
})
~~~

This metadata can be placed on the operation. For repeatable sort parameters, describe the array and serialization style clearly in OpenAPI YAML or use annotations with the corresponding attributes.

Common imports for the annotation snippet:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.Schema;
~~~

## 11. Capping Page Size and Controlling Sorting

Do not allow clients to request arbitrary page sizes. A request with `size=1000000` can trigger heavy queries, consume excessive memory, and produce oversized responses. Define:

- Default value for size.
- Minimum and maximum page size.
- How negative page numbers or zero size are handled.
- List of allowed sort fields.
- Default sort direction.
- Whether multiple sort criteria are permitted.

Example of applying bounds:

~~~java
int effectivePage = Math.max(page, 0);
int effectiveSize = Math.min(Math.max(size, 1), 100);
Pageable pageable = PageRequest.of(
    effectivePage,
    effectiveSize,
    Sort.by(Sort.Direction.DESC, "createdAt")
);
~~~

The snippet illustrates capping page and size along with a default sort. If clients are allowed to pass sort criteria, map public field names against an allowlist of valid fields:

~~~java
private static final Set<String> ALLOWED_SORTS =
    Set.of("name", "createdAt", "price");

private Sort toSort(String field, String direction) {
    if (!ALLOWED_SORTS.contains(field)) {
        throw new IllegalArgumentException("Unsupported sort field");
    }

    Sort.Direction sortDirection = Sort.Direction.fromString(direction);
    return Sort.by(sortDirection, field);
}
~~~

Never concatenate client sort strings directly into SQL or JPQL. Use Spring Data's Sort/Pageable with an allowed field list; if public field names need mapping to internal property names, perform that mapping on the server.

If the controller uses Bean Validation on method parameters such as `@Min` and `@Max`, configure method validation appropriately for your Spring Boot version—for instance placing `@Validated` on the controller and adding constraints to parameters. Whether you validate or clamp values, documentation must accurately reflect what happens when page/size is invalid or exceeds bounds.

## 12. Offset vs. Cursor Pagination

Page/size pagination is usually offset pagination. The client requests a page and size; the server skips the corresponding number of rows and fetches the next slice. This is intuitive and fits many admin screens, though deep pages can incur high query costs. When data changes between calls, items can shift, causing clients to see duplicates or skipped rows if ordering is unstable.

Cursor pagination uses a cursor representing the next position:

~~~json
{
  "items": [
    {
      "id": 42,
      "name": "Mechanical keyboard"
    }
  ],
  "page": {
    "nextCursor": "eyJpZCI6NDJ9",
    "hasNext": true
  }
}
~~~

The next request might look like:

~~~text
GET /api/products?cursor=eyJpZCI6NDJ9&limit=20
~~~

OpenAPI can document cursor and limit as query parameters, while response metadata contains nextCursor and hasNext. Cursors should be generated and validated on the server rather than letting clients modify raw offsets or internal keys. With cursor pagination, `totalElements` and `totalPages` are often omitted; computing totals can be expensive and unnecessary for infinite-scroll feeds.

| Criterion | Offset/page | Cursor |
|---|---|---|
| Navigation | By page number | By next/previous cursor |
| Jumping to an arbitrary page | Easy to support | Usually inconvenient |
| Continuously changing data | Items can shift between pages | More stable when cursor relies on suitable sort keys |
| Total element count | Often able to return total | Can omit total to reduce cost |
| Best suited for | Admin pages, data tables | Large feeds, infinite scroll, frequently changing data |

Choose the pagination model based on how clients navigate and query costs. Do not reuse the parameter name `page` for a cursor when its actual semantics is a continuation token.

## 13. Using springdoc to Document Arrays and Wrappers

With clear return types, springdoc usually infers arrays and item schemas automatically:

~~~java
@GetMapping
public List<ProductResponse> list() {
    return productService.findAll();
}
~~~

To declare an array response explicitly, use `@ArraySchema` inside `@Content`:

~~~java
@GetMapping
@ApiResponse(
    responseCode = "200",
    description = "Product list",
    content = @Content(
        mediaType = "application/json",
        array = @ArraySchema(
            schema = @Schema(implementation = ProductResponse.class)
        )
    )
)
public List<ProductResponse> list() {
    return productService.findAll();
}
~~~

With a concrete wrapper:

~~~java
@Schema(name = "ProductListEnvelope")
public record ProductListEnvelope(
    @ArraySchema(
        schema = @Schema(implementation = ProductResponse.class)
    )
    List<ProductResponse> data,
    String message
) {}
~~~

With a paginated response:

~~~java
@Schema(name = "ProductPageResponse")
public record ProductPageResponse(
    @ArraySchema(
        schema = @Schema(implementation = ProductResponse.class)
    )
    List<ProductResponse> items,
    PageMetadata page
) {}
~~~

The controller can declare the concrete response:

~~~java
@GetMapping
@ApiResponse(
    responseCode = "200",
    description = "Page of products",
    content = @Content(
        mediaType = "application/json",
        schema = @Schema(implementation = ProductPageResponse.class)
    )
)
public ProductPageResponse search(@ParameterObject Pageable pageable) {
    return productService.searchPage(pageable);
}
~~~

These examples illustrate schema and response metadata. Corresponding ProductResponse, PageMetadata, and service definitions are required. With generic return types, component names and type-argument substitution can differ across swagger-core/springdoc versions; inspect the generated JSON document to ensure `items` actually resolves to ProductResponse.

### When to Use `@ArraySchema`?

- Use the Java type `List<ProductResponse>` when springdoc already infers accurately.
- Use `@ArraySchema` when you need to describe items, array constraints, or specific examples.
- Use a regular object schema when the body is a wrapper holding an array inside a property.
- Do not declare an array response as an object just because the array's elements are objects.

If you need item-count constraints, add `minItems` or `maxItems` in `@ArraySchema` according to your annotation API version. Make sure the server enforces those bounds.

## 14. Customizing Generic Schemas and Component Names

Generics reduce repetitive Java code:

~~~java
public record ApiResponse<T>(
    T data,
    String message
) {}

public record PageResponse<T>(
    List<T> items,
    PageMetadata page
) {}
~~~

An operation might return:

~~~java
public ApiResponse<PageResponse<ProductResponse>> search(...) {
    // ...
}
~~~

Contractually, the final schema must represent these layers:

1. ApiResponse object with `data` and `message`.
2. `data` is a PageResponse object.
3. PageResponse has `items` as an array of ProductResponse and `page` as PageMetadata.

The component names springdoc generates for generic wrappers depend on generic resolution and library version. Never hardcode a guessed name in tests or guides. Open `/v3/api-docs`, follow `$ref` from the response into `components.schemas`, and verify that generic types were substituted properly.

If you need stable public schema names, create concrete DTOs:

~~~java
@Schema(name = "ProductSearchResponse")
public record ProductSearchResponse(
    ProductPageResponse data,
    String message
) {}
~~~

Or use schema customization via `OpenApiCustomizer` when a project needs broad naming rules or generic schema replacement. Customizers must update both schemas and all corresponding `$ref` values; never rename a component while leaving stale references behind.

### Avoid Sharing One Name for Multiple Generic Specializations

For instance, `ApiResponse<ProductResponse>` and `ApiResponse<OrderResponse>` share the same raw Java type while `data` has different schemas. If the component generator does not distinguish specializations under your current setup, the two types can collide or produce ambiguous schemas. For key responses, concrete DTOs are easier to control and help schema names reflect business context.

## 15. Handling Empty Pages, Last Pages, and Mutating Data

Pagination cases should be clearly specified:

| Case | Common response | Metadata |
|---|---|---|
| Results on first page | `200` with items | `first=true` |
| Middle page | `200` with items | `first=false`, `last=false` |
| Last page | `200` with items | `last=true` |
| No matching records | `200` with `items: []` | `empty=true`, `totalElements=0`, `totalPages=0` |
| Requested page past last page | Usually `200` with `items: []` | Total pages still reflects the query |

An API can pick a different policy for out-of-range pages, provided it is consistent and clearly documented. For collection searches, returning an empty page is usually easier to handle than returning `404`, since the collection endpoint still exists even when no elements sit at that offset.

### Stable Sorting

With offset pagination, use a deterministic sort order. If multiple records can share the same `createdAt`, add a unique key such as `id` as a tiebreaker. Otherwise, records can shift between pages when the database returns tied rows in an arbitrary order.

### Cost of Total Counts

`totalElements` usually requires a count query. With large datasets or complex filters, count queries can be expensive. If clients only need to know whether more data follows, consider responses with `hasNext` and cursors instead of always computing total pages.

### Effective Page Size

If the server caps `size`, the response should return the actual size applied. Do not return `size=1000` if the server fetched at most 100 items. Metadata must describe how the server processed the request, not merely echo back what the client sent.

## 16. Testing Array and Paginated Responses

MockMvc can verify JSON arrays:

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    ProductService productService;

    @Test
    void returnsProductArray() throws Exception {
        given(productService.findAll()).willReturn(List.of(
            new ProductResponse(42L, "Mechanical keyboard", new BigDecimal("1250000")),
            new ProductResponse(43L, "Wireless mouse", new BigDecimal("650000"))
        ));

        mockMvc.perform(get("/api/products"))
            .andExpect(status().isOk())
            .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
            .andExpect(jsonPath("$").isArray())
            .andExpect(jsonPath("$.length()").value(2))
            .andExpect(jsonPath("$[0].id").value(42));
    }

    @Test
    void returnsEmptyArrayWhenNoProductsMatch() throws Exception {
        given(productService.findAll()).willReturn(List.of());

        mockMvc.perform(get("/api/products"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$").isArray())
            .andExpect(jsonPath("$.length()").value(0));
    }
}
~~~

Pagination tests can assert both items and metadata:

~~~java
@Test
void returnsPageItemsAndMetadata() throws Exception {
    Page<ProductResponse> result = new PageImpl<>(
        List.of(new ProductResponse(
            42L, "Mechanical keyboard", new BigDecimal("1250000")
        )),
        PageRequest.of(0, 20),
        57
    );
    given(productService.search(any(Pageable.class))).willReturn(result);

    mockMvc.perform(get("/api/products")
            .param("page", "0")
            .param("size", "20"))
        .andExpect(status().isOk())
        .andExpect(jsonPath("$.items[0].id").value(42))
        .andExpect(jsonPath("$.page.number").value(0))
        .andExpect(jsonPath("$.page.size").value(20))
        .andExpect(jsonPath("$.page.totalElements").value(57))
        .andExpect(jsonPath("$.page.totalPages").value(3));
}
~~~

The example assumes the controller converts Page to ProductPageResponse and the service is mocked with matching signatures. Add Spring Test, Mockito, PageImpl, PageRequest, and project DTO imports. If the controller accepts `Pageable`, verify that query parameters bind properly as well.

### Verifying OpenAPI Schemas

Call the docs endpoint and verify the array response:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.paths['/api/products'].get.responses['200'].content['application/json'].schema.type"
    ).value("array"));
~~~

For page responses, check that the schema is an object whose `items` property is an array and whose `page` references PageMetadata. Schema names may vary when using generic wrappers; inspect the actual `$ref` instead of assuming a component name.

A thorough test suite should cover:

- Non-empty arrays and empty arrays.
- Wrappers where `data` is an object and where `data` is an array.
- First page, middle page, last page, and empty page.
- Negative `page`, zero `size`, and `size` exceeding the maximum.
- Valid sort, unsupported sort, and multiple sort criteria.
- OpenAPI schemas accurately reflecting array items, wrappers, and page metadata.

## 17. Common Design Mistakes

| Mistake | Consequence | Fix |
|---|---|---|
| Returning `List<T>` while docs describe an object | Clients parse body structure incorrectly | Use an array schema with the right `items` type |
| Declaring `type: array` without `items` | Clients do not know the element type | Reference an item schema or declare a scalar type |
| Returning `null` for an empty array | Clients must handle an unnecessary extra state | Return `[]` when the collection has no items |
| Returning `204` and expecting clients to read JSON | Response has no body under HTTP semantics | Use `200` when returning an empty array or metadata |
| Wrapping response without a `data` property in OpenAPI | Contract mismatches actual JSON | Describe the wrapper schema instead of the item schema directly |
| Using raw generic `ApiResponse` | `data` schema lacks a concrete type | Declare complete generics or dedicated DTOs |
| Returning PageImpl structure directly as a long-term contract | Clients depend on Spring Data internals | Convert to a PageResponse DTO or intentionally configure stable DTO serialization |
| Not capping page size | Requests can trigger huge queries and responses | Enforce defaults, maximums, and server-side checks |
| Allowing sorting on any property | Exposes persistence details or unsafe queries | Map through an allowlist of public fields |
| Missing a unique sort tiebreaker | Records can shift positions across pages | Add a unique key as a secondary sort criterion |
| Always computing total count when unnecessary | Count queries can be expensive | Consider cursors and `hasNext` metadata |
| Generic schema name collisions | Client generators receive wrong or ambiguous models | Use concrete DTOs or control component names |

### When Can You Use `PageSerializationMode.VIA_DTO`?

Spring Data Commons 3.3+ offers a DTO serialization mode for Page to avoid exposing PageImpl internals directly:

~~~java
import org.springframework.data.web.config.EnableSpringDataWebSupport;
import org.springframework.data.web.config.EnableSpringDataWebSupport.PageSerializationMode;
import org.springframework.context.annotation.Configuration;

@EnableSpringDataWebSupport(pageSerializationMode = PageSerializationMode.VIA_DTO)
@Configuration
public class SpringDataWebConfiguration {
}
~~~

This is useful if a project wants to adopt Spring Data's built-in DTO representation. Even so, responses still follow Spring Data's PagedModel structure. If an API requires custom property names, metadata, or compatibility rules, map Page into an application DTO such as PageResponse. Check your Spring Data version before enabling this setting.

## 18. Comprehensive Practice Exercise

Build a product search endpoint supporting both lists and pagination:

1. Create ProductResponse and an endpoint returning `List<ProductResponse>` for a small dataset.
2. Verify springdoc generates an array schema with `items` referencing ProductResponse.
3. Create ApiResponse<T> and ProductListEnvelope to compare a direct array response with an envelope.
4. Create PageMetadata and ProductPageResponse with items and metadata.
5. Accept Pageable using `@ParameterObject` or declare `page`, `size`, and `sort` explicitly.
6. Set default page to 0, default size to 20, and cap maximum size at 100.
7. Allow sorting only on defined public fields and add id as a secondary tiebreaker for stable ordering.
8. Convert `Page<ProductResponse>` from the service into ProductPageResponse before returning to clients.
9. Generate the OpenAPI spec for the paginated response and inspect schemas in Swagger UI.
10. Write tests for an empty array, first page, last page, out-of-range page, and oversized size.
11. Compare runtime JSON against the OpenAPI schema and adjust if any property or data type mismatches.
12. Evaluate when the API needs offset pagination and when cursor pagination is a better fit.

### Completion Criteria

- [ ] Array responses have schema `type: array` and accurate `items` types.
- [ ] Empty arrays are represented consistently and not confused with 204 responses.
- [ ] Wrappers have schemas accurately showing the data property and inner generic type.
- [ ] Page responses have an items array and clearly described metadata.
- [ ] Query parameters page, size, and sort include types, defaults, bounds, and examples.
- [ ] The server enforces size caps and the sort allowlist as specified in the contract.
- [ ] Metadata reflects the effective page size and accurate total counts.
- [ ] OpenAPI JSON and Swagger UI display array, wrapper, and page responses accurately.
- [ ] Tests cover empty results, multiple pages, and invalid parameters.
- [ ] No direct coupling to unstable internal library serialization structures.

## Next Steps

After this lesson, combine array and page responses with standardized error handling, reusable response components, and contract versioning. When changing from a raw array to a wrapper or altering pagination metadata structures, treat it as an API change requiring compatibility review, OpenAPI updates, and client testing before release.
