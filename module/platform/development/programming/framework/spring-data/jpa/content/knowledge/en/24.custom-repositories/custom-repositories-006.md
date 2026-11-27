# Building Dynamic Queries with EntityManager in Spring Data JPA

When search criteria change depending on user input, a fixed repository method or a long derived query may no longer fit. For example, a customer search screen may allow optional filtering by name, email, status, and creation date range. Each request might supply only a few criteria; the application needs to build a query containing only the matching predicates.

JPA provides `EntityManager` to build and execute dynamic JPQL or Criteria API queries. In Spring Data JPA, you can place this query logic inside a custom repository fragment and compose it with a regular `JpaRepository`. This organization keeps complex search logic near the repository layer while supporting safe parameters, pagination, sorting, and count queries.

This lesson covers two ways to build dynamic queries: controlled JPQL assembly and the Criteria API. The focus is on binding values, whitelisting sort property names, reusing conditions for content/count queries, managing transactions, and testing results.

## 1. When Are Dynamic Queries Needed?

Derived queries suit fixed conditions, such as:

~~~java
List<Customer> findByStatusAndNameContainingIgnoreCase(
        CustomerStatus status,
        String name);
~~~

However, if a form has many optional fields, the number of method combinations grows rapidly. With four filter fields, users can submit many different combinations. You should not create a separate method for every combination.

Dynamic JPQL or the Criteria API is appropriate when:

- Some conditions are added only when the request supplies a value.
- Users can combine multiple filters.
- Sorting or projection varies by use case.
- Content and count queries must be generated from the same filter set.
- `EXISTS` conditions, joins, or complex predicates are needed.
- The query cannot be expressed readably in a method name.

You do not need `EntityManager` for every query. When conditions are simple and fixed, derived queries or `@Query` are usually shorter and easier to maintain.

## 2. Entity and Data Types Used in the Example

The example searches `Customer` by name, email, status, and creation timestamp. All code in these modeling snippets belongs to the `com.example.customer` package.

Enum:

~~~java
package com.example.customer;

public enum CustomerStatus {
    ACTIVE,
    INACTIVE,
    BLOCKED
}
~~~

Entity:

~~~java
package com.example.customer;

import java.time.Instant;

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

    @Column(nullable = false, length = 150)
    private String name;

    @Column(nullable = false, length = 200)
    private String email;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false, length = 20)
    private CustomerStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    protected Customer() {
    }

    public Customer(
            String name,
            String email,
            CustomerStatus status,
            Instant createdAt) {
        this.name = name;
        this.email = email;
        this.status = status;
        this.createdAt = createdAt;
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

    public Instant getCreatedAt() {
        return createdAt;
    }
}
~~~

This entity is used consistently across the JPQL, Criteria API, and test examples. JPQL queries reference the entity name `Customer` and Java properties such as `name`, `email`, `status`, and `createdAt`—never the physical table name `customers` or physical column names.

Search criteria DTO:

~~~java
package com.example.customer;

import java.time.Instant;

public record CustomerSearchCriteria(
        String nameContains,
        String emailEquals,
        CustomerStatus status,
        Instant createdFromInclusive,
        Instant createdBeforeExclusive
) {
}
~~~

Null fields mean the corresponding filter is not applied. The time range uses an inclusive start bound and an exclusive end bound to avoid ambiguity when data has seconds or nanoseconds. For example, a single day can be represented as the interval from the start of that day to the start of the next day.

If requests arrive from an API, validate the time range before running the query. For instance, `createdFromInclusive` must be before `createdBeforeExclusive` when both are provided.

## 3. Organizing the Custom Repository Fragment

Spring Data JPA lets you extend a repository with a custom fragment. Create an interface describing the search capability:

~~~java
package com.example.customer;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;

public interface CustomerSearchRepository {

    Page<Customer> search(
            CustomerSearchCriteria criteria,
            Pageable pageable);
}
~~~

The main repository extends both `JpaRepository` and the fragment:

~~~java
package com.example.customer;

import org.springframework.data.jpa.repository.JpaRepository;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                CustomerSearchRepository {
}
~~~

The fragment implementation follows the interface-plus-`Impl`-suffix convention:

~~~text
CustomerSearchRepository
CustomerSearchRepositoryImpl
~~~

Spring Data composes the fragment implementation into `CustomerRepository`. This keeps standard CRUD operations in `JpaRepository` while placing custom queries in a separate class.

Place the implementation in a package discovered by Spring Data repository scanning, typically the same package or an appropriate subpackage under the repository configuration. If the project changes `repositoryImplementationPostfix`, the implementation class name must follow the configured suffix.

## 4. What Is EntityManager and How to Inject It in Spring

`EntityManager` is the JPA API for managing the persistence context and executing queries. In Spring, you can inject `EntityManager` with `@PersistenceContext`:

~~~java
@PersistenceContext
private EntityManager entityManager;
~~~

Spring supplies a proxy bound to the current transaction. Do not manually create an `EntityManager` via `EntityManagerFactory.createEntityManager()` in regular repositories, as doing so easily detaches from Spring-managed transactions and makes closing resources the application's responsibility.

Commonly used APIs:

| API | Purpose |
|---|---|
| `createQuery(jpql, resultType)` | Creates a typed JPQL query |
| `createQuery(criteriaQuery)` | Creates a query from the Criteria API |
| `setParameter(name, value)` | Binds a parameter value |
| `setFirstResult(offset)` | Sets the starting offset |
| `setMaxResults(limit)` | Limits the number of results |
| `getResultList()` | Retrieves a list, empty if there are no rows |
| `getSingleResult()` | Retrieves a single result; may throw if 0 or multiple rows per JPA API |
| `persist(entity)` | Adds a new entity to the persistence context |
| `merge(entity)` | Merges detached state into a managed entity |
| `flush()` | Synchronizes persistence context changes to the database |
| `clear()` | Detaches all entities from the persistence context |

In this lesson, `EntityManager` is mainly used to build read queries. Write operations can still go through `JpaRepository` or service transactions depending on the design.

## 5. Building Dynamic JPQL with StringBuilder

Dynamic JPQL can be constructed by appending each predicate when its corresponding criterion has a value. Only assemble query structure controlled by the application; user values must always be bound via parameters.

Illustrative snippet:

~~~java
StringBuilder jpql = new StringBuilder(
        "select c from Customer c where 1 = 1");

if (criteria.status() != null) {
    jpql.append(" and c.status = :status");
}

if (criteria.emailEquals() != null) {
    jpql.append(" and lower(c.email) = :email");
}
~~~

The `1 = 1` condition makes appending `AND` clauses convenient, though it is not required. You can use `List<String> predicates` and `String.join(" and ", predicates)` to avoid a dummy predicate.

Never concatenate values directly into JPQL:

~~~java
// Unsafe: input data alters the query structure.
String jpql = "select c from Customer c where c.email = '"
        + requestEmail + "'";
~~~

The safe way is using placeholders:

~~~java
String jpql =
        "select c from Customer c where c.email = :email";

TypedQuery<Customer> query =
        entityManager.createQuery(jpql, Customer.class);

query.setParameter("email", requestEmail);
~~~

Parameter binding protects statement structure from SQL injection. It also helps the provider handle type conversion and reuse query plans better in some cases.

## 6. Distinguishing Parameter Values from Dynamic Property Names

Parameters only replace values, not entity names, property names, or query keywords.

This example does not work as intended:

~~~java
String jpql = "select c from Customer c order by :sortField";
query.setParameter("sortField", "createdAt");
~~~

The database treats `:sortField` as a literal value, not an identifier to sort by.

If dynamic sorting is required, select property names from an allowlist and append the controlled identifier into JPQL. Never concatenate arbitrary column names or sort expressions sent by a client directly.

Whitelist example:

~~~java
private static final Map<String, String> SORT_FIELDS = Map.of(
        "name", "c.name",
        "email", "c.email",
        "status", "c.status",
        "createdAt", "c.createdAt",
        "id", "c.id"
);
~~~

When receiving a `Sort.Order`, check that the property exists in the map before adding it to `ORDER BY`. If invalid, reject the request with a clear validation error.

## 7. Writing a Helper to Build WHERE and a Parameter Map

So that the content query and count query share identical conditions, write a helper solely responsible for building the `WHERE` clause and parameter map.

~~~java
private String buildWhere(
        CustomerSearchCriteria criteria,
        Map<String, Object> parameters) {

    List<String> predicates = new ArrayList<>();

    if (criteria.nameContains() != null
            && !criteria.nameContains().isBlank()) {
        predicates.add("lower(c.name) like :name escape '!'");
        String value = escapeLike(
                criteria.nameContains().trim().toLowerCase(Locale.ROOT));
        parameters.put("name", "%" + value + "%");
    }

    if (criteria.emailEquals() != null
            && !criteria.emailEquals().isBlank()) {
        predicates.add("lower(c.email) = :email");
        parameters.put(
                "email",
                criteria.emailEquals().trim().toLowerCase(Locale.ROOT));
    }

    if (criteria.status() != null) {
        predicates.add("c.status = :status");
        parameters.put("status", criteria.status());
    }

    if (criteria.createdFromInclusive() != null) {
        predicates.add("c.createdAt >= :createdFrom");
        parameters.put("createdFrom", criteria.createdFromInclusive());
    }

    if (criteria.createdBeforeExclusive() != null) {
        predicates.add("c.createdAt < :createdBefore");
        parameters.put("createdBefore", criteria.createdBeforeExclusive());
    }

    if (predicates.isEmpty()) {
        return "";
    }

    return " where " + String.join(" and ", predicates);
}
~~~

Wildcard escape helper:

~~~java
private String escapeLike(String value) {
    return value
            .replace("!", "!!")
            .replace("%", "!%")
            .replace("_", "!_");
}
~~~

JPQL `LIKE` uses `%` and `_` as wildcards. In this example, `!` is chosen as the escape character. `escapeLike` escapes the escape character itself first, then escapes `%` and `_`, so user input containing those characters is matched literally.

Without escaping, a search for a name containing `%` could unintentionally match far too many rows. Parameter binding still prevents SQL injection, but it does not change `LIKE` wildcard semantics; `LIKE` escaping solves that separate issue.

Predicates are combined with `AND`. If business rules require `OR`, parenthesized groups, or complex logic, build an explicit predicate structure rather than concatenating strings arbitrarily.

## 8. Binding All Parameters to TypedQuery

