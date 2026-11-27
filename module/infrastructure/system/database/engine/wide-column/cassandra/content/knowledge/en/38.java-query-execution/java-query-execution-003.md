# Positional and Named Binding and Type Checking in the Cassandra Java Driver

> **Chapter:** Query Execution from Java  
> **Focus:** Using `PreparedStatement`/`BoundStatement` in Apache Cassandra Java Driver 4.x to bind values by position (`?`) or name (`:name`), verifying CQL types from metadata, distinguishing `NULL`/`UNSET`, checking Java codecs, and avoiding ordering/type bugs that make queries return incorrect data. Examples follow the Driver 4.17 API and are conceptually compatible with the Apache 4.18 branch; verify the exact version in use before applying to production.

## 1. Learning objectives

After this lesson, learners can:

1. Describe the **`prepare → bind → execute → decode`** lifecycle and the role of metadata in the Cassandra Java Driver.
2. Write CQL with anonymous `?` markers, bind by **0-based index** using `bind(...)`/`setXxx(index, ...)`, and recognize when ordering is error-prone.
3. Write named markers `:tenant`, `:day`, use `setXxx("name", ...)`, and handle repeated column names/quoted identifiers without equating marker names with column names.
4. Read `PreparedStatement.getVariableDefinitions()`, verify marker order, names, and **CQL DataTypes**, and distinguish driver validation from business validation.
5. Choose the right setters/getters for `text`, `int`, `bigint`, `decimal`, `date`, `timestamp`, `uuid`/`timeuuid`, `blob`, and collections/UDTs.
6. Distinguish `setToNull` from `unset` and their impact on **primary keys, tombstones, TTL**, and partial updates.
7. Write a complete Java example using one `CqlSession` and multiple prepared statements, setting a consistency level appropriate for RF and verifying read-back results.
8. Design intentional negative tests to catch **swapped same-type values**, **codec mismatches**, **wrong marker names**, **duplicate names**, and **timezone mismatches** before production data is written incorrectly.
9. Connect **partition key → routing key → token → natural replicas** properly rather than treating binding as mere string substitution.

**Scope within `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA`:** Apache Cassandra is a distributed wide-column database. Table schemas are typically query-driven; partition keys determine tokens/replicas, and read/write consistency choices remain critical when calling from Java. Incorrect binding does not always throw an exception: sometimes a query **succeeds yet hits the wrong partition**, which is more dangerous than a fail-fast type error.

## 2. Big picture: prepare, bind, execute

~~~text
         Java service / Repository
                   |
         CQL with bind markers
          ?           :name
                   |
            session.prepare()
                   |
           PREPARE to Cassandra
             schema / types
                   |
        PreparedStatement (reusable)
             |              |
        bind(...)        bind() then
        by position      setXxx(name)
             |              |
             +------+-------+
                    |
          Immutable BoundStatement
          encoded values + metadata
                    |
            session.execute(...)
                    |
           Coordinator and replicas
                    |
                ResultSet
                    |
            Row.getXxx(...) typed
~~~

### 2.1. A prepared statement is not SQL string concatenation

Suppose:

~~~java
String cql =
    "SELECT event_id, status FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ?";

PreparedStatement prepared = session.prepare(cql);
BoundStatement request =
    prepared.bind("tenant-a", LocalDate.parse("2026-11-21"));
ResultSet result = session.execute(request);
~~~

The CQL text is parsed during `prepare`, and the driver sends the **prepared ID + values serialized according to CQL types** during `execute`. It does not build a new text statement by replacing `?` with `'tenant-a'`. Thanks to metadata from PREPARE, the driver can validate codecs and compute routing keys when all partition-key components are supplied. See [Java Driver — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/).

### 2.2. Key components

| Component | Role | Do not mistake it for |
|---|---|---|
| `CqlSession` | Connections, pools, metadata, and CQL execution; reused across the app | A new session per query |
| `PreparedStatement` | Prepared query + variable/type/routing metadata | An already-executed CQL result |
| `BoundStatement` | Prepared statement with concrete values, ready to execute | A SQL string with concatenated literals |
| `BoundStatementBuilder` | Constructs a bound object; setters mutate the builder, then `build()` | An object safe to share across threads while mutating |
| `ColumnDefinitions` | Describes names/types/slots of bind vars or result cols | Full table schema or version history |
| `TypeCodec` | Encodes/decodes a CQL type ↔ Java type | Business validation for all input data |
| `Row` | Result row containing typed values + column metadata | An automatically mapped Java entity |

**Separate failure phases:** Invalid CQL or missing schema is usually caught at `prepare`; Java/CQL type mismatches typically happen at **bind**; timeouts, quorum failures, or authorization errors happen at **execute**; calling the wrong `Row` getter or casting incorrectly fails at **decode**.

### 2.3. Mental checklist before each statement

~~~text
1. Which CQL query serves this exact access pattern?
2. How many bind markers exist and in what order?
3. Which marker names are unique? Are any markers repeated?
4. What CQL type does metadata report for each marker?
5. Do Java DTO fields match type, precision, and timezone?
6. Should this field be null, unset, or fail validation?
7. Are all partition keys bound and CL/idempotency set properly?
8. Execute and decode results with the matching getters?
9. Verify primary key and business values?
~~~

## 3. Baseline CQL schema for examples

This lesson uses a **single-node Cassandra lab** to focus on binding rather than throughput. On multi-datacenter clusters, use `NetworkTopologyStrategy` with real RF/DCs and reviewed consistency levels.

~~~sql
CREATE KEYSPACE IF NOT EXISTS java_bind_lab
WITH replication = {
  'class': 'SimpleStrategy',
  'replication_factor': 1
};

CREATE TABLE IF NOT EXISTS java_bind_lab.events_by_tenant_day (
  tenant_id text,
  day date,
  event_time timestamp,
  event_id uuid,
  status text,
  amount decimal,
  note text,
  tags set<text>,
  PRIMARY KEY ((tenant_id, day), event_time, event_id)
) WITH CLUSTERING ORDER BY (
  event_time DESC,
  event_id ASC
);

CREATE TABLE IF NOT EXISTS java_bind_lab.customer_profiles (
  tenant_id text,
  customer_id uuid,
  name text,
  age int,
  active boolean,
  updated_at timestamp,
  PRIMARY KEY ((tenant_id), customer_id)
);
~~~

### 3.1. Two key groups to remember

| Table | Partition key | Clustering key | Example matching query |
|---|---|---|---|
| `events_by_tenant_day` | `(tenant_id, day)` | `(event_time, event_id)` | Events for a tenant on a day or a specific event |
| `customer_profiles` | `tenant_id` | `customer_id` | A customer's profile within a tenant |

In `events_by_tenant_day`, the Java values `tenantId:String` and `day:LocalDate` **must be bound in the right position or by the right name**. If you swap two positions with different types, the driver usually blocks it at the codec layer; if both are `text` (for example in another table with `region text, tenant_id text`), swapping them can **succeed silently** and route to a completely different partition.

### 3.2. Do not use SimpleStrategy as a production recipe

`SimpleStrategy` RF=1 is only suitable for a single-node demo. With multiple nodes/DCs, configure RF according to the real topology, for example:

~~~sql
-- Illustrative only when DCs named dc1/dc2 actually exist.
CREATE KEYSPACE production_events
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': '3',
  'dc2': '2'
};
~~~

CL is a **request** property; RF is a keyspace property. A properly typed `getUuid("event_id")` getter does not prove every replica holds the data; those are two separate verification layers.

## 4. Positional binding with `?`

### 4.1. Order follows appearance in the CQL text

~~~java
PreparedStatement insert = session.prepare(
    "INSERT INTO java_bind_lab.customer_profiles " +
    "(tenant_id, customer_id, name, age, active, updated_at) " +
    "VALUES (?, ?, ?, ?, ?, ?)");

BoundStatement bound = insert.bind(
    "tenant-a",                                    // slot 0: text
    UUID.fromString("11111111-1111-1111-1111-111111111111"), // 1: uuid
    "Linh",                                        // 2: text
    28,                                            // 3: int
    true,                                          // 4: boolean
    Instant.parse("2026-11-21T04:00:00Z")          // 5: timestamp
);

session.execute(bound);
~~~

**Indices are 0-based**, not 1-based. Positions match the **order of `?` in the statement**, **not** column order in `CREATE TABLE`, `PRIMARY KEY`, or alphabetical order. If someone edits the column list without updating the bind arguments, the query can fail early or persist corrupted data.

### 4.2. Index-based setters

~~~java
BoundStatement bound = insert.bind()
    .setString(0, "tenant-a")
    .setUuid(1, UUID.fromString(
        "11111111-1111-1111-1111-111111111111"))
    .setString(2, "Linh")
    .setInt(3, 28)
    .setBoolean(4, true)
    .setInstant(5, Instant.parse("2026-11-21T04:00:00Z"));
~~~

In Driver 4.x, built-in `BoundStatement` is **immutable**, and every setter returns a **new instance**. The chained code above captures the updated values. The snippet below is wrong:

~~~java
BoundStatement bad = insert.bind();
bad.setString(0, "tenant-a");  // returns a new object that gets discarded
session.execute(bad);          // tenant_id remains UNSET
~~~

