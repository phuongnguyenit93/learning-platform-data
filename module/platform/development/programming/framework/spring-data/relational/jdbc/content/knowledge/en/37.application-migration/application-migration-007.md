# Adopting an Existing Schema Without Unintended Data Changes

Introducing Spring Data Relational JDBC into an application with an existing database does not require recreating the schema or reloading data. Spring Data JDBC can work with existing tables, keys, and data as long as the mapping matches the database structure accurately. The tricky part is preserving the contract that other applications, reports, triggers, stored procedures, and batch jobs depend on.

The safe rule is **discover first, map second, alter schema last and only when truly necessary**:

1. Inventory existing schemas, data, constraints, indexes, sequences, triggers, and consumers.
2. Design Spring Data JDBC mappings to match the existing schema using explicit table and column names.
3. Verify insert/update/delete behavior on a database clone populated with representative data.
4. Manage necessary changes using versioned migrations; never let the application alter the schema implicitly.
5. Compare before-and-after data and roll out in observable, reversible steps.

This lesson focuses on adopting an existing database for Spring Data JDBC while preserving data and minimizing side effects. The first milestone is reading existing data accurately; enable write paths only after confirming mapping and transaction behavior.

## 1. Distinguishing the Existing Schema from Java Mapping

The schema is the database contract: tables, columns, data types, primary keys, foreign keys, unique/check constraints, indexes, defaults, sequences, triggers, views, and permissions.

Java mapping is how Spring Data JDBC interprets that contract. Annotations do not alter an existing schema on their own. Example:

~~~java
@Table("legacy_order")
public class PurchaseOrder {

    @Id
    @Column("order_no")
    private Long id;

    @Column("customer_no")
    private Long customerId;

    @Column("order_state")
    private String status;
}
~~~

This class instructs Spring Data JDBC to map to the `legacy_order` table with columns `order_no`, `customer_no`, and `order_state`. If the real database uses different names, types, or schemas, the mapping must be adjusted accordingly.

Never assume renaming a Java property renames a database column. Changing annotations also does not run migrations. DDL changes only when a tool or operator executes the corresponding DDL statements.

### Components to Inventory

| Component | What to Record |
|---|---|
| Tables and schemas | Exact names, case sensitivity, default owner/schema |
| Columns | Names, types, lengths, precision/scale, nullability |
| Primary keys | Single-column or composite, ID type, generated vs. assigned |
| Foreign keys | Referenced columns, delete/update actions, whether constraints are enabled |
| Unique/check | Business keys, data validity rules |
| Indexes | Columns, ordering, uniqueness, partial/filtered indexes |
| Defaults | Default values, expressions, sequences |
| Triggers | Auto-generated audit fields, timestamp updates, business cascades |
| Sequences/identities | Sequence names, current values, increments, caching |
| Views/procedures | Consumers, permissions, and semantics |
| Data | Row counts, NULLs, duplicates, orphans, boundary values |
| Current writers | Applications, batches, ETL jobs, reports, or manual SQL |

Schema dumps and migration history should be archived alongside deployment records for later comparison.

## 2. Start with Read Permissions and a Data Clone

Before connecting Spring Data JDBC to an environment with real data:

- Take a schema dump or metadata snapshot.
- Create a restorable backup and test the restore procedure.
- Use staging or a database clone with representative structure and data.
- Grant read-only permissions for the discovery phase if possible.
- Never run repository saves/deletes, migrations, or seed scripts on production just to test mappings.
- Record current migration versions and the database version.

A read-only connection lets you verify mappings and queries without write privileges. For new applications, you can configure a read-only `DataSource` or a `SELECT`-only database user during shadow-read phases. Read-only flags on JDBC connections or application configuration do not replace database permissions; actual privileges should be restricted on the database user.

### Capturing Baseline Metrics

Example overview SQL checks:

~~~sql
SELECT COUNT(*) AS order_count
FROM legacy_order;

SELECT COUNT(*) AS line_count
FROM legacy_order_line;

SELECT COUNT(*) AS rows_without_customer
FROM legacy_order
WHERE customer_no IS NULL;

SELECT order_state, COUNT(*) AS total
FROM legacy_order
GROUP BY order_state
ORDER BY order_state;
~~~

