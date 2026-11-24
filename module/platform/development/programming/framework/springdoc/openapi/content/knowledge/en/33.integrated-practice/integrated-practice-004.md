# Documenting Pagination, Filtering, and Sorting APIs

A list API often needs to support multiple query capabilities at the same time: retrieving pages of data, limiting record counts, filtering by multiple criteria, and sorting by one or more fields. With Spring Boot, Spring Data Web provides Pageable to bind pagination/sorting parameters from the query string; springdoc-openapi can turn Pageable into query parameters displayed in OpenAPI and Swagger UI.

This hands-on exercise builds a book search API. Clients can search by keyword, category, price range, and stock status, while selecting page, size, and sort. The goal is to keep the OpenAPI contract aligned with how Spring MVC binds requests, how Spring Data constructs queries, and the shape of the returned JSON.

## 1. Objectives and target contract

After this exercise, you will be able to:

- Design query parameters for pagination, filtering, and sorting.
- Use Pageable and @PageableDefault in controllers.
- Use @ParameterObject so Springdoc documents Pageable and filter objects as individual query parameters.
- Use Specification to combine dynamic filter criteria.
- Enforce limits on page size and the list of allowed sort fields.
- Design a stable response envelope instead of letting the API depend directly on Spring Data's internal structure.
- Verify OpenAPI JSON, Swagger UI, and runtime behavior using integration tests.

Example contract:

| Group | Parameter | Meaning | Default |
| --- | --- | --- | --- |
| Filtering | keyword | Search in book title or author | No filter |
| Filtering | category | Filter by exact category | No filter |
| Filtering | minPrice | Minimum price, inclusive | No filter |
| Filtering | maxPrice | Maximum price, inclusive | No filter |
| Filtering | inStock | Include only in-stock or out-of-stock books | No filter |
| Pagination | page | Page index, starting from 0 | 0 |
| Pagination | size | Maximum number of records per page | 20 |
| Sorting | sort | Field and sort direction; parameter may repeat | createdAt desc, id desc |

Example request:

~~~http
GET /api/books?keyword=spring&category=backend&minPrice=100000&maxPrice=500000&inStock=true&page=0&size=20&sort=price,asc&sort=createdAt,desc
~~~

The request above searches for books matching the keyword spring, in the backend category, priced from 100,000 to 500,000, and in stock; results are returned as the first page with up to 20 records, sorted by price ascending and then creation date descending.

## 2. Distinguishing pagination, filtering, and sorting

The three parameter groups have distinct responsibilities:

| Group | Executed in | Effect |
| --- | --- | --- |
| Filtering | Specification, Criteria API, or repository query | Determines which records are selected |
| Sorting | Sort inside Pageable or ORDER BY | Determines record ordering |
| Pagination | PageRequest/Pageable and repository | Selects a slice of the result set |

The logical processing order is filter first, then sort, and finally paginate. If you paginate first and filter afterward in Java, results may omit matching records and totalElements metadata will no longer be accurate.

For example, if there are 1,000 books but only 80 belong to the backend category, the API must filter the 80 records first before paginating. Never fetch the first 20 records out of 1,000 and filter them in memory.

## 3. Spring Data Pageable query parameter conventions

Spring Data Web reads these parameters by default:

| Parameter | Meaning | Example |
| --- | --- | --- |
| page | Page number, zero-based | page=0 |
| size | Number of elements per page | size=20 |
| sort | Field and sort direction | sort=price,asc |

The first page is page=0. The second page is page=1. With size=20, page 0 contains items 0–19 and page 1 contains items 20–39 of the filtered and sorted result set.

Multiple sort parameters can be sent to sort by multiple fields:

~~~text
?sort=price,asc&sort=createdAt,desc
~~~

Here, price is the primary sort criterion; createdAt is used when two records have the same price. If no sort is passed, the API uses the default order declared in the controller or application configuration.

## 4. Adding required dependencies

A Spring MVC application using Spring Data JPA and Springdoc v2 may need the following starters:

~~~xml
<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-web</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-data-jpa</artifactId>
</dependency>

<dependency>
    <groupId>org.springframework.boot</groupId>
    <artifactId>spring-boot-starter-validation</artifactId>