Even if the statement executes, an **UNSET PK** is invalid, so the server may reject it. In other mutations, discarding a setter for a regular column can silently omit that column without error, which is even more dangerous. See [Java Driver — Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/) and [Upgrade guide](https://apache.github.io/cassandra-java-driver/4.18.0/upgrade-README/).

### 4.3. Builder: many setters without intermediate allocations

~~~java
BoundStatement request = insert.boundStatementBuilder()
    .setString(0, "tenant-a")
    .setUuid(1, UUID.fromString(
        "11111111-1111-1111-1111-111111111111"))
    .setString(2, "Linh")
    .setInt(3, 28)
    .setBoolean(4, true)
    .setInstant(5, Instant.parse("2026-11-21T04:00:00Z"))
    .setConsistencyLevel(DefaultConsistencyLevel.ONE)
    .build();
~~~

`BoundStatementBuilder` is **mutable** and not thread-safe while building; never share a builder across requests or threads. A built `BoundStatement` is thread-safe in the default implementation, though you should still construct a distinct instance per value set. You can safely share **`PreparedStatement`** across multiple threads.

### 4.4. Reordering the query while forgetting to reorder bindings

~~~java
// Initially:
String cql1 = "SELECT name FROM java_bind_lab.customer_profiles " +
              "WHERE tenant_id = ? AND customer_id = ?";
// bind: (String tenantId, UUID customerId)

// After refactoring:
String cql2 = "SELECT name FROM java_bind_lab.customer_profiles " +
              "WHERE customer_id = ? AND tenant_id = ?";
// MUST update bind order to (UUID customerId, String tenantId).
~~~

In the example above, the driver catches the mismatch if old bindings are kept because `uuid` differs from `text`. However, with two `text` columns, wrong ordering **still encodes cleanly** and can produce empty results or hit the wrong tenant. Type safety is a **necessary but insufficient safeguard**.

## 5. Named binding with `:name` markers

### 5.1. Declaring explicit marker names

~~~java
PreparedStatement insertNamed = session.prepare(
    "INSERT INTO java_bind_lab.customer_profiles " +
    "(tenant_id, customer_id, name, age, active, updated_at) " +
    "VALUES (:tenant, :customer, :full_name, :age_years, " +
    ":is_active, :modified_at)");

BoundStatement named = insertNamed.bind()
    .setString("tenant", "tenant-a")
    .setUuid("customer", UUID.fromString(
        "22222222-2222-2222-2222-222222222222"))
    .setString("full_name", "Minh")
    .setInt("age_years", 31)
    .setBoolean("is_active", true)
    .setInstant("modified_at",
        Instant.parse("2026-11-21T05:00:00Z"));

session.execute(named);
~~~

`:full_name` is a **bind marker** chosen by the query author; it **does not need to match the column name `name`**. When calling the setter, **omit the `:` prefix**: call `setString("full_name", ...)`, not `setString(":full_name", ...)`.

### 5.2. Named setters can also work with `?`

When preparing `INSERT ... (tenant_id, name) VALUES (?, ?)`, Cassandra can infer marker metadata names from the target columns, so:

~~~java
PreparedStatement p = session.prepare(
    "INSERT INTO java_bind_lab.customer_profiles " +
    "(tenant_id, customer_id, name) VALUES (?, ?, ?)");

BoundStatement b = p.bind()
    .setString("tenant_id", "tenant-a")
    .setUuid("customer_id", UUID.fromString(
        "33333333-3333-3333-3333-333333333333"))
    .setString("name", "Thu");
~~~

**However, do not assume inferred marker names always match column names in complex queries.** Inspect `getVariableDefinitions()` or declare `:name` explicitly when clarity matters. Especially with multiple conditions on the same column, inferred names can **collide**. See [Prepared statements — Parameters and binding](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/).

### 5.3. Duplicate marker names and range queries: a major trap

~~~sql
-- Ambiguous query form:
SELECT event_time, status
FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = ?
  AND day = ?
  AND event_time >= ?
  AND event_time < ?;
~~~

The last two markers typically receive the same inferred metadata name `event_time`. Calling `setInstant("event_time", x)` can apply **x to every occurrence** of that name, turning the condition into an empty range `event_time >= x AND event_time < x`. The [SettableByName](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/data/SettableByName.html) API documents that named setters write **all matching occurrences**, not just one.

**Option 1 — Use positional indices for two distinct bounds:**

~~~java
PreparedStatement byRange = session.prepare(
    "SELECT event_time, status " +
    "FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ? " +
    "AND event_time >= ? AND event_time < ?");

BoundStatement window = byRange.bind()
    .setString(0, "tenant-a")
    .setLocalDate(1, LocalDate.parse("2026-11-21"))
    .setInstant(2, Instant.parse("2026-11-21T00:00:00Z"))
    .setInstant(3, Instant.parse("2026-11-22T00:00:00Z"));
~~~

**Option 2 — Declare unambiguous marker names:**

~~~java
PreparedStatement rangeNamed = session.prepare(
    "SELECT event_time, status " +
    "FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = :tenant " +
    "AND day = :target_day " +
    "AND event_time >= :start_time " +
    "AND event_time < :end_time");

BoundStatement windowNamed = rangeNamed.bind()
    .setString("tenant", "tenant-a")
    .setLocalDate("target_day", LocalDate.parse("2026-11-21"))
    .setInstant("start_time", Instant.parse("2026-11-21T00:00:00Z"))
    .setInstant("end_time", Instant.parse("2026-11-22T00:00:00Z"));
~~~

**Practical constraint:** A CQL query must already satisfy partition/clustering restrictions before it can be prepared; placing two range bounds on the same clustering column is valid on the example table. Switching binding style **does not** magically validate queries missing a partition key or misusing `ALLOW FILTERING`.

## 6. CQL identifiers, quoted identifiers, and marker names vs column names

### 6.1. Three kinds of names in one statement

~~~sql
SELECT status
FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = :tenant
  AND day = :report_day;
~~~

| Component | Example | Meaning |
|---|---|---|
| Keyspace/table name | `java_bind_lab.events_by_tenant_day` | Schema identifier |
| Column name | `tenant_id`, `day`, `status` | Column identifier |
| Bind marker name | `tenant`, `report_day` | Key used by the application to attach values |

There is no `setTableName("...")` method to bind a table name with `?` or `:table`. **Bind markers represent values**, not CQL identifiers, `ORDER BY` clauses, or full `WHERE` syntax. In multi-tenant systems, never concatenate table names from HTTP requests; select tables/columns from a **code-defined allowlist** and enforce data authorization in the application/CQL roles.

### 6.2. Unquoted identifiers are canonicalized to lowercase

In CQL:

~~~sql
-- Both forms refer to the same case-insensitive names when unquoted:
SELECT status FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = :Tenant AND day = :TargetDay;

SELECT status FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = :tenant AND day = :targetday;
~~~

With **quoted identifiers**, case becomes significant. If a legacy schema happens to have column `"DisplayName"`, calling `getString("displayname")` vs `getString("\"DisplayName\"")` can behave differently. Driver 4.x uses `CqlIdentifier` to distinguish **CQL text form** from **internal canonical form**:

~~~java
import com.datastax.oss.driver.api.core.CqlIdentifier;

CqlIdentifier ordinary = CqlIdentifier.fromCql("Tenant_ID");
System.out.println(ordinary.asInternal()); // tenant_id

CqlIdentifier quoted =
    CqlIdentifier.fromCql("\"DisplayName\"");
System.out.println(quoted.asInternal());    // DisplayName
~~~

**Design guideline:** prefer **unquoted** snake_case for keyspace, table, column, and marker names. For legacy case-sensitive schemas, use `CqlIdentifier.fromCql(...)` or the matching overloads and inspect returned metadata instead of guessing how the driver converts `String`. See [Case Sensitivity — Apache Java Driver](https://apache.github.io/cassandra-java-driver/4.18.1/case_sensitivity/).

### 6.3. Why named binding is not “completely refactor-proof”

If a query renames `:tenant` to `:tenant_id` while Java still calls `setString("tenant", ...)`, the driver fails with **unknown marker**. That is better than silent corruption, yet you still need tests for statement construction. If you change the **CQL column attached to a marker** without updating DTO mapping, code can still bind a valid String into a **semantically wrong** String column.

Do not rely on the driver “guessing the right column name”: for complex queries, **standardize marker names** and test declared bind variables after `prepare()`.

## 7. Inspecting marker metadata before binding

### 7.1. What does `getVariableDefinitions()` know?

The `PreparedStatement` returned by `session.prepare()` contains `ColumnDefinitions` for the bind markers. Each definition provides:

- **Index** matching the marker's position in CQL.
- **Name** assigned by the server: explicit marker name or context-inferred name.
- **CQL type** expected by Cassandra, such as `text`, `date`, `timestamp`, `uuid`, `decimal`.

Java example:

~~~java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ColumnDefinitions;
import com.datastax.oss.driver.api.core.cql.ColumnDefinition;

PreparedStatement p = session.prepare(
    "SELECT event_time, event_id, status " +
    "FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = :tenant AND day = :report_day");

ColumnDefinitions defs = p.getVariableDefinitions();
for (int index = 0; index < defs.size(); index++) {
    ColumnDefinition def = defs.get(index);
    System.out.printf(
        "index=%d name=%s CQL type=%s%n",
        index, def.getName().asInternal(), def.getType());
}
~~~

Expected output (illustrative):

~~~text
index=0 name=tenant CQL type=text
index=1 name=report_day CQL type=date
~~~

**Do not confuse bind-variable metadata with result-column metadata.** `getVariableDefinitions()` describes **inputs**; `Row.getColumnDefinitions()` describes **returned SELECT columns**. The same name `status` may be a bound variable in an UPDATE and a result column in a SELECT, but they belong to different objects and contexts.

### 7.2. Assert variable count and types rather than just printing

~~~java
import com.datastax.oss.driver.api.core.type.DataTypes;
import com.datastax.oss.driver.api.core.cql.ColumnDefinitions;

static void requireVariables(PreparedStatement p) {
    ColumnDefinitions defs = p.getVariableDefinitions();
    if (defs.size() != 2
            || !defs.contains("tenant")
            || !defs.contains("report_day")
            || !DataTypes.TEXT.equals(defs.get("tenant").getType())
            || !DataTypes.DATE.equals(defs.get("report_day").getType())) {
        throw new IllegalStateException(
            "Prepared query markers no longer match repository contract");
    }
}
~~~

For queries using `?`, marker names may be inferred by the server; the more reliable check is **count and type by index**:

~~~java
static void requirePositionalTypes(PreparedStatement p) {
    ColumnDefinitions defs = p.getVariableDefinitions();
    if (defs.size() != 2
            || !DataTypes.TEXT.equals(defs.get(0).getType())
            || !DataTypes.DATE.equals(defs.get(1).getType())) {
        throw new IllegalStateException("Unexpected bind layout");
    }
}
~~~

**Scope note:** These assertions prove Java code has a **valid CQL type mapping**, not that `"tenant-a"` exists, the user is authorized for `tenant-a`, or `day` uses the right business timezone/bucket. Business validation must be layered separately.

### 7.3. Detecting duplicate marker names before writing

~~~java
ColumnDefinitions defs = rangeQuery.getVariableDefinitions();
for (int i = 0; i < defs.size(); i++) {
    String name = defs.get(i).getName().asInternal();
    if (defs.allIndicesOf(name).size() > 1) {
        System.out.printf(
            "ambiguous named binding: %s at slots %s%n",
            name, defs.allIndicesOf(name));
    }
}
~~~

For `event_time >= ? AND event_time < ?`, this warning shows `event_time` appearing twice. Do not assume the query itself is invalid: **positional setters** can still populate the two slots independently. It serves as a guard against **calling the same named setter** for two semantically distinct values. `ColumnDefinitions.allIndicesOf` detects duplicates rather than returning only `firstIndexOf`.

### 7.4. Schema changes after prepare

A prepared statement holds metadata from prepare time. For compatible schema changes, the driver/server can refresh or reprepare depending on version/protocol; for **column type changes or dropped/recreated columns/tables**, never assume old objects remain valid forever.

Runbook for type/schema changes:

1. Apply CQL schema changes via a dedicated migration plan and wait for schema agreement.
2. Ensure running JVMs have compatible query text, DTOs, and codecs.
3. Run prepare/bind/execute integration tests against the target cluster.
4. Avoid `SELECT *` in code requiring stable metadata across schema evolution.
5. Verify results and failure rates after deploy; watch for `UNPREPARED` and codec mismatch errors.

**The driver will not turn `setString` into `setInstant`** if the DB alters a column from text to timestamp. Schema migrations must update code, codecs, and data policies—not just retry queries.

## 8. CQL ↔ Java mapping table: choosing setters and getters

| CQL type | Common Java type | Bound statement setter | `Row` getter | Watch out for |
|---|---|---|---|---|
| `ascii`, `text`, `varchar` | `String` | `setString` | `getString` | UTF-8 Unicode; no automatic trim/casefolding |
| `boolean` | `boolean`/`Boolean` | `setBoolean` | `getBoolean` | Primitive getter returns false on NULL; check `isNull` |
| `tinyint` | `byte`/`Byte` | `setByte` | `getByte` | Range -128..127 |
| `smallint` | `short`/`Short` | `setShort` | `getShort` | Range -32768..32767 |
| `int` | `int`/`Integer` | `setInt` | `getInt` | NULL vs 0; overflow when parsing |
| `bigint`/`counter` | `long`/`Long` | `setLong` | `getLong` | Counter UPDATE has different semantics from upserts |
| `varint` | `BigInteger` | `setBigInteger` | `getBigInteger` | Do not silently downcast to long |
| `decimal` | `BigDecimal` | `setBigDecimal` | `getBigDecimal` | Never use float/double for money |
| `float` | `float` | `setFloat` | `getFloat` | IEEE-754 precision/NaN policy |
| `double` | `double` | `setDouble` | `getDouble` | Not a substitute for business `decimal` |
| `uuid`/`timeuuid` | `UUID` | `setUuid` | `getUuid` | `timeuuid` requires a valid version-1 UUID |
| `date` | `LocalDate` | `setLocalDate` | `getLocalDate` | Contains no timezone or time of day |
| `time` | `LocalTime` | `setLocalTime` | `getLocalTime` | Contains no date or timezone |
| `timestamp` | `Instant` | `setInstant` | `getInstant` | Absolute instant; CQL stores millisecond precision |
| `duration` | `CqlDuration` | `setCqlDuration` | `getCqlDuration` | Distinct from `java.time.Duration` |
| `inet` | `InetAddress` | `setInetAddress` | `getInetAddress` | Verify IPv4/IPv6 expectations |
| `blob` | `ByteBuffer` | `setByteBuffer` | `getByteBuffer` | Position/limit semantics; do not assume backing array |
| `list<text>` | `List<String>` | `setList(..., String.class)` | `getList(..., String.class)` | Ordered CQL list with specific update semantics |
| `set<text>` | `Set<String>` | `setSet(..., String.class)` | `getSet(..., String.class)` | Uniqueness; iteration order is not guaranteed |
| `map<text,int>` | `Map<String,Integer>` | `setMap(..., String.class, Integer.class)` | `getMap(..., String.class, Integer.class)` | No null keys or values |
| `tuple<...>` | `TupleValue` | `setTupleValue` | `getTupleValue` | Field order is part of the contract |
| UDT | `UdtValue` | `setUdtValue` | `getUdtValue` | Field names/types must match schema |

Consult [Core Driver — CQL to Java type mapping](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/) for version alignment. The codec registry is extensible, yet each mapping must pair the **exact CQL type and Java type**; never assume the driver auto-converts any `String` into UUID, decimal, or timestamp.

### 8.1. Type mismatches that fail early

~~~java
PreparedStatement p = session.prepare(
    "SELECT status FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = :tenant AND day = :target_day");

// CORRECT: day is CQL date, mapped to Java LocalDate.
BoundStatement good = p.bind()
    .setString("tenant", "tenant-a")
    .setLocalDate("target_day", LocalDate.parse("2026-11-21"));

// WRONG (under default codecs):
// p.bind().setString("target_day", "2026-11-21");
// CQL date has no default String setter codec.
~~~

A string that looks like a date **is not** automatically a `LocalDate`. Parse and validate at the application boundary, passing only validated typed objects to the bound statement.

### 8.2. Fail-fast checks and the gaps that remain

| Check type | Enforced by | Example |
|---|---|---|
| Marker/value count | Driver | Passing too many values to `bind(Object...)` throws |
| Marker name/index | Driver | `setString("typo", ...)` not in metadata |
| CQL↔Java codec type | Driver/codec registry | `setUuid` on a `date` column |
| Primary key validity | Cassandra/CQL rules | NULL/UNSET in partition key |
| Business constraints | Application | Tenant authorization, `age >= 0` |
| Consistency/availability | Replicas/CL/coordinator | RF3 `LOCAL_QUORUM` missing a replica |
| End-to-end correctness | Tests/reconciliation | Not swapping two `text` fields of the same type |

**Do not equate successful binding with a valid write:** the driver checks encoding, not whether `customer_id` belongs to `tenant_id`, whether `NEW → PAID` is a legal state transition, or whether an event timestamp falls into the right day partition.

## 9. `bind(Object...)`, named setters, and generic `set`: picking the safe style

### 9.1. Prefer typed setters when code needs clear reviewability

~~~java
BoundStatement b = p.bind()
    .setString("tenant", tenantId)
    .setLocalDate("target_day", day);
~~~

Typed named setters show the mapping right at the bind site, making review much safer than `bind(tenantId, day)` as marker counts grow. Conversely, `bind(Object...)` is concise and fine for small statements **when protected by metadata/order tests**.

### 9.2. Generic overload with type hints

~~~java
// Example for a CQL decimal marker:
BoundStatement b = decimalPrepared.bind()
    .set("amount", new BigDecimal("1200.50"), BigDecimal.class);
~~~

For nested generic collections where `Class` cannot express element types, use `GenericType<T>`; for custom codecs, pass a registered/verified `TypeCodec<T>`:

~~~java
import com.datastax.oss.driver.api.core.type.reflect.GenericType;

GenericType<List<String>> listOfText = new GenericType<List<String>>() {};
BoundStatement b = listPrepared.bind()
    .set("labels", List.of("new", "paid"), listOfText);
~~~

Only use the snippet above when `labels` is `list<text>` on the target table. The lab table `events_by_tenant_day` defines `tags set<text>`, so **never** call `setList("tags", ...)` on it; use `setSet("tags", ...)`.

### 9.3. `bind(Object...)` accepts fewer values than markers

Driver 4.x allows `prepared.bind()` or `bind(v0, v1)` with **fewer** values than markers; remaining slots stay **UNSET** when the protocol supports it. Passing **more values than markers** is rejected by the driver. <https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/cql/PreparedStatement.html>

This does not mean “you can omit any parameter freely”. If an UNSET slot is a partition key or a value needed in WHERE, execution can fail server-side. In UPDATEs, UNSET on a regular column can intentionally mean “leave this field untouched”; validation must reflect **statement type and business semantics**.

## 10. `NULL`, `UNSET`, and Java `null`: three concepts never to mix

### 10.1. States of a bind variable

| State | How created | In UPDATE of a regular column | In a partition-key marker |
|---|---|---|---|
| Concrete value | `setString("name", "Linh")` | Writes the new value | Used to locate partition |
| **CQL NULL** | `setToNull("name")` or passing null to a nullable setter | May create a **tombstone**/delete old value | Invalid |
| **UNSET** | `bind()` not set; `unset(index)` | Column is skipped (no tombstone from UNSET) | Invalid for required keys |

**Never equate “field omitted in JSON PATCH” with “send CQL NULL”.** An omitted field normally means **no change**; a field explicitly sent as null may mean **clear/delete** per API contract. Both behaviors must be explicitly coded.

### 10.2. Selective profile update example

~~~java
PreparedStatement update = session.prepare(
    "UPDATE java_bind_lab.customer_profiles " +
    "SET name = :new_name, age = :new_age, active = :new_active " +
    "WHERE tenant_id = :tenant AND customer_id = :customer");

UUID id = UUID.fromString(
    "11111111-1111-1111-1111-111111111111");

// PATCH: update name only, leave age/active untouched.
BoundStatement patch = update.bind()
    .setString("tenant", "tenant-a")
    .setUuid("customer", id)
    .setString("new_name", "Linh Trần");

// new_age and new_active remain UNSET.
session.execute(patch);
~~~

With native protocol V4+ and an UPDATE supporting UNSET, `age` and `active` are neither deleted nor rewritten. On the same API, if you call:

~~~java
BoundStatement eraseAge = update.bind()
    .setString("tenant", "tenant-a")
    .setUuid("customer", id)
    .setToNull("new_age");

session.execute(eraseAge);
~~~

The `age` field is explicitly cleared (CQL NULL/tombstone), which **differs** from `new_age` being UNSET. Whether clearing a customer's age is allowed must be enforced by business validation; the driver does not know which fields are nullable.

### 10.3. Preventing Java `null` from being misinterpreted

`bind(..., null)` and `setString("note", null)` can encode **CQL NULL** depending on the codec, rather than “omitting the marker”. When implementing a `PATCH` API, never pass all DTO fields straight to `bind(Object...)` if Java `null` is overloaded for both **absent** and **clear**.

Explicit three-state model:

~~~java
sealed interface PatchField<T>
        permits PatchField.Unspecified,
                PatchField.Clear,
                PatchField.Value {
    record Unspecified<T>() implements PatchField<T> {}
    record Clear<T>() implements PatchField<T> {}
    record Value<T>(T value) implements PatchField<T> {}
}
~~~

Applied to `new_name`:

~~~java
static BoundStatement applyName(
        BoundStatement statement, PatchField<String> field) {
    if (field instanceof PatchField.Unspecified<?>) {
        return statement.unset("new_name");
    }
    if (field instanceof PatchField.Clear<?>) {
        return statement.setToNull("new_name");
    }
    if (field instanceof PatchField.Value<?> value) {
        return statement.setString(
            "new_name", (String) value.value());
    }
    throw new IllegalStateException("Unsupported patch field");
}
~~~

In production code, generics/validation should ensure `Value` never wraps null and all inputs pass authorization and field-allowlist checks. The example merely illustrates the semantics: **absent → UNSET**, **clear → NULL**, **value → typed value**.

### 10.4. Checking `isSet` and `isNull`

~~~java
BoundStatement b = update.bind()
    .setString("tenant", "tenant-a")
    .setUuid("customer", id)
    .setToNull("new_age");

System.out.println(b.isSet("new_age")); // true
System.out.println(b.isNull("new_age")); // true
System.out.println(b.isSet("new_name")); // false (UNSET)
~~~

`isSet` reports whether a variable has been set; `isNull` reports NULL status. Check `isSet` **before reading getters on an UNSET slot**. Notably, with duplicate marker names, `isSet(name)`/`unset(name)` on `Bindable` operate on the **first occurrence**, whereas `setXxx(name)` on `SettableByName` writes **all occurrences**. Therefore **never reuse the same name to encode multiple distinct values**; check `allIndicesOf(name)` and use indices when needed. See [Bindable 4.17 API](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/cql/Bindable.html).

### 10.5. Important exceptions to watch

- **Primary key:** must not be NULL/UNSET if the statement needs the key to identify a row; reject invalid input at the boundary.
- **LWT `IF ...`:** UNSET is not a wildcard in conditions; verify rules per marker position.
- **TTL:** NULL can generate a tombstone while UNSET generally skips updating the field. Do not assume every TTL operation behaves identically.
- **Counter:** do not replace increments with NULL/UNSET arbitrarily; counters have dedicated mutation rules.
- **Collections:** NULL, empty collections, and UNSET have distinct semantics; review schema, CQL syntax, and version.
- **Protocol:** UNSET requires native protocol V4 (Cassandra 2.2+). Older protocols do not allow omitting required variables.

## 11. Primitive getters and the “NULL turns into 0/false” bug

A subtle issue that surfaces only on **reads**:

~~~java
Row row = session.execute(selectCustomer).one();

// Dangerous if age is nullable:
int age = row.getInt("age");
// When CQL age = NULL, the primitive getter defaults to 0.
// 0 can be mistaken for a real age or sentinel value.
~~~

Primitive getters `getInt`, `getLong`, `getBoolean` cannot return Java `null`. On CQL NULL, they return default `0`/`false`; use `row.isNull(...)` or wrapper types:

~~~java
Integer age = row.isNull("age")
    ? null
    : row.getInt("age");

Boolean active = row.isNull("active")
    ? null
    : row.getBoolean("active");

// Or if the driver provides the matching codec:
Integer age2 = row.get("age", Integer.class);
~~~

**Business bug:** If you write `if (age == 0) ...` to mean “age not yet set”, you have conflated `NULL` and `0`. DTO/REST/GraphQL contracts must preserve this distinction if business rules require it.

### 11.1. Nullable primitives vs collections

Some built-in collection codecs decode CQL NULL as an **empty collection** per codec policy; do not infer from `getSet("tags")` returning empty that an empty CQL set was explicitly stored. When distinguishing NULL from empty matters, check `row.isNull("tags")` and verify your driver version's semantics. <https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/>

## 12. Dates, times, and precision: valid types do not guarantee valid business logic

### 12.1. Three distinct types

| CQL | Java | Meaning |
|---|---|---|
| `date` | `LocalDate` | A **calendar date** with no time of day or timezone |
| `time` | `LocalTime` | Time of day with no date or timezone |
| `timestamp` | `Instant` | An absolute point in time; CQL timestamp stores millisecond resolution |

Example:

~~~java
LocalDate localBusinessDay =
    LocalDate.parse("2026-11-21");

Instant absoluteEventTime =
    Instant.parse("2026-11-21T08:00:00Z");

BoundStatement event = insertEvent.bind()
    .setLocalDate("target_day", localBusinessDay)
    .setInstant("event_time", absoluteEventTime);
~~~

A Java `Instant` has nanosecond precision, whereas Cassandra `timestamp` stores **milliseconds**; micro/nanoseconds are truncated on round-trip. If business rules require sub-millisecond ordering, consider `timeuuid`, a sequence/version column, or a dedicated precision field.

### 12.2. Timezone conversion must happen at the boundary

Suppose a client submits:

~~~text
2026-11-21T00:30:00+07:00
~~~

The corresponding absolute instant is:

~~~text
2026-11-20T17:30:00Z
~~~

Java code:

~~~java
import java.time.OffsetDateTime;
import java.time.ZoneId;

OffsetDateTime submitted =
    OffsetDateTime.parse("2026-11-21T00:30:00+07:00");
Instant stored = submitted.toInstant();

LocalDate utcDay = stored.atZone(
    ZoneId.of("UTC")).toLocalDate();
LocalDate vietnamDay = stored.atZone(
    ZoneId.of("Asia/Ho_Chi_Minh")).toLocalDate();
~~~

In this example, the **UTC day is 2026-11-20**, whereas the **Vietnam local day is 2026-11-21**: the exact same `Instant` lands in two different day buckets. Define explicitly whether `day` is UTC day or business-local day. Never parse a `LocalDateTime` and casually treat it as UTC.

### 12.3. Timezone bugs do not throw CodecException

If the app binds `day=2026-11-20` instead of `2026-11-21` due to a wrong timezone policy, the driver still encodes a valid `LocalDate`. The CQL query simply returns 0 rows without any type error. This is a prime example of why **type checks cannot replace data validation**.

### 12.4. UUID, timeuuid, and source of identity

~~~java
UUID eventId =
    UUID.fromString("22222222-2222-2222-2222-222222222222");
~~~

`UUID.fromString` only validates UUID syntax, not that the business identity exists; `UUID.randomUUID()` generates v4, which cannot be used for `timeuuid` requiring version 1. When retrying a write for the same event, **you must reuse the same ID** so you do not create logical duplicates; generating a fresh UUID on every retry breaks idempotency.

### 12.5. Decimal, integers, and precision

~~~java
BigDecimal correctMoney = new BigDecimal("1200.50");

// Avoid constructing money from double when exact precision is required:
BigDecimal riskyMoney = new BigDecimal(0.1);
~~~

`new BigDecimal(0.1)` captures the binary floating-point approximation of `double`, not exact decimal `0.1`. For money, parse from validated strings/decimal sources and define scale/rounding policies. Cassandra `decimal` stores arbitrary-precision decimals; Java should use `BigDecimal`, never converting through `float`/`double` for convenience.

`int`, `bigint`, and `varint` have different ranges. Values exceeding `Integer.MAX_VALUE` must never be truncated/cast to fit into `int`; pick the proper schema type and boundary validation from the start.

## 13. Collection binding: the **element** type is also part of the contract

### 13.1. `setSet` on the lab table

~~~java
PreparedStatement tagsInsert = session.prepare(
    "INSERT INTO java_bind_lab.events_by_tenant_day " +
    "(tenant_id, day, event_time, event_id, tags) " +
    "VALUES (:tenant, :target_day, :event_time, :event_id, :tags)");

BoundStatement withTags = tagsInsert.bind()
    .setString("tenant", "tenant-a")
    .setLocalDate("target_day", LocalDate.parse("2026-11-21"))
    .setInstant("event_time",
        Instant.parse("2026-11-21T08:00:00Z"))
    .setUuid("event_id", UUID.fromString(
        "11111111-1111-1111-1111-111111111111"))
    .setSet("tags", Set.of("order", "created"), String.class);
~~~

`tags` has CQL type `set<text>`. Passing `List<String>` or `Set<Integer>` will not cause the registry to silently coerce it into `set<text>`. Use the matching getter:

~~~java
Set<String> tags = row.getSet("tags", String.class);
~~~

`Set` iteration order is not a business contract. When ordering or duplicates are needed, `list` has different semantics; do not alter collection schema types merely for Java convenience.

### 13.2. List and Map

Example **only when the schema defines them**:

~~~sql
CREATE TABLE IF NOT EXISTS java_bind_lab.collection_demo (
  tenant_id text,
  demo_id uuid,
  labels list<text>,
  metrics map<text,int>,
  PRIMARY KEY ((tenant_id), demo_id)
);
~~~

Java:

~~~java
PreparedStatement p = session.prepare(
    "INSERT INTO java_bind_lab.collection_demo " +
    "(tenant_id, demo_id, labels, metrics) " +
    "VALUES (:tenant, :id, :labels, :metrics)");

BoundStatement request = p.bind()
    .setString("tenant", "tenant-a")
    .setUuid("id", UUID.fromString(
        "55555555-5555-5555-5555-555555555555"))
    .setList("labels", List.of("new", "paid"), String.class)
    .setMap("metrics", Map.of("attempts", 1),
        String.class, Integer.class);
~~~

Cassandra collections carry specific update, tombstone, and read-amplification trade-offs. If you need to store many events, **never** replace a wide-column table with clustering keys with a giant list inside one column just because `setList` is convenient.

### 13.3. Nested types and `GenericType`

For nested generic structures (such as `frozen<list<text>>` inside another collection), raw Java `List.class`/`Set.class` lose element type info due to type erasure. Use `GenericType`:

~~~java
import com.datastax.oss.driver.api.core.type.reflect.GenericType;

GenericType<List<String>> labelsType =
    new GenericType<List<String>>() {};

BoundStatement b = p.bind()
    .set("labels", List.of("a", "b"), labelsType);
~~~

Avoid instantiating `new GenericType<...>(){}` millions of times inside hot loops; store an immutable static constant where needed. When using complex nested collections, verify CQL `frozen`/collection compatibility and serializer behavior before production rollout.

## 14. UDT and Tuple: do not bind an arbitrary `Map` or `List`

### 14.1. User-defined types have contractual field names

Lab UDT example:

~~~sql
CREATE TYPE IF NOT EXISTS java_bind_lab.postal_address (
  city text,
  postal_code int
);

CREATE TABLE IF NOT EXISTS java_bind_lab.customer_addresses (
  tenant_id text,
  customer_id uuid,
  address frozen<postal_address>,
  PRIMARY KEY ((tenant_id), customer_id)
);
~~~

**Note:** `frozen<postal_address>` is valid when the type resides in the same keyspace as the table; if using fully qualified references, resolve `java_bind_lab.postal_address` properly. UDTs have strict field order, names, and types; you cannot simply pass a Java `Map.of("city", "...")` and expect `setUdtValue` to know how to encode it.

Java retrieves the definition **from the target schema metadata**:

~~~java
import com.datastax.oss.driver.api.core.type.UserDefinedType;
import com.datastax.oss.driver.api.core.data.UdtValue;

UserDefinedType addressType = session.getMetadata()
    .getKeyspace("java_bind_lab")
    .flatMap(keyspace -> keyspace.getUserDefinedType("postal_address"))
    .orElseThrow(() -> new IllegalStateException("Missing address UDT"));

UdtValue address = addressType.newValue()
    .setString("city", "Hồ Chí Minh")
    .setInt("postal_code", 700000);

PreparedStatement insertAddress = session.prepare(
    "INSERT INTO java_bind_lab.customer_addresses " +
    "(tenant_id, customer_id, address) VALUES (:tenant, :customer, :address)");

BoundStatement b = insertAddress.bind()
    .setString("tenant", "tenant-a")
    .setUuid("customer", UUID.fromString(
        "66666666-6666-6666-6666-666666666666"))
    .setUdtValue("address", address);

session.execute(b);
~~~

**Common mistake:** creating a UDT on cluster A with different fields/order than cluster B, then copying binary/`UdtValue` over to B. Always obtain UDT schema from the **target session/cluster** and map fields explicitly across versions or differing codecs. Never fabricate UDT metadata with internal APIs to “make values fit”. See [UDTs — Cassandra Java Driver](https://apache.github.io/cassandra-java-driver/4.19.0/core/udts/).

### 14.2. Tuple: binding by slot inside the tuple

~~~sql
CREATE TABLE IF NOT EXISTS java_bind_lab.measurements (
  tenant_id text,
  measurement_id uuid,
  coordinate tuple<text,int>,
  PRIMARY KEY ((tenant_id), measurement_id)
);
~~~

Java:

~~~java
import com.datastax.oss.driver.api.core.type.TupleType;
import com.datastax.oss.driver.api.core.data.TupleValue;

PreparedStatement insertMeasurement = session.prepare(
    "INSERT INTO java_bind_lab.measurements " +
    "(tenant_id, measurement_id, coordinate) " +
    "VALUES (:tenant, :mid, :coordinate)");

TupleType coordType = (TupleType) insertMeasurement
    .getVariableDefinitions()
    .get("coordinate")
    .getType();

TupleValue coord = coordType.newValue()
    .setString(0, "floor")
    .setInt(1, 12);

BoundStatement b = insertMeasurement.bind()
    .setString("tenant", "tenant-a")
    .setUuid("mid", UUID.fromString(
        "77777777-7777-7777-7777-777777777777"))
    .setTupleValue("coordinate", coord);
~~~

Tuple slot `0` is `text` and slot `1` is `int` according to the **tuple declaration**, not a map key. Unlike named markers on a CQL statement, tuple fields have no names for `setString("foo")`. If a tuple type changes order in a migration, payload mapping code must change too. See [Tuples — Java Driver](https://apache.github.io/cassandra-java-driver/4.19.0/core/tuples/).

### 14.3. Driver 4.x and immutability

Driver 4.x `UdtValue`/`TupleValue` setters return new instances following built-in immutability conventions. Chain `newValue().setXxx(...).setYyy(...)` or reassign the reference; never call a setter and ignore the return value. With many fields, use type-safe codecs and round-trip tests; avoid relying on `toString()` for business data, as it may expose PII or omit expected formatting.

## 15. Blob, ByteBuffer, and custom TypeCodecs

### 15.1. `blob` does not mean `byte[]`

By default the driver uses `ByteBuffer` for CQL `blob`:

~~~sql
CREATE TABLE IF NOT EXISTS java_bind_lab.binary_objects (
  tenant_id text,
  object_id uuid,
  content blob,
  PRIMARY KEY ((tenant_id), object_id)
);
~~~

~~~java
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;

PreparedStatement upload = session.prepare(
    "INSERT INTO java_bind_lab.binary_objects " +
    "(tenant_id, object_id, content) " +
    "VALUES (:tenant, :id, :content)");

byte[] bytes = "hello".getBytes(StandardCharsets.UTF_8);
ByteBuffer data = ByteBuffer.wrap(bytes.clone());

BoundStatement b = upload.bind()
    .setString("tenant", "tenant-a")
    .setUuid("id", UUID.fromString(
        "88888888-8888-8888-8888-888888888888"))
    .setByteBuffer("content", data);
~~~

**Never** call `ByteBuffer.array()` blindly when decoding: the buffer may be **direct**, read-only, have a non-zero `position`, or lack a backing array. To read bytes safely:

~~~java
ByteBuffer returned = row.getByteBuffer("content");
ByteBuffer view = returned.asReadOnlyBuffer();
byte[] decoded = new byte[view.remaining()];
view.get(decoded);
~~~

`view` provides an independent `position/limit` cursor without mutating the original `ByteBuffer`'s position. For very large payloads, avoid copying everything onto the heap unnecessarily. Cassandra is not optimized for storing huge blobs arbitrarily: consider object storage and keeping only metadata/URIs in Cassandra.

### 15.2. `getBytesUnsafe`/`setBytesUnsafe` are advanced paths

The *Unsafe* APIs trade raw binary slices and carry strict warnings about buffer ownership and positions. For standard applications, use `setByteBuffer`/`getByteBuffer` or a controlled custom codec. Misusing *Unsafe* methods can encode corrupted bytes without normal type checks; they are **not** a “free speed boost”.

### 15.3. When should you use a custom codec?

Suppose a domain model has a Java enum `OrderStatus` while the Cassandra column is `text`. There are three approaches:

1. **Simplest:** `setString("status", orderStatus.name())` and parse the enum on read, with a clear policy for unknown values.
2. **Domain codec:** implement a thread-safe, fast, immutable `TypeCodec<OrderStatus>` for `text ↔ OrderStatus`, registered on the session or passed directly when binding.
3. **Object mapper:** use the driver mapper for DAO/entity mapping when the app is mostly stable CRUD, while still verifying column types and null/unset behavior.

A custom codec **does not** enforce business workflow validation: the enum may include `CANCELLED`, yet transitioning `PAID → CANCELLED` may be forbidden by business rules. Never use a codec to mask a schema using the wrong CQL type, and test round-trips with NULL, empty, and Unicode values.

### 15.4. Querying the codec registry when needed

If the app genuinely uses custom domain types, you can inspect the registry:

~~~java
import com.datastax.oss.driver.api.core.type.DataTypes;
import com.datastax.oss.driver.api.core.type.codec.TypeCodec;

TypeCodec<String> textCodec = session.getContext()
    .getCodecRegistry()
    .codecFor(DataTypes.TEXT, String.class);
~~~

`CodecRegistry.codecFor` looks up a codec for the exact **CQL type + Java target type**, throwing if none exists. Checking this at startup helps protect complex contracts; however, **having a codec alone does not prove columns/markers are bound with the right business meaning**.

## 16. Prepared vs Simple Statement: binding values and preventing injection

### 16.1. Prepared statements are recommended for repeated queries

~~~java
PreparedStatement byTenantAndDay = session.prepare(
    "SELECT event_time, event_id, status " +
    "FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ?");

BoundStatement query = byTenantAndDay.bind(
    "tenant-a", LocalDate.parse("2026-11-21"));
~~~

Prepared queries are parsed/cached, marker type metadata validates early, and the driver can compute routing keys. `PreparedStatement` is thread-safe in the built-in implementation; prepare once in the repository and bind per request. Never `prepare` randomly generated query text per request, which causes cache churn and extra round trips.

### 16.2. Simple statements can bind values, but metadata differs

~~~java
import com.datastax.oss.driver.api.core.cql.SimpleStatement;

SimpleStatement simple = SimpleStatement.builder(
        "SELECT status FROM java_bind_lab.customer_profiles " +
        "WHERE tenant_id = ? AND customer_id = ?")
    .addPositionalValues(
        "tenant-a",
        UUID.fromString("11111111-1111-1111-1111-111111111111"))
    .build();

Row row = session.execute(simple).one();
~~~

On a `SimpleStatement`, the driver must infer types from Java objects because it lacks prepared variable metadata. When a Java type maps to multiple CQL types (e.g., `String` for `text`/`ascii`, `UUID` for `uuid`/`timeuuid`), wrong type inference can cause server-side conversion issues; prepared statements provide explicit typed metadata. Named simple values also exist, though you **cannot mix positional and named values on the same built-in SimpleStatement**.

### 16.3. Binding values does not allow dynamic table or column names

**Wrong due to injection and lack of type safety:**

~~~java
String cql = "SELECT status FROM " + userProvidedTable +
    " WHERE tenant_id = '" + tenantId + "'";
session.execute(cql);
~~~

**Better:**

~~~java
// Table name is a reviewed constant; tenantId is a bind value.
PreparedStatement p = session.prepare(
    "SELECT status FROM java_bind_lab.customer_profiles " +
    "WHERE tenant_id = :tenant AND customer_id = :customer");
~~~

Even when `tenantId` is safely bound and escaped, you must still enforce **authorization**: a client can submit a type-valid `tenant-b` that does not belong to the authenticated user. Binding prevents literal injection; it does not replace ACLs or tenant isolation.

### 16.4. Prepared statements and schema evolution

Avoid `SELECT *` in prepared statements on tables undergoing `ALTER TABLE`, especially on Cassandra 3.x / older native protocols. Explicit column selection reduces the chance of metadata/result-decoder drift during schema changes. Cassandra 4+ with native protocol v5 improves result metadata updates, yet you should still run integration tests on schema migrations. [Prepared statements — schema changes](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/).

## 17. Routing key, consistency, and why binding the full partition key matters

~~~text
Java bind: tenant="tenant-a", day=2026-11-21
                     |
          Prepared variable metadata
                     |
       Partition key (tenant_id, day)
                     |
              Murmur3 token
                     |
        Natural replicas per RF/DC
                     |
          Coordinator + CL responses
                     |
           ResultSet / write ACK
~~~

### 17.1. Token-aware routing needs all partition-key components

With `PRIMARY KEY ((tenant_id, day), event_time, event_id)`, once the driver has metadata and the bound statement holds **both `tenant_id` and `day` with valid types**, it can compute the routing key/token and pick a favorable coordinator. If a component is missing, routing degrades or the query becomes invalid.

Having `WHERE tenant_id = ?` alone is not enough: a composite partition key also needs `day`. And if you swap `tenant_id` between two tenants of the same type, the driver still computes a routing key — **routing cleanly to the wrong business partition**.

### 17.2. Choose CL by design, not by binding errors

~~~java
BoundStatement request = byTenantAndDay.bind(
        "tenant-a", LocalDate.parse("2026-11-21"))
    .setConsistencyLevel(DefaultConsistencyLevel.ONE);
~~~

`ONE` is used here **solely for the RF1 lab**. With RF3 across multiple nodes and stricter application consistency needs, `LOCAL_QUORUM` may be required; this must be decided from the data contract and per-DC RF.

### 17.3. Problems setters cannot fix

- Oversized/hot partitions: a proper `setString` cannot spread a single partition across multiple tokens.
- Queries missing a partition key: properly typed binding does not turn a full scan into a point lookup.
- Down replicas or missing repair: typed binding cannot make `LOCAL_QUORUM` gather enough responses.
- Tombstones/TTL: data written in SSTables may not surface even with valid markers.
- Idempotence: retrying with the same UUID and timestamp/semantics requires explicit review and is not solved by marker naming.

**Diagnose errors by layer:** `prepare/bind` (metadata/codecs) is distinct from `execute` (network/CL) and from `result correctness` (logic/routing/TTL/tombstones).

## 18. CQL lab — preparing multi-type test data

**Goal:** Insert a few rows on a single-node Cassandra lab, verify keys/types in `cqlsh`, then run Java to bind positionally and by name. The lab requires neither benchmarking nor a multi-node cluster.

**Prerequisites:** A Cassandra 4.1/5.0 lab, `cqlsh`, Java 17 + driver 4.x, permissions to create keyspaces/tables, and working network/credentials. Never run `TRUNCATE` on production tables. Run the DDL from Section 3 **before** the steps below.

### 18.1. Initialize schema

In `cqlsh`, run the `CREATE KEYSPACE` and `CREATE TABLE` statements from Section 3; then:

~~~sql
DESCRIBE KEYSPACE java_bind_lab;
DESCRIBE TABLE java_bind_lab.events_by_tenant_day;
DESCRIBE TABLE java_bind_lab.customer_profiles;

CONSISTENCY ONE;
~~~

The lab uses RF1; multi-node/multi-DC environments must use `NetworkTopologyStrategy` with proper RF and application CL per contract.

### 18.2. Load sample events

~~~sql
INSERT INTO java_bind_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, amount, note, tags)
VALUES (
  'tenant-a', '2026-11-21', '2026-11-21T08:00:00Z',
  11111111-1111-1111-1111-111111111111,
  'NEW', 1200.50, 'created', {'order', 'new'}
);

INSERT INTO java_bind_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, amount, note, tags)
VALUES (
  'tenant-a', '2026-11-21', '2026-11-21T08:05:00Z',
  22222222-2222-2222-2222-222222222222,
  'PAID', 1200.50, 'payment received', {'order', 'paid'}
);

INSERT INTO java_bind_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, amount, note, tags)
VALUES (
  'tenant-a', '2026-11-21', '2026-11-21T08:10:00Z',
  33333333-3333-3333-3333-333333333333,
  'SHIPPED', 1200.50, 'sent', {'order', 'shipped'}
);

INSERT INTO java_bind_lab.events_by_tenant_day
  (tenant_id, day, event_time, event_id, status, amount, note, tags)
VALUES (
  'tenant-b', '2026-11-21', '2026-11-21T09:00:00Z',
  44444444-4444-4444-4444-444444444444,
  'NEW', 75.25, 'created', {'new'}
);
~~~

### 18.3. Verify via CQL before running Java

~~~sql
SELECT event_time, event_id, status, amount, tags
FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-a'
  AND day = '2026-11-21';

SELECT event_time, event_id, status, amount, tags
FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = 'tenant-b'
  AND day = '2026-11-21';
~~~

Expect 3 events for `tenant-a` and 1 for `tenant-b`. Event `2222…` is `PAID` with amount `1200.50`. Due to `CLUSTERING ORDER BY (event_time DESC,...)`, rows within a partition are returned newest-first; do not confuse **output ordering** with **bind marker order**.

### 18.4. Expected variable/type table for the range query

~~~sql
SELECT event_time, event_id, status, amount
FROM java_bind_lab.events_by_tenant_day
WHERE tenant_id = :tenant
  AND day = :target_day
  AND event_time >= :from_time
  AND event_time < :to_time;
~~~

| Marker index | Name | CQL type | Java |
|---:|---|---|---|
| 0 | `tenant` | text | String |
| 1 | `target_day` | date | LocalDate |
| 2 | `from_time` | timestamp | Instant |
| 3 | `to_time` | timestamp | Instant |

Verify in Java via `getVariableDefinitions()` that actual metadata matches this table; if query source code changes, tests must catch the change. **Do not assume from the name `from_time` that it is `timestamp`** if CQL changed to another type — the source of truth for types is prepared metadata.

## 19. Java lab — a program combining positional, named, and typed metadata

### 19.1. Session configuration

The code below uses Java 17 + Java Driver 4.x, assuming a local Cassandra lab at `127.0.0.1:9042` with local DC `datacenter1`. If your node belongs to a DC named `dc1`, update `withLocalDatacenter` accordingly. Never place passwords or TLS secrets in source code; if your lab enables authentication/TLS, configure them via an appropriate config loader or secrets manager.

Illustrative dependency for version 4.17:

~~~xml
<dependency>
  <groupId>com.datastax.oss</groupId>
  <artifactId>java-driver-core</artifactId>
  <version>4.17.0</version>
</dependency>
~~~

This dependency snippet is meant for an **existing** Java/Maven project, with no need to create a `pom.xml` in this module. For ASF releases starting at 4.18, verify Maven coordinates and APIs against the version documentation you use.

### 19.2. Java 17 program

~~~java
package example;

import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.ColumnDefinitions;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.core.type.DataTypes;

import java.math.BigDecimal;
import java.net.InetSocketAddress;
import java.time.Instant;
import java.time.LocalDate;
import java.util.Set;
import java.util.UUID;

public final class JavaBindLab {
    private JavaBindLab() {}

    public static void main(String[] args) {
        // Replace datacenter1 with the actual DC of your lab node.
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("datacenter1")
                .build()) {

            // 1) Positional form for a single partition.
            PreparedStatement byDay = session.prepare(
                "SELECT event_time, event_id, status, amount, tags " +
                "FROM java_bind_lab.events_by_tenant_day " +
                "WHERE tenant_id = ? AND day = ?");

            // Verify contract before binding.
            ColumnDefinitions vars = byDay.getVariableDefinitions();
            require(vars.size() == 2, "Expected two bind markers");
            require(DataTypes.TEXT.equals(vars.get(0).getType()),
                "Marker 0 must be text tenant_id");
            require(DataTypes.DATE.equals(vars.get(1).getType()),
                "Marker 1 must be date");

            BoundStatement dayRequest = byDay.bind(
                    "tenant-a", LocalDate.parse("2026-11-21"))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .setPageSize(2);

            ResultSet byDayResult = session.execute(dayRequest);
            int count = 0;
            for (Row row : byDayResult) {
                count++;
                System.out.printf(
                    "row=%s status=%s amount=%s tags=%s%n",
                    row.getUuid("event_id"),
                    row.getString("status"),
                    row.getBigDecimal("amount"),
                    row.getSet("tags", String.class));
            }
            require(count == 3, "Expected three tenant-a events");

            // 2) Named binding for a range.
            PreparedStatement range = session.prepare(
                "SELECT event_time, event_id, status " +
                "FROM java_bind_lab.events_by_tenant_day " +
                "WHERE tenant_id = :tenant " +
                "AND day = :target_day " +
                "AND event_time >= :from_time " +
                "AND event_time < :to_time");

            ColumnDefinitions rangeVars =
                range.getVariableDefinitions();
            require(rangeVars.size() == 4,
                "Expected four named bind markers");
            require(DataTypes.TIMESTAMP.equals(
                    rangeVars.get("from_time").getType()),
                "from_time must be timestamp");
            require(DataTypes.TIMESTAMP.equals(
                    rangeVars.get("to_time").getType()),
                "to_time must be timestamp");

            BoundStatement rangeRequest = range.bind()
                .setString("tenant", "tenant-a")
                .setLocalDate("target_day",
                    LocalDate.parse("2026-11-21"))
                .setInstant("from_time",
                    Instant.parse("2026-11-21T08:04:00Z"))
                .setInstant("to_time",
                    Instant.parse("2026-11-21T08:11:00Z"))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE);

            int inRange = 0;
            for (Row row : session.execute(rangeRequest)) {
                inRange++;
                System.out.println("range status=" +
                    row.getString("status"));
            }
            require(inRange == 2,
                "Expected PAID and SHIPPED in the range");

            // 3) Named INSERT with decimal, timestamp, UUID, set<text>.
            PreparedStatement insert = session.prepare(
                "INSERT INTO java_bind_lab.events_by_tenant_day " +
                "(tenant_id, day, event_time, event_id, " +
                "status, amount, note, tags) VALUES " +
                "(:tenant, :target_day, :at, :eid, " +
                ":state, :amount, :note, :tags)");

            BoundStatement inserted = insert.boundStatementBuilder()
                .setString("tenant", "tenant-c")
                .setLocalDate("target_day",
                    LocalDate.parse("2026-11-21"))
                .setInstant("at",
                    Instant.parse("2026-11-21T10:00:00Z"))
                .setUuid("eid", UUID.fromString(
                    "55555555-5555-5555-5555-555555555555"))
                .setString("state", "NEW")
                .setBigDecimal("amount",
                    new BigDecimal("19.95"))
                .setString("note", "created from Java")
                .setSet("tags", Set.of("java", "new"),
                    String.class)
                .setConsistencyLevel(DefaultConsistencyLevel.ONE)
                .build();
            session.execute(inserted);

            BoundStatement verify = byDay.bind(
                    "tenant-c", LocalDate.parse("2026-11-21"))
                .setConsistencyLevel(DefaultConsistencyLevel.ONE);
            Row persisted = session.execute(verify).one();

            require(persisted != null,
                "Inserted event must be visible");
            require("NEW".equals(persisted.getString("status")),
                "Unexpected status");
            require(new BigDecimal("19.95").compareTo(
                    persisted.getBigDecimal("amount")) == 0,
                "Unexpected amount");

            System.out.println("BIND_LAB_PASS");
        }
    }

    private static void require(boolean condition, String message) {
        if (!condition) {
            throw new IllegalStateException(message);
        }
    }
}
~~~

