# Pageable, Sort, and How They Are Documented

Data lists often need to support pagination and sorting so clients do not have to load all records in a single call. In Spring Data, **Pageable** describes the page to retrieve, the page size, and the sort order; **Sort** describes one or more sorting criteria. Spring MVC converts query parameters into these objects before invoking the controller.

With springdoc-openapi, a Pageable parameter can be presented as individual query parameters so Swagger UI users know how to call the API. The **@ParameterObject** annotation helps Springdoc decompose a composite parameter into query parameters. The documentation also needs to explain the page numbering convention, default size, maximum limit, sort syntax, and paginated response structure.

## 1. Why Do List APIs Need Pagination?

An endpoint that returns all data may work fine when the record count is small. As data grows, large responses increase query time, payload size, and memory consumption on both the server and the client.

Pagination helps:

- Limit the number of records in each response.
- Reduce the amount of data transferred over the network.
- Allow clients to load data on demand.
- Combine with sorting so results have a deterministic order.
- Support table views, lists, and admin screens.

Example endpoint:

~~~http
GET /api/v1/products?page=0&size=20&sort=createdAt,desc
~~~

This request asks for the first page, up to 20 products, sorted by creation timestamp descending. Spring Data converts the query parameters into a Pageable object for the service or repository to use.

## 2. What Is Pageable?

Pageable is a Spring Data interface that describes pagination information. It provides the following main properties:

| Property | Meaning |
|---|---|
| pageNumber | Page index |
| pageSize | Maximum number of items in a page |
| offset | Starting record position |
| sort | Sorting criteria |

With the default page numbering, the first page has index 0. If page=2 and size=20, the corresponding offset is 40, meaning the query starts from the 41st item in the sorted order.

In Spring MVC, a controller can accept Pageable directly:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/v1/products")
public class ProductController {

    private final ProductService productService;

    public ProductController(ProductService productService) {
        this.productService = productService;
    }

    @GetMapping
    public Page<ProductResponse> list(Pageable pageable) {
        return productService.findAll(pageable);
    }
}
~~~

Spring Data Web supports resolving Pageable from query parameters. In the common default configuration, the parameters are:

- page: page index, starting from 0.
- size: number of items requested in a page.
- sort: property and sort direction; can appear multiple times.

Pageable is a query parameter of the HTTP request. Clients do not need to send a JSON object with fields named pageNumber, pageSize, or sort in the request body.

## 3. @ParameterObject Helps Springdoc Display Pageable

If Pageable is left as a composite parameter without appropriate metadata, the documentation may not present the query parameters the way integrators expect. Springdoc provides @ParameterObject to decompose the object into individual parameters:

~~~java
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Pageable;

@GetMapping
public Page<ProductResponse> list(
    @ParameterObject Pageable pageable
) {
    return productService.findAll(pageable);
}
~~~

With standard Spring Data Web configuration, Swagger UI can display the page, size, and sort parameters. Users can enter query values directly instead of constructing a JSON object.

When using Springdoc 2.x in a Spring Boot 3 application, the annotation package is typically org.springdoc.core.annotations.ParameterObject. If the project uses another version, check the corresponding package and annotation API for the installed dependency.

### 3.1. Hiding Pageable from the Parameter List and Declaring Manually

In some cases, a project wants complete control over the names, descriptions, default values, or examples of the parameters. You can hide the Pageable parameter from the documentation and declare the public query parameters explicitly:

~~~java
import io.swagger.v3.oas.annotations.Parameter;
import io.swagger.v3.oas.annotations.Parameters;
import io.swagger.v3.oas.annotations.enums.ParameterIn;
import io.swagger.v3.oas.annotations.media.ArraySchema;
import io.swagger.v3.oas.annotations.media.Schema;
import org.springframework.data.domain.Pageable;

