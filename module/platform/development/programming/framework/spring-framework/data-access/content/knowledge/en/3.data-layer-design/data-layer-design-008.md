# Keeping SQL and Driver Details Out of the Presentation Layer

## 1. Lesson Objectives

In a Spring application, the presentation layer can be a REST controller serving web/mobile clients, a server-rendered view, or a GraphQL adapter. This layer needs to know **what the user requested, which data may be returned, and which business error codes to display**. It does not need to know SQL statements, table/column names, `ResultSet`, `SQLException`, JDBC URLs, or PostgreSQL/MySQL drivers.

After this lesson, you will be able to:

- Recognize forms of storage-detail leakage from controllers, JSON responses, exceptions, logs, and API contracts.
- Separate responsibilities cleanly across controllers, application services, repositories/DAOs, databases, and drivers; choose the right data types crossing each boundary.
- Write a Spring Boot example using `JdbcTemplate` where SQL stays inside the data adapter while the controller interacts only with services and DTOs.
- Translate database failures into stable business outcomes and HTTP responses without leaking SQL, vendor error codes, stack traces, or connection settings to clients.
- Test boundaries so that later swapping JDBC for JPA or switching DBMSs does not force API contract changes due to storage details.

**Core principle:** the presentation layer depends on the **application contract** (use cases, DTOs, public error codes), while queries and drivers live in the **data access infrastructure**.

## 2. Why Is a Clear Boundary Needed?

Imagine a UI calling `POST /api/products` to create a product. If the controller executes SQL directly and returns raw `SQLException.getMessage()`, the browser may see the `products` table name, constraint names, database address, SQL strings, operational details, and internal schema structure. Even when that information contains no secrets, the UI becomes coupled to a specific storage layout, making schema changes likely to break the API.

Several problems usually appear together:

1. **Coupling:** controllers change alongside tables/columns or DB technologies; swapping `JdbcTemplate` for JPA/R2DBC becomes hard.
2. **Hard to test:** testing a simple HTTP rule ends up requiring a running DB, driver setup, and seed data.
3. **Errors and security:** SQL, stack traces, and driver exceptions can get serialized to clients; string-concatenated SQL invites SQL injection.
4. **Missing business rules:** controllers touching the DB directly easily bypass transactions, authorization, data normalization, or state-transition policies managed by services.
5. **Hard to maintain contracts:** changing a `ResultSet`, entity, column name, or driver error message can break the UI even when business behavior is unchanged.

A sound boundary enables change and isolates failures. It does **not** mean adding interfaces to every class or inventing a custom framework: for a small application, one focused repository and one use-case service are usually plenty.

## 3. Desired Dependency and Data Flow

```text
Browser / Mobile / Frontend
    |
    | HTTP + JSON: CreateProductRequest, ProductResponse, stable error codes
    v
ProductController                     [Presentation]
    |
    | Calls createProduct(...), getProduct(...)
    v
CatalogService                        [Application / use case]
    |
    | ProductStore + application domain types
    v
ProductStore (interface)              [Data access port]
    ^
    | implements
    |
JdbcProductStore                      [Infrastructure]
    |
    | JdbcTemplate -> DataSource -> JDBC driver -> SQL
    v
PostgreSQL
```

Data and exceptions permitted to cross each boundary:

| Boundary | Should cross | Should not cross |
| --- | --- | --- |
| Frontend ↔ Controller | JSON DTOs, HTTP statuses, stable error codes, request ID | SQL, `SQLException`, JDBC URL, constraint names, driver stack traces |
| Controller ↔ Service | Use-case inputs, domain/application results, business errors | `ResultSet`, `Connection`, `EntityManager`, SQL statements |
| Service ↔ Repository port | Methods like `create`, `findById`; domain objects | Dynamic SQL from UI, vendor exceptions |
| Repository adapter ↔ DB | SQL, bound parameters, row mapping, transaction resources | Display contracts and UI wording |

**Key dependency direction:** the controller calls the service; the service uses an interface describing persistence capabilities per application needs; the JDBC adapter implements that interface. The service does not need to import `org.postgresql.*`, `java.sql.ResultSet`, `JdbcTemplate`, or `SQLException`. Spring injects the matching adapter via dependency injection.

A DTO that happens to share field names with DB columns is still an **intentional public DTO** as long as you control it. By contrast, returning raw `Map<String, Object>` from `queryForList` turns column names, JDBC types, and schema into an implicit client contract.

## 4. Bad Smell: SQL and Driver Errors in the Controller

