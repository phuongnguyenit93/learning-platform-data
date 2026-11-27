# Choosing JDBC or Specialized Tools When JPA Is Not Suitable

Spring Data JPA helps map tables to entities and manage the PersistenceContext, dirty checking, relationships, and transactions using an object model. However, not every data operation suits an ORM. Reporting queries with heavy aggregations, database-dependent SQL, massive bulk updates/deletes, batch imports/exports, or operations requiring exact control over every SQL statement may fit JDBC or a specialized tool better.

Common options:

- **JPA/JPQL**: fits working with entities, associations, lifecycles, and domain models.
- **Native SQL via JPA**: keeps JPA's EntityManager/transactions while allowing direct SQL.
- **Spring JDBC** (`JdbcTemplate`, `NamedParameterJdbcTemplate`, `JdbcClient`): fits when you want explicit control over SQL, parameter binding, and result mapping.
- **jOOQ**: fits when needing a type-safe SQL DSL, deep database feature support, and code generation.
- **MyBatis**: fits when wanting explicit SQL management alongside result-mapping mappers.
- **Spring Batch**: fits when the problem is high-volume data processing with jobs, chunks, checkpoints, retries, and restarts.

Choose tools based on the nature of the work, not habit. An application can use JPA for business CRUD and JDBC for reporting/batching within the same service layer. What matters is controlling transactions, PersistenceContext, and boundaries between data access approaches.

## 1. When is JPA no longer the best choice?

JPA works well when the application manipulates entities and relationships in a domain model. Yet ORM carries conversion costs between object graphs and SQL, as well as rules around dirty checking, flushing, persistence context, and fetch plans.

Signs to consider JDBC or another tool:

1. Queries with many CTEs, window functions, vendor-specific operators, or specialized SQL syntax.
2. Reports needing GROUP BY, pivots, multiple aggregates, UNIONs, or complex projections.
3. Massive bulk updates/deletes where per-entity lifecycle callbacks are not needed.
4. High-throughput imports of hundreds of thousands or millions of rows.
5. Batch inserts/updates needing exact control over statements, parameters, and generated keys.
6. Returned data is merely a flat read model with no need for managed entities.
7. Queries requiring optimization for a specific execution plan where ORM-generated SQL is hard to control.
8. Working with stored procedures, views, temporary tables, or vendor-specific database features.
9. Streaming/cursor reading with bounded memory.
10. Entity/association mappings causing N+1 queries or loading excessive object graphs.

A complex JPQL query does not automatically mean abandoning JPA. You can try native queries via EntityManager or a Spring Data repository first. Switch to JDBC when gains in SQL control, mapping, batching, or streaming are clear and measurable.

## 2. Distinguishing JPA native queries from JDBC

Native SQL does not equate to JDBC. JPA also lets you run raw SQL:

```java
List<Object[]> rows = entityManager
    .createNativeQuery("""
        select id, name, price
        from product
        where active = ?
        order by created_at desc
        """)
    .setParameter(1, true)
    .getResultList();
```

This is still a native query running through EntityManager. The JPA provider manages query execution within the current PersistenceContext/transaction and returns results via JPA mapping.

Comparison:

| Criterion | Native SQL via JPA | Spring JDBC |
|---|---|---|
| Execution API | EntityManager / Spring Data @Query | JdbcTemplate, NamedParameterJdbcTemplate, JdbcClient |
| SQL | Physical database SQL | Physical database SQL |
| Entity mapping | Can map entities or result set mappings | Typically mapped via RowMapper/ResultSetExtractor |
| PersistenceContext | Involved if returning entities or sharing EntityManager | Does not auto-sync PersistenceContext |
| Dirty checking/lifecycle | Present when working with managed entities; bulk DML still skips per-entity lifecycle | No automatic entity lifecycle |
| Batch and JDBC control | Provider decides many details | Direct control over JDBC API via Spring abstraction |
| Best suited for | Vendor SQL while still using JPA mappings | SQL-centric work, batching, reporting, custom mapping |

Native queries via JPA remain useful when you need specialized SQL whose result is a JPA-mapped entity or DTO. JDBC is better when you want direct control over ResultSet, batching, generated keys, streaming, or SQL-centric access.

## 3. What is Spring JDBC?

Spring JDBC is an abstraction over the JDBC API that reduces boilerplate such as opening/closing Connections, creating PreparedStatements, binding parameters, iterating ResultSets, and translating SQLExceptions into Spring's exception hierarchy.

