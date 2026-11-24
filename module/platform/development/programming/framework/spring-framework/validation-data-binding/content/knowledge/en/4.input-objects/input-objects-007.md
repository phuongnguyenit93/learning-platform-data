# Separating Create, Update, and Search Objects

In a Spring Framework application, **sharing the same business entity does not mean every request should share the same input data type**. Create, update, and search differ in purpose, allowed fields, required-field rules, and handling logic. Designing separate **input object** types helps Spring MVC bind the right data, Bean Validation enforce the right constraints, and the service avoid accidentally receiving fields the caller is not permitted to change.

The running example is book management. The system stores a `Book` with `id`, `title`, `author`, `price`, and `stock`. API clients can add books, edit allowed attributes, or filter the book list. Those three actions use three distinct types: `BookCreateRequest`, `BookUpdateRequest`, and `BookSearchQuery`.

## 1. Why Separate the Three Input Object Types?

Consider an approach using a single `Book` across all endpoints:

~~~java
// Design to avoid: binding requests directly onto a persistence entity.
@PostMapping("/books")
void create(@RequestBody Book book) { /* ... */ }

@PutMapping("/books/{id}")
void update(@PathVariable long id, @RequestBody Book book) { /* ... */ }

@GetMapping("/books")
List<Book> search(Book book) { /* ... */ }
~~~

If `Book` also has `id`, `createdAt`, `ownerId`, `approved`, or JPA relationships, sharing that type blurs the question: *which fields is the caller allowed to decide?* When fields are later added to the entity, the deserialized/bound surface area can also change unintentionally.

Common differences:

| Aspect | Create | Update | Search |
|---|---|---|---|
| Purpose | Provide data to create a record | Modify an existing record | Build query criteria |
| Typical HTTP | `POST /api/books` | `PUT /api/books/{id}` (or `PATCH` with its own contract) | `GET /api/books?...` |
| Primary input | JSON body | Path ID + JSON body | Query string |
| Record ID | Server-generated, not client-assigned | Taken from path, requires authorization check | Filter only, if feature allows |
| Required attributes | Values to create a valid record | Values per update contract | Mostly optional, with defaults |
| Validation | E.g., title/price/stock on creation | E.g., updated fields must be valid | E.g., page ≥ 0, bounded page size |
| Outcome | Creates a resource, typically `201 Created` | Returns updated record or `204 No Content` | Returns list/page of results |
| Appropriate type | `BookCreateRequest` | `BookUpdateRequest` | `BookSearchQuery` |

These are **input contracts** per use case, often called request DTOs, command objects, or search criteria. A `DTO` is not a JPA-managed entity. The output object returned to clients (such as `BookResponse`) should also be designed separately because returned fields do not necessarily match accepted fields.

## 2. Standard Data Flow Across the Spring MVC Boundary

~~~text
                 HTTP request
                      |
          +-----------+------------+
          |           |            |
        POST          PUT          GET
        JSON          JSON      query params
          |           |            |
          v           v            v
    CreateRequest UpdateRequest SearchQuery
          |           |            |
       JSON body    JSON body   @ModelAttribute
       deserialize  deserialize  data binding
          |           |            |
     @Valid /      @Valid /     @Valid /
     validation    validation   BindingResult
          |           |            |
          v           v            v
   Create service Update service Search service
          |           |            |
  create Entity   load Entity,  build query
  assign allowed  check authz,   criteria
     fields      assign allowed  with paging
                    fields
          |           |            |
          +-----------+------------+
                      |
                   Response DTO
~~~

At the HTTP layer, keep the two mechanisms distinct:

- For JSON `@RequestBody`, an `HttpMessageConverter` (usually Jackson) reads the body and creates a Java object; `@Valid` triggers Bean Validation when properly configured.
- For query parameters or `@ModelAttribute` forms, Spring MVC uses **data binding** for properties or constructor parameters, performing type conversion and recording errors into `BindingResult`. `@InitBinder` can configure `WebDataBinder` for that target.
- **`WebDataBinder.setAllowedFields(...)` is not a JSON property filter for `@RequestBody`.** For JSON, design request DTOs containing only permitted fields and apply appropriate Jackson settings and input policies.
- DTO validation does not replace update authorization checks, existence checks, business rules, transactions, or concurrency control in the service.

