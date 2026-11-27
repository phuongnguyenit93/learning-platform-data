# CriteriaBuilder, CriteriaQuery, Root, Path, and Predicate

## 1. What Is the Criteria API?

The Jakarta Persistence Criteria API lets you build queries using Java objects instead of concatenating JPQL strings. This is a useful option when search criteria vary based on input: users may choose status, date ranges, names, amounts, related entities, or multiple optional filters.

In Spring Data JPA, the Criteria API appears directly when writing `Specification<T>`. Spring Data passes three key objects into the callback:

- `Root<T>`: represents the root entity in the FROM clause.
- `CriteriaQuery<T>`: describes the query structure, result type, conditions, grouping, and ordering.
- `CriteriaBuilder`: provides operations to create expressions and conditions.
- `Path<X>`: a path to an entity property or association.
- `Predicate`: a logical condition used in WHERE or HAVING.

These components work together to produce a strongly typed query. The workflow looks like this:

1. Obtain CriteriaBuilder from EntityManager.
2. Create a CriteriaQuery with the desired result type.
3. Declare a Root for the entity to query.
4. Use Path to access properties and Join to traverse relationships.
5. Use CriteriaBuilder to create Predicates and Expressions.
6. Attach selection, where, group by, having, and order by clauses to the CriteriaQuery.
7. Create a TypedQuery and execute it.

The Criteria API is a standard Jakarta Persistence API. In Spring Boot 3 and later, imports typically reside in the `jakarta.persistence.criteria` package; older Spring Boot 2/JPA projects use `javax.persistence.criteria`. Never mix both namespaces in the same application.

## 2. Relationships Between the Components

A Criteria query typically takes the form:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaQuery<Customer> query =
    cb.createQuery(Customer.class);

Root<Customer> customer = query.from(Customer.class);

Path<String> name = customer.get(Customer_.name);

Predicate condition =
    cb.like(cb.lower(name), "%an%");

query.select(customer)
     .where(condition)
     .orderBy(cb.asc(name));

List<Customer> result =
    entityManager.createQuery(query).getResultList();
```

In this example:

- `CriteriaBuilder` creates the query and expressions.
- `CriteriaQuery<Customer>` declares the result type as Customer.
- `Root<Customer>` represents the Customer table/entity in FROM.
- `Path<String>` points to the `name` property of type String.
- `Predicate` represents the LIKE condition.
- `select`, `where`, and `orderBy` complete the query structure.

Criteria objects describe the query; they do not execute SQL yet. SQL is generated and executed only when you create a TypedQuery and call `getResultList()`, `getSingleResult()`, or equivalent APIs.

## 3. CriteriaBuilder: Creating Queries and Expressions

### 3.1. Obtaining CriteriaBuilder and Creating CriteriaQuery

CriteriaBuilder is obtained from EntityManager:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
```

Creating a query returning an entity:

```java
CriteriaQuery<Customer> query =
    cb.createQuery(Customer.class);
```

Creating queries returning other types:

```java
CriteriaQuery<Long> countQuery =
    cb.createQuery(Long.class);

CriteriaQuery<Tuple> tupleQuery =
    cb.createTupleQuery();
```

The generic type of CriteriaQuery specifies the result type the query will return. This lets the compiler type-check many operations, reducing casting errors compared to JPQL string concatenation.

### 3.2. Basic Comparison Operations

CriteriaBuilder provides methods such as:

| Method | Meaning |
|---|---|
| `equal(x, y)` | Equal |
| `notEqual(x, y)` | Not equal |
| `gt(x, y)` | Greater than |
| `ge(x, y)` | Greater than or equal to |
| `lt(x, y)` | Less than |
| `le(x, y)` | Less than or equal to |
| `between(x, a, b)` | Within range |
| `like(x, pattern)` | Matches LIKE pattern |
| `isNull(x)` | Is null |
| `isNotNull(x)` | Is not null |
| `in(x)` | Membership in a value set |

Example:

```java
Predicate active =
    cb.equal(root.get(Customer_.status), CustomerStatus.ACTIVE);

Predicate minAge =
    cb.ge(root.get(Customer_.age), 18);

Predicate createdBetween =
    cb.between(
        root.get(Customer_.createdAt),
        from,
        to
    );
```

Numeric comparison methods use `Number`; date/time range comparisons use the corresponding Comparable type. Pass Java types compatible with the entity property type.

