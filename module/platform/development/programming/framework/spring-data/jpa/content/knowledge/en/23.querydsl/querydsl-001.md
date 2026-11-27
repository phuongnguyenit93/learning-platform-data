# The Role of Querydsl and Choosing It Over Specification

Querydsl and Spring Data JPA Specification both help build dynamic queries from multiple search criteria. The difference lies in how the query is expressed: Querydsl provides a type-safe DSL with Q classes generated from Entities, whereas Specification uses the JPA Criteria API to create composable predicates.

Querydsl is often appealing when queries involve multiple JOINs, expressions, subqueries, or projections and the development team wants to write queries in a fluent, readable style. Specification is suitable when you mainly need to compose reusable filter conditions, want to rely on the standard JPA Criteria API, and want to limit external library dependencies.

Neither choice is inherently faster. Both are translated into queries that the JPA provider executes against the database. Choose based on query complexity, type safety requirements, code organization, maintainability, and the project's dependency ecosystem.

## 1. What Problem Does Querydsl Solve?

On a customer search screen, a user might enter a name, email, active status, and registration date range. Each parameter is optional, so the query must adapt to the input data.

If you use many fixed Repository methods, the number of methods can grow rapidly:

~~~java
findByNameContaining(String name);
findByEmail(String email);
findByActive(Boolean active);
findByNameContainingAndActive(String name, Boolean active);
findByEmailAndActive(String email, Boolean active);
// And many more combinations...
~~~

If you use a static JPQL query with many nullable parameter conditions, the query can become long and hard to optimize. Querydsl allows you to compose predicates only for the conditions that are actually provided.

Querydsl is a Java library for building queries using a fluent API. With Querydsl JPA, expressions are constructed from the Entity model and translated into JPQL for execution by the JPA provider. Querydsl also has other modules, such as Querydsl SQL; Querydsl JPA should be distinguished from writing SQL directly.

## 2. Q-Types Generated from Entities

Querydsl uses an annotation processor to generate metamodel classes prefixed with Q from Entities. For example, the Customer Entity typically generates the QCustomer class.

Entity:

~~~java
import jakarta.persistence.*;

@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    private String name;
    private String email;
    private Boolean active;

    protected Customer() {
    }

    public Customer(String name, String email, Boolean active) {
        this.name = name;
        this.email = email;
        this.active = active;
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

    public Boolean getActive() {
        return active;
    }
}
~~~

After running a build with the Querydsl annotation processor, the generated source code can be used as follows:

~~~java
QCustomer customer = QCustomer.customer;
~~~

QCustomer provides typed paths corresponding to Entity properties, such as customer.name, customer.email, customer.active, and customer.id.

The strength is that the IDE can autocomplete properties and the compiler can catch many wrong property names or type mismatches at compile time. If an Entity property is renamed and the project is rebuilt, code referencing the old Q-type will fail to compile so it can be updated.

Q-types are generated during the build process; normally, you do not need to write or modify Q classes directly. Make sure the generated sources directory is properly configured and recognized by your IDE and build tool.

## 3. Configuring Querydsl for a Spring Data JPA Project

To use Querydsl JPA, a project needs:

1. A Querydsl JPA dependency compatible with the Java, Spring Data, and JPA provider versions.
2. The Querydsl annotation processor to generate Q-types from Entities.
3. Build tool configuration to include generated sources in compilation.
4. An artifact version compatible with the project's persistence namespace.

With Spring Boot 3 and Jakarta Persistence, you must choose Querydsl artifacts that use the Jakarta namespace (usually distributed via the jakarta classifier in the corresponding Querydsl versions). Spring Boot 2 projects using javax.persistence need artifacts matching the older namespace. Do not mix Q-types or processors using javax with an application using jakarta.

Dependency names and annotation processor configurations can vary across Maven, Gradle, and Querydsl versions. Use the same Querydsl version for both runtime and the annotation processor, check your project's dependency management repository, and run a clean build to confirm Q-types are generated.

A typical Maven build command is:

~~~bash
./mvnw clean compile
~~~

With Gradle:

~~~bash
./gradlew clean compileJava
~~~

Command names may vary depending on the project wrapper. The purpose of a clean build is to verify that generated sources are regenerated from the current Entities, avoiding reliance on stale Q-types left in the build directory.

## 4. Using QuerydslPredicateExecutor with Spring Data

Spring Data JPA integrates with Querydsl through QuerydslPredicateExecutor. A Repository simply extends this interface to gain Predicate-based query operations.

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.querydsl.QuerydslPredicateExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer> {
}
~~~

Commonly used operations include:

- findOne(predicate): finds a single matching result.
- findAll(predicate): retrieves matching Entities.
- findAll(predicate, sort): retrieves and sorts results.
- findAll(predicate, pageable): retrieves a Page.
- count(predicate): counts matching results.
- exists(predicate): checks whether any matching result exists.

Example of building dynamic search conditions:

~~~java
import com.querydsl.core.BooleanBuilder;

public Page<Customer> search(
        String name,
        String email,
        Boolean active,
        Pageable pageable) {

    QCustomer customer = QCustomer.customer;
    BooleanBuilder predicate = new BooleanBuilder();

    if (name != null && !name.isBlank()) {
        predicate.and(customer.name.containsIgnoreCase(name));
    }

    if (email != null && !email.isBlank()) {
        predicate.and(customer.email.equalsIgnoreCase(email));
    }

    if (active != null) {
        predicate.and(customer.active.eq(active));
    }

    return customerRepository.findAll(predicate, pageable);
}
~~~

BooleanBuilder lets you append conditions per parameter. containsIgnoreCase creates a case-insensitive substring match condition; equalsIgnoreCase compares strings case-insensitively; eq compares against the exact value of the property.

When no conditions are added, an empty BooleanBuilder may represent a predicate without a WHERE clause depending on how Querydsl/the provider handles it. If business rules forbid querying all data, validate inputs and reject empty queries in the service layer.

## 5. BooleanExpression and Composing Predicates

Besides BooleanBuilder, Querydsl can compose BooleanExpression instances directly:

~~~java
QCustomer customer = QCustomer.customer;

BooleanExpression predicate =
        customer.active.isTrue()
                .and(customer.name.containsIgnoreCase("an"))
                .and(customer.email.endsWithIgnoreCase("@example.com"));

List<Customer> result = queryFactory
        .selectFrom(customer)
        .where(predicate)
        .fetch();
~~~

The and(), or(), and not() methods express logical relationships:

~~~java
BooleanExpression nameMatches =
        customer.name.containsIgnoreCase(keyword);

BooleanExpression emailMatches =
        customer.email.containsIgnoreCase(keyword);

BooleanExpression search =
        nameMatches.or(emailMatches)
                   .and(customer.active.isTrue());
~~~

The final expression corresponds to:

~~~text
(nameMatches OR emailMatches) AND active = true
~~~

Using intermediate variables makes condition grouping explicit and reduces mistakes caused by combining AND/OR in the wrong order. Querydsl expressions are immutable in typical usage: combining operations return a new expression for further predicate building.

## 6. When You Need More Complex Queries: JPAQueryFactory

QuerydslPredicateExecutor fits finding Entities by predicate with basic return types. When you need control over SELECT, JOIN, projection, GROUP BY, subqueries, or fetch join, you can use JPAQueryFactory in a custom repository.

Bean configuration:

~~~java
import com.querydsl.jpa.impl.JPAQueryFactory;
import jakarta.persistence.EntityManager;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
public class QuerydslConfiguration {

    @Bean
    JPAQueryFactory jpaQueryFactory(EntityManager entityManager) {
        return new JPAQueryFactory(entityManager);
    }
}
~~~

Query example:

~~~java
QCustomer customer = QCustomer.customer;

List<Customer> customers = queryFactory
        .selectFrom(customer)
        .where(
                customer.active.isTrue(),
                customer.name.containsIgnoreCase(keyword)
        )
        .orderBy(customer.name.asc(), customer.id.asc())
        .fetch();
~~~

