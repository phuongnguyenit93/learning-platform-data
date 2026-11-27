# Parameter and Result Nullability Across Spring Data Versions

Nullability specifies whether a parameter or return value is permitted to be `null`. In Spring Data, this contract directly affects how repository methods are declared, how missing records are handled, how optional parameters are passed, and whether violations can be caught at method invocation time.

How nullability is expressed has evolved across Spring Data generations. Since Spring Data 2.0, CRUD methods returning a single aggregate use Java `Optional`; versions 2.x and 3.x commonly use Spring Framework's JSR-305-based nullability annotations; starting with Spring Framework 7 and Spring Data 4, JSpecify is the recommended direction and Spring's legacy nullability annotations are deprecated.

This article focuses on Spring Data JPA, Java, and Kotlin. Always check the Spring Data Commons version bundled with your project, since most repository contracts are defined in the Commons module and reused by Spring Data JPA.

## 1. Where can null appear in a repository?

A repository method can encounter null in two independent places:

1. **Input parameters:** can the caller pass null, or is a value required?
2. **Return values:** a query may find no matching row; in that case, does the method return null, an empty Optional, or throw an exception?

Example:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Customer findByEmail(String email);

    Optional<Customer> findOptionalByEmail(String email);

    List<Customer> findAllByActiveTrue();
}
```

These three methods have different contracts:

- `findByEmail` returns a Customer or may return null if no result exists, unless a nullability contract dictates a non-null return.
- `findOptionalByEmail` represents a potentially absent result with `Optional<Customer>`.
- `findAllByActiveTrue` returns a list; if no records exist, the list is empty, never null.

Do not apply a single rule to every return type. A single entity may be absent; a collection normally represents an empty result set with an empty collection; a parameter may be nullable even when the return value is required.

## 2. Result contract since Spring Data 2.0

A major change arrived in **Spring Data 2.0**: CRUD methods returning a single aggregate instance use Java 8 `Optional` to represent the possibility that no value is found.

Modern API example:

```java
Optional<Customer> customer = customerRepository.findById(42L);
```

If the ID exists, Optional contains the Customer. If it does not exist, the result is `Optional.empty()`. Callers must handle both cases.

Prior to Spring Data 2.0, the legacy CRUD API used methods like `findOne(ID)` and could return null when not found. When upgrading to 2.0, the method was renamed to `findById(ID)` with an Optional return type. Consequently, legacy code cannot simply rename the method while keeping the old result handling.

Handling examples:

```java
Customer customer = customerRepository.findById(id)
    .orElseThrow(() -> new CustomerNotFoundException(id));
```

Or when absence is a normal business branch:

```java
Optional<Customer> customer = customerRepository.findById(id);

if (customer.isPresent()) {
    updateCustomer(customer.get());
} else {
    createCustomer();
}
```

Never call `get()` without verifying that Optional holds a value. Use `orElseThrow`, `ifPresent`, `map`, `orElse`, or appropriate combinators.

## 3. Changes across Spring Data generations

| Generation | Common representation | Key notes |
|---|---|---|
| Spring Data 1.x | Legacy single-result CRUD APIs like findOne could return null | Lacked the modern Optional CRUD API contract |
| Spring Data 2.x | Optional for single-aggregate CRUD; Spring nullability annotations | Can use @NonNullApi, @NonNull, @Nullable to declare and enforce |
| Spring Data 3.x | Continues Optional; Spring Framework 6 nullability annotations | Common with Spring Boot 3 and Java 17+; Spring annotations remain standard |
| Spring Data 4.x / Spring Framework 7 | Optional still supported; JSpecify is the recommended nullability approach | Legacy Spring @NonNullApi/@Nullable deprecated in favor of JSpecify's @NullMarked/@Nullable |

This table summarizes the main changes in nullability contracts, not every API change across major versions. Wrappers like Guava Optional, Scala Option, and Vavr Option are also supported on query methods depending on the module and classpath. For new Java code, prefer `java.util.Optional`.

When reading an older repository, do not infer the contract solely from the method name. Check the actual Spring Data Commons version, return type, package annotations, and method/parameter annotations.

## 4. Spring Data 2.x and 3.x: @NonNullApi

In Spring Data 2.x and 3.x, the standard way to declare non-null defaults for a package is `@NonNullApi` in `package-info.java`.

Example structure:

```text
src/main/java/
  com/example/customer/
    package-info.java
    Customer.java
    CustomerRepository.java