</dependency>

<dependency>
    <groupId>org.springdoc</groupId>
    <artifactId>springdoc-openapi-starter-webmvc-ui</artifactId>
    <version>2.x-compatible-version</version>
</dependency>
~~~

Replace the version placeholder with the Springdoc 2.x version compatible with your project's Spring Boot 3 version. If the application uses WebFlux, choose the corresponding webflux starter and appropriate repository/service implementation.

## 5. Configuring pagination limits

Parameter names, default size, and maximum size can be configured in application.yml:

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

Meaning:

- page-parameter and size-parameter keep query parameter names consistent with the contract.
- default-page-size sets the default number of items when the client does not send size.
- max-page-size caps the number of items a single request can ask for.
- one-indexed-parameters=false keeps the convention that the first page is 0.

Capping page size is important to prevent a client from requesting hundreds of thousands of records in one request. Resolver configuration acts as an input guard; the service should still enforce business limits if there are internal call paths or custom resolvers.

## 6. Creating the filter DTO

Do not accept the full entity as a query object. Create a DTO containing only the criteria allowed by the API:

~~~java
import io.swagger.v3.oas.annotations.media.Schema;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

@Schema(description = "Filter criteria for listing books")
public class BookSearchCriteria {

    @Size(max = 100)
    @Schema(description = "Search in title or author name", example = "spring")
    private String keyword;

    @Size(max = 50)
    @Schema(description = "Category code to filter by", example = "backend")
    private String category;

    @DecimalMin("0.00")
    @Schema(description = "Minimum price, inclusive", example = "100000")
    private BigDecimal minPrice;

    @DecimalMin("0.00")
    @Schema(description = "Maximum price, inclusive", example = "500000")
    private BigDecimal maxPrice;

    @Schema(description = "Return only in-stock books when true", example = "true")
    private Boolean inStock;

    public BookSearchCriteria() {}

    public String getKeyword() { return keyword; }
    public void setKeyword(String keyword) { this.keyword = keyword; }

    public String getCategory() { return category; }
    public void setCategory(String category) { this.category = category; }

    public BigDecimal getMinPrice() { return minPrice; }
    public void setMinPrice(BigDecimal minPrice) { this.minPrice = minPrice; }

    public BigDecimal getMaxPrice() { return maxPrice; }
    public void setMaxPrice(BigDecimal maxPrice) { this.maxPrice = maxPrice; }

    public Boolean getInStock() { return inStock; }
    public void setInStock(Boolean inStock) { this.inStock = inStock; }
}
~~~

Fields are nullable to indicate no filter condition is applied. Bean Validation checks keyword/category length and non-negative prices. The rule that minPrice must not exceed maxPrice is checked in the service or via a dedicated class-level validator. The DTO uses getX()-style getters so Springdoc can extract each field from @ParameterObject; a Java record only has component-named accessors, so bean-style getters would be needed if using a record here. Keep query DTOs flat because @ParameterObject does not automatically flatten nested parameter objects.

For query objects, use @ModelAttribute so Spring MVC binds query parameters into the DTO. @ParameterObject adds instructions for Springdoc to expand the object into individual parameters in OpenAPI:

~~~java
@Valid
@ModelAttribute
@ParameterObject
BookSearchCriteria criteria
~~~

@ParameterObject is an annotation for documentation purposes. It does not replace Spring MVC's binding mechanism.

## 7. Documenting Pageable with @ParameterObject

Springdoc supports Spring Data's Pageable. Placing @ParameterObject on a Pageable parameter documents the query parameters page, size, and sort instead of displaying a confusing Java object.

Example:

~~~java
@ParameterObject
@PageableDefault(
    page = 0,
    size = 20,
    sort = {"createdAt", "id"},
    direction = Sort.Direction.DESC
)
Pageable pageable
~~~

@PageableDefault defines runtime defaults for requests that omit page/size/sort. Springdoc can use this metadata to document defaults in OpenAPI. The official Springdoc FAQ confirms that Pageable is supported when combined with @ParameterObject and @PageableDefault.

