# Combining Bean Validation, Business Rules, and Database Constraints

A Spring Data JPA application needs to validate data at multiple points and across multiple layers. Bean Validation checks the shape and basic validity of input data; business rules decide whether an operation is permitted in the current state; database constraints protect data integrity right where data is stored.

These three layers solve different problems and complement one another. Validating only at the API layer is insufficient because data can arrive from batch jobs, message consumers, or other services. Relying solely on the database is also insufficient because error messages are often unfriendly to users and cannot express every business rule.

## 1. What Are the Responsibilities of the Three Validation Layers?

| Layer | Purpose | Example |
|---|---|---|
| Bean Validation | Validates structure and local data conditions | valid email format, non-empty name, quantity greater than 0 |
| Business validation | Validates rules based on domain logic, state, and context | cannot cancel a shipped order, cannot exceed granted credit limit |
| Database constraints | Protects integrity at the storage layer, even with multiple writers | UNIQUE, NOT NULL, FOREIGN KEY, CHECK |

For example, when registering a customer:

- Bean Validation rejects an empty or malformed email.
- Business rules verify whether the customer is eligible to register or whether the email is already in use under application policy.
- The database enforces a unique constraint on email to prevent two concurrent requests from creating the same email.

A condition can be checked in multiple layers when each layer serves a distinct purpose. For example, a non-negative quantity can be checked in the DTO to fail fast, in the domain model to protect business invariants, and with a CHECK constraint to protect data against all write paths.

## 2. Bean Validation on Request DTOs

For APIs, validate incoming data on DTOs. This separates the HTTP contract from JPA entities and allows the application to validate inputs before starting database operations.

Example using a Java 17 record and Jakarta Bean Validation:

```java
package com.example.customer.api;

import jakarta.validation.constraints.Email;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Size;

public record CreateCustomerRequest(
        @NotBlank(message = "Email is required")
        @Email(message = "Email format is invalid")
        @Size(max = 254, message = "Email is too long")
        String email,

        @NotBlank(message = "Name is required")
        @Size(max = 120, message = "Name is too long")
        String name
) {
}
```

The Controller triggers validation with `@Valid`:

```java
package com.example.customer.api;

import com.example.customer.Customer;
import com.example.customer.CustomerService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.*;

@RestController
@RequestMapping("/customers")
public class CustomerController {

    private final CustomerService service;

    public CustomerController(CustomerService service) {
        this.service = service;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Customer create(
            @Valid @RequestBody CreateCustomerRequest request) {
        return service.create(request);
    }
}
```

When data fails constraints on the request body, Spring MVC performs validation before invoking the service. In a typical Spring MVC setup, this failure is reported as `MethodArgumentNotValidException`; the application can translate field errors into a structured HTTP 400 response.

Key notes:

- `@NotBlank` rejects null, empty strings, and whitespace-only strings.
- `@Email` checks format according to the validator; it does not prove that the email address actually exists or belongs to the user.
- `@Size` bounds data length. The database still needs appropriate column lengths.
- `@Valid` on nested fields cascades validation to child objects; for collections, place `@Valid` on the elements to be validated.
- Without a Bean Validation provider on the classpath, annotations may not be enforced. In Spring Boot, typically add the validation starter matching your project version.

Do not accept an entity directly from a request and bind all fields. DTOs prevent clients from supplying fields like ID, status, role, or audit metadata that only the server may modify.

## 3. Validating Multi-Field Rules

Some conditions only make sense when inspecting multiple fields together, such as start date preceding end date or payment type determining which fields are required.

You can use a class-level constraint with a custom validator, or check in the service/domain if the condition depends on business logic. Class-level constraints suit structural rules of a single request; rules depending on database data or current state usually belong in the business layer.

For example, a request with a date range:

```java
public record BookingRequest(
        @NotNull LocalDate startDate,
        @NotNull LocalDate endDate
) {
}
```