This is your baseline to compare after migrations or after enabling a new write path. On large tables, `COUNT(*)` can be expensive; choose an appropriate timing, snapshot, or database statistics approach.

Beyond counts, record:

- Total distinct IDs.
- Min/max IDs and timestamps.
- NULL counts across critical columns.
- Duplicate counts on business keys.
- Orphaned FKs if the legacy schema did not enforce FKs.
- Totals of amounts/quantities for critical invariants.
- A masked sample preserving relationships and data types.

## 3. Mapping Table and Column Names Explicitly

Spring Data Relational has a `NamingStrategy` to derive table/column names from classes/properties. Legacy schemas often follow custom conventions: prefixes, abbreviations, uppercase names, shorthands, or column names that do not match Java properties.

When adopting an existing schema, favor explicit mappings for critical names:

~~~java
@Table("legacy_order")
public class PurchaseOrder {

    @Id
    @Column("order_no")
    private Long id;

    @Column("customer_no")
    private Long customerId;

    @Column("order_state")
    private String status;

    @Column("created_on")
    private LocalDateTime createdAt;
}
~~~

If the schema contains table `ORDER_HEADER` and column `ORDER_ID`, map identifiers accurately for your database and JDBC driver. Some databases distinguish quoted identifiers from unquoted identifiers; case-folding rules vary by vendor. Do not alter casing in migrations just to match Java conventions.

### Using NamingStrategy When Conventions Are Consistent

If the entire legacy schema follows one consistent rule, you can configure a custom `NamingStrategy`. However, if only certain tables/columns are exceptions, `@Table` and `@Column` are usually easier to understand and carry smaller blast radii.

Changing `NamingStrategy` can affect many aggregates at once. Verify mapping metadata across all affected entities before deploying.

### Schemas, Catalogs, and Default Schema

If the database has multiple schemas such as `sales`, `billing`, and `reporting`, verify the default connection points to the right schema or that SQL/mappings are configured properly. A table with the same name can exist in multiple schemas; a query working locally yet hitting the wrong schema in production is a major data risk.

Do not assume the database name in a JDBC URL equals the schema name. Verify the current schema or search path using a database-specific query as the real application user.

## 4. Preserving Primary Keys and ID Strategies

Existing IDs are often referenced by other tables, APIs, import files, external systems, and reports. Do not change IDs just to switch frameworks.

For a root with a numeric primary key:

~~~java
@Table("legacy_customer")
public class Customer {

    @Id
    @Column("customer_no")
    private Long id;

    @Column("display_name")
    private String name;
}
~~~

Before writing, determine whether IDs are generated by:

- Identity/auto-increment columns.
- Database sequences.
- Triggers.
- The application.
- External systems or import files.

Spring Data JDBC and the JDBC dialect must align with the database's ID generation strategy. Test inserts on the real engine/driver to confirm generated keys are returned and populated on the object.

### Assigned IDs and Detecting New Entities

If the legacy application assigns IDs before inserting, a non-null ID does not automatically mean the row already exists. Spring Data JDBC uses newness detection; with assigned IDs, configure newness tracking appropriately—such as implementing `Persistable` and `isNew()` when needed.

~~~java
public class ImportedCustomer implements Persistable<Long> {

    @Id
    @Column("customer_no")
    private Long id;

    @Transient
    private boolean newEntity;

    protected ImportedCustomer() {}

    public ImportedCustomer(Long id, String name) {
        this.id = id;
        this.name = name;
        this.newEntity = true;
    }

    @Override
    public Long getId() {
        return id;
    }

    @Override
    public boolean isNew() {
        return newEntity;
    }
}
~~~

This is a condensed example; complete the state transition after insert according to your application's lifecycle or immutable model. If `isNew` stays true forever, the next save will attempt another insert and violate the primary key. If it is always false, the first save may take the update branch.

### Do Not Reset Sequences Arbitrarily

If data was imported with manual IDs into an identity/sequence-backed table, the current sequence value may lag behind `MAX(id)`. Subsequent inserts can collide with existing primary keys.

Before synchronizing a sequence:

1. Identify the exact sequence/identity in use.
2. Read its current value and `MAX(primary_key)`.
3. Check whether other writers can allocate IDs concurrently.
4. Use a reviewed vendor-specific command inside a maintenance window if necessary.
5. Verify subsequent inserts do not produce duplicate IDs.

