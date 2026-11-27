# Method Name Structure: Subject, Predicate, and Ordering

## Objectives

After this lesson, you will be able to:

- Break down a Spring Data JPA derived query method into its subject, predicate, and ordering parts.
- Properly use the `find`, `exists`, `count`, `delete`, and `remove` prefixes.
- Combine properties with `And`, `Or`, and operators such as `Between`, `In`, `Like`, and `IsNull`.
- Express nested property paths and handle ambiguous property names.
- Choose appropriate return types such as `Optional`, `List`, `Page`, and `Slice`.
- Use `Sort` or `Pageable` for dynamic sorting.
- Recognize when a method name becomes too complex and should be switched to `@Query` or a custom repository.

## 1. What is a derived query method?

Spring Data JPA can generate queries from method names declared in a repository. This approach is commonly called query derivation or a derived query.

Example:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findByStatusAndCreatedAtAfter(
        CustomerStatus status,
        Instant time
    );
}
~~~

Spring Data parses the method name, looks up the entity's properties, and generates the corresponding query. The first method finds a Customer by email. The second method finds Customers with a matching status and a creation timestamp after a given point in time.

Derived queries are useful when a query has a simple structure, its name accurately describes the business intent, and there is no need to write JPQL/SQL. It is not a natural language understanding mechanism; method names must follow Spring Data's grammar.

## 2. General structure: subject, By, predicate, and ordering

A derived query typically has the following structure:

~~~text
[Subject][By][Predicate][OrderBy][SortDirection]
~~~

Example:

~~~java
List<Customer> findDistinctTop10ByStatusAndCreatedAtAfterOrderByCreatedAtDesc(
    CustomerStatus status,
    Instant createdAfter
);
~~~

This can be split into:

| Part | Value | Meaning |
|---|---|---|
| Subject | `findDistinctTop10` | Return search results, remove duplicates, and limit to at most 10 |
| Delimiter | `By` | Begins the predicate section |
| Predicate | `StatusAndCreatedAtAfter` | Status equals the passed value and createdAt is after the timestamp |
| Ordering | `OrderByCreatedAtDesc` | Sort createdAt in descending order |

The order of parameters in the method signature corresponds to the order of parameterized conditions in the predicate. Operators that do not require parameters such as `IsNull`, `True`, or `False` do not add extra input parameters.

## 3. The Subject part

The subject appears before `By`. It tells Spring Data the type of operation or desired result type.

### Common prefixes

| Prefix | Purpose | Example |
|---|---|---|
| `findBy` | Find entities | `findByEmail(...)` |
| `readBy` | Read entities | `readByStatus(...)` |
| `getBy` | Get entities | `getById` may collide with reserved methods; prefer descriptive names |
| `queryBy` | Query entities | `queryByStatus(...)` |
| `searchBy` | Search entities | `searchByName(...)` |
| `streamBy` | Return results as a Stream if supported by the return type | `streamByStatus(...)` |
| `existsBy` | Check whether a record exists | `existsByEmail(...)` |
| `countBy` | Count records | `countByStatus(...)` |
| `deleteBy` | Delete by condition | `deleteByStatus(...)` |
| `removeBy` | Delete by condition | `removeByStatus(...)` |

In search methods, the Subject can contain additional keywords:

- `Distinct`: requests distinct results.
- `First` or `Top`: limits the number of results.
- Some forms can be combined, for example `findDistinctTop5ByStatus(...)`.

Example:

~~~java
List<Customer> findTop5ByStatusOrderByCreatedAtDesc(
    CustomerStatus status
);
~~~

This method retrieves at most 5 Customers with the matching status and sorts them by createdAt descending.

`First` and `Top` can omit a number; in that case, the default limit is one result. You can use the entity type or `Optional` as the return type if business rules guarantee there is at most one result.

### Understanding Distinct properly

`findDistinctByLastname(...)` generates a distinct query for entity results. However, `countDistinctByLastname(...)` typically counts distinct entity identifiers, not necessarily the number of different last names. Because each entity has its own ID, the result can be the same as `countByLastname(...)`.

If you need to count the number of distinct values of a property, write an explicit `@Query`, such as `select count(distinct c.lastname) ...`, instead of assuming that `countDistinctByLastname` means counting distinct last names.

## 4. The Predicate part

The Predicate appears after `By`. It describes the properties and comparison operators.

### Common comparison operators