```

Contents of `package-info.java`:

```java
@NonNullApi
package com.example.customer;

import org.springframework.lang.NonNullApi;
```

When a package is marked `@NonNullApi`:

- Repository method parameters are non-null by default.
- Repository method return values are non-null by default.
- `@Nullable` can be placed on specific parameters or methods to permit null.
- `@NonNull` can explicitly mark a non-null position, though it is usually redundant inside a package already annotated with @NonNullApi.

Spring annotations are meta-annotated with JSR-305 so IDEs and static analysis tools understand nullability. Package-level annotations express the contract across the entire repository interface without annotating every parameter and return type.

Note: package annotations do not apply recursively to subpackages. If repositories live in subpackages, declare nullability in each corresponding package or check the active annotation scope.

## 5. @Nullable for parameters and results in Spring Data 2.x/3.x

Use `org.springframework.lang.Nullable` to explicitly mark where null is allowed as an argument or return value:

```java
package com.example.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.lang.Nullable;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    // email is required; result may be absent as Optional.
    Optional<Customer> findOptionalByEmail(String email);

    // Parameter can be null and single result can also be null.
    @Nullable
    Customer findByLegacyCode(@Nullable String legacyCode);

    // Collections always represent no results with an empty list.
    List<Customer> findAllByActiveTrue();
}
```

In a package with `@NonNullApi`:

- `findOptionalByEmail(null)` is rejected because email is non-null.
- If the email is not found, the method returns `Optional.empty()`.
- `findByLegacyCode(null)` is permitted to receive null.
- If `findByLegacyCode` finds no row, the method returns null because the return type is annotated with @Nullable.
- `findAllByActiveTrue()` returns an empty list if there are no active Customers.

Method/parameter annotations are intentional exceptions to the package default. Placing `@Nullable` on the return type does not automatically allow null parameters; to allow both, annotate both positions.

## 6. Runtime validation when using @NonNullApi

Nullability annotations are not merely documentation or IDE warnings. When a repository's package is marked `@NonNullApi`, Spring Data can enforce the nullability contract at runtime for query methods.

Example:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Customer getByEmail(String email);
}
```

If the package applies @NonNullApi:

- Passing `null` for non-null email can cause the method to throw `IllegalArgumentException`.
- If the query finds no Customer and the method is declared non-null, Spring Data throws `EmptyResultDataAccessException` instead of returning null.

Comparison of three declarations:

| Declaration | Null parameter | No result found |
|---|---|---|
| `Customer getByEmail(String email)` in @NonNullApi package | Rejected | EmptyResultDataAccessException |
| `@Nullable Customer findByEmail(@Nullable String email)` | Allowed | Returns null |
| `Optional<Customer> findOptionalByEmail(String email)` | Rejected if package defaults to non-null | Optional.empty() |

These checks are performed by Spring Data's repository proxy; they do not mean every Java method in the entire application is automatically checked. Scope depends on annotations, packages, method types, and framework version.

If a package has no nullability default and a method has no annotations, the contract may be unspecified. Callers should not assume the result is guaranteed non-null. Use Optional or declare nullability explicitly to avoid relying on implicit assumptions.

## 7. Collection, Page, Slice, and Stream never return null

Spring Data guarantees that repository methods returning collections, collection alternatives, wrappers, or streams represent missing results with their respective empty forms.

Example:

```java
List<Customer> findByLastname(String lastname);

Set<Customer> findByActiveTrue();

Page<Customer> findByStatus(
    CustomerStatus status,
    Pageable pageable
);

Slice<Customer> findByCity(
    String city,
    Pageable pageable
);

Stream<Customer> streamByActiveTrue();
```

When no records match:

- List returns `Collections.emptyList()` or an equivalent empty list.
- Set returns an empty set.
- Page returns a Page with empty content.
- Slice returns a Slice with empty content.
- Stream returns an empty stream.

Therefore, you do not need to write:

```java
List<Customer> customers = repository.findByLastname(lastname);

if (customers != null && !customers.isEmpty()) {
    // ...
}
```

Simply write:

```java
if (!customers.isEmpty()) {
    // ...
}
```

Streams must be properly closed and used within an appropriate transaction. A non-null guarantee does not mean a stream always loads incrementally without holding JDBC resources.

## 8. Optional fits a single result

Use `Optional<T>` when a query can return at most one entity:

```java
Optional<Customer> findByEmail(String email);

Optional<Customer> findByExternalCode(String externalCode);
```

An important requirement is that the query must have at-most-one semantics. If the database contains multiple matching records, Spring Data can throw `IncorrectResultSizeDataAccessException`; Optional does not mean "pick the first of multiple records".

If multiple results are expected, use List, Set, Page, Slice, or Stream as appropriate.

Do not use `Optional<List<Customer>>` to represent a potentially empty list. Return `List<Customer>` and use an empty list when no elements match. Optional is meant for a single potentially absent value.

For the CRUD API, `findById` is the canonical example:

```java
Optional<Customer> customer = repository.findById(id);
```

For custom query methods, you can declare:

```java
Optional<Customer> findByEmail(String email);
```

## 9. A nullable parameter does not mean skipping the search condition

This is a common misconception. `@Nullable` on a parameter only states that the method accepts a null value. It does not automatically mean the query omits the condition when null is passed.

Example:

```java
List<Customer> findByCity(@Nullable String city);
```

If the caller passes null, the derived query may interpret the equality condition as matching rows where city is NULL. That does not mean "return all Customers regardless of city".

If business rules require a null parameter to skip the filter, write explicit logic:

```java
public List<Customer> searchCustomers(@Nullable String city) {
    if (city == null) {
        return repository.findAll();
    }

    return repository.findByCity(city);
}
```

For multiple optional filters, use Specification, Criteria API, or dynamic queries. A JPQL expression like `(:city is null or c.city = :city)` can also express an optional filter, though you must check performance, index usage, and null semantics on the actual database.

For native queries, SQL follows three-valued logic: comparing `column = NULL` is not equivalent to `column IS NULL`. Never assume a null parameter in native SQL behaves like a derived query.

## 10. Parameter nullability and database column nullability are separate layers

Repository annotations like `@Nullable`, `@NonNullApi`, or JSpecify describe the Java method contract. They do not create database constraints on their own.

Distinguish:

| Mechanism | Purpose |
|---|---|
| `@Nullable` / `@NonNullApi` | Null contract of method parameters and return values |
| `@Column(nullable = false)` | Non-nullable column mapping metadata and schema generation support |
| Bean Validation `@NotNull` | Object value validation per the validation lifecycle |
| `NOT NULL` in database | Data integrity constraint at the database layer |

Example:

```java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @NotNull
    @Column(name = "email", nullable = false, length = 254)
    private String email;
}
```

Here `@NotNull` and `nullable = false` describe the entity/column email data. They do not replace annotations on repository methods. A repository method might still accept a nullable parameter if business logic needs to search for Customers with NULL email, even if this entity design marks email non-nullable.

In real systems, align all three layers: Java API contract, business validation, and database constraints. Database constraints remain the final safeguard against concurrent operations or writes outside the application.

## 11. Spring Data 4.x: moving to JSpecify