## 3. Standalone Java 17 Example Showing Different Contracts

This is a **pure Java** example without Spring or a database, illustrating three objects serving three different actions. Save as `RequestRolesDemo.java`:

~~~java
import java.math.BigDecimal;
import java.util.Locale;

public class RequestRolesDemo {

    record CreateBook(
            String title,
            String author,
            BigDecimal price,
            int initialStock) {}

    record UpdateBook(
            String title,
            BigDecimal price,
            int stock) {}

    record SearchBooks(
            String keyword,
            int page,
            int size) {}

    static final class Book {
        private final long id;              // Server-assigned only
        private final String author;         // Fixed after creation
        private String title;
        private BigDecimal price;
        private int stock;

        Book(long id, CreateBook request) {
            this.id = id;
            this.title = request.title();
            this.author = request.author();
            this.price = request.price();
            this.stock = request.initialStock();
        }

        void update(UpdateBook request) {
            this.title = request.title();
            this.price = request.price();
            this.stock = request.stock();
        }

        boolean matches(SearchBooks query) {
            return title.toLowerCase(Locale.ROOT)
                    .contains(query.keyword().toLowerCase(Locale.ROOT));
        }

        String summary() {
            return id + " | " + title + " | " + author + " | "
                    + price.toPlainString() + " | stock=" + stock;
        }
    }

    public static void main(String[] args) {
        CreateBook create = new CreateBook(
                "Java Basics", "An", new BigDecimal("120.00"), 3);
        Book book = new Book(101L, create);
        System.out.println("CREATED: " + book.summary());

        UpdateBook update = new UpdateBook(
                "Java Advanced", new BigDecimal("150.00"), 5);
        book.update(update);
        System.out.println("UPDATED: " + book.summary());

        SearchBooks search = new SearchBooks("java", 0, 20);
        System.out.println("SEARCH_MATCH: " + book.matches(search));
    }
}
~~~

Compile and run with JDK 17+:

~~~bash
javac RequestRolesDemo.java
java RequestRolesDemo
~~~

Exact output:

~~~text
CREATED: 101 | Java Basics | An | 120.00 | stock=3
UPDATED: 101 | Java Advanced | An | 150.00 | stock=5
SEARCH_MATCH: true
~~~

Observation: the create request carries `author` and `initialStock`; the update request carries `stock` without accepting `id` or modifying `author`; the search request carries only criteria, `page`, and `size`. The `matches` method only illustrates keyword filtering; this pure Java example **does not implement pagination**. A real application must apply pagination in the service/repository layer.

In Spring, keep that separation of roles while adding binding, validation, mapping, and error handling at the appropriate layers.

## 4. Create Object: Data Needed to Construct a Record

In a Spring MVC project with `spring-webmvc` and Jakarta Bean Validation (in Spring Boot typically `spring-boot-starter-web` and `spring-boot-starter-validation`), you can write an immutable record:

File `BookCreateRequest.java`:

~~~java
package example.books.api;

import java.math.BigDecimal;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record BookCreateRequest(
        @NotBlank @Size(max = 120) String title,
        @NotBlank @Size(max = 80) String author,
        @NotNull @DecimalMin("0.00") BigDecimal price,
        @NotNull @Min(0) Integer initialStock) {
}
~~~

Valid JSON example:

~~~json
{
  "title": "Spring in Practice",
  "author": "Mai",
  "price": 180000.00,
  "initialStock": 12
}
~~~

**Contract semantics:**