You can use a generic helper:

~~~java
private <T> TypedQuery<T> bindParameters(
        TypedQuery<T> query,
        Map<String, Object> parameters) {

    parameters.forEach(query::setParameter);
    return query;
}
~~~

How to call it:

~~~java
Map<String, Object> parameters = new LinkedHashMap<>();
String where = buildWhere(criteria, parameters);

TypedQuery<Customer> contentQuery = entityManager.createQuery(
        "select c from Customer c" + where,
        Customer.class
);

bindParameters(contentQuery, parameters);
~~~

Using a map allows the same set of values to be bound to both the content query and the count query. Parameter names must match the placeholders in JPQL exactly.

`LinkedHashMap` preserves insertion order for stable debugging, even though named parameter binding order does not affect semantics.

Manual casting is unnecessary when `createQuery` receives an explicit result type. `TypedQuery<Customer>` lets the compiler and IDE catch certain return-type errors earlier than the non-generic `Query` API.

## 9. Building Dynamic ORDER BY Safely

The helper below allows sorting only on declared properties:

~~~java
private String buildOrderBy(Sort sort) {
    if (sort.isUnsorted()) {
        return " order by c.id asc";
    }

    List<String> orders = new ArrayList<>();
    boolean includesId = false;

    for (Sort.Order order : sort) {
        String expression = SORT_FIELDS.get(order.getProperty());

        if (expression == null) {
            throw new IllegalArgumentException(
                    "Unsupported sort property: " + order.getProperty());
        }

        if (order.isIgnoreCase()) {
            if (!order.getProperty().equals("name")
                    && !order.getProperty().equals("email")) {
                throw new IllegalArgumentException(
                        "Ignore-case sort is only supported for text fields");
            }
            expression = "lower(" + expression + ")";
        }

        orders.add(expression + (order.isAscending() ? " asc" : " desc"));

        if (order.getProperty().equals("id")) {
            includesId = true;
        }
    }

    if (!includesId) {
        orders.add("c.id asc");
    }

    return " order by " + String.join(", ", orders);
}
~~~

Key points:

- Sort properties are looked up in a whitelist.
- `ASC`/`DESC` direction is derived from an enum, never taken as raw SQL from the client.
- `IgnoreCase` is accepted only for text fields.
- `id` is added as a tie-breaker if the caller did not already sort by `id`.
- When unsorted, the query defaults to sorting by `id`.

Deterministic ordering is critical for pagination. If multiple `Customer` rows share the same `createdAt`, adding `id` keeps ordering consistent across pages.

## 10. Complete Custom Repository Implementation

Assemble the helpers into the fragment implementation:

~~~java
package com.example.customer;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

import jakarta.persistence.EntityManager;
import jakarta.persistence.PersistenceContext;
import jakarta.persistence.TypedQuery;

import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.stereotype.Repository;
import org.springframework.transaction.annotation.Transactional;

@Repository
public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private static final Map<String, String> SORT_FIELDS = Map.of(
            "name", "c.name",
            "email", "c.email",
            "status", "c.status",
            "createdAt", "c.createdAt",
            "id", "c.id"
    );

    @PersistenceContext
    private EntityManager entityManager;

    @Override
    @Transactional(readOnly = true)
    public Page<Customer> search(
            CustomerSearchCriteria criteria,
            Pageable pageable) {

        validateCriteria(criteria);

        Map<String, Object> parameters = new LinkedHashMap<>();
        String where = buildWhere(criteria, parameters);
        String orderBy = buildOrderBy(pageable.getSort());

        String contentJpql =
                "select c from Customer c" + where + orderBy;

        TypedQuery<Customer> contentQuery =
                entityManager.createQuery(contentJpql, Customer.class);

        bindParameters(contentQuery, parameters);

        if (pageable.isPaged()) {
            contentQuery.setFirstResult(
                    Math.toIntExact(pageable.getOffset()));
            contentQuery.setMaxResults(pageable.getPageSize());
        }

        List<Customer> content = contentQuery.getResultList();

        String countJpql =
                "select count(c) from Customer c" + where;

        TypedQuery<Long> countQuery =
                entityManager.createQuery(countJpql, Long.class);

        bindParameters(countQuery, parameters);

        long total = countQuery.getSingleResult();

        return new PageImpl<>(content, pageable, total);
    }

    private void validateCriteria(CustomerSearchCriteria criteria) {
        if (criteria == null) {
            throw new IllegalArgumentException("criteria must not be null");
        }

        if (criteria.createdFromInclusive() != null
                && criteria.createdBeforeExclusive() != null
                && !criteria.createdFromInclusive()
                        .isBefore(criteria.createdBeforeExclusive())) {
            throw new IllegalArgumentException(
                    "createdFromInclusive must be before createdBeforeExclusive");
        }
    }

    private String buildWhere(
            CustomerSearchCriteria criteria,
            Map<String, Object> parameters) {

        List<String> predicates = new ArrayList<>();

        if (criteria.nameContains() != null
                && !criteria.nameContains().isBlank()) {
            predicates.add("lower(c.name) like :name escape '!'");
            String value = escapeLike(
                    criteria.nameContains().trim().toLowerCase(Locale.ROOT));
            parameters.put("name", "%" + value + "%");
        }

        if (criteria.emailEquals() != null
                && !criteria.emailEquals().isBlank()) {
            predicates.add("lower(c.email) = :email");
            parameters.put(
                    "email",
                    criteria.emailEquals().trim().toLowerCase(Locale.ROOT));
        }

        if (criteria.status() != null) {
            predicates.add("c.status = :status");
            parameters.put("status", criteria.status());
        }

        if (criteria.createdFromInclusive() != null) {
            predicates.add("c.createdAt >= :createdFrom");
            parameters.put("createdFrom", criteria.createdFromInclusive());
        }

        if (criteria.createdBeforeExclusive() != null) {
            predicates.add("c.createdAt < :createdBefore");
            parameters.put("createdBefore", criteria.createdBeforeExclusive());
        }

        return predicates.isEmpty()
                ? ""
                : " where " + String.join(" and ", predicates);
    }

    private String escapeLike(String value) {
        return value
                .replace("!", "!!")
                .replace("%", "!%")
                .replace("_", "!_");
    }

    private String buildOrderBy(Sort sort) {
        if (sort.isUnsorted()) {
            return " order by c.id asc";
        }

        List<String> orders = new ArrayList<>();
        boolean includesId = false;

        for (Sort.Order order : sort) {
            String expression = SORT_FIELDS.get(order.getProperty());

            if (expression == null) {
                throw new IllegalArgumentException(
                        "Unsupported sort property: " + order.getProperty());
            }

            if (order.isIgnoreCase()) {
                if (!order.getProperty().equals("name")
                        && !order.getProperty().equals("email")) {
                    throw new IllegalArgumentException(
                            "Ignore-case sort is only supported for text fields");
                }
                expression = "lower(" + expression + ")";
            }

            orders.add(expression
                    + (order.isAscending() ? " asc" : " desc"));

            if (order.getProperty().equals("id")) {
                includesId = true;
            }
        }

        if (!includesId) {
            orders.add("c.id asc");
        }

        return " order by " + String.join(", ", orders);
    }

    private <T> TypedQuery<T> bindParameters(
            TypedQuery<T> query,
            Map<String, Object> parameters) {

        parameters.forEach(query::setParameter);
        return query;
    }
}
~~~

