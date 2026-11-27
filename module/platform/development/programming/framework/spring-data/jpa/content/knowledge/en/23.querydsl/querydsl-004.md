# QuerydslPredicateExecutor for Searching, Counting, and Existence Checks

## Objectives

Querydsl lets you express query conditions as type-safe Java expressions instead of concatenating JPQL or SQL strings. Spring Data JPA integrates Querydsl through `QuerydslPredicateExecutor<T>`, enabling repositories to accept a Predicate and perform searches, pagination, counts, or existence checks.

This approach works well when an application has many optional filters and needs to combine them using AND/OR conditions. Q classes automatically generated from entities enable IDE autocomplete and catch property name mistakes at compile time.

After this lesson, you will be able to:

- Understand the role of Querydsl and Q classes generated from entities.
- Configure Querydsl compatible with Jakarta Persistence.
- Have a repository extend `QuerydslPredicateExecutor`.
- Build predicates using Q-types, `BooleanExpression`, and `BooleanBuilder`.
- Use `findAll`, `findOne`, `count`, and `exists`.
- Combine predicates with `Sort` and `Pageable`.
- Restrict which fields can be bound from HTTP requests.
- Recognize executor limitations and when a custom repository with `JPAQueryFactory` is needed.
- Test query results against a real JPA provider.

Examples use Java 17+, Spring Boot 3.x, Jakarta Persistence, and Spring Data JPA. Querydsl configuration examples should be aligned with your project's Spring Data/Querydsl versions.

## 1. Querydsl and Predicate

Querydsl is a library for building queries with a typed Java API. Instead of writing a query string:

```java
String jpql =
        "select c from Customer c where c.active = true";
```

we can express the condition as a Java expression:

```java
QCustomer customer = QCustomer.customer;

Predicate predicate = customer.active.isTrue();
```

`Predicate` describes a logical condition that can be translated into a WHERE clause. Comparisons, string matching, null checks, sets, and date conditions are expressed via appropriately typed methods.

Example:

```java
customer.firstName.eq("An");
customer.email.containsIgnoreCase("@example.com");
customer.age.goe(18);
customer.createdAt.before(Instant.now());
customer.department.name.eq("Engineering");
```

These expressions do not execute queries immediately. They describe conditions; the repository or Querydsl query factory executes them against the database.

### 1.1. Automatically Generated Q-Types

For the `Customer` entity, the Querydsl annotation processor generates the `QCustomer` class. This class has paths corresponding to entity properties:

- `customer.id`: path for the ID.
- `customer.firstName`: StringPath.
- `customer.email`: StringPath.
- `customer.active`: BooleanPath.
- `customer.createdAt`: DateTimePath or corresponding temporal path.
- Associations also have paths matching the related entity types.

Q-types typically reside in the same package as the entity. Do not manually write or edit generated Q classes; they are annotation processing outputs and are regenerated on build.

## 2. Configuring Querydsl for Jakarta Persistence

Spring Boot 3.x uses Jakarta Persistence, so Querydsl dependencies must be Jakarta-compatible. A common Maven configuration with Querydsl 5.1.x:

```xml
<properties>
    <querydsl.version>5.1.0</querydsl.version>
</properties>

<dependencies>
    <dependency>
        <groupId>com.querydsl</groupId>
        <artifactId>querydsl-jpa</artifactId>
        <version>5.1.0</version>
        <classifier>jakarta</classifier>
    </dependency>
</dependencies>

<build>
    <plugins>
        <plugin>
            <groupId>org.apache.maven.plugins</groupId>
            <artifactId>maven-compiler-plugin</artifactId>
            <version>3.13.0</version>
            <configuration>
                <annotationProcessorPaths>
                    <path>
                        <groupId>com.querydsl</groupId>
                        <artifactId>querydsl-apt</artifactId>
                        <version>5.1.0</version>
                        <classifier>jakarta</classifier>
                    </path>
                    <path>
                        <groupId>jakarta.persistence</groupId>
                        <artifactId>jakarta.persistence-api</artifactId>
                        <version>3.1.0</version>
                    </path>
                    <path>
                        <groupId>jakarta.annotation</groupId>
                        <artifactId>jakarta.annotation-api</artifactId>
                        <version>2.1.1</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
```

