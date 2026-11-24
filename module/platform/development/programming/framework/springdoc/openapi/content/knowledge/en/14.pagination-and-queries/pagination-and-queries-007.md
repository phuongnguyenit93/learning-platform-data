# Page, Slice, and Application-Owned Pagination DTOs

Spring Data provides `Page<T>` and `Slice<T>` to represent partial query results. Both contain the items of the current data slice and navigation information, but differ in total-count metadata. `Page<T>` provides the total number of elements and total pages; `Slice<T>` focuses on whether a next slice exists and usually avoids a total count query.

When exposing results via an API, a controller can return `Page<T>` or `Slice<T>` directly. That is fast to get started, yet JSON from library types is not necessarily a stable public contract. An application-owned pagination DTO gives control over field names, metadata, OpenAPI schemas, and compatibility across Spring Data upgrades.

This lesson focuses on choosing Page or Slice based on requirements, converting query results into public DTOs, documenting responses with springdoc-openapi, and testing both data and metadata.

## Objectives

After this lesson, you will be able to:

- Distinguish `Page<T>` and `Slice<T>` in terms of contents, metadata, and query cost.
- Understand when paginated queries need a count query and when it can be avoided.
- Choose Page or Slice based on actual client needs.
- Design application-owned pagination DTOs with stable field names and semantics.
- Convert Spring Data Page/Slice into DTOs using `map()` and corresponding metadata.
- Document Page and Slice responses in OpenAPI using springdoc-openapi.
- Publish `page`, `size`, and `sort` query parameters along with valid bounds.
- Test the first page, middle pages, last page, empty pages, and accurately mapped metadata.

## 1. What Problem Do Page and Slice Solve?

Suppose a product search API has hundreds of thousands of records. Returning the entire list in one response forces the server to load excessive data, bloats the response, and makes clients process more than needed. Pagination allows clients to request one slice of results:

~~~http
GET /api/products?page=0&size=20
~~~

Spring Data uses `Pageable` to represent a page request and returns one of these abstractions:

- `Page<T>`: current contents along with metadata on total results and total pages.
- `Slice<T>`: current contents along with whether a next slice exists, without requiring total result count.

Both abstractions expose the current items via `getContent()`, page size, current page number, and basic navigation flags. The key difference is that Page knows the totals; Slice does not provide total elements or total pages.

## 2. Page<T>: When Clients Need Total Results

`Page<T>` fits when the UI needs to display total records, total pages, a page-number bar, or allow jumping directly to a specific page.

Example of a Page:

~~~text
page number        = 0
page size          = 20
total elements     = 57
total pages        = 3
number of elements = 20
first              = true
last               = false
~~~

Commonly used methods:

| Method | Meaning |
|---|---|
| `getContent()` | List of items on the current page |
| `getNumber()` | Current page index, starting from 0 by default |
| `getSize()` | Page size |
| `getNumberOfElements()` | Actual number of items on the current page |
| `getTotalElements()` | Total number of items matching the query |
| `getTotalPages()` | Total number of pages |
| `isFirst()` / `isLast()` | Whether this is the first/last page |
| `hasNext()` / `hasPrevious()` | Whether a next/previous page exists |
| `isEmpty()` | Current page has no items |

### Count Query Cost

With Spring Data JPA, constructing `Page<T>` typically requires knowing the total number of matching records. Alongside the data query, the repository may run an extra count query to compute `totalElements`, from which `totalPages` is derived.

Query example:

~~~java
Page<Product> findPageByStatus(
    ProductStatus status,
    Pageable pageable
);
~~~

Conceptual SQL equivalent:

~~~sql
SELECT id, name, price
FROM products
WHERE status = ?
ORDER BY created_at DESC
LIMIT ? OFFSET ?;

SELECT COUNT(*)
FROM products
WHERE status = ?;
~~~

This illustrates the two kinds of work, not a guarantee that Spring Data always emits exactly two SQL statements in every scenario. The framework can optimize or skip the count query when totals can be inferred from results and query metadata. Still, when an exact total is required, the count query is often a significant cost—especially with complex filters, multi-table joins, or large datasets.

### When Is Total-Count Cost Justified?

Choose Page when clients genuinely need to:

- Display total result count, e.g., "12,450 products found".
- Display page numbers and allow jumping directly to any page.
- Build reports requiring exact totals at query time.
- Show progress through the full result set by page number.

