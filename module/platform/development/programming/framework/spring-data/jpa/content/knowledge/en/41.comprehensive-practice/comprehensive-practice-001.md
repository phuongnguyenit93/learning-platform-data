# Building Customer Management with CRUD, Validation, and DTOs Using Spring Data JPA

## 1. Objectives and Architecture

This lab builds a customer management REST API with the following features:

- Create a new customer.
- View details by ID.
- List, search, and paginate customers.
- Update customer information.
- Delete a customer.
- Validate input data using Jakarta Bean Validation.
- Use DTOs to decouple the HTTP contract from the JPA entity.
- Return structured errors for invalid data, duplicate emails, and non-existent customers.

The application uses Java 17+, Spring Boot 3.x, Spring Web MVC, Spring Data JPA, Jakarta Validation, and H2 for the practice environment. The examples use constructor injection, Java records for DTOs, and manual mapping so learners can clearly see the data flow.

Processing flow:

~~~text
HTTP request
    |
    v
CustomerController
    |  @Valid + request DTO
    v
CustomerService
    |  transaction + business rules
    v
CustomerRepository
    |  Spring Data JPA
    v
Hibernate / EntityManager
    |
    v
Database

Entity -> mapper -> response DTO -> HTTP response
Exceptions -> GlobalExceptionHandler -> structured HTTP error
~~~

The controller receives and returns DTOs. The service executes business logic and manages transactions. The repository accesses the database. The entity represents persisted state. The mapper converts the entity into a response DTO.

Do not return entities directly from a REST controller. Doing so can expose internal fields, create coupling to persistence mappings, trigger lazy-loading outside a transaction, and cause entity changes to unintentionally alter the API.

## 2. Project Initialization and Dependencies

Create a Spring Boot project using Spring Initializr with Java 17 or higher. Select Spring Web, Spring Data JPA, Validation, H2 Database, and Spring Boot Test.

Main Maven dependencies:

~~~xml
<dependencies>
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
        <groupId>com.h2database</groupId>
        <artifactId>h2</artifactId>
        <scope>runtime</scope>
    </dependency>

    <dependency>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-test</artifactId>
        <scope>test</scope>
    </dependency>
</dependencies>
~~~

For dependencies to omit explicit versions, the project must inherit the Spring Boot parent or import the Spring Boot dependency BOM. Choose a Spring Boot version still supported in your project environment; do not manually mix versions of Spring Framework, Hibernate, and Spring Data JPA without a clear compatibility reason.

Recommended package structure:

~~~text
src/main/java/com/example/customers/
    CustomerApplication.java
    controller/
        CustomerController.java
    dto/
        CreateCustomerRequest.java
        UpdateCustomerRequest.java
        CustomerResponse.java
        PageResponse.java
        ApiError.java
    entity/
        Customer.java
    exception/
        CustomerNotFoundException.java
        DuplicateCustomerEmailException.java
        GlobalExceptionHandler.java
    mapper/
        CustomerMapper.java
    repository/
        CustomerRepository.java
    service/
        CustomerService.java

src/main/resources/
    application.properties

src/test/java/com/example/customers/
    CustomerApiIntegrationTest.java
~~~

Startup class:

~~~java
package com.example.customers;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;

@SpringBootApplication
public class CustomerApplication {

    public static void main(String[] args) {
        SpringApplication.run(CustomerApplication.class, args);
    }
}
~~~

## 3. Table Design and the Customer Entity

A customer has the following fields:

| Field | Java Type | Rules |
|---|---|---|
| id | Long | Primary key, database-generated |
| fullName | String | Required, maximum 120 characters |
| email | String | Required, maximum 320 characters, unique |
| phone | String | Optional, maximum 20 characters |
| createdAt | Instant | Creation timestamp |
| updatedAt | Instant | Most recent update timestamp |
| version | long | Optimistic locking |

Entity:

~~~java
package com.example.customers.entity;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(
    name = "customers",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_customers_email",
        columnNames = "email"
    )
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(name = "full_name", nullable = false, length = 120)
    private String fullName;

    @Column(nullable = false, length = 320)
    private String email;

    @Column(length = 20)
    private String phone;

    @Column(name = "created_at", nullable = false, updatable = false)
    private Instant createdAt;

    @Column(name = "updated_at", nullable = false)
    private Instant updatedAt;

    @Version
    private long version;

    protected Customer() {
        // Required by JPA.
    }

    public Customer(String fullName, String email, String phone) {
        this.fullName = fullName;
        this.email = email;
        this.phone = phone;
    }

    public void updateProfile(
            String fullName,
            String email,
            String phone) {
        this.fullName = fullName;
        this.email = email;
        this.phone = phone;
    }

    @PrePersist
    void onCreate() {
        Instant now = Instant.now();
        this.createdAt = now;
        this.updatedAt = now;
    }

    @PreUpdate
    void onUpdate() {
        this.updatedAt = Instant.now();
    }

    public Long getId() {
        return id;
    }

    public String getFullName() {
        return fullName;
    }

    public String getEmail() {
        return email;
    }

    public String getPhone() {
        return phone;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public Instant getUpdatedAt() {
        return updatedAt;
    }

    public long getVersion() {
        return version;
    }
}
~~~

Key points to understand:

- The no-arg constructor has protected visibility so JPA can instantiate the entity.
- The business constructor accepts the fields allowed to be set upon creation.
- No public setters are provided for ID, timestamps, or version.
- The `updateProfile` method expresses allowed business state changes.
- `@PrePersist` and `@PreUpdate` are lifecycle callbacks to update timestamps.
- `@Version` helps Hibernate detect concurrent updates when the entity is written.
- The database unique constraint is the final safeguard preventing two transactions from creating duplicate emails simultaneously.

Normalize email to lowercase before saving so values such as `An@Example.com` and `an@example.com` do not become two different customers under the application's rules. If the system needs to preserve original email casing for display, you can store the display value separately alongside a `normalized_email` column with a unique index.

Do not rely solely on duplicate email checks in Java. Two concurrent requests can both check and see that the email does not exist yet, then both insert. A database unique constraint is what guarantees uniqueness under contention.

## 4. Creating Request DTOs and Validation

A DTO is an object representing data exchanged over the API. A request DTO contains only the fields the client is allowed to send. It does not contain database-generated IDs, timestamps, version, or internal attributes.

### CreateCustomerRequest

~~~java
package com.example.customers.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(

    @NotBlank(message = "Full name is required")
    @Size(max = 120, message = "Full name must not exceed 120 characters")
    String fullName,

    @NotBlank(message = "Email is required")
    @Email(message = "Email format is invalid")
    @Size(max = 320, message = "Email must not exceed 320 characters")
    String email,

    @Size(max = 20, message = "Phone must not exceed 20 characters")
    @Pattern(
        regexp = "^$|^[0-9+(). -]{7,20}$",
        message = "Phone must contain 7 to 20 valid characters"
    )
    String phone
) {
}
~~~

### UpdateCustomerRequest

With PUT, the request is treated as a full replacement of the editable information. Therefore, `fullName` and `email` remain required. `phone` can be an empty string or null if the user wants to remove the phone number.

~~~java
package com.example.customers.dto;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record UpdateCustomerRequest(

    @NotBlank(message = "Full name is required")
    @Size(max = 120, message = "Full name must not exceed 120 characters")
    String fullName,

    @NotBlank(message = "Email is required")
    @Email(message = "Email format is invalid")
    @Size(max = 320, message = "Email must not exceed 320 characters")
    String email,

    @Size(max = 20, message = "Phone must not exceed 20 characters")
    @Pattern(
        regexp = "^$|^[0-9+(). -]{7,20}$",
        message = "Phone must contain 7 to 20 valid characters"
    )
    String phone
) {
}
~~~

Important annotations:

| Annotation | Meaning |
|---|---|
| @NotNull | Value must not be null |
| @NotBlank | String must not be null, empty, or whitespace-only |
| @NotEmpty | Not null and not empty; does not exclude whitespace-only |
| @Size | Limits string length or collection size |
| @Email | Checks email format at the Bean Validation level |
| @Pattern | Validates a string against a regular expression |
| @Min, @Max | Numeric value bounds |
| @Positive | Numeric value must be greater than 0 |

`@Email` does not prove that an email exists or that the sender owns the address. If the business requires verification, you must send a confirmation email or run a separate verification flow.

`@Valid` on the controller instructs Spring MVC to run Bean Validation on the request object. If the validation dependency is missing, the annotations may not execute as expected.

## 5. Response DTOs and Pagination DTO

Response DTOs define the exact data exposed by the API:

~~~java
package com.example.customers.dto;

import java.time.Instant;

public record CustomerResponse(
    Long id,
    String fullName,
    String email,
    String phone,
    Instant createdAt,
    Instant updatedAt,
    long version
) {
}
~~~

Pagination DTO:

~~~java
package com.example.customers.dto;

import java.util.List;
import org.springframework.data.domain.Page;

public record PageResponse<T>(
    List<T> content,
    int page,
    int size,
    long totalElements,
    int totalPages,
    boolean first,
    boolean last
) {

    public static <T> PageResponse<T> from(Page<T> source) {
        return new PageResponse<>(
            source.getContent(),
            source.getNumber(),
            source.getSize(),
            source.getTotalElements(),
            source.getTotalPages(),
            source.isFirst(),
            source.isLast()
        );
    }
}
~~~

Returning a dedicated pagination DTO keeps the API more stable than serializing Spring Data's `Page` implementation directly. Clients can rely on the `content`, `page`, `size`, `totalElements`, and `totalPages` fields without depending on the internal structure of `PageImpl`.

Do not put entities inside a response DTO. Converting entities to DTOs should happen in the service or mapper within an appropriate transaction to avoid accidentally accessing lazy associations after the persistence context closes.

## 6. Writing a Manual Mapper

For a simple entity, a manual mapper is easy to read and requires no extra libraries:

~~~java
package com.example.customers.mapper;

import com.example.customers.dto.CustomerResponse;
import com.example.customers.entity.Customer;

public final class CustomerMapper {

    private CustomerMapper() {
    }

    public static CustomerResponse toResponse(Customer customer) {
        return new CustomerResponse(
            customer.getId(),
            customer.getFullName(),
            customer.getEmail(),
            customer.getPhone(),
            customer.getCreatedAt(),
            customer.getUpdatedAt(),
            customer.getVersion()
        );
    }
}
~~~

