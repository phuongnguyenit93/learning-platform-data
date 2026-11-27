# DataIntegrityViolationException and Database Constraints

In Spring Data JPA, **DataIntegrityViolationException** typically occurs when a write operation violates a database integrity constraint, such as primary key, foreign key, UNIQUE, NOT NULL, or CHECK.

The error may not appear right on the line calling **save()**. JPA/Hibernate can defer SQL until flush or transaction commit. Therefore, you must understand when the database actually checks constraints, how Spring translates exceptions, how transactions roll back, and how to return safe errors to APIs.

This lesson also distinguishes three similarly named exceptions: **org.springframework.dao.DataIntegrityViolationException**, **org.hibernate.exception.ConstraintViolationException**, and **jakarta.validation.ConstraintViolationException**. They belong to different layers and should not be handled as a single error type.

**Example prerequisites:** Java 17 or higher, Spring Boot 3.x, Spring Data JPA, Hibernate, and Jakarta Bean Validation. The application requires **spring-boot-starter-data-jpa**, **spring-boot-starter-validation**, a JDBC driver, a DataSource, and an initialized schema. Illustrative SQL migrations must adjust identity/sequence syntax for the target database. These are components of a Spring Boot application, not standalone programs run solely with javac.

## 1. What is Data Integrity?

Data integrity is the set of rules ensuring that data stored in the database remains valid and consistent.

For example, a sales system might enforce these rules:

- Every customer must have a unique ID.
- Customer emails must not be duplicated.
- Email and display name must not be null.
- Every order must reference an existing customer.
- Order total amount must not be negative.

Databases enforce these rules using constraints. When an INSERT or UPDATE violates a constraint, the database rejects the operation and JDBC reports an error. Spring/Hibernate can wrap that error into a Java-layer exception.

Constraints are the last line of defense because they are enforced directly at the database level, even when data is written by another application, batch job, or direct SQL.

## 2. Common Constraint Types

| Constraint | Purpose | Error example |
|---|---|---|
| PRIMARY KEY | Uniquely identifies each row | Inserting an existing ID |
| UNIQUE | Disallows duplicate values or value combinations | Two customers sharing the same email |
| NOT NULL | Requires the column to have a value | Saving a null email |
| FOREIGN KEY | Ensures valid referential integrity | Order referencing a non-existent customer |
| CHECK | Ensures a conditional expression holds true | Saving a negative quantity |
| Composite UNIQUE | Disallows duplicate column combinations | Same tenant and username |

Illustrative DDL example:

~~~sql
CREATE TABLE customers (
    id BIGINT PRIMARY KEY,
    email VARCHAR(255) NOT NULL,
    display_name VARCHAR(120) NOT NULL,
    CONSTRAINT uk_customers_email UNIQUE (email)
);

CREATE TABLE orders (
    id BIGINT PRIMARY KEY,
    customer_id BIGINT NOT NULL,
    total_amount DECIMAL(12, 2) NOT NULL,
    CONSTRAINT fk_orders_customer
        FOREIGN KEY (customer_id) REFERENCES customers(id),
    CONSTRAINT ck_orders_total_nonnegative
        CHECK (total_amount >= 0)
);
~~~

Explicit constraint names such as **uk_customers_email** or **fk_orders_customer** make operations and diagnostics easier. Auto-increment syntax, schemas, and certain constraint types vary by database; place engine-appropriate DDL in Flyway or Liquibase migrations.

## 3. Database Constraints vs. Application Validation

Two validation layers are commonly used together:

- **Bean Validation** checks data at the application layer before or during entity persist/update.
- **Database constraints** protect data in storage, even when multiple applications write concurrently.

Entity example:

~~~java
@Entity
@Table(
    name = "customers",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_customers_email",
            columnNames = "email"
        )
    }
)
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Email
    @Column(nullable = false, length = 255)
    private String email;

    @NotBlank
    @Column(name = "display_name", nullable = false, length = 120)
    private String displayName;

    protected Customer() {
    }

    public Customer(String email, String displayName) {
        this.email = email;
        this.displayName = displayName;
    }

    public Long getId() {
        return id;
    }

    public String getEmail() {
        return email;
    }

    public String getDisplayName() {
        return displayName;
    }
}
~~~

In the example:

- **@NotBlank** requires the string to be non-null and contain at least one non-whitespace character.
- **@Email** checks the email address format according to the validator.
- **@Column(nullable = false)** declares mapping/schema metadata.
- **@UniqueConstraint** declares a unique constraint for schema generated from mapping.

Mapping annotations do not guarantee the production database already has those constraints. When the schema is managed by migrations, you must create constraints in the migrations. **@Column(nullable = false)** or **@UniqueConstraint** can affect DDL when Hibernate generates the schema, but they do not replace managing the deployed schema.

Bean Validation also does not replace database UNIQUE/FK/CHECK constraints. For instance, `@Email` does not ensure email uniqueness; `@NotNull` in the app does not stop another SQL client from writing null if the database lacks NOT NULL.

## 4. DataIntegrityViolationException Belongs to the Spring Layer

**org.springframework.dao.DataIntegrityViolationException** is an exception in Spring's DAO exception hierarchy. It indicates a data operation violated integrity, such as a database constraint or related data mapping error.

Characteristics:

- Unchecked exception extending **DataAccessException**.
- Can occur during repository calls or during flush/transaction commit.
- Spring exception translation reduces direct coupling to JDBC/provider exceptions.
- Does not represent only UNIQUE errors; NOT NULL, FK, and other integrity errors can also be wrapped in this type.

Import example:

~~~java
import org.springframework.dao.DataIntegrityViolationException;
~~~

Do not rely on the exception name alone to determine which specific constraint was violated. Accurate classification requires checking the cause chain, SQLState/vendor code, and constraint name if supplied by the provider.

## 5. Distinguishing Three ConstraintViolationException Classes

There are three very easily confused exception names:

| Exception | Package | Layer | Meaning |
|---|---|---|---|
| DataIntegrityViolationException | org.springframework.dao | Spring DAO | Spring-translated data integrity violation |
| ConstraintViolationException | org.hibernate.exception | Hibernate | SQL error caused by a database constraint, may include SQL and constraint name |
| ConstraintViolationException | jakarta.validation | Bean Validation | One or more object validation constraints failed |

### Hibernate Exception

**org.hibernate.exception.ConstraintViolationException** usually wraps an SQL error caused by a database constraint. It can provide:

- **getConstraintName()**: constraint name if identifiable by the driver/provider.
- **getSQLException()**: underlying SQLException.
- **getSQL()**: associated SQL statement in some contexts.

Constraint name may be null depending on the database and driver. Do not rely on text error messages for portable classification.

### Jakarta Bean Validation Exception

**jakarta.validation.ConstraintViolationException** holds a set of validation violations, such as an invalid email field or blank name. This error can occur before the database executes INSERT/UPDATE.

Example:

~~~java
import jakarta.validation.ConstraintViolationException;
~~~

Do not confuse this exception with **org.hibernate.exception.ConstraintViolationException**. When reading logs or writing catch blocks, use fully qualified package names when needed to distinguish them.

## 6. When Does DataIntegrityViolationException Occur?

A repository call may appear to complete even though SQL has not yet been sent to the database.

~~~java
@Transactional
public Customer create(Customer customer) {
    return customerRepository.save(customer);
}
~~~

JPA can hold changes in the persistence context. Hibernate executes SQL at flush points, such as:

- When the application calls **EntityManager.flush()**.
- When calling **JpaRepository.saveAndFlush()**.
- Before a query that needs pending changes synchronized.
- When the transaction commits.