| Keyword | Meaning | Example |
|---|---|---|
| No operator, `Is`, `Equals` | Equals | `findByStatus(...)` |
| `IsNot`, `Not` | Not equal | `findByStatusNot(...)` |
| `LessThan`, `Before` | Less than / before | `findByAgeLessThan(...)` |
| `LessThanEqual` | Less than or equal to | `findByAgeLessThanEqual(...)` |
| `GreaterThan`, `After` | Greater than / after | `findByCreatedAtAfter(...)` |
| `GreaterThanEqual` | Greater than or equal to | `findByAgeGreaterThanEqual(...)` |
| `Between` | Within a range | `findByCreatedAtBetween(from, to)` |
| `IsNull`, `Null` | Null value | `findByDeletedAtIsNull()` |
| `IsNotNull`, `NotNull` | Not null | `findByDeletedAtIsNotNull()` |
| `In` | In a collection of values | `findByStatusIn(statuses)` |
| `NotIn` | Not in a collection of values | `findByStatusNotIn(statuses)` |
| `True`, `False` | Boolean true/false | `findByActiveTrue()` |
| `Like` | Matches a LIKE pattern | `findByNameLike(pattern)` |
| `NotLike` | Does not match a LIKE pattern | `findByNameNotLike(pattern)` |

Example:

~~~java
List<Customer> findByAgeBetween(int minAge, int maxAge);

List<Customer> findByStatusIn(Collection<CustomerStatus> statuses);

List<Customer> findByDeletedAtIsNull();

List<Customer> findByActiveTrue();
~~~

With `Between`, the two parameters correspond to the lower bound and upper bound. With `In` and `NotIn`, the parameter is typically a Collection or array compatible with the property type.

### Null in parameters

If you use a regular equality method and pass null, Spring Data typically translates that comparison into an IS NULL condition. With `Not`/not equal and null, the corresponding behavior can be IS NOT NULL. Use `IsNull` or `IsNotNull` in the method name when the intent is explicitly to check for null; avoid relying on passing null implicitly to express multiple meanings.

## 5. Combining conditions with And and Or

`And` and `Or` combine predicates:

~~~java
List<Customer> findByStatusAndActiveTrue(
    CustomerStatus status
);

List<Customer> findByFirstNameOrLastName(
    String firstName,
    String lastName
);
~~~

Both can be combined:

~~~java
List<Customer> findByStatusAndActiveTrueOrPriority(
    CustomerStatus status,
    boolean priority
);
~~~

This naming corresponds to the grouped condition:

~~~text
(status = ? AND active = true) OR priority = ?
~~~

Spring Data splits `Or` parts into branches, and within each branch there can be multiple `And` conditions. SQL also gives AND higher precedence than OR, but you should not use long method names to describe complex or easily misunderstood business logic.

Derived methods do not provide arbitrary parentheses syntax like Java expressions. If the logic involves multiple OR/AND groups, nested conditions, subqueries, or requires explicit precedence control, use `@Query` or the Specification/Criteria API.

## 6. LIKE, Containing, and string search

Spring Data supports several keywords for LIKE operations:

| Keyword | Meaning |
|---|---|
| `Like` | Uses the LIKE pattern supplied by the parameter |
| `StartingWith` | String starts with the value |
| `EndingWith` | String ends with the value |
| `Containing` | String contains the value |
| `NotLike` | Does not match the pattern |
| `NotContaining` | Does not contain the value |

Example:

~~~java
List<Customer> findByNameStartingWith(String prefix);

List<Customer> findByNameEndingWith(String suffix);

List<Customer> findByNameContaining(String fragment);

List<Customer> findByNameContainingIgnoreCase(String fragment);
~~~

With `Like`, the parameter must usually include wildcard characters such as `%` or `_` according to SQL syntax. With `StartingWith`, `EndingWith`, and `Containing`, Spring Data automatically adds the appropriate wildcards.

Spring Data has a mechanism to escape certain wildcard characters in derived queries using containing/starting/ending so that they are treated as literal data characters rather than pattern wildcards. If you need exact control over patterns, escape characters, or full-text search, use `@Query` or dedicated database features.

### IgnoreCase

`IgnoreCase` can be appended after a string property:

~~~java
Optional<Customer> findByEmailIgnoreCase(String email);

List<Customer> findByFirstNameAndLastNameAllIgnoreCase(
    String firstName,
    String lastName
);
~~~

`IgnoreCase` applies to a single String property; `AllIgnoreCase` applies to all eligible String properties in the predicate. It is meaningless for numeric, date/time, or enum types.

How case-insensitive comparison behaves depends on the database, collation, and how the provider generates SQL. For identifying data such as email, normalize the value on write and define clear uniqueness rules rather than relying solely on IgnoreCase at query time.

## 7. Nested property paths

Derived queries can traverse associations or embedded properties.

Suppose Customer has an `address` property, and Address has `zipCode`:

~~~java
List<Customer> findByAddressZipCode(String zipCode);
~~~

Spring Data parses the name to resolve the property path `address.zipCode`.