The versions above are examples for a Jakarta stack; use versions compatible with the Spring Boot/Spring Data managed in your project. If the project uses Spring Boot 2.x with `javax.persistence`, you need the javax-compatible dependency and annotation processor without the Jakarta classifier.

With Gradle, the corresponding configuration usually places the runtime library in `implementation` and the annotation processor in `annotationProcessor`:

```groovy
dependencies {
    implementation "com.querydsl:querydsl-jpa:5.1.0:jakarta"

    annotationProcessor "com.querydsl:querydsl-apt:5.1.0:jakarta"
    annotationProcessor "jakarta.persistence:jakarta.persistence-api:3.1.0"
    annotationProcessor "jakarta.annotation:jakarta.annotation-api:2.1.1"
}
```

### 2.1. Generating Q-Classes

After configuring the annotation processor, run the build:

```bash
./mvnw clean compile
```

On Windows:

```powershell
.mvnw.cmd clean compile
```

Q-classes are created in the build's generated sources directory, usually:

```text
target/generated-sources/annotations/
```

For example, an entity in package `com.example.demo.customer` generates `QCustomer` in the corresponding package. The IDE may need to reload Maven/Gradle or mark generated sources to recognize the newly generated classes.

If Q-classes are not generated, check the annotation processor, Jakarta/Javax classifier, `jakarta.persistence.Entity` import, compiler configuration, and clean compile output. Do not create a manual Q class to hide a configuration error.

## 3. Sample Entity and Repository

Customer entity:

```java
package com.example.demo.customer;

import jakarta.persistence.*;
import java.time.Instant;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 100)
    private String firstName;

    @Column(nullable = false, length = 100)
    private String lastName;

    @Column(nullable = false, unique = true, length = 320)
    private String email;

    @Column(nullable = false)
    private boolean active;

    @Column(nullable = false)
    private Instant createdAt;

    protected Customer() {
    }

    public Customer(
            String firstName,
            String lastName,
            String email,
            boolean active,
            Instant createdAt
    ) {
        this.firstName = firstName;
        this.lastName = lastName;
        this.email = email;
        this.active = active;
        this.createdAt = createdAt;
    }

    public Long getId() {
        return id;
    }

    public String getFirstName() {
        return firstName;
    }

    public String getLastName() {
        return lastName;
    }

    public String getEmail() {
        return email;
    }

    public boolean isActive() {
        return active;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

After building, Querydsl creates a conceptually equivalent class:

```java
// Generated source - do not write or edit manually.
public class QCustomer extends EntityPathBase<Customer> {
    public static final QCustomer customer =
            new QCustomer("customer");

    public final StringPath firstName = createString("firstName");
    public final StringPath lastName = createString("lastName");
    public final StringPath email = createString("email");
    public final BooleanPath active = createBoolean("active");
}
```

The Q-class snippet above only illustrates structure, not a file to add to source code. The annotation processor generates the full class based on the entity's actual mapping.

Repository:

```java
package com.example.demo.customer;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
```

Simply by extending `QuerydslPredicateExecutor<Customer>`, the repository can accept Querydsl Predicates without writing a separate method for every filter combination.

## 4. Methods of QuerydslPredicateExecutor

Main operations:

| Method | Return type | Purpose |
|---|---|---|
| `findAll(predicate)` | `Iterable<T>` | Retrieve all entities matching the predicate |
| `findAll(predicate, sort)` | `Iterable<T>` | Retrieve ordered results |
| `findAll(predicate, pageable)` | `Page<T>` | Retrieve a page and pagination metadata |
| `findOne(predicate)` | `Optional<T>` | Retrieve a single result if the predicate matches |
| `count(predicate)` | `long` | Count matching entities |
| `exists(predicate)` | `boolean` | Check whether any entity matches |

These methods accept `Predicate` from `com.querydsl.core.types.Predicate`.

Example checking an email:

```java
QCustomer customer = QCustomer.customer;

Predicate predicate = customer.email.eq("an@example.com");

Optional<Customer> result = repository.findOne(predicate);
```

`findOne` does not mean arbitrarily picking the first row. The predicate should identify at most one result. If multiple rows match, Spring Data may throw `IncorrectResultSizeDataAccessException`. For queries returning multiple results, use `findAll` or Page.

## 5. Creating Predicates Directly from Q-Types

Q-types have methods matching the property type.

### 5.1. Exact Comparisons

```java
QCustomer customer = QCustomer.customer;