### 3.3. Combining AND, OR, and NOT

CriteriaBuilder supports logical composition:

```java
Predicate active = cb.equal(
    root.get(Customer_.status),
    CustomerStatus.ACTIVE
);

Predicate adult = cb.ge(root.get(Customer_.age), 18);

Predicate activeAdult = cb.and(active, adult);

Predicate namedAn = cb.like(
    cb.lower(root.get(Customer_.name)),
    "%an%"
);

Predicate result = cb.or(activeAdult, namedAn);
```

Corresponding operations:

- `cb.and(p1, p2)`: both conditions hold.
- `cb.or(p1, p2)`: at least one condition holds.
- `cb.not(p)`: negates the condition.
- `cb.conjunction()`: always-true condition, useful when the filter list is empty.
- `cb.disjunction()`: always-false condition.

You can build a Predicate from a list:

```java
List<Predicate> predicates = new ArrayList<>();

predicates.add(cb.equal(
    root.get(Customer_.status),
    CustomerStatus.ACTIVE
));

predicates.add(cb.ge(root.get(Customer_.age), 18));

query.where(cb.and(predicates.toArray(Predicate[]::new)));
```

This fits dynamic filters well. Only add a predicate when the corresponding input is actually supplied.

### 3.4. Expressions and Computed Functions

CriteriaBuilder also creates Expressions representing values computed inside the query:

```java
Expression<String> normalizedName =
    cb.lower(root.get(Customer_.name));

Expression<Integer> nameLength =
    cb.length(root.get(Customer_.name));

Expression<BigDecimal> discountedPrice =
    cb.prod(
        root.get(Product_.price),
        new BigDecimal("0.9")
    );
```

Expressions can be used in select, where, order by, group by, or other calculations depending on type and context. Not all database functions are portable; if you need a database-specific function, `cb.function(...)` can be used, but it must be tested on the target dialect.

## 4. CriteriaQuery: Describing Query Structure

### 4.1. Declaring Result Type and Selection

`CriteriaQuery<T>` represents a query with result type T. For an entity:

```java
CriteriaQuery<Customer> query =
    cb.createQuery(Customer.class);

Root<Customer> customer = query.from(Customer.class);

query.select(customer);
```

For a scalar value:

```java
CriteriaQuery<Long> query =
    cb.createQuery(Long.class);

Root<Customer> customer = query.from(Customer.class);

query.select(cb.count(customer));
```

For multiple values, Tuple can be used:

```java
CriteriaQuery<Tuple> query = cb.createTupleQuery();

Root<Customer> customer = query.from(Customer.class);

query.multiselect(
    customer.get(Customer_.id).alias("id"),
    customer.get(Customer_.name).alias("name")
);
```

After running a Tuple query, retrieve values by alias:

```java
Tuple row = entityManager.createQuery(query)
    .getSingleResult();

Long id = row.get("id", Long.class);
String name = row.get("name", String.class);
```

Aliases must be consistent and unique within the same selection.

### 4.2. WHERE and Caution on Multiple Calls

You can set a condition:

```java
query.where(
    cb.equal(customer.get(Customer_.status), CustomerStatus.ACTIVE)
);
```

A common mistake is calling `where()` multiple times expecting conditions to accumulate automatically:

```java
query.where(activePredicate);
query.where(agePredicate);
```

The later call replaces the previous restriction. To combine them, create a combined Predicate:

```java
query.where(cb.and(activePredicate, agePredicate));
```

Or collect conditions into a List and call `where()` once. The same principle applies to selection and ordering methods: when multiple items are needed, assemble the complete collection before applying it to the query.

### 4.3. DISTINCT

Collection JOINs can generate multiple SQL rows for the same root entity. If the goal is to retrieve each Customer once, you can use:

```java
query.select(customer).distinct(true);
```

DISTINCT removes duplicate results according to query semantics. When paginating or counting totals, the count query must also count unique entities properly, often requiring `countDistinct(root)` or a query form that avoids row multiplication.

### 4.4. ORDER BY

CriteriaQuery accepts a list of Orders:

```java
query.orderBy(
    cb.asc(customer.get(Customer_.name)),
    cb.desc(customer.get(Customer_.createdAt)),
    cb.asc(customer.get(Customer_.id))
);
```