Starting with **Spring Framework 7 and Spring Data 4**, JSpecify is the recommended way to describe nullability. Legacy Spring nullability annotations such as `@NonNullApi` and `org.springframework.lang.Nullable` are deprecated in favor of JSpecify.

Primary annotations:

| Annotation | Meaning |
|---|---|
| `@NullMarked` | Sets non-null default at module, package, or class scope |
| `@Nullable` | Type/value may be null |
| `@NonNull` | Type/value must be non-null |
| `@NullUnmarked` | Opts out of an enclosing null-marked scope, returning to unspecified nullness |

Package-level declaration in `package-info.java`:

```java
@NullMarked
package com.example.customer;

import org.jspecify.annotations.NullMarked;
```

Repository inside that package:

```java
package com.example.customer;

import java.util.Optional;
import org.jspecify.annotations.Nullable;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    @Nullable
    Customer findByLegacyCode(@Nullable String legacyCode);

    List<Customer> findAllByActiveTrue();
}
```

The semantics mirror the earlier non-null default model:

- email is non-null by default.
- Optional remains the wrapper representing potentially absent results.
- legacyCode is permitted to be null.
- the Customer result of findByLegacyCode is permitted to be null.
- returned collections use empty collections when no data matches.

With JSpecify, `@Nullable` is a type-use annotation. Placing the annotation immediately before the target type clearly distinguishes nullability of return values, parameters, generic type arguments, or array elements.

Examples of type-use semantics:

```java
@Nullable String findNickname();   // String result may be null.

List<@Nullable String> labels();   // Non-null List whose elements may be null.

@Nullable List<String> loadLabels(); // The List itself may be null.
```

In typical repositories, Spring Data collection return types are guaranteed non-null, so do not declare nullable collections unless a specific custom API truly requires it.

## 12. @NullUnmarked and nullability scope in JSpecify

`@NullMarked` can be placed on a module, package, or class. This scope applies non-null defaults across the API without annotating every position individually.

If an area of code needs to keep unspecified nullability, you can apply `@NullUnmarked` at the appropriate package, class, or method level:

```java
@NullUnmarked
class LegacyCustomerAdapter {
    // Nullness in this scope is not inferred from an enclosing @NullMarked.
}
```

Avoid applying `@NullUnmarked` broadly just to dodge declaring nullability. It reduces the information available to the compiler, IDE, and static analysis tools. When migrating a large codebase to JSpecify, use it as an intentional compatibility boundary and narrow it over time.

When overriding methods, repeat appropriate nullness annotations. Nullability annotations should not be assumed to be inherited automatically in every override scenario.

## 13. Kotlin repositories and null-safety

Kotlin expresses nullability directly in the type system:

```kotlin
interface CustomerRepository : JpaRepository<Customer, Long> {

    fun findByEmail(email: String): Customer?

    fun findOptionalByEmail(email: String): Customer?

    fun findByLegacyCode(code: String?): Customer?

    fun findAllByActiveTrue(): List<Customer>
}
```

Types:

- `String` disallows null.
- `String?` allows null.
- `Customer` is a required non-null result.
- `Customer?` is a nullable result.
- `List<Customer>` is non-null; an empty list represents no elements.
- `List<Customer?>` means elements may be null, distinct from a nullable list `List<Customer>?`.

The Kotlin compiler warns about or rejects calls passing null into non-null parameters. Spring Data also reads Kotlin metadata to perform corresponding runtime null checks. `kotlin-reflect` must be on the classpath for Kotlin nullability introspection to work properly per Spring Data documentation.

In Kotlin, you do not need Java Optional for every absent result; nullable types usually express it more naturally. However, when calling Java APIs returning Optional, still convert and handle their contract properly.

## 14. Checking your project's actual version

Do not decide which annotations to use based on a Spring Boot version mentioned in an old README. Inspect the actually resolved dependencies:

Maven:

```bash
mvn dependency:tree -Dincludes=org.springframework.data:spring-data-jpa,org.springframework.data:spring-data-commons,org.springframework:spring-core
```

