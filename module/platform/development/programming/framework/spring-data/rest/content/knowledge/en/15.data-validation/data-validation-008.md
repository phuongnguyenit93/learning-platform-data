# Coordinating Validators with Unique and Foreign Key Constraints in the Database

## Objective

A write request can be structurally valid yet still violate business rules or database integrity. For example:

- A Customer's email must be properly formatted and must not duplicate an existing email.
- An Order must reference a real Customer.
- A Customer currently referenced by an Order may not be allowed to be deleted.
- A business code must be unique within a tenant scope.

Spring Data REST can validate input data using Bean Validation or a Spring Validator before calling the repository. The database continues protecting integrity through constraints such as UNIQUE and FOREIGN KEY. These two layers complement each other:

- Validators provide early, clear errors tied to fields or business rules.
- Database constraints act as the final barrier protecting data against concurrent requests, other write paths, and application bugs.

You should not use a repository check to replace a database constraint. Between the check and the write, another transaction can alter the data. Conversely, do not rely solely on database errors when invalid data can be detected early to return helpful messages to the client.

## 1. Three Layers of Data Validation

A data write flow typically requires three distinct validation layers:

| Layer | Example | Role |
|---|---|---|
| Bean Validation / Spring Validator | @NotBlank, @Email, business rule checks | Catch invalid input before writing |
| Repository/service check | existsByEmail(...), existsById(...) | Detect conflicts or missing references to fail fast |
| Database constraint | UNIQUE, FOREIGN KEY, NOT NULL, CHECK | Protect integrity whenever any write path accesses the data |

Example with Customer:

    @Entity
    @Table(
        name = "customer",
        uniqueConstraints = {
            @UniqueConstraint(
                name = "uk_customer_email",
                columnNames = "email"
            )
        }
    )
    public class Customer {

        @Id
        @GeneratedValue
        private Long id;

        @NotBlank
        @Email
        @Column(nullable = false)
        private String email;

        @NotBlank
        private String name;
    }

Each annotation has a specific meaning:

- @NotBlank and @Email are Bean Validation rules.
- @Column(nullable = false) describes mapping and can participate in schema generation.
- @UniqueConstraint describes a unique constraint in JPA metadata so schema generation can create the corresponding constraint.
- The database only truly enforces uniqueness when the constraint exists in the running schema.

If the schema is managed with Flyway, Liquibase, or DBAs, create the constraint in the actual migration/schema. Do not assume JPA annotations automatically update production databases.

## 2. Bean Validation for Request Data

Bean Validation defines constraints on objects or properties. Spring Boot typically integrates Jakarta Bean Validation via a provider such as Hibernate Validator when the validation dependency is added to the application.

Example:

    public class CustomerRequest {

        @NotBlank
        @Email
        private String email;

        @NotBlank
        @Size(max = 120)
        private String name;
    }

Common constraints:

| Annotation | Purpose |
|---|---|
| @NotNull | Value must not be null |
| @NotBlank | String is not null and has at least one non-whitespace character |
| @NotEmpty | String/collection/map/array must not be empty |
| @Size | Limits length or number of elements |
| @Email | Checks email address shape per the validator |
| @Min / @Max | Numeric bounds |
| @Positive / @PositiveOrZero | Checks sign of a number |
| @Pattern | Checks a string against a regular expression |
| @Past / @Future | Time constraints |

Validators check data at the application level. They do not automatically create unique indexes or foreign keys in the database.

### 2.1. Distinguishing null, empty, and blank

The following three cases differ:

- null: no value present.
- empty string: "".
- whitespace-only string: "   ".

@NotNull only rejects null. @NotEmpty rejects null and empty values. @NotBlank fits when a field must contain actual text content.

For PATCH requests, distinguish an omitted property from a property explicitly sent as null. Do not mechanically apply the exact same validation group or DTO across POST, PUT, and PATCH.

### 2.2. Triggering validation

In a custom Spring MVC controller, place @Valid or @Validated on the request body:

    @PostMapping("/customers")
    public ResponseEntity<Customer> create(
            @Valid @RequestBody CustomerRequest request) {
        // Map request, save entity, return response.
    }

Spring MVC runs Bean Validation before the handler method proceeds. If the object violates constraints, the request is typically handled as a 400 Bad Request error via Spring MVC's exception handling mechanism.

With Spring Data REST, requests pass through the repository exporter. You can register a Spring Validator using Spring Data REST's validator mechanism or use a repository event handler to validate before saving. Do not assume a @Valid annotation on a custom controller automatically applies to every repository exporter endpoint.

