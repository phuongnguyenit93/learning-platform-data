# Testing Mapping, Embedded Objects, Collections, Converters, and IDs

Spring Data JDBC maps Java objects to database rows based on metadata such as `@Table`, `@Column`, `@Id`, `@Version`, `@Embedded`, and `@MappedCollection`. Custom converters further govern how a domain type is transformed into a JDBC type when writing and reconstructed when reading.

These rules must be tested against a real database or compatible test database. A unit test that merely constructs Java objects does not prove that column names, foreign keys, collection ordering, converters, or generated IDs work properly. This lesson shows how to organize integration tests for key mapping features, using `@DataJdbcTest`, `JdbcTemplate`, and Testcontainers when verifying against the exact production DBMS/driver.

## 1. Distinguishing Unit Tests from Mapping Integration Tests

Each test layer answers a different question:

| Test Type | What Does It Verify? | Example |
|---|---|---|
| Domain unit test | Business logic independent of persistence | Calculating totals, validating positive quantities |
| Converter unit test | Java value conversion rules | Money to BigDecimal and vice versa |
| Repository integration test | Does Spring Data JDBC generate SQL and map data properly? | Saving then loading an aggregate |
| Database integration test | Are the driver, dialect, DDL, and data types compatible? | Generated keys, UUID, timestamp, embedded |
| Transaction integration test | Do multiple persistence operations commit/roll back properly? | Root and children rolling back together |

Mapping tests should use a real Spring context so Spring Data JDBC registers mapping metadata, converters, repository proxies, and the DataSource. Mocking repositories bypasses the mapping layer entirely.

## 2. Using @DataJdbcTest for the Repository Slice

Spring Boot provides `@DataJdbcTest` to create a test slice for Spring Data JDBC. This annotation typically configures repositories, `JdbcTemplate`, and required JDBC test infrastructure, while by default running each test inside a transaction rolled back after each test.

Test skeleton example:

~~~java
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.data.jdbc.DataJdbcTest;
import org.springframework.jdbc.core.JdbcTemplate;

@DataJdbcTest
class PurchaseOrderMappingTest {

    @Autowired
    PurchaseOrderRepository repository;

    @Autowired
    JdbcTemplate jdbcTemplate;

    @Test
    void contextLoads() {
        // Repository and mapping tests go here.
    }
}
~~~

`@DataJdbcTest` can replace the DataSource with an embedded database if H2, HSQLDB, or Derby is on the classpath. This runs quickly and suits basic mapping checks. If production uses PostgreSQL, MySQL, SQL Server, or Oracle, add integration tests with that exact DBMS/driver because dialects, generated keys, and data types may differ.

Test schemas can be created using `schema.sql`, `@Sql`, or the project's migrations. Use the same table structures and constraints as real migrations so tests remain meaningful.

## 3. Aggregate Model Used in Examples

Suppose an order has an embedded shipping address and a collection of order lines:

~~~java
import java.math.BigDecimal;
import java.util.List;
import org.springframework.data.annotation.Id;
import org.springframework.data.annotation.Version;
import org.springframework.data.relational.core.mapping.Column;
import org.springframework.data.relational.core.mapping.Embedded;
import org.springframework.data.relational.core.mapping.MappedCollection;
import org.springframework.data.relational.core.mapping.Table;

@Table("purchase_orders")
public record PurchaseOrder(
        @Id Long id,
        @Version Long version,
        @Column("order_number") String orderNumber,
        @Embedded(
                prefix = "shipping_",
                onEmpty = Embedded.OnEmpty.USE_NULL
        )
        Address shippingAddress,
        @MappedCollection(
                idColumn = "order_id",
                keyColumn = "line_no"
        )
        List<OrderLine> lines,
        Money total
) {}

public record Address(
        String street,
        String city
) {}

@Table("order_lines")
public record OrderLine(
        String sku,
        int quantity,
        BigDecimal unitPrice
) {}

public record Money(BigDecimal amount) {}
~~~

In this example:

- `PurchaseOrder` is the aggregate root.
- `id` is the database-generated primary key.
- `version` is used for optimistic locking.
- `orderNumber` maps to the `order_number` column.
- `Address` is embedded into `purchase_orders` with the `shipping_` prefix.
- `OrderLine` is stored in `order_lines`, referencing the root via `order_id`.
- `line_no` stores the element position within the `List`.
- `Money` is a value object requiring custom converters to store into a `DECIMAL` column.

If your project uses a Spring Data Relational version with different annotation APIs, use the exact packages and attributes of your dependency. This example illustrates common mapping configurations.

## 4. Creating a Test Schema Matching the Mapping

A simple schema for the aggregate above:

~~~sql
CREATE TABLE purchase_orders (
    id BIGINT GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    version BIGINT NOT NULL,
    order_number VARCHAR(40) NOT NULL UNIQUE,
    shipping_street VARCHAR(150),
    shipping_city VARCHAR(80),
    total DECIMAL(12, 2) NOT NULL
);

CREATE TABLE order_lines (
    order_id BIGINT NOT NULL,
    line_no INTEGER NOT NULL,
    sku VARCHAR(40) NOT NULL,
    quantity INTEGER NOT NULL,
    unit_price DECIMAL(12, 2) NOT NULL,
    PRIMARY KEY (order_id, line_no),
    CONSTRAINT fk_order_lines_order
        FOREIGN KEY (order_id) REFERENCES purchase_orders(id)
);
~~~

You can save this script at `src/test/resources/schema.sql` for Spring Boot to initialize the test schema, or use `@Sql("/schema.sql")` on the test class/method.

The schema must accurately reflect:

- Table and column names after mapping rules apply.
- Column types compatible with Java/JDBC types.
- Nullability.
- Primary keys and foreign keys.
- Required unique constraints and indexes.
- Generated ID strategy.
- Version column and prefixed embedded columns.

Do not create minimal tables just to make tests pass if production migrations add important constraints. Those constraints are often where mapping mistakes and invalid data surface.

## 5. Testing @Table and @Column

The goal is to confirm Java properties map to the right physical tables and columns.

With `PurchaseOrder`, `orderNumber` must be saved to `order_number`. A test can save the aggregate and then query directly using `JdbcTemplate`:

~~~java
@Test
void mapsTableAndColumnNames() {
    PurchaseOrder input = new PurchaseOrder(
            null,
            null,
            "PO-MAP-001",
            new Address("12 Nguyen Hue", "Ho Chi Minh City"),
            List.of(),
            new Money(new BigDecimal("250.00"))
    );

    PurchaseOrder saved = repository.save(input);

    assertNotNull(saved.id());

    String storedNumber = jdbcTemplate.queryForObject(
            "SELECT order_number FROM purchase_orders WHERE id = ?",
            String.class,
            saved.id()
    );

    assertEquals("PO-MAP-001", storedNumber);
}
~~~

This test verifies both important directions: the repository writes to the right column and direct SQL finds the data in the expected location.

Add another test that reads through the repository after inserting via SQL fixture. That catches cases where both writing and reading share a wrong mapping assumption yet accidentally pass on an object round-trip.

## 6. Testing @Embedded and Column Prefixes

`@Embedded` stores a value object's properties as columns on the same row as the enclosing entity. With prefix `shipping_`, `Address.street` and `Address.city` map to `shipping_street` and `shipping_city`.

Write and read test:

~~~java
@Test
void mapsEmbeddedAddressWithPrefix() {
    PurchaseOrder input = new PurchaseOrder(
            null,
            null,
            "PO-EMBED-001",
            new Address("12 Nguyen Hue", "Ho Chi Minh City"),
            List.of(),
            new Money(new BigDecimal("100.00"))
    );

    PurchaseOrder saved = repository.save(input);
    PurchaseOrder loaded = repository.findById(saved.id()).orElseThrow();

    assertEquals("12 Nguyen Hue", loaded.shippingAddress().street());
    assertEquals("Ho Chi Minh City", loaded.shippingAddress().city());

    assertEquals(
            "12 Nguyen Hue",
            jdbcTemplate.queryForObject(
                    "SELECT shipping_street FROM purchase_orders WHERE id = ?",
                    String.class,
                    saved.id()
            )
    );
}
~~~

Testing through the repository verifies object mapping; querying directly confirms physical column names.

### Testing Empty or Null Embedded Objects

When all columns of an embedded object are null, Spring Data JDBC uses the `onEmpty` policy to decide whether reading produces `null` or an object whose properties are null.

In the example above:

~~~java
@Embedded(
        prefix = "shipping_",
        onEmpty = Embedded.OnEmpty.USE_NULL
)
Address shippingAddress
~~~

With `USE_NULL`, tests should save an aggregate with a `null` `shippingAddress`, reload it, and verify the property is `null`. If the domain expects an empty `Address`, configure `USE_EMPTY` and write matching assertions.

What needs testing is the domain's nullability contract: does an unspecified address mean `null`, or an existing value object with unset fields? Choose explicit semantics and test both on insert and when reading fixture rows where all embedded columns are `NULL`.

Do not only assert on the object passed into save. Always reload from the database because `onEmpty` rules only manifest when mapping a `ResultSet` back into an object.

## 7. Testing @MappedCollection and Foreign Keys

`@MappedCollection` maps child entities into a separate table. `idColumn` specifies the column linking children to the root; `keyColumn` stores the collection's key or index.

With `List<OrderLine>`, `line_no` preserves element order. Tests should confirm:

- Child rows are inserted when saving the root.
- Every child has the correct `order_id`.
- `line_no` is stored properly and reconstructs `List` order.
- On reading the root, the collection has the exact count and values.
- The foreign key points to the root.
- After updating the collection and saving, database child rows reflect the new collection.

Example:

~~~java
@Test
void persistsAndReloadsMappedCollection() {
    List<OrderLine> lines = List.of(
            new OrderLine("SKU-A", 2, new BigDecimal("10.00")),
            new OrderLine("SKU-B", 1, new BigDecimal("25.00"))
    );

    PurchaseOrder input = new PurchaseOrder(
            null,
            null,
            "PO-LINES-001",
            new Address("1 Le Loi", "Ho Chi Minh City"),
            lines,
            new Money(new BigDecimal("45.00"))
    );

    PurchaseOrder saved = repository.save(input);
    PurchaseOrder loaded = repository.findById(saved.id()).orElseThrow();

    assertEquals(2, loaded.lines().size());
    assertEquals("SKU-A", loaded.lines().get(0).sku());
    assertEquals("SKU-B", loaded.lines().get(1).sku());

    Integer childCount = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM order_lines WHERE order_id = ?",
            Integer.class,
            saved.id()
    );

    assertEquals(2, childCount);
}
~~~

For ordered collections, assert ordering after reload rather than just comparing sizes. If using a `Set`, test child `equals`/`hashCode` semantics and do not assume stable iteration order.

### Verifying Foreign Keys Independently

You can query child rows directly:

~~~java
List<Long> parentIds = jdbcTemplate.query(
        "SELECT order_id FROM order_lines WHERE order_id = ?",
        (rs, rowNum) -> rs.getLong("order_id"),
        saved.id()
);

assertEquals(List.of(saved.id(), saved.id()), parentIds);
~~~

Besides the assertion above, foreign key constraints in the schema must be active. If the test schema lacks FKs, tests could pass even if the application writes child rows with nonexistent parent IDs.

## 8. Testing Collection Updates

Spring Data JDBC does not track child row snapshots to generate partial diffs. When saving an existing aggregate, referenced entities may be deleted and reinserted according to the current collection.

Therefore, tests should focus on the final state:

~~~java
@Test
void savesCurrentCollectionState() {
    PurchaseOrder created = repository.save(newOrderWithTwoLines());

    PurchaseOrder changed = new PurchaseOrder(
            created.id(),
            created.version(),
            created.orderNumber(),
            created.shippingAddress(),
            List.of(new OrderLine(
                    "SKU-C",
                    3,
                    new BigDecimal("8.00")
            )),
            created.total()
    );

    PurchaseOrder saved = repository.save(changed);
    PurchaseOrder loaded = repository.findById(saved.id()).orElseThrow();

    assertEquals(1, loaded.lines().size());
    assertEquals("SKU-C", loaded.lines().get(0).sku());

    Integer count = jdbcTemplate.queryForObject(
            "SELECT COUNT(*) FROM order_lines WHERE order_id = ?",
            Integer.class,
            saved.id()
    );

    assertEquals(1, count);
}
~~~

This test confirms that the database collection after saving matches the new collection. If the application has other tables directly referencing child rows, add tests for those foreign keys and delete/reinsert behavior.

Do not write tests assuming only changed children receive `UPDATE` statements. The goal is verifying the persistence contract and final data, not enforcing an internal SQL strategy the framework does not promise.

## 9. Testing Bidirectional Custom Converters

Spring Data JDBC custom converters typically come in two directions:

- `WritingConverter`: converts a domain type into a database/JDBC type.
- `ReadingConverter`: converts a database/JDBC type into a domain type.

For example, `Money` stored as `DECIMAL`:

~~~java
public record Money(BigDecimal amount) {}
~~~

Writing converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.WritingConverter;

@WritingConverter
public class MoneyWritingConverter
        implements Converter<Money, BigDecimal> {

    @Override
    public BigDecimal convert(Money source) {
        return source.amount();
    }
}
~~~

Reading converter:

~~~java
import org.springframework.core.convert.converter.Converter;
import org.springframework.data.convert.ReadingConverter;

@ReadingConverter
public class MoneyReadingConverter
        implements Converter<BigDecimal, Money> {

    @Override
    public Money convert(BigDecimal source) {
        return new Money(source);
    }
}
~~~

Register converters in Spring Data JDBC configuration:

~~~java
import java.util.List;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.jdbc.repository.config.AbstractJdbcConfiguration;

@Configuration
public class JdbcConfiguration extends AbstractJdbcConfiguration {

    @Override
    protected List<?> userConverters() {
        return List.of(
                new MoneyWritingConverter(),
                new MoneyReadingConverter()
        );
    }
}
~~~

Configuration signatures and imports must match your project's Spring Data Relational version. In a Spring Boot test slice, use `@Import(JdbcConfiguration.class)` to include the converter configuration in the test context.

## 10. Testing Converters Standalone and Through Repositories

Unit tests verify conversion rules:

~~~java
@Test
void writesMoneyAsBigDecimal() {
    MoneyWritingConverter converter = new MoneyWritingConverter();

    assertEquals(
            new BigDecimal("125.50"),
            converter.convert(new Money(new BigDecimal("125.50")))
    );
}

@Test
void readsBigDecimalAsMoney() {
    MoneyReadingConverter converter = new MoneyReadingConverter();

    assertEquals(
            new Money(new BigDecimal("125.50")),
            converter.convert(new BigDecimal("125.50"))
    );
}
~~~

These unit tests are useful, yet do not prove Spring Data JDBC registered the converters. A repository integration test is required:

~~~java
@Test
void roundTripsMoneyThroughJdbcMapping() {
    PurchaseOrder input = new PurchaseOrder(
            null,
            null,
            "PO-MONEY-001",
            new Address("1 Le Loi", "Ho Chi Minh City"),
            List.of(),
            new Money(new BigDecimal("125.50"))
    );

    PurchaseOrder saved = repository.save(input);

    BigDecimal storedAmount = jdbcTemplate.queryForObject(
            "SELECT total FROM purchase_orders WHERE id = ?",
            BigDecimal.class,
            saved.id()
    );

    PurchaseOrder loaded = repository.findById(saved.id()).orElseThrow();

    assertEquals(new BigDecimal("125.50"), storedAmount);
    assertEquals(new Money(new BigDecimal("125.50")), loaded.total());
}
~~~

This test verifies the writing converter, physical database value, and reading converter together. For money, use `BigDecimal` and compare with `equals` when scale is part of the contract; if the domain treats `125.5` and `125.50` as equivalent, define explicit normalization inside `Money`.

## 11. Testing Converters with Nulls and Boundary Data

Converters should be tested for:

- Normal valid values.
- Zero values.
- Negative numbers if allowed by the domain.
- Maximum precision and scale.
- Null values if properties/schemas allow nulls.
- Legacy data or obsolete codes.

Not every converter is invoked with `null`; Spring's `ConversionService` and mapping layer may handle nulls before invoking converters. Verify the exact contract and test behavior through the repository instead of assuming converters always receive `null`.

If a reading converter encounters an unrecognized code, fail loudly rather than silently returning a default value that could corrupt domain state.

## 12. Testing Generated IDs

With identity columns, a new entity normally has a `null` ID. Spring Data JDBC inserts the row and retrieves the generated key according to dialect/driver capabilities.

Test:

~~~java
@Test
void returnsGeneratedIdAfterInsert() {
    PurchaseOrder input = newOrderWithOneLine();

    assertNull(input.id());

    PurchaseOrder saved = repository.save(input);

    assertNotNull(saved.id());

    PurchaseOrder loaded = repository.findById(saved.id()).orElseThrow();
    assertEquals(saved.orderNumber(), loaded.orderNumber());
}
~~~

With immutable records, use the instance returned from `save`. Do not assume the input object is mutated to receive the ID.

You can verify the generated key was saved on the root and child rows use the right parent ID:

~~~java
Long childParentId = jdbcTemplate.queryForObject(
        "SELECT order_id FROM order_lines WHERE order_id = ?",
        Long.class,
        saved.id()
);

assertEquals(saved.id(), childParentId);
~~~

Generated ID behavior depends on the database and driver. Passing on H2 does not prove PostgreSQL or SQL Server behaves identically; add tests on the production engine if generated-key behavior is critical to your system.

## 13. Testing Application-Assigned IDs

Not all IDs are database-generated. The application may generate a `UUID` before inserting.

Spring Data JDBC needs to know whether that entity is new or already exists. If the ID is already non-null, the default newness strategy may treat the entity as existing unless a version property or `Persistable` signals otherwise.

A common approach is using `@Version` with `null` for new entities:

~~~java
@Table("external_customers")
public record ExternalCustomer(
        @Id UUID id,
        @Version Long version,
        String name
) {}
~~~

The application generates the `UUID` and leaves `version` initially `null`. Spring Data JDBC can use `version` to determine newness per the `@Version` entity strategy. After insert, `version` is initialized.

Tests should confirm:

- The application-assigned `UUID` is preserved.
- `INSERT` is executed instead of `UPDATE`.
- The row exists in the database.
- `version` is initialized per framework behavior.
- Subsequent `save` executes an `UPDATE` and changes `version`.

If an entity has no `@Version` and uses pre-assigned IDs, consider implementing `Persistable` and defining `isNew()` explicitly. Test the lifecycle transition from new to persisted so a saved object does not keep getting treated as new.

## 14. Testing Updates and @Version

If an aggregate root uses `@Version`, tests should verify `version` changes after updates and stale versions are detected.

Example:

~~~java
@Test
void incrementsVersionWhenUpdatingAggregate() {
    PurchaseOrder created = repository.save(newOrderWithOneLine());

    PurchaseOrder changed = new PurchaseOrder(
            created.id(),
            created.version(),
            created.orderNumber(),
            created.shippingAddress(),
            created.lines(),
            created.total()
    );

    PurchaseOrder updated = repository.save(changed);

    assertEquals(created.id(), updated.id());
    assertNotEquals(created.version(), updated.version());
}
~~~

To test stale writes, keep two reads at the same version, save the first, then try saving the second. Spring Data JDBC must detect the mismatched version and report an optimistic locking failure according to your version's contract.

Do not reuse an old entity version for subsequent collection update tests after saving another instance. Always use the latest returned object so tests do not accidentally test stale state instead of mapping.

## 15. Testing Directly Inserted Data Read Through a Repository

A round-trip of `save` followed by `findById` can mask bugs if both writing and reading share a wrong assumption. Adding tests that seed data directly verifies the read path independently.

Example:

~~~java
@Test
void readsExistingDatabaseRowIntoMappedAggregate() {
    jdbcTemplate.update("""
        INSERT INTO purchase_orders(
            id, version, order_number,
            shipping_street, shipping_city, total
        )
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        9001L,
        0L,
        "PO-FIXTURE-001",
        "10 Dong Khoi",
        "Ho Chi Minh City",
        new BigDecimal("88.00")
    );

    jdbcTemplate.update("""
        INSERT INTO order_lines(
            order_id, line_no, sku, quantity, unit_price
        )
        VALUES (?, ?, ?, ?, ?)
        """,
        9001L,
        0,
        "SKU-FIXTURE",
        2,
        new BigDecimal("44.00")
    );

    PurchaseOrder loaded = repository.findById(9001L).orElseThrow();

    assertEquals("PO-FIXTURE-001", loaded.orderNumber());
    assertEquals("10 Dong Khoi", loaded.shippingAddress().street());
    assertEquals(new Money(new BigDecimal("88.00")), loaded.total());
    assertEquals("SKU-FIXTURE", loaded.lines().get(0).sku());
}
~~~

Fixtures must use ID/version types and identity syntax compatible with the DBMS. With identity columns, inserting explicit IDs may require special syntax or permissions; if not portable, use a fixture builder or sequence strategy suited to the test database.

Direct-seeding tests are especially valuable when integrating with legacy schemas or data written by other systems.

## 16. Testing Mapping Against the Project's Real Schema

If the application uses Flyway or Liquibase, run migrations in integration tests to build the schema. This catches mismatches between:

- Entity annotations.
- Migration DDL.
- Indexes and foreign keys.
- Data types.
- Default values.
- Constraints and generated ID strategies.

Do not maintain a separate test `schema.sql` alongside divergent production migrations over the long term. The two schema sources can drift. If using `schema.sql` for fast tests, maintain at least one test suite that runs real migrations.

With Testcontainers, tests can start a database engine close to production and use the real JDBC driver. Example PostgreSQL container configuration:

~~~java
@Testcontainers
@DataJdbcTest
@AutoConfigureTestDatabase(
        replace = AutoConfigureTestDatabase.Replace.NONE
)
@Import(JdbcConfiguration.class)
class PurchaseOrderPostgresMappingTest {

    @Container
    static PostgreSQLContainer<?> postgres =
            new PostgreSQLContainer<>("postgres:16-alpine");

    @DynamicPropertySource
    static void databaseProperties(DynamicPropertyRegistry registry) {
        registry.add("spring.datasource.url", postgres::getJdbcUrl);
        registry.add("spring.datasource.username", postgres::getUsername);
        registry.add("spring.datasource.password", postgres::getPassword);
    }

    // Repository mapping tests.
}
~~~

Add the Testcontainers PostgreSQL module, JUnit integration, and PostgreSQL JDBC driver to test dependencies. If using a Spring Boot version with service connection support, you can configure it via that mechanism; the example above uses `DynamicPropertySource` for illustration.

## 17. Transaction Testing and Cleanup

`@DataJdbcTest` normally runs each test inside a transaction and rolls back afterward. This prevents test data from leaking between tests.

Notes:

- Do not use `@Commit` without reason.
- If a test calls code running in an independent transaction such as `REQUIRES_NEW`, rolling back the outer test transaction does not undo data committed in the inner transaction.
- If a test needs to verify post-commit behavior, design explicit test transactions and clean up data appropriately.
- With Testcontainers, containers are often reused across a class/suite; schemas and sequences must be reset or tests must use unique IDs/fixtures.
- Do not rely on test execution order.

When testing transaction rollback of root and children, trigger a failure after some SQL has executed and read state back from another transaction or after the transaction ends. Checking in-memory objects alone does not prove the database rolled back.

## 18. Testing Nullability and Default Values

Mappings must match schema nullability.

For example:

- New IDs can be `null` before insert if the database generates IDs.
- `version` can be `null` before insert to denote a new entity.
- Embedded columns can be nullable if the embedded object is optional.
- An empty collection normally means zero child rows.
- `Money`/`total` can be `NOT NULL` if business rules require it.
- Java properties use wrapper/reference types if the database permits `NULL`.

Tests should cover:

1. Null embedded object.
2. Embedded object with partial null properties.
3. Empty collection.
4. Single-element collection.
5. Nullable converter values.
6. Missing `NOT NULL` column value rejected by the database.
7. Database-supplied default values if mapping relies on them.

Do not substitute SQL `NULL` with `0`, `false`, or an empty string if the domain needs to distinguish those states.

## 19. Testing Collection Order and keyColumn

With a `List` mapped via `keyColumn`, element positions can be stored in the child table. Tests should save a list with a distinctive order, reload it, and assert the order.

~~~java
List<OrderLine> expected = List.of(
        new OrderLine("SKU-Z", 1, new BigDecimal("1.00")),
        new OrderLine("SKU-A", 2, new BigDecimal("2.00")),
        new OrderLine("SKU-M", 3, new BigDecimal("3.00"))
);

PurchaseOrder saved = repository.save(orderWithLines(expected));
PurchaseOrder loaded = repository.findById(saved.id()).orElseThrow();

assertEquals(expected, loaded.lines());
~~~

If `keyColumn` is omitted or an unordered collection is used, do not write position-based assertions. Use `Set` when the domain does not care about ordering, and ensure child `equals`/`hashCode` are implemented properly.

Inspect `line_no` directly if ordering is part of the persistence contract:

~~~java
List<Integer> positions = jdbcTemplate.query(
        "SELECT line_no FROM order_lines WHERE order_id = ? ORDER BY line_no",
        (rs, rowNum) -> rs.getInt(1),
        saved.id()
);
~~~

## 20. Testing Converters Across Schema Versions

If a converter stores enum codes or value objects, the schema may change across migrations. For example, status used to be stored as `NEW`/`PAID` and then migrated to `N`/`P`.

Tests should verify:

- New data is written in the new format.
- Legacy data can still be read if the application must support rolling deployments.
- Unrecognized values fail clearly.
- Migrations transform legacy data before new code reads it.
- All writers (Spring Data JDBC, `JdbcTemplate`, MyBatis, batch jobs) use the same format.

A converter tested only against data written within the same test may miss backward-compatibility problems. Seed pre-existing database values to test the reading converter independently.

## 21. Testing Multiple DBMSs and JDBC Drivers

H2 is great for fast tests, yet does not fully emulate the semantics of every DBMS. If production runs a different database, maintain matching test profiles or Testcontainers suites.

Common differences to test:

| Item | Risk When Switching DBMS/Driver |
|---|---|
| Generated ID | Drivers return generated keys differently |
| UUID | Native, binary, or string types |
| Timestamp | Precision, timezone, and session settings |
| Boolean | `BOOLEAN`, `BIT`, or numeric representation |
| Decimal | Precision/scale and rounding |
| Identifiers | Quoting, reserved words, and case |
| Embedded | Prefixed column names and null semantics |
| Collection | FK, delete/reinsert, and constraints |
| Converter | JDBC type reported by the driver |
| Migration | Identity/sequence syntax and default values |

If the application claims to support multiple DBMSs, run the same contract test suite on every supported database. Do not test only one engine and assume all others are compatible.

## 22. Common Mistakes When Testing Mappings

| Symptom | Common Cause | Direction to Fix |
|---|---|---|
| Property reads back as null | `@Column`, prefix, or DDL mismatch | Check metadata and physical column names |
| Embedded object is always null | All embedded columns are null or `onEmpty` mismatches contract | Check data and `onEmpty` configuration |
| Child collection is empty after load | Wrong `idColumn` or mismatched child FK | Check `@MappedCollection` and schema |
| List changes order | Missing `keyColumn` or test assumes unguaranteed ordering | Declare `keyColumn` and verify `line_no` |
| Converter works in only one direction | Missing reading or writing converter | Register both directions and test repository round-trip |
| Converter not invoked in test slice | Converter configuration not imported/scanned | Bring configuration into test context |
| Generated ID is null | Reading input object, driver not returning keys, or wrong ID strategy | Use object returned by `save` and test with real driver |
| Entity with pre-assigned ID receives UPDATE instead of INSERT | Newness strategy does not recognize new entity | Use null `@Version` or `Persistable.isNew` |
| Version does not change | `@Version` not mapped or using stale object instance | Check version column and `save` return value |
| Test passes on H2 but fails in production | Dialect/driver semantics differ | Add Testcontainers or real DBMS integration tests |
| Tests interfere with each other | Committed data, shared sequences, or shared context | Use rollback/cleanup and isolated fixtures |
| Round-trip test passes despite wrong column name | Checking objects only without independent schema/read path | Seed/query directly with `JdbcTemplate` |

## 23. Minimum Test Matrix for an Aggregate

A solid mapping test suite should cover these corresponding checks:

| Component | Write Test | Read Test | Database Assertion |
|---|---|---|---|
| `@Table` / `@Column` | Save root | Find root | Correct physical table/column |
| `@Embedded` | Save Address | Read Address | Prefixed columns and null semantics |
| `@MappedCollection` | Save child list | Read child list | FK, key/index, and row count |
| Converter | Domain → store | Store → domain | Correct physical value and type |
| Generated ID | Insert null ID | Read by new ID | ID generated and children reference it |
| Assigned ID | Insert UUID | Read/update UUID | ID preserved, newness accurate |
| `@Version` | Insert/update | Reload | Version increments and stale writes rejected |
| Nullability | Save null/empty | Read null/empty | Matches constraints and `onEmpty` |
| Migration | Run migrations | Repository CRUD | Real schema compatible |

You do not need one giant test checking everything. Split tests by contract so failures are easy to pinpoint and when a mapping changes, readers know which test guards that behavior.

## 24. Practice Exercises

Using the `PurchaseOrder` aggregate above, perform the following:

1. Save a new root with a `null` ID; confirm the returned object has a generated ID.
2. Query `order_number` directly to verify `@Column`.
3. Save an `Address` with street and city populated; verify `shipping_street` and `shipping_city` columns.
4. Save a `null` `Address`; confirm `USE_NULL` or `USE_EMPTY` semantics.
5. Save three `OrderLine` items with different SKUs; reload and assert `List` ordering.
6. Count child rows by `order_id` and verify the FK.
7. Shrink the collection from three items to one; save again and assert the final state.
8. Save `Money` and read the raw `DECIMAL` via `JdbcTemplate`.
9. Reload `Money` through the repository to verify `ReadingConverter`.
10. Create an aggregate with a pre-assigned UUID and confirm `INSERT` via the newness strategy.
11. Update the aggregate and confirm `version` changes.
12. Seed a row via SQL and read it through the repository.
13. Run the same test suite on H2 and a production-like DBMS if the project supports multiple databases.

Document which tests run on an embedded DB and which run on a production-like database. This helps maintainers understand the evidence boundaries of each suite.

## 25. Key Principles

- Use `@DataJdbcTest` to test repositories and mapping inside a Spring context; mocking repositories does not test SQL mapping.
- Use a schema matching migrations, including column names, data types, nullability, keys, and constraints.
- Verify `@Table`/`@Column` using both repositories and direct queries via `JdbcTemplate`.
- Verify `@Embedded` with prefixes and `onEmpty` policies for null/empty objects.
- Verify `@MappedCollection` via child row count, foreign keys, `keyColumn`, and collection order.
- Test both `WritingConverter` and `ReadingConverter`; confirm converters are registered in the test context.
- Use the object returned from `repository.save` to obtain generated IDs and versions.
- For pre-assigned IDs, test the newness strategy via `@Version` or `Persistable`.
- Seed data directly to test the read path independently of the write path.
- Test against the exact DBMS/driver when relying on generated keys, UUIDs, temporal types, or dialects.
- Understand test transactions and cleanup to avoid leaking committed data.
- Split tests by mapping contract for easy fault localization and maintainability.

Mapping in Spring Data JDBC is a contract between object model, metadata, and database schema. A valuable test suite runs through real repositories, reads data back, inspects physical rows and columns, and executes on the target driver when DBMS differences exist. Testing embedded objects, collections, converters, and IDs individually lets teams catch mapping errors early before they surface in large use cases or after migrations.

## References

- [Spring Data Relational — Object Mapping](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html)
- [Spring Data Relational — Entity Persistence](https://docs.spring.io/spring-data/relational/reference/jdbc/entity-persistence.html)
- [Spring Boot — Data JDBC Tests](https://docs.spring.io/spring-boot/reference/testing/spring-boot-applications.html#testing.spring-boot-applications.autoconfigured-spring-data-jdbc)
- [Spring Data Relational — Custom Conversions](https://docs.spring.io/spring-data/relational/reference/jdbc/mapping.html#jdbc.custom-conversions)
- [Testcontainers for Java](https://java.testcontainers.org/)
