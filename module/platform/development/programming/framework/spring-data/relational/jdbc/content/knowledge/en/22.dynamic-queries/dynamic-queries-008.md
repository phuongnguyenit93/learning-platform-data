# Distinguishing Spring Data Relational Criteria from JPA Criteria, Specification, and Querydsl

In Java applications, there are multiple ways to describe query conditions without manually concatenating SQL strings. Their names sound similar, yet **Spring Data Relational Criteria**, **JPA Criteria API**, **Spring Data JPA Specification**, and **Querydsl** are distinct abstractions built for different persistence models.

With **Spring Data JDBC**, Criteria belongs to Spring Data Relational and is typically paired with **Query** and **JdbcAggregateTemplate** to create dynamic filters on aggregates. JPA Criteria and Specification are built on the Jakarta Persistence (JPA) model, whereas Querydsl is a standalone DSL library that integrates with several backends. You cannot take a JPA Specification or Querydsl JPA example and drop it straight into Spring Data JDBC.

This lesson compares the purpose, APIs, capabilities, and selection criteria of each tool, alongside side-by-side examples to highlight their differences.

## 1. Four Names, Four Roles

| Tool | Ecosystem | Primary Purpose | Typical Usage |
|---|---|---|---|
| **Spring Data Relational Criteria** | Spring Data Relational, used by Spring Data JDBC | Describe structured predicates for queries/updates on mapped relational data | Build Criteria, wrap in Query, call JdbcAggregateTemplate |
| **JPA Criteria API** | Jakarta Persistence / JPA | Build JPA queries via an object API with Root, Path, Join, Predicate, and subqueries | EntityManager + CriteriaBuilder + CriteriaQuery |
| **Spring Data JPA Specification** | Spring Data JPA | Package JPA predicates into composable, reusable units | Specification<T> + JpaSpecificationExecutor |
| **Querydsl** | Independent query DSL library | Build queries using a fluent API and generated Q-types from models | Querydsl JPA or Querydsl SQL via corresponding integration |

The name Criteria in Spring Data Relational does not mean it is a stripped-down JPA Criteria API sharing the same interfaces. The two APIs do not share types such as CriteriaBuilder, CriteriaQuery, Root, or EntityManager.

Similarly, Specification is not a universal feature of every Spring Data repository. Specification is common in Spring Data JPA because it builds on top of the JPA Criteria API. Spring Data JDBC does not provide JpaSpecificationExecutor on JdbcAggregateTemplate.

## 2. What Is Spring Data Relational Criteria?

Spring Data Relational provides classes in package org.springframework.data.relational.core.query, notably Criteria and Query. Criteria describes filter conditions; Query combines those conditions with sorting, limit, offset, and other query options.

Example aggregate root:

~~~java
import java.math.BigDecimal;
import java.time.LocalDateTime;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        String orderNumber,
        String status,
        BigDecimal total,
        LocalDateTime createdAt
) {}
~~~

Building Criteria:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;

Criteria criteria = Criteria.where("status").is("OPEN")
        .and("total").greaterThanOrEquals(new BigDecimal("100.00"));

Query query = Query.query(criteria);
~~~

This Criteria expresses the condition:

~~~sql
WHERE status = ?
  AND total >= ?
~~~

Condition values are bound via JDBC; there is no need to concatenate user data into SQL strings.

To execute, inject JdbcAggregateTemplate:

~~~java
import java.util.List;
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;

List<PurchaseOrder> orders =
        template.findAll(query, PurchaseOrder.class);
~~~

The template uses Spring Data Relational metadata to map results back to the PurchaseOrder aggregate root. This differs from custom SQL queries returning flat rows or DTOs.

### Common Predicates

Depending on the Spring Data Relational version, Criteria offers common comparisons and checks such as:

| Predicate | Meaning |
|---|---|
| is(value) | Equals value |
| not(value) | Not equal to value |
| greaterThan(value) | Greater than |
| greaterThanOrEquals(value) | Greater than or equal to |
| lessThan(value) | Less than |
| lessThanOrEquals(value) | Less than or equal to |
| between(from, to) | Within range |
| in(values) | In a set of values |
| like(pattern) | Matches LIKE pattern |
| isNull() / isNotNull() | Checks for NULL |
| and(...) / or(...) | Combines conditions |

Example:

~~~java
Criteria criteria = Criteria.where("status").in(List.of("OPEN", "PENDING"))
        .and("createdAt").greaterThanOrEquals(from)
        .and("createdAt").lessThan(to);
~~~

Property names in Criteria must resolve against the aggregate's mapping. In the example above, Java properties and physical column names align closely; if a project uses @Column or a custom naming strategy, inspect metadata and generated SQL to confirm names map properly.

## 3. How Do Query, Sort, and Pageable Work with Criteria?

Criteria only holds conditions. Query wraps Criteria alongside ordering and result bounds:

~~~java
import org.springframework.data.domain.PageRequest;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.relational.core.query.Query;

Criteria criteria = Criteria.where("status").is("OPEN");
Query baseQuery = Query.query(criteria);

Sort sort = Sort.by(
        Sort.Order.desc("createdAt"),
        Sort.Order.asc("id")
);

Pageable pageable = PageRequest.of(0, 20, sort);
Query pageQuery = baseQuery.with(pageable);

List<PurchaseOrder> content =
        template.findAll(pageQuery, PurchaseOrder.class);
~~~

Query.with(pageable) applies sort, offset, and limit into a new Query. Query is immutable, so you must keep the object returned by fluent calls.

If you need the total element count to construct a Page, count against the original unpaginated query:

~~~java
long total = template.count(baseQuery, PurchaseOrder.class);
Page<PurchaseOrder> page = new PageImpl<>(content, pageable, total);
~~~

Do not pass pageQuery to count when you want the total matching records across all pages, because pageQuery already contains page limit and offset.

### Building Criteria from Optional Filters

A search screen might send status, minimum amount, and start time. Add predicates only when the user actually provides values:

~~~java
Criteria criteria = Criteria.empty();

if (status != null && !status.isBlank()) {
    criteria = criteria.and("status").is(status);
}

if (minimumTotal != null) {
    criteria = criteria.and("total")
            .greaterThanOrEquals(minimumTotal);
}

if (createdAfter != null) {
    criteria = criteria.and("createdAt")
            .greaterThanOrEquals(createdAfter);
}

Query query = Query.query(criteria);
~~~

Operations building Criteria return a new expression; reassign the variable. Exact APIs for empty Criteria and chaining the first predicate may vary across versions; if your project uses a version with restrictions on Criteria.empty(), collect predicates and combine them using that version's supported Criteria API.

Criteria fits relational filters supported by QueryMapper and the dialect. It is not a universal API capable of describing every possible SQL query.

## 4. How Does Spring Data Relational Criteria Differ from the JPA Criteria API?

The JPA Criteria API is Jakarta Persistence's object-oriented query API. It operates on entities, attributes, associations, and JPA query clauses.

Example JPA entity:

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrderEntity {
    @Id
    private Long id;

    private String status;

    private BigDecimal total;
}
~~~

A JPA Criteria query can be written as:

~~~java
CriteriaBuilder cb = entityManager.getCriteriaBuilder();
CriteriaQuery<PurchaseOrderEntity> cq =
        cb.createQuery(PurchaseOrderEntity.class);

Root<PurchaseOrderEntity> root = cq.from(PurchaseOrderEntity.class);

Predicate statusIsOpen =
        cb.equal(root.get("status"), "OPEN");

Predicate totalAtLeast =
        cb.greaterThanOrEqualTo(
                root.get("total"),
                new BigDecimal("100.00")
        );

cq.select(root).where(cb.and(statusIsOpen, totalAtLeast));

List<PurchaseOrderEntity> result =
        entityManager.createQuery(cq).getResultList();
