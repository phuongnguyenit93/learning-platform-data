# Building a Data Management Feature from Schema to WebFlux API

A data management feature in a Spring Data Relational R2DBC application consists of more than just a repository and a controller. A complete implementation requires designing the schema, migrations, entity mapping, reactive queries, business rules, validation, API contract, error handling, transactions, and testing against a real database.

This practice guide builds a product management (`Product`) feature flowing from PostgreSQL to an HTTP API using Spring WebFlux and Spring Data R2DBC. Users can create products, view details, list with cursor-based pagination, update, and delete. The examples use PostgreSQL, Java, and Spring Boot; package names, dependency versions, and certain properties should be adjusted to match your actual project version.

## 1. Defining requirements and API contract

Before writing SQL or Java, define the data and behavior the feature must provide.

A product has the following attributes:

| Attribute | Type | Rules |
|---|---|---|
| id | BIGINT | Primary key, database-generated |
| sku | VARCHAR(64) | Required, unique |
| name | VARCHAR(200) | Required |
| description | TEXT | Optional |
| price | NUMERIC(12,2) | Required, non-negative |
| active | BOOLEAN | Defaults to true |
| created_at | TIMESTAMPTZ | Creation timestamp |
| updated_at | TIMESTAMPTZ | Update timestamp |
| version | BIGINT | Optimistic locking version |

API contract:

| Method | Endpoint | Purpose | Key results |
|---|---|---|---|
| GET | /api/products | List with cursor pagination | 200 |
| GET | /api/products/{id} | View details | 200, 404 |
| POST | /api/products | Create product | 201, 400, 409 |
| PUT | /api/products/{id} | Replace mutable fields | 200, 400, 404, 409 |
| DELETE | /api/products/{id} | Delete product | 204, 404 |

The list endpoint uses keyset pagination by `id` with a maximum page size. This keeps queries bounded and avoids materializing the entire table.

Processing flow:

~~~text
HTTP request
    |
    v
WebFlux Controller
    |
    v
Request validation / DTO
    |
    v
Product Service
    |
    +---- business rules
    |
    v
Spring Data R2DBC Repository / DatabaseClient
    |
    v
R2DBC PostgreSQL Driver
    |
    v
PostgreSQL schema
~~~

The controller handles the HTTP protocol and data conversion. The service holds business rules. The repository/`DatabaseClient` performs data access. Database constraints serve as the final line of defense for data integrity, even under concurrent requests.

## 2. Preparing the project and dependencies

A Spring Boot project needs these core components:

- Spring WebFlux to build a reactive HTTP API.
- Spring Data R2DBC for entity mapping and repositories.
- R2DBC PostgreSQL driver to connect to PostgreSQL.
- Spring Boot Validation to validate request DTOs.
- Spring Boot Actuator/Micrometer if operational metrics are needed.
- Spring Boot Test and Reactor Test for testing.
- PostgreSQL Testcontainers for integration tests.