Predicate predicate = customer.active.isTrue()
        .and(customer.lastName.eq("Nguyen"));
```

Commonly used methods:

- `eq(value)`: equal.
- `ne(value)`: not equal.
- `isNull()` and `isNotNull()`: null checks.
- `isTrue()` and `isFalse()`: boolean.
- `in(collection)`: belongs to a set of values.
- `notIn(collection)`: does not belong to a set of values.

### 5.2. String Searches

```java
Predicate predicate = customer.firstName.containsIgnoreCase("an")
        .and(customer.email.endsWithIgnoreCase("@example.com"));
```

Common String methods:

| Method | Meaning |
|---|---|
| `eq` | Exact match |
| `contains` | Contains substring |
| `containsIgnoreCase` | Contains substring, case-insensitive |
| `startsWith` | Starts with |
| `endsWith` | Ends with |
| `like` | LIKE match |
| `matches` | Regex expression depending on backend/provider support |

Regex behavior or specialized functions are not always portable across databases. Prefer expressions supported by Querydsl JPA and the provider; test against the real database.

### 5.3. Date and Numeric Comparisons

For ordered properties:

```java
Instant from = Instant.parse("2026-01-01T00:00:00Z");
Instant to = Instant.parse("2026-02-01T00:00:00Z");

Predicate predicate = customer.createdAt.goe(from)
        .and(customer.createdAt.lt(to));
```

Common methods include `gt`, `goe`, `lt`, and `loe`. You can use a half-open interval `[from, to)`: inclusive start, exclusive end to avoid boundary overlap between consecutive periods.

## 6. Combining Optional Filters with BooleanBuilder

Search forms often have many optional fields. `BooleanBuilder` lets you append predicates when corresponding inputs are present.

Search DTO:

```java
public record CustomerSearchForm(
        String name,
        String email,
        Boolean active,
        Instant createdFrom,
        Instant createdTo
) {
}
```

Building the predicate:

```java
import com.querydsl.core.BooleanBuilder;

public Predicate buildPredicate(CustomerSearchForm form) {
    QCustomer customer = QCustomer.customer;
    BooleanBuilder builder = new BooleanBuilder();

    if (form.name() != null && !form.name().isBlank()) {
        builder.and(
                customer.firstName.containsIgnoreCase(
                        form.name().trim()
                ).or(
                        customer.lastName.containsIgnoreCase(
                                form.name().trim()
                        )
                )
        );
    }

    if (form.email() != null && !form.email().isBlank()) {
        builder.and(
                customer.email.eq(form.email().trim())
        );
    }

    if (form.active() != null) {
        builder.and(customer.active.eq(form.active()));
    }

    if (form.createdFrom() != null) {
        builder.and(customer.createdAt.goe(form.createdFrom()));
    }

    if (form.createdTo() != null) {
        builder.and(customer.createdAt.lt(form.createdTo()));
    }

    if (!builder.hasValue()) {
        throw new IllegalArgumentException(
                "At least one search criterion is required"
        );
    }

    return builder;
}
```

`BooleanBuilder` is mutable: each call to `and` or `or` updates the builder. Create a new builder for each request or search; do not keep a shared builder in a static field or singleton service because concurrent requests can mix each other's conditions.

If a form allows unfiltered searches, handle an empty builder explicitly—for example, by calling a separately bounded query or returning validation errors per product requirements. Do not accidentally scan the entire table simply because a user submitted an empty form.

### 6.1. AND and OR

`and` narrows the result set; `or` widens the result set. Logical grouping must be placed accurately:

```java
BooleanBuilder builder = new BooleanBuilder();

builder.and(customer.active.isTrue());

BooleanExpression nameMatches =
        customer.firstName.containsIgnoreCase("an")
                .or(customer.lastName.containsIgnoreCase("an"));

builder.and(nameMatches);
```

Equivalent logic:

```sql
WHERE active = true
  AND (
      lower(first_name) LIKE '%an%'
      OR lower(last_name) LIKE '%an%'
  )
```

Extracting the OR group into a separate expression before ANDing it into the builder preserves the intended business parentheses.

## 7. Creating Reusable Predicates

For conditions used in multiple places, you can extract functions returning `BooleanExpression`:

```java
public final class CustomerPredicates {