selectFrom(customer) selects the Customer Entity. where() accepts predicates; the conditions are combined with AND. orderBy() defines a deterministic order by name then id. fetch() executes the query and returns a List.

JPAQueryFactory should be injected into a custom repository or a persistence component with clear responsibilities. Database queries should not be placed in controllers.

## 7. Projections with Querydsl

If an API only needs a subset of data, Querydsl can select expressions and map the results to a DTO.

DTO:

~~~java
public record CustomerSummary(
        Long id,
        String name,
        String email
) {
}
~~~

Query:

~~~java
QCustomer customer = QCustomer.customer;

List<CustomerSummary> summaries = queryFactory
        .select(Projections.constructor(
                CustomerSummary.class,
                customer.id,
                customer.name,
                customer.email
        ))
        .from(customer)
        .where(customer.active.isTrue())
        .orderBy(customer.name.asc())
        .fetch();
~~~

Projections.constructor constructs the DTO using a constructor whose parameter order and types match the SELECT expressions. Java records have a canonical constructor, making them convenient for read-only DTOs.

Check argument order and types carefully. If the constructor does not match, errors may occur at runtime. For projects wanting stronger compile-time projection checks, consider @QueryProjection and a Q-type for the DTO, at the trade-off of making the DTO depend on the Querydsl annotation.

Projections explicitly specify the required return data and avoid hydrating full Entities when unnecessary. This is an advantage of custom Querydsl queries over using only the basic methods of QuerydslPredicateExecutor.

## 8. JOIN and Fetch Join in Querydsl

Querydsl JPA allows writing JOINs based on Entity associations:

~~~java
QCustomer customer = QCustomer.customer;
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;

List<Customer> customers = queryFactory
        .selectFrom(customer)
        .join(customer.orders, order)
        .where(order.status.eq(OrderStatus.PAID))
        .distinct()
        .fetch();
~~~

This example finds customers who have at least one order in the PAID status. If a Customer has multiple matching orders, the JOIN can produce multiple rows for the same Customer; distinct() removes duplicate Entity results.

If you want to load the collection in the same query:

~~~java
List<Customer> customers = queryFactory
        .selectFrom(customer)
        .leftJoin(customer.orders).fetchJoin()
        .where(customer.active.isTrue())
        .distinct()
        .fetch();
~~~

fetchJoin() instructs the provider to load the association alongside the main query, avoiding some N+1 issues when the application needs to access the collection immediately afterward.

Do not arbitrarily combine collection fetch joins with pagination. A collection JOIN can multiply SQL rows, breaking pagination semantics or causing the provider to load excessive data and paginate in memory. For paginated lists, consider fetching a Page of IDs first and then loading associations for that set of IDs, or using a suitable projection or EntityGraph.

## 9. What Is Specification?

Spring Data JPA Specification is an abstraction for building predicates with the JPA Criteria API. The Specification<T> interface has a toPredicate() method that takes Root, CriteriaQuery, and CriteriaBuilder and returns a Predicate.

The Repository needs to extend JpaSpecificationExecutor:

~~~java
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.JpaSpecificationExecutor;

public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                JpaSpecificationExecutor<Customer> {
}
~~~

A Specification for a name condition:

~~~java
import org.springframework.data.jpa.domain.Specification;
import jakarta.persistence.criteria.Predicate;
import java.util.Locale;

public class CustomerSpecifications {

    public static Specification<Customer> nameContains(String name) {
        return (root, query, cb) -> {
            if (name == null || name.isBlank()) {
                return cb.conjunction();
            }

            String pattern =
                    "%" + name.toLowerCase(Locale.ROOT) + "%";

            return cb.like(
                    cb.lower(root.<String>get("name")),
                    pattern
            );
        };
    }

    public static Specification<Customer> isActive(Boolean active) {
        return (root, query, cb) -> {
            if (active == null) {
                return cb.conjunction();
            }

            return cb.equal(root.get("active"), active);
        };
    }
}
~~~

They can be composed:

~~~java
Specification<Customer> specification =
        CustomerSpecifications.nameContains(name)
                .and(CustomerSpecifications.isActive(active));

