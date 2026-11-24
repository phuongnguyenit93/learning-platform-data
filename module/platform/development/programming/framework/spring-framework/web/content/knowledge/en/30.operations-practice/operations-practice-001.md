# Designing a Thin HTTP Layer, Clear Service Boundaries, and Explicit Data Contracts

## 1. Why is HTTP boundary design an operational concern?

In a Spring Framework application, `@RestController` is where an HTTP request enters the system. Putting all logic directly in the controller can feel fast initially, but over time it tends to cause problems: endpoints contain SQL or JPA repository calls, transaction handling gets mixed with JSON mapping, business exceptions are returned as HTTP 500, renaming a database column alters the JSON response, and testing business logic requires starting a web server.

Designing a **thin HTTP layer** means the controller only handles responsibilities belonging to the HTTP protocol:

1. Receive and interpret input from path, query, headers, or JSON body.
2. Perform data-shape validation at the boundary (for example, Bean Validation).
3. Convert the request DTO into input for a use case/service.
4. Call the service and convert the result into a response DTO.
5. Choose the HTTP status, response headers, and a stable error contract.

The **service boundary** keeps business behavior independent of HTTP: enforcing business invariants, orchestrating repositories/domain logic, demarcating transactions, and publishing events as designed. A **data contract** is an explicit agreement on request, response, data types, optional fields, error rules, versioning, status codes, and semantics; a contract can outlive a database table or a domain class.

This is not a call to create excessive layers. For a very simple endpoint, the service can be small. The goal is for responsibilities to have a clear home, for changes to have predictable blast radius, and for tests to target the right layer.

Scope: HTTP APIs in **Spring MVC**, Java 17+ / Spring Boot 3.3.x / Spring Framework 6.1.x, with distinctions noted when using WebFlux. The runnable exercise illustrates a book registration and lookup API, using an in-memory repository to focus on architecture without needing a database.

## 2. Separating transport, application, domain, and persistence

A typical HTTP flow:

```text
HTTP client
    │ POST /api/books + JSON
    ▼
[HTTP adapter / @RestController]
  - parse/validate request DTO
  - map DTO → command
  - call application service
  - map result → response DTO + HTTP 201
    │
    ▼
[Application service / use case]
  - apply business rules
  - choose transaction boundary if needed
  - call repository port
    │
    ▼
[Repository abstraction] ← port (data access contract)
    │
    ▼
[Persistence adapter]
  - JPA/JDBC/Mongo/in-memory
    │
    ▼
Database or storage
```

| Layer/responsibility | What it knows | What it avoids |
| --- | --- | --- |
| **Controller / HTTP adapter** | URL, HTTP verb, status, headers, JSON DTO, `@Valid` | SQL, entity manager, transaction policy, lengthy business algorithms |
| **Application service** | Use cases, input command, business permissions, transactions, and orchestration | `ResponseEntity`, `HttpServletRequest`, `@RequestBody`, status 404/409 |
| **Domain** | Entities/value objects, invariants, business rules | Jackson annotations, HTTP query params, database column names |
| **Repository port** | Storage operations required by the use case | HTTP transport details |
| **Repository adapter** | Specific JDBC/JPA/SQL/index/cache/storage | HTTP serialization, response status |
| **Exception translation / advice** | Translate exceptions into public error responses | Hiding bugs as 200, leaking stack traces |

A sound dependency direction is: controller depends on service; service depends on domain and repository interface; storage implementation implements that interface. Spring dependency injection via constructor can be used. You do not need full Clean Architecture with dozens of Java modules for every CRUD endpoint; separating at least the HTTP boundary from business logic is a high-value step.

### Example signs that a controller is getting too thick

```java
// ANTI-PATTERN example; accompanying classes are omitted and not standalone-runnable.
@PostMapping("/orders")
public ResponseEntity<?> place(@RequestBody OrderEntity order) {
    order.setStatus("NEW");
    repository.save(order);
    paymentClient.charge(order.getAmount());
    emailSender.send(order.getCustomerEmail());
    return ResponseEntity.ok(order);
}
```

This snippet simultaneously accepts a persistence entity over HTTP, orchestrates payment/email, writes data, and chooses the response. Failures can leave partial state: saving the order first and then failing to charge; retrying POST can double-charge. It is difficult to guarantee transactions and idempotency.

Redesign: the HTTP adapter receives `PlaceOrderRequest` (the contract), calls `OrderApplicationService.place(command)`, the service enforces rules/transactions/outbox and returns a `PlacedOrder` result; the controller maps it to `201 Created` and a DTO. For external payments, a database transaction cannot roll back an HTTP charge that already succeeded: an idempotency key, saga/compensation, or an appropriate event-driven workflow is needed.

## 3. Define the HTTP contract before writing the controller

Start from the API contract from the consumer's perspective. Example "create book" and "get one book":