If the client only needs a "Load more" or "Next" button, computing totals may be unnecessary overhead. In that case, consider Slice.

## 3. Slice<T>: When You Only Need to Know If More Data Follows

`Slice<T>` provides the current contents and navigation information without requiring total item count. Common methods:

| Method | Meaning |
|---|---|
| `getContent()` | List of items in the current slice |
| `getNumber()` | Current slice index |
| `getSize()` | Requested size |
| `getNumberOfElements()` | Actual number of items |
| `isFirst()` / `isLast()` | Whether this is the first/last slice |
| `hasNext()` / `hasPrevious()` | Whether a next/previous slice exists |
| `nextPageable()` / `previousPageable()` | Pageable for the next/previous slice |
| `isEmpty()` | Current slice has no items |

Slice does not have `getTotalElements()` or `getTotalPages()`. That is intentional: clients navigate onward using `hasNext()` instead of needing the full dataset size upfront.

### Why Does Slice Usually Avoid a Count Query?

For standard paginated queries, Spring Data JPA can fetch one item more than the requested size to determine whether more data remains. For example, if the client requests 20 items, the query can fetch up to 21 rows:

- If 21 rows return, the framework keeps 20 items and sets `hasNext=true`.
- If at most 20 rows return, no next item exists and `hasNext=false`.

Exact execution depends on the Spring Data module and query type. The purpose of Slice is avoiding a total-record count just to know whether a next page exists.

Repository example:

~~~java
Slice<Product> findSliceByStatus(
    ProductStatus status,
    Pageable pageable
);
~~~

Slice is well suited for:

- Activity feeds or latest event lists.
- Infinite scroll lists.
- "Load more" screens that do not show total counts.
- Large datasets where a count query is expensive and adds no user value.

If the UI requires "Page 4 of 12" or jumping to the last page, Slice does not provide enough data. Never try to infer totals from `hasNext()`; use Page or another pagination contract that includes total counts.

## 4. Comparing Page and Slice

| Criterion | Page<T> | Slice<T> |
|---|---|---|
| Current page content | Yes | Yes |
| Page index and size | Yes | Yes |
| Total elements | Yes | No |
| Total pages | Yes | No |
| Has next slice | Yes | Yes |
| Count query | Usually needed to determine total | Usually not needed |
| Jump to arbitrary page | Better suited | Lacks total info to support fully |
| "Load more" | Usable, but carries extra metadata | Well suited |
| Query cost | Can be higher due to count | Typically lower when count is expensive |

A practical rule of thumb:

- Use Page when total result count is part of the business or UX requirement.
- Use Slice when clients only need to know whether they can load more.
- Use cursor pagination when data changes continuously, cursor navigation is needed, or deep offsets become expensive.

Do not pick Slice merely assuming it is always faster. The main data query can still be heavy due to joins, sorting, filtering, or large offsets. Slice only eliminates the requirement to compute totals; it does not automatically optimize every part of the query.

## 5. Why Should the API Own Its Pagination DTO?

Returning `Page<T>` or `Slice<T>` directly can be convenient early on:

~~~java
@GetMapping
public Page<ProductResponse> list(Pageable pageable) {
    return productService.findAll(pageable);
}
~~~

However, Spring Data's return types are library abstractions. Serializing implementations like PageImpl directly can expose internal details in JSON and change across versions. Clients then depend on a library-generated structure rather than an application-defined contract.

An application-owned pagination DTO helps:

- Keep property names clear and stable.
- Expose only the metadata clients actually need.
- Hide Spring Data implementation details.
- Standardize structure across multiple endpoints.
- Keep OpenAPI schemas decoupled from repository implementations.
- Swap Page for Slice or another data source without forcing unintended client contract changes.

Example of an application-controlled response:

~~~json
{
  "items": [
    {
      "id": 42,
      "name": "Mechanical keyboard"
    }
  ],
  "page": {
    "number": 0,
    "size": 20,
    "numberOfElements": 1,
    "totalElements": 57,
    "totalPages": 3,
    "first": true,
    "last": false
  }
}
~~~

The names `items` and `page` are application contract choices. You can use `content`, `metadata`, or other names, as long as they are consistent and accurately documented in OpenAPI.

