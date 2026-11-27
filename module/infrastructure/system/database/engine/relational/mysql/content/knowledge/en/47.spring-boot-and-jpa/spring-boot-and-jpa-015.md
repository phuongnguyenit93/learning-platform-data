# Spring Boot and JPA

## Stored Procedures, Multiple Result Sets, and OUT Parameters

MySQL stored procedures can return multiple result sets, affected row counts, and OUT/INOUT parameters within a single invocation. A reporting procedure might return an order list in its first result set, status aggregates in its second result set, and total order count plus total revenue via OUT parameters. A Spring Boot application must consume the entire sequence of results in the exact order before reading output parameters and returning the connection to the pool.

In the **DATABASE_MYSQL** module, you learn to master MySQL from table design, data types, keys, and SQL queries through indexes, transactions, and concurrency control. You also practice reading execution plans, query tuning, access control, backups, and relational database operations. This lesson bridges stored procedures with the Java tier: declaring procedures, choosing among Spring Data JPA `@Procedure`, `StoredProcedureQuery`, or JDBC via `JdbcTemplate`, mapping multiple result sets, reading OUT parameters, and keeping transactions and the persistence context consistent.

Examples use MySQL 8.x, Spring Boot 3.x, Jakarta Persistence, and MySQL Connector/J. In Spring Boot 2.x, JPA packages use `javax.persistence` instead of `jakarta.persistence`; verify your dependency versions before copying imports.

### 1. Understanding the Stored Procedure Contract

A single procedure call can emit several result types:

- **Result set:** rows/columns returned by a `SELECT` inside the procedure.
- **Update count:** row count affected by a DML statement.
- **OUT parameter:** a value assigned by the procedure to return to the caller.
- **INOUT parameter:** an input value read and potentially modified by the procedure.
- **Return status:** MySQL procedures have no scalar `RETURN` value like stored functions; use OUT parameters or result sets when summary values are needed.

For instance, a customer report procedure might have the contract:

1. `IN p_customer_id`: identifies the customer to report on.
2. First result set: list of orders.
3. Second result set: order summary by status.
4. `OUT p_order_count`: total order count.
5. `OUT p_total_amount`: total monetary amount.

The contract must specify result set order, column names/casing, data types, nullability, and OUT parameter semantics. Reordering a `SELECT` inside the procedure can break application mappers even if the procedure signature stays unchanged.

### 2. Creating a MySQL Procedure with Multiple Result Sets and OUT Parameters

The example below assumes an `orders` table with columns `order_id`, `customer_id`, `created_at`, `status`, and `total_amount`:

~~~sql
DELIMITER //

CREATE PROCEDURE customer_order_report(
    IN p_customer_id BIGINT,
    OUT p_order_count INT,
    OUT p_total_amount DECIMAL(15, 2)
)
BEGIN
    -- Result set 1: order details.
    SELECT
        order_id,
        created_at,
        status,
        total_amount
    FROM orders
    WHERE customer_id = p_customer_id
    ORDER BY created_at DESC, order_id DESC;

    -- Result set 2: summary by status.
    SELECT
        status,
        COUNT(*) AS order_count,
        COALESCE(SUM(total_amount), 0) AS amount_by_status
    FROM orders
    WHERE customer_id = p_customer_id
    GROUP BY status
    ORDER BY status;

    -- OUT parameters: single summary values for the entire report.
    SELECT
        COUNT(*),
        COALESCE(SUM(total_amount), 0)
    INTO p_order_count, p_total_amount
    FROM orders
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
~~~

This procedure produces exactly two result sets. The final `SELECT ... INTO` assigns OUT parameters without emitting a third result set. If the customer has no orders, `COUNT(*)` yields 0 and `COALESCE(SUM(...), 0)` ensures total amount is 0 rather than NULL.

`DELIMITER` is a command-line client directive to change the statement terminator when entering a procedure body; it is not a SQL statement sent to MySQL Server. When deploying via JDBC, migration runners, or deployment tools, submit `CREATE PROCEDURE ... BEGIN ... END` using the syntax supported by that tool—never send `DELIMITER` lines as SQL statements.