The mapper does not take a request directly and blindly copy every property into the entity. The service controls which fields are changed and enforces business rules before invoking domain methods.

For large projects with many entities and complex mappings, MapStruct can be considered. Regardless of the mapper used, request-to-entity mapping must be tightly controlled to prevent mass assignment—for example, a client sending `role`, `status`, `ownerId`, or `version` that the API does not allow modifying.

## 7. Declaring CustomerRepository

Spring Data JPA provides CRUD operations via `JpaRepository`:

~~~java
package com.example.customers.repository;

import com.example.customers.entity.Customer;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    boolean existsByEmailIgnoreCase(String email);

    Page<Customer>
    findByFullNameContainingIgnoreCaseOrEmailContainingIgnoreCase(
        String fullName,
        String email,
        Pageable pageable
    );
}
~~~

`JpaRepository` already provides commonly used methods:

- `save(entity)`: inserts or updates the entity according to JPA rules.
- `findById(id)`: finds by primary key, returning an `Optional`.
- `findAll()`: retrieves all entities.
- `findAll(pageable)`: retrieves a page.
- `existsById(id)`: checks existence.
- `delete(entity)`, `deleteById(id)`: deletes an entity.
- `count()`: counts entities.

The method name `findByFullNameContainingIgnoreCaseOrEmailContainingIgnoreCase` is a derived query. Spring Data parses the method name, generates the appropriate query, and binds the parameters. `Containing` creates a substring match condition; `IgnoreCase` performs case-insensitive comparison according to the provider/database capabilities.

Do not concatenate SQL or JPQL strings from user input. Derived queries and parameter binding prevent syntax errors and reduce injection risk.

## 8. Creating Business Exceptions

Dedicated exceptions allow the service to express business scenarios clearly:

~~~java
package com.example.customers.exception;

public class CustomerNotFoundException extends RuntimeException {

    public CustomerNotFoundException(Long id) {
        super("Customer with id " + id + " was not found");
    }
}
~~~

~~~java
package com.example.customers.exception;

public class DuplicateCustomerEmailException extends RuntimeException {

    public DuplicateCustomerEmailException(String email) {
        super("Email is already registered: " + email);
    }
}
~~~

The service should not construct `ResponseEntity` or know about HTTP status codes. It only throws business exceptions; the controller advice translates exceptions into appropriate HTTP responses.

## 9. Building CustomerService

The service is where transactions and business rules are centralized.

~~~java
package com.example.customers.service;

import com.example.customers.dto.*;
import com.example.customers.entity.Customer;
import com.example.customers.exception.*;
import com.example.customers.mapper.CustomerMapper;
import com.example.customers.repository.CustomerRepository;
import java.util.Locale;
import org.springframework.data.domain.*;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerService {

    private static final int MAX_PAGE_SIZE = 100;

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public CustomerResponse create(CreateCustomerRequest request) {
        String email = normalizeEmail(request.email());

        if (repository.existsByEmailIgnoreCase(email)) {
            throw new DuplicateCustomerEmailException(email);
        }

        Customer customer = new Customer(
            request.fullName().trim(),
            email,
            normalizePhone(request.phone())
        );

        Customer saved = repository.saveAndFlush(customer);
        return CustomerMapper.toResponse(saved);
    }

    @Transactional(readOnly = true)
    public CustomerResponse getById(Long id) {
        Customer customer = repository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

        return CustomerMapper.toResponse(customer);
    }

    @Transactional(readOnly = true)
    public PageResponse<CustomerResponse> search(
            String query,
            int page,
            int size) {

        validatePage(page, size);

        Pageable pageable = PageRequest.of(
            page,
            size,
            Sort.by(
                Sort.Order.asc("fullName"),
                Sort.Order.asc("id")
            )
        );

        String term = query == null ? "" : query.trim();

        Page<Customer> customers;
        if (term.isEmpty()) {
            customers = repository.findAll(pageable);
        } else {
            customers =
                repository
                    .findByFullNameContainingIgnoreCaseOrEmailContainingIgnoreCase(
                        term,
                        term,
                        pageable
                    );
        }

        Page<CustomerResponse> responsePage =
            customers.map(CustomerMapper::toResponse);

        return PageResponse.from(responsePage);
    }

    @Transactional
    public CustomerResponse update(
            Long id,
            UpdateCustomerRequest request) {

        Customer customer = repository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

        String email = normalizeEmail(request.email());

        if (!customer.getEmail().equals(email)
                && repository.existsByEmailIgnoreCase(email)) {
            throw new DuplicateCustomerEmailException(email);
        }

        customer.updateProfile(
            request.fullName().trim(),
            email,
            normalizePhone(request.phone())
        );

        // Flush so @PreUpdate and @Version are reflected in the response.
        repository.flush();
        return CustomerMapper.toResponse(customer);
    }

    @Transactional
    public void delete(Long id) {
        Customer customer = repository.findById(id)
            .orElseThrow(() -> new CustomerNotFoundException(id));

        repository.delete(customer);
    }

    private static String normalizeEmail(String email) {
        return email.trim().toLowerCase(Locale.ROOT);
    }

    private static String normalizePhone(String phone) {
        if (phone == null || phone.isBlank()) {
            return null;
        }
        return phone.trim();
    }

    private static void validatePage(int page, int size) {
        if (page < 0) {
            throw new IllegalArgumentException(
                "Page index must be zero or greater"
            );
        }

        if (size < 1 || size > MAX_PAGE_SIZE) {
            throw new IllegalArgumentException(
                "Page size must be between 1 and " + MAX_PAGE_SIZE
            );
        }
    }
}
~~~