This is a complete implementation for the declared `Customer` model. The content query and count query share the exact same `WHERE` string and parameter map. The count query omits `ORDER BY` because ordering does not affect the row count.

`Math.toIntExact` converts `Pageable`'s `long` offset to the `int` required by JPA `setFirstResult`. If the offset exceeds `int` bounds, conversion fails loudly instead of silently overflowing. Applications should cap page numbers/page sizes to avoid huge offsets.

If `pageable` is unpaged, the implementation skips calling `setFirstResult` and `setMaxResults`. `PageImpl` still receives `pageable` and the total count. For public APIs, you should normally require paged `Pageable` instances and enforce a maximum page size to avoid returning an entire table.

## 11. Why Must Content and Count Use the Same WHERE?

`Page<T>` holds both `content` and `totalElements`. If the content query filters by `status` and `name`, while the count query filters only by `status`, the reported page count will exceed reality.

Example:

~~~text
Content:
status = ACTIVE
AND name contains "an"

Count:
status = ACTIVE
~~~

Content includes only customers with matching names, while count totals all active customers. `totalElements` and `totalPages` become incorrect.

In the implementation above, `buildWhere()` is called only once. The `WHERE` clause and parameter map are reused for both queries, reducing the risk of the two queries drifting out of sync.

If a query has a to-many `JOIN`, `count(c)` may count joined rows instead of unique `Customer` entities. In that case, use `EXISTS` when you only need to check for a related element, or `count(distinct c.id)` when the `JOIN` is necessary. The count query must reflect the root entity's cardinality, not intermediate join rows.

## 12. Building Queries with the Criteria API

Assembling JPQL with `StringBuilder` is convenient when the query structure is relatively simple. For complex dynamic predicates, the Criteria API provides a typed API for roots, predicates, ordering, and subqueries.

Example building a list of predicates:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<Customer> cq = cb.createQuery(Customer.class);
Root<Customer> root = cq.from(Customer.class);

List<Predicate> predicates = new ArrayList<>();

if (criteria.status() != null) {
    predicates.add(cb.equal(
            root.get("status"),
            criteria.status()));
}

if (criteria.emailEquals() != null
        && !criteria.emailEquals().isBlank()) {
    predicates.add(cb.equal(
            cb.lower(root.get("email")),
            criteria.emailEquals().trim().toLowerCase(Locale.ROOT)));
}

if (criteria.createdFromInclusive() != null) {
    predicates.add(cb.greaterThanOrEqualTo(
            root.get("createdAt"),
            criteria.createdFromInclusive()));
}

if (criteria.createdBeforeExclusive() != null) {
    predicates.add(cb.lessThan(
            root.get("createdAt"),
            criteria.createdBeforeExclusive()));
}

cq.select(root)
        .where(cb.and(predicates.toArray(Predicate[]::new)))
        .orderBy(cb.asc(root.get("id")));

TypedQuery<Customer> query = entityManager.createQuery(cq);
query.setFirstResult(0);
query.setMaxResults(20);

List<Customer> result = query.getResultList();
~~~