    private static final QCustomer CUSTOMER = QCustomer.customer;

    private CustomerPredicates() {
    }

    public static BooleanExpression isActive(Boolean active) {
        return active == null
                ? null
                : CUSTOMER.active.eq(active);
    }

    public static BooleanExpression nameContains(String name) {
        if (name == null || name.isBlank()) {
            return null;
        }

        return CUSTOMER.firstName.containsIgnoreCase(name.trim())
                .or(CUSTOMER.lastName.containsIgnoreCase(name.trim()));
    }

    public static BooleanExpression emailEquals(String email) {
        if (email == null || email.isBlank()) {
            return null;
        }

        return CUSTOMER.email.eq(email.trim());
    }
}
```

Combining nullable expressions:

```java
BooleanBuilder builder = new BooleanBuilder();

BooleanExpression active = CustomerPredicates.isActive(form.active());
BooleanExpression name = CustomerPredicates.nameContains(form.name());
BooleanExpression email = CustomerPredicates.emailEquals(form.email());

if (active != null) {
    builder.and(active);
}
if (name != null) {
    builder.and(name);
}
if (email != null) {
    builder.and(email);
}
```

Do not call `builder.and(null)` carelessly. Check for null before adding an expression to make it clear which filters are applied.

A predicate factory should be stateless and only describe conditions. Form validation, access control, tenant scoping, and result limits should be enforced in the service layer.

## 8. Searching, Counting, and Checking Existence

Once you have a Predicate, you can reuse the same condition across multiple operations.

```java
Predicate predicate = buildPredicate(form);

Iterable<Customer> customers = repository.findAll(predicate);

long total = repository.count(predicate);

boolean hasMatch = repository.exists(predicate);
```

Operations serve different use cases:

- Result list: `findAll(predicate)` or overload with Pageable.
- Display result count: `count(predicate)`.
- Check whether an email or code already exists: `exists(predicate)`.
- Fetch a single entity by unique condition: `findOne(predicate)`.

Example checking email:

```java
public boolean emailExists(String email) {
    if (email == null || email.isBlank()) {
        throw new IllegalArgumentException("Email is required");
    }

    QCustomer customer = QCustomer.customer;
    return repository.exists(customer.email.equalsIgnoreCase(email.trim()));
}
```

If email needs to match system rules accurately, use the same semantics as the database unique constraint and collation. An exists query helps pre-check, but it does not replace a unique constraint because two concurrent transactions can both check "does not exist" and then both INSERT.

## 9. Combining Predicate with Sort and Pageable

The repository supports passing Sort:

```java
Iterable<Customer> result = repository.findAll(
        predicate,
        Sort.by(
                Sort.Order.asc("lastName"),
                Sort.Order.asc("firstName"),
                Sort.Order.asc("id")
        )
);
```

Sort uses Java entity properties. When multiple rows share the same name, add ID as a tie-breaker for more deterministic ordering.

With pagination:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by(
                Sort.Order.asc("lastName"),
                Sort.Order.asc("id")
        )
);

Page<Customer> page = repository.findAll(predicate, pageable);

List<Customer> content = page.getContent();
long totalElements = page.getTotalElements();
int totalPages = page.getTotalPages();
boolean hasNext = page.hasNext();
```

`Page` usually requires a count query to determine the total number of elements. If the UI only needs to know whether a next page exists, consider `Slice` in a suitable custom query or a scrolling mechanism. `QuerydslPredicateExecutor.findAll(predicate, pageable)` returns Page.

Control page size in the service/controller; do not let clients request a huge page. On large datasets, deep OFFSET can be expensive; consider keyset/scrolling or custom queries appropriate for your Spring Data version.

## 10. Using QuerydslPredicateExecutor in a Service

The service can take responsibility for building predicates, validating input, and applying pagination:

```java
@Service
@Transactional(readOnly = true)
public class CustomerSearchService {

    private final CustomerRepository repository;

    public CustomerSearchService(CustomerRepository repository) {
        this.repository = repository;
    }

    public Page<Customer> search(
            CustomerSearchForm form,
            Pageable pageable
    ) {
        if (pageable.getPageSize() > 100) {
            throw new IllegalArgumentException("Page size must not exceed 100");
        }

        if (form.createdFrom() != null
                && form.createdTo() != null
                && !form.createdFrom().isBefore(form.createdTo())) {
            throw new IllegalArgumentException(
                    "createdFrom must be earlier than createdTo"
            );
        }

        Predicate predicate = buildPredicate(form);
        return repository.findAll(predicate, pageable);
    }

    private Predicate buildPredicate(CustomerSearchForm form) {
        QCustomer customer = QCustomer.customer;
        BooleanBuilder builder = new BooleanBuilder();

        if (form.name() != null && !form.name().isBlank()) {
            String name = form.name().trim();
            builder.and(
                    customer.firstName.containsIgnoreCase(name)
                            .or(customer.lastName.containsIgnoreCase(name))
            );
        }

        if (form.email() != null && !form.email().isBlank()) {
            builder.and(customer.email.equalsIgnoreCase(form.email().trim()));
        }

        if (form.active() != null) {
            builder.and(customer.active.eq(form.active()));
        }

        if (form.createdFrom() != null) {
            builder.and(customer.createdAt.goe(form.createdFrom()));
        }

        if (form.createdTo() != null) {
            builder.and(customer.createdAt.lt(form.createdTo()));
        }

        if (!builder.hasValue()) {
            throw new IllegalArgumentException(
                    "At least one search criterion is required"
            );
        }

        return builder;
    }
}
```

This example uses `Boolean` in the form to distinguish "no status selected" from `false`. If a primitive boolean were used, the default value false might unintentionally become a filter.

The service also validates the date range and enforces a page size limit. In real applications, validation can be moved to Bean Validation or a dedicated validator class.

## 11. Binding a Predicate from an HTTP Request

Spring Data Web can construct a Querydsl Predicate from query parameters. Controller example:

```java
@GetMapping("/customers")
public Page<Customer> search(
        @QuerydslPredicate(root = Customer.class) Predicate predicate,
        @PageableDefault(size = 20) Pageable pageable
) {
    return repository.findAll(predicate, pageable);
}
```

`@QuerydslPredicate` asks Spring Data to build a predicate from request parameters using binding rules. Depending on application configuration, you may need to enable Spring Data web support with `@EnableSpringDataWebSupport` or ensure the corresponding auto-configuration is active.

Example request:

```http
GET /customers?firstName=An&active=true&page=0&size=20
```

Default binding can expose more entity properties than intended. Do not allow every property to be filtered just because the Q-type has a corresponding path.

### 11.1. Restricting Allowed Fields with QuerydslBinderCustomizer

The repository can customize binding:

```java
import com.querydsl.core.types.dsl.StringExpression;
import org.springframework.data.querydsl.binding.QuerydslBinderCustomizer;
import org.springframework.data.querydsl.binding.QuerydslBindings;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer>,
                QuerydslBinderCustomizer<QCustomer> {

    @Override
    default void customize(
            QuerydslBindings bindings,
            QCustomer customer
    ) {
        bindings.excludeUnlistedProperties(true);

        bindings.including(
                customer.firstName,
                customer.lastName,
                customer.active
        );

        bindings.bind(customer.firstName)
                .first((path, value) -> path.containsIgnoreCase(value));

        bindings.bind(customer.lastName)
                .first((path, value) -> path.containsIgnoreCase(value));
    }
}
```

This configuration allows binding only the listed properties. The two name fields use containsIgnoreCase; active keeps default boolean binding.

Do not include properties such as tenantId, role, internalStatus, salary, or sensitive data in binding simply because they exist on the entity. If queries must be restricted by tenant/user, add that condition from the server-side security context; never accept tenant scope from the client.

If the repository already extends QuerydslBinderCustomizer, do not redeclare the repository's extends list in two places; combine the interfaces in a single declaration as shown.

### 11.2. Do Not Return Entities Directly When the API Only Needs Partial Data

Real-world controller examples should usually map results to a DTO to control the response:

```java
public record CustomerSummary(
        Long id,
        String firstName,
        String lastName,
        String email
) {
    static CustomerSummary from(Customer customer) {
        return new CustomerSummary(
                customer.getId(),
                customer.getFirstName(),
                customer.getLastName(),
                customer.getEmail()
        );
    }
}
```