Orders are applied in priority sequence. When paginating, add a unique property such as ID as a tie-breaker. If you sort only by name and multiple rows share the same name, the ordering among those rows is not guaranteed.

## 5. Root: The Root Entity in FROM

### 5.1. Which Entity Does Root Represent?

Root is created with `from()`:

```java
Root<Customer> customer = query.from(Customer.class);
```

It represents Customer in the FROM clause and serves as the starting point for accessing properties, joining relationships, or building expressions.

A query can have multiple Roots:

```java
Root<Customer> customer = query.from(Customer.class);
Root<Order> order = query.from(Order.class);
```

Two independent Roots can produce a Cartesian product without an appropriate linking predicate. When entities have association mappings, prefer joining through relationships instead of declaring extra Roots unnecessarily.

### 5.2. Accessing Properties from Root

Root supports Path navigation:

```java
Path<Long> id = customer.get(Customer_.id);
Path<String> name = customer.get(Customer_.name);
Path<CustomerStatus> status = customer.get(Customer_.status);
```

String names can also be used:

```java
Path<String> name = customer.get("name");
```

String paths are concise, but property name typos only surface at runtime. The static metamodel lets the compiler catch many naming/type mistakes during compilation.

## 6. Path: Navigating to Properties

### 6.1. What Is Path?

`Path<X>` represents a typed navigation path to an entity property or component. Root is itself a Path, with the added role of being a root entity capable of creating joins.

Example:

```java
Path<String> name = customer.get(Customer_.name);
Path<Integer> age = customer.get(Customer_.age);
Path<LocalDate> birthDate = customer.get(Customer_.birthDate);
```

Generic typing tells CriteriaBuilder whether an expression is String, Integer, or LocalDate so it can select the right comparison operations.

### 6.2. Traversing Embedded or Single Properties

If Customer has an `@Embedded` Address, you can access nested properties:

```java
Path<String> city =
    customer.get(Customer_.address).get(Address_.city);
```

This path traverses an embedded attribute. For entity associations like Customer having many Orders, use Join to express the association and control join type.

### 6.3. Path vs. Join

Path navigates to attributes. Join connects entities across an association in a query.

Example:

```java
Path<String> customerName =
    customer.get(Customer_.name);

Join<Customer, Order> orders =
    customer.join(Customer_.orders);
```

You cannot treat a collection association as a scalar Path to access element properties. You must join the collection first, then retrieve attributes from the related entity.

## 7. Static Metamodel and Type-Safe Queries

### 7.1. Why Use the Metamodel?

The static metamodel consists of classes generated from entities, typically suffixed with an underscore, such as `Customer_`. They provide typed attributes for use in the Criteria API.

Sample entity:

```java
@Entity
public class Customer {

    @Id
    private Long id;

    private String name;

    private Integer age;
}
```

The generated metamodel takes the general form:

```java
@StaticMetamodel(Customer.class)
public class Customer_ {
    public static volatile SingularAttribute<Customer, Long> id;
    public static volatile SingularAttribute<Customer, String> name;
    public static volatile SingularAttribute<Customer, Integer> age;
}
```

This illustrates the shape of code generated by the annotation processor; metamodel classes are normally not written by hand.

Using the metamodel:

```java
Path<String> name = customer.get(Customer_.name);
Predicate condition = cb.equal(name, "An");
```

If a property is renamed and the metamodel is regenerated, the compiler catches references to the old attribute. With string paths like `get("nam")`, the error appears only at runtime.

### 7.2. Configuring the Annotation Processor

The project needs an annotation processor matching your Jakarta Persistence version and build tool. The artifact name and configuration depend on the Hibernate/JPA metamodel generator version. Use a version compatible with your Spring Boot/Jakarta Persistence stack and configure it on the annotation processor path rather than adding it as an arbitrary runtime dependency.

After building, verify that metamodel classes are generated in the generated sources directory and that your IDE recognizes that directory as a source root. If the metamodel is not generated, queries referencing `Customer_.name` will fail to compile.

For small projects, string paths may suffice; for large codebases or frequent entity refactoring, the static metamodel provides stronger type safety.

## 8. Predicate: Query Logical Conditions

### 8.1. What Is Predicate?

A Predicate is a Boolean expression. It is typically placed in WHERE or HAVING:

```java
Predicate active = cb.equal(
    customer.get(Customer_.status),
    CustomerStatus.ACTIVE
);

Predicate nameContains = cb.like(
    cb.lower(customer.get(Customer_.name)),
    "%an%"
);

query.where(cb.and(active, nameContains));
```