If Pageable parameters are hidden from Swagger UI or the documentation only shows a single object, check that you imported the right org.springdoc.core.annotations.ParameterObject annotation and the Springdoc starter dependency. Do not use a similarly named annotation from another library.

## 8. Creating a repository supporting Specification and Pageable

The repository needs to support CRUD queries, Specification, and Pageable:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface BookRepository
        extends JpaRepository<Book, Long>,
                JpaSpecificationExecutor<Book> {
}
~~~

JpaSpecificationExecutor lets you call findAll(specification, pageable). Spring Data JPA applies filter conditions, sort order, and page limits in the database.

If the application uses custom SQL queries, declare an appropriate count query when returning Page<T>. Page needs the total record count to compute totalElements and totalPages; the count query can be a significant cost with complex joins.

## 9. Building a Specification from the filter

Specification lets you compose optional predicates without writing a repository method for every filter combination:

~~~java
import jakarta.persistence.criteria.Predicate;
import java.math.BigDecimal;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.util.StringUtils;

public final class BookSpecifications {

    private BookSpecifications() {}

    public static Specification<Book> from(BookSearchCriteria filter) {
        return (root, query, cb) -> {
            List<Predicate> predicates = new ArrayList<>();

            if (StringUtils.hasText(filter.getKeyword())) {
                String keyword = "%" + filter.getKeyword().trim().toLowerCase(Locale.ROOT) + "%";
                predicates.add(cb.or(
                    cb.like(cb.lower(root.<String>get("title")), keyword),
                    cb.like(cb.lower(root.<String>get("author")), keyword)
                ));
            }

            if (StringUtils.hasText(filter.getCategory())) {
                predicates.add(cb.equal(root.get("categoryCode"), filter.getCategory()));
            }

            if (filter.getMinPrice() != null) {
                predicates.add(
                    cb.greaterThanOrEqualTo(root.<BigDecimal>get("price"), filter.getMinPrice())
                );
            }

            if (filter.getMaxPrice() != null) {
                predicates.add(
                    cb.lessThanOrEqualTo(root.<BigDecimal>get("price"), filter.getMaxPrice())
                );
            }

            if (filter.getInStock() != null) {
                if (filter.getInStock()) {
                    predicates.add(cb.greaterThan(root.<Integer>get("stockQuantity"), 0));
                } else {
                    predicates.add(cb.equal(root.<Integer>get("stockQuantity"), 0));
                }
            }

            return cb.and(predicates.toArray(Predicate[]::new));
        };
    }
}
~~~

Each condition is added only when the client sends the corresponding value. With no filters, the predicate list is empty and the query returns all books within the user's access scope.

In a real application, decide clearly whether category is a code or display name, whether search is accent/case-sensitive, and whether inStock=false includes discontinued products or only items with zero stock.

## 10. Validating price range and input data

If minPrice is greater than maxPrice, the request makes no sense. You can validate this in the service:

~~~java
private void validateFilter(BookSearchCriteria filter) {
    if (filter.getMinPrice() != null
            && filter.getMaxPrice() != null
            && filter.getMinPrice().compareTo(filter.getMaxPrice()) > 0) {
        throw new ResponseStatusException(
            HttpStatus.BAD_REQUEST,
            "minPrice must be less than or equal to maxPrice"
        );
    }
}
~~~

Public error messages should be standardized and localizable. Never return stack traces, SQL statements, or internal entity details to the client.

## 11. Restricting allowed sort fields

Do not let clients sort arbitrarily on any entity attribute. Some properties lack indexes, involve expensive nested joins, or are not part of the API contract. Define an allowlist:

~~~java
private static final Set<String> ALLOWED_SORT_FIELDS = Set.of(
    "title",
    "price",
    "createdAt",
    "id"
);
~~~

The service validates each Sort.Order:

~~~java
private Sort validateSort(Sort requested) {
    List<Sort.Order> orders = new ArrayList<>();

    requested.forEach(order -> {
        if (!ALLOWED_SORT_FIELDS.contains(order.getProperty())) {
            throw new ResponseStatusException(
                HttpStatus.BAD_REQUEST,
                "Unsupported sort field: " + order.getProperty()
            );
        }
        orders.add(order);
    });

    if (orders.isEmpty()) {
        orders.add(Sort.Order.desc("createdAt"));
    }

    // Add a tie-breaker to keep ordering stable across pages.
    if (orders.stream().noneMatch(order -> order.getProperty().equals("id"))) {
        orders.add(Sort.Order.desc("id"));
    }

    return Sort.by(orders);
}
~~~

