# Preventing CQL Injection with Bind Parameters and Dynamic Identifier Validation in Apache Cassandra

## 1. The Security Problem in a Distributed CQL System

Apache Cassandra is a distributed **wide-column** database. Data is partitioned by **partition key**, tables are designed around critical queries, and CQL operations pass through a coordinator to replicas at a **consistency level**. Java applications typically receive parameters from HTTP APIs, gRPC, message queues, or internal jobs to build `SELECT`, `INSERT`, `UPDATE`, and `DELETE` statements.

Risk arises when code mixes two distinct categories of information:

1. **Application-controlled query structure**: keyspace names, table names, columns, `WHERE` clauses, `ORDER BY`, operators, statement types.
2. **External data values**: UUIDs, dates, timestamps, strings, numbers, lists, update values.

Concatenating external input directly into CQL lets callers influence statement syntax rather than merely supplying values. That is the essence of **CQL injection**.

Foundational defenses:

- Use **prepared statements and bind parameters** (`?`) for **data values**.
- Use an **allowlist mapping to predefined CQL statements** for **identifiers or structural parts chosen dynamically**.
- Validate types, sizes, ranges, access rights, and tenant boundaries at the application layer.
- Configure authentication, authorization, TLS, and least privilege at the Cassandra layer.

This lesson belongs to the **Security** chapter of module **DATABASE_ENGINE_WIDE_COLUMN_CASSANDRA**, covering CQL, replication, partition-key modeling, error handling, and the Java Driver. Its focus is preventing untrusted input from being interpreted as **query code**.

> Prepared statements protect **positions where values can be bound**. They **do not check user permissions**, do not cap query cost, and do not sanitize dynamic CQL fragments concatenated into a template before calling `prepare`.

## 2. A Bad Example: Concatenating Values Directly into CQL

Suppose an API serves recent device events by day. The table is designed around its partition key:

~~~cql
-- Datacenter name dc1 is illustrative only.
CREATE KEYSPACE telemetry
WITH replication = {
    'class': 'NetworkTopologyStrategy',
    'dc1': 3
}
AND durable_writes = true;