A Predicate does not execute immediately upon creation. It is part of the query structure that the provider translates into SQL.

### 8.2. Dynamic Filters

A search use case often has many optional inputs. Do not build different queries by concatenating SQL strings. Add Predicates only when values are present:

```java
List<Predicate> predicates = new ArrayList<>();

if (status != null) {
    predicates.add(cb.equal(
        customer.get(Customer_.status),
        status
    ));
}

if (minAge != null) {
    predicates.add(cb.ge(
        customer.get(Customer_.age),
        minAge
    ));
}

if (keyword != null && !keyword.isBlank()) {
    String pattern = "%" + keyword.trim().toLowerCase(Locale.ROOT) + "%";

    predicates.add(cb.like(
        cb.lower(customer.get(Customer_.name)),
        pattern
    ));
}

query.where(cb.and(predicates.toArray(Predicate[]::new)));
```

If the list is empty, `cb.and()` with zero predicates has true semantics per the Criteria API. You can also use `cb.conjunction()` to explicitly express an always-true condition.

The LIKE snippet above illustrates substring search; if the user enters `%` or `_`, they still act as wildcards. If literal text matching is required, escape those two characters and pass the escape character to the appropriate `cb.like()` overload.

### 8.3. Handling Nulls

Do not use `cb.equal(path, null)` to express SQL IS NULL. Instead, use:

```java
Predicate noEmail =
    cb.isNull(customer.get(Customer_.email));

Predicate hasEmail =
    cb.isNotNull(customer.get(Customer_.email));
```

If a null filter means "do not apply this condition", skip adding the Predicate. If null means "find rows containing null", use `isNull()`. These two meanings must be distinguished in the API/service.

### 8.4. IN and NOT IN

Finding entities belonging to a set of values:

```java
Predicate selectedStatuses =
    customer.get(Customer_.status)
        .in(CustomerStatus.ACTIVE, CustomerStatus.PENDING);
```

You can also use CriteriaBuilder:

```java
Predicate selectedIds =
    cb.in(customer.get(Customer_.id))
      .value(10L)
      .value(20L)
      .value(30L);
```

If the input list is empty, define the business behavior explicitly: skip filtering, return empty, or reject the request. Do not let empty-list semantics implicitly dictate API output.

## 9. JOIN and JoinType

### 9.1. Joining Across Associations

Suppose Customer has a `@OneToMany` relationship to Order:

```java
@OneToMany(mappedBy = "customer")
private List<Order> orders = new ArrayList<>();
```

You can join:

```java
Join<Customer, Order> order =
    customer.join(Customer_.orders, JoinType.INNER);

Predicate paid = cb.equal(
    order.get(Order_.status),
    OrderStatus.PAID
);

query.select(customer)
     .where(paid)
     .distinct(true);
```

Common join types:

- `JoinType.INNER`: only returns roots with a matching related element.
- `JoinType.LEFT`: keeps the root even if there is no related element.
- `JoinType.RIGHT`: less common, and support depends on the provider/database.

Collection JOINs can multiply root rows. If one Customer has three matching Orders, the SQL join can yield three rows for that Customer. Use `distinct(true)` when results need each Customer once, and review the count query when paginating.

### 9.2. Difference Between Conditions in ON vs. WHERE

With a LEFT JOIN, placing a condition on the right-hand table inside WHERE can filter out rows without related elements, making the effective result behave like an INNER JOIN.

Example:

```java
Join<Customer, Order> orders =
    customer.join(Customer_.orders, JoinType.LEFT);

orders.on(
    cb.equal(orders.get(Order_.status), OrderStatus.PAID)
);
```

The `on()` condition restricts which Order rows are joined while still retaining Customers that have no PAID Orders. Replacing it with `query.where(cb.equal(orders.get(...), PAID))` causes rows with null Orders to fail the predicate.

Choose ON or WHERE according to business semantics, not just syntax.

### 9.3. Fetch vs. Join

`join()` participates in query conditions and structure. `fetch()` instructs the provider to load the association alongside the root entity to reduce lazy loading/N+1 queries. Fetch returns `Fetch`, not `Join`, so it cannot be used directly as a Path to build predicates in all cases.

