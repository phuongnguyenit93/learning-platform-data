# QueryBuilder, Identifiers, and Avoiding Input Concatenation into CQL

> **Chapter:** Query Execution from Java  
> **Module:** `DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA` — Apache Cassandra: distributed and wide-column architecture, partition keys, query-driven table design, read/write consistency levels, CQL, replication, compaction, repair, error handling, and Java applications.  
> **Focus:** Building dynamic queries with **Apache Cassandra Java Driver 4.x QueryBuilder**; distinguishing **identifiers** (keyspace/table/column names) from **values** (parameter values); using `CqlIdentifier` and **bind markers** to avoid concatenating untrusted input directly into CQL.

An application letting users search orders by tenant, day, and time range is very easy to write unsafely:

```java
// DO NOT USE: concatenating input directly into CQL structure.
String cql = "SELECT * FROM app.orders_by_tenant_day "
    + "WHERE tenant_id = " + tenantFromHttp
    + " AND order_day = '" + dateFromHttp + "'";
session.execute(cql);
```

Even when inputs are “usually valid dates”, this mixes **CQL syntax** with **request data**. It opens quoting bugs, parse/type coercion issues, and *CQL injection* risks; testing with a single-quoted value can immediately reveal failures. Using `QueryBuilder` expresses query structure more cleanly, yet it **does not automatically make arbitrary user strings safe**. The core defenses are:

1. **Dynamic values** → `bindMarker()` in prepared CQL, bound with proper types via `PreparedStatement`/`BoundStatement`.
2. **Dynamic identifiers** (table, column, keyspace names) → **allowlist/mapping from business choices** to `CqlIdentifier`, never a bind marker for identifiers.
3. **Dynamic CQL fragments** (optional WHERE, ORDER BY, LIMIT) → constructed via a **structured DSL** permitting only *query shapes designed around the partition key*, rather than accepting free-form CQL fragments.
4. **Data permissions** → CQL authentication/authorization and tenant scoping; escaping/quoting **is not authorization**.

This lesson walks from broken examples to sound implementations, with a CQL lab, Java Driver 4.x code, testing, performance, incident analysis, and a code-review checklist.

## 1. Learning objectives

After this lesson, you will be able to:

1. Explain the boundary between **CQL syntax**, **schema identifiers**, and **bound data values**.
2. Know when to use `SimpleStatement`, `PreparedStatement`, `BoundStatement`, and `QueryBuilder`.
3. Add a `java-driver-query-builder` module dependency compatible with Java Driver core.
4. Use `selectFrom`, `insertInto`, `update`, `deleteFrom`, and `bindMarker` under the 4.x API.
5. Distinguish `CqlIdentifier.fromCql(...)` from `fromInternal(...)`, and handle case sensitivity, spaces, keywords, and quotes.
6. Understand why **a bind marker cannot substitute a table/column name or an ORDER BY direction**.
7. Design **allowlists** for projections, table choices, sorting, and optional filters without accepting raw CQL from HTTP.
8. Validate query shapes against partition/clustering keys to avoid `ALLOW FILTERING` and expensive scans.
9. Reuse prepared queries instead of rebuilding CQL on every request, keeping caches bounded.
10. Test special inputs, tenant isolation, type errors, and security requirements.
11. Analyze timeouts/retries, consistency levels, paging, and observability for dynamically built queries.
12. Build a Java repository with a shared `CqlSession`, bound parameters, and explicit validation.

## 2. Three layers in a CQL statement

Consider the query:

```sql
SELECT event_time, event_type
FROM app.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
LIMIT 50;
```

Classification:

| Component | Example | Role | Should it come directly from HTTP? |
|---|---|---|---|
| Keyword / structure | `SELECT`, `FROM`, `WHERE`, `LIMIT` | CQL grammar | No |
| Keyspace identifier | `app` | Selects namespace/schema | No; select from an allowlist |
| Table identifier | `events_by_tenant_day` | Selects data layout | No; select from an allowlist |
| Column identifier | `tenant_id`, `event_day` | Access path and routing | No; select from schema/allowlist |
| Value | Tenant UUID, date | Matching data | **Yes, via bind markers** |
| Numeric policy | Maximum rows returned | API/cluster protection | Input value must be validated/clamped |
| Query plan shape | With/without clustering range | Determines data scanned | Choose from supported patterns |
| Authentication context | Service account / tenant identity | Governs data access | Never trust a query parameter alone |

**Common confusion:** in Java, both a table name and a `String` value are strings, yet in CQL they belong to **two different semantic categories**. Manually quoting/escaping Java strings cannot replace driver parameter binding.

### 2.1. A bind marker is a placeholder for a *value*

```sql
-- Template prepared through Java Driver; cqlsh normally does not run
-- bare ? markers without a matching bind mechanism.
SELECT account_id, display_name
FROM app.accounts_by_id
WHERE account_id = ?;
```

The driver and server know `?` is a **value in a predicate position**, not a SQL/CQL snippet to be re-parsed after receiving the value. Values like `O'Reilly` or `a;b` are encoded using the CQL type's codec, never treated as closing literal quotes or statement terminators.

### 2.2. A bind marker cannot represent a table name

```sql
-- Semantically invalid: CQL does not replace table names with bind markers.
SELECT account_id FROM ? WHERE account_id = ?;

-- Invalid: do not use a marker as a column name.
SELECT ? FROM app.accounts_by_id WHERE account_id = ?;
```

CQL must know **schema and column names** to parse the statement and build an execution plan. If a user may choose between two business tables, the application must **map that choice to an allowlisted identifier** and prepare a statement for the chosen query shape.

### 2.3. Bind markers do not replace access control

A query with proper bind markers can still read another tenant's data if the application binds the wrong `tenant_id`:

```java
// The query is parameterized, yet if tenantId comes freely from the request,
// the API remains vulnerable to horizontal privilege escalation (IDOR).
BoundStatement stmt = prepared.bind(tenantIdFromRequest);
```

In multi-tenant APIs, tenant scope must originate from the **authenticated identity** and application policy, never solely from a caller-supplied query string or body. CQL role permissions and auditing still apply under the security model.

## 3. Why avoid concatenating inputs into CQL?

### 3.1. Quoted data is not syntax

An account with `display_name = "O'Reilly"` is valid data. Concatenation:

```java
String unsafe = "SELECT account_id FROM app.accounts_by_id "
    + "WHERE display_name = '" + userName + "'";
```

produces malformed CQL literals whenever `userName` contains `'`. If the application also exposes dynamic query parts, the risk grows further. Never patch this with `replace("'", "''")` and keep concatenating:

- Easy to miss cases with collections, UUIDs, timestamps, blobs, or Unicode text.
- Different CQL positions follow different syntax rules.
- Escaping a value never protects an **identifier** or an entire **WHERE fragment**.
- Driver or CQL syntax changes can introduce new edge-case gaps.
- Logging the concatenated string can expose personal data.

### 3.2. CQL injection is not identical to SQL injection

Cassandra is not an RDBMS running the same SQL dialect or supporting arbitrary SQL syntax. A SQL-style payload with `UNION SELECT` or semicolon-separated multi-statements `;` may be rejected by the CQL parser. That **does not prove concatenation is safe**:

- Input can alter literal values or break syntax.
- A system building table/column/sort names dynamically can be steered toward unauthorized queries.
- A fragment from configuration or UI can inject `ALLOW FILTERING`, wide scans, or data-modifying clauses if embedded verbatim.
- Repeated failing queries can cause denial-of-service or log spam.
- Security and correctness impact scales with the service account's privileges.

**Never rely on “Cassandra blocks multi-statements” as an injection defense.** Sound design uses stable CQL structure, protocol-level value binding, and allowlist-only identifiers.

### 3.3. Alphanumeric regex checks are insufficient

Even a column name matching `[a-z_]+` can target a sensitive column such as `password_hash` or produce an expensive scan shape. **Syntax checking** and **business authorization** are separate concerns.

For example, an API may expose only `display_name` and `account_state`. Even though `internal_notes` is a valid CQL identifier, callers **must not** be permitted to select it if the API contract forbids it.

## 4. What is Java Driver 4.x QueryBuilder?

### 4.1. Separate module from driver core

Java Driver 4.x includes a QueryBuilder module for **building CQL via a fluent DSL**. In the Apache Cassandra Java Driver 4.19 documentation, an example Maven dependency is:

```xml
<dependency>
  <groupId>org.apache.cassandra</groupId>
  <artifactId>java-driver-query-builder</artifactId>
  <version>4.19.0</version>
</dependency>
```

