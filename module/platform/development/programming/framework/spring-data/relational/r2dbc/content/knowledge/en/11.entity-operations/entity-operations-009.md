# Using Step-by-Step Fluent Operations to Express Queries

Spring Data R2DBC provides `R2dbcEntityTemplate` with a step-by-step interface (fluent API). Instead of assembling a long SQL string, an application can describe a query in meaningful steps: choosing the entity type, building conditions, sorting, limiting results, and selecting how to consume the publisher. The same API style is also used for insert, update, and delete.

The fluent API fits well when queries must be built dynamically from input parameters while preserving Spring Data's entity mapping. It sits at a higher abstraction level than `DatabaseClient`: the application works with entities, properties, and `Query`/`Criteria`, while Spring Data translates those descriptions into database-appropriate statements.

## 1. R2dbcEntityTemplate in the Data Access Architecture

`R2dbcEntityTemplate` is Spring Data Relational's abstraction for operating on entities over R2DBC. It relies on `DatabaseClient` and `MappingR2dbcConverter` to execute SQL, bind parameters, and convert between database rows and Java objects.

You can select the API level based on your needs:

| API | Purpose |
| --- | --- |
| Reactive repository | CRUD operations and method-name derived queries |
| `R2dbcEntityTemplate` fluent API | Building entity queries step by step with `Query`, `Criteria`, and `Sort` |
| `DatabaseClient` | Executing custom SQL and mapping results as desired |
| R2DBC SPI | Low-level control over connections, statements, and results |

The fluent API eliminates manual connection handling and row-by-row `Row` mapping for common entity queries. It retains the reactive model: operations return `Mono` or `Flux` and execute only when the publisher is subscribed to.

## 2. Configuring and Injecting R2dbcEntityTemplate

In a Spring Boot application with the R2DBC starter and a suitable driver, Spring normally auto-configures `DatabaseClient`, the mapping infrastructure, and `R2dbcEntityTemplate`.

You can inject the template into a service:

```java
import org.springframework.data.r2dbc.core.R2dbcEntityTemplate;
import org.springframework.stereotype.Service;

@Service
public class ProductQueryService {

    private final R2dbcEntityTemplate template;

    public ProductQueryService(R2dbcEntityTemplate template) {
        this.template = template;
    }
}
```

If a project needs to configure multiple `ConnectionFactory` beans or multiple databases manually, create corresponding templates and wire the proper converters, mapping contexts, and transaction managers. For single-database applications, rely on auto-configuration whenever it meets your needs.

Example entity:

```java
import java.math.BigDecimal;
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Table;

@Table("product")
public record Product(
        @Id Long id,
        String name,
        String status,
        BigDecimal price
) {}
```

Java property names are mapped to columns by Spring Data according to mapping rules and metadata. Use `@Column` when a column name differs from the default convention.

## 3. Basic Steps of the Fluent API

For read operations, the expression typically looks like:

```java
template.select(Product.class)
        .matching(query(Criteria.where("status").is("ACTIVE")))
        .all();
```

Each step has a distinct role:

1. `select(Product.class)` specifies the entity type to read.
2. `matching(query(...))` supplies the query criteria.
3. `all()` requests emitting all matching results as a `Flux<Product>`.

Steps chain into a readable expression. The return type remains reactive: `all()` returns a multi-element publisher; the application can further apply `map`, `filter`, `take`, `collectList`, or return the `Flux` to WebFlux.

Other operations follow the same pattern:

```java
template.insert(Product.class).using(product);

template.update(Product.class)
        .matching(query(Criteria.where("id").is(id)))
        .apply(Update.update("status", "ARCHIVED"));

template.delete(Product.class)
        .matching(query(Criteria.where("id").is(id)))
        .all();
```

The fluent API describes intent step by step; the publisher performs work only when consumed.

## 4. Building a Query with Criteria

`Query` represents conditions, sorting, and limits for a query. `Criteria` describes predicates on entity properties.

Commonly used comparison operators:

| Criteria | Meaning |
| --- | --- |
| `is(value)` | Equal to value |
| `not().is(value)` | Negates equality comparison |
| `greaterThan(value)` | Greater than |
| `greaterThanOrEquals(value)` | Greater than or equal to |
| `lessThan(value)` | Less than |
| `lessThanOrEquals(value)` | Less than or equal to |
| `in(values)` | Contained in a set of values |
| `notIn(values)` | Not contained in a set of values |
| `like(pattern)` | Pattern matching |
| `isNull()` | Value is null |
| `isNotNull()` | Value is not null |