However, camelCase names can be ambiguous if the entity simultaneously has an `addressZip` property and an `address.zipCode` property. The parser might choose a different path than intended.

Use an underscore to explicitly mark the boundary:

~~~java
List<Customer> findByAddress_ZipCode(String zipCode);
~~~

The underscore is the property path delimiter in derived method names. If the model has properties starting with an underscore or unusual names, follow Spring Data's escaping/property path rules and consider renaming properties to avoid ambiguity.

Example with an association:

~~~java
List<Order> findByCustomer_EmailIgnoreCase(String email);
~~~

This path means filtering Orders by the email of the associated Customer.

## 8. Sorting with OrderBy

`OrderBy` is placed at the end of the method name, after the predicate:

~~~java
List<Customer> findByStatusOrderByCreatedAtDesc(
    CustomerStatus status
);
~~~

Multiple properties can be sorted:

~~~java
List<Customer> findByStatusOrderByCreatedAtDescIdAsc(
    CustomerStatus status
);
~~~

- `Asc`: ascending.
- `Desc`: descending.
- Multiple properties can be chained consecutively.
- Property names after OrderBy must still exist in the entity/property path.

If Asc or Desc is omitted, the default direction is ascending. When stable ordering is needed for pagination, add a unique secondary key such as ID to prevent records with the same timestamp from shifting positions between pages.

## 9. Dynamic sorting and pagination

Method names are suited for fixed ordering. If the caller determines the order, use `Sort` or `Pageable`.

~~~java
Page<Customer> findByStatus(
    CustomerStatus status,
    Pageable pageable
);

List<Customer> findByActiveTrue(Sort sort);
~~~

Invocation example:

~~~java
Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
    )
);

Page<Customer> page =
        customerRepository.findByStatus(CustomerStatus.ACTIVE, pageable);
~~~

`Page` usually requires an additional count query to know the total number of elements/pages. `Slice` can be useful when you only need to know whether more data exists on the next page without needing the total count:

~~~java
Slice<Customer> findByStatus(
    CustomerStatus status,
    Pageable pageable
);
~~~

When combining static `OrderBy` with `Sort` or `Pageable`, clearly verify the resulting sort order according to the Spring Data API version in use. Avoid specifying both a fixed order in the method name and passing a different sort unnecessarily.

## 10. Return types and their semantics

| Return type | Meaning |
|---|---|
| Entity | Expects at most one result; if multiple results exist, an incorrect cardinality error may occur |
| `Optional<Entity>` | Returns an empty Optional if no result exists; more than one result is still an error |
| `List<Entity>` | List of results, which may be empty |
| `Set<Entity>` | Set of results; requires proper equals/hashCode |
| `Page<Entity>` | Page data and total count metadata, usually executes a count query |
| `Slice<Entity>` | Page data and whether a next page exists, without needing total count |
| `long` / `Long` | Typically used for count queries |
| `boolean` / `Boolean` | Typically used for exists queries |
| `void` or an appropriate count | Can be used for derived delete depending on the method and API |

If a query can return multiple results, do not declare `Optional<Entity>` hoping to retrieve only the first record. Use `First`/`Top` with explicit ordering if you truly want to limit results.

## 11. Reserved methods and property names

Some method names inherited from `CrudRepository`/`JpaRepository` are reserved methods, for example:

- `findById(ID id)`
- `existsById(ID id)`
- `deleteById(ID id)`

These methods always operate on the identifier declared with `@Id`, not necessarily a property named `id`.

If an entity has a primary key named `pk` as well as a business field named `id`, `findById(...)` is still the reserved method for finding by the primary key. To query the business property, use another clear method name, for example:

~~~java
Optional<Customer> findCustomerById(String externalId);
~~~

The descriptive token `Customer` before `By` avoids colliding with the reserved signature, and the parser resolves the `id` property in the predicate.

When a method name is confusing, choose a more descriptive name or use `@Query` to make the intent explicit.

## 12. Derived delete, exists, and count

In addition to queries that fetch entities, you can use the subject to create other operations:

~~~java
boolean existsByEmailIgnoreCase(String email);

long countByStatus(CustomerStatus status);

long deleteByStatus(CustomerStatus status);
~~~

`existsBy` checks existence, `countBy` counts matches, and `deleteBy`/`removeBy` deletes entities matching the condition.

Derived delete may load the matching entities and delete them one by one to apply lifecycle callbacks and cascades according to repository semantics. This differs from a bulk delete using `@Modifying @Query`, which can execute a single DELETE statement directly without synchronizing entities currently in the persistence context.

Custom-declared query methods do not always carry the same default transaction configuration as inherited CRUD methods. Place `@Transactional` on the appropriate service or method when the operation requires a transaction:

~~~java
@Service
public class CustomerCleanupService {

    private final CustomerRepository repository;