The following is an **anti-pattern for analysis; never use it in a real application**:

```java
// Flawed illustration: DO NOT use in a real system.
@GetMapping("/api/products")
public Object products(@RequestParam String sku) {
    try {
        String sql =
            "SELECT * FROM products WHERE sku = '" + sku + "'";
        return jdbcTemplate.queryForList(sql);
    } catch (Exception ex) {
        return ex.getMessage();
    }
}
```

There are at least five bugs here:

- The controller writes SQL itself and depends on `JdbcTemplate`, violating responsibility boundaries.
- Concatenating `sku` directly into SQL causes SQL injection; quotes in input data can also break syntax.
- `SELECT *` combined with returning raw `Map`s can expose internal columns such as `cost_price`, `deleted_at`, or newly added schema fields.
- Returning `ex.getMessage()` turns DB vendor messages into public output, potentially exposing SQL, table/column names, constraints, or connection details.
- Returning an error string as a normal response breaks HTTP semantics: clients may receive `200 OK` even though the query failed.

Moving the SQL into a `private` helper inside the controller itself **does not** solve the boundary: the controller still knows query syntax, DB constraints, and data error handling. Similarly, merely switching `JdbcTemplate` to calling `JpaRepository` directly from the controller still couples the UI to persistence APIs and risks bypassing use-case rules.

## 5. Designing the Application Contract Before Choosing SQL

Example product management API:

- `POST /api/products` accepts `sku`, `name`, `price`; returns `201 Created` with the product DTO on success.
- `GET /api/products/{id}` returns the product or `404 Not Found` if absent.
- `sku` is unique per business rules; duplicate creation returns `409 Conflict` with `code = SKU_ALREADY_USED`.
- Invalid request data returns `400 Bad Request` with `code = INVALID_INPUT`.
- Unexpected DB access failures return `500` with a neutral message; details are recorded only in internal observability systems.

The UI can rely on these statuses and error codes, **without** depending on `SQLSTATE 23505`, `PSQLException`, `DuplicateKeyException`, or the `uq_products_sku` constraint name.

Example success JSON (ID is illustrative; never hard-code it in the application):

```json
{
  "id": 17,
  "sku": "BK-001",
  "name": "Spring Book",
  "price": 129000.00
}
```

Example duplicate-SKU response formatted as `ProblemDetail` (RFC 9457; server may add `instance`):

```json
{
  "type": "about:blank",
  "title": "Conflict",
  "status": 409,
  "detail": "Product SKU is already in use.",
  "code": "SKU_ALREADY_USED"
}
```

A message intended for the UI must be stable and business-appropriate. Not every `DataIntegrityViolationException` means "SKU already exists": it might be an FK, NOT NULL, CHECK, or schema mismatch. Translate a violation into a specific error only once the exact invariant has been identified.

## 6. Implementation Example: Spring Boot 3.x + Java 17+ + PostgreSQL

This is a small application example containing all the main boundaries. The Java files below share package `demo.catalog`; the project requires Spring Boot 3.x, Spring Web MVC, Spring JDBC, Bean Validation, the PostgreSQL driver, and a configured `DataSource`. The SQL uses PostgreSQL-specific `INSERT ... ON CONFLICT ... RETURNING`; because that syntax lives solely inside `JdbcProductStore`, switching DBMSs does not require changing the frontend contract.

### 6.1. Build Dependencies and Schema

Add these dependencies inside `dependencies { ... }` of a Gradle Spring Boot project configured with plugins and Java 17+:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.flywaydb:flyway-core'
    runtimeOnly 'org.flywaydb:flyway-database-postgresql'
    runtimeOnly 'org.postgresql:postgresql'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}
```

Create `src/main/resources/db/migration/V1__create_products.sql`:

```sql
CREATE TABLE products (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    sku VARCHAR(64) NOT NULL,
    name VARCHAR(200) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    CONSTRAINT uq_products_sku UNIQUE (sku),
    CONSTRAINT ck_products_price CHECK (price >= 0)
);
```

`UNIQUE (sku)` in the database is the ultimate enforcement point even when two requests create the same SKU concurrently. HTTP-level validation improves error messages, yet cannot guarantee uniqueness under a race condition. To keep the example focused, SKU normalization policies (case, whitespace, Unicode) should be decided consistently at the use case and DB if required by the business.

Connection configuration belongs to the server environment, such as `SPRING_DATASOURCE_URL`, `SPRING_DATASOURCE_USERNAME`, and `SPRING_DATASOURCE_PASSWORD` supplied to the application. Never place passwords, internal JDBC URLs, or driver names into browser JavaScript or API JSON. Flyway executes migrations on startup when properly configured.

### 6.2. Domain Object Independent of JDBC/JPA

`src/main/java/demo/catalog/Product.java`:

```java
package demo.catalog;