Configure **core driver** with a matching version in the same build, aligned via your project's BOM or dependency management. In older 4.x releases, the Maven groupId may be `com.datastax.oss`. **Check the POM/documentation for your exact version**, and never mix two different artifact groups or versions arbitrarily.

Java packages typically share the namespace:

```java
import com.datastax.oss.driver.api.querybuilder.QueryBuilder;
import com.datastax.oss.driver.api.querybuilder.select.Select;
import com.datastax.oss.driver.api.core.CqlIdentifier;
```

### 4.2. QueryBuilder builds CQL; CqlSession executes it

```java
import static com.datastax.oss.driver.api.querybuilder.QueryBuilder.*;

Select query = selectFrom("system", "local")
    .column("release_version");

// Get CQL text for tests/debugging (without bound values).
String text = query.asCql();

// Build into a statement and send via session.
SimpleStatement statement = query.build();
Row row = session.execute(statement).one();
```

QueryBuilder **does not connect** to the database or execute queries. `CqlSession` still handles prepare/execute, pools/metadata/CL/timeouts, while the Cassandra server determines replicas and the read path.

### 4.3. The fluent API is immutable

```java
Select base = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id");

Select withName = base.column("display_name");
Select withState = base.column("account_state");

// base, withName, and withState are three distinct query objects.
```

Builder steps generally **return a new object** rather than mutating the receiver. Therefore:

```java
// WRONG: the result of .whereColumn(...).isEqualTo(...) is discarded.
Select query = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id");
query.whereColumn("account_id").isEqualTo(bindMarker());

// CORRECT:
query = query.whereColumn("account_id").isEqualTo(bindMarker());
```

When dynamic conditions branch, always reassign `query = ...`. Immutability lets a component share a base query safely when used properly, though you should still avoid rebuilding queries on every call just because the DSL looks concise.

### 4.4. QueryBuilder does not replace understanding CQL

QueryBuilder does not enforce all data or workload constraints:

- It can build a query the server rejects for missing a partition key.
- It can produce queries requiring `ALLOW FILTERING` or wide scans.
- It does not verify that an index or materialized view serves the query efficiently.
- It does not grant database permissions.
- It does not stop multi-tenant data leaks when a mapping allows picking the wrong table.
- It exposes `raw(...)` to inject CQL fragments **verbatim**, with zero escaping or validation.

Start from **valid CQL and query-driven table design**, then express it in the builder DSL.

## 5. Three options: static CQL strings, SimpleStatement, and QueryBuilder

| Need | Typically sensible choice | Reason |
|---|---|---|
| Fixed-shape query executed thousands of times | Static CQL text + `session.prepare` | Readable, fewer allocations, reusable |
| Rare query with no dynamic structure | `SimpleStatement` with appropriate bound values | Minimal setup; still requires type/security checks |
| Projection/WHERE/ORDER BY with a few designed variants | `QueryBuilder` + bind markers + allowlist | Avoids manual syntax string concatenation |
| Dynamic query run repeatedly with the same shape | QueryBuilder builds at init/first use → `PreparedStatement` cache | Cuts preparation cost |
| User wants to run arbitrary CQL | Never expose via the service account | Requires separate admin tooling and permission boundaries |
| Simple CRUD/DAO with stable schema | Java Driver Mapper where fitting | Cuts boilerplate; still verify query semantics |
| Analytic query without a partition key | Choose query-first schema or an analytics engine | Builder does not make full scans cheap |

A clean CQL string with markers **is not less safe** merely because it is a String constant:

```java
PreparedStatement find = session.prepare(
    "SELECT account_id, display_name " +
    "FROM lab_java_query.accounts_by_id " +
    "WHERE account_id = ?");

Row row = session.execute(find.bind("user-001")).one();
```

The mistake to avoid is **building CQL from input data**, not having static string literals in source code.

## 6. Lab: schema suited for QueryBuilder

### 6.1. Environment prerequisites

This lab assumes Cassandra 4.x/5.x compatible with Java Driver 4.x, local datacenter `dc1`, CQL access, and **at least three full replicas in dc1** when using RF=3. On a single-node lab cluster, set RF=1; never assume RF=3 quorum is available without checking.

```sql
CREATE KEYSPACE IF NOT EXISTS lab_java_query
WITH replication = {
  'class': 'NetworkTopologyStrategy',
  'dc1': 3
};
```

### 6.2. Accounts table for exact lookups

```sql
CREATE TABLE IF NOT EXISTS lab_java_query.accounts_by_id (
    account_id text PRIMARY KEY,
    display_name text,
    account_state text,
    contact_email text
);
```

Designed query:

```sql
SELECT account_id, display_name, account_state
FROM lab_java_query.accounts_by_id
WHERE account_id = 'user-001';
```

**Do not** design frequent lookups with `WHERE display_name = '...'` on this table without a dedicated lookup table or index. `display_name` is a regular column, and that query has no partition key in `WHERE`.

### 6.3. Events table by tenant and day

```sql
CREATE TABLE IF NOT EXISTS lab_java_query.events_by_tenant_day (
    tenant_id uuid,
    event_day date,
    event_time timestamp,
    event_id uuid,
    event_type text,
    payload text,
    PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
) WITH CLUSTERING ORDER BY (
    event_time DESC,
    event_id DESC
);
```

Model strengths:

- `(tenant_id, event_day)` is a composite partition key that locates a single partition.
- `event_time` is the first clustering column, supporting time-range queries within a tenant/day.
- `event_id` disambiguates events sharing the same timestamp.
- `event_type` is a regular column: to filter by type at scale, consider an `events_by_tenant_type_day` table instead of filtering an entire history.
- Partition size per tenant/day still needs sizing; very hot tenants may require hourly buckets or sharding.

### 6.4. Test data containing quotes

```sql
CONSISTENCY LOCAL_QUORUM;

INSERT INTO lab_java_query.accounts_by_id (
    account_id, display_name, account_state, contact_email
) VALUES (
    'user-001', 'O''Reilly', 'ACTIVE', 'demo@example.invalid'
);

INSERT INTO lab_java_query.accounts_by_id (
    account_id, display_name, account_state, contact_email
) VALUES (
    'user-002', 'Tên có dấu phẩy, dấu nháy '' và Unicode',
    'INACTIVE', 'demo2@example.invalid'
);

INSERT INTO lab_java_query.events_by_tenant_day (
    tenant_id, event_day, event_time, event_id, event_type, payload
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21', '2026-11-21 08:00:00+0000',
    22222222-2222-4222-8222-222222222222,
    'LOGIN', 'payload-A'
);

INSERT INTO lab_java_query.events_by_tenant_day (
    tenant_id, event_day, event_time, event_id, event_type, payload
) VALUES (
    11111111-1111-1111-1111-111111111111,
    '2026-11-21', '2026-11-21 09:00:00+0000',
    33333333-3333-4333-8333-333333333333,
    'PURCHASE', 'payload-B'
);
```

Both `account_id` and `tenant_id` use synthetic values. CQL statements with doubled single quotes follow **CQL text literal** syntax when entered directly in `cqlsh`; the Java app should bind values instead of escaping manually.

## 7. Safe lookups with QueryBuilder + bind markers

### 7.1. Build the query once

```java
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.querybuilder.select.Select;

import static com.datastax.oss.driver.api.querybuilder.QueryBuilder.*;

Select selectAccount = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id")
    .column("display_name")
    .column("account_state")
    .whereColumn("account_id").isEqualTo(bindMarker());

PreparedStatement findAccount = session.prepare(
    selectAccount.build()
);
```

The generated CQL has the structure:

```sql
SELECT account_id,display_name,account_state
FROM lab_java_query.accounts_by_id
WHERE account_id = ?;
```

Marker placement is **fixed at prepare time**, independent of the length or characters inside `accountId`.

### 7.2. Bind values from Java

```java
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.Row;

String accountId = "user-001";

Row row = session.execute(
    findAccount.bind(accountId)
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
).one();

if (row != null) {
    System.out.println(row.getString("display_name"));
}
```

Values containing quotes or Unicode pass through the CQL type codec as **parameter values**. You neither need nor want to wrap `accountId` in `'` characters when binding.

### 7.3. Named bind markers

```java
Select query = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id")
    .column("display_name")
    .whereColumn("account_id").isEqualTo(bindMarker("id"));

PreparedStatement prepared = session.prepare(query.build());

Row row = session.execute(
    prepared.boundStatementBuilder()
        .setString("id", "user-001")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
        .build()
).one();
```

`bindMarker("id")` emits placeholder `:id`. **Named markers still bind values only**; `id` is a developer-chosen placeholder name, never a user-supplied column or table name.

## 8. QueryBuilder for INSERT/UPDATE/DELETE

### 8.1. INSERT with markers

