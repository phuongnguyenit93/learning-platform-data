# Distinguishing Mapping Constraints, Bean Validation, and Database Constraints

When building a JPA entity, you often encounter annotations such as **@Column(nullable = false)**, **@NotNull**, **@Size**, and database constraints like **NOT NULL**, **UNIQUE**, and **CHECK**. They may describe seemingly similar conditions, but they operate at different layers and are checked at different times.

To design data safely, distinguish three layers:

1. **JPA mapping constraints** describe how Java properties map to columns or relationships in the database.
2. **Bean Validation** checks whether data satisfies validity rules at the application layer.
3. **Database constraints** protect data integrity directly at the storage layer.

All three layers can express the same rule, such as a book title must not be null. However, each layer has a distinct purpose. Mapping annotations do not replace validation; application-layer validation cannot replace database constraints, especially when concurrent write requests occur or data is written by another system.

**Example prerequisites:** the code snippets below use Spring Boot 3.x, Java 17 or higher, Jakarta Persistence, and Jakarta Bean Validation. The application needs **spring-boot-starter-data-jpa**, **spring-boot-starter-validation**, a JDBC driver, a DataSource, and the corresponding schema. These are files within a Spring Boot application, not standalone programs that can compile with **javac** alone.

## 1. Quick overview of the three constraint layers

| Layer | Typical tools | Question answered | Where enforced |
|---|---|---|---|
| JPA mapping | **@Column**, **@Table**, **@JoinColumn**, **@Id** | Which column, type, and relationship does this property map to? | JPA provider uses metadata when building mappings and interacting with the database |
| Bean Validation | **@NotNull**, **@NotBlank**, **@Size**, **@Digits**, custom constraints | Is the data received or about to be saved by the application valid? | Validator, Spring MVC, method validation, or JPA lifecycle integration |
| Database constraint | **PRIMARY KEY**, **NOT NULL**, **UNIQUE**, **FOREIGN KEY**, **CHECK** | Is the database permitted to store this data state? | Database when executing INSERT/UPDATE/DELETE |

Example of a title attribute:

~~~java
@NotBlank
@Size(max = 150)
@Column(nullable = false, length = 150)
private String title;
~~~

The three annotations are not three ways of writing the same action:

- **@NotBlank** checks that the string has a value and contains at least one non-whitespace character when Bean Validation is invoked.
- **@Size(max = 150)** checks the string length at the application layer.
- **@Column(nullable = false, length = 150)** describes column mapping and metadata for the JPA provider, especially when the provider generates the schema.

The database still needs matching constraints to protect data at the storage layer.

## 2. JPA mapping constraints describe storage structure

JPA mapping describes the relationship between Java classes and relational structures. Common mapping annotations:

| Annotation | Mapping meaning |
|---|---|
| **@Id** | Entity identifier property |
| **@GeneratedValue** | Primary key generation strategy |
| **@Column** | Column name, nullability, length, precision, scale, and other metadata |
| **@Table** | Table name, schema, and certain table-level constraints |
| **@JoinColumn** | Column used to map a relationship |
| **@ManyToOne**, **@OneToMany**, **@OneToOne**, **@ManyToMany** | How relationships between entities are mapped |
| **@Enumerated** | How an enum is stored |
| **@Embedded**, **@Embeddable** | Maps a group of values into the same entity/table |

Example:

~~~java
@Entity
@Table(
    name = "books",
    uniqueConstraints = {
        @UniqueConstraint(
            name = "uk_books_isbn",
            columnNames = "isbn"
        )
    }
)
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(
        name = "title",
        nullable = false,
        length = 150
    )
    private String title;

    @Column(
        name = "isbn",
        nullable = false,
        length = 20
    )
    private String isbn;

    @Column(
        name = "price",
        nullable = false,
        precision = 12,
        scale = 2
    )
    private BigDecimal price;

    protected Book() {
    }
}
~~~

Attributes of **@Column** have mapping semantics:

- **name**: column name in the database.
- **nullable**: metadata indicating whether the column allows null.
- **length**: string column length when the provider creates the schema.
- **precision** and **scale**: precision and digits after the decimal point for appropriate numeric types.
- **unique**: metadata about column uniqueness during schema generation; for named or multi-column constraints, use **@Table(uniqueConstraints = ...)**.