```java
@GetMapping("/customers")
public Page<CustomerSummary> search(
        @QuerydslPredicate(root = Customer.class) Predicate predicate,
        @PageableDefault(size = 20) Pageable pageable
) {
    return repository.findAll(predicate, pageable)
            .map(CustomerSummary::from);
}
```

DTOs control exposed data; authorization must still be checked separately.

## 12. Testing QuerydslPredicateExecutor

Use `@DataJpaTest` to verify that predicates are executed by the repository and JPA provider.

```java
package com.example.demo.customer;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import com.querydsl.core.BooleanBuilder;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @BeforeEach
    void setUp() {
        repository.saveAllAndFlush(List.of(
                new Customer(
                        "An", "Nguyen", "an@example.com", true,
                        Instant.parse("2026-01-10T00:00:00Z")
                ),
                new Customer(
                        "Binh", "Tran", "binh@example.com", true,
                        Instant.parse("2026-01-11T00:00:00Z")
                ),
                new Customer(
                        "Chi", "Le", "chi@example.com", false,
                        Instant.parse("2026-01-12T00:00:00Z")
                )
        ));
    }

    @Test
    void findsCustomersByComposedPredicate() {
        QCustomer customer = QCustomer.customer;

        BooleanBuilder predicate = new BooleanBuilder();
        predicate.and(customer.active.isTrue());
        predicate.and(customer.firstName.containsIgnoreCase("an"));

        Iterable<Customer> result = repository.findAll(predicate);

        assertThat(result)
                .extracting(Customer::getEmail)
                .containsExactly("an@example.com");
    }

    @Test
    void countsAndChecksExistence() {
        QCustomer customer = QCustomer.customer;
        var predicate = customer.active.isTrue();

        assertThat(repository.count(predicate)).isEqualTo(2);
        assertThat(repository.exists(
                customer.email.eq("an@example.com")
        )).isTrue();
    }

    @Test
    void findsOneWhenPredicateIsUnique() {
        QCustomer customer = QCustomer.customer;

        var result = repository.findOne(
                customer.email.eq("binh@example.com")
        );

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getLastName()).isEqualTo("Tran");
    }

    @Test
    void appliesPageAndSort() {
        QCustomer customer = QCustomer.customer;

        Page<Customer> page = repository.findAll(
                customer.active.isTrue(),
                PageRequest.of(
                        0,
                        1,
                        Sort.by(Sort.Direction.ASC, "lastName")
                                .and(Sort.by("id"))
                )
        );

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getTotalElements()).isEqualTo(2);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }
}
```

The example assumes QCustomer was generated by the annotation processor, the repository and entity are in the proper package, and JUnit 5, AssertJ, and Spring Boot JPA test support dependencies are present. `@DataJpaTest` typically runs in a transaction and rolls back after each test.

This test verifies four different behaviors: composing predicates, count/exists, findOne with a unique condition, and Page with count/sort. It verifies repository behavior; it does not prove queries use optimal indexes or run fast on production data.

## 13. What Are the Limitations of QuerydslPredicateExecutor?

`QuerydslPredicateExecutor` is a convenient abstraction for common Predicate-based read operations. It is not a full API for controlling every part of a query.

Cases where a custom repository with `JPAQueryFactory` should be considered:

- Complex DTO projections or selecting multiple expressions.
- JOIN FETCH to control association loading.
- GROUP BY, HAVING, or specialized aggregates.
- Subqueries or queries with multiple complex roots.
- Controlling DISTINCT, selections, or query metadata.
- Bulk UPDATE/DELETE.
- Specific SQL optimization and query plan control.

Example custom repository accepting the same Predicate while choosing its own projection:

```java
@Repository
public class CustomerQueryRepository {

    private final JPAQueryFactory queryFactory;

    public CustomerQueryRepository(JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    public List<CustomerSummary> findSummaries(Predicate predicate) {
        QCustomer customer = QCustomer.customer;

        return queryFactory
                .select(Projections.constructor(
                        CustomerSummary.class,
                        customer.id,
                        customer.firstName,
                        customer.lastName,
                        customer.email
                ))
                .from(customer)
                .where(predicate)
                .orderBy(customer.lastName.asc(), customer.id.asc())
                .fetch();
    }
}
```

This example illustrates using `JPAQueryFactory`; to compile, declare the factory bean with `EntityManager` and configure a compatible Querydsl JPA setup. The DTO constructor must match the order and types of the selected expressions.