Main APIs:

- `JdbcTemplate`: common API for executing queries/updates/batches.
- `NamedParameterJdbcTemplate`: binds parameters by name instead of `?` position.
- `JdbcClient`: fluent API introduced in Spring Framework 6.1, supporting named/positional parameters and queries/updates.
- `SimpleJdbcInsert` / `SimpleJdbcCall`: assists with inserts and stored procedures via metadata/configuration.

Spring JDBC is not an ORM. It does not manage entity graphs, dirty checking, cascades, or lazy loading. The application defines the SQL and how each row is mapped.

## 4. JdbcTemplate: queries and RowMapper

Example record as a read model:

```java
public record ProductRow(
    Long id,
    String name,
    BigDecimal price
) {
}
```

JDBC repository:

```java
@Repository
public class ProductJdbcRepository {

    private final JdbcTemplate jdbcTemplate;

    private static final RowMapper<ProductRow> ROW_MAPPER =
        (rs, rowNum) -> new ProductRow(
            rs.getLong("id"),
            rs.getString("name"),
            rs.getBigDecimal("price")
        );

    public ProductJdbcRepository(JdbcTemplate jdbcTemplate) {
        this.jdbcTemplate = jdbcTemplate;
    }

    public List<ProductRow> findActiveProducts() {
        return jdbcTemplate.query("""
            select id, name, price
            from product
            where active = ?
            order by name, id
            """, ROW_MAPPER, true);
    }

    public int updatePrice(Long id, BigDecimal price) {
        return jdbcTemplate.update("""
            update product
            set price = ?
            where id = ?
            """, price, id);
    }
}
```

Meaning:

- `query(..., RowMapper, args...)` executes SELECT and maps each row.
- `RowMapper` creates one object per row; no need to retain the entire ResultSet.
- `update(...)` returns the number of affected rows.
- Parameters are bound via PreparedStatement, never concatenated directly into SQL.

For nullable columns, watch out that primitive JDBC getters like `getLong()` return 0 for SQL NULL; call `rs.wasNull()` right after the getter to distinguish. For nullable types, you can use `getObject("column", Long.class)` if the driver supports proper JDBC mapping.

## 5. NamedParameterJdbcTemplate

For queries with many parameters, named parameters prevent positional mix-ups:

```java
@Repository
public class ProductSearchJdbcRepository {

    private final NamedParameterJdbcTemplate jdbc;

    public ProductSearchJdbcRepository(
            NamedParameterJdbcTemplate jdbc) {
        this.jdbc = jdbc;
    }

    public List<ProductRow> search(
            String category,
            BigDecimal minimumPrice,
            boolean active) {

        String sql = """
            select id, name, price
            from product
            where category = :category
              and price >= :minimumPrice
              and active = :active
            order by name, id
            """;

        MapSqlParameterSource params = new MapSqlParameterSource()
            .addValue("category", category)
            .addValue("minimumPrice", minimumPrice)
            .addValue("active", active);

        return jdbc.query(sql, params, (rs, rowNum) ->
            new ProductRow(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getBigDecimal("price")
            )
        );
    }
}
```

NamedParameterJdbcTemplate translates named placeholders into JDBC positional parameters before execution. Values are still bound via PreparedStatement.

With collections:

```java
String sql = """
    select id, name, price
    from product
    where id in (:ids)
    """;

List<ProductRow> rows = jdbc.query(
    sql,
    Map.of("ids", ids),
    ROW_MAPPER
);
```

Spring can expand a collection into multiple placeholders. Handle empty lists at the application layer before calling the query; SQL `IN ()` is not portable and handling may depend on database/framework. For very large lists, chunk or use database-specific mechanisms such as temporary tables/array parameters.

## 6. JdbcClient in Spring Framework 6.1+

`JdbcClient` provides a fluent API over JDBC with named and positional parameters. It fits when you want concise code while keeping SQL and mapping explicit.

Example:

```java
@Repository
public class ProductJdbcClientRepository {

    private final JdbcClient jdbcClient;

    public ProductJdbcClientRepository(JdbcClient jdbcClient) {
        this.jdbcClient = jdbcClient;
    }

    public Optional<ProductRow> findById(Long id) {
        return jdbcClient.sql("""
            select id, name, price
            from product
            where id = :id
            """)
            .param("id", id)
            .query((rs, rowNum) -> new ProductRow(
                rs.getLong("id"),
                rs.getString("name"),
                rs.getBigDecimal("price")
            ))
            .optional();
    }
}
```