```java
import com.datastax.oss.driver.api.querybuilder.insert.Insert;

Insert insert = insertInto("lab_java_query", "accounts_by_id")
    .value("account_id", bindMarker())
    .value("display_name", bindMarker())
    .value("account_state", bindMarker())
    .value("contact_email", bindMarker());

PreparedStatement upsertAccount = session.prepare(insert.build());

session.execute(
    upsertAccount.bind(
        "user-003",
        "O'Reilly User",
        "ACTIVE",
        "hello@example.invalid"
    ).setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
);
```

Benefits: zero manual quote escaping, and codecs bind typed values cleanly. An **upsert** on an existing primary key does not strictly mean a brand-new row was created; it can overwrite columns and timestamps.

### 8.2. UPDATE with an explicit partition key

```java
PreparedStatement changeState = session.prepare(
    update("lab_java_query", "accounts_by_id")
        .setColumn("account_state", bindMarker())
        .whereColumn("account_id").isEqualTo(bindMarker())
        .build()
);

session.execute(
    changeState.bind("SUSPENDED", "user-003")
        .setConsistencyLevel(DefaultConsistencyLevel.LOCAL_QUORUM)
);
```

The business rule “is the caller allowed to transition to SUSPENDED” must be enforced in the service layer and by roles. QueryBuilder does not verify authorization for changing account state.

### 8.3. DELETE can lose data — never leave identifiers free-form

```java
PreparedStatement deleteAccount = session.prepare(
    deleteFrom("lab_java_query", "accounts_by_id")
        .whereColumn("account_id").isEqualTo(bindMarker())
        .build()
);
```

This is a **dangerous CQL pattern if invoked improperly**, even with bind markers. Never accept arbitrary table names, WHERE clauses, or delete modes from HTTP. Enforce permissions, auditing, business confirmations, and awareness of tombstones/TTL.

### 8.4. BoundStatement and retries

On a write timeout, a mutation may already have applied on some replicas even though the driver received no ACK. `QueryBuilder` does not solve **idempotence**: counter increments, conditional writes, and writes whose timestamps change on retry must be analyzed individually. Set `setIdempotent(true)` only when operation semantics genuinely allow safe retries.

## 9. CqlIdentifier: schema names are not text values

### 9.1. Two identifier forms in Cassandra

CQL supports two identifier forms:

- **Unquoted identifier:** case-insensitive; Cassandra folds it to lowercase.
- **Double-quoted identifier:** preserves exact case and special characters; requires proper quoting and escaping.

Example:

```sql
-- These reference the SAME case-insensitive name:
CREATE TABLE lab_java_query.demo_unquoted (
    UserId text PRIMARY KEY
);
-- Stored internal column name: userid.

-- Quoted identifiers preserve exact casing.
CREATE TABLE lab_java_query."AuditLog" (
    "EventID" text PRIMARY KEY,
    "SourceName" text
);
```

On a schema with case-sensitive names, you cannot drop the `"` quotes when querying:

```sql
SELECT "EventID", "SourceName"
FROM lab_java_query."AuditLog"
WHERE "EventID" = 'evt-001';
```

### 9.2. `fromCql`: string in CQL syntax

```java
import com.datastax.oss.driver.api.core.CqlIdentifier;

CqlIdentifier a = CqlIdentifier.fromCql("AuditLog");
CqlIdentifier b = CqlIdentifier.fromCql("\"AuditLog\"");

// a parses an UNQUOTED identifier: internal = auditlog
// b parses a QUOTED identifier: internal = AuditLog
```

`fromCql("AuditLog")` **does not** guess that you wanted a table named `"AuditLog"`. If the CQL name is quoted, pass the quoted CQL syntax, or use `fromInternal` when you **already hold the exact internal name**.

### 9.3. `fromInternal`: exact known internal name

```java
CqlIdentifier exact = CqlIdentifier.fromInternal("AuditLog");
String forQuery = exact.asCql(true);      // "AuditLog"
String stored = exact.asInternal();       // AuditLog

CqlIdentifier lower = CqlIdentifier.fromCql("accounts_by_id");
String canonical = lower.asInternal();    // accounts_by_id
```

When an identifier contains double quotes in its name, `asCql(...)` applies the appropriate CQL quoting/escaping rules. **Never concatenate `asInternal()` directly into CQL**, because it is the unescaped name, not CQL syntax.

### 9.4. Using `asCql(true)` properly

If you must emit static/dynamic CQL outside QueryBuilder after **selecting a validated identifier**:

```java
CqlIdentifier column = CqlIdentifier.fromInternal("AuditLog");
String safeSyntaxForIdentifier = column.asCql(true);
```

`asCql(true)` produces **valid identifier syntax**, **not** a check that the table is permitted or exists in the cluster. Allowlists and authorization remain mandatory.

### 9.5. An identifier is a single segment, not a qualified path

```text
lab_java_query.accounts_by_id
^^^^^^^^^^^^^^ ^^^^^^^^^^^^^^
keyspace id    table id
```

Never wrap `"lab_java_query.accounts_by_id"` in a **single `CqlIdentifier`** when an API expects separate keyspace and table identifiers. QueryBuilder provides an overload:

```java
Select query = selectFrom(
    CqlIdentifier.fromCql("lab_java_query"),
    CqlIdentifier.fromCql("accounts_by_id")
).all();
```

Each segment is quoted/escaped independently. If clients send dots, spaces, or special characters, never split/join them by guesswork without explicit schema requirements.

### 9.6. Comparison table

| Java API | Input | Interpretation | Use case |
|---|---|---|---|
| `fromCql("Foo")` | Unquoted | `foo` | Standard case-insensitive names |
| `fromCql("\"Foo\"")` | Quoted | `Foo` | Case-sensitive CQL names |
| `fromInternal("Foo")` | Exact internal name | `Foo` | Names from metadata or allowlist |
| `asCql(true)` | One identifier | CQL syntax, quoted if needed | Rendering identifiers in queries |
| `asInternal()` | One identifier | Unquoted internal name | Metadata, mapping, display |
| `selectFrom(keyspaceId,tableId)` | Two identifiers | Qualified table name | Avoids dotted-name bugs |

**Classic security bug:** passing an arbitrary HTTP table name into `fromInternal(userInput)` and treating it as “safe”. Proper quoting only mitigates syntax breakouts; it **does not stop** users from picking any table the service account can access.

## 10. Choosing tables dynamically via an allowlist

### 10.1. Real-world requirement

An API accepts `view=active` or `view=archived`. The application maintains two purpose-built tables:

```text
view=active   → app.active_orders_by_tenant
view=archived → app.archived_orders_by_tenant
```

Never do this:

```java
// WRONG: client can choose any table name.
String table = httpRequest.getParameter("table");
String cql = "SELECT * FROM app." + table + " WHERE tenant_id = ?";
```

Instead, **map business choices** to developer-defined identifiers:

```java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import java.util.Map;

private static final Map<String, CqlIdentifier> TABLES = Map.of(
    "active", CqlIdentifier.fromCql("active_orders_by_tenant"),
    "archived", CqlIdentifier.fromCql("archived_orders_by_tenant")
);

static CqlIdentifier allowedTable(String view) {
    CqlIdentifier id = TABLES.get(view);
    if (id == null) {
        throw new IllegalArgumentException("Unsupported order view");
    }
    return id;
}
```

Once the table is validated:

```java
CqlIdentifier tableId = allowedTable(view);

Select query = selectFrom(
    CqlIdentifier.fromCql("app"), tableId)
    .column("order_id")
    .column("order_state")
    .whereColumn("tenant_id").isEqualTo(bindMarker());
```

### 10.2. Allowlists differ from regexes

`^[a-z_]+$` blocks weird characters, yet it **does not** prove a table belongs to the API contract. Restricting strictly to `active` and `archived` prevents callers from:

- Querying unexposed tables.
- Selecting tables lacking tenant-scoping in their primary key.
- Querying oversized tables or sensitive columns.
- Generating unbounded query shapes that blow up the prepared statement cache.
- Hitting the wrong keyspace or schema version.

### 10.3. Never auto-populate allowlists from schema metadata

Common mistake: “query all table names from `system_schema.tables` and let users pick”. Metadata shows **existence**, not whether a table is **safe to expose, tenant-isolated, or SLO-compliant**. Allowlists must come from deliberate API design and authorization review.

## 11. Dynamic projections: expose only approved columns

An endpoint lets callers select fields:

```text
GET /accounts/user-001?fields=name,state
```

If a caller passes `fields=contact_email` when the API must not expose emails, even a syntactically valid query causes **data exposure**.

### 11.1. Map API field names to schema columns