    public CustomerCleanupService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional
    public long removeInactive(CustomerStatus status) {
        return repository.deleteByStatus(status);
    }
}
~~~

With bulk deletes, consider clearing the persistence context or avoiding keeping affected entities in the context afterward to prevent stale managed state.

## 13. Comprehensive repository example

Suppose Customer has properties `email`, `firstName`, `lastName`, `status`, `active`, `createdAt`, and embedded `address.zipCode`.

~~~java
package com.example.customer;

import java.time.Instant;
import java.util.List;
import java.util.Optional;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.domain.Sort;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmailIgnoreCase(String email);

    List<Customer> findByStatusAndActiveTrue(
        CustomerStatus status
    );

    List<Customer> findByCreatedAtBetween(
        Instant from,
        Instant to
    );

    List<Customer> findByAddress_ZipCode(String zipCode);

    List<Customer> findTop5ByStatusOrderByCreatedAtDesc(
        CustomerStatus status
    );

    Page<Customer> findByLastNameContainingIgnoreCase(
        String fragment,
        Pageable pageable
    );

    List<Customer> findByStatus(CustomerStatus status, Sort sort);

    boolean existsByEmailIgnoreCase(String email);

    long countByStatus(CustomerStatus status);
}
~~~

Method names must match the entity's properties exactly. If `createdAt` is renamed to `createdOn`, the corresponding methods must also be updated. Spring Data typically parses repository methods when initializing the application context; an invalid property name can cause the application to fail at startup.

## 14. When should you switch to @Query?

Derived queries reduce boilerplate, but method names can become long and hard to read.

Example:

~~~java
List<Customer> findByStatusAndActiveTrueOrPriorityAndCreatedAtAfterOrderByLastNameAscFirstNameAsc(
    CustomerStatus status,
    boolean priority,
    Instant createdAfter
);
~~~

When a query has multiple condition groups, subqueries, aggregations, complex projections, or requires control over joins/fetches, use `@Query`:

~~~java
@Query("""
    select c
    from Customer c
    where c.status = :status
      and (
          c.active = true
          or c.priority = true
      )
      and c.createdAt >= :createdAfter
    order by c.lastName asc, c.firstName asc
    """)
List<Customer> findCandidates(
    @Param("status") CustomerStatus status,
    @Param("createdAfter") Instant createdAfter
);
~~~

JPQL uses entity names and Java properties, not SQL table/column names directly. If a query is database-specific, you can use a native query, though you should evaluate portability and maintainability.

## 15. Common errors and troubleshooting

| Symptom | Cause | Resolution |
|---|---|---|
| Application context fails to start | Property name in method does not exist | Verify field names and property paths |
| Query returning multiple results throws an error | Used entity/Optional for a non-unique query | Use List/Page or Top/First with explicit ordering |
| String search returns wrong results | Used Like without wildcards or confused it with Containing | Choose the right operator and understand the pattern |
| Property path points to the wrong field | Ambiguous camelCase name | Use underscore to mark property boundaries |
| Paginated results change order | Unstable sorting when multiple records share the same value | Add a unique secondary key to Sort |
| countDistinctBy does not count distinct field values as expected | Distinct is usually applied on entity/ID | Use @Query with count(distinct property) |
| deleteBy loads many entities | Derived delete executes per-entity lifecycle | Use a bulk query if semantics allow and manage the persistence context |
| Delete query method lacks a transaction | Custom-declared method does not have an active transaction | Call inside a @Transactional service |
| Method name is too long and hard to understand | Logic has many AND/ORs or multiple groups | Use @Query, Specification, or a custom repository |

## Pre-merge checklist

- [ ] Subject uses the proper prefix: find/read/get/query/exists/count/delete/remove.
- [ ] By properly separates the subject and predicate.
- [ ] Predicate property names match the entity and parameters are in the right order.
- [ ] And/Or logic is clear; complex queries are moved to @Query.
- [ ] OrderBy has explicit Asc/Desc directions and pagination sorting is stable.
- [ ] Return type matches cardinality and pagination requirements.
- [ ] Nested property paths use underscores when needed to avoid ambiguity.
- [ ] Reserved methods such as findById are understood to target the entity identifier.
- [ ] Delete/count/exists have appropriate transactions and semantics.
- [ ] Repository methods are verified by integration tests.

## Conclusion

Spring Data JPA derived query methods are parsed from the subject, the `By` delimiter, the predicate, and the `OrderBy` clause. The subject defines the operation and limit; the predicate describes properties and operators; ordering can be fixed in the method name or passed via Sort/Pageable. Method names must accurately reflect property paths and query cardinality. When AND/OR logic becomes complex, or special projections or join control are needed, switch to `@Query` or a custom repository to keep queries clear and easy to test.