Never run generic `setval`/`ALTER SEQUENCE` snippets on production without confirming the sequence name, permissions, and concurrency.

## 5. Mapping Collections Without Unintended Table Changes

In Spring Data JDBC, entities owned inside a collection usually reside in a separate table with an FK back to the owner. `@MappedCollection` specifies the FK column and the key/index column if the collection requires element positioning.

~~~java
@Table("legacy_order")
public class PurchaseOrder {

    @Id
    @Column("order_no")
    private Long id;

    @MappedCollection(idColumn = "order_no", keyColumn = "line_position")
    private List<OrderLine> lines = new ArrayList<>();
}

@Table("legacy_order_line")
public class OrderLine {

    @Id
    @Column("line_no")
    private Long id;

    @Column("product_no")
    private Long productId;

    @Column("ordered_qty")
    private Integer quantity;
}
~~~

This mapping assumes `legacy_order_line` has column `order_no` pointing to `legacy_order.order_no` and `line_position` storing the `List` index. Verify exact column names, data types, and constraints against the real schema.

| Mapping | Required Legacy Column |
|---|---|
| Root `@Id` | Root primary key |
| `@MappedCollection(idColumn = "order_no")` | FK `order_no` in child table |
| `keyColumn = "line_position"` | Column storing collection index/key |
| Child `@Id` | Child PK if mapping uses child identity |
| Child reference `productId` | `product_no` column, with FK if schema enforces it |

### Lists Require Durable Ordering

If the Java model uses a `List`, the database must have a way to store element positions. If the legacy table lacks an order/index column, you cannot assume read order will match insert order or physical storage order.

Options:

- Add a position column via migration if ordering is part of the contract.
- Use a `Set` if the domain does not require order.
- Use a custom query with `ORDER BY` for read models.
- Keep an existing `sortOrder`/`businessLineNumber` property if it already represents ordering.

Never add `keyColumn` to the annotation before the column exists in the table. Annotations do not create columns, and queries will fail when the framework references a missing column.

### Maps and Sets

`Map`s require a suitable key column; `Set`s must not depend on ordering. If a legacy schema uses composite keys or unusual association tables, test the actual mapping before assuming it behaves as a standard owned collection.

If a child table is referenced by multiple roots or has an independent lifecycle, do not map it as an owned child merely for convenience. Define aggregate boundaries and use IDs/references or appropriate read queries.

## 6. Preserving Cross-Aggregate Relationships

An FK column such as `customer_no` in `legacy_order` typically represents a reference to `Customer`, not that `Customer` is a child of `PurchaseOrder`.

You can map a scalar ID:

~~~java
@Column("customer_no")
private Long customerId;
~~~

Or use `AggregateReference` if the domain wants to express a typed reference to another aggregate root:

~~~java
private AggregateReference<Customer, Long> customer;
~~~

Either way, Spring Data JDBC does not auto-load `Customer` via a lazy proxy and does not cascade saves/deletes to the `Customer` aggregate.

If you need the customer name on an order screen, use a JOIN/projection query. If you need to modify `Customer`, load and save `Customer` via its own repository.

### Protecting Legacy Foreign Keys

Do not add new FKs solely because the Java model has a reference property. First verify whether existing data satisfies the constraint:

~~~sql
SELECT o.order_no, o.customer_no
FROM legacy_order o
LEFT JOIN legacy_customer c
    ON c.customer_no = o.customer_no
WHERE o.customer_no IS NOT NULL
  AND c.customer_no IS NULL;
~~~

If the query returns rows, the database contains orphan references. Adding an FK immediately may fail or force premature data changes. Determine whether these are valid under legacy contracts, errors requiring cleanup, or references to external systems.

## 7. Preserving Nullability, Defaults, and SQL Types

Java mappings must be compatible with existing SQL types. Do not map every numeric column to `Long` or every timestamp to `LocalDateTime` without checking precision and semantics.

