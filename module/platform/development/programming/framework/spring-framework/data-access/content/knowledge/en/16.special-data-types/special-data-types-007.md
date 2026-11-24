# SQL ARRAY, Enums, JSON, and Database-Specific Types

When using Spring JDBC, `VARCHAR`, `INTEGER`, and `BIGINT` columns are usually straightforward to map because JDBC provides standard Java types and methods for them. However, many database management systems also offer **SQL arrays (`ARRAY`)**, **enumerated types (`ENUM`)**, **JSON/`JSONB`**, **user-defined types (`DOMAIN`, `STRUCT`/composite)**, and vendor-specific types such as `UUID`, ranges, network addresses, and spatial types. They provide strong constraint checking and querying at the SQL layer, yet **there is no single universal bind/read mechanism across all DBMSs**.

This lesson explains how to distinguish Java types, JDBC type codes, and native database types; how to transfer values in `JdbcTemplate`/`NamedParameterJdbcTemplate`; a Java 17+ example on PostgreSQL; and limitations when porting code to MySQL, Oracle, or other DBMSs.

## 1. Three Type Layers That Must Align

Data passes through three layers:

```text
Java domain / DTO
  ├─ String[], List<String>, enum, JsonNode, UUID, record...
  ↓ mapping + validation
JDBC / Spring JDBC
  ├─ java.sql.Array, java.sql.Types, PreparedStatement, ResultSet
  ├─ SqlParameterValue, SqlTypeValue, RowMapper, JdbcTemplate
  └─ Driver extension: e.g. org.postgresql.util.PGobject
  ↓ driver type conversion and value encoding
Database
  ├─ text[], item_state, jsonb, uuid
  └─ domain, composite, range, and other vendor-specific types
```

For example, a `String[]` in Java **is not automatically** a SQL `text[]`. Likewise, Java `enum ItemState { NEW, READY }` does not automatically turn into PostgreSQL `CREATE TYPE item_state AS ENUM (...)`; nor is a string `"{\\"a\\":1}"` guaranteed to be recognized by the driver as `jsonb`.

| Concept | Java Representation | JDBC | PostgreSQL Example | Watch Out For |
| --- | --- | --- | --- | --- |
| SQL Array | `String[]`, `Integer[]`, sometimes `Object[]` | `java.sql.Array`, `Types.ARRAY` | `text[]`, `integer[]` | Element type, dimensions, NULLs, allocation/freeing |
| Database Enum | `enum` or `String` | Usually driver-specific/`Types.OTHER` | `item_state` | Labels and label order are a schema contract |
| JSON | `String`, `JsonNode`, DTO | `setObject`, SQL cast, `Types.OTHER` per driver | `json`, `jsonb` | Valid JSON, structure, and nulls |
| UUID | `UUID` | `setObject`/`getObject` per driver | `uuid` | Some drivers support directly, others require conversion |
| Custom types | Dedicated object/DTO | `PGobject`, `Struct`, `SQLData`, driver extensions | `int4range`, domain, composite | Varying API and SQL syntax support |

`java.sql.Types` describes **SQL type codes for JDBC**, not a magic converter. `Types.OTHER` means JDBC has no specific standard type for that case; **it is not enough to tell** whether an `Object` holds `jsonb`, an enum, or a range.

## 2. SQL ARRAY: SQL Arrays Differ from Java Collections

A SQL ARRAY allows a single column to hold a collection of elements of the same type, for example:

```sql
CREATE TABLE article (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    tags TEXT[] NOT NULL
);

INSERT INTO article(tags) VALUES (ARRAY['spring', 'jdbc']);
SELECT tags[1] FROM article; -- 'spring' in default PostgreSQL
```

PostgreSQL normally starts array indexing at **1**, whereas Java starts at **0**. PostgreSQL can support lower bounds other than 1 when special array values are constructed, so code indexing SQL arrays needs to know the array's actual structure. In Java, once converted to `String[]`, the first element is always `tags[0]`.

### 2.1. Writing an ARRAY with Standard JDBC

On a driver supporting the corresponding API, create a `java.sql.Array` using **the exact connection used by the statement**, then call `PreparedStatement.setArray`:

```java
// Excerpt running inside a JdbcTemplate ConnectionCallback.
java.sql.Array dbArray = connection.createArrayOf(
    "text", new String[] { "spring", "jdbc" }
);
try (PreparedStatement ps = connection.prepareStatement(
        "INSERT INTO article(tags) VALUES (?)")) {
    ps.setArray(1, dbArray);
    ps.executeUpdate();
} finally {
    dbArray.free();
}
```

Here `"text"` is the PostgreSQL **element type name**, not `"text[]"`. For `integer[]`, use `createArrayOf("integer", new Integer[] {1, 2})`. Type names and support depend on the DBMS/driver; some databases (notably Oracle collection types) require specialized APIs.

Because `Connection.createArrayOf` creates a connection-bound object, never create a `java.sql.Array` on connection A and pass it to a statement on connection B. Spring's `JdbcTemplate.execute(ConnectionCallback<T>)` gives access to the callback's exact connection while preserving Spring's connection management and exception translation.

Call `Array.free()` **after** the SQL has executed; do not free it before the driver uses it. When using driver-specific APIs, check the resource-management guarantees documented by that driver.

### 2.2. Reading an ARRAY with ResultSet

```java
// Excerpt inside RowMapper; column tags has type text[].
java.sql.Array sqlArray = rs.getArray("tags");
String[] tags;
if (sqlArray == null) {
    tags = null; // SQL NULL differs from an empty array.
} else {
    try {
        tags = (String[]) sqlArray.getArray();
    } finally {
        sqlArray.free();
    }
}
```

With pgJDBC and `text[]`, `getArray()` normally returns `String[]`. With other drivers or element types, the result may be a different Java array type, so **do not blindly cast every `ARRAY` to `String[]`**. For large arrays, consider `Array.getResultSet()` if well supported by the driver; remember to close that `ResultSet` and free the `Array`.

### 2.3. Three Cases That Must Not Be Equated

| Data | Meaning |
| --- | --- |
| SQL `NULL` | Column has no ARRAY value (if schema allows) |
| `ARRAY[]::text[]` | An array exists, with **zero elements** |
| `ARRAY[NULL]::text[]` | An array with **one NULL element** |

In Java, these may map respectively to `null`, `new String[0]`, and `new String[] {null}`; exact API return values and mappings must be tested against the driver. Also distinguish SQL array brackets from JSON array brackets; `text[]` and `jsonb` holding `["spring","jdbc"]` are **two different types**, with different query operators and mappings.

### 2.4. Querying ARRAYs on PostgreSQL

```sql
SELECT id, tags
FROM article
WHERE tags @> ARRAY['spring']::text[];

SELECT id, tags
FROM article
WHERE 'jdbc' = ANY(tags);
```

`@>` is PostgreSQL's array containment operator; `ANY` compares a value against elements of the array. This SQL ARRAY syntax is not uniform across all DBMSs. For suitable workloads a `GIN` index can help, but inspect the execution plan and actual cardinality instead of indexing every array column automatically.

If elements need their own attributes, significant business ordering, complex joins, or unbounded growth, a normalized child table is usually better than storing everything in an ARRAY.

## 3. Enum: Distinguish Java Enums from Database Enums

In PostgreSQL:

```sql
CREATE TYPE item_state AS ENUM ('NEW', 'READY', 'ARCHIVED');

CREATE TABLE catalog_item (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    state item_state NOT NULL
);
```

Java can define:

```java
enum ItemState {
    NEW, READY, ARCHIVED
}
```

Both enums share identical labels yet **are not automatically linked**. A schema change such as adding `PAUSED` must be reflected in Java parsing, validation, migrations, and application version compatibility.

### 3.1. Binding Enums as PostgreSQL Types

An explicit approach with pgJDBC is `PGobject` (a PostgreSQL JDBC driver extension):

```java
PGobject stateValue = new PGobject();
stateValue.setType("item_state");
stateValue.setValue(ItemState.READY.name());

ps.setObject(1, stateValue);
```

Another approach without `PGobject` in a specific SQL statement is an explicit cast:

```java
// For PostgreSQL; ? remains a JDBC parameter.
jdbc.update(
    "UPDATE catalog_item SET state = CAST(? AS item_state) WHERE id = ?",
    ItemState.READY.name(), id
);
```