### Transaction Analysis

- `create`, `update`, and `delete` use write transactions.
- `getById` and `search` use read-only transactions.
- The repository is injected via constructor for testability and to avoid field injection.
- The entity is loaded inside the transaction and modified via the `updateProfile` method.
- There is no need to call `save` again on a managed entity after modifying its attributes; JPA dirty checking detects changes on flush.
- `saveAndFlush` in `create` forces the insert to be sent to the database immediately inside the method, obtaining the ID and detecting constraint violations earlier. The commit is still performed by the transaction manager.

### Duplicate Email Check and Race Conditions

`existsByEmailIgnoreCase` helps return an early, client-friendly error. However, two concurrent requests can still both pass this check. The database unique constraint guarantees that the final data has no duplicate emails.

Therefore, the application must handle both `DuplicateCustomerEmailException` and `DataIntegrityViolationException`. Do not rely on `existsByEmailIgnoreCase` as a concurrency lock.

### Stable Pagination

The service caps `size` at 100 to prevent clients from requesting hundreds of thousands of records. It sorts by `fullName` then `id` to provide a stable tie-breaker order when multiple customers share the same name.

`Page` usually requires an extra count query to compute `totalElements` and `totalPages`. If the UI does not need total page counts, `Slice` can be used to avoid the count query. For very large datasets, consider keyset pagination instead of deep offsets.

## 10. Creating CustomerController

The controller defines the HTTP contract and delegates requests to the service:

~~~java
package com.example.customers.controller;

import com.example.customers.dto.*;
import com.example.customers.service.CustomerService;
import jakarta.validation.Valid;
import java.net.URI;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;
import org.springframework.web.servlet.support.ServletUriComponentsBuilder;