| Operation | Request | Success | Typical errors |
| --- | --- | --- | --- |
| Create book | `POST /api/books`, JSON `{"title":"Spring","isbn":"9780000000001"}` | `201 Created`, `Location: /api/books/1`, JSON response with id/title/isbn | `400` if JSON/fields are invalid; `409` if ISBN already exists |
| Lookup | `GET /api/books/{id}` | `200 OK`, JSON response | `400` if id is invalid; `404` if not found |

A request DTO is distinct from a response DTO:

```java
// Java 17+ records, fragment; full runnable file is in section 8.
public record CreateBookRequest(
        @NotBlank String title,
        @NotBlank String isbn) {}

public record BookResponse(
        long id,
        String title,
        String isbn) {}
```

The `@NotBlank` annotation belongs to Bean Validation (import `jakarta.validation.constraints.NotBlank`). It validates input at the HTTP boundary; the service should still protect core rules because a use case may be invoked from a scheduler, message listener, batch job, or test without going through the controller.

### A contract is not a database schema

Suppose the persistence entity also has `costPrice`, `supplierId`, `internalNotes`, `rowVersion`. A public API should not expose all of those fields just because the entity has getters. Serializing `@Entity` directly can leak data, trigger JSON circular references across JPA relationships, and cause lazy-loading to execute while writing the response. A DTO is an **intentional projection**.

Keep JSON names, types, and semantics stable. `id` is the resource identifier, `title` is the book title, and `isbn` is the book identifier used for duplicate checking under the demo policy. If ISBN must follow a standard format in production, add corresponding business validation instead of relying solely on `@NotBlank`.

### Contract decisions to write down explicitly

- Which fields are required and which are optional? Distinguish **missing** fields, `null` values, empty strings, and default values.
- Should POST return `201 Created` or `202 Accepted`? If created synchronously, 201; if only queued for later processing, 202 may be more accurate.
- After POST, which resource does `Location` point to? Public paths must stay consistent with GET.
- Do timestamp fields use ISO 8601/UTC or a specific timezone? What representation is used for monetary amounts (avoid arbitrary `double`)?
- Which query params are used for pagination/filtering/sorting? Are there limits on result count, string length, and payload size?
- How is the error contract structured with `status`, `detail`, `type`, and correlation ID? Does it leak internal data?
- Do we need an idempotency key for retryable POSTs, ETag/`If-Match` for concurrent updates, and versioning when changing the contract?

Document these decisions in API docs/OpenAPI + contract tests. Do not conflate accidental Jackson property-naming behavior with business decisions.

## 4. Thin controller: how is an HTTP operation written?

A controller doing only its proper job can be just a few lines:

```java
@RestController
@RequestMapping(path = "/api/books", produces = MediaType.APPLICATION_JSON_VALUE)
class BookController {
    private final BookService service;

    BookController(BookService service) {
        this.service = service;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {
        Book created = service.create(request.title(), request.isbn());
        BookResponse response = toResponse(created);
        return ResponseEntity
                .created(URI.create("/api/books/" + created.id()))
                .body(response);
    }

    @GetMapping("/{id}")
    BookResponse get(@PathVariable long id) {
        return toResponse(service.find(id));
    }

    private static BookResponse toResponse(Book book) {
        return new BookResponse(book.id(), book.title(), book.isbn());
    }
}
```

This is a **fragment**; Java imports and accompanying classes are in section 8. Key observations:

- `@RestController` corresponds to a controller with body serialization, using Spring MVC `HttpMessageConverter` to read/write JSON.
- `@RequestMapping` defines the path and `produces`; `@PostMapping(consumes=...)` defines the supported request content type. Spring can return `415` when Content-Type is unsupported and `406` when the response cannot satisfy the Accept header.
- `@Valid @RequestBody` validates the DTO if the project has a Jakarta Bean Validation provider. Malformed JSON, type mismatch, and Bean Validation can produce different exceptions.
- The controller builds `Location` and `201 Created` because that is an **HTTP** decision, not a domain rule.
- `toResponse` converts the domain object to a DTO in a controlled way; the mapper can be extracted into a separate class when complex or reused.
- The service only knows two business values and returns `Book`, **neither accepting `HttpServletRequest` nor returning `ResponseEntity`**.

For a return type like `BookResponse`, Spring defaults to 200 on success. If you need control over headers or status, return `ResponseEntity<BookResponse>`. Do not force every handler to always return `ResponseEntity<?>` when a fixed return type already expresses the contract well.

### A pragmatic rule for judging "thin"

A controller method should generally read like a pipeline: `bind → validate → map → call → map → respond`. It does not contain a long business-processing loop, does not directly call repository/persistence APIs, and does not decide business transactions. Line count is not the sole metric: a 40-line controller made purely of DTO mapping can still be reasonable, whereas a 5-line controller containing a SQL command or a non-idempotent business operation is still in the wrong place.

## 5. Service boundary: business logic, transactions, and orchestration

The application service is where **use cases** are expressed. For the book example, the key rules are:

- Title and ISBN after basic normalization must not be blank, even when the service is called outside HTTP.
- Two books with the same ISBN cannot be registered under the example's rules.
- The ID is assigned at the storage boundary, and looking up an invalid ID must fail intentionally.
- The repository is a dependency behind an interface, so the service can be unit tested without a web server or database.

```java
@Service
class BookService {
    private final BookRepository repository;

    BookService(BookRepository repository) {
        this.repository = repository;
    }

    Book create(String title, String isbn) {
        String normalizedTitle = normalize(title, "title");
        String normalizedIsbn = normalize(isbn, "isbn");
        return repository.saveUnique(normalizedTitle, normalizedIsbn);
    }

    Book find(long id) {
        if (id <= 0) {
            throw new InvalidBookInputException("id must be positive");
        }
        return repository.find(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    private static String normalize(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new InvalidBookInputException(field + " must not be blank");
        }
        return value.strip();
    }
}
```

This is a fragment extracted from the complete example, using `@Service`, the `BookRepository` interface, and the `Book` domain record. The service does not import `org.springframework.http.*` and does not define HTTP 404/409; it throws business exceptions (e.g., `BookNotFoundException`), which the HTTP advice layer translates.

### Why must the service check invariants even when the DTO has @NotBlank?

Bean Validation at the controller handles the validity of the **incoming HTTP body**, helping return 400 early. However, the service can be called from a scheduled task or other consumers. To prevent critical invariants from being bypassed, place them in the service/domain and/or database constraints.

ISBN uniqueness is a rule subject to concurrent contention. A code pattern like `if (!exists) save()` across two threads has a race condition: both see that it does not exist yet. In production, a **unique index/constraint in the database** is an essential layer of protection; the service/adapter must map duplicate-key violations to a business error. The in-memory example in section 8 uses `synchronized` to illustrate an atomic operation within one JVM, **not** a distributed locking solution across multiple nodes.

### Where does the transaction boundary sit?

Typically `@Transactional` is placed on the service method that executes a data-modifying use case:

```java
@Service
class OrderService {
    @Transactional
    public OrderResult place(PlaceOrderCommand command) {
        // Load aggregate, check rules, modify multiple tables,
        // write outbox event in the same transaction if needed.
        return ...; // conceptual fragment, does not compile standalone
    }
}
```

The line `return ...;` is descriptive notation, **not runnable Java**. For JPA/JDBC databases, an appropriate transaction manager is required. In Spring proxy mode, `@Transactional` is normally applied when invoked through a Spring proxy; self-invocation via `this.otherTransactionalMethod()` within the same object does not trigger proxy interception. A transaction only covers resources enlisted in that transaction; it does not turn an HTTP call to a payment service into something that rolls back automatically.

Do not put `@Transactional` on every controller "to be safe." That mixes persistence policy into transport and can hold a transaction open during response serialization or slow network calls. Reserve transactions for business boundaries that require consistency.

## 6. Repository port and persistence adapter

A repository interface describes **the operations the service needs**, rather than exposing every possible query or data-management API:

```java
interface BookRepository {
    Book saveUnique(String title, String isbn);
    Optional<Book> find(long id);
}
```

In the runnable example, an in-memory adapter implements this interface. If switching to JPA, you can have a Spring Data repository for `BookEntity`, while `JpaBookRepositoryAdapter` converts entity ↔ domain `Book` and implements `BookRepository`.

Dependency diagram:

```text
BookController ──► BookService ──► BookRepository (interface)
                                          ▲
                                          │ implements
                                  JpaBookRepositoryAdapter
                                          │
                                          ▼
                                Spring Data/JPA/Database
```

The benefit is that the service is easy to unit test with an in-memory/fake implementation and is not coupled to JPA lazy proxies. **It is not strictly required to create a separate repository port in every small application**; if using `JpaRepository` directly in the service is already stable, that can be acceptable. When you need to decouple the persistence model, support independent testing, or work with multiple data sources, a port/adapter creates a useful boundary.

### Rules you should not trade away

- Do not return JPA `Page<Entity>` directly out of convenience: decide on DTO fields, pagination metadata, and the public contract.
- Do not let the controller implement business conditions with scattered `if` chains; centralize them in the service/domain.
- Do not trigger lazy-loading outside a transaction accidentally when Jackson serializes an entity.
- When an API accepts IDs belonging to other users' resources, the service/security layer must enforce resource-level authorization to prevent insecure direct object reference (IDOR).
- Storage-specific errors such as `DataIntegrityViolationException` should be translated at the appropriate boundary into a domain conflict once the cause is understood, rather than blindly turning every database error into 409.

## 7. Validation, error contract, and HTTP status must stay consistent

### 7.1 Distinguishing shape validation from business validation