### 19.3. Expected output

~~~text
row=33333333-... status=SHIPPED amount=1200.50 tags=[...]
row=22222222-... status=PAID amount=1200.50 tags=[...]
row=11111111-... status=NEW amount=1200.50 tags=[...]
range status=SHIPPED
range status=PAID
BIND_LAB_PASS
~~~

**Output is illustrative only**; `Set` display order is not contractual and the driver may format decimal text differently. What matters is that Java:

- Reused the **same `PreparedStatement`** across multiple value sets.
- Verified metadata **before** binding.
- Used positional `bind(Object...)` and named `setXxx("name")`.
- Selected proper Java types for Cassandra date/timestamp/uuid/decimal/set.
- Used page size 2 yet read all **3 rows** via paging.
- Read back the inserted row and compared with `BigDecimal.compareTo` so scale differences are not mistaken for value differences.

### 19.4. If results do not match expectations

| Symptom | Check first |
|---|---|
| Session fails to build | Contact point, local DC, TLS/auth, node UP |
| Prepare fails | Keyspace/table/column names, CQL syntax, schema agreement |
| Metadata assertion fails | Query markers changed, column type/schema differs from expected |
| Codec exception at bind | Java type mismatches CQL type, missing custom codec registration |
| `tenant-a` has fewer/more than 3 rows | Lab ran previously, prior UPDATE/DELETE/TTL, dirty environment |
| Range returns 0 rows | Check `from/to` (UTC), `day` bucket, named marker names |
| Insert succeeds yet SELECT is empty | Wrong tenant/day/PK, CL, tombstones/TTL, mismatched query |