In particular, combining a collection fetch join with pagination can multiply rows and make pagination unpredictable. Do not add fetch joins to every Specification; choose the fetch plan per use case and verify the count query.

## 10. Subqueries and EXISTS

The Criteria API supports subqueries inside a CriteriaQuery:

```java
CriteriaQuery<Customer> query =
    cb.createQuery(Customer.class);

Root<Customer> customer = query.from(Customer.class);

Subquery<Integer> paidOrderExists =
    query.subquery(Integer.class);

Root<Order> order = paidOrderExists.from(Order.class);

paidOrderExists.select(cb.literal(1));
paidOrderExists.where(
    cb.equal(order.get(Order_.customer), customer),
    cb.equal(order.get(Order_.status), OrderStatus.PAID)
);

query.select(customer)
     .where(cb.exists(paidOrderExists));
```

Meaning: find Customers who have at least one Order with status PAID.

EXISTS is often useful when you only need to check the existence of a related record. It avoids multiplying root rows like some collection joins. The optimizer may transform the execution plan; actual performance depends on indexes and the database.

You can use `cb.not(cb.exists(subquery))` to find Customers without matching Orders. Verify the correlation condition between the subquery and the outer root to avoid creating an unintended uncorrelated subquery.

## 11. GROUP BY, HAVING, and Aggregate Functions

The Criteria API supports functions such as `count`, `countDistinct`, `sum`, `avg`, `min`, and `max`.

Example counting orders per customer:

```java
CriteriaQuery<Tuple> query = cb.createTupleQuery();

Root<Customer> customer = query.from(Customer.class);

Join<Customer, Order> order =
    customer.join(Customer_.orders, JoinType.LEFT);

Expression<Long> orderCount = cb.count(order);

query.multiselect(
    customer.get(Customer_.id).alias("customerId"),
    customer.get(Customer_.name).alias("customerName"),
    orderCount.alias("orderCount")
);

query.groupBy(
    customer.get(Customer_.id),
    customer.get(Customer_.name)
);

query.having(cb.ge(orderCount, 3L));
```

The query returns Customers with at least three Orders. With a LEFT JOIN, `count(order)` counts non-null Order elements; `count(customer)` would count joined Customer rows and does not express the same meaning.

Distinguish:

- WHERE filters rows before grouping.
- GROUP BY defines the groups.
- HAVING filters results after grouping.
- COUNT/DISTINCT/SUM are aggregate expressions.

When a query uses GROUP BY, the count query for a Page must count the number of result groups, not the total source rows. A separate count query or an appropriate subquery may be needed.

## 12. DTO Projections with CriteriaBuilder.construct

The Criteria API can instantiate a DTO directly via its constructor:

```java
public record CustomerSummary(Long id, String name) {
}
```

Building the query:

```java
CriteriaQuery<CustomerSummary> query =
    cb.createQuery(CustomerSummary.class);

Root<Customer> customer = query.from(Customer.class);

query.select(
    cb.construct(
        CustomerSummary.class,
        customer.get(Customer_.id),
        customer.get(Customer_.name)
    )
);
```

The DTO constructor must match the count, order, and types of the Expressions passed in. Unlike interface projections, class-based projections rely on a constructor. DTOs are not managed entities; modifying returned objects does not automatically persist changes to the database.

For DTO constructors with many parameters, keep parameter order clear and test the mapping. If the constructor is incompatible, errors typically occur when the provider builds or parses the query.

## 13. Pagination and Counting Results with the Criteria API

The Criteria API itself does not accept a Pageable like a repository method. When manually building queries with EntityManager, apply offset and limit explicitly:

```java
TypedQuery<Customer> typedQuery =
    entityManager.createQuery(query);

typedQuery.setFirstResult(
    Math.toIntExact(pageable.getOffset())
);
typedQuery.setMaxResults(pageable.getPageSize());

List<Customer> content = typedQuery.getResultList();
```

`setFirstResult()` takes an int. Pageable's offset is a long; `Math.toIntExact` detects overflow instead of silently truncating values. APIs should bound page size and page index reasonably.

To build a Page, a separate count query is required:

```java
CriteriaQuery<Long> countCriteria =
    cb.createQuery(Long.class);

Root<Customer> countRoot =
    countCriteria.from(Customer.class);

List<Predicate> countPredicates =
    buildPredicates(cb, countRoot, filter);

countCriteria.select(cb.count(countRoot))
             .where(cb.and(
                 countPredicates.toArray(Predicate[]::new)
             ));

long total = entityManager.createQuery(countCriteria)
    .getSingleResult();

return new PageImpl<>(content, pageable, total);
```