~~~

In JPA Criteria:

- EntityManager supplies CriteriaBuilder.
- CriteriaBuilder creates predicates and expressions.
- Root represents the root entity in the query.
- Path accesses entity attributes.
- Join describes entity associations.
- CriteriaQuery describes select, where, group by, order by, and other query parts.
- Subqueries and more complex expressions can be constructed.

Spring Data Relational Criteria has a narrower scope. It usually starts with string property names, builds predicates for Query, and then Query is passed to JdbcAggregateTemplate to read aggregates. There is no EntityManager, CriteriaBuilder, Root, or JPA persistence context in that execution path.

| Aspect | Spring Data Relational Criteria | JPA Criteria API |
|---|---|---|
| Query target | Spring Data Relational aggregate mapping | JPA Entity |
| Entry point | Criteria.where(...), Query.query(...) | EntityManager, CriteriaBuilder |
| Property reference | Typically string property names | Path from Root/Join; optional static metamodel |
| Entity joins | Not a general join API equivalent to JPA | Supports Root.join(...) |
| Subqueries | Not a primary goal of relational Criteria | Supports subqueries |
| Integration | JdbcAggregateTemplate and Spring Data JDBC | JPA provider and EntityManager |
| Persistence context | No JPA-style persistence context | Entities managed in a persistence context |

Do not import jakarta.persistence.criteria.CriteriaBuilder in Spring Data JDBC code just because both APIs contain the word Criteria. They are type-incompatible and not interchangeable.

## 5. What Is JPA Specification?

Spring Data JPA Specification is an abstraction that packages a JPA predicate into a composable, reusable unit. It lives in package org.springframework.data.jpa.domain and uses the JPA Criteria API under the hood.

Example:

~~~java
import org.springframework.data.jpa.domain.Specification;

public final class PurchaseOrderSpecifications {

    public static Specification<PurchaseOrderEntity> hasStatus(String status) {
        return (root, query, cb) ->
                status == null ? cb.conjunction()
                        : cb.equal(root.get("status"), status);
    }

    public static Specification<PurchaseOrderEntity> totalAtLeast(
            BigDecimal minimum) {
        return (root, query, cb) ->
                minimum == null ? cb.conjunction()
                        : cb.greaterThanOrEqualTo(root.get("total"), minimum);
    }
}
~~~

JPA Repository:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface PurchaseOrderJpaRepository
        extends JpaRepository<PurchaseOrderEntity, Long>,
                JpaSpecificationExecutor<PurchaseOrderEntity> {
}
~~~

Composing specifications:

~~~java
Specification<PurchaseOrderEntity> spec =
        Specification.where(
                PurchaseOrderSpecifications.hasStatus("OPEN"))
        .and(PurchaseOrderSpecifications.totalAtLeast(
                new BigDecimal("100.00")));

List<PurchaseOrderEntity> result =
        purchaseOrderJpaRepository.findAll(spec);
~~~

Specification extracts predicates into functions composable with and, or, and not. It is especially useful when many filters are reused across multiple JPA queries.

### Why Can't Specification Be Passed to JdbcAggregateTemplate?

Specification's signature depends on JPA types such as Root, CriteriaQuery, CriteriaBuilder, and Predicate. JdbcAggregateTemplate expects a Spring Data Relational Query. The two APIs have different models and types.

Consequently, you cannot do this:

~~~java
Specification<PurchaseOrderEntity> spec = ...;
template.findAll(spec, PurchaseOrder.class); // No matching API
~~~

If the application uses Spring Data JDBC, build Spring Data Relational Criteria/Query or implement a suitable custom repository/SQL query. If the application uses Spring Data JPA, Specification is the natural choice for composing JPA predicates.

## 6. Querydsl: Fluent Query DSL and Generated Q-Types

Querydsl is an independent library providing a fluent query API. In common integrations, an annotation processor generates Q-classes representing models, such as QPurchaseOrderEntity. Rather than writing property names as strings, code references properties through typed fields.