The sort allowlist must use property names understood by Spring Data JPA, not necessarily database column names. If the API exposes public names different from entity properties, map from the public name to the allowed property instead of passing client strings straight into queries.

A tie-breaker like id keeps ordering deterministic when multiple records share the same price or createdAt. Without a unique final criterion, a record could appear on two pages or be skipped if data changes between requests.

## 12. Creating a safe Pageable

Combine the validated sort with page size bounds:

~~~java
private Pageable normalizePageable(Pageable requested) {
    int page = Math.max(0, requested.getPageNumber());
    int size = Math.max(1, Math.min(requested.getPageSize(), 100));
    Sort sort = validateSort(requested.getSort());

    return PageRequest.of(page, size, sort);
}
~~~

Service-level bounds act as an extra safeguard alongside spring.data.web.pageable.max-page-size. For systems that must reject oversized requests rather than silently clamping them, use a custom PageableHandlerMethodArgumentResolver or validate inputs before the service runs and return a 400 error with a clear message.

An overly large page number can force the database to skip many rows when using offset pagination. Limiting size does not completely solve deep-page costs; monitor queries and consider keyset/cursor pagination as data grows.

## 13. Writing the service combining filter, sort, and page

The service orchestrates steps in the right order:

~~~java
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;

@Service
public class BookSearchService {

    private final BookRepository repository;

    public BookSearchService(BookRepository repository) {
        this.repository = repository;
    }

    public Page<Book> search(BookSearchCriteria filter, Pageable requested) {
        validateFilter(filter);
        Pageable pageable = normalizePageable(requested);
        return repository.findAll(BookSpecifications.from(filter), pageable);
    }
}
~~~

The validateFilter, normalizePageable, and validateSort methods are the ones built in previous sections. They can live inside the service class or be extracted into separate validators/policies if multiple APIs share the rules.

The service should not load all data itself and filter/sort using Java Streams. Let the database apply WHERE, ORDER BY, and LIMIT/OFFSET so only the needed slice is returned.

## 14. Designing a stable response envelope

Spring Data Page<T> contains content and pagination metadata. Returning Page directly is convenient, but the JSON structure of Page can depend on the Spring Data version and serialization configuration. If the API is a public contract, create your application's own response DTO:

~~~java
import java.util.List;
import org.springframework.data.domain.Page;

public record BookPageResponse(
    List<BookResponse> content,
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last,
    boolean hasNext,
    boolean hasPrevious
) {
    public static BookPageResponse from(Page<BookResponse> result) {
        return new BookPageResponse(
            result.getContent(),
            result.getNumber(),
            result.getSize(),
            result.getTotalElements(),
            result.getTotalPages(),
            result.isFirst(),
            result.isLast(),
            result.hasNext(),
            result.hasPrevious()
        );
    }
}
~~~

Example BookResponse:

~~~java
import java.math.BigDecimal;
import java.time.Instant;

public record BookResponse(
    Long id,
    String title,
    String author,
    String category,
    BigDecimal price,
    Instant createdAt,
    int stockQuantity
) {}
~~~

The controller converts Page<Book> into Page<BookResponse> using a mapper and wraps it in the envelope. The response DTO keeps the API structure stable even if Spring Data adds or changes internal metadata.

If the project intentionally adopts Spring Data's Page JSON, it can return Page<T> directly. In that case, inspect the OpenAPI schema and actual JSON after every Spring Data upgrade; never assume serialization structure is always immutable.

## 15. Declaring the controller and OpenAPI metadata

The controller uses @ParameterObject for both the filter and Pageable:

~~~java
import io.swagger.v3.oas.annotations.Operation;
import io.swagger.v3.oas.annotations.media.Content;
import io.swagger.v3.oas.annotations.media.Schema;
import io.swagger.v3.oas.annotations.responses.ApiResponse;
import io.swagger.v3.oas.annotations.responses.ApiResponses;
import jakarta.validation.Valid;
import org.springdoc.core.annotations.ParameterObject;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

// Book, BookResponse, BookPageResponse, BookMapper,
// BookSearchCriteria, and BookSearchService belong to the application package.

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookSearchService service;
    private final BookMapper mapper;

    public BookController(BookSearchService service, BookMapper mapper) {
        this.service = service;
        this.mapper = mapper;
    }

    @GetMapping
    @Operation(
        summary = "Search books",
        description = """
            Filter the list of books by keyword, category, price range, and stock.

            Pagination uses 0-based page and a maximum size of 100.
            Repeat sort to specify multiple criteria, for example
            sort=price,asc&sort=createdAt,desc.
            """
    )
    @ApiResponses({
        @ApiResponse(
            responseCode = "200",
            description = "List of books with pagination metadata",
            content = @Content(
                schema = @Schema(implementation = BookPageResponse.class)
            )
        ),
        @ApiResponse(
            responseCode = "400",
            description = "Invalid filter, page, size, or sort"
        )
    })
    public BookPageResponse search(
            @Valid
            @ModelAttribute
            @ParameterObject
            BookSearchCriteria filter,

            @ParameterObject
            @PageableDefault(
                page = 0,
                size = 20,
                sort = {"createdAt", "id"},
                direction = Sort.Direction.DESC
            )
            Pageable pageable) {

        Page<Book> books = service.search(filter, pageable);
        Page<BookResponse> responsePage = books.map(mapper::toResponse);
        return BookPageResponse.from(responsePage);
    }
}
~~~

The imports and classes Book, BookMapper, BookSearchService, and BookPageResponse belong in your application's packages. The example focuses on the contract; adjust the mapper and constructor to your actual project structure.

## 16. What does @ParameterObject do in the documentation?

Without @ParameterObject, Springdoc may document the filter/Pageable differently from how clients pass query strings. When the annotation is used properly:

- Properties of BookSearchCriteria become individual query parameters.
- Pageable is expanded into page, size, and sort.
- @PageableDefault supplies default page, size, and sort.
- @Schema on properties supplies descriptions, examples, and schema constraints.

Example expected document parameters:

~~~yaml
paths:
  /api/books:
    get:
      parameters:
        - name: keyword
          in: query
          required: false
          schema:
            type: string
            maxLength: 100
        - name: category
          in: query
          required: false
          schema:
            type: string
            maxLength: 50
        - name: minPrice
          in: query
          schema:
            type: number
        - name: maxPrice
          in: query
          schema:
            type: number
        - name: inStock
          in: query
          schema:
            type: boolean
        - name: page
          in: query
          schema:
            type: integer
            default: 0
        - name: size
          in: query
          schema:
            type: integer
            default: 20
            maximum: 100
        - name: sort
          in: query
          description: Parameter may be repeated to sort by multiple fields
          schema:
            type: array
            items:
              type: string
          style: form
          explode: true
~~~

This is an illustrative shape. The actual OpenAPI document depends on Springdoc, Spring Data, and the application's Pageable configuration. Open /v3/api-docs to check the exact names, schemas, defaults, and style/explode generated by your version.

## 17. Documenting the sort allowlist for clients

OpenAPI can describe sort as a string or an array of strings. If declaring sort manually instead of using the Pageable converter, you can put the description in Operation:

~~~java
@Operation(parameters = @Parameter(
    name = "sort",
    in = ParameterIn.QUERY,
    description = """
        Sort field using the syntax property,direction.
        Parameter may be repeated.
        Supported fields: title, price, createdAt, id.
        Direction: asc or desc.
        """
))
~~~

The snippet above requires importing Parameter and ParameterIn. Do not declare an extra explicit sort parameter if the Pageable converter already creates that parameter, as it can cause duplicate parameter names in the documentation. For controllers using the Pageable converter, prefer the Operation description or a customizer suitable for your Springdoc version without creating duplicate parameters.

The allowlist in the service is what enforces the rule. The OpenAPI description only informs clients of the rule; it does not prevent the server from receiving an invalid sort property.