@GetMapping
@Parameters({
    @Parameter(
        name = "page",
        in = ParameterIn.QUERY,
        description = "Page index, starting from 0.",
        schema = @Schema(type = "integer", minimum = "0", defaultValue = "0")
    ),
    @Parameter(
        name = "size",
        in = ParameterIn.QUERY,
        description = "Maximum number of items per page.",
        schema = @Schema(type = "integer", minimum = "1", defaultValue = "20")
    ),
    @Parameter(
        name = "sort",
        in = ParameterIn.QUERY,
        description = "Property and sort direction, e.g., createdAt,desc.",
        array = @ArraySchema(schema = @Schema(type = "string"))
    )
})
public Page<ProductResponse> list(
    @Parameter(hidden = true) Pageable pageable
) {
    return productService.findAll(pageable);
}
~~~

This illustrates how to handle cases where parameter customization is needed. Verify that the documentation contains only one set of page, size, and sort to avoid both decomposing Pageable and declaring parameters manually, which would cause duplicate parameters.

When multiple endpoints share the same convention, you can reuse a composite annotation or configure an OpenAPI customizer instead of repeating metadata.

## 4. The page and size Query Parameters

### 4.1. page

page specifies the index of the page to retrieve. By Spring Data default, the index starts at 0:

~~~http
GET /api/v1/products?page=0
GET /api/v1/products?page=1
GET /api/v1/products?page=2
~~~

If a client sends a negative number, the resolver may normalize it to a valid value according to Spring Data's mechanism. However, the API should still publish a non-negative value range and may actively validate if it wants to return an explicit error instead of silently normalizing.

### 4.2. size

size specifies the maximum number of items in a page:

~~~http
GET /api/v1/products?size=10
GET /api/v1/products?size=50
~~~

Clients should not be allowed to request an unbounded size. An overly large size can cause heavy queries and huge responses. Configure a default value together with a maximum limit on the server, then document them.

Example Spring Boot configuration:

~~~yaml
spring:
  data:
    web:
      pageable:
        page-parameter: page
        size-parameter: size
        default-page-size: 20
        max-page-size: 100
        one-indexed-parameters: false
~~~

These properties adjust the parameter names, default size, maximum size, and page numbering convention. Parameter names and numbering changed here must be reflected consistently in OpenAPI, examples, and integration guides.

### 4.3. One-Based Page Numbering

Some APIs want the first page to be page=1 to match common UI expectations. You can enable:

~~~yaml
spring:
  data:
    web:
      pageable:
        one-indexed-parameters: true
~~~

When enabled, the resolver interprets the query parameter using a one-based convention. Distinguish between the index sent by the client and the internal index used by Pageable. Do not change only the examples in Swagger UI while forgetting to change the resolver at runtime.

## 5. Sort and Query Parameter Syntax

Sort is Spring Data's abstraction for describing sort order. A Sort can consist of multiple Order instances; each Order specifies a property, ascending/descending direction, and several other options.

Common query syntax:

~~~http
GET /api/v1/products?sort=name,asc
GET /api/v1/products?sort=createdAt,desc
GET /api/v1/products?sort=category,asc&sort=price,desc
~~~

Meaning:

- name,asc: sort by name ascending.
- createdAt,desc: sort by creation timestamp descending.
- Multiple sort parameters: create a multi-criteria priority order; the first criterion is applied first.

If only the property is provided without specifying a direction, Spring Data typically uses ASC. Clearly document the API's default behavior.

### 5.1. Default Sort Using @PageableDefault

You can set the default page size and sort directly on the controller parameter:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springdoc.core.annotations.ParameterObject;

@GetMapping
public Page<ProductResponse> list(
    @ParameterObject
    @PageableDefault(
        page = 0,
        size = 20,
        sort = "createdAt",
        direction = Sort.Direction.DESC
    )
    Pageable pageable
) {
    return productService.findAll(pageable);
}
~~~

When the client omits sort, Spring Data uses the declared default criterion. If the client sends sort, the client-provided value can replace the default order. Verify the resolver behavior and document it clearly in the API.

### 5.2. Multiple Default Sort Criteria