import java.math.BigDecimal;

public record Product(
        long id,
        String sku,
        String name,
        BigDecimal price
) {}
```

This is a plain Java type with no `@Entity`, `ResultSet`, or `Connection`. It represents the information the application needs in the use case. In a larger system, the domain model may hold more invariants/behavior than a `record`; choose the structure matching real complexity.

### 6.3. Port Defining Storage Capabilities

`src/main/java/demo/catalog/ProductStore.java`:

```java
package demo.catalog;

import java.math.BigDecimal;
import java.util.Optional;

public interface ProductStore {
    Product insert(String sku, String name, BigDecimal price);

    Optional<Product> findById(long id);
}
```

The service asks only to "insert a product" and "find a product". The interface does not force callers to know how connections are acquired, how rows are mapped, or what query dialect is used. Another adapter can use JPA or an alternative store as long as it preserves the same semantics.

### 6.4. DB-Independent Business Exceptions

`src/main/java/demo/catalog/CatalogErrors.java`:

```java
package demo.catalog;

public final class CatalogErrors {
    private CatalogErrors() {}

    public static final class SkuAlreadyUsed extends RuntimeException {}

    public static final class ProductMissing extends RuntimeException {}
}
```

These two error types express **what the application chooses to surface**, without carrying `SQLException` or vendor codes. Class names can follow project conventions; what the client sees is the HTTP status and `code` field defined by the web layer.

### 6.5. JDBC Adapter Owns All SQL

`src/main/java/demo/catalog/JdbcProductStore.java`:

```java
package demo.catalog;

import java.math.BigDecimal;
import java.util.List;
import java.util.Optional;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.stereotype.Repository;

@Repository
public class JdbcProductStore implements ProductStore {

    private static final RowMapper<Product> PRODUCT_MAPPER =
            (rs, rowNumber) -> new Product(
                    rs.getLong("id"),
                    rs.getString("sku"),
                    rs.getString("name"),
                    rs.getBigDecimal("price")
            );

    private final JdbcTemplate jdbc;

    public JdbcProductStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    @Override
    public Product insert(String sku, String name, BigDecimal price) {
        List<Product> inserted = jdbc.query(
                """
                INSERT INTO products (sku, name, price)
                VALUES (?, ?, ?)
                ON CONFLICT (sku) DO NOTHING
                RETURNING id, sku, name, price
                """,
                PRODUCT_MAPPER,
                sku,
                name,
                price
        );

        return inserted.stream()
                .findFirst()
                .orElseThrow(CatalogErrors.SkuAlreadyUsed::new);
    }

    @Override
    public Optional<Product> findById(long id) {
        List<Product> products = jdbc.query(
                """
                SELECT id, sku, name, price
                FROM products
                WHERE id = ?
                """,
                PRODUCT_MAPPER,
                id
        );
        return products.stream().findFirst();
    }
}
```

**Key mechanisms:**

1. `JdbcTemplate` and `RowMapper` appear only inside the adapter. The JDBC driver executes SQL and talks to PostgreSQL, yet controllers and services never see JDBC types.
2. `?` with bound parameters protects input data from being interpreted as SQL syntax. Never concatenate `sku` directly into `WHERE` or `INSERT`.
3. `ON CONFLICT (sku) DO NOTHING` handles conflicts strictly on the `sku` unique key. `RETURNING` returns the newly inserted row; on an SKU conflict, the result is empty and the adapter throws `SkuAlreadyUsed`. This is a grounded business decision, avoiding labeling every UNIQUE error as a duplicate SKU.
4. For any other DB failure (exhausted connections, wrong schema, unvalidated CHECK violation...), `JdbcTemplate` translates the JDBC error into Spring's `DataAccessException` hierarchy via its translator. Unexpected infrastructure errors are not mislabeled as `SkuAlreadyUsed`.
5. When migrating from PostgreSQL to another DBMS, change the SQL and generated-key retrieval **inside the adapter**. Neither `ProductStore`, use cases, nor the JSON contract change if business semantics stay the same.

`@Repository` registers a Spring-managed bean and supports exception translation infrastructure for appropriate DAOs; `JdbcTemplate` itself already translates `SQLException` to `DataAccessException`. There is no need to manually `catch (SQLException)` and return error strings.

### 6.6. Service Holds Use Cases and Transactions

`src/main/java/demo/catalog/CatalogService.java`:

```java
package demo.catalog;

