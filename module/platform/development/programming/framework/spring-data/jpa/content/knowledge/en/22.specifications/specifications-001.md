# Why Specification Is Needed for Dynamic Combined Filters

## Objectives

After this lesson, you can:

- Explain which kinds of searches Query by Example (QBE) fits and where its limitations lie.
- Recognize when dynamic filters require AND/OR expressions, value ranges, IS NULL, IN, joins, or subqueries.
- Use Spring Data JPA Specification to build independent predicates and combine them.
- Design a filter object that distinguishes between not filtering, filtering for null, and filtering by value.
- Combine Specification with JpaSpecificationExecutor, pagination, and sorting.
- Avoid duplicate rows, incorrect counts, inappropriate fetch joins, and client-controlled filter criteria.
- Test filter combinations and choose the right tool among QBE, Specification, and @Query.

## 1. The Dynamic Combined Filter Problem

A customer search screen may allow users to enter multiple criteria:

- Name contains a text snippet.
- Email equals a value or email is null.
- Status belongs to an enum.
- Creation date falls within a range.
- Only return customers that are enabled or disabled.
- Has at least one paid order.

Each criterion can be provided or omitted independently. A user might filter only by name, or combine name with status, creation date, and order existence.

If there are six independent filters, the number of input combinations is already very large. Writing a repository method for each combination creates many nearly identical methods:

~~~java
findByNameContaining(...);
findByStatus(...);
findByNameContainingAndStatus(...);
findByStatusAndCreatedAtBetween(...);
findByNameContainingAndStatusAndEnabled(...);
// And many more combinations...
~~~

Another approach is to write a long JPQL query with multiple conditions such as:

~~~jpql
where (:name is null or lower(c.name) like ...)
  and (:status is null or c.status = :status)
  and (:enabled is null or c.enabled = :enabled)
~~~

This approach works for simple filters, but quickly becomes hard to read when there are OR groups, explicit null conditions, optional date ranges, joins, subqueries, or logic that only applies when a filter group is enabled.

Spring Data JPA Specification solves this problem by representing each condition as a reusable predicate, then combining the predicates according to the needs of the request.

## 2. What Is Query by Example Suitable For?

Query by Example (QBE) uses an object as a probe. Non-null or matched properties in the probe are matched according to an ExampleMatcher.

For example, suppose the Customer entity has the properties name, email, and status. You can create a probe:

~~~java
Customer probe = new Customer(
    "an",
    null,
    CustomerStatus.ACTIVE,
    null,
    null
);

ExampleMatcher matcher = ExampleMatcher.matchingAll()
    .withIgnoreNullValues()
    .withMatcher("name", rule -> rule.contains().ignoreCase());

Example<Customer> example = Example.of(probe, matcher);

List<Customer> customers = repository.findAll(example);
~~~

This snippet assumes Customer has a constructor accepting name, email, status, createdAt, and enabled in that order, as shown in the entity illustrated later.

QBE is suitable when:

- Conditions mainly match property values.
- Null in the probe means ignoring that property.
- Logic is AND between properties, or simple OR using matchingAny().
- String matching uses exact, starts with, ends with, or contains.
- No complex business expressions or subqueries are required.

### Does QBE Support OR?

Yes. matchingAny() requires matching any of the probe properties. However, this is a simple OR across the properties declared in the probe; it does not freely express nested groups such as:

~~~text
(status = ACTIVE AND enabled = true)
OR
(status = VIP AND createdAt >= from)
~~~

This is an important distinction: QBE can handle some basic OR conditions, but it is not a general-purpose logical expression builder.

## 3. When Is QBE No Longer Enough?

QBE has limitations that make it unsuitable for many business search screens:

- Cannot directly express greater-than, less-than, or BETWEEN range comparisons in a general way.
- Cannot express arbitrary AND/OR groups with logical parentheses.
- Does not provide a general way to create joins and subqueries as needed.
- Not suitable for conditions requiring database functions, arithmetic, or complex Criteria expressions.
- Does not support matching collections and maps in the usual probe style.
- Difficult to clearly distinguish between an omitted filter and a filter sent with a null value if relying solely on a nullable property.

For example, the following requirement needs several types of predicates:

~~~text
name contains "an"
AND status IN (ACTIVE, VIP)
AND createdAt >= 2026-01-01
AND (enabled = true OR status = VIP)
AND EXISTS (a PAID order)
~~~

This is no longer simple field matching in a probe. Specification is more appropriate because it lets you use the Criteria API to create like, in, greaterThanOrEqualTo, or, exists, and joins.

## 4. What Is Specification?

Specification<T> is a Spring Data JPA abstraction used to describe a query condition for entity T. It is built on the JPA Criteria API and typically returns a Predicate.

A Specification has three input parameters:

- Root<T>: the root entity being queried.
- CriteriaQuery<?>: the query object, usable for subqueries or configuring distinct.
- CriteriaBuilder: the factory for building predicates and expressions such as equal, like, between, isNull, and, or.

A small example:

~~~java
Specification<Customer> activeCustomers =
    (root, query, cb) -> cb.isTrue(root.get("enabled"));
~~~

This Specification describes the condition enabled = true. It does not execute the query yet. The repository combines this Specification with other conditions and generates SQL upon execution.

### Specifications Are Composable

Spring Data provides composition operations:

- and(other): both conditions must hold.
- or(other): at least one condition holds.
- not(spec): negates a Specification.

For example:

~~~java
Specification<Customer> spec =
    activeCustomers.and(hasStatus(CustomerStatus.ACTIVE));
~~~

Small predicates can be placed in separate methods, named after business concepts, and reused across multiple use cases.

## 5. Declaring the Entity and Filter Object

The example below uses Java 17+, Spring Data JPA, and Jakarta Persistence. The Customer entity has fields for searching.

~~~java
package com.example.customer;

import java.time.LocalDateTime;

import jakarta.persistence.Column;
import jakarta.persistence.Entity;
import jakarta.persistence.EnumType;
import jakarta.persistence.Enumerated;
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

    @Column(nullable = false, length = 120)
    private String name;

    @Column(length = 254)
    private String email;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private CustomerStatus status;

    @Column(nullable = false)
    private LocalDateTime createdAt;

    @Column(nullable = false)
    private Boolean enabled;

    protected Customer() {
    }

    public Customer(
            String name,
            String email,
            CustomerStatus status,
            LocalDateTime createdAt,
            Boolean enabled) {
        this.name = name;
        this.email = email;
        this.status = status;
        this.createdAt = createdAt;
        this.enabled = enabled;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }

    public String getEmail() {
        return email;
    }

    public CustomerStatus getStatus() {
        return status;
    }

    public LocalDateTime getCreatedAt() {
        return createdAt;
    }

    public Boolean getEnabled() {
        return enabled;
    }
}
~~~

Enum:

~~~java
package com.example.customer;

public enum CustomerStatus {
    ACTIVE,
    INACTIVE,
    VIP
}
~~~

Filter object:

~~~java
package com.example.customer;

import java.time.LocalDateTime;

public record CustomerFilter(
        String name,
        CustomerStatus status,
        LocalDateTime createdFrom,
        LocalDateTime createdTo,
        Boolean enabled,
        String email,
        boolean emailIsNull) {

    public CustomerFilter {
        if (emailIsNull && email != null) {
            throw new IllegalArgumentException(
                "email and emailIsNull cannot both be set"
            );
        }

        if (email != null && email.isBlank()) {
            throw new IllegalArgumentException(
                "email must not be blank"
            );
        }

        if (createdFrom != null
                && createdTo != null
                && createdFrom.isAfter(createdTo)) {
            throw new IllegalArgumentException(
                "createdFrom must not be after createdTo"
            );
        }
    }
}
~~~

In this filter:

- null for name, status, createdFrom, createdTo, or enabled means skipping the corresponding condition.
- enabled = false is still a valid filter; because Boolean is used, null and false are distinguished.
- email = null with emailIsNull = false means skipping the email filter.
- email = null with emailIsNull = true means searching for email IS NULL.
- email having a value means searching for equality with that value.

A good filter object clarifies input semantics before building the query. Do not leave Specification to guess whether null means skipping the filter or searching for a null column.

## 6. Writing Small Specifications

Create a class holding reusable predicates:

~~~java
package com.example.customer;

import java.time.LocalDateTime;
import java.util.Locale;

import org.springframework.data.jpa.domain.Specification;

public final class CustomerSpecifications {