If multiple default criteria are needed, you can use @SortDefault:

~~~java
import org.springframework.data.domain.Sort;
import org.springframework.data.web.SortDefault;

@GetMapping
public Page<ProductResponse> list(
    @ParameterObject
    @SortDefault.SortDefaults({
        @SortDefault(
            sort = "createdAt",
            direction = Sort.Direction.DESC
        ),
        @SortDefault(
            sort = "name",
            direction = Sort.Direction.ASC
        )
    })
    Pageable pageable
) {
    return productService.findAll(pageable);
}
~~~

In this example, records are sorted by createdAt descending; if multiple records share the same creation timestamp, name ascending is used as the next criterion. A stable secondary criterion such as ID helps reduce order shifting across queries when multiple records have the same sort value.

### 5.3. Accepting Only Sort When Pagination Is Not Needed

An endpoint may only need to sort a business-bounded list without requiring page and size. Spring Data Web supports accepting Sort on its own:

~~~java
import java.util.List;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Sort;

@GetMapping("/featured")
public List<ProductResponse> featured(
    @ParameterObject Sort sort
) {
    return productService.findFeatured(sort);
}
~~~

In this case, the sort query parameter can still be repeated to pass multiple criteria. There is no page or size because the controller does not accept Pageable. Check the OpenAPI JSON to confirm Springdoc represents Sort as a query parameter matching what the resolver accepts.

## 6. Controlling Allowed Sort Properties

Clients should not be allowed to sort arbitrarily by any entity or database property. Some properties may be sensitive, unindexed, or cause expensive queries. Additionally, API field names do not necessarily match database column names.

Define a list of supported sort fields, for example:

| Query sort field | Business property |
|---|---|
| name | Product name |
| price | Selling price |
| createdAt | Creation timestamp |
| updatedAt | Update timestamp |

You can validate the sort list before calling the repository:

~~~java
private static final Set<String> ALLOWED_SORT_FIELDS = Set.of(
    "name",
    "price",
    "createdAt",
    "updatedAt"
);

private Pageable validateSort(Pageable pageable) {
    for (Sort.Order order : pageable.getSort()) {
        if (!ALLOWED_SORT_FIELDS.contains(order.getProperty())) {
            throw new InvalidSortFieldException(order.getProperty());
        }
    }
    return pageable;
}
~~~

The example requires importing java.util.Set, Sort, Pageable, and defining a custom exception. Error handling can return 400 Bad Request with code INVALID_SORT_FIELD. If mapping between API names and entity property names, convert through an allowlist rather than directly concatenating client-supplied strings into SQL statements.

## 7. Describing Pageable in OpenAPI

With @ParameterObject, Springdoc can generate query parameters from Pageable. Even so, the API author still needs to inspect the generated documentation:

~~~yaml
parameters:
  - name: page
    in: query
    description: Page index, starting from 0.
    required: false
    schema:
      type: integer
      minimum: 0
      default: 0
  - name: size
    in: query
    description: Maximum number of items per page; default 20, max 100.
    required: false
    schema:
      type: integer
      minimum: 1
      maximum: 100
      default: 20
  - name: sort
    in: query
    description: Can be repeated to specify multiple criteria; e.g., createdAt,desc.
    required: false
    schema:
      type: array
      items:
        type: string
~~~

OpenAPI allows declaring sort as an array when a query parameter can be repeated. Query serialization must match the Spring Data resolver and client tools. If Swagger UI formats sort differently from what the server expects, customize parameter style/explode or provide accurate examples.

Do not assume Springdoc always knows every custom Pageable configuration in the application. When renaming page to pageNumber, size to limit, enabling one-based numbering, or using prefixes/qualifiers, inspect /v3/api-docs and adjust metadata accordingly if needed.

## 8. Customizing Parameter Names and Multiple Pageables

Spring Data Web allows configuring query parameter names and prefixes for Pageables distinguished by qualifiers. Example configuration:

~~~yaml
spring:
  data:
    web:
      pageable:
        page-parameter: page
        size-parameter: limit
        prefix: ""
        qualifier-delimiter: _
~~~

When multiple Pageable parameters appear in the same method, @Qualifier can be used to create separate parameter name groups:

~~~java
@GetMapping("/dashboard")
public DashboardResponse dashboard(
    @Qualifier("orders") Pageable ordersPageable,
    @Qualifier("customers") Pageable customersPageable
) {
    return dashboardService.load(ordersPageable, customersPageable);
}
~~~

With the _ delimiter, the parameter groups may look like orders_page, orders_limit, orders_sort and customers_page, customers_limit, customers_sort, depending on resolver configuration. This case requires closer inspection of the OpenAPI documentation because @ParameterObject and customizers may need prefix/qualifier support so displayed names match runtime behavior.

If an endpoint needs multiple paginated datasets, consider splitting it into multiple endpoints or creating dedicated request models if using multiple Pageables makes the contract hard to understand.

## 9. How Do Page, Slice, and List Differ?

Spring Data provides several query result types:

| Type | Contents | Metadata | Typical Cost |
|---|---|---|---|
| List<T> | List of records | No page metadata | Does not self-describe total pages |
| Slice<T> | A slice of data | Indicates whether a next page exists | Can avoid total count query |
| Page<T> | A page of data | Includes total elements and total pages | Usually requires a count query |

Page<T> fits when the UI needs to display total results or total pages. Slice<T> fits when the client only needs to know whether more data exists, such as a "Load more" button. List<T> fits when the API actively limits data or does not need pagination metadata.

Repository and service example:

~~~java
public interface ProductRepository extends JpaRepository<Product, Long> {
    Page<Product> findByActiveTrue(Pageable pageable);
}

public Page<ProductResponse> findAll(Pageable pageable) {
    return productRepository.findByActiveTrue(pageable)
        .map(productMapper::toResponse);
}
~~~

The map method preserves page metadata while converting each item from entity to DTO. Return public DTOs instead of directly returning persistence entities.

## 10. Paginated Response Structure

A Page object contains data and metadata such as:

- content: items of the current page.
- number: page index.
- size: page size.
- numberOfElements: actual number of items on the page.
- totalElements: total number of items matching the query.
- totalPages: total number of pages.
- first, last, empty: page state flags.
- sort: sorting information.

Illustrative response example:

~~~json
{
  "content": [
    {
      "id": 101,
      "name": "Mechanical keyboard",
      "price": 1250000
    },
    {
      "id": 102,
      "name": "Wireless mouse",
      "price": 450000
    }
  ],
  "number": 0,
  "size": 20,
  "numberOfElements": 2,
  "totalElements": 42,
  "totalPages": 3,
  "first": true,
  "last": false,
  "empty": false
}
~~~

This is a simplified response shape to explain the metadata. Actual JSON when directly serializing PageImpl may include additional properties such as pageable and sort, and the structure can vary across Spring Data versions. Do not rely on field ordering or the internal structure of PageImpl as a stable contract without verifying it.

## 11. Designing a Stable Paginated Response DTO

If you want full control over the JSON response, you can create a dedicated DTO:

~~~java
public record PageResponse<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last,
    boolean empty
) {
    public static <T> PageResponse<T> from(Page<T> source) {
        return new PageResponse<>(
            source.getContent(),
            source.getNumber(),
            source.getSize(),
            source.getTotalElements(),
            source.getTotalPages(),
            source.isFirst(),
            source.isLast(),
            source.isEmpty()
        );
    }
}
~~~

The controller can convert Page to the DTO:

~~~java
@GetMapping
public PageResponse<ProductResponse> list(
    @ParameterObject Pageable pageable
) {
    return PageResponse.from(productService.findAll(pageable));
}
~~~

With a dedicated DTO, the API can choose metadata names like page instead of number, limit exposed fields, and keep the response structure stable across Spring Data upgrades. Document the generic schema and corresponding examples in OpenAPI.