Example Maven dependencies (using your project's Spring Boot dependency management/BOM to manage versions):

~~~xml
<dependencies>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-webflux</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-data-r2dbc</artifactId>
    </dependency>
    <dependency>
        <groupId>org.postgresql</groupId>
        <artifactId>r2dbc-postgresql</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-validation</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-actuator</artifactId>
    </dependency>
    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>io.projectreactor</groupId>
        <artifactId>reactor-test</artifactId>
        <scope>test</scope>
    </dependency>
    <dependency>
        <groupId>org.testcontainers</groupId>
        <artifactId>postgresql</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

If using Flyway to manage migrations, add Flyway and the PostgreSQL JDBC driver at matching versions. Flyway typically connects over JDBC, while this feature's runtime data access uses R2DBC. Both connection paths can coexist, but they must be configured and budgeted separately. In newer Flyway versions, database support may reside in a separate module such as `flyway-database-postgresql`; use the right dependency for your version.

Do not add the JDBC starter solely for migrations without understanding Spring Boot auto-configuration, as it can create an extra `DataSource` and connection pool. If Flyway is needed, configure the JDBC migration connection intentionally.

## 3. Creating the migration for the PostgreSQL schema

Create a migration, for example `V1__create_product.sql`:

~~~sql
CREATE TABLE product (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    description TEXT,
    price NUMERIC(12, 2) NOT NULL,
    active BOOLEAN NOT NULL DEFAULT TRUE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    version BIGINT NOT NULL DEFAULT 0,
    CONSTRAINT uk_product_sku UNIQUE (sku),
    CONSTRAINT ck_product_price_non_negative CHECK (price >= 0)
);

CREATE INDEX idx_product_active_id
    ON product (active, id);
~~~

The identity primary key is assigned by PostgreSQL. The unique constraint prevents duplicate SKUs under concurrent requests. The check constraint prevents negative prices even if another writer bypasses API validation.

The primary key already creates an index on `id`, so there is no need to add a redundant index solely for sorting by `id`. The `(active, id)` index should only be kept if queries filtering by `active` and sorting by `id` are frequent enough to benefit. Check the execution plan on representative data before keeping the index.

Once applied to a real environment, a migration should be treated as immutable. When changing the schema, create a new migration instead of editing an already-executed file.

### 3.1. Running migrations before application rollout

Typical deployment order:

1. Create the database/schema or grant permissions to the application user.
2. Run the migration using a controlled migration job/runner.
3. Verify the migration succeeded.
4. Start or roll out the application using the new schema.
5. Monitor mapping/query errors after deployment.

Do not let multiple application replicas run ad-hoc DDL simultaneously at startup if the migration tool and lock coordination are not clearly configured.

### 3.2. Configuring the application database

Example `application.yml`:

~~~yaml
spring:
  application:
    name: product-service
  r2dbc:
    url: r2dbc:postgresql://localhost:5432/catalog
    username: catalog_app
    password: change-me
    pool:
      enabled: true
      initial-size: 2
      max-size: 10
      max-acquire-time: 2s
      max-create-connection-time: 3s
      max-idle-time: 10m
      max-life-time: 30m
server:
  port: 8080
~~~

Pool values are examples only. `max-size` is the limit for one pool in a single instance; when scaling across multiple replicas, multiply by the maximum number of instances and add all other pools accessing the same database. Available properties and exact names depend on your Spring Boot/R2DBC Pool version.

Do not put real passwords in committed files. Use a secret manager or environment variables provided by the deployment environment. If TLS is used, configure certificates/SSL according to the PostgreSQL driver and infrastructure requirements.

## 4. Creating the Product entity

The entity maps a row in the `product` table. Use `@Table` and `@Column` to declare table/column names explicitly:

~~~java
import java.math.BigDecimal;
import java.time.OffsetDateTime;

import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public class Product {

    @Id
    private Long id;
    @Column("sku")
    private String sku;
    @Column("name")
    private String name;
    @Column("description")
    private String description;
    @Column("price")
    private BigDecimal price;
    @Column("active")
    private Boolean active;
    @Column("created_at")
    private OffsetDateTime createdAt;
    @Column("updated_at")
    private OffsetDateTime updatedAt;
    @Version
    @Column("version")
    private Long version;

    public Product() {
    }

    public Product(
            Long id,
            String sku,
            String name,
            String description,
            BigDecimal price,
            Boolean active,
            OffsetDateTime createdAt,
            OffsetDateTime updatedAt,
            Long version) {
        this.id = id;
        this.sku = sku;
        this.name = name;
        this.description = description;
        this.price = price;
        this.active = active;
        this.createdAt = createdAt;
        this.updatedAt = updatedAt;
        this.version = version;
    }

    public Long getId() { return id; }
    public String getSku() { return sku; }
    public String getName() { return name; }
    public String getDescription() { return description; }
    public BigDecimal getPrice() { return price; }
    public Boolean getActive() { return active; }
    public OffsetDateTime getCreatedAt() { return createdAt; }
    public OffsetDateTime getUpdatedAt() { return updatedAt; }
    public Long getVersion() { return version; }

    public void setId(Long id) { this.id = id; }
    public void setSku(String sku) { this.sku = sku; }
    public void setName(String name) { this.name = name; }
    public void setDescription(String description) {
        this.description = description;
    }
    public void setPrice(BigDecimal price) { this.price = price; }
    public void setActive(Boolean active) { this.active = active; }
    public void setCreatedAt(OffsetDateTime createdAt) {
        this.createdAt = createdAt;
    }
    public void setUpdatedAt(OffsetDateTime updatedAt) {
        this.updatedAt = updatedAt;
    }
    public void setVersion(Long version) { this.version = version; }
}
~~~

Key points:

- Use nullable `Long` for new IDs to represent an entity not yet assigned a key by the database.
- Use `BigDecimal` for money; never use `double`/`float` due to binary rounding errors.
- `OffsetDateTime` fits PostgreSQL `TIMESTAMPTZ` columns and preserves offset information when mapped through the driver.
- `@Version` enables optimistic locking when Spring Data R2DBC processes an entity update. Verify exact behavior for the Spring Data version in use.
- Do not accept the entity directly from HTTP requests. DTOs decouple the API contract from the persistence model.

When a new entity is saved, Spring Data can retrieve the generated ID and version and emit the saved entity in the publisher. Always use the entity emitted by `save` rather than assuming the input object was mutated in place.

## 5. Creating the repository

Basic reactive repository:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;
import reactor.core.publisher.Mono;

public interface ProductRepository
        extends ReactiveCrudRepository<Product, Long> {

    Mono<Boolean> existsBySku(String sku);

    Mono<Boolean> existsBySkuAndIdNot(String sku, Long id);
}
~~~

`ReactiveCrudRepository` provides CRUD operations returning `Mono`/`Flux`. Methods like `existsBy...` are parsed by Spring Data into query methods based on property names.

Never call `block()` in a controller or service to unwrap repository results. Compose publishers with `map`, `flatMap`, and `switchIfEmpty`, and return the publisher to WebFlux.

### 5.1. Repositories do not replace database constraints

The service can check the SKU before `INSERT` to return a clear error. However, two concurrent requests can still both see the SKU as non-existent and both issue an `INSERT`. The unique constraint `uk_product_sku` is the final safeguard.

Therefore:

- Check in the service to improve user experience.
- Keep the unique constraint in the database to guarantee correctness.
- Translate the unique violation into HTTP 409 at the appropriate boundary.

## 6. Creating DTOs for requests and responses

The request DTO defines the data clients are allowed to send:

~~~java
import java.math.BigDecimal;

import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record ProductWriteRequest(
    @NotBlank
    @Size(max = 64)
    String sku,
    @NotBlank
    @Size(max = 200)
    String name,
    @Size(max = 4000)
    String description,
    @NotNull
    @DecimalMin(value = "0.00", inclusive = true)
    @Digits(integer = 10, fraction = 2)
    BigDecimal price,
    Boolean active
) {
}
~~~

Rules:

- SKU and name must not be blank.
- SKU is at most 64 characters.
- Name is at most 200 characters.
- Description is at most 4,000 characters.
- Price is required, non-negative, and has at most two decimal places.
- `active` can be omitted; the service defaults it to `true` on creation.

The response DTO avoids exposing persistence objects:

~~~java
import java.math.BigDecimal;
import java.time.OffsetDateTime;

public record ProductResponse(
    Long id,
    String sku,
    String name,
    String description,
    BigDecimal price,
    Boolean active,
    OffsetDateTime createdAt,
    OffsetDateTime updatedAt,
    Long version
) {
    public static ProductResponse from(Product product) {
        return new ProductResponse(
            product.getId(),
            product.getSku(),
            product.getName(),
            product.getDescription(),
            product.getPrice(),
            product.getActive(),
            product.getCreatedAt(),
            product.getUpdatedAt(),
            product.getVersion()
        );
    }
}
~~~

Paginated response:

~~~java
import java.util.List;

public record ProductPageResponse(
    List<ProductResponse> items,
    Long nextAfterId
) {
}
~~~

`nextAfterId` is the last ID of the current page. The client sends this value in the next request. If there are no remaining items, `nextAfterId` is `null`.

## 7. Writing a paginated reader with DatabaseClient

Spring Data reactive repositories suit basic CRUD. For page queries that need explicit SQL, `DatabaseClient` can be used.

~~~java
import java.math.BigDecimal;
import java.time.OffsetDateTime;

import org.springframework.r2dbc.core.DatabaseClient;
import org.springframework.stereotype.Repository;
import reactor.core.publisher.Flux;

@Repository
public class ProductPageReader {

    private final DatabaseClient databaseClient;

    public ProductPageReader(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }

    public Flux<Product> findAfter(long afterId, int pageSize) {
        return databaseClient.sql("""
                SELECT id, sku, name, description, price, active,
                       created_at, updated_at, version
                FROM product
                WHERE id > :afterId
                ORDER BY id
                LIMIT :pageSize
                """)
            .bind("afterId", afterId)
            .bind("pageSize", pageSize)
            .map((row, metadata) -> new Product(
                row.get("id", Long.class),
                row.get("sku", String.class),
                row.get("name", String.class),
                row.get("description", String.class),
                row.get("price", BigDecimal.class),
                row.get("active", Boolean.class),
                row.get("created_at", OffsetDateTime.class),
                row.get("updated_at", OffsetDateTime.class),
                row.get("version", Long.class)
            ))
            .all();
    }
}
~~~

The query uses keyset pagination:

- `id > :afterId` starts after the cursor.
- `ORDER BY id` guarantees order.
- `LIMIT :pageSize` caps the number of rows returned by the database.

Because `id` is the primary key, the cursor order is unique. When sorting by a non-unique column, add a unique key as a tie-breaker in both the cursor predicate and `ORDER BY`.

`Row.get` mappings must use types compatible with the driver. The PostgreSQL R2DBC driver typically maps `NUMERIC` to `BigDecimal`, `TIMESTAMPTZ` to `OffsetDateTime`, and `BIGINT` to `Long`. If your project uses different versions or codecs, adjust converters and integration tests accordingly.

## 8. Building the service and business rules

The service is responsible for:

- Normalizing input at the business level.
- Checking whether the SKU already exists.
- Generating timestamps.
- Looking up the entity before updating or deleting to return 404.
- Updating the entity and invoking the repository.
- Bounding the page size.
- Mapping entities to response DTOs.

~~~java
import java.time.Clock;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.List;

import org.springframework.stereotype.Service;
import reactor.core.publisher.Mono;

@Service
public class ProductService {

    private static final int DEFAULT_PAGE_SIZE = 50;
    private static final int MAX_PAGE_SIZE = 200;

    private final ProductRepository repository;
    private final ProductPageReader pageReader;
    private final Clock clock;

    public ProductService(
            ProductRepository repository,
            ProductPageReader pageReader,
            Clock clock) {
        this.repository = repository;
        this.pageReader = pageReader;
        this.clock = clock;
    }

    public Mono<ProductResponse> create(ProductWriteRequest request) {
        return repository.existsBySku(request.sku())
            .flatMap(exists -> {
                if (exists) {
                    return Mono.error(
                        new ProductSkuConflictException(request.sku())
                    );
                }

                OffsetDateTime now = now();
                Product product = new Product(
                    null,
                    request.sku(),
                    request.name(),
                    request.description(),
                    request.price(),
                    request.active() == null ? true : request.active(),
                    now,
                    now,
                    null
                );

                return repository.save(product)
                    .map(ProductResponse::from);
            });
    }

    public Mono<ProductResponse> findById(Long id) {
        return repository.findById(id)
            .switchIfEmpty(Mono.error(
                new ProductNotFoundException(id)
            ))
            .map(ProductResponse::from);
    }

    public Mono<ProductResponse> update(
            Long id,
            ProductWriteRequest request) {

        return repository.findById(id)
            .switchIfEmpty(Mono.error(
                new ProductNotFoundException(id)
            ))
            .flatMap(product ->
                repository.existsBySkuAndIdNot(request.sku(), id)
                    .flatMap(skuExists -> {
                        if (skuExists) {
                            return Mono.error(
                                new ProductSkuConflictException(request.sku())
                            );
                        }

                        product.setSku(request.sku());
                        product.setName(request.name());
                        product.setDescription(request.description());
                        product.setPrice(request.price());
                        if (request.active() != null) {
                            product.setActive(request.active());
                        }
                        product.setUpdatedAt(now());

                        return repository.save(product);
                    })
            )
            .map(ProductResponse::from);
    }

    public Mono<Void> delete(Long id) {
        return repository.findById(id)
            .switchIfEmpty(Mono.error(
                new ProductNotFoundException(id)
            ))
            .flatMap(repository::delete);
    }

    public Mono<ProductPageResponse> findPage(
            long afterId,
            Integer requestedSize) {

        if (afterId < 0) {
            return Mono.error(
                new IllegalArgumentException("afterId must be non-negative")
            );
        }

        int pageSize = requestedSize == null
            ? DEFAULT_PAGE_SIZE
            : Math.min(Math.max(requestedSize, 1), MAX_PAGE_SIZE);

        return pageReader.findAfter(afterId, pageSize)
            .collectList()
            .map(products -> {
                List<ProductResponse> items = products.stream()
                    .map(ProductResponse::from)
                    .toList();

                Long nextAfterId = products.isEmpty()
                    ? null
                    : products.get(products.size() - 1).getId();

                return new ProductPageResponse(items, nextAfterId);
            });
    }

    private OffsetDateTime now() {
        return OffsetDateTime.ofInstant(clock.instant(), ZoneOffset.UTC);
    }
}
~~~

Declare a `Clock` bean so tests can control time:

~~~java
import java.time.Clock;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class TimeConfiguration {

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }
}
~~~