@RestController
@RequestMapping("/api/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @PostMapping
    public ResponseEntity<CustomerResponse> create(
            @Valid @RequestBody CreateCustomerRequest request) {

        CustomerResponse created = service.create(request);

        URI location = ServletUriComponentsBuilder
            .fromCurrentRequest()
            .path("/{id}")
            .buildAndExpand(created.id())
            .toUri();

        return ResponseEntity.created(location).body(created);
    }

    @GetMapping("/{id}")
    public CustomerResponse getById(@PathVariable Long id) {
        return service.getById(id);
    }

    @GetMapping
    public PageResponse<CustomerResponse> search(
            @RequestParam(required = false) String q,
            @RequestParam(defaultValue = "0") int page,
            @RequestParam(defaultValue = "20") int size) {

        return service.search(q, page, size);
    }

    @PutMapping("/{id}")
    public CustomerResponse update(
            @PathVariable Long id,
            @Valid @RequestBody UpdateCustomerRequest request) {

        return service.update(id, request);
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> delete(@PathVariable Long id) {
        service.delete(id);
        return ResponseEntity.noContent().build();
    }
}
~~~

Endpoints:

| HTTP | URL | Function | Success |
|---|---|---|---|
| POST | /api/customers | Create customer | 201 Created |
| GET | /api/customers/{id} | View details | 200 OK |
| GET | /api/customers | Search/paginate | 200 OK |
| PUT | /api/customers/{id} | Full update of allowed fields | 200 OK |
| DELETE | /api/customers/{id} | Delete customer | 204 No Content |

POST returns a `Location` header pointing to the newly created resource. DELETE returns 204 because there is no response body. If the ID does not exist, the service throws `CustomerNotFoundException` and the advice returns 404.

PUT in this example performs a full replacement of the editable fields. If you want partial updates, design a PATCH DTO and explicit rules for three states: omitted field, field sent as null, and field with a value. Do not reuse a PUT DTO and silently treat null as "keep existing" because clients cannot easily predict the behavior.

## 11. Standardizing Errors with @RestControllerAdvice

Define the error structure:

~~~java
package com.example.customers.dto;

import java.time.Instant;
import java.util.Map;

public record ApiError(
    String code,
    String message,
    Map<String, String> fieldErrors,
    Instant timestamp
) {
}
~~~

Global exception handler:

~~~java
package com.example.customers.exception;

import com.example.customers.dto.ApiError;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.stream.Collectors;
import org.springframework.dao.DataIntegrityViolationException;
import org.springframework.http.*;
import org.springframework.web.bind.MethodArgumentNotValidException;
import org.springframework.web.bind.annotation.*;

@RestControllerAdvice
public class GlobalExceptionHandler {

    @ExceptionHandler(CustomerNotFoundException.class)
    public ResponseEntity<ApiError> handleNotFound(
            CustomerNotFoundException exception) {

        return response(
            HttpStatus.NOT_FOUND,
            "CUSTOMER_NOT_FOUND",
            exception.getMessage(),
            Map.of()
        );
    }

    @ExceptionHandler(DuplicateCustomerEmailException.class)
    public ResponseEntity<ApiError> handleDuplicateEmail(
            DuplicateCustomerEmailException exception) {

        return response(
            HttpStatus.CONFLICT,
            "DUPLICATE_EMAIL",
            exception.getMessage(),
            Map.of()
        );
    }

    @ExceptionHandler(MethodArgumentNotValidException.class)
    public ResponseEntity<ApiError> handleValidation(
            MethodArgumentNotValidException exception) {

        Map<String, String> errors =
            exception.getBindingResult()
                .getFieldErrors()
                .stream()
                .collect(Collectors.toMap(
                    error -> error.getField(),
                    error -> error.getDefaultMessage() == null
                        ? "Invalid value"
                        : error.getDefaultMessage(),
                    (first, ignored) -> first,
                    LinkedHashMap::new
                ));

        return response(
            HttpStatus.BAD_REQUEST,
            "VALIDATION_FAILED",
            "Request validation failed",
            errors
        );
    }

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ApiError> handleDataIntegrity(
            DataIntegrityViolationException exception) {

        return response(
            HttpStatus.CONFLICT,
            "DATA_CONSTRAINT_VIOLATION",
            "The request conflicts with an existing database constraint",
            Map.of()
        );
    }

    @ExceptionHandler(IllegalArgumentException.class)
    public ResponseEntity<ApiError> handleBadRequest(
            IllegalArgumentException exception) {

        return response(
            HttpStatus.BAD_REQUEST,
            "INVALID_ARGUMENT",
            exception.getMessage(),
            Map.of()
        );
    }

    private static ResponseEntity<ApiError> response(
            HttpStatus status,
            String code,
            String message,
            Map<String, String> fieldErrors) {

        ApiError body = new ApiError(
            code,
            message,
            fieldErrors,
            Instant.now()
        );

        return ResponseEntity.status(status).body(body);
    }
}
~~~

In a production application, log database exceptions on the server with a correlation ID while never returning SQL, internal constraint names, stack traces, or sensitive data to the client.

If you use Spring MVC method validation directly on parameters, depending on the method signature and Spring version, you may also need to handle `HandlerMethodValidationException`. This lab validates fields inside request DTOs with `@Valid`, so it focuses on `MethodArgumentNotValidException`.

## 12. Configuring the Database for the Practice Environment

With H2 in-memory:

~~~properties
spring.application.name=customer-management

spring.datasource.url=jdbc:h2:mem:customers;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.datasource.driver-class-name=org.h2.Driver

# Only use create-drop for temporary demo/test databases.
spring.jpa.hibernate.ddl-auto=create-drop

spring.jpa.open-in-view=false
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
~~~

`create-drop` creates the schema when the application starts and drops it when the `SessionFactory` closes. This setting is suitable for demos or temporary tests, not for databases that need to retain data.

`open-in-view=false` disables Open EntityManager in View. The controller must work with DTOs constructed inside the transaction, avoiding response serialization triggering lazy loading outside the service.

### Production Configuration

For shared or production databases, manage the schema with Flyway or Liquibase. Run versioned migrations and then use:

~~~properties
spring.jpa.hibernate.ddl-auto=validate
spring.jpa.open-in-view=false
~~~

`validate` checks the mappings against the existing schema. The migration tool is solely responsible for creating tables, columns, constraints, and indexes. Do not let Hibernate `update` and a migration tool modify the same schema together.

## 13. Running the Application and Calling the API

Run the application with the Maven Wrapper:

~~~bash
./mvnw spring-boot:run
~~~

Create a customer:

~~~bash
curl -i -X POST http://localhost:8080/api/customers \
  -H "Content-Type: application/json" \
  -d '{
    "fullName": "An Nguyen",
    "email": "an@example.com",
    "phone": "+84 900 123 456"
  }'
~~~

A successful response looks like:

~~~http
HTTP/1.1 201 Created
Location: http://localhost:8080/api/customers/1
Content-Type: application/json
~~~

~~~json
{
  "id": 1,
  "fullName": "An Nguyen",
  "email": "an@example.com",
  "phone": "+84 900 123 456",
  "createdAt": "2026-11-09T10:00:00Z",
  "updatedAt": "2026-11-09T10:00:00Z",
  "version": 0
}
~~~

Actual timestamps and IDs in the response are generated by the database/application and will differ from the illustrative example.

Get a customer:

~~~bash
curl http://localhost:8080/api/customers/1
~~~

Search and paginate:

~~~bash
curl "http://localhost:8080/api/customers?q=an&page=0&size=10"
~~~

The paginated response has the structure:

~~~json
{
  "content": [
    {
      "id": 1,
      "fullName": "An Nguyen",
      "email": "an@example.com",
      "phone": "+84 900 123 456",
      "createdAt": "2026-11-09T10:00:00Z",
      "updatedAt": "2026-11-09T10:00:00Z",
      "version": 0
    }
  ],
  "page": 0,
  "size": 10,
  "totalElements": 1,
  "totalPages": 1,
  "first": true,
  "last": true
}
~~~

Update a customer:

~~~bash
curl -i -X PUT http://localhost:8080/api/customers/1 \
  -H "Content-Type: application/json" \
  -d '{
    "fullName": "An Nguyen Updated",
    "email": "an@example.com",
    "phone": "+84 912 000 111"
  }'