    private CustomerSpecifications() {
    }

    public static Specification<Customer> unrestricted() {
        return (root, query, cb) -> cb.conjunction();
    }

    public static Specification<Customer> nameContains(String name) {
        if (name == null || name.isBlank()) {
            return unrestricted();
        }

        String pattern = "%"
            + name.trim().toLowerCase(Locale.ROOT)
            + "%";

        return (root, query, cb) ->
            cb.like(cb.lower(root.<String>get("name")), pattern);
    }

    public static Specification<Customer> hasStatus(
            CustomerStatus status) {
        if (status == null) {
            return unrestricted();
        }

        return (root, query, cb) ->
            cb.equal(root.get("status"), status);
    }

    public static Specification<Customer> enabled(Boolean enabled) {
        if (enabled == null) {
            return unrestricted();
        }

        return (root, query, cb) ->
            cb.equal(root.<Boolean>get("enabled"), enabled);
    }

    public static Specification<Customer> createdFrom(
            LocalDateTime from) {
        if (from == null) {
            return unrestricted();
        }

        return (root, query, cb) ->
            cb.greaterThanOrEqualTo(
                root.<LocalDateTime>get("createdAt"),
                from
            );
    }

    public static Specification<Customer> createdTo(
            LocalDateTime to) {
        if (to == null) {
            return unrestricted();
        }

        return (root, query, cb) ->
            cb.lessThanOrEqualTo(
                root.<LocalDateTime>get("createdAt"),
                to
            );
    }

    public static Specification<Customer> emailMatches(
            String email,
            boolean emailIsNull) {
        if (emailIsNull) {
            return (root, query, cb) ->
                cb.isNull(root.get("email"));
        }

        if (email == null) {
            return unrestricted();
        }

        String normalized = email.trim().toLowerCase(Locale.ROOT);

        return (root, query, cb) ->
            cb.equal(
                cb.lower(root.<String>get("email")),
                normalized
            );
    }
}
~~~

Key points to understand:

- unrestricted() returns an always-true predicate using cb.conjunction(). When combined with AND, this condition does not restrict results.
- Each method handles the case where the filter is not provided.
- enabled(Boolean) does not use if (!enabled), because that would also skip the false value.
- The time range is split into two predicates to support having only a lower bound, only an upper bound, or both.
- emailMatches() clearly distinguishes skipping the filter, searching for null, and searching by value.

In the name contains example, `%` and `_` characters entered by the user are treated as LIKE wildcards. If the business requirement calls for matching them as literal characters, escape the pattern with the Criteria API escape character or normalize input according to documented rules.

Using root.get("name") relies on String property names. For large projects, you can use the JPA static metamodel (for example Customer_.name) to catch property rename errors at compile time.

## 7. Combining Filters in the Service

The repository needs to extend JpaSpecificationExecutor:

~~~java
package com.example.customer;

import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
~~~

The service composes the Specifications:

~~~java
package com.example.customer;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.domain.Specification;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class CustomerSearchService {

    private final CustomerRepository repository;

    public CustomerSearchService(CustomerRepository repository) {
        this.repository = repository;
    }

    @Transactional(readOnly = true)
    public Page<Customer> search(
            CustomerFilter filter,
            Pageable pageable) {

        Specification<Customer> spec =
            CustomerSpecifications.unrestricted()
                .and(CustomerSpecifications.nameContains(filter.name()))
                .and(CustomerSpecifications.hasStatus(filter.status()))
                .and(CustomerSpecifications.createdFrom(filter.createdFrom()))
                .and(CustomerSpecifications.createdTo(filter.createdTo()))
                .and(CustomerSpecifications.enabled(filter.enabled()))
                .and(CustomerSpecifications.emailMatches(
                    filter.email(),
                    filter.emailIsNull()
                ));

        return repository.findAll(spec, pageable);
    }
}
~~~

The repository builds the query from the final Specification. The service does not need a separate method for every filter combination.

Invocation example:

~~~java
CustomerFilter filter = new CustomerFilter(
    "an",
    CustomerStatus.ACTIVE,
    LocalDateTime.of(2026, 1, 1, 0, 0),
    null,
    true,
    null,
    false
);