Calling from a SQL client:

~~~sql
SET @order_count = NULL;
SET @total_amount = NULL;

CALL customer_order_report(42, @order_count, @total_amount);

SELECT
    @order_count AS order_count,
    @total_amount AS total_amount;
~~~

The SQL client displays both result sets from `CALL`, and then the separate `SELECT` reads the session variables. Over JDBC `CallableStatement`, the driver provides OUT parameters via `getInt()`/`getBigDecimal()` after the caller finishes processing the procedure's results.

### 3. Choosing the Right API in Spring

Not every procedure-calling API handles multiple result sets equally well:

| Invocation Approach | Best Fit | Caveats to Watch |
|---|---|---|
| Spring Data JPA `@Procedure` | Simple procedures returning a single OUT/scalar or a set of OUT parameters | Not convenient for iterating multiple result sets sequentially |
| JPA `StoredProcedureQuery` | Keeping calls inside `EntityManager`, using JPA mappings and JPA transaction management | Multiple result set handling varies by mapping/provider; test with your Hibernate version |
| Spring JDBC `JdbcTemplate` / `SimpleJdbcCall` | Procedures with multiple result sets, update counts, and OUT parameters needing explicit control | Mappings are explicit; operates at the JDBC layer outside entity lifecycle |
| Direct JDBC `CallableStatement` | Fine-grained protocol control and custom result loops | Must manage resources and transactions carefully; prefer via `JdbcTemplate` or Spring-managed connections |

Practical rule:

- Procedure returning a single OUT parameter: `@Procedure` is usually concise.
- Procedure returning multiple result sets to map sequentially: use `JdbcTemplate` with `CallableStatementCallback` for exact control.
- Procedure needing JPA result mappings: use `StoredProcedureQuery`, verified on your actual provider.

### 4. Calling a Simple Procedure with Spring Data JPA `@Procedure`

For a procedure returning one OUT parameter, declare a repository method:

~~~sql
DELIMITER //

CREATE PROCEDURE count_customer_orders(
    IN p_customer_id BIGINT,
    OUT p_order_count INT
)
BEGIN
    SELECT COUNT(*)
    INTO p_order_count
    FROM orders
    WHERE customer_id = p_customer_id;
END//

DELIMITER ;
~~~

~~~java
public interface OrderProcedureRepository
        extends Repository<Order, Long> {

    @Procedure(procedureName = "count_customer_orders")
    Integer countCustomerOrders(
            @Param("p_customer_id") Long customerId);
}
~~~

Calling from a service:

~~~java
@Service
public class OrderReportService {

    private final OrderProcedureRepository procedures;

    public OrderReportService(OrderProcedureRepository procedures) {
        this.procedures = procedures;
    }

    public int countOrders(long customerId) {
        Integer count = procedures.countCustomerOrders(customerId);
        return count == null ? 0 : count;
    }
}
~~~

The procedure name must match the database. Parameter names must match how Spring Data JPA/the provider binds parameters; if environments differ, inspect SQL logs and procedure metadata. Never concatenate procedure names or schema names from user input.

When a procedure has multiple OUT parameters, Spring Data JPA can return a `Map<String, Object>` given appropriate `@Procedure`/`@NamedStoredProcedureQuery` declarations. However, if the procedure also returns multiple result sets, use `StoredProcedureQuery` or JDBC to manage the result stream explicitly.

### 5. Calling Procedures with JPA `StoredProcedureQuery`

JPA provides `StoredProcedureQuery` through `EntityManager`. This API supports registering IN, OUT, and INOUT parameters, executing the procedure, and iterating subsequent results.

Example reading result sets as `Object[]` to stay independent of entity mappings:

In this example, `created_at` is assumed to be `DATETIME` and mapped to `LocalDateTime`. If the column is `TIMESTAMP`, use `Instant` or an explicit timezone convention; never convert implicitly to the JVM's local time.

~~~java
@Service
public class JpaOrderReportService {

    @PersistenceContext
    private EntityManager entityManager;