Page<Customer> page =
        customerRepository.findAll(specification, pageable);
~~~

Specification describes filter conditions; Spring Data JPA executes them via the Criteria API. Small Specifications can be reused and composed using and(), or(), or not().

## 10. The Same Requirement Written with Querydsl and Specification

Suppose the requirement is to find active customers whose name contains a keyword and whose email belongs to a given domain.

### Querydsl

~~~java
QCustomer customer = QCustomer.customer;

BooleanBuilder predicate = new BooleanBuilder();

if (keyword != null && !keyword.isBlank()) {
    predicate.and(customer.name.containsIgnoreCase(keyword));
}

if (domain != null && !domain.isBlank()) {
    predicate.and(customer.email.endsWithIgnoreCase(domain));
}

predicate.and(customer.active.isTrue());

Page<Customer> result =
        customerRepository.findAll(predicate, pageable);
~~~

### Specification

~~~java
Specification<Customer> specification =
        CustomerSpecifications.nameContains(keyword)
                .and(CustomerSpecifications.isActive(true))
                .and((root, query, cb) -> {
                    if (domain == null || domain.isBlank()) {
                        return cb.conjunction();
                    }

                    return cb.like(
                            cb.lower(root.<String>get("email")),
                            "%" + domain.toLowerCase(Locale.ROOT)
                    );
                });

Page<Customer> result =
        customerRepository.findAll(specification, pageable);
~~~

Both approaches can express dynamic conditions. Querydsl is usually shorter and more intuitive when there are many operations on properties. Specification uses the Criteria API, which can be more verbose because it works through Root and CriteriaBuilder.

Input semantics must be aligned. For example, endsWithIgnoreCase(domain) and LIKE '%domain' are conceptually equivalent, but wildcard character escaping and collation must be verified according to the implementation.

## 11. Comparing Querydsl and Specification

| Criterion | Querydsl | Specification |
|---|---|---|
| Foundation | Querydsl library | JPA Criteria API via Spring Data |
| Type safety | Q-types generated from Entities, strong property and type checking | Can use string paths; can improve type safety with JPA static metamodel |
| Style | Fluent DSL, expressions close to query language | Lambdas with Root, CriteriaBuilder, Predicate |
| Dynamic conditions | BooleanBuilder, BooleanExpression | Composing Specifications with and/or/not |
| JOINs and paths | Fluent, readable syntax | Criteria joins and paths |
| Projection | Strong when using JPAQueryFactory | Can use multiselect/construct, but Criteria code is often verbose |
| Subquery | DSL has dedicated API | CriteriaBuilder subquery |
| Basic pagination | QuerydslPredicateExecutor or custom query | JpaSpecificationExecutor |
| Dependencies | Requires Querydsl and annotation processor | No query library needed beyond JPA/Spring Data |
| Build | Must maintain Q-type generation | Can use metamodel processor if type-safe paths are desired |
| Best suited for | Complex dynamic queries, many joins/projections | Dynamic filters, reusable predicates, standard JPA-based architecture |

Specification does not strictly require string property names. You can use the JPA static metamodel such as Customer_ to increase type safety. However, generating the static metamodel also requires configuring an annotation processor, and Criteria syntax remains more verbose than Querydsl in many situations.

## 12. Advantages and Trade-offs of Querydsl

### Advantages

- Q-types catch wrong property names and expression types earlier.
- IDEs provide good autocomplete and refactoring support.
- Clear and/or/not expressions, convenient for dynamic conditions.
- JOINs, subqueries, aggregates, and projections have a consistent DSL.
- JPAQueryFactory gives better control over SELECT and query structure than the basic methods of QuerydslPredicateExecutor.
- The same predicate can be reused across multiple suitable queries.

### Trade-offs

- Must configure and maintain an annotation processor.
- Build depends on Querydsl version and javax/jakarta namespace.
- Q-types are generated; after changing an Entity, a rebuild is required to update them.
- Adds a dependency and a DSL that new team members must learn.
- Querydsl JPA is still bounded by JPQL/JPA provider capabilities; database-specific SQL features may require native SQL.
- The basic predicate executor does not completely replace a custom repository when projections, fetch joins, or complex reporting queries are needed.

