# Boundary Data, Unicode Characters, Nulls, and Invalid Relationships

In the **Test Data** group of the **Spring Boot - testing** module, a test running only with “ordinary” data like `quantity=5`, `name="Book"`, and an existing ID rarely catches boundary bugs. Real bugs typically emerge at **min/max values**, values **just outside limits**, Unicode strings with multiple representations, **missing/null/blank** JSON fields, or **references pointing to nonexistent records**. These cases span Jackson, Bean Validation, Java, SQL, transactions, and the response contract simultaneously.

Example: an order-creation API accepts `customerId`, `label`, `note`, and `quantity`. The application requires:

- `customerId` is required and must point to an existing customer.
- `label` is required, must not be whitespace-only, and has a maximum length of **24 UTF-16 code units under Bean Validation**.
- `note` is optional, may be `null`, and if present has a maximum length of 100 UTF-16 code units.
- `quantity` is a required integer in **[1, 100]**.
- SQL must enforce a **foreign key** so an orphaned `customerId` is rejected even if service-level checks are bypassed or encounter a race condition.
- HTTP responses must not silently corrupt or lose Unicode characters; invalid inputs must return stable error codes without leaking SQL exceptions or sensitive data.

This lesson combines a **test case matrix**, **JUnit 5**, **Spring Boot 3.5 / Spring Framework 6.2**, **Java 17**, **Jackson 2**, **Bean Validation**, **MockMvc**, **JdbcTemplate**, and **H2**. The examples include complete source files for a Spring Boot Gradle project plus a standalone Java SE program with `javac`/`java` commands and exact stdout.

## 1. What Is Boundary Data and Why Test It?

Boundary values sit **right on or immediately adjacent to** the limits of a rule. For `quantity` from 1 to 100:

| Value | Meaning | Expected |
| ---: | --- | --- |
| `null` | Missing required value | 400 / no DB write |
| `0` | Just below min | 400 / no DB write |
| `1` | Exact min | Accepted |
| `2` | Just above min | Accepted |
| `50` | Middle of valid domain | Accepted |
| `99` | Just below max | Accepted |
| `100` | Exact max | Accepted |
| `101` | Just above max | 400 / no DB write |
| `"abc"` | Wrong JSON type | 400 / parse error |
| `2147483648` | Outside `Integer` range | 400 / parse error under typical strict config |

This is **boundary value analysis** (BVA). Instead of picking random numbers from the same equivalence class, intentionally test **min−1, min, min+1, max−1, max, max+1**, plus nulls and type mismatches. For complex rules, combine with **equivalence partitioning**: valid, too small, too large, wrong type, missing, and database-rejected values.

**A boundary can exist at multiple layers**:

```text
Client JSON
  |
  v
Jackson deserialization
  |
  v
Bean Validation (@NotNull/@Min/@Max/@Size)
  |
  v
Service business rules
  |
  v
JdbcTemplate (parameterized SQL)
  |
  v
Database (NOT NULL / CHECK / UNIQUE / FOREIGN KEY)
```

Tests must be clear about **which defense layer** they verify. An HTTP 400 response proves the request was rejected, yet **does not prove a DB CHECK constraint exists**. A test throwing `DataIntegrityViolationException` via direct JDBC proves the DB rejects bad rows, yet does not prove the controller translates it into safe error JSON.

## 2. Designing a Test Matrix Before Writing Code

For the order-creation DTO, build a matrix like this:

| Group | Input | HTTP Expectation | DB Expectation |
| --- | --- | --- | --- |
| Happy path | Existing customer, valid label, quantity 1 | 201 + matching fields | 1 order |
| Numeric boundary | Quantity 100 | 201 | 1 order |
| Out of bounds | Quantity 0 or 101 | 400 | No row added |
| Null number | `"quantity":null` | 400 | No row added |
| Missing number | No `quantity` key | 400 | No row added |
| Unicode | `"Cà phê 😀 é"` | 201 + exact round-trip | Value preserved per policy |
| Blank label | `"label":"   "` | 400 | No row added |
| Null label | `"label":null` | 400 | No row added |
| Label too long | 13 `😀` emojis with 24 UTF-16 unit limit | 400 | No row added |
| Label at boundary | 12 `😀` emojis | 201 | 1 order |
| Null note | `"note":null` | 201 | SQL NULL |
| Missing note | No `note` key | 201 if contract permits | SQL NULL |
| Note too long | 101 ASCII characters | 400 | No row added |
| Invalid relationship | Nonexistent `customerId=999` | 422 in sample policy | No order added |
| Bypassed service check | Direct JDBC INSERT with bad FK | Outside HTTP test | DB throws `DataIntegrityViolationException` |
| Bad SQL data | Direct JDBC `quantity=0` | Outside HTTP test | DB `CHECK` blocks |
| Malformed JSON | Unclosed JSON or wrong type | 400 with safe code | No row added |

Status codes 400/422/409 reflect the **sample application's contract**, not a universal rule for all REST APIs. Another system might use 400 for an invalid foreign-key reference; test against the published API contract rather than guessing framework status codes.

**Testing principle:** include both *positive assertions* (valid cases succeed) and *negative assertions* (invalid cases are rejected). Writing only negative tests can falsely stay green if the endpoint rejects everything; writing only happy-path tests misses validation gaps.

## 3. Distinguishing Missing, Null, Empty, Blank, and Zero

A JSON request can carry several distinct states:

```json
{}
```

```json
{"quantity": null}
```

```json
{"quantity": 0}
```

```json
{"label": ""}
```

```json
{"label": "   "}
```

**Do not treat them as equivalent**:

- **Missing:** JSON object **lacks the key**. With Jackson record constructors and reference type `Integer`, a missing field typically binds as `null` under default config. If an API must distinguish missing from explicit null, build a presence-aware DTO or custom deserializer instead of inferring from the bound Java field.
- **Explicit null:** the key is present with JSON value `null`. When bound to `Integer`, it becomes Java `null`.
- **Zero:** a valid number by type, yet rejected by `@Min(1)` per business rules.
- **Empty string `""`:** length 0, rejected by `@NotBlank`.
- **Blank string `"   "`:** length > 0 with no visible characters per the validator's blank rules; rejected by `@NotBlank`.
- **Unicode whitespace:** not every whitespace-looking code point behaves identically under `String.trim()`, `String.isBlank()`, or validation libraries. Specifically, **NBSP U+00A0** and zero-width characters need dedicated tests if policy forbids them.

**Never use primitive `int quantity` when you need to distinguish null from zero.** Under many Jackson configurations, JSON null/missing binds to default `0` for primitives, erasing information. Use `Integer` with `@NotNull` and `@Min`/`@Max` to keep the contract explicit.