In Spring Boot, auto-configuration of JdbcClient depends on the Spring Boot/Spring Framework version and classpath. If no auto-configured bean exists, you can create one with `JdbcClient.create(dataSource)`.

`JdbcClient` does not replace JDBC semantics; it still executes SQL and maps ResultSets. If the project uses Spring Framework prior to 6.1, use JdbcTemplate or NamedParameterJdbcTemplate.

## 7. Batch update and batch insert with JDBC

JDBC batching fits when you need to execute many identically structured statements with different parameter sets. `JdbcTemplate.batchUpdate` sends multiple value sets in one batch.

Example:

```java
public int[] updatePrices(List<PriceChange> changes) {
    return jdbcTemplate.batchUpdate(
        """
        update product
        set price = ?
        where id = ?
        """,
        new BatchPreparedStatementSetter() {
            @Override
            public void setValues(
                    PreparedStatement ps,
                    int index) throws SQLException {
                PriceChange change = changes.get(index);
                ps.setBigDecimal(1, change.price());
                ps.setLong(2, change.productId());
            }

            @Override
            public int getBatchSize() {
                return changes.size();
            }
        }
    );
}
```

Record:

```java
public record PriceChange(
    Long productId,
    BigDecimal price
) {
}
```

The result is an array of updated row counts per batch command. A JDBC driver may return `Statement.SUCCESS_NO_INFO` or `Statement.EXECUTE_FAILED` in some batch scenarios; handle according to driver and transaction contracts.

For large datasets:

- Split the list into appropriately sized chunks.
- Use clear transaction boundaries per chunk or for the entire job depending on atomicity requirements.
- Measure batch size, round-trips, lock duration, and memory.
- Use PreparedStatement parameter binding.
- Handle retries/idempotency if the job can re-run.
- Check whether the driver/database supports batch rewriting or corresponding optimizations.

JDBC batching does not automatically invoke JPA lifecycle callbacks, cascades, or dirty checking. If operating on tables also managed by JPA within the same PersistenceContext, synchronize state as described in the transaction section below.

## 8. Batch insert and generated keys

If an insert needs generated keys, JDBC supports `GeneratedKeyHolder` with `JdbcTemplate`:

```java
KeyHolder keyHolder = new GeneratedKeyHolder();

jdbcTemplate.update(connection -> {
    PreparedStatement ps = connection.prepareStatement(
        """
        insert into product(name, price, active)
        values (?, ?, ?)
        """,
        Statement.RETURN_GENERATED_KEYS
    );

    ps.setString(1, "Tea");
    ps.setBigDecimal(2, new BigDecimal("12.50"));
    ps.setBoolean(3, true);
    return ps;
}, keyHolder);

Number generatedId = keyHolder.getKey();
```

This snippet is a method body inside a JDBC repository; you need imports for `KeyHolder`, `GeneratedKeyHolder`, `PreparedStatement`, `Statement`, and a database/JDBC driver supporting generated keys.

For batch inserts, retrieving generated keys for each row depends on the driver/database and API. Do not assume every driver returns keys in the exact same way or order. If exact mapping is required, consult driver documentation and integration-test on the target database.

## 9. JDBC and JPA in the same transaction

A Spring Boot application typically shares the same DataSource for JPA and JdbcTemplate. When configured properly, `JpaTransactionManager` can coordinate JDBC access on the same DataSource inside a JPA transaction; `JdbcTemplate` uses Spring's synchronization to participate in the transaction-managed connection.

Example:

```java
@Service
public class ProductMaintenanceService {

    private final ProductRepository jpaRepository;
    private final ProductJdbcRepository jdbcRepository;
    private final EntityManager entityManager;

    public ProductMaintenanceService(
            ProductRepository jpaRepository,
            ProductJdbcRepository jdbcRepository,
            EntityManager entityManager) {
        this.jpaRepository = jpaRepository;
        this.jdbcRepository = jdbcRepository;
        this.entityManager = entityManager;
    }

    @Transactional
    public void changePrice(Long id, BigDecimal price) {
        Product product = jpaRepository.findById(id)
            .orElseThrow();

        entityManager.flush();

        jdbcRepository.updatePrice(id, price);

        entityManager.refresh(product);
    }
}
```