### 2.3. Registering a validator for Spring Data REST

Spring Data REST supports Spring Validators named after the operation and domain type. For example, a validator running before creating a Customer can be registered by bean name:

    @Component("beforeCreateCustomerValidator")
    public class CustomerCreateValidator implements Validator {

        @Override
        public boolean supports(Class<?> type) {
            return Customer.class.isAssignableFrom(type);
        }

        @Override
        public void validate(Object target, Errors errors) {
            Customer customer = (Customer) target;

            if (customer.getEmail() == null
                    || customer.getEmail().isBlank()) {
                errors.rejectValue(
                    "email",
                    "customer.email.required",
                    "Email is required"
                );
            }
        }
    }

A bean name following the `beforeCreate<CustomerType>Validator` convention attaches the validator to the create operation. Spring Data REST also supports validators for save/update operations using the corresponding naming convention, such as `beforeSaveCustomerValidator`.

The domain type name in the bean name must match the simple class name per Spring Data REST's convention. Check your project's configuration and version if the validator is not invoked.

### 2.4. Using a repository event handler

Another option is handling rules before the repository saves:

    @Component
    @RepositoryEventHandler(Customer.class)
    public class CustomerEventHandler {

        private final CustomerRepository customers;

        public CustomerEventHandler(CustomerRepository customers) {
            this.customers = customers;
        }

        @HandleBeforeCreate
        public void beforeCreate(Customer customer) {
            if (customers.existsByEmail(customer.getEmail())) {
                throw new IllegalArgumentException(
                    "Email is already registered"
                );
            }
        }
    }

Event handlers are useful when rules belong to the repository exporter flow. However, checking existsByEmail is only an early check. The database must still have a unique constraint to handle concurrent requests.

Do not put complex business logic, external service calls, or non-rollbackable side effects inside validators. Validators should focus on determining whether data is valid.

## 3. UNIQUE Constraints in the Database

UNIQUE guarantees that a value or combination of values is not duplicated according to database rules.

Example where email must be unique:

    CREATE TABLE customer (
        id BIGINT PRIMARY KEY,
        email VARCHAR(255) NOT NULL,
        name VARCHAR(120) NOT NULL,
        CONSTRAINT uk_customer_email UNIQUE (email)
    );

Or with JPA:

    @Entity
    @Table(
        name = "customer",
        uniqueConstraints = @UniqueConstraint(
            name = "uk_customer_email",
            columnNames = "email"
        )
    )
    public class Customer {
        // fields
    }

### 3.1. Single-column unique constraint

A unique constraint on email prevents two rows from having the same email according to database comparison rules.

Decide whether email is case-sensitive or case-insensitive. Some databases/collations compare strings case-insensitively; others compare case-sensitively. If the business treats An@example.test and an@example.test as the same address, normalize the value or create an expression-based unique index supported by your database.

Do not merely check by arbitrarily calling toLowerCase(). Establish consistent normalization, locale, and storage rules.

### 3.2. Multi-column unique constraint

A combination of multiple columns may need to be unique even if each individual column is allowed to repeat.

For example, department code unique within each tenant:

    @Table(
        uniqueConstraints = @UniqueConstraint(
            name = "uk_department_tenant_code",
            columnNames = {"tenant_id", "code"}
        )
    )

This constraint allows two different tenants to use the same code, but prevents two departments in the same tenant from having the same code.

When checking early via the repository, the method must check the exact combination:

    boolean existsByTenantIdAndCode(Long tenantId, String code);

If you only check code without considering tenant, the validator can mistakenly reject valid data.

### 3.3. Unique constraints and null values

How UNIQUE handles null depends on the database. Many databases allow multiple rows with NULL in a unique column because NULL is not considered equal to another NULL; some database engines have specific syntax or semantics.

If a field is required to have a value, combine UNIQUE with NOT NULL. If the domain allows null, verify the exact behavior of your database and schema.

### 3.4. @Column(unique = true) and @UniqueConstraint

You can declare:

    @Column(unique = true)
    private String email;

This is convenient for single-column unique constraints. Use @Table(uniqueConstraints = ...) when you need to:

- Name the constraint.
- Create a multi-column unique constraint.
- Declare table structure explicitly.

JPA annotations primarily describe schema metadata. If the database already exists and migrations manage the schema, verify that the migration actually created the corresponding constraint.

## 4. Checking Uniqueness Before Writing

A repository can provide query methods to check for duplicates:

    public interface CustomerRepository
            extends JpaRepository<Customer, Long> {

        boolean existsByEmail(String email);

        boolean existsByEmailAndIdNot(String email, Long id);
    }