Another option is Spring HATEOAS PagedModel if the API wants to return navigation links such as self, next, prev, and page metadata in a hypermedia model. Choose one consistent format matching how clients consume the API.

## 12. Describing Page Responses in Springdoc

Springdoc can infer the response schema from a Page<ProductResponse> return type, though the final schema depends on the springdoc version, Spring Data, and serialization settings. With a dedicated DTO, the schema is usually clearer and easier to control.

You can describe the response DTO using annotations:

~~~java
@Schema(name = "ProductPageResponse")
public record ProductPageResponse(
    @Schema(description = "List of products on the current page.")
    List<ProductResponse> content,

    @Schema(description = "Page index, starting from 0.", example = "0")
    int page,

    @Schema(description = "Page size.", example = "20")
    int size,

    @Schema(description = "Total number of products matching the query.", example = "42")
    long totalElements,

    @Schema(description = "Total number of pages.", example = "3")
    int totalPages,

    boolean first,
    boolean last,
    boolean empty
) {
}
~~~

In a real project, ProductResponse needs to be defined and imported from the proper package. If using a generic PageResponse<T>, you can declare a concrete schema per operation using @Schema(implementation = ...) or configure the corresponding schema so client generators receive the concrete item type.

## 13. Combining Filtering with Pageable and Sort

A list API often combines multiple filter query parameters with Pageable:

~~~java
@GetMapping
public Page<ProductResponse> search(
    @RequestParam(required = false) String keyword,
    @RequestParam(required = false) BigDecimal minPrice,
    @RequestParam(required = false) BigDecimal maxPrice,
    @ParameterObject
    @PageableDefault(size = 20, sort = "createdAt",
                     direction = Sort.Direction.DESC)
    Pageable pageable
) {
    return productService.search(
        keyword, minPrice, maxPrice, pageable
    );
}
~~~

Example request:

~~~http
GET /api/v1/products?keyword=keyboard&minPrice=100000&maxPrice=2000000&page=0&size=20&sort=createdAt,desc
~~~

OpenAPI documentation needs to describe each filter query parameter along with the pagination/sorting parameters. Clearly state min/max combination rules, handling of invalid values, and the default sort behavior.

If the query has many conditions, business parameters can be grouped into a dedicated request model while Pageable is still typically passed as query parameters. Do not put Pageable inside a JSON request body if the endpoint uses standard Spring Data Web pagination.

## 14. Pagination Limits, Performance, and Stability

Offset/page-number pagination is easy to use, but it has several characteristics:

- When data changes between calls, records can shift across pages.
- Page usually needs to count total records to compute totalElements and totalPages.
- Pages with very large offsets can make database queries slow.
- Unstable sorting can cause records to be duplicated or skipped across pages.

To improve stability:

1. Cap the maximum size on the server.
2. Use deterministic sort criteria; add ID as a secondary criterion when needed.
3. Create appropriate indexes on commonly filtered and sorted fields.
4. Consider Slice if the total record count is not needed.
5. For very large or rapidly changing datasets, consider cursor/keyset pagination instead of offset pagination.

Cursor pagination typically requires a token or bookmark value to fetch the next slice of data. This is a different contract from standard Pageable; separately document the cursor, traversal direction, expiration, and behavior when a cursor is invalid.

## 15. Complete OpenAPI Documentation Example

The condensed example below describes a product list endpoint:

~~~yaml
paths:
  /api/v1/products:
    get:
      summary: Search products with pagination
      description: |
        Returns a list of products matching filter criteria and sort order.
        page starts at 0; size defaults to 20 and is capped at 100.
        sort can be repeated to specify multiple criteria.
      parameters:
        - name: keyword
          in: query
          required: false
          schema:
            type: string
        - name: page
          in: query
          required: false
          description: Page index, starting from 0.
          schema:
            type: integer
            minimum: 0
            default: 0
        - name: size
          in: query
          required: false
          description: Items per page, maximum 100.
          schema:
            type: integer
            minimum: 1
            maximum: 100
            default: 20
        - name: sort
          in: query
          required: false
          description: Can be repeated, e.g., sort=createdAt,desc.
          style: form
          explode: true
          schema:
            type: array
            items:
              type: string
      responses:
        '200':
          description: Page of product results.
          content:
            application/json:
              schema:
                $ref: '#/components/schemas/ProductPageResponse'
        '400':
          description: Invalid pagination, filter, or sort parameter.