import java.math.BigDecimal;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CatalogService {

    private final ProductStore store;

    public CatalogService(ProductStore store) {
        this.store = store;
    }

    @Transactional
    public Product create(String sku, String name, BigDecimal price) {
        return store.insert(sku, name, price);
    }

    @Transactional(readOnly = true)
    public Product get(long id) {
        return store.findById(id)
                .orElseThrow(CatalogErrors.ProductMissing::new);
    }
}
```

The service depends on `ProductStore` and contains no SQL. It is the right place to coordinate multiple repository operations, authorization, business policies, and transactions. When an unchecked exception escapes a `@Transactional` method invoked through a Spring proxy under standard setup, the transaction rolls back by default. Avoid assuming self-calls like `this.create(...)` within the same bean go through the proxy. Add transactions only where consistency requires them; in this example it shows where transactions sit once future use cases add more operations.

If the service must create both a product and an audit record in one transaction, both commit or roll back together. The controller receives only the final outcome and never needs to know about commits, connections, or isolation levels.

### 6.7. Controller Works with DTOs and HTTP

`src/main/java/demo/catalog/CatalogController.java`:

```java
package demo.catalog;

import java.math.BigDecimal;
import java.net.URI;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/products")
public class CatalogController {

    public record CreateProductRequest(
            @NotBlank @Size(max = 64) String sku,
            @NotBlank @Size(max = 200) String name,
            @NotNull @DecimalMin("0.00")
                @Digits(integer = 10, fraction = 2) BigDecimal price
    ) {}

    public record ProductResponse(
            long id, String sku, String name, BigDecimal price
    ) {
        public static ProductResponse from(Product product) {
            return new ProductResponse(
                    product.id(),
                    product.sku(),
                    product.name(),
                    product.price()
            );
        }
    }

    private final CatalogService service;