Querydsl makes query code clearer, but it does not automatically make SQL faster. Performance depends on the final SQL, indexes, data, execution plan, and transactions.

## 13. Advantages and Trade-offs of Specification

### Advantages

- Built on the Jakarta Persistence Criteria API.
- Does not require Querydsl runtime or Q-type generation.
- Easy to compose filter conditions into small modules.
- Integrates directly with JpaSpecificationExecutor.
- Well suited for search APIs with many optional parameters.
- Specifications can be shared across multiple services or use cases.

### Trade-offs

- Criteria API is often longer and harder to read when queries have many JOINs or expressions.
- String-based paths like root.get("name") are prone to typos if not using the static metamodel.
- Projections, grouping, and complex queries can make Specifications hard to organize.
- Specification focuses on predicates; if you need control over SELECT, fetch plans, or query structure, a custom repository may fit better.
- Adding a fetch join inside a Specification can cause side effects when Spring Data generates the count query for a Page; content and count queries need separate control.

Specification is not a weaker choice. For dynamic filters consisting mainly of WHERE conditions, it is often sufficient and avoids adding another library.

## 14. Limitations of QuerydslPredicateExecutor

QuerydslPredicateExecutor provides a convenient API to find Entities by Predicate, but it is not a complete query API for every use case.

Its operations are suited for:
- findAll(predicate)
- findAll(predicate, sort)
- findAll(predicate, pageable)
- findOne(predicate)
- count(predicate)
- exists(predicate)

When you need:
- Complex DTO or interface projections.
- Controlled JOINs and fetch joins.
- GROUP BY/HAVING.
- Subqueries or custom SELECT expressions.
- Reporting queries.
- Custom count query optimization.
- Lock modes, query hints, or special query structures.

use a custom repository with JPAQueryFactory or EntityManager. Do not try to cram every query into QuerydslPredicateExecutor simply because the Repository extends this interface.

## 15. Organizing a Custom Repository with JPAQueryFactory

You can separate complex queries into a repository fragment:

~~~java
public interface CustomerSearchRepository {
    List<CustomerSummary> searchSummaries(
            String keyword,
            Boolean active
    );
}
~~~

Implementation:

~~~java
import com.querydsl.core.BooleanBuilder;
import com.querydsl.core.types.Projections;
import com.querydsl.jpa.impl.JPAQueryFactory;