### 8.1. Why is a unique constraint still needed when the service checks SKU?

Two requests can run `existsBySku` concurrently and both receive `false`. Both then proceed to `INSERT`. Only one request is accepted by the database; the other receives a unique violation.

In production, you must translate the unique violation of constraint `uk_product_sku` into `ProductSkuConflictException` or the corresponding conflict error. This can be classified using SQLSTATE/vendor metadata and constraint names depending on the driver/database. Do not turn every `DataIntegrityViolationException` into an SKU conflict because check constraints or foreign keys carry different meanings.

The service code above illustrates an early check to return a friendly error. The unique constraint remains the mechanism that guarantees correctness.

### 8.2. Optimistic locking under concurrent updates

The entity has `@Version`. Spring Data R2DBC can use the version to update only when the database version matches the version read into the entity. If another request updated the row first, `save` can emit `OptimisticLockingFailureException`.

The API can return `409 Conflict` so the client reloads the data and decides whether to retry the update. If concurrent update control is not needed, the `version` column and `@Version` can be omitted; in that case you must accept last-write-wins or define another policy.

### 8.3. Bounding collectList in pagination

The service uses `collectList`, but the query is already bounded by `LIMIT` and the service caps the page size at 200. This is explicitly bounded materialization, unlike collecting an entire table.