Example finding active products:

```java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
);

Flux<Product> products = template.select(Product.class)
        .matching(query)
        .all();
```

The name passed to `Criteria.where(...)` is typically the entity's persistent property name, not necessarily the cased or physical SQL column name after mapping. Spring Data uses metadata to resolve the property to the right column.

### Combining Multiple AND Conditions

```java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .and("price").greaterThanOrEquals(new BigDecimal("100"))
        .and("name").like("%keyboard%");

Query query = Query.query(criteria);
```

All conditions chained with `and` must hold for a row to be selected.

### Combining OR Conditions

```java
Criteria criteria = Criteria.where("status").is("ACTIVE")
        .or("status").is("FEATURED");

Query query = Query.query(criteria);
```

This condition selects products whose status is ACTIVE or FEATURED. For complex expressions mixing multiple AND/OR groups, construct explicit `Criteria` groupings and verify that the generated SQL matches the logical precedence business rules require.

## 5. Building Dynamic Queries from Parameters

A common scenario is a search screen letting users pick optional filters. Avoid writing separate repository methods for every combination of filters. Start with a required predicate and append `Criteria` when optional parameters are provided:

```java
public Flux<Product> searchProducts(
        String status,
        BigDecimal minimumPrice,
        String namePart) {

    Criteria criteria = Criteria.where("status").is(status);

    if (minimumPrice != null) {
        criteria = criteria.and("price")
                .greaterThanOrEquals(minimumPrice);
    }

    if (namePart != null && !namePart.isBlank()) {
        criteria = criteria.and("name")
                .like("%" + namePart + "%");
    }

    Query query = Query.query(criteria);

    return template.select(Product.class)
            .matching(query)
            .all();
}
```

Here, status is a required condition; minimum price and name substring are added only when supplied by the user. Values are passed through Criteria so Spring Data handles them as query parameters. Never concatenate input values directly into SQL strings.

If every filter is optional, design how the initial criteria group is constructed according to the API of your Spring Data version. Avoid concatenating SQL snippets or column names from untrusted data. For dynamic queries with many branches, extracting a Criteria builder helper keeps the service clean.

Note that parameter values can be bound safely, whereas sort property names or dynamic column names form part of the query structure. If clients can select sort fields, map them through an allowlist of permitted fields instead of passing arbitrary strings verbatim.

## 6. Sorting, Limiting, and Pagination

`Query` can be combined with `Sort`, `limit`, and `offset`:

```java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
)
        .sort(Sort.by(Sort.Order.desc("price")))
        .limit(20)
        .offset(40);

Flux<Product> page = template.select(Product.class)
        .matching(query)
        .all();
```

This query fetches up to 20 products starting at offset 40, sorted by descending price. In production applications, add a deterministic tie-breaker such as ID so rows with equal prices retain a stable order:

```java
Sort sort = Sort.by(
        Sort.Order.desc("price"),
        Sort.Order.asc("id")
);
```

Offset pagination is convenient for numbered page screens, but large offsets force the database to skip many rows before returning results. For large or rapidly changing datasets, consider keyset pagination: use the values from the last row of the previous page (e.g., `price` and `id`) as predicates for the next page.

When building paginated APIs, bound `pageSize` and `offset` so clients cannot request excessive amounts of data. Avoid calling `collectList()` by default on unbounded query results.

## 7. Reading All, Taking One Result, or Taking the First Element

With fluent select, `all()` returns a `Flux<T>` to stream all matching rows:

```java
public Flux<Product> findActiveProducts() {
    Query query = Query.query(
            Criteria.where("status").is("ACTIVE")
    );

    return template.select(Product.class)
            .matching(query)
            .all();
}
```

If only the first element is needed, limit the query or apply an operator to the publisher:

```java
public Mono<Product> findCheapestActiveProduct() {
    Query query = Query.query(
            Criteria.where("status").is("ACTIVE")
    )
            .sort(Sort.by(Sort.Order.asc("price")))
            .limit(1);

    return template.select(Product.class)
            .matching(query)
            .all()
            .next();
}
```

`next()` takes the first element emitted by the Flux and completes. Setting `limit(1)` on the Query ensures the database needs to return at most one row. If business rules require verifying genuine uniqueness, enforce it with a constraint and use an API with matching semantics; taking the first item does not prove only one row existed.