You can use QuerydslPredicateExecutor for simple searches and a custom repository for reports or specialized queries. There is no need to force every query into a single abstraction.

## 14. Performance and Security

Querydsl builds queries with parameter binding through the provider, but that does not replace validation or authorization.

**Restrict filters.** Expose only fields users are allowed to search. Use `QuerydslBinderCustomizer` to restrict web binding.

**Limit page size.** Do not let clients request hundreds of thousands of records in a single request.

**Enforce tenant/user scope on the server.** Combine tenant conditions obtained from the security context with user-supplied predicates. Never trust a tenantId or ownerId sent by the client.

**Validate empty strings and null.** Do not add a condition when a filter is not selected; distinguish false/0 from omitted input.

**Be careful with contains.** `containsIgnoreCase` usually produces LIKE with a leading wildcard; standard B-tree indexes may not support it efficiently. Inspect execution plans and consider full-text/trigram indexes depending on the database.

**Paginate with deterministic ordering.** Append a unique key at the end of sort to reduce the chance of records shifting order across pages.

**Measure count queries.** Page may issue a separate count query. For filters with JOINs or complex predicates, counting can be expensive.

**Do not log sensitive data.** Query parameters may contain emails or personal information; mask data when logging.

## 15. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| QCustomer not found | Annotation processor did not run or wrong classifier | Check apt, Jakarta/Javax, and clean compile |
| Q-type does not reflect entity changes | Stale generated source or IDE not reloaded | Run clean compile and refresh project |
| Repository does not accept Predicate | Missing QuerydslPredicateExecutor or incompatible dependency | Check repository extends and Querydsl version |
| findOne throws multiple results error | Predicate is not unique | Use findAll or ensure a unique constraint |
| Empty form returns all data | BooleanBuilder has no conditions | Define explicit behavior and check hasValue |
| False filter gets ignored | Using truthy check instead of null check | Use Boolean wrapper and check != null |
| OR widens results unexpectedly | Wrong predicate grouping | Build OR BooleanExpression before ANDing into builder |
| Clients can filter internal fields | Default web binding is too permissive | Use excludeUnlistedProperties and including |
| Slow Page total | Complex count query | Measure count separately, consider Slice/custom query |
| Duplicate results after JOIN | Association produces multiple rows | Use distinct or a custom query with right semantics |
| Querydsl methods insufficient | Executor only provides basic predicate operations | Use custom repository / JPAQueryFactory |
| Query slow with containsIgnoreCase | Leading-wildcard LIKE or missing suitable index | Inspect execution plan and search strategy |

## 16. Implementation Checklist

- [ ] Querydsl dependency and annotation processor match the project's Jakarta Persistence setup.
- [ ] Q-types are generated from entities, never edited manually.
- [ ] Repository extends `QuerydslPredicateExecutor<T>`.
- [ ] Predicates use Q-types instead of query string concatenation.
- [ ] A fresh BooleanBuilder is created per request.
- [ ] Optional filters distinguish null from false/0.
- [ ] Empty predicate behavior is explicitly decided.
- [ ] findOne is used only when the condition guarantees at most one result.
- [ ] count/exists are used for their intended purposes.
- [ ] Pageable enforces page size limits and deterministic sorting.
- [ ] Web binding allows only approved fields.
- [ ] Tenant/authorization conditions are added server-side.
- [ ] Complex queries use an appropriate custom repository.
- [ ] Integration tests verify findAll/findOne/count/exists and pagination.
- [ ] Important queries are measured via SQL and execution plans on the target database.

## Conclusion

`QuerydslPredicateExecutor` enables Spring Data JPA to execute type-safe Predicates through familiar repository methods: `findAll`, `findOne`, `count`, and `exists`. Q-types generated from entities give IDE property support and catch errors early; `BooleanBuilder` allows combining optional filters without concatenating JPQL strings.

Create a fresh predicate for each search, define clear behavior for empty forms, restrict HTTP-bound fields, and add tenant/authorization conditions on the server. Use Pageable when Page and count are needed; switch to a custom repository with `JPAQueryFactory` when projections, fetch joins, aggregates, or advanced query control are required. Test through the repository and a real JPA provider to verify both results and pagination behavior.