Do not remove `LIMIT` from the SQL just because the service calls `collectList`. Page size must be enforced at both the API layer and the query layer.

## 9. Creating business exceptions

Domain errors should have dedicated types so the error handler can map them to HTTP statuses:

~~~java
public class ProductNotFoundException extends RuntimeException {

    public ProductNotFoundException(Long id) {
        super("Product not found: " + id);
    }
}
~~~

~~~java
public class ProductSkuConflictException extends RuntimeException {

    public ProductSkuConflictException(String sku) {
        super("Product SKU already exists: " + sku);
    }
}
~~~

Never include SQL, bind parameters, passwords, connection URLs, or stack traces in error messages returned to clients. Internal logs may keep the cause according to redaction and access-control policies.

## 10. Building the WebFlux Controller

The controller declares HTTP routes and returns publishers:

~~~java
import java.net.URI;

import jakarta.validation.Valid;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import reactor.core.publisher.Mono;

@RestController
@RequestMapping("/api/products")
public class ProductController {

    private final ProductService service;

    public ProductController(ProductService service) {
        this.service = service;
    }

    @GetMapping
    public Mono<ProductPageResponse> list(
            @RequestParam(defaultValue = "0") long afterId,
            @RequestParam(defaultValue = "50") Integer size) {
        return service.findPage(afterId, size);
    }

    @GetMapping("/{id}")
    public Mono<ProductResponse> findById(@PathVariable Long id) {
        return service.findById(id);
    }

    @PostMapping
    public Mono<ResponseEntity<ProductResponse>> create(
            @Valid @RequestBody ProductWriteRequest request) {
        return service.create(request)
            .map(product -> ResponseEntity
                .created(URI.create("/api/products/" + product.id()))
                .body(product));
    }

    @PutMapping("/{id}")
    public Mono<ProductResponse> update(
            @PathVariable Long id,
            @Valid @RequestBody ProductWriteRequest request) {
        return service.update(id, request);
    }

    @DeleteMapping("/{id}")
    public Mono<ResponseEntity<Void>> delete(@PathVariable Long id) {
        return service.delete(id)
            .thenReturn(ResponseEntity.noContent().build());
    }
}
~~~

WebFlux subscribes to the publisher when handling the request. Never call `subscribe()` or `block()` inside a controller. Subscribing manually detaches the work from the HTTP lifecycle and can lose cancellation propagation, security/transaction context, and request error handling.

### 10.1. Request body validation

`@Valid` triggers Bean Validation on the DTO. When a request is invalid, WebFlux can emit `WebExchangeBindException` during request body resolution. Exact method validation behavior can vary by Spring Framework version; check the actual exception when writing handlers.

API validation does not replace database constraints. Clients can bypass validation or data can be written by batch jobs and other services.