On creation:

    if (customers.existsByEmail(request.getEmail())) {
        errors.rejectValue(
            "email",
            "customer.email.duplicate",
            "Email is already registered"
        );
    }

On update, exclude the entity currently being updated:

    if (customers.existsByEmailAndIdNot(
            request.getEmail(), customerId)) {
        errors.rejectValue(
            "email",
            "customer.email.duplicate",
            "Email is already used by another customer"
        );
    }

If you forget the differing-ID condition, updating a Customer while keeping its current email will falsely report a duplicate against itself.

### 4.1. Why existsBy... is not enough

Suppose two concurrent requests both create the email `an@example.test`:

1. Transaction A checks existsByEmail and receives false.
2. Transaction B checks existsByEmail and also receives false.
3. A inserts the row.
4. B inserts the row.
5. Without a unique constraint, both may be saved.
6. With a unique constraint, only one transaction succeeds; the other is rejected by the database.

This is a race condition between check and write (time-of-check to time-of-use). Default transaction isolation does not automatically turn an exists query into a uniqueness lock for that value across all databases.

Therefore:

- Use validators/exists queries to return early, clear errors.
- Use UNIQUE to protect data in all concurrency scenarios.
- Catch and translate constraint errors into appropriate API responses.

## 5. FOREIGN KEY Constraints

A foreign key guarantees that a reference value in a child table points to a valid row in the parent table.

Example where Order must reference Customer:

    CREATE TABLE customer (
        id BIGINT PRIMARY KEY
    );

    CREATE TABLE orders (
        id BIGINT PRIMARY KEY,
        customer_id BIGINT NOT NULL,
        CONSTRAINT fk_order_customer
            FOREIGN KEY (customer_id)
            REFERENCES customer(id)
    );

With JPA:

    @Entity
    public class Order {

        @Id
        @GeneratedValue
        private Long id;

        @ManyToOne(optional = false)
        @JoinColumn(
            name = "customer_id",
            nullable = false,
            foreignKey = @ForeignKey(name = "fk_order_customer")
        )
        private Customer customer;
    }

Each element has a distinct meaning:

- @ManyToOne describes the object relationship between Order and Customer.
- optional = false describes that the association must not be missing at the mapping level.
- @JoinColumn(name = ...) specifies the foreign key column.
- nullable = false describes that the column does not accept null.
- @ForeignKey(name = ...) provides constraint name metadata for schema generation.

The database only enforces references when the foreign key actually exists in the schema.

### 5.1. Checking references before writing

You can verify that Customer exists before creating an Order:

    if (!customers.existsById(request.getCustomerId())) {
        errors.rejectValue(
            "customerId",
            "order.customer.notFound",
            "Customer does not exist"
        );
    }

Then the service loads the entity and assigns the association:

    Customer customer = customers.findById(request.getCustomerId())
        .orElseThrow(CustomerNotFoundException::new);

    Order order = new Order();
    order.setCustomer(customer);

    orders.save(order);

This produces a clear error for the client if Customer does not exist. However, Customer could still be deleted between the check and inserting Order. The database foreign key is the final layer preventing Order from pointing to a row that no longer exists.

### 5.2. Do not blindly accept whole nested entities from the client

A request body might send:

    {
      "customer": {
        "id": 1001
      }
    }

Deserializing a nested object does not prove Customer 1001 exists or that the client is authorized to use that Customer.

In an API with explicit contracts, accept customerId or an association URI, validate the ID and access permissions, and load the entity from the repository. Spring Data REST also supports referencing associations by URI according to its representation. Either way, the server must validate references and authorization.

## 6. Checks and Constraints on Update

When PUT/PATCH changes a field with a unique constraint or an association with a foreign key, validate the new state.

Example changing email:

    @Transactional
    public Customer updateEmail(Long id, String newEmail) {
        Customer customer = customers.findById(id)
            .orElseThrow(CustomerNotFoundException::new);

        if (customers.existsByEmailAndIdNot(newEmail, id)) {
            throw new DuplicateEmailException(newEmail);
        }

        customer.setEmail(newEmail);
        return customers.save(customer);
    }

Early checks provide clear business errors. Yet the unique constraint must still exist to handle two concurrent updates.

For foreign keys, updating an association requires verifying the target entity exists and is allowed to be linked. The database blocks invalid IDs, but it does not automatically understand every business rule such as same tenant, compatible status, or permission to use.

For example, an Order may only be assigned to a Customer in the same tenant. A simple foreign key to customer.id may not suffice to express this rule. Check the tenant in the service/validator and consider a composite foreign key if the schema/domain requires database-level enforcement.