    @Transactional(readOnly = true)
    public OrderReport loadReport(long customerId) {
        StoredProcedureQuery query =
                entityManager.createStoredProcedureQuery(
                        "customer_order_report");

        query.registerStoredProcedureParameter(
                "p_customer_id", Long.class, ParameterMode.IN);
        query.registerStoredProcedureParameter(
                "p_order_count", Integer.class, ParameterMode.OUT);
        query.registerStoredProcedureParameter(
                "p_total_amount", BigDecimal.class, ParameterMode.OUT);

        query.setParameter("p_customer_id", customerId);

        List<OrderRow> orders = new ArrayList<>();
        List<StatusSummary> summaries = new ArrayList<>();
        int resultSetIndex = 0;
        boolean hasResultSet = query.execute();

        while (true) {
            if (hasResultSet) {
                List<?> rows = query.getResultList();

                if (resultSetIndex == 0) {
                    for (Object row : rows) {
                        Object[] columns = (Object[]) row;
                        orders.add(new OrderRow(
                                ((Number) columns[0]).longValue(),
                                toLocalDateTime(columns[1]),
                                (String) columns[2],
                                (BigDecimal) columns[3]));
                    }
                } else if (resultSetIndex == 1) {
                    for (Object row : rows) {
                        Object[] columns = (Object[]) row;
                        summaries.add(new StatusSummary(
                                (String) columns[0],
                                ((Number) columns[1]).longValue(),
                                (BigDecimal) columns[2]));
                    }
                } else {
                    throw new IllegalStateException(
                            "Unexpected result set index: " + resultSetIndex);
                }

                resultSetIndex++;
            } else if (query.getUpdateCount() == -1) {
                break;
            }

            hasResultSet = query.hasMoreResults();
        }

        if (resultSetIndex != 2) {
            throw new IllegalStateException(
                    "Expected 2 result sets but received " + resultSetIndex);
        }

        // Read OUT parameters after consuming all result sets and update counts.
        Integer orderCount = (Integer)
                query.getOutputParameterValue("p_order_count");
        BigDecimal totalAmount = (BigDecimal)
                query.getOutputParameterValue("p_total_amount");

        return new OrderReport(
                orders,
                summaries,
                orderCount == null ? 0 : orderCount,
                totalAmount == null ? BigDecimal.ZERO : totalAmount);
    }

    private LocalDateTime toLocalDateTime(Object value) {
        if (value instanceof LocalDateTime dateTime) {
            return dateTime;
        }
        throw new IllegalArgumentException(
                "Unexpected created_at type: " + value);
    }
}
~~~

This snippet illustrates JPA result iteration. Exact Java types for each column depend on the JDBC driver, dialect, and provider; verify returned types in integration tests. Notice `Number.longValue()` is used for integer columns to avoid assuming the provider always returns `Long`.

DTO records:

~~~java
public record OrderRow(
        long orderId,
        LocalDateTime createdAt,
        String status,
        BigDecimal totalAmount) {}

public record StatusSummary(
        String status,
        long orderCount,
        BigDecimal amountByStatus) {}

public record OrderReport(
        List<OrderRow> orders,
        List<StatusSummary> summaries,
        int orderCount,
        BigDecimal totalAmount) {}
~~~

`createStoredProcedureQuery("customer_order_report")` specifies no result mapping, so each row comes back as `Object[]`. To map into entities/DTOs via `@SqlResultSetMapping`, declare mappings matching the result set order and test against your deployed Hibernate version. JPA providers can vary in how they handle multi-result procedures; when strict protocol control is required, JDBC is usually easier to reason about.

### 6. Iterating Multiple Result Sets with JDBC via `JdbcTemplate`

For procedures returning multiple result sets and OUT parameters, `CallableStatement` provides a clean loop:

1. Call `execute()`.
2. If the current result is a `ResultSet`, read and close it.
3. Otherwise, inspect the update count.
4. Call `getMoreResults()` to advance to the next result.
5. Stop when there is no `ResultSet` and `getUpdateCount()` returns `-1`.
6. Read OUT parameters only after consuming all results.

Complete Spring JDBC pattern:

~~~java
@Service
public class JdbcOrderReportService {

    private final JdbcTemplate jdbcTemplate;

    public JdbcOrderReportService(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    @Transactional(readOnly = true)
    public OrderReport loadReport(long customerId) {
        return jdbcTemplate.execute(
                connection -> {
                    CallableStatement statement =
                            connection.prepareCall(
                                    "{call customer_order_report(?, ?, ?)}");
                    statement.setLong(1, customerId);
                    statement.registerOutParameter(2, Types.INTEGER);
                    statement.registerOutParameter(3, Types.DECIMAL);
                    return statement;
                },
                (CallableStatementCallback<OrderReport>) statement -> {
                    List<OrderRow> orders = new ArrayList<>();
                    List<StatusSummary> summaries = new ArrayList<>();
                    int resultSetIndex = 0;
                    boolean hasResultSet = statement.execute();

                    while (true) {
                        if (hasResultSet) {
                            try (ResultSet rs = statement.getResultSet()) {
                                if (resultSetIndex == 0) {
                                    while (rs.next()) {
                                        orders.add(new OrderRow(
                                                rs.getLong("order_id"),
                                                rs.getObject(
                                                        "created_at",
                                                        LocalDateTime.class),
                                                rs.getString("status"),
                                                rs.getBigDecimal("total_amount")));
                                    }
                                } else if (resultSetIndex == 1) {
                                    while (rs.next()) {
                                        summaries.add(new StatusSummary(
                                                rs.getString("status"),
                                                rs.getLong("order_count"),
                                                rs.getBigDecimal("amount_by_status")));
                                    }
                                } else {
                                    throw new SQLException(
                                            "Unexpected result set index: "
                                                    + resultSetIndex);
                                }
                            }
                            resultSetIndex++;
                        } else {
                            int updateCount = statement.getUpdateCount();
                            if (updateCount == -1) {
                                break;
                            }
                        }

                        hasResultSet = statement.getMoreResults(
                                Statement.CLOSE_CURRENT_RESULT);
                    }

                    if (resultSetIndex != 2) {
                        throw new SQLException(
                                "Expected 2 result sets but received "
                                        + resultSetIndex);
                    }

                    // Retrieve OUT values only after reading all CALL results.
                    int orderCount = statement.getInt(2);
                    if (statement.wasNull()) {
                        orderCount = 0;
                    }
                    BigDecimal totalAmount = statement.getBigDecimal(3);
                    if (totalAmount == null) {
                        totalAmount = BigDecimal.ZERO;
                    }

                    return new OrderReport(
                            orders, summaries, orderCount, totalAmount);
                });
    }
}
~~~

`JdbcTemplate.execute(CallableStatementCreator, CallableStatementCallback)` manages connection acquisition/release via Spring JDBC and closes the statement after the callback. Each `ResultSet` is closed right inside the loop. If using `CallableStatement` directly outside `JdbcTemplate`, close `ResultSet`, `CallableStatement`, and `Connection` manually in proper order.

This example expects the first and second result sets to match the contract. If the procedure changes order or adds a new `SELECT`, checking `resultSetIndex` catches the contract drift instead of silently mis-mapping data.

### 7. Why Consume All Results Before Reading OUT Parameters?

A procedure call returns a stream of results over the JDBC protocol. While unread result sets remain, the driver is still processing the `CALL` response. Reading OUT parameters prematurely can force the driver to discard remaining results, behave inconsistently across drivers/providers, or skip update count inspection.

Safe rules:

- Read every `ResultSet` completely in order.
- Close each `ResultSet` before calling `getMoreResults()`.
- Handle update counts if the procedure executes DML.
- Stop only when `getUpdateCount()` equals `-1` and no result set remains.
- Only then invoke `getInt()`, `getBigDecimal()`, or `getObject()` for OUT parameters.

Never call `executeQuery()` on a multi-result procedure. `executeQuery()` suits statements returning a single `ResultSet`; for mixed-result procedures, use `execute()` and a `getMoreResults()` loop.

### 8. Handling IN, OUT, and INOUT

JDBC uses `registerOutParameter()` to register output parameters:

~~~java
try (Connection connection = dataSource.getConnection();
     CallableStatement statement =
             connection.prepareCall("{call adjust_credit(?, ?, ?)}")) {

    statement.setLong(1, customerId);                 // IN
    statement.registerOutParameter(2, Types.DECIMAL); // OUT
    statement.setBigDecimal(3, adjustment);           // INOUT input
    statement.registerOutParameter(3, Types.DECIMAL); // INOUT output

    statement.execute();

    BigDecimal newCredit = statement.getBigDecimal(2);
    BigDecimal adjustedValue = statement.getBigDecimal(3);
}
~~~

In MySQL, the matching procedure declaration:

~~~sql
CREATE PROCEDURE adjust_credit(
    IN p_customer_id BIGINT,
    OUT p_new_credit DECIMAL(15, 2),
    INOUT p_adjustment DECIMAL(15, 2)
)
BEGIN
    UPDATE customers
    SET credit_limit = credit_limit + p_adjustment
    WHERE customer_id = p_customer_id;