### 10.2. HTTP status meanings

| Case | HTTP status |
|---|---:|
| Read succeeded | 200 OK |
| Create succeeded | 201 Created |
| Update succeeded | 200 OK |
| Delete succeeded | 204 No Content |
| Invalid request | 400 Bad Request |
| Product not found | 404 Not Found |
| SKU already exists | 409 Conflict |
| Optimistic locking conflict | 409 Conflict |
| Unexpected system error | 500 Internal Server Error |

## 11. Standardizing errors with ProblemDetail

Spring Framework 6 supports `ProblemDetail` for returning structured, consistent error responses:

~~~java
import java.util.List;
import java.util.Map;

import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.dao.OptimisticLockingFailureException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;
import org.springframework.web.bind.support.WebExchangeBindException;

@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(ProductNotFoundException.class)
    public ResponseEntity<ProblemDetail> notFound(
            ProductNotFoundException error) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.NOT_FOUND,
            "The requested product does not exist."
        );
        problem.setTitle("Product not found");
        return ResponseEntity.status(HttpStatus.NOT_FOUND).body(problem);
    }

    @ExceptionHandler(ProductSkuConflictException.class)
    public ResponseEntity<ProblemDetail> skuConflict(
            ProductSkuConflictException error) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "A product with the same SKU already exists."
        );
        problem.setTitle("Product SKU conflict");
        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }

    @ExceptionHandler(OptimisticLockingFailureException.class)
    public ResponseEntity<ProblemDetail> concurrentUpdate(
            OptimisticLockingFailureException error) {
        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "The product was changed by another request. Reload and retry."
        );
        problem.setTitle("Concurrent update");
        return ResponseEntity.status(HttpStatus.CONFLICT).body(problem);
    }

    @ExceptionHandler(WebExchangeBindException.class)
    public ResponseEntity<ProblemDetail> validation(
            WebExchangeBindException error) {

        List<Map<String, String>> fieldErrors =
            error.getFieldErrors().stream()
                .map(fieldError -> Map.of(
                    "field", fieldError.getField(),
                    "message", String.valueOf(fieldError.getDefaultMessage())
                ))
                .toList();

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.BAD_REQUEST,
            "One or more request fields are invalid."
        );
        problem.setTitle("Validation failed");
        problem.setProperty("errors", fieldErrors);
        return ResponseEntity.badRequest().body(problem);
    }
}
~~~

In a complete application, add handlers for `IllegalArgumentException` or appropriate query parameter errors. Do not write a catch-all handler that turns every exception into 400; database errors or internal bugs should be recorded as server errors.

### 11.1. Mapping unique violations from the database

Pre-checking the SKU in the service does not eliminate race conditions. When the unique constraint raises an error:

1. Catch the exception at the appropriate persistence/service boundary.
2. Walk the cause chain or driver metadata to inspect SQLSTATE/vendor codes.
3. Confirm it is a unique violation on constraint `uk_product_sku`.
4. Translate it to `ProductSkuConflictException`.
5. Leave other integrity errors intact for separate classification by the handler.

In PostgreSQL, SQLSTATE `23505` indicates a unique violation. If a table has multiple unique constraints, distinguish by constraint name so another violation does not return an SKU conflict message. Exception translation can vary by driver and Spring Data version.

## 12. Transactions in data management features

Single operations such as one `INSERT`, `UPDATE`, or `DELETE` are typically already atomic statements in the database. There is no need to open an explicit transaction just to invoke a single repository method.

When a use case spans multiple operations that must succeed or fail together, use a reactive transaction:

~~~java
import org.springframework.stereotype.Service;
import org.springframework.transaction.reactive.TransactionalOperator;
import reactor.core.publisher.Mono;

@Service
public class ProductImportService {

    private final ProductRepository repository;
    private final TransactionalOperator transactionalOperator;

    public ProductImportService(
            ProductRepository repository,
            TransactionalOperator transactionalOperator) {
        this.repository = repository;
        this.transactionalOperator = transactionalOperator;
    }

    public Mono<Void> importTwoProducts(
            Product first,
            Product second) {

        Mono<Void> work = repository.save(first)
            .then(repository.save(second))
            .then();

        return transactionalOperator.transactional(work);
    }
}
~~~

This example illustrates two write operations inside the same transaction. If the second operation fails, the transaction manager can roll back both. `TransactionalOperator` must be configured with the matching `ReactiveTransactionManager`; Spring Boot typically auto-configures this when a suitable R2DBC `ConnectionFactory` is present.

Never call `block()` or `subscribe()` inside a transaction. The transaction context is propagated via the subscription's Reactor Context. Detaching a publisher with a manual subscription can cause operations to run outside the intended transaction.

### 12.1. Do not hold transactions across slow external calls

Avoid wrapping slow HTTP calls, user waits, or large file processing inside a database transaction unless necessary. Long-running transactions hold connections and can increase lock and snapshot pressure.

If a use case must coordinate the database with a message broker or another service, consider a transactional outbox or saga instead of keeping a transaction open across the entire distributed workflow.

## 13. Adding filtering and searching

When the API needs to filter by `active` status, add an explicit query:

~~~sql
SELECT id, sku, name, description, price, active,
       created_at, updated_at, version
FROM product
WHERE active = :active
  AND id > :afterId
ORDER BY id
LIMIT :pageSize;
~~~

Create a reader method taking `active` and binding it as `Boolean`. If the filter is optional, use two explicit queries or a SQL condition that handles `null`. Avoid concatenating request values directly into SQL.