## 7. Handling Database Constraint Errors

When an insert or update violates UNIQUE or FOREIGN KEY, the database rejects the statement. The persistence provider may throw an exception; Spring usually translates data access exceptions into the DataAccessException hierarchy, such as DataIntegrityViolationException.

Example handling in a service:

    @Transactional
    public Customer create(Customer customer) {
        try {
            return customers.saveAndFlush(customer);
        } catch (DataIntegrityViolationException ex) {
            throw new CustomerConstraintException(
                "Customer data conflicts with an existing record",
                ex
            );
        }
    }

This example assumes the repository is a JpaRepository. With CrudRepository, you can use EntityManager.flush or another suitable flush approach. The goal of flushing is to force the provider to send SQL early so constraint violations surface within the current handling scope.

Flush is not always the final point where errors appear. Deferred constraints may only be checked at commit time. Exception handling needs to sit at a transaction boundary capable of observing commit errors.

### 7.1. Distinguishing validation errors from constraint errors

| Error | Example | Appropriate Handling |
|---|---|---|
| Input validation | Malformed email | 400 Bad Request with field error |
| Business validation | Customer is locked and cannot create Order | Business error with status defined by API contract |
| UNIQUE violation | Two requests create the same email | Typically mapped to 409 Conflict |
| FOREIGN KEY violation | customer_id does not exist | 400 or 409 per contract; typically return a clear reference error |
| Missing resource | Item ID does not exist | 404 Not Found per contract |
| Unexported method | DELETE is disabled | 405 Method Not Allowed |

Do not assume Spring Data REST always maps every DataIntegrityViolationException to a single status. Behavior depends on exception handlers, Spring Data REST version, and application configuration. If the API needs stable statuses, define explicit exception mappings.

### 7.2. Do not return internal database details

Error responses should provide:

- A stable error code, e.g., CUSTOMER_EMAIL_DUPLICATE.
- Relevant field or resource if applicable.
- Understandable and actionable message.
- Correlation ID if needed for investigation.

Do not return raw SQL, internal schema/table names, sensitive data, stack traces, or database connection details.

### 7.3. Do not catch and continue a broken transaction

Some persistence errors mark the transaction rollback-only. After a database constraint fails, do not catch the exception and continue performing further operations in the same transaction as if everything were normal.

Let the transaction roll back, translate the exception at the appropriate boundary, and build the error response after the transaction state is clear.

## 8. Combining Validators with Spring Data REST

Validation for repository exporters can be organized into layers:

### Layer 1 — Constraints on domain/request models

Use annotations such as @NotBlank, @Email, and @Size for database-independent rules.

### Layer 2 — Validators before create/save

Use Spring Validator beans or repository event handlers to check rules requiring repository access, such as whether an email already exists or a referenced customer is valid.

### Layer 3 — Database constraints

Ensure UNIQUE, FOREIGN KEY, NOT NULL, and CHECK are created in the real schema. This is the final defense when concurrent requests or other write paths bypass validators.

### Layer 4 — Exception mapping

Translate remaining constraint errors into stable API responses. Preserve transaction rollback and avoid leaking database details.

Example handler before creation:

    @Component
    @RepositoryEventHandler(Order.class)
    public class OrderValidator {

        private final CustomerRepository customers;

        public OrderValidator(CustomerRepository customers) {
            this.customers = customers;
        }

        @HandleBeforeCreate
        public void validateBeforeCreate(Order order) {
            if (order.getCustomer() == null
                    || order.getCustomer().getId() == null
                    || !customers.existsById(
                        order.getCustomer().getId())) {
                throw new IllegalArgumentException(
                    "A valid customer reference is required"
                );
            }
        }
    }

This is an illustrative example for a pre-create rule. In real projects, use custom domain exceptions and map them to appropriate statuses/bodies. Foreign keys must still exist to protect integrity if state changes between validation and insert.

## 9. Designing Constraints in Migrations

If using Flyway, migrations can create constraints explicitly:

    ALTER TABLE customer
        ALTER COLUMN email SET NOT NULL;

    ALTER TABLE customer
        ADD CONSTRAINT uk_customer_email UNIQUE (email);

    ALTER TABLE orders
        ADD CONSTRAINT fk_order_customer
        FOREIGN KEY (customer_id)
        REFERENCES customer(id);

Exact syntax depends on the database. The example above uses PostgreSQL-style syntax; SQL Server, MySQL, Oracle, and other engines differ.