### Does mapping automatically validate an object upon assignment?

No. For example:

~~~java
Book book = new Book();
book.setTitle(null);
~~~

If the entity allows calling a setter like this, **@Column(nullable = false)** is not an automatic validator call at assignment time. The annotation describes mapping for the JPA provider. The provider may perform internal nullability checks on flush depending on configuration, but that does not turn **@Column** into a general-purpose input validation system.

Similarly:

- **length = 150** does not automatically truncate strings longer than 150 characters.
- **precision = 12, scale = 2** does not automatically round prices to two decimal places according to business rules.
- **unique = true** does not automatically query whether a value already exists before saving.
- **@JoinColumn(nullable = false)** does not automatically guarantee an association object is non-null upon object creation.

When the provider generates DDL from mappings, these attributes can be translated into corresponding column types or constraints. If the schema is managed by Flyway/Liquibase or another migration tool, migrations must create compatible structures. Changing an annotation in source code alone does not update a deployed production database.

## 3. Bean Validation checks application data validity

Bean Validation is Jakarta's validation standard. In Spring Boot 3, common annotations live in the **jakarta.validation.constraints** package.

Common constraints:

| Annotation | Rule |
|---|---|
| **@NotNull** | Value must not be null |
| **@NotBlank** | String must not be null, empty, or whitespace-only |
| **@NotEmpty** | String/collection/map/array must not be null or empty |
| **@Size(min, max)** | Limits size of a string, collection, map, or array |
| **@Min**, **@Max** | Bounds integer values against a threshold |
| **@DecimalMin**, **@DecimalMax** | Bounds numeric values against a decimal threshold |
| **@Digits** | Limits the number of integer and fractional digits |
| **@Positive**, **@PositiveOrZero** | Value must be positive or non-negative |
| **@Email** | Validates string against an email format supported by the provider |
| **@Pattern** | Validates string against a regular expression |

Important distinctions to remember:

- **@NotNull** only forbids null. It still allows empty strings or strings with only spaces.
- **@NotEmpty** forbids null and empty values, but a string of three spaces is still not empty.
- **@NotBlank** is appropriate when a string must contain at least one non-whitespace character.
- **@Size** bounds length/size; it does not replace **@NotNull** if the value is also required.
- **@Digits(integer = 10, fraction = 2)** checks digit counts; it does not automatically format or round numbers.

To use Bean Validation in Spring Boot, add the dependency:

~~~kotlin
dependencies {
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-validation")
}
~~~

With Gradle Groovy:

~~~groovy
dependencies {
    implementation 'org.springframework.boot:spring-boot-starter-data-jpa'
    implementation 'org.springframework.boot:spring-boot-starter-validation'
}
~~~

The validation starter brings a matching Bean Validation provider onto the classpath. Importing annotations alone without a corresponding provider may prevent actual validation from running as expected.

## 4. Combining mapping and Bean Validation in an entity

An entity can use both annotation layers. Example:

~~~java
package com.example.catalog.domain;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import jakarta.persistence.UniqueConstraint;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

@Entity
@Table(
    name = "books",
    uniqueConstraints = @UniqueConstraint(
        name = "uk_books_isbn",
        columnNames = "isbn"
    )
)
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotBlank
    @Size(max = 150)
    @Column(nullable = false, length = 150)
    private String title;

    @NotBlank
    @Size(max = 20)
    @Column(nullable = false, length = 20)
    private String isbn;

    @NotNull
    @DecimalMin("0.00")
    @Digits(integer = 10, fraction = 2)
    @Column(nullable = false, precision = 12, scale = 2)
    private BigDecimal price;

    protected Book() {
    }

    public Book(String title, String isbn, BigDecimal price) {
        this.title = title;
        this.isbn = isbn;
        this.price = price;
    }

    public Long getId() {
        return id;
    }

    public String getTitle() {
        return title;
    }

    public String getIsbn() {
        return isbn;
    }

    public BigDecimal getPrice() {
        return price;
    }
}
~~~

Here:

- **@NotBlank** and **@Size** validate title/isbn content.
- **@NotNull**, **@DecimalMin**, and **@Digits** validate the price.
- **@Column** describes the column mapped by the JPA provider.
- **@UniqueConstraint** describes the table-level unique constraint for ISBN when the provider generates DDL.