Sequence:

1. Load entity via JPA.
2. Flush pending JPA changes before JDBC reads/writes the same data.
3. Execute UPDATE via JDBC.
4. Refresh the specific entity to update its state from the database.

If JDBC modifies many managed entities, consider `entityManager.clear()` to detach the entire persistence context and reload when needed. Clear affects all managed entities in the context, so do not use it carelessly.

Without refreshing/clearing, entities in the first-level cache may hold old values. A subsequent flush could write stale state back to the database if the entity was modified in memory. This is a subtle source of lost-update bugs.

Important conditions:

- JPA and JDBC must share the same DataSource/transaction resource if they are to share a local transaction.
- Access JDBC via JdbcTemplate/NamedParameterJdbcTemplate or a Spring-managed connection to participate in the transaction.
- If the application has multiple DataSources/transaction managers, specify the appropriate manager via `@Transactional(transactionManager = "...")`.
- Two independent transaction managers do not automatically create a shared atomic transaction. If atomicity across multiple resources is needed, design distributed transactions/JTA or appropriate compensation workflows.
- Do not obtain connections directly via `DriverManager` in a transaction-managed Spring service.

## 10. Flush, clear, and read/write ordering when mixing ORM with JDBC

JPA and JDBC do not share the same object state:

- JPA PersistenceContext holds entity instances and dirty-checking snapshots.
- JDBC acts directly on database rows.
- JDBC does not notify EntityManager that an entity was UPDATED/DELETED.
- EntityManager does not automatically re-read every row after JDBC runs.

Common synchronization workflow:

| Operation | Purpose |
|---|---|
| `entityManager.flush()` before JDBC | Writes pending JPA changes so JDBC can see them |
| JDBC update/delete | Modifies database directly |
| `entityManager.refresh(entity)` | Reloads a specific managed entity |
| `entityManager.clear()` | Detaches all managed entities to avoid using stale state |
| Reload entity | Fetches database state into a fresh/clean context |

Not every JDBC SELECT requires a flush; only flush when the query must observe pending JPA changes in business order. AUTO flush may occur depending on query/provider, yet when mixing APIs you should determine ordering explicitly.

After a JDBC UPDATE, if related entities are currently managed, refresh or clear before continuing to work with that state. If JDBC DELETES a managed entity, do not continue using the instance as if it still existed in the database.

## 11. Performance comparison with JPA batching

Before migrating bulk operations to JDBC, check whether JPA is already configured properly. Hibernate supports JDBC batching for inserts/updates:

```properties
spring.jpa.properties.hibernate.jdbc.batch_size=50
spring.jpa.properties.hibernate.order_inserts=true
spring.jpa.properties.hibernate.order_updates=true
```

With many entities, flushing and clearing in chunks prevents the PersistenceContext from growing too large:

```java
for (int i = 0; i < entities.size(); i++) {
    entityManager.persist(entities.get(i));

    if ((i + 1) % 50 == 0) {
        entityManager.flush();
        entityManager.clear();
    }
}
```

This is an illustrative skeleton; if ID generation uses the identity strategy, insert batching capability may be limited depending on Hibernate/database. After clear, previous entities are detached; do not retain and continue modifying them as managed.

Fair comparison:

- JPA batching preserves entity lifecycles, cascades, and mapping semantics, but incurs entity management overhead.
- JDBC batching controls SQL directly and avoids building entity graphs, but the application manages mapping, auditing, optimistic locking, and consistency manually.
- Native bulk DML via JPA also bypasses per-entity lifecycles, even though it runs through EntityManager.

Measure on production-like data and schema before deciding. Do not switch to JDBC merely because row counts are large if JPA batching already meets throughput and semantics needs.

## 12. jOOQ: type-safe SQL DSL

jOOQ provides a DSL for constructing SQL in Java, and can use code generation from the schema to produce typed table/field references.

Illustrative jOOQ-style example:

```java
var records = dsl
    .select(PRODUCT.ID, PRODUCT.NAME, PRODUCT.PRICE)
    .from(PRODUCT)
    .where(PRODUCT.ACTIVE.eq(true))
    .orderBy(PRODUCT.CREATED_AT.desc(), PRODUCT.ID.desc())
    .limit(50)
    .fetch();
```

`PRODUCT` and field constants in the example are typically generated from the schema by the jOOQ code generator. Actual API details depend on code generation config and edition/version.

