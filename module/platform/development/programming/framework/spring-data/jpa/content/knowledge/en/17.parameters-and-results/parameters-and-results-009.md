# Handling Empty Results and IncorrectResultSizeDataAccessException in Spring Data JPA

When calling a repository, a query may find zero rows, find exactly one row, or return multiple rows unexpectedly. How Spring Data JPA represents each case depends on the method's return type. If a method expects a single unique result but the database returns multiple rows, the application can receive IncorrectResultSizeDataAccessException.

Understanding the result contract helps separate "not found" from "non-unique data", choose the right return type, avoid catching exceptions improperly, and design deterministic queries. This lesson explains the behavior of Optional, single entities, collections, Page/Slice, exception handling, causes of duplicate query results, and testing edge cases.

## 1. Three query result cardinality cases

A typical read query can produce three result counts:

| Result count | Meaning | How the application should handle it |
|---:|---|---|
| 0 | No matching rows | Return empty/null per return type or handle "not found" business logic |
| 1 | Exactly one row | Return entity, populated Optional, or a scalar value |
| More than 1 | Multiple matching rows | Return a collection or fail if the method requires a single unique result |

The repository return type is part of the contract. If business rules allow multiple results, use List, Page, or Slice. If business rules require uniqueness, use Optional or a single entity and guarantee the query condition is genuinely unique.

Do not pick Optional just to make code look concise. Optional<T> expresses 0 or 1 result; it does not mean "pick an arbitrary element among many".

## 2. Empty results with Optional<T>

Optional<T> is appropriate when a query may find no record and at most one record should exist.

Example:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);
}
~~~

Usage:

~~~java
Optional<Customer> result =
        repository.findByEmail("missing@example.com");

if (result.isPresent()) {
    Customer customer = result.get();
    System.out.println(customer.getDisplayName());
} else {
    System.out.println("Customer not found");
}
~~~

Output if no record matches:

~~~text
Customer not found
~~~

You can use ifPresent(), map(), orElse(), or orElseThrow():

~~~java
Customer customer = repository.findByEmail(email)
        .orElseThrow(() -> new CustomerNotFoundException(email));
~~~

Common usage patterns:

| Call | Meaning |
|---|---|
| isPresent() | Checks if a value is present |
| isEmpty() | Checks if no value is present |
| orElse(value) | Returns a default value if empty |
| orElseGet(supplier) | Lazily creates a default value when needed |
| orElseThrow() | Throws an exception if empty |
| map(function) | Transforms the value if present |
| ifPresent(consumer) | Executes an action if present |

Note: Optional cannot contain null. If a query returns a null value or no rows, mapping to Optional can yield Optional.empty(). If you need to distinguish "no row" from "row exists but selected column is null", query an entity/DTO containing the primary key or a non-null field to preserve the distinction.

## 3. Empty results with a single entity or nullable type

A repository can declare a single entity return type:

~~~java
Customer findByEmail(String email);
~~~

For a query with no results, Spring Data JPA normally returns null for a single reference type. If more than one row matches, the method cannot validly choose one and will raise a result size error.

A nullable return type can fit legacy Java code, though Optional usually expresses intent more clearly:

~~~java
Optional<Customer> findByEmail(String email);
~~~

If using a nullable single return type, document nullability and check for null before accessing properties. Do not let null propagate deep into services and cause NullPointerException.

Example:

~~~java
Customer customer = repository.findByEmail(email);

if (customer == null) {
    throw new CustomerNotFoundException(email);
}

return customer.getDisplayName();
~~~

Do not confuse an empty query result with a null property value on an entity. An entity can exist while one of its nullable columns is null.

## 4. Collections return empty lists

If a query can return multiple records, use List<T>, Set<T>, or an appropriate collection.

~~~java
List<Customer> findByDisplayNameContainingIgnoreCase(String keyword);
~~~

When no rows match, the repository returns an empty collection, normally never null:

~~~java
List<Customer> customers =
        repository.findByDisplayNameContainingIgnoreCase("unknown");

if (customers.isEmpty()) {
    System.out.println("No matching customers");
}
~~~

No null check is needed before calling isEmpty() on standard collection results.

Collection types:

| Return type | No results | Multiple results |
|---|---|---|
| List<T> | Empty List | Preserves query result order if ORDER BY is present |
| Set<T> | Empty Set | Removes duplicates per equals/hashCode |
| Collection<T> | Empty Collection | Contains matching elements |
| Iterable<T> | Empty Iterable | Allows iterating over elements |