| Issue type | Ideal detection point | Suggested HTTP mapping |
| --- | --- | --- |
| Malformed JSON syntax or type | Spring `HttpMessageConverter` | `400 Bad Request` |
| Required title/isbn fields | `@Valid` / Bean Validation | `400 Bad Request` |
| Path ID cannot convert to `long` | Spring MVC argument binding | `400 Bad Request` |
| Parsed ID is invalid (<=0) | Service/domain | `400 Bad Request` |
| No matching resource | Service/domain | `404 Not Found` |
| ISBN already exists | Service/repository uniqueness | `409 Conflict` |
| User unauthenticated / unauthorized | Security layer | `401 Unauthorized` / `403 Forbidden` |
| Request too large / overloaded | Web/server/gateway policy | `413` or `429` as appropriate |
| Unexpected program/infra error | Exception monitoring | `500` or `503` depending on context; no stack trace |

These statuses are a **mapping policy**, not annotations inferring everything automatically. Spring MVC has default behavior for many binding/validation errors, but the application needs to define a consistent error payload.

### 7.2 Using ProblemDetail for public error reporting

Spring Framework 6 supports `ProblemDetail` according to the problem details standard; in Spring 6.1 the documentation references RFC 7807, while newer updates reference RFC 9457. Example:

```java
@RestControllerAdvice
class ApiErrorHandler {

    @ExceptionHandler(BookNotFoundException.class)
    ProblemDetail notFound(BookNotFoundException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, ex.getMessage());
    }

    @ExceptionHandler(DuplicateIsbnException.class)
    ProblemDetail duplicate(DuplicateIsbnException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT, ex.getMessage());
    }

    @ExceptionHandler(InvalidBookInputException.class)
    ProblemDetail invalid(InvalidBookInputException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, ex.getMessage());
    }
}
```

The complete example also handles `MethodArgumentNotValidException` for `@Valid`. Spring supports the `application/problem+json` content type when serializing ProblemDetail. Common fields include `type`, `title`, `status`, `detail`, `instance`; you can add controlled extension properties such as `errorCode`, `traceId`, and a `violations` list.

**Do not reflect internal exception messages directly to the public**: SQL table names, stack traces, bearer tokens, sensitive raw user input, internal hostnames, or vendor errors can leak sensitive information. The example displays `BookNotFoundException` containing a simple non-sensitive ID; production should use standardized error codes and messages.

### 7.3 Business errors are different from programming bugs

An expected `BookNotFoundException` when GETting a nonexistent ID is a business outcome, suited for 404. A `NullPointerException` in a service must not be "rescued" with `@ExceptionHandler(Exception.class)` to return 200 or 400. Log the correlation ID, return a safe 500 response, and fix the bug. If an external dependency is unavailable, returning 503 may fit the contract, while designing retry/backoff and circuit breakers independently.

For updates, combining `ETag` and `If-Match` or a version field helps detect lost updates (typically returning 412 Precondition Failed per HTTP semantics when the precondition is not met). Do not assume every `PUT` is automatically idempotent if business logic inserts extra child records or emits uncontrolled events.

## 8. Complete example: Java 17+ Spring Boot API

The book API example below runs **without a database**: it stores data in an in-memory repository, using Spring MVC and Jakarta Validation. It demonstrates the HTTP adapter, service boundary, repository port, DTOs, duplicate detection, and error contract. The in-memory mechanism does not persist data across restarts and is not intended for multi-instance deployments.

### 8.1 Structure and dependencies

```text
thin-http-demo/
├── build.gradle
└── src/
    ├── main/java/demo/ThinHttpApp.java
    └── test/java/demo/BookServiceTest.java
```

`build.gradle`:

```groovy
plugins {
    id 'java'
    id 'org.springframework.boot' version '3.3.13'
    id 'io.spring.dependency-management' version '1.1.7'
}

group = 'demo'
version = '1.0.0'

repositories {
    mavenCentral()
}

java {
    toolchain {
        languageVersion = JavaLanguageVersion.of(17)
    }
}

dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-web'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
    testImplementation 'org.springframework.boot:spring-boot-starter-test'
}

tasks.named('test') {
    useJUnitPlatform()
}

springBoot {
    mainClass = 'demo.ThinHttpApp'
}
```

Requires a Gradle version compatible with the plugin along with JDK 17+. If the project already has a Gradle Wrapper, use the wrapper; this example does not assume a wrapper is automatically present in a newly created folder. Spring Boot starter web brings in Spring MVC + Jackson; starter validation brings in Hibernate Validator/Jakarta Bean Validation implementation.

### 8.2 Full source: ThinHttpApp.java