    SELECT credit_limit
    INTO p_new_credit
    FROM customers
    WHERE customer_id = p_customer_id;

    SET p_adjustment = p_new_credit;
END;
~~~

This example illustrates parameter modes only. In production, verify the customer row exists, handle zero-row updates, lock rows when needed, and document INOUT semantics. Never assume the procedure always yields a valid value if `SELECT INTO` finds no rows.

### 9. Using `SimpleJdbcCall` for Declarative Mapping

`SimpleJdbcCall` is Spring JDBC's abstraction for stored procedures. It lets you declare `SqlOutParameter` and `returningResultSet()` to map result sets by name:

~~~java
@Repository
public class OrderReportDao {

    private final SimpleJdbcCall reportCall;

    public OrderReportDao(JdbcTemplate jdbcTemplate) {
        this.reportCall = new SimpleJdbcCall(jdbcTemplate)
                .withProcedureName("customer_order_report")
                .withoutProcedureColumnMetaDataAccess()
                .declareParameters(
                        new SqlParameter("p_customer_id", Types.BIGINT),
                        new SqlOutParameter("p_order_count", Types.INTEGER),
                        new SqlOutParameter("p_total_amount", Types.DECIMAL))
                .returningResultSet(
                        "orders",
                        (rs, rowNum) -> new OrderRow(
                                rs.getLong("order_id"),
                                rs.getObject("created_at", LocalDateTime.class),
                                rs.getString("status"),
                                rs.getBigDecimal("total_amount")))
                .returningResultSet(
                        "summaries",
                        (rs, rowNum) -> new StatusSummary(
                                rs.getString("status"),
                                rs.getLong("order_count"),
                                rs.getBigDecimal("amount_by_status")));
    }