## 18. Example requests and responses

Pagination-only request:

~~~http
GET /api/books?page=0&size=20
~~~

Filtering and multi-field sorting request:

~~~http
GET /api/books?keyword=spring&category=backend&minPrice=100000&maxPrice=500000&inStock=true&page=0&size=20&sort=price,asc&sort=createdAt,desc
~~~

Example response:

~~~json
{
  "content": [
    {
      "id": 42,
      "title": "Spring Boot in Practice",
      "author": "Nguyen An",
      "category": "backend",
      "price": 250000,
      "createdAt": "2026-01-12T09:30:00Z",
      "stockQuantity": 12
    }
  ],
  "page": 0,
  "size": 20,
  "totalElements": 1,
  "totalPages": 1,
  "first": true,
  "last": true,
  "hasNext": false,
  "hasPrevious": false
}
~~~

If no matching records exist, the API still returns HTTP 200 with content as an empty array and metadata reflecting the empty result. An empty list is not a 404 error.

## 19. Configuring custom query parameter names

Spring Data allows renaming page/size parameters via configuration:

~~~yaml
spring:
  data:
    web:
      pageable:
        page-parameter: pageNumber
        size-parameter: pageSize
~~~

Once renamed, the URL becomes:

~~~text
GET /api/books?pageNumber=0&pageSize=20
~~~

Springdoc must read the corresponding Spring Data configuration so the document reflects the new names. After changing properties, check OpenAPI JSON and test a real request. Never change only the @Operation description while the runtime resolver still uses the old names.

If using multiple Pageables in a single endpoint, you can use @Qualifier and a qualifier delimiter to separate parameter names, such as orders_page/orders_size and reviews_page/reviews_size. Check the generated document to confirm prefixes match the resolver.

## 20. One-based vs. zero-based pagination

Spring Data defaults to zero-based indexing: page=0 is the first page. You can enable one-indexed-parameters so the public API treats page=1 as the first page:

~~~yaml
spring:
  data:
    web:
      pageable:
        one-indexed-parameters: true
~~~

Enable this only when the API contract clearly agrees on it. Simultaneously check:

- Swagger UI displays default page as 1.
- A page=1 request returns the first set of records.
- Whether response metadata page is defined as the public page number or internal index.
- Whether next/previous links, if present, follow the same convention.

Do not subtract 1 manually in the controller if the resolver already performs one-indexed conversion, as that will shift pages off by one. For new APIs, zero-based is usually easier to align with PageRequest and Spring Data documentation.

## 21. Testing the OpenAPI document

Create an integration test that fetches /v3/api-docs and verifies the query parameters appear:

~~~java
@SpringBootTest
@AutoConfigureMockMvc
class BookOpenApiTest {

    @Autowired
    MockMvc mockMvc;

    @Autowired
    ObjectMapper objectMapper;

    @Test
    void documentsFilterAndPageableParameters() throws Exception {
        String json = mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk())
            .andReturn()
            .getResponse()
            .getContentAsString();

        JsonNode spec = objectMapper.readTree(json);
        JsonNode parameters = spec.at("/paths/~1api~1books/get/parameters");

        Set<String> names = StreamSupport.stream(parameters.spliterator(), false)
            .map(parameter -> parameter.path("name").asText())
            .collect(Collectors.toSet());

        assertThat(names).contains(
            "keyword", "category", "minPrice", "maxPrice",
            "inStock", "page", "size", "sort"
        );
    }
}
~~~

The test snippet needs imports for JsonNode, ObjectMapper, StreamSupport, Collectors, Set, AssertJ, and static MockMvcRequestBuilders.get. If Spring Security protects docs, supply an appropriate user/authority in the test.

You can extend the test to check the schema default:

~~~java
JsonNode pageParameter = StreamSupport.stream(parameters.spliterator(), false)
    .filter(parameter -> "page".equals(parameter.path("name").asText()))
    .findFirst()
    .orElseThrow();

assertThat(pageParameter.at("/schema/default").asInt()).isZero();
~~~

