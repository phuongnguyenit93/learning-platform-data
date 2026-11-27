# Selecting the Target Table and Result Type for Each Operation

## 1. Two Decisions When Building a Data Operation

When working with relational databases in Spring Data R2DBC, every data operation needs two things clearly defined:

1. **Which table does the operation target?** The table can be inferred from entity mapping, specified via an entity class in the template, or written explicitly in SQL.
2. **In what form does the application need the result?** The result may be a single entity, multiple entities, a scalar value such as affected row count, a boolean flag, or simply a completion signal.

These two decisions are related, yet distinct. The entity type typically determines the table and data mapping; the return type determines how the caller consumes the result in the reactive pipeline.

For example:

- Creating a new Customer: the target table is `customers`, and a useful result is `Mono<Customer>` to receive the entity with its database-generated ID.
- Finding active Customers: the target table is still `customers`, and the result is `Flux<Customer>`.
- Updating status: the target table is `customers`, and the result is usually `Mono<Long>` representing the affected row count.
- Checking whether an email exists: the target table is `customers`, and the result is `Mono<Boolean>`.
- Deleting a record via a CRUD repository: the standard result is typically `Mono<Void>`, signaling only completion.

Spring Data R2DBC provides multiple API levels to express these choices: repositories, `R2dbcEntityTemplate`, and `DatabaseClient`.

## 2. Selecting the Target Table via Entity Mapping

### 2.1. @Table Identifies an Entity's Table

With repositories or template entity mapping, Spring Data needs to know which table corresponds to an entity. You can declare the table name using the `@Table` annotation:

~~~java
import org.springframework.data.annotation.Id;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Table;

@Table("customers")
public record Customer(
        @Id Long id,
        String name,
        @Column("email_address") String email,
        String status
) {}
~~~

In this example:

- `Customer` is the mapped domain type.
- `@Table("customers")` specifies the target table.
- `@Id` marks the primary key.
- `@Column("email_address")` maps the `email` property to the `email_address` column.

If no explicit table name is provided, Spring Data can derive the name from the entity type using a naming strategy. Against an existing schema, verify the physical table/column names and use `@Table` and `@Column` where needed.

### 2.2. A Repository Is Bound to One Entity Type

A repository declares its entity type and ID type:

~~~java
import org.springframework.data.repository.reactive.ReactiveCrudRepository;

public interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {

    Mono<Customer> findByEmail(String email);

    Flux<Customer> findByStatus(String status);

    Mono<Boolean> existsByEmail(String email);

    Mono<Long> countByStatus(String status);
}
~~~

Because the repository is declared for `Customer`, its CRUD operations and derived queries operate on the table mapped from `Customer`. Method names define query conditions; the generic entity type determines the data model to read/write.

You cannot switch a repository to a different table simply by changing a method's return type. To operate on another table, use a repository for that entity, pass a different domain type to the template, or write explicit SQL via DatabaseClient.

### 2.3. Entity Type and Table Are Separate Mapping Concepts

A table does not have to share the exact name of a Java class. For example, `PurchaseOrder` may map to `purchase_orders`. Conversely, a reporting query may read columns across multiple tables and return a DTO such as `OrderSummary`.

In the latter case, the DTO only describes the output shape; it does not identify a table on its own. The SQL or query mapping determines where the data comes from.

## 3. Selecting the Target Table with R2dbcEntityTemplate

`R2dbcEntityTemplate` provides entity-oriented APIs for insert, select, update, delete, count, and exists. For these operations, the entity class passed to the template lets Spring Data look up mapping metadata to resolve the table and column mappings.

### 3.1. Inserting into the Entity's Table

~~~java
Mono<Customer> inserted =
        template.insert(Customer.class)
                .using(new Customer(
                        null,
                        "An Nguyen",
                        "an@example.test",
                        "ACTIVE"
                ));
~~~

`Customer.class` tells the template the entity type and mapped table. `using(...)` supplies the object to insert. The result is `Mono<Customer>`, emitting the saved entity with any generated ID or persistence-updated values when supported by the database/driver.

### 3.2. Selecting from the Entity's Table

~~~java
Query query = Query.query(Criteria.where("status").is("ACTIVE"));

Flux<Customer> activeCustomers =
        template.select(query, Customer.class);
~~~

Here, `Customer.class` selects the table and result mapping; `Query` defines the filter condition. The result is `Flux<Customer>` because the query may match multiple customers.

When at most one result is needed:

~~~java
Mono<Customer> customer =
        template.selectOne(
                Query.query(Criteria.where("email").is("an@example.test")),
                Customer.class
        );
~~~

Use `selectOne` when business logic or database constraints guarantee at most one row. If the query can match multiple rows, use `select` with `Flux`, or explicitly select the first element under a defined ordering.

### 3.3. Updating the Entity's Table

~~~java
Query query = Query.query(Criteria.where("id").is(customerId));

Mono<Long> updatedRows =
        template.update(Customer.class)
                .matching(query)
                .apply(Update.update("status", "INACTIVE"));
~~~

`Customer.class` determines the table to update. `matching(query)` selects matching rows. `apply(update)` specifies the columns to change. The result is `Mono<Long>` representing the updated row count.

When filtering by primary key, the result is typically 0 or 1. A value of 0 can mean the record does not exist or no longer satisfies the condition; do not assume 0 is automatically a database error.

### 3.4. Deleting from the Entity's Table

~~~java
Query query = Query.query(Criteria.where("id").is(customerId));

Mono<Long> deletedRows =
        template.delete(Customer.class)
                .matching(query)
                .all();
~~~

`Customer.class` identifies the table to delete from. `Mono<Long>` reports how many rows were deleted. Even when deleting by primary key, make sure conditions are specific enough to avoid accidentally deleting multiple rows.

### 3.5. Count and Exists

These two operations do not need to return entities:

~~~java
Mono<Long> customerCount =
        template.count(
                Query.query(Criteria.where("status").is("ACTIVE")),
                Customer.class
        );

Mono<Boolean> customerExists =
        template.exists(
                Query.query(Criteria.where("email").is("an@example.test")),
                Customer.class
        );
~~~

Both still use the entity type to resolve the target table. However, the result type matches the business question: quantity uses `Mono<Long>`, while existence uses `Mono<Boolean>`.

## 4. Choosing the Result Type by Row Cardinality

Reactor provides two primary types to represent data results:

- **Mono<T>:** a publisher emitting at most one value of type T, or completing empty if none exists.
- **Flux<T>:** a publisher emitting zero, one, or many values of type T.

Pick the type based on the cardinality expected by business logic:

| Need | Typical Result Type | Meaning |
|---|---|---|
| Read by primary key | `Mono<Customer>` | Zero or one entity |
| Read by unique key | `Mono<Customer>` | Zero or one entity if uniqueness is enforced |
| Read a list | `Flux<Customer>` | Zero or many entities |
| Count rows | `Mono<Long>` | Single count value |
| Check existence | `Mono<Boolean>` | Single true/false value |
| Wait for completion without data | `Mono<Void>` | Completion or error signal only |
| Update/delete needing row count | `Mono<Long>` | Affected row count |
| Return an aggregated DTO | `Mono<OrderSummary>` or `Flux<OrderSummary>` | One or many projections |

### 4.1. Mono Is Not a Nullable Object

Reactive Streams does not permit emitting null values. If a query finds no rows, `Mono<Customer>` completes without emitting an item. You can handle that case with operators such as:

~~~java
return customerRepository.findById(id)
        .switchIfEmpty(Mono.error(
                new CustomerNotFoundException(id)
        ));
~~~

Do not use null to represent a missing result. `Mono.empty()` and an error signal are two distinct states: empty means no result was found; error means the operation failed.

### 4.2. Choose Mono Only When There Is Truly At Most One Row

Queries by primary key or columns backed by a unique constraint fit `Mono<T>`. If a condition is non-unique yet the method declares `Mono<T>`, multiple matching rows can trigger a cardinality error rather than arbitrarily picking one.

If business logic wants the first matching record, specify a deterministic order:

~~~java
@Query("""
    SELECT id, name, email_address, status
    FROM customers
    WHERE status = :status
    ORDER BY id
    LIMIT 1
    """)
Mono<Customer> findFirstByStatus(String status);
~~~

This SQL example uses PostgreSQL syntax. With derived queries, you can use prefixes such as `findFirst...` or `findTop...` as supported by Spring Data query derivation. When writing custom SQL, add `ORDER BY` so the result is deterministic.

### 4.3. Choose Flux for Result Sets

~~~java
Flux<Customer> customers = customerRepository.findByStatus("ACTIVE");
~~~

`Flux` fits when result counts are variable or may span multiple rows. However, Flux does not guarantee the database returns rows in any particular order on its own. If ordering matters, add `ORDER BY` to the query.

For large datasets, consider pagination, row limits, and backpressure. Avoid converting a very large Flux into an in-memory List unless genuinely necessary.