| Existing SQL | Common Java Type Candidates | What to Verify |
|---|---|---|
| `BIGINT` | `Long` | ID range and signedness by vendor |
| `INTEGER` | `Integer` | Range and nullability |
| `NUMERIC(p,s)` | `BigDecimal` | Precision/scale and rounding |
| `CHAR(n)`/`VARCHAR(n)` | `String` | Padding, length, collation |
| `DATE` | `LocalDate` | Date only |
| `TIMESTAMP` | `LocalDateTime` | Carries no time zone |
| `TIMESTAMP WITH TIME ZONE` | `Instant`/`OffsetDateTime` per driver | Time-zone normalization and JDBC mapping |
| `UUID`/native `uniqueidentifier` | `UUID` or converter | Driver/dialect support |
| `JSON`/`JSONB` | `String`/`JsonNode`/custom type | TypeHandler/converter and native JDBC type |
| `BINARY`/`BLOB` | `byte[]` or stream | Size and memory behavior |

### NULL Is Different from Default

Having a `DEFAULT` on a column does not mean passing SQL `NULL` applies the default. In SQL, defaults typically apply when a column is omitted from `INSERT` or the `DEFAULT` keyword is used; if an `INSERT` explicitly passes `NULL`, the column may store `NULL` or fail a `NOT NULL` constraint.

Spring Data JDBC generates `INSERT`s based on mappings and object values. If the database relies on important defaults or triggers, inspect the generated SQL and generated-value behavior. Never assume a null Java property automatically triggers a database default.

### Columns Populated by Triggers or Database Defaults

Legacy schemas may populate `created_on`, `modified_on`, `status_code`, or `audit_user` using defaults or triggers. If the framework also writes those columns, it may conflict with or overwrite database-generated values.

Establish a clear single source of truth:

- The application supplies the value.
- A database default/trigger supplies the value.
- Another ETL process supplies the value.

Only one mechanism should own a column's value at a time. Use read-only mappings or generated-value mechanisms supported by your Spring Data Relational version where appropriate; inspect `INSERT`/`UPDATE` SQL and re-read rows to confirm. When uncertain, omit the column from the write model and read it via a separate query until behavior is verified.

## 8. Converters for Legacy Data Types

Schemas may store status codes, char flags, numeric enums, or legacy date/time formats. Spring Data JDBC uses its own conversion infrastructure; never assume Hibernate converters/`AttributeConverter`s are used automatically.

Example legacy single-character status:

~~~java
public enum OrderStatus {
    OPEN("O"),
    PAID("P"),
    CANCELLED("C");

    private final String code;

    OrderStatus(String code) {
        this.code = code;
    }

    public String code() {
        return code;
    }

    public static OrderStatus fromCode(String code) {
        return Arrays.stream(values())
                .filter(status -> status.code.equals(code))
                .findFirst()
                .orElseThrow(() ->
                        new IllegalArgumentException("Unknown order status"));
    }
}
~~~

Writing converter:

~~~java
@WritingConverter
public class OrderStatusWritingConverter
        implements Converter<OrderStatus, String> {

    @Override
    public String convert(OrderStatus source) {
        return source.code();
    }
}
~~~

Reading converter:

~~~java
@ReadingConverter
public class OrderStatusReadingConverter
        implements Converter<String, OrderStatus> {

    @Override
    public OrderStatus convert(String source) {
        return OrderStatus.fromCode(source);
    }
}
~~~

Register both converters in `JdbcCustomConversions` according to your application's Spring Data JDBC configuration. Test unrecognized legacy values, `NULL`, whitespace, and letter casing. Never silently map unknown codes to a default valid status, as that can corrupt business logic.

If existing data needs conversion, write a migration/backfill with before-and-after counts; converters only change how the application reads and writes, not stored data.

## 9. Do Not Assume save() Updates Only a Few Columns

A key difference when adopting an existing schema is aggregate write behavior. Spring Data JDBC does not dirty-check individual fields like JPA. Repository `save` writes the aggregate per mapping and may execute multiple `INSERT`/`UPDATE`/`DELETE` statements for owned entities.

For aggregates with collections, the persistence strategy may delete and re-insert child rows when updating the root. This can affect:

- Child primary keys and generated values.
- Triggers firing on `DELETE`/`INSERT`.
- Audit history and CDC streams.
- External table FKs referencing child rows.
- Database-generated timestamps or `created_by` columns.
- Association tables shared with other systems.

Before enabling `save` on a legacy aggregate, enable SQL logging in staging and inspect every statement. Check whether child rows are updated in place or deleted and re-inserted under your framework version and mapping. If a child table is referenced by external systems by ID or carries critical triggers, verify this before enabling the write path.