1. `title` and `author` must not be null, empty, or whitespace-only; length bounds match storage rules.
2. `price` is required and non-negative; `BigDecimal` is more suitable than `double` for decimal currency values. Real business rules also require currency unit, precision, and upper-limit rules.
3. `initialStock` must be present and non-negative. Use `Integer` instead of `int` to distinguish an omitted field (null) from 0; `@Min(0)` alone **does not reject null**.
4. The DTO **has no** `id`, `ownerId`, `createdAt`, `approved`, or `version`. Those values must be determined by the server and business policy.
5. A record fits immutable JSON requests well. For `@ModelAttribute` requests, JavaBeans with setters or supported constructor binding are alternatives; you do not have to force one pattern onto every input channel.

`@Valid` checks constraints on the record when the controller receives JSON. Errors like missing `title` or `price < 0` normally make Spring MVC return HTTP 400 if the controller does not handle a `BindingResult` itself. Malformed JSON or severe type mismatches can raise body-reading errors before Bean Validation runs, so keep those two error kinds distinct.

## 5. Update Object: Only Editable Fields, ID Separate from Body

Assume `author` is fixed after creation; users may only edit title, price, and stock through a full update of editable fields.

File `BookUpdateRequest.java`:

~~~java
package example.books.api;

import java.math.BigDecimal;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record BookUpdateRequest(
        @NotBlank @Size(max = 120) String title,
        @NotNull @DecimalMin("0.00") BigDecimal price,
        @NotNull @Min(0) Integer stock) {
}
~~~

Request:

~~~http
PUT /api/books/101
Content-Type: application/json

{"title":"Spring Advanced","price":210000.00,"stock":9}
~~~

Intentional differences:

- `BookCreateRequest` uses `initialStock` and accepts `author` when the record does not yet exist.
- `BookUpdateRequest` uses `stock` for the updated stock level and **omits `author`** because this contract does not allow editing the author.
- `id=101` comes from `@PathVariable` to identify the record; the body has no authority to alter the primary identifier.
- For **PUT under this contract**, `title`, `price`, and `stock` are all required. If users need to change only the price, design a dedicated partial-update contract such as PATCH; do not silently turn PUT into PATCH simply because a field is omitted.

The existing record is fetched and verified before applying changes, for example in the service:

~~~java
// Snippet in the project's service/repository, not a standalone program.
Book entity = repository.findById(bookId)
        .orElseThrow(() -> new BookNotFoundException(bookId));

authorization.checkCanEdit(currentUser, entity);

entity.setTitle(request.title().trim());
entity.setPrice(request.price());
entity.setStock(request.stock());

repository.save(entity);
~~~

Types `Book`, `BookNotFoundException`, `repository`, `authorization`, and `currentUser` here are components of the integrated application, **not built-in Spring APIs**. The key point is that the service assigns only the fields permitted by the update contract, after resolving the record and verifying caller permissions.

If inventory must be managed through dedicated stock-in/stock-out transactions, remove `stock` from the book metadata update DTO and provide a dedicated inventory operation. Exact boundaries are driven by the use case.

## 6. Search Object: Optional Criteria, Defaults, and Query Limits

A search request **neither creates nor modifies entities**. It describes filtering and pagination criteria. In Spring MVC, query strings are conveniently bound via `@ModelAttribute` into a dedicated query object.

File `BookSearchQuery.java`:

~~~java
package example.books.api;

import java.math.BigDecimal;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.Size;

public class BookSearchQuery {

    @Size(max = 120)
    private String keyword;

    @DecimalMin("0.00")
    private BigDecimal minPrice;

    @DecimalMin("0.00")
    private BigDecimal maxPrice;

    @Min(0)
    private int page = 0;

    @Min(1)
    @Max(100)
    private int size = 20;

    public String getKeyword() {
        return keyword;
    }

    public void setKeyword(String keyword) {
        this.keyword = keyword;
    }

    public BigDecimal getMinPrice() {
        return minPrice;
    }

    public void setMinPrice(BigDecimal minPrice) {
        this.minPrice = minPrice;
    }

    public BigDecimal getMaxPrice() {
        return maxPrice;
    }

    public void setMaxPrice(BigDecimal maxPrice) {
        this.maxPrice = maxPrice;
    }

    public int getPage() {
        return page;
    }