```java
package demo;

import java.net.URI;
import java.util.HashMap;
import java.util.Map;
import java.util.Optional;

import jakarta.validation.Valid;
import jakarta.validation.constraints.NotBlank;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ProblemDetail;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Repository;
import org.springframework.stereotype.Service;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.ExceptionHandler;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.bind.annotation.RestControllerAdvice;

@SpringBootApplication
public class ThinHttpApp {
    public static void main(String[] args) {
        SpringApplication.run(ThinHttpApp.class, args);
    }
}

// ----- Public API contracts -----

record CreateBookRequest(
        @NotBlank String title,
        @NotBlank String isbn) {}

record BookResponse(
        long id,
        String title,
        String isbn) {}

// ----- Domain model and application exceptions -----

record Book(long id, String title, String isbn) {}

class BookNotFoundException extends RuntimeException {
    BookNotFoundException(long id) {
        super("Book " + id + " not found");
    }
}

class DuplicateIsbnException extends RuntimeException {
    DuplicateIsbnException(String isbn) {
        super("ISBN already exists: " + isbn);
    }
}

class InvalidBookInputException extends RuntimeException {
    InvalidBookInputException(String detail) {
        super(detail);
    }
}

// ----- Storage port -----

interface BookRepository {
    Book saveUnique(String title, String isbn);
    Optional<Book> find(long id);
}

// ----- Persistence adapter (demo only) -----

@Repository
class InMemoryBookRepository implements BookRepository {
    private final Map<Long, Book> byId = new HashMap<>();
    private final Map<String, Long> idByIsbn = new HashMap<>();
    private long nextId = 1;

    @Override
    public synchronized Book saveUnique(String title, String isbn) {
        if (idByIsbn.containsKey(isbn)) {
            throw new DuplicateIsbnException(isbn);
        }

        Book book = new Book(nextId++, title, isbn);
        byId.put(book.id(), book);
        idByIsbn.put(isbn, book.id());
        return book;
    }

    @Override
    public synchronized Optional<Book> find(long id) {
        return Optional.ofNullable(byId.get(id));
    }
}

// ----- Application service: completely independent of HTTP -----

@Service
class BookService {
    private final BookRepository repository;

    BookService(BookRepository repository) {
        this.repository = repository;
    }

    Book create(String title, String isbn) {
        String normalizedTitle = normalize(title, "title");
        String normalizedIsbn = normalize(isbn, "isbn");
        return repository.saveUnique(normalizedTitle, normalizedIsbn);
    }

    Book find(long id) {
        if (id <= 0) {
            throw new InvalidBookInputException("id must be positive");
        }
        return repository.find(id)
                .orElseThrow(() -> new BookNotFoundException(id));
    }

    private static String normalize(String value, String field) {
        if (value == null || value.isBlank()) {
            throw new InvalidBookInputException(field + " must not be blank");
        }
        return value.strip();
    }
}

// ----- HTTP adapter: bind, validate, map, respond -----

@RestController
@RequestMapping(
        path = "/api/books",
        produces = MediaType.APPLICATION_JSON_VALUE)
class BookController {
    private final BookService service;

    BookController(BookService service) {
        this.service = service;
    }

    @PostMapping(consumes = MediaType.APPLICATION_JSON_VALUE)
    ResponseEntity<BookResponse> create(
            @Valid @RequestBody CreateBookRequest request) {
        Book result = service.create(request.title(), request.isbn());
        BookResponse body = toResponse(result);
        URI location = URI.create("/api/books/" + result.id());
        return ResponseEntity.created(location).body(body);
    }

    @GetMapping("/{id}")
    BookResponse get(@PathVariable long id) {
        return toResponse(service.find(id));
    }

    private static BookResponse toResponse(Book book) {
        return new BookResponse(book.id(), book.title(), book.isbn());
    }
}

// ----- HTTP exception mapping -----

@RestControllerAdvice
class ApiErrorHandler {
    @ExceptionHandler(BookNotFoundException.class)
    ProblemDetail notFound(BookNotFoundException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.NOT_FOUND, ex.getMessage());
    }

    @ExceptionHandler(DuplicateIsbnException.class)
    ProblemDetail duplicate(DuplicateIsbnException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.CONFLICT, ex.getMessage());
    }

    @ExceptionHandler(InvalidBookInputException.class)
    ProblemDetail badInput(InvalidBookInputException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST, ex.getMessage());
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ProblemDetail invalidBody(MethodArgumentNotValidException ex) {
        return ProblemDetail.forStatusAndDetail(
                HttpStatus.BAD_REQUEST,
                "Request body validation failed");
    }
}
```

**Why does a single Java file still show the boundaries?** Java allows only one public class (`ThinHttpApp`), while the remaining top-level classes/records are package-private in the same file. This is a way to shorten the example setup. In a real codebase, they should be split by responsibility, such as `api/`, `application/`, `domain/`, and `persistence/`, so ownership and visibility are clearer. `InMemoryBookRepository` uses `synchronized` on both writes and reads to keep the two maps consistent within one process; replace it with appropriate storage in real deployments.

The controller does not know those two maps exist. The service does not know `ResponseEntity` or `ProblemDetail`. Switching from in-memory to a JPA adapter only affects the repository implementation and wiring as long as the interface remains unchanged.

### 8.3 Unit testing the service without a Spring context

`src/test/java/demo/BookServiceTest.java`:

```java
package demo;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BookServiceTest {

    @Test
    void createsAndFindsBook() {
        BookService service =
                new BookService(new InMemoryBookRepository());

        Book book = service.create("  Spring HTTP  ", "  123  ");

        assertEquals(1L, book.id());
        assertEquals("Spring HTTP", book.title());
        assertEquals("123", book.isbn());
        assertEquals(book, service.find(1L));
    }

    @Test
    void rejectsDuplicateAndMissingBook() {
        BookService service =
                new BookService(new InMemoryBookRepository());

        service.create("First", "ISBN-1");

        assertThrows(DuplicateIsbnException.class,
                () -> service.create("Other", "ISBN-1"));
        assertThrows(BookNotFoundException.class,
                () -> service.find(42L));
        assertThrows(InvalidBookInputException.class,
                () -> service.find(0L));
    }
}
```

The test invokes the service like a regular Java object. There is no Tomcat, HTTP, Spring `ApplicationContext`, Jackson, or database. This is a good sign: **business logic has its own boundary** and can be verified independently.

Run:

```bash
gradle test
gradle bootRun
```

In practice, `gradle test` is a command that finishes and then `gradle bootRun` starts the server; when using two separate terminals, you can run them independently. If a wrapper is present: `./gradlew test` / `./gradlew bootRun`, or on PowerShell `.\gradlew.bat test` / `.\gradlew.bat bootRun`.

Expected test result: **2 tests pass**. This is the logical expectation based on the code shown, not a report of an actual run in this environment. There is no fixed stdout from `System.out.println`; Gradle writes its own logs.

### 8.4 Using curl to verify the public contract

While the Boot server is running on port 8080, create a book:

```bash
curl -i -X POST http://localhost:8080/api/books \
  -H "Content-Type: application/json" \
  -d '{"title":"Spring HTTP","isbn":"9780000000001"}'
```

**Example success response** (only relevant status/headers/body shown; the server may add headers and vary order):

```http
HTTP/1.1 201 Created
Location: /api/books/1
Content-Type: application/json

{"id":1,"title":"Spring HTTP","isbn":"9780000000001"}
```

Next, GET:

```bash
curl -i http://localhost:8080/api/books/1
```

**Example response:**

```http
HTTP/1.1 200 OK
Content-Type: application/json

{"id":1,"title":"Spring HTTP","isbn":"9780000000001"}
```

A second POST with the same ISBN (after the service strips whitespace) returns **409 Conflict** and a `ProblemDetail` with `status:409` along with the duplicate message. Calling `GET /api/books/999` returns **404 Not Found**; calling `GET /api/books/0` returns **400 Bad Request**. A POST body `{"title":"","isbn":"x"}` is rejected by Bean Validation and returns 400 before the service creates a book. Malformed JSON syntax in the body also typically receives HTTP 400 from Spring MVC, even though it does not go through the `MethodArgumentNotValidException` handler.

**Do not assert the exact full error JSON** from the example if other auto-configurations or extensions are present. Only treat the status and defined contract fields as expected; for strict stability, add HTTP integration tests verifying response JSON keys, content type, and status.

Try a valid POST right after restarting the server: the in-memory repository resets so the ID starts again at 1. That is demo behavior, not a requirement for a production application.

### 8.5 Why do you also need HTTP contract tests?

Unit testing `BookService` cannot catch a wrong `@PostMapping` route, Jackson failing to deserialize a record, a missing `@Valid`, a wrong `Location`, or status 200 instead of 201. Therefore, you need a web test layer using `MockMvc` or running the server on a random port; with Spring Boot you can use `@WebMvcTest(BookController.class)` + a mocked service, or `@SpringBootTest` + `@AutoConfigureMockMvc` to verify wiring. Tests should assert the real contract, for example:

- `POST /api/books` with valid JSON returns `201`, the right `Location` header, and JSON with the three expected fields.
- POST missing title returns `400`, and the service is **not called**.
- Duplicate ISBN returns `409` and the `application/problem+json` error contract.
- GET for a nonexistent ID returns `404`; GET for an existing ID returns `200`.
- Invalid JSON returns `400`; a request with the wrong Content-Type can return `415`.

When security is enabled, tests must also verify proper 401/403 responses and ensure a user cannot access another user's resources. Combine unit tests for business rules, web tests for mapping, persistence integration tests for uniqueness/transactions, and end-to-end tests for critical contracts.

## 9. Designing request/response mapping without creating hidden coupling

### 9.1 DTO mapping should be explicit

In the demo, the mapper is a private method:

```java
private static BookResponse toResponse(Book book) {
    return new BookResponse(
            book.id(), book.title(), book.isbn());
}
```

If there are many endpoints, complex mappings, or a need for reuse, you can extract `BookDtoMapper`. A mapper should represent intentional data conversion without transactions, repository lookups, or network calls. MapStruct can be helpful for many fields, but it does not solve contract design on its own; you still have to choose which fields are public.

### 9.2 Contract changes that easily break clients