If result order matters, use List and declare ORDER BY. Never rely on arbitrary database ordering.

## 5. Page, Slice, and Stream when there are no results

Pagination return types also have clear contracts.

~~~java
Page<Customer> findByDisplayNameContaining(
        String keyword,
        Pageable pageable);

Slice<Customer> findByActiveTrue(Pageable pageable);
~~~

- Page has empty content when no records match. totalElements is 0 and totalPages is 0.
- Slice has empty content and hasNext() is false when no more data exists.
- Stream<T> may contain zero elements; close the stream after use and generally keep a transaction active while reading.

Page example:

~~~java
Page<Customer> page = repository.findByDisplayNameContaining(
        "unknown",
        PageRequest.of(0, 20)
);

if (page.isEmpty()) {
    System.out.println("No customers on this page");
}

System.out.println(page.getTotalElements());
~~~

With an empty result, the output will be:

~~~text
No customers on this page
0
~~~

Page may execute an extra COUNT query to compute total elements. Slice only needs to know whether a next element exists. When total record counts are unneeded, Slice can reduce cost.

Stream example:

~~~java
@Transactional(readOnly = true)
public void printCustomers() {
    try (Stream<Customer> customers = repository.streamAllByActiveTrue()) {
        customers.forEach(customer ->
                System.out.println(customer.getDisplayName()));
    }
}
~~~

Repository streams must be closed to release resources; fetching behavior may depend on the provider/driver. Never return a Stream out of an ended transaction.

## 6. findById(), getReferenceById(), and missing results

These two methods have different semantics:

~~~java
Optional<Customer> customer = repository.findById(id);
~~~

findById() queries by primary key and returns Optional.empty() if the entity does not exist.

~~~java
Customer customer = repository.getReferenceById(id);
~~~

getReferenceById() typically returns a reference/proxy without necessarily loading data immediately. If the key does not exist, EntityNotFoundException may only surface when the proxy is accessed. Therefore, do not use getReferenceById() as an existence check.

When you need to check existence, use findById() or existsById():

~~~java
if (!repository.existsById(id)) {
    throw new CustomerNotFoundException(id);
}
~~~

If you need entity data immediately, findById() is usually the clearer choice.

## 7. What is IncorrectResultSizeDataAccessException?

IncorrectResultSizeDataAccessException belongs to Spring's DAO exception hierarchy. It indicates that a query operation expected a specific number of results, yet actually received a different count.

In Spring Data JPA, the typical case is a method with a single or Optional return type whose JPQL/derived query returns more than one row. The JPA provider may raise NonUniqueResultException; Spring translates the corresponding persistence error into its DataAccessException hierarchy, typically IncorrectResultSizeDataAccessException.

Repository example:

~~~java
Optional<Customer> findByDisplayName(String displayName);
~~~

If the database contains two customers with displayName "Alex", calling:

~~~java
repository.findByDisplayName("Alex");
~~~

can throw:

~~~text
org.springframework.dao.IncorrectResultSizeDataAccessException
~~~

This is a data/query contract violation: the method asked for at most one result, but the condition is not actually unique. It is not synonymous with "not found".

## 8. Distinguishing result-count errors

| Situation | Typical exception or result | Meaning |
|---|---|---|
| Repository Optional finds no row | Optional.empty() | Not found |
| Repository single entity finds no row | null under nullable contract | Not found |
| JPA EntityManager.getSingleResult() finds no row | NoResultException | Not found when using JPA API directly |
| Single-result query returns multiple rows | IncorrectResultSizeDataAccessException in Spring layer | Violates single-result contract |
| JPA getSingleResult() returns multiple rows | NonUniqueResultException | Multiple results exist |
| getReferenceById() points to nonexistent ID | EntityNotFoundException may occur when proxy is accessed | Invalid reference |
| Insert violates unique constraint | DataIntegrityViolationException or equivalent | Data constraint violation on write |

Spring Data repositories handle zero-row results for Optional/single entities according to the return type. When using EntityManager directly, getSingleResult() throws NoResultException on zero rows. Do not assume direct JPA API behavior applies identically to repository methods.

## 9. Why queries return multiple results unexpectedly

Several reasons explain why a supposedly unique method returns multiple rows:

1. The search criterion is not a unique key. For example, displayName can duplicate.
2. Missing database unique constraint even though code assumes email is unique.
3. Legacy data already contained duplicates before a constraint was added.
4. A JOIN to a collection produces multiple rows for the same entity.
5. Query lacks DISTINCT when joining associations.
6. A derived query filters only by a non-unique property.
7. The method returns Optional<T> even though business rules allow multiple records.

Collection join example:

~~~java
@Query("""
       select c
       from Customer c
       join c.orders o
       where o.status = :status
       """)
List<Customer> findCustomersWithOrderStatus(
        @Param("status") OrderStatus status);
~~~

One Customer can have multiple Orders in the same status, so the join can emit multiple rows for the same customer. If you want each Customer to appear once, use DISTINCT:

~~~java
@Query("""
       select distinct c
       from Customer c
       join c.orders o
       where o.status = :status
       """)
List<Customer> findDistinctCustomersWithOrderStatus(
        @Param("status") OrderStatus status);
~~~

If the query is declared to return Optional<Customer>, DISTINCT eliminates duplicates of the same entity, yet multiple distinct Customers may still match. DISTINCT does not turn a multi-customer query into a unique one.

## 10. Enforcing uniqueness in the database

If business rules dictate that email is unique, protect it at both layers:

- Java/domain: normalize and validate format.
- Database: unique constraint or unique index.

Entity example:

~~~java
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

    @Column(nullable = false, length = 200)
    private String email;

    @Column(nullable = false, length = 150)
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

Mapping annotations document the constraint, but production schemas should be managed via Flyway/Liquibase migrations and verified to enforce the constraint.

Do not rely solely on checking before insert:

~~~java
if (!repository.existsByEmail(email)) {
    repository.save(new Customer(email, name));
}
~~~

This snippet does not guarantee uniqueness under concurrent requests: two requests can both see that email does not exist yet and both insert. A database unique constraint is the final safeguard. The application must catch constraint violations and respond appropriately.

If emails are case-insensitive, define normalization/collation rules. A standard column unique constraint may still allow both Alex@example.com and alex@example.com depending on the database/collation. Store normalized values or create a database-appropriate expression unique index.

## 11. Choosing the right return type for business intent

| Need | Suitable return type / method |
|---|---|
| Find by primary key, may not exist | Optional<T> with findById() |
| Find by business key guaranteed unique | Optional<T> |
| Find by name that can duplicate | List<T> |
| Only need to know if a record exists | boolean with existsBy... |
| Only need the count | long with countBy... |
| Pick one result by an explicit rule | Optional<T> with First/Top and ORDER BY |
| Load data in pages | Page<T> or Slice<T> |
| Fetch only a few fields | DTO/interface projection |

Repository example:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    List<Customer> findAllByDisplayName(String displayName);

    Optional<Customer> findFirstByDisplayNameOrderByIdAsc(
            String displayName);

    boolean existsByEmail(String email);

    long countByDisplayName(String displayName);

    Page<Customer> findByDisplayNameContainingIgnoreCase(
            String keyword,
            Pageable pageable);
}
~~~

Do not use findFirstBy... merely to hide unexpected duplicates. Only use First/Top when business rules genuinely permit picking one element by deterministic order, such as the newest record or the record with the lowest ID.

## 12. First and Top: intentional result limiting

Spring Data supports First and Top in derived query names:

~~~java
Optional<Customer> findFirstByDisplayNameOrderByIdAsc(
        String displayName);

List<Customer> findTop5ByActiveTrueOrderByCreatedAtDesc();
~~~

- First/Top limits the number of rows the query returns.
- When no results match, Optional is empty or List is empty depending on the return type.
- When multiple rows match, the database returns only up to the limit.
- Always add ORDER BY if you need to know which record is picked.

Without ORDER BY, the database does not guarantee row order. Therefore, findFirstByDisplayName("Alex") without a sort rule cannot guarantee returning the same customer consistently.

Top/First suits use cases like "get the latest record", "get top 5 featured products by score", or "pick one record by priority". It does not replace a unique constraint when data must be unique.

## 13. Using existsBy and countBy instead of loading entities

If you only need to check existence, avoid loading the entire entity:

~~~java
boolean existsByEmail(String email);
~~~

If you only need a count:

~~~java
long countByDisplayName(String displayName);
~~~