~~~

Delete a customer:

~~~bash
curl -i -X DELETE http://localhost:8080/api/customers/1
~~~

A successful deletion returns HTTP 204 No Content.

## 14. Example Response When Validation Fails

Send a request with a blank name and an invalid email format:

~~~bash
curl -i -X POST http://localhost:8080/api/customers \
  -H "Content-Type: application/json" \
  -d '{
    "fullName": " ",
    "email": "not-an-email",
    "phone": "123"
  }'
~~~

Illustrative response:

~~~http
HTTP/1.1 400 Bad Request
Content-Type: application/json
~~~

~~~json
{
  "code": "VALIDATION_FAILED",
  "message": "Request validation failed",
  "fieldErrors": {
    "fullName": "Full name is required",
    "email": "Email format is invalid",
    "phone": "Phone must contain 7 to 20 valid characters"
  },
  "timestamp": "2026-11-09T10:00:00Z"
}
~~~

`fieldErrors` contains the violating fields and their corresponding messages. `timestamp` is the time the server processed the error.

## 15. Testing the API with MockMvc

Integration tests verify multiple components working together: controller, validation, service, repository, Hibernate, and the database.

~~~java
package com.example.customers;

import com.example.customers.repository.CustomerRepository;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.time.Instant;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.*;

@SpringBootTest
@AutoConfigureMockMvc
class CustomerApiIntegrationTest {

    @Autowired
    private MockMvc mockMvc;

    @Autowired
    private ObjectMapper objectMapper;

    @Autowired
    private CustomerRepository repository;

    @BeforeEach
    void cleanDatabase() {
        repository.deleteAllInBatch();
    }

    @Test
    void createReadUpdateAndDeleteCustomer() throws Exception {
        String createBody = """
            {
              "fullName": "An Nguyen",
              "email": "an@example.com",
              "phone": "+84 900 123 456"
            }
            """;

        MvcResult result = mockMvc.perform(
                post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(createBody)
            )
            .andExpect(status().isCreated())
            .andExpect(header().exists("Location"))
            .andExpect(jsonPath("$.email").value("an@example.com"))
            .andReturn();

        JsonNode created = objectMapper.readTree(
            result.getResponse().getContentAsString()
        );
        long id = created.get("id").asLong();
        Instant createdAt = Instant.parse(created.get("createdAt").asText());
        long createdVersion = created.get("version").asLong();

        mockMvc.perform(get("/api/customers/{id}", id))
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.fullName").value("An Nguyen"));

        // Ensure the lifecycle timestamp advances at the database precision.
        Thread.sleep(20L);

        String updateBody = """
            {
              "fullName": "An Nguyen Updated",
              "email": "an@example.com",
              "phone": "+84 912 000 111"
            }
            """;

        MvcResult updateResult = mockMvc.perform(
                put("/api/customers/{id}", id)
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(updateBody)
            )
            .andExpect(status().isOk())
            .andExpect(
                jsonPath("$.fullName").value("An Nguyen Updated")
            )
            .andReturn();

        JsonNode updated = objectMapper.readTree(
            updateResult.getResponse().getContentAsString()
        );
        Instant updatedAt = Instant.parse(updated.get("updatedAt").asText());
        long updatedVersion = updated.get("version").asLong();

        assertTrue(
            updatedAt.isAfter(createdAt),
            "updatedAt should advance after the update"
        );
        assertTrue(
            updatedVersion > createdVersion,
            "version should increment after the update"
        );

        MvcResult persistedResult = mockMvc.perform(
                get("/api/customers/{id}", id)
            )
            .andExpect(status().isOk())
            .andReturn();

        JsonNode persisted = objectMapper.readTree(
            persistedResult.getResponse().getContentAsString()
        );
        Instant persistedUpdatedAt =
            Instant.parse(persisted.get("updatedAt").asText());

        assertTrue(
            persistedUpdatedAt.isAfter(createdAt),
            "updatedAt should be persisted after the update"
        );
        assertEquals(
            updatedVersion,
            persisted.get("version").asLong(),
            "the response version should match the persisted version"
        );

        mockMvc.perform(delete("/api/customers/{id}", id))
            .andExpect(status().isNoContent());

        mockMvc.perform(get("/api/customers/{id}", id))
            .andExpect(status().isNotFound());
    }

    @Test
    void rejectsInvalidRequest() throws Exception {
        String invalidBody = """
            {
              "fullName": "",
              "email": "invalid-email",
              "phone": "123"
            }
            """;

        mockMvc.perform(
                post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(invalidBody)
            )
            .andExpect(status().isBadRequest())
            .andExpect(jsonPath("$.code").value("VALIDATION_FAILED"))
            .andExpect(jsonPath("$.fieldErrors.fullName").exists())
            .andExpect(jsonPath("$.fieldErrors.email").exists());
    }