    public void setPage(int page) {
        this.page = page;
    }

    public int getSize() {
        return size;
    }

    public void setSize(int size) {
        this.size = size;
    }
}
~~~

Example:

~~~http
GET /api/books?keyword=Spring&minPrice=100000&maxPrice=250000&page=0&size=20
~~~

Key points to understand:

- `keyword`, `minPrice`, and `maxPrice` are **optional filters**; null means "do not apply this criterion" per service convention.
- `page=0` and `size=20` are defaults when the client omits those parameters. `@Min` and `@Max` enforce bounds once bound.
- Spring attempts to convert query strings into `BigDecimal` / `int`. With `size=abc`, binding can raise a type mismatch error; inspect `BindingResult` before running a query.
- `@DecimalMin("0.00")` does not require the number to be present; add `@NotNull` if a filter is truly mandatory.
- **Cross-field constraint**: if both `minPrice` and `maxPrice` are present, `minPrice <= maxPrice` must hold. Per-field annotations do not guarantee that condition; use a class-level custom constraint or check explicitly at the query boundary.
- Normalize `keyword` (trim, length cap, case-insensitive matching policy if needed) in the criteria conversion layer. Never concatenate user query strings directly into SQL.
- Queries can be expensive; enforce `size` limits, stable sort order, required indexes, and other optimizations. If supporting `sort`, allow choosing only from an approved list of sort fields.

Do not add fields like `title`, `author`, and `price` to the search object merely because they exist on the entity. Declare only the criteria the API actually supports with clear semantics when omitted.

## 7. Connecting the Three Input Objects to a Spring MVC Controller

Below is an **integration code example inside a Spring MVC application**, assuming a `BookService` has been implemented and registered as a bean. The DTOs from sections 4–6 live in package `example.books.api`.

File `BookResponse.java`, output separated from input:

~~~java
package example.books.api;

import java.math.BigDecimal;

public record BookResponse(
        long id,
        String title,
        String author,
        BigDecimal price,
        int stock) {
}
~~~

File `BookService.java`, contract for the business layer:

~~~java
package example.books.api;

import java.util.List;

public interface BookService {
    BookResponse create(BookCreateRequest request);
    BookResponse update(long bookId, BookUpdateRequest request);
    List<BookResponse> search(BookSearchQuery query);
}
~~~

File `BookController.java`:

~~~java
package example.books.api;

import java.net.URI;
import java.util.List;
import java.util.Map;

import jakarta.validation.Valid;

import org.springframework.http.ResponseEntity;
import org.springframework.validation.BindingResult;
import org.springframework.web.bind.WebDataBinder;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.InitBinder;
import org.springframework.web.bind.annotation.ModelAttribute;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.PutMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/books")
public class BookController {

    private final BookService service;

    public BookController(BookService service) {
        this.service = service;
    }

    @InitBinder("filters")
    void bindSearchFields(WebDataBinder binder) {
        binder.setAllowedFields(
                "keyword", "minPrice", "maxPrice", "page", "size");
    }

    @PostMapping
    public ResponseEntity<BookResponse> create(
            @Valid @RequestBody BookCreateRequest request) {
        BookResponse created = service.create(request);
        URI location = URI.create("/api/books/" + created.id());
        return ResponseEntity.created(location).body(created);
    }

    @PutMapping("/{id}")
    public BookResponse update(
            @PathVariable long id,
            @Valid @RequestBody BookUpdateRequest request) {
        return service.update(id, request);
    }

    @GetMapping
    public ResponseEntity<?> search(
            @Valid @ModelAttribute("filters") BookSearchQuery query,
            BindingResult errors) {

        if (errors.hasErrors()) {
            List<Map<String, String>> details =
                    errors.getFieldErrors().stream()
                            .map(error -> Map.of(
                                    "field", error.getField(),
                                    "code", String.valueOf(error.getCode())))
                            .toList();
            return ResponseEntity.badRequest()
                    .body(Map.of("errors", details));
        }

        if (query.getMinPrice() != null
                && query.getMaxPrice() != null
                && query.getMinPrice().compareTo(query.getMaxPrice()) > 0) {
            return ResponseEntity.badRequest().body(Map.of(
                    "errors", List.of(Map.of(
                            "field", "maxPrice",
                            "code", "range.invalid"))));
        }

        return ResponseEntity.ok(service.search(query));
    }
}
~~~