Illustrative Querydsl JPA example:

~~~java
QPurchaseOrderEntity order =
        QPurchaseOrderEntity.purchaseOrderEntity;

BooleanBuilder predicate = new BooleanBuilder();

if (status != null) {
    predicate.and(order.status.eq(status));
}

if (minimumTotal != null) {
    predicate.and(order.total.goe(minimumTotal));
}

List<PurchaseOrderEntity> result =
        queryFactory.selectFrom(order)
                .where(predicate)
                .fetch();
~~~

QPurchaseOrderEntity is generated from the entity/model by Querydsl annotation processing. IDEs and compilers can catch misspelled property names or type mismatches earlier than with string-based Criteria DSLs.

Querydsl supports multiple backends, among which you must distinguish:

- **Querydsl JPA** builds queries over the JPA model using an entity manager/provider.
- **Querydsl SQL** builds SQL directly using table/column metadata and JDBC connections/SQL templates.

These two backends do not share the same contract. Having Q-types for JPA entities does not mean you can use them with Querydsl SQL or Spring Data JDBC without corresponding configuration.

## 7. Does Spring Data JDBC Provide Built-In Querydsl Support Like Spring Data JPA?

Spring Data JPA has well-known integration via QuerydslPredicateExecutor and related repository mechanisms. Do not assume Spring Data JDBC offers the same built-in integration or that JdbcAggregateTemplate has overloads accepting Querydsl Predicate.

If you want to use Querydsl in a Spring Data JDBC application, you can consider Querydsl SQL as a separate SQL library wired through a custom repository fragment/JDBC access. When doing so, the application becomes responsible for:

- Mapping SQL results to DTOs or domain objects.
- Table/column names and dialects.
- Transaction management and participating in active transactions.
- Data type conversions and nullability.
- Optimistic locking if update statements require version checks.
- Child relationships and aggregate persistence rules.

Querydsl SQL does not automatically act as a Spring Data JDBC aggregate write path. A direct SQL query does not invoke JdbcAggregateTemplate lifecycles or apply all mapping/aggregate rules.

Therefore, choose Querydsl SQL only when its expressiveness, type safety, or SQL complexity justifies the extra integration and mapping effort.

## 8. Comparing Capabilities and Type Safety

| Criterion | Relational Criteria | JPA Criteria / Specification | Querydsl |
|---|---|---|---|
| Fluent API | Yes | Yes | Yes |
| Property type safety | More limited because property names are typically strings | Can use static metamodel; Root/Path API checks types at expression level | Strong when Q-types are properly generated |
| Dynamic condition composition | Yes, for supported predicates | Yes, Specification and Predicate | Yes, BooleanBuilder/Predicate |
| Arbitrary joins | Not the primary goal of aggregate Criteria | Yes, via Root/Join | Yes, depending on backend |
| Subqueries | Not a general API | Yes | Yes, depending on backend |
| Spring Data JDBC aggregate mapping | Yes, via JdbcAggregateTemplate | No | Not automatic |
| Repository integration | Spring Data JDBC/Relational template | JpaSpecificationExecutor, JPA repositories | Depends on backend and integration |
| Code generation | No Q-types required | Optional JPA static metamodel generator | Q-types generated by annotation processor |
| Complex custom SQL | Use @Query/custom JDBC when needed | Provider generates SQL from Criteria | Querydsl SQL generates SQL via SQL backend |

No single tool wins in every scenario. The right choice depends on the persistence model and query complexity.

## 9. When to Use Spring Data Relational Criteria?

Choose Spring Data Relational Criteria when:

- The application uses Spring Data JDBC.
- Queries mainly filter on aggregate root properties.
- Conditions must be built dynamically from optional parameters.
- Query needs to combine with Sort, limit, offset, or Pageable.
- Expected results are aggregates mapped by Spring Data JDBC from metadata.
- General SQL JOIN/subquery expressions are not required.