    @Test
    void rejectsDuplicateEmailIgnoringCase() throws Exception {
        String first = """
            {
              "fullName": "An Nguyen",
              "email": "an@example.com",
              "phone": null
            }
            """;

        String duplicate = """
            {
              "fullName": "Another Customer",
              "email": "AN@EXAMPLE.COM",
              "phone": null
            }
            """;

        mockMvc.perform(
                post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(first)
            )
            .andExpect(status().isCreated());

        mockMvc.perform(
                post("/api/customers")
                    .contentType(MediaType.APPLICATION_JSON)
                    .content(duplicate)
            )
            .andExpect(status().isConflict())
            .andExpect(jsonPath("$.code").value("DUPLICATE_EMAIL"));
    }

    @Test
    void searchesAndReturnsPageMetadata() throws Exception {
        repository.saveAll(java.util.List.of(
            new com.example.customers.entity.Customer(
                "An Nguyen", "an@example.com", null
            ),
            new com.example.customers.entity.Customer(
                "Binh Tran", "binh@example.com", null
            ),
            new com.example.customers.entity.Customer(
                "An Le", "an.le@example.com", null
            )
        ));

        mockMvc.perform(
                get("/api/customers")
                    .param("q", "an")
                    .param("page", "0")
                    .param("size", "1")
            )
            .andExpect(status().isOk())
            .andExpect(jsonPath("$.content.length()").value(1))
            .andExpect(jsonPath("$.page").value(0))
            .andExpect(jsonPath("$.size").value(1))
            .andExpect(jsonPath("$.totalElements").value(2))
            .andExpect(jsonPath("$.totalPages").value(2));
    }
}
~~~

The search test matches either name or email containing the search string. With the sample data, two customers have names starting with `An` and emails containing `an`; the case-insensitive search query returns two results.

The tests use a dedicated test database and clean up data before each test. Do not run these tests against a shared or production database.

## 16. Testing the Repository and Constraints

In addition to MockMvc integration tests, `@DataJpaTest` can be used to test the repository independently:

- Derived queries find the right customers by name/email.
- `existsByEmailIgnoreCase` works regardless of uppercase/lowercase.
- Unique constraint rejects duplicate emails.
- `Pageable` returns the expected `content`, `totalElements`, and `totalPages`.
- Sorting is stable when multiple customers share the same `fullName`.
- `@Version` increments when the entity is updated.

`@DataJpaTest` typically configures an embedded database and rolls back the transaction after each test. If you need to verify DDL, collation, data types, or constraint behavior against the production engine, use Testcontainers with the same database type.

Do not rely solely on H2 to conclude that migrations or SQL will behave identically on PostgreSQL/MySQL/SQL Server. Databases differ in collation, data types, unique indexes, identity, locking, and transaction behavior.

## 17. DTO Validation vs. Business Validation

Bean Validation checks the shape of input data:

- `fullName` is not blank.
- `email` has a valid format and length limit.
- `phone` follows string pattern rules.

Business validation checks rules that depend on system state:

- Email is not already used by another customer.
- Customer exists before updating/deleting.
- Customer can be deleted according to business policy.
- Current user is authorized to modify that customer.
- Customer state allows the operation.

Do not try to cram every business rule into DTO annotations. Rules requiring database access, security context, or multiple entities should be enforced in the service/domain layer.

If a rule must always hold regardless of which API writes the data, protect it in the database with unique, foreign key, check constraints, or an appropriate mechanism, while also checking it in the service to return a friendly error.

## 18. Handling Concurrency and Optimistic Locking

The entity has `@Version`. When Hibernate updates the entity, the SQL statement typically checks the current version and increments it. If another transaction updated the same record beforehand, the update may affect 0 rows and JPA throws an optimistic locking failure.

This prevents two people editing the same customer from silently overwriting each other's data.

You can add a handler for this error:

~~~java
@ExceptionHandler(
    org.springframework.orm.ObjectOptimisticLockingFailureException.class
)
public ResponseEntity<ApiError> handleOptimisticLock(
        org.springframework.orm.ObjectOptimisticLockingFailureException exception) {

    return response(
        HttpStatus.CONFLICT,
        "CONCURRENT_MODIFICATION",
        "Customer was changed by another request. Reload and retry.",
        Map.of()
    );
}
~~~

Place this method inside `GlobalExceptionHandler` alongside the previously declared handlers. HTTP 409 indicates that the client needs to reload the latest data and decide whether to reapply its changes.

If you want the API to explicitly support optimistic concurrency at the HTTP layer, you can return `version` in the response and accept `If-Match`/`ETag` on requests. In that case, you must define version semantics, handle `412 Precondition Failed`, and ensure the version is checked inside the transaction. This lab returns `version` in the DTO so learners can extend it.

## 19. Security and API Limits

Customer CRUD typically contains personal information. Before deploying the API to a real environment, add:

- Spring Security and authentication/authorization.
- Access control by tenant/owner, not just by ID.
- HTTPS and secret management outside source code.
- Rate limits or quotas for public APIs.
- Page size limits and search query controls.
- Audit logs for create, update, and delete operations.
- Avoid logging emails, phone numbers, or sensitive request bodies unnecessarily.
- Data retention, deletion, and export policies per business requirements.
- Backups, migrations, and database monitoring.

Do not use random or hard-to-guess IDs as an authorization mechanism. Every get/update/delete operation must still verify whether the current user has permission to access the resource.