public class CustomerSearchRepositoryImpl
        implements CustomerSearchRepository {

    private final JPAQueryFactory queryFactory;

    public CustomerSearchRepositoryImpl(JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    @Override
    public List<CustomerSummary> searchSummaries(
            String keyword,
            Boolean active) {

        QCustomer customer = QCustomer.customer;
        BooleanBuilder predicate = new BooleanBuilder();

        if (keyword != null && !keyword.isBlank()) {
            predicate.and(customer.name.containsIgnoreCase(keyword));
        }

        if (active != null) {
            predicate.and(customer.active.eq(active));
        }

        return queryFactory
                .select(Projections.constructor(
                        CustomerSummary.class,
                        customer.id,
                        customer.name,
                        customer.email
                ))
                .from(customer)
                .where(predicate)
                .orderBy(customer.name.asc(), customer.id.asc())
                .fetch();
    }
}
~~~

The main Repository extends the fragment:

~~~java
public interface CustomerRepository
        extends JpaRepository<Customer, Long>,
                QuerydslPredicateExecutor<Customer>,
                CustomerSearchRepository {
}
~~~

According to Spring Data's repository fragment convention, the implementation is named after the fragment interface with the matching default suffix (usually Impl). If the project configures a different repository implementation postfix, the class name must follow that configuration.

This organization keeps custom queries in the persistence layer and allows the main Repository to combine CRUD, basic predicate queries, and specialized projection queries.

## 16. Pagination and Count with Querydsl

QuerydslPredicateExecutor can return a Page when given a Pageable:

~~~java
Page<Customer> page =
        customerRepository.findAll(predicate, pageable);
~~~

Spring Data is responsible for generating the corresponding content and count queries. For simple predicates, this is convenient.

When writing queries manually with JPAQueryFactory, you must manage the count yourself if you want to return a Page:

~~~java
List<Customer> content = queryFactory
        .selectFrom(customer)
        .where(predicate)
        .orderBy(customer.id.asc())
        .offset(pageable.getOffset())
        .limit(pageable.getPageSize())
        .fetch();

Long total = queryFactory
        .select(customer.id.count())
        .from(customer)
        .where(predicate)
        .fetchOne();

return new PageImpl<>(
        content,
        pageable,
        total == null ? 0L : total
);
~~~

This snippet assumes the query counts directly from Customer with no JOINs that multiply rows. If there is a collection JOIN, you may need count distinct on ID or a separate count query matching the logical result.

Do not use fetchResults() or fetchCount() from older online examples without checking the Querydsl version. These APIs have been deprecated/removed in newer Querydsl lines; the safe approach is writing explicit content and count queries when control is needed.

If the UI does not need totalElements, consider Slice or a supported Window/scrolling stream. Do not run a count just to fetch page content.

## 17. Collection JOIN, DISTINCT, and N+1

Querydsl does not automatically eliminate common ORM issues.

When JOINing a collection:
- A parent Entity can appear across multiple SQL rows.
- Entity results may need distinct().
- Count may need countDistinct() on ID.
- Combining collection fetch joins with pagination must be designed carefully.

Example:

~~~java
QCustomer customer = QCustomer.customer;
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;

List<Customer> customers = queryFactory
        .selectFrom(customer)
        .join(customer.orders, order)
        .where(order.status.eq(OrderStatus.PAID))
        .distinct()
        .fetch();
~~~

If you only need customers with PAID orders, EXISTS/subquery can be another way to express it. If you need to load orders for immediate use, fetch join may fit, though result size should be checked.

Querydsl is only a way to build queries. N+1, lazy loading, duplicate rows, transaction boundaries, and fetch strategies must still be handled just as with JPQL or Specification.

## 18. When Should You Choose Querydsl?

Querydsl is usually a good choice when:

1. Dynamic filters have many optional conditions and multiple AND/OR groups.
2. Queries have multiple JOINs, subqueries, expressions, or association traversals.
3. DTO projections and SELECT control are needed.
4. Predicates need to be reused across multiple queries.
5. The team wants strong type safety and refactoring support from Q-types.
6. The project already uses Querydsl and its setup/maintenance cost is accepted.

For example, an order search system might filter by customer, status, date range, total amount, product, shipping address, and many condition combinations. Querydsl can make building predicates and JOINs clearer.

## 19. When Should You Choose Specification?

Specification is usually a good fit when:

1. Conditions are mainly simple WHERE predicates.
2. APIs have many optional filters but few projections or reporting queries.
3. You want to break conditions into small, reusable Specifications.
4. You want to rely on the JPA Criteria API and minimize external dependencies.
5. The team is already familiar with Criteria API or wants to keep the persistence layer standard JPA.
6. Queries do not require complex SELECT/JOIN operations.

For example, a customer admin screen filtering by name, status, creation date, and tenant can be built from small Specifications composed as needed.

## 20. Can Querydsl and Specification Be Combined?

An application can use both across different groups of use cases, provided boundaries and conventions are clear.

For example:
- Specification for simple CRUD filters and admin lists.
- Querydsl custom repository for multi-JOIN searches, projections, or reports.
- JPQL/@Query for short, readable static queries.
- Native SQL for database-specific features that JPQL/Querydsl JPA cannot express.

There is no need to convert every Repository to Querydsl just because of one complex query. Nor should you force every query into Specification if Criteria API makes code hard to read.

The important thing is to avoid implementing the same business condition in multiple inconsistent ways. If there is tenant logic, soft delete, or access control, place it in a layer that can be tested and reused across all relevant query paths.

## 21. Testing Querydsl and Specification

Both approaches require integration tests to verify that the JPA provider generates the right queries.

For Querydsl, you should verify:
- Q-types are generated from the current Entities.
- Predicates with and without optional parameters.
- Logical correctness of AND/OR combinations.
- JOINs do not produce unintended duplicate results.
- Projections map constructor types and parameter order correctly.
- Page totalElements/count is accurate when JOINs are present.
- Fetch joins do not break pagination.
- Queries execute properly on the target database.

For Specification, you should verify:
- Each Specification individually.
- Composing and()/or()/not().
- Null or empty parameters are handled properly.
- JOINs and DISTINCT.
- Count query when a Specification uses JOINs.
- Not adding fetch joins that break the count query.
- Pagination results and ordering.

A test can use @DataJpaTest with small fixture data. For queries involving collation, JSON, database-specific types, or index optimization, integration tests on the same engine as production are necessary. Do not draw performance conclusions from H2 or tests with only a few records.

## 22. Common Pitfalls

**Q-types are not generated**

Check the annotation processor, Jakarta/Javax classifier, generated sources directory, and clean build. Do not manually create Q-types to mask configuration errors.

**Runtime and annotation processor version mismatch**

Easily causes compilation errors or API differences. Keep versions synchronized.

**Using QuerydslPredicateExecutor for queries needing projections/fetch joins**

The executor primarily provides Predicate-based operations. Switch to a custom repository with JPAQueryFactory when you need control over SELECT and JOIN.

**Empty BooleanBuilder causes unfiltered queries**

If business rules prohibit returning all data, validate input conditions and reject empty queries.

**Confusing Q-types with table/column names**

QCustomer is the metamodel of the Customer Entity. Q properties reflect the Java model; the provider remains responsible for translating them to SQL.

**Specification using misspelled string paths**

root.get("lastNmae") may only be caught when the query runs. Use the static metamodel if you want stronger type safety.

**Using collection fetch join with Page**

Can multiply rows or break pagination. Separate the ID query from the association-loading query if needed.

**Duplicate counts on JOIN**

Identify the Entity level to count and use count distinct on the key when appropriate.

**Assuming Querydsl is faster than Specification**

Both generate queries for the JPA provider. Compare actual SQL and execution plans; the DSL itself does not optimize the database.

**Using Querydsl JPA for database-specific SQL syntax**

Querydsl JPA still operates through the JPA/JPQL model. For CTEs, window functions, or unsupported database operators, consider native SQL or a specialized solution.

## 23. Decision Process

When starting a dynamic query:

1. Determine whether the result needs Entities, projections, or DTOs.
2. Evaluate the number of conditions and AND/OR structure.
3. If it is only a simple WHERE filter, try derived queries or Specification.
4. If you need a type-safe DSL for multiple JOINs, subqueries, and expressions, consider Querydsl.
5. If using QuerydslPredicateExecutor but needing projections or fetch joins, create a custom repository with JPAQueryFactory.
6. If the query is short and static, @Query JPQL may be the simplest option.
7. If database-specific SQL is required, use a native query and isolate that dependency.
8. Check dependencies, annotation processor, and Jakarta/Javax namespace.
9. Write integration tests for optional conditions, JOINs, projections, counts, and boundary data.
10. Measure SQL and execution plans before concluding which approach performs better.

## 24. Conclusion

Querydsl provides a strongly typed query DSL through Q-types generated from Entities. It is especially useful for complex dynamic queries, multiple JOINs, subqueries, and projections. Spring Data JPA can integrate QuerydslPredicateExecutor for basic Predicate operations; when control over SELECT and fetch plans is needed, use a custom repository with JPAQueryFactory.

Specification is based on the JPA Criteria API, suits reusable dynamic filters, and helps minimize external dependencies. The Criteria API is generally more verbose but sufficient for many standard search screens. Choose Querydsl when a DSL and type safety deliver clear benefits; choose Specification when predicates are the focus and you want to stick to a standard JPA approach. Both can coexist in the same application along clear use-case boundaries. Ultimately, performance depends on SQL, indexes, execution plans, and the database—not on the library name alone.