The example intentionally aligns **@Size(max = 150)** with **length = 150** and **@Digits(integer = 10, fraction = 2)** with **precision = 12, scale = 2**. These pairs must stay consistent so the application does not accept data that the schema cannot store.

However, the two annotation layers still have distinct semantics. You can have mappings without Bean Validation, or Bean Validation without a matching DDL change. Do not rely on the provider inferring some schema attributes from validation annotations as a reason to skip migrations.

## 5. When does Bean Validation run?

Declaring constraints does not mean every created object will automatically be validated immediately. Validation only runs when a mechanism invokes a validator or framework integration triggers it.

There are three common places.

### 5.1. Validating requests in Spring MVC

When receiving HTTP requests, place constraints on DTOs and use **@Valid** on controller parameters:

~~~java
package com.example.catalog.api;

import jakarta.validation.Valid;
import jakarta.validation.constraints.DecimalMin;
import jakarta.validation.constraints.Digits;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

import java.math.BigDecimal;

public record CreateBookRequest(
    @NotBlank
    @Size(max = 150)
    String title,

    @NotBlank
    @Size(max = 20)
    String isbn,

    @NotNull
    @DecimalMin("0.00")
    @Digits(integer = 10, fraction = 2)
    BigDecimal price
) {
}
~~~

Controller:

~~~java
package com.example.catalog.api;

import com.example.catalog.service.BookService;
import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.ResponseStatus;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/books")
public class BookController {

    private final BookService bookService;

    public BookController(BookService bookService) {
        this.bookService = bookService;
    }

    @PostMapping
    @ResponseStatus(HttpStatus.CREATED)
    public Long create(@Valid @RequestBody CreateBookRequest request) {
        return bookService.create(
            request.title(),
            request.isbn(),
            request.price()
        );
    }
}
~~~

If the request violates constraints, Spring MVC performs validation before invoking the controller method body. For an invalid request body, Spring typically returns HTTP 400 under its default error handling or the application's custom handler.

DTOs let you define API input rules without forcing all of them to be entity persistence rules. For example, a request might require a password confirmation field, while the account entity does not need to store that confirmation field.

### 5.2. Validating in services with method validation

Constraints can be placed on parameters or return values of service methods:

~~~java
@Service
@Validated
public class BookService {

    public void changePrice(
            @NotBlank String isbn,
            @NotNull @DecimalMin("0.00") BigDecimal price) {
        // Execute business logic.
    }
}
~~~

**@Validated** on a bean enables Spring method validation to enforce constraints at method call boundaries when configuration/providers are in place. This is a different mechanism from JPA entity lifecycle validation. Check validation dependencies and ensure the bean is called through its Spring proxy.

Do not assume that calling a method directly via **new BookService(...)** will automatically trigger Spring method validation.

### 5.3. Validation when JPA persists/updates an entity

Jakarta Persistence integrates with Jakarta Bean Validation. When a Bean Validation provider is present and validation integration is enabled by persistence configuration, the JPA provider can trigger validation at lifecycle events such as pre-persist and pre-update.

Default groups are typically:

- Pre-persist: **Default** group.
- Pre-update: **Default** group.
- Pre-remove: by default no validation group runs.

Validation groups for lifecycle events can be configured via persistence properties, such as **jakarta.persistence.validation.group.pre-persist** and **jakarta.persistence.validation.group.pre-update**. In Spring Boot, JPA provider properties can be passed through **spring.jpa.properties**. Check the exact provider and actual configuration of your application.

Key point: Bean Validation does not run merely because you write:

~~~java
Book book = new Book(null, "9780000000000", BigDecimal.TEN);
~~~

A Java object has been created. If no validator has been invoked, the constructor does not automatically evaluate constraint annotations. Only when the application calls **Validator.validate(book)**, uses Spring MVC **@Valid**, method validation, or JPA lifecycle integration are the constraints evaluated.

## 6. Database constraints protect data at the storage layer

Database constraints are rules enforced by the database itself. They protect data regardless of whether writes come from:

- Spring Data JPA.
- JDBC or native SQL.
- Another service.
- A batch job or admin tool.
- Another application sharing the same database.

Important constraints:

| Constraint | Role | Example |
|---|---|---|
| **PRIMARY KEY** | Uniquely identifies a row, non-null | **id BIGINT PRIMARY KEY** |
| **NOT NULL** | Forbids null values | **title VARCHAR(150) NOT NULL** |
| **UNIQUE** | Forbids duplicate values or combinations | **UNIQUE (isbn)** |
| **FOREIGN KEY** | Ensures reference points to an existing row | **FOREIGN KEY (category_id) REFERENCES categories(id)** |
| **CHECK** | Evaluates an expression on each row | **CHECK (price >= 0)** |

PostgreSQL DDL example:

~~~sql
CREATE TABLE books (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    title VARCHAR(150) NOT NULL,
    isbn VARCHAR(20) NOT NULL,
    price NUMERIC(12, 2) NOT NULL,
    CONSTRAINT uk_books_isbn UNIQUE (isbn),
    CONSTRAINT ck_books_title_not_blank
        CHECK (length(trim(title)) > 0),
    CONSTRAINT ck_books_price_non_negative
        CHECK (price >= 0)
);
~~~

This DDL protects key rules even when a program bypasses Bean Validation. For example, a direct SQL statement attempting to insert a negative price will be rejected by the database due to the CHECK constraint.

Several details depend on the database management system:

- String comparisons in UNIQUE may be case-sensitive or case-insensitive depending on collation and data type.
- String length calculation may differ with Unicode and column types.
- CHECK behavior when expressions receive NULL follows SQL three-valued logic; if a column is required, combine it with NOT NULL.
- DDL support and syntax can vary across PostgreSQL, MySQL, SQL Server, Oracle, and other systems.

Therefore, write migrations targeting the exact database you deploy to and test constraints on that database.

## 7. Comparing one rule across all three layers

Take the rule "book price must not be null and must not be negative":

| Layer | How declared | What is protected |
|---|---|---|
| JPA mapping | **@Column(nullable = false, precision = 12, scale = 2)** | Mapping metadata and column structure during schema generation |
| Bean Validation | **@NotNull**, **@DecimalMin("0.00")**, **@Digits(...)** | Validated objects do not contain violating values |
| Database | **NOT NULL**, **CHECK (price >= 0)**, **NUMERIC(12,2)** | Prevents storing rows that violate constraints |

The three layers complement one another:

1. Mapping helps JPA understand the data structure.
2. Bean Validation catches invalid data early and returns user-friendly errors.
3. Database constraints are the final line of defense protecting data integrity.

With mapping alone, request data can still be invalid for business rules. With Bean Validation alone, a direct SQL statement can still bypass the validator. With database constraints alone, errors may only surface at write time and be difficult to turn into appropriate user messages.

## 8. Why does existsBy... not replace a UNIQUE constraint?

Suppose a service checks ISBN before saving:

~~~java
if (bookRepository.existsByIsbn(isbn)) {
    throw new IllegalStateException("ISBN already exists");
}

bookRepository.save(book);
~~~

This check improves user experience when the ISBN already exists at check time. However, it does not guarantee uniqueness under concurrent load:

1. Request A calls **existsByIsbn** and receives **false**.
2. Request B calls the same query and also receives **false**.
3. Both insert the same ISBN.
4. Without a UNIQUE constraint in the database, both rows can be saved.

This is a race condition between the check and the write. Checking in Java alone does not lock all write paths to the database.

Solution:

- Keep the service check if early feedback is desired.
- Create a UNIQUE constraint on the column or column combination in the database.
- Catch and translate constraint violation errors into appropriate business/API errors.
- If more complex concurrent updates must be handled, consider optimistic locking with **@Version** or an appropriate locking strategy.

Bean Validation also does not replace a UNIQUE constraint. **@Unique** is not a built-in standard constraint in Jakarta Bean Validation for database-wide uniqueness; checking uniqueness generally requires querying and still has a race condition. You can build a custom validator for early checks, but the database must still maintain the UNIQUE constraint.

## 9. Constraints on entity relationships

For JPA relationships, distinguish relationship mapping, Bean Validation, and foreign keys.

Example where a book must belong to a category:

~~~java
@Entity
@Table(name = "books")
public class Book {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "category_id", nullable = false)
    @NotNull
    private Category category;

    protected Book() {
    }
}
~~~

Meaning:

- **@ManyToOne** describes a many-books-to-one-category relationship.
- **optional = false** describes a required relationship at the JPA mapping level.
- **@JoinColumn(nullable = false)** describes a non-nullable foreign key column in the mapping.
- **@NotNull** checks the association when Bean Validation is triggered.
- The database needs a **category_id NOT NULL** column and a FOREIGN KEY referencing **categories(id)** to protect actual integrity.

A non-null association can still reference a non-existent or improperly persisted entity. Only a database foreign key constraint guarantees that the foreign key value references a valid row.

## 10. Custom constraints for complex business rules

Built-in constraints handle single-property rules well. For rules spanning multiple fields, you can create a class-level constraint.

Example where end date must be after start date:

~~~java
@Target(ElementType.TYPE)
@Retention(RetentionPolicy.RUNTIME)
@Constraint(validatedBy = ValidDateRangeValidator.class)
public @interface ValidDateRange {

    String message() default "endDate must be after startDate";

    Class<?>[] groups() default {};

    Class<? extends Payload>[] payload() default {};
}
~~~

Validator:

~~~java
public class ValidDateRangeValidator
        implements ConstraintValidator<ValidDateRange, BookingRequest> {

    @Override
    public boolean isValid(
            BookingRequest value,
            ConstraintValidatorContext context) {

        if (value == null
                || value.getStartDate() == null
                || value.getEndDate() == null) {
            return true;
        }

        return value.getEndDate().isAfter(value.getStartDate());
    }
}
~~~

DTO:

~~~java
@ValidDateRange
public class BookingRequest {

    @NotNull
    private LocalDate startDate;

    @NotNull
    private LocalDate endDate;

    public LocalDate getStartDate() {
        return startDate;
    }

    public LocalDate getEndDate() {
        return endDate;
    }
}
~~~

The validator returns **true** when compared fields are missing because null-checking responsibility is delegated to **@NotNull**. This avoids confusing duplicate validation errors. If requirements demand a different message when a field is null, design the validator to fit that requirement.

Custom Bean Validation constraints validate application data. If a rule must also be protected across all write paths, evaluate whether it can be expressed with database CHECK/FK/UNIQUE constraints or requires a different data design.

## 11. Validation groups and differences between create and update

Some rules apply on creation but not on update, or vice versa. Bean Validation supports validation groups.

Example declaring marker interfaces:

~~~java
public interface OnCreate {
}

public interface OnUpdate {
}
~~~

DTO:

~~~java
public class BookRequest {

    @NotBlank(groups = {OnCreate.class, OnUpdate.class})
    @Size(max = 150, groups = {OnCreate.class, OnUpdate.class})
    private String title;

    @NotBlank(groups = OnCreate.class)
    private String isbn;

    @NotNull(groups = {OnCreate.class, OnUpdate.class})
    @DecimalMin(value = "0.00", groups = {OnCreate.class, OnUpdate.class})
    private BigDecimal price;

    // getters/setters
}
~~~

The controller can select the group:

~~~java
@PostMapping
public void create(
        @Validated(OnCreate.class) @RequestBody BookRequest request) {
    // ...
}

@PutMapping("/{id}")
public void update(
        @Validated(OnUpdate.class) @RequestBody BookRequest request) {
    // ...
}
~~~

Note: when specifying only a group like **OnCreate.class**, Bean Validation does not automatically run the **Default** group unless a group sequence or group inheritance is configured to include it. Therefore, if a DTO has constraints without an explicit group, decide clearly how groups combine.

For JPA lifecycle validation, the groups used for pre-persist/pre-update have defaults and can be changed via persistence properties. Do not assume the group selected in a controller automatically becomes the group used when Hibernate validates an entity on persist. Those are two separate validation trigger points.

## 12. DDL generation and migrations

JPA mappings can be used by Hibernate to generate DDL. Bean Validation providers can also integrate with Hibernate ORM, and some constraints may affect DDL metadata, such as **@NotNull** or **@Size**. However, the result depends on provider, version, configuration, and schema generation mode.

Common Hibernate modes configured via Spring Boot:

~~~yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
~~~

Common values:

- **none**: neither generates nor validates the schema.
- **validate**: checks mappings against the existing schema.
- **update**: attempts to adjust the schema to match mappings.
- **create**: recreates the schema at startup according to provider behavior.
- **create-drop**: creates the schema at startup and drops it on context close according to provider behavior.

