# Joins, Projections, and Complex Queries in Custom Repositories with Querydsl

Querydsl lets you build queries whose data types are checked directly in Java. With Spring Data JPA, Querydsl JPA constructs queries from entities and Java properties, then translates them into JPQL for execution by the JPA provider. When queries need multiple JOINs, optional filters, DTO projections, GROUP BY/HAVING, or paginated queries with a custom count query, a custom repository fragment is usually the right place to consolidate that logic.

This lesson uses examples that search orders by customer, status, and date range; return DTOs instead of entities; summarize revenue by customer; and paginate results. The focus is on repository organization, Q-type generation, building dynamic predicates, choosing the right JOIN, mapping DTOs, and avoiding row multiplication when joining collections.

## 1. What Problem Does Querydsl JPA Solve?

JPQL is an entity-oriented query language. You can write string queries in `@Query`, but when conditions vary per request, string concatenation or maintaining many nearly identical queries quickly becomes hard to manage.

Querydsl provides a Java DSL to express every part of a query:

- Entities and properties are represented by Q-type classes generated from mappings.
- Predicates are constructed using typed expressions, such as `order.status.eq(status)`.
- JOIN, GROUP BY, HAVING, ORDER BY, projections, and result limits follow query structure.
- Parameter values are bound by the provider; there is no need to concatenate input into JPQL/SQL strings.
- The IDE and compiler catch many property-name typos or type mismatches before runtime.

With Querydsl JPA, queries still obey JPQL/JPA semantics and are executed by a provider such as Hibernate. Querydsl does not turn queries into database-specific SQL. If you need raw SQL, CTEs, or database-specific features, consider Querydsl SQL or native queries.

## 2. When to Use QuerydslPredicateExecutor vs. a Custom Repository

Spring Data JPA offers two common integration patterns.

### 2.1. QuerydslPredicateExecutor for simple repository queries

A repository can extend `QuerydslPredicateExecutor`:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long>,
                QuerydslPredicateExecutor<PurchaseOrder> {
}
~~~

Then build a predicate and call:

~~~java
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;

BooleanBuilder predicate = new BooleanBuilder();
predicate.and(order.status.eq(OrderStatus.PAID));

Iterable<PurchaseOrder> result =
        repository.findAll(predicate);
~~~

This is convenient when finding entities by predicate using standard repository operations. However, queries requiring complex DTO projections, multiple conditional JOINs, GROUP BY/HAVING, custom count queries, or specific pagination rules usually need more explicit control.

### 2.2. Custom repository fragment for complex queries

Create a fragment interface describing the use cases:

~~~java
public interface PurchaseOrderQueryRepository {

    Page<OrderSummary> search(OrderSearchFilter filter, Pageable pageable);

    List<CustomerSpend> summarizePaidOrders(
            Instant from,
            Instant to,
            BigDecimal minimumSpend);
}
~~~

The main repository combines that fragment:

~~~java
public interface PurchaseOrderRepository
        extends JpaRepository<PurchaseOrder, Long>,
                PurchaseOrderQueryRepository {
}
~~~

Spring Data composes the fragment implementation into the repository. By convention, the implementation is named `PurchaseOrderQueryRepositoryImpl`:

~~~java
@Repository
public class PurchaseOrderQueryRepositoryImpl
        implements PurchaseOrderQueryRepository {

    private final JPAQueryFactory queryFactory;

    public PurchaseOrderQueryRepositoryImpl(
            JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    // Implement query methods here.
}
~~~

This organization fits well when queries have custom logic while still preserving the Spring Data repository API. You do not need to put all complex queries in a service or create a repository completely detached from Spring Data.

## 3. Configuring Querydsl JPA and Generating Q-Types

Q-types such as `QPurchaseOrder` and `QCustomer` are generated from entities by an annotation processor. Do not write or edit generated Q classes manually.

The examples below use Querydsl 5.1.0 with Jakarta Persistence, suitable for Spring Boot 3/Jakarta projects. If a project uses Spring Boot 2 or the `javax.persistence` JPA namespace, it must use artifacts/classifiers and versions compatible with that namespace. Verify your Spring Data JPA, Querydsl, and JDK versions before copying configurations.

### 3.1. Maven

Runtime/compile dependency:

~~~xml
<properties>
    <querydsl.version>5.1.0</querydsl.version>
</properties>

<dependencies>
    <dependency>
        <groupId>com.querydsl</groupId>
        <artifactId>querydsl-jpa</artifactId>
        <version>${querydsl.version}</version>
        <classifier>jakarta</classifier>
    </dependency>
</dependencies>
~~~

Configure the annotation processor in Maven Compiler Plugin:

~~~xml
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
                        <version>${querydsl.version}</version>
                        <classifier>jakarta</classifier>
                    </path>
                    <path>
                        <groupId>jakarta.persistence</groupId>
                        <artifactId>jakarta.persistence-api</artifactId>
                        <version>3.1.0</version>
                    </path>
                </annotationProcessorPaths>
            </configuration>
        </plugin>
    </plugins>
</build>
~~~

In real projects, use the Jakarta Persistence version managed by Spring Boot dependency management to avoid API version drift. The annotation processor must see the persistence annotations used by the entities.

### 3.2. Gradle

With Gradle, declare Querydsl JPA and the corresponding annotation processor:

~~~groovy
dependencies {
    implementation "com.querydsl:querydsl-jpa:5.1.0:jakarta"

    annotationProcessor "com.querydsl:querydsl-apt:5.1.0:jakarta"
    annotationProcessor "jakarta.persistence:jakarta.persistence-api:3.1.0"
}
~~~

If the project has test sources defining their own entities, configure the annotation processor for the test source set as needed.

### 3.3. Verifying Q-Types Were Generated

After building, locate the Q classes in the generated sources directory, usually:

- Maven: `target/generated-sources/annotations`.
- Gradle: `build/generated/sources/annotationProcessor/java/main`.

Example entity:

~~~java
@Entity
public class Customer {

    @Id
    private Long id;

    private String name;
}
~~~

The generated Q-type can be used as follows:

~~~java
QCustomer customer = QCustomer.customer;

NumberPath<Long> idPath = customer.id;
StringPath namePath = customer.name;
~~~

Do not edit Q-types by hand. If Q-types are missing, check the annotation processor, Jakarta/Javax classifier, source sets, and whether entities have valid JPA annotations.

## 4. Configuring JPAQueryFactory

`JPAQueryFactory` is the entry point for building Querydsl JPA queries. You can declare a bean:

~~~java
@Configuration
public class QuerydslConfiguration {

    @Bean
    JPAQueryFactory jpaQueryFactory(EntityManager entityManager) {
        return new JPAQueryFactory(entityManager);
    }
}
~~~

In Spring, the injected EntityManager is typically a transaction-bound proxy. Querydsl uses that EntityManager when executing queries.

The custom repository implementation receives the factory via constructor:

~~~java
@Repository
public class PurchaseOrderQueryRepositoryImpl
        implements PurchaseOrderQueryRepository {

    private final JPAQueryFactory queryFactory;

    public PurchaseOrderQueryRepositoryImpl(
            JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }
}
~~~

Do not manually create a new EntityManager per method, and do not share a manually created EntityManager across threads. Let Spring manage the persistence context and transactions.

## 5. Sample Domain Model

We use two entities:

- `Customer` with `id`, `name`, and a One-to-Many association to orders.
- `PurchaseOrder` with `id`, `status`, `createdAt`, `total`, and a Many-to-One association to customer.

### 5.1. Status Enum

~~~java
public enum OrderStatus {
    NEW,
    PAID,
    CANCELLED,
    COMPLETED
}
~~~

### 5.2. Customer Entity

~~~java
@Entity
@Table(name = "customers")
public class Customer {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Column(nullable = false, length = 120)
    private String name;

    @OneToMany(mappedBy = "customer")
    private List<PurchaseOrder> orders = new ArrayList<>();

    protected Customer() {
    }

    public Customer(String name) {
        this.name = name;
    }

    public Long getId() {
        return id;
    }

    public String getName() {
        return name;
    }
}
~~~

### 5.3. PurchaseOrder Entity

~~~java
@Entity
@Table(name = "purchase_orders")
public class PurchaseOrder {

    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    private Long id;

    @Enumerated(EnumType.STRING)
    @Column(nullable = false)
    private OrderStatus status;

    @Column(nullable = false)
    private Instant createdAt;

    @Column(nullable = false, precision = 14, scale = 2)
    private BigDecimal total;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "customer_id", nullable = false)
    private Customer customer;

    protected PurchaseOrder() {
    }

    public PurchaseOrder(
            OrderStatus status,
            Instant createdAt,
            BigDecimal total,
            Customer customer) {
        this.status = status;
        this.createdAt = createdAt;
        this.total = total;
        this.customer = customer;
    }

    public Long getId() {
        return id;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public BigDecimal getTotal() {
        return total;
    }

    public Customer getCustomer() {
        return customer;
    }
}
~~~

These entities are minimal examples. Real projects may have additional constructors, auditing, tenant IDs, or required fields; adjust fixtures and mappings to match your actual model.

## 6. Building DTO Projections

List search results do not need to return full entities. Create a DTO:

~~~java
public record OrderSummary(
        Long id,
        String customerName,
        OrderStatus status,
        Instant createdAt,
        BigDecimal total) {
}
~~~

With Querydsl, there are multiple ways to project.

### 6.1. Projections.constructor

~~~java
.select(Projections.constructor(
        OrderSummary.class,
        order.id,
        customer.name,
        order.status,
        order.createdAt,
        order.total
))
~~~

Querydsl invokes a matching constructor. This is concise and works with records or DTOs with matching constructors, though type/order matching is validated when the query runs rather than via a DTO Q-type checking the full constructor at compile time.

Expression order must match DTO parameter order. If field types or order change without updating the projection, errors may appear at query execution time.

### 6.2. Projections.bean and Projections.fields

`Projections.bean` maps by property name and requires setters or a compatible bean mechanism:

~~~java
.select(Projections.bean(
        OrderSummaryBean.class,
        order.id.as("id"),
        customer.name.as("customerName"),
        order.status.as("status"),
        order.createdAt.as("createdAt"),
        order.total.as("total")
))
~~~

`Projections.fields` maps directly into fields by name:

~~~java
.select(Projections.fields(
        OrderSummaryFields.class,
        order.id.as("id"),
        customer.name.as("customerName"),
        order.status.as("status"),
        order.createdAt.as("createdAt"),
        order.total.as("total")
))
~~~

Both require aliases matching the DTO's property/field names. They are convenient for mutable DTOs but depend on reflection rules and class structure. Do not use them with immutable constructor-only DTOs that lack corresponding fields/setters.

### 6.3. @QueryProjection for Stronger Constructor Checking

You can annotate a DTO constructor with `@QueryProjection`:

~~~java
public class OrderSummaryView {

    private final Long id;
    private final String customerName;
    private final OrderStatus status;
    private final Instant createdAt;
    private final BigDecimal total;

    @QueryProjection
    public OrderSummaryView(
            Long id,
            String customerName,
            OrderStatus status,
            Instant createdAt,
            BigDecimal total) {
        this.id = id;
        this.customerName = customerName;
        this.status = status;
        this.createdAt = createdAt;
        this.total = total;
    }

    public Long getId() {
        return id;
    }

    public String getCustomerName() {
        return customerName;
    }

    public OrderStatus getStatus() {
        return status;
    }

    public Instant getCreatedAt() {
        return createdAt;
    }

    public BigDecimal getTotal() {
        return total;
    }
}
~~~

The annotation processor generates `QOrderSummaryView`. The query can then be written:

~~~java
.select(new QOrderSummaryView(
        order.id,
        customer.name,
        order.status,
        order.createdAt,
        order.total
))
~~~

This checks constructor types and parameter order at compile time. In exchange, the DTO depends on the Querydsl annotation and requires the annotation processor to generate the Q DTO. If you want DTOs free of Querydsl dependencies, use `Projections.constructor`.

## 7. JOINs in Querydsl JPA

JOINs allow querying across entity relationships and selecting fields from multiple entities.

### 7.1. Inner join

~~~java
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
QCustomer customer = QCustomer.customer;

List<OrderSummary> result = queryFactory
        .select(Projections.constructor(
                OrderSummary.class,
                order.id,
                customer.name,
                order.status,
                order.createdAt,
                order.total
        ))
        .from(order)
        .join(order.customer, customer)
        .where(order.status.eq(OrderStatus.PAID))
        .fetch();
~~~

`join(order.customer, customer)` is an inner join. Only orders with a matching customer appear. Because the example entity sets `optional = false`, this is a required relationship.

### 7.2. Left join

If an association can be null or you want to preserve left-side rows when no related record exists, use:

~~~java
.leftJoin(order.customer, customer)
~~~

In that case, `customer.name` may be null. The DTO must use nullable reference types and callers must handle null values.

Do not turn a LEFT JOIN into an inner-like filter by putting a WHERE condition on the right-hand table when you still want to keep unmatched left-side rows. For example:

~~~java
.leftJoin(order.customer, customer)
.where(customer.name.containsIgnoreCase(keyword))
~~~

The WHERE clause filters out rows where `customer.name` is null, making the result behave almost like an inner join. If you want to keep left-side rows while restricting joined right-side rows, consider placing the condition in `on(...)`:

~~~java
.leftJoin(order.customer, customer)
.on(customer.name.startsWithIgnoreCase(prefix))
~~~

Distinguish conditions filtering the root entity from conditions restricting which rows are joined on the right side.

### 7.3. Multi-level joins

Querydsl supports chaining across multiple relationships:

~~~java
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
QCustomer customer = QCustomer.customer;
QDepartment department = QDepartment.department;

List<Tuple> rows = queryFactory
        .select(order.id, customer.name, department.name)
        .from(order)
        .join(order.customer, customer)
        .join(customer.department, department)
        .fetch();
~~~

Each Q-type alias represents a single path in the query. If the same entity type is JOINed twice in two different roles, create distinct aliases using the Q-type constructor, such as `new QCustomer("buyer")` and `new QCustomer("approver")`.

## 8. Fetch Join vs. Regular JOIN

Regular JOINs are used to filter or select expressions from related entities. Fetch join instructs the provider to load the association together with the root entity:

~~~java
List<PurchaseOrder> orders = queryFactory
        .selectFrom(order)
        .join(order.customer, customer).fetchJoin()
        .where(order.status.eq(OrderStatus.PAID))
        .fetch();
~~~

Fetch join is useful when the caller needs the PurchaseOrder entity along with Customer in the persistence context. It can prevent N+1 queries when accessing ToOne associations.

When only a DTO is needed, normally use a regular JOIN and select DTO expressions. Do not add `fetchJoin()` to a DTO query expecting to reduce columns; fetch join is an instruction to load an association on the selected entity, not a projection mechanism.

### 8.1. Collection fetch join and pagination

Fetch joining a ToMany collection can multiply SQL rows. If a customer has 10 orders, the collection JOIN can yield 10 rows for the same customer. Combining a collection fetch join with offset/limit can paginate at the wrong entity level or force Hibernate to fetch many rows and paginate in memory, depending on provider and version.

Rules of thumb:

- ToOne fetch joins usually cause less row multiplication if the association is truly singular.
- Avoid paginating directly on queries with collection fetch joins.
- Use DTO projections when you only need fields from multiple tables.
- If you need root entities with collections, paginate root IDs first and then fetch the collection for that batch of IDs.
- Check Hibernate logs and warnings; never ignore collection fetch pagination warnings.

## 9. Dynamic Predicates with BooleanBuilder

Search filters often have optional fields. Instead of writing a separate query per combination, build predicates from the conditions actually provided.

Filter DTO:

~~~java
public record OrderSearchFilter(
        OrderStatus status,
        String customerName,
        Instant createdFrom,
        Instant createdTo,
        BigDecimal minimumTotal) {
}
~~~

Predicate builder helper:

~~~java
private BooleanBuilder buildPredicate(OrderSearchFilter filter) {
    QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
    QCustomer customer = QCustomer.customer;

    BooleanBuilder where = new BooleanBuilder();

    if (filter.status() != null) {
        where.and(order.status.eq(filter.status()));
    }

    if (filter.customerName() != null
            && !filter.customerName().isBlank()) {
        where.and(customer.name.containsIgnoreCase(
                filter.customerName().trim()));
    }

    if (filter.createdFrom() != null) {
        where.and(order.createdAt.goe(filter.createdFrom()));
    }

    if (filter.createdTo() != null) {
        where.and(order.createdAt.lt(filter.createdTo()));
    }

    if (filter.minimumTotal() != null) {
        where.and(order.total.goe(filter.minimumTotal()));
    }

    return where;
}
~~~

The predicate uses a half-open time interval: `createdAt >= from` and `createdAt < to`. This allows splitting adjacent periods without double-counting timestamps on the boundary.

In the query implementation, the customer JOIN is declared if the predicate or projection references customer fields. Do not add JOINs unnecessarily when unused, as they can affect row counts and execution plans.

### 9.1. Mandatory predicates and optional conditions

In multi-tenant applications, tenant ID is a mandatory security condition, not an optional filter:

~~~java
where.and(order.tenantId.eq(currentTenantId));
~~~

Obtain the tenant from a trusted authentication context; never trust an arbitrary tenant ID sent by the client. Always apply the tenant predicate to the query alongside any optional search conditions.

### 9.2. Do not concatenate input into query strings

Querydsl binds values through expressions. Avoid manually assembling JPQL/SQL by concatenating keywords or filters. Column names and sort paths remain part of query structure, not bind parameters; if clients can choose sorting, map inputs through a whitelist of supported properties.

## 10. Complete Custom Repository Search with DTO and Pageable

Let us implement `search` in `PurchaseOrderQueryRepositoryImpl`. The example uses a default descending order by timestamp and descending ID to keep rows with identical timestamps deterministic.

~~~java
@Repository
public class PurchaseOrderQueryRepositoryImpl
        implements PurchaseOrderQueryRepository {

    private final JPAQueryFactory queryFactory;

    public PurchaseOrderQueryRepositoryImpl(
            JPAQueryFactory queryFactory) {
        this.queryFactory = queryFactory;
    }

    @Override
    public Page<OrderSummary> search(
            OrderSearchFilter filter,
            Pageable pageable) {

        QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
        QCustomer customer = QCustomer.customer;

        BooleanBuilder where = buildPredicate(filter);

        List<OrderSummary> content = queryFactory
                .select(Projections.constructor(
                        OrderSummary.class,
                        order.id,
                        customer.name,
                        order.status,
                        order.createdAt,
                        order.total
                ))
                .from(order)
                .leftJoin(order.customer, customer)
                .where(where)
                .orderBy(order.createdAt.desc(), order.id.desc())
                .offset(pageable.getOffset())
                .limit(pageable.getPageSize())
                .fetch();

        Long count = queryFactory
                .select(order.id.count())
                .from(order)
                .leftJoin(order.customer, customer)
                .where(where)
                .fetchOne();

        long total = count == null ? 0L : count;

        return new PageImpl<>(content, pageable, total);
    }

    private BooleanBuilder buildPredicate(OrderSearchFilter filter) {
        QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
        QCustomer customer = QCustomer.customer;

        BooleanBuilder where = new BooleanBuilder();

        if (filter.status() != null) {
            where.and(order.status.eq(filter.status()));
        }

        if (filter.customerName() != null
                && !filter.customerName().isBlank()) {
            where.and(customer.name.containsIgnoreCase(
                    filter.customerName().trim()));
        }

        if (filter.createdFrom() != null) {
            where.and(order.createdAt.goe(filter.createdFrom()));
        }

        if (filter.createdTo() != null) {
            where.and(order.createdAt.lt(filter.createdTo()));
        }

        if (filter.minimumTotal() != null) {
            where.and(order.total.goe(filter.minimumTotal()));
        }

        return where;
    }
}
~~~

This example covers a ToOne relationship. Both content and count queries share the same predicate so total counts do not mismatch page content.

Key elements:

- `select(Projections.constructor(...))` returns DTOs.
- `leftJoin` preserves orders when customer might be absent.
- `where(where)` applies the same dynamic filter.
- `orderBy` includes ID as a tie-breaker for deterministic pagination.
- `offset` and `limit` are applied from `Pageable`.
- The count query counts orders only, without selecting DTO columns.
- `PageImpl` combines content, pageable, and total row count.

To keep the example focused, the code uses a fixed sort order. If you want to support `pageable.getSort()`, map each allowed property to its corresponding Q-path; never pass arbitrary column names from requests into queries.

## 11. Handling Sort with a Whitelist

You should not silently ignore Sort in Pageable without informing the caller. There are two options: specify that the repository supports only a fixed sort, or support a predefined set of sort fields.

Simple mapper example:

~~~java
private OrderSpecifier<?>[] toOrderSpecifiers(
        Sort sort,
        QPurchaseOrder order,
        QCustomer customer) {

    if (sort.isUnsorted()) {
        return new OrderSpecifier<?>[] {
                order.createdAt.desc(),
                order.id.desc()
        };
    }

    List<OrderSpecifier<?>> result = new ArrayList<>();

    for (Sort.Order item : sort) {
        boolean ascending = item.isAscending();

        switch (item.getProperty()) {
            case "id" -> result.add(
                    ascending ? order.id.asc() : order.id.desc());

            case "createdAt" -> result.add(
                    ascending
                            ? order.createdAt.asc()
                            : order.createdAt.desc());

            case "total" -> result.add(
                    ascending ? order.total.asc() : order.total.desc());

            case "customerName" -> result.add(
                    ascending ? customer.name.asc()
                              : customer.name.desc());

            default -> throw new IllegalArgumentException(
                    "Unsupported sort property: " + item.getProperty());
        }
    }

    return result.toArray(OrderSpecifier[]::new);
}
~~~

The key idea is allowing sorting only on explicitly defined properties. In production, make sure the final ordering ends with a unique tie-breaker like ID even when the client sends another sort. If the sort already includes ID, do not append it again.

If you do not want to support dynamic sorting, reject unsupported Sort values or clearly document the contract that the query uses a fixed order. Never silently return a different order than the client requested.

## 12. Collection JOINs: Duplicate Rows and Count Distinct

ToMany JOINs are where complex queries most often go wrong.

Suppose we add OrderLine and an order has many lines. The query:

~~~java
.from(order)
.join(order.lines, line)
.where(line.productName.containsIgnoreCase(keyword))
~~~

can produce multiple rows for the same order if multiple order lines match. If the SELECT DTO represents one row per line, repeating order information matches the query grain. If the use case requires one row per order, duplicates must be eliminated.

### 12.1. Using exists/subquery when only checking for a matching line

If you only want orders that have at least one matching line, expressing it with EXISTS avoids multiplying rows in the main query:

~~~java
QOrderLine line = QOrderLine.orderLine;

BooleanExpression hasMatchingLine =
        JPAExpressions
                .selectOne()
                .from(line)
                .where(
                        line.purchaseOrder.eq(order),
                        line.productName.containsIgnoreCase(keyword)
                )
                .exists();

List<OrderSummary> result = queryFactory
        .select(Projections.constructor(
                OrderSummary.class,
                order.id,
                customer.name,
                order.status,
                order.createdAt,
                order.total
        ))
        .from(order)
        .leftJoin(order.customer, customer)
        .where(hasMatchingLine)
        .fetch();
~~~

The main query retains one row per order as long as remaining JOINs do not multiply rows. This is usually the right choice when the child relationship is used solely for existence filtering.

### 12.2. Count queries must count at the right grain

If a content query JOINs a collection and produces multiple rows per order, `order.id.count()` counts joined rows rather than unique orders.

You can use:

~~~java
.select(order.id.countDistinct())
~~~

However, simply changing count to distinct is not enough if the content query still returns duplicate DTOs. Decide explicitly whether the result should have one row per order or one row per order line, and design both SELECT and count at the same grain.

### 12.3. Two-step pagination for collections

When you need `Page<Order>` along with collection data:

1. Query unique order IDs matching the filter, ordering, and pageable.
2. Query the DTOs/entities along with their collections for that list of IDs.
3. Count unique orders using count distinct or an appropriate query.
4. Preserve the ID order from step one when assembling the final result, because `IN (...)` does not guarantee ordering.

This avoids paginating directly over multiplied JOIN rows. For simple DTOs, step one can fetch IDs and step two can fetch the related fields.

## 13. GROUP BY, HAVING, and Aggregate Projections

Querydsl supports aggregate expressions and grouping in JPQL.

Suppose we need to summarize paid order count and total spend by customer.

DTO:

~~~java
public record CustomerSpend(
        Long customerId,
        String customerName,
        Long orderCount,
        BigDecimal totalSpent) {
}
~~~

Query:

~~~java
@Override
public List<CustomerSpend> summarizePaidOrders(
        Instant from,
        Instant to,
        BigDecimal minimumSpend) {

    QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
    QCustomer customer = QCustomer.customer;

    NumberExpression<Long> orderCount = order.id.count();
    NumberExpression<BigDecimal> totalSpent = order.total.sum();

    return queryFactory
            .select(Projections.constructor(
                    CustomerSpend.class,
                    customer.id,
                    customer.name,
                    orderCount,
                    totalSpent
            ))
            .from(order)
            .join(order.customer, customer)
            .where(
                    order.status.eq(OrderStatus.PAID),
                    order.createdAt.goe(from),
                    order.createdAt.lt(to)
            )
            .groupBy(customer.id, customer.name)
            .having(totalSpent.goe(minimumSpend))
            .orderBy(totalSpent.desc(), customer.id.asc())
            .fetch();
}
~~~

Explanation:

- `count()` returns the number of orders per group.
- `sum()` sums order totals.
- `groupBy(customer.id, customer.name)` creates one group per customer.
- `having(...)` filters after aggregation.
- `orderBy(totalSpent.desc(), customer.id.asc())` sorts by total spend, using ID as a tie-breaker.

`WHERE` filters rows before grouping; `HAVING` filters groups after aggregation. Do not place grouped total conditions in WHERE.

The example uses an inner join, so only customers with PAID orders in the time window appear. If you need to include customers with no orders, start the query from Customer and LEFT JOIN orders with status/date conditions inside `on(...)`, then handle null aggregate values.

### 13.1. Be careful aggregating when joining multiple collections

If a query simultaneously JOINs orders and lines, each order has multiple lines. Then `sum(order.total)` can be summed multiple times per line, and `count(order.id)` can also double-count.

Determine the grain before aggregating:

- Order total sum: avoid ToMany JOINs or use an appropriate subquery.
- Line total sum: sum line expressions.
- Order count: count distinct order IDs when JOINs can multiply rows.
- Customer totals across multiple tables: consider aggregating each source separately and combining results.

Do not blindly fix inflated numbers by adding distinct. `SUM(DISTINCT order.total)` is also wrong if two different orders share the same total amount; it deduplicates monetary amounts rather than deduplicating orders.

## 14. Querydsl GroupBy Transform and When to Use It

Querydsl provides the `GroupBy` result transformer to aggregate flat rows into nested object structures in Java. It is useful when constructing DTOs with child collections from JOIN results.

Conceptual example:

~~~java
Map<Long, CustomerOrdersDto> grouped = queryFactory
        .from(order)
        .join(order.customer, customer)
        .transform(
                GroupBy.groupBy(customer.id).as(
                        Projections.constructor(
                                CustomerOrdersDto.class,
                                customer.id,
                                customer.name,
                                GroupBy.list(
                                        Projections.constructor(
                                                OrderItemDto.class,
                                                order.id,
                                                order.total
                                        )
                                )
                        )
                )
        );
~~~

This code illustrates the grouping idea in Querydsl; constructors and DTO collection types must be adapted to the projection/transformer of your Querydsl version. The transformer groups already-fetched rows in Java memory; it does not replace database GROUP BY. If a query returns millions of rows, JVM-side grouping can still consume substantial heap memory.

Use SQL/JPQL aggregation whenever possible so the database computes aggregates. Use GroupBy transform when building nested object graphs from a reasonably bounded result set where the reduction in query count is worthwhile.

## 15. Subqueries and Complex Queries

Querydsl JPA supports subqueries via `JPAExpressions`. For example, fetching orders whose total exceeds the average order total within the same status:

~~~java
QPurchaseOrder order = QPurchaseOrder.purchaseOrder;
QPurchaseOrder other = new QPurchaseOrder("other");

JPQLQuery<BigDecimal> averageForStatus =
        JPAExpressions
                .select(other.total.avg())
                .from(other)
                .where(other.status.eq(order.status));

List<PurchaseOrder> aboveAverage = queryFactory
        .selectFrom(order)
        .where(order.total.gt(averageForStatus))
        .fetch();
~~~

A correlated subquery references the outer alias (`order.status`). Use a separate alias for the inner entity to avoid path ambiguity.

Subqueries keep logic inside a single query, though they are not always faster than JOINs. Inspect execution plans, indexes, and cardinality on the real database.

## 16. Query Optimization and Avoiding Performance Pitfalls

### 16.1. JOIN only when needed

Adding table JOINs can increase cost and multiply rows. Declare a JOIN only if properties from that table are used in projections, predicates, grouping, or ordering.

### 16.2. Choose the right JOIN type

- `join(...)`: keeps only rows with matching associations.
- `leftJoin(...)`: preserves left-side rows even without associations.
- `on(...)`: constrains matched rows on the joined side.
- `fetchJoin()`: loads associations of selected entities, not a DTO optimization technique.

### 16.3. Avoid N+1

If you return entities and access lazy associations inside a loop, an extra query may fire per entity. Use DTO projections with explicit JOINs or an appropriate fetch plan when entities are needed.

### 16.4. Index according to predicates and JOINs

For queries filtering by status, createdAt, and customer_id, evaluate indexes suited to the workload, such as a composite index `(status, created_at)` or an index on FK `customer_id`. Column order in a composite index should reflect selectivity and query patterns; do not apply one sample index blindly across every database.

### 16.5. Do not fetch join collections when paginating

Use two steps: paginate IDs first, then load projections/entities for those IDs. This keeps the number of entities per page exact and avoids applying limit to multiplied join rows.

### 16.6. Measure real queries

Enable SQL logging in development, use Hibernate Statistics or a datasource proxy to count queries, and run `EXPLAIN` on the database. A clean Querydsl DSL does not guarantee optimal generated SQL.

## 17. Testing Custom Repositories

Tests should verify DTO contents, dynamic predicates, JOINs, aggregates, and count queries.

Example with `@DataJpaTest`:

~~~java
@DataJpaTest
class PurchaseOrderQueryRepositoryTest {

    @Autowired
    private TestEntityManager entityManager;

    @Autowired
    private PurchaseOrderRepository orders;

    @Test
    void searchFiltersAndProjectsOrders() {
        Customer customer = new Customer("An Nguyen");
        entityManager.persist(customer);

        entityManager.persist(new PurchaseOrder(
                OrderStatus.PAID,
                Instant.parse("2026-02-10T10:00:00Z"),
                new BigDecimal("120.00"),
                customer
        ));

        entityManager.persist(new PurchaseOrder(
                OrderStatus.CANCELLED,
                Instant.parse("2026-02-11T10:00:00Z"),
                new BigDecimal("80.00"),
                customer
        ));

        entityManager.flush();
        entityManager.clear();

        OrderSearchFilter filter = new OrderSearchFilter(
                OrderStatus.PAID,
                "An",
                Instant.parse("2026-02-01T00:00:00Z"),
                Instant.parse("2026-03-01T00:00:00Z"),
                new BigDecimal("100.00")
        );

        Page<OrderSummary> page = orders.search(
                filter,
                PageRequest.of(0, 10)
        );

        assertThat(page.getContent()).hasSize(1);
        assertThat(page.getTotalElements()).isEqualTo(1);

        OrderSummary summary = page.getContent().get(0);
        assertThat(summary.customerName()).isEqualTo("An Nguyen");
        assertThat(summary.status()).isEqualTo(OrderStatus.PAID);
        assertThat(summary.total())
                .isEqualByComparingTo("120.00");
    }
}
~~~

The test assumes entities and constructors match the model section. `flush()` writes fixtures to the database, and `clear()` forces queries to read from the database rather than relying on a managed persistence context.

Add tests for:

- Omitted optional filters returning the expected scope.
- Null customer if allowed by the mapping.
- Non-matching customer names.
- Timestamps equal to `from` and equal to `to` to verify the half-open interval.
- Multiple orders with identical createdAt to verify the ID tie-breaker.
- Second page not duplicating rows.
- ToMany JOIN with multiple matching lines to verify duplicate handling and count distinct.
- GROUP BY/HAVING with customers having multiple orders and totals equal to the threshold.
- Unsupported sort properties being rejected.

For aggregates, fixtures should include two different orders with the exact same total to catch invalid usage of `SUM(DISTINCT ...)`.

## 18. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Q-type not found | Annotation processor did not run or wrong Jakarta/Javax classifier | Check Querydsl APT and generated sources |
| Repository does not pick up custom fragment | Wrong implementation name or fragment interface not extended | Use `FragmentNameImpl` and extend the fragment interface |
| DTO projection constructor error | Wrong parameter order or types | Match the constructor; consider `@QueryProjection` |
| Bean projection has null values | Alias does not match property/setter | Use exact aliases or constructor projection |
| Root rows duplicated | ToMany JOIN produces multiple rows | Use EXISTS, appropriate distinct, or align DTO grain |
| Total count larger than entity count | Counting JOIN rows instead of unique entities | Use count distinct and matching count query semantics |
| Summed total multiplied | Joining multiple collections before aggregation | Aggregate at the proper grain or isolate in a subquery |
| LEFT JOIN drops null rows | Right-table predicate placed in WHERE | Move join filter into ON when preserving left-side rows |
| Collection fetch pagination wrong | Limit applied to JOIN rows or provider paginates in memory | Paginate IDs first, then fetch details |
| Incorrect sorting | Pageable sort ignored or mapped incorrectly | Use a sort whitelist and deterministic tie-breaker |
| Query slow despite clean DSL | Unnecessary JOINs, missing indexes, or high cardinality | Inspect SQL and execution plans |
| Querydsl uses wrong namespace | Javax Querydsl artifact in Jakarta app or vice versa | Choose compatible classifier and versions |

## 19. Custom Querydsl Repository Design Checklist

- [ ] Use QuerydslPredicateExecutor only for simple queries where appropriate.
- [ ] Use repository fragments for complex JOINs/projections/grouping.
- [ ] Q-types are auto-generated by the annotation processor.
- [ ] Querydsl artifacts use the correct Jakarta/Javax namespace.
- [ ] JPAQueryFactory receives the Spring-managed EntityManager.
- [ ] Dynamic predicates are composed from validated filters.
- [ ] Mandatory tenant/owner predicates are added from server context.
- [ ] Choose inner join, left join, and on with accurate semantics.
- [ ] DTO projections have matching constructors/aliases.
- [ ] Use @QueryProjection if compile-time constructor checking is desired.
- [ ] Do not use fetch join merely to select a few DTO columns.
- [ ] Count queries count at the same grain as the result.
- [ ] ToMany JOINs do not duplicate DTOs or inflate totals.
- [ ] GROUP BY/HAVING conditions are not mistakenly placed in WHERE.
- [ ] Pageable has deterministic ordering and whitelisted sorting.
- [ ] Do not paginate directly over collection fetch joins.
- [ ] Test null cases, empty filters, duplicates, and subsequent pages.
- [ ] Measure SQL, query counts, and execution plans on the target database.

## 20. References

- [Spring Data JPA — Querydsl Extension](https://docs.spring.io/spring-data/jpa/reference/repositories/core-extensions.html#core.extensions.querydsl) — Querydsl integration and QuerydslPredicateExecutor.
- [Spring Data JPA — Custom Repository Implementations](https://docs.spring.io/spring-data/jpa/reference/repositories/custom-implementations.html) — repository fragments and implementation conventions.
- [Querydsl Reference Guide](https://querydsl.com/static/querydsl/latest/reference/html_single/) — JPAQueryFactory, joins, predicates, projections, grouping, and subqueries.
- [Querydsl JPA API](https://querydsl.com/static/querydsl/latest/apidocs/com/querydsl/jpa/impl/JPAQueryFactory.html) — creating JPA queries from the factory.
- [Jakarta Persistence Specification](https://jakarta.ee/specifications/persistence/) — JPQL, joins, fetch joins, grouping, and pagination semantics.
- [Hibernate ORM User Guide](https://docs.hibernate.org/orm/current/userguide/html_single/Hibernate_User_Guide.html) — fetching, pagination, query execution, and persistence context.

A custom Querydsl repository keeps complex queries in one structured, type-checked place. Use Q-types for predicates, JOIN the right associations, use DTO projections for read data, and make count queries reflect the exact count of objects the caller wants to paginate. For collection JOINs and aggregates, decide the result grain before writing the query; then verify SQL, row counts, and execution plans with integration tests.