`buildPredicates` must build fresh predicates from `countRoot`. Never reuse Predicates created from the content query's Root, because Paths and Roots are bound to the query that created them.

If the content query joins a collection and can produce duplicate Customers, the count query needs `cb.countDistinct(countRoot)` or EXISTS to count unique Customers accurately. Content and count must apply the exact same filter conditions, tenant/access scope, and business semantics.

With Specification and paging-capable repositories, Spring Data can generate the count query automatically. Even so, if the Specification adds fetch joins or complex distinct behavior, inspect the actual count SQL.

## 14. CriteriaUpdate and CriteriaDelete

The Criteria API is not limited to SELECT. Jakarta Persistence also provides bulk updates and deletes.

### 14.1. CriteriaUpdate

Example updating inactive Customer statuses:

```java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();

CriteriaUpdate<Customer> update =
    cb.createCriteriaUpdate(Customer.class);

Root<Customer> customer = update.from(Customer.class);

update.set(
    Customer_.status,
    CustomerStatus.INACTIVE
);

update.where(
    cb.lessThan(
        customer.get(Customer_.lastLoginAt),
        cutoff
    )
);

int affected = entityManager.createQuery(update)
    .executeUpdate();
```

The return value is the number of affected rows reported by the database/provider. Bulk updates execute directly on a set basis without loading each Customer entity or dirty-checking individual objects.

### 14.2. CriteriaDelete

```java
CriteriaDelete<Customer> delete =
    cb.createCriteriaDelete(Customer.class);

Root<Customer> customer = delete.from(Customer.class);

delete.where(
    cb.equal(
        customer.get(Customer_.status),
        CustomerStatus.DELETED
    )
);

int affected = entityManager.createQuery(delete)
    .executeUpdate();
```

Bulk updates/deletes have important limitations:

- Do not perform cascade removes like individual entity removals.
- Do not invoke entity lifecycle callbacks such as `@PreUpdate` or `@PreRemove` per entity.
- Do not synchronize the state of managed entities currently in the persistence context.
- May leave stale data in first-level/second-level caches.
- Database foreign key constraints still apply.

Before bulk operations, you typically need to flush pending changes. Afterward, consider clearing the persistence context or refreshing affected entities to avoid reading stale state. Run within a transaction and explicitly account for dependent relationships.

## 15. Using the Criteria API Inside Spring Data Specification

### 15.1. Specification Is the Bridge

Spring Data JPA defines Specification with the callback:

```java
public interface Specification<T> {
    Predicate toPredicate(
        Root<T> root,
        CriteriaQuery<?> query,
        CriteriaBuilder criteriaBuilder
    );
}
```

This is a simplified signature; the actual interface includes default methods for combining Specifications. The three parameters passed in are precisely the Criteria API components covered above.

The repository must extend `JpaSpecificationExecutor`:

```java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
```

### 15.2. Creating a Simple Specification

```java
public static Specification<Customer> hasStatus(
        CustomerStatus status) {

    return (root, query, cb) -> {
        if (status == null) {
            return cb.conjunction();
        }

        return cb.equal(
            root.get(Customer_.status),
            status
        );
    };
}
```

A Specification returns a Predicate; it does not execute the query. Spring Data integrates the Predicate into the query generated by the repository.

### 15.3. Combining Conditions

```java
public static Specification<Customer> nameContains(String keyword) {
    return (root, query, cb) -> {
        if (keyword == null || keyword.isBlank()) {
            return cb.conjunction();
        }

        String pattern =
            "%" + keyword.trim().toLowerCase(Locale.ROOT) + "%";

        return cb.like(
            cb.lower(root.get(Customer_.name)),
            pattern
        );
    };
}

public static Specification<Customer> ageAtLeast(Integer age) {
    return (root, query, cb) -> age == null
        ? cb.conjunction()
        : cb.ge(root.get(Customer_.age), age);
}
```

The service combines them:

```java
Specification<Customer> specification =
    hasStatus(CustomerStatus.ACTIVE)
        .and(nameContains("an"))
        .and(ageAtLeast(18));

Page<Customer> page =
    customerRepository.findAll(
        specification,
        PageRequest.of(0, 20, Sort.by("name").ascending())
    );
```