| Change | Impact | Safer approach |
| --- | --- | --- |
| Rename JSON `isbn` to `bookNumber` | Old clients read the wrong field | Keep a compatibility alias or version the API |
| Change `id` from number to UUID string | Client parsing/storage breaks | Design a migration and versioning |
| Turn an optional field into required | Old requests return 400 | Use a transition period, default, or endpoint version |
| Return a new optional field | Usually backward compatible with tolerant clients | Do not assume all clients ignore unknown fields |
| Change 404 to 200 + `null` | Consumer error branch breaks | Keep semantics stable, announce contract changes |
| Use a new persistence entity as response | Risks exposing internal fields | Map an explicit response DTO |
| Change order of JSON properties | Usually irrelevant to JSON semantics | Consumers should not compare raw JSON strings |

OpenAPI helps with contract discovery, but an auto-generated schema file does not replace a review of semantics. An API with valid OpenAPI can still have confusing field names or return the wrong status for domain errors.

### 9.3 Versioning, pagination, and idempotency

Versioning can live in the URL (`/api/v1/books`), a header, or a media type. More important than placement is the **compatibility policy**: which changes are breaking, how long old versions are supported, and how deprecation and migration occur.

List endpoints should specify pagination and sorting rather than returning an arbitrarily sized full dataset. Return a response DTO with `items`, `nextCursor`, or `page`/`size` as required, without leaking the internal `Page<Entity>` structure directly. Enforce a max page size at the HTTP boundary; the service must validate query scope and guard query cost.

For POSTs with side effects or payments, consider a client-sent `Idempotency-Key` header. The service/storage must persist key state per user/operation together with a request fingerprint, handling concurrency and TTL; merely reading the header in the controller without storage/deduplication does **not** achieve idempotency.

## 10. Security, observability, and operations at the boundary

### 10.1 AuthN/AuthZ is not the controller manually parsing JWTs

Authentication establishes identity and is usually handled by the Spring Security filter chain. The controller can receive the principal or required security context, and then the application layer verifies **authorization on the resource and use case**. Do not trust any `userId`/`tenantId` sent by the client as proof of ownership.

For example, `GET /api/books/42` in the demo is public with no auth. Production needs to decide who may read/create/update, protecting against IDOR and enforcing multi-tenancy. Resource constraints should be enforced in service/repository queries based on the authenticated identity, not just by hiding buttons on the frontend.

### 10.2 Layer-appropriate logging and tracing

- At the HTTP layer: log HTTP method, route template, status, latency, correlation ID/trace ID; avoid logging full Authorization headers, cookies, and sensitive bodies.
- At the service layer: log meaningful business events (book registered, order placed), outcomes, and non-sensitive identifiers without duplicating request data.
- At the persistence layer: track metrics for query latency, slow queries, and constraint violations; do not log raw database credentials.
- At exception mapping: distinguish expected client/business errors from unexpected 5xx. Do not log stack traces for expected 404s as critical errors.
- Use Spring Boot's Micrometer/Observation/trace propagation where appropriate so request IDs connect across HTTP clients, services, and storage.

Observability should not force the service to know `HttpServletRequest`; pass explicit business context/correlation when truly needed, or rely on properly managed tracing context.

### 10.3 Timeouts, resources, and avoiding inappropriate blocking

With MVC/Servlet, the request thread can be held during synchronous database/remote API calls; connection pools, timeouts, and concurrency limits are essential. With WebFlux, the controller should return a reactive pipeline and avoid `block()` on the event loop. The service boundary must remain clear even when method signatures are `Mono<Result>` or `Flux<Result>`.

When the service calls external APIs, define connect/response timeouts, conditional retries, circuit breakers, and appropriate backpressure. Do not put `Thread.sleep`, infinite retries, or synchronization on a global lock in the controller to mitigate load bottlenecks. For very long tasks, you can return `202 Accepted` with an operation ID and offload background/job processing by design instead of keeping an HTTP request open too long.

## 11. Choosing a package structure and refactoring bloated controllers

A simple feature-based structure is often easier to follow than a single folder containing hundreds of shared controllers/services:

```text
com.example.books/
├── api/
│   ├── BookController.java
│   ├── CreateBookRequest.java
│   ├── BookResponse.java
│   └── BookApiErrorHandler.java
├── application/
│   ├── BookService.java
│   └── BookRepository.java
├── domain/
│   ├── Book.java
│   └── DuplicateIsbnException.java
└── persistence/
    ├── JpaBookRepositoryAdapter.java
    └── BookEntity.java
```

This is an organizational model; small projects do not have to create these exact four packages. With multiple bounded contexts, each feature can manage its own domain and adapters. Name services after **use cases** (`RegisterBookService`, `PlaceOrderService`) if a class grows too large; do not let a `CommonService` handle everything.

### Safe refactoring steps

1. **Capture the current public contract:** routes, methods, JSON bodies, statuses, headers, error cases. Write HTTP tests for the behavior clients currently rely on.
2. **Identify business rules** inside the controller: state checks, resource permissions, uniqueness, transactions, orchestration.
3. **Separate request/response DTOs from persistence entities**, moving mapping into adapters; avoid unintended JSON contract changes.
4. **Move use cases into the service** with HTTP-independent inputs/outputs. Attach transaction boundaries to the service as needed.
5. **Move storage behind a repository/adapter**, using database constraints to protect concurrent data.
6. **Standardize exception translation** with `@RestControllerAdvice`/`ProblemDetail`, keeping public status codes if they are already a stable contract.
7. **Run unit + HTTP contract + persistence integration tests** and check logs/metrics before rolling out.