The controller and types are fully declared in terms of Java 17+ APIs, yet **to boot into a real application** they still need Spring Boot/Spring MVC configuration, a Bean Validation provider, a bean implementing `BookService`, persistence or test data, and business error handling. There is no built-in repository or database in the snippets above. Only the pure Java example in section 3 is a standalone program runnable solely with `javac` / `java`.

### Important Controller Details

**Create:** `@RequestBody` deserializes JSON into `BookCreateRequest`. `@Valid` enforces constraints; the success branch returns `201 Created` with `Location` and `BookResponse`. `service.create(...)` is responsible for assigning the ID, setting allowed attributes, and saving.

**Update:** URL `/api/books/{id}` identifies the resource. The DTO includes only editable fields; `service.update(...)` verifies existence, permissions, version, and updates the exact allowed properties. If the ID does not exist, the service/controller should translate that to `404`; if there is a version conflict, it may respond with `409 Conflict` depending on the API contract.

**Search:** `@ModelAttribute("filters")` binds the query string. `@InitBinder("filters")` restricts bindable properties through `WebDataBinder`. The `BindingResult` parameter sits **immediately after** `@ModelAttribute`; this allows the controller to inspect binding/validation errors and return 400 without hitting the repository. The price-range check runs after individual values are valid.

**Error example limitations:** Malformed JSON and validation failures on `@RequestBody` are normally handled by Spring MVC via exceptions; the `BindingResult` next to `BookSearchQuery` in the example only handles errors of the *search model attribute* locally. To return JSON errors in a consistent structure, an application should define an appropriate `@RestControllerAdvice`. The error `Map` structure here only illustrates an error contract, not an automatic Spring format.

## 8. Distinguishing PUT and PATCH When Designing Updates

Separating DTOs for create/update/search is **not enough** if full replacement and partial update are mixed together.

**PUT** normally represents submitting the desired state of a resource according to the endpoint contract. In the example, the properties *permitted to be edited via the PUT contract* are all required fields. `null` or missing fields must not silently mean "keep unchanged".

**PATCH** expresses a set of changes. When supporting PATCH, clearly distinguish:

| Submitted JSON | Intended Meaning That May Be Required |
|---|---|
| Key `title` omitted | Keep existing title unchanged |
| `"title": null` | Possibly a request to clear the value, or invalid per contract |
| `"title": ""` | Request to set an empty title; likely rejected by validation |
| `"title": "New"` | Set title to `"New"` |

If you define a PATCH DTO with `String title` and use standard Jackson, both "key absent" and "key with null value" can become `null`, losing **presence information**. Use a PATCH contract with an explicit presence model (for example JSON Merge Patch per RFC 7396, JSON Patch per RFC 6902, or a wrapper type representing `absent/null/value`), and apply only fields that were actually sent and valid.

**Do not turn every nullable field into a PATCH contract**. A field may be optional on create, required on PUT, and three-state on PATCH. If PATCH is supported, create a dedicated PATCH DTO/binding mechanism rather than ambiguously reusing `BookUpdateRequest`.

For concurrent updates, consider `version`, optimistic locking (e.g., JPA `@Version`), or `ETag`/`If-Match`, so two users editing the same record do not silently overwrite each other. `version` should not become an arbitrary entity field modifiable purely through binding.

## 9. Validation Tailored to Each Action

Annotations like `@NotNull`, `@NotBlank`, `@Size`, and `@Min` only make sense within **the use-case context**.