Therefore, the exception can surface at commit after the service method body has finished executing. Spring's transaction interceptor performs the commit before the proxy call returns to the caller.

There are cases where the database/provider executes SQL earlier—for instance, the IDENTITY generation strategy may require an immediate INSERT. Do not rely on one fixed timing across all entities and databases.

## 7. Using Flush to Surface Errors Earlier

If you want Hibernate to send SQL and receive constraint feedback immediately within the method scope, you can use **saveAndFlush()**:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public Customer create(Customer customer) {
        return repository.saveAndFlush(customer);
    }
}
~~~

Or:

~~~java
@Transactional
public Customer create(Customer customer) {
    Customer saved = repository.save(customer);
    entityManager.flush();
    return saved;
}
~~~

**flush() is not commit.** It synchronizes pending changes in the persistence context down to the database, yet the transaction can still roll back afterward.

Some constraints configured as deferred may still only be checked at commit. Thus, flush does not guarantee every integrity error surfaces right where flush is called.

Use flush intentionally for use cases requiring early write-error detection. Do not mechanically call flush after every operation, as it forfeits batching benefits and increases database round-trips.

## 8. UNIQUE Constraints and Race Conditions

A common pre-insert check is:

~~~java
if (repository.existsByEmail(email)) {
    throw new EmailAlreadyUsedException();
}
~~~

This check helps return a user-friendly error when data already exists. However, it does not guarantee uniqueness under concurrent requests:

~~~text
Request A: existsByEmail -> false
Request B: existsByEmail -> false
Request A: INSERT email
Request B: INSERT email
Database: only one INSERT succeeds
Database: the other INSERT violates UNIQUE
~~~

This is a race condition between checking and writing. **A database UNIQUE constraint is the mechanism that enforces uniqueness concurrently.**

You can combine both:

1. Pre-check to improve normal user feedback.
2. Create an actual UNIQUE constraint in the database.
3. Catch and classify integrity errors when two requests race on the same value.
4. Return a consistent business error to the losing request.

Do not remove the database constraint just because existsByEmail is already present.

## 9. Naming Constraints for Easier Diagnostics

Migrations with explicit constraint names:

~~~sql
ALTER TABLE customers
ADD CONSTRAINT uk_customers_email UNIQUE (email);
~~~

When Hibernate receives the error, the cause chain may contain **org.hibernate.exception.ConstraintViolationException**. If the driver supplies the constraint name, Hibernate can return it via getConstraintName().

Example Hibernate-specific cause inspection:

~~~java
Throwable cause = ex.getMostSpecificCause();

if (cause instanceof
        org.hibernate.exception.ConstraintViolationException hibernateEx) {

    String constraintName = hibernateEx.getConstraintName();
}
~~~

This is a Hibernate-dependent technique. **getMostSpecificCause()** comes from Spring. In some cases, the direct cause or most-specific cause may be SQLException rather than the Hibernate exception; traverse the cause chain if implementing a thorough classifier.

Do not assume constraint names are always present or identical across all databases. You can use SQLState/vendor codes and exception types as additional signals, but test the classifier on your actual target database.

Do not parse error message text substrings like "Duplicate entry" for portable business logic. Error messages can change by database, version, locale, and driver.

## 10. Transaction Rollback on Integrity Errors

**DataIntegrityViolationException** is an unchecked exception. By default, Spring transactions roll back when a RuntimeException or Error escapes a transactional method.

Example:

~~~java
@Transactional
public Customer register(Customer customer) {
    return repository.saveAndFlush(customer);
}
~~~

If the INSERT violates UNIQUE and the exception escapes the method, the transaction rolls back.

Keep in mind:

- If the exception occurs during flush, Hibernate may mark the transaction or Session unusable for subsequent operations.
- If you catch the exception inside the same transaction and keep querying/writing, the database may have already marked the transaction rollback-only or placed it in an error state.
- When a transaction is already rollback-only, the caller may receive **UnexpectedRollbackException** at commit even though the original exception was caught.
- Do not catch and ignore DataIntegrityViolationException to keep reusing the same persistence context.