Do not call `save` just to "sync objects" after a read. Call `save` only when the use case genuinely needs to persist aggregate mutations.

### Partial Updates Are Not Aggregate Saves

If you only need to change a single column in a large table with triggers or columns owned by other systems, an explicit `UPDATE` can be safer than loading and saving the whole aggregate. Example:

~~~java
@Modifying
@Query("""
    UPDATE legacy_order
    SET order_state = :status
    WHERE order_no = :id
    """)
int updateStatus(
        @Param("id") Long id,
        @Param("status") String status
);
~~~

This illustrates explicit DML; syntax and query annotation support must match your Spring Data JDBC version. Custom repositories with `JdbcTemplate` are another option.

With direct DML, the application takes responsibility for versioning, auditing, domain invariants, and cache invalidation. Do not expect `save` entity callbacks to fire for custom `UPDATE` statements.

## 10. Soft Deletes and Legacy Status Columns

Some systems never delete rows physically, using `deleted_flag`, `active`, `record_status`, or `deleted_at` instead.

Spring Data JDBC `repository.delete` normally represents persistence deletion of the aggregate and does not automatically interpret legacy soft-delete columns. Calling `delete` directly may physically delete the row per mapping.

If the system requires soft deletes:

- Use a domain method to change status and save the aggregate when appropriate.
- Or use a conditional custom `UPDATE`.
- Ensure all read queries filter properly on deleted/active state.
- Define uniqueness semantics: unique across all rows or only non-deleted rows.
- Check FKs and retention policies.
- Never call `repository.delete` when the business intent is only marking a row deleted.

Soft deletion is usually a business lifecycle concept, not merely a technical flag. Put the rules in services/domain objects and protect them with appropriate queries and constraints.

## 11. Inspect Existing Data Before Adding Constraints

Legacy databases may hold rows written before constraints existed or by old processes that skipped validation.

Before adding `NOT NULL`:

~~~sql
SELECT COUNT(*)
FROM legacy_order
WHERE order_state IS NULL;
~~~

Before adding a unique constraint:

~~~sql
SELECT external_order_code, COUNT(*)
FROM legacy_order
GROUP BY external_order_code
HAVING COUNT(*) > 1;
~~~

Before adding an FK:

~~~sql
SELECT line.order_no
FROM legacy_order_line line
LEFT JOIN legacy_order root
    ON root.order_no = line.order_no
WHERE root.order_no IS NULL;
~~~

If violating rows exist, never automatically delete or alter rows just to make a migration pass. Identify business owners, cleanup rules, backups, and handling for each category. Add constraints only after backfill and verification complete.

On large tables, creating indexes or constraints can lock tables or consume heavy resources. Use online/concurrent strategies suited to your database vendor and maintenance window.

## 12. Managing Migrations and Schema Baselines

Spring Data JDBC focuses on mapping/persistence, not production DDL synchronization. Use Flyway or Liquibase to manage schema versions.

If the database already existed before introducing Flyway, **baseline** migration history accurately to match the current schema state. A baseline only records the starting point in the tool's configuration; it does not prove the actual schema matches migration history and does not clean data.

Baseline procedure:

1. Dump the existing schema and store a verification copy.
2. Reconcile tables, columns, constraints, and indexes against the state represented by the baseline version.
3. Determine the baseline version and which migrations will run subsequently.
4. Test the baseline on a clone first.
5. Confirm Flyway/Liquibase does not re-run migrations that create already-existing tables.
6. Run subsequent migrations on the clone and compare schema/data.
7. Only after review, plan rollout for shared environments.

Do not blindly enable `baselineOnMigrate` across every database. Baseline settings must never mask connecting to the wrong schema or schema drift.

### Do Not Let Multiple Mechanisms Alter the Schema

Check whether any of the following are active:

- Flyway/Liquibase migrations.
- Spring Boot SQL initialization via `schema.sql`/`data.sql`.
- Hibernate DDL auto if JPA is still present in the application.
- Custom deployment initialization scripts.
- Triggers/procedures creating objects automatically.

Pick one primary schema management mechanism. Avoid letting Hibernate create/update and Flyway modify the same schema without clear rules. On existing production databases, never run unintended schema initialization on application startup.