Run the lab in a **fresh isolated keyspace/table** or intentionally reset the **lab environment**; never run `TRUNCATE` on unapproved data.

## 20. Negative tests: intentionally misbinding to see where errors get caught

### 20.1. Testing a CQL type mismatch at bind

With the query:

~~~java
PreparedStatement p = session.prepare(
    "SELECT event_id FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = :tenant AND day = :target_day");
~~~

`target_day` has CQL type `date`, so:

~~~java
// CORRECT:
BoundStatement correct = p.bind()
    .setString("tenant", "tenant-a")
    .setLocalDate("target_day", LocalDate.parse("2026-11-21"));

// Expected to fail at bind because there is no TEXT -> CQL date codec:
// p.bind().setString("target_day", "2026-11-21");
~~~

If the application receives dates as text, parse them with `LocalDate.parse` in the validation layer before setting; **do not** increase retry attempts for deterministic type errors.

### 20.2. Wrong marker name

~~~java
// Declared :tenant, not :tenant_id.
// Runtime failure: unknown marker name.
// p.bind().setString("tenant_id", "tenant-a");
~~~

Assert `p.getVariableDefinitions().contains("tenant")` right after `prepare` in integration tests, and avoid hardcoding the same marker name across unsynchronized places.

### 20.3. Too many or too few values