Example:

~~~java
Criteria criteria = Criteria.where("status").is(status)
        .and("total").between(minimum, maximum);

Query query = Query.query(criteria)
        .sort(Sort.by(Sort.Order.desc("createdAt")));

List<PurchaseOrder> orders =
        template.findAll(query, PurchaseOrder.class);
~~~

This is the natural choice for moderately complex aggregate filters requiring dynamic queries.

## 10. When to Use JPA Criteria and Specification?

Choose JPA Criteria/Specification when the application actually uses Spring Data JPA and needs:

- Composing reusable predicates across multiple use cases.
- Entity and association joins.
- Subqueries, group by, having, or complex JPA expressions.
- Leveraging JpaSpecificationExecutor with Page, Sort, or JPA queries.
- Working with entities managed by a JPA persistence context.

Example search screen with several optional filters:

~~~java
Specification<PurchaseOrderEntity> spec =
        Specification.where(hasStatus(status))
                .and(totalAtLeast(minimumTotal))
                .and(createdAfter(from));

Page<PurchaseOrderEntity> page =
        repository.findAll(spec, pageable);
~~~

Do not introduce Specification into a Spring Data JDBC module just because it is named "Specification". It is a JPA abstraction tied to JPA Criteria types.

## 11. When to Use Querydsl?

Querydsl fits when:

- Queries have many dynamic branches and you want stronger type safety than string property names.
- The application requires complex dynamic JOINs, subqueries, projections, or dynamic SQL.
- The Querydsl backend is clearly chosen: JPA or SQL.
- The project accepts configuring annotation processors and generated Q-types.
- You can manage mapping, transactions, and lifecycles appropriate to that backend.

If the application uses Spring Data JDBC, Querydsl SQL can be a custom option for complex read/reporting queries. However, if queries only filter a few aggregate root properties, adding Querydsl can introduce more configuration overhead than value.

## 12. Choosing for a Concrete Use Case

Suppose an order search screen has filters for status, total amount range, creation time, sorting, and pagination:

| Need | Suitable Choice |
|---|---|
| Spring Data JDBC, filter a few root properties | Criteria + Query + JdbcAggregateTemplate |
| Spring Data JDBC, fixed, readable method | Derived repository query |
| Spring Data JDBC, complex SQL JOINs/reports | @Query or custom repository fragment/JdbcTemplate |
| Spring Data JPA, reusable predicates | Specification + JpaSpecificationExecutor |
| Spring Data JPA, complex dynamic type-safe queries | Querydsl JPA |
| Direct SQL, type-safe query DSL with custom mapping acceptable | Querydsl SQL/custom repository |

Practical rule of thumb:

1. Use repository derived methods for stable, short, readable conditions.
2. Use Relational Criteria for moderate dynamic aggregate filters in Spring Data JDBC.
3. Use @Query or custom JDBC fragments when specific SQL, JOINs, or projections are needed.
4. Use Specification when the persistence layer is JPA.
5. Use Querydsl when the value of a type-safe DSL outweighs configuration and backend integration cost.

## 13. Do Not Mix Abstractions in the Same Method

These types belong to different packages and models:

~~~java
org.springframework.data.relational.core.query.Criteria
org.springframework.data.relational.core.query.Query

jakarta.persistence.criteria.CriteriaBuilder
jakarta.persistence.criteria.CriteriaQuery
org.springframework.data.jpa.domain.Specification

com.querydsl.core.types.Predicate
com.querydsl.core.BooleanBuilder
~~~

A method expecting a Spring Data Relational Query cannot accept a JPA Specification or Querydsl Predicate without a custom adapter. Nor can you pass a JPA Root into Spring Data Relational's Criteria.where.

If a codebase uses both Spring Data JDBC and Spring Data JPA, keep each abstraction in its proper module/repository. Avoid creating a generic interface named Criteria that returns incompatible types, as callers will find it unclear which persistence technology executes the query.