This snippet illustrates code inside a method where `criteria` and `entityManager` are already declared. Appropriate imports for `CriteriaBuilder`, `CriteriaQuery`, `Root`, `Predicate`, `TypedQuery`, and Java collections are required.

The Criteria API avoids concatenating JPQL strings. Predicates are created via `cb.equal()`, `cb.like()`, `cb.greaterThanOrEqualTo()`, `cb.and()`, `cb.or()`, and similar methods.

### Comparing the Two Approaches

| Criterion | Assembling JPQL | Criteria API |
|---|---|---|
| Representation | Query string | Object/query tree |
| Readability for simple queries | Usually easy to read | More verbose |
| Dynamic predicates | Append JPQL clauses | Add `Predicate` to a `List` |
| Property names | Strings in JPQL | Can use typed metamodel |
| Complex queries | String management can get difficult | Dedicated API for joins/subqueries/grouping |
| Binding values | `setParameter` | `ParameterExpression` or query-bound literals |
| Syntax checking | Usually at query creation/execution | Part of structure checked by compiler/API |

The Criteria API does not automatically guarantee business correctness or query efficiency. It simply lets you construct query structure with a Java API instead of string assembly.

## 13. Reusing Predicates for the Criteria Count Query

When using the Criteria API for a `Page`, you must create a count query with matching predicates.

Example helper creating predicates for a root:

~~~java
private List<Predicate> buildPredicates(
        CustomerSearchCriteria criteria,
        CriteriaBuilder cb,
        Root<Customer> root) {

    List<Predicate> predicates = new ArrayList<>();

    if (criteria.status() != null) {
        predicates.add(cb.equal(root.get("status"), criteria.status()));
    }

    if (criteria.nameContains() != null
            && !criteria.nameContains().isBlank()) {
        String escaped = escapeLike(
                criteria.nameContains().trim().toLowerCase(Locale.ROOT));

        predicates.add(cb.like(
                cb.lower(root.get("name")),
                "%" + escaped + "%",
                '!'));
    }

    if (criteria.emailEquals() != null
            && !criteria.emailEquals().isBlank()) {
        predicates.add(cb.equal(
                cb.lower(root.get("email")),
                criteria.emailEquals().trim().toLowerCase(Locale.ROOT)));
    }

    if (criteria.createdFromInclusive() != null) {
        predicates.add(cb.greaterThanOrEqualTo(
                root.get("createdAt"),
                criteria.createdFromInclusive()));
    }

    if (criteria.createdBeforeExclusive() != null) {
        predicates.add(cb.lessThan(
                root.get("createdAt"),
                criteria.createdBeforeExclusive()));
    }

    return predicates;
}
~~~

Content query:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaQuery<Customer> contentCq =
        cb.createQuery(Customer.class);
Root<Customer> contentRoot = contentCq.from(Customer.class);

List<Predicate> contentPredicates =
        buildPredicates(criteria, cb, contentRoot);

contentCq.select(contentRoot)
        .where(cb.and(contentPredicates.toArray(Predicate[]::new)))
        .orderBy(cb.asc(contentRoot.get("createdAt")),
                 cb.asc(contentRoot.get("id")));

TypedQuery<Customer> contentQuery =
        entityManager.createQuery(contentCq);

contentQuery.setFirstResult(Math.toIntExact(pageable.getOffset()));
contentQuery.setMaxResults(pageable.getPageSize());

List<Customer> content = contentQuery.getResultList();
~~~

Count query:

~~~java
CriteriaQuery<Long> countCq = cb.createQuery(Long.class);
Root<Customer> countRoot = countCq.from(Customer.class);

List<Predicate> countPredicates =
        buildPredicates(criteria, cb, countRoot);

countCq.select(cb.count(countRoot))
        .where(cb.and(countPredicates.toArray(Predicate[]::new)));

long total = entityManager.createQuery(countCq).getSingleResult();
~~~

Each query has its own `Root`, so you must build fresh `Predicate` objects for each root. Never reuse a `Predicate` created from the content root in the count query.

If predicates involve a to-many `JOIN`, the count query needs to prevent duplicate roots via `EXISTS` or `countDistinct(countRoot.get("id"))`. For queries filtering only on `Customer` attributes as in the example, `cb.count(countRoot)` is appropriate.

## 14. Criteria API with OR and Grouped Conditions

The Criteria API can build explicit `AND`/`OR` groups. For example, find customers where:

- `status` is `ACTIVE`
- and (`name` contains `"an"` or `email` ends with `"@example.com"`)

~~~java
Predicate active = cb.equal(
        root.get("status"),
        CustomerStatus.ACTIVE);

Predicate nameMatches = cb.like(
        cb.lower(root.get("name")),
        "%an%",
        '!');

Predicate emailMatches = cb.like(
        cb.lower(root.get("email")),
        "%@example.com");

Predicate contactMatches = cb.or(nameMatches, emailMatches);

cq.where(cb.and(active, contactMatches));
~~~

Equivalent result:

~~~sql
WHERE status = 'ACTIVE'
  AND (
      lower(name) LIKE '%an%'
      OR lower(email) LIKE '%@example.com'
  )
~~~

Use `cb.and()` and `cb.or()` to preserve exact condition grouping. Avoid assembling string predicates if a query involves multiple parenthesized groups.