## 13. Use Expand–Migrate–Contract for Necessary Changes

If a new mapping needs a column that does not yet exist, never deploy new code assuming the column exists before the schema is updated.

Use three phases:

~~~mermaid
flowchart TD
    A["Expand"] --> B["Add new columns/tables, keep old code working"]
    B --> C["Deploy compatible code"]
    C --> D["Backfill and verify data"]
    D --> E["Switch reads/writes to the new structure"]
    E --> F["Contract"]
    F --> G["Drop old columns/tables once no consumers remain"]
~~~

Example changing `customer_code` to `customer_id`:

1. Expand: add nullable `customer_id`, then indexes/FKs once data is clean.
2. Deploy: code can read both old/new columns or write consistently per clear rules.
3. Backfill: populate `customer_id` from `customer_code` in checkpointed batches.
4. Verify: compare row counts, NULLs, orphans, and mappings by business key.
5. Cutover: switch reads to `customer_id`.
6. Contract: drop `customer_code` only after all legacy consumers have stopped using it.

If dual-writing, enforce strict consistency rules and partial-failure handling. Never write to two columns indefinitely without a single source of truth.

## 14. Testing Mappings on a Database Clone

`@DataJdbcTest` works well for testing repositories and mappings. However, embedded databases may not reproduce production dialects, identity behavior, triggers, types, and constraints.

For legacy schemas, use Testcontainers running the same engine and major version whenever possible. Load schemas from migrations or sanitized schema dumps.

Key tests:

- Load existing rows without mutating stored data.
- Map table/column names and types accurately.
- Read NULLs and boundary values.
- Verify generated IDs work with existing identities/sequences.
- Confirm inserts do not bypass or overwrite defaults/triggers unintentionally.
- Confirm root updates do not clear columns owned by other systems.
- Confirm aggregate updates do not trigger unexpected child deletes/reinserts.
- Verify FK, unique, and check constraints remain respected.
- Confirm soft deletes do not become physical deletes.
- Confirm optimistic locking works if a version column exists.
- Confirm read-only queries emit no DML.
- Confirm transaction rollbacks leave no partial data.

### Read-Without-Write Test

~~~java
@DataJdbcTest
class LegacyOrderMappingTest {

    @Autowired PurchaseOrderRepository repository;
    @Autowired JdbcTemplate jdbcTemplate;

    @Test
    void readsExistingRowWithoutChangingStoredValues() {
        jdbcTemplate.update("""
                INSERT INTO legacy_order(
                    order_no, customer_no, order_state, created_on
                )
                VALUES (?, ?, ?, ?)
                """,
                1001L,
                42L,
                "P",
                Timestamp.valueOf("2026-01-10 09:00:00")
        );

        PurchaseOrder order = repository.findById(1001L).orElseThrow();

        assertThat(order.getId()).isEqualTo(1001L);
        assertThat(order.getCustomerId()).isEqualTo(42L);
        assertThat(order.getStatus()).isEqualTo(OrderStatus.PAID);

        String storedState = jdbcTemplate.queryForObject(
                "SELECT order_state FROM legacy_order WHERE order_no = ?",
                String.class,
                1001L
        );

        assertThat(storedState).isEqualTo("P");
    }
}
~~~

This is an illustrative example; repositories, entities, converters, and schemas should be configured for your application. Test slices typically run inside transactions and roll back on completion.

### Controlled Update Test

~~~java
@Test
void updatesOnlyTheIntendedBusinessValue() {
    PurchaseOrder order = repository.findById(1001L).orElseThrow();

    order.changeStatus(OrderStatus.CANCELLED);
    repository.save(order);

    Map<String, Object> row = jdbcTemplate.queryForMap("""
            SELECT order_state, customer_no
            FROM legacy_order
            WHERE order_no = ?
            """, 1001L);

    assertThat(row.get("order_state")).isEqualTo("C");
    assertThat(((Number) row.get("customer_no")).longValue()).isEqualTo(42L);
}
~~~

If the table has triggers, audit columns, or child collections, extend tests to confirm those columns and rows preserve expected behavior. Do not assert only the modified field; assert critical data that must remain unchanged.

## 15. Comparing Data Before and After Migration