For example, `ps.setString(1, "READY")` **is not always** automatically converted by the driver/server from `VARCHAR` to `item_state` without an explicit cast in SQL. Using `PGobject` or an explicit cast makes the intent clear. `Types.OTHER` may be needed when binding NULL or using generic APIs; the actual SQL type must still be established.

### 3.2. Reading Enums and Handling Label Changes

```java
String label = rs.getString("state");
ItemState state = ItemState.valueOf(label);
```

`valueOf` requires an **exact case match**. If the DB contains a label unknown to the code, `IllegalArgumentException` signals a **schema mismatch** rather than something to silently replace with `NEW` or `READY`. Where forward/backward compatibility is required, define an explicit `UNKNOWN` mapping rule in the domain layer.

PostgreSQL enums compare in order of label declaration. That differs from Java `ordinal()`; **never store `ordinal()`** as a DB protocol because reordering constants in Java will silently misinterpret existing data. Likewise, do not assume MySQL `ENUM` and PostgreSQL enums share DDL syntax or ordering behavior.

## 4. JSON and JSONB: Structured Data Is Not Arbitrary Text

PostgreSQL example:

```sql
CREATE TABLE example_json (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    document JSONB NOT NULL
);

INSERT INTO example_json(document)
VALUES ('{"source":"jdbc","priority":2}'::jsonb);
```

In PostgreSQL:

- `json` stores valid JSON text preserving the input representation in most cases, including whitespace and key order.
- `jsonb` converts to a structured binary representation, generally better for containment queries and indexing. It **does not preserve** whitespace, object key order, or duplicate keys from the original text.
- Both can store objects, arrays, numbers, strings, booleans, and JSON `null`; **JSON null differs from SQL NULL**.
- JSON helps model flexible attributes, but **does not replace domain constraints, schema validation, versioning, and relational columns for core data**.

### 4.1. Binding JSONB with the Right SQL Type

Using `PGobject`:

```java
PGobject value = new PGobject();
value.setType("jsonb");
value.setValue("{\"source\":\"jdbc\",\"priority\":2}");
ps.setObject(1, value);
```

Or bind the JSON string as a parameter and cast in SQL:

```java
jdbc.update(
    "UPDATE example_json SET document = CAST(? AS jsonb) WHERE id = ?",
    "{\"source\":\"jdbc\",\"priority\":2}", id
);
```

Both keep JSON inside **parameter binding**; never concatenate user-supplied JSON directly into SQL statements. PostgreSQL validates JSON syntax when converting to `jsonb`; the application should validate structure and business values **before** writing.

Read via `rs.getString("document")` and use a JSON library (e.g., Jackson) to parse into `JsonNode`/DTOs. **Do not compare raw JSONB strings character-for-character against input JSON**, because the DB may alter whitespace or key ordering; compare structure or meaningful fields instead.

### 4.2. Querying JSONB

```sql
SELECT id
FROM example_json
WHERE document @> '{"source":"jdbc"}'::jsonb;

SELECT document ->> 'source'
FROM example_json;
```

`@>` is PostgreSQL's JSONB containment operator; `->>` extracts a value as text. JSONB columns frequently queried with `@>` can consider a `GIN` index; choose indexes based on actual queries and `EXPLAIN` rather than assuming all `GIN` indexes behave alike.

**pgJDBC pitfall:** PostgreSQL has the `?` JSONB key-existence operator, while `?` is also `PreparedStatement`'s parameter placeholder. In SQL strings passed to pgJDBC, write **`??`** to escape the operator; for example:

```java
Boolean hasPriority = jdbc.queryForObject(
    "SELECT document ?? ? FROM example_json WHERE id = ?",
    Boolean.class, "priority", id
);
```

pgJDBC translates `??` into the SQL `?` operator; the following `?` remains the placeholder for key `"priority"`. This is a pgJDBC rule, not generic SQL syntax across other drivers.

### 4.3. JSON NULL vs. SQL NULL

```sql
SELECT 'null'::jsonb IS NULL; -- false: a JSON null value exists
SELECT NULL::jsonb IS NULL;   -- true: SQL NULL
```