A database note: `VARCHAR NOT NULL` rejects SQL `NULL`, yet **does not automatically reject empty strings or all-space strings** in many engines. Bean Validation and `CHECK` constraints cover different scopes; never confuse `NOT NULL` with `NOT BLANK`.

## 4. Unicode: Code Units, Code Points, and Grapheme Clusters

A Java `String` is a sequence of **UTF-16 code units**. Most precomposed Vietnamese characters like `"ế"` fit in one `char`, whereas emojis outside the BMP usually require **two code units** (a surrogate pair). A single user-perceived character can also combine **multiple Unicode code points**, such as a base letter plus combining mark or emoji sequences joined with zero-width joiners.

| Example | Representation | `String.length()` | `codePointCount(...)` | User-Perceived |
| --- | --- | ---: | ---: | --- |
| `"A"` | U+0041 | 1 | 1 | 1 character |
| `"😀"` | U+1F600 | 2 | 1 | 1 emoji |
| `"é"` | U+00E9 (precomposed) | 1 | 1 | 1 character |
| `"e\u0301"` | U+0065 + U+0301 (combining mark) | 2 | 2 | 1 character |
| `"🇻🇳"` | Two regional-indicator code points | 4 | 2 | 1 flag emoji |

**Note:** the “user-perceived” column is intuitive visual guidance; exact grapheme cluster segmentation depends on the Unicode version and rendering engine. Do not treat `length()` or `codePointCount` as a full grapheme-counting algorithm.

### What Does @Size Count?

Under standard Bean Validation implementations (Hibernate Validator for `CharSequence`), `@Size(max = 24)` checks **`CharSequence.length()`**, which for Java `String` is the count of **UTF-16 code units**:

- `"😀".repeat(12)` has `length() = 24` → right at max 24.
- `"😀".repeat(13)` has `length() = 26` → exceeds max 24.
- `"e\u0301"` has length 2, even though it looks like `"é"` of length 1.

This matters when UX specifies “max 24 characters”: the specification must clarify whether that means **UTF-16 units**, Unicode code points, grapheme clusters, or UTF-8 bytes. If business rules demand 24 *user-perceived characters*, `@Size(max=24)` alone **is not enough**; implement a custom validator using proper grapheme segmentation and test with combining marks and ZWJ sequences.

**Database limits can differ too:** a DB may measure `VARCHAR(n)` in code points/characters rather than Java UTF-16 code units. H2, PostgreSQL, and MySQL differ in collations, normalization, byte lengths, and character lengths. Passing on H2 **does not prove** PostgreSQL compares or enforces lengths identically. For Unicode-sensitive contracts, test against the production engine via Testcontainers.

## 5. Unicode Normalization: NFC and NFD

Two visually identical strings can **differ at the code-point level**:

```java
String composed = "é";      // U+00E9
String decomposed = "e\u0301"; // U+0065 + U+0301
boolean rawEqual = composed.equals(decomposed);  // false
```

If business logic needs canonical Unicode equivalence, use `java.text.Normalizer`:

```java
String left = Normalizer.normalize(
        composed, Normalizer.Form.NFC);
String right = Normalizer.normalize(
        decomposed, Normalizer.Form.NFC);
boolean normalizedEqual = left.equals(right);     // true
```

This is a **Java snippet**, not a standalone program; the complete demo in Section 13 provides full imports, run commands, and exact stdout.

**Do not normalize unconditionally:** a contract may require preserving raw inputs for digital signatures, auditing, or exact round-trips. For searchable names or usernames, normalization may belong at a documented boundary. Pick one explicit policy:

- **Preserve exact code-unit sequences JSON → Java → DB → JSON** (after UTF-8 decode/encode), testing round-trips with `String.equals`.
- **Normalize to NFC before storing/comparing**, testing stable NFC outputs and checking database uniqueness/collation rules.

Never use default-locale `toLowerCase()` as identifier normalization; Unicode case folding, locales, and confusables are separate concerns, especially for accounts, usernames, and emails.

## 6. Defining “Invalid Relationships”

An `Order` whose `customerId` references a `Customer` is a **referential relationship**. In SQL, enforce a foreign key:

```text
customers
  id (PRIMARY KEY)
  email (UNIQUE)
      |
      | 1-to-many
      v
purchase_orders
  id (PRIMARY KEY)
  customer_id (FOREIGN KEY -> customers.id)
  label, note, quantity
```

Relationship cases worth testing:

1. **Missing parent key:** `customer_id=999` → must not create an orphaned Order.
2. **Null parent key:** `customer_id NOT NULL` column → must fail.
3. **Deleting parent while children exist:** without cascading, parent `DELETE` must be blocked.
4. **Parent deleted concurrently by another transaction:** a service doing “exists check then INSERT” faces a **race condition**; the DB FK remains the decisive line of defense.
5. **Wrong owner assignment:** an Order with a valid FK pointing to another Customer can still violate authorization; FKs **do not** enforce access control.
6. **Duplicate relationships:** if the domain requires uniqueness on a pair, add a `UNIQUE`/composite key or explicit policy; an FK alone does not forbid two Orders for one customer.
7. **Graph edges/cycles:** in trees or DAGs, simple DB FKs do not prevent cycles; enforce validation, recursive constraints, or transaction logic and test explicitly.

A service-level check like `customerStore.existsById(id)` provides a clear business error (`422`), yet **never replaces a foreign key**: a concurrent delete can occur between `SELECT` and `INSERT`. Having both layers provides “defense in depth.”

## 7. Complete Spring Boot 3.5 / Java 17 Example

We use **Spring MVC + Bean Validation + JDBC + H2**. JPA is unnecessary to demonstrate foreign keys, nulls, and `CHECK` constraints; `JdbcTemplate` keeps SQL side effects visible.

File structure:

```text
src/
├── main/java/example/testing/boundaries/
│   ├── BoundaryApplication.java
│   ├── CreateOrderRequest.java
│   ├── OrderView.java
│   ├── CustomerStore.java
│   ├── OrderStore.java
│   ├── OrderService.java
│   ├── OrderController.java
│   ├── ErrorAdvice.java
│   └── UnicodeBoundaryDemo.java
└── test/
    ├── java/example/testing/boundaries/
    │   ├── OrderHttpContractTest.java
    │   └── UnicodeBoundaryTest.java
    └── resources/schema.sql
```

**Test scope:** `OrderHttpContractTest` boots a Spring Boot test context with **synchronous** MockMvc and embedded H2, rolling back transactions after each method. It is **not** live HTTP over a real TCP port and not a Testcontainers production DB. It verifies validation, JSON, JDBC, and SQL schema behavior within that stated boundary.

### 7.1. Gradle Dependencies

In a Gradle project already configured with the Spring Boot plugin, repositories, and Java 17+ toolchain:

```groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    implementation 'org.springframework.boot:spring-boot-starter-jdbc'

    testImplementation 'org.springframework.boot:spring-boot-starter-test'
    testRuntimeOnly 'com.h2database:h2'
}

tasks.named('test', Test) {
    useJUnitPlatform()
}
```

This snippet **adds to an existing `build.gradle`**, not a complete build script from scratch. Spring Boot 3.5 manages compatible versions of Spring Framework, Jakarta Validation, Hibernate Validator, Jackson, and H2 via its BOM. On Boot 4.x, double-check package/module names and current version behavior.

If a project uses both Flyway/Liquibase and `schema.sql`, avoid overlapping table creation. On non-embedded databases, Spring SQL initialization may need `spring.sql.init.mode=always` or proper migration tools.

### 7.2. Spring Boot Application: BoundaryApplication.java

Create `src/main/java/example/testing/boundaries/BoundaryApplication.java`:

```java
package example.testing.boundaries;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class BoundaryApplication {
    public static void main(String[] args) {
        SpringApplication.run(BoundaryApplication.class, args);
    }
}
```

Unified package for controller, service, and repositories. In tests, Boot locates this `@SpringBootApplication` class to bootstrap the context. When running `main()` outside tests, configure a production database and migrations; H2 in `testRuntimeOnly` is absent at production runtime.

### 7.3. schema.sql: Real Constraints in the Database

Create `src/test/resources/schema.sql`:

```sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email VARCHAR(120) NOT NULL UNIQUE
);

CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    label VARCHAR(24) NOT NULL,
    note VARCHAR(100),
    quantity INTEGER NOT NULL CHECK (
        quantity >= 1 AND quantity <= 100
    ),
    CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id)
);
```

H2 2.x supports this identity, `CHECK`, and `FOREIGN KEY` syntax in standard test configurations.

**Meaning of each constraint:**

- `customers.id PRIMARY KEY`: every customer has a unique ID.
- `email UNIQUE NOT NULL`: forbids null or duplicate emails per engine collation; real email format rules need separate validation.
- `purchase_orders.customer_id NOT NULL + FOREIGN KEY`: every order must reference an existing customer.
- `quantity INTEGER NOT NULL CHECK 1..100`: DB rejects null, 0, or 101 even if the controller is bypassed.
- `label VARCHAR(24) NOT NULL`: blocks nulls and certain overlong strings at the DB; **does not block blank strings**.
- `note VARCHAR(100)`: permits SQL `NULL`; Jackson/validation govern how missing/null arrives via HTTP.

**No `ON DELETE CASCADE` declared:** therefore H2 blocks deleting a `Customer` referenced by an `Order`. If your contract calls for cascading deletes, alter the DDL and test child deletion explicitly rather than assuming database defaults.

## 8. Source Files: Request DTO, Response, and Repositories

### 8.1. CreateOrderRequest.java

Create `src/main/java/example/testing/boundaries/CreateOrderRequest.java`:

```java
package example.testing.boundaries;

import jakarta.validation.constraints.Max;
import jakarta.validation.constraints.Min;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateOrderRequest(
        @NotNull Long customerId,

        @NotBlank
        @Size(max = 24)
        String label,

        @Size(max = 100)
        String note,

        @NotNull
        @Min(1)
        @Max(100)
        Integer quantity) {
}
```

**Each annotation has a distinct role:**

- `@NotNull` requires a non-null value, without checking whether the ID exists in the database.
- `@NotBlank` rejects null, empty, and blank `CharSequence` values; it is not an exhaustive filter for every invisible Unicode code point.
- `@Size` on `CharSequence` **allows null by default**. For required fields, combine it with `@NotNull` or `@NotBlank`.
- `@Min`/`@Max` check numeric bounds; pair with `@NotNull` to reject null.
- `Integer` instead of `int` preserves null state from Jackson binding.

This intentionally permits `note=null`. Never convert null into `"null"` or `""` when saving.

### 8.2. OrderView.java

Create `src/main/java/example/testing/boundaries/OrderView.java`:

```java
package example.testing.boundaries;

public record OrderView(
        Long id,
        Long customerId,
        String label,
        String note,
        Integer quantity) {
}
```

This is a dedicated response DTO. If a SQL entity later gains internal metadata, do not expose it directly in HTTP responses. `note=null` serializes to JSON `null` under Boot 3.5 defaults unless customized. Tests verify the exact contract of this example.

### 8.3. CustomerStore.java

Create `src/main/java/example/testing/boundaries/CustomerStore.java`:

```java
package example.testing.boundaries;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Repository;

@Repository
public class CustomerStore {
    private final JdbcTemplate jdbc;

    public CustomerStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public boolean existsById(long id) {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM customers WHERE id = ?",
                Integer.class, id);
        return count != null && count > 0;
    }
}
```

Use `?` SQL parameters instead of concatenating input into query strings. `COUNT(*)` reads real DB state within the active connection/transaction, though a race remains between check and insert; foreign keys continue guarding integrity.

### 8.4. OrderStore.java

Create `src/main/java/example/testing/boundaries/OrderStore.java`:

```java
package example.testing.boundaries;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.namedparam.MapSqlParameterSource;
import org.springframework.jdbc.core.simple.SimpleJdbcInsert;
import org.springframework.stereotype.Repository;

@Repository
public class OrderStore {
    private final JdbcTemplate jdbc;
    private final SimpleJdbcInsert inserter;

    public OrderStore(JdbcTemplate jdbc) {
        this.jdbc = jdbc;
        this.inserter = new SimpleJdbcInsert(jdbc)
                .withTableName("purchase_orders")
                .usingColumns(
                        "customer_id", "label",
                        "note", "quantity")
                .usingGeneratedKeyColumns("id");
    }

    public long insert(CreateOrderRequest input) {
        Number key = inserter.executeAndReturnKey(
                new MapSqlParameterSource()
                        .addValue("customer_id", input.customerId())
                        .addValue("label", input.label())
                        .addValue("note", input.note())
                        .addValue("quantity", input.quantity()));
        return key.longValue();
    }

    public OrderView findById(long id) {
        return jdbc.queryForObject(
                """
                SELECT id, customer_id, label, note, quantity
                FROM purchase_orders
                WHERE id = ?
                """,
                (rs, rowNum) -> new OrderView(
                        rs.getLong("id"),
                        rs.getLong("customer_id"),
                        rs.getString("label"),
                        rs.getString("note"),
                        rs.getInt("quantity")),
                id);
    }

    public int countForCustomer(long customerId) {
        Integer count = jdbc.queryForObject(
                """
                SELECT COUNT(*) FROM purchase_orders
                WHERE customer_id = ?
                """,
                Integer.class, customerId);
        return count == null ? 0 : count;
    }
}
```