## 8. Step-by-Step Insert

Fluent insert starts with the entity class and finishes with the entity to persist:

```java
public Mono<Product> createProduct(
        String name,
        BigDecimal price) {

    Product product = new Product(
            null,
            name,
            "ACTIVE",
            price
    );

    return template.insert(Product.class)
            .using(product);
}
```

`insert(Product.class)` identifies the entity type and mapping metadata. `using(product)` provides the object to insert. The publisher emits the saved entity, potentially containing a database-generated ID.

For immutable entities such as records, always use the instance emitted by the publisher:

```java
return template.insert(Product.class)
        .using(product)
        .map(saved -> saved.id());
```

Explicit insert is helpful when business logic is certain it is creating a new record. If you want Spring Data to choose between insert and update based on entity state, use `repository.save(entity)`; the two APIs express different intents.

## 9. Conditional Update

Fluent update uses `matching(Query)` to select target rows and `apply(Update)` to specify fields to modify:

```java
public Mono<Long> archiveProduct(Long id) {
    Query query = Query.query(
            Criteria.where("id").is(id)
    );

    Update update = Update.update("status", "ARCHIVED");

    return template.update(Product.class)
            .matching(query)
            .apply(update);
}
```

The result is the updated row count as a publisher. If the ID matches no rows, the updated row count may be 0.

Multiple fields can be updated in a single call:

```java
Update update = Update.update("status", "ACTIVE")
        .set("price", new BigDecimal("129.00"));
```

Update conditions must be scoped carefully. If Query lacks a sufficiently narrow predicate, multiple rows can be modified. For ID-targeted operations, use the primary key criterion. For batch updates, make business conditions explicit and inspect the affected row count.

Fluent update modifies only the listed columns without loading the full entity to call `save`. This is beneficial for updating a few fields or performing conditional updates.

## 10. Conditional Delete

Fluent delete follows the same model:

```java
public Mono<Long> deleteProduct(Long id) {
    Query query = Query.query(
            Criteria.where("id").is(id)
    );

    return template.delete(Product.class)
            .matching(query)
            .all();
}
```

`all()` executes the deletion for matching rows and returns the affected row count. Here `all()` means applying to all rows matching the Query; therefore, exercise extra caution if conditions could be empty or broader than expected.

Example deleting discontinued products:

```java
public Mono<Long> deleteArchivedProducts() {
    Query query = Query.query(
            Criteria.where("status").is("ARCHIVED")
    );

    return template.delete(Product.class)
            .matching(query)
            .all();
}
```

If the database has foreign keys referencing products, the delete statement may be rejected or trigger configured constraint actions. The fluent API does not bypass database integrity rules.

## 11. Combining the Fluent API with Reactive Operators

Because template results are publishers, they compose naturally with Reactor operators:

```java
public Flux<ProductSummary> findActiveSummaries() {
    Query query = Query.query(
            Criteria.where("status").is("ACTIVE")
    );

    return template.select(Product.class)
            .matching(query)
            .all()
            .map(product -> new ProductSummary(
                    product.id(),
                    product.name(),
                    product.price()
            ))
            .filter(summary -> summary.price().signum() > 0);
}
```

Here, the template produces `Flux<Product>`; `map` converts entities to DTOs; `filter` retains items matching an additional condition. Whenever a filter can be expressed in SQL, prefer putting it into `Criteria` so the database filters rows early and reduces data sent over the wire.

If you need to combine results from two independent publishers, use `Mono.zip` or a suitable combinator. If a second query depends on a value from the first query, use `flatMap`. Never call `block()` to retrieve intermediate values in a reactive service.

## 12. Fluent API vs. DatabaseClient: Picking the Right Abstraction Level

Not every query should use the fluent entity API. Choose the tool according to data shape and purpose:

| Need | Suitable Choice |
| --- | --- |
| Standard CRUD by ID | Reactive repository |
| Finding entities with dynamic conditions | `R2dbcEntityTemplate` + `Query`/`Criteria` |
| Conditional insert/update/delete | Template fluent operations |
| Complex SQL JOINs or CTEs | `DatabaseClient` |
| Custom projections not mapping directly to entities | `DatabaseClient` or specialized queries |
| Low-level statement and result control | R2DBC SPI |