Jackson `NullNode`, Java `null`, and a **missing** JSON property must be distinguished per domain rules. Never call `String.valueOf(null)` to store `"null"` without defining its exact meaning.

## 5. Runnable Java 17+ Example: ARRAY + Enum + JSONB in One Table

This example uses **Spring JDBC 6.2.x, pgJDBC, and PostgreSQL 16**. It inserts a catalog item with all three special types, reads it back via `RowMapper`, and tests a structured SQL query. Schema creation runs **outside the Java program** purely to set up the learning environment; real applications need schema migrations.

### 5.1. Start Local PostgreSQL

If Docker is available, launch a test PostgreSQL instance:

```bash
docker run --rm --name jdbc-special-types -d \
  -e POSTGRES_USER=demo \
  -e POSTGRES_PASSWORD=demo \
  -e POSTGRES_DB=jdbc_types_demo \
  -p 5433:5432 \
  postgres:16
```

Wait until the database is ready before running the script (e.g., `docker exec jdbc-special-types pg_isready -U demo -d jdbc_types_demo`). On machines with PostgreSQL already installed, you can create an equivalent database and user instead of using Docker.

Create `schema.sql`:

```sql
-- Only for resetting demo data.
DROP TABLE IF EXISTS catalog_item;
DROP TYPE IF EXISTS item_state;

CREATE TYPE item_state AS ENUM ('NEW', 'READY', 'ARCHIVED');

CREATE TABLE catalog_item (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    title TEXT NOT NULL,
    tags TEXT[] NOT NULL,
    state item_state NOT NULL,
    properties JSONB NOT NULL,
    CONSTRAINT properties_is_object
        CHECK (jsonb_typeof(properties) = 'object')
);
```

Run the script from Bash:

```bash
docker exec -i jdbc-special-types \
  psql -v ON_ERROR_STOP=1 -U demo -d jdbc_types_demo < schema.sql
```

On Windows PowerShell:

```powershell
Get-Content -Raw schema.sql |
    docker exec -i jdbc-special-types psql -v ON_ERROR_STOP=1 -U demo -d jdbc_types_demo
```

The `DROP` statements are for resetting **the test database** to obtain deterministic output. Never apply them directly in production.

### 5.2. Gradle Configuration

Create `settings.gradle`:

```groovy
rootProject.name = 'jdbc-special-types-demo'
```

Create `build.gradle`:

```groovy
plugins {
    id 'application'
}

repositories {
    mavenCentral()
}

dependencies {
    implementation 'org.springframework:spring-jdbc:6.2.19'
    implementation 'org.postgresql:postgresql:42.7.14'
    implementation 'com.fasterxml.jackson.core:jackson-databind:2.19.2'
}

application {
    mainClass = 'JdbcSpecialTypesDemo'
}
```

These are concrete versions for the example, not a claim that they are the latest. pgJDBC is `implementation` (not merely `runtimeOnly`) because the Java code references `PGobject` directly.

### 5.3. Complete Java Program

Create `src/main/java/JdbcSpecialTypesDemo.java`:

```java
import java.sql.Array;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.util.Arrays;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import org.postgresql.util.PGobject;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.ConnectionCallback;
import org.springframework.jdbc.datasource.DriverManagerDataSource;

public final class JdbcSpecialTypesDemo {
    enum ItemState {
        NEW, READY, ARCHIVED
    }

    record CatalogItem(
        String title,
        String[] tags,
        ItemState state,
        String propertiesJson
    ) {}

    private JdbcSpecialTypesDemo() {}

    public static void main(String[] args) throws Exception {
        DriverManagerDataSource dataSource = new DriverManagerDataSource();
        dataSource.setDriverClassName("org.postgresql.Driver");
        dataSource.setUrl("jdbc:postgresql://127.0.0.1:5433/jdbc_types_demo");
        dataSource.setUsername("demo");
        dataSource.setPassword("demo");

        JdbcTemplate jdbc = new JdbcTemplate(dataSource);

        long id = insert(jdbc);
        CatalogItem item = jdbc.queryForObject(
            "SELECT title, tags, state, properties " +
                "FROM catalog_item WHERE id = ?",
            (rs, rowNum) -> mapRow(rs),
            id
        );

        if (item == null) {
            throw new IllegalStateException("Row not found after insert");
        }

        JsonNode json = new ObjectMapper().readTree(item.propertiesJson());
        Boolean matched = jdbc.queryForObject(
            "SELECT EXISTS (" +
                "SELECT 1 FROM catalog_item " +
                "WHERE tags @> ARRAY[?]::text[] " +
                "AND properties @> ?::jsonb " +
                "AND state = ?::item_state)",
            Boolean.class,
            "spring",
            "{\"source\":\"lesson\"}",
            "READY"
        );

        System.out.println("Title: " + item.title());
        System.out.println("State: " + item.state());
        System.out.println("Tags: " + Arrays.toString(item.tags()));
        System.out.println("JSON priority: " + json.path("priority").asInt());
        System.out.println("JSON source: " + json.path("source").asText());
        System.out.println("Query matched: " + Boolean.TRUE.equals(matched));
    }

    private static long insert(JdbcTemplate jdbc) {
        Long id = jdbc.execute((ConnectionCallback<Long>) connection -> {
            Array sqlTags = connection.createArrayOf(
                "text", new String[] { "spring", "jdbc", "json" }
            );

            try {
                PGobject dbState = new PGobject();
                dbState.setType("item_state");
                dbState.setValue(ItemState.READY.name());

                PGobject dbProperties = new PGobject();
                dbProperties.setType("jsonb");
                dbProperties.setValue(
                    "{\"priority\":2,\"source\":\"lesson\"}"
                );

                try (PreparedStatement ps = connection.prepareStatement(
                    "INSERT INTO catalog_item " +
                    "(title, tags, state, properties) " +
                    "VALUES (?, ?, ?, ?) RETURNING id"
                )) {
                    ps.setString(1, "Sample");
                    ps.setArray(2, sqlTags);
                    ps.setObject(3, dbState);
                    ps.setObject(4, dbProperties);

                    try (ResultSet rs = ps.executeQuery()) {
                        if (!rs.next()) {
                            throw new SQLException("INSERT returned no id");
                        }
                        return rs.getLong(1);
                    }
                }
            } finally {
                sqlTags.free();
            }
        });

        if (id == null) {
            throw new IllegalStateException("No generated identifier");
        }
        return id;
    }

    private static CatalogItem mapRow(ResultSet rs) throws SQLException {
        Array sqlTags = rs.getArray("tags");
        if (sqlTags == null) {
            throw new SQLException("tags unexpectedly NULL");
        }

        String[] tags;
        try {
            tags = (String[]) sqlTags.getArray();
        } finally {
            sqlTags.free();
        }

        return new CatalogItem(
            rs.getString("title"),
            tags,
            ItemState.valueOf(rs.getString("state")),
            rs.getString("properties")
        );
    }
}
```

**Important points to understand:**

- `ConnectionCallback` lets you call `createArrayOf` on the exact connection used by `PreparedStatement`. `JdbcTemplate` still manages the connection lifecycle and translates `SQLException` into the appropriate `DataAccessException` hierarchy.
- `PGobject.setType("item_state")` and `setType("jsonb")` inform the driver of the PostgreSQL type. Java cannot automatically infer the SQL enum type from `ItemState`.
- `INSERT ... RETURNING id` is a **PostgreSQL-specific** way to retrieve the generated key after insert; the example does not treat an ID as proof that unrelated business workflows succeeded.
- `RowMapper` uses `getArray`, `getString`, and `ItemState.valueOf`; if JSON violates the expected schema or the enum gains a new label, handle errors explicitly.
- Jackson parses `JSONB` after reading, so logic does not depend on key ordering or whitespace reformatted by PostgreSQL.

Once `schema.sql` has been executed, use JDK 17+ and a compatible Gradle version:

```bash
gradle run --quiet
```

If the project has a Gradle Wrapper, use `./gradlew run --quiet` on Linux/macOS or `gradlew.bat run --quiet` on Windows.

With a freshly reset schema, the expected **stdout from the Java program** is:

```text
Title: Sample
State: READY
Tags: [spring, jdbc, json]
JSON priority: 2
JSON source: lesson
Query matched: true
```