`SimpleJdbcInsert` builds a prepared `INSERT` and returns the generated identity key. `MapSqlParameterSource` handles null `note` values cleanly. `findById` reads **the stored database row** rather than echoing the input object, allowing tests to detect encoding or mapping bugs.

With `JdbcTemplate` and H2, Spring typically translates SQL constraint violations into `DataIntegrityViolationException`; production code can map by constraint name or SQLState as needed. **Never assume every constraint failure yields the same HTTP status or exception subclass across all drivers and databases.**

## 9. Source Files: Service, Controller, and Error Mapping

### 9.1. OrderService.java

Create `src/main/java/example/testing/boundaries/OrderService.java`:

```java
package example.testing.boundaries;

import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class OrderService {
    private final CustomerStore customers;
    private final OrderStore orders;

    public OrderService(
            CustomerStore customers, OrderStore orders) {
        this.customers = customers;
        this.orders = orders;
    }

    @Transactional
    public OrderView create(CreateOrderRequest input) {
        if (!customers.existsById(input.customerId())) {
            throw new CustomerNotFoundException();
        }

        long id = orders.insert(input);
        return orders.findById(id);
    }
}

final class CustomerNotFoundException
        extends RuntimeException {
    CustomerNotFoundException() {
        super("Unknown customer");
    }
}
```

The service checks customer existence to return a clear business error. However, **SELECT followed by INSERT is not an atomic referential check** if another transaction deletes the customer in between; the foreign key remains the final safeguard.

`@Transactional` on the Spring-managed service ensures check, insert, and read run in one application transaction (when invoked through the Spring proxy with a transaction manager configured). In a synchronous MockMvc test with `@Transactional` on the JUnit method, the service's default `REQUIRED` propagation joins the **test transaction** and rolls back at method end.

**Do not instantiate `new OrderService(...)` inside an HTTP test** and assume AOP/DB transactions are under test; obtain the Spring-managed bean from the context when testing real proxies.

### 9.2. OrderController.java

Create `src/main/java/example/testing/boundaries/OrderController.java`:

```java
package example.testing.boundaries;

import jakarta.validation.Valid;

import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/orders")
public class OrderController {
    private final OrderService service;

    public OrderController(OrderService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<OrderView> create(
            @Valid @RequestBody CreateOrderRequest input) {
        OrderView created = service.create(input);
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(created);
    }
}
```

`@Valid` triggers Bean Validation on the request body when MVC binds the record. Violating `@NotNull`, `@NotBlank`, `@Min`, `@Max`, or `@Size` causes Spring MVC to throw `MethodArgumentNotValidException`, handled by the advice.

**Do not forget `spring-boot-starter-validation`:** without a Jakarta Validation provider, annotations may silently not execute as expected. HTTP tests for invalid cases catch non-working validation configuration immediately.

### 9.3. ErrorAdvice.java

Create `src/main/java/example/testing/boundaries/ErrorAdvice.java`:

```java
package example.testing.boundaries;

import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.http.converter.HttpMessageNotReadableException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@RestControllerAdvice
public class ErrorAdvice {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ErrorBody invalidFields(
            MethodArgumentNotValidException exception) {
        return new ErrorBody("INVALID_ORDER");
    }

    @ExceptionHandler(HttpMessageNotReadableException.class)
    @ResponseStatus(HttpStatus.BAD_REQUEST)
    public ErrorBody malformedJson(
            HttpMessageNotReadableException exception) {
        return new ErrorBody("MALFORMED_JSON");
    }

    @ExceptionHandler(CustomerNotFoundException.class)
    @ResponseStatus(HttpStatus.UNPROCESSABLE_ENTITY)
    public ErrorBody unknownCustomer(
            CustomerNotFoundException exception) {
        return new ErrorBody("CUSTOMER_NOT_FOUND");
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    @ResponseStatus(HttpStatus.CONFLICT)
    public ErrorBody dataConstraintViolation(
            DataIntegrityViolationException exception) {
        return new ErrorBody("DATA_CONSTRAINT_VIOLATION");
    }

    public record ErrorBody(String code) {
    }
}
```

**Why not return `exception.getMessage()`?** JDBC and validation exceptions can expose user input, SQL statements, constraint names, connection properties, or stack traces. This example returns **fixed public error codes**. Real applications also add a structured error taxonomy, correlation IDs, safe logging/masking, authorization, and i18n.

`422` for unknown customer and `409` for DB constraints are **illustrative policy choices**. Other systems choose `400`, `404`, or `409` depending on their semantics. Pick an explicit policy and test it consistently rather than treating “foreign key always means HTTP 409” as a Spring rule.

**Distinguishing JSON errors:**

- `{"quantity":null}` → Jackson binds the record with `quantity=null`; Bean Validation returns `INVALID_ORDER`.
- `{"quantity":"not-a-number"}` → Jackson fails to bind `Integer` under strict config; `HttpMessageNotReadableException` → `MALFORMED_JSON`.
- Invalid JSON syntax → also `MALFORMED_JSON`.
- Well-typed customer ID that **does not exist** → `CUSTOMER_NOT_FOUND`.
- DB constraint violated due to bypassed service or race condition → `DATA_CONSTRAINT_VIOLATION` if it reaches the HTTP boundary.

## 10. Complete HTTP/SQL Test Suite with MockMvc

Create `src/test/java/example/testing/boundaries/OrderHttpContractTest.java`:

```java
package example.testing.boundaries;

import java.util.List;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.ResultActions;
import org.springframework.transaction.annotation.Transactional;

import static org.hamcrest.Matchers.nullValue;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

@SpringBootTest(
        webEnvironment = SpringBootTest.WebEnvironment.MOCK)
@AutoConfigureMockMvc
@Transactional
class OrderHttpContractTest {

    @Autowired
    private MockMvc mvc;

    @Autowired
    private JdbcTemplate jdbc;

    @Autowired
    private ObjectMapper mapper;

    @BeforeEach
    void seedCustomer() {
        jdbc.update(
                "INSERT INTO customers(id,email) VALUES (?,?)",
                1L, "fixture@example.test");
    }

    private ResultActions postOrder(
            CreateOrderRequest input) throws Exception {
        return mvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsString(input)));
    }

    private ResultActions postRaw(String json)
            throws Exception {
        return mvc.perform(post("/orders")
                .contentType(MediaType.APPLICATION_JSON)
                .content(json));
    }

    private int countOrders() {
        Integer count = jdbc.queryForObject(
                "SELECT COUNT(*) FROM purchase_orders",
                Integer.class);
        return count == null ? 0 : count;
    }

    @Test
    void quantityMinimumAndMaximumAreAccepted()
            throws Exception {
        postOrder(new CreateOrderRequest(
                1L, "minimum", null, 1))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.quantity").value(1));

        postOrder(new CreateOrderRequest(
                1L, "maximum", "note", 100))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.quantity").value(100));

        assertEquals(2, countOrders());
    }

    @Test
    void invalidQuantityNearBoundariesIsRejected()
            throws Exception {
        postOrder(new CreateOrderRequest(
                1L, "zero", null, 0))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        postOrder(new CreateOrderRequest(
                1L, "too-many", null, 101))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        assertEquals(0, countOrders());
    }

    @Test
    void explicitNullAndMissingQuantityAreRejected()
            throws Exception {
        postRaw("""
                {
                  "customerId":1,
                  "label":"null quantity",
                  "note":null,
                  "quantity":null
                }
                """)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        postRaw("""
                {
                  "customerId":1,
                  "label":"missing quantity",
                  "note":null
                }
                """)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        assertEquals(0, countOrders());
    }

    @Test
    void blankEmptyAndNullLabelsAreRejected()
            throws Exception {
        for (String value : List.of("", "   ", "\t")) {
            postOrder(new CreateOrderRequest(
                    1L, value, null, 1))
                    .andExpect(status().isBadRequest())
                    .andExpect(jsonPath("$.code")
                            .value("INVALID_ORDER"));
        }

        postOrder(new CreateOrderRequest(
                1L, null, null, 1))
                .andExpect(status().isBadRequest());

        assertEquals(0, countOrders());
    }

    @Test
    void unicodeRoundTripsThroughJsonAndJdbc()
            throws Exception {
        String label = "Cà phê 😀 e\u0301";

        String json = postOrder(new CreateOrderRequest(
                1L, label, "Ghi chú Việt", 1))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.label").value(label))
                .andExpect(jsonPath("$.note")
                        .value("Ghi chú Việt"))
                .andReturn()
                .getResponse()
                .getContentAsString();

        JsonNode body = mapper.readTree(json);
        Long id = body.path("id").longValue();
        assertTrue(id > 0L);

        String fromDb = jdbc.queryForObject(
                "SELECT label FROM purchase_orders WHERE id = ?",
                String.class, id);

        assertEquals(label, fromDb);
        assertEquals(1, countOrders());
    }

    @Test
    void emojiBoundaryUsesUtf16Units()
            throws Exception {
        String exactly24Units = "😀".repeat(12);
        String tooLong26Units = "😀".repeat(13);

        assertEquals(24, exactly24Units.length());
        assertEquals(26, tooLong26Units.length());

        postOrder(new CreateOrderRequest(
                1L, exactly24Units, null, 1))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.label")
                        .value(exactly24Units));

        postOrder(new CreateOrderRequest(
                1L, tooLong26Units, null, 1))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        assertEquals(1, countOrders());
    }

    @Test
    void nullNoteIsAcceptedAndStoredAsSqlNull()
            throws Exception {
        String json = postOrder(new CreateOrderRequest(
                1L, "nullable note", null, 1))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.note").value(nullValue()))
                .andReturn()
                .getResponse()
                .getContentAsString();

        long id = mapper.readTree(json).path("id").asLong();

        String fromDb = jdbc.queryForObject(
                "SELECT note FROM purchase_orders WHERE id = ?",
                String.class, id);

        assertEquals(null, fromDb);
    }

    @Test
    void missingOptionalNoteAlsoMapsToNull()
            throws Exception {
        String json = postRaw("""
                {"customerId":1,"label":"note omitted",
                 "quantity":1}
                """)
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.note").value(nullValue()))
                .andReturn()
                .getResponse()
                .getContentAsString();

        long id = mapper.readTree(json).path("id").asLong();
        String note = jdbc.queryForObject(
                "SELECT note FROM purchase_orders WHERE id = ?",
                String.class, id);

        assertEquals(null, note);
    }

    @Test
    void noteBeyondMaxLengthIsRejected()
            throws Exception {
        postOrder(new CreateOrderRequest(
                1L, "note overflow", "x".repeat(101), 1))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        assertEquals(0, countOrders());
    }

    @Test
    void nonexistentCustomerIsAControlledBusinessError()
            throws Exception {
        postOrder(new CreateOrderRequest(
                999L, "orphan", null, 1))
                .andExpect(status().is(422))
                .andExpect(jsonPath("$.code")
                        .value("CUSTOMER_NOT_FOUND"));

        assertEquals(0, countOrders());
    }

    @Test
    void foreignKeyRejectsOrphanEvenWithoutServiceCheck() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbc.update(
                        """
                        INSERT INTO purchase_orders
                            (customer_id, label, note, quantity)
                        VALUES (?, ?, ?, ?)
                        """,
                        999L, "orphan", null, 1));

        assertEquals(0, countOrders());
    }

    @Test
    void referencedCustomerCannotBeDeleted() {
        jdbc.update(
                """
                INSERT INTO purchase_orders
                    (customer_id, label, note, quantity)
                VALUES (?, ?, ?, ?)
                """,
                1L, "linked", null, 1);

        assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbc.update(
                        "DELETE FROM customers WHERE id = ?",
                        1L));

        assertEquals(1, countOrders());
    }

    @Test
    void checkConstraintRejectsInvalidQuantityDirectly() {
        assertThrows(
                DataIntegrityViolationException.class,
                () -> jdbc.update(
                        """
                        INSERT INTO purchase_orders
                            (customer_id, label, note, quantity)
                        VALUES (?, ?, ?, ?)
                        """,
                        1L, "wrong quantity", null, 0));

        assertEquals(0, countOrders());
    }

    @Test
    void malformedJsonReturnsSafeErrorCode()
            throws Exception {
        postRaw("""
                {"customerId":1,"label":"broken",
                 "quantity":
                """)
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("MALFORMED_JSON"));

        assertEquals(0, countOrders());
    }

    @Test
    void apostrophesAndSqlMetacharactersAreData()
            throws Exception {
        String label = "O'Reilly; --";

        postOrder(new CreateOrderRequest(
                1L, label, null, 1))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.label").value(label));

        assertEquals(1, countOrders());
    }

    @Test
    void requiredCustomerIdCannotBeNull()
            throws Exception {
        postOrder(new CreateOrderRequest(
                null, "no parent", null, 1))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.code")
                        .value("INVALID_ORDER"));

        assertEquals(0, countOrders());
    }
}
```

This is **16 test methods** in one JUnit class. Nothing mocks `JdbcTemplate`, `OrderStore`, or `OrderService`; every request exercises real Spring MVC, Jackson, Bean Validation, service, JDBC, and H2 inside the test. Because `MockMvc` invokes the controller **synchronously** on the test thread and the test is annotated `@Transactional`, each method rolls back the data it created.

**Notable assertion details:**