| Rule | Create | Update | Search |
|---|---|---|---|
| Book title | Required, non-blank | Required in defined PUT | No `title` field; uses optional `keyword` |
| Author | Required on create | Not editable via this endpoint | Filtering by author not supported in example API |
| Price | `price` required, ≥ 0 | `price` required, ≥ 0 | `minPrice`/`maxPrice` optional and ≥ 0 |
| Stock | `initialStock` required, ≥ 0 | `stock` required, ≥ 0 | No stock field in example filters |
| Pagination | Not applicable | Not applicable | `page` ≥ 0, `size` in [1,100] |
| Cross-field rules | Possible depending on business logic | May differ from create | `minPrice <= maxPrice` if both appear |

One class with multiple validation groups like `Create.class` and `Update.class` can work when the input structure is genuinely identical. However, if allowed fields, field semantics, and binding sources differ, **three separate types are much clearer**. Validation groups only switch which constraints are evaluated; they **do not restrict which properties can be deserialized/bound** and do not replace authorization.

Even when the persistence entity has database constraints (such as non-null columns), request-DTO validation is still necessary to produce clear messages and block bad input before starting a transaction. The service/domain must also enforce invariants because it can be invoked from scheduled jobs, message consumers, CLIs, or internal code outside HTTP.

## 10. Mapping DTOs to Entities: Assign Only Contract Fields

Practical rules:

**Create:** instantiate a new entity, assign exact fields supplied by the create DTO; generate IDs, timestamps, owner, and default status on the server. In a real system, the service runs inside a transaction to guarantee consistent persistence state.

**Update:** load the entity by ID from the URL, verify authorization and business preconditions, and assign each permitted field. Never instantiate a new entity from the request body and `save` over everything when doing so would wipe server-owned values.

**Search:** translate the search DTO into a query/read model; never convert it into an entity and persist it. `page` and `size` are query metadata, not properties of `Book`.

Example of intentional mapping:

~~~java
// Illustrative code in service: assumes entity and repository exist.
Book createEntity(BookCreateRequest request, long currentOwnerId) {
    Book book = new Book();
    book.setTitle(request.title().trim());
    book.setAuthor(request.author().trim());
    book.setPrice(request.price());
    book.setStock(request.initialStock());
    book.setOwnerId(currentOwnerId); // Identity from server
    return book;                       // ID/timestamps managed by persistence
}

void applyUpdate(Book entity, BookUpdateRequest request) {
    entity.setTitle(request.title().trim());
    entity.setPrice(request.price());
    entity.setStock(request.stock());
    // Do not touch id, author, ownerId, createdAt...
}
~~~

The code above **does not run standalone** because `Book` APIs and persistence depend on the application. Immutable request objects prevent modifying input data after validation; mapping itself must still follow an allowed-field list and business policy. Tools like MapStruct can reduce boilerplate, but target fields must be explicitly configured, especially when updating existing entities.

If you previously used `BeanUtils.copyProperties(request, entity)` or an automatic by-name mapper across all properties, carefully audit newly added fields, nested properties, null values, and relational objects. Those utilities do not replace an explicit allowed-fields contract.

## 11. Common Mistakes and Fixes

### 11.1. Using a JPA Entity as `@ModelAttribute` or `@RequestBody`

Risk: requests can touch unintended properties, leak internal fields, or mutate unwanted relationships. Fix: use per-use-case request DTOs and restrict field binding; never expose entities directly in responses when they hold sensitive data or complex relationships.

### 11.2. Using One DTO with Too Many Optional Fields

When `id`, `keyword`, `page`, `title`, and `price` are all nullable on the same class, code struggles to distinguish missing data, not-applicable fields, valid values, and requested changes. Fix: define field presence and requiredness per action.

### 11.3. Putting `@NotNull` on Optional Search Fields

When `minPrice` is omitted, the query may still be completely valid. `@NotNull` here causes the API to reject valid requests. Apply only validation rules that match search semantics.

### 11.4. Thinking `@InitBinder.setAllowedFields` Also Blocks JSON

`@InitBinder` configures data binding for model attributes via `WebDataBinder`. JSON `@RequestBody` is read by `HttpMessageConverter`; use a dedicated request type with only permitted properties and an explicit deserialization policy. Never rely on Jackson's default ignoring of unknown fields as a substitute for access control.