Gradle:

```bash
./gradlew dependencyInsight --dependency spring-data-jpa --configuration runtimeClasspath
./gradlew dependencyInsight --dependency spring-data-commons --configuration runtimeClasspath
```

Check all of:

- spring-data-jpa.
- spring-data-commons.
- spring-core / Spring Framework.
- JDK version and Kotlin version if repositories are written in Kotlin.

Let Spring Boot dependency management or the Spring Data BOM manage related versions. Never pin spring-data-jpa and spring-data-commons to two different release trains, as APIs and nullability metadata may be incompatible.

Practical rule:

- Spring Data 2.x/3.x projects: typically use `org.springframework.lang.NonNullApi`, `NonNull`, `Nullable`.
- Spring Data 4.x / Spring Framework 7 projects: prefer `org.jspecify.annotations.NullMarked`, `Nullable`, `NonNull`.
- When upgrading major versions: check deprecation warnings, update package-info, and test repository methods returning no results.

## 15. Designing repository methods around business intent

Choose return types according to result count and the meaning of not finding a match:

| Need | Suggested return type | When no result matches |
|---|---|---|
| Find at most one Customer; absence is normal | `Optional<Customer>` | Optional.empty() |
| Find one Customer that must exist | `Customer` in a non-null package | Exception when missing |
| Find one Customer; returning null is acceptable | `@Nullable Customer` | null |
| Find multiple Customers | `List<Customer>` | Empty List |
| Find multiple Customers with total page count | `Page<Customer>` | Empty Page |
| Load more without needing total count | `Slice<Customer>` | Empty Slice |
| Iterate results as a stream | `Stream<Customer>` | Empty Stream; must close stream |
| Required filter parameter | `String email` in non-null scope | Null rejected |
| Optional filter parameter | `@Nullable String city` or `String?` | Query must explicitly define null semantics |

Clear repository example:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByCity(String city);

    Page<Customer> findByStatus(
        CustomerStatus status,
        Pageable pageable
    );

    long countByStatus(CustomerStatus status);

    boolean existsByEmail(String email);
}
```

Do not use Optional for booleans or counts: `existsByEmail` already expresses true/false; `countByStatus` returns a count. Also never use null in place of an empty collection.

## 16. Common errors

| Symptom | Cause | Solution |
|---|---|---|
| Calling get() on Optional fails | Optional.empty() returned without caller checking | Use orElseThrow, ifPresent, or map |
| findBy... returns null unexpectedly | Method returns entity directly without a non-null contract | Use Optional or declare @Nullable/@NonNullApi explicitly |
| Empty query throws EmptyResultDataAccessException | Method is declared non-null inside a @NonNullApi/@NullMarked package | Use Optional or mark return @Nullable if business logic allows it |
| Passing null throws IllegalArgumentException | Parameter is inside a non-null scope | Annotate @Nullable if null is valid, or reject input at the boundary |
| Subpackage does not inherit default nullability | package-info in parent package does not apply recursively | Declare annotations on subpackages or JSpecify module scope |
| Unnecessary null checks on collections | Confusing empty collections with null | Use isEmpty() |
| Optional receives multiple results | Query does not guarantee at most one row | Use List or add unique constraints/conditions |
| @Nullable parameter assumed to skip filter | Confusing null contract with dynamic query logic | Handle null explicitly in service/Specification |
| Using Spring annotations on Spring Data 4 | Legacy annotations deprecated in Spring Framework 7 | Migrate to JSpecify |
| Using JSpecify inconsistently in older projects | Dependencies/tooling lack uniform support | Check version and use annotations matching the release train |
| @Column(nullable=false) yet repository still accepts null | Confusing database mapping with method contract | Declare nullability on repository as well as entity/validation/database |
| Kotlin code hits runtime nulls | Missing kotlin-reflect or unrecognized metadata | Check dependencies and Kotlin signature nullability |

## 17. Checklist when upgrading Spring Data

Before upgrading from Spring Data 1.x to 2.x:

1. Locate `findOne(...)` calls and migrate to `findById(...)`.
2. Replace null-check logic with Optional handling.
3. Audit query methods returning entities directly and decide where to use Optional.
4. Identify nullable parameters and declare explicit contracts.
5. Test zero-result and multi-result cases.

When upgrading from Spring Data 2.x to 3.x:

1. Verify Java 17 and Spring Framework 6 requirements.
2. Audit nullability annotation imports from `org.springframework.lang`.
3. Check runtime validation inside @NonNullApi packages.
4. Re-test repository queries and Kotlin metadata if applicable.

When upgrading from Spring Data 3.x to 4.x:

1. Verify Spring Framework 7 and compatible JDK version.
2. Migrate package-level `@NonNullApi` to JSpecify `@NullMarked`.
3. Migrate `org.springframework.lang.Nullable` to `org.jspecify.annotations.Nullable`.
4. Review `@NonNull` and `@NullUnmarked` across type/package/class scopes.
5. Update IDE, compiler, and static analysis tools to recognize JSpecify.
6. Run tests for null parameters, missing results, and empty collections.

Do not upgrade by mechanically replacing all imports. Verify the intended nullability semantics before and after changing, especially in packages using non-null defaults.

## 18. Testing nullability contracts

Write tests for both parameters and results:

```java
@DataJpaTest
class CustomerRepositoryNullabilityTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void optionalResultRepresentsMissingCustomer() {
        Optional<Customer> result =
            repository.findByEmail("missing@example.com");