    @SuppressWarnings("unchecked")
    public OrderReport load(long customerId) {
        Map<String, Object> result =
                reportCall.execute(Map.of("p_customer_id", customerId));

        List<OrderRow> orders =
                (List<OrderRow>) result.get("orders");
        List<StatusSummary> summaries =
                (List<StatusSummary>) result.get("summaries");
        Number count = (Number) result.get("p_order_count");
        BigDecimal total = (BigDecimal) result.get("p_total_amount");

        return new OrderReport(
                orders == null ? List.of() : orders,
                summaries == null ? List.of() : summaries,
                count == null ? 0 : count.intValue(),
                total == null ? BigDecimal.ZERO : total);
    }
}
~~~

When disabling metadata lookup via `withoutProcedureColumnMetaDataAccess()`, declare every parameter accurately by name, order, and SQL type. Declare `returningResultSet()` calls in the exact order the procedure emits result sets. Verify map keys and value types against your actual Spring JDBC version; if you need to inspect update counts or handle complex result streams, the `CallableStatement` callback shown earlier offers finer control.

### 10. Integrating Transactions with JPA

If the procedure is read-only, use `@Transactional(readOnly = true)` as in the examples. If the procedure writes data, use a standard read-write transaction:

~~~java
@Transactional
public void closeOrder(long orderId) {
    // Call a procedure that updates order status.
}
~~~

`JdbcTemplate` participates in Spring-managed transactions when it shares the same `DataSource` with `JpaTransactionManager` and proper transaction configuration. Never wire a separate `DataSource` for `JdbcTemplate` and expect JPA transactions to wrap that connection automatically.

Key guidelines:

- Never execute `COMMIT` or `ROLLBACK` manually inside a procedure when Spring manages the transaction, unless intentionally designed that way.
- MySQL DDL triggers an implicit commit; avoid mixing DDL inside business transactions.
- Never mark a transaction read-only if the procedure performs DML.
- Keep procedures short and minimize lock scope; never hold transactions open while making HTTP calls or waiting externally.
- On deadlocks, retry the entire transaction unit at the service layer with bounded attempts and idempotency.

`@Transactional(readOnly = true)` is metadata/a hint to the transaction manager and provider—not a security privilege mechanism replacing `GRANT` in MySQL.

### 11. Persistence Context and Procedure-Modified Data

The JPA persistence context may already hold managed entities loaded before a stored procedure updates those same rows. When a procedure runs via JDBC or a native call, Hibernate does not automatically know in-memory entities changed.

Example:

1. An `Order` entity is loaded into the persistence context.
2. A stored procedure updates `orders.status` to `SHIPPED`.
3. Code reloads the same entity from `EntityManager`.
4. Hibernate may return the managed instance with stale state because the identity map does not re-read rows automatically.

Mitigations:

- Call `entityManager.flush()` before the procedure if the procedure must observe pending JPA writes.
- Call `entityManager.refresh(entity)` on specific entities that must re-sync.
- Call `entityManager.clear()` after the procedure if many entities were affected and the persistence context can be discarded.
- If using a second-level cache or query cache, evict affected regions/entities via provider APIs; `clear()` only clears the first-level persistence context.

Never call `clear()` carelessly while unflushed entity changes remain, as pending writes would be dropped from the persistence context. Sequence flushing, procedure invocation, and refresh/clear deliberately within the transaction.

### 12. Mapping Result Sets to DTOs or Entities

Three common mapping approaches:

**JDBC RowMapper:** ideal for DTOs with strict control over types and column names.

~~~java
RowMapper<OrderRow> orderMapper = (rs, rowNum) ->
        new OrderRow(
                rs.getLong("order_id"),
                rs.getObject("created_at", LocalDateTime.class),
                rs.getString("status"),
                rs.getBigDecimal("total_amount"));
~~~

**JPA `@SqlResultSetMapping`:** fits when relying on persistence metadata mappings. Declare constructor results for DTOs or entity results for entities, ensuring column aliases match the mapping.

**`Object[]`:** handy for quick prototyping yet brittle if the procedure reorders columns. When used, document column indices and types explicitly, test the contract, and convert promptly to DTOs.

Never map a result set into a JPA entity merely because column names match. Entities may require primary keys, discriminators, version columns, or relationships omitted by the result set. For read-only reports, DTOs are simpler and safer.

### 13. Data Types and NULL in OUT Parameters

OUT parameters can be NULL. With primitive JDBC getters like `getInt()`, SQL NULL returns `0`; call `wasNull()` immediately after the getter to distinguish NULL from a genuine zero:

~~~java
int rawCount = statement.getInt("p_order_count");
Integer count = statement.wasNull() ? null : rawCount;
~~~

With `getBigDecimal()` and `getString()`, SQL NULL normally returns `null`. Never silently replace NULL with zero if NULL carries distinct business meaning.

Keep Java and SQL types compatible:

| MySQL | JDBC Type | Common Java Type |
|---|---|---|
| BIGINT | Types.BIGINT | Long |
| INT | Types.INTEGER | Integer |
| DECIMAL(p,s) | Types.DECIMAL | BigDecimal |
| VARCHAR | Types.VARCHAR | String |
| DATE | Types.DATE | LocalDate or java.sql.Date |
| DATETIME | Types.TIMESTAMP/driver-dependent mapping | LocalDateTime or Timestamp |
| TIMESTAMP | Types.TIMESTAMP | Instant/Timestamp per timezone policy |

For DECIMAL, always use `BigDecimal`; never convert through `double`, which risks monetary rounding errors.

### 14. Error Handling and Resource Cleanup

Common failures:

- Wrong procedure name or procedure not yet deployed.
- Missing `EXECUTE` privilege.
- Parameter name or position mismatch.
- Incompatible SQL type for OUT parameter.
- Second result set mapped as the first result set.
- Failing to consume all results, leaving the connection unusable for subsequent statements.
- Reading OUT parameters before the driver finishes the result stream.
- Procedure raising a SQL exception between result sets.
- Connection drop mid-procedure or during commit.

With plain JDBC, use try-with-resources for `ResultSet`/`Statement`/`Connection`. With `JdbcTemplate`, let Spring manage the connection/statement and close each `ResultSet` inside the callback. After an exception, never keep reusing a `CallableStatement` or connection in an indeterminate protocol state; let Spring/the pool reclaim or discard the broken connection.

Do not retry every procedure error. Missing privileges, parameter mismatches, or SQL syntax errors require code/configuration fixes. Deadlocks can retry the entire transaction if business logic allows. Connection loss during commit creates an indeterminate outcome; use idempotency keys or business-state lookups before retrying.

### 15. Procedure Security

Procedures are often granted `EXECUTE` so applications do not need direct table privileges. Actual execution privileges, however, depend on `SQL SECURITY DEFINER` versus `SQL SECURITY INVOKER`.

- `DEFINER`: executes with the privileges of the definer account within MySQL rules.
- `INVOKER`: executes with the privileges of the calling account.

Follow least privilege, manage definer accounts centrally, and avoid personal accounts as definers. Never build dynamic SQL inside procedures by concatenating user input. When dynamic table/column names are unavoidable, validate against an allowlist and quote identifiers; parameter markers only bind values, never identifiers.

Grant the runtime account only `EXECUTE` on required procedures plus minimal necessary access. Never grant `CREATE ROUTINE`, `ALTER ROUTINE`, or administrative privileges to runtime accounts unnecessarily.

### 16. Testing Procedures in Spring Boot

Run integration tests against real MySQL or a compatible MySQL container, since H2 does not fully emulate MySQL `CALL` syntax, OUT parameters, multiple result sets, or Connector/J behavior.

Example service integration test:

~~~java
@SpringBootTest
@Transactional
class JdbcOrderReportServiceIT {