Pageable pageable = PageRequest.of(
    0,
    20,
    Sort.by(
        Sort.Order.asc("name"),
        Sort.Order.asc("id")
    )
);

Page<Customer> result = searchService.search(filter, pageable);
~~~

This example searches for customers whose name contains "an", with status ACTIVE, enabled, and created from January 1, 2026; with no upper bound or email restriction. It sorts by name and then id so pagination order is deterministic.

Page<T> typically requires a count query to calculate the total number of elements. If the UI only needs to know whether more results exist without the total count, consider a Slice or a window-based query design supported by your API/version.

## 8. Expressing OR Groups with Logical Parentheses

A major advantage of Specification is that you can build a predicate group and combine that group with other conditions.

Suppose the requirement is:

~~~text
(name contains "an")
AND
(status = ACTIVE OR status = VIP)
AND
(enabled = true)
~~~

Create the OR group:

~~~java
public static Specification<Customer> activeOrVip() {
    return (root, query, cb) ->
        cb.or(
            cb.equal(root.get("status"), CustomerStatus.ACTIVE),
            cb.equal(root.get("status"), CustomerStatus.VIP)
        );
}
~~~

Combine them:

~~~java
Specification<Customer> spec =
    CustomerSpecifications.nameContains("an")
        .and(CustomerSpecifications.activeOrVip())
        .and(CustomerSpecifications.enabled(true));
~~~

Equivalent result:

~~~sql
WHERE lower(name) LIKE '%an%'
  AND (status = 'ACTIVE' OR status = 'VIP')
  AND enabled = true
~~~

The OR group lives inside its own predicate, so when joined with AND, the logical parentheses are preserved properly. This is something QBE cannot flexibly express with a simple probe.

## 9. IN, NOT IN, and Filter Lists

Specification can express membership in a set of values:

~~~java
public static Specification<Customer> statusIn(
        Collection<CustomerStatus> statuses) {
    if (statuses == null) {
        return unrestricted();
    }

    if (statuses.isEmpty()) {
        return (root, query, cb) -> cb.disjunction();
    }

    return (root, query, cb) ->
        root.get("status").in(statuses);
}
~~~

This example specifies:

- null collection: do not apply the filter.
- Empty collection: no records match.
- Non-empty collection: only return records whose status is in the set.

Do not assume an empty collection means skipping the filter. Those two semantics differ and must be clearly defined by the API contract.

You can create notIn similarly. If the collection contains null, SQL three-valued logic can make NOT IN produce unexpected results; validate and reject nulls from the list before creating the predicate.

## 10. Joins and Subqueries

Specification is based on the Criteria API, so it can join associations or create subqueries.

Suppose the PurchaseOrder entity has a ManyToOne property customer and status of type OrderStatus. To find Customers with at least one PAID order, you can use EXISTS:

~~~java
public static Specification<Customer> hasPaidOrder() {
    return (root, query, cb) -> {
        Subquery<Long> subquery = query.subquery(Long.class);
        Root<PurchaseOrder> order =
            subquery.from(PurchaseOrder.class);

        subquery.select(order.<Long>get("id"));
        subquery.where(
            cb.equal(order.get("customer"), root),
            cb.equal(order.get("status"), OrderStatus.PAID)
        );

        return cb.exists(subquery);
    };
}
~~~

This fragment depends on the application's PurchaseOrder entity and OrderStatus enum. An EXISTS subquery accurately expresses "has at least one PAID order" without multiplying Customer rows by the number of orders.

If using a collection join:

~~~java
Join<Customer, PurchaseOrder> orders =
    root.join("orders", JoinType.INNER);

query.distinct(true);

return cb.equal(orders.get("status"), OrderStatus.PAID);
~~~

A collection join can produce multiple SQL rows for the same Customer. When the result needs each Customer once, duplicates must be handled via distinct or by considering EXISTS.

For paginated queries, collection joins can complicate the count query. Always inspect the SQL and total element count, not just the content list.

## 11. Specification with Pagination and Sorting

JpaSpecificationExecutor provides common methods:

- findAll(spec): retrieves all entities matching the condition.
- findAll(spec, sort): retrieves sorted results.
- findAll(spec, pageable): retrieves a Page.
- count(spec): counts entities matching the condition.
- exists(spec): checks if any matching entity exists.
- findOne(spec): retrieves at most one entity; if multiple results exist, the operation may throw a cardinality exception.