## 14. Limitations of Relational Criteria to Remember

Spring Data Relational Criteria is intentionally smaller than a general-purpose query language:

- It describes predicates and query properties supported by Spring Data Relational.
- QueryMapper translates metadata and Criteria into dialect-specific SQL.
- It fits mapped aggregate queries, not an API for assembling arbitrary multi-root JOINs like JPA Criteria.
- There is no persistence context, dirty checking, or JPA association traversal.
- It does not provide the full feature set of Specification or Querydsl.
- When projections or complex SQL are needed, use @Query, custom fragments, JdbcTemplate, or a dedicated SQL DSL.

Do not confuse this limitation with an inability for Spring Data JDBC to run SQL JOINs. JDBC can execute JOINs through @Query or custom JDBC code; the distinction is that the aggregate template's Criteria/Query is not a general DSL for arbitrary joins and mappings.

## 15. Controlling Property Names, Data Types, and Input Values

Criteria commonly accepts property names as Strings. This is convenient, though the compiler cannot catch every typo at compile time:

~~~java
Criteria.where("stauts").is("OPEN"); // Typo, may only surface at runtime
~~~

Use constants or helpers when property names appear in multiple places, while still verifying metadata and actual queries. For properties with @Column, embedded prefixes, or custom naming strategies, know how names resolve in the mapping.

Input values should be validated before building Criteria:

~~~java
if (minimumTotal != null && minimumTotal.signum() < 0) {
    throw new IllegalArgumentException("minimumTotal must not be negative");
}
~~~

Never accept arbitrary property names or sort expressions from requests and pass them directly into Criteria/Sort. Whitelist allowed fields. Condition values are safely bound, whereas property names are query metadata and must be controlled separately.

## 16. Complete Example: Search Service with Criteria

The example below combines optional conditions, sorting, and pagination. It uses Spring Data Relational Criteria, not JPA Specification:

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.PageImpl;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jdbc.core.JdbcAggregateTemplate;
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class PurchaseOrderSearchService {
    private final JdbcAggregateTemplate template;

    public PurchaseOrderSearchService(JdbcAggregateTemplate template) {
        this.template = template;
    }

    @Transactional(readOnly = true)
    public Page<PurchaseOrder> search(
            String status,
            BigDecimal minimumTotal,
            Pageable pageable
    ) {
        Criteria criteria = Criteria.empty();

        if (status != null && !status.isBlank()) {
            criteria = criteria.and("status").is(status);
        }

        if (minimumTotal != null) {
            criteria = criteria.and("total")
                    .greaterThanOrEquals(minimumTotal);
        }

        Query baseQuery = Query.query(criteria);
        List<PurchaseOrder> content = template.findAll(
                baseQuery.with(pageable),
                PurchaseOrder.class
        );
        long total = template.count(baseQuery, PurchaseOrder.class);

        return new PageImpl<>(content, pageable, total);
    }
}
~~~

This is an intentional implementation for when Spring Data JDBC needs a Page. Check the Criteria.empty() API and predicate chaining behavior against your project's Spring Data Relational version; if that version does not support this initialization/chaining style, initialize Criteria from the first predicate and append remaining conditions.

## 17. Common Misconceptions

| Misconception | Accurate Understanding |
|---|---|
| Relational Criteria is the JPA Criteria API | Two independent APIs with different packages and execution models |
| Specification works with every Spring Data repository | Standard Specification belongs to Spring Data JPA and relies on JPA Criteria |
| JdbcAggregateTemplate accepts Specification | The template accepts Spring Data Relational Query/Criteria |
| Querydsl always integrates out of the box with all Spring Data modules | Integration depends on module/backend; QuerydslPredicateExecutor is not available by default for Spring Data JDBC |
| Querydsl SQL automatically maps Spring Data JDBC aggregates | Querydsl SQL is a separate SQL path; mapping and lifecycle must be handled explicitly |
| Relational Criteria can build any JOIN like JPA | Aggregate Criteria has a narrower scope; use SQL/custom fragments for complex JOINs |
| Criteria is as type-safe as Querydsl Q-types | Property names are typically Strings, so typos may only appear at runtime |
| Querydsl is always better than Criteria | A richer DSL carries configuration and integration costs; choose based on actual complexity |