jOOQ fits when:

- Queries use CTEs, window functions, lateral joins, JSON/arrays, or vendor-specific SQL.
- SQL expressions need representation in a typed DSL.
- You want compile-time assistance for table/column names and data types when schema/code generation stay in sync.
- SQL is a central part of the domain/data access layer.

Trade-offs:

- Code generation must be managed alongside schema migrations.
- Generated sources must be updated whenever the schema changes.
- Certain features or database support may depend on edition/version.
- jOOQ does not replace JPA entity lifecycles; it can run alongside JPA for query-centric workloads.

## 13. MyBatis: SQL mapper

MyBatis lets you write explicit SQL in XML mappers or annotations and map results into Java objects.

Mapper interface:

```java
@Mapper
public interface ProductMapper {

    @Select("""
        select id, name, price
        from product
        where active = #{active}
        order by name, id
        """)
    List<ProductRow> findActive(
        @Param("active") boolean active
    );
}
```

MyBatis fits when:

- You want per-mapper-method SQL control.
- Queries have complex structures or many dynamic SQL branches.
- The team is comfortable managing XML/annotation mappers.
- Results need mapping into DTOs/associations via resultMaps.

MyBatis does not provide a PersistenceContext or dirty checking like JPA. The application controls SQL and mapping; transactions can integrate via Spring's transaction manager as configured.

Never use string substitution `${...}` for user data in MyBatis because it interpolates directly into SQL. Use `#{...}` to bind values. If dynamic identifiers must be substituted, whitelist values before inserting them into SQL.

## 14. Spring Batch for large data jobs

If the requirement is processing files or millions of database rows as a job, the problem goes beyond choosing JDBC vs. JPA. You must manage:

- Chunk size and transaction boundaries.
- Checkpoints/restarts after failures.
- Retries/skips for bad records.
- Idempotency on re-runs.
- Job parameters and execution state.
- Reader/writer throughput.
- Job monitoring and operations.

Spring Batch provides abstractions like ItemReader, ItemProcessor, ItemWriter, and chunk-oriented processing. You can use JDBC cursor/paging readers, repository readers, or custom readers depending on workload.

Conceptual flow:

```text
ItemReader
    -> ItemProcessor
        -> ItemWriter
            -> Commit chunk
                -> Checkpoint
```

For example, a chunk of 500 records is read, processed, written, and committed. If the job fails, restart can resume from the checkpoint according to reader/writer configuration and semantics.

Spring Batch fits ETL, imports/exports, reconciliation, and batch maintenance. Do not pull in Spring Batch just to execute one short `JdbcTemplate.batchUpdate`; use the framework when job lifecycles, restartability, skip/retry, and operational tooling are needed.

## 15. Stored procedures, views, and database-specific features

You can choose JDBC or JPA native queries when calling stored procedures or reading views.

JPA supports stored procedures via `StoredProcedureQuery` or `@NamedStoredProcedureQuery`; Spring JDBC offers `SimpleJdbcCall`. Choose based on current mapping and transaction setup.

Database views are useful for complex read models. You can read views using a JDBC DTO mapper or map them as read-only entities under provider-specific configuration. Do not map a view to an updatable entity if the view does not support updates or the mapping lacks clear semantics.

For database-specific features like JSON operators, arrays, full-text search, recursive CTEs, or window functions, native SQL/JDBC/jOOQ usually express intent more clearly than JPQL. Isolate database-dependent SQL in repositories/adapters so vendor syntax does not leak into services/domain logic.

## 16. Streaming and reading large datasets

If a SELECT returns millions of rows, do not use `queryForList` or materialize the entire result into a List if memory is insufficient.

Options:

- Forward-only JDBC `ResultSet` with an appropriate fetch size.
- `JdbcTemplate.query(..., RowCallbackHandler)` to process each row.
- Spring Batch readers to read in chunks.
- JPA Stream/scrolling if provider and transaction support it properly; streams must be closed and transactions/connections kept open for the required duration.

RowCallbackHandler example:

```java
jdbcTemplate.query(
    "select id, name from product order by id",
    rs -> {
        long id = rs.getLong("id");
        String name = rs.getString("name");
        processRow(id, name);
    }
);
```

RowCallbackHandler processes each row in the callback, avoiding constructing a huge List. Still, drivers may buffer rows depending on fetch size, cursor mode, and database. Configure/verify the driver to actually stream; using a callback alone does not guarantee constant memory on every driver.