## 6. Designing a DTO for Page Responses

For endpoints needing total counts, define dedicated metadata:

~~~java
public record PageMetadata(
    int number,
    int size,
    int numberOfElements,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last,
    boolean empty
) {}

public record ProductPageResponse(
    List<ProductResponse> items,
    PageMetadata page
) {}
~~~

Meaning of each field:

| Field | Meaning |
|---|---|
| `items` | Items on the current page |
| `number` | Current page index, typically starting from 0 |
| `size` | Effective page size |
| `numberOfElements` | Actual number of items in `items` |
| `totalElements` | Total number of items matching the query |
| `totalPages` | Total number of pages |
| `first` | Whether the current page is the first page |
| `last` | Whether the current page is the last page |
| `empty` | Whether the current page has no items |

Do not mechanically copy every property of Page into the DTO. For example, if clients do not need internal `sort`, `pageable`, or offset, omit them. Metadata is part of the contract and should have stable meaning for clients.

### Converting Page to DTO

A mapper can convert Page<ProductResponse> into ProductPageResponse:

~~~java
private ProductPageResponse toPageResponse(Page<ProductResponse> result) {
    PageMetadata metadata = new PageMetadata(
        result.getNumber(),
        result.getSize(),
        result.getNumberOfElements(),
        result.getTotalElements(),
        result.getTotalPages(),
        result.isFirst(),
        result.isLast(),
        result.isEmpty()
    );

    return new ProductPageResponse(result.getContent(), metadata);
}
~~~

Here `size` comes from the Page created after applying Pageable. If the application enforces page size caps, the metadata should reflect the actual size applied by the server.

## 7. Designing a DTO for Slice Responses

Slice has no totals, so do not reuse PageMetadata and fill `totalElements` and `totalPages` with `0` or `null`. Those values can mislead clients into thinking the system computed totals and found zero results.

Define metadata that accurately reflects Slice semantics:

~~~java
public record SliceMetadata(
    int number,
    int size,
    int numberOfElements,
    boolean first,
    boolean last,
    boolean hasNext,
    boolean hasPrevious,
    boolean empty
) {}

public record ProductSliceResponse(
    List<ProductResponse> items,
    SliceMetadata slice
) {}
~~~

Example response:

~~~json
{
  "items": [
    {
      "id": 42,
      "name": "Mechanical keyboard"
    }
  ],
  "slice": {
    "number": 0,
    "size": 20,
    "numberOfElements": 1,
    "first": true,
    "last": false,
    "hasNext": true,
    "hasPrevious": false,
    "empty": false
  }
}
~~~

Clients can use `hasNext` to decide whether to show a "Load more" button. Without `totalPages`, clients cannot show "Page 1 of N" unless they call another API for the total count.

### Converting Slice to DTO

~~~java
private ProductSliceResponse toSliceResponse(Slice<ProductResponse> result) {
    SliceMetadata metadata = new SliceMetadata(
        result.getNumber(),
        result.getSize(),
        result.getNumberOfElements(),
        result.isFirst(),
        result.isLast(),
        result.hasNext(),
        result.hasPrevious(),
        result.isEmpty()
    );

    return new ProductSliceResponse(result.getContent(), metadata);
}
~~~

`isLast()` and `hasNext()` express two sides of the same navigation state in Slice. Keep both in the DTO if clients find them useful; if you prefer a leaner schema, you can expose only `hasNext` and `hasPrevious`.

## 8. Reusing Mappers with Page.map() and Slice.map()

Typically, repositories return entities while the API needs response DTOs. You do not need to loop through content and manually recompute metadata. Both Page and Slice have a `map()` method to transform each element while preserving pagination info:

~~~java
Page<Product> entities = productRepository.findPageByStatus(status, pageable);
Page<ProductResponse> responsePage = entities.map(ProductResponse::from);
~~~

With Slice:

~~~java
Slice<Product> entities = productRepository.findSliceByStatus(status, pageable);
Slice<ProductResponse> responseSlice = entities.map(ProductResponse::from);
~~~

Example DTO:

~~~java
public record ProductResponse(
    Long id,
    String name,
    BigDecimal price
) {
    public static ProductResponse from(Product product) {
        return new ProductResponse(
            product.getId(),
            product.getName(),
            product.getPrice()
        );
    }
}
~~~