    public CatalogController(CatalogService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<ProductResponse> create(
            @Valid @RequestBody CreateProductRequest request
    ) {
        Product product = service.create(
                request.sku(),
                request.name(),
                request.price()
        );
        URI location = URI.create("/api/products/" + product.id());
        return ResponseEntity.created(location)
                .body(ProductResponse.from(product));
    }

    @GetMapping("/{id}")
    public ProductResponse get(@PathVariable long id) {
        return ProductResponse.from(service.get(id));
    }
}
```

The controller imports HTTP/validation types and the service; **it does not import JDBC, JPA, drivers, `DataSource`, or `java.sql`**. `CreateProductRequest` carries constraints to fail fast; the DB still has `NOT NULL`, `UNIQUE`, and `CHECK` to protect consistency across all write paths. `ProductResponse` is constructed explicitly, so adding a sensitive column to the table will not automatically expose it in JSON.

Avoid returning JPA `@Entity` objects directly from controllers: entities may hold internal fields, lazy links, proxies, bidirectional cycles, or fields outside the API contract. Use explicit DTOs/projections to govern public data.

### 6.8. Translating Errors into Safe ProblemDetails

`src/main/java/demo/catalog/ApiErrorHandler.java`:

```java
package demo.catalog;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.dao.DataAccessException;
import org.springframework.http.HttpStatus;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ApiErrorHandler {

    private static final Logger log =
            LoggerFactory.getLogger(ApiErrorHandler.class);

    @ExceptionHandler(CatalogErrors.SkuAlreadyUsed.class)
    public ResponseEntity<ProblemDetail> duplicateSku() {
        return issue(
                HttpStatus.CONFLICT,
                "SKU_ALREADY_USED",
                "Product SKU is already in use."
        );
    }

    @ExceptionHandler(CatalogErrors.ProductMissing.class)
    public ResponseEntity<ProblemDetail> missingProduct() {
        return issue(
                HttpStatus.NOT_FOUND,
                "PRODUCT_NOT_FOUND",
                "Product not found."
        );
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ProblemDetail> invalidInput() {
        return issue(
                HttpStatus.BAD_REQUEST,
                "INVALID_INPUT",
                "Invalid request data."
        );
    }

    @ExceptionHandler(DataAccessException.class)
    public ResponseEntity<ProblemDetail> unexpectedStorage(
            DataAccessException failure
    ) {
        log.error("Unexpected persistence failure", failure);
        return issue(
                HttpStatus.INTERNAL_SERVER_ERROR,
                "UNEXPECTED_STORAGE_ERROR",
                "Unable to process the request at this time."
        );
    }

    private static ResponseEntity<ProblemDetail> issue(
            HttpStatus status, String code, String message
    ) {
        ProblemDetail problem =
                ProblemDetail.forStatusAndDetail(status, message);
        problem.setTitle(status.getReasonPhrase());
        problem.setProperty("code", code);
        return ResponseEntity.status(status).body(problem);
    }
}
```

The HTTP layer knows `SkuAlreadyUsed`, `ProductMissing`, and validation errors; it never needs to inspect `PSQLException`, `SQLState`, or driver error strings to pick a status code. The `DataAccessException` handler acts solely as a safety net with a neutral message. Detailed server logs should enforce access control, mask sensitive data, and include correlation/request IDs in observability systems; never automatically forward stack traces or raw SQL to client telemetry.

**Example scope note:** the handler covers the listed errors; a real system also needs a safe fallback rule for other unexpected errors and standard Spring MVC error handling aligned with the project's API policy. Never `catch (Exception)` and always return `200`, or map every error to `409`.

### 6.9. Spring Boot Entry Point

`src/main/java/demo/catalog/CatalogApplication.java`:

```java
package demo.catalog;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CatalogApplication {
    public static void main(String[] args) {
        SpringApplication.run(CatalogApplication.class, args);
    }
}
```

This is Spring Boot code requiring the corresponding libraries and DB; it cannot run standalone with `javac CatalogApplication.java` alone. In a Gradle project configured with the Spring Boot plugin, provide PostgreSQL and the `SPRING_DATASOURCE_*` environment variables to the application process and run:

```bash
./gradlew bootRun
```

On Windows, use `gradlew.bat bootRun`. On the first run against an empty database with Flyway enabled, migrations create the table before the controller accepts requests. Endpoints can be called with an HTTP client or `curl`, for example:

```bash
curl -i -X POST http://localhost:8080/api/products \
  -H 'Content-Type: application/json' \
  -d '{"sku":"BK-001","name":"Spring Book","price":129000.00}'

curl -i http://localhost:8080/api/products/1
```

The `GET` for ID `1` succeeds only if that record actually exists; do not assume IDs from the example. A successful `POST` returns `201` with `Location` pointing to the product URI and `ProductResponse` in the body. Resubmitting the same SKU returns `409` and code `SKU_ALREADY_USED`, with no SQL in the response body.

## 7. Distinguishing Technical Errors from Business Errors

| Event | Handling in infrastructure/service | Presentation response |
| --- | --- | --- |
| SKU already exists | PostgreSQL `ON CONFLICT (sku)` or identifying exact unique constraint; translate to `SkuAlreadyUsed` | `409`, `SKU_ALREADY_USED` |
| Queried ID does not exist | Repository returns `Optional.empty()`; service throws `ProductMissing` | `404`, `PRODUCT_NOT_FOUND` |
| Missing input / negative price | DTO validation and DB constraints | `400`, `INVALID_INPUT` |
| DB connection lost, bad SQL, resource failure | `DataAccessException`; internal log/metrics | `500` or `503` per policy; generic error code |
| Deadlock / serialization conflict | Bounded retry policy and idempotency at the proper layer | Stable meaningful error, no `SQLSTATE` leaked |
| Other business error, such as unauthorized action | Determined by service/policy; not derived from table names | `403`/`409` per API contract |

`DataAccessException` is a Spring exception family that reduces vendor coupling. It is **still** a data-layer concept; avoid inspecting `SQLException` deeply or relying on `getMessage()` in controllers. If a large project wants presentation completely decoupled even from `DataAccessException`, translate unexpected infrastructure failures into a generic application exception in the adapter/service and handle it centrally at the web layer. Either way, preserve the root cause in logs and ensure transaction rollback.

**Never mask all errors behind a single log message:** clients see a neutral message, while operators still need to know which DB error occurred, which request was affected, timestamps, exception chains, constraint names, and safe query paths to troubleshoot incidents. Never write passwords or bind parameters containing sensitive data into unguarded logs.

## 8. Transactions Are Not the Presentation Layer's Responsibility

Controllers should never:

- Manually call `connection.setAutoCommit(false)`, `commit()`, or `rollback()`.
- Open a `Connection` and pass it through DTOs/services or hold connections across browser sessions.
- Manually "retry" a side-effecting SQL statement simply upon receiving a driver error message.
- Catch persistence exceptions and turn them into returned strings, making failures look like success.

A use case writing to multiple tables must place its transaction on the service or an equivalent application boundary. When the service uses a JDBC repository backed by `JdbcTemplate` and a properly configured transaction manager, operations join the same transaction. Unchecked exceptions escaping the `@Transactional` proxy trigger rollback by default. If a service catches an error and returns success anyway, review rollback behavior: partial data may commit or a PostgreSQL transaction may already be in an aborted state.

For retries, base decisions on business semantics (idempotency keys, optimistic locks, retryable conflicts, max attempt limits) in the service/infrastructure, never letting the frontend guess from `SQLSTATE 40001` or vendor codes. The frontend may retry a request **per the public contract** when the server declares safe retryability.

## 9. Do the Principles Change When Using Spring Data JPA?

No. Replace `JdbcProductStore` with a JPA adapter:

```text
CatalogController -> CatalogService -> ProductStore
                                         ^
                                         |
                                   JpaProductStore
                                         |
                              EntityManager/JpaRepository
                                         |
                                      Database
```

`@Entity`, `EntityManager`, `JpaRepository`, JPQL, Criteria API, and `Pageable` belong to the data access implementation and may appear inside the adapter. The service should not force controllers to use `EntityManager` or return `Page<Entity>` as the default API contract merely because the repository conveniently returns it. Create a page DTO with stable public fields (`items`, `page`, `size`, `total` when genuinely needed) and constrain which sorts/filters clients may request.

Spring translates many JDBC/JPA failures into `DataAccessException` subtypes; exact behavior depends on the call path, provider, and configuration. With JPA, SQL may execute only at `flush` or `commit`; never assume a UNIQUE violation is always thrown immediately inside `save`. Design error-handling and transaction boundaries around actual execution timing, and test against the production DBMS.

Using a Spring Data projection containing only allowed display fields can be very effective. However, infrastructure projections/entities should not silently replace public DTO contracts when persistence changes could break the API.

## 10. Filtering, Sorting, and Pagination Without Letting the UI Send SQL

A subtler form of leakage is an endpoint accepting `sql`, `where`, `tableName`, or `orderByClause` parameters and concatenating them into SQL. That causes both tight coupling and injection vulnerabilities, since `?` placeholders bind **data values only**, never table names, column names, or SQL keywords.

Instead of accepting `sort=price DESC; DROP TABLE products`, define a fixed set of public values:

```text
GET /api/products?sort=price_asc&page=0&size=20
GET /api/products?sort=name_asc&page=1&size=20
```

The controller validates `sort` is `price_asc` or `name_asc` and caps `size`; the service forwards the business choice; the repository maps it to real SQL columns:

```java
// Illustrates logic placed inside the repository, not a complete class.
String orderBy = switch (publicSort) {
    case "price_asc" -> "price ASC, id ASC";
    case "name_asc"  -> "name ASC, id ASC";
    default -> throw new IllegalArgumentException("Unsupported sort");
};

String sql =
        "SELECT id, sku, name, price FROM products ORDER BY "
        + orderBy + " LIMIT ? OFFSET ?";
```

Here, `orderBy` comes from a **fixed server-defined allowlist**, not raw client string concatenation. `LIMIT` and `OFFSET` are still bound via `?` (and should be bounded to avoid overflow or huge scans). Specific SQL patterns stay inside the repository; adding an `id` tie-breaker keeps pagination order deterministic within a snapshot, even though offset pagination can still shift under concurrent writes.

For invalid sort inputs, return `400` per the HTTP contract for unsupported `sort` values; never return `"column price does not exist"` or the DB's `ORDER BY` structure.

## 11. Sensitive Data Boundaries

Hiding SQL is part of secure API design. Control these as well:

- **Response DTO allowlist:** return only fields callers are permitted to view. An entity with `password_hash`, `internal_note`, or `purchase_cost` must never be serialized directly.
- **Authorization at use case/query level:** controllers/services verify caller permissions; repositories filter by valid tenant/owner scope. Merely omitting a column from JSON does not prevent data leaks through another endpoint.
- **Connection settings:** JDBC URLs, usernames/passwords, internal hostnames, and pool settings belong to server configuration/secrets managers, never frontend bundles or responses.
- **Exceptions and tracing:** public messages must omit SQL, tables, drivers, stack traces, and DB addresses; internal logs/traces must still restrict PII and read access.
- **Caching and telemetry:** never ship full error payloads containing SQL or bind parameters to browser-side analytics tools.
- **Migrations:** the API does not change merely because `products` splits into two tables or SQL is tuned with indexes/materialized views.

Even for internal-network APIs, browsers and mobile apps remain clients outside the server's data-protection boundary.

## 12. Testing Architecture and Contracts Instead of Inspecting SQL from the UI

Two complementary test types apply.

**Web contract tests, no DB needed:** mock/fake `CatalogService`, send requests via Spring MVC `MockMvc`, and verify status codes, DTOs, and error bodies. The example below uses Spring Boot 3.3.x `@MockBean` (newer versions may use `@MockitoBean`):

`src/test/java/demo/catalog/CatalogContractTest.java`:

```java
package demo.catalog;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.WebMvcTest;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.dao.DataAccessResourceFailureException;
import org.springframework.test.web.servlet.MockMvc;

import static org.hamcrest.Matchers.containsString;
import static org.hamcrest.Matchers.not;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@WebMvcTest(CatalogController.class)
@Import(ApiErrorHandler.class)
class CatalogContractTest {

    @Autowired
    MockMvc mvc;

    @MockBean
    CatalogService service;

    @Test
    void unexpectedDatabaseFailureDoesNotLeakDriverDetails()
            throws Exception {
        when(service.get(99L)).thenThrow(
                new DataAccessResourceFailureException(
                        "jdbc:postgresql://internal-host/secret"
                )
        );

        mvc.perform(get("/api/products/99"))
                .andExpect(status().isInternalServerError())
                .andExpect(jsonPath("$.code")
                        .value("UNEXPECTED_STORAGE_ERROR"))
                .andExpect(content().string(
                        not(containsString("jdbc:postgresql"))
                ))
                .andExpect(content().string(
                        not(containsString("internal-host"))
                ));
    }
}
```

With the test dependencies and example classes above, run:

```bash
./gradlew test
```

This test verifies a property **valuable to clients**: infrastructure errors are hidden from responses. It does not confirm real PostgreSQL is running or `ON CONFLICT` works; that belongs to integration tests.

**Data-layer integration tests:** use a real PostgreSQL instance or Testcontainers and verify:

1. `ProductStore.insert` creates a row and maps `BigDecimal` and the generated ID properly.
2. Inserting the same SKU twice, including concurrently, creates only one record and the adapter returns `SkuAlreadyUsed` on conflict.
3. `findById` returns `Optional.empty()` when no row exists, without leaking driver exceptions to the service.
4. Unexpected DB errors remain failures and are not misreported as `SKU_ALREADY_USED`.
5. When a use case performs multiple writes, the transaction rolls back completely if a later step fails.

Switching the adapter to JPA or optimizing SQL should not break web contract tests; what must be re-verified are integration tests for the new persistence implementation.

**Static architecture checks / code reviews:** look for imports of `java.sql.*`, `org.postgresql.*`, `JdbcTemplate`, `EntityManager`, or query strings containing `SELECT/INSERT/UPDATE/DELETE` inside web/presentation packages. Not every occurrence of the word "SELECT" in a comment is a bug; evaluate real boundaries and callers. Also inspect response serializers, `@ExceptionHandler`s, logging, and schema/error snapshots for leaks.

## 13. Common Misconceptions

| Practice | Problem | How to fix |
| --- | --- | --- |
| Controller calls `JdbcTemplate` directly | UI couples to SQL and transactions | Move SQL into repository/DAO; controller calls service |
| Returning `List<Map<String,Object>>` straight from DB | Responses shift silently with column/schema renames | Map into controlled DTOs |
| Controller catches `SQLException` | Couples to driver and SQLSTATE | Translate in adapter; service/web handle application meaning |
| Returning `ex.getMessage()` to clients | Leaks SQL/constraints/stack traces, unstable error contract | Return status + error code + safe message |
| Mapping every `DataIntegrityViolationException` to `409` | Conflates unique, FK, NOT NULL, and CHECK | Classify exact invariants or return a generic error |
| Checking uniqueness only with `SELECT` before `INSERT` | Race condition under concurrent load | Enforce UNIQUE in DB, handle conflicts properly |
| Concatenating request filters/sorts into SQL | SQL injection, couples API to column names | Bind values and allowlist SQL structures |
| Returning JPA entities directly | Exposes internal fields, lazy/cycle issues, schema changes alter JSON | Use deliberate API DTOs/projections |
| Service passes around `ResultSet` or `Connection` | Application logic depends on DB details | Convert to domain/application types inside adapter |
| UI layer manually commits/rolls back | Breaks transaction boundaries and use-case policy | Let service/application manage transactions |
| Hiding all error details even in logs | Impossible to troubleshoot incidents | Minimal public response, controlled internal logs |
| Creating interfaces for trivial assignments | Adds complexity without creating a useful boundary | Abstract only where swapping implementations or testing use cases helps |

## 14. Design Scenario: Swapping Drivers Without Changing the UI

A team currently uses PostgreSQL/JDBC to store products. Later they want to swap the adapter to JPA or offload reads to a search engine. If the public API accidentally returns snake_case column names and `PSQLException`, the frontend must be rewritten around every storage decision.

With the design in Section 6, the team can implement `JpaProductStore implements ProductStore` or a `SearchProductReader` for read use cases; the service still accepts/returns `Product` or defined application results, and the controller still produces the same `ProductResponse` and error codes. Only when **business requirements** change (e.g., prices gain a currency, SKUs change uniqueness rules) does the team intentionally evolve the public contract and version/migrate per product policy.

This is the practical payoff of boundaries: evolving layers independently, testing each responsibility in isolation, and shrinking blast radius when fixing database issues.

## 15. Self-Check Exercises

**Exercise 1 — spotting coupling:** a controller accepts `String whereClause` and calls `jdbc.queryForList("SELECT * FROM orders WHERE " + whereClause)`. List the risks regarding coupling, injection, and exposed data, and propose a replacement using request/DTO/service/repository.

**Exercise 2 — error handling:** an API returns `"ERROR: duplicate key value violates unique constraint uq_products_sku"` in its body to clients. Design an appropriate `ProblemDetail` response and identify which details belong strictly in server logs.

**Exercise 3 — switching DBMS:** the adapter currently uses `ON CONFLICT ... RETURNING`; the team wants to migrate to a system that supports generated keys with different syntax. List which classes must change and which classes/API structures should stay unchanged.

**Exercise 4 — testing:** use `MockMvc` to simulate `DataAccessResourceFailureException` as in Section 12; add assertions verifying the response contains neither `SQLException`, `SELECT`, nor hostnames, has the expected HTTP status and public `code`; and write an integration test for duplicate SKUs on PostgreSQL.

**Hints:** (1) expose allowlisted business filters, never accept raw SQL; (2) `409` + `SKU_ALREADY_USED` + concise message, while internal logs retain controlled details; (3) mostly change the adapter and migrations/config, keeping use cases and DTOs if semantics are unchanged; (4) separate HTTP contract tests from DB tests because they protect two different boundaries.

## 16. Code Review Checklist

- Does the controller import `JdbcTemplate`, `java.sql`, `EntityManager`, or driver classes?
- Does any request parameter carry raw SQL, table/column names, or verbatim `WHERE`/`ORDER BY` clauses?
- Does the web layer return stable DTOs rather than leaking `ResultSet`/`Map`/JPA entities or unintended DB columns?
- Does the service call a semantically clear data access port rather than knowing SQL or drivers itself?
- Are SQL, bound parameters, row mapping, and SQL dialect handling encapsulated inside repository adapters?
- Are concurrency invariants backed by DB constraints rather than `SELECT`-before-write checks alone?
- Do clients receive appropriate business/HTTP error codes without exception messages, SQLSTATEs, or stack traces?
- Are transactions placed at use-case boundaries, with rollback and retries tested against real exceptions?
- Are internal logs/traces sufficient for debugging without leaking secrets/PII to client telemetry?
- Can storage technology be swapped by replacing adapters and integration tests without changing API contracts?

**Conclusion:** SQL, query plans, connection pools, JDBC drivers, and constraint names are implementation details belonging to the data layer. Controllers should handle only HTTP transport, validation, and DTOs; services manage use cases and transactions; repositories execute queries, map results, and translate failures into appropriate application signals. Public APIs reflect **business semantics**, making them both safer and easier to evolve across storage technologies.

## References

- Spring Framework — DAO Support and `DataAccessException`: https://docs.spring.io/spring-framework/reference/data-access/dao.html
- Spring Framework — JDBC Core, `JdbcTemplate`, and `SQLExceptionTranslator`: https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html
- Spring Framework — Transaction Management: https://docs.spring.io/spring-framework/reference/data-access/transaction/declarative/annotations.html
- Spring Framework — REST Error Responses and `ProblemDetail`: https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html
- PostgreSQL — `INSERT` / `ON CONFLICT` / `RETURNING`: https://www.postgresql.org/docs/current/sql-insert.html
- OWASP — SQL Injection Prevention Cheat Sheet: https://cheatsheetseries.owasp.org/cheatsheets/SQL_Injection_Prevention_Cheat_Sheet.html