If processing takes a long time, transactions and connections may be held open too long. Split into chunks/pages or use a batch framework if appropriate.

## 17. SQL security and dynamic queries

Whether using JPA native queries, JdbcTemplate, jOOQ, or MyBatis, the general rules are:

- Bind all data values using parameters.
- Never concatenate user input into WHERE, LIKE, LIMIT, or SQL literals.
- Parameters cannot replace table/column names, keywords, or ASC/DESC direction.
- Dynamic identifiers must come from an application-defined whitelist.
- Enforce access control in the service/domain layer; SQL parameterization does not replace authorization.
- Do not log sensitive bind values in production.

Safe example:

```java
jdbcTemplate.query(
    "select id, name from product where category = ?",
    ROW_MAPPER,
    category
);
```

Identifier whitelist example:

```java
String orderBy = switch (sortKey) {
    case "name" -> "name";
    case "price" -> "price";
    case "createdAt" -> "created_at";
    default -> "id";
};

String sql = "select id, name from product order by " + orderBy;
```

Only concatenate `orderBy` because it is selected from application-controlled literals. Never substitute arbitrary request values.

## 18. Transactions and multiple DataSources

If JPA and JDBC share one DataSource and one matching transaction manager, they can participate in the same local transaction. If there are two independent DataSources, a single standard `@Transactional` does not automatically guarantee atomic commit/rollback across both.

With multiple resources:

- Identify which transaction manager each repository/service uses.
- Use `@Transactional(transactionManager = "jpaTransactionManager")` or the corresponding manager name when clarity is needed.
- If atomic commits across multiple resources are required, evaluate JTA/XA and operational costs.
- If distributed transactions are unsuitable, design outbox, saga, or retry/compensation workflows according to business needs.
- Do not assume a JDBC update and a JPA update across two datasources will roll back together.

Also pay attention to transaction propagation. A `REQUIRES_NEW` method runs its own transaction and commits independently of an outer transaction. Do not use it if business logic requires all operations to roll back together.

## 19. Comparing tools by need

| Need | Option to consider | Reason |
|---|---|---|
| Entity CRUD, associations, lifecycles | Spring Data JPA | Mapping and persistence context |
| Moderate object-centric queries | JPQL/Criteria/Specification | Tied to the entity model |
| Specialized SQL while still needing EntityManager | JPA native query | Preserves JPA transactions/mappings |
| Custom SQL, clear row mapping | JdbcTemplate | Simple API, SQL control |
| Many parameters and collection parameters | NamedParameterJdbcTemplate | Readable queries |
| Fluent JDBC API on Spring 6.1+ | JdbcClient | Fluent syntax, clear mapping |
| SQL DSL and compile-time schema types | jOOQ | Complex queries, database-centric |
| SQL mapper/XML and dynamic SQL | MyBatis | Explicit SQL, resultMap |
| Large import/export jobs, restart/retry | Spring Batch | Job lifecycle and chunk processing |
| Simple batch updates | JdbcTemplate.batchUpdate | Minimal abstraction, direct efficiency |

No single tool is always fastest. Performance depends on SQL, indexes, cardinality, drivers, network round-trips, transaction size, and mapping style.

## 20. Decision process before leaving JPA

1. Identify bottlenecks using SQL logs, metrics, and execution plans.
2. Check N+1 queries, fetch plans, indexes, pagination, and query counts.
3. Check whether JPQL/Criteria/EntityGraph or DTO projections can optimize it.
4. Check Hibernate JDBC batching for bulk inserts/updates.
5. Try native queries via JPA if only specialized SQL syntax is needed.
6. Choose JdbcTemplate/JdbcClient when direct SQL and ResultSet control are required.
7. Choose jOOQ when query DSL/code generation delivers clear value.
8. Choose MyBatis when SQL mappers match the team's style.
9. Choose Spring Batch when job/chunk/checkpoint/restart capabilities are needed.
10. Design transactions, flush/clear, optimistic locking, auditing, and retries before implementation.
11. Benchmark using the same dataset, database, and transaction semantics.
12. Write integration tests against the target database engine.

Do not compare a JPA entity load against a JDBC DTO projection and conclude JDBC is always faster. The two may be returning different data and executing different semantics. Benchmarks must compare identical business requirements.

## 21. Testing and observability

For JDBC/JPA hybrids, testing should cover:

- Correct SQL and parameter binding.
- RowMapper handling NULLs and JDBC types properly.
- Batch updates reporting appropriate row counts.
- Generated keys behaving properly with the driver/database.
- JDBC and JPA participating in the same transaction when designed to do so.
- Rollback of one operation rolling back the other within the same local transaction.
- Flushing before JDBC allowing pending changes to be visible.
- Refreshing/clearing preventing stale entity use after JDBC DML.
- Job retries neither creating duplicates nor skipping data.
- Streaming not unexpectedly materializing the entire result set.
- Count/page or cursor behavior matching the API contract.

Use Testcontainers or a test database using the same engine as production when specialized SQL is involved. H2 may not accurately reproduce real database data types, locking, generated keys, SQL dialects, and execution plans.

Metrics to monitor include query count, latency, rows read/updated, batch size, transaction duration, connection pool utilization, lock waits, memory, and retry/failure counts.

## 22. Common mistakes

| Symptom | Cause | Resolution |
|---|---|---|
| JDBC does not see JPA-persisted data | Pending JPA changes not flushed | Flush before JDBC reads |
| JPA returns old values after JDBC UPDATE | PersistenceContext still holds stale entities | Refresh entity or clear appropriately |
| JPA overwrites JDBC results | Stale entity dirty-checked/flushed after JDBC | Sync context before next flush |
| JDBC does not roll back with JPA | Different DataSource or transaction manager | Share resource/manager or design distributed consistency |
| SQL injection via sort column | Concatenating identifier from request | Whitelist identifiers |
| IN query fails on empty list | Generated SQL IN () is invalid/non-portable | Handle empty list before query |
| Slow batch or driver error | Inappropriate batch size/driver rewrite/parameter limit | Measure and adjust chunk/batch size |
| Missing generated keys in batch | Driver does not return keys as assumed | Check driver docs and integration-test |
| Memory spikes when reading many rows | Materializing full List or driver buffering | RowCallbackHandler/cursor/chunk with proper fetch size |
| N+1 still occurs in JPA | Fetch plan does not resolve associations | EntityGraph/fetch join/batch fetching/DTO |
| Switching to JDBC loses audit/cascade | JDBC bypasses JPA lifecycle | Implement audit/domain behavior explicitly |
| Spring Batch restart duplicates processing | Writer is not idempotent or checkpoint is wrong | Design idempotency and transactions/checkpoints |

## 23. Tool selection checklist

- [ ] Measured the bottleneck instead of guessing JPA is slow?
- [ ] JPA queries/fetch plans/indexes/batching already optimized?
- [ ] Does the result require managed entities or DTOs/read models?
- [ ] Is a native query via JPA sufficient?
- [ ] Do you need JdbcTemplate, NamedParameterJdbcTemplate, or JdbcClient?
- [ ] Does the query fit jOOQ or MyBatis better?
- [ ] Does the problem need Spring Batch job lifecycle?
- [ ] Do JDBC and JPA share the DataSource/transaction manager properly?
- [ ] Are flush/refresh/clear defined?
- [ ] Are cascades, callbacks, auditing, or optimistic locking needed?
- [ ] Have batch/chunk/fetch sizes been measured?
- [ ] Are dynamic identifiers whitelisted?
- [ ] Do integration tests run on a production-compatible database?
- [ ] Are metrics in place for latency, query count, memory, locks, and connection pool?

## 24. Conclusion

JPA is a solid choice for CRUD and domain workflows needing entity mapping, associations, lifecycles, and a PersistenceContext. When complex SQL, reporting, bulk processing, or streaming make ORM awkward, native queries, Spring JDBC, jOOQ, or MyBatis can handle the appropriate parts. For large jobs requiring restarts, checkpoints, retries, and chunking, Spring Batch provides a higher operational layer than raw JDBC batches.

When mixing JDBC with JPA, actively synchronize the two worlds: flush JPA changes before JDBC needs to read them; refresh or clear managed entities after JDBC DML; ensure the same DataSource and transaction manager if atomicity is required. JDBC does not automatically invoke JPA lifecycle callbacks, cascades, dirty checking, or optimistic locking, so necessary business semantics must be designed explicitly.

Choose tools based on actual SQL, required return data, transaction semantics, throughput, and operability. Measure with the same workload, test against the target database/driver, and maintain clean data access boundaries so the application can use multiple tools while remaining maintainable.