Do not rewrite all endpoints at once just for "architectural beauty." For legacy systems, pick one vertical slice, preserve behavior, and refactor incrementally. If a flawed contract currently exists that clients still depend on, fixing it requires a compatibility/versioning plan rather than silently switching 200 to 404 in production.

## 12. Common anti-patterns

1. **Controller calls repository directly and holds all rules:** business logic becomes hard to reuse/test, and transaction boundaries scatter.
2. **Service returns `ResponseEntity` or accepts `HttpServletRequest`:** transport coupling leaks into the application core.
3. **Returning JPA entities directly:** hard to lock down JSON schema, risks lazy loading, and exposes internal fields.
4. **Believing `@Valid` protects every rule:** it does not replace business invariants, concurrency constraints, or authorization.
5. **Non-atomic exists + save duplicate check:** concurrent execution creates duplicates; use a database unique constraint and map the error appropriately.
6. **Catching all exceptions and returning 200 with `success:false`:** violates HTTP semantics, breaks monitoring/retry/caching, and damages the client contract.
7. **Turning every business error into 500:** blurs expected outcomes and triggers false alarms.
8. **Using `Map<String,Object>` for every DTO:** typo-prone, lacks compile-time safety, leaves contracts unclear, and skips validation.
9. **Turning the service into a "God object" with dozens of dependencies:** each use case should have a clear scope; split orchestration/aggregates along domain boundaries.
10. **Using the DTO class as the domain entity:** one object carrying `@Entity`, `@JsonProperty`, `@RequestBody`, and business lifecycle forces every layer to change together.
11. **Relying on message wording instead of error codes:** clients parse the `detail` string for branching, causing breakage when text is translated.
12. **Failing to distinguish synchronous creation from async processing:** returning 201 before the job has created the resource; consider 202 + an operation status endpoint.
13. **Logging request/response bodies by default:** can leak tokens and personal data while inflating log volume.
14. **Guessing performance from layer count:** network/DB/serialization costs usually dwarf a service call; benchmark with evidence before optimizing.

## 13. Self-check exercises

**Question 1.** A controller has a method that calls a JPA repository, transfers money, and sends an email before returning a response. Why should a service be extracted?

**Answer:** The HTTP adapter currently owns business orchestration, transactions, and integration failure handling. A service should establish the use-case boundary; side effects outside the database need appropriate idempotency/outbox/saga policies.

**Question 2.** `@NotBlank` is on `CreateBookRequest.title`; do we still need to check for null/blank in the service?

**Answer:** For important invariants, yes. The service can be called from a job/message listener without passing through `@Valid`. Avoid overly complex duplicate validation, but do not let domain safety depend on HTTP.

**Question 3.** A client POSTs an ISBN that already exists; should it return 500?

**Answer:** No, if duplicates are an expected business conflict, 409 is a sensible choice. The mapping must derive from the actual rule rather than turning every database exception into 409.

**Question 4.** Are `BookService` unit tests alone enough to prove the POST endpoint returns 201 and the right Location?

**Answer:** Not yet. You need HTTP contract tests for route annotations, JSON binding, validation, status, headers, errors, security, and serialization.

**Question 5.** Should `BookEntity` be returned directly as JSON since the entity already has getters?

**Answer:** It should not. Public DTOs control fields and versioning; entities often contain internals, relationships, or persistence-specific metadata.

**Question 6.** Would spinning up three Spring instances keep ISBN uniqueness safe if each instance locks with `synchronized`?

**Answer:** No. That lock is only within one JVM. Production needs a unique index/constraint in shared storage and a mechanism to handle contention.

**Question 7.** When does a REST controller return 202 instead of 201?

**Answer:** When the request has only been **accepted for later processing** and resource creation is not yet complete. The contract should provide an operation ID/status URL for clients to check status.

**Question 8.** Once the service is separated from HTTP, can WebFlux naturally reuse the old synchronous service on the event loop?

**Answer:** Not automatically. Blocking I/O must be avoided on the event loop; you may need reactive persistence/clients, or offload blocking work to an appropriate controlled scheduler. The boundary idea remains valid, but the execution model affects signatures and thread usage.

## Official references

- [Spring Framework — Annotated Controllers (Spring MVC)](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller.html)
- [Spring Framework — RequestBody and Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-methods/requestbody.html)
- [Spring Framework — Controller Advice](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-advice.html)
- [Spring Framework — Error Responses / Problem Details](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-ann-rest-exceptions.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Framework — Transaction Management](https://docs.spring.io/spring-framework/reference/data-access/transaction.html)
- [Spring Boot — Validation](https://docs.spring.io/spring-boot/reference/io/validation.html)
- [Spring Boot — Testing](https://docs.spring.io/spring-boot/reference/testing/index.html)