## 18. Practice Exercise Comparing Three Styles

For the use case of finding open orders with a total of at least 100:

**A. Spring Data JDBC Relational Criteria**

~~~java
Criteria criteria = Criteria.where("status").is("OPEN")
        .and("total").greaterThanOrEquals(new BigDecimal("100.00"));

List<PurchaseOrder> result = template.findAll(
        Query.query(criteria),
        PurchaseOrder.class
);
~~~

**B. Spring Data JPA Specification**

~~~java
Specification<PurchaseOrderEntity> spec =
        Specification.where(hasStatus("OPEN"))
                .and(totalAtLeast(new BigDecimal("100.00")));

List<PurchaseOrderEntity> result = jpaRepository.findAll(spec);
~~~

**C. Querydsl JPA**

~~~java
QPurchaseOrderEntity order =
        QPurchaseOrderEntity.purchaseOrderEntity;

List<PurchaseOrderEntity> result = queryFactory.selectFrom(order)
        .where(
                order.status.eq("OPEN"),
                order.total.goe(new BigDecimal("100.00"))
        )
        .fetch();
~~~

Comparison:

- A returns Spring Data JDBC aggregates via JdbcAggregateTemplate.
- B builds reusable JPA predicates executed via JpaSpecificationExecutor.
- C uses Q-types and Querydsl JPA to build type-safe predicates.

Do not combine all three snippets into one repository method. Each snippet belongs to a specific persistence stack and requires its corresponding setup.

## 19. Principles to Remember

- Spring Data Relational Criteria is a small DSL for building conditions for Query and Spring Data JDBC operations.
- Query combines Criteria with sort, limit, offset, and other query options; JdbcAggregateTemplate executes queries on aggregates.
- JPA Criteria API uses CriteriaBuilder, CriteriaQuery, Root, Path, Join, and Predicate through EntityManager.
- Spring Data JPA Specification wraps and composes JPA predicates; it is not a general abstraction for Spring Data JDBC.
- Querydsl provides a fluent DSL and generated Q-types; distinguish Querydsl JPA from Querydsl SQL.
- Spring Data JDBC does not provide the same default QuerydslPredicateExecutor integration as Spring Data JPA.
- Relational Criteria is not a general query builder for arbitrary JOINs/subqueries; use @Query or custom JDBC when complex SQL is needed.
- Choose tools based on persistence model, query complexity, type-safety requirements, and integration cost.

When working with Spring Data JDBC, start with Spring Data Relational Criteria/Query for moderate dynamic aggregate filters. If the application uses JPA and needs reusable predicates, Specification is the natural fit; if you need a strongly type-safe DSL and have selected the matching backend, consider Querydsl. Distinguishing these abstractions properly prevents mixing incompatible APIs and keeps queries, mappings, and aggregate boundaries consistent with the persistence technology in use.

## References

- [Spring Data Relational — Querying](https://docs.spring.io/spring-data/relational/reference/jdbc/querying.html)
- [Spring Data Relational API — Criteria](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/query/Criteria.html)
- [Spring Data Relational API — Query](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/relational/core/query/Query.html)
- [Spring Data JDBC API — JdbcAggregateTemplate](https://docs.spring.io/spring-data/relational/docs/current/api/org/springframework/data/jdbc/core/JdbcAggregateTemplate.html)
- [Spring Data JPA — Specifications](https://docs.spring.io/spring-data/jpa/reference/jpa/specifications.html)
- [Jakarta Persistence — Criteria API](https://jakarta.ee/specifications/persistence/)
- [Querydsl Reference](https://querydsl.com/static/querydsl/latest/reference/html_single/)