## 5. Result Types for Each CRUD Operation

### 5.1. Insert: Return the Saved Entity

Repository:

~~~java
Mono<Customer> saved = customerRepository.save(customer);
~~~

Template:

~~~java
Mono<Customer> inserted =
        template.insert(Customer.class).using(customer);
~~~

Returning the entity is useful when the application needs database-generated IDs, versions, or persistence-updated fields. Use the entity emitted by the publisher, especially for immutable entities such as Java records.

If you only need to know that the operation finished without needing the entity, convert the result to a completion signal:

~~~java
Mono<Void> completed =
        customerRepository.save(customer).then();
~~~

After calling `then()`, the saved entity and its ID are no longer emitted downstream. Choose `Mono<Void>` only when you truly do not need those values.

### 5.2. Select: Return One Entity or Many Entities

~~~java
Mono<Customer> one = customerRepository.findById(id);

Flux<Customer> many = customerRepository.findByStatus("ACTIVE");
~~~

Choose the type based on cardinality and data constraints. For single-row lookups, rely on primary keys or unique keys. For list queries, use Flux and add ordering/pagination where appropriate.

### 5.3. Update: Return Affected Row Count

Repositories can expose custom update methods depending on query method capabilities and SQL:

~~~java
@Modifying
@Query("""
    UPDATE customers
    SET status = :status
    WHERE id = :id
    """)
Mono<Integer> updateStatus(Long id, String status);
~~~

For modifying queries, the return type is typically chosen to receive the affected row count as supported by Spring Data/the driver—for example `Mono<Integer>` or `Mono<Long>`, depending on your version's supported method signatures. For clear, consistent counts, `R2dbcEntityTemplate.update(...).apply(...)` returns `Mono<Long>`.

If you need to verify that exactly one row was updated, check the count:

~~~java
return template.update(Customer.class)
        .matching(Query.query(Criteria.where("id").is(id)))
        .apply(Update.update("status", "INACTIVE"))
        .flatMap(rows -> {
            if (rows == 0) {
                return Mono.error(new CustomerNotFoundException(id));
            }
            return Mono.just(rows);
        });
~~~

A row count of 0 may mean no record was found or the condition no longer holds. When updating with a version check to prevent overwrites, 0 rows can also indicate a conflict depending on the execution path.

### 5.4. Delete: Return Row Count or Completion Only

Standard CRUD methods like `deleteById(id)` return `Mono<Void>`, which fits when you only need to know the operation completed.

If you need the deleted row count, use the template:

~~~java
Mono<Long> deleted =
        template.delete(Customer.class)
                .matching(Query.query(Criteria.where("id").is(id)))
                .all();
~~~

Or use DatabaseClient to run SQL and retrieve affected rows:

~~~java
Mono<Long> deletedRows =
        databaseClient.sql("DELETE FROM customers WHERE id = :id")
                .bind("id", id)
                .fetch()
                .rowsUpdated();
~~~

### 5.5. Count and Exists: Return Scalar Types

Do not load entire entities just to count or check existence:

~~~java
Mono<Long> count = customerRepository.count();

Mono<Boolean> exists = customerRepository.existsById(id);
~~~

Using scalar APIs minimizes data transferred from the database and avoids unnecessary entity mapping.

## 6. Choosing Results When Using DatabaseClient

`DatabaseClient` lets you write explicit SQL. Because SQL itself names the table in the FROM, INSERT, UPDATE, or DELETE clause, an entity type no longer automatically determines the table as with repository/template mapping.

### 6.1. Selecting the Table via SQL

~~~java
databaseClient.sql("""
        SELECT id, name, email_address, status
        FROM customers
        WHERE status = :status
        """)
    .bind("status", "ACTIVE")
    .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("name", String.class),
            row.get("email_address", String.class),
            row.get("status", String.class)
    ))
    .all();
~~~

The `FROM customers` clause selects the table. The `map` callback determines the output type by constructing `Customer`. The `all()` method returns `Flux<Customer>`.

### 6.2. Selecting a Single Result

~~~java
Mono<Customer> customer =
        databaseClient.sql("""
                SELECT id, name, email_address, status
                FROM customers
                WHERE id = :id
                """)
            .bind("id", id)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("email_address", String.class),
                    row.get("status", String.class)
            ))
            .one();
~~~

`one()` fits when the query is expected to return at most one row. If you need the first row from a multi-row result set, use the appropriate `first()` API and always include `ORDER BY` in the SQL.

### 6.3. Choosing a DTO/Projection as the Result Type

Not every query needs to hydrate a full entity. A list view may only require ID, name, and status:

~~~java
public record CustomerSummary(Long id, String name, String status) {}
~~~

SQL fetches only the necessary columns and the callback maps them to the DTO:

~~~java
Flux<CustomerSummary> summaries =
        databaseClient.sql("""
                SELECT id, name, status
                FROM customers
                WHERE status = :status
                ORDER BY id
                """)
            .bind("status", "ACTIVE")
            .map((row, metadata) -> new CustomerSummary(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("status", String.class)
            ))
            .all();
~~~

DTOs/projections reduce the number of columns read and decouple read shapes from write entities. For repository query methods, Spring Data also supports projections where appropriate; for custom SQL or aggregations, DatabaseClient gives explicit control over mapping.

### 6.4. Non-Returning DML: rowsUpdated()

When executing UPDATE or DELETE and only needing the affected row count:

~~~java
Mono<Long> affected =
        databaseClient.sql("""
                UPDATE customers
                SET status = :status
                WHERE id = :id
                """)
            .bind("status", "INACTIVE")
            .bind("id", id)
            .fetch()
            .rowsUpdated();
~~~

`rowsUpdated()` returns the affected row count reported by the driver. If you need data returned after the statement, use your database's returning clause and map result rows instead of taking only the row count.

### 6.5. DML with RETURNING

PostgreSQL supports `RETURNING` for INSERT, UPDATE, and DELETE. Example:

~~~java
Mono<Customer> inserted =
        databaseClient.sql("""
                INSERT INTO customers (name, email_address, status)
                VALUES (:name, :email, :status)
                RETURNING id, name, email_address, status
                """)
            .bind("name", name)
            .bind("email", email)
            .bind("status", status)
            .map((row, metadata) -> new Customer(
                    row.get("id", Long.class),
                    row.get("name", String.class),
                    row.get("email_address", String.class),
                    row.get("status", String.class)
            ))
            .one();
~~~

Here, the SQL targets the `customers` table; `RETURNING` instructs PostgreSQL to emit the resulting row; the callback selects `Customer`; and `one()` expresses a single-row result. This is a dialect-specific feature; do not assume every database supports the exact same syntax.

## 7. Targeting Different Tables in the Same Application

An application can have multiple entities and repositories:

~~~java
@Table("customers")
public record Customer(@Id Long id, String name) {}

@Table("orders")
public record Order(@Id Long id, Long customerId, String status) {}
~~~

Each repository pairs with one entity:

~~~java
interface CustomerRepository
        extends ReactiveCrudRepository<Customer, Long> {}

interface OrderRepository
        extends ReactiveCrudRepository<Order, Long> {}
~~~

Or use the template with the corresponding target class:

~~~java
Mono<Customer> customer =
        template.selectOne(customerQuery, Customer.class);

Flux<Order> orders =
        template.select(orderQuery, Order.class);
~~~

A single `R2dbcEntityTemplate` instance can operate across multiple tables because each call specifies the target entity class. That type's metadata determines the table and mappings.

If a table is not mapped as a standalone entity, or a query joins multiple tables, use DatabaseClient and write explicit SQL. Do not invent a fake entity just to force a reporting query into an ill-fitting mapping.

## 8. Dynamic Table Selection: Limits and Safe Patterns

In some systems, the target table depends on a selected resource type. However, table names are SQL identifiers; they cannot be bound like regular parameter values.

The following example is invalid for identifier binding:

~~~java
databaseClient.sql("SELECT * FROM :tableName")
        .bind("tableName", tableName);
~~~

Parameter binding applies only to data values. If dynamic table selection is truly required, use an application-controlled allowlist:

~~~java
Map<String, String> tableNames = Map.of(
        "customers", "customers",
        "orders", "orders"
);

String table = tableNames.get(resourceType);
if (table == null) {
    return Mono.error(new IllegalArgumentException("Unsupported resource"));
}

String sql = "SELECT id FROM " + table + " WHERE status = :status";

return databaseClient.sql(sql)
        .bind("status", status)
        .map((row, metadata) -> row.get("id", Long.class))
        .all();
~~~

The string concatenated into SQL here comes strictly from a static allowlist. Never use table names supplied directly by users, as that opens SQL injection through identifiers.

When the set of tables is finite and each table has its own model, using dedicated repositories or template calls with each entity type is usually cleaner than dynamic SQL.

## 9. Ensuring the Result Type Fits the Operation

Choosing a return type is not just a matter of syntax. It governs how the application detects business states.

### 9.1. Zero Rows vs. One Row

For update/delete by ID, the affected row count can be:

- 0: no row matched the condition.
- 1: one row was modified.
- Greater than 1: the condition was not narrow enough, or business logic permits multi-row changes.

If the operation is expected to affect strictly one row, validate the count:

~~~java
return updatedRows.flatMap(rows -> {
    if (rows != 1) {
        return Mono.error(new IllegalStateException(
                "Expected exactly one updated row, got " + rows
        ));
    }
    return Mono.just(rows);
});
~~~

Not every zero-row outcome is an error. For instance, an idempotent delete may treat an already-absent record as a normal completion. Base the decision on the business contract.

### 9.2. Mono<Void> Provides No Row Count

`Mono<Void>` emits only a completion or error signal. It does not tell you how many rows were updated or deleted.

If an API needs to return 404 when no record exists or report the modified row count, choose an API that returns a count or add an appropriate check. Avoid discarding the result with `then()` prematurely if callers still need it.

### 9.3. Mono<Boolean> and Mono<Long> Do Not Replace Entities

When you only need an existence check, `Mono<Boolean>` is cheaper than loading an entity. When you only need a count, `Mono<Long>` is far better than loading the entire result set and counting in Java.

Conversely, if subsequent steps need the database-generated ID, version, or updated fields, retain the entity result instead of reducing it to a boolean or count.

## 10. Choosing an API Based on Need

| Need | API to Consider | How Table Is Determined | Result Type |
|---|---|---|---|
| Standard CRUD for one entity | ReactiveCrudRepository | Generic entity type and @Table | Mono<Entity>, Flux<Entity>, Mono<Void> |
| Explicit insert | R2dbcEntityTemplate | Target class | Mono<Entity> |
| Select with Criteria | R2dbcEntityTemplate | Target class | Mono<Entity> or Flux<Entity> |
| Conditional update/delete | R2dbcEntityTemplate | Target class | Mono<Long> affected rows |
| Conditional count/exists | R2dbcEntityTemplate | Target class | Mono<Long> / Mono<Boolean> |
| SQL JOIN or reporting | DatabaseClient | Table written in SQL | Mono<DTO> / Flux<DTO> |
| SQL DML needing row count | DatabaseClient | Table written in SQL | Mono<Long> via rowsUpdated |
| SQL DML returning records | DatabaseClient and RETURNING if supported | Table written in SQL | Mono<DTO> / Flux<DTO> |
| Selecting among a finite set of tables | Dedicated repository/template or DatabaseClient with allowlist | Entity type or allowlisted identifier | Per business result |

Repositories are usually the simplest choice for CRUD and entity-bound query methods. The template fits when building queries/updates using mapping metadata. DatabaseClient fits when you need concrete SQL, multiple tables, custom projections, or database-specific features.

## 11. Example Service Combining Multiple Result Types

A single service can expose different return types depending on each operation:

~~~java
@Service
public class CustomerService {

    private final CustomerRepository repository;
    private final R2dbcEntityTemplate template;

    public CustomerService(
            CustomerRepository repository,
            R2dbcEntityTemplate template) {
        this.repository = repository;
        this.template = template;
    }

    public Mono<Customer> create(Customer customer) {
        return repository.save(customer);
    }

    public Mono<Customer> findById(Long id) {
        return repository.findById(id);
    }

    public Flux<Customer> findActive() {
        return repository.findByStatus("ACTIVE");
    }

    public Mono<Long> deactivate(Long id) {
        return template.update(Customer.class)
                .matching(Query.query(Criteria.where("id").is(id)))
                .apply(Update.update("status", "INACTIVE"));
    }

    public Mono<Boolean> existsByEmail(String email) {
        return repository.existsByEmail(email);
    }

    public Mono<Long> countActive() {
        return template.count(
                Query.query(Criteria.where("status").is("ACTIVE")),
                Customer.class
        );
    }

    public Mono<Long> deleteByIdAndCount(Long id) {
        return template.delete(Customer.class)
                .matching(Query.query(Criteria.where("id").is(id)))
                .all();
    }
}
~~~

A service does not need the same return type across all methods. Each return type is chosen for what the caller needs to know:

- create needs the saved entity.
- findById may find nothing, so it returns Mono.
- findActive may match multiple records, so it returns Flux.
- deactivate needs the updated row count, so it returns Mono<Long>.
- existsByEmail needs a boolean.
- countActive needs a quantity.
- deleteByIdAndCount needs the deleted row count.

Imports for template queries:

~~~java
import org.springframework.data.relational.core.query.Criteria;
import org.springframework.data.relational.core.query.Query;
import org.springframework.data.relational.core.query.Update;
~~~

Across different Spring Data versions, verify the exact API signatures in your project's release. The principles for choosing the entity type and result type remain the same.

## 12. Transactions and Results Across Multiple Operations

A business workflow may combine multiple operations with different result types:

~~~java
@Transactional
public Mono<Order> createOrder(CreateOrderRequest request) {
    Order order = new Order(null, request.customerId(), "NEW");

    return orderRepository.save(order)
            .flatMap(saved ->
                    orderLineRepository.saveAll(
                            toOrderLines(saved.id(), request.lines())
                    ).thenReturn(saved)
            );
}
~~~

- The first call returns `Mono<Order>`, holding the new order's ID.
- The second call returns `Flux<OrderLine>`, emitting the saved order lines.
- `thenReturn(saved)` discards the OrderLine emissions and re-emits the saved Order once the publisher completes.

If all steps must be atomic, a reactive transaction must enclose the entire pipeline. Never call `subscribe()` inside a transactional method, as doing so creates an independent subscription that may run outside the transaction context.

If you only need to know that all operations finished, `then()` converts the final result to `Mono<Void>`. If you need to return the Order, use `thenReturn(saved)`. Operator choice dictates what data survives downstream.

## 13. Common Pitfalls When Selecting Tables and Result Types

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Query targets the wrong table | Entity mapping or @Table does not match schema | Check target class and mapping metadata |
| Repository returns entity while SQL needs a DTO | Using entity type for a different read model | Use projections or DatabaseClient mapping |
| Mono reports multiple results | Query condition is not unique | Use Flux or enforce a unique constraint; if taking the first, add ORDER BY |
| Flux emits rows in unexpected order | Missing ORDER BY | Add ordering to the query |
| Update/delete gives no indication whether rows were affected | API returns Mono<Void> or result count was discarded | Use template or rowsUpdated to capture the count |
| Generated ID missing at caller | Reading the input object instead of the returned entity | Use the entity emitted by save/insert |
| Dynamic table query fails or is unsafe | Trying to bind table name or concatenating raw input | Use fixed entity types or an identifier allowlist |
| Only receiving count when post-DML data is needed | Choosing rowsUpdated when generated/returned row is needed | Use RETURNING or an entity-returning API if supported |
| Counting data by loading the entire list | Choosing Flux<Entity> for a count need | Use a count query returning Mono<Long> |
| Delete completes and caller assumes the record definitely existed | Using Mono<Void> and ignoring row counts | Choose idempotent semantics or check row counts |

## 14. Practical Selection Guidelines

You can follow this sequence for each operation:

1. Identify which entity or table the data belongs to.
2. If using repository/template mapping, determine the target entity class and verify `@Table`.
3. If querying across multiple tables or needing a custom projection, specify tables via SQL in DatabaseClient.
4. Determine the expected business row cardinality: zero or one, or many rows.
5. Choose `Mono<T>` or `Flux<T>` for entities/DTOs.
6. Choose `Mono<Long>` for counts or affected row counts.
7. Choose `Mono<Boolean>` for existence questions.
8. Choose `Mono<Void>` only when the caller needs no result data.
9. If database-generated values are needed, return the entity or row emitted by the database.
10. Validate zero-row, multi-row, ordering, constraint, and transaction behavior against the business contract.

A handy rule of thumb is: **the entity type or SQL determines the source data; the publisher type determines the shape of the result the caller receives.** Do not infer the target table from the return type, and do not load a full entity when only a number or flag is needed.

## 15. Conclusion

In Spring Data R2DBC, the target table is typically determined from entity mapping via `@Table` and the entity class of a repository or `R2dbcEntityTemplate`. With `DatabaseClient`, the table is specified directly in SQL. Queries joining multiple tables or returning DTOs can use DatabaseClient to control both data sources and output shapes.

Result types should reflect cardinality and the information business logic needs: `Mono<T>` for at most one value, `Flux<T>` for multiple values, `Mono<Long>` for counts or affected rows, `Mono<Boolean>` for existence, and `Mono<Void>` when only a completion signal is required. Inserts should normally return the entity so callers receive IDs or versions; updates/deletes should preserve counts when callers need to verify how many rows changed.

Choosing the right table and result type makes code intent explicit, avoids unnecessary data loading, handles empty results cleanly, and makes reactive pipelines easy to compose.