~~~java
// p has 2 markers; passing 3 values -> driver rejects.
// p.bind("tenant-a", LocalDate.parse("2026-11-21"), 99);

// p has 2 markers; binding 1 leaves the second UNSET:
BoundStatement incomplete = p.bind("tenant-a");
System.out.println(incomplete.isSet(0));  // true
System.out.println(incomplete.isSet(1));  // false (UNSET)
~~~

The fact that `bind("tenant-a")` **constructs a statement** does not mean `execute` will succeed: `day` is part of the partition key, so it cannot be UNSET when executing this query. Enforce required parameters at the service boundary via schema contract validation for clear error messages.

### 20.4. Negative or out-of-range indices

~~~java
// Driver must throw IndexOutOfBoundsException:
// p.bind().setString(-1, "tenant-a");
// p.bind().setString(2, "tenant-a");  // only indices 0 and 1 exist
~~~

Never “quick-fix” by shifting indices by +1/-1 everywhere. Print `getVariableDefinitions()` and update the mapping to match marker order.

### 20.5. Swapping two markers of the same type is the most dangerous bug

Suppose a business table has:

~~~sql
CREATE TABLE IF NOT EXISTS java_bind_lab.tenant_region_notes (
  tenant_id text,
  region_code text,
  note text,
  PRIMARY KEY ((tenant_id), region_code)
);
~~~