Because the parameter shape generated by Springdoc can vary across versions, verify the exact JSON Pointer in your actual document. If the sort parameter is represented as a string instead of an array, update the assertion and description to match.

## 22. Testing pagination and filtering behavior

Runtime tests must prove the server applies the filter and Pageable properly. Example with a mock service:

~~~java
@Test
void passesFilterAndPageableToService() throws Exception {
    mockMvc.perform(get("/api/books")
            .param("keyword", "spring")
            .param("category", "backend")
            .param("page", "1")
            .param("size", "10")
            .param("sort", "price,asc"))
        .andExpect(status().isOk());

    ArgumentCaptor<BookSearchCriteria> filterCaptor =
        ArgumentCaptor.forClass(BookSearchCriteria.class);
    ArgumentCaptor<Pageable> pageableCaptor =
        ArgumentCaptor.forClass(Pageable.class);

    verify(service).search(filterCaptor.capture(), pageableCaptor.capture());

    assertThat(filterCaptor.getValue().getKeyword()).isEqualTo("spring");
    assertThat(filterCaptor.getValue().getCategory()).isEqualTo("backend");
    assertThat(pageableCaptor.getValue().getPageNumber()).isEqualTo(1);
    assertThat(pageableCaptor.getValue().getPageSize()).isEqualTo(10);
    assertThat(pageableCaptor.getValue().getSort().getOrderFor("price").getDirection())
        .isEqualTo(Sort.Direction.ASC);
}
~~~

The test above assumes the controller uses a mock service and the mock's response is configured. For integration tests against a real database, also verify content, totalElements, and sort order after querying.

## 23. Checking edge cases

A list API should test at least these scenarios:

| Case | Expected result |
| --- | --- |
| No filter passed | Returns list within access scope |
| No page/size passed | Uses page=0, size=20 |
| size exceeds 100 | Clamped or returns 400 per published policy |
| Negative page | Resolver normalizes or returns 400 per policy |
| Unsupported sort field | Returns 400 |
| minPrice greater than maxPrice | Returns 400 |
| No results | 200 with empty content |
| Multiple records with same sort value | Tie-breaker keeps order deterministic |
| Filter with special characters | Binding and query parameter encoding handled properly |
| Data changes between two page loads | Client understands offset pagination may shift |

Do not write tests that only assert HTTP 200. Verify returned data, page metadata, and actual sort/filter conditions.

## 24. Page, Slice, and cursor pagination

Page<T> includes total element count and total pages. To compute totalElements, Spring Data usually needs an extra count query. This is useful when the UI needs to show total page count, though it can be costly with complex joins or filters.

| Type | Metadata | Best suited for |
| --- | --- | --- |
| Page<T> | content, totalElements, totalPages, page number | UI needs total results and page count |
| Slice<T> | content, hasNext, page/size | UI only needs to know if a next page exists |
| Cursor/keyset | continuation cursor/position, independent of deep offset | Large datasets, continuous sequential traversal |

If the API does not need total result counts, consider Slice to avoid the count query. If data is huge and users frequently navigate deep into pages, consider keyset/cursor pagination. In that case the contract uses a cursor or continuation token instead of a page number; document the cursor schema and rules separately in OpenAPI.

Do not refer to every pagination mechanism as Pageable. Pageable is an offset-based page/size/sort model; cursor pagination has different semantics and usually needs dedicated request/response DTOs.

## 25. Performance and database indexing

Filters and sorts must be designed alongside database indexes:

- Searching by category and createdAt may need a composite index matching actual query patterns.
- Filtering by minPrice/maxPrice calls for considering an index on price.
- Contains searches using LIKE '%keyword%' rarely leverage B-tree indexes effectively; consider full-text search or a search engine at scale.
- Multi-field sorting requires evaluating index column order.
- Deep pages with large OFFSET can be slow even when page size is small.
- Page<T> can trigger a count query; measure data query time and count query time separately.

Do not create indexes for every conceivable filter. Use query logs, execution plans, and real workloads to determine the right indexes.

## 26. Security and correctness of filtering/sorting

Several key principles:

1. Expose only filters users are permitted to use.
2. Always enforce tenant/user scope on the backend; never let clients pass an arbitrary tenantId to read someone else's data.
3. Use Criteria API/Specification or parameter binding; never concatenate SQL strings from query parameters.
4. Cap page size and allowlist sort fields.
5. Do not allow sorting/filtering on sensitive properties like passwordHash, internalCost, or authorization data.
6. Limit keyword length and the number of sort criteria.
7. Enforce access permissions before computing totalElements to avoid leaking out-of-scope record counts.

OpenAPI only describes the contract; authorization and validation must be enforced on the backend. Hiding a parameter in Swagger UI is not a security measure.

## 27. Common mistakes

| Symptom | Cause | Resolution |
| --- | --- | --- |
| Swagger UI shows Pageable as an object | Missing @ParameterObject or wrong import | Use org.springdoc.core.annotations.ParameterObject |
| Filter object does not bind query string | Missing @ModelAttribute or DTO cannot bind | Use @ModelAttribute with appropriate constructor/setters |
| Page/size missing from OpenAPI | Pageable is hidden or wrong Springdoc starter | Check @ParameterObject and pageable converter |
| Wrong default page/size in docs | @PageableDefault or Spring Data property mismatch | Check runtime resolver and OpenAPI JSON |
| Sort does not work | Wrong sort syntax or field does not exist | Use valid property, e.g., sort=price,asc |
| Unstable sort order | Missing unique tie-breaker | Add id as the final criterion |
| API returns missing results after filtering | Filtering in Java after paginating | Move filters into Specification/database query |
| Incorrect totalElements | Count query does not apply the same filter criteria | Inspect count query and Specification |
| Request size too large | Max page size not capped | Configure max-page-size and validate in service |
| Sort field causes runtime error | Client sent an unsupported property | Validate sort allowlist and return 400 |
| Page response schema changes on Boot upgrade | Returning Page<T> directly and serialization changed | Use a stable response DTO or check schema diffs |
| Slow search | LIKE contains, missing index, or heavy joins | Review execution plan and consider full-text search |

## 28. Exercise completion checklist

- [ ] Query filter contains only fields allowed by the API.
- [ ] Filter DTO has appropriate descriptions, examples, and validation.
- [ ] Controller uses @ModelAttribute for the filter object.
- [ ] Controller uses @ParameterObject for both the filter and Pageable.
- [ ] @PageableDefault documents default page, size, and sort.
- [ ] page starts at 0 or follows an explicitly published one-based convention.
- [ ] max-page-size is capped in configuration and/or service.
- [ ] Sort fields are validated against an allowlist.
- [ ] Multi-field sort and tie-breaker produce deterministic ordering.
- [ ] Specification combines filters before the repository paginates.
- [ ] Response has clear content and page metadata.
- [ ] OpenAPI JSON displays keyword/category/minPrice/maxPrice/inStock/page/size/sort.
- [ ] Swagger UI allows entering query parameters accurately and shows defaults.
- [ ] Tests verify both the OpenAPI document and runtime requests.
- [ ] Tests cover invalid filters, oversized page size, unsupported sorts, and empty results.
- [ ] Database indexes are evaluated against real queries.
- [ ] Tenant/user authorization is always enforced server-side.

When combining Spring Data Pageable with @ParameterObject, Springdoc can document page, size, and sort as query parameters that clients can use directly in Swagger UI. For a reliable API, model filters with a dedicated DTO, apply Specifications in the database, enforce sort/page size limits, and return a stable response envelope. Finally, verify both the OpenAPI document and runtime requests/responses to keep documentation and implementation behavior in sync.

## References

- [Springdoc OpenAPI FAQ — Pageable and @ParameterObject](https://springdoc.org/faq.html)
- [Springdoc OpenAPI v2 FAQ](https://springdoc.org/v2/faq.html)
- [Spring Data Commons — PageableHandlerMethodArgumentResolver](https://docs.spring.io/spring-data/commons/docs/current/api/org/springframework/data/web/PageableHandlerMethodArgumentResolver.html)
- [Spring Data Commons — Pageable resolver configuration](https://docs.spring.io/spring-data/commons/reference/api/java/org/springframework/data/web/PageableHandlerMethodArgumentResolverSupport.html)
- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