Specifications can be reused and combined as needed. Use `.or(...)` for OR, or `.not(...)` for negation depending on your Spring Data version's API.

### 15.4. Avoiding Risky Side Effects in Specifications

Specifications are frequently used for both the content query and the count query when paginating. Therefore, do not arbitrarily add fetch joins, custom selections, ordering, or grouping to every Specification without considering the query type being generated.

For instance, a collection fetch can cause errors or inaccurate results when Spring Data builds the count query. If you need a specific fetch plan, separate the query or use EntityGraph/custom repositories. Predicates should stay focused on filter criteria; special structural query modifications should be explicitly controlled.

## 16. A Complete Criteria API Example in a Custom Repository

The example below illustrates grouping filters, sorting, and pagination in a custom repository. The Customer, CustomerFilter, and Customer_ classes must be declared/generated in the project.

```java
@Repository
public class CustomerSearchRepository {

    @PersistenceContext
    private EntityManager entityManager;

    public Page<Customer> search(
            CustomerFilter filter,
            Pageable pageable) {

        CriteriaBuilder cb =
            entityManager.getCriteriaBuilder();

        CriteriaQuery<Customer> criteria =
            cb.createQuery(Customer.class);

        Root<Customer> root =
            criteria.from(Customer.class);

        List<Predicate> predicates =
            buildPredicates(cb, root, filter);

        criteria.select(root)
                .where(cb.and(
                    predicates.toArray(Predicate[]::new)
                ));

        List<jakarta.persistence.criteria.Order> orders =
            new ArrayList<>();

        orders.add(cb.asc(root.get(Customer_.name)));
        orders.add(cb.asc(root.get(Customer_.id)));

        criteria.orderBy(orders);

        TypedQuery<Customer> typedQuery =
            entityManager.createQuery(criteria);

        typedQuery.setFirstResult(
            Math.toIntExact(pageable.getOffset())
        );
        typedQuery.setMaxResults(pageable.getPageSize());

        List<Customer> content = typedQuery.getResultList();

        CriteriaQuery<Long> countCriteria =
            cb.createQuery(Long.class);

        Root<Customer> countRoot =
            countCriteria.from(Customer.class);

        List<Predicate> countPredicates =
            buildPredicates(cb, countRoot, filter);

        countCriteria.select(cb.count(countRoot))
                     .where(cb.and(
                         countPredicates.toArray(Predicate[]::new)
                     ));

        long total = entityManager.createQuery(countCriteria)
            .getSingleResult();

        return new PageImpl<>(content, pageable, total);
    }

    private List<Predicate> buildPredicates(
            CriteriaBuilder cb,
            Root<Customer> root,
            CustomerFilter filter) {

        List<Predicate> predicates = new ArrayList<>();

        if (filter.status() != null) {
            predicates.add(cb.equal(
                root.get(Customer_.status),
                filter.status()
            ));
        }

        if (filter.keyword() != null
                && !filter.keyword().isBlank()) {
            String pattern = "%"
                + filter.keyword().trim().toLowerCase(Locale.ROOT)
                + "%";

            predicates.add(cb.like(
                cb.lower(root.get(Customer_.name)),
                pattern
            ));
        }

        if (filter.minAge() != null) {
            predicates.add(cb.ge(
                root.get(Customer_.age),
                filter.minAge()
            ));
        }

        return predicates;
    }
}
```

This is a custom repository skeleton, not a standalone program. Corresponding Jakarta Persistence, Spring Data, collection, DTO/filter, and entity imports are required.

The example uses a fixed sort by name then id to guarantee deterministic ordering. If clients are allowed to choose sort fields, map properties through an allowlist; never accept arbitrary property names directly from a request. If the filter uses a collection JOIN, adjust the count query to avoid double-counting root entities.

## 17. Common Errors When Using the Criteria API