Before adding a unique constraint to a table with existing data:

1. Find duplicate values.
2. Define normalization and case-sensitivity rules.
3. Clean up existing data.
4. Create the constraint or unique index in the migration.
5. Verify the constraint was created in the target database.

Before adding a foreign key:

1. Find foreign key values without matching parent rows.
2. Clean up orphaned data.
3. Check nullability and historical data.
4. Create the foreign key.
5. Verify the constraint is enabled and active.

Do not rely on JPA annotations if the production schema is managed independently.

## 10. Testing

Test both validators and database constraints. Unit testing a validator alone does not prove the database has the constraint; database integration testing alone does not prove clients receive good error messages.

### 10.1. Testing Bean Validation

- Malformed email is rejected.
- Null or blank required fields are rejected.
- Strings exceeding limits are rejected.
- Error path and error code identify the right field.

### 10.2. Testing unique constraints

- Creating a Customer with a nonexistent email succeeds.
- Creating a Customer with a duplicate email is rejected.
- Updating a Customer while keeping its own email succeeds.
- Updating to another Customer's email is rejected.
- Two concurrent transactions creating the same email: only one transaction commits.

### 10.3. Testing foreign keys

- Creating an Order with an existing Customer succeeds.
- Creating an Order with a nonexistent Customer ID is rejected.
- Deleting a Customer referenced by an Order is rejected if the constraint uses RESTRICT/NO ACTION.
- Test deleting a Customer according to cascade policy if the domain permits it and verify the exact child rows affected.

### 10.4. Testing API responses

With MockMvc or equivalent HTTP tests, confirm:

- Validation errors return status and body per the API contract.
- Duplicate email is mapped to a conflict error with a stable code.
- Missing references are clearly described.
- Raw SQL and stack traces do not appear in responses.
- Transactions roll back when constraints fail.
- Valid requests are still saved and return proper JSON/HAL representations.

## 11. Common Pitfalls

| Symptom | Cause to Check |
|---|---|
| Validator reports duplicate but database still contains duplicates | Schema lacks UNIQUE or validator checks the wrong scope |
| Two concurrent requests both create the same value | Only exists query present, missing database unique constraint |
| Updating an entity flags a duplicate against itself | Check query lacks condition excluding current ID |
| Order referencing a nonexistent Customer is still saved | Foreign key not created or mapping/schema out of sync |
| @Column(unique = true) does not create constraint in production | Schema is managed via migrations and migration has not added the constraint |
| Error appears at commit rather than save | SQL/constraints checked at flush or commit |
| API returns 500 for duplicates | Exception mapping does not handle DataIntegrityViolationException specifically |
| Validation does not run on repository REST endpoints | Missing proper validator bean name/event handler registration or misconfiguration |
| PATCH request rejected when fields are omitted | Using create/update validation rules without distinguishing field state |
| Constraint reports confusing errors | Missing constraint name or missing translation from database exception to business error code |

## 12. Implementation Checklist

1. Identify which rules are input validation and which are database integrity.
2. Place Bean Validation constraints for format, nullability, and field limits.
3. Register Spring Validators or repository event handlers for rules requiring queries.
4. Use exists queries to detect duplicates/missing references early.
5. On updates, exclude the current entity itself from uniqueness checks.
6. Create real UNIQUE and FOREIGN KEY constraints in the schema via migrations or schema management.
7. Check race conditions: validators do not replace database constraints.
8. Identify transaction boundaries and flush/commit timing.
9. Map constraint violations to stable statuses, error codes, and messages.
10. Test valid requests, duplicates, missing references, and concurrent requests.
11. Verify the production schema actually contains the constraints.
12. Never return raw SQL or internal details to clients.

## References

- [Spring Data REST — Validation](https://docs.spring.io/spring-data/rest/reference/validation.html)
- [Spring Data REST — Events](https://docs.spring.io/spring-data/rest/reference/events.html)
- [Spring Framework — Validation](https://docs.spring.io/spring-framework/reference/core/validation/beanvalidation.html)
- [Jakarta Bean Validation — Specification](https://jakarta.ee/specifications/bean-validation/)
- [Jakarta Persistence — Table and Column mapping](https://jakarta.ee/specifications/persistence/3.2/jakarta-persistence-spec-3.2.html)
- [Spring Data JPA — Transactionality](https://docs.spring.io/spring-data/jpa/reference/jpa/transactions.html)
- [Spring Framework — DataIntegrityViolationException](https://docs.spring.io/spring-framework/docs/current/javadoc-api/org/springframework/dao/DataIntegrityViolationException.html)
