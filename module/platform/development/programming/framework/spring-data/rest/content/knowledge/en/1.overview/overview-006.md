# Comparing Spring Data REST Repository APIs with Custom Controller–Service–DTO APIs

> Scope: overview article in the Spring Data REST module. The goal is to understand the two approaches to exposing data from Spring Data over HTTP, how they differ in API contract, and when to choose each.

## 1. Core idea

Both Spring Data REST and custom-written APIs can share the same Spring Data repository in the data access layer. The difference lies in how the HTTP API is created and where the team controls the contract with clients.

- **Spring Data REST** inspects repository interfaces and automatically exports them as REST resources. Repositories, domain types, and configuration determine most paths, HTTP operations, and data representations.
- **Controller–Service–DTO** lets the team explicitly define endpoints with Spring MVC, validate requests, invoke a service to execute a use case, and map results into DTOs tailored for clients.

High-level flow:

~~~text
Spring Data REST:
Client -> Spring Data REST exporter -> Repository -> Database

Controller–Service–DTO:
Client -> Controller -> Request DTO validation -> Service -> Repository -> Database
                                                     |
                                                     v
                                             Response DTO -> Client
~~~

Spring Data REST significantly reduces repetitive CRUD boilerplate. A custom-written API requires more layers, yet gives explicit control over input/output data, business logic, and how the API evolves.

## 2. Same domain, two ways to expose the API

Let us use an example of a product with an identifier, name, and price. The code snippets below are Java 17+ building blocks to illustrate architecture; they need to live inside a Spring Boot application with persistence configuration, a database, and corresponding Spring dependencies, so they do not form a standalone program runnable via the `java` command alone.

### 2.1. Shared entity and repository

~~~java
// Product.java
package com.example.catalog.product;

import jakarta.persistence.*;
import java.math.BigDecimal;

@Entity
@Table(name = "products")
public class Product {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Product() {
        // JPA requires a no-arg constructor.
    }

    public Product(String name, BigDecimal price) {
        this.name = name;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public BigDecimal getPrice() {
        return price;
    }

    // Public setters enable JSON data binding when writing via Spring Data REST.
    public void setName(String name) {
        this.name = name;
    }

    public void setPrice(BigDecimal price) {
        this.price = price;
    }
}
~~~

With Spring Data JPA, the repository can be declared as follows:

~~~java
// ProductRepository.java
package com.example.catalog.product;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.repository.query.Param;
import org.springframework.data.rest.core.annotation.RepositoryRestResource;
import org.springframework.data.rest.core.annotation.RestResource;

@RepositoryRestResource(
    path = "products",
    collectionResourceRel = "products"
)
public interface ProductRepository extends JpaRepository<Product, Long> {