### 13.1. Searching by name

~~~sql
SELECT id, sku, name, price, active
FROM product
WHERE name ILIKE :pattern
  AND id > :afterId
ORDER BY id
LIMIT :pageSize;
~~~

`ILIKE` is a PostgreSQL extension for case-insensitive search. Consider an appropriate index if the dataset is large; standard B-tree indexes are not optimal for every leading-wildcard pattern. A trigram index may be suitable if the extension and workload justify it.

### 13.2. Do not concatenate SQL strings from input

Do not do this:

~~~java
String sql = "SELECT * FROM product WHERE name = '" + userInput + "'";
~~~

Use bind parameters:

~~~java
databaseClient.sql(
        "SELECT id, name FROM product WHERE name = :name"
    )
    .bind("name", userInput);
~~~

Bind parameters protect data values from being interpreted as SQL syntax. For dynamic column names or sort directions, bind parameters cannot replace identifiers; use an allowlist of options defined in code.

## 14. Pagination API and request/response examples

Fetching the first page:

~~~http
GET /api/products?afterId=0&size=50
Accept: application/json
~~~

Response:

~~~json
{
  "items": [
    {
      "id": 101,
      "sku": "KB-101",
      "name": "Mechanical Keyboard",
      "description": "Compact keyboard",
      "price": 89.90,
      "active": true,
      "createdAt": "2026-11-15T09:00:00Z",
      "updatedAt": "2026-11-15T09:00:00Z",
      "version": 0
    }
  ],
  "nextAfterId": 101
}
~~~

Fetching the next page using the cursor:

~~~http
GET /api/products?afterId=101&size=50
~~~

The cursor is a server-returned value; the client does not need to compute the next ID. If no further rows exist, `items` is an empty array and `nextAfterId` is `null`.

Keyset pagination fits sequential traversal in key order. It does not support jumping directly to page 20 like offset pagination. If the UI requires arbitrary page jumping, consider offset pagination or a dedicated cursor/index strategy.

## 15. Testing the API over HTTP

### 15.1. Creating a product

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{
    "sku": "KB-101",
    "name": "Mechanical Keyboard",
    "description": "Compact mechanical keyboard",
    "price": 89.90,
    "active": true
  }'
~~~

The expected result is `201 Created`, a `Location` header pointing to `/api/products/{id}`, and a response containing the database-generated ID.

### 15.2. Reading details

~~~bash
curl -i http://localhost:8080/api/products/101
~~~

If the ID does not exist, the API returns `404 Not Found` with a `ProblemDetail`.

### 15.3. Updating

~~~bash
curl -i -X PUT http://localhost:8080/api/products/101 \
  -H "Content-Type: application/json" \
  -d '{
    "sku": "KB-101",
    "name": "Mechanical Keyboard Pro",
    "description": "Updated model",
    "price": 99.90,
    "active": true
  }'
~~~

If the version in the database changed after the entity was read, optimistic locking can raise a conflict. The client should reload the latest state before retrying the update.

### 15.4. Deleting

~~~bash
curl -i -X DELETE http://localhost:8080/api/products/101
~~~

The success result is `204 No Content`.

### 15.5. Validation failure

~~~bash
curl -i -X POST http://localhost:8080/api/products \
  -H "Content-Type: application/json" \
  -d '{
    "sku": "",
    "name": "",
    "price": -10
  }'
~~~

The result is `400 Bad Request` with a list of field errors. Invalid requests are not written to the database.

## 16. Testing the service and repository

Testing should be split between unit tests for logic and integration tests for mapping, SQL, and driver behavior.

### 16.1. Unit testing the service with StepVerifier

With a mocked repository, you can verify that the service emits the right error when the SKU already exists:

~~~java
import java.math.BigDecimal;
import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;

import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import reactor.core.publisher.Mono;
import reactor.test.StepVerifier;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

@ExtendWith(MockitoExtension.class)
class ProductServiceTest {

    @Mock
    ProductRepository repository;

    @Mock
    ProductPageReader pageReader;

    @Test
    void rejectsDuplicateSku() {
        Clock clock = Clock.fixed(
            Instant.parse("2026-11-15T09:00:00Z"),
            ZoneOffset.UTC
        );

        ProductService service = new ProductService(
            repository, pageReader, clock
        );

        ProductWriteRequest request = new ProductWriteRequest(
            "KB-101",
            "Keyboard",
            null,
            new BigDecimal("89.90"),
            true
        );

        when(repository.existsBySku("KB-101"))
            .thenReturn(Mono.just(true));

        StepVerifier.create(service.create(request))
            .expectError(ProductSkuConflictException.class)
            .verify();

        verify(repository, never()).save(any());
    }
}
~~~

This unit test verifies the business branch and confirms `save` is not called when the pre-check detects a duplicate. It does not test the PostgreSQL unique constraint or actual database exceptions.

### 16.2. Testing page size clamping in pagination

Mock `ProductPageReader` to return a small number of rows, call the service with a size above the limit, and verify that the reader receives the maximum size. Unit tests protect the clamping rule in the service; integration tests must confirm the SQL actually applies `LIMIT`.

## 17. Integration testing with real PostgreSQL

Mapping, SQL dialect, identity generation, constraints, and optimistic locking must be tested against a compatible database. PostgreSQL Testcontainers is one option.