    @Autowired
    private JdbcOrderReportService service;

    @Test
    void returnsTwoResultSetsAndOutParameters() {
        OrderReport report = service.loadReport(42L);

        assertEquals(3, report.orders().size());
        assertEquals(2, report.summaries().size());
        assertEquals(3, report.orderCount());
        assertEquals(new BigDecimal("125.50"), report.totalAmount());
    }
}
~~~

Fixtures must insert data with known totals and row counts. If a test runs with `@Transactional`, verify how the test framework rolls back and how the procedure shares that connection/transaction. Never rely on arbitrary pre-existing rows in a shared database.

Cases to test:

1. Customer with multiple orders across multiple statuses.
2. Customer with zero orders: empty result sets, count 0, total 0.
3. NULL OUT parameters when permitted by the contract.
4. Procedure emitting update counts interspersed between result sets.
5. Procedure throwing an error in the second result set.
6. DECIMAL columns with fractional cents and large values.
7. Adding/removing/reordering SELECTs in the procedure to verify contract-drift detection.
8. Connector/J reconnect or pool eviction after a procedure failure.
9. Procedure writing data and rolling back when the service throws an exception.
10. Entities loaded prior to a procedure being properly refreshed or cleared.

### 17. Symptom-Based Troubleshooting

| Symptom | Possible Cause | Resolution |
|---|---|---|
| `PROCEDURE ... does not exist` | Wrong schema/name or migration not deployed | Check active database, `SHOW PROCEDURE STATUS`, and deployment logs |
| `executeQuery()` misses results | Procedure returns multiple result sets or update counts | Use `execute()` and `getMoreResults()` |
| `getMoreResults()` skips data | Closing/advancing result sets out of order | Read and close the current result set before advancing |
| OUT parameter reads as 0 despite DB NULL | Called `getInt()` without checking `wasNull()` | Check `wasNull()` immediately after the getter |
| OUT parameter unavailable | Result sets or update counts not fully consumed | Consume the entire result stream before reading OUT values |
| Second result set maps to wrong DTO | Mapper depends on fragile column order or drifted contract | Check result set index, aliases, and data types |
| JPA returns entities with stale data | Persistence context/cache unaware of procedure updates | Flush before, refresh/clear after; evict second-level cache if needed |
| `EXECUTE command denied` | Runtime account lacks privileges | Grant `EXECUTE` on the procedure and verify `DEFINER`/`INVOKER` |
| Procedure runs outside expected transaction | `JdbcTemplate` uses a different `DataSource`/transaction manager or procedure commits itself | Share the same `DataSource`; inspect transaction manager and procedure SQL |
| Connection fails after procedure | Unconsumed result sets, protocol error, or broken socket | Close all results, inspect driver logs, and let pool discard bad connections |
| Wrong `DECIMAL` values | Using `float`/`double` or mismatched scale | Use `BigDecimal` and verify precision/scale |

### 18. Design and Operations Checklist

- [ ] Procedure has an explicit contract for IN, OUT, INOUT, and result set order.
- [ ] Column names, aliases, data types, and nullability documented.
- [ ] Procedure emits a stable number of result sets; changes are treated as breaking API changes.
- [ ] Appropriate calling API chosen: `@Procedure` for simple cases; JPA/JDBC for complex results.
- [ ] With JDBC, uses `execute()` and loops `getMoreResults()` until exhausted.
- [ ] Closes each `ResultSet` before advancing to the next result.
- [ ] Reads OUT parameters only after consuming all result sets and update counts.
- [ ] Checks `wasNull()` after primitive getters.
- [ ] DTO mapping avoids untested integer casts or fragile positional assumptions.
- [ ] JPA persistence context flushed/refreshed/cleared appropriately when procedures mutate data.
- [ ] `JdbcTemplate` shares the same `DataSource`/transaction manager when participating in JPA transactions.
- [ ] Procedure does not issue `COMMIT`/`ROLLBACK` outside transaction design.
- [ ] Runtime account has only `EXECUTE` and required minimal privileges; `DEFINER`/`INVOKER` audited.
- [ ] Integration tests run on real MySQL with the exact Connector/J version.
- [ ] Retries bounded; write operations handle indeterminate commit outcomes safely.
- [ ] Logs record procedure name, duration, SQLState, and correlation ID without leaking sensitive data.

### 19. Hands-On Exercise

A Spring Boot service calls procedure `customer_order_report`, which returns an order list, status summaries, and two OUT parameters. The application reads only the first result set; afterward, the next query on the same connection fails. Another endpoint returns `orderCount = 0` even for customers who have orders.

1. Why is `executeQuery()` unsuitable for procedures returning multiple result sets?
2. Write the JDBC loop processing `ResultSet`s and update counts until all results are exhausted.
3. Why must the current `ResultSet` be closed before calling `getMoreResults()`?
4. When is it safe to read OUT parameters?
5. How do you distinguish a NULL OUT parameter from numeric `0`?
6. When should you choose Spring Data `@Procedure`, JPA `StoredProcedureQuery`, or `JdbcTemplate`?
7. If a procedure updates an entity already managed by `EntityManager`, what must you do to the persistence context?
8. Design integration tests for a customer with zero orders and a procedure throwing an error between result sets.

### 20. Operational Principles

Treat every stored procedure as a versioned API contract: define parameters, result set order, aliases, data types, and OUT parameters explicitly. For a simple single OUT/scalar result, Spring Data `@Procedure` usually suffices; for multiple result sets and update counts, use `StoredProcedureQuery` or `JdbcTemplate` to iterate results deterministically. Consume and close every result before reading OUT parameters, keep transactions unified with Spring, synchronize the persistence context after procedure writes, and test against real MySQL and Connector/J.