    @RestResource(path = "by-name", rel = "by-name")
    Page<Product> findByNameContainingIgnoreCase(
        @Param("q") String q,
        Pageable pageable
    );
}
~~~

When the repository is published by Spring Data REST, clients can access default resources and search resources corresponding to query methods. Publishing also depends on whether the repository is detected, whether the method exists, and whether it is marked `exported = false`.

### 2.2. Approach A — letting Spring Data REST export the repository

Add the Spring Data REST dependency matching the active Spring Boot version, along with the store starter (such as Spring Data JPA) and database driver. Spring Boot dependency management should be used to choose compatible versions.

With the repository above, typical URLs are:

| Request | Meaning |
|---|---|
| `GET /products` | Retrieve the product collection |
| `GET /products/{id}` | Retrieve a single product |
| `POST /products` | Create a product |
| `PUT /products/{id}` | Replace resource state if the method is exported |
| `PATCH /products/{id}` | Partially update if the method is exported |
| `DELETE /products/{id}` | Delete the resource if the method is exported |
| `GET /products/search/by-name?q=keyboard&page=0&size=10` | Run the query method searching by name |

Available HTTP methods depend on repository methods and export configuration. For example, if the repository does not provide or export a save operation, the corresponding write endpoint will not be provided.

A request to create a product can send JSON matching exposed properties:

~~~http
POST /products
Content-Type: application/json

{
  "name": "Keyboard",
  "price": 1290000
}
~~~

Spring Data REST typically returns a HAL representation. The client may receive sections such as:

~~~json
{
  "_embedded": {
    "products": [
      {
        "name": "Keyboard",
        "price": 1290000,
        "_links": {
          "self": {
            "href": "http://localhost:8080/products/1"
          }
        }
      }
    ]
  },
  "_links": {
    "self": {
      "href": "http://localhost:8080/products"
    }
  },
  "page": {
    "size": 20,
    "totalElements": 1,
    "totalPages": 1,
    "number": 0
  }
}
~~~

The JSON above only illustrates structure; full URLs, links, and actual metadata depend on configuration, data, and the request. HAL places links in `_links`, collections usually sit in `_embedded`, and paginated responses include `page` metadata. Clients can discover resources from the application's root URL instead of hard-coding every path.

**Pagination and sorting:** for repositories supporting `Pageable` or `Sort`, Spring Data REST understands `page`, `size`, and `sort` parameters. Page numbers start at 0; the default size is usually 20 and is configurable. For example:

~~~http
GET /products?page=0&size=10&sort=name,asc
~~~

Paginated results include metadata and links such as `next` or `prev` when corresponding pages exist. Query methods intended for pagination need to accept `Pageable` and return `Page` or `Slice`.

**Customization:** you can change the collection path or relation using `@RepositoryRestResource`, change a query method's path using `@RestResource`, hide a repository with `@RepositoryRestResource(exported = false)`, or hide an individual method with `@RestResource(exported = false)`. `RepositoryRestConfigurer` lets you configure the base path, default/maximum page sizes, and other options.

**Representation:** Spring Data projections can select a subset of properties to return; Spring Data REST can also configure a default projection for collections. Projections help control the data view, but do not automatically create a DTO boundary completely independent from the domain model.

### 2.3. Approach B — writing Controller–Service–DTO manually

In this approach, the repository still works with entities, while the controller accepts and returns data types designed specifically for the API. As a result, clients do not need to send or receive the entire persistence structure directly.

Request DTOs and response DTOs are placed in separate files:

~~~java
// CreateProductRequest.java
package com.example.catalog.product.api;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;
import java.math.BigDecimal;

public record CreateProductRequest(
    @NotBlank @Size(max = 120) String name,
    @NotNull @Positive BigDecimal price
) {}
~~~

~~~java
// ProductResponse.java
package com.example.catalog.product.api;

import java.math.BigDecimal;

public record ProductResponse(
    Long id,
    String name,
    BigDecimal price
) {}
~~~

~~~java
// ProductPageResponse.java
package com.example.catalog.product.api;

import java.util.List;

public record ProductPageResponse<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    int totalPages
) {}
~~~

The service contains use cases and coordinates the repository:

~~~java
// ProductService.java
package com.example.catalog.product;

import com.example.catalog.product.api.CreateProductRequest;
import com.example.catalog.product.api.ProductResponse;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
@Transactional(readOnly = true)
public class ProductService {

    private final ProductRepository repository;

    public ProductService(ProductRepository repository) {
        this.repository = repository;
    }

    public Page<ProductResponse> findAll(Pageable pageable) {
        return repository.findAll(pageable).map(this::toResponse);
    }

    @Transactional
    public ProductResponse create(CreateProductRequest request) {
        Product product = new Product(request.name(), request.price());
        Product saved = repository.save(product);
        return toResponse(saved);
    }

    private ProductResponse toResponse(Product product) {
        return new ProductResponse(
            product.getId(),
            product.getName(),
            product.getPrice()
        );
    }
}
~~~

The controller defines the HTTP contract:

~~~java
// ProductController.java
package com.example.catalog.product.api;

import com.example.catalog.product.ProductService;
import jakarta.validation.Valid;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping
    public ProductPageResponse<ProductResponse> findAll(
        @PageableDefault(size = 20, sort = "name") Pageable pageable
    ) {
        Page<ProductResponse> result = service.findAll(pageable);

        return new ProductPageResponse<>(
            result.getContent(),
            result.getNumber(),
            result.getSize(),
            result.getTotalElements(),
            result.getTotalPages()
        );
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public ProductResponse create(
        @Valid @RequestBody CreateProductRequest request
    ) {
        return service.create(request);
    }
}
~~~

For Bean Validation annotations to take effect, the application needs the corresponding validation dependency, such as the Spring Boot validation starter. When a request fails `@NotBlank`, `@Size`, `@NotNull`, or `@Positive`, validation rejects the request before the controller calls the service. Business rules depending on multiple pieces of data or state should be checked in the service/domain, as not every rule can be expressed via DTO annotations.