After every migration or write-enabling rollout, compare baseline and results:

| Check | Question |
|---|---|
| Row count | Did row counts change unexpectedly? |
| Primary keys | Were any IDs lost, duplicated, or altered? |
| Business keys | Were unexpected duplicates or normalizations introduced? |
| NULL count | Did any required column become NULL? |
| FK/orphans | Are there invalid references? |
| Aggregate totals | Did total quantities/amounts remain intact? |
| Timestamps | Did time zones or precision shift? |
| Defaults/triggers | Do audit/default-generated values still work? |
| Sequences | Could the next generated ID collide? |
| Consumer compatibility | Can legacy apps and reports still read the data? |

For large datasets, full-table checksums can be expensive and hash functions vary across databases. You can compare by partition or key range, counts and sums of critical business columns, followed by detailed row sampling.

Every discrepancy must be classified: expected change, backfill, valid trigger, or unintended error. Never look only at total row counts, as two different datasets can share identical row counts.

## 16. Running JPA and Spring Data JDBC Side by Side During Transition

An application may temporarily keep both JPA and Spring Data JDBC in the same runtime. Exercise particular care when doing so:

- Both may target the same database with different objects, caches, and lifecycles.
- JPA's persistence context may retain stale entities after JDBC writes.
- JDBC does not know which entities are managed in `EntityManager`.
- JPA dirty checking may flush a stale object and overwrite fresh JDBC changes.
- JPA cascades and JDBC aggregate saves may affect the same child tables with different semantics.

If coexistence is unavoidable:

1. Assign one write owner per aggregate/table for each phase.
2. Never let JPA and JDBC arbitrarily write to the same aggregate simultaneously.
3. After JDBC writes, `EntityManager` may need `refresh`/`clear` before reading via JPA.
4. After JPA writes, Spring Data JDBC repositories read fresh data per transaction visibility; avoid stale objects in application caches.
5. Share a transaction only when both genuinely use the same `DataSource`/resource and compatible transaction manager.
6. Write integration tests for bidirectional read/write ordering and rollbacks.

Avoid long-lived dual-writes from both frameworks against the same aggregate. Migrate one use case at a time and establish when the old write path retires.

## 17. Protecting External Database Consumers

Existing databases often have multiple consumers: other APIs, ETL jobs, BI tools, data warehouses, batch jobs, stored procedures, or operational scripts.

Before modifying the schema:

- Identify consumers relying on table/column names.
- Determine whether consumers read directly or through views.
- Check whether triggers emit events or write audit logs.
- Identify FKs from other schemas referencing the tables being changed.
- Check CDC/replication publications if present.
- Inspect stored procedures/functions referencing column names.
- Communicate and coordinate cutover around compatibility windows.

Never drop a column simply because the new application no longer maps it. External systems may still depend on it. Use expand–contract and observe access before contracting.

## 18. Common Pitfalls

| Symptom | Possible Cause | Resolution |
|---|---|---|
| Repository cannot find table | Wrong `@Table`/naming strategy or default schema | Map names explicitly and verify current schema |
| Column not found | `@Column`/`idColumn`/`keyColumn` mismatch | Reconcile database metadata with entity mapping |
| Insert uses wrong ID | Wrong dialect/identity/sequence or assigned ID newness | Check generated-key path and `isNew` |
| Insert duplicates primary key | Sequence below `MAX(ID)` or existing object treated as new | Inspect sequence and newness detection |
| Default value not applied | SQL `INSERT` sends `NULL` instead of omitting column | Check SQL and generated/default-value mapping |
| Trigger runs twice | Both application and database own the side effect | Choose a single source for audit/events |
| Children deleted and re-inserted | Aggregate save handles owned collection per persistence strategy | Inspect SQL and evaluate FKs/triggers/child identity |
| List reads in wrong order | Legacy table has no position/key column | Store order column or use `ORDER BY`/read model |
| Adding FK fails | Legacy data contains orphan references | Quantify, review/clean data, then add constraint |
| Soft delete turns into physical delete | Calling `repository.delete` on a status-flag schema | Update status via domain rules |
| Hibernate and JDBC read differently | Stale JPA persistence context/cache | Refresh/clear and restrict write ownership |
| Migration re-runs `CREATE TABLE` | Wrong baseline/version history | Check schema history and test baseline on clone |
| Production differs from staging | Schema drift, triggers, permissions, or version mismatch | Dump metadata and verify parity before deploying |