After mapping, `Page` preserves total count, page number, and first/last state; `Slice` preserves hasNext/hasPrevious. This avoids the common bug of extracting `getContent()` and building metadata by counting the current list.

Never compute `totalElements` from `items.size()`: that is only the item count on the current page. Likewise, do not infer `hasNext` by comparing `items.size()` to page size after mapping when you already have Slice metadata.

## 9. Structuring Service and Controller for Page

The repository can return a Page of entities:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {
    Page<Product> findPageByStatus(ProductStatus status, Pageable pageable);
}
~~~

The service handles querying and can map entities to DTOs:

~~~java
public Page<ProductResponse> findPage(
        ProductStatus status,
        Pageable pageable) {

    return productRepository
        .findPageByStatus(status, pageable)
        .map(ProductResponse::from);
}
~~~

The controller converts the DTO Page into an application-owned response DTO:

~~~java
@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping("/page")
    public ProductPageResponse findPage(
            @ParameterObject
            @PageableDefault(
                size = 20,
                sort = "createdAt",
                direction = Sort.Direction.DESC
            )
            Pageable pageable) {

        Page<ProductResponse> result =
            productService.findPage(ProductStatus.ACTIVE, pageable);

        return toPageResponse(result);
    }
}
~~~

In this example, the repository/service owns the query; the controller exposes the public DTO. The response DTO does not expose `PageImpl`, `Pageable`, or Spring Data internals.

## 10. Structuring Service and Controller for Slice

If a screen only needs "load more", declare the repository to return Slice:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {
    Slice<Product> findSliceByStatus(ProductStatus status, Pageable pageable);
}
~~~

Service:

~~~java
public Slice<ProductResponse> findSlice(
        ProductStatus status,
        Pageable pageable) {

    return productRepository
        .findSliceByStatus(status, pageable)
        .map(ProductResponse::from);
}
~~~

Controller:

~~~java
@GetMapping("/feed")
public ProductSliceResponse feed(
        @ParameterObject
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        )
        Pageable pageable) {

    Slice<ProductResponse> result =
        productService.findSlice(ProductStatus.ACTIVE, pageable);

    return toSliceResponse(result);
}
~~~

This API returns `hasNext` and `hasPrevious` metadata in `slice`, without returning `totalElements` or `totalPages`. Clients can request the next page after receiving the current response. If the server caps size, the DTO should reflect the applied size.

### Do Not Convert Page to Slice After Querying

If the repository queries a Page and runs a count query, and then the controller drops total metadata to return a Slice DTO, the count cost has already been paid. To avoid the count, declare the repository method to return `Slice<T>` from the start. Changing only the response DTO does not change the repository's query strategy.

## 11. Exposing Pageable as Query Parameters

Spring Data typically accepts pagination via query parameters:

~~~http
GET /api/products/page?page=0&size=20&sort=createdAt,desc
~~~

| Parameter | Meaning | Example value |
|---|---|---|
| `page` | Zero-based page index | `0` |
| `size` | Maximum items per page | `20` |
| `sort` | Property name and sort direction | `createdAt,desc` |

`sort` can be repeated to sort by multiple criteria:

~~~http
GET /api/products/page?page=0&size=20&sort=createdAt,desc&sort=name,asc
~~~

Springdoc provides `@ParameterObject` to expand the Pageable object into query parameters in OpenAPI:

~~~java
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;

@GetMapping("/page")
public ProductPageResponse findPage(
        @ParameterObject
        @PageableDefault(
            size = 20,
            sort = "createdAt",
            direction = Sort.Direction.DESC
        )
        Pageable pageable) {
    // ...
}
~~~

`@PageableDefault` sets default values when the client omits parameters. `@ParameterObject` helps documentation render Pageable's fields rather than an opaque parameter object. The import above applies to modern springdoc versions; use the exact package for your project's dependency.

### Explicit Parameter Documentation

If you do not want documentation to rely on how springdoc infers Pageable, you can declare the parameters explicitly:

~~~yaml
parameters:
  - name: page
    in: query
    description: Page index, starting from 0
    schema:
      type: integer
      minimum: 0
      default: 0
  - name: size
    in: query
    description: Maximum number of items per page
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
  - name: sort
    in: query
    description: Can be repeated to specify multiple sorting criteria
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