In the example above, the paginated response is an application-defined `ProductPageResponse`. This is intentional: if a public API requires a stable contract, do not assume Jackson's direct serialization of the internal `Page` type is a long-term format. Explicitly select the fields clients need and test the actual JSON.

Other endpoints such as reading by ID, updating, and deleting are also explicitly defined by the team in controllers/services. For example, the service can throw an exception when a product is not found; `@RestControllerAdvice` translates that error into a consistent error response with status and error code matching the application's contract.

## 3. Direct comparison

| Criterion | Spring Data REST repository | Controller–Service–DTO |
|---|---|---|
| Initial code volume | Low; repositories can provide CRUD resources out of the box | Higher; requires writing controllers, DTOs, services, and mapping |
| Where the API is defined | Derived from repositories, domain types, and export annotations | Explicitly defined in controllers and DTOs |
| Request/response contract | Fairly tightly coupled to entity/repository; customizable via projections and config | Team proactively designs DTOs, fields, envelopes, and errors |
| CRUD | Built-in when corresponding repository methods are exported | Only operations explicitly written by the team |
| Search | Query methods can auto-export as resources under `/search` | Team explicitly defines routes, parameters, and query logic |
| Pagination/sorting | Built-in support for `Pageable`, `Sort`, metadata, and HAL links | Can use `Pageable`, while the team decides format and exposure policy |
| Multi-step business logic | Requires customization; exported repository requests do not automatically go through a custom service | Service is a natural place to coordinate multiple repositories and business rules |
| DTOs and data transformation | Projections support certain data views | DTOs and mappers are fully controlled |
| Validation | Can register `Validator` instances on repository events | Can use Bean Validation for request DTOs and business checks in services |
| Status, headers, errors | Follows framework behavior and configuration; has extension points | Directly controlled via Spring MVC and exception handlers |
| Hypermedia | HAL and resource discovery links are built in | Not automatic; can be designed manually or with Spring HATEOAS |
| Contract maintenance | Entity/repository changes can affect exported APIs | DTOs can remain stable as entities and databases evolve |
| Access surface control | Must audit exported repositories/methods and protect with Spring Security | Routes and operations are explicitly declared; still requires Spring Security |
| Best suited for | Data-oriented CRUD, internal APIs, or cases where the domain model fits the public representation | Business-oriented APIs, public/mobile/partner APIs, and contracts needing stability |

### 3.1. Critical difference in business flow

Suppose `ProductService.create()` checks inventory quotas, writes an audit log, and publishes a business event before saving. Requests going through `POST /api/products` invoke that service because the controller explicitly delegates to it.

If at the same time the repository is published by Spring Data REST at `POST /products`, requests to that path are handled directly by the exporter through the repository. It **does not automatically call `ProductService.create()`**. Therefore, two endpoints can create products through two different flows even though both write to the same table.

This is a design risk to address early. If business rules must execute on every write path, place rules in a shared domain/service layer and choose an exposure approach ensuring all requests pass through that flow. To use only the custom API, disable repository export with `@RepositoryRestResource(exported = false)`. If using Spring Data REST, you can add repository event handlers and validators at appropriate hooks, though carefully weigh their scope and do not treat them as an automatic substitute for a full use-case service.

## 4. DTOs, projections, and entities are not the same concept

These three types solve different problems:

- **Entity** models data and relationships in persistence/domain. It may hold internal properties, lazy relationships, or structures unsuitable for public exposure.
- **Projection** creates a selective view over objects returned by a repository. It is useful when you want to hide properties or present a simpler read structure in Spring Data.
- **DTO** is a data type belonging to the application/API contract. It can rename fields, combine data from multiple aggregates, represent requests differently from entities, or remain unchanged when database structure changes.

For example, an entity has `internalCost`, `supplierId`, and an `auditEntries` relationship; the public product API should return only `id`, `name`, and `price`. DTOs make this boundary explicit. Projections can also pick a subset of fields, yet when the API has its own transformation, aggregation, or versioning rules, DTOs are generally easier to manage.

Do not expose an entity simply because Spring Data REST can serialize it. Before publishing, review sensitive fields, associations, circular serialization, lazy loading, and the number of generated queries.