Example using `DatabaseClient` when a JOIN is needed:

```java
public Flux<ProductSummary> findProductSummaries() {
    return databaseClient.sql("""
            SELECT p.id, p.name, p.price, c.name AS category_name
            FROM product p
            JOIN category c ON c.id = p.category_id
            WHERE p.status = :status
            ORDER BY p.name
            """)
            .bind("status", "ACTIVE")
            .map((row, metadata) -> new ProductSummary(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("price", BigDecimal.class),
                    row.get("category_name", String.class)
            ))
            .all();
}
```

This JOIN query fits a read model pulling fields from multiple tables. The fluent entity API focuses on a single entity and its mapping metadata; `DatabaseClient` fits better when explicit control over SQL and result shapes is central.

## 13. Property Names, Column Names, and Mapping

When writing Criteria, Sort, or Update, use the entity's persistent property names according to Spring Data metadata. For example, an entity property `createdAt` may map to column `created_at`; in Query and Sort you typically use `createdAt`, whereas hand-written SQL in `DatabaseClient` uses the database column name `created_at`.

Example:

```java
Query query = Query.query(
        Criteria.where("status").is("ACTIVE")
)
        .sort(Sort.by(Sort.Order.desc("createdAt")));
```

Using the wrong property name can cause mapping to fail to locate the property or generate unexpected SQL. When a column name is a database reserved word or diverges from the default naming convention, declare the mapping explicitly with `@Column`.

## 14. Transactions and Multiple Fluent Operations

If a use case requires multiple write operations to commit or roll back together, wrap them in a reactive transaction:

```java
@Transactional
public Mono<Product> createProductAndAudit(Product product) {
    return template.insert(Product.class)
            .using(product)
            .flatMap(saved ->
                    auditTemplate.insert(ProductAudit.class)
                            .using(new ProductAudit(
                                    null,
                                    saved.id(),
                                    "CREATED"
                            ))
                            .thenReturn(saved)
            );
}
```

This example assumes both templates share the same database and an appropriate reactive transaction manager. The publisher must be returned within the same pipeline so the transaction manager oversees the reactive lifecycle. Never call `subscribe()` inside a transactional method, as that detaches the operation from the publisher tracked by the transaction manager.

## 15. Common Pitfalls When Using the Fluent API

1. **Forgetting to consume the publisher.** Constructing a fluent expression does not execute SQL; return the publisher to the framework or subscribe at the proper boundary.
2. **Using column names instead of property names in Criteria.** Entity queries use mapping metadata; verify property names.
3. **Building dynamic conditions by concatenating SQL.** Use Criteria and bound values; prevent SQL injection.
4. **Allowing clients to pass arbitrary sort names.** Allowlist properties permitted for sorting.
5. **Updating or deleting with overly broad conditions.** Inspect Query predicates before running write operations.
6. **Using `next()` as a uniqueness check.** It simply takes the first element; uniqueness requires constraints or explicit cardinality checks.
7. **Very large offset pagination.** Consider keyset pagination on large tables.
8. **Collecting an unbounded Flux into a List.** Apply limits or pagination as needed.
9. **Forcing complex JOIN queries into the template.** Use DatabaseClient when SQL and custom projections are the focus.
10. **Subscribing manually inside services.** Keep the publisher chain intact so the framework coordinates errors, cancellation, and transactions.

## Operation Selection Workflow

- Choose the entity class via `select`, `insert`, `update`, or `delete`.
- For read queries, express conditions using `Query` and `Criteria`.
- Add `Sort`, `limit`, and `offset` if sorting or pagination is needed.
- End select with `all()` for a `Flux`; use an appropriate operator if only a single result is needed.
- For insert, supply the entity via `using(...)`.
- For update, identify rows with `matching(query)` and specify changes with `apply(update)`.
- For delete, tightly define rows to remove with `matching(query)` and invoke `all()`.
- Keep publishers reactive and switch to `DatabaseClient` when custom SQL or complex JOINs are required.

Spring Data R2DBC's fluent API lets queries be expressed as meaningful, composable steps driven by input parameters. `Query` and `Criteria` describe conditions, `Sort` and limits control the result set, and `select`, `insert`, `update`, and `delete` make entity operations explicit. By selecting the right abstraction level and preserving the reactive publisher chain, data access code remains readable and extensible while leveraging Spring Data's mapping and execution engine.