Example:

~~~java
Page<Customer> page =
    repository.findAll(
        spec,
        PageRequest.of(
            0,
            20,
            Sort.by(
                Sort.Order.asc("createdAt"),
                Sort.Order.asc("id")
            )
        )
    );
~~~

Adding a unique key like id at the end of the sort ensures deterministic ordering when multiple records share the same createdAt. With continuously changing data, offset pagination can still shift between requests; if deep sequential traversal is needed, consider keyset scrolling in supported Spring Data versions.

## 12. Do Not Arbitrarily Mix Fetch Joins into Specifications

A Specification is often reused for both the data query and the count query of a Page. Therefore, calling root.fetch(...) inside a shared Specification can cause issues when Spring Data generates the count query, because count queries should not fetch associations.

Several guidelines:

- Do not add collection fetch joins to every Specification just to avoid lazy loading.
- Separate filter predicates from data fetching strategies whenever possible.
- Use @EntityGraph on repository methods or a dedicated query when associations need to be loaded.
- If using a collection join for filtering, consider EXISTS to avoid row multiplication.
- Verify the count query when combining distinct, grouping, or joins.

Specification should describe reusable filter conditions. The fetch plan is a separate decision belonging to the read use case.

## 13. QBE, Specification, and @Query: Which Tool to Choose?

| Need | Suitable Tool | Reason |
|---|---|---|
| Matching multiple non-null fields with AND | QBE | Minimal code, easy-to-understand probe and matcher |
| Simple OR across probe fields | QBE matchingAny | Basic any-match support |
| Optional filters with date ranges, greater/less than, IN | Specification | Criteria API provides the right operators |
| Nested AND/OR groups | Specification | Predicates can be composed with logical grouping |
| Joins, EXISTS, conditional subqueries | Specification | Can access associations and Criteria subqueries |
| A fixed, complex, yet stable query | @Query | Explicit JPQL/SQL |
| Database-specific SQL or CTE/window functions | Native @Query/custom repository | Direct SQL syntax control |
| Very complex dynamic queries needing a type-safe DSL | Querydsl or custom Criteria | DSL suits large expressions |

Not every dynamic query needs Specification. If QBE already expresses the business logic accurately and remains readable, keep QBE. If a query is fixed and clearly named, @Query can be simpler. Specification shines when multiple optional predicates must be composed dynamically according to business rules.

## 14. Testing Specifications

Test both individual key predicates and realistic combinations through the repository against a test database.

Integration test example:

~~~java
package com.example.customer;

import static org.junit.jupiter.api.Assertions.assertEquals;

import java.time.LocalDateTime;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Sort;
import org.springframework.data.jpa.domain.Specification;

@DataJpaTest
class CustomerSpecificationTest {

    @Autowired
    CustomerRepository repository;

    @Test
    void combinesNameStatusAndEnabledFilters() {
        repository.saveAll(List.of(
            new Customer(
                "An Nguyen",
                "an@example.com",
                CustomerStatus.ACTIVE,
                LocalDateTime.of(2026, 2, 1, 10, 0),
                true
            ),
            new Customer(
                "An Tran",
                "an2@example.com",
                CustomerStatus.INACTIVE,
                LocalDateTime.of(2026, 2, 2, 10, 0),
                true
            ),
            new Customer(
                "Binh Le",
                null,
                CustomerStatus.ACTIVE,
                LocalDateTime.of(2026, 2, 3, 10, 0),
                false
            )
        ));
        repository.flush();

        Specification<Customer> spec =
            CustomerSpecifications.nameContains("an")
                .and(CustomerSpecifications.hasStatus(
                    CustomerStatus.ACTIVE
                ))
                .and(CustomerSpecifications.enabled(true));

        List<Customer> result = repository.findAll(
            spec,
            Sort.by(Sort.Order.asc("id"))
        );

        assertEquals(1, result.size());
        assertEquals("An Nguyen", result.get(0).getName());
    }
}
~~~

This test assumes Customer, CustomerStatus, CustomerSpecifications, and CustomerRepository are declared as in earlier sections, along with a compatible test database. DataJpaTest typically runs in a test transaction and rolls back after each test.

Additional tests to include:

- No filters provided: returns all records allowed by access scope.
- Boolean false: still creates a predicate and returns only false records.
- Individual lower/upper bounds and both bounds together.
- Email IS NULL and email equals a value.
- Empty IN collection and non-empty collection.
- OR groups with logical parentheses.
- EXISTS with no orders, PENDING orders, and PAID orders.
- Pagination, count query, and sorting with duplicate values.

## 15. Security and Filter Control

Never accept arbitrary property names or Criteria/SQL fragments from the client and pass them directly into the query.

For example, if the API receives sortBy=name, map it through a whitelist:

~~~java
Sort sort = switch (sortBy) {
    case "name" -> Sort.by("name").ascending();
    case "createdAt" -> Sort.by("createdAt").descending();
    default -> Sort.by("id").ascending();
};
~~~

Similarly, only allow filters that the use case exposes. Never let clients choose internal fields such as role, tenantId, approvalState, or audit fields if they are not authorized to alter query scope.

Specification also does not replace authorization. Tenant, ownership, or access-control conditions must be enforced at the service/security layer so every request is properly scoped.

## 16. Common Pitfalls

| Symptom | Cause | Solution |
|---|---|---|
| A false filter is ignored | Checking boolean truthiness instead of null | Use Boolean and only skip when null |
| Cannot distinguish skipping filter from IS NULL | Using one nullable parameter for two meanings | Use a presence flag or tri-state filter |
| QBE cannot express date ranges | QBE focuses on probe matching, not general relational operators | Use Specification |
| QBE OR returns overly broad results | matchingAny applies simple OR across probe properties | Use Specification predicate groups |
| Query returns duplicate Customers | Collection join multiplies rows | Use EXISTS or intentional distinct |
| Page total is incorrect | Count query counts joined rows instead of root entities | Verify count semantics, use EXISTS/count distinct |
| Count query fails after adding fetch | Specification applies fetch join in the count query too | Separate fetch plan from predicates |
| LIKE treats % as a wildcard | User-supplied pattern characters are not escaped | Escape pattern when literal matching is needed |
| Specification is hard to maintain | One method contains all filter logic | Split predicates by attribute/business rule |
| Client filters on internal fields | Accepting raw property names or sort without a whitelist | Map input through an allowlist |
| Tests only check one combination | Null, false, empty, and OR states are untested | Write tests for each key state and combination |

## Selection Workflow

1. Determine whether filters are simple field matches or involve complex operators and logical groups.
2. Use QBE when a probe and matcher express the requirement accurately.
3. Use Specification when optional predicates, ranges, IN, null, AND/OR groups, joins, or subqueries are needed.
4. Use @Query for fixed queries where explicit JPQL/SQL is easier to read.
5. Define the semantics of null, false, blank strings, and empty collections in the filter object.
6. Compose small predicates in the service/use case instead of creating one monolithic Specification.
7. Check for duplicate rows, count query behavior, fetch plan, and indexes.
8. Whitelist sort/filter inputs and ensure authorization is enforced.
9. Integration-test representative filter combinations and edge cases.

## Pre-Merge Checklist

- [ ] QBE was considered and is only used when its matching semantics fully satisfy the requirements.
- [ ] Specification only adds predicates when the corresponding filter is provided.
- [ ] Boolean false is not confused with an omitted filter.
- [ ] Null filters have clear semantics: skip or IS NULL.
- [ ] AND/OR predicates have proper grouping.
- [ ] Range, IN, join, and EXISTS are used appropriately.
- [ ] Collection joins do not duplicate entities or distort counts.
- [ ] Fetch plans are not arbitrarily mixed into Specifications used for Page.
- [ ] Sort/filter inputs are whitelisted.
- [ ] Authorization/tenant scope is always applied.
- [ ] Integration tests cover empty filters, false, null, ranges, OR, and pagination.

## Conclusion

Query by Example fits probe-based searches and simple matchers. When filters require value ranges, IN, explicit null checks, nested AND/OR groups, joins, or subqueries, Specification provides the Criteria API to build independent predicates and compose them per use case. The filter object must clearly define the semantics of null, false, and empty collections. Keep predicates small, separate the fetch plan from filter conditions, verify count queries, and restrict which fields clients may query. This keeps dynamic search screens extensible while preserving clear, testable logic.
