# Mapping JSON and Database-Specific Types in Hibernate

Hibernate extends JPA mapping capabilities to work with database types not directly represented by basic Java types, including JSON, SQL ARRAY, UUID, native enums, and RDBMS-specific types. For JSON, Hibernate 6 provides mapping via `@JdbcTypeCode(SqlTypes.JSON)`, allowing you to map a Java property such as a POJO, `Map`, or JSON tree structure to a database JSON column.

Three concerns should be kept separate:

- **Java type:** the object type used by the application, such as `Map<String, Object>`, a record, or `JsonNode`.
- **JDBC/Hibernate type:** how Hibernate serializes, binds parameters, and reads data over JDBC.
- **Database column type:** the actual column type such as PostgreSQL `jsonb`, PostgreSQL `json`, MySQL `JSON`, or another database's JSON-specific storage type.

The `@JdbcTypeCode` annotation guides Hibernate in selecting the JDBC type. `columnDefinition` primarily describes a DDL fragment when Hibernate generates schema; it does not by itself supply serialization, JDBC binding, or JSON query support. Migrations and the real schema must match the mapping.

This document uses Hibernate ORM 6+ and Jakarta Persistence (`jakarta.persistence`) in Spring Boot 3 and above. Extensions such as JSON mapping, custom UserTypes, and database-specific JDBC types depend on the Hibernate version and dialect; always cross-check against the ORM version managed by the Spring Boot BOM.

## 1. Why Are Hibernate-Specific Types Needed?

Standard JPA provides common mappings such as strings, numbers, dates/times, enums, relationships, and converters. Modern databases, however, support richer types:

- JSON/JSONB for storing semi-structured documents.
- SQL ARRAY for storing a collection of values in a single column.
- Native UUID.
- Database-defined enum types.
- Network types such as PostgreSQL INET/CIDR.
- Spatial types such as geometry/geography.
- Vendor-specific binary, range, vector, or other extended types.

Using String for every specialized type can cause the application to lose specialized database binding, validation, query operators, or indexes. Hibernate's type system maps Java types to more appropriate JDBC and database types.

Not all databases support the same data types. A mapping that runs on PostgreSQL may fail on MySQL or H2 if dialects, DDL, and JDBC drivers differ.

## 2. JSON Mapping in Hibernate 6

Hibernate 6 provides JSON mapping via:

```java
@JdbcTypeCode(SqlTypes.JSON)
```

Imports:

```java
import org.hibernate.annotations.JdbcTypeCode;
import org.hibernate.type.SqlTypes;
```

Entity example:

```java
@Entity
@Table(name = "event")
public class Event {

    @Id
    @GeneratedValue
    private Long id;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private Map<String, Object> payload;

    protected Event() {
    }

    public Map<String, Object> getPayload() {
        return payload;
    }

    public void setPayload(Map<String, Object> payload) {
        this.payload = payload;
    }
}
```

Here:

- `Map<String, Object>` is the Java representation.
- `@JdbcTypeCode(SqlTypes.JSON)` instructs Hibernate to use JSON JDBC mapping.
- `columnDefinition = "jsonb"` is a PostgreSQL-specific DDL fragment used when Hibernate generates schema.
- Migrations must create a column whose type is compatible with the mapping.

`columnDefinition` alone does not enable a JSON serializer. Writing only `@Column(columnDefinition = "jsonb")` without configuring JSON JDBC mapping may leave Hibernate handling the property with default Java/JDBC types and raising errors.

When schemas are managed by Flyway/Liquibase, DDL migrations are the source of truth. Never rely on `columnDefinition` to create or alter columns in production.

## 3. Java Representations You Can Use

Hibernate JSON mapping can serialize/deserialize Java structures supported by the configured JSON format mapper.

### 3.1. Map

```java
@JdbcTypeCode(SqlTypes.JSON)
@Column(columnDefinition = "jsonb")
private Map<String, Object> metadata;
```

Pros:

- Flexible when document structure evolves.
- Easy to add/remove keys.
- Useful for metadata, settings, or schemaless payloads.

Cons:

- Weak type safety.
- Easy to mistype key names or misread value types.
- Nested objects typically require casting or runtime type checks.
- Refactoring JSON structure has little compiler assistance.

If using a Map, clearly define key conventions, value types, and document schema versioning.

### 3.2. POJO or record

For stable structures, use a class or record:

```java
public record DeliveryAddress(
    String city,
    String postalCode,
    String countryCode
) {
}
```

Entity:

```java
@Entity
public class Shipment {

    @Id
    @GeneratedValue
    private Long id;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private DeliveryAddress destination;
}
```

This increases type safety, simplifies refactoring, and makes application-layer validation easier. Immutable records make replacing an entire value object explicit when updating a document.

Hibernate requires a JSON format mapper capable of serializing/deserializing that Java type. Jackson or JSON-B is commonly used depending on classpath/configuration; verify your application's actual dependencies and mapper. When using custom constructors, record components, polymorphic types, or custom serializers, write integration tests for round-trip serialization.

### 3.3. JSON tree such as JsonNode

If the application uses Jackson:

```java
import com.fasterxml.jackson.databind.JsonNode;

@Entity
public class AuditEvent {

    @Id
    @GeneratedValue
    private Long id;

    @JdbcTypeCode(SqlTypes.JSON)
    @Column(columnDefinition = "jsonb")
    private JsonNode document;
}
```

JsonNode is useful when manipulating JSON trees without creating POJOs for every structure. It depends on Jackson and is not a Jakarta Persistence JSON type.

Choose one Java representation suited to the domain. Avoid converting a Map to a String and storing a JSON string in a JSON column when the goal is for Hibernate to manage JSON binding directly; doing so can double-encode the JSON as a string literal rather than a document.

## 4. JSON Format Mapper and Serialization Configuration

Hibernate needs a JSON format mapper to convert between Java objects and JSON. Hibernate 6 can select a mapper based on libraries present on the classpath—typically Jackson or JSON-B—and can also be configured explicitly via the corresponding Hibernate setting.

Factors affecting serialization behavior:

- Jackson modules for Java Time, records, or custom types.
- Naming strategies and serialization annotations.
- Custom serializers/deserializers.
- Handling of unknown properties and nulls.
- Polymorphic type metadata.
- JSON document schema versioning.

Do not assume every Spring Boot `ObjectMapper` customization is automatically shared by Hibernate's JSON mapper. Hibernate's JSON format mapper and Spring MVC's HTTP Jackson serialization can follow separate configurations; if identical behavior is needed, configure and test explicitly for your Hibernate version.

For long-lived persisted documents, changing serializers or property names can break deserialization of legacy data. Adopt a versioning/migration strategy for JSON schemas, especially when documents represent core business data.

## 5. PostgreSQL: json and jsonb

PostgreSQL offers two main types:

| Type | Characteristics |
|---|---|
| `json` | Stores exact input JSON text; preserves whitespace and key order as received, validates JSON syntax |
| `jsonb` | Stores decomposed binary format; does not preserve original whitespace/key order, supports richer operators and indexing |

In most cases `jsonb` is better suited for documents queried or indexed frequently. `json` may fit when preserving exact textual formatting or when workloads only write and read whole documents.

Example migration:

```sql
create table event (
    id bigserial primary key,
    payload jsonb not null
);
```

Entity:

```java
@JdbcTypeCode(SqlTypes.JSON)
@Column(columnDefinition = "jsonb", nullable = false)
private Map<String, Object> payload;
```

The column type must match between migration and mapping. If the schema uses a `json` column, do not declare `jsonb` on the entity as if the two types were interchangeable; match the actual database column type.

## 6. MySQL and Other Databases

MySQL provides a `JSON` column type with database-level JSON validation and functions such as `JSON_EXTRACT`, `JSON_SET`, and `JSON_CONTAINS`.

Illustrative DDL:

```sql
create table event (
    id bigint primary key auto_increment,
    payload json not null
);
```

Hibernate mapping:

```java
@JdbcTypeCode(SqlTypes.JSON)
@Column(columnDefinition = "json")
private Map<String, Object> payload;
```

Do not copy PostgreSQL `jsonb` DDL to MySQL. Type names, operators, indexes, and JSON query syntax differ by database.

Some databases store JSON in text/binary types or provide native JSON types depending on version. Oracle, SQL Server, MariaDB, and others vary in DDL, constraints, functions, and indexing. Check the documentation for your exact database version and Hibernate dialect.

## 7. Querying JSON Properties with Native SQL

Hibernate JSON mapping handles storing and reading documents, while JSON query syntax usually depends on the database.

PostgreSQL:

```sql
select id, payload ->> 'status' as status
from event
where payload ->> 'status' = :status;
```

MySQL:

```sql
select id,
       json_unquote(json_extract(payload, '$.status')) as status
from event
where json_unquote(json_extract(payload, '$.status')) = :status;
```

These can be executed via Spring Data native queries or EntityManager:

```java
@Query(
    value = """
        select *
        from event
        where payload ->> 'status' = :status
        """,
    nativeQuery = true
)
List<Event> findByPayloadStatus(
    @Param("status") String status
);
```

The query above targets PostgreSQL. Do not run that exact SQL on MySQL; use the corresponding functions and operators.

Bind values using parameters. Dynamic JSON paths or identifiers cannot always be bound like value parameters consistently across databases; if dynamic paths are needed, whitelist allowed paths and construct queries safely. Never concatenate raw user input into SQL.

JPQL has no single portable JSON operator across all databases. You can invoke database functions through Hibernate HQL/Criteria functions or native SQL, though function names and semantics remain dialect-dependent.

## 8. Indexing JSON

There is no single JSON index design that works identically across all databases.

PostgreSQL:

```sql
create index ix_event_payload_gin
on event using gin (payload);
```

A GIN index accelerates many JSONB containment and key-existence queries. You can also create an expression index on a specific path:

```sql
create index ix_event_payload_status
on event ((payload ->> 'status'));
```

MySQL typically relies on generated columns or functional indexes matching JSON expressions:

```sql
alter table event
add column payload_status varchar(40)
    generated always as (
        json_unquote(json_extract(payload, '$.status'))
    ) stored;

create index ix_event_payload_status
on event(payload_status);
```

Index behavior depends on engine/version, and expressions must match the query. Inspect EXPLAIN/EXPLAIN ANALYZE to confirm the optimizer uses the index.

Do not add GIN or JSON indexes to every JSON column by default. Indexes increase storage and INSERT/UPDATE overhead; index only paths and operators that actually appear in your workload.

## 9. Partial Document Update vs. Replacing the Whole JSON

When the application modifies a property inside a Map or POJO, Hibernate typically serializes and writes back the entire JSON column value. It does not automatically perform a database-side partial JSON path update.

Example:

```java
@Transactional
public void changeStatus(Long id, String status) {
    Event event = repository.findById(id).orElseThrow();

    Map<String, Object> payload =
        new HashMap<>(event.getPayload());

    payload.put("status", status);
    event.setPayload(payload);
}
```

Assigning a new Map instance makes the reference change explicit and keeps dirty-checking semantics predictable. With mutable types, verify the mutability plan and equality semantics used by Hibernate and its mapper; do not assume deep in-place mutations are detected identically across all types.

If you need to update a single path without rewriting the entire document, you can use native functions such as PostgreSQL `jsonb_set` or MySQL `JSON_SET`. This is database-specific DML and requires synchronizing the PersistenceContext if entities are managed.

PostgreSQL example:

```sql
update event
set payload = jsonb_set(
    payload,
    '{status}',
    to_jsonb(cast(:status as text)),
    true
)
where id = :id;
```

After a native bulk update, managed Event entities may still hold the old payload. Refresh affected entities or clear the PersistenceContext as appropriate. Bulk/native DML does not automatically trigger entity lifecycle callbacks, cascades, or dirty checking.

## 10. SQL NULL, JSON null, and Missing Keys

These three states are distinct:

1. **SQL NULL:** the payload column itself has no database value.
2. **JSON null:** the document is the JSON literal `null`, or a property's value is `null`.
3. **Missing key:** the JSON object does not contain the queried key.

Example document:

```json
{
  "status": null
}
```

This differs from:

```json
{}
```

And both differ from a SQL column with payload = NULL.

Database JSON functions may return SQL NULL, JSON null, or varying results depending on function/path/operator. For example, PostgreSQL's `->>` operator returns text and has specific semantics for missing keys and JSON null. MySQL `JSON_EXTRACT` can return a JSON value or JSON null, with `JSON_UNQUOTE` having corresponding behavior.

Define business semantics clearly: do "missing status", "null status", and "missing payload" mean different things? Write integration tests for all three cases, not only well-formed populated JSON objects.

## 11. AttributeConverter vs. @JdbcTypeCode(JSON)

JPA `AttributeConverter<X, Y>` converts a domain type X to a basic type Y and back:

```java
@Converter
public class SettingsConverter
        implements AttributeConverter<Settings, String> {

    @Override
    public String convertToDatabaseColumn(Settings value) {
        // Serialize Settings to JSON text.
        return value == null ? null : serialize(value);
    }

    @Override
    public Settings convertToEntityAttribute(String value) {
        // Deserialize JSON text to Settings.
        return value == null ? null : deserialize(value);
    }
}
```

This example is a skeleton; `serialize`/`deserialize` must be implemented with an actual mapper and proper exception/null handling.

Comparison:

| Criterion | AttributeConverter to String | Hibernate JSON JDBC Mapping |
|---|---|---|
| Java type | Domain object | Map/POJO/JSON tree |
| JDBC representation | Typically VARCHAR/CLOB | JSON JDBC type per Hibernate/dialect |
| Database JSON operators/indexes | May be restricted if column/driver treats it as text | Better suited for native JSON types |
| Portability | Standard JPA converter, though storage/queries depend on DB | Hibernate-specific and database-dependent |
| Serialization | Managed by application converter | Managed via Hibernate JSON format mapper |

If the database column is genuinely JSON/JSONB and JSON operators/indexes are needed, prefer Hibernate's JSON mapping when supported by dialect and driver. Converting to String can fit when the schema stores text or Java-side mapping portability is desired, provided column types and binding are verified.

Do not apply both a converter and `@JdbcTypeCode(SqlTypes.JSON)` to the same property without understanding Hibernate's precedence and mapping composition; overlapping configurations can produce unexpected JDBC types.

## 12. @JavaType, @JdbcTypeCode, and Custom Types

Hibernate separates Java-side type handling from JDBC-side type handling:

- `@JavaType` selects how Hibernate understands, compares, copies, and manages the Java value.
- `@JdbcTypeCode` selects the JDBC type code used for binding and reading.
- `@JdbcType` can specify a concrete JdbcType implementation.
- `@Type` attaches a custom Hibernate UserType.

Example using a type code:

```java
@JdbcTypeCode(SqlTypes.JSON)
private Map<String, Object> payload;
```

This is usually the simplest option for JSON in Hibernate 6.

When special behavior is needed—such as custom serialization, custom conversion, mutability plans, or specialized JDBC binding—you can implement a custom JavaType/JdbcType or UserType. Do not write a custom type if built-in JSON support meets your needs; custom types increase compatibility maintenance across Hibernate versions, JDBC drivers, and schemas.

## 13. Custom UserType in Hibernate

Hibernate provides the `UserType` extension point to define how a Java value is read/written via JDBC, compared, copied, and cached. The API changed between Hibernate 5 and Hibernate 6.

Hibernate 6 uses a generic UserType and class-referenced `@Type` annotation:

```java
@Type(MyCustomType.class)
private CustomValue value;
```

This shows only how the type is attached; the `MyCustomType` implementation must fulfill the Hibernate 6 contract, including JDBC mapping, equality/hashCode, deep copy/mutability, and null handling.

Hibernate 5 had a different UserType API and commonly used the older string-based annotation syntax:

```java
@Type(type = "com.example.MyCustomType")
private CustomValue value;
```

Do not copy Hibernate 5 custom type code into Hibernate 6 without porting the API. Consult the Javadoc/source for the exact Hibernate ORM version in your project. Custom types must be integration-tested against a real provider and database—especially for null binding, dirty checking, second-level caching, and schema validation.

## 14. Other Database-Specific Types

### 14.1. UUID

UUIDs can be stored as native UUID, binary, or character columns depending on database/dialect and Hibernate configuration.

```java
@Id
@GeneratedValue
@JdbcTypeCode(SqlTypes.UUID)
private UUID id;
```

Hibernate generally has built-in UUID mapping support; specify the type code only when clarifying the mapping or matching an existing schema. Verify the actual DDL and database representation. If a legacy schema stores UUIDs as CHAR(36) or BINARY(16), the mapping must remain compatible with existing data.

### 14.2. SQL ARRAY

On databases supporting ARRAY, Hibernate can map Java arrays or supported collections:

```java
@JdbcTypeCode(SqlTypes.ARRAY)
@Column(columnDefinition = "text[]")
private String[] tags;
```

This example targets databases supporting SQL ARRAY such as PostgreSQL. MySQL does not share the same native ARRAY column semantics. Do not use `text[]` DDL on databases that do not support this type.

### 14.3. Native enum

Standard JPA supports:

```java
@Enumerated(EnumType.STRING)
private OrderStatus status;
```

This typically maps to a VARCHAR/string representation rather than a database native enum type.

Hibernate provides extensions for named/native enums depending on dialect and version. On PostgreSQL, mapping a native enum may require `SqlTypes.NAMED_ENUM` or a PostgreSQL enum JdbcType compatible with your Hibernate version, paired with a `columnDefinition` matching the schema's enum type name. Verify support in your specific version; `@Enumerated(EnumType.STRING)` does not create a PostgreSQL enum type.

### 14.4. Network and spatial types

Types such as INET/CIDR or GEOMETRY/GEOGRAPHY typically require specialized JDBC types/dialects or dedicated libraries. Hibernate Spatial supports a range of spatial types and functions; exact mappings depend on the database and extensions.

Do not force these types into String if the application needs database-specific operators or indexes. Conversely, if you only display values without querying by specialized semantics, a simpler representation may suffice. Weigh dependencies and portability before adding extensions.

## 15. When Is a Custom Dialect or Function Registration Needed?

A Dialect describes SQL, type, and function differences of a database to Hibernate. In most cases, modern built-in dialects already support common types; avoid creating a custom Dialect merely to tweak a single column definition.

Extensions may be necessary when:

- A database vendor/version has a type or function not yet recognized by Hibernate.
- You need to register a SQL function for invocation in HQL/Criteria.
- A JDBC driver returns a vendor type code or object requiring custom binding.
- You need shared custom type registration across multiple entities.

Depending on the Hibernate version, extension APIs and type/function registration mechanisms change. Prefer APIs documented for your current version; avoid internal classes or deprecated APIs. Keep custom Dialects small and covered by SQL generation tests.

## 16. Schema Migration and Validation

With JSON and specialized types, schema migrations must match entity mappings.

PostgreSQL migration:

```sql
alter table event
add column payload jsonb;

create index ix_event_payload_gin
on event using gin (payload);
```

Entity:

```java
@JdbcTypeCode(SqlTypes.JSON)
@Column(columnDefinition = "jsonb")
private Map<String, Object> payload;
```

In production, use Flyway or Liquibase to manage DDL. `spring.jpa.hibernate.ddl-auto=validate` can catch certain schema mismatches, but it does not replace migration reviews or verify every index, function, or constraint.

Never use `ddl-auto=update` as a production migration tool for custom types, JSON indexes, or database-specific DDL. Hibernate-generated DDL may fail to create all required indexes, operator classes, or constraints.

When changing `json` to `jsonb` or modifying JSON structure, run data migrations and validate legacy documents before deploying new code.

## 17. Queries, Dirty Checking, and PersistenceContext

A JSON property is part of entity state. When a managed entity's JSON value changes, Hibernate can mark the entity dirty and rewrite the JSON column during flush. For custom mutable objects, behavior depends on the JavaType/mutability plan and how equality and copying are implemented.

Safe practices:

- Prefer immutable value objects/records where appropriate.
- Replace with a new object instead of mutating deep nested maps when dirty detection is uncertain.
- Write integration tests for nested mutations and updates.
- Inspect SQL UPDATE statements to see whether Hibernate rewrites the entire JSON column.
- When using native JSON updates, refresh/clear managed entities to avoid stale state.
- Do not expect automatic partial JSON path updates just because the property is a Map or POJO.

Second-level caching, optimistic locking, and audit/version columns should also be reviewed if JSON data changes frequently.

## 18. Security and Validation for JSON

JSON is structured data, yet it remains untrusted input when originating from clients or external systems.

- Validate schema and domain rules before persisting.
- Enforce document size limits and nesting depth limits.
- Never deserialize arbitrary polymorphic classes from untrusted type metadata.
- Do not store secrets/tokens without appropriate encryption and access controls.
- Avoid logging entire JSON payloads containing personal data or credentials.
- Use parameter binding for values; whitelist dynamic JSON paths and SQL identifiers.
- Define unknown-field and versioning behavior clearly when schemas evolve.

If a JSON document has a stable business structure, consider extracting frequently filtered, joined, or sorted fields into regular relational columns. JSON should not become a dumping ground for relational data that makes constraints, indexing, and queries difficult to manage.

## 19. Testing Against a Real Database

H2 or mocks cannot reliably emulate PostgreSQL/MySQL JSON types, operators, indexes, native enums, or driver behavior.

Use Testcontainers or a test database running an engine and version close to production to verify:

1. The schema has JSON/JSONB columns with the expected types.
2. Persisting POJOs/Maps/JsonNodes produces valid documents without double-encoding.
3. Reading documents back preserves types, nulls, and nested values.
4. SQL NULL behaves distinctly from JSON null and missing keys as expected.
5. JSON operators/functions return the expected results.
6. Execution plans use indexes for key queries.
7. Nested mutations trigger dirty checking properly.
8. Native JSON updates synchronize the PersistenceContext.
9. Custom UserTypes handle nulls, equality, deep copies, and caching.
10. Migrations upgrading legacy documents execute safely.

Testcontainers does not automatically guarantee production parity if image or driver versions differ. Pin exact database image, driver, and Hibernate versions in your build/test setup.

## 20. Common Pitfalls

| Symptom | Cause | Resolution |
|---|---|---|
| Hibernate binds JSON as VARCHAR | Only columnDefinition specified or missing JSON JDBC mapping | Use `@JdbcTypeCode(SqlTypes.JSON)` and verify dialect |
| Schema has JSONB but app fails with type error | DDL and Hibernate/driver types mismatch | Align column types, dialect, and migrations |
| JSON is double-encoded | Storing a JSON string as a JSON string value | Map POJO/Map/JsonNode directly using JSON mapping |
| Cannot deserialize record/POJO | JSON mapper/dependency/constructor config mismatch | Verify Jackson/JSON-B mapper and round-trip tests |
| JSON operator fails on another DB | Vendor-specific native functions/operators | Write DB-specific queries or isolate behind an abstraction |
| Slow JSON queries | Missing GIN/expression/generated-column index | Design indexes for actual operators/paths and check EXPLAIN |
| Nested Map updated but no SQL UPDATE issued | Mutability/equality/dirty checking differs from expectation | Assign a new object and test SQL UPDATE |
| JPA reads stale JSON after native update | Stale PersistenceContext | Refresh entity or clear context appropriately |
| SQL NULL confused with JSON null | Different semantics across columns, paths, and functions | Test missing key, JSON null, and SQL NULL separately |
| Native enum binding error | Hibernate type/dialect does not match DB enum | Use version-appropriate native enum mapping or STRING |
| Custom UserType fails to compile after upgrade | Hibernate 5/6 UserType API differences | Port to current version's UserType API |
| H2 tests pass while production fails | Differences in JSON types, functions, drivers, or dialects | Run integration tests with Testcontainers/real engine |

## 21. Mapping Selection Workflow

1. Identify the database engine/version and JDBC driver.
2. Check whether the database has native JSON/ARRAY/UUID/enum types.
3. Choose the Java representation: POJO/record, Map, or JSON tree.
4. Use Hibernate built-in types such as `@JdbcTypeCode(SqlTypes.JSON)` where supported.
5. Declare accurate DDL in migrations; use `columnDefinition` only as a DDL hint when appropriate.
6. Determine JSON querying, function, and indexing requirements.
7. Choose native SQL or dialect functions for vendor-specific queries.
8. Write AttributeConverter/UserType/custom JdbcType only when built-in mappings fall short.
9. Verify dirty checking, mutability, caching, and update semantics.
10. Test round-trips, NULLs, nested mutations, native DML, and migrations on the target database.

## 22. Pre-Production Checklist for JSON/Custom Types

- [ ] Do the Hibernate version and dialect support the required type code?
- [ ] Can the Java type be serialized/deserialized by the JSON format mapper?
- [ ] Is `@JdbcTypeCode(SqlTypes.JSON)` used for Hibernate JSON mapping?
- [ ] Does `columnDefinition` match the actual column type and migration?
- [ ] Are PostgreSQL json/jsonb and MySQL JSON properly distinguished?
- [ ] Are vendor-specific JSON queries properly isolated?
- [ ] Are JSON indexes grounded in real workload patterns and EXPLAIN?
- [ ] Are SQL NULL, JSON null, and missing key semantics clearly defined?
- [ ] Are nested mutations properly handled by dirty checking?
- [ ] Does native DML refresh/clear the PersistenceContext?
- [ ] Are custom types compatible with the exact Hibernate major version?
- [ ] Are tests executed against a database/driver close to production?
- [ ] Do JSON payloads have validation, size limits, and security policies?

## 23. Conclusion

Hibernate 6 provides built-in JSON mapping via `@JdbcTypeCode(SqlTypes.JSON)`, allowing Maps, POJOs/records, or JSON trees to map cleanly to dialect- and database-supported JSON types. `columnDefinition` describes DDL, whereas the JDBC type and JSON format mapper govern binding and serialization; neither substitutes for the other.

Database-specific types such as UUID, ARRAY, native enums, network, or spatial types require matching dialect/driver mappings and sometimes Hibernate extensions. Write custom UserTypes, JdbcTypes, or Dialects only when built-in support is insufficient, as extensions couple tightly to Hibernate versions.

Ultimately, JSON querying/indexing, SQL NULL versus JSON null, dirty checking, and native DML depend on the database and provider. Manage schemas via migrations, test against the real engine, inspect execution plans, and keep the PersistenceContext synchronized when executing native updates. Doing so lets you leverage JSON and custom types while preserving correctness and operability.