With `style: form` and `explode: true`, each sort criterion is sent as a repeated query parameter. The documentation must match how Spring Data actually parses incoming requests.

## 12. Designing OpenAPI Schemas for Page DTOs

The Page response schema can be described using components:

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
          example: 0
        size:
          type: integer
          minimum: 1
          example: 20
        numberOfElements:
          type: integer
          example: 20
        totalElements:
          type: integer
          format: int64
          example: 57
        totalPages:
          type: integer
          example: 3
        first:
          type: boolean
        last:
          type: boolean
        empty:
          type: boolean
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

Operation referencing the response:

~~~yaml
paths:
  /api/products/page:
    get:
      summary: Get products by page
      parameters:
        - name: page
          in: query
          schema:
            type: integer
            minimum: 0
            default: 0
        - name: size
          in: query
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
      responses:
        '200':
          description: Page of products
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductPageResponse'
~~~

There is no need to expose every property of Page if the DTO only carries a subset of metadata. OpenAPI must describe exactly what the JSON actually returns.

## 13. Designing OpenAPI Schemas for Slice DTOs

Slice responses have no total count. The schema should clearly expose navigation properties:

~~~yaml
components:
  schemas:
    SliceMetadata:
      type: object
      required:
        - number
        - size
        - hasNext
        - hasPrevious
      properties:
        number:
          type: integer
          minimum: 0
        size:
          type: integer
          minimum: 1
        numberOfElements:
          type: integer
        first:
          type: boolean
        last:
          type: boolean
        hasNext:
          type: boolean
        hasPrevious:
          type: boolean
        empty:
          type: boolean
    ProductSliceResponse:
      type: object
      required:
        - items
        - slice
      properties:
        items:
          type: array
          items:
            $ref: '#/components/schemas/ProductResponse'
        slice:
          $ref: '#/components/schemas/SliceMetadata'
~~~

Operation:

~~~yaml
paths:
  /api/products/feed:
    get:
      summary: Get next slice of products
      responses:
        '200':
          description: Slice of products with navigation status
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductSliceResponse'
~~~

Never add `totalElements: 0` or `totalPages: 0` to SliceMetadata just to make the two DTOs look alike. `0` is a known total value, whereas Slice never computes a total. If you want schema reuse, share only the metadata that genuinely has the same semantics; do not force nonexistent fields into the contract.

## 14. Springdoc Annotations for Pagination DTOs

For Java DTOs, springdoc typically infers objects, arrays, and properties from record/class types:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;

@Schema(name = "PageMetadata", description = "Summary metadata of the page")
public record PageMetadata(
    @Schema(description = "Zero-based page index", example = "0")
    int number,
    @Schema(description = "Effective page size", example = "20")
    int size,
    int numberOfElements,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last,
    boolean empty
) {}

@Schema(name = "ProductPageResponse")
public record ProductPageResponse(
    List<ProductResponse> items,
    PageMetadata page
) {}
~~~

The controller can describe the response explicitly:

~~~java
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;
import org.springframework.http.MediaType;
import org.springframework.web.bind.annotation.GetMapping;

@GetMapping("/page")
@ApiResponse(
    responseCode = "200",
    description = "Page of products",
    content = @Content(
        mediaType = MediaType.APPLICATION_JSON_VALUE,
        schema = @Schema(implementation = ProductPageResponse.class)
    )
)
public ProductPageResponse findPage(
        @ParameterObject Pageable pageable) {
    // ...
}
~~~

These annotations generate documentation metadata. They do not convert Page to a DTO and do not perform pagination. Mapping must happen in the service or controller before returning the response.

If a generic DTO like `PageResponse<T>` is reused across multiple element types, check the component names and `$ref` targets generated by your springdoc/swagger-core version. For critical public contracts, concrete DTOs like ProductPageResponse and ProductSliceResponse generally yield clearer and more stable schemas.

## 15. Limiting Page Size and Controlling Sort

Clients should not be allowed to request arbitrary page sizes. A request like `size=1000000` can cause heavy queries, exhaust memory, and bloat responses. Define:

- Default value of size.
- Minimum and maximum page size.
- How negative page or zero size is handled.
- List of allowed sort fields.
- Default sort direction.
- Whether multiple sort criteria are allowed.

Value normalization example:

~~~java
int effectivePage = Math.max(page, 0);
int effectiveSize = Math.min(Math.max(size, 1), 100);

Pageable pageable = PageRequest.of(
    effectivePage,
    effectiveSize,
    Sort.by(Sort.Direction.DESC, "createdAt")
);
~~~

This snippet illustrates clamping page to non-negative and size to the range 1 to 100. Another API might choose to return a 400 error instead of silently normalizing values; what matters is consistent behavior documented in OpenAPI.

If clients can supply sort, map public field names through an allowlist:

~~~java
private static final Set<String> ALLOWED_SORTS =
    Set.of("name", "createdAt", "price");

private Sort toSort(String field, String direction) {
    if (!ALLOWED_SORTS.contains(field)) {
        throw new IllegalArgumentException(
            "Unsupported sort field"
        );
    }

    Sort.Direction sortDirection = Sort.Direction.fromString(direction);
    return Sort.by(sortDirection, field);
}
~~~

Never concatenate client sort strings directly into SQL or JPQL. Use Spring Data Sort/Pageable with an allowlist of fields; if public names need mapping to internal property names, perform that mapping on the server.

If the controller uses Bean Validation on method parameters like `@Min` and `@Max`, configure method validation appropriately for your Spring Boot version, such as placing `@Validated` on the controller and constraints on parameters. Whether using validation or normalization, documentation must accurately reflect how invalid or out-of-bounds page/size values behave.

## 16. Empty Pages, Last Pages, and Changing Data

Edge cases need clear definitions:

| Scenario | Page response | Slice response |
|---|---|---|
| Results on first page | `200`, `first=true` | `200`, `first=true` |
| Middle page | `200`, `first=false`, `last=false` | `200`, `hasNext=true` if more data exists |
| Last page | `200`, `last=true` | `200`, `hasNext=false`, `last=true` |
| No matching records | `items=[]`, `totalElements=0`, `totalPages=0` | `items=[]`, `empty=true`, `hasNext=false` |
| Requested page beyond last page | Usually returns `200` with `items=[]` and query totals | Usually returns `200` with `items=[]`, `hasNext=false` |

For collection endpoints, returning an empty page is usually easier to handle than returning 404, because the collection endpoint still exists even when no items fall at the requested position. An API may adopt a different policy for out-of-range pages, provided it is consistent and clearly documented.

### Page Size vs. Actual Element Count

`size` is the effective page size; `numberOfElements` is the actual count of items on the page. The last page may hold only a few items even if size is 20. Never set `size = numberOfElements`, because the two fields have different meanings.

### Stable Sorting

With offset pagination, use a deterministic sort order. If multiple records share the same `createdAt`, add a unique key like `id` as a secondary criterion. Otherwise, records can swap positions across pages if the database returns tied rows in an unspecified order.

Example:

~~~java
Sort sort = Sort.by(
    Sort.Order.desc("createdAt"),
    Sort.Order.desc("id")
);
Pageable pageable = PageRequest.of(page, size, sort);
~~~

### Data Mutating Between Requests

With offset pagination, if new records are inserted or deleted before the current offset, clients can see duplicate or skipped items when moving between pages. This is an inherent property of positional pagination over changing datasets. If stable traversal of a large stream is required, consider cursor pagination or snapshot semantics.

## 17. Page, Slice, and Cursor Pagination

Spring Data's Page and Slice typically rely on page numbers and offsets. Cursor pagination is a different model: clients send a server-issued cursor to resume from a prior position.

Example cursor response:

~~~json
{
  "items": [
    {
      "id": 42,
      "name": "Mechanical keyboard"
    }
  ],
  "continuation": {
    "nextCursor": "eyJjcmVhdGVkQXQiOiIyMDI2LTExLTIwIn0",
    "hasNext": true
  }
}
~~~

Next request:

~~~http
GET /api/products/feed?cursor=eyJjcmVhdGVkQXQiOiIyMDI2LTExLTIwIn0&limit=20
~~~

Cursors should be generated and validated on the server; never let clients forge offsets or internal keys. With cursor pagination, `totalElements` and `totalPages` are usually omitted; computing totals can be expensive and unnecessary for infinite-scroll streams.