Query:

~~~java
PreparedStatement q = session.prepare(
    "SELECT note FROM java_bind_lab.tenant_region_notes " +
    "WHERE tenant_id = ? AND region_code = ?");

// TYPE-VALID yet SEMANTICALLY WRONG:
BoundStatement wrong = q.bind("ap-south", "tenant-a");

// CORRECT:
BoundStatement right = q.bind("tenant-a", "ap-south");
~~~

The driver sees both columns as CQL `text`, so it **cannot distinguish** tenant from region. Even with named markers, code can still mistakenly call `setString("tenant", region)` and `setString("region", tenant)` — names aid review, they do not prevent semantic swaps. Guard against this with **typed domain wrappers/validation**, tests using **asymmetric keys**, and primary-key result assertions.

### 20.6. Duplicate names in a range query

~~~java
PreparedStatement q = session.prepare(
    "SELECT event_id FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ? " +
    "AND event_time >= ? AND event_time < ?");

System.out.println(
    q.getVariableDefinitions().allIndicesOf("event_time"));
// Expected: [2, 3] from server metadata.
~~~

Never call `setInstant("event_time", from)` followed by `setInstant("event_time", to)` to bind two bounds: each named setter can overwrite **both slots**, leaving both equal to `to`. Switch to `:from_time`/`:to_time` or positional indices 2 and 3. This bug causes **silent empty results** that can easily be mistaken for data loss.