components:
  schemas:
    ProductPageResponse:
      type: object
      properties:
        content:
          type: array
          items:
            $ref: '#/components/schemas/ProductResponse'
        page:
          type: integer
        size:
          type: integer
        totalElements:
          type: integer
          format: int64
        totalPages:
          type: integer
        first:
          type: boolean
        last:
          type: boolean
        empty:
          type: boolean
~~~

In a real specification, confirm that query array serialization for sort matches the Spring Data resolver. If the server expects repeated parameters like sort=name,asc&sort=price,desc, OpenAPI should describe appropriate serialization so Swagger UI and client generators build requests properly.

## 16. Verifying the Generated Documentation

After running the Spring Boot application, open the default OpenAPI endpoint:

~~~bash
curl -s http://localhost:8080/v3/api-docs
~~~

Find the list operation and check:

1. Whether the page, size, and sort query parameters are present.
2. Whether the data types and `in: query` location are accurate.
3. Whether default values match @PageableDefault and resolver configuration.
4. Whether size reflects the maximum limit enforced by the server.
5. Whether sort is repeatable and documents direction syntax.
6. Whether the response schema accurately reflects runtime JSON.
7. Whether other filter parameters document value ranges and error behavior.

Test directly in Swagger UI with the first page, next page, default size, maximum size, and multiple sort criteria. Whenever Pageable configuration changes, re-run verification because the old documentation may no longer match.

## 17. Common Pitfalls

| Mistake | Consequence | Fix |
|---|---|---|
| Not using @ParameterObject for Pageable | Swagger UI does not display page/size/sort properly | Add the annotation or declare query parameters manually |
| Documenting page starting from 1 while resolver uses 0 | Clients fetch the wrong page | Synchronize one-indexed-parameters and documentation |
| Not limiting size | Clients can request overly large responses | Configure max-page-size and publish the limit |
| Not documenting repeatable sort | Clients struggle to pass multiple sort criteria | Describe repeatable array/query parameter |
| Allowing arbitrary sorting by any field | Slow queries or exposure of internal properties | Use an allowlist of sort fields |
| Sort without a stable secondary criterion | Results across pages can shift | Add a secondary criterion such as ID |
| Returning PageImpl directly without checking JSON | Schema may depend on Spring Data version | Use a stable pagination DTO or verify serialization |
| Assuming @ParameterObject enforces size limits | Server does not enforce the documented limit | Configure actual resolver limits and validation |
| Documenting only query params without response metadata | Clients do not know how to paginate | Document content, totalElements, totalPages, or next cursor |

## 18. Key Takeaways

- Pageable contains page index, page size, offset, and Sort.
- Spring Data Web typically binds page, size, and sort from query parameters.
- @ParameterObject helps Springdoc decompose Pageable into separate query parameters.
- page starts at 0 by default; this convention can be changed, but the resolver and documentation must stay aligned.
- @PageableDefault and @SortDefault set default pagination/sorting values.
- sort can be repeated for multiple criteria; allowed sort fields should be restricted.
- Page<T> provides total elements and total pages; Slice<T> only needs to know whether more data exists; List<T> has no page metadata.
- A paginated response DTO keeps JSON stable and controls the schema.
- Always check /v3/api-docs and runtime responses to ensure documentation matches Spring Data configuration.

When building list APIs with Spring Data, treat Pageable and Sort as part of the HTTP contract. Clearly describe query parameters, defaults, limits, and sorting syntax using Springdoc, and choose a paginated response with a stable schema so clients can navigate data accurately.
