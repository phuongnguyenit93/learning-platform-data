# Creating Queries with DatabaseClient.sql

Spring Data R2DBC provides the repository abstraction for common CRUD operations. When you need to write explicit SQL, complex joins, custom projections, database-specific queries, or have exact control over the statement, the application can use Spring Framework's **DatabaseClient**.

DatabaseClient provides a fluent API to construct SQL statements, bind values, execute statements, and map results into Java objects. The API returns a Mono or Flux, so it can compose directly with reactive services and controllers. The key part is maintaining a clean boundary between the SQL template and input data: bind values using parameters, while dynamic identifiers or fragments must be controlled via an allowlist.

## 1. When to Use DatabaseClient?

DatabaseClient sits at a lower data-access layer than repositories. It is appropriate when:

- You need to write custom SQL that derived queries cannot express clearly.
- You need to join multiple tables and map to DTOs/read models.
- You need to use CTEs, window functions, JSON operators, or database-specific features.
- You need control over column projections and aliases.
- You need to run UPDATE/DELETE statements and receive the number of affected rows.
- You need to integrate manual SQL with Spring-managed reactive transactions.

Repositories remain a good choice for standard CRUD and query methods. R2dbcEntityTemplate is useful when working with entities and query criteria. DatabaseClient fits when the SQL statement itself is central to the operation.

| API | Abstraction Level | Best Suited For |
|---|---|---|
| ReactiveCrudRepository | High | Entity-based CRUD and query methods |
| R2dbcEntityTemplate | Medium | Entity operations, Criteria, mapping |
| DatabaseClient | Lower | Explicit SQL, joins, projections, and database-specific queries |
| R2DBC SPI Connection/Statement | Lowest | Direct connection/statement control when higher-level APIs fall short |

DatabaseClient still uses the R2DBC SPI underneath. It does not make SQL portable across all databases; handwritten SQL must still adhere to the dialect of the connected server.

## 2. Creating DatabaseClient from ConnectionFactory

DatabaseClient needs a ConnectionFactory to open connections to the database. In a Spring Boot application with the R2DBC starter and a default ConnectionFactory, auto-configuration usually provides a DatabaseClient ready to inject. Exact behavior depends on the Boot version and the application's bean configuration.

If configuring it manually, you can declare a bean:

~~~java
import io.r2dbc.spi.ConnectionFactory;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.r2dbc.core.DatabaseClient;

@Configuration
class DatabaseClientConfiguration {

    @Bean
    DatabaseClient databaseClient(ConnectionFactory connectionFactory) {
        return DatabaseClient.create(connectionFactory);
    }
}
~~~

A service injects DatabaseClient:

~~~java
@Service
public class CustomerQueryService {

    private final DatabaseClient databaseClient;

    public CustomerQueryService(DatabaseClient databaseClient) {
        this.databaseClient = databaseClient;
    }
}
~~~

DatabaseClient is designed to be shared as a bean. Do not create a new ConnectionFactory or DatabaseClient per request. Connection lifecycle is managed by the client, ConnectionFactory, and Spring's transaction infrastructure.

### 2.1. When There Are Multiple ConnectionFactories

If the application connects to multiple databases, create one DatabaseClient per ConnectionFactory and name the beans clearly:

~~~java
@Configuration
class MultiDatabaseClientConfiguration {

    @Bean("ordersDatabaseClient")
    DatabaseClient ordersDatabaseClient(
            @Qualifier("ordersConnectionFactory")
            ConnectionFactory connectionFactory) {
        return DatabaseClient.create(connectionFactory);
    }

    @Bean("billingDatabaseClient")
    DatabaseClient billingDatabaseClient(
            @Qualifier("billingConnectionFactory")
            ConnectionFactory connectionFactory) {
        return DatabaseClient.create(connectionFactory);
    }
}
~~~

Services must inject the right client:

~~~java
public BillingQueryService(
        @Qualifier("billingDatabaseClient")
        DatabaseClient databaseClient) {
    this.databaseClient = databaseClient;
}
~~~

DatabaseClient is bound to the ConnectionFactory passed at creation time. An Orders client will not automatically run queries against Billing just because the SQL mentions another schema or database name.

## 3. Fluent API Structure

A DatabaseClient query typically follows these steps:

1. Call sql(...) with a SQL template.
2. Bind parameters using bind(...) or bindNull(...).
3. Choose how to map rows if needed.
4. Choose how to retrieve results: one(), first(), all(), or rowsUpdated().
5. Compose the publisher into a reactive chain.

General pattern:

~~~java
databaseClient.sql("""
        SELECT id, email
        FROM customer
        WHERE id = :id
        """)
    .bind("id", customerId)
    .map((row, metadata) -> /* convert Row to object */)
    .one();
~~~

The methods form a pipeline. Publishers are usually lazy; the SQL statement is executed when a subscriber consumes the result. Therefore, merely creating the publisher does not mean the query has run.

Do not call subscribe() inside a service to launch an independent branch on its own. Return the Mono/Flux to the caller or chain publishers using flatMap, map, then, and appropriate operators.

## 4. Named Parameters and Value Binding

DatabaseClient supports named parameters in SQL templates. Write markers as :parameterName and pass the name without the colon to bind.

Example:

~~~java
public Mono<Customer> findByEmail(String email) {
    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE email = :email
            """)
        .bind("email", email)
        .map((row, metadata) -> new Customer(
            row.get("id", Long.class),
            row.get("email", String.class),
            row.get("display_name", String.class)
        ))
        .one();
}
~~~

In this example:

- :email is a named marker in SQL.
- bind("email", email) supplies the value for the marker.
- DatabaseClient translates the named parameter to the bind marker required by the dialect/driver.
- .one() returns Mono<Customer> because the operation expects at most one row.

Parameter names must match exactly. If the SQL has :customerId but the code binds "id", the statement will be missing a binding.

### 4.1. Do Not Concatenate Input Values into SQL

Do not do the following:

~~~java
String sql = "SELECT id, email FROM customer WHERE email = '"
    + email
    + "'";
~~~

If email contains special SQL characters, the structure of the statement can be altered. Use bind parameters:

~~~java
databaseClient.sql("""
        SELECT id, email
        FROM customer
        WHERE email = :email
        """)
    .bind("email", email)
    .fetch()
    .all();
~~~

The database receives email as a data value. Parameter binding is the primary defense for value input and helps the driver pass the proper data type.

### 4.2. Parameters Only Replace Values

Bind parameters cannot be used to replace:

- Table or schema names.
- Column names or aliases.
- ASC/DESC.
- Operators or keywords.
- Arbitrary WHERE, JOIN, or ORDER BY clauses.

For example, ORDER BY :sortColumn does not pick a column by the submitted name. The database treats sortColumn as a value expression.

If dynamic sorting is needed, map the selection from the request to a fixed set of application-controlled identifiers, and only then append the valid fragment into SQL. Filter values must still be bound separately.

## 5. Binding Null with bindNull

Do not pass null into bind(...). R2DBC needs to know the Java type of SQL NULL so the driver can determine the parameter type.

Example:

~~~java
public Mono<Integer> updateNickname(Long id, String nickname) {
    var spec = databaseClient.sql("""
            UPDATE customer
            SET nickname = :nickname
            WHERE id = :id
            """)
        .bind("id", id);

    if (nickname == null) {
        spec = spec.bindNull("nickname", String.class);
    } else {
        spec = spec.bind("nickname", nickname);
    }

    return spec.fetch().rowsUpdated();
}
~~~

bindNull("nickname", String.class) represents a SQL NULL with type String/VARCHAR matching the nickname column. Choose the Java type according to the column type and driver mapping.

Distinguish three cases:

- Parameter has a value: use bind.
- Parameter needs SQL NULL: use bindNull with a Java type.
- SQL does not contain that parameter: do not bind it.

Failing to bind a parameter declared in SQL usually leads to an execution error. Omitting a parameter does not mean passing SQL NULL.

### 5.1. NULL in WHERE Conditions

SQL uses three-valued logic. The expression nickname = NULL does not evaluate to TRUE for rows where nickname is NULL. If you need to find null values, use IS NULL:

~~~sql
SELECT id, email
FROM customer
WHERE nickname IS NULL
~~~

If an API has optional filters, build the corresponding predicate branches. Do not bind a null parameter expecting an equality comparison to match null rows.

## 6. Index-Based Binding and Native Markers

DatabaseClient supports named parameters to reduce coupling to driver-native markers. If you use the R2DBC SPI directly via Connection.createStatement(...), you must write driver-specific markers and bind by index.

PostgreSQL native example:

~~~java
Statement statement = connection.createStatement("""
    SELECT id, email
    FROM customer
    WHERE email = $1
    """);

statement.bind(0, email);
~~~

In PostgreSQL, the first marker appears as $1, but the R2DBC SPI API uses a zero-based index, so you call bind(0, ...).

Do not confuse the two mechanisms:

| Execution Approach | Marker in SQL | Binding Method |
|---|---|---|
| Spring DatabaseClient named parameter | :email | bind("email", value) |
| R2DBC SPI native PostgreSQL | $1 | bind(0, value) |
| R2DBC SPI driver with other positional markers | Driver-specific | Index matching marker order |

When moving SQL from DatabaseClient to a raw Statement, adjust the markers and bindings for the driver. Do not copy a named-parameter SQL template directly into a native Statement.

## 7. Choosing one(), first(), all(), and rowsUpdated()

DatabaseClient provides several ways to consume results. Choose based on cardinality and the operation's semantics.

| Method | Return Type | Meaning |
|---|---|---|
| one() | Mono<T> | At most one row; errors if multiple rows exist |
| first() | Mono<T> | Takes the first row if present |
| all() | Flux<T> | Emits all rows |
| rowsUpdated() | Mono<Integer> | Number of rows affected by update/delete/insert depending on driver |

### 7.1. Using one() for a Single Result

Example lookup by primary key:

~~~java
public Mono<Customer> findById(Long id) {
    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE id = :id
            """)
        .bind("id", id)
        .map(customerMapper)
        .one();
}
~~~

one() fits when the condition guarantees at most one row. If the SQL accidentally returns multiple rows, it signals an error rather than silently discarding the remaining rows.

If the result can contain multiple rows, use all() or apply explicit limits/ordering before using first().

### 7.2. Using first() When Only the First Row Is Needed

Example fetching the latest record:

~~~java
public Mono<Order> findLatestOrder(Long customerId) {
    return databaseClient.sql("""
            SELECT id, customer_id, created_at, total
            FROM purchase_order
            WHERE customer_id = :customerId
            ORDER BY created_at DESC, id DESC
            """)
        .bind("customerId", customerId)
        .map(orderMapper)
        .first();
}
~~~

ORDER BY must define a clear order. Without sorting, the "first row" has no deterministic meaning across executions.

When possible, add a SQL limit according to database syntax so the server only needs to return the required data.

### 7.3. Using all() for Lists

~~~java
public Flux<Customer> findActiveCustomers() {
    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE active = :active
            ORDER BY id
            """)
        .bind("active", true)
        .map(customerMapper)
        .all();
}
~~~

all() returns Flux<Customer>. The Flux is empty when there are no rows and emits an error if the query fails.

Do not call collectList() on an entire large table just to turn a Flux into a Mono<List<T>>. For large lists, use pagination or batch processing.

### 7.4. Using rowsUpdated() for Write Operations

~~~java
public Mono<Integer> renameCustomer(Long id, String displayName) {
    return databaseClient.sql("""
            UPDATE customer
            SET display_name = :displayName
            WHERE id = :id
            """)
        .bind("displayName", displayName)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
~~~

rowsUpdated() returns the number of affected rows as reported by the driver. A value of 0 may mean the ID does not exist or the condition did not match; the service needs to decide whether to translate that into a not-found error.

Do not assume rowsUpdated() always represents the number of rows whose values changed. Some databases/drivers report matched rows, changed rows, or different semantics. Verify behavior for your driver and database.

## 8. Mapping a Row to a Java Object

DatabaseClient provides Row and RowMetadata when using a map callback. The application converts the columns into the appropriate DTO/entity.

Record example:

~~~java
public record Customer(
    Long id,
    String email,
    String displayName
) {}
~~~

Mapper:

~~~java
private Customer mapCustomer(Row row, RowMetadata metadata) {
    return new Customer(
        row.get("id", Long.class),
        row.get("email", String.class),
        row.get("display_name", String.class)
    );
}
~~~

Usage in a query:

~~~java
return databaseClient.sql("""
        SELECT id, email, display_name
        FROM customer
        WHERE id = :id
        """)
    .bind("id", id)
    .map(this::mapCustomer)
    .one();
~~~

Row.get(column, type) requires a column/alias name and a Java type compatible with the driver. For nullable columns, the result can be null; the DTO must allow null or the application must convert it to an appropriate representation.

### 8.1. Column Aliases in JOINs

When joining multiple tables that share column names such as id, name, or created_at, always use explicit aliases:

~~~sql
SELECT
    c.id AS customer_id,
    c.email AS customer_email,
    o.id AS order_id,
    o.created_at AS order_created_at
FROM customer c
JOIN purchase_order o
  ON o.customer_id = c.id
WHERE c.id = :customerId
~~~

The mapper reads by alias:

~~~java
.map((row, metadata) -> new CustomerOrderView(
    row.get("customer_id", Long.class),
    row.get("customer_email", String.class),
    row.get("order_id", Long.class),
    row.get("order_created_at", LocalDateTime.class)
))
~~~

Aliases prevent column mix-ups and reduce reliance on how the driver handles duplicate labels.

### 8.2. Using RowMetadata When Metadata Inspection Is Needed

RowMetadata can provide information about the columns in the result. This is useful when handling dynamic projections or inspecting metadata.

Normally, DTO mapping should use known alias names. Avoid building an overly dynamic mapper if the query has a stable projection.

Do not retain Row or RowMetadata for use after the callback completes. Extract the needed data into objects immediately inside the mapper.

### 8.3. Data Types and Conversion

Do not assume every database returns the same Java type for the same SQL type. UUID, JSON, array, numeric, timestamp, enum, and proprietary types can differ by driver.

If converters or codecs are needed, configure them per driver and test against a real database. Do not force every value to String to avoid conversion errors, as that can lose type semantics or precision.

## 9. List Queries and Pagination

DatabaseClient returns a Flux when using all(). For list endpoints, data should be bounded directly in SQL.

PostgreSQL/MySQL example:

~~~java
public Flux<Customer> findPage(int limit, int offset) {
    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            ORDER BY id
            LIMIT :limit OFFSET :offset
            """)
        .bind("limit", limit)
        .bind("offset", offset)
        .map(customerMapper)
        .all();
}
~~~

LIMIT/OFFSET syntax is not portable across all databases. SQL Server typically uses OFFSET/FETCH with ORDER BY. Use the dialect of your target server.

Validate limit and offset before binding:

- limit must be greater than 0.
- Cap the maximum limit to avoid returning too many rows.
- offset must be non-negative and within business limits.
- ORDER BY must be deterministic, typically adding the primary key as a tie-breaker.

### 9.1. Keyset Pagination

For large tables, deep offsets can force the database to skip many rows. Keyset pagination uses the last value of the previous page:

~~~sql
SELECT id, email, display_name
FROM customer
WHERE id > :lastSeenId
ORDER BY id
LIMIT :limit
~~~

This approach works well when ordering is based on an ascending key with an appropriate index. If sorting by multiple columns, the cursor must contain all sort values and corresponding comparison conditions.

## 10. Queries with Multiple Optional Conditions

Some search endpoints allow filtering by multiple fields. You can construct SQL from fixed predicates while keeping value parameters separate.

Illustrative example with optional filter names:

~~~java
public Flux<Customer> search(String email, Boolean active) {
    StringBuilder sql = new StringBuilder("""
        SELECT id, email, display_name
        FROM customer
        WHERE 1 = 1
        """);

    var bindings = new LinkedHashMap<String, Object>();

    if (email != null) {
        sql.append(" AND email = :email");
        bindings.put("email", email);
    }

    if (active != null) {
        sql.append(" AND active = :active");
        bindings.put("active", active);
    }

    sql.append(" ORDER BY id");

    var spec = databaseClient.sql(sql.toString());

    for (var entry : bindings.entrySet()) {
        spec = spec.bind(entry.getKey(), entry.getValue());
    }

    return spec.map(customerMapper).all();
}
~~~

The parts appended to SQL here are fixed fragments authored by the application. Email and active are bound separately. If a filter can carry SQL NULL, use bindNull with the proper type rather than skipping the parameter or calling bind with null.

### 10.1. Dynamic Sorting Must Use an Allowlist

Do not use:

~~~sql
ORDER BY :sortColumn
~~~

Instead, map the client's choice to a fixed identifier:

~~~java
String orderBy = switch (sortField) {
    case "email" -> "email";
    case "createdAt" -> "created_at";
    case "displayName" -> "display_name";
    default -> throw new IllegalArgumentException(
        "Unsupported sort field"
    );
};
~~~

Then interpolate orderBy from the allowlist into SQL. Direction must also be validated and converted to one of the two literals ASC or DESC. Never concatenate client-supplied strings directly.

Bind parameters cannot replace table names, column names, schemas, operators, or keywords. Identifier quoting is no substitute for allowlist validation either.

## 11. Binding a Collection in an IN Clause

DatabaseClient supports named parameter expansion for collections in supported cases, commonly used with IN:

~~~java
public Flux<Customer> findByIds(Collection<Long> ids) {
    if (ids.isEmpty()) {
        return Flux.empty();
    }

    return databaseClient.sql("""
            SELECT id, email, display_name
            FROM customer
            WHERE id IN (:ids)
            """)
        .bind("ids", ids)
        .map(customerMapper)
        .all();
}
~~~

Spring can expand a collection into multiple markers. However, verify the API/version and driver in use; collection expansion differs from binding a native SQL array.

### 11.1. Handling Empty Collections

Do not let a query produce IN () if the expansion mechanism does not support empty lists. Handle it before creating the query and decide the semantics:

- Empty list means no results: return Flux.empty().
- Empty list means no filter applied: omit the IN predicate.
- Empty list is invalid input: return a validation error.

Do not pick semantics implicitly, as that could cause an endpoint to return all data when the caller expects no results.

### 11.2. Limiting the Number of Elements

Overly large collections can produce statements with thousands of markers, increasing parse cost or exceeding driver/database limits. Cap the size, split into batches, or use an array/table parameter mechanism supported by the database.

## 12. Inserts and Generated Values

DatabaseClient can run INSERT and map the result returned by the database. How generated IDs are retrieved depends on the database and driver.

PostgreSQL example using RETURNING:

~~~java
public Mono<Long> insertCustomer(String email, String displayName) {
    return databaseClient.sql("""
            INSERT INTO customer (email, display_name)
            VALUES (:email, :displayName)
            RETURNING id
            """)
        .bind("email", email)
        .bind("displayName", displayName)
        .map((row, metadata) -> row.get("id", Long.class))
        .one();
}
~~~

RETURNING is database-specific syntax; PostgreSQL supports it, but do not assume all databases share the same syntax. For other databases/drivers, check the appropriate generated-values API or use R2dbcEntityTemplate/repositories if that abstraction fits your needs.

For nullable columns, use bindNull with the Java type instead of binding a null value.

## 13. Updates and Deletes

Update:

~~~java
public Mono<Integer> updateEmail(Long id, String email) {
    return databaseClient.sql("""
            UPDATE customer
            SET email = :email
            WHERE id = :id
            """)
        .bind("email", email)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
~~~

Delete:

~~~java
public Mono<Integer> deleteById(Long id) {
    return databaseClient.sql("""
            DELETE FROM customer
            WHERE id = :id
            """)
        .bind("id", id)
        .fetch()
        .rowsUpdated();
}
~~~

rowsUpdated() returns Mono<Integer>. The service can inspect the count:

~~~java
return deleteById(id)
    .flatMap(count -> {
        if (count == 0) {
            return Mono.error(new CustomerNotFoundException(id));
        }
        return Mono.empty();
    });
~~~

This is a business decision. Some endpoints treat deleting a non-existent record as an idempotent success; in that case, a count of 0 is not necessarily an error.

## 14. Using DatabaseClient in a Reactive Transaction

DatabaseClient integrates with Spring's transaction infrastructure. When a reactive transaction is bound to the same ConnectionFactory, DatabaseClient operations within that reactive context can participate in the transaction.

Example:

~~~java
@Transactional
public Mono<Customer> createCustomer(
        String email,
        String displayName) {

    return databaseClient.sql("""
            INSERT INTO customer (email, display_name)
            VALUES (:email, :displayName)
            RETURNING id, email, display_name
            """)
        .bind("email", email)
        .bind("displayName", displayName)
        .map(customerMapper)
        .one()
        .flatMap(customer ->
            databaseClient.sql("""
                    INSERT INTO audit_log (entity_type, entity_id, action)
                    VALUES (:type, :id, :action)
                    """)
                .bind("type", "CUSTOMER")
                .bind("id", customer.id())
                .bind("action", "CREATED")
                .fetch()
                .rowsUpdated()
                .thenReturn(customer)
        );
}
~~~

The RETURNING example is for PostgreSQL. If both statements use a DatabaseClient bound to the same ConnectionFactory and share the same reactive transaction context, they can commit or roll back together.

### 14.1. Keeping All Operations in One Publisher Chain

Reactive transactions use Reactor Context to propagate transaction resources. Therefore:

- Return Mono/Flux from the transactional method.
- Chain operations using flatMap, then, zip, or appropriate operators.
- Do not call subscribe() inside the method.
- Do not call block() to obtain intermediate results.
- Do not launch fire-and-forget tasks expecting them to join the transaction.

When using multiple ConnectionFactories, a transaction manager for one source does not automatically manage a client for another source.

### 14.2. Selecting the Transaction Manager with Multiple Data Sources

If multiple ReactiveTransactionManagers exist, specify the right manager:

~~~java
@Transactional(transactionManager = "ordersTransactionManager")
public Mono<Order> createOrder(...) {
    // Query via ordersDatabaseClient.
}
~~~

Ensure the client and transaction manager point to the corresponding ConnectionFactory. A single annotation does not create a distributed transaction across multiple databases.

### 14.3. TransactionalOperator

You can use TransactionalOperator to wrap a publisher:

~~~java
return transactionalOperator.transactional(
    databaseClient.sql("""
            UPDATE account
            SET status = :status
            WHERE id = :id
            """)
        .bind("status", "ACTIVE")
        .bind("id", accountId)
        .fetch()
        .rowsUpdated()
);
~~~

TransactionalOperator is useful when transaction boundaries need to be expressed directly inside a reactive chain or selected dynamically along an execution path.

## 15. Error Handling and Exception Translation

DatabaseClient translates many R2DBC errors into Spring's DataAccessException hierarchy. This allows services to handle errors via Spring's abstraction instead of depending entirely on driver-specific exception classes.

Common error categories:

- Bad SQL grammar: invalid SQL syntax or object names.
- Data integrity violation: unique, foreign key, not-null, or constraint violations.
- Type mismatch: incompatible binding or conversion.
- Transient resource failure: network or database temporarily unavailable.
- Connection/acquire timeout: pool could not provide a connection.
- Permission/authentication failure: insufficient user privileges or invalid credentials.

Do not convert every DataAccessException into "not found." Map errors strictly according to known semantics. Syntax or authentication errors are not empty results.

### 15.1. Preserving the Cause Chain

When wrapping errors into domain exceptions, keep the cause:

~~~java
.onErrorMap(
    DataAccessException.class,
    error -> new CustomerPersistenceException(
        "Could not load customer",
        error
    )
)
~~~

Do not strip SQLState or vendor codes if they are needed for diagnostics.

### 15.2. Do Not Log Sensitive Bind Data

Log sanitized query name, datasource alias, duration, row count, and error code. Avoid logging passwords, tokens, personal emails, payment details, or full parameter values.

## 16. Query Optimization and Resource Limits

DatabaseClient lets you write explicit SQL, but it does not guarantee efficient queries on its own.

Pay attention to:

- Select only the needed columns rather than SELECT *.
- Have appropriate indexes for predicates and join keys.
- Use a deterministic ORDER BY for pagination.
- Bound the number of returned rows.
- Avoid N+1 queries when mapping relationships.
- Do not call collectList() on an unbounded dataset.
- Configure timeouts at the appropriate layers.
- Check query plans on a real database.
- Monitor pool acquire latency and query duration.

### 16.1. Do Not Hold Connections Too Long

A slowly consumed Flux can hold database resources longer than expected, depending on the driver and fetch behavior. For large exports, consider batch/keyset pagination or a background job generating a file rather than keeping a query open while a client downloads data.

### 16.2. Avoiding N+1 Queries During Mapping

Do not execute database queries inside the synchronous per-row mapper. The mapper should convert a Row into an object. If you need to load relationships, structure a reactive pipeline with bounded concurrency or write an appropriate JOIN/projection.

For example, do not call a blocking repository inside the map callback. If one query per customer is needed, use flatMap/concatMap with bounded concurrency; even better, consider a single join or batch query.

## 17. Testing DatabaseClient

Unit tests can mock DatabaseClient to verify service coordination, but mocks do not test the SQL parser, driver markers, type mappings, or real transactions.

You should have integration tests against the target database/driver, typically via Testcontainers.

Cases worth testing:

- Named parameters are bound correctly.
- Missing parameters produce diagnostic errors.
- SQL NULL uses bindNull with the proper type.
- one() behavior with 0, 1, and multiple rows.
- first() with a deterministic ORDER BY.
- all() emits all rows and completes.
- rowsUpdated() returns the count according to the driver.
- UUID, JSON, decimal, and temporal mappings.
- Collection expansion and empty collections.
- Identifier quoting and schema qualification.
- Transaction commit/rollback across multiple queries chained together.
- Cancellation and timeout releasing connections.
- Native SQL matching the dialect.
- SQL injection inputs bound strictly as values.

### 17.1. StepVerifier for Single-Result Queries

~~~java
StepVerifier.create(queryService.findByEmail("test@example.com"))
    .expectNextMatches(customer ->
        customer.email().equals("test@example.com")
    )
    .verifyComplete();
~~~

### 17.2. StepVerifier for Lists

~~~java
StepVerifier.create(queryService.findActiveCustomers())
    .expectNextCount(2)
    .verifyComplete();
~~~

Fixture data must be deterministic so tests do not rely on default database ordering. When using all(), include ORDER BY in SQL whenever order is part of the contract.

### 17.3. Testing Transaction Rollback

Write an integration test that succeeds on the first operation and intentionally fails on the second operation within the same reactive transaction. After the publisher terminates with an error, query the database again to verify the first operation was rolled back.

Do not use mocks to conclude that transactions roll back; a real database and transaction manager are required.

## 18. Common Mistakes

**Using DatabaseClient but forgetting to bind a parameter.** SQL has a marker, but execution lacks the matching value. Cross-check every marker with a bind call.

**Passing a colon in the bind name.** SQL uses :email, while bind expects "email", not ":email".

**Using the wrong driver's native marker.** DatabaseClient named markers and raw Statement native markers are two separate mechanisms.

**Binding null with bind.** Use bindNull with the appropriate Java type.

**Using one() for multi-row queries.** one() represents at most one row and errors on multiple rows. Use all() or apply proper limits/ordering.

**Using first() without ORDER BY.** The first result is non-deterministic. Specify explicit ordering.

**Treating rowsUpdated() as a boolean.** Counts can be 0 or greater than 1. Define the operation's semantics.

**Concatenating value inputs into SQL.** Prone to SQL injection. Use bind.

**Binding column names or sort directions.** Value parameters cannot replace identifiers or keywords. Use an allowlist.

**Forgetting to handle empty collections in IN.** Handle empty-list semantics before constructing the query.

**Mapping duplicate column names in JOINs.** Use unique aliases and map by alias.

**Retaining Row after the mapper callback.** Extract data into DTOs immediately inside the callback.

**Using DatabaseClient for the wrong datasource.** Qualify clients and transaction managers to match the intended ConnectionFactory.

**Calling subscribe() or block() in services.** This can detach operations from the reactive chain and transaction context. Return publishers to the caller.

**Testing only with H2 or mocks.** Syntax, type mapping, and driver behavior can differ from production. Test against the target database.

## 19. Design Principles

- Use repositories for simple CRUD/queries and DatabaseClient for custom SQL needing explicit control.
- Inject a shared DatabaseClient bound to the appropriate ConnectionFactory.
- Use named parameters and bind values; never concatenate input data into SQL.
- Use bindNull with an explicit Java type.
- Choose one(), first(), or all() according to cardinality and ordering.
- Use rowsUpdated() for write operations and interpret counts per driver semantics.
- Alias columns clearly in JOINs and projections.
- Use Java types matching SQL types and verify driver conversions.
- Handle empty collections and bound the size of IN lists.
- Allowlist dynamic identifiers and sort directions; bind value filters separately.
- Keep queries aligned with the real database dialect.
- Combine DatabaseClient with reactive transactions in the same publisher chain.
- Select the transaction manager matching the ConnectionFactory.
- Never call subscribe/block inside services.
- Bound results, concurrency, and connection hold times.
- Test SQL, mappings, transactions, and driver behavior via integration tests on the target database.
- Do not log parameter values or sensitive data.

## 20. Key Takeaways

DatabaseClient.sql is the starting point for building an explicit R2DBC query. From a SQL template, the application binds values, maps Rows into DTOs/entities, and selects one(), first(), all(), or rowsUpdated() based on the expected result. Named parameters separate data from SQL, and DatabaseClient translates markers to match the driver.

Use bindNull for SQL NULL, clear aliases when joining, explicit handling for empty collections, and bounded pagination. Dynamic identifiers cannot be bound as values, so they must come from an allowlist and follow the dialect. DatabaseClient can participate in reactive transactions when sharing the same ConnectionFactory and transaction context; keep operations within a single publisher chain and verify with a real database and driver to ensure SQL, mappings, and transactions behave as expected.