| Error | Cause | Solution |
|---|---|---|
| Previous condition disappears | Calling `where()` multiple times | Collect Predicates and call `where()` once |
| Property not found | Typo in `get("...")` | Use the static metamodel |
| Query returns duplicate entities | Collection JOIN produces multiple root rows | Use distinct or EXISTS |
| Count exceeds logical content | `Count(*)` after a one-to-many JOIN | Count distinct roots or write count with EXISTS |
| LEFT JOIN behaves like INNER JOIN | Right-hand condition placed in WHERE | Move appropriate condition into `Join.on()` |
| Predicate uses wrong Root | Reusing Predicates from another query | Create fresh Paths/Predicates per Root |
| Null filter behaves wrongly | Confusing "skip filter" with IS NULL | Skip predicate or use `isNull` explicitly |
| LIKE matches too broadly | `%` and `_` from input not escaped | Escape wildcards when literal search is needed |
| Unstable pagination | ORDER BY lacks tie-breaker | Add unique property such as ID |
| Count query fails with fetch join | Specification applies fetch in count query too | Separate fetch plan from shared predicates |
| Bulk update reads stale data | Persistence context not auto-synchronized | Flush and clear/refresh appropriately |
| Database-dependent query | Using dialect-specific functions or types | Integration-test against target database |

## 18. Testing and Optimization

Because the Criteria API builds dynamic queries, tests must cover filter combinations rather than only the default case.

Recommended test cases:

- No filters applied.
- Each individual filter.
- Multiple filters combined with AND and OR.
- Null values, empty strings, and empty lists.
- Joins with no related data.
- A single root with multiple matching children.
- EXISTS and NOT EXISTS.
- DISTINCT, GROUP BY, and HAVING.
- Content and count queries applying identical conditions.
- Multi-field sorting and tie-breakers.
- Bulk update/delete with managed entities.

Use `@DataJpaTest` for testing repositories and the persistence layer. If queries rely on database-specific functions, collations, types, or execution plans, run integration tests against the same database engine as production.

To optimize, inspect the generated SQL and execution plan. The Criteria API does not make queries inherently faster than JPQL; the provider translates both into SQL. Performance depends on query structure, indexes, row counts, joins, selectivity, and database optimization.

Avoid building one overly generic query with dozens of optional predicates if different branches prevent effective SQL optimization. Split use cases into distinct, clear queries when conditions and access patterns differ substantially.

## 19. When Should You Use the Criteria API?

The Criteria API is suitable when:

- Filters vary across many optional inputs.
- Nested AND/OR combinations are needed.
- Dynamic joins or subqueries are required.
- Predicates need to be reused across multiple queries.
- Dynamic projections, aggregates, or differing return types must be constructed.
- You want to use Spring Data Specification for a search API.

JPQL or derived queries are usually more readable when queries are fixed and simple. Native SQL fits database-specific features or fine-grained SQL control. Do not use the Criteria API for every query simply because it is flexible.

## 20. Pre-Production Checklist for Criteria Queries

- [ ] CriteriaQuery result type matches the intended entity/DTO/scalar.
- [ ] Root represents the right source entity.
- [ ] Paths reference the correct properties and types.
- [ ] Static metamodel is generated from the right entity version.
- [ ] Predicates are combined properly without being overwritten by `where()`.
- [ ] Null and empty strings have clear semantics.
- [ ] LIKE wildcards are escaped when literal matching is needed.
- [ ] Collection JOINs do not unintentionally duplicate root rows.
- [ ] LEFT JOIN uses ON/WHERE according to intended semantics.
- [ ] Count query counts the right result unit.
- [ ] Pageable has valid page size/offset and deterministic sorting.
- [ ] Specifications do not create fetch/count query conflicts.
- [ ] Bulk operations handle cascades, callbacks, and the persistence context.
- [ ] SQL and execution plans have been verified on the target database.

## 21. Conclusion

The Criteria API is a way to construct JPA queries with typed objects. `CriteriaBuilder` creates expressions and operations; `CriteriaQuery` describes SELECT, WHERE, GROUP BY, HAVING, and ORDER BY; `Root` represents the entity in FROM; `Path` accesses properties; and `Predicate` expresses logical conditions. Joins and Subqueries extend querying across associations and complex rules.

In Spring Data JPA, Specification uses those same Root, CriteriaQuery, and CriteriaBuilder abstractions to build composable, reusable Predicates. For dynamic queries, collect conditions and apply them together, use the static metamodel where practical, control duplicates from JOINs, and build accurate count queries for pagination. Bulk updates and deletes have different semantics from normal entity operations, so manage transactions and the persistence context carefully.

Choose the Criteria API when queries genuinely require dynamism and composability. For fixed queries, JPQL or derived queries are often clearer. Whichever approach you pick, test the results and verify the SQL and execution plan on your deployment database.