## 19. Safe Schema Adoption Procedure

1. **Lock scope:** determine which database, schema, tables, and use cases migrate first.
2. **Backup and test restore:** verify a reliable path back to original data.
3. **Inventory schema:** capture DDL, metadata, constraints, indexes, triggers, sequences, and migration history.
4. **Baseline data:** record row counts, NULLs/duplicates/orphans, and key business totals.
5. **Design aggregates:** distinguish roots, owned children, embedded values, and references.
6. **Write explicit mappings:** `@Table`, `@Column`, `@MappedCollection`, `@Embedded`, `@Id`, and converters.
7. **Verify IDs/defaults:** generated keys, assigned IDs, triggers, defaults, and sequences.
8. **Run read-only integration tests:** confirm accurate reads with zero DML.
9. **Run write tests on clone:** controlled insert/update/delete checking children/triggers/FKs.
10. **Write needed migrations:** baseline accurately; use expand–migrate–contract for breaking changes.
11. **Compare before/after:** row counts, IDs, totals, references, timestamps, and audit fields.
12. **Shadow read/canary:** switch one set of use cases or tenants first, watching queries and errors.
13. **Open write paths gradually:** only after rollbacks, concurrency, and data verification are proven.
14. **Retire legacy writers:** once all consumers have migrated and stale caches/dual-writes are gone.

### Quick Decision Table

| Situation | Safe Action |
|---|---|
| Schema already matches domain | Map directly; no migration needed just to switch frameworks |
| Legacy table/column names differ from convention | Use explicit `@Table`/`@Column` |
| Database-generated ID | Verify identity/sequence and generated-key behavior |
| Externally assigned ID | Design newness detection and test assigned IDs |
| Ordered collection | Map `keyColumn` to existing position column or add a reviewed migration |
| Triggers/defaults present | Establish write ownership and verify SQL NULL/default behavior |
| Soft delete used | Update status; do not invoke physical delete |
| Orphan FKs in legacy data | Classify and resolve under review before adding constraints |
| Read-only needed | Start with read-only permissions and queries/projections |
| Schema change needed | Versioned migration, backup, staging, verification, phased rollout |
| JPA and JDBC share runtime | One write owner per aggregate; manage persistence context/caches |
| Guarantee zero data loss | Baseline comparison, rollback tests, and restore rehearsal |

**Key takeaway:** adopt an existing schema by making mappings match the existing database first. Preserve IDs, column names, data types, defaults, triggers, FKs, and dependent consumers. Alter the schema only through versioned migrations after measuring baselines, testing on a clone, inspecting real SQL, and comparing data. Start read-only, open write paths incrementally, and contract legacy structures only once all consumers have moved.

## Official References

- [Spring Data Relational — Object Mapping Fundamentals](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html): `@Table`, `@Column`, `@Id`, `@MappedCollection`, `@Embedded`, `AggregateReference`, `NamingStrategy`, and converters.
- [Spring Data Relational — Persisting Entities](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html): aggregate inserts/updates, generated IDs, newness detection, and persistence behavior.
- [Spring Data Relational — Transactionality](https://docs.spring.io/spring-data/relational/reference/jdbc/transactions.html): transaction boundaries for repositories and the service layer.
- [Spring Boot — Database Initialization](https://docs.spring.io/spring-boot/how-to/data-initialization.html): SQL initialization, Flyway, and Liquibase integration.
- [Flyway — Baselines](https://documentation.red-gate.com/flyway/flyway-concepts/baselines): recording an existing schema/database as the starting point for migration history.
- [Flyway — Versioned Migrations](https://documentation.red-gate.com/flyway/flyway-concepts/migrations/versioned-migrations): managing schema changes via versioned migrations.
- [PostgreSQL — Constraints](https://www.postgresql.org/docs/current/ddl-constraints.html): primary keys, foreign keys, unique, check, and nullability.
- [PostgreSQL — Identity Columns](https://www.postgresql.org/docs/current/ddl-identity-columns.html): identity generation and sequence behavior.
- [Testcontainers — Database Modules](https://java.testcontainers.org/modules/databases/): testing against real database engines.