These queries express intent directly and are typically more efficient than loading a list and calling size(). On large datasets, avoid:

~~~java
List<Customer> customers = repository.findByActiveTrue();
long count = customers.size();
~~~

Use countByActiveTrue() if you only need the count.

However, existsByEmail() does not replace a unique constraint during concurrent writes. It only reflects state at the moment of the query.

## 14. Scalar queries, projections, and null values

An empty result for an entity query differs from a query selecting a single nullable column.

Example:

~~~java
@Query("select c.displayName from Customer c where c.email = :email")
Optional<String> findDisplayNameByEmail(@Param("email") String email);
~~~

If no Customer matches, Optional will be empty. If a Customer exists but displayName is null, the scalar value can also map to null/Optional.empty(). Thus, Optional<String> may not distinguish these two cases.

If you need to distinguish them, return a DTO or projection containing both the ID and the nullable field:

~~~java
public record CustomerNameView(Long id, String displayName) {
}
~~~

~~~java
@Query("""
       select new com.example.customer.CustomerNameView(c.id, c.displayName)
       from Customer c
       where c.email = :email
       """)
Optional<CustomerNameView> findNameViewByEmail(
        @Param("email") String email);
~~~

A non-null ID indicates the entity exists even when displayName is null.

## 15. Aggregate queries when no rows match

Aggregate functions follow specific rules:

| Function | When dataset has no matching values |
|---|---|
| COUNT | Returns 0 |
| SUM | Usually returns null when there are no values to sum |
| AVG | Usually returns null when there are no values to average |
| MIN | Returns null when no values exist |
| MAX | Returns null when no values exist |

Example:

~~~java
@Query("select count(c) from Customer c where c.active = true")
long countActiveCustomers();

@Query("select coalesce(sum(o.total), 0) from PurchaseOrder o")
BigDecimal sumOrderTotalOrZero();
~~~

COUNT does not need COALESCE to turn an empty result into 0. SUM may need COALESCE if the business contract wants 0 instead of null.

When a query includes GROUP BY and no groups match, the result is an empty collection; do not confuse this with an aggregate query without GROUP BY, which can return one row containing null.

## 16. Handling errors in services and APIs

Do not catch IncorrectResultSizeDataAccessException and return Optional.empty() or HTTP 404. This exception signals that a query expecting a single unique result received multiple rows; that is a data integrity or query design bug.

Service example:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;

    public CustomerService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Customer getByEmail(String email) {
        return repository.findByEmail(email)
                .orElseThrow(() -> new CustomerNotFoundException(email));
    }
}
~~~

If findByEmail returns Optional.empty(), the service can throw CustomerNotFoundException and the API can return HTTP 404 per application conventions.

If the repository throws IncorrectResultSizeDataAccessException, let the failure be logged and handled as a data/query error. In production, use @ControllerAdvice to map it to an appropriate generic error response, log it, and alert operations. Never expose SQL details or sensitive data to clients.

Do not use broad try/catch blocks to swallow all DataAccessExceptions. That can hide connection failures, constraint errors, mapping bugs, and query faults.

## 17. Complete entity, repository, and test example

Customer entity:

~~~java
package com.example.customer;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.GeneratedValue;
import jakarta.persistence.GenerationType;
import jakarta.persistence.Id;
import jakarta.persistence.Table;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, unique = true, length = 200)
    private String email;

    @Column(nullable = false, length = 150)
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

Repository:

~~~java
package com.example.customer;

import java.util.List;
import java.util.Optional;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long> {

    Optional<Customer> findByEmail(String email);

    Optional<Customer> findByDisplayName(String displayName);

    List<Customer> findAllByDisplayName(String displayName);

    Optional<Customer> findFirstByDisplayNameOrderByIdAsc(
            String displayName);

    boolean existsByEmail(String email);
}
~~~

Note: email is unique per the entity mapping, whereas displayName is not unique. Thus findByEmail suits Optional; findByDisplayName only suits Optional if actual data is guaranteed unique. The next test deliberately inserts two matching displayNames to demonstrate the failure.

Tests:

~~~java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.dao.IncorrectResultSizeDataAccessException;