```java
import com.datastax.oss.driver.api.core.CqlIdentifier;
import java.util.Map;

static final Map<String,CqlIdentifier> VISIBLE_FIELDS = Map.of(
    "name", CqlIdentifier.fromCql("display_name"),
    "state", CqlIdentifier.fromCql("account_state")
);
```

### 11.2. Build the projection with QueryBuilder

```java
import com.datastax.oss.driver.api.querybuilder.select.Select;
import static com.datastax.oss.driver.api.querybuilder.QueryBuilder.*;

static Select buildAccountProjection(
        java.util.List<String> requestedFields) {

    if (requestedFields == null
            || requestedFields.isEmpty()
            || requestedFields.size() > 2) {
        throw new IllegalArgumentException("Invalid projection");
    }

    Select query = selectFrom("lab_java_query", "accounts_by_id")
        .column("account_id");

    java.util.Set<String> used = new java.util.HashSet<>();
    for (String field : requestedFields) {
        if (!used.add(field)) {
            throw new IllegalArgumentException("Duplicate field");
        }
        CqlIdentifier id = VISIBLE_FIELDS.get(field);
        if (id == null) {
            throw new IllegalArgumentException("Forbidden field");
        }
        query = query.column(id);
    }

    return query.whereColumn("account_id")
        .isEqualTo(bindMarker());
}
```

Identifiers are defined by the service, never passing raw field text to `.column(userInput)`. QueryBuilder can quote valid column names, yet it cannot verify **whether the caller is permitted to read them**.

### 11.3. Be careful with `SELECT *`

`SELECT *` automatically includes columns added in later schema migrations, potentially leaking private data. To maintain a stable API/DTO contract, **list columns explicitly**. QueryBuilder provides `.all()`, yet “shorter” is not always safer.

### 11.4. Cap the number of query shapes

With 10 columns and arbitrary subsets allowed, there are \(2^{10}=1,024\) theoretical projection shapes. Calling `session.prepare(...)` on every combination unchecked bloats caches and metadata. Instead:

- Offer a few projection profiles (such as summary vs detail) per API.
- Use a bounded/LRU cache keyed by **normalized query shape**, never by values.
- Cap allowed fields and filters.
- Monitor prepare rate, cache hit rate, memory, and latency.

## 12. Optional filters: only generate queries matching the data model

### 12.1. Example: time filtering within a partition

`events_by_tenant_day` has the primary key:

```sql
PRIMARY KEY ((tenant_id, event_day), event_time, event_id)
```

With the full partition key and clustering column `event_time`, this query fits cleanly:

```sql
SELECT event_time, event_id, event_type
FROM lab_java_query.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
  AND event_time >= ?
  AND event_time < ?
LIMIT 100;
```

`event_time` is the first clustering column, so range bounds work efficiently. An optional filter on `event_type` **does not share that property**, because `event_type` is a regular column on this table.

### 12.2. Building with QueryBuilder

```java
import com.datastax.oss.driver.api.querybuilder.select.Select;
import static com.datastax.oss.driver.api.querybuilder.QueryBuilder.*;

Select query = selectFrom("lab_java_query", "events_by_tenant_day")
    .column("event_time")
    .column("event_id")
    .column("event_type")
    .whereColumn("tenant_id").isEqualTo(bindMarker("tenant"))
    .whereColumn("event_day").isEqualTo(bindMarker("day"));

if (hasStart) {
    query = query.whereColumn("event_time")
        .isGreaterThanOrEqualTo(bindMarker("from_time"));
}
if (hasEnd) {
    query = query.whereColumn("event_time")
        .isLessThan(bindMarker("to_time"));
}

query = query.limit(100);
```

**Execution note:** you may need distinct query variants aligned with clustering restrictions and your Cassandra version so the server accepts `WHERE`/`ORDER BY`. In production code, test all variants against your **exact schema, driver, and Cassandra version** and prepare/cache them in a controlled way.

### 12.3. Never let optional filters drop the partition key

Mistake:

```java
// WRONG: if tenant/day is omitted, builds a SELECT without a partition key.
// QueryBuilder does not prevent full-table scans.
if (request.getTenantId() != null) { ... }
```

An API treating `tenantId` as “optional” can trigger cluster-wide scans whenever callers omit it. Instead:

- Require tenant/day on this endpoint.
- Or use a separate query-driven table/index designed and sized for that access path.
- Or reject unsupported requests.
- Never add `ALLOW FILTERING` just to make a query execute.

### 12.4. Bound filter combinations

Three optional filters yield \(2^3=8\) query shapes. As filters multiply, shape counts and invalid-query risk escalate. A safer pattern is **declaring an explicit list of valid shapes**, each backed by a prepared statement and tests.

## 13. Dynamic ORDER BY: validate both direction and column

### 13.1. Never bind `ASC/DESC` as a value

CQL:

```sql
SELECT event_time, event_id
FROM lab_java_query.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?
ORDER BY event_time DESC
LIMIT 100;
```

`DESC` is not a value you bind with `?`; it is grammar. If the app offers `sort=oldest` or `sort=newest`:

```java
import com.datastax.oss.driver.api.core.metadata.schema.ClusteringOrder;

ClusteringOrder sortOrder;
switch (sortFromRequest) {
    case "oldest":
        sortOrder = ClusteringOrder.ASC;
        break;
    case "newest":
        sortOrder = ClusteringOrder.DESC;
        break;
    default:
        throw new IllegalArgumentException("Unsupported sort");
}

Select query = selectFrom("lab_java_query", "events_by_tenant_day")
    .column("event_time")
    .column("event_id")
    .whereColumn("tenant_id").isEqualTo(bindMarker())
    .whereColumn("event_day").isEqualTo(bindMarker())
    .orderBy("event_time", sortOrder)
    .limit(100);
```

### 13.2. Sort only on columns CQL supports

In Cassandra, `ORDER BY` is restricted to **clustering columns** and must align with partition restrictions and table clustering order rules. Never accept an arbitrary regular column like `event_type` expecting the builder to produce a valid/fast “ORDER BY event_type”.

If the API needs sorting by non-PK attributes, consider:

- A denormalized table tailored to that sort/query pattern.
- A suitable index or search engine.
- Bounding the result set and sorting in the application when row counts are strictly small.
- An analytics engine when cluster-wide sorting is required.

### 13.3. Never concatenate sort direction verbatim

```java
// Do not use:
String cql = baseQuery + " ORDER BY event_time " + sortFromHttp;
```

Even when only `ASC`/`DESC` are valid, mapping through an enum/allowlist in Java keeps structure clean and isolates user input. When adding new sort fields, update data modeling and performance tests.

## 14. LIMIT, page size, and request budgets

### 14.1. LIMIT can be dynamic, yet must be validated

Java Driver QueryBuilder 4.x supports both `limit(int)` and an overload accepting `BindMarker`. Example:

```java
int requested = request.getLimit();

if (requested < 1 || requested > 100) {
    throw new IllegalArgumentException(
        "limit must be within 1..100");
}

Select query = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id")
    .whereColumn("account_id").isEqualTo(bindMarker())
    .limit(requested);
```

A lookup by single `account_id` already returns at most one row, so `LIMIT` adds little there; it simply illustrates validation. With many events per partition, `LIMIT` caps rows returned to the API.

### 14.2. Binding LIMIT

```java
Select query = selectFrom("lab_java_query", "events_by_tenant_day")
    .column("event_time")
    .whereColumn("tenant_id").isEqualTo(bindMarker())
    .whereColumn("event_day").isEqualTo(bindMarker())
    .limit(bindMarker());

// PreparedStatement bind(tenantUuid, day, boundedLimit)
```

The CQL parser only permits markers in **grammatically allowed positions**; `LIMIT` is supported by this API, which does not imply you can bind table names, ORDER BY columns, or entire clauses. Always validate limits **before binding**.

### 14.3. Paging does not cap total cost

```java
BoundStatement page = prepared.bind(tenant, day)
    .setPageSize(100)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM);
```

`setPageSize(100)` tunes the size of each page; iterating through the entire `ResultSet` can still read millions of rows. Setting `LIMIT 100` and partition bounds caps total rows, yet **large partitions, tombstones, and overlapping SSTables** can still cause heavy I/O.

To protect the system, enforce:

- Mandatory partition keys.
- Bounded clustering ranges.
- Bounded `LIMIT`.
- Page sizes tuned to row width and latency.
- Server/client timeouts, rate limits/backpressure, and concurrency budgets.
- SLOs/read latency, tombstone metrics, retries, and alerts.

## 15. How does `literal(...)` differ from `bindMarker()`?

QueryBuilder supports:

```java
Select literalQuery = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id")
    .whereColumn("account_id")
    .isEqualTo(literal("user-001"));
```

`literal(...)` embeds a **codec-formatted literal value** directly into the CQL text. It differs from `raw(...)` and suits genuinely fixed constants, but carries trade-offs:

- Each distinct value creates a different query string, hurting prepared statement reuse.
- Values can show up in logs, traces, and query strings.
- Literal formatting depends on codec/type and must not substitute for validation.
- It does not solve authorization or tenant scoping.
- For user-supplied payloads, **prefer bind markers + prepared statements**.

Comparison table:

| API | Emits | Escaping / formatting | Use for user values? |
|---|---|---|---|
| `bindMarker()` | `?` or `:name` | Value bound via codec/protocol | **Yes — preferred** |
| `literal(value)` | Literal inside CQL text | Controlled codec/formatter | Usually no; use for trusted constants |
| `raw(text)` | Verbatim CQL snippet | **No escaping, no syntax checks** | **No** |
| `CqlIdentifier` | Properly quoted schema name | Escapes identifier syntax | Only after allowlist/authorization |

Key takeaway: **query safety is the sum of structure, validation, authorization, and data modeling**, not a single method call.

## 16. `raw(...)` is a dangerous escape hatch

The Java Driver documentation describes `QueryBuilder.raw(String)` as injecting a snippet **verbatim** into CQL without syntax checks or escaping. It helps when the DSL does not yet expose a newer CQL feature, yet must be handled with extreme care.

```java
// DO NOT USE: untrusted input flowing into raw CQL.
String customFilter = httpRequest.getParameter("filter");
Select query = selectFrom("lab_java_query", "accounts_by_id")
    .column("account_id")
    .whereRaw(customFilter);
```

Even where such an API exists in a given position, treating a user-supplied filter string as a CQL fragment is **fundamentally wrong**. It risks syntax errors, wide scans, or unauthorized data access.

### 16.1. When raw is unavoidable

Use it only when **no DSL exists for a reviewed feature**:

1. The snippet is a **developer-controlled constant**, containing zero user input.
2. Any dynamic values still use bind markers wherever permitted.
3. The query shape undergoes security review and load testing.
4. Integration tests run against the target Cassandra version.
5. A feature flag/rollback exists if servers reject the new syntax.
6. Never use `raw` as a backdoor for `ALLOW FILTERING` or arbitrary queries.

### 16.2. Avoid string interpolation across all layers

A bug can hide behind multiple helper layers:

```text
HTTP request.filter
   └── buildSearchFilter(String)
         └── String.format("event_type='%s'", filter)
               └── QueryBuilder.raw(result)
                     └── CQL
```

Code reviews must trace **tainted data flow**, not merely grep for `session.execute("..." + user)`. Passing un-allowlisted names through `CqlIdentifier` also leaves authorization bypass risks intact.

## 17. Safe Java repository: one session, one query shape

Full example using `lab_java_query.accounts_by_id`. It constructs CQL once with QueryBuilder, prepares once, and binds per request.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.Row;
import com.datastax.oss.driver.api.querybuilder.select.Select;

import java.net.InetSocketAddress;
import java.util.Objects;

import static com.datastax.oss.driver.api.querybuilder.QueryBuilder.*;

public final class SafeAccountRepository implements AutoCloseable {
    private final CqlSession session;
    private final PreparedStatement find;
    private final PreparedStatement upsert;

    public SafeAccountRepository(CqlSession session) {
        this.session = Objects.requireNonNull(session);

        Select lookup = selectFrom("lab_java_query", "accounts_by_id")
            .column("account_id")
            .column("display_name")
            .column("account_state")
            .whereColumn("account_id").isEqualTo(bindMarker());

        this.find = session.prepare(lookup.build());

        this.upsert = session.prepare(
            insertInto("lab_java_query", "accounts_by_id")
                .value("account_id", bindMarker())
                .value("display_name", bindMarker())
                .value("account_state", bindMarker())
                .build()
        );
    }

    public String findDisplayName(String accountId) {
        validateAccountId(accountId);

        BoundStatement request = find.bind(accountId)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM);

        Row row = session.execute(request).one();
        return row == null ? null : row.getString("display_name");
    }

    public void save(
            String accountId,
            String displayName,
            String accountState) {
        validateAccountId(accountId);

        if (displayName == null || displayName.length() > 256) {
            throw new IllegalArgumentException("Bad display name");
        }
        if (!"ACTIVE".equals(accountState)
                && !"INACTIVE".equals(accountState)) {
            throw new IllegalArgumentException("Bad state");
        }

        BoundStatement request = upsert.bind(
                accountId, displayName, accountState)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM);

        session.execute(request);
    }

    private static void validateAccountId(String value) {
        if (value == null || value.isEmpty() || value.length() > 128) {
            throw new IllegalArgumentException("Invalid account id");
        }
    }

    @Override
    public void close() {
        // The repository does NOT own the injected session.
        // The application's session owner closes it on shutdown.
    }

    public static void main(String[] args) {
        try (CqlSession session = CqlSession.builder()
                .addContactPoint(
                    new InetSocketAddress("127.0.0.1", 9042))
                .withLocalDatacenter("dc1")
                .build()) {

            SafeAccountRepository repo =
                new SafeAccountRepository(session);

            repo.save(
                "user-010",
                "O'Reilly; data characters, not CQL",
                "ACTIVE"
            );

            System.out.println(repo.findDisplayName("user-010"));
        }
    }
}
```

**Lab scope:** `validateAccountId` only checks basic length; real systems need **authentication, authorization, and tenant scoping**. The repository must not close an injected session owned by application bootstrap. In a single-node RF=1 lab, CL/RF may need adjustment; **never drop CL casually in production**.

### 17.1. Why still validate if binding is safe?

Binding protects syntax and types, yet it does not stop:

- A 20 MiB input spiking memory/latency.
- Queries outside business scope.
- Access to sensitive columns or other tenants.
- Unbounded row limits, page sizes, or request deadlines.
- Domain-invalid values (unknown statuses).
- Spam/abuse or excessive request rates.

Validation and authorization complement parameterization; neither replaces the other.

### 17.2. Logging guidelines

Never log `displayName`, emails, tokens, passwords, or arbitrary bound values in production just to “debug injection”. Log instead:

- Logical query shape / operation name.
- Predefined logical table/keyspace labels.
- Latency, CL, retry/error category, and row counts/bytes.
- A correlation ID designed not to leak PII.
- A query shape hash rather than raw values when appropriate.

## 18. Safe dynamic sorting example

A service offers only two choices: `newest` or `oldest`. Build **two prepared statements** from the same schema instead of concatenating raw `ORDER BY` from HTTP.

```java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.metadata.schema.ClusteringOrder;
import com.datastax.oss.driver.api.querybuilder.select.Select;

import static com.datastax.oss.driver.api.querybuilder.QueryBuilder.*;

public final class EventQueries {
    private final PreparedStatement newest;
    private final PreparedStatement oldest;

    public EventQueries(CqlSession session) {
        this.newest = session.prepare(build(ClusteringOrder.DESC).build());
        this.oldest = session.prepare(build(ClusteringOrder.ASC).build());
    }

    private static Select build(ClusteringOrder order) {
        return selectFrom("lab_java_query", "events_by_tenant_day")
            .column("event_time")
            .column("event_id")
            .column("event_type")
            .whereColumn("tenant_id").isEqualTo(bindMarker())
            .whereColumn("event_day").isEqualTo(bindMarker())
            .orderBy("event_time", order)
            .limit(100);
    }

    public PreparedStatement select(String requestedOrder) {
        if ("newest".equals(requestedOrder)) return newest;
        if ("oldest".equals(requestedOrder)) return oldest;
        throw new IllegalArgumentException("Unsupported order");
    }
}
```

**Remember:** Cassandra restricts `ORDER BY` to clustering columns of a fixed partition; verify against the real schema. Two prepared statements do not mean “a session per sort”; they share one `CqlSession` and represent two approved query shapes.

## 19. Quoted identifiers, keywords, and case sensitivity

### 19.1. Tricky identifier example

Suppose a legacy schema (not recommended for new tables) defines table `"Order History"` and column `"Event""Name"`. In CQL:

```sql
CREATE TABLE lab_java_query."Order History" (
    "EventID" text PRIMARY KEY,
    "Event""Name" text
);
```

A `"` inside an internal identifier is written as **two double quotes** in CQL syntax. With QueryBuilder:

```java
CqlIdentifier table =
    CqlIdentifier.fromInternal("Order History");

CqlIdentifier eventName =
    CqlIdentifier.fromInternal("Event\"Name");

Select query = selectFrom(
        CqlIdentifier.fromCql("lab_java_query"), table)
    .column(eventName)
    .whereColumn(
        CqlIdentifier.fromInternal("EventID"))
    .isEqualTo(bindMarker());
```

The driver emits proper identifier syntax; you **do not** manually insert `"` in Java strings. This handles awkward schema-defined names, **not** letting users invent or pick arbitrary identifiers.

### 19.2. Recommendations for new schemas

Prefer:

- Lowercase `snake_case` names.
- Avoiding quoted identifiers wherever possible.
- Avoiding reserved keywords as table/column names.
- Fixed application keyspace and table names.
- Column names aligned clearly with query patterns.
- Testing metadata names and serialization when legacy schema compatibility is unavoidable.

Case-sensitive identifiers raise the risk of Java code, schema migrations, and query DSLs **mismatching names**. `CqlIdentifier` makes handling explicit, yet does not remove operational complexity.

## 20. Dynamic queries and Cassandra correctness

### 20.1. Not every filter is a valid query

On `events_by_tenant_day`:

```sql
-- Efficient when the full partition key is provided:
SELECT event_time, event_type
FROM lab_java_query.events_by_tenant_day
WHERE tenant_id = ?
  AND event_day = ?;

-- Not naturally efficient on that schema:
SELECT event_time, event_type
FROM lab_java_query.events_by_tenant_day
WHERE event_type = ?;
```

The second query lacks a partition key; QueryBuilder does not turn it into a point lookup. If the API needs lookups by event type, design a query-first table:

```sql
CREATE TABLE IF NOT EXISTS lab_java_query.events_by_tenant_type_day (
    tenant_id uuid,
    event_type text,
    event_day date,
    event_time timestamp,
    event_id uuid,
    payload text,
    PRIMARY KEY (
        (tenant_id, event_type, event_day),
        event_time, event_id
    )
) WITH CLUSTERING ORDER BY (
    event_time DESC, event_id DESC
);
```

The application must maintain the secondary table on writes, deletes, and TTLs; there are no automatic cross-table joins or transactions. For massive or hot datasets, add bucketing/sharding or a search/analytics layer.

### 20.2. ALLOW FILTERING is not a “QueryBuilder fix”

```java
// .allowFiltering() exists in the API, but should not be enabled by default.
Select expensive = selectFrom("lab_java_query", "events_by_tenant_day")
    .all()
    .whereColumn("event_type").isEqualTo(bindMarker())
    .allowFiltering();
```

The CQL server may scan vast numbers of partitions/cells to filter; client timeouts and p99 can spike sharply. A syntactically valid query can still generate dangerous load.

When queries need non-PK filters, require a data-modeling/index review and load test rather than slipping `allowFiltering()` into a “not found” branch.

### 20.3. LIMIT does not rescue wide scans

`LIMIT 10` only caps the rows returned or selected per query semantics. It neither creates a secondary index nor guarantees the server reads only 10 physical rows when filters, tombstones, or overlapping SSTables intervene. **Evaluate partition scope first.**

### 20.4. Small result does not mean small work

A cluster-wide `SELECT COUNT(*)` returns one number yet may scan huge amounts of data; QueryBuilder only builds the string. Never use QueryBuilder to bypass Cassandra's OLTP boundaries.

## 21. Typed values: UUID, date, timestamp, collections

### 21.1. Bind using matching type codecs

```java
import java.time.LocalDate;
import java.time.Instant;
import java.util.UUID;

UUID tenant = UUID.fromString(
    "11111111-1111-1111-1111-111111111111");

LocalDate day = LocalDate.of(2026, 11, 21);

PreparedStatement prepared = session.prepare(
    selectFrom("lab_java_query", "events_by_tenant_day")
        .column("event_time")
        .column("event_id")
        .whereColumn("tenant_id").isEqualTo(bindMarker())
        .whereColumn("event_day").isEqualTo(bindMarker())
        .build()
);

BoundStatement bound = prepared.bind(tenant, day)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM);
```

The driver serializes UUID/date cleanly per CQL. Never format text manually:

```java
// DO NOT USE:
String where = "WHERE tenant_id = '" + tenant + "' "
    + "AND event_day = '" + day + "'";
```

Beyond injection/syntax bugs, manual formatting risks type mismatches (UUID is not CQL text), date/timezone errors, and lost prepared-statement reuse.

### 21.2. Timestamps are a distinct type

Java Driver 4.x commonly maps:

- CQL `uuid` → Java `UUID`.
- CQL `date` → Java `LocalDate`.
- CQL `timestamp` → Java `Instant`.
- CQL `text` → Java `String`.
- CQL `bigint` → Java `long`/`Long`.

When users submit times over HTTP, parse according to your standard, validate timezone/range, and **bind `Instant`**. Never accept a CQL snippet like `toTimestamp(now())` from a query parameter instead of a value. If a server-generated function is needed, it must be part of a **developer-defined query shape** reviewed for idempotence.

### 21.3. Null and unset are not equivalent in all cases

Binding null has driver/CQL semantics around null/tombstones; some APIs support `unset` to leave a column untouched. Never use the string literal `"null"` to mean CQL null. For UPDATE/INSERT, define explicitly:

- Absent field: leave unchanged.
- Explicit null field: delete/set null per semantics.
- Valued field: upsert.
- Unset field: only where statement/driver/server support it and policy allows.

The difference affects tombstones, TTLs, compaction, and retries. QueryBuilder only emits syntax; your domain model must decide.

## 22. Prepared statement caching and performance

### 22.1. Do not prepare on every request

```java
// Inefficient:
public Row load(String id) {
    Select q = selectFrom("lab_java_query", "accounts_by_id")
        .column("display_name")
        .whereColumn("account_id").isEqualTo(bindMarker());
    PreparedStatement p = session.prepare(q.build());
    return session.execute(p.bind(id)).one();
}
```

Under heavy load, rebuilding the DSL and calling `prepare` repeatedly adds overhead; the driver caches and reprepares internally, yet you should not lean on that to rescue a hot path.

Better pattern:

```java
final class AccountLookup {
    private final CqlSession session;
    private final PreparedStatement prepared;

    AccountLookup(CqlSession session) {
        this.session = session;
        this.prepared = session.prepare(
            selectFrom("lab_java_query", "accounts_by_id")
                .column("display_name")
                .whereColumn("account_id").isEqualTo(bindMarker())
                .build());
    }

    String find(String id) {
        Row r = session.execute(prepared.bind(id)).one();
        return r == null ? null : r.getString("display_name");
    }
}
```

### 22.2. Cache shapes, never input values

Cache keys should capture:

- Allowlisted keyspace/table identifiers.
- Selected columns / query variants.
- Predicate shape / sort direction.
- Schema/version context where needed.

**Never** create a new prepared statement per `tenant_id` or per account value. Prepared statements built from the same query shape reuse across values.

### 22.3. Variant explosion

Suppose an API exposes:

- 5 projection profiles.
- 4 optional predicate sets.
- 2 sort orders.
- 3 table views.

Up to:

\[
5 \times 4 \times 2 \times 3 = 120
\]

prepared query shapes if every combination is allowed. **Bound and predefine** valid combinations instead of caching arbitrary input combinations unboundedly. A cache keyed by un-allowlisted user-provided CQL fragments is both a memory and a security risk.

### 22.4. QueryBuilder is optional for static CQL

For simple queries, **static CQL Strings + PreparedStatement** are often sufficient and easier to maintain. QueryBuilder shines when query structure is genuinely dynamic under strict controls. Weigh readability, caching, and testability instead of converting every static query to DSL just because the library is present.

## 23. Consistency level, idempotence, and retries in dynamic queries

### 23.1. CL lives on the statement

```java
BoundStatement statement = prepared.bind(tenant, day)
    .setConsistencyLevel(
        DefaultConsistencyLevel.LOCAL_QUORUM)
    .setPageSize(200);
```

`LOCAL_QUORUM` depends on keyspace RF and local DC. With RF=3 in `dc1`, local quorum requires 2 full replicas. QueryBuilder does not choose a business-meaningful CL on its own.

### 23.2. Timeouts do not prove a request did not execute

On UPDATE or DELETE, a timeout can occur after some replicas have already written while the client missed the ACK. On retry:

- Recomputed timestamps can alter conflict resolution.
- Retrying counter increments can double-count.
- Retrying LWT/conditional mutations has distinct semantics.
- Unbounded retries can overload the cluster.

Set `setIdempotent(true)` only when the operation is genuinely safe to retry. Never automatically mark every statement produced by QueryBuilder as idempotent.

### 23.3. QueryBuilder can only infer idempotence partially