### 20.7. Wrong getter on the result

When `status` is CQL `text`, calling `getInt("status")` is a type mismatch. Also ensure the `SELECT` projection **actually includes `status`**, since a getter naming a column that exists in the schema but not in the projection still fails. Prepare an independent verification query:

~~~java
PreparedStatement qStatus = session.prepare(
    "SELECT status FROM java_bind_lab.events_by_tenant_day " +
    "WHERE tenant_id = ? AND day = ?");

Row statusRow = session.execute(
    qStatus.bind("tenant-a", LocalDate.parse("2026-11-21"))).one();

String goodStatus = statusRow.getString("status");
// statusRow.getInt("status") -> codec/type mismatch.
~~~

### 20.8. Negative tests must also verify **no bad writes occurred**

When testing invalid-type INSERT/UPDATE calls, do not stop at “an exception was thrown”. Check:

- Did the call fail **before execution** or after reaching the server?
- Could any mutation have been partially applied? A write timeout does not prove “nothing was written”.
- Were the source event ID and primary key regenerated on retry?
- Did metadata/schema just change during a rolling deployment?
- Did logs/traces expose raw bind values or PII?

For deterministic codec errors, retrying with the same inputs will never succeed. For timeouts or quorum failures, apply dedicated **idempotency policies and reconciliation**.

## 21. Concurrent requests and reusing prepared statements

### 21.1. What can be shared across threads?

| Object | Share? | Rule |
|---|---|---|
| `CqlSession` | **Yes** | Reuse one session per app/cluster as appropriate |
| `PreparedStatement` | **Yes** | Prepare once on repository init, cache/reuse |
| Built-in `BoundStatement` | Possible, since immutable | Create a fresh bound statement per distinct value set |
| `BoundStatementBuilder` | **No** while mutating | Create per request; mutable and not thread-safe |
| `Row`, `ResultSet` | Follow API/consumption semantics | Do not share a result iterator across threads |
| App-held mutable `ByteBuffer` | Conditionally shareable | Never mutate position/contents after binding |

### 21.2. Repository with one prepared and many bound statements

~~~java
public final class CustomerRepository {
    private final CqlSession session;
    private final PreparedStatement findById;

    public CustomerRepository(CqlSession session) {
        this.session = session;
        this.findById = session.prepare(
            "SELECT name, age, active " +
            "FROM java_bind_lab.customer_profiles " +
            "WHERE tenant_id = :tenant AND customer_id = :customer");
    }

    public Row find(String tenantId, UUID customerId) {
        BoundStatement request = findById.bind()
            .setString("tenant", tenantId)
            .setUuid("customer", customerId)
            .setConsistencyLevel(DefaultConsistencyLevel.ONE);

        return session.execute(request).one();
    }
}
~~~

In production, the repository should map `Row` to a DTO promptly, handle nullable fields explicitly, and set consistency level according to RF and application contracts rather than hardcoding `ONE`.

### 21.3. Async does not change binding rules

~~~java
BoundStatement request = findById.bind()
    .setString("tenant", tenantId)
    .setUuid("customer", customerId);

CompletionStage<AsyncResultSet> future =
    session.executeAsync(request);
~~~

A `BoundStatement` holding concrete values is never mutated while being sent asynchronously. Never mutate a shared `BoundStatementBuilder` across concurrent async calls; that is a data race.

An async bulk importer needs **bounded in-flight requests** and backpressure. Never fire millions of unbounded futures and call `allOf` once at the end. When a request times out, write outcomes may be uncertain; retry only if semantics are truly idempotent.

### 21.4. Prepared cache and schema changes

Driver 4.x caches prepared statements by **CQL text and relevant execution parameters**; preparing the exact same query again usually hits the client cache, though you should avoid calling it on the hot path when you can hold a reference. The driver automatically reprepares on node join/restart/`UNPREPARED`, so you do not need to manually call `session.prepare` for every query after transient errors. [Prepared statements — caching and reprepare](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/).

## 22. Production binding-error diagnostic workflow

~~~text
               Failed request or wrong data
                          |
              Exception during prepare?
                /                \
              YES                 NO
               |                   |
       Check CQL/schema        Failed at bind?
       keyspace/column           /       \
                               YES        NO
                               |           |
                         Metadata +     Failed at execute?
                         markers/types    /      \
                                        YES      NO
                                         |        |
                                Quorum/network   Result decode?
                                auth/timeout      /      \
                                                YES      NO
                                                 |        |
                                          Row metadata   Business audit:
                                          getter/null     wrong PK/timezone
                                                          TTL/tombstone
~~~

### 22.1. Error classification by layer

| Layer | Symptom | Evidence to gather | Action |
|---|---|---|---|
| Prepare | `InvalidQuery`, unknown column/table | CQL text, schema digest, server logs | Fix query/schema; verify schema agreement |
| Bind marker | Unknown name, out of bounds | `getVariableDefinitions()` names/indices | Fix marker names/positions; keep tests |
| Bind codec | Codec not found / invalid value type | CQL type + Java runtime class + codec registry | Parse/validate properly or register valid codec |
| Execute | Timeout, unavailable, auth | CL, RF, node status, client/server metrics | Incident/backpressure/network; no blind retries |
| Decode | Missing column getter/wrong type, NULL primitive | `row.getColumnDefinitions()`, `isNull` | Fix projection/DTO/getter |
| Logic | Query succeeds yet wrong tenant/day/amount | Expected PK, event audit, timezone/decimal policy | Fix mapping; recover miswritten data |

### 22.2. Safe debug logging

You can log **non-sensitive metadata**:

~~~text
query_family=events.byTenantDay
statement_kind=prepared
bind_count=2
bind_schema=[0:text,1:date]
profile=point_read
consistency=LOCAL_QUORUM
outcome=codec_error
duration_ms=...
~~~

**Never log** raw bind values, full tokens/credentials, passwords, emails, addresses, card numbers, or other PII fields just for debugging. If reproduction samples are required, use a secure environment with masking and retention policies. Metric labels from per-record `tenantId`/UUIDs also cause **high cardinality** in Prometheus.

### 22.3. “Fail fast” does not replace Cassandra-side observability

If binding succeeds yet requests are slow:

~~~bash
nodetool status
nodetool tpstats
nodetool compactionstats
nodetool tablestats java_bind_lab.events_by_tenant_day
~~~

Monitor driver `cql-requests`, `cql-messages`, retries, in-flight pools, and request timeouts. Inspect partition sizes, tombstone scans, read/write latencies, disk/GC, and consistency quorum. **Never raise timeouts merely to mask a query with a broken partition key.**

### 22.4. Post-incident decision matrix

| Investigation finding | Decision |
|---|---|
| Wrong CQL marker name/index | Fix code, add contract test; do not retry |
| Wrong Java type/codec | Fix parser/DTO/custom codec and re-test |
| Two markers share a name yet need two values | Rename to distinct `:names` or use indices |
| Wrong tenant/partition despite valid types | STOP rollout and audit business data |
| Unintended NULL generating tombstones | STOP writes, restore logic from source of truth |
| UNSET PK or condition | Validate required fields before binding |
| Timeout after execute | Evaluate unknown outcome and retry/idempotency |
| Schema changed during rolling deploy | Coordinate compatibility, reprepare/DTO migration |

## 23. Code review and production readiness checklist

### 23.1. Before writing the query

- [ ] Identified the **query pattern** and right table/partition key.
- [ ] CQL uses explicit columns, avoiding `SELECT *` where schemas can evolve.
- [ ] Value sources come from user inputs/DTOs that passed parsing, validation, and authorization.
- [ ] Keyspace/table/column names are **allowlisted**, never concatenated directly from request text.
- [ ] Repeated prepared statements are prepared once and cached in the repository.
- [ ] Marker count, order/names, and expected types are captured in contract tests.
- [ ] Multiple conditions on the same column use distinct marker names or positional indices.
- [ ] Case-sensitive identifiers are modeled explicitly or unnecessary quoting is avoided.
- [ ] Connection/session local DC and authentication match the target cluster.

### 23.2. When binding values

- [ ] Positional indices are **0-based**; order follows CQL markers, not DDL column order.
- [ ] Named marker setters pass names **without the `:` prefix**.
- [ ] When using implicit named binding with `?`, `getVariableDefinitions()` was verified.
- [ ] Checked `allIndicesOf(name)` wherever a name might appear multiple times.
- [ ] Typed setters/getters match the CQL↔Java mapping.
- [ ] `date` and `timestamp` inputs are parsed with explicit timezone/precision rules.
- [ ] Monetary values use `BigDecimal` from a reliable decimal source, never converted through double.
- [ ] `uuid`/`timeuuid` and retry identities follow an explicit policy.
- [ ] Collection element types, UDTs, and tuple components match the target schema.
- [ ] Blob `ByteBuffer` is never mutated after binding and does not assume `array()`.
- [ ] An explicit **absent vs NULL vs UNSET** policy exists for every optional/PATCH field.
- [ ] Primary keys, WHERE restrictions, and critical business fields are never unintentionally UNSET/NULL.
- [ ] Return values from `BoundStatement.setXxx`/`unset` are never discarded.
- [ ] If using a builder, mutable builders are never shared across threads.
- [ ] Consistency level, timeout, idempotence, and execution profile fit the use case.

### 23.3. When executing and reading back

- [ ] Check prepare/bind errors before retrying; type/name errors are permanent.
- [ ] On timeouts/write failures, classify **unknown outcomes** by idempotency.
- [ ] Check `Row` for null when expecting a single record.
- [ ] Never call primitive getters without `isNull` when NULL has distinct meaning.
- [ ] Never mistake `page size` for a total returned-record limit.
- [ ] Check result projection/column metadata to match getters accurately.
- [ ] Assert expected primary keys and values; do not only check “SELECT returned a row”.
- [ ] Verify timestamps, status transitions, decimal precision, and row/collection semantics.
- [ ] On multi-DC clusters, verify CL and replica data within the required scope.
- [ ] Track metrics by query family, bind outcome, retry rate, and Cassandra server health.
- [ ] Logs contain no raw bind values, PII, secrets, or high-cardinality IDs.