In production environments, manage schemas with versioned migrations such as Flyway or Liquibase. Migrations explicitly record adding columns, changing types, creating unique constraints, foreign keys, and CHECK constraints. Annotations in code do not automatically update deployed databases.

A safe workflow is typically:

1. Add or adjust Bean Validation to validate data at the application layer.
2. Update JPA mappings to match the desired structure.
3. Write a migration creating or updating constraints in the database.
4. Run the migration in a test environment.
5. Run integration tests to verify both validation and database constraints.
6. Use **ddl-auto: validate** where appropriate to catch mapping-schema mismatches.

## 13. Handling errors by the layer that raised them

A well-designed system separates application validation errors from database constraint errors.

| Error | Typical occurrence | How to respond |
|---|---|---|
| DTO violates **@NotBlank** | When Spring MVC validates request | HTTP 400 with field errors |
| Service method violates constraint | When Spring method validation runs | Translate into input error per API convention |
| Entity violates JPA lifecycle validation | Pre-persist/update depending on validation integration config | Translate into invalid-data error |
| UNIQUE/FOREIGN KEY/CHECK violated | When database executes SQL | Catch persistence/data integrity error and map to an appropriate response |
| Schema incompatible with mapping | During schema validation or startup | Fix migration/schema or mapping before deploying |

Do not return raw SQL, internal table names, or database stack traces to clients. Log them on the server with a suitable correlation id and return meaningful API errors.

For UNIQUE constraints, remember errors may only surface on flush or commit. Calling **save()** does not guarantee SQL executes immediately across all ID strategies and flush configurations. If you need to catch an error at a specific point, you can explicitly call **saveAndFlush()** or **flush()**, while still handling transaction rollback properly.

## 14. Common mistakes

| Mistake | Cause | Resolution |
|---|---|---|
| Empty string still saved | Only using **@NotNull** | Use **@NotBlank** if string must contain non-whitespace content |
| String too long causes database error | Has **@Column(length = ...)** without input validation or schema out of sync | Combine **@Size** with an appropriately sized VARCHAR column |
| Negative price reaches service | Missing Bean Validation or domain invariant | Use **@DecimalMin** and enforce rules in domain/service |
| Two requests create the same ISBN | Only using **existsByIsbn** | Create a UNIQUE constraint in the database and handle duplicate errors |
| Non-null association set but invalid foreign key | Only using **@NotNull** on relationship | Ensure entity is persisted and create a FOREIGN KEY constraint |
| Validation does not run | Missing provider, missing trigger, or validation disabled in config | Check dependencies and validation trigger points |
| DDL unchanged after editing annotations | Schema managed by migrations or ddl-auto does not generate schema | Update the corresponding migration |
| Database rejects value Bean Validation allowed | Application constraint weaker than schema or different semantics | Align rules and test against real database |
| Relying on database errors to report input errors | Missing early validation | Validate requests/DTOs before entering the persistence layer |

## 15. Constraint design checklist

- [ ] Identify whether a rule belongs to mapping, validation, or data integrity.
- [ ] Use **@Column** and mapping annotations to describe storage structure.
- [ ] Use **@NotNull**, **@NotBlank**, **@Size**, **@Digits**, and appropriate constraints to validate application data.
- [ ] Use DTOs and **@Valid** for API input data.
- [ ] Check JPA lifecycle validation if validating entities pre-persist/update.
- [ ] Use NOT NULL, UNIQUE, FOREIGN KEY, and CHECK in the database for invariants that must hold across all write paths.
- [ ] Do not rely on pre-insert existence queries to replace UNIQUE constraints.
- [ ] Keep mappings, Bean Validation, and migrations synchronized.
- [ ] Test both application validation errors and database constraint errors.
- [ ] Translate errors into appropriate API responses without exposing internal SQL details.

## 16. Conclusion

JPA mapping constraints describe how Java data is stored; Bean Validation checks data where the application triggers a validator; database constraints protect integrity directly at storage time. An important rule may appear in all three layers, but each layer must be configured and tested for its specific role.

Use validation to catch invalid data early, mapping to keep the Java model consistent with the schema, and database constraints to protect data against concurrent access or write paths that bypass the application.