Fixed terms or bind markers have clearer idempotence properties than `raw(...)` or non-deterministic functions (like `now()`). QueryBuilder sometimes suggests statement attributes automatically, yet it **knows nothing about business semantics** like event IDs, counters, or compensating actions.

Code review must check:
- Are keys and payloads identical on retry?
- Are there side effects outside Cassandra?
- Do source timestamps or TTLs shift on retry?
- Is read-after-write or quorum required?
- Are retry budgets and reconciliation defined?

## 24. Testing against injection and malformed queries

### 24.1. Test “awkward” yet valid data

Test values:

| Test input | Purpose |
|---|---|
| `O'Reilly` | Single quotes in values do not break CQL |
| `a;b` | Semicolons remain data when bound |
| `"name"` | Double quotes in **values** do not alter identifiers |
| `\n`, accented Unicode | Text/UTF-8 codec handles properly |
| String near policy length limit | Validation/size guards |
| Empty/null strings | Domain policy enforced |
| Malformed UUID/date | Rejected before binding with controlled errors |
| Another caller's tenant | Authorization rejects |
| Unknown table/column | Allowlist rejects |
| Sort other than `newest/oldest` | Blocked before building CQL |

### 24.2. Verify generated CQL contains no values

Unit tests can assert:

```java
Select q = selectFrom("lab_java_query", "accounts_by_id")
    .column("display_name")
    .whereColumn("account_id").isEqualTo(bindMarker());

String cql = q.asCql();

assert cql.contains("?");
assert !cql.contains("O'Reilly");
```

This only checks **query shape**. It does not prove authorization, query plans, or that all inputs are bound; pair it with integration tests.

### 24.3. Test identifier case sensitivity

```java
CqlIdentifier lower = CqlIdentifier.fromCql("AuditLog");
CqlIdentifier exact = CqlIdentifier.fromCql("\"AuditLog\"");

assert lower.asInternal().equals("auditlog");
assert exact.asInternal().equals("AuditLog");
assert !lower.equals(exact);
```

Test keywords, spaces, and double quotes too. Never compare quoted identifiers with `equalsIgnoreCase` when semantics are case-sensitive.

### 24.4. Test table/field mappings

```java
// Unit test pseudocode.
assert allowedTable("active") != null;
assert allowedTable("archived") != null;
assertThrows(
    IllegalArgumentException.class,
    () -> allowedTable("system_schema")
);
assertThrows(
    IllegalArgumentException.class,
    () -> allowedTable("admin")
);
```

Also test inputs with extra whitespace or non-matching casing. If the API normalizes inputs (such as trim/lowercase), do so by strict rules so unexpected identifiers never slip through.

### 24.5. Integration tests against real Cassandra

A solid test suite should:

1. Create a lab schema mirroring production (PK, clustering order, NTS/RF).
2. Prepare queries and bind `String` values containing quotes and Unicode.
3. Verify queries return exact rows by account/tenant/day.
4. Ensure queries missing mandatory partition keys fail **in validation** before reaching Cassandra.
5. Verify sort/limit variants align with the data model.
6. Verify disallowed table/column options are rejected rather than waiting for DB unknown-table errors.
7. Verify the Cassandra role lacks access to unrelated tables.
8. Measure p95/p99, read amplification, tombstones, and page counts on representative datasets.

## 25. Observability and logging when QueryBuilder produces multiple shapes

### 25.1. Name every operation

Instead of logging raw queries with values, assign logical operation names:

```text
FindAccountById
ListTenantEventsByDayNewest
ListTenantEventsByDayOldest
UpdateAccountState
DeleteAccountById
```

Metrics per operation and normalized shape are far clearer than per-request CQL logs.

### 25.2. Metrics to monitor

| Group | Metric | Meaning |
|---|---|---|
| Driver | Request latency p95/p99, in-flight, timeouts, retries | How the driver/client handles load |
| Query shape | Frequency, prepared cache size/hits/misses, compile/prepare errors | Whether dynamic queries are exploding |
| Cassandra | Read/write latency, range-scan latency | Queries missing PK or doing costly filtering |
| Storage | SSTables-per-read, tombstone scans, compaction backlog | Read amplification |
| Security | Forbidden table/column selections, tenant mismatches | Attempts exceeding API contract |
| Reliability | Unavailable vs timeout, CL/DC, error budget | Replica/cluster health |
| Paging | Page count/bytes per API request | Overly broad fetches |
| Audit | Authenticated principal, operation name, outcome | Traceability without leaking secrets |

### 25.3. Selective tracing

`TRACING ON` in `cqlsh` or driver statement tracing helps debug specific lab queries. Never enable 100% tracing on high-QPS services; tracing adds overhead and storage load. When investigating injection attempts, avoid logging raw sensitive input payloads.

### 25.4. Never cure a scanning query by raising timeouts

If QueryBuilder emits `ALLOW FILTERING` and a query takes seconds:

- Root causes are missing partition keys/indexes, tombstones, and range scans.
- Increasing timeouts keeps more requests holding resources longer.
- Increasing concurrency worsens read p99.
- Changing CL does not turn a scan into a point lookup.
- Switching from String CQL to QueryBuilder does not reduce bytes read.

Prioritize **fixing the schema and query shape**, not just tweaking driver settings.

## 26. Common errors and troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| CQL syntax error when `accountId` contains `'` | Value concatenated into string literal | Use bind markers |
| `InvalidQueryException` table/column mismatch | Case sensitivity, `CqlIdentifier` form | Compare schema and `fromCql/fromInternal` |
| QueryBuilder emits WHERE missing a condition | Discarded immutable builder result | `query = query.where...` |
| Markers bound out of order | Anonymous markers, wrong `bind` order | Use named markers or order tests |
| `CodecNotFoundException` / type mismatch | Bound String for UUID/date or vice versa | Parse typed values and bind matching codec |
| Query requires `ALLOW FILTERING` | Missing PK, filtering on regular column | Design query-first table |
| Query returns another tenant's data | Used HTTP `tenantId` without authz | Scope from principal, policy, and audit |
| Dynamic queries create thousands of prepared entries | Unbounded shapes keyed by raw inputs | Use allowlists and bounded caches |
| `ORDER BY` rejected by server | Non-clustering column or invalid restriction | Fix schema/query and test |
| Driver timeout despite small LIMIT | Large partition, tombstones, SSTable overlap | Narrow range, monitor read I/O |
| Sensitive value appears in CQL log | Used `literal(...)` or string concatenation | Bind values and restrict query logging |
| `raw(...)` accepts unintended fragment | Untrusted CQL fragment | Remove `raw`, use DSL + allowlist |
| Table exists yet access is denied | Cassandra role lacks permission | Fix authz; never over-grant privileges |
| One contact point works, another node fails | Driver topology/TLS/SAN/CL issue | Verify endpoints, local DC, TLS, and health |

**Not every `InvalidQuery` error is injection.** It may reflect schema drift, query restrictions, or type mismatches; classify accurately and never log secrets while debugging.

## 27. Code review checklist before merging QueryBuilder code

**Data flow**

- [ ] Every value from HTTP/messages/jobs goes through bind markers, never concatenated into CQL.
- [ ] No `raw(userInput)`, `whereRaw(userInput)`, or `String.format` injecting tainted values.
- [ ] Inputs are parsed into exact CQL types before binding.
- [ ] UUIDs, dates, and timestamps are never interpolated into CQL text.
- [ ] Validation covers length/domain ranges, nulls, and request budgets.

**Identifiers and authorization**

- [ ] Keyspace/table/column names come from a service-controlled allowlist/mapping.
- [ ] `CqlIdentifier.fromCql`/`fromInternal` are used with accurate semantics.
- [ ] `asInternal()` is never concatenated directly into CQL syntax.
- [ ] `SELECT *` does not expose private fields outside the contract.
- [ ] Tenant scope is derived from authenticated identity/policy, never trusted from query parameters.
- [ ] The CQL service role holds least-privilege permissions only.

**Cassandra query semantics**

- [ ] `WHERE` includes the full partition key per the data model and proper clustering bounds.
- [ ] No `ALLOW FILTERING` without approved design and load testing.
- [ ] `ORDER BY` targets clustering columns with valid directions only.
- [ ] `LIMIT`/page size/concurrency have guardrails to avoid accidental large history scans.
- [ ] RF, CL, and local DC match consistency requirements.
- [ ] DELETE/UPDATE/TTL/idempotence/retries match actual semantics.

**Performance and operations**