### 11.5. Omitting `BindingResult` on Search

For example, `GET /api/books?page=abc` can produce a type-conversion error. Without checking errors, executing a query with partially bound data can make the service misbehave. Place `BindingResult` immediately after `@ModelAttribute` and reject the query when errors exist. For JSON, handle body-reading and validation errors via appropriate exception mapping.

### 11.6. Updating Entities from Request Body Before Checking Permissions

A DTO only constrains **data shape**; it does not confirm whether the caller is allowed to edit `bookId`. The service must check authorization for the caller and specific record before modifying or saving.

### 11.7. Allowing Unbounded Search Queries

Requests with `size=1000000` or sorting on arbitrary columns can overload the system. Cap page size, condition count, and allowed sort fields; pass query parameters safely through a repository/query builder instead of concatenating SQL from input.

### 11.8. Using One Update Type for Both PUT and PATCH

If a request omits `price`, does it mean "do not update price" or "set price to null"? Without a clear contract, the system easily deletes data or retains stale values unexpectedly. Create a PATCH model with field-presence tracking if partial updates are truly needed.

## 12. Testing the Boundaries Across the Three Input Types

These scenarios should be verified with Spring MVC tests (such as `MockMvc`) combined with service tests:

| Request | What to Verify |
|---|---|
| `POST /api/books` with all valid fields | Returns `201`, creates record accurately, server assigns ID |
| POST missing `title` or `initialStock` | Validation rejects; service does not save |
| POST with server-owned field like `ownerId` | Field does not control entity; unknown JSON may be rejected per API config |
| `PUT /api/books/101` with valid data | Only `title`, `price`, `stock` update; `author`/`ownerId` stay unchanged |
| PUT missing `price` | Rejected because PUT contract requires price |
| PUT with nonexistent ID | `404` per API policy, does not silently create a new record |
| PUT by unauthorized caller | `403` or denial per security policy, no database write |
| GET with no query params | Uses empty filters, `page=0`, `size=20` |
| GET with `size=0` / `size=1000` | Validation rejects |
| GET with `minPrice=300&maxPrice=100` | Cross-field rule rejects |
| GET with `page=abc` | Caught as type mismatch via `BindingResult`, query does not run |
| Valid GET | Modifies no data; results honor actual filters and pagination |

To test thoroughly, use a spy/mock on the service or repository to confirm **no write operations occur** on searches or invalid create/update requests. Also verify that blocked or unsupported fields cannot leak into internal entity data.

## 13. Guidelines for Choosing an Input Type

When designing a new endpoint, determine step by step:

1. **What is the action?** Create, full update, partial update, or query? Each operation deserves a clear contract.
2. **Where does data come from?** JSON body via `@RequestBody`, query/form via `@ModelAttribute`, path via `@PathVariable`; each source has its own binding path and error behavior.
3. **Which fields may the client supply?** Declare only those fields on the DTO; the server owns IDs, user identity, timestamps, roles, and internal values.
4. **What do missing and null mean?** Required for create/PUT; optional for search; PATCH must distinguish "omitted" from "set to null" when business rules require it.
5. **Which layer checks what?** Bean Validation for input structure/bounds; service/domain for permissions, cross-field relations, record existence, concurrency, and invariants.
6. **What does the response contain?** Use a response DTO with appropriate fields rather than returning raw entities or echoing request objects by default.

**Core idea:** `BookCreateRequest` expresses *what is needed to create*, `BookUpdateRequest` expresses *what is permitted to change*, and `BookSearchQuery` expresses *what may be queried*. Separating them makes data binding and validation unambiguous, prevents accidental update bugs, and allows each endpoint to evolve without forcing the entire system to share a single input class.

### References

- [Spring Framework — Data Binding in Spring MVC](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-data-binding.html)
- [Spring Framework — @ModelAttribute](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/modelattrib-method-args.html)
- [Spring Framework — @RequestBody](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