For search, enforce a maximum length on `q`, add appropriate indexes, and plan queries for large datasets. Substring searches with a leading wildcard may not use standard B-tree indexes. Inspect the execution plan and consider full-text search if required by the business.

## 20. Common Pitfalls

### 20.1. Returning Entities Directly from Controllers

This can expose internal fields, trigger lazy-loading, cause JSON cycles on bidirectional relationships, or couple the API to the database structure. Use response DTOs.

### 20.2. Forgetting @Valid on the Request Body

Validation annotations on a DTO will not run automatically in the controller unless validation is triggered on the request. Use `@Valid` together with the validation starter dependency.

### 20.3. Checking Duplicate Emails Only in the Service

Two concurrent requests can both pass `existsByEmailIgnoreCase`. Add a database unique constraint and handle `DataIntegrityViolationException`.

### 20.4. Reusing the Create DTO for Update Without Defining Semantics

PUT typically performs a full replacement of editable fields; PATCH performs a partial update. Distinguish request DTOs and how null or omitted fields are handled.

### 20.5. Allowing Clients to Send ID, Version, or Timestamps

Clients might attempt to modify internal fields or database-managed fields. Request DTOs should only contain fields allowed for editing.

### 20.6. Returning a Page of Entities Directly

The API may depend on Spring Data's serialization implementation and accidentally return entities. Map to a `PageResponse` containing DTOs.

### 20.7. Paginating Without a Stable Sort

If the sort key is not unique, records can shift between pages. Add a secondary key such as `id` to the sort order.

### 20.8. Not Limiting Page Size

Clients could request too much data, increasing memory usage, SQL time, and response size. Set a default page size and a maximum cap.

### 20.9. Calling save on Every Change to a Managed Entity

JPA dirty checking already detects changes on a managed entity within a transaction. Calling `save` again is unnecessary in that case, even if it does not necessarily cause an error.

### 20.10. Enabling Open EntityManager in View to Mask Lazy Loading Errors

Serializing entities after the service transaction can trigger unintended queries. Use DTOs built inside the transaction and consider `open-in-view=false`.

### 20.11. Using create-drop in Production

The schema can be dropped when the application shuts down. Use versioned migrations and `ddl-auto=validate` or `none`.

### 20.12. Returning Raw Database Errors to Clients

SQL, stack traces, and constraint names can reveal internal structure. Return an appropriate error code and message; log details in protected server logs.

## 21. Lab Implementation Workflow

Follow this sequence:

1. Create a Spring Boot project with Web, Data JPA, Validation, and H2.
2. Create the `Customer` entity with a unique email constraint and `@Version`.
3. Create `CreateCustomerRequest` and `UpdateCustomerRequest` with Bean Validation.
4. Create `CustomerResponse` and `PageResponse`.
5. Write `CustomerMapper`.
6. Create `CustomerRepository` with `existsByEmailIgnoreCase` and the derived search query.
7. Write business exceptions for not found and duplicate email.
8. Write `CustomerService` with transaction boundaries, email normalization, and pagination.
9. Write `CustomerController` with POST, GET, PUT, and DELETE.
10. Write `GlobalExceptionHandler` for validation and business errors.
11. Configure H2 and `open-in-view=false`.
12. Run the application and call the API using curl or Postman.
13. Write MockMvc integration tests for CRUD, validation, duplicate email, and pagination.
14. Run tests against a production-like database before deployment.

## 22. Key Takeaways

- Entities describe persistence state; DTOs describe the data the API receives and returns.
- Request DTOs restrict which fields clients may send and reduce mass-assignment risk.
- `@Valid` triggers Jakarta Bean Validation on request objects.
- `@NotBlank` suits required strings; `@Email` checks email format, not ownership.
- Services hold business rules and transaction boundaries.
- `JpaRepository` provides CRUD, derived queries, and `Pageable`.
- Mappers convert entities into response DTOs, avoiding direct entity serialization.
- A database unique constraint is mandatory to guarantee non-duplicate emails under concurrent requests.
- `@Version` supports optimistic locking and detects competing updates.
- `PageResponse` lets the API control the pagination payload structure.
- `@RestControllerAdvice` standardizes 400, 404, and 409 errors.
- Pagination requires size limits and stable sorting.
- `open-in-view=false` encourages completing DTO mapping inside the transaction.
- Use integration tests to verify that controller, validation, service, repository, and database work together properly.
- For production, use Flyway/Liquibase, security, auditing, backups, and an appropriate database engine.

This complete lab demonstrates how layers in Spring Data JPA collaborate to build a CRUD API with data validation, clear DTOs, transactions, and consistent error handling. When extending to a real project, add authorization, versioned migrations, concurrency contracts, and observability according to business requirements.

## References

- [Spring Data JPA — JPA Repositories](https://docs.spring.io/spring-data/jpa/reference/jpa.html)
- [Spring Data JPA — Query Methods](https://docs.spring.io/spring-data/jpa/reference/jpa/query-methods.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Framework — Spring MVC Validation](https://docs.spring.io/spring-framework/reference/web/webmvc/mvc-controller/ann-validation.html)
- [Spring Framework — Bean Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Spring Boot — SQL Databases](https://docs.spring.io/spring-boot/reference/data/sql.html)
- [Jakarta Bean Validation Specification](https://jakarta.ee/specifications/bean-validation/)