CREATE TABLE telemetry.events_by_device_day (
    device_id uuid,
    event_day date,
    event_time timestamp,
    metric_value double,
    PRIMARY KEY ((device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

An **unsafe** way to write this in Java:

~~~java
// DO NOT USE: client-supplied strings go straight into CQL syntax.
String rawDevice = request.getParameter("deviceId");
String rawDay = request.getParameter("day");

String cql = "SELECT event_time, metric_value " +
    "FROM telemetry.events_by_device_day " +
    "WHERE device_id = " + rawDevice +
    " AND event_day = '" + rawDay + "'" +
    " LIMIT 50";

session.execute(cql);
~~~

The problem is not just missing quotes. When a caller controls text in a CQL value position, the resulting statement can have **its structure altered, fail parsing, execute outside the intended query scope, or be abused**. CQL does not include all traditional SQL syntax, so **do not assume a typical SQL injection payload works identically on Cassandra**. Actual exploitability depends on where concatenation occurs, the parser, statement type, and version.

"Manually escaping single quotes" is also insufficient:

- Each CQL type has its own syntax and encoding rules.
- It is easy to miss another concatenation spot on a different code path.
- Treating UUIDs, timestamps, collections, or blobs as raw strings increases formatting bugs.
- Concatenated table or column names are not protected by escaping **values**.
- Sanitizing input with regex instead of binding can corrupt valid data.

**Right approach:** predefine the query shape, pass values through **bind markers**, and let the driver encode them by CQL type.

## 3. How Prepared Statements and Bind Parameters Work

### 3.1. Separating Structure from Data

CQL template:

~~~cql
SELECT event_time, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
LIMIT ?;
~~~

The three `?` markers stand for **values**: UUID, date, and integer row limit. The application can supply different values without rebuilding query syntax.

~~~mermaid
flowchart LR
    A["Fixed CQL template"] --> B["Prepare on cluster"]
    C["Input from HTTP / message"] --> D["Parse and validate data types"]
    D --> E["Bind values by position and type"]
    B --> F["BoundStatement"]
    E --> F
    F --> G["Driver sends CQL request"]
    G --> H["Coordinator executes shaped statement"]
    I["Input requesting table, WHERE, or ORDER BY choice"] --> J["Allowlist / template selection"]
    J --> A
~~~

Conceptually, **query syntax is never constructed by concatenating external data**. Prepared statements also commonly allow reusing preparation and query metadata, yet the security goal is **the boundary between data and syntax**.

### 3.2. Complete Java Driver 4.x Example

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.DefaultConsistencyLevel;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;
import com.datastax.oss.driver.api.core.cql.Row;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.List;
import java.util.Objects;
import java.util.UUID;

public final class SafeEventRepository {
    private final CqlSession session;
    private final PreparedStatement readLatest;

    public SafeEventRepository(CqlSession session) {
        this.session = Objects.requireNonNull(session);
        this.readLatest = session.prepare(
            "SELECT event_time, metric_value " +
            "FROM telemetry.events_by_device_day " +
            "WHERE device_id = ? AND event_day = ? LIMIT ?"
        );
    }

    public List<Row> latest(UUID deviceId,
                            LocalDate day,
                            int requestedLimit) {
        Objects.requireNonNull(deviceId, "deviceId");
        Objects.requireNonNull(day, "day");

        // This is an API policy, not a Cassandra default.
        if (requestedLimit < 1 || requestedLimit > 100) {
            throw new IllegalArgumentException(
                "limit must be between 1 and 100");
        }

        BoundStatement statement = readLatest
            .bind(deviceId, day, requestedLimit)
            .setConsistencyLevel(
                DefaultConsistencyLevel.LOCAL_QUORUM)
            .setPageSize(Math.min(requestedLimit, 50));

        List<Row> rows = new ArrayList<>();
        ResultSet result = session.execute(statement);
        for (Row row : result) {
            rows.add(row);
        }
        return rows;
    }
}
~~~

This example assumes the keyspace/table exist and the cluster has enough replicas in the local datacenter for `LOCAL_QUORUM`. `CqlSession` is initialized elsewhere with proper local DC/auth/TLS. Because the code bounds results to **100 rows**, collecting into a list here has a clear cap; for larger result sets, stream pages instead of loading everything into RAM.

**Security highlights:**

- `UUID` and `LocalDate` are parsed into strong types before binding.
- `requestedLimit` is range-checked, then bound as an integer.
- The query shape is constant—no user-chosen CQL text.
- `PreparedStatement` is prepared **once over the repository lifecycle**, rather than preparing a new string per request.
- `setPageSize` is a fetch/paging parameter; it **does not replace `LIMIT`** or block queries lacking a partition key.
- `LOCAL_QUORUM` is a consistency choice; it does not prevent injection in place of binding.

### 3.3. Using Bind Parameters for Writes

~~~java
PreparedStatement upsert = session.prepare(
    "INSERT INTO telemetry.events_by_device_day " +
    "(device_id, event_day, event_time, metric_value) " +
    "VALUES (?, ?, ?, ?)"
);

BoundStatement write = upsert.bind(
    deviceId,
    LocalDate.of(2026, 11, 21),
    java.time.Instant.parse("2026-11-21T08:30:00Z"),
    24.7
);
session.execute(write);
~~~

Columns are fixed in code; the four values are encoded by the driver. You never manually quote timestamps or construct JSON strings to represent mutations.

For `UPDATE` and `DELETE`, the same principle holds: **keep `SET` and `WHERE` in approved structures**, binding only variable values. If the system allows updating **different columns**, use allowlisted templates or map fields to predefined statements instead of concatenating raw column names.

## 4. Bind Parameters Apply to Data, Not Identifiers

### 4.1. Classifying What Can Be Bound

| CQL Element | Should You Use `?`? | Safe Handling |
|---|---|---|
| UUID, number, string, timestamp in `WHERE` | **Yes** | Parse type, validate, and bind |
| Values in `INSERT ... VALUES` | **Yes** | Prepared/bound statement |
| Values in `UPDATE ... SET` | **Yes** | Bind matching column type |
| Numeric `LIMIT` value (where statement supports) | **Yes** | Validate reasonable bounds, then bind |
| Supported `IF` condition values | **Yes** | Bind; evaluate LWT semantics separately |
| **Keyspace name** | **No** | Allowlist/trusted config mapping |
| **Table name** | **No** | Allowlist mapping to query templates |
| **Column name** | **No** | Allowlist or matching template |
| **Clustering column name in `ORDER BY`** | **No** | Fixed by schema and query shape |
| **`ASC` or `DESC`** | **No** | Enum/allowlist selecting a statement |
| **Operators, `WHERE` fragments, `ALLOW FILTERING`** | **No** | Select from approved query shapes |
| **`CREATE/ALTER/DROP/TRUNCATE` or statement type** | **No** | Never accept from normal requests; RBAC and separate admin flows |

`?` is not magic that turns any arbitrary position in CQL into a parameter. A marker for a **term/value** cannot stand in for table names, columns, keywords, or `WHERE` clauses.

### 4.2. What Is a Dynamic Identifier?

Some needs can be legitimate:

- Choosing between an authorized active table or archive table.
- Choosing one of several predesigned report queries.
- Choosing newest-first or oldest-first order on a supported clustering column.
- Selecting a keyspace corresponding to a tenant via a controlled mapping.
- Choosing one of a few API-supported mutation types.

This **does not mean** clients can send arbitrary raw table names or CQL fragments. The proper boundary is **a server-defined set of choices**.

~~~text
External input:
    dataset = "archive"
    sort = "newest"

Server mapping:
    archive -> template A (known table)
    newest  -> ORDER BY event_time DESC (supported)

Never:
    "FROM " + request.tableName
    "ORDER BY " + request.sortExpression
~~~

### 4.3. Escaping Identifiers Does Not Replace Authorization

Cassandra has rules for **unquoted identifiers** and **quoted identifiers**, including case sensitivity when quoted. Libraries can quote identifiers cleanly, yet **proper quoting does not mean the caller is allowed to access that table**.

For instance, even a table name containing only `a-z0-9_` could point to a table holding confidential data. A regex blocking special characters **does not prove an identifier is authorized**.

Correct order of reasoning:

1. Verify the caller is authorized to select that data category.
2. Map a **business code** to an approved identifier/template.
3. If an identifier genuinely must be constructed, use a CQL builder API or controlled quoting and syntax validation.
4. Use prepared/bound values for all remaining values.
5. Rely on Cassandra RBAC as an **additional defense layer**, not solely application-side checks.

## 5. Best Approach: Select Among Fixed-Structure Queries

### 5.1. Mapping Dynamic Input to an Enum

Suppose a lab or production setup has two existing keyspaces with **matching schemas** for `events_by_device_day`:

- `telemetry.events_by_device_day`.
- `telemetry_archive.events_by_device_day`.

Both queries must include the full partition key in `WHERE`. Java accepts only `live` or `archive`.

~~~java
public enum Dataset {
    LIVE("telemetry.events_by_device_day"),
    ARCHIVE("telemetry_archive.events_by_device_day");

    private final String qualifiedTable;

    Dataset(String qualifiedTable) {
        this.qualifiedTable = qualifiedTable;
    }

    public String qualifiedTable() {
        return qualifiedTable;
    }

    public static Dataset fromApi(String input) {
        if ("live".equals(input)) {
            return LIVE;
        }
        if ("archive".equals(input)) {
            return ARCHIVE;
        }
        throw new IllegalArgumentException("Unsupported dataset");
    }
}
~~~

Here **`qualifiedTable` is hardcoded in reviewed code**, not a string taken from an HTTP request. If a caller sends anything else, the system **rejects** it rather than trying to sanitize/escape the input into a valid table name.

### 5.2. Prepare One Template per Valid Choice

~~~java
import com.datastax.oss.driver.api.core.CqlSession;
import com.datastax.oss.driver.api.core.cql.BoundStatement;
import com.datastax.oss.driver.api.core.cql.PreparedStatement;
import com.datastax.oss.driver.api.core.cql.ResultSet;

import java.time.LocalDate;
import java.util.EnumMap;
import java.util.Map;
import java.util.UUID;

public final class DatasetReader {
    private final CqlSession session;
    private final Map<Dataset, PreparedStatement> queries =
        new EnumMap<>(Dataset.class);

    public DatasetReader(CqlSession session) {
        this.session = session;

        for (Dataset dataset : Dataset.values()) {
            // Safe: identifier comes from an internal enum,
            // never directly from user input.
            String cql =
                "SELECT event_time, metric_value FROM " +
                dataset.qualifiedTable() +
                " WHERE device_id = ? AND event_day = ? LIMIT ?";
            queries.put(dataset, session.prepare(cql));
        }
    }

    public ResultSet read(String datasetFromRequest,
                          UUID deviceId,
                          LocalDate day,
                          int limit) {
        Dataset dataset = Dataset.fromApi(datasetFromRequest);
        if (limit < 1 || limit > 100) {
            throw new IllegalArgumentException("Invalid limit");
        }
        BoundStatement bs = queries.get(dataset)
            .bind(deviceId, day, limit);
        return session.execute(bs);
    }
}
~~~

This approach never creates unbounded prepared statements. **The set of query shapes is bounded by the enum**, making it verifiable by code review and tests.

Note: putting `dataset` in an enum does not check whether the user is allowed to view the archive. If only certain roles are allowed, authenticate/authorize **before selecting the enum or executing the query**.

### 5.3. When Tables Have Different Schemas

If `orders_by_customer` and `orders_by_id` have different partition keys, do not merge them into one template `WHERE id = ?` and swap table names. Each access pattern needs **its own statement matching its primary key**.

Right direction:

~~~text
Operation GET_BY_ORDER_ID
    -> SELECT ... FROM commerce.orders_by_id WHERE order_id = ?

Operation GET_BY_CUSTOMER
    -> SELECT ... FROM commerce.orders_by_customer
       WHERE customer_id = ? ...

Caller only picks an operation permitted by the server.
Each operation has its own validation, permissions, and limits.
~~~

An allowlist protects security **and** stops mismatched-schema queries from causing cluster-wide scans.

## 6. Dynamic Sorting: `ORDER BY` Must Match Clustering Keys

### 6.1. Never Concatenate Client Sort Strings

**Unsafe** code:

~~~java
String rawOrder = request.getParameter("orderBy");
String cql = "SELECT event_time, metric_value " +
    "FROM telemetry.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? " +
    "ORDER BY " + rawOrder;
~~~

Even though values in `WHERE` are bound, the `ORDER BY` portion can still be altered by the caller. **Preparing a statement that contains a raw fragment does not make that fragment safe.**

### 6.2. Use Two Fixed Templates

On a table with clustering column `event_time`, when querying by the full partition key, you can support both valid sort directions:

~~~cql
-- Newest-first option:
SELECT event_time, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
ORDER BY event_time DESC
LIMIT ?;

-- Oldest-first option:
SELECT event_time, metric_value
FROM telemetry.events_by_device_day
WHERE device_id = ?
  AND event_day = ?
ORDER BY event_time ASC
LIMIT ?;
~~~

Java:

~~~java
String latestCql =
    "SELECT event_time, metric_value " +
    "FROM telemetry.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? " +
    "ORDER BY event_time DESC LIMIT ?";

String oldestCql =
    "SELECT event_time, metric_value " +
    "FROM telemetry.events_by_device_day " +
    "WHERE device_id = ? AND event_day = ? " +
    "ORDER BY event_time ASC LIMIT ?";

PreparedStatement newest = session.prepare(latestCql);
PreparedStatement oldest = session.prepare(oldestCql);

PreparedStatement selected;
switch (sortInput) {
    case "newest":
        selected = newest;
        break;
    case "oldest":
        selected = oldest;
        break;
    default:
        throw new IllegalArgumentException("Unsupported sort");
}

BoundStatement bs = selected.bind(deviceId, day, 50);
~~~

This illustrates logic inside a method with `session`, `sortInput`, `deviceId`, and `day`. Production code should prepare statements once at service startup and reuse them.

**Cassandra nuance:** `ORDER BY` is not an arbitrary sorter across any column as in many RDBMSs. Ordering is constrained by clustering columns, partition restrictions, and schema. Allowlisting is only one layer; each query shape must still be valid and benchmarked.

## 7. Dynamic Filtering: Field Lists Do Not Mean Arbitrary Queries

Users may want to filter by `device_id`, date, or metric threshold. In Cassandra, even more critical than injection is **whether the data model supports that access pattern**.

### 7.1. Never Build `WHERE` Fragments from the API

~~~java
// DO NOT USE:
String rawFilter = request.getParameter("filter");
String cql = "SELECT * FROM telemetry.events_by_device_day " +
    "WHERE " + rawFilter;
~~~

This hands full control of the `WHERE` clause to the client; even with only "safe" ASCII characters, callers can trigger overly broad queries, miss partition keys, or consume excessive resources.

### 7.2. Define APIs at the Business Operation Level

| Permitted Operation | Defined `WHERE` Shape | Why |
|---|---|---|
| `GET_LATEST_BY_DEVICE_DAY` | `device_id = ? AND event_day = ?` | Full partition key |
| `GET_RANGE_BY_DEVICE_DAY` | `device_id = ? AND event_day = ? AND event_time >= ? AND event_time < ?` | Bounded clustering range |
| `GET_BY_METRIC_RANGE` | Do not expose on this table if access path is missing | May require a separate designed table/index/search |
| `SCAN_EVERYTHING` | Never expose on a public HTTP API | Avoid cluster-wide scans |

`?` marks bindable values, while **query shape is controlled by code and schema**.

### 7.3. Do Not Make `ALLOW FILTERING` an Arbitrary Option

Even without character-level injection, an API allowing callers to toggle `ALLOW FILTERING` can push Cassandra into scanning many partitions. Enforce performance standards, control access patterns, and bound row counts and concurrency at the application tier.

`LIMIT 50` only caps returned rows; if a filter must scan across many SSTables/tombstones/partitions to find 50 rows, the workload remains resource-intensive. **Query safety** includes preventing resource abuse, not just parser manipulation.

## 8. Multi-Tenant: Bind `tenant_id` from the Authenticated Identity

### 8.1. Cross-Tenant Read Risk

Suppose an application serves multiple organizations. If a client passes `tenantId` in the query string and the backend uses it unconditionally, a user can request another tenant's data **even when the query uses a prepared statement**.

This is an **authorization bug**, not an injection bug. Binding stops text from altering CQL syntax, but it does not check whether the caller owns the queried partition.

### 8.2. Partition Key Model Including Tenant

~~~cql
CREATE TABLE telemetry.events_by_tenant_device_day (
    tenant_id uuid,
    device_id uuid,
    event_day date,
    event_time timestamp,
    metric_value double,
    PRIMARY KEY ((tenant_id, device_id, event_day), event_time)
) WITH CLUSTERING ORDER BY (event_time DESC);
~~~

Query:

~~~cql
SELECT event_time, metric_value
FROM telemetry.events_by_tenant_device_day
WHERE tenant_id = ?
  AND device_id = ?
  AND event_day = ?
LIMIT ?;
~~~

Crucial: `tenant_id` must come from the **authenticated principal/authorization context** verified by the server; if the request carries a tenant field, validate authorization against it rather than trusting client-supplied values.

A sound flow:

~~~mermaid
flowchart TD
    A["HTTP request + access token"] --> B["Verify token"]
    B --> C["Resolve valid tenant/roles"]
    C --> D["Authorize device/data access"]
    D --> E["Select fixed template"]
    E --> F["Bind verified tenant_id + device_id + day + limit"]
    F --> G["Cassandra RBAC and query"]
    H["Self-asserted tenantId from request"] -. "Never trust blindly" .-> D
~~~

**Cassandra `GRANT` at the keyspace/table level does not replace application per-row authorization.** When multiple tenants share a table, the application must enforce access control at API and query boundaries.

### 8.3. When Each Tenant Has a Separate Keyspace

If the architecture uses one keyspace per tenant:

- Use a **backend-managed mapping**, e.g., authenticated tenant UUID → registered keyspace.
- Never build keyspace names directly from a client-supplied slug.
- Consider schema/keyspace counts, prepared statements, and operational overhead when tenant counts grow large.
- Create least-privilege roles and GRANTs per required scope; note that connection pool/role design belongs to the application architecture.
- Be careful with automated provisioning and cleanup when a tenant is deleted.

A regex blocking dots/quotes does not replace a permission mapping. **A syntactically valid name can still point to an unauthorized resource.**

## 9. Validate Values and Resource Bounds Before Binding

Prepared statements handle **data encoding**, not business validation. Important constraints:

| Input | Validation Needed | Impact If Skipped |
|---|---|---|
| Device UUID | Parse valid UUID; authorize device access | Exceptions, wrong data read |
| Date | Clear format and permitted date range | Scanning many partitions across requests |
| Time range | `start <= end` and bounded day/hour span | Overly broad query or massive request fan-out |
| `LIMIT` | Positive integer with API upper bound | Large result sets, RAM/network strain |
| Page size | Bounded byte/row counts per workload | Excessive allocations or round-trips |
| Strings/collections/blobs | Length, element count, type, and quota | Oversized mutations, disk/GC/compaction pressure |
| Timestamp/TTL | Valid range and business policy | Unexpected expiration or timestamp skew |
| Dynamic operations | Enum/allowlist and role permission | Out-of-purpose table or operation access |
| Request rate | Per-caller/tenant quota/rate limit | Query abuse despite proper binding |

For example, even a query specifying the full partition key can be slow if a partition is huge or tombstone-heavy. **Proper binding is necessary for security; table design, concurrency limits, and p99 monitoring mitigate data-layer denial of service.**

### 9.1. Validation Differs from Encoding

- **Validation** answers: "Is the value business-valid?"
- **Authorization** answers: "Is the caller permitted to access this data/resource?"
- **Binding** answers: "Will the value be sent strictly as data rather than CQL syntax?"
- **Query planning/data modeling** answers: "Can Cassandra serve this query efficiently and safely?"

All four layers are necessary; none replaces all the others.

## 10. Least Privilege in Cassandra: An Additional Defense Layer

Suppose operations created `telemetry_reader` per internal policy. Grant read access only on the permitted table:

~~~cql
-- Run by an admin authorized to grant rights, never by public APIs.
GRANT SELECT ON TABLE telemetry.events_by_device_day
TO telemetry_reader;
~~~

Check exact syntax/permissions and authentication/authorizer settings for your Cassandra version. In real systems, never create roles with hardcoded passwords from lessons or commit secrets to Git.

Principles:

1. **Separate application roles** for read APIs from migration/admin accounts.
2. **Never grant `ALL PERMISSIONS` on all keyspaces** to a web service.
3. Grant only `SELECT`, `MODIFY`, or admin permissions strictly needed for the duty.
4. Monitor schema migrations and whether roles expand unintentionally.
5. Enforce client-to-node TLS, private internode networking, and secret protection.
6. Distinguish **authorization errors** from syntax errors, timeouts, and `Unavailable`.
7. Audit sensitive operations per version capabilities; never log unbounded sensitive bind values.

If a raw-CQL concatenation bug causes an app to attempt out-of-scope operations, a **least-privilege role** limits damage. Still, a broad `SELECT` role can read unauthorized data—API authorization cannot be skipped.

## 11. Safe Logging: Log Query IDs, Never Raw Bind Values

### 11.1. Slow-Request Logs Must Not Create New Risks

Logs are a common way sensitive data leaks outside the database. A slow-query event should log low-cardinality fields:

~~~text
event=cassandra_request
query_id=read_events_by_device_day
duration_ms=184
outcome=success
consistency=LOCAL_QUORUM
page_size=50
dc=dc1
rows_returned=50
~~~

This is an **illustrative application log schema**, not Cassandra's default log format. Avoid putting these in routine logs:

- `tenant_id`, `device_id`, emails, access tokens, or full raw CQL with bind values.
- Passwords, secrets, key material, and data payloads.
- Full request URIs if they contain sensitive IDs.
- Uncontrolled exception messages that may echo query parameters.

When investigating a specific partition, use access-controlled traces/logs with retention and sampling policies. **Never attach user IDs or partition keys to Prometheus labels**, as that explodes cardinality and widens exposure.

### 11.2. Never Prepare Every Request with Literal Values

Code like this defeats binding and proliferates query shapes:

~~~java
// Wrong: literal is interpolated into the statement before prepare.
String cql = "SELECT ... WHERE device_id = " + rawValue;
PreparedStatement ps = session.prepare(cql);
~~~

`prepare()` **does not sanitize an interpolated CQL string**. Prepared statements only work when query text contains markers and all dynamic values pass through `bind()`.

Beyond security, preparing thousands of distinct statements wastes cache/memory and increases prepare traffic. Maintain a finite set of query templates.

## 12. Testing to Prove Inputs Do Not Control Query Shape

### 12.1. Testing Dataset Selection

JUnit 5 snippet testing an enum allowlist (no Cassandra connection needed):

~~~java
import static org.junit.jupiter.api.Assertions.*;

import org.junit.jupiter.api.Test;

class DatasetTest {
    @Test
    void acceptsOnlyKnownPublicValues() {
        assertEquals(Dataset.LIVE, Dataset.fromApi("live"));
        assertEquals(Dataset.ARCHIVE, Dataset.fromApi("archive"));
    }

    @Test
    void rejectsUnknownOrCqlLikeInputs() {
        assertThrows(IllegalArgumentException.class,
            () -> Dataset.fromApi("system"));
        assertThrows(IllegalArgumentException.class,
            () -> Dataset.fromApi("archive; DROP TABLE something"));
        assertThrows(IllegalArgumentException.class,
            () -> Dataset.fromApi("ARCHIVE"));
        assertThrows(IllegalArgumentException.class,
            () -> Dataset.fromApi(""));
        assertThrows(IllegalArgumentException.class,
            () -> Dataset.fromApi(null));
    }
}
~~~

This test proves **input cannot select resources outside the mapping**. You do not need to test whether a semicolon string makes Cassandra execute multiple commands—proving it is rejected before statement construction suffices.

### 12.2. Testing Binding and Bounds

For repositories and APIs, test that:

- Invalid UUIDs are rejected during parsing, **before** running CQL.
- `limit = 0` and `limit = 101` (per example bounds) are rejected.
- Strings containing quotes, semicolons, comment markers, or Unicode in **text fields** are stored/queried as **intact literal values** when bound, never becoming syntax.
- Table/keyspace/column names outside the allowlist never enter queries.
- Tenant permissions are checked against the **authenticated principal**, not just a `tenantId` field in the body.
- Malformed requests do not cause loggers to leak raw values.
- Oversized queries/broad scans are blocked by API policy and query shapes.

### 12.3. Integration Testing in an Isolated Environment

An integration test against a Cassandra lab can:

1. Create the test keyspace/table schema.
2. Insert a row with special-character text via `bind`.
3. Read it back with a prepared `SELECT`, verifying identical bytes/strings.
4. Send a request with a dataset outside the allowlist and confirm **zero CQL is sent**.
5. Send a request as tenant A trying to read tenant B, verifying `403 Forbidden` or equivalent API denial.
6. Confirm telemetry/logs contain no sensitive data.
7. Monitor p95/p99 and timeouts to catch overloading query shapes.

Never run destructive tests or `DROP` commands against production. Isolate database integration tests from clusters holding real data and run them with low-privilege roles.

## 13. Is CQL Injection Identical to RDBMS SQL Injection?

**The root principle is the same:** untrusted data must never become query syntax. However, Apache Cassandra has **different grammar and access patterns**:

- It does not support SQL constructs like `JOIN`, `UNION SELECT`, `OFFSET`, or general `OR` by default; capabilities vary by CQL/version.
- `WHERE` is primarily designed to specify partition/clustering keys or supported query features, not arbitrary filters across any column.
- A payload attempting stacked statements may be rejected by the driver/server rather than executed. **Never claim every semicolon string runs as multiple statements.**
- Even when the parser rejects a payload, **concatenating input into query text remains an anti-pattern** that can turn into a vulnerability as code evolves.
- Syntactically valid queries can still cause **resource exhaustion** if apps allow broad scans or unthrottled request rates.

Therefore, never blindly copy "sample SQL payloads" to evaluate Cassandra security. Check **data/syntax boundaries, query template sets, permissions, and resource limits**.

## 14. Anti-Patterns to Catch During Code Review

| Anti-Pattern | Risk | Fix |
|---|---|---|
| `"WHERE name = '" + userInput + "'"` | Value controls query text | Prepared/bound text |
| `"WHERE id = " + rawUuid` | Unparsed/unencoded raw UUID | Parse `UUID` and bind |
| `"FROM " + request.table` | Caller controls identifier | Map enum → table/template |
| `"SELECT " + request.columns` | Caller controls projection | Allowlist projection forms |
| `"ORDER BY " + request.order` | Caller controls clause | Sort enum → fixed query |
| `"WHERE " + filterExpression` | Caller controls entire `WHERE` | Choose operation/template per access pattern |
| `"LIMIT " + rawLimit` | Unvalidated data in query | Validate number and bind |
| `session.prepare("..." + rawInput)` | Preparing input-concatenated query | Fixed template then bind |
| Regex `[a-z0-9_]+` alone for tables | Syntactically valid name can still be unauthorized | Resource and principal allowlist |
| Request body supplies `tenant_id` and server trusts it | Cross-tenant access despite binding | Derive tenant from authenticated context |
| Using a schema-admin role in APIs | Huge blast radius from unintended ops | Least-privilege roles |
| Logging raw bound values | PII/secret leakage | Query IDs, redaction, log TTL |
| Unbounded `LIMIT` and concurrency | RAM, I/O, query DoS | Validation, rate limits, backpressure |

### 14.1. Validating Regex Is a Secondary Layer, Not a Security Contract

If a system genuinely creates many physical identifiers provisioned by the platform, you may add syntax validation like `^[a-z][a-z0-9_]{0,47}$`. Still, that limit is only an **application convention**—it neither reflects Cassandra's full naming grammar nor replaces:

- Approved tenant → keyspace mapping.
- List of authorized tables/columns.
- Query schema compatibility.
- Role or principal authorization.

When choices are few, **fixed enums/templates are far easier to audit than regex + string concatenation**.

## 15. Runbook: Suspected Client Control of Identifiers or Query Fragments

**Scenario:** Logs reveal requests passing strange `dataset` values, rising syntax errors, and abnormal query throughput. Operations suspects an API is concatenating raw table names or `WHERE` fragments.

### Step 1 — Scope the Issue

Collect the API route, relevant commits/deploys, query IDs, Cassandra role used, UTC timestamps, syntax/error/timeout rates, and affected keyspaces/tables. **Never put raw tokens or sensitive data in public tickets/logs.**

### Step 2 — Inspect Code Paths

Search for query text built from untrusted input:

~~~text
"FROM " + ...
"WHERE " + ...
"ORDER BY " + ...
"LIMIT " + ...
session.prepare(dynamicCql)
session.execute(dynamicCql)
~~~

These are **review heuristics**, not a rule that all concatenation is broken. Concatenating **allowlisted constants** can be valid; concatenating request input is not.

### Step 3 — Contain Impact Immediately

Depending on severity, temporarily disable the endpoint, restrict to known operations, tighten rate limits, narrow role permissions, or roll back the deployment per incident procedure. Never test weird payloads directly on real data "to see if `DROP` works."

### Step 4 — Migrate to Fixed Templates + Binding

- Design query shapes around schema/partition keys.
- Move all values to prepared/bound statements.
- Move table/column/sort choices to enums/allowlists.
- Bind tenant identity from the authenticated principal.
- Add limit/range validation and backpressure.

### Step 5 — Test and Observe

Run unit/integration tests in an isolated environment; test special characters, disallowed choices, and boundary limits. Verify syntax errors drop, logs leak no data, valid queries stay accurate, and p99/timeouts do not degrade.

### Step 6 — Post-Incident Investigation

Review audit/driver/server logs per version capabilities, verify Cassandra account permissions, inspect anomalous schema/data actions, and rotate credentials if exposure is indicated. **Do not infer successful exploitation solely from an injection-like string**; require verifiable evidence.

## 16. Self-Check Exercises

### Question 1 — Can a Bind Parameter Replace a Table Name?

An application wants to use `FROM ?` and bind a table name sent by the caller. Is this valid?

**Answer:** No. Bind markers only work in supported value positions; table names are structural identifiers. Use an allowlist mapping to approved tables/query templates.

### Question 2 — Does `prepare` Sanitize a Raw String?

Code concatenates `rawName` into `WHERE name = '...'` and then calls `session.prepare(cql)`. Is it protected against injection?

**Answer:** No. The CQL string was already built from untrusted input before `prepare`. Put `?` markers in the template and bind values separately.

### Question 3 — Regex Checking Table Names

The name `financial_reports` matches `[a-z_]+`. Is that enough for a caller to `SELECT` that table?

**Answer:** No. Regex validates format only, not authorization or access-pattern validity. You need an allowlist and authorization.

### Question 4 — Multi-Tenant

A request from tenant A sets `tenantId=B`, yet both are valid UUIDs and bound properly. Is it safe?

**Answer:** No. Binding prevents injection, not cross-tenant access. The backend must derive the tenant from the authenticated principal or check explicit permissions.

### Question 5 — Dynamic Sorting

The client picks "oldest" or "newest." Should raw `orderBy` be concatenated into CQL?

**Answer:** No. Use an enum to select between two prepared statements containing valid `ORDER BY event_time ASC` or `DESC`; the column must fit the clustering schema.

### Question 6 — `LIMIT`

The limit input is bound, with value 10,000,000. Is the query guaranteed performance-safe?

**Answer:** No. Binding prevents syntax tampering but does not cap load. Enforce API upper bounds, page sizes, query shapes, and rate limits.

### Question 7 — Typical SQL Payloads

An SQL attack string containing `UNION SELECT` triggers a Cassandra syntax error. Can we conclude the raw-concatenated CQL code is safe?

**Answer:** No. CQL grammar differs from SQL; one rejected payload does not prove all inputs are safe. Inspect query structure, binding, and allowlists.

### Question 8 — Over-Privileged Role

An event-reading API connects to Cassandra using a role with cluster-wide schema-change permissions. Do bind parameters sufficiently reduce risk?

**Answer:** No. Enforce least-privilege authorization and separate read-API accounts from migration/admin accounts.

### Question 9 — Storing Text Containing Quotes

Valid text input contains `'`, semicolons, and newlines. Must all those characters be stripped before storing?

**Answer:** No, if the data is business-valid. Use bind parameters so the driver encodes the value intact; validation should only enforce genuinely needed formats/sizes.

### Question 10 — Query Missing Partition Key

An API uses safe prepared statements but includes `ALLOW FILTERING`, running broad queries under high concurrency. Is this an issue to address?

**Answer:** Yes. While not traditional injection, it poses resource/DoS risk. Design proper access patterns, cap concurrency, and review schema/indexes.

### Question 11 — Dynamic Column Updates

An API accepts a JSON map able to update any column of a table. Is binding values enough for security?

**Answer:** No. Column names and editable fields must be allowlisted by role and mapped to specific `UPDATE` templates, alongside type, TTL, and business-rule validation.

### Question 12 — Logging Full Query Text

A team logs every interpolated CQL query including customer IDs and tokens. Is this a good choice for error tracing?

**Answer:** No. It risks exposing sensitive information. Log query IDs, outcomes, latencies, DC/CL, and sanitized metadata; use controlled tracing only when needed.

## 17. Pre-Production Review Checklist for a Cassandra API

~~~text
[ ] Zero raw request data concatenated into CQL syntax.
[ ] SELECT/INSERT/UPDATE/DELETE use valid prepared/bound values.
[ ] Keyspace, table, column, ORDER BY, operators, and WHERE shape are fixed
    or mapped from a server-side allowlist/enum.
[ ] No client-defined ALLOW FILTERING or arbitrary CQL fragments.
[ ] Query shapes match partition-key/clustering schema and are benchmarked.
[ ] UUIDs, dates, numeric ranges, LIMIT/page size, and payload sizes validated.
[ ] Tenant ID derived from authenticated principal or explicitly authorized.
[ ] Cassandra role holds only least privileges needed by the API.
[ ] Authentication, TLS, secrets, and access controls configured per policy.
[ ] No raw bind values/PII logged; metrics tags have bounded cardinality.
[ ] Prepared statements reused from a finite template set.
[ ] Negative tests reject out-of-allowlist identifiers/operations.
[ ] Integration tests run in an isolated environment, never production.
[ ] Rate limits, concurrency, and timeouts prevent resource exhaustion.
[ ] Timeouts/retries follow policy without causing duplicate side effects.
[ ] Audits and incident runbooks can detect unauthorized queries.
~~~

This checklist does not prove an entire application is secure; it specifies criteria for **CQL construction boundaries** and data access rights. Other security controls—secret rotation, network segmentation, encryption at rest, backup protection, and patching—must be managed per system standards.

## 18. Summary

**CQL injection is prevented primarily by never turning untrusted input into query syntax.** With Cassandra and the Java Driver:

1. **Keep query structure fixed; bind all variable values** via prepared/bound statements.
2. **Bind markers cannot replace identifiers** such as keyspaces/tables/columns, `ORDER BY`, operators, or `WHERE` fragments.
3. **Dynamic identifiers must be allowlisted**, ideally mapping business codes or enums to a finite template set.
4. **Regex/quoting is not authorization**: a syntactically valid name can still point to out-of-scope data.
5. **Tenant isolation must check caller identity**, never trusting a tenant ID taken straight from the request even when bound.
6. **Prepared statements do not replace validation**: bound `LIMIT`, row sizes, ranges, concurrency, TTL, and query the full partition key.
7. **Least-privilege RBAC, TLS, and safe logging** contain blast radius when application bugs occur.
8. **Test negative cases** before deploying, and investigate suspicious inputs only in authorized, isolated environments.

During code reviews, ask: **"Which part of this CQL statement is defined by the application itself, which part is bound data, and who is allowed to choose among the permitted query shapes?"** When those three boundaries are explicit in code, the risk of CQL injection and cross-tenant data exposure drops dramatically while making Cassandra easier to tune and audit.