### 23.4. When schema changes

- [ ] Schema/table/keyspace version reviewed before deploying new Java code.
- [ ] Contract tests assert `getVariableDefinitions()` against the target version.
- [ ] Deployed code supports backward/forward compatibility during rolling deploys.
- [ ] Custom codecs/UDT types are compatible with every cluster/session schema.
- [ ] Never change PK types/order without a dedicated data migration.
- [ ] New queries tested end-to-end (prepare, bind, execute, decode) on staging.
- [ ] If mis-mapping is detected, halt rollout and inspect mutations that may have written bad data.

## 24. Self-assessment questions and answer hints

**Q1.** Why does `PreparedStatement` differ from concatenating literals into a CQL string?  
**Hint:** Cassandra parses the query once, returns type metadata, and `BoundStatement` sends the prepared ID plus encoded values; this reduces injection risk in value positions.

**Q2.** A query has 3 `?` markers. What is the index of the last marker?  
**Hint:** 2; positional binding is 0-based.

**Q3.** When reordering columns or `?` in CQL, does Java `bind(...)` automatically re-map by DTO property names?  
**Hint:** No; you must update argument order or use named markers and tests.

**Q4.** If you swap `"tenant-a"` between `region_code text` and `tenant_id text`, will the driver block it?  
**Hint:** Not necessarily; both are `String`/`text`, so semantic errors must be caught by validation and integration tests.

**Q5.** In `event_time >= ? AND event_time < ?`, why is calling `setInstant("event_time", ...)` twice dangerous?  
**Hint:** Metadata names collide; named setters write all matching occurrences, so both bounds end up equal.

**Q6.** What is the safest way when two markers on the same column need two different values?  
**Hint:** Use positional indices or explicit `:from_time`/`:to_time` markers.

**Q7.** For `INSERT ... VALUES (:tenant, :customer)`, is calling `setString(":tenant", ...)` in Java correct?  
**Hint:** No; call `setString("tenant", ...)`.

**Q8.** Must named marker `:full_name` match the column name `name`?  
**Hint:** No; the name is defined by the query and exposed in prepared metadata.

**Q9.** How does `getVariableDefinitions()` differ from `row.getColumnDefinitions()`?  
**Hint:** The former describes bind input variables; the latter describes returned result columns.

**Q10.** Why assert `DataTypes.DATE` for the `day` marker?  
**Hint:** It verifies the schema/CQL contract has not changed and matches Java `LocalDate`.

**Q11.** Should CQL `date` be bound with Java `String` or `LocalDate`?  
**Hint:** `LocalDate` via `setLocalDate`; parse strings at the boundary.

**Q12.** Which Java type decodes CQL `timestamp` by default in the driver?  
**Hint:** `Instant` via `getInstant`; review millisecond precision and timezone policy.

**Q13.** Can `LocalDateTime` and `Instant` be substituted interchangeably when binding CQL timestamps?  
**Hint:** No; `LocalDateTime` lacks a timezone/offset and must be explicitly zoned first.

**Q14.** For money stored in CQL `decimal`, should you use `BigDecimal` or `double`?  
**Hint:** `BigDecimal`, avoiding binary floating-point rounding.

**Q15.** Is Java `UUID.randomUUID()` suitable for CQL `timeuuid` when a version-1 UUID is required?  
**Hint:** No; `randomUUID` generates version 4.

**Q16.** What happens if you call `setString(...)` on a `BoundStatement` and ignore the return value?  
**Hint:** Built-in objects are immutable; the original statement remains unchanged.

**Q17.** Can `PreparedStatement` be shared across threads? What about `BoundStatementBuilder`?  
**Hint:** Prepared statements can be shared; mutable builders are not thread-safe.

**Q18.** Does calling `bind(v0)` on a prepared statement with two markers always throw immediately?  
**Hint:** No; the remaining slot stays UNSET when protocol allows, though execution can fail if the marker is required.

**Q19.** What is the difference between `setToNull("age")` and leaving `age` unset in an UPDATE?  
**Hint:** NULL can delete/create a tombstone; UNSET skips updating that field.

**Q20.** If `new_age` is UNSET and `new_name` is set, what does `isSet("new_age")` return?  
**Hint:** `false`.

**Q21.** Why is `isNull("age")` needed before calling `getInt("age")`?  
**Hint:** Primitive getters return 0 on CQL NULL; if business logic distinguishes NULL from 0, you must check explicitly.

**Q22.** `setSet("tags", Set.of(...), String.class)` works for `tags set<text>`. Is `setList` equivalent?  
**Hint:** No; CQL `list` and `set` have distinct codecs and semantics.

**Q23.** When nested collections hit Java generic type erasure, is `List.class` sufficient?  
**Hint:** Use `GenericType<T>` or an appropriate codec to preserve element types.

**Q24.** What must you do when binding a UDT across clusters with differing schemas?  
**Hint:** Fetch `UserDefinedType` from the target session/schema, verify fields/version, and map values explicitly.

**Q25.** Why can `ByteBuffer.array()` fail when reading a blob?  
**Hint:** The buffer may be direct, read-only, or have `position`/`limit` covering only a slice; use a read-only view and `remaining()`.

**Q26.** `PreparedStatement` prevents value injection—can you also bind a user-supplied table name into `FROM ?`?  
**Hint:** No; bind values cannot replace CQL identifiers; select table/column names from an allowlist.

**Q27.** When the driver binds both `tenant_id` and `day` of a composite partition key, what is the routing benefit?  
**Hint:** It can compute the routing key/token and choose an optimal coordinator, though RF/DC/CL must still be configured properly.

**Q28.** If binding succeeds yet the result is empty, does that guarantee the data does not exist?  
**Hint:** No; it could be a wrong tenant/day, TTL/tombstone, CL/DC issue, or wrong query shape.

**Q29.** Why are tests that only check “an exception is thrown on type mismatch” insufficient?  
**Hint:** Same-type swaps fail silently, and timeouts leave write outcomes uncertain; audit primary keys and values.

**Q30.** During a schema change, which tests must run before rollout?  
**Hint:** Prepare/variable metadata, typed binding, execution, result decoding, nullable/UDT/collection handling, PK routing, and business correctness.

## 25. Summary: positional vs named — and where to validate types

~~~text
                       CQL QUERY TEXT
                             |
                    PreparedStatement
                             |
                   getVariableDefinitions
                 /           |             \
           INDEX          MARKER NAME      CQL TYPE
            0,1,2        :tenant,:day      text,date
                 \           |             /
                          VALIDATE
                             |
                 +-----------+------------+
                 |                        |
            Positional bind          Named bind
              ?, ?, ?               :tenant, :day
                 |                        |
           bind(v0,v1,...)           setXxx("name")
           setXxx(index)            distinct marker names
                 +-----------+------------+
                             |
                    CQL NULL / UNSET?
                             |
                  BoundStatement immutable
                             |
              Routing key + CL + execute
                             |
                 Row metadata + getter
                             |
                Business key/value checks
~~~

**When to choose positional binding?** Short CQL statements with fixed marker order, no repeated conditions on the same column, and contract tests guarding types/order. Also use indices when binding **two distinct values to the same column** whose inferred names collide.

**When to choose named binding?** Queries with many fields, evolving order, or where code readability matters; use **explicit, unique `:name` markers** and verify metadata. Do not blindly rely on names inferred from `?`.

**Where to check types?** **Before binding**, validate DTOs and business parsing; **after prepare**, assert `getVariableDefinitions()`; **during bind**, use typed setters/codecs; **on decode**, rely on `Row` metadata/getters and `isNull`; **after execute**, verify primary keys, timezones, decimals, and business invariants.

**Core takeaway:** Java Driver 4.x enforces **CQL↔Java type formatting** and handles markers deterministically, but it cannot know which tenant is authorized, which order status is valid, or whether a query fits Cassandra's wide-column model. A bind call that is **technically valid yet semantically wrong** can corrupt data more severely than a blocked type error. Combine **clear named markers, typed metadata assertions, explicit null/unset policies, prepared statement reuse, and partition-key integration tests**.

## References

- [Apache Cassandra Java Driver 4.18 — Prepared statements](https://apache.github.io/cassandra-java-driver/4.18.0/core/statements/prepared/) — `?`, `:name`, prepared variable metadata, bound setters, immutability, and reprepare.
- [DataStax Java Driver 4.17 — Prepared statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/prepared/) — API baseline for the examples.
- [Apache Cassandra Java Driver 4.18 — Core overview](https://apache.github.io/cassandra-java-driver/4.18.0/core/) — CQL-to-Java type mapping, primitive NULLs, collection generics, and row metadata.
- [Java Driver 4.17 — PreparedStatement Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/cql/PreparedStatement.html) — `bind(Object...)`, `getVariableDefinitions()`, `boundStatementBuilder`.
- [Java Driver 4.17 — ColumnDefinitions Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/cql/ColumnDefinitions.html) — `contains`, `get`, `allIndicesOf`, and type metadata.
- [Java Driver 4.17 — SettableByName Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/data/SettableByName.html) — named setters applying to all matching occurrences.
- [Java Driver 4.17 — Bindable Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/cql/Bindable.html) — `unset`, `isSet`, and constraints.
- [Java Driver 4.17 — GettableByIndex Javadoc](https://docs.datastax.com/en/drivers/java/4.17/com/datastax/oss/driver/api/core/data/GettableByIndex.html) — typed row getters and `isNull`.
- [Apache Cassandra Java Driver — Case sensitivity](https://apache.github.io/cassandra-java-driver/4.18.1/case_sensitivity/) — `CqlIdentifier` and named lookup with quoted identifiers.
- [Apache Cassandra Java Driver — UDTs](https://apache.github.io/cassandra-java-driver/4.19.0/core/udts/) — retrieving type metadata, building `UdtValue`, and binding to statements.
- [Apache Cassandra Java Driver — Tuples](https://apache.github.io/cassandra-java-driver/4.19.0/core/tuples/) — typed tuple fields and `TupleValue`.
- [Apache Cassandra Java Driver — Detachable types](https://apache.github.io/cassandra-java-driver/4.18.0/core/detachable_types/) — UDT/tuple cross-session/protocol codec concerns.
- [DataStax Java Driver — Custom codecs](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/custom_codecs/) — mapping domain types and codec registry.
- [DataStax Java Driver — Statements](https://docs.datastax.com/en/developer/java-driver/4.17/manual/core/statements/) — statements, immutable setters, and query attributes.
- [Apache Cassandra — Data modeling](https://cassandra.apache.org/doc/stable/cassandra/developing/data-modeling/intro.html) — partition keys, clustering columns, and query-first schemas.
- [Apache Cassandra — CQL data manipulation](https://cassandra.apache.org/doc/stable/cassandra/developing/cql/dml.html) — INSERT/UPDATE/SELECT, NULL/TTL/conditional mutations.
- [Apache Cassandra — Replication and consistency](https://cassandra.apache.org/doc/stable/cassandra/architecture/dynamo.html) — routing/token ring, natural replicas, and CL.
