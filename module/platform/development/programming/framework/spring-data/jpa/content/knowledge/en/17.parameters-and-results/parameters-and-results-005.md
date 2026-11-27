# Single Return Types, Optional, and Multiple Results

## Objectives

The return type of a repository method in Spring Data JPA expresses how many results the application expects. A query may find zero rows, exactly one row, or multiple rows. Choosing the right return type makes empty cases explicit in code, avoids cardinality errors, and avoids loading more data than needed.

Common options:

- `T`: a single entity or projection; if no result is found, the method may return `null`; if more than one result is found, Spring Data throws a result size exception.
- `Optional<T>`: returns `Optional.empty()` if not found, `Optional.of(value)` if one is found; multiple results still fail.
- `List<T>` or collection: accepts zero, one, or many results; returns an empty collection when none match.
- `Page<T>` and `Slice<T>`: return a single page of results, with different metadata.
- `Stream<T>`: iterates results as a stream; requires managing transactions and closing the stream properly.

The return type does not enforce data uniqueness by itself. If business rules require an email or identifier to be unique, the database still needs a unique constraint.

## 1. Cardinality: how many rows can the query return?

Before declaring a method, determine the cardinality of the search criteria:

| Cardinality | Example | Appropriate return type |
| --- | --- | --- |
| Zero or at most one | Find customer by unique email | `Optional<Customer>` or nullable `Customer` |
| Exactly one by business rule | Load mandatory configuration | `Customer` with null check or explicit error handling |
| Zero, one, or many | Find customers by city | `List<Customer>` or another collection |
| First result by order | Latest record in a group | `Optional<T>` combined with `First` and deterministic sort |
| One page in a large set | Search list with page navigation | `Page<T>` or `Slice<T>` |

Do not choose a return type merely because the current caller wants one object. The query condition must genuinely guarantee at most one result, or the method must actively limit the results.

## 2. Returning a single entity: T

A repository method can return an entity directly:

```java
Customer getByEmailAddress(String emailAddress);
```

For single-result query methods, Spring Data JPA behaves as follows:

- No matching row: returns `null` if strict nullability is not enabled for the repository/package.
- Exactly one row: returns that entity.
- More than one row: throws `IncorrectResultSizeDataAccessException` (translated from the JPA provider's non-unique result error).

Type `T` is appropriate when the query is guaranteed to return at most one row, such as looking up by primary key or a business key backed by a unique constraint.

### Repository method nullability

In Spring Data, package-level nullability checks can be enabled via `@NonNullApi` in `package-info.java`. Parameters and return values are then treated as non-null by default; if a single-result query finds nothing, Spring Data may throw `EmptyResultDataAccessException` instead of silently returning null.

Example:

```java
@org.springframework.lang.NonNullApi
package com.example.repositories;
```

If a method in that package is allowed to return no result and you want to represent that with `null`, annotate it explicitly with `@Nullable`. When absence is normal, `Optional<T>` is usually easier to read and less ambiguous.

Do not assume every repository shares the same nullability policy. Inspect the project's package annotations and actual signatures.

## 3. Optional<T>: representing potentially absent results

`Optional<T>` fits when a query returns at most one result and not finding one is normal.

```java
Optional<Customer> findByEmailAddress(String emailAddress);
```

Usage:

```java
Optional<Customer> result = repository.findByEmailAddress(email);

if (result.isPresent()) {
    Customer customer = result.get();
    System.out.println(customer.getName());
} else {
    System.out.println("Customer not found");
}
```

Or more concisely:

```java
Customer customer = repository.findByEmailAddress(email)
        .orElseThrow(() -> new CustomerNotFoundException(email));
```

Useful Optional methods:

| Method | Meaning |
| --- | --- |
| `isPresent()` / `isEmpty()` | Checks whether a value is present or absent. |
| `orElse(value)` | Returns a default value if empty; `value` expression is evaluated eagerly before the call. |
| `orElseGet(supplier)` | Computes the default value lazily when Optional is actually empty. |
| `orElseThrow()` | Throws `NoSuchElementException` if empty. |
| `map(fn)` | Transforms the inner value if present. |
| `ifPresent(action)` | Performs an action if present. |

If creating the default value is expensive, `orElseGet` avoids unnecessary execution:

```java
Customer customer = repository.findByEmailAddress(email)
        .orElseGet(() -> createGuestCustomer(email));
```

`Optional<T>` does not mean the query picks an arbitrary row. If the condition matches multiple rows, Spring Data still throws `IncorrectResultSizeDataAccessException`. Optional only expresses zero-or-one.

### Optional and unique constraints

Suppose email is a unique identifier:

```java
@Column(nullable = false, unique = true)
private String emailAddress;
```

Repository:

```java
Optional<Customer> findByEmailAddress(String emailAddress);
```

A database unique constraint is the final safeguard against concurrent writes. Declaring `Optional` or checking `existsByEmailAddress` alone does not prevent two concurrent transactions from inserting the same email.

### Do not use Optional for every return type

- Do not use `Optional<List<Customer>>` for multi-result queries. Use `List<Customer>` and receive an empty list when there are no rows.
- Do not use `Optional` as the type of a persistent property in a JPA entity. Use regular property types; Optional can be used at the repository/service layer.
- Do not return `null` instead of an `Optional`; repositories should return `Optional.empty()`.
- Do not call `get()` without checking or having a guaranteed reason that the Optional holds a value.

## 4. Multiple results: List and collections

When a query may match multiple entities, use a collection:

```java
List<Customer> findAllByCityOrderByNameAscIdAsc(String city);
```

Characteristics:

- No results: returns an empty collection, never `null`.
- One result: collection contains one element.
- Multiple results: collection contains the matching elements.
- Ordering is only guaranteed when the query declares `OrderBy` or the caller passes a `Sort`/`Pageable` with sorting.

Collection types supported by Spring Data include `List`, `Collection`, `Iterable`, `Set`, and `Streamable` where appropriate. `List` is usually the clearest choice when order and indexed access matter.

### Why not return a single entity when a query might match multiple rows?

Example:

```java
Customer findByCity(String city);
```

If the city has multiple customers, the method above does not automatically return the first element. It throws `IncorrectResultSizeDataAccessException` because the signature asks for one result while the query returns more than one.

If you need all results, change it to `List<Customer>`. If you only need one result according to business rules, use `First`/`Top` with deterministic ordering:

```java
Optional<Customer> findFirstByCityOrderByCreatedAtDescIdDesc(String city);
```

Here `createdAt DESC` picks the newest record; `id DESC` acts as a tie-breaker when timestamps are equal. Without sorting, "first" has no stable meaning because databases do not guarantee row order.

## 5. Page, Slice, and List with Pageable

For large datasets, avoid loading all results into memory just to display one page.

### Page<T>

`Page<T>` contains page content along with total element count and total page count:

```java
Page<Customer> findByCity(String city, Pageable pageable);
```

Example:

```java
Pageable pageable = PageRequest.of(
        0,
        20,
        Sort.by("name").ascending().and(Sort.by("id").ascending())
);
Page<Customer> page = repository.findByCity("Ha Noi", pageable);

List<Customer> content = page.getContent();
long total = page.getTotalElements();
int pages = page.getTotalPages();
```

The first page has index `0`. `Page` typically requires a count query to calculate the total number of rows; Spring Data can optimize and omit the count query in some cases when the total can be inferred from the page content, but you should not assume counting is free.

### Slice<T>

`Slice<T>` provides page content and whether a next page exists, without requiring an exact total count:

```java
Slice<Customer> findByActiveTrue(Pageable pageable);
```

```java
Slice<Customer> slice = repository.findByActiveTrue(
        PageRequest.of(0, 20, Sort.by("id").ascending())
);
boolean hasNext = slice.hasNext();
```

Spring Data typically fetches one extra row beyond the page size to determine `hasNext()`. Since no total count is needed, Slice can avoid an expensive count query.

### List<T> with Pageable

A method can return `List<T>` and accept `Pageable` to apply limit/offset and sorting without returning Page/Slice metadata:

```java
List<Customer> findByActiveTrue(Pageable pageable);
```

Choose `Page` when the UI needs the total page count, `Slice` when it only needs to know if there is a next page, and `List` when you only need the content of a data slice.

## 6. Stream<T> and resource lifecycle

Repository methods can return `Stream<T>` to iterate results lazily:

```java
Stream<Customer> streamByCity(String city);
```

A stream may hold JDBC resources and the persistence context open during iteration. Therefore, execute it within an appropriate transaction and close the stream:

```java
try (Stream<Customer> customers = repository.streamByCity("Ha Noi")) {
    customers.forEach(this::processCustomer);
}
```

Do not keep the stream alive after the transaction ends. If you only need a moderately sized list, `List<T>` is simpler. For large batch processing, consider streaming, fetch size, and keyset pagination based on provider/database capabilities.

## 7. Projections and non-entity return types

Repositories do not have to return full entities. If only a few fields are needed, use an interface projection or DTO to reduce data fetched and hydrated:

```java
public interface CustomerNameView {
    Long getId();
    String getName();
}

List<CustomerNameView> findByCity(String city);
```

Or a DTO constructor expression in JPQL:

```java
@Query("select new com.example.CustomerSummary(c.id, c.name) "
     + "from Customer c where c.city = :city")
List<CustomerSummary> findSummariesByCity(@Param("city") String city);
```

Cardinality rules still apply: a single-value projection may return no result or fail if the query returns multiple rows; a collection projection can return multiple rows or an empty collection.

## 8. @Query does not change return type rules

The return type must still match the number of rows the JPQL query can return:

```java
@Query("select c from Customer c where c.emailAddress = :email")
Optional<Customer> lookupByEmail(@Param("email") String email);

@Query("select c from Customer c where c.city = :city order by c.name")
List<Customer> lookupByCity(@Param("city") String city);
```

Using `@Query` does not turn a multi-row query into a single-row query. If you declare `Optional<Customer>` and two rows match, a result size exception will still occur.

For single-row queries that may find nothing, `Optional<T>` expresses the contract more clearly. For multi-row queries, use a collection or Page/Slice.

## 9. Return type decision table

| Need | Recommended | Avoid |
| --- | --- | --- |
| Find by primary key | `Optional<T>` via `findById` | Querying a collection and taking the first item |
| Find by unique email | `Optional<T>` plus unique constraint | Assuming Optional enforces uniqueness |
| Query may return nothing and caller accepts null | Nullable `T`, with explicit nullability | Leaving callers guessing if null is valid |
| Find all entities by property | `List<T>` | `Optional<List<T>>` |
| Pick one latest record | `Optional<T>` + `First` + stable sort | `findFirst` without ordering |
| List with total page count | `Page<T>` | Running a second manual count when Page already provides total |
| Only need to know if more data exists | `Slice<T>` | Counting everything when total is unneeded |
| Stream large results | `Stream<T>` properly closed in transaction | Keeping stream open past transaction |

## 10. Runnable example with Java 17+, Spring Boot, and H2

This example creates four customers. Email is unique; multiple customers can share the same city. The repository demonstrates single results, Optional, List, First, Page, and Slice.

### Project structure

```text
repository-return-types/
├── pom.xml
└── src/
    └── main/
        ├── java/com/example/returntypes/
        │   ├── ReturnTypesApplication.java
        │   ├── Customer.java
        │   └── CustomerRepository.java
        └── resources/
            └── application.properties
```

### `pom.xml`

```xml
<?xml version="1.0" encoding="UTF-8"?>
<project xmlns="http://maven.apache.org/POM/4.0.0"
         xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"
         xsi:schemaLocation="http://maven.apache.org/POM/4.0.0 https://maven.apache.org/xsd/maven-4.0.0.xsd">
    <modelVersion>4.0.0</modelVersion>
    <parent>
        <groupId>org.springframework.boot</groupId>
        <artifactId>spring-boot-starter-parent</artifactId>
        <version>3.4.5</version>
        <relativePath/>
    </parent>
    <groupId>com.example</groupId>
    <artifactId>repository-return-types</artifactId>
    <version>0.0.1-SNAPSHOT</version>
    <properties>
        <java.version>17</java.version>
    </properties>
    <dependencies>
        <dependency>
            <groupId>org.springframework.boot</groupId>
            <artifactId>spring-boot-starter-data-jpa</artifactId>
        </dependency>
        <dependency>
            <groupId>com.h2database</groupId>
            <artifactId>h2</artifactId>
            <scope>runtime</scope>
        </dependency>
    </dependencies>
    <build>
        <plugins>
            <plugin>
                <groupId>org.springframework.boot</groupId>
                <artifactId>spring-boot-maven-plugin</artifactId>
            </plugin>
        </plugins>
    </build>
</project>
```

### `src/main/resources/application.properties`

```properties
spring.datasource.url=jdbc:h2:mem:returntypes;DB_CLOSE_DELAY=-1
spring.datasource.username=sa
spring.datasource.password=
spring.jpa.hibernate.ddl-auto=create-drop
spring.jpa.open-in-view=false
logging.level.org.hibernate.SQL=DEBUG
```

### `Customer.java`

```java
package com.example.returntypes;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;
import java.time.Instant;

@Entity
@Table(name = "customers")
public class Customer {
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @Column(nullable = false, unique = true, length = 180)
    private String emailAddress;

    @Column(nullable = false, length = 80)
    private String city;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false)
    private boolean active;

    protected Customer() {
    }

    public Customer(String name, String emailAddress, String city,
                    Instant createdAt, boolean active) {
        this.name = name;
        this.emailAddress = emailAddress;
        this.city = city;
        this.createdAt = createdAt;
        this.active = active;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmailAddress() {
        return emailAddress;
    }

    public String getCity() {
        return city;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }
}
```

### `CustomerRepository.java`

```java
package com.example.returntypes;

import java.util.List;
import java.util.Optional;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Slice;
import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository extends JpaRepository<Customer, Long> {
    Customer getByEmailAddress(String emailAddress);

    Optional<Customer> findByEmailAddress(String emailAddress);

    List<Customer> findAllByCityOrderByNameAscIdAsc(String city);

    Optional<Customer> findFirstByCityOrderByCreatedAtDescIdDesc(String city);

    Page<Customer> findByCity(String city, Pageable pageable);

    Slice<Customer> findByActiveTrue(Pageable pageable);
}
```

`getByEmailAddress` illustrates a direct entity return type; if not found and the package does not enable strict nullability, the result is null. `findByEmailAddress` expresses the same cardinality using Optional. Do not declare both methods in practice to differentiate query logic; they merely illustrate two different return contracts.

### `ReturnTypesApplication.java`

```java
package com.example.returntypes;

import java.time.Instant;
import java.util.List;
import org.springframework.boot.CommandLineRunner;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Slice;
import org.springframework.data.domain.Sort;

@SpringBootApplication
public class ReturnTypesApplication {
    public static void main(String[] args) {
        SpringApplication.run(ReturnTypesApplication.class, args);
    }

    @Bean
    CommandLineRunner demo(CustomerRepository repository) {
        return args -> {
            repository.saveAll(List.of(
                    new Customer("An", "an@example.com", "Ha Noi",
                            Instant.parse("2025-01-01T00:00:00Z"), true),
                    new Customer("Binh", "binh@example.com", "Ha Noi",
                            Instant.parse("2025-02-01T00:00:00Z"), true),
                    new Customer("Cuong", "cuong@example.com", "Ho Chi Minh City",
                            Instant.parse("2025-02-15T00:00:00Z"), true),
                    new Customer("Dung", "dung@example.com", "Ha Noi",
                            Instant.parse("2025-03-01T00:00:00Z"), false)
            ));
            repository.flush();

            Customer single = repository.getByEmailAddress("an@example.com");
            System.out.println("Single entity: " + single.getName());

            System.out.println("Optional missing: "
                    + repository.findByEmailAddress("missing@example.com").isEmpty());

            List<Customer> cityCustomers =
                    repository.findAllByCityOrderByNameAscIdAsc("Ha Noi");
            System.out.println("List by city: " + names(cityCustomers));

            Customer latest = repository
                    .findFirstByCityOrderByCreatedAtDescIdDesc("Ha Noi")
                    .orElseThrow();
            System.out.println("Latest in Ha Noi: " + latest.getName());

            Page<Customer> page = repository.findByCity(
                    "Ha Noi",
                    PageRequest.of(0, 2, Sort.by("name").ascending().and(Sort.by("id").ascending()))
            );
            System.out.println("Page 0: " + names(page.getContent())
                    + " | total=" + page.getTotalElements());

            Slice<Customer> slice = repository.findByActiveTrue(
                    PageRequest.of(0, 2, Sort.by("id").ascending())
            );
            System.out.println("Active slice: " + names(slice.getContent())
                    + " | hasNext=" + slice.hasNext());
        };
    }

    private static String names(List<Customer> customers) {
        return customers.stream()
                .map(Customer::getName)
                .reduce((left, right) -> left + ", " + right)
                .orElse("");
    }
}
```

### Running the application

```bash
mvn spring-boot:run
```

Application console output:

```text
Single entity: An
Optional missing: true
List by city: An, Binh, Dung
Latest in Ha Noi: Dung
Page 0: An, Binh | total=3
Active slice: An, Binh | hasNext=true
```

Output is based on a fresh H2 database for the example. IDs are generated in insertion order; list and page ordering is determined by `OrderBy` or `Sort`, not by physical table order.

## 11. Common errors

1. **Using a single entity for a condition that can match multiple rows:** Spring Data throws `IncorrectResultSizeDataAccessException`. Switch to a collection or explicitly limit with `First`/`Top`.
2. **Thinking Optional automatically picks one row:** Optional only represents zero-or-one; multiple rows still fail.
3. **Using Optional<List<T>>:** collection queries already return an empty list when there are no results.
4. **Assuming an entity return is always non-null:** if not found, the method may return null unless a nullability policy dictates otherwise.
5. **Using First without sorting:** the selected result is unstable. Add `OrderBy` with a unique tie-breaker.
6. **Using Optional instead of a unique constraint:** two transactions can still write the same business key. Protect with a database constraint.
7. **Choosing Page when total count is not needed:** the count query can be expensive; consider Slice or List with Pageable.
8. **Failing to close Stream:** streams can hold connections and the persistence context open. Use try-with-resources inside a transaction.
9. **Returning full entities when only a few fields are needed:** consider projections or DTOs to reduce loaded data.
10. **Returning null for Optional:** return `Optional.empty()` and keep the contract consistent.

## 12. Practical guidelines

- Determine the maximum number of results before choosing a return type.
- Use `Optional<T>` for zero-or-one queries where absence is normal.
- Only use `T` when the query guarantees at most one result; clarify nullability.
- Use `List<T>` or collections for multi-result queries; an empty collection represents not found.
- Use `First`/`Top` with stable sorting when business rules require picking one item from multiple rows.
- Use unique constraints to guarantee business key uniqueness under concurrency.
- Choose `Page`, `Slice`, or `List` with `Pageable` based on metadata needs.
- Close `Stream<T>` and keep it within an appropriate transaction.
- Use projections when the entire entity is not needed.

Key takeaway: **`T` represents a single result and may be null when not found; `Optional<T>` explicitly represents zero-or-one; a collection represents zero-to-many and is empty when no rows match. If a query can return multiple rows, never declare a single return type unless results are limited or uniqueness is enforced in the database.**