@DataJpaTest
class CustomerRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void optionalIsEmptyWhenNoCustomerMatches() {
        assertThat(repository.findByEmail("missing@example.com"))
                .isEmpty();
    }

    @Test
    void collectionIsEmptyWhenNoCustomerMatches() {
        assertThat(repository.findAllByDisplayName("Unknown"))
                .isEmpty();
    }

    @Test
    void singleResultMethodFailsWhenMultipleRowsMatch() {
        repository.saveAndFlush(
                new Customer("alex1@example.com", "Alex"));
        repository.saveAndFlush(
                new Customer("alex2@example.com", "Alex"));

        assertThatThrownBy(() -> repository.findByDisplayName("Alex"))
                .isInstanceOf(IncorrectResultSizeDataAccessException.class);
    }

    @Test
    void firstQueryUsesExplicitOrdering() {
        repository.saveAndFlush(
                new Customer("alex1@example.com", "Alex"));
        repository.saveAndFlush(
                new Customer("alex2@example.com", "Alex"));

        var result = repository.findFirstByDisplayNameOrderByIdAsc("Alex");

        assertThat(result).isPresent();
        assertThat(result.orElseThrow().getEmail())
                .isEqualTo("alex1@example.com");
    }
}
~~~

The first test confirms Optional is empty when not found. The second confirms an empty collection. The third proves a method requiring a unique result fails when multiple rows match. The last shows First is only safe with explicit ordering.

@DataJpaTest usually runs inside a transaction and rolls back after each test. saveAndFlush() forces INSERT execution so constraints and queries are verified immediately. To verify unique constraint behavior on a production database, run integration tests against that engine.

## 18. Common errors and fixes

| Symptom | Cause | Fix |
|---|---|---|
| Optional.empty() when application expects data | Wrong search condition or data does not exist | Check parameters, data normalization, and business contract |
| IncorrectResultSizeDataAccessException | Single-result method returned multiple rows | Use List or enforce unique query/constraint |
| Optional used for potentially duplicate name | Return type does not reflect cardinality | Use List, or First/Top with ORDER BY per business rules |
| Using getReferenceById to check existence | Reference may not have loaded data yet | Use findById or existsById |
| Join query returns duplicate entities | An entity has multiple matching association rows | Use DISTINCT if the goal is unique entities |
| Used DISTINCT yet multiple entities still returned | Multiple distinct entities satisfy the condition | Choose List or design a unique condition |
| Catching exception and returning empty | Hides duplicate data | Fix query/constraint and log the error |
| existsBy before insert still produces duplicates | Two concurrent requests both check at once | Use a unique constraint and handle write failures |
| Scalar Optional cannot tell row-null from no-row | Selected column can be null | Return a DTO with ID or include a non-null field |
| Empty Page has unexpected total | Count query or filter differs from content query | Verify count query and predicates |
| First result changes between runs | No deterministic ORDER BY | Add a stable sort order |

## 19. Self-assessment checklist

- [ ] Can distinguish 0, 1, and multiple results.
- [ ] Chooses Optional<T> for at-most-one queries.
- [ ] Understands single entities may return null when no result exists.
- [ ] Uses List/Page/Slice for multi-result queries.
- [ ] Knows an empty Page has totalElements = 0 and an empty Slice has no next page.
- [ ] Distinguishes findById() from getReferenceById().
- [ ] Can explain IncorrectResultSizeDataAccessException.
- [ ] Distinguishes "not found" errors from "multiple results" errors.
- [ ] Identifies duplicate causes from non-unique conditions or collection joins.
- [ ] Uses DISTINCT appropriately and understands it does not guarantee a single entity.
- [ ] Uses unique constraints to protect business keys.
- [ ] Does not rely on existsBy to prevent race conditions during inserts.
- [ ] Uses First/Top with deterministic ORDER BY when business logic allows picking one row.
- [ ] Distinguishes empty aggregate results from empty collections.
- [ ] Tests 0, 1, and multiple results using @DataJpaTest.
- [ ] Does not convert IncorrectResultSizeDataAccessException into "not found".

## 20. Conclusion

Empty results are a normal query outcome and must be expressed according to the return type: Optional.empty(), null under a nullable contract, an empty collection, or an empty Page/Slice. When a query requires a single unique result yet the database returns multiple rows, Spring Data JPA can throw IncorrectResultSizeDataAccessException.

Choose return types to match actual cardinality, enforce database unique constraints for unique data, verify whether JOINs produce duplicates, and only use First/Top with explicit ordering. Handling these cases properly helps services cleanly separate "not found" from "inconsistent data", making APIs and systems much more predictable.