The program omits printing `id` to avoid sequence dependency. If run multiple times without resetting the database, it inserts additional rows while stdout still reflects the newly inserted row thanks to `WHERE id = ?`. The demo does not self-verify against a production deployment environment; run integration tests against your target PostgreSQL/driver.

## 6. Writing Concisely with JdbcTemplate and NamedParameterJdbcTemplate

The full example above uses `ConnectionCallback` because creating a SQL ARRAY requires the connection. When the SQL type can be specified via an **explicit cast**, you can keep Spring's higher-level API style:

```java
// Illustrative code in a repository that already has namedJdbc and id.
String sql = """
    UPDATE catalog_item
       SET state = CAST(:state AS item_state),
           properties = CAST(:json AS jsonb)
     WHERE id = :id
    """;

MapSqlParameterSource params = new MapSqlParameterSource()
    .addValue("state", ItemState.ARCHIVED.name())
    .addValue("json", "{\"priority\":3,\"source\":\"api\"}")
    .addValue("id", id);

int updated = namedJdbc.update(sql, params);
```

This is an **illustrative DAO snippet**, not a standalone Java file: it requires `NamedParameterJdbcTemplate namedJdbc`, `id`, `ItemState`, and `MapSqlParameterSource`. `CAST(:json AS jsonb)` is clearer in SQL with named parameters; JSON is still bound as a parameter value.

When the driver requires a specific JDBC code, Spring also provides:

```java
// Options for passing SQL type metadata; choice depends on the API.
new SqlParameterValue(Types.OTHER, dbSpecificValue);

new MapSqlParameterSource()
    .addValue("payload", dbSpecificValue, Types.OTHER);
```

These are illustrative *parameter values*; imports required are `org.springframework.jdbc.core.SqlParameterValue`, `org.springframework.jdbc.core.namedparam.MapSqlParameterSource`, and `java.sql.Types`. Specifying `Types.OTHER` does not substitute for passing a `PGobject` with the right `setType` or an appropriate SQL cast.

When calling stored procedures with `ARRAY`/`STRUCT` `IN`/`OUT` parameters, Spring offers `SqlTypeValue`/`AbstractSqlTypeValue` to create specialized objects on the active connection, and `SqlReturnType` to convert return values. These typically appear in `SqlParameter`/`SqlOutParameter` combined with `SimpleJdbcCall`. Never assume every driver supports `Connection.createStruct` or `Connection.createArrayOf` for every database type.

## 7. Database-Specific Types: DOMAIN, Composite, Range, UUID…

"Custom types" encompass several distinct categories; do not lump every type into `PGobject` mechanically.

### 7.1. PostgreSQL DOMAIN

```sql
CREATE DOMAIN positive_amount AS NUMERIC(12,2)
    CHECK (VALUE >= 0);
```

A `DOMAIN` is based on an underlying type (here `NUMERIC`) plus constraints. The application can bind with `BigDecimal` depending on context, and the database checks the `CHECK` constraint. When a parameter's type is ambiguous, a cast can help:

```sql
SELECT CAST(? AS positive_amount);
```

Do not confuse domains with enums: a domain can map to its underlying Java type, whereas an enum has a discrete set of labels. `CHECK` violations must be translated into appropriate business-contract errors.

### 7.2. PostgreSQL Composite and Range

```sql
CREATE TYPE shipping_address AS (
    city TEXT,
    postal_code TEXT
);

CREATE TABLE delivery_slot (
    id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    allowed_numbers int4range NOT NULL
);
```

- `shipping_address` is a **composite type**. JDBC has `java.sql.Struct`/`SQLData` interfaces, yet support for `createStruct`, `getObject`, and composite mapping **varies across drivers**. pgJDBC may read unknown types as a `PGobject` containing a text representation; the application needs tested conversion logic or SQL projections selecting individual fields.
- `int4range` is a PostgreSQL **range type**, completely different from a two-element `integer[]`. `[10,20)` represents an interval inclusive of lower bound 10 and exclusive of upper bound 20; ranges also have empty representations, unbounded ends, and dedicated operators. It can be bound via `PGobject` if the driver/SQL supports that type:

```java
// Illustrative snippet for a PostgreSQL int4range column.
PGobject bounds = new PGobject();
bounds.setType("int4range");
bounds.setValue("[10,20)");
jdbc.update(
    "INSERT INTO delivery_slot(allowed_numbers) VALUES (?)",
    bounds
);
```

- PostgreSQL `uuid` is conveniently mapped by pgJDBC to `java.util.UUID` via `setObject`/`getObject(..., UUID.class)`. However, do not conclude every DBMS has a native UUID type or identical mapping.
- Types like `inet`/`cidr`, `hstore` extension, `tsvector`, and PostGIS `geometry`/`geography` require inspecting the specific SQL type, driver, and extension library. Only use wrappers that match supported formats and query operators.

### 7.3. Oracle and MySQL Do Not Share PostgreSQL's Contract

- Oracle has collections/UDTs such as `VARRAY`, nested tables, and object types. Some cases use `OracleConnection.createOracleArray(typeName, elements)` via `connection.unwrap(OracleConnection.class)` per Oracle JDBC documentation, instead of assuming JDBC `createArrayOf` works identically to PostgreSQL.
- MySQL offers `JSON` and `ENUM` types with their own storage/SQL rules. You cannot copy `CREATE TYPE item_state AS ENUM`, `jsonb @>`, `PGobject`, `text[]`, or `int4range` to MySQL and expect it to run.
- SQL Server, Oracle, PostgreSQL, and their drivers can differ in `ResultSet.getObject` return types, `NULL` binding, encoding/timezone handling, and metadata access. When switching DBMSs, update **DDL, SQL, JDBC mappings, and integration tests**, not just the connection string.

## 8. Crucial Boundaries When Working with Special Types

### 8.1. NULL, Empty Values, and Invalid Data

- **ARRAY:** SQL `NULL` differs from an empty `{}` array and from an array containing `NULL` elements.
- **ENUM:** `"READY"` is a valid label in the example schema; `"ready"` is not a matching label unless mapped explicitly; `"UNKNOWN"` may be rejected by the database.
- **JSONB:** SQL `NULL` differs from JSON `null`, object `{}` differs from array `[]`; the schema check `jsonb_typeof(properties)='object'` in the demo rejects scalars/arrays yet **does not validate** individual domain fields.
- **CUSTOM:** a negative value for `positive_amount` violates the constraint; malformed range syntax or wrong type causes driver/server errors.

With prepared statements, `ps.setNull(index, Types.ARRAY)`, `Types.OTHER`, or `ps.setObject(index, null)` can behave differently; when needed, supply explicit SQL types/casts/type names and test the driver. Never substitute `""`, `"null"`, or an empty array for SQL NULL unless specified by the domain.

### 8.2. Transactions and Consistency

Whether a column is JSONB or ENUM, `INSERT`/`UPDATE` statements executed by Spring JDBC still abide by the active connection's transaction boundaries. When a service uses `@Transactional` through a proper proxy, statements in the same transaction typically commit or roll back together. Binding JSON/ARRAY successfully **does not prove the transaction committed**, nor does payload parsing/serialization replace business outcome verification.

If a `PGobject` is constructed with the wrong type, an enum label does not exist, or JSONB has syntax errors, the database may raise `SQLException`. `JdbcTemplate` normally translates it to `DataAccessException`; never swallow conversion errors and return "saved successfully". Schema/version mismatch errors should be logged with adequate context (type name, operation, correlation ID) while avoiding logging sensitive JSON payloads in full.

### 8.3. Performance and Schema Design

Using JSONB/ARRAY is not automatically faster or more flexible than a relational schema:

- Filtering by array elements, JSONB keys, or ranges depends on indexes, data selectivity, and operators; `EXPLAIN (ANALYZE, BUFFERS)` in a realistic environment beats guesswork.
- Large JSONB columns updated frequently can increase write/WAL/TOAST overhead; consider relational columns for frequently updated, filtered, or joined fields.
- Database enums suit stable label sets, yet adding/renaming labels requires migrations and version compatibility. For rapidly changing statuses, a lookup/reference table may fit better.
- SQL ARRAYs are convenient for short, homogeneous lists with few joins. Data with rich relationships, ordering, or per-element metadata may need a child table.
- Custom types are handy when strong SQL constraints/functions are desired, but increase DBMS lock-in. Document that trade-off in architecture notes.