The rule `startDate <= endDate` can be implemented via a custom class-level annotation such as `@ValidDateRange`. The validator receives the whole object, checks both values, and attaches errors to the object or appropriate field. When writing custom validators, handle nulls consistently: `@NotNull` constraints check nulls separately, while the range validator can skip when either bound is null to avoid duplicate error messages.

Do not cram all business rules into custom validators. Validators should generally be pure, fast, and independent of transaction state or database queries.

## 4. Placing Business Rules in Domain/Service

Business rules decide whether an action is valid in the current state. For example, a shipped order cannot be cancelled.

```java
public enum OrderStatus {
    PENDING,
    PAID,
    SHIPPED,
    CANCELLED
}
```

```java
@Entity
public class PurchaseOrder {

    @Id
    private Long id;

    @Enumerated(EnumType.STRING)
    private OrderStatus status;

    protected PurchaseOrder() {
    }

    public void cancel() {
        if (status == OrderStatus.SHIPPED) {
            throw new OrderRuleViolationException(
                    "A shipped order cannot be cancelled");
        }

        if (status == OrderStatus.CANCELLED) {
            throw new OrderRuleViolationException(
                    "The order is already cancelled");
        }

        status = OrderStatus.CANCELLED;
    }
}
```

The Service loads the aggregate, invokes the business behavior, and persists changes:

```java
@Service
public class OrderService {

    private final PurchaseOrderRepository repository;

    public OrderService(PurchaseOrderRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public void cancel(Long orderId) {
        PurchaseOrder order = repository.findById(orderId)
                .orElseThrow(() -> new OrderNotFoundException(orderId));

        order.cancel();
    }
}
```

When the entity is managed within the persistence context, JPA dirty checking tracks changes; calling `save` again for a managed entity is not strictly necessary. Repository `save` remains useful when working with new entities or detached entities as appropriate.

Placing state-coupled rules inside the aggregate ensures all callers share the same behavior. Rules requiring data from multiple aggregates or repositories—such as aggregate credit limits or subscription-dependent conditions—typically need service/domain-service orchestration and explicit transactions.

Do not rely solely on controllers to enforce business rules. Batch jobs, message consumers, or internal APIs may invoke the service without passing through a controller.

## 5. Bean Validation on Entities and the JPA Lifecycle

Some constraints can be placed on entities to validate entity state when JPA persists or updates. For example:

```java
@Entity
@Table(name = "customer")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Email
    @Column(nullable = false, length = 254)
    private String email;

    @NotBlank
    @Column(nullable = false, length = 120)
    private String name;

    protected Customer() {
    }

    public Customer(String email, String name) {
        this.email = email;
        this.name = name;
    }
}
```

When JPA is integrated with a Bean Validation provider, constraints on entities can execute during persist/update events depending on the validation mode configuration. Under default settings, the provider usually validates before writing the corresponding data; thus failures may appear at `persist`, `flush`, or final transaction commit.

However, do not treat entity annotations as the sole layer of protection:

- Write paths outside JPA such as JDBC, native SQL, or admin tools do not run JPA's Bean Validation listeners.
- Bulk JPQL updates/deletes bypass per-entity lifecycle callbacks.
- An entity can be mutated in memory before validation actually executes.
- Entity validation does not replace request DTO validation or business rules.

If the same constraint appears on both DTO and entity, clarify the role of each location. DTOs protect the input contract; entities protect object state as it passes through the JPA lifecycle.

## 6. Database Constraints as the Final Layer of Protection

Database constraints ensure data remains valid regardless of which application writes it or how concurrently writes happen.

Common constraints:

- **NOT NULL:** column must have a value.
- **UNIQUE:** disallows duplicate values or value combinations.
- **PRIMARY KEY:** uniquely identifies each row.
- **FOREIGN KEY:** ensures referential relationships point to existing rows.
- **CHECK:** restricts values via expressions, such as non-negative quantities.