Example container configuration:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.DynamicPropertyRegistry;
import org.springframework.test.context.DynamicPropertySource;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.testcontainers.containers.PostgreSQLContainer;
import org.testcontainers.junit.jupiter.Container;
import org.testcontainers.junit.jupiter.Testcontainers;

@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
@Testcontainers
class ProductApiIntegrationTest {

    @Container
    static PostgreSQLContainer<?> postgres =
        new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.r2dbc.url", () ->
            "r2dbc:postgresql://" + postgres.getHost()
                + ":" + postgres.getFirstMappedPort()
                + "/" + postgres.getDatabaseName()
        );
        registry.add("spring.r2dbc.username", postgres::getUsername);
        registry.add("spring.r2dbc.password", postgres::getPassword);
    }

    @Autowired
    WebTestClient webTestClient;

    @Test
    void createsAndReadsProduct() {
        String body = """
            {
              "sku": "KB-101",
              "name": "Mechanical Keyboard",
              "description": "Compact keyboard",
              "price": 89.90,
              "active": true
            }
            """;

        webTestClient.post()
            .uri("/api/products")
            .header("Content-Type", "application/json")
            .bodyValue(body)
            .exchange()
            .expectStatus().isCreated()
            .expectHeader().exists("Location")
            .expectBody()
            .jsonPath("$.id").exists()
            .jsonPath("$.sku").isEqualTo("KB-101");
    }
}
~~~

This test demonstrates dynamic R2DBC URL configuration. Schema migrations must run before the test. If using Flyway, configure the corresponding dynamic JDBC URL/credentials and add the JDBC driver plus the appropriate Flyway database module. Do not assume JDBC configuration automatically configures R2DBC.

### 17.1. Integration scenarios to cover

- `INSERT` a new entity and verify the generated ID.
- Read back the written row.
- Unique constraint rejects a duplicate SKU.
- Check constraint rejects a negative price when written directly via a database path.
- `findById` returns empty when absent.
- Update changes `updated_at` and `version`.
- Two concurrent updates produce an optimistic locking conflict as configured.
- Delete succeeds and subsequent read returns 404.
- Keyset pages neither duplicate nor skip IDs over static data.
- Page size never exceeds the limit.
- Query errors/timeouts return connections to the pool.

### 17.2. Testing API validation and ProblemDetail

Send a request missing SKU or with a negative price and verify:

- HTTP status is 400.
- Response has the expected content type/problem structure.
- Validation field errors are present.
- No corresponding row exists in the database.

Send an existing SKU and verify 409. For race conditions, include a database-level unique constraint test or concurrency test to ensure only one request creates the row.

## 18. Testing cursor pagination correctness

Given static data with IDs 1 through 5 and page size 2:

| Request | Rows returned | Next cursor |
|---|---|---:|
| afterId=0 | 1, 2 | 2 |
| afterId=2 | 3, 4 | 4 |
| afterId=4 | 5 | 5 |
| afterId=5 | None | null |

Tests should loop through pages until `items` is empty and verify:

- Every ID appears exactly once.
- Order is ascending.
- Each page does not exceed the maximum size.
- Each cursor equals the last ID of the preceding page.

Keyset pagination avoids large `OFFSET` costs, but it does not automatically guarantee a consistent snapshot if rows are updated or deleted while the client fetches multiple pages. For exports needing a snapshot, add a cutoff/version or a dedicated snapshot mechanism.

## 19. Securing the API and data

The example leaves out Spring Security configuration to focus on the data flow. In a real deployment, define:

- Who can read lists and details?
- Who can create, update, or delete?
- Is access scoped by tenant or owner?
- Must SKU be globally unique or unique per tenant?
- Are actor and timestamp auditing required?
- Are rate limits or quotas needed for list/export endpoints?

Never trust `tenantId`, `createdBy`, `role`, or `ownerId` sent by the client in the request body. Obtain identity and tenant from the authenticated security context and enforce authorization at service/query boundaries.

Never return stack traces, SQL, bind values, database hostnames, credentials, or tokens in `ProblemDetail`. Internal logs need structured logging, redaction, and correlation IDs.

### 19.1. Pagination is also a resource limit

The API must enforce a maximum page size and may add per-user/per-tenant quotas. Never let a client request `size=1000000` and materialize a massive response. For large datasets, provide a dedicated export job.

## 20. Observability and operations

A CRUD feature needs sufficient metrics to detect failures:

- HTTP request rate, 4xx/5xx counts, and p95/p99 latency.
- R2DBC pool acquired, idle, pending acquire, and acquire timeouts.
- Query/operation duration by operation name.
- Database exception categories and retry counts.
- Transaction duration/rollbacks if applicable.
- JVM heap, allocation rate, and GC pauses.

Operation names should be constants such as `product.create`, `product.find-by-id`, and `product.list-page`; never use product ID or SKU as metric tags. Do not log full bind parameters, as they may contain sensitive data.

If pool pending acquires rise, inspect queries/transactions holding connections too long, replica counts, and total pool capacity. If query latency increases, inspect database execution plans, lock waits, and indexes. If HTTP responses are slow while SQL is fast, inspect mapping, downstream calls, and the network.

## 21. Common pitfalls when building from schema to API