If you need to translate the exception, normally let it escape the transactional service and handle it outside the transaction, such as in ControllerAdvice. If you must catch inside a service, design a separate transaction boundary and do not continue using the failed persistence context.

## 11. Handling Errors in REST APIs with ProblemDetail

Spring Framework 6 supports **ProblemDetail** to return structured HTTP API errors clearly.

General handler example:

~~~java
@RestControllerAdvice
public class ApiExceptionHandler {

    @ExceptionHandler(DataIntegrityViolationException.class)
    public ResponseEntity<ProblemDetail> handleIntegrityViolation(
            DataIntegrityViolationException exception) {

        ProblemDetail problem = ProblemDetail.forStatusAndDetail(
            HttpStatus.CONFLICT,
            "Data could not be saved due to a constraint violation."
        );

        problem.setTitle("Data conflict");

        return ResponseEntity
            .status(HttpStatus.CONFLICT)
            .body(problem);
    }
}
~~~

Illustrative response:

~~~json
{
  "type": "about:blank",
  "title": "Data conflict",
  "status": 409,
  "detail": "Data could not be saved due to a constraint violation."
}
~~~

This is a simple fallback handler. In real applications, not every DataIntegrityViolationException should necessarily return 409:

- UNIQUE conflicts typically fit 409 Conflict.
- Invalid input data may be caught early and return 400 or 422 per the API contract.
- References to non-existent resources may call for 404/409/422 depending on endpoint semantics.
- Constraint errors caused by bugs or unexpected internal data may need to be logged as server errors.

Classify known cases using a provider/database-aware classifier, then return stable business error codes. Never return SQL, internal table/column names, constraint details, raw data values, or stack traces to clients.

## 12. Do Not Confuse with Request Validation Errors

You can use **@Valid** to validate request DTOs before calling the service:

~~~java
public record CreateCustomerRequest(
    @NotBlank @Email String email,
    @NotBlank @Size(max = 120) String displayName
) {
}
~~~

Controller:

~~~java
@PostMapping("/customers")
public CustomerResponse create(
        @Valid @RequestBody CreateCustomerRequest request) {

    return customerService.create(request);
}
~~~

If email is blank or malformed, Bean Validation can reject the request before the repository executes. That is an input validation error, not a database UNIQUE violation.

However, request validation cannot replace database constraints:

- `@Email` does not check whether someone else already registered that email.
- `existsByEmail` checks have race conditions.
- Another process can still write directly to the database.
- Relational and consistency rules must be enforced in storage.

Use both validation and constraints to provide fast feedback while protecting final data integrity.

## 13. Foreign Key Violations

Foreign keys ensure child rows reference existing parent rows.

Example Order with customer_id:

~~~sql
ALTER TABLE orders
ADD CONSTRAINT fk_orders_customer
FOREIGN KEY (customer_id) REFERENCES customers(id);
~~~

If the application saves an Order with a non-existent customer_id, the database rejects the INSERT/UPDATE.

In JPA, represent the relationship using an association:

~~~java
@ManyToOne(fetch = FetchType.LAZY, optional = false)
@JoinColumn(
    name = "customer_id",
    nullable = false,
    foreignKey = @ForeignKey(name = "fk_orders_customer")
)
private Customer customer;
~~~

Example service loading customer first:

~~~java
@Transactional
public Order createOrder(Long customerId) {
    Customer customer = customerRepository.findById(customerId)
        .orElseThrow(CustomerNotFoundException::new);

    Order order = new Order(customer);
    return orderRepository.save(order);
}
~~~

Loading the customer lets you return a clear business error when the ID does not exist. The foreign key is still needed in the database to guard against concurrent requests and all other write paths.

Also distinguish two scenarios:

- The customer does not exist when the application checks.
- The customer is deleted between the check and writing the Order.

The foreign key handles the second race condition. How deleting a referenced customer behaves must be designed explicitly: RESTRICT/NO ACTION, CASCADE, or a dedicated business workflow.

## 14. CHECK and NOT NULL Violations

A CHECK constraint ensures an expression holds true for every row:

~~~sql
ALTER TABLE order_items
ADD CONSTRAINT ck_order_items_quantity_positive
CHECK (quantity > 0);
~~~

If quantity is 0 or negative, the database rejects the operation.

NOT NULL:

~~~sql
ALTER TABLE customers
ALTER COLUMN email SET NOT NULL;
~~~

ALTER COLUMN syntax varies across databases; the example fits certain engines and must be adapted for the target engine.

You can validate early with Bean Validation:

~~~java
@NotNull
@Positive
private Integer quantity;
~~~

However, CHECK/NOT NULL in the database remain necessary because application validation does not execute for all write sources. For CHECK constraints with complex expressions or multi-column dependencies, database constraints enforce rules at the data layer.

## 15. Bulk Updates and Native SQL

JPQL bulk updates/deletes and native SQL operate directly on the database, bypassing ordinary entity lifecycle handling. They do not automatically run Bean Validation per entity and do not trigger entity listeners like updating a managed entity does.

Example:

~~~java
@Modifying
@Transactional
@Query("""
    update Customer c
    set c.email = :email
    where c.id = :id
    """)
int updateEmail(
    @Param("id") Long id,
    @Param("email") String email
);
~~~

If email violates UNIQUE, the database still rejects the UPDATE and Spring can translate the error into DataIntegrityViolationException. Database constraints remain active even though the Bean Validation lifecycle does not run for individual entities.

After a bulk update, the persistence context may retain stale entities. Consider flushing beforehand and clearing afterward or using appropriate `@Modifying` options. Do not keep using stale managed entities as if the database had not changed.

If a bulk operation can violate multiple constraint types, test it against the real database and design appropriate error classification.

## 16. Migrations and Existing Data

When adding UNIQUE, NOT NULL, or FK constraints to a table that already contains data, the migration can fail if legacy rows already violate the new rule.

For example, before adding UNIQUE on email, find duplicates:

~~~sql
SELECT email, COUNT(*)
FROM customers
GROUP BY email
HAVING COUNT(*) > 1;
~~~

Before adding NOT NULL:

~~~sql
SELECT COUNT(*)
FROM customers
WHERE email IS NULL;
~~~

Before adding a foreign key, locate orphaned rows using LEFT JOIN or NOT EXISTS.

A safe rollout workflow typically includes:

1. Inspect and clean up existing data.
2. Decide how to handle duplicate/null/orphan records per business rules.
3. Deploy code compatible with existing data if multi-step rollout is needed.
4. Add constraints via migration.
5. Verify migrations on production-like data.
6. Monitor integrity errors after deployment.

Do not rely on **spring.jpa.hibernate.ddl-auto=update** as a production schema management tool. Use Flyway or Liquibase so migrations are versioned, reviewable, and reproducible.

## 17. Testing DataIntegrityViolationException

Integration tests should flush so constraints are verified directly during the test:

~~~java
@DataJpaTest
class CustomerConstraintTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void rejectsDuplicateEmail() {
        repository.saveAndFlush(
            new Customer("an@example.test", "An")
        );

        assertThatThrownBy(() ->
            repository.saveAndFlush(
                new Customer("an@example.test", "Another An")
            )
        ).isInstanceOf(DataIntegrityViolationException.class);
    }
}
~~~

The test assumes the test schema has a UNIQUE constraint on email and Spring exception translation is active. Depending on database/provider, the exact exception type and cause chain may vary; asserting at the Spring layer is generally more stable than asserting directly on database messages.

Additional scenarios worth testing:

- NOT NULL and CHECK constraints.
- Foreign key to a non-existent customer.
- Deleting a customer referenced by orders.
- Bean Validation before SQL executes.
- Bulk update violating UNIQUE.
- Transaction rollback after failure.
- Constraints checked at commit if the database uses deferred constraints.

### Testing Transaction Rollback

When testing rollback, use an explicit transaction boundary. A default test method may run inside `@DataJpaTest`'s transaction and roll back on completion; that alone does not prove a service transaction rolled back properly when an exception escaped through the proxy.

For service transaction tests, call the service from a test method without `@Transactional`, assert the exception, and query again in a fresh transaction to verify data was not committed.

Do not try to continue operating on the same persistence context after a flush failure. Use a fresh transaction/test context for follow-up assertions.

## 18. Common Mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| save() does not throw immediately | SQL is deferred until flush/commit | Use saveAndFlush or flush when early detection is needed |
| Catch exception yet commit still fails | Transaction was marked rollback-only | Let errors escape the transaction and handle outside |
| Exists check before insert still yields duplicates | Race condition between check and insert | Keep UNIQUE constraint in the database |
| Confusing the two ConstraintViolationExceptions | Different packages and layers | Distinguish Hibernate's exception from Jakarta Validation's exception |
| `@Column(nullable=false)` does not protect production | Actual schema lacks NOT NULL | Add constraint in migration |
| `@Valid` does not prevent duplicate emails | Format validation does not check concurrent uniqueness | Use UNIQUE constraint and handle conflicts |
| Cannot retrieve constraint name | Driver/provider does not supply it | Use cause chain, SQLState/vendor code; do not rely on name always being present |
| FK fails despite checking ID | Parent row deleted concurrently or wrong mapping | Keep FK and handle errors at transaction boundary |
| Bulk update skips Bean Validation | Bulk DML bypasses entity lifecycle | Validate inputs separately and keep database constraints |
| Migration adding constraint fails | Legacy data already violates it | Audit and clean data before migration |
| API leaks SQL details | Exposing exception message/cause directly | Return stable ProblemDetail, log details internally |

## 19. Data Integrity Troubleshooting Checklist

- [ ] Identify the constraint to enforce: PK, UNIQUE, NOT NULL, FK, or CHECK.
- [ ] Create real constraints in the database via migrations.
- [ ] Use Bean Validation for early feedback on invalid input.
- [ ] Distinguish Spring's DataIntegrityViolationException from Hibernate's and Jakarta Validation's ConstraintViolationException.
- [ ] Understand that save() can defer SQL until flush/commit.
- [ ] Use saveAndFlush/flush when early error detection is needed, without confusing flush with commit.
- [ ] Use UNIQUE constraints to handle race conditions rather than relying solely on exists queries.
- [ ] Give constraints explicit names in migrations.
- [ ] Do not keep using a persistence context after a flush failure.
- [ ] Translate exceptions into stable API errors outside the transaction boundary.
- [ ] Never return SQL, stack traces, or sensitive data to clients.
- [ ] Test constraints against the same database/driver used in deployment.
- [ ] Clean existing data before adding new constraints.
- [ ] Check bulk updates/deletes since they bypass entity lifecycle validation.

## 20. Conclusion

**DataIntegrityViolationException** is a Spring-layer exception indicating a data operation violated integrity. The cause may be UNIQUE, NOT NULL, FK, CHECK, or another constraint; provider details usually sit in the cause chain. Distinguish it from **org.hibernate.exception.ConstraintViolationException** (Hibernate's SQL constraint error) and **jakarta.validation.ConstraintViolationException** (Bean Validation error).

JPA can defer SQL until flush or commit, so errors do not necessarily occur right at save(). Database constraints are what protect data against concurrent writes and multiple writers; Bean Validation provides early feedback. When an error occurs, let the transaction roll back properly, handle it at an appropriate boundary, return a stable API error response, and keep technical details in internal logs.