## 5. Which approach to choose in real-world scenarios?

### Choose Spring Data REST when

- The primary need is CRUD on an aggregate/repository and HTTP operations map directly to data operations.
- The API serves internal tools, admin UIs, or clients capable of working with HAL and resource discovery links.
- The domain representation is suitable to expose without complex request/response transformations.
- You want to stand up an API quickly and accept Spring Data REST's endpoint conventions.
- The team can tightly control which repositories, methods, and properties are exported.

### Choose Controller–Service–DTO when

- The API serves mobile apps, partners, or external clients and needs a stable contract across versions.
- A single request must coordinate multiple repositories, call external services, apply workflows, or perform multiple steps.
- Requests/responses differ substantially from entities; aggregation, field renaming, data masking, or multi-client support is needed.
- You need exact control over status codes, headers, error formats, idempotency, or update rules.
- Access permissions depend on the use case, user, tenant, or business state.
- You do not want entity/repository changes to accidentally alter the public API.

### Use a hybrid approach when boundaries are clear

An application can use Spring Data REST for internal CRUD resources and dedicated controllers for business use cases. For example, `/products` can power a simple admin screen, while `/api/orders/{id}/checkout` is a dedicated use case orchestrated by a service.

When combining both, clearly define which endpoints are allowed to write and where mandatory rules are enforced. Avoid having one endpoint go through a service while another writes straight to a repository and produces inconsistent business outcomes. If two routes represent the same contract, consider keeping only one write path.

## 6. Checklist before taking an API to production

1. **List of exported repositories:** verify the repository detection strategy and all `exported` annotations. Never assume only repositories used by controllers are exposed.
2. **Read and write permissions:** apply Spring Security to URLs and/or repository methods. Distinguish permissions for reading collections, reading items, creating, editing, deleting, and manipulating associations. Never treat hiding links or changing URLs as a security mechanism.
3. **Returned data:** audit entity fields, associations, projections, lazy loading, serialization cycles, and internal data.
4. **Pagination:** set a maximum page size limit, avoid returning entire large collections, and allow sorting only on appropriate properties.
5. **Validation:** validate input data and business invariants. Validators attached to Spring Data REST events run only within that event flow; do not assume they cover every write path in the application.
6. **Errors and status codes:** test not-found, invalid input, conflict, insufficient permission, and external dependency error cases. For custom APIs, standardize error responses via `@RestControllerAdvice`.
7. **Client compatibility:** renaming entities, repository methods, fields, or associations can affect Spring Data REST resources. For public APIs, manage versions and DTO changes intentionally.
8. **Integration testing:** test real endpoints, media types, JSON/HAL, links, pagination, allowed methods, validation, and security. Unit-testing a repository alone does not prove the HTTP contract is correct.

## 7. Summary of the choice

Spring Data REST fits well when the repository is the center of the API and the team wants to expose standardized data operations with minimal code. Controller–Service–DTO fits well when the API is a product contract that must be designed and maintained independently from persistence.

You can use this quick rule of thumb to decide:

- If the main question is **“which repository resources does the client need CRUD access to?”**, start with Spring Data REST.
- If the main question is **“which use cases does the client need to execute and what data contract must it send/receive?”**, start with Controller–Service–DTO.
- If you need both, establish read/write boundaries and ensure all mandatory business rules execute across every access path.

## 8. References

- [Spring Data REST Reference — Repository resources](https://docs.spring.io/spring-data/rest/reference/repository-resources.html): collection, item, query method resources, and HTTP methods.
- [Spring Data REST Reference — Getting started and configuration](https://docs.spring.io/spring-data/rest/reference/introduction/getting-started.html): repository detection, base path, and configuration.
- [Spring Data REST Reference — Paging and sorting](https://docs.spring.io/spring-data/rest/reference/paging-and-sorting.html): page, size, sort parameters, and navigation links.
- [Spring Data REST Reference — Projections](https://docs.spring.io/spring-data/rest/reference/data-commons/repositories/projections.html): Spring Data projections.
- [Spring Data REST Reference — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html): registering `Validator` instances on repository events.
- [Spring Data REST Reference — Events](https://docs.spring.io/spring-data/rest/reference/events.html): repository event handlers.
- [Spring Data REST Reference — Security](https://docs.spring.io/spring-data/rest/reference/security.html): Spring Security integration and method-level security.