If user input is placed into `LIKE`, you still need to escape wildcards with your chosen escape character. The Criteria API does not automatically treat user-entered `%` and `_` as literal characters.

## 15. JOIN, EXISTS, and Count When Querying Associations

Suppose `Customer` has multiple `PurchaseOrder` entities and you want customers with at least one `PAID` order.

You can use JPQL `EXISTS`:

~~~java
select c
from Customer c
where exists (
    select o.id
    from PurchaseOrder o
    where o.customer = c
      and o.status = :orderStatus
)
~~~

This keeps each `Customer` once in the outer result. The count query can use `count(c)` with the same `EXISTS` clause.

If you use `JOIN`:

~~~java
select c
from Customer c
join c.orders o
where o.status = :orderStatus
~~~

a `Customer` with multiple `PAID` orders may appear multiple times. If the content needs each `Customer` once, use `DISTINCT`; the count query needs `count(distinct c.id)` or switching to `EXISTS`.

When you only need to check whether a matching association exists, `EXISTS` expresses intent more directly and avoids duplicating root rows. When you need data from the association, `JOIN` or a dedicated fetch plan may fit better.

Do not place collection fetches inside a `Page` content query solely for filtering. Separate predicates from fetch plans and verify the count query independently.

## 16. Projections to Fetch Only Needed Fields

If a screen only needs name, email, and status, loading the entire entity is unnecessary.

DTO:

~~~java
package com.example.customer;

public record CustomerSummary(
        Long id,
        String name,
        String email,
        CustomerStatus status
) {
}
~~~

JPQL constructor expression:

~~~java
String jpql = """
        select new com.example.customer.CustomerSummary(
            c.id, c.name, c.email, c.status
        )
        from Customer c
        """ + where + orderBy;

TypedQuery<CustomerSummary> query =
        entityManager.createQuery(jpql, CustomerSummary.class);
~~~

`WHERE` parameters are bound just like the entity content query. The count query still uses:

~~~java
String countJpql = "select count(c) from Customer c" + where;
~~~

DTO projections reduce the columns fetched from the database and avoid instantiating unnecessary entities/associations. Constructor expressions must use the fully qualified class name, and parameter types/order must match the record constructor.

If a query uses `GROUP BY` or aggregates, design the count query for the number of result groups rather than defaulting to counting root entities.

## 17. Pagination and Limiting Data

`EntityManager` provides `setFirstResult()` and `setMaxResults()`:

~~~java
TypedQuery<Customer> query =
        entityManager.createQuery(jpql, Customer.class);

query.setFirstResult(0);
query.setMaxResults(20);

List<Customer> firstPage = query.getResultList();
~~~

Offset is 0-based. The first page has offset 0; the second page with a page size of 20 has offset 20.

When accepting `Pageable`:

~~~java
if (pageable.isPaged()) {
    query.setFirstResult(Math.toIntExact(pageable.getOffset()));
    query.setMaxResults(pageable.getPageSize());
}
~~~

JPA takes offset as an `int`. On large tables, high offsets can be costly because the database still scans past many rows before reaching the target window. For very large datasets or rapidly changing feeds, consider keyset/cursor pagination.

Always enforce a maximum page size at the API/service layer. Never allow clients to send unlimited page sizes or huge offsets.

## 18. Dynamic and Safe Sorting

Sort properties are identifiers, not bindable parameter values. Therefore, accept only whitelisted properties.

Example:

~~~java
Map<String, String> allowed = Map.of(
        "name", "c.name",
        "email", "c.email",
        "createdAt", "c.createdAt",
        "id", "c.id"
);

String expression = allowed.get(requestedSort);

if (expression == null) {
    throw new IllegalArgumentException("Unsupported sort field");
}

String direction = ascending ? "asc" : "desc";
String orderBy = " order by " + expression + " " + direction;
~~~

Do not write:

~~~java
String orderBy = " order by c." + requestedSort;
~~~

because a client could send an invalid string or attempt to alter the query structure.

With Spring Data's `Sort`, still whitelist each `Sort.Order` property. Only append expressions looked up from the map and directions derived from `isAscending()`. Add `id` as a tie-breaker so pagination order stays deterministic.

## 19. Transactions and Persistence Context

Read queries using `EntityManager` should run inside an appropriate transaction. You can place `@Transactional(readOnly = true)` on the service or custom repository method.

~~~java
@Transactional(readOnly = true)
public Page<Customer> search(
        CustomerSearchCriteria criteria,
        Pageable pageable) {
    return repository.search(criteria, pageable);
}
~~~

A transaction lets `EntityManager` join a Spring-managed persistence context and keeps lazy associations accessible within the transaction scope.

`readOnly = true` is metadata/a hint for the transaction manager and provider; it is not a guarantee that the database cannot perform writes across every configuration.

For two-phase queries or when reading `LAZY` associations, keep the steps in the same transaction. Do not return a `Stream` or an entity with lazy associations outside the transaction and access them after the persistence context has closed.

## 20. Handling Nulls, Empty Strings, and Whitespace

Dynamic queries must define input semantics clearly:

| Value | Example Policy |
|---|---|
| `null` | Do not add predicate |
| Empty string | Do not add predicate |
| Whitespace-only string | Trim and treat as not provided |
| Concrete value | Add predicate and bind parameter |
| Invalid date range | Reject request via validation |