- `status().isCreated()` proves valid requests actually succeed; `jsonPath("$.label").value(label)` proves the response preserves Unicode per current policy.
- `countOrders()` verifies SQL row counts to rule out returning HTTP 400 after writing to the database.
- `unicodeRoundTripsThroughJsonAndJdbc` reads **back from the database** instead of only comparing response to input.
- `nullNote...` checks both JSON `null` and SQL `NULL`. If the app switches to omitting null fields via `@JsonInclude(NON_NULL)`, update both contract and tests intentionally rather than silently dropping assertions.
- The 12/13 emoji test verifies `@Size(max=24)` and `String.length()`, without claiming that equals 24 grapheme clusters.
- The foreign-key and check-constraint tests run JDBC **directly** to prove the DB rejects bad inputs; the 422 business error test verifies the separate service-level check.
- The parent-delete test confirms **no `ON DELETE CASCADE`** exists in the schema; if production adopts cascading deletes, update the test to match that policy.
- `"O'Reilly; --"` is stored **strictly as data** because JDBC uses parameterized queries rather than SQL string concatenation. This is only one regression check, not a substitute for auditing all query-building code.

**Important:** `@Transactional` on a **synchronous** MockMvc JUnit test behaves differently from real HTTP tests via `RANDOM_PORT`. Over real HTTP, the server handles requests on another thread and transaction; DB writes **commit and do not roll back** via the test client's transaction. When migrating these tests to live HTTP sockets, manage cleanup with isolated databases or separate transactions.

## 11. Unit Testing Unicode and Cases Without a Spring Context

Several properties can be verified in plain Java/JUnit, far faster than booting Spring.

Create `src/test/java/example/testing/boundaries/UnicodeBoundaryTest.java`:

```java
package example.testing.boundaries;

import java.text.Normalizer;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class UnicodeBoundaryTest {

    @Test
    void emojiLengthDiffersFromCodePointCount() {
        String emoji = "😀";
        assertEquals(2, emoji.length());
        assertEquals(
                1,
                emoji.codePointCount(0, emoji.length()));
    }

    @Test
    void canonicallyEquivalentStringsAreNotRawEqual() {
        String nfcLike = "é";
        String nfdLike = "e\u0301";

        assertFalse(nfcLike.equals(nfdLike));

        assertEquals(
                Normalizer.normalize(
                        nfcLike, Normalizer.Form.NFC),
                Normalizer.normalize(
                        nfdLike, Normalizer.Form.NFC));
    }

    @Test
    void blankAndEmptyAreDifferentProperties() {
        assertTrue("".isEmpty());
        assertTrue("".isBlank());

        assertFalse("   ".isEmpty());
        assertTrue("   ".isBlank());
    }
}
```

These three tests demonstrate Java `String` and `Normalizer`; **they do not prove** Jackson, Bean Validation, or the DB share the same behavior. Those layers are tested in `OrderHttpContractTest`. Avoid loading `@SpringBootTest` when plain Java already verifies an algorithm.

## 12. Running Tests and Scope of Results

From the project root with a Gradle wrapper:

```bash
./gradlew test --tests example.testing.boundaries.UnicodeBoundaryTest
./gradlew test --tests example.testing.boundaries.OrderHttpContractTest
```

On Windows PowerShell:

```powershell
.\gradlew.bat test --tests "example.testing.boundaries.UnicodeBoundaryTest"
.\gradlew.bat test --tests "example.testing.boundaries.OrderHttpContractTest"
```

**Expected in a properly configured environment:**

- `UnicodeBoundaryTest`: **3 JUnit methods** verifying UTF-16, Unicode normalization, and blank vs. empty.
- `OrderHttpContractTest`: **16 JUnit methods** verifying HTTP + JDBC + H2 cases.
- **19 test methods total**, provided test classes and schema match the files above.

Gradle/JUnit console output varies with version and reporter configuration; there is no single fixed stdout string for `gradlew test`. To inspect failures precisely, open the Gradle test report and read the failing method's stack trace.

**This is a MockMvc + H2 integration test**, not a live TCP port test. If switching to `@SpringBootTest(webEnvironment = RANDOM_PORT)`, test-managed `@Transactional` will not roll back server transactions; use a dedicated database isolation/cleanup strategy. For production PostgreSQL/MySQL, add Testcontainers tests covering dialect, encoding, constraints, and collation.

## 13. Standalone Java 17 Program: UnicodeBoundaryDemo.java

Create `src/main/java/example/testing/boundaries/UnicodeBoundaryDemo.java`:

```java
package example.testing.boundaries;

import java.text.Normalizer;

public class UnicodeBoundaryDemo {
    public static void main(String[] args) {
        String emoji = "😀";
        String composed = "é";
        String decomposed = "e\u0301";

        System.out.println(
                "emoji.utf16=" + emoji.length());
        System.out.println(
                "emoji.codePoints="
                        + emoji.codePointCount(
                                0, emoji.length()));
        System.out.println(
                "sameRaw=" + composed.equals(decomposed));
        System.out.println(
                "sameNFC=" + Normalizer.normalize(
                        composed, Normalizer.Form.NFC)
                        .equals(Normalizer.normalize(
                                decomposed, Normalizer.Form.NFC)));
        System.out.println(
                "blank=" + " \t\n".isBlank());
    }
}
```

Run with **JDK 17+** without Spring, Gradle, JDBC, or JUnit:

```bash
javac -encoding UTF-8 -d out src/main/java/example/testing/boundaries/UnicodeBoundaryDemo.java
java -cp out example.testing.boundaries.UnicodeBoundaryDemo
```

**Exact stdout** when the file is saved as UTF-8 and compiled with UTF-8 encoding:

```text
emoji.utf16=2
emoji.codePoints=1
sameRaw=false
sameNFC=true
blank=true
```

**Why does it print this output?** The `😀` emoji lies outside the Basic Multilingual Plane and uses two surrogate code units while representing one code point. `"é"` (U+00E9) differs from `"e\u0301"` (U+0065 + combining acute accent) under raw Java `String.equals`; after NFC normalization they match. A string containing spaces, tabs, and newlines is blank according to `String.isBlank()`.

**Limitation:** this demo does not verify how JDBC drivers store text or how H2 compares Unicode. To prove round-tripping through the database, run `unicodeRoundTripsThroughJsonAndJdbc`. To handle user-perceived grapheme clusters, apply a proper segmentation algorithm and test combining/ZWJ emoji sequences.

## 14. Advanced Testing: Decision Tables and Property-Based Tests

When the input space is huge, you cannot write a separate test for every string or ID. Combine hand-picked **boundary cases** with **property-based testing** or bounded fuzzing.

### 14.1. Request Decision Table

Define three predicates:

- `Q`: quantity in `[1, 100]`?
- `L`: label non-blank and length ≤ 24?
- `C`: `customerId` exists?