| Criterion | Page | Slice | Cursor |
|---|---|---|---|
| Position | Page number/offset | Page number/offset | Continuation token |
| Total count | Yes | No | Usually no |
| Knows if more exists | Yes | Yes | Yes via continuation metadata |
| Jump to arbitrary page | Possible | Lacks totals to support fully | Usually no |
| Mutating data | Items can shift | Items can shift | More stable if cursor uses proper sort keys |
| Best suited for | Data tables needing totals | Paginated "load more" | Large feeds, infinite scroll |

Do not name the parameter `page` for a cursor when its semantics are actually a continuation token. Naming parameters `cursor` and `limit` helps clients understand how navigation works.

## 18. Testing Mappers and Response DTOs

Test mappers independently to verify metadata is transferred accurately. Example for Page:

~~~java
@Test
void mapsPageMetadataWithoutLosingTotalCount() {
    Pageable pageable = PageRequest.of(0, 20);
    Page<ProductResponse> source = new PageImpl<>(
        List.of(new ProductResponse(42L, "Mechanical keyboard", new BigDecimal("1250000"))),
        pageable,
        57
    );

    ProductPageResponse response = mapper.toPageResponse(source);

    assertEquals(0, response.page().number());
    assertEquals(20, response.page().size());
    assertEquals(1, response.page().numberOfElements());
    assertEquals(57, response.page().totalElements());
    assertEquals(3, response.page().totalPages());
    assertTrue(response.page().first());
    assertFalse(response.page().last());
}
~~~

With Slice:

~~~java
@Test
void mapsSliceNavigationWithoutInventingTotals() {
    Pageable pageable = PageRequest.of(0, 20);
    Slice<ProductResponse> source = new SliceImpl<>(
        List.of(new ProductResponse(42L, "Mechanical keyboard", new BigDecimal("1250000"))),
        pageable,
        true
    );

    ProductSliceResponse response = mapper.toSliceResponse(source);

    assertEquals(0, response.slice().number());
    assertEquals(20, response.slice().size());
    assertTrue(response.slice().hasNext());
    assertFalse(response.slice().hasPrevious());
    assertFalse(response.slice().last());
}
~~~

These tests assume a mapper and DTOs matching the earlier examples. `PageImpl` and `SliceImpl` are useful in unit tests for building sample data; they are not public API response types.

## 19. Testing Endpoints and OpenAPI Schemas

MockMvc can verify the Page endpoint's response DTO:

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.test.web.servlet.MockMvc;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.BDDMockito.given;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(ProductController.class)
class ProductControllerTest {

    @Autowired
    MockMvc mockMvc;

    @MockBean
    ProductService productService;

    @Test
    void returnsApplicationOwnedPageResponse() throws Exception {
        Page<ProductResponse> page = new PageImpl<>(
            List.of(new ProductResponse(
                42L, "Mechanical keyboard", new BigDecimal("1250000")
            )),
            PageRequest.of(0, 20),
            57
        );
        given(productService.findPage(any(), any(Pageable.class)))
            .willReturn(page);

        mockMvc.perform(get("/api/products/page")
                .param("page", "0")
                .param("size", "20"))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.items[0].id").value(42))
            .andExpect(jsonPath("$.page.totalElements").value(57))
            .andExpect(jsonPath("$.page.totalPages").value(3));
    }
}
~~~

In this example, the service returns Page<ProductResponse> as in the controller shown earlier; the controller invokes the mapper to produce ProductPageResponse before serialization. If your project places the mapper in the service, adjust the return type and mock to match that boundary.

You can verify the OpenAPI schema:

~~~java
mockMvc.perform(get("/v3/api-docs"))
    .andExpect(status().isOk())
    .andExpect(jsonPath(
        "$.components.schemas.ProductPageResponse.properties.items.type"
    ).value("array"))
    .andExpect(jsonPath(
        "$.components.schemas.ProductPageResponse.properties.page['$ref']"
    ).exists())
    .andExpect(jsonPath(
        "$.components.schemas.PageMetadata.properties.totalElements.type"
    ).value("integer"));
~~~

For Slice, verify `ProductSliceResponse` has `items` as an array and `slice.hasNext` as a boolean; the schema should not contain `totalElements` or `totalPages`. If springdoc names components differently due to configuration, follow the actual `$ref` in `/v3/api-docs` and update the JSONPath.

## 20. Common Issues and Fixes