In the sample code, `nameContains` and `emailEquals` are added only when non-null and non-blank. Strings are trimmed before binding.

Do not blindly apply the same policy to every field. For example, a `null` status might mean "do not filter by status", whereas another use case might require finding customers without a status. When searching for null values, add an `IS NULL` predicate explicitly.

For date ranges, an exclusive end bound usually represents whole days cleanly. For instance, to query all of `2026-01-10`, use inclusive start of day 10 to exclusive start of day 11 in the business timezone.

## 21. Preventing SQL Injection and Query Assembly Bugs

Key rules:

- Bind all data values via `setParameter()`.
- Never concatenate input directly into JPQL literals.
- Never bind parameters in place of entity names, property names, or keywords.
- Whitelist sort fields and sort directions.
- Escape `LIKE` wildcards when users need literal character matching.
- Validate page sizes, offsets, date ranges, and enums.
- Never accept raw `WHERE`/`ORDER BY` fragments from clients.
- Use the Criteria API when predicate structures are complex or error-prone with string assembly.

Unsafe example:

~~~java
String jpql = "select c from Customer c where c.name like '%"
        + request.name() + "%'";
~~~

Safer example:

~~~java
String jpql =
        "select c from Customer c where c.name like :name";

TypedQuery<Customer> query =
        entityManager.createQuery(jpql, Customer.class);

query.setParameter("name", "%" + escapedName + "%");
~~~

Parameter binding prevents input data from becoming query syntax. Escaping `LIKE` is still necessary whenever `%` and `_` must be matched literally.

## 22. Testing Custom Repositories with `@DataJpaTest`

Tests should verify multiple filter combinations, counts, sorting, paging, and wildcards. Example:

~~~java
package com.example.customer;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Instant;
import java.util.List;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.orm.jpa.DataJpaTest;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Sort;

@DataJpaTest
class CustomerSearchRepositoryTest {

    @Autowired
    private CustomerRepository repository;

    @Test
    void combinesOptionalFiltersAndCountsMatchingRows() {
        repository.saveAll(List.of(
                new Customer(
                        "An Nguyen",
                        "an@example.com",
                        CustomerStatus.ACTIVE,
                        Instant.parse("2026-01-03T10:00:00Z")),
                new Customer(
                        "Anna Tran",
                        "anna@example.com",
                        CustomerStatus.ACTIVE,
                        Instant.parse("2026-01-02T10:00:00Z")),
                new Customer(
                        "Binh Le",
                        "binh@example.com",
                        CustomerStatus.INACTIVE,
                        Instant.parse("2026-01-01T10:00:00Z"))
        ));

        CustomerSearchCriteria criteria = new CustomerSearchCriteria(
                "an",
                null,
                CustomerStatus.ACTIVE,
                null,
                null
        );

        Page<Customer> page = repository.search(
                criteria,
                PageRequest.of(
                        0,
                        1,
                        Sort.by(Sort.Direction.DESC, "createdAt")
                )
        );

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getContent().getFirst().getName())
                .isEqualTo("An Nguyen");
        assertThat(page.getTotalElements()).isEqualTo(2);
        assertThat(page.getTotalPages()).isEqualTo(2);
    }

    @Test
    void treatsLikeWildcardsAsLiteralCharacters() {
        repository.saveAll(List.of(
                new Customer(
                        "100% Real",
                        "percent@example.com",
                        CustomerStatus.ACTIVE,
                        Instant.parse("2026-01-03T10:00:00Z")),
                new Customer(
                        "100X Real",
                        "other@example.com",
                        CustomerStatus.ACTIVE,
                        Instant.parse("2026-01-02T10:00:00Z"))
        ));

        CustomerSearchCriteria criteria = new CustomerSearchCriteria(
                "100%",
                null,
                null,
                null,
                null
        );

        Page<Customer> page = repository.search(
                criteria,
                PageRequest.of(0, 10)
        );

        assertThat(page.getTotalElements()).isEqualTo(1);
        assertThat(page.getContent())
                .extracting(Customer::getName)
                .containsExactly("100% Real");
    }
}
~~~

The example uses `List.getFirst()`, available since Java 21. If the project runs on Java 17, replace it with `page.getContent().get(0)`. Spring Data and Hibernate APIs must also match your project's versions.

`@DataJpaTest` normally configures the persistence layer and rolls back transactions after each test. If a custom fragment is not discovered inside the test slice due to package layout or custom configuration, check repository scanning and import the required configuration instead of altering the implementation arbitrarily.

Consider adding tests for:

- No filters, returning all results within page bounds.
- Each individual filter on its own.
- Multiple filters combined with `AND`.
- Inclusive/exclusive time intervals.
- Names/emails containing `%`, `_`, and the `!` escape character.
- Non-whitelisted sort properties being rejected.
- Sorting with the `id` tie-breaker.
- Count queries matching content filters accurately.
- Boundary offsets and page sizes.

## 23. Performance and Observing SQL

Dynamic queries can generate many different SQL shapes depending on predicate combinations. Measure with production-like data volumes.

Things to inspect:

- Indexes on frequently filtered columns such as `status`, `email`, or `createdAt`.
- `LOWER(column)` may not use standard indexes if the database lacks an appropriate functional index.
- `LIKE '%term%'` typically cannot utilize a standard B-tree index effectively.
- Page queries with `ORDER BY` need indexes aligned with filters/sorts when workload demands it.
- Count queries carry their own cost; avoid returning `Page` if the UI does not need a total count.
- Large offsets can be slow; consider keyset pagination.
- To-many `JOIN` predicates can multiply rows; use `EXISTS` or count distinct when appropriate.
- Avoid loading entities/associations if a DTO projection meets the requirement.

In development, you can enable SQL logging:

~~~properties
spring.jpa.show-sql=true
spring.jpa.properties.hibernate.format_sql=true
logging.level.org.hibernate.SQL=DEBUG
logging.level.org.hibernate.orm.jdbc.bind=TRACE
~~~

Bound parameter logs may include emails or personal data. Enable them only for debugging in controlled environments and avoid logging sensitive data in production.

## 24. When to Choose Dynamic JPQL, Criteria API, or Specification?

| Approach | Best Suited When |
|---|---|
| Derived query | Fixed, short, readable conditions |
| `@Query` | A single fixed JPQL query needing explicit control |
| Dynamic JPQL with `EntityManager` | Query structure varies per request while keeping a readable query string |
| Criteria API with `EntityManager` | Complex dynamic predicates with many joins/subqueries/groupings |
| `Specification` | Reusable predicates combined dynamically via `JpaSpecificationExecutor` |
| Querydsl | Project wants a type-safe query API and rich query composition |

Dynamic JPQL is often shorter and easier to debug when there are only a few predicates. The Criteria API fits better when a query is built from many logical branches. `Specification` packages Criteria predicates for direct integration with repositories. These options are not mutually exclusive; pick based on complexity and project conventions.

## 25. Common Mistakes

| Symptom | Cause | Fix |
|---|---|---|
| SQL injection via filter | Concatenating user values into JPQL | Use named parameters |
| Sorting fails when binding field name | Parameters replace values, not identifiers | Whitelist and append controlled properties |
| Content is right, `totalElements` is wrong | Count query has different predicates than content | Reuse the same `WHERE` clause and parameter map |
| Count exceeds entity count | To-many `JOIN` creates duplicate roots | Use `EXISTS` or `COUNT DISTINCT` |
| Searching for `%` returns too many rows | `LIKE` treats `%` as a wildcard | Escape `%`, `_`, and the escape character |
| Null accidentally filters with `IS NULL` | Include-null logic or faulty predicate | Add predicates only when criteria are provided |
| Empty string produces `LIKE %%` | Blank values not normalized | Trim/validate per API contract |
| Query fails to resolve entity/property | SQL table/column names used in JPQL | Use entity names and Java properties |
| Unknown client sort field causes failure | Missing whitelist | Reject properties outside the allowed list |
| Offset overflows `int` | `Pageable` offset exceeds JPA limit | Cap page/offset or use keyset pagination |
| `LazyInitializationException` | Accessing associations after transaction ends | Load inside transaction or return a DTO |
| N+1 when iterating collections | Root query lacks an appropriate fetch plan | Batch fetch or query associations separately |
| Criteria `Predicate` used with wrong `Root` | Reusing predicates between content and count roots | Build fresh predicates for each query root |
| `EntityManager` does not join transaction | Manually created `EntityManager` outside Spring | Use `@PersistenceContext` and Spring transactions |

## 26. Self-Assessment Checklist

- [ ] Know when dynamic queries require `EntityManager`.
- [ ] Organize custom repository fragments with proper interface and implementation naming.
- [ ] Inject `EntityManager` via `@PersistenceContext`.
- [ ] Use `createQuery()` with `TypedQuery`.
- [ ] Assemble predicates without concatenating input values into JPQL.
- [ ] Bind named parameters using `setParameter()`.
- [ ] Distinguish parameter values from identifiers/sort fields.
- [ ] Whitelist sort properties and directions.
- [ ] Escape `LIKE` wildcards when literal matching is needed.
- [ ] Normalize `null`, empty, and blank inputs per API contract.
- [ ] Reuse the same filters for content and count queries.
- [ ] Use `EXISTS` or count distinct when filtering across collections.
- [ ] Use `CriteriaBuilder` when dynamic predicates get complex.
- [ ] Create fresh `Predicate` instances for each Criteria `Root`.
- [ ] Apply `setFirstResult` and `setMaxResults` properly.
- [ ] Cap page sizes and handle large offsets.
- [ ] Use appropriate transactions for `EntityManager` and lazy associations.
- [ ] Test filters, counts, sorting, paging, and wildcards.
- [ ] Inspect SQL and execution plans on the target database.

## 27. Conclusion

`EntityManager` lets you construct dynamic queries using JPQL or the Criteria API. With JPQL, assemble controlled structural clauses, bind all values, and whitelist sort identifiers. With the Criteria API, build a `Predicate` per criterion and combine them with `AND`/`OR`.

In Spring Data JPA, a custom repository fragment is the right place to encapsulate this logic. Content and count queries must use identical filter predicates; if a collection `JOIN` can multiply rows, consider `EXISTS` or `COUNT DISTINCT`. Managing transactions, bounding pagination, testing filter combinations, and inspecting generated SQL keep dynamic queries safe and maintainable.