| Q | L | C | Expected |
| --- | --- | --- | --- |
| true | true | true | 201 + one row |
| false | true | true | 400; DB unchanged |
| true | false | true | 400; DB unchanged |
| true | true | false | 422; DB unchanged |
| false | false | false | 400; validation rejects before service |

**You do not always need all 2³ combinations** when conditions are independent and execution is expensive; pairwise/decision coverage works well as long as important interactions remain covered. When multiple constraints fail at once, an API may return one generic error or a list of field errors; assert per contract rather than relying on unguaranteed validator ordering.

### 14.2. Property-Based Invariants

Certain properties hold independently of specific inputs:

1. For every valid `quantity`, the DB stores that exact value and the response returns it.
2. For every `quantity < 1` or `quantity > 100`, no new row is created.
3. For every policy-valid Unicode `label`, the JSON/DB round-trip stays **unchanged** or is normalized per published policy.
4. For every nonexistent `customerId`, zero orphaned Orders exist.
5. For every rejected input, zero DB side effects occur.
6. No “dangling” child → parent reference exists after successful transactions.

Libraries such as jqwik or QuickTheories can generate inputs, provided you manage **seeds**, replay/shrinking, test duration, input sizes, and database cleanup. **Never use unseeded randomness** that introduces flaky, unreproducible failures.

### 14.3. Adversarial Unicode Cases

Cases worth testing depending on contract:

- Precomposed and decomposed Vietnamese letters: `"á"` vs. `"a\u0301"`.
- Non-BMP emojis: `😀`.
- Emojis with skin-tone modifiers or ZWJ sequences: one visual glyph made of multiple code points.
- Zero-width joiner U+200D, zero-width space U+200B.
- NBSP U+00A0, thin spaces, line breaks, tabs.
- Unpaired/invalid surrogates (when input enters a Java layer without UTF-8 decoder or JSON serializer protection).
- Strings containing apostrophes, brackets, `&`, `<`, `>`, and escape characters.
- Very long strings to test request-body limits, validation, and performance.

When testing a Unicode case, explicitly state the **expected policy** (accept, normalize, reject, or preserve). Never blindly label unfamiliar characters “invalid”; many legitimate scripts rely on combining marks and symbols.

## 15. Invalid Relationships Beyond Foreign Keys

In Order → Customer, an FK guarantees parent existence yet does not enforce every invariant:

**Wrong ownership:** User A submits User B's `customerId`. The FK succeeds because the customer exists; the application must verify principal/ownership/authorization before creating the Order. HTTP tests must exercise multiple security principals and assert `403`/`404` per policy, not just `422` for a missing parent.

**Orphaned edges in join tables:** in many-to-many tables, two independent FKs prevent dangling references at both ends. A `UNIQUE` constraint on the pair may also be needed to forbid duplicate links.

**Invalid cycles:** in hierarchical trees, a node pointing to itself or forming `A → B → A` can break domain logic even though every FK is valid. Add cycle detection, recursive database checks, or transactional checks, testing self-loops, two-node cycles, and multi-hop cycles.

**Cardinality:** if a child may have at most one active parent, enforce uniqueness/partial indexes or business logic. An FK alone confirms the parent exists rather than enforcing “at most one active assignment.”

**Race conditions:** `existsById` can pass, another transaction deletes the parent, and then `INSERT` fails. The FK protects integrity; controller/service error mapping must convert the DB exception into a stable error response. Concurrency tests need real DB isolation and explicit synchronization (latches/barriers), never `Thread.sleep`.

**Soft delete:** a parent row still exists with `deleted=true`; an FK still permits referencing it. Business-rule tests must forbid orders for deactivated customers. DB FKs do not understand active/inactive flags unless the schema includes matching constraints.

**Do not overclaim test scope:** this lesson's example proves FK existence and no-cascade behavior on H2; it does not verify authorization, soft deletes, graph cycles, or production concurrency semantics.

## 16. Failure Layers and Avoiding False Positives

| Layer | Symptom | Test to Write |
| --- | --- | --- |
| Jackson | Overflow integer, wrong type, broken JSON syntax | `HttpMessageNotReadableException` → safe error body |
| Bean Validation | 0, 101, null, blank, overlong string | HTTP 400 and DB unchanged |
| Business service | Nonexistent customer ID | HTTP 422 per policy + no insert |
| JDBC | Quotes, semicolons, Unicode data | Parameterized statements and accurate round-trip |
| Database | `CHECK`/`NOT NULL`/FK/`UNIQUE` violated | Direct SQL → `DataIntegrityViolationException` or matching DB error |
| Transaction | Service fails after an intermediate write | Rollback/commit assertions outside transaction as appropriate |
| HTTP serialization | Unicode altered, nulls dropped | JSON body + DB read-back |
| Security | Valid ID owned by another user | Dedicated role/owner policy tests |

**Every failing test should pinpoint which layer broke.** Avoid `assertThrows(Exception.class, ...)`, which passes even if the DB connection died or an unrelated bug threw. Assert the specific exception type and verify unchanged DB state; across JDBC drivers, inspect root causes, SQLStates, or constraint names when the contract distinguishes them.

**Avoid asserting exact H2 or Jackson error message wording:** messages shift across versions and locales and sometimes leak internal details. At the HTTP boundary, assert public error codes; at the repository layer, assert exception types or constraint behavior rather than locking down full exception strings.

## 17. H2 vs. Production Databases and Testcontainers

H2 gives rapid feedback, yet differs from production engines in key ways:

- **Unicode lengths:** Java `@Size`, H2 `VARCHAR(n)`, and PostgreSQL `character varying(n)` can measure surrogates and graphemes differently.
- **Collation and case sensitivity:** comparing `"é"` and `"e\u0301"` varies by collation, normalization, engine, and index.
- **NULL semantics:** `UNIQUE` with multiple NULLs, null sort order, and constraint enforcement differ across engines.
- **Foreign keys:** deferrable constraints, `ON DELETE CASCADE`/`RESTRICT`, isolation levels, and deadlocks behave differently.
- **Data types:** UUID, JSONB, timezones, decimal precision, arrays, enums, and generated columns require testing on the real engine.
- **Concurrent transactions:** H2 locking, isolation, and visibility differ from PostgreSQL and MySQL.

In Spring Boot 3.5, production-like database integration tests can use Testcontainers with `@ServiceConnection`, disabling automatic embedded DB replacement in data slices. Full-application tests need appropriate container lifecycles and connection details pointing strictly to an **ephemeral test DB**.

Illustrative **directional snippet**, not a complete class:

```java
@Testcontainers
@SpringBootTest
class PostgreSqlBoundaryTest {
    @Container
    @ServiceConnection
    static PostgreSQLContainer<?> database =
            new PostgreSQLContainer<>("postgres:16-alpine");
}
```