- [ ] QueryBuilder is not re-run continuously on hot paths when query shapes are fixed.
- [ ] `PreparedStatement` is reused with a bounded set of query variants.
- [ ] `CqlSession` is shared per cluster/security context, never opened per request.
- [ ] Exceptions and timeouts have bounded budgets; no infinite retries.
- [ ] Metrics track normalized operations without logging PII or secrets.
- [ ] Unit/integration tests cover quotes, disallowed identifiers, and query shapes.

## 28. Hands-on exercises and scenarios

### Exercise 1 — Quoted values

An account has display name `O'Reilly`. Why can `WHERE display_name = '...' + input` break syntax? How does `bindMarker()` eliminate that class of bugs without manual escaping?

### Exercise 2 — Identifiers are not values

An API selects between `active_orders_by_tenant` and `archived_orders_by_tenant`. Can you write `FROM ?` and bind the table name as a string? Propose a safe alternative.

### Exercise 3 — Identifier casing

Compare `CqlIdentifier.fromCql("AuditLog")`, `fromCql("\"AuditLog\"")`, and `fromInternal("AuditLog")`. Which ones correctly reference the quoted table `"AuditLog"`?

### Exercise 4 — QueryBuilder immutability

Snippet:

```java
Select q = selectFrom("ks", "accounts").column("account_id");
q.whereColumn("account_id").isEqualTo(bindMarker());
```

What is the mental mistake here, and how do you fix it?

### Exercise 5 — Raw snippets

Does `QueryBuilder.raw(...)` escape or syntax-check its argument before inserting it? If the app receives `filterClause` over HTTP, should it pass it to `raw`?

### Exercise 6 — Tenant isolation

A query uses a bind marker for `tenant_id`, yet callers can pass any tenant ID. The query stops CQL injection—is that enough to prevent cross-tenant reads?

### Exercise 7 — Dynamic sorting

An endpoint accepts `sort=event_type_desc`. On a table with PK `((tenant_id, event_day), event_time, event_id)`, can you add `orderBy("event_type", DESC)` and expect it to be valid and fast? What should you do instead?

### Exercise 8 — Optional filters

QueryBuilder adds `WHERE tenant_id = ?` only if the user supplies a tenant ID; when omitted, a full-table query is built. Redesign the validation and query shapes.

### Exercise 9 — LIMIT and paging

A query sets `setPageSize(200)` while the total result has 2 million rows. Does Cassandra only read 200 rows? How do you cap **total** work?

### Exercise 10 — Prepared cache

A repository builds queries from 10 optional boolean filters while also allowing arbitrary column projections. What is the risk to the prepared cache, and how do you prevent it?

### Exercise 11 — LWT/DELETE and retries

A DELETE with bind markers times out. Can you conclude the DELETE did not happen? How should you handle retries when auditability is required?

### Exercise 12 — Using `literal(...)`

Do `literal(userInput)` and `bindMarker()` share the same strengths for query reuse, caching, and logging? When is `literal` reasonable?

### Exercise 13 — Quoted schema

Table `"Order History"` has column `"Event""Name"`. Write Java code using `CqlIdentifier.fromInternal` to build a SELECT without manually concatenating raw identifiers.

### Exercise 14 — Syntactically valid yet slow query

QueryBuilder generates:

```sql
SELECT COUNT(*) FROM lab_java_query.events_by_tenant_day;
```

The query can run, yet why should it not power every dashboard refresh? Does QueryBuilder make it O(1)?

### Exercise 15 — Code review

A PR contains:

```java
String table = req.getParameter("table");
String id = req.getParameter("id");
String cql = "SELECT * FROM " + table + " WHERE id='" + id + "'";
```

List at least five security, correctness, or performance flaws and sketch an alternative design.

### Answer hints

1. Quotes break CQL literals; prepared/bind sends values over the protocol via codecs instead of parsing them as syntax.
2. No. Map `active`/`archived` to allowlisted `CqlIdentifier` instances and prepare a query per shape.
3. Use `fromCql("\"AuditLog\"")` or `fromInternal("AuditLog")`; the unquoted form folds to `auditlog`.
4. The builder is immutable; reassign `q = q.whereColumn(...).isEqualTo(...)`.
5. `raw` inserts verbatim with no escaping or syntax checks; never use it for untrusted inputs.
6. Not enough. Authenticate the caller, derive tenant scope from the principal/policy, and enforce RBAC and CQL permissions.
7. No, `event_type` is a regular column; Cassandra `ORDER BY` requires clustering constraints; design a query-first table or sort bounded results in-app.
8. Require tenant/day or choose another query pattern with a matching table/index; reject missing keys before reaching DB.
9. No; paging splits results into pages. Use partition/clustering bounds, reasonable `LIMIT`, rate limits/backpressure, and proper data modeling.
10. Combinatorial explosion of \(2^{10}=1,024\) filter shapes before multiplying by projections; expose only finite approved variants with bounded caching.
11. No; some or all replicas may have applied the delete. Retry only per semantics/idempotence, audit, and reconciliation.
12. No. `literal` inlines values into CQL, risking log exposure and hurting reuse; limit it to developer-controlled constants.
13. Use `selectFrom(CqlIdentifier.fromCql("lab_java_query"), CqlIdentifier.fromInternal("Order History")).column(CqlIdentifier.fromInternal("Event\"Name"))...` with bound WHERE values.
14. Full-table `COUNT(*)` scans massive data; QueryBuilder only generates CQL and does not create a count index.
15. Arbitrary table identifier injection, concatenated `id` literal, no binding, no tenant authz, `SELECT *`, no query plan/limit, and logging risks; replace with allowlists, explicit columns, prepared markers, and authorization policies.

## 29. References

Useful official docs to verify exact APIs and versions:

- [Apache Cassandra Java Driver 4.19 — Query Builder Overview](https://apache.github.io/cassandra-java-driver/4.19.0/query_builder/): DSL, dependencies, immutability, caching, and limitations.
- [Java Driver 4.19 API — QueryBuilder](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/querybuilder/QueryBuilder.html): `selectFrom`, `insertInto`, `bindMarker`, `literal`, `raw`.
- [Java Driver 4.19 API — CqlIdentifier](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/core/CqlIdentifier.html): CQL/internal forms, case sensitivity, and escaping.
- [Java Driver 4.19 API — Select](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/querybuilder/select/Select.html): `where`, `limit`, `orderBy`, `allowFiltering`.
- [Java Driver 4.19 API — BuildableQuery](https://apache.github.io/cassandra-java-driver/4.19.0/api/com/datastax/oss/driver/api/querybuilder/BuildableQuery.html): `asCql()`, `build()`, and statement builders.
- [Java Driver 4.x — Case Sensitivity](https://apache.github.io/cassandra-java-driver/4.18.1/case_sensitivity/): quoted identifiers, `fromCql`, and internal names.
- [Java Driver 4.19 — Core Manual](https://apache.github.io/cassandra-java-driver/4.19.0/core/): `CqlSession`, prepared/bound statements, and type mapping.
- [Apache Cassandra — CQL SELECT/WHERE/ORDER BY/LIMIT](https://cassandra.apache.org/doc/latest/cassandra/developing/cql/dml.html).
- [Apache Cassandra — Data Modeling](https://cassandra.apache.org/doc/latest/cassandra/developing/data-modeling/): partition keys and query-first design.
- [Apache Cassandra — Security](https://cassandra.apache.org/doc/latest/cassandra/managing/operating/security.html): TLS, authentication, and authorization.

**Version note:** Maven coordinates and some APIs/behaviors vary across Driver 4.x releases. Apache 4.19 keeps the Java package namespace `com.datastax.oss.driver.api` even though the query-builder module's Maven groupId may be `org.apache.cassandra`. Verify the exact artifact, driver core version, and Cassandra release of your application before using these snippets in production.

## 30. Conclusion: four boundaries to enforce

1. **Values differ from identifiers.** Use bind markers for data values; keyspace, table, and column names require `CqlIdentifier` and an **allowlist**. A bind marker cannot replace a CQL identifier.
2. **Escaping differs from authorization.** QueryBuilder handles syntax; it does not decide which tables or tenants a user may read. Tenant scope must come from authenticated identity/policy and role permissions.
3. **Valid CQL differs from cheap queries.** `WHERE` clauses must fit partition/clustering keys; `ALLOW FILTERING`, full-table `COUNT`, and pagination cannot rescue a flawed data model.
4. **Dynamic queries differ from arbitrary queries.** Support only finite, predefined query shapes, keep prepare caches bounded, bind via codecs, monitor errors/latency, and test edge-case inputs.

By upholding all four boundaries, Java applications can dynamically select valid tables, columns, and conditions **without concatenating untrusted inputs into CQL**, while still leveraging prepared statements, token-aware routing, consistency levels, and Cassandra's wide-column model.