| Pitfall | Consequence | Fix |
|---|---|---|
| Creating entities before agreeing on the schema | Column names/types mismatch | Design migrations and mappings together |
| No versioned migrations | Dev/test/prod schemas drift | Manage DDL with Flyway/Liquibase or an equivalent tool |
| Validating only in the controller | Other writers can persist invalid data | Combine API validation with database constraints |
| Checking SKU only with SELECT | Race condition creates duplicate SKUs | Enforce unique constraint and map unique violations |
| Using double for price | Monetary rounding errors | Use BigDecimal and NUMERIC |
| Using entities as request/response models | Clients can modify internal fields | Use dedicated DTOs |
| Calling block() in WebFlux | Blocks threads and loses reactive benefits | Compose publishers and return them to the caller |
| Calling subscribe() in the service | Detaches work from the request lifecycle | Return the publisher and let the framework subscribe |
| Calling findAll().collectList() | Heap grows with the entire table | Use SQL LIMIT/keyset pages or bounded streaming |
| Paginating with an unstable cursor | Duplicate or skipped rows | Use a unique ordering with a tie-breaker |
| Skipping optimistic locking | Last-write-wins can overwrite changes | Use @Version when the domain requires it |
| Mapping all DB errors to 400 | Hides server failures | Classify errors by root cause |
| Returning exception messages to clients | Leaks SQL or internal details | Use ProblemDetail with safe messages |
| Holding transactions across slow HTTP calls | Ties up connections and transactions | Shorten transactions; use workflows/outbox |
| Testing only with mocks | Misses dialect/codec/constraint bugs | Write integration tests against real PostgreSQL |
| Not verifying generated IDs | Clients receive entities without IDs or broken mappings | Test INSERT and read back from the database |
| Sizing pools for a single pod | Scaling replicas exceeds DB limits | Calculate total pool size at peak replica count |

## 22. End-to-end implementation sequence

A practical workflow can follow these steps:

1. **Finalize requirements:** define fields, validation, uniqueness, update/delete semantics, and API status codes.
2. **Design the schema:** choose data types, primary key, unique/check constraints, and indexes.
3. **Create migrations:** write versioned DDL and run it on a test database.
4. **Configure R2DBC:** URL, credentials, pool size, and timeouts per environment.
5. **Create entities:** explicit mappings, appropriate Java types, and a version field if needed.
6. **Create repositories:** use reactive CRUD and derived queries for simple operations.
7. **Create query readers:** use `DatabaseClient` for custom page/filter SQL.
8. **Create DTOs:** separate request/response models and declare Bean Validation rules.
9. **Write the service:** business rules, timestamps, not-found, conflict, and page limits.
10. **Write the controller:** HTTP routes, request binding, and returning `Mono`/`Flux`.
11. **Standardize errors:** `ProblemDetail`, 400/404/409/500, and no database detail leaks.
12. **Write unit tests:** validation branches, business rules, and publisher signals.
13. **Write integration tests:** migrations, mapping, generated IDs, constraints, pagination, and transactions on PostgreSQL.
14. **Load test and observe:** pool behavior, latency, heap usage, and concurrent requests.
15. **Deploy:** run migrations before rollout, verify health/metrics, and prepare rollback plans.

## 23. Feature completion checklist

| Item | Completion criteria |
|---|---|
| Schema | Primary key, data types, and constraints are correct |
| Migration | Versioned, repeatable per tool history, and controlled |
| R2DBC config | Credentials from secrets, bounded pool/timeouts |
| Entity | Mapping matches schema; ID and version are correct |
| Repository | No blocking calls |
| Custom query | Explicit bind parameters, projections, and LIMIT |
| Service | Business rules and not-found/conflict cases handled |
| DTO | Separate validation and response contracts |
| Controller | Correct HTTP methods/statuses, returns publishers |
| Error handler | Safe ProblemDetail, no SQL/secret leaks |
| Transaction | Clear boundaries, not held across slow external work |
| Tests | Unit and PostgreSQL integration tests |
| Observability | HTTP, pool, query, error, and JVM metrics |
| Security | Authentication, authorization, and tenant scope defined |
| Deployment | Migrations before app, pool budget sized for peak replicas |

## 24. Key takeaways

- Start from requirements and the API contract, then design the schema and migrations before mapping entities.
- Use database primary keys and unique/check constraints as the final layer of data protection.
- Use versioned migrations and keep schema deployments compatible with running code.
- Use nullable `Long` for new identities, `BigDecimal` for money, and PostgreSQL-compatible time types.
- Keep entities separate from request and response DTOs.
- Use `ReactiveCrudRepository` for basic CRUD and `DatabaseClient` when SQL control is needed.
- Never call `block()` or `subscribe()` inside reactive controllers or services.
- Check SKU uniqueness in the service for early feedback, while keeping the unique constraint to prevent race conditions.
- Use `@Version` when concurrent update detection is needed.
- Enforce page size limits in both the service and SQL; keyset cursors require deterministic ordering.
- `collectList` is only appropriate when the query is explicitly bounded.
- Use `ProblemDetail` for safe error responses and clearly distinguish 400, 404, 409, and 500.
- Open reactive transactions only when multiple operations require atomicity; avoid holding connections across slow network calls.
- Test against real PostgreSQL to verify driver codecs, identity generation, SQL, constraints, and transactions.
- Monitor HTTP latency/errors, R2DBC pool metrics, query duration, retries, and JVM memory.
- Budget pool sizes across total replicas, all pools, and rollout surges before scaling.

A complete data management feature comes from consistency across schema, mapping, business rules, and the HTTP contract. PostgreSQL constraints protect the data, Spring Data R2DBC manages reactive persistence, the service enforces business rules, and WebFlux provides a non-blocking API. Controlled migrations, bounded pagination, safe error handling, and integration tests against a real database keep the feature reliable as data volume, traffic, and replica counts grow.