| Symptom | Cause | Fix |
|---|---|---|
| Slice DTO still has total count | Reused PageMetadata or queried Page and dropped fields | Use a Slice repository method and dedicated SliceMetadata |
| Using Page but total count is wrong | Count query does not apply the same filters or metadata mapping is wrong | Inspect query conditions and total count source |
| Clients cannot tell if a next page exists | Slice response lacks hasNext | Publish hasNext/hasPrevious in SliceMetadata |
| Public response changes after Spring Data upgrade | Serializing PageImpl/SliceImpl directly | Switch to an application-owned DTO |
| Total elements equals current page item count | Setting totalElements from items.size() | Use Page.getTotalElements() |
| Count query slows down the endpoint | Client does not need total count yet repository returns Page | Switch repository method to Slice if UX allows |
| Slice does not prevent heavy queries | Joins, sorting, or large offsets remain expensive | Optimize queries, indexes, sorting, and consider cursor |
| Page size is too large | No server-side cap | Set default, maximum, and validation |
| Sort exposes internal fields | Allowing arbitrary client property names | Use an allowlist and map public names |
| Pages contain duplicate or missing items | Unstable sort order or mutating data | Add a unique key as secondary sort; consider cursor |
| Schema lacks Page metadata | springdoc fails to recognize DTO or wrong response annotation | Check return type, component, and `$ref` in `/v3/api-docs` |

## 21. Guiding Principles for Pagination Contracts

When exposing Page or Slice over an API, apply these principles:

1. Choose Page when clients need total counts; choose Slice when they only need to know if more data follows.
2. Convert Spring Data results into public DTOs before serialization.
3. Use separate PageMetadata and SliceMetadata so total fields are never misrepresented.
4. Use `Page.map()` or `Slice.map()` to transform entities to DTOs while preserving metadata.
5. Publish page, size, and sort with clear defaults, bounds, and semantics.
6. Cap size and allow sorting only on supported public fields.
7. Use a deterministic sort order, typically adding a unique key as a secondary criterion.
8. Document response DTOs with concrete OpenAPI schemas and verify `$ref`s.
9. Test both runtime JSON and OpenAPI JSON.
10. Treat response structure changes as contract changes requiring compatibility checks.

## 22. Comprehensive Practice Exercise

Build a product search API with two navigation styles:

1. Create a repository method returning `Page<Product>` for an admin screen that needs total counts.
2. Create a repository method returning `Slice<Product>` for a feed that only needs "load more".
3. Convert entities to ProductResponse using `Page.map()` and `Slice.map()`.
4. Create ProductPageResponse with PageMetadata for the Page endpoint.
5. Create ProductSliceResponse with SliceMetadata for the Slice endpoint.
6. Write mappers preserving Page's total count and Slice's hasNext/hasPrevious.
7. Use `@ParameterObject` and `@PageableDefault` to describe Pageable, or declare page/size/sort explicitly.
8. Enforce a maximum size and allowlist sort fields.
9. Use springdoc to generate schemas for both response DTOs.
10. Write unit tests for the mappers using PageImpl and SliceImpl.
11. Write MockMvc tests for the first page, last page, empty page, and OpenAPI schemas.
12. Inspect SQL/query logs to confirm Page may issue a count query while Slice does not require total counts.
13. Compare UX requiring total counts against "load more" UX and justify the Page/Slice choice.

### Completion Criteria

- [ ] Page response has items with accurate totalElements and totalPages.
- [ ] Slice response has items with hasNext/hasPrevious and does not fabricate total counts.
- [ ] Public DTOs do not depend on PageImpl/SliceImpl serialization structures.
- [ ] Entity-to-DTO mapping preserves pagination metadata.
- [ ] Query parameters page, size, and sort are accurately documented in OpenAPI.
- [ ] Server caps page size and restricts sorting via an allowlist.
- [ ] OpenAPI schemas accurately describe ProductPageResponse and ProductSliceResponse.
- [ ] Tests verify mappers, JSON responses, and generated schemas.
- [ ] Page/Slice selection is justified by client requirements and query cost.

## Next Steps

After this lesson, combine Page/Slice DTOs with filtering, sorting, cursor pagination, and standardized error responses. When switching from Page to Slice or renaming metadata fields, assess client impact, update OpenAPI, and run contract tests before releasing.