Running this snippet requires Testcontainers PostgreSQL, Spring Boot's testcontainers module, the PostgreSQL driver, schemas/migrations, imports, and test methods. **Do not treat it as a standalone file**; the main lesson already provides a complete H2 suite. When using containers, verify Boot/Testcontainers compatibility, Docker availability, SSL/networking, and cleanup; ensure test schemas match production migrations rather than hand-rolled test scripts alone.

## 18. Common Mistakes When Testing Boundary Data

**1. Testing only mid-range values.** `quantity=50` proves neither min nor max; add 0/1/100/101.

**2. Using primitive `int` for fields that must detect JSON null.** Missing/null silently becomes 0; use `Integer` + `@NotNull`.

**3. Using `@Size` to forbid null.** `@Size` permits null; pair with `@NotBlank` or `@NotNull`.

**4. Using `@NotNull` to forbid `""` or `"   "`.** It only rejects null; use `@NotBlank` for required non-whitespace text.

**5. Assuming one emoji equals one Java `char`.** Many emojis use surrogate pairs; `String.length()` counts UTF-16 code units.

**6. Assuming code point equals grapheme.** An accented letter or ZWJ emoji can span multiple code points while appearing as one glyph.

**7. Ignoring NFC vs. NFD.** Visually identical strings can differ in `equals` and unique index matching. Define a normalization policy.

**8. Testing Unicode only in controller responses.** JSON may look fine while DB storage corrupts it; check JDBC read-backs when needed.

**9. Assuming `NOT NULL` blocks blank strings.** It does not; SQL has no built-in notion of “visible characters.”

**10. Checking customer existence in the service without an FK.** Races or bypassed paths can still insert orphans; the DB must protect integrity.

**11. Testing FKs only via HTTP 422.** The service check may block before the DB is reached; add a direct JDBC test to prove the FK exists.

**12. Assuming an FK enforces authorization.** Another user's customer still exists; test ownership and roles separately.

**13. Testing invalid relationships by asserting only the exception.** Also assert zero orphaned rows were written.

**14. Using `JdbcTemplate` with SQL string concatenation.** Risks SQL injection and escaping bugs; use parameterized placeholders.

**15. Asserting exact SQL exception messages.** Wording varies by driver, version, and locale; return stable codes at public APIs.

**16. Using `@Transactional` in real HTTP tests assuming rollback deletes server writes.** HTTP server threads run separate transactions; clean up committed rows explicitly.

**17. Letting multiple tests share seeds/keys and depend on execution order.** Enforce test isolation, rollback, or unique fixtures.

**18. Claiming PostgreSQL collation/constraint behavior works based on H2 alone.** Verify dialect-dependent behavior on a production-like engine.

**19. Using unseeded random data.** Failures become irreproducible; use deterministic fixtures and replayable seeds for property tests.

**20. Assuming `@NotBlank` blocks all invisible Unicode.** Write custom rules aligned with your Unicode policy and test them directly.

## 19. Pre-Release QA Checklist

**Test data matrix:**

- Are min−1, min, min+1, max−1, max, and max+1 covered?
- Are null, missing, zero, empty, and blank tested for each applicable field?
- Are optional fields explicitly tested for null vs. omitted behavior?
- Are wrong JSON types, broken JSON syntax, and out-of-range numbers covered?
- Do rejected requests leave zero DB side effects?

**Unicode:**

- Are Vietnamese accented text, non-BMP emojis, and combining sequences included?
- Are UTF-16 code units, code points, and grapheme clusters distinguished?
- Are strings exactly at and one unit past `@Size(max=n)` tested?
- Is the NFC/NFD preservation vs. normalization policy explicit?
- Are round-trips verified across Jackson and the DB, not just Java Strings?
- Are production engine and collation tested separately if Unicode sorting/uniqueness is critical?

**Relationships and database:**

- Does the DB define `FOREIGN KEY`, `NOT NULL`, `CHECK`, and required `UNIQUE` constraints?
- Are invalid relationships tested by **bypassing the service** to prove DB FKs work?
- Are parent deletion and cascade/restrict behavior tested per contract?
- Are valid-but-unauthorized parent references tested per authorization policy?
- Are duplicate links, graph cycles, and soft deletes tested if required by the domain?
- Are SQL queries parameterized and transaction cleanups sound?

**Test quality:**

- Do positive tests prove valid requests succeed?
- Do negative tests verify both HTTP status/error code and unchanged DB state?
- Is the right test slice or integration level used for each boundary?
- Are source files, Gradle dependencies, and schemas consistent?
- Are real tokens and PII absent from fixtures and logs?
- Do failures clearly pinpoint whether Jackson, validation, service, or DB failed?
- Are conclusions accurately scoped to H2/MockMvc limits?

**Conclusion:** thorough boundary testing is more than tossing in `0` and `100`. You need an **intentional matrix** covering values at and adjacent to bounds, JSON null vs. missing, blank text, Unicode UTF-16/normalization behavior, and invalid relationships. Bean Validation guards the request boundary; services enforce business rules; **database FKs, CHECKs, and NOT NULLs** form the indispensable final wall. Combining HTTP/JSON tests with direct JDBC tests proves every bug is stopped at the right layer without leaving orphaned rows or mangling Unicode on round-trips.

## 20. References

- [Spring Framework — Testing Spring MVC with MockMvc](https://docs.spring.io/spring-framework/reference/testing/mockmvc.html): testing requests, responses, statuses, and JSON bodies.
- [Spring Boot 3.5 — Testing Applications](https://docs.spring.io/spring-boot/3.5/reference/testing/spring-boot-applications.html): `@SpringBootTest`, `@AutoConfigureMockMvc`, rollback, and database test boundaries.
- [Jakarta Bean Validation 3.0 — Specification](https://jakarta.ee/specifications/bean-validation/3.0/jakarta-bean-validation-spec-3.0.html): semantics of `@NotNull`, `@NotBlank`, `@Size`, `@Min`, and `@Max`.
- [Java SE 17 — String API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/lang/String.html): `length()`, `codePointCount()`, `isBlank()`.
- [Java SE 17 — Normalizer API](https://docs.oracle.com/en/java/javase/17/docs/api/java.base/java/text/Normalizer.html): Unicode NFC/NFD normalization.
- [Spring Framework — JDBC Core](https://docs.spring.io/spring-framework/reference/data-access/jdbc/core.html): `JdbcTemplate`, `SimpleJdbcInsert`, and database exceptions.
- [Spring Framework — Test-managed Transactions](https://docs.spring.io/spring-framework/reference/testing/testcontext-framework/tx.html): rollback, test isolation, and propagation.
- [Spring Boot — SQL Database Initialization](https://docs.spring.io/spring-boot/3.5/reference/how-to/data-initialization.html): embedded databases and `schema.sql`.