        assertThat(result).isEmpty();
    }

    @Test
    void collectionResultIsEmptyRatherThanNull() {
        List<Customer> result =
            repository.findByCity("unknown-city");

        assertThat(result).isNotNull().isEmpty();
    }

    @Test
    void nullableResultCanRepresentAbsence() {
        Customer result =
            repository.findByLegacyCode("missing-code");

        assertThat(result).isNull();
    }
}
```

This is an illustrative skeleton; method names and annotations must match the actual repository. Tests invoking a non-null return method inside a @NonNullApi package when no data is found should assert the expected exception:

```java
assertThatThrownBy(() -> repository.getByEmail("missing@example.com"))
    .isInstanceOf(EmptyResultDataAccessException.class);
```

Non-null parameter tests can verify that null is rejected:

```java
assertThatThrownBy(() -> repository.findOptionalByEmail(null))
    .isInstanceOf(IllegalArgumentException.class);
```

Do not just verify that the code compiles. Test the runtime behavior of the repository proxy because nullability validation can occur at method invocation time.

## 19. Official reference documentation

- [Spring Data JPA 3.5 — Null Handling of Repository Methods](https://docs.spring.io/spring-data/data-jpa/reference/3.5/repositories/null-handling.html): Optional contracts, @NonNullApi, @Nullable, and runtime validation in the Spring Data 3.x generation.
- [Spring Data Commons 4.1 — Null Handling of Repository Methods](https://docs.spring.io/spring-data/commons/reference/repositories/null-handling.html): JSpecify, wrapper return types, runtime validation, and Kotlin null-safety in Spring Data 4.x.
- [Spring Data Commons 2.0 — Reference Documentation](https://docs.spring.io/spring-data/commons/docs/2.0.13.RELEASE/reference/html/): historical milestone introducing Optional and nullability annotations in Spring Data 2.0.

**Core principle:** choose return types to express whether a result can be absent; use Optional for a single potentially absent result, empty collections for multiple results, and @Nullable when null is genuinely part of the contract. Spring Data 2.x/3.x commonly use Spring nullability annotations with @NonNullApi; Spring Data 4.x moves to JSpecify with @NullMarked. Always check your actual Spring Data Commons version, package scope, and repository runtime behavior rather than relying on assumptions about null.