Example SQL migration:

```sql
CREATE TABLE customer (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    email VARCHAR(254) NOT NULL,
    name VARCHAR(120) NOT NULL,
    CONSTRAINT uk_customer_email UNIQUE (email)
);

CREATE TABLE inventory (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    available INTEGER NOT NULL,
    CONSTRAINT ck_inventory_available_nonnegative
        CHECK (available >= 0)
);
```

Use Flyway or Liquibase to manage schema migrations in a controlled manner. Annotations like `@Column(nullable = false)`, `@Column(unique = true)`, and `@Table(uniqueConstraints = ...)` describe mappings and can assist schema generation when DDL generation is enabled. In production environments, explicit migrations verify what constraints actually exist in the database.

For relationships, declare foreign keys in the database. `@ManyToOne` or `@OneToMany` describe relationships in the object model, but do not assume mapping annotations automatically guarantee corresponding foreign keys exist when schemas are managed externally.

## 7. Why Do Pre-Write Checks Not Replace a UNIQUE Constraint?

Suppose a service checks email before creating a customer:

```java
if (repository.existsByEmail(normalizedEmail)) {
    throw new EmailAlreadyRegisteredException();
}

repository.save(new Customer(normalizedEmail, name));
```

This check helps return an early message when the email already exists at query time. Yet it does not eliminate race conditions:

1. Request A checks and sees the email does not exist.
2. Request B also checks and sees the email does not exist.
3. Both execute INSERT.
4. The database permits only one transaction to commit because of the unique constraint.

Therefore, a unique constraint is mandatory whenever data must be unique. Checking `existsByEmail` is only a UX improvement; the application must still handle database errors under contention.

If the rule is case-insensitive, normalize the email before saving and querying, or create a unique index matching your database's collation/expression support. Ensure all writers follow the same normalization rule. Do not assume `UNIQUE(email)` automatically treats `A@example.com` and `a@example.com` as equal across every database.

## 8. Translating Validation and Constraint Errors into Appropriate Responses

Errors can occur at different points in time:

| Error type | Example | Where typically detected |
|---|---|---|
| Request Bean Validation | empty email, name too long | Before calling the service |
| Business rule | cannot cancel a shipped order | Inside domain/service |
| JPA Bean Validation | entity violates `@NotNull` or `@Size` | Persist, flush, or commit |
| Database constraint | unique, foreign key, check | When database executes SQL or commits |

Spring MVC typically throws `MethodArgumentNotValidException` when `@Valid @RequestBody` fails validation. Method validation can throw `jakarta.validation.ConstraintViolationException`. JPA Bean Validation also uses Jakarta Validation exceptions.

Database constraint errors are commonly translated by Spring into `DataIntegrityViolationException`; Hibernate has `org.hibernate.exception.ConstraintViolationException` for SQL constraint failures. Distinguish Hibernate's exception from `jakarta.validation.ConstraintViolationException`: their names look similar, but their origins differ.

`@RestControllerAdvice` can standardize error responses:

```java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(MethodArgumentNotValidException.class)
    ResponseEntity<?> handleInvalidRequest(
            MethodArgumentNotValidException ex) {
        // Return HTTP 400 with the list of field errors.
        return ResponseEntity.badRequest().body(
                Map.of("error", "INVALID_REQUEST"));
    }

    @ExceptionHandler(OrderRuleViolationException.class)
    ResponseEntity<?> handleBusinessRule(
            OrderRuleViolationException ex) {
        // Return an appropriate business error, e.g. HTTP 409.
        return ResponseEntity.status(HttpStatus.CONFLICT).body(
                Map.of("error", ex.getMessage()));
    }
}
```

The snippet illustrates two error types that can be mapped directly. For `DataIntegrityViolationException`, do not assume every occurrence means a duplicate email. It can originate from unique, foreign key, NOT NULL, or CHECK constraints. Classify based on known constraint/schema metadata and business context; avoid parsing vendor-specific message strings as your primary mechanism. Never expose SQL, internal table names, or sensitive data in public responses.

When a database error surfaces only at flush or commit, catch it outside the transaction boundary, such as in the caller of a `@Transactional` service or in the request exception handler. Catching and ignoring a persistence exception inside a transaction can leave the transaction marked rollback-only.

## 9. Validation Groups and Method Validation

For the same object, some applications need different validation sets per operation. For instance, ID must be absent on create and present on update. Bean Validation supports validation groups to select which constraints run. However, avoid overusing groups to the point where DTOs become hard to read; in many cases, two separate DTOs for create and update are clearer.

Services can also enable method validation with `@Validated` and place constraints on parameters/methods:

```java
@Service
@Validated
public class InventoryService {

    public void reserve(@Positive int quantity) {
        // Execute business logic after parameters are validated.
    }
}
```

Method validation relies on Spring validation configuration and calls passing through the corresponding proxy. Internal self-invocation within the same object can bypass validation proxies. Even with method validation, rules depending on database state still belong in the business layer and database constraints.

## 10. Design and Testing Workflow

When adding a field or business operation, decide which layer owns each condition:

1. **Input:** is the data of the right type, non-empty, well-formatted, and within size limits? Use Bean Validation on DTOs.
2. **Business logic:** is the action allowed given current state, user permissions, and related data? Use domain methods or services/domain services.
3. **Data integrity:** must data be unique, required, referentially valid, or within a value range? Create database constraints via migrations.
4. **Concurrency errors:** if two transactions pass the pre-check together, does the database prevent invalid state? Use UNIQUE, CHECK, optimistic locking, or conditional updates as appropriate.
5. **Responses:** map input errors, business errors, and constraint errors to meaningful responses without leaking internal details.

Your test suite should cover:

- Requests missing email or with malformed email are rejected before the service runs.
- Domain rules reject invalid state transitions.
- Entities violating constraints are caught at persist/flush according to JPA configuration.
- The database rejects values violating NOT NULL, UNIQUE, FOREIGN KEY, or CHECK.
- Two concurrent requests registering the same email: only one transaction succeeds thanks to the unique constraint.
- Bulk updates or native SQL are tested separately since they can bypass the Bean Validation lifecycle and domain methods.
- Critical integration tests run against a production-compatible database engine; Testcontainers is a helpful option for testing constraints and concurrency instead of relying solely on an embedded mock database.

## 11. Common Design Mistakes

- **Validating only in the controller:** batch jobs, message consumers, and other callers can bypass controllers. Place shared rules in domain/service and database constraints.
- **Checking only with `existsBy...`:** two transactions can both see the data as absent. Use unique constraints as the final safeguard.
- **Putting every rule in entity annotations:** annotations do not express state-dependent rules, authorization, or cross-aggregate logic well.
- **Using database constraints to replace all validation:** databases reject invalid data, but messages are rarely user-friendly; business errors should be caught earlier when possible.
- **Confusing `@Column(nullable = false)` with an existing constraint:** check actual schema migrations and confirm the database has NOT NULL.
- **Catching every `DataIntegrityViolationException` as a duplicate email error:** failures may stem from foreign keys, checks, or other constraints. Classify by cause and context.
- **Assuming bulk updates run full entity validation:** bulk JPQL/native SQL bypasses per-entity lifecycles. Enforce conditions in the statement and protect with database constraints.
- **Testing only with H2 when production uses a different database:** differences in collation, data types, constraints, isolation, and locking can mask bugs. Use Testcontainers or an equivalent integration environment for critical behavior.

## 12. Key Takeaways

Bean Validation rejects malformed input data; business validation protects business rules and state; database constraints protect integrity across all write paths and concurrent contention. Assign clear responsibilities to each layer, enforce critical constraints in the database, handle errors at the right transaction boundary, and test against a database close to production.