## 9. Testing Mappings at the Real Boundary

A meaningful integration test must run against **the same database family and driver** used in production. Test scenarios should include:

1. **Normal ARRAY:** write and read `["spring","jdbc"]` with all elements in order; `@>` query returns expected rows.
2. **Empty/NULL ARRAY:** distinguish `new String[0]`, SQL `NULL`, and `NULL` elements; test multi-dimensional arrays if actually used.
3. **Valid/invalid ENUM:** `READY` round-trips; unknown labels are rejected; Java reading a newly added label follows defined compatibility rules.
4. **Valid JSON:** nested objects, Unicode, numbers, booleans, and arrays; read back with a JSON parser and compare structure, not raw strings.
5. **Invalid JSON:** missing quotes/braces, violating `CHECK` type, JSON `null` vs. SQL NULL; verify error handling.
6. **Custom types:** violated domain constraints, boundary ranges, UUIDs, and composite mappings if used in the project.
7. **Transactions:** when one statement fails, updates in the same transaction roll back; verify from an independent transaction/connection.
8. **Security & operations:** all values bound via parameters, never interpolating input JSON/enum/ARRAY literals into SQL; enforce payload size limits and sensible timeouts.

With Spring Boot/JUnit, you can use Testcontainers PostgreSQL to spin up a real DB for tests; H2 or mock databases usually **do not accurately emulate** PostgreSQL enums, JSONB, custom ranges, and pgJDBC. Without a running PostgreSQL in tests, you can only claim syntax verification, not real DB behavior.

## 10. Summary of How to Choose Mappings

| DB Data Type | Spring JDBC Starting Point | Priority Checks |
| --- | --- | --- |
| PostgreSQL `text[]`/`integer[]` | `Connection.createArrayOf` + `ps.setArray`; read `rs.getArray` | Element type name, NULL/empty, `Array.free()` |
| PostgreSQL enum | `PGobject` with right type or SQL `CAST(? AS enum_type)`; `getString` then parse Java enum | Label/version/case, schema privileges |
| PostgreSQL JSONB | `PGobject("jsonb")` or `CAST(? AS jsonb)`; `getString` + Jackson | SQL NULL vs. JSON null, validation, query operators |
| DOMAIN | Bind underlying type, cast when needed | Constraints and scale/precision |
| Composite/`STRUCT` | Driver extension or JDBC `Struct` when supported | Metadata, field order, driver compatibility |
| Range/`inet`/UDT | SQL cast, `PGobject`, or dedicated driver/type library | Exact representation and DB-specific operators |
| Oracle collection/UDT | Oracle JDBC extension / `SqlTypeValue` | SQL type name, unwrap connection, driver API |

**Principle:** Design and test mappings across all three sides: **Java ↔ JDBC/Spring ↔ database**. Never infer that using `setObject` or `Types.OTHER` makes Spring understand every special type automatically, nor treat successfully reading back a JSON/enum string as proof the data satisfies business rules.

### References

- [Spring Framework — JDBC parameter handling and complex SQL types](https://docs.spring.io/spring-framework/reference/6.2/data-access/jdbc/parameter-handling.html)
- [Spring Framework — JdbcTemplate API](https://docs.spring.io/spring-framework/docs/6.2.19/javadoc-api/org/springframework/jdbc/core/JdbcTemplate.html)
- [pgJDBC — PostgreSQL-specific JDBC extensions and arrays](https://jdbc.postgresql.org/documentation/server-prepare/)
- [pgJDBC — Query and question-mark operator escaping](https://jdbc.postgresql.org/documentation/query/)
- [PostgreSQL — Arrays](https://www.postgresql.org/docs/16/arrays.html)
- [PostgreSQL — Enumerated types](https://www.postgresql.org/docs/16/datatype-enum.html)
- [PostgreSQL — JSON types](https://www.postgresql.org/docs/16/datatype-json.html)
- [PostgreSQL — CREATE TYPE](https://www.postgresql.org/docs/16/